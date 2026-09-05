"""The disk cache stays under its size ceiling.

The ceiling is one budget for the whole cache directory, and eviction is by
tier before age: the large cheap caches give up their space before the small
expensive ones. See ``app/cache.py``.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from app.cache import CacheSweeper, DiskCache, main


def write_entry(root: Path, cache: str, key: str, size: int, age_s: float = 0.0) -> Path:
    """Put a file where the cache itself would put it, without going through it."""

    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    path = root / cache / digest[:2] / digest
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    if age_s:
        stamp = time.time() - age_s
        os.utime(path, (stamp, stamp))
    return path


def tree_bytes(root: Path) -> int:
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def test_sweep_brings_an_over_full_cache_under_the_ceiling(tmp_path: Path):
    root = tmp_path / "cache"
    for i in range(30):
        write_entry(root, "tiles", f"tile-{i}", 10_000, age_s=100 - i)

    before = tree_bytes(root)
    result = CacheSweeper(root, max_bytes=100_000).sweep()

    assert before == 300_000
    assert result.bytes_before == before
    assert result.bytes_after <= 100_000
    assert tree_bytes(root) == result.bytes_after
    assert result.entries_removed > 0


def test_a_cache_under_the_ceiling_is_left_alone(tmp_path: Path):
    root = tmp_path / "cache"
    write_entry(root, "tiles", "one", 10_000)

    result = CacheSweeper(root, max_bytes=100_000).sweep()

    assert result.entries_removed == 0
    assert tree_bytes(root) == 10_000


def test_the_cheap_large_cache_is_evicted_before_the_expensive_small_one(tmp_path: Path):
    """A BORIS land value costs a round trip to an authority and changes yearly;
    a basemap tile is one request away. Age alone would evict them together."""

    root = tmp_path / "cache"
    boris = [write_entry(root, "boris", f"brw-{i}", 1_000, age_s=10_000) for i in range(10)]
    tiles = [write_entry(root, "basemap", f"tile-{i}", 20_000, age_s=1) for i in range(10)]

    CacheSweeper(root, max_bytes=100_000).sweep()

    assert all(p.is_file() for p in boris)
    assert sum(1 for p in tiles if p.is_file()) < 10


def test_expired_entries_go_before_anything_still_valid(tmp_path: Path):
    root = tmp_path / "cache"
    sweeper = CacheSweeper(root, max_bytes=60_000)
    # The TTL a DiskCache registers is what makes an entry expired, not its age.
    sweeper.register("motis", 3600)
    fresh = [write_entry(root, "motis", f"plan-{i}", 5_000, age_s=1) for i in range(10)]
    stale = [write_entry(root, "motis", f"old-{i}", 10_000, age_s=7200) for i in range(10)]

    sweeper.sweep()

    assert not any(p.is_file() for p in stale)
    assert all(p.is_file() for p in fresh)


def test_a_write_in_flight_survives_the_sweep(tmp_path: Path):
    root = tmp_path / "cache"
    entry = write_entry(root, "tiles", "any", 10)
    in_flight = entry.with_name(entry.name + ".deadbeef.tmp")
    in_flight.write_bytes(b"half")

    result = CacheSweeper(root, max_bytes=1).sweep()

    assert in_flight.is_file()
    assert result.temp_files_removed == 0
    # And the entry it was replacing is what got evicted, not the half-file.
    assert not entry.is_file()


def test_debris_from_a_dead_writer_is_removed(tmp_path: Path):
    root = tmp_path / "cache"
    entry = write_entry(root, "tiles", "any", 10)
    debris = entry.with_name(entry.name + ".deadbeef.tmp")
    debris.write_bytes(b"half")
    stamp = time.time() - 4 * 3600
    os.utime(debris, (stamp, stamp))

    result = CacheSweeper(root, max_bytes=100_000).sweep()

    assert not debris.exists()
    assert result.temp_files_removed == 1


def test_files_that_are_not_cache_entries_are_neither_counted_nor_deleted(tmp_path: Path):
    root = tmp_path / "cache"
    root.mkdir()
    stray = root / "README"
    stray.write_bytes(b"y" * 50_000)

    result = CacheSweeper(root, max_bytes=1).sweep()

    assert stray.is_file()
    assert result.bytes_before == 0


def test_writing_past_the_ceiling_sweeps_without_being_asked(tmp_path: Path):
    root = tmp_path / "cache"
    cache = DiskCache(root / "tiles", ttl_s=3600, max_bytes=100_000)

    for i in range(40):
        cache.set_bytes(f"tile-{i}", b"x" * 10_000)

    # 400 kB written into a 100 kB cache, and nobody called sweep().
    assert tree_bytes(root) <= 100_000
    assert cache.get_bytes("tile-39") == b"x" * 10_000


def test_a_cache_over_the_ceiling_at_startup_is_swept(tmp_path: Path):
    """The deployment stopped while over the limit. Nothing writes for hours."""

    root = tmp_path / "cache"
    for i in range(30):
        write_entry(root, "tiles", f"tile-{i}", 10_000, age_s=100 - i)
    assert tree_bytes(root) == 300_000

    DiskCache(root / "tiles", ttl_s=3600, max_bytes=100_000)

    assert tree_bytes(root) <= 100_000


def test_every_cache_below_one_root_shares_the_budget(tmp_path: Path):
    root = tmp_path / "cache"
    tiles = DiskCache(root / "tiles", ttl_s=3600, max_bytes=100_000)
    basemap = DiskCache(root / "basemap", ttl_s=3600, max_bytes=100_000)

    assert tiles.sweeper is basemap.sweeper

    for i in range(20):
        tiles.set_bytes(f"t-{i}", b"x" * 10_000)
        basemap.set_bytes(f"b-{i}", b"x" * 10_000)

    assert tree_bytes(root) <= 100_000


def test_a_half_written_entry_is_never_readable_as_a_hit(tmp_path: Path):
    root = tmp_path / "cache"
    cache = DiskCache(root / "tiles", ttl_s=3600)
    cache.set_bytes("key", b"complete")

    path = cache._path("key")
    path.with_name(path.name + ".abc123.tmp").write_bytes(b"trunc")

    assert cache.get_bytes("key") == b"complete"


def test_the_command_line_sweep_reports_what_it_did(tmp_path: Path, capsys):
    root = tmp_path / "cache"
    for i in range(30):
        write_entry(root, "tiles", f"tile-{i}", 10_000, age_s=100 - i)

    assert main([str(root), "--max-bytes", "100000", "--json"]) == 0
    import json

    report = json.loads(capsys.readouterr().out)
    assert report["bytes_before"] == 300_000
    assert report["bytes_after"] <= 100_000
    assert report["entries_removed"] > 0


def test_a_dry_run_deletes_nothing(tmp_path: Path, capsys):
    root = tmp_path / "cache"
    for i in range(30):
        write_entry(root, "tiles", f"tile-{i}", 10_000)

    assert main([str(root), "--max-bytes", "100000", "--dry-run"]) == 0
    capsys.readouterr()

    assert tree_bytes(root) == 300_000


def test_a_dry_run_reports_what_would_go(tmp_path: Path):
    """The defect this pins: the selection was skipped under dry_run, so the
    report said "nothing would be removed" however far over the ceiling the
    tree was -- in the one mode an operator uses to decide whether to switch
    the job on."""

    root = tmp_path / "cache"
    for i in range(30):
        write_entry(root, "tiles", f"tile-{i}", 10_000)

    planned = CacheSweeper(root, max_bytes=100_000).sweep(dry_run=True)
    assert planned.entries_removed > 0
    assert planned.bytes_after <= 100_000
    assert planned.bytes_before == 300_000
    # And still only a plan.
    assert tree_bytes(root) == 300_000

    done = CacheSweeper(root, max_bytes=100_000).sweep()
    assert (done.entries_removed, done.bytes_after) == (planned.entries_removed, planned.bytes_after)
    assert tree_bytes(root) == done.bytes_after


def test_a_missing_cache_directory_is_not_an_error(tmp_path: Path, capsys):
    assert main([str(tmp_path / "nothing-here")]) == 0
    assert "nothing to sweep" in capsys.readouterr().out
