"""Small caches with a TTL: one in memory, one on disk.

Caching is not an optimisation here but a requirement: a parcel polygon does
not change between two page views, a house type does not change weekly, and
every LLM fetch costs money.

The disk cache also has a ceiling. It is not per cache but one budget for the
whole cache directory, because what actually runs out is the volume the
directory lives on, and eight separate limits would still not bound the sum.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

logger = logging.getLogger(__name__)

# The ceiling for the whole cache directory. Wired through
# AppSettings.cache_max_bytes; until a caller passes one, this is what applies.
DEFAULT_MAX_BYTES = 100 * 1024 * 1024

# A sweep clears down to this fraction of the ceiling rather than to the
# ceiling itself, so a full cache does not sweep on every single write.
_LOW_WATER = 0.9

# Bytes that may be written between two size checks, as a fraction of the
# ceiling. Walking the tree on every write would make a cache hit cheaper than
# a cache write by orders of magnitude; this keeps the walk rare and still
# cannot overshoot the ceiling by more than this much.
_WRITE_BUDGET = 0.05

# How long a half-written entry is left alone. Long enough that no live writer
# is ever swept away, short enough that a crashed one does not stay forever.
_TEMP_GRACE_S = 3600.0

# Entries are named after a SHA-256 digest; anything else in the tree is not
# ours to delete.
_ENTRY_NAME = re.compile(r"^[0-9a-f]{64}$")
_TEMP_SUFFIX = ".tmp"

# Which caches give up their space first. The tree holds answers of wildly
# different cost: a basemap tile is about 1 MB, immutable, and one request away
# from any tile server, while a BORIS land value is a few hundred bytes,
# changes once a year and costs a slow round trip to an authority -- and an LLM
# extraction costs money and has no TTL at all. Least-recently-used over the
# whole tree would evict the small expensive answers to make room for large
# cheap ones, which is exactly backwards, so eviction goes by tier first and
# only reaches the expensive caches if clearing the cheap ones was not enough.
# Within a tier the oldest entry goes first, by mtime and not by last read:
# freshness is computed from mtime, so touching an entry on a hit would also
# reset its TTL and keep a hot answer alive long past the point where it should
# have been refetched.
_EVICTION_TIERS = {
    "basemap": 0,
    "tiles": 0,
    # One small public document, one fast request from the provider. It frees
    # almost nothing, and holding on to it buys almost nothing either.
    "oidc": 0,
    "motis": 1,
    "motis-stops": 1,
    "motis-matrix": 1,
    "overpass": 1,
    "alkis": 2,
    "boris": 2,
    "llm": 2,
}
_UNKNOWN_TIER = 1
_EXPIRED_TIER = -1


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class MemoryCache:
    """Process-local cache with a per-entry expiry."""

    def __init__(self, ttl_s: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.ttl_s = ttl_s
        self._clock = clock
        self._entries: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at <= self._clock():
                del self._entries[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl_s: float | None = None) -> None:
        with self._lock:
            self._entries[key] = (self._clock() + (ttl_s if ttl_s is not None else self.ttl_s), value)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


@dataclass(frozen=True)
class SweepResult:
    """What one sweep of a cache directory did."""

    directory: Path
    limit_bytes: int
    bytes_before: int
    bytes_after: int
    entries_before: int
    entries_removed: int
    temp_files_removed: int

    @property
    def bytes_removed(self) -> int:
        return self.bytes_before - self.bytes_after


@dataclass(frozen=True)
class _Entry:
    path: Path
    size: int
    mtime: float
    tier: int


class CacheSweeper:
    """One size budget for every :class:`DiskCache` under the same directory.

    Instances register themselves so the sweep knows each cache's TTL and can
    drop entries that have expired before it evicts anything still valid.
    """

    def __init__(self, directory: Path | str, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
        self.directory = Path(directory)
        self.max_bytes = int(max_bytes)
        self._ttls: dict[str, float | None] = {}
        self._unswept_bytes = 0
        self._lock = threading.Lock()
        self._sweep_lock = threading.Lock()

    def register(self, name: str, ttl_s: float | None) -> None:
        with self._lock:
            self._ttls[name] = ttl_s

    def note_write(self, n_bytes: int) -> SweepResult | None:
        """Account for a written entry and sweep once enough has accumulated."""

        with self._lock:
            self._unswept_bytes += n_bytes
            due = self._unswept_bytes >= max(1, int(self.max_bytes * _WRITE_BUDGET))
            if due:
                self._unswept_bytes = 0
        return self.sweep() if due else None

    def sweep(self, dry_run: bool = False) -> SweepResult:
        with self._sweep_lock:
            return self._sweep(dry_run)

    def _sweep(self, dry_run: bool = False) -> SweepResult:
        now = time.time()
        with self._lock:
            ttls = dict(self._ttls)

        entries: list[_Entry] = []
        total = 0
        temp_removed = 0
        for path, name, stat in self._walk():
            if name.endswith(_TEMP_SUFFIX):
                # A rename is atomic, so a temp file is either a write still in
                # flight -- which must survive -- or the debris of one that
                # died. Age is what tells them apart.
                if now - stat.st_mtime > _TEMP_GRACE_S and (dry_run or _unlink(path)):
                    temp_removed += 1
                continue
            if not _ENTRY_NAME.match(name):
                continue
            cache_name = self._cache_name(path)
            ttl = ttls.get(cache_name)
            expired = ttl is not None and (now - stat.st_mtime) >= ttl
            tier = _EXPIRED_TIER if expired else _EVICTION_TIERS.get(cache_name, _UNKNOWN_TIER)
            entries.append(_Entry(path, stat.st_size, stat.st_mtime, tier))
            total += stat.st_size

        before = total
        count_before = len(entries)
        removed = 0
        # The selection runs in both modes: a dry run that skipped it reported
        # "nothing would go" however far over the ceiling the tree was, which is
        # the opposite of what the mode is for -- it is the one an operator uses
        # to decide whether to switch the job on at all.
        if total > self.max_bytes:
            target = int(self.max_bytes * _LOW_WATER)
            entries.sort(key=lambda e: (e.tier, e.mtime))
            for entry in entries:
                if total <= target:
                    break
                # Deleting an entry a request is reading is harmless -- the
                # reader already holds the open file -- and a writer replacing
                # it renames a complete file over the gap.
                if dry_run or _unlink(entry.path):
                    total -= entry.size
                    removed += 1

        return SweepResult(
            directory=self.directory,
            limit_bytes=self.max_bytes,
            bytes_before=before,
            bytes_after=total,
            entries_before=count_before,
            entries_removed=removed,
            temp_files_removed=temp_removed,
        )

    def _cache_name(self, path: Path) -> str:
        """The cache an entry belongs to: the first path element below the root."""

        try:
            return path.relative_to(self.directory).parts[0]
        except (ValueError, IndexError):
            return ""

    def _walk(self) -> Iterator[tuple[Path, str, os.stat_result]]:
        for parent, _dirs, files in os.walk(self.directory, onerror=lambda _e: None):
            for name in files:
                path = Path(parent) / name
                try:
                    yield path, name, path.stat()
                except OSError:
                    continue


def _unlink(path: Path) -> bool:
    try:
        path.unlink()
        return True
    except OSError:
        return False


_sweepers: dict[Path, CacheSweeper] = {}
_sweepers_lock = threading.Lock()


def get_sweeper(directory: Path | str, max_bytes: int | None = None) -> CacheSweeper:
    """The sweeper for one cache directory, shared by every cache below it.

    A newly created one sweeps immediately: a deployment that was over the
    ceiling when it stopped must not stay over it until the next write.
    """

    key = Path(directory).absolute()
    with _sweepers_lock:
        sweeper = _sweepers.get(key)
        if sweeper is not None:
            if max_bytes is not None:
                sweeper.max_bytes = int(max_bytes)
            return sweeper
        sweeper = CacheSweeper(key, DEFAULT_MAX_BYTES if max_bytes is None else int(max_bytes))
        _sweepers[key] = sweeper
    if key.is_dir():
        sweeper.sweep()
    return sweeper


class DiskCache:
    """File-backed cache. ``ttl_s=None`` keeps entries forever.

    Forever is the right setting for LLM extractions keyed by normalised URL --
    the spec asks for exactly that. The size ceiling applies regardless: the
    sweeper is shared with every other cache in the same parent directory.
    """

    def __init__(
        self,
        directory: Path | str,
        ttl_s: float | None = None,
        max_bytes: int | None = None,
    ) -> None:
        self.directory = Path(directory)
        self.ttl_s = ttl_s
        self.sweeper = get_sweeper(self.directory.parent, max_bytes)
        self.sweeper.register(self.directory.name, ttl_s)
        # Said once, not once per write: a wrong path would otherwise turn a
        # warning into the thing that fills the disk.
        self._write_failed = False

    def _path(self, key: str) -> Path:
        digest = _digest(key)
        return self.directory / digest[:2] / digest

    def _fresh(self, path: Path) -> bool:
        if not path.is_file():
            return False
        if self.ttl_s is None:
            return True
        return (time.time() - path.stat().st_mtime) < self.ttl_s

    def has(self, key: str) -> bool:
        """Whether ``get_bytes`` would answer, without reading the file."""

        return self._fresh(self._path(key))

    def get_bytes(self, key: str) -> bytes | None:
        path = self._path(key)
        if not self._fresh(path):
            return None
        try:
            return path.read_bytes()
        except OSError:
            return None

    def set_bytes(self, key: str, value: bytes) -> None:
        """Keep an answer, or do not. Never fail the request over it.

        `get_bytes` has always swallowed an OSError and this did not, which is
        the wrong way round: a cache that cannot read is slow, and a cache that
        cannot *write* is slow too. Measured 19.09.2026 in the compose stack --
        the backend runs as an unprivileged user and its cache directory was
        not the one the volume is mounted at, so every single
        `/api/listings/extract` answered 500 with a PermissionError on `.cache`
        *after* the model had already answered. The work was done and paid for
        and thrown away because storing it failed.

        Said once per directory. A warning per write turns a wrong path into a
        full disk.
        """

        path = self._path(key)
        tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}{_TEMP_SUFFIX}")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write-then-rename so a reader never sees a half-written entry,
            # and under a name of its own so two writers of the same key cannot
            # end up renaming each other's half-written file into place.
            tmp.write_bytes(value)
            tmp.replace(path)
        except OSError as exc:
            _unlink(tmp)
            if not self._write_failed:
                self._write_failed = True
                logger.warning(
                    "Cache %s ist nicht beschreibbar (%s) — die Antworten werden "
                    "weiter geliefert, aber jede kostet den Dienst erneut.",
                    self.directory,
                    exc,
                )
            return
        self.sweeper.note_write(len(value))

    def get_json(self, key: str) -> Any | None:
        raw = self.get_bytes(key)
        if raw is None:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def set_json(self, key: str, value: Any) -> None:
        self.set_bytes(key, json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))

    def clear(self) -> None:
        if self.directory.exists():
            shutil.rmtree(self.directory, ignore_errors=True)


def _format_bytes(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB"


def main(argv: list[str] | None = None) -> int:
    """Sweep a cache directory from the command line.

    This is what the ``cache-sweep`` job runs. It reads APP_CACHE_MAX_BYTES
    directly rather than through Settings, which is the same environment
    variable the setting will carry, so the two cannot disagree.
    """

    parser = argparse.ArgumentParser(
        prog="python -m app.cache",
        description="Sweep the disk cache back under its size ceiling.",
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=os.environ.get("APP_CACHE_DIR", ".cache"),
        help="Cache root. Defaults to APP_CACHE_DIR, or .cache.",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=int(os.environ.get("APP_CACHE_MAX_BYTES", DEFAULT_MAX_BYTES)),
        help="Ceiling in bytes. Defaults to APP_CACHE_MAX_BYTES, or 100 MB.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report the size, delete nothing.")
    parser.add_argument("--json", action="store_true", help="Machine-readable output.")
    args = parser.parse_args(argv)

    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"No cache directory at {directory} — nothing to sweep.")
        return 0

    # A sweep run from the command line knows nothing of the TTLs the services
    # configure, so it evicts by tier and age alone. That is not wrong, only
    # less informed: an expired entry would have gone first, and now goes with
    # the rest of its tier.
    result = CacheSweeper(directory, args.max_bytes).sweep(dry_run=args.dry_run)

    if args.json:
        print(
            json.dumps(
                {
                    "directory": str(result.directory),
                    "limit_bytes": args.max_bytes,
                    "bytes_before": result.bytes_before,
                    "bytes_after": result.bytes_after,
                    "entries_before": result.entries_before,
                    "entries_removed": result.entries_removed,
                    "temp_files_removed": result.temp_files_removed,
                }
            )
        )
    else:
        print(
            f"{result.directory}: {_format_bytes(result.bytes_before)} in "
            f"{result.entries_before} entries, limit {_format_bytes(args.max_bytes)}"
        )
        if args.dry_run:
            over = result.bytes_before - args.max_bytes
            print("over by " + _format_bytes(over) if over > 0 else "under the limit")
        else:
            print(
                f"removed {result.entries_removed} entries "
                f"({_format_bytes(result.bytes_removed)}) and "
                f"{result.temp_files_removed} stale temp files, "
                f"now {_format_bytes(result.bytes_after)}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
