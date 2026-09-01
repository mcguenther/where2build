"""GET /api/gemarkungen -- the cadastral district picklist and the file behind it.

Run against the committed directory in ``backend/data``, not against invented
rows: it is the real answer of ``ave:KatasterBezirk``, and the two districts
asserted by name here are the ones verified against the live service --
Mölkau 145592 out of the cadastre answer for Mölkau Flurstück 204, and
Moritzburg 143044.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.deps import reset_services
from app.gemarkung_index import (
    GemarkungDirectory,
    GemarkungEntry,
    fold,
    fold_expanded,
    load_directory,
)

from .conftest import FIXTURES

BACKEND = Path(__file__).resolve().parent.parent
DIRECTORY_FILE = BACKEND / "data" / "gemarkungen-sachsen.json"


@pytest.fixture
def without_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A server on which the build script has never run."""

    monkeypatch.setenv("ALKIS_GEMARKUNG_INDEX_PATH", str(tmp_path / "kein-verzeichnis.json"))
    reset_services()
    yield


# --------------------------------------------------------------------------
# The endpoint
# --------------------------------------------------------------------------


def test_the_whole_directory_comes_back_sorted_by_name(client: TestClient):
    answer = client.get("/api/gemarkungen")

    assert answer.status_code == 200
    body = answer.json()
    names = [entry["name"] for entry in body["gemarkungen"]]
    assert names == sorted(names, key=lambda name: (fold(name), name))
    assert len(names) > 5000
    assert body["stand"]


def test_moelkau_is_in_the_directory_with_the_key_the_cadastre_answered(client: TestClient):
    treffer = client.get("/api/gemarkungen", params={"q": "Mölkau"}).json()["gemarkungen"]

    assert {"name": "Mölkau", "schluessel": "145592", "gemeinde": "Stadt Leipzig"} in treffer


def test_moritzburg_is_in_the_directory(client: TestClient):
    treffer = client.get("/api/gemarkungen", params={"q": "Moritzburg"}).json()["gemarkungen"]

    keys = {entry["schluessel"] for entry in treffer}
    assert "143044" in keys


@pytest.mark.parametrize("query", ["Mölkau", "mölkau", "MÖLKAU", "Molkau", "moelkau", "ölka"])
def test_the_search_ignores_case_and_how_the_umlaut_is_written(query, client: TestClient):
    """Whoever types "Molkau" has to find "Mölkau" -- an input mask that only
    answers the spelling with the dots is a mask that answers nobody."""

    treffer = client.get("/api/gemarkungen", params={"q": query}).json()["gemarkungen"]

    assert "Mölkau" in {entry["name"] for entry in treffer}


def test_the_search_also_matches_the_key(client: TestClient):
    treffer = client.get("/api/gemarkungen", params={"q": "145592"}).json()["gemarkungen"]

    assert [entry["name"] for entry in treffer] == ["Mölkau"]


def test_a_query_that_matches_nothing_is_an_empty_list_not_an_error(client: TestClient):
    answer = client.get("/api/gemarkungen", params={"q": "Kleinkleckersdorf"})

    assert answer.status_code == 200
    assert answer.json()["gemarkungen"] == []


def test_an_empty_query_is_the_same_as_none(client: TestClient):
    with_empty = client.get("/api/gemarkungen", params={"q": "  "}).json()
    without = client.get("/api/gemarkungen").json()

    assert with_empty == without


def test_the_answer_may_be_cached_by_the_browser(client: TestClient):
    answer = client.get("/api/gemarkungen")

    assert "max-age=" in answer.headers["cache-control"]
    assert "public" in answer.headers["cache-control"]


def test_a_missing_directory_is_a_german_error_not_an_empty_list(
    without_directory, client: TestClient
):
    answer = client.get("/api/gemarkungen")

    assert answer.status_code == 503
    detail = answer.json()["detail"]
    assert "Gemarkungsverzeichnis" in detail
    assert "build_gemarkung_index.py" in detail


def test_health_says_when_the_directory_has_not_been_built(without_directory, client: TestClient):
    dienste = {entry["name"]: entry for entry in client.get("/api/health").json()["dienste"]}

    assert dienste["gemarkungen"]["konfiguriert"] is False
    assert "build_gemarkung_index.py" in dienste["gemarkungen"]["hinweis"]


def test_health_reports_the_built_directory_with_its_size_and_date(client: TestClient):
    dienste = {entry["name"]: entry for entry in client.get("/api/health").json()["dienste"]}

    assert dienste["gemarkungen"]["konfiguriert"] is True
    assert "5339 Gemarkungen" in dienste["gemarkungen"]["hinweis"]


def test_the_endpoint_is_in_the_openapi_document(client: TestClient):
    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/gemarkungen" in paths


