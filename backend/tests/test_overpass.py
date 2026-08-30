"""The live OpenStreetMap source behind /api/nearby -- opt-in, one query, cached.

Every test here runs against ``fixtures/overpass_liebertwolkwitz.json``, which
is a **real** ``[out:json]`` answer from ``overpass-api.de`` (generator
0.7.62.11, ``timestamp_osm_base`` 2026-08-30T06:16:58Z) for the box around the
Liebertwolkwitz test plot: 38 elements, nodes, ways with a ``center`` and one
multipolygon relation. It was captured on a machine that can reach the service;
this sandbox cannot (docs/research/poi.md § 2.1), so what is verified here is
the reading of a genuine response, not the making of the request.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.poi_index import PoiIndex, classify_school, classify_school_grades
from app.services.overpass import build_query, entries_from_elements

from .conftest import MOTIS_URL, OVERPASS_URL, fixture_json

STOPS_URL = f"{MOTIS_URL}/api/v6/map/stops"
MATRIX_URL = f"{MOTIS_URL}/api/v1/one-to-many"

# Leipzig-Liebertwolkwitz, the plot from the brief and the centre of the box the
# recorded answer covers.
ORIGIN = {"lat": 51.2828, "lon": 12.4630}

ANSWER = "overpass_liebertwolkwitz.json"


def _by_air(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    return httpx.Response(
        200,
        json=[
            {"duration": 60.0 * (index + 1), "distance": 80.0 * (index + 1)}
            for index in range(len(body["many"]))
        ],
    )


def _mock_motis():
    respx.get(STOPS_URL).mock(return_value=httpx.Response(200, json=fixture_json("motis_stops.json")))
    respx.post(MATRIX_URL).mock(side_effect=_by_air)


def _mock_overpass(**kwargs):
    return respx.post(OVERPASS_URL).mock(
        return_value=httpx.Response(200, json=fixture_json(ANSWER)), **kwargs
    )


# --------------------------------------------------------------------------
# Reading a real answer
# --------------------------------------------------------------------------


def test_the_live_answer_is_filtered_by_the_same_tag_rules_as_the_extract():
    """33 of the 38 recorded objects are kept, and the five dropped are dropped
    for reasons the offline build applies too -- one mapping, two sources."""

    elements = fixture_json(ANSWER)["elements"]
    entries = entries_from_elements(elements)

    assert len(elements) == 38
    assert len(entries) == 33
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry.kategorie] = counts.get(entry.kategorie, 0) + 1
    assert counts == {"schule": 5, "kindergarten": 4, "park": 10, "spielplatz": 10, "arzt": 4}

    kept = {entry.osm_id for entry in entries}
    # A pharmacy is not a doctor's surgery; `arzt` is amenity=doctors|clinic.
    assert "N3287433218" not in kept
    # `healthcare=doctor` sits on the same nodes as `amenity=doctors` and is not
    # unioned in -- four surgeries, not eight.
    assert len([entry for entry in entries if entry.kategorie == "arzt"]) == 4


def test_a_playground_behind_a_fence_is_not_one_the_children_can_use():
    """`access` is the most common companion tag on Saxon playgrounds, and this
    box has both sides of the filter: a school yard on `permit` and a public
    playground on `yes` a few metres away."""

    kept = {entry.osm_id for entry in entries_from_elements(fixture_json(ANSWER)["elements"])}

    assert "W1180989850" not in kept  # access=private
    assert {"W1442483019", "W1442483020", "W1442483021"}.isdisjoint(kept)  # access=permit
    assert "W1089038316" in kept  # access=yes, right next to them
    assert "W1323465600" in kept  # access=permissive is not a closed playground


def test_ways_and_relations_are_read_from_the_centre_overpass_computed():
    """`out tags center` sends no geometry -- only that one coordinate."""

    entries = {entry.osm_id: entry for entry in entries_from_elements(fixture_json(ANSWER)["elements"])}

    # The recorded answer gives this park only `center: 51.2820114, 12.4626348`.
    park = entries["W264900334"]
    assert (park.lat, park.lon) == (51.282011, 12.462635)
    # The one multipolygon in the box, a Kita mapped as a relation.
    kita = entries["R15981760"]
    assert kita.name == 'Kita "Wolkser Kinderland"'
    assert (kita.lat, kita.lon) == (51.281208, 12.458459)
    assert all(entry.osm_id[0] in "NWR" for entry in entries.values())


def test_a_place_without_a_name_keeps_its_kind_and_no_invented_name():
    """18 of the 33 carry no `name` at all. "Park" is honest, "" is not."""

    entries = entries_from_elements(fixture_json(ANSWER)["elements"])
    nameless = [entry for entry in entries if entry.name is None]

    assert len(nameless) == 18
    assert all(entry.art for entry in nameless)
    assert {entry.art for entry in nameless if entry.kategorie == "park"} == {"Park"}
    assert not any(entry.name == "" for entry in entries)


def test_the_school_type_comes_from_grades_first_and_the_name_second():
    """All five schools in the box, and why each one classifies as it does.

    `grades` is on three of them and decides one case the name cannot: the
    "Umweltschule der Stadt Leipzig" is a Grundschule and says so nowhere in
    its name.
    """

    schools = {
        entry.osm_id: entry
        for entry in entries_from_elements(fixture_json(ANSWER)["elements"])
        if entry.kategorie == "schule"
    }

    assert schools["N10985287011"].art == "Oberschule"  # grades 5-10, name agrees
    assert schools["N10985287012"].art == "Grundschule"  # grades 1-4, name agrees
    assert schools["W649704869"].art == "Grundschule"  # grades 1-4, name says nothing
    assert classify_school("Umweltschule der Stadt Leipzig") is None
    assert schools["W1204202981"].art == "Oberschule"  # no grades, name says it
    assert schools["W1068011411"].art == "Schule"  # neither -- and no guess


@pytest.mark.parametrize(
    "grades, expected",
    [
        ("1-4", "Grundschule"),
        ("5-10", "Oberschule"),
        ("5-12", "Gymnasium"),
        ("1;2;3;4", "Grundschule"),
        # Not a range, and the one value taginfo reports that is not a level.
        ("9", None),
        # Primary through upper secondary is a campus, not one of the three types.
        ("1-12", None),
        (None, None),
    ],
)
def test_grades_are_only_read_where_they_are_unambiguous(grades, expected):
    assert classify_school_grades(grades) == expected


def test_the_same_place_mapped_twice_is_still_one_place():
    """Am Angerteich in the recorded box: two named school nodes 49 m apart plus
    the unnamed way of the shared grounds. A human sees two schools."""

    index = PoiIndex(entries_from_elements(fixture_json(ANSWER)["elements"]))
    found = index.nearest("schule", ORIGIN["lat"], ORIGIN["lon"], 3000, 10)

    assert [entry.osm_id for entry, _ in found[:2]] == ["N10985287011", "N10985287012"]
    # The nameless way of the grounds is 49 m from the Grundschule node.
    assert "W1068011411" not in {entry.osm_id for entry, _ in found}


# --------------------------------------------------------------------------
# The query that goes out
# --------------------------------------------------------------------------


def test_one_query_carries_every_requested_category():
    query = build_query(["schule", "park"], 51.283, 12.463, 3200, 25)

    assert query.startswith("[out:json][timeout:25];(")
    assert query.endswith(");out tags center;")
    assert query.count("nwr[") == 5  # one school tag, four park tags
    assert 'nwr["amenity"="school"](around:3200,51.283,12.463);' in query
    # leisure=garden is Saxony's most common green tag and 26 of 12 583 are public.
    assert "garden" not in query


@respx.mock
def test_the_request_is_one_post_with_the_apps_user_agent(overpass, client: TestClient):
    route = _mock_overpass()
    _mock_motis()

    client.post("/api/nearby", json={"origin": ORIGIN, "kategorien": ["schule", "park"]})

    assert route.call_count == 1
    request = route.calls[0].request
    agent = request.headers["user-agent"]
    # The policy is ultimately after a way to reach the operator.
    assert "GrundstuecksCheckSachsen" in agent and "@" in agent
    assert b"data=" in request.content


@respx.mock
def test_the_endpoint_is_a_setting_not_a_constant(overpass, monkeypatch, client: TestClient):
    """Pointing at a self-hosted instance has to be one line in .env."""

    from app.deps import reset_services

    eigene = "https://overpass.intern.example.org/api/interpreter"
    monkeypatch.setenv("OVERPASS_URL", eigene)
    reset_services()
    route = respx.post(eigene).mock(return_value=httpx.Response(200, json=fixture_json(ANSWER)))
    public = _mock_overpass()
    _mock_motis()

    client.post("/api/nearby", json={"origin": ORIGIN, "kategorien": ["schule"]})

    assert route.call_count == 1
    assert public.call_count == 0


@respx.mock
def test_the_query_is_rounded_so_neighbouring_plots_share_one_answer(
    overpass, client: TestClient
):
    """A hard cache is the whole reason this is inside the policy at all."""

    route = _mock_overpass()
    _mock_motis()

    for origin in ({"lat": 51.2828, "lon": 12.4630}, {"lat": 51.28312, "lon": 12.46284}):
        for umkreis in (2400, 2800):
            answer = client.post(
                "/api/nearby",
                json={"origin": origin, "kategorien": ["schule"], "umkreis_m": umkreis},
            )
            assert answer.status_code == 200

    assert route.call_count == 1
    query = route.calls[0].request.content.decode()
    # Centre rounded to three decimals, radius up to the next full step plus
    # the margin that covers the rounding.
    assert "51.283%2C12.463" in query or "51.283,12.463" in query
    assert "around%3A3200" in query or "around:3200" in query


# --------------------------------------------------------------------------
# Which source answers
# --------------------------------------------------------------------------


@respx.mock
def test_without_the_switch_nothing_is_asked_and_the_answer_stays_honest(client: TestClient):
    """Off by default: a deployment gets the "kein Datenbestand" answer, not a
    request to a public instance nobody agreed to."""

    route = _mock_overpass()
    _mock_motis()

    body = client.post(
        "/api/nearby", json={"origin": ORIGIN, "kategorien": ["schule", "bus"]}
    ).json()

    assert route.call_count == 0
    status = {entry["kategorie"]: entry for entry in body["kategorien"]}
    assert status["schule"]["verfuegbar"] is False
    assert "kein Datenbestand" in status["schule"]["hinweis"]
    assert status["bus"]["anzahl"] >= 1


@respx.mock
def test_with_the_switch_the_osm_categories_answer_without_any_index(
    overpass, client: TestClient
):
    _mock_overpass()
    _mock_motis()

    body = client.post(
        "/api/nearby",
        json={
            "origin": ORIGIN,
            "kategorien": ["schule", "spielplatz", "arzt", "bus"],
            "treffer_je_kategorie": 2,
        },
    ).json()

    status = {entry["kategorie"]: entry for entry in body["kategorien"]}
    assert status["schule"]["verfuegbar"] is True
    assert status["schule"]["anzahl"] == 2
    assert status["arzt"]["anzahl"] == 2

    schulen = [hit for hit in body["treffer"] if hit["kategorie"] == "schule"]
    assert {hit["art"] for hit in schulen} == {"Oberschule", "Grundschule"}
    # The source is named per hit: `overpass`, not the built index and not MOTIS.
    assert all(hit["quelle"] == "overpass" for hit in schulen)
    assert all(hit["osm_id"].startswith(("N", "W", "R")) for hit in schulen)
    assert [hit["quelle"] for hit in body["treffer"] if hit["kategorie"] == "bus"] == ["motis"] * len(
        [hit for hit in body["treffer"] if hit["kategorie"] == "bus"]
    )
    # A nameless playground is a hit like any other.
    spielplatz = next(hit for hit in body["treffer"] if hit["kategorie"] == "spielplatz")
    assert spielplatz["name"] is None and spielplatz["art"] == "Spielplatz"


@respx.mock
def test_the_datenstand_is_the_instances_own_timestamp(overpass, client: TestClient):
    _mock_overpass()
    _mock_motis()

    body = client.post("/api/nearby", json={"origin": ORIGIN, "kategorien": ["schule"]}).json()

    assert body["datenstand"] == "2026-08-30T06:16:58Z"


@respx.mock
def test_a_built_index_wins_over_the_live_query(poi_index, overpass, client: TestClient):
    """Index if present, Overpass only if not. Never both, never a mix."""

    route = _mock_overpass()
    _mock_motis()

    body = client.post("/api/nearby", json={"origin": ORIGIN, "kategorien": ["schule"]}).json()

    assert route.call_count == 0
    assert all(hit["quelle"] == "osm" for hit in body["treffer"])
    assert body["datenstand"] == "2026-08-22T20:21:02Z"


@respx.mock
def test_asking_only_for_stops_asks_overpass_nothing(overpass, client: TestClient):
    route = _mock_overpass()
    _mock_motis()

    client.post("/api/nearby", json={"origin": ORIGIN, "kategorien": ["bus", "bahnhof"]})

    assert route.call_count == 0


# --------------------------------------------------------------------------
# When the service is busy
# --------------------------------------------------------------------------


@respx.mock
def test_a_rate_limited_overpass_says_so_and_leaves_the_stops_alone(
    overpass, client: TestClient
):
    """HTTP 429 is the documented answer when the caller is over its slot quota,
    and the quota is per IP -- ours."""

    respx.post(OVERPASS_URL).mock(
        return_value=httpx.Response(
            429, text="You have downloaded too much data. Please try again later."
        )
    )
    _mock_motis()

    answer = client.post(
        "/api/nearby", json={"origin": ORIGIN, "kategorien": ["schule", "bus"]}
    )

    assert answer.status_code == 200
    body = answer.json()
    status = {entry["kategorie"]: entry for entry in body["kategorien"]}
    assert status["schule"]["verfuegbar"] is False
    assert "429" in status["schule"]["hinweis"]
    assert "zu vieler Zugriffe" in status["schule"]["hinweis"]
    # Not the "kein Datenbestand" sentence: the source exists, it did not answer.
    assert "kein Datenbestand" not in status["schule"]["hinweis"]
    # The transit half comes from the timetable and is untouched.
    assert status["bus"]["verfuegbar"] is True
    assert status["bus"]["anzahl"] >= 1


@respx.mock
def test_the_runtime_error_body_is_never_read_as_nothing_found(overpass, client: TestClient):
    """Under load Overpass answers HTTP 200 with an empty `elements` and puts the
    failure in `remark`. Reading that as "im Umkreis gibt es keine Schule" is the
    one answer this endpoint exists to avoid."""

    respx.post(OVERPASS_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("overpass_runtime_error.json"))
    )
    _mock_motis()

    body = client.post(
        "/api/nearby", json={"origin": ORIGIN, "kategorien": ["schule", "bus"]}
    ).json()

    status = {entry["kategorie"]: entry for entry in body["kategorien"]}
    assert status["schule"]["verfuegbar"] is False
    assert status["schule"]["anzahl"] == 0
    assert "abgebrochen" in status["schule"]["hinweis"]
    assert "Umkreis von" not in status["schule"]["hinweis"]
    assert status["bus"]["anzahl"] >= 1


@respx.mock
def test_a_broken_answer_from_overpass_does_not_take_the_stops_down(
    overpass, client: TestClient
):
    respx.post(OVERPASS_URL).mock(return_value=httpx.Response(200, text="<html>kein json"))
    _mock_motis()

    body = client.post(
        "/api/nearby", json={"origin": ORIGIN, "kategorien": ["park", "bus"]}
    ).json()

    status = {entry["kategorie"]: entry for entry in body["kategorien"]}
    assert status["park"]["verfuegbar"] is False
    assert "JSON" in status["park"]["hinweis"]
    assert status["bus"]["anzahl"] >= 1


@respx.mock
def test_a_slow_overpass_is_reported_as_slow(overpass, client: TestClient):
    respx.post(OVERPASS_URL).mock(side_effect=httpx.ReadTimeout("langsam"))
    _mock_motis()

    answer = client.post(
        "/api/nearby", json={"origin": ORIGIN, "kategorien": ["schule", "bus"]}
    )

    assert answer.status_code == 200
    status = {entry["kategorie"]: entry for entry in answer.json()["kategorien"]}
    assert "nicht rechtzeitig" in status["schule"]["hinweis"]
    assert "Fahrplandienst" in status["schule"]["hinweis"]


@respx.mock
def test_a_failed_query_is_not_cached(overpass, client: TestClient):
    """Otherwise one bad minute would blank the categories for a month."""

    route = respx.post(OVERPASS_URL).mock(
        side_effect=[
            httpx.Response(200, json=fixture_json("overpass_runtime_error.json")),
            httpx.Response(200, json=fixture_json(ANSWER)),
        ]
    )
    _mock_motis()

    request = {"origin": ORIGIN, "kategorien": ["schule"]}
    first = client.post("/api/nearby", json=request).json()
    second = client.post("/api/nearby", json=request).json()

    assert route.call_count == 2
    assert first["kategorien"][0]["verfuegbar"] is False
    assert second["kategorien"][0]["verfuegbar"] is True
