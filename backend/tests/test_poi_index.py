"""The local POI index and the build step that produces it."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.poi_index import (
    PoiEntry,
    PoiIndex,
    classify_school,
    deduplicate,
    haversine_m,
    load_index,
)

from .conftest import FIXTURES

BACKEND = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Schule Liebertwolkwitz - Grundschule der Stadt Leipzig", "Grundschule"),
        ("Geschwister Scholl Schule Liebertwolkwitz - Oberschule der Stadt Leipzig", "Oberschule"),
        ("102. Grundschule „Johanna“", "Grundschule"),
        ("Bertolt-Brecht-Gymnasium", "Gymnasium"),
        ('Berufliches Schulzentrum für Technik "Gustav Anton Zeuner"', "Berufliche Schule"),
        ("Förderschule für Lernbehinderte", "Förderschule"),
        ("Freie Waldorfschule Leipzig", "Freie Schule"),
        # No Saxon OSM tag carries the school type, and not every name does
        # either. Guessing would be worse than saying nothing.
        ("Umweltschule der Stadt Leipzig", None),
        (None, None),
        ("", None),
    ],
)
def test_the_school_type_is_read_off_the_name(name, expected):
    assert classify_school(name) == expected


def test_an_unnamed_object_next_to_a_named_one_is_the_same_place():
    """OSM maps a school as the named node and as the way of its grounds."""

    named = PoiEntry("schule", 51.2828, 12.4630, name="Schule Liebertwolkwitz")
    grounds = PoiEntry("schule", 51.28285, 12.46305, name=None)

    kept = deduplicate([named, grounds])

    assert kept == [named]


def test_two_differently_named_schools_on_one_campus_are_two_schools():
    grundschule = PoiEntry("schule", 51.2828, 12.4630, name="Schule Liebertwolkwitz - Grundschule")
    oberschule = PoiEntry("schule", 51.28285, 12.46305, name="Geschwister Scholl Schule")

    assert len(deduplicate([grundschule, oberschule])) == 2


def test_the_same_place_far_apart_is_two_places():
    a = PoiEntry("park", 51.2828, 12.4630, name=None)
    b = PoiEntry("park", 51.2900, 12.4700, name=None)

    assert len(deduplicate([a, b])) == 2


def test_the_radius_is_a_circle_not_the_grid_cell():
    index = PoiIndex(
        [
            PoiEntry("park", 51.2828, 12.4630, name="nah"),
            PoiEntry("park", 51.3300, 12.4630, name="fern"),
        ]
    )

    found = index.nearest("park", 51.2828, 12.4630, radius_m=1000, limit=10)

    assert [entry.name for entry, _ in found] == ["nah"]


def test_the_search_crosses_grid_cell_boundaries():
    """A point just over the cell edge is still within the radius."""

    index = PoiIndex([PoiEntry("park", 51.3001, 12.4630, name="jenseits")])

    found = index.nearest("park", 51.2999, 12.4630, radius_m=1000, limit=10)

    assert [entry.name for entry, _ in found] == ["jenseits"]


def test_hits_come_back_with_their_air_distance_and_sorted_by_it():
    index = PoiIndex(
        [
            PoiEntry("supermarkt", 51.2900, 12.4630, name="fern"),
            PoiEntry("supermarkt", 51.2840, 12.4630, name="nah"),
        ]
    )

    found = index.nearest("supermarkt", 51.2828, 12.4630, radius_m=3000, limit=10)

    assert [entry.name for entry, _ in found] == ["nah", "fern"]
    assert found[0][1] < found[1][1]
    assert 100 < found[0][1] < 200


def test_haversine_matches_a_known_distance():
    # Leipzig Hbf to Dresden Hbf, about 100 km.
    metres = haversine_m(51.34547, 12.38207, 51.04024, 13.73220)

    assert 99_000 < metres < 103_000


def test_a_missing_index_is_none_not_an_exception(tmp_path: Path):
    assert load_index(tmp_path / "gibt-es-nicht.json") is None


def test_a_file_that_is_not_an_index_raises(tmp_path: Path):
    path = tmp_path / "falsch.json"
    path.write_text('{"hallo": 1}', encoding="utf-8")

    with pytest.raises(ValueError):
        load_index(path)


def test_the_fixture_index_loads_with_its_metadata():
    index = load_index(FIXTURES / "poi_index.json")

    assert index is not None
    assert index.datenstand == "2026-08-22T20:21:02Z"
    assert index.counts["schule"] == 3
    assert index.count == 7


def test_a_gzipped_index_is_read_transparently(tmp_path: Path):
    import gzip

    payload = json.loads((FIXTURES / "poi_index.json").read_text(encoding="utf-8"))
    path = tmp_path / "poi.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)

    index = load_index(path)

    assert index is not None and index.count == 7


# --------------------------------------------------------------------------
# The build step
# --------------------------------------------------------------------------


def test_the_builder_turns_an_extract_into_the_index_the_api_reads(tmp_path: Path):
    """End to end through the real script, on a small hand-written extract.

    The Saxon extract itself cannot be fetched in every environment, but the
    conversion is exactly the same code path, and this pins the tag decisions
    from docs/research/poi.md § 4: driving schools are not schools, a private
    playground is not a playground, and `leisure=garden` is not a park.
    """

    pytest.importorskip("osmium", reason="pyosmium is only needed to build the index")
    out = tmp_path / "poi.json"

    result = subprocess.run(
        [
            sys.executable,
            str(BACKEND / "scripts" / "build_poi_index.py"),
            str(FIXTURES / "poi_extract.osm"),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    index = load_index(out)
    assert index is not None
    assert index.counts == {"schule": 3, "supermarkt": 1, "spielplatz": 1, "arzt": 1, "park": 1}

    entries = json.loads(out.read_text(encoding="utf-8"))["eintraege"]
    names = {entry.get("name") for entry in entries}
    assert "Fahrschule Nein Danke" not in names  # amenity=driving_school
    kinds = {entry.get("name"): entry.get("art") for entry in entries}
    assert kinds["Schule Liebertwolkwitz - Grundschule der Stadt Leipzig"] == "Grundschule"
    # A way becomes one point at the centre of its ring, as Overpass' `out center`.
    park = next(entry for entry in entries if entry["kategorie"] == "park")
    assert park["osm_id"] == "W100"
    assert park["lat"] == pytest.approx(51.2865, abs=1e-4)
    # leisure=garden is Saxony's most common green tag and almost never public.
    assert not any(entry["kategorie"] == "park" and entry["osm_id"] == "W101" for entry in entries)


def test_the_builder_needs_an_extract_or_the_download_flag():
    result = subprocess.run(
        [sys.executable, str(BACKEND / "scripts" / "build_poi_index.py")],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "--download" in result.stderr