# --------------------------------------------------------------------------
# The committed file
# --------------------------------------------------------------------------


def test_every_key_is_six_digits_starting_with_the_saxon_prefix():
    """Pins what ``expand_gemarkung_key`` relies on: the four-digit form the
    Geoportal's Flurstueck layer prints expands to exactly one full key."""

    directory = load_directory(DIRECTORY_FILE)

    assert directory is not None
    keys = [entry.schluessel for entry in directory.entries]
    assert len(keys) == 5339
    assert all(len(key) == 6 and key.isdigit() and key.startswith("14") for key in keys)
    assert len(set(keys)) == len(keys)
    assert len({key[2:] for key in keys}) == len(keys)


def test_the_name_is_not_unique_so_the_key_has_to_be_shown_too():
    directory = load_directory(DIRECTORY_FILE)

    assert directory is not None
    names = [entry.name for entry in directory.entries]
    assert len(set(names)) < len(names)


def test_a_missing_file_is_none_not_an_exception(tmp_path: Path):
    assert load_directory(tmp_path / "gibt-es-nicht.json") is None


def test_a_file_that_is_not_a_directory_raises(tmp_path: Path):
    path = tmp_path / "falsch.json"
    path.write_text('{"hallo": 1}', encoding="utf-8")

    with pytest.raises(ValueError):
        load_directory(path)


# --------------------------------------------------------------------------
# Folding and search
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, folded, expanded",
    [
        ("Mölkau", "molkau", "moelkau"),
        ("Großschirma", "grossschirma", "grossschirma"),
        ("Siehdichfür", "siehdichfur", "siehdichfuer"),
        ("Ablaß", "ablass", "ablass"),
    ],
)
def test_folding_covers_both_spellings_of_an_umlaut(text, folded, expanded):
    assert fold(text) == folded
    assert fold_expanded(text) == expanded


def test_the_directory_sorts_umlauts_with_their_base_letter():
    directory = GemarkungDirectory(
        [
            GemarkungEntry(name="Zwota", schluessel="145427"),
            GemarkungEntry(name="Mölkau", schluessel="145592"),
            GemarkungEntry(name="Moritzburg", schluessel="143044"),
        ]
    )

    assert [entry.name for entry in directory.entries] == ["Mölkau", "Moritzburg", "Zwota"]


# --------------------------------------------------------------------------
# The build step
# --------------------------------------------------------------------------


def test_the_builder_reads_the_layer_and_throws_the_geometry_away():
    """On a recorded ``ave:KatasterBezirk`` response, not on a hand-written one.

    Nieder-Seifersdorf is 19 kB of boundary polygon for 90 bytes of text; the
    point of the streaming parse is that none of the polygon survives.
    """

    from scripts.build_gemarkung_index import parse_features, to_entries

    raw = (FIXTURES / "alkis_katasterbezirk.gml").read_bytes()
    features = list(parse_features(raw[at : at + 4096] for at in range(0, len(raw), 4096)))

    assert [feature["schluessel"] for feature in features] == ["146360", "146361", "146362"]
    assert all(set(feature) <= {"art", "name", "schluessel", "gemeinde"} for feature in features)

    entries, kinds = to_entries(features)
    assert kinds == {"Gemarkung": 3}
    assert entries[0] == GemarkungEntry(
        name="Nieder-Seifersdorf Flur 1", schluessel="146360", gemeinde="Waldhufen"
    )


def test_only_gemarkungen_are_kept_out_of_the_layer():
    """``ave:KatasterBezirk`` is the layer for cadastral districts of every
    ``art``; only a Gemarkung addresses a parcel."""

    from scripts.build_gemarkung_index import to_entries

    entries, kinds = to_entries(
        [
            {"art": "Gemarkung", "name": "Mölkau", "schluessel": "145592"},
            {"art": "Gemeinde", "name": "Stadt Leipzig", "schluessel": "14713000"},
        ]
    )

    assert [entry.schluessel for entry in entries] == ["145592"]
    assert kinds == {"Gemarkung": 1, "Gemeinde": 1}


def test_what_the_builder_writes_is_what_the_endpoint_reads(tmp_path: Path):
    from scripts.build_gemarkung_index import write_directory

    out = tmp_path / "gemarkungen.json"
    write_directory(
        [GemarkungEntry(name="Mölkau", schluessel="145592", gemeinde="Stadt Leipzig")],
        out,
        source="https://geodienste.example.org/wfs",
    )

    directory = load_directory(out)
    assert directory is not None
    assert directory.stand == json.loads(out.read_text(encoding="utf-8"))["stand"]
    assert directory.search("molkau")[0].gemeinde == "Stadt Leipzig"
