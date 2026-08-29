"""Small caches with a TTL: one in memory, one on disk.

Caching is not an optimisation here but a requirement: a parcel polygon does
not change between two page views, a house type does not change weekly, and
every LLM fetch costs money.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Callable


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


class DiskCache:
    """File-backed cache. ``ttl_s=None`` keeps entries forever.

    Forever is the right setting for LLM extractions keyed by normalised URL --
    the spec asks for exactly that.
    """

    def __init__(self, directory: Path | str, ttl_s: float | None = None) -> None:
        self.directory = Path(directory)
        self.ttl_s = ttl_s

    def _path(self, key: str) -> Path:
        digest = _digest(key)
        return self.directory / digest[:2] / digest

    def _fresh(self, path: Path) -> bool:
        if not path.is_file():
            return False
        if self.ttl_s is None:
            return True
        return (time.time() - path.stat().st_mtime) < self.ttl_s

    def get_bytes(self, key: str) -> bytes | None:
        path = self._path(key)
        if not self._fresh(path):
            return None
        try:
            return path.read_bytes()
        except OSError:
            return None

    def set_bytes(self, key: str, value: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write-then-rename so a reader never sees a half-written entry.
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(value)
        tmp.replace(path)

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
