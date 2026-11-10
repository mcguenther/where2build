"""A rebuilt index or price list reaches the running backend without a restart.

The scheduler rebuilds the POI and address indexes quarterly and the price
list monthly, in a container of its own. Before ``app/reloading.py`` the
backend kept whatever it had read at startup until somebody restarted it.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from app.reloading import FileBacked

FIXTURES = Path(__file__).parent / "fixtures"


def _replace(path: Path, text: str, *, bump: int = 1) -> None:
    """Write as the builders do -- beside the target, then rename -- and make
    sure the modification time moves even on a coarse file system."""

    before = path.stat().st_mtime_ns if path.exists() else 0
    part = path.with_name(path.name + ".part")
    part.write_text(text, encoding="utf-8")
    part.replace(path)
    stamp = before + bump * 1_000_000_000
    os.utime(path, ns=(stamp, stamp))


def _counting_loader(path: Path):
    calls = []

    def load():
        calls.append(1)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    return load, calls


def test_an_unchanged_file_is_read_once(tmp_path: Path):
    target = tmp_path / "index.json"
    target.write_text('{"v": 1}', encoding="utf-8")
    load, calls = _counting_loader(target)
    source = FileBacked([target], load, check_every=0)

    for _ in range(5):
        assert source.get() == {"v": 1}
    assert len(calls) == 1


def test_a_replaced_file_is_read_again(tmp_path: Path):
    target = tmp_path / "index.json"
    target.write_text('{"v": 1}', encoding="utf-8")
    load, calls = _counting_loader(target)
    source = FileBacked([target], load, check_every=0)
    assert source.get() == {"v": 1}

    _replace(target, '{"v": 2}')

    assert source.get() == {"v": 2}
    assert len(calls) == 2


def test_a_broken_rebuild_keeps_the_previous_value_until_it_is_fixed(tmp_path: Path):
    target = tmp_path / "index.json"
    target.write_text('{"v": 1}', encoding="utf-8")
    load, calls = _counting_loader(target)
    source = FileBacked([target], load, check_every=0)
    assert source.get() == {"v": 1}

    _replace(target, "{kaputt")
    assert source.get() == {"v": 1}
    assert source.error
    # The broken file is not parsed again on every request.
    source.get()
    assert len(calls) == 2

    _replace(target, '{"v": 3}', bump=2)
    assert source.get() == {"v": 3}
    assert source.error is None


def test_a_broken_file_at_startup_reads_as_not_built(tmp_path: Path):
    target = tmp_path / "index.json"
    target.write_text("{kaputt", encoding="utf-8")
    load, _ = _counting_loader(target)
    source = FileBacked([target], load, check_every=0)

    assert source.get() is None
    assert source.error


def test_an_index_built_after_startup_is_picked_up(tmp_path: Path):
    target = tmp_path / "index.json"
    load, _ = _counting_loader(target)
    source = FileBacked([target], load, check_every=0)
    assert source.get() is None

    _replace(target, '{"v": 1}')

    assert source.get() == {"v": 1}


def test_a_deleted_file_reads_as_not_built(tmp_path: Path):
    target = tmp_path / "index.json"
    target.write_text('{"v": 1}', encoding="utf-8")
    load, _ = _counting_loader(target)
    source = FileBacked([target], load, check_every=0)
    assert source.get() == {"v": 1}

    target.unlink()

    assert source.get() is None


def test_between_two_checks_no_file_is_touched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import app.reloading as reloading

    clock = [100.0]
    monkeypatch.setattr(reloading.time, "monotonic", lambda: clock[0])
    target = tmp_path / "index.json"
    target.write_text('{"v": 1}', encoding="utf-8")
    load, _ = _counting_loader(target)
    source = FileBacked([target], load, check_every=10)
    assert source.get() == {"v": 1}

    _replace(target, '{"v": 2}')
    clock[0] += 5
    assert source.get() == {"v": 1}
    clock[0] += 6
    assert source.get() == {"v": 2}


def test_a_second_file_counts_too(tmp_path: Path):
    committed, refreshed = tmp_path / "a.json", tmp_path / "b.json"
    committed.write_text("1", encoding="utf-8")
    source = FileBacked(
        [committed, refreshed],
        lambda: [p.read_text() for p in (committed, refreshed) if p.is_file()],
        check_every=0,
    )
    assert source.get() == ["1"]

    _replace(refreshed, "2")

    assert source.get() == ["1", "2"]


# -- through the real services ----------------------------------------------


def test_a_rebuilt_poi_index_reaches_the_nearby_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.deps import nearby_service, reset_services

    target = tmp_path / "poi_index.json"
    shutil.copy(FIXTURES / "poi_index.json", target)
    monkeypatch.setenv("NEARBY_POI_INDEX_PATH", str(target))
    reset_services()
    service = nearby_service()
    service._source.check_every = 0
    assert service.index.datenstand == "2026-08-22T20:21:02Z"

    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["datenstand"] = "2026-11-01T04:20:00Z"
    _replace(target, json.dumps(payload))

    assert service.index.datenstand == "2026-11-01T04:20:00Z"
    assert service.index_status()["datenstand"] == "2026-11-01T04:20:00Z"
    reset_services()


def test_the_monthly_price_job_reaches_the_cost_column(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.deps import llm_prices, price_source, reset_services

    committed = Path(__file__).resolve().parents[2] / "ops" / "llm-preise.json"
    refreshed = tmp_path / "preisliste" / "llm-preise.json"
    refreshed.parent.mkdir()
    monkeypatch.setenv("LLM_PRICES_PATH", str(committed))
    monkeypatch.setenv("LLM_PRICES_UPDATE_PATH", str(refreshed))
    reset_services()
    price_source().check_every = 0
    before = llm_prices()
    assert before.usable

    newer = json.loads(committed.read_text(encoding="utf-8"))
    newer["stand"] = "2099-01-01T00:00:00+00:00"
    _replace(refreshed, json.dumps(newer))

    after = llm_prices()
    assert after.stand == "2099-01-01T00:00:00+00:00"
    assert after is not before
    reset_services()
