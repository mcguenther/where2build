"""Cache behaviour: expiry, permanence, and surviving broken entries."""

from __future__ import annotations

from pathlib import Path

from app.cache import DiskCache, MemoryCache


def test_memory_cache_returns_a_value_until_it_expires():
    now = [1000.0]
    cache = MemoryCache(ttl_s=60, clock=lambda: now[0])

    cache.set("a", 42)
    assert cache.get("a") == 42

    now[0] += 59
    assert cache.get("a") == 42

    now[0] += 2
    assert cache.get("a") is None
    assert len(cache) == 0


def test_disk_cache_round_trips_bytes_and_json(tmp_path: Path):
    cache = DiskCache(tmp_path / "c")

    cache.set_bytes("key", b"binary")
    cache.set_json("other", {"wert": 1})

    assert cache.get_bytes("key") == b"binary"
    assert cache.get_json("other") == {"wert": 1}
    assert cache.get_bytes("missing") is None


def test_disk_cache_without_a_ttl_keeps_entries(tmp_path: Path):
    cache = DiskCache(tmp_path / "c", ttl_s=None)
    cache.set_json("haustyp", {"bebaute_flaeche_m2": 96.88})

    # A second handle on the same directory sees the same entry.
    assert DiskCache(tmp_path / "c", ttl_s=None).get_json("haustyp")["bebaute_flaeche_m2"] == 96.88


def test_disk_cache_expires_entries(tmp_path: Path, monkeypatch):
    cache = DiskCache(tmp_path / "c", ttl_s=10)
    cache.set_bytes("key", b"x")

    import app.cache as cache_module

    monkeypatch.setattr(cache_module.time, "time", lambda: 10**10)
    assert cache.get_bytes("key") is None


def test_broken_entry_is_treated_as_a_miss(tmp_path: Path):
    cache = DiskCache(tmp_path / "c")
    cache.set_bytes("key", b"{not json")

    assert cache.get_json("key") is None


def test_clear_removes_everything(tmp_path: Path):
    cache = DiskCache(tmp_path / "c")
    cache.set_bytes("key", b"x")

    cache.clear()

    assert cache.get_bytes("key") is None
