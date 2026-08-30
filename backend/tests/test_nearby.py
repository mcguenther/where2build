"""POST /api/nearby -- "wie weit ist die nächste Schule".

The two halves are tested separately because they fail separately: stops come
from the timetable and always work, the six OpenStreetMap categories need a
local index that a deployment may simply not have built.
"""

from __future__ import annotations

import json

import httpx
import respx
from fastapi.testclient import TestClient

from .conftest import MOTIS_URL, fixture_json

STOPS_URL = f"{MOTIS_URL}/api/v6/map/stops"
MATRIX_URL = f"{MOTIS_URL}/api/v1/one-to-many"
STOP_URL = f"{MOTIS_URL}/api/v6/stop"

# Leipzig-Liebertwolkwitz, the plot from the brief.
ORIGIN = {"lat": 51.2828, "lon": 12.4630}


def _by_air(request: httpx.Request) -> httpx.Response:
    """Durations that agree with the order the candidates were sent in."""

    body = json.loads(request.content)
    return httpx.Response(
        200,
        json=[
            {"duration": 60.0 * (index + 1), "distance": 80.0 * (index + 1)}
            for index in range(len(body["many"]))
        ],
    )


def _mock_stops():
    respx.get(STOPS_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("motis_stops.json"))
    )


@respx.mock
def test_stops_are_separated_by_the_mode_that_actually_calls_there(client: TestClient):
    _mock_stops()
    respx.post(MATRIX_URL).mock(side_effect=_by_air)

    answer = client.post(
        "/api/nearby",
        json={
            "origin": ORIGIN,
            "kategorien": ["tram", "sbahn", "bus", "bahnhof"],
            "umkreis_m": 5000,
        },
    )

    assert answer.status_code == 200
    body = answer.json()
    by_category: dict[str, list[dict]] = {}
    for hit in body["treffer"]:
        by_category.setdefault(hit["kategorie"], []).append(hit)

    assert [hit["name"] for hit in by_category["tram"]] == ["Leipzig, Meusdorf"]
    assert by_category["tram"][0]["art"] == "Straßenbahn, Bus"
    assert {hit["name"] for hit in by_category["bahnhof"]} == {
        "Leipzig-Liebertwolkwitz",
        "Leipzig-Holzhausen",
    }
    assert by_category["bus"][0]["name"] == "Leipzig, Liebertwolkwitzer Markt"
    # No feed in the fixture carries SUBURBAN, so the S-Bahn category is
    # available and empty -- which is a different statement from "no data".
    status = {entry["kategorie"]: entry for entry in body["kategorien"]}
    assert status["sbahn"]["verfuegbar"] is True
    assert status["sbahn"]["anzahl"] == 0
    assert "Umkreis" in status["sbahn"]["hinweis"]


@respx.mock
def test_the_stops_request_is_lat_lon_and_grouped(client: TestClient):
    route = respx.get(STOPS_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("motis_stops.json"))
    )
    respx.post(MATRIX_URL).mock(side_effect=_by_air)

    client.post("/api/nearby", json={"origin": ORIGIN, "kategorien": ["bus"]})

    params = route.calls[0].request.url.params
    assert params["grouped"] == "true"
    # lat,lon in that order -- swapping them puts the box in the Indian Ocean.
    south, west = (float(value) for value in params["min"].split(","))
    north, east = (float(value) for value in params["max"].split(","))
    assert south < ORIGIN["lat"] < north
    assert west < ORIGIN["lon"] < east


@respx.mock
def test_the_matrix_request_uses_a_semicolon_and_one_call_for_everything(client: TestClient):
    _mock_stops()
    matrix = respx.post(MATRIX_URL).mock(side_effect=_by_air)

    client.post(
        "/api/nearby",
        json={"origin": ORIGIN, "kategorien": ["bus", "bahnhof", "tram"], "umkreis_m": 5000},
    )

    assert matrix.call_count == 1
    body = json.loads(matrix.calls[0].request.content)
    # A comma between lat and lon is answered with "is not a valid geo coordinate".
    assert body["one"] == "51.2828;12.463"
    assert all(";" in entry and "," not in entry for entry in body["many"])
    assert body["mode"] == "WALK"
    assert body["arriveBy"] is False
    # Leaving this out is answered with "key maxMatchingDistance not found".
    assert body["maxMatchingDistance"] == 250


@respx.mock
def test_ranking_is_by_walking_time_not_by_air_distance(client: TestClient):
    """The finding the whole design rests on: the two orders disagree.

    The nearest stop by air (Liebertwolkwitzer Markt, 98 m) is given a longer
    walk than one 250 m away, and the answer has to follow the walk.
    """

    _mock_stops()

    def responder(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        # The Markt is the nearest by air; Zur alten Sandgrube is 250 m further.
        durations = {"51.2827": 900.0, "51.2806": 300.0}
        return httpx.Response(
            200,
            json=[
                {
                    "duration": next(
                        (
                            seconds
                            for prefix, seconds in durations.items()
                            if entry.startswith(prefix)
                        ),
                        1200.0,
                    ),
                    "distance": 500.0,
                }
                for entry in body["many"]
            ],
        )

    respx.post(MATRIX_URL).mock(side_effect=responder)

    treffer = client.post(
        "/api/nearby",
        json={"origin": ORIGIN, "kategorien": ["bus"], "treffer_je_kategorie": 2},
    ).json()["treffer"]

    assert treffer[0]["name"] == "Leipzig, Zur alten Sandgrube"
    assert treffer[0]["duration_s"] == 300
    assert treffer[0]["luftlinie_m"] > 200
    assert treffer[1]["name"] == "Leipzig, Liebertwolkwitzer Markt"
    # Air distance is only how the candidate list was cut down.
    assert treffer[1]["luftlinie_m"] < treffer[0]["luftlinie_m"]


@respx.mock
def test_an_unreachable_place_is_reported_not_dropped(client: TestClient):
    """MOTIS answers ``{}`` for a destination with no walkable route.

    Measured in Dresden: the nearest playground by air is across the Elbe and
    the crossing is a ferry. Rendering that as duration 0 would be a lie, and
    dropping it hides the most interesting thing about the plot.
    """

    _mock_stops()
    respx.post(MATRIX_URL).mock(
        side_effect=lambda request: httpx.Response(
            200, json=[{} for _ in json.loads(request.content)["many"]]
        )
    )

    treffer = client.post(
        "/api/nearby", json={"origin": ORIGIN, "kategorien": ["bus"], "treffer_je_kategorie": 1}
    ).json()["treffer"]

    assert treffer[0]["erreichbar"] is False
    assert treffer[0]["duration_s"] is None
    assert treffer[0]["luftlinie_m"] > 0
    assert "zu Fuß" in treffer[0]["hinweis"]


@respx.mock
def test_the_response_shape_of_a_real_matrix_answer_is_read_correctly(client: TestClient):
    """The live answer uses E notation and an empty object for "no route"."""

    _mock_stops()
    respx.post(MATRIX_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("motis_one_to_many.json"))
    )

    treffer = client.post(
        "/api/nearby",
        json={"origin": ORIGIN, "kategorien": ["bus"], "treffer_je_kategorie": 10},
    ).json()["treffer"]

    # Floats in E notation, and an empty object where there is no walkable route.
    assert treffer[0]["duration_s"] == 241
    assert treffer[0]["distance_m"] == 115
    assert treffer[1]["duration_s"] == 382
    assert [hit["erreichbar"] for hit in treffer[:3]] == [True, True, True]
    assert treffer[-1]["erreichbar"] is False


# --------------------------------------------------------------------------
# The index is a build artefact and may be absent
# --------------------------------------------------------------------------


@respx.mock
def test_without_the_index_those_categories_say_so_and_return_nothing(client: TestClient):
    """The case this endpoint was most carefully shaped around.

    An empty ``treffer`` list would read as "es gibt hier keine Schule". The
    answer has to say "dieser Server hat dazu keine Daten" instead, and the
    transit half has to keep working.
    """

    _mock_stops()
    respx.post(MATRIX_URL).mock(side_effect=_by_air)

    body = client.post(
        "/api/nearby",
        json={"origin": ORIGIN, "kategorien": ["schule", "park", "spielplatz", "bus"]},
    ).json()

    status = {entry["kategorie"]: entry for entry in body["kategorien"]}
    for kategorie in ("schule", "park", "spielplatz"):
        assert status[kategorie]["verfuegbar"] is False
        assert status[kategorie]["anzahl"] == 0
        assert "kein Datenbestand" in status[kategorie]["hinweis"]
        assert "nicht, dass es hier nichts gibt" in status[kategorie]["hinweis"]
    assert not [hit for hit in body["treffer"] if hit["kategorie"] != "bus"]
    assert status["bus"]["verfuegbar"] is True
    assert status["bus"]["anzahl"] >= 1
    assert body["datenstand"] is None


@respx.mock
def test_without_the_index_and_only_osm_categories_nothing_is_requested(client: TestClient):
    """No candidates means no reason to trouble a volunteer routing service."""

    stops = respx.get(STOPS_URL).mock(return_value=httpx.Response(200, json=[]))
    matrix = respx.post(MATRIX_URL).mock(side_effect=_by_air)

    body = client.post("/api/nearby", json={"origin": ORIGIN, "kategorien": ["schule"]}).json()

    assert body["treffer"] == []
    assert body["kategorien"][0]["verfuegbar"] is False
    assert stops.call_count == 0
    assert matrix.call_count == 0


@respx.mock
def test_with_the_index_the_osm_categories_answer(poi_index, client: TestClient):
    respx.post(MATRIX_URL).mock(side_effect=_by_air)

    body = client.post(
        "/api/nearby",
        json={"origin": ORIGIN, "kategorien": ["schule", "supermarkt"], "treffer_je_kategorie": 2},
    ).json()

    status = {entry["kategorie"]: entry for entry in body["kategorien"]}
    assert status["schule"]["verfuegbar"] is True
    assert body["datenstand"] == "2026-08-22T20:21:02Z"

    schulen = [hit for hit in body["treffer"] if hit["kategorie"] == "schule"]
    # The type comes out of the name -- no Saxon OSM tag carries it.
    assert {hit["art"] for hit in schulen} == {"Grundschule", "Oberschule"}
    assert all(hit["quelle"] == "osm" for hit in schulen)
    assert all(hit["osm_id"].startswith(("N", "W", "R")) for hit in schulen)

    supermarkt = next(hit for hit in body["treffer"] if hit["kategorie"] == "supermarkt")
    assert supermarkt["name"] == "Konsum"


@respx.mock
def test_a_place_without_a_name_is_still_a_hit(poi_index, client: TestClient):
    """88 % of Saxon playgrounds have no name. That is not a reason to hide them."""

    respx.post(MATRIX_URL).mock(side_effect=_by_air)

    treffer = client.post(
        "/api/nearby", json={"origin": ORIGIN, "kategorien": ["spielplatz"]}
    ).json()["treffer"]

    assert len(treffer) == 1
    assert treffer[0]["name"] is None
    assert treffer[0]["art"] == "Spielplatz"


@respx.mock
def test_a_broken_index_file_does_not_take_the_stops_down(
    monkeypatch, tmp_path, client: TestClient
):
    from app.deps import reset_services

    broken = tmp_path / "kaputt.json"
    broken.write_text("{nope", encoding="utf-8")
    monkeypatch.setenv("NEARBY_POI_INDEX_PATH", str(broken))
    reset_services()

    _mock_stops()
    respx.post(MATRIX_URL).mock(side_effect=_by_air)

    body = client.post(
        "/api/nearby", json={"origin": ORIGIN, "kategorien": ["schule", "bus"]}
    ).json()

    status = {entry["kategorie"]: entry for entry in body["kategorien"]}
    assert status["schule"]["verfuegbar"] is False
    assert status["bus"]["anzahl"] >= 1


# --------------------------------------------------------------------------
# Budget, lines, and the ways this can fail
# --------------------------------------------------------------------------


@respx.mock
def test_every_category_at_once_costs_two_upstream_requests(poi_index, client: TestClient):
    stops = respx.get(STOPS_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("motis_stops.json"))
    )
    matrix = respx.post(MATRIX_URL).mock(side_effect=_by_air)

    answer = client.post("/api/nearby", json={"origin": ORIGIN, "umkreis_m": 5000})

    assert answer.status_code == 200
    assert stops.call_count == 1
    assert matrix.call_count == 1
    assert len(json.loads(matrix.calls[0].request.content)["many"]) <= 128


@respx.mock
def test_the_candidate_list_never_exceeds_the_server_limit(client: TestClient):
    """MOTIS refuses 129 destinations with a 422 naming its own config key."""

    many_stops = [
        {
            "name": f"Haltestelle {index}",
            "stopId": f"stop-{index}",
            "lat": 51.2828 + index * 0.0002,
            "lon": 12.4630,
            "modes": ["BUS"],
        }
        for index in range(400)
    ]
    respx.get(STOPS_URL).mock(return_value=httpx.Response(200, json=many_stops))
    matrix = respx.post(MATRIX_URL).mock(side_effect=_by_air)

    answer = client.post(
        "/api/nearby",
        json={
            "origin": ORIGIN,
            "kategorien": ["bus"],
            "umkreis_m": 15000,
            "treffer_je_kategorie": 10,
        },
    )

    assert answer.status_code == 200
    assert len(json.loads(matrix.calls[0].request.content)["many"]) <= 128


@respx.mock
def test_lines_are_only_fetched_when_asked_for(client: TestClient):
    _mock_stops()
    respx.post(MATRIX_URL).mock(side_effect=_by_air)
    stop = respx.get(STOP_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("motis_stop.json"))
    )

    quiet = client.post(
        "/api/nearby", json={"origin": ORIGIN, "kategorien": ["tram"], "umkreis_m": 5000}
    ).json()
    assert stop.call_count == 0
    # Not an empty list: nothing was asked, so nothing is claimed.
    assert quiet["treffer"][0]["linien"] is None

    loud = client.post(
        "/api/nearby",
        json={"origin": ORIGIN, "kategorien": ["tram"], "umkreis_m": 5000, "linien": True},
    ).json()
    assert stop.call_count == 1
    # Only the lines of the mode the category is about, in human order.
    assert loud["treffer"][0]["linien"] == ["2", "15", "31"]


@respx.mock
def test_beyond_the_line_budget_nothing_is_claimed(monkeypatch, client: TestClient):
    """Running out of budget must not look like "an dieser Haltestelle fährt nichts"."""

    from app.deps import reset_services

    monkeypatch.setenv("NEARBY_MAX_LINE_LOOKUPS", "1")
    reset_services()
    _mock_stops()
    respx.post(MATRIX_URL).mock(side_effect=_by_air)
    respx.get(STOP_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("motis_stop.json"))
    )

    treffer = client.post(
        "/api/nearby",
        json={
            "origin": ORIGIN,
            "kategorien": ["bus"],
            "treffer_je_kategorie": 3,
            "linien": True,
        },
    ).json()["treffer"]

    assert treffer[0]["linien"] is not None
    assert [hit["linien"] for hit in treffer[1:]] == [None, None]


@respx.mock
def test_a_stop_the_routing_never_reached_keeps_its_air_distance(client: TestClient):
    _mock_stops()
    respx.post(MATRIX_URL).mock(return_value=httpx.Response(200, json=[]))

    treffer = client.post(
        "/api/nearby", json={"origin": ORIGIN, "kategorien": ["bus"], "treffer_je_kategorie": 1}
    ).json()["treffer"]

    assert treffer[0]["erreichbar"] is False
    assert treffer[0]["luftlinie_m"] > 0


def test_an_unknown_category_is_a_422(client: TestClient):
    answer = client.post("/api/nearby", json={"origin": ORIGIN, "kategorien": ["kegelbahn"]})

    assert answer.status_code == 422
    assert "Traceback" not in answer.text


def test_a_radius_outside_the_allowed_range_is_a_422(client: TestClient):
    assert client.post("/api/nearby", json={"origin": ORIGIN, "umkreis_m": 40}).status_code == 422
    weit = client.post("/api/nearby", json={"origin": ORIGIN, "umkreis_m": 99999})
    assert weit.status_code == 422


def test_a_missing_origin_is_a_422(client: TestClient):
    assert client.post("/api/nearby", json={"kategorien": ["bus"]}).status_code == 422


@respx.mock
def test_a_broken_answer_from_the_stop_service_is_a_502(client: TestClient):
    respx.get(STOPS_URL).mock(return_value=httpx.Response(200, text="kein json"))

    answer = client.post("/api/nearby", json={"origin": ORIGIN, "kategorien": ["bus"]})

    assert answer.status_code == 502
    assert "Traceback" not in answer.text
    assert "Grundstücks" in answer.json()["detail"] or "Routing-Dienst" in answer.json()["detail"]


@respx.mock
def test_a_slow_routing_service_is_a_504(client: TestClient):
    _mock_stops()
    respx.post(MATRIX_URL).mock(side_effect=httpx.ReadTimeout("langsam"))

    answer = client.post("/api/nearby", json={"origin": ORIGIN, "kategorien": ["bus"]})

    assert answer.status_code == 504


@respx.mock
def test_the_answer_carries_its_sources_and_a_note_on_what_the_numbers_are(client: TestClient):
    _mock_stops()
    respx.post(MATRIX_URL).mock(side_effect=_by_air)

    body = client.post("/api/nearby", json={"origin": ORIGIN, "kategorien": ["bus"]}).json()

    assert "OpenStreetMap" in body["quelle"] and "Transitous" in body["quelle"]
    assert "Gehzeiten" in body["hinweis"]
    assert "Luftlinie" in body["hinweis"]


# --------------------------------------------------------------------------
# One physical stop, one row
# --------------------------------------------------------------------------

# Wilhelm-Leuschner-Platz, over the Leipzig City-Tunnel. `motis_stops_citytunnel`
# and `motis_stop_citytunnel` are real `map/stops` and `stop` answers from
# api.transitous.org, recorded 30.08.2026 -- the stops around this coordinate are
# the case that made this necessary: `Leipzig Markt`, `Leipzig Bayerischer
# Bahnhof` and `Leipzig Wilhelm-Leuschner-Platz` each carry REGIONAL_RAIL *and*
# SUBURBAN, so each was listed once as `sbahn` and again as `bahnhof`.
CITYTUNNEL = {"lat": 51.3350, "lon": 12.3770}


def _mock_citytunnel():
    respx.get(STOPS_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("motis_stops_citytunnel.json"))
    )


@respx.mock
def test_a_stop_serving_two_categories_is_listed_once(client: TestClient):
    """The observed bug, and the shape of the fix.

    Six rows for three stations become three. Both categories still count all
    three -- `anzahl` is over `kategorien`, not over the label -- so nothing
    claims "nichts gefunden" about something that was found.
    """

    _mock_citytunnel()
    respx.post(MATRIX_URL).mock(side_effect=_by_air)

    body = client.post(
        "/api/nearby",
        json={
            "origin": CITYTUNNEL,
            "kategorien": ["sbahn", "bahnhof"],
            "treffer_je_kategorie": 3,
        },
    ).json()

    assert [hit["name"] for hit in body["treffer"]] == [
        "Leipzig Wilhelm-Leuschner-Platz",
        "Leipzig Markt",
        "Leipzig Bayerischer Bahnhof",
    ]
    # Labelled with the longest-range category it serves, and carrying the rest.
    assert [hit["kategorie"] for hit in body["treffer"]] == ["bahnhof"] * 3
    assert all(hit["kategorien"] == ["sbahn", "bahnhof"] for hit in body["treffer"])
    # `art` already said what calls there; that is unchanged.
    assert body["treffer"][0]["art"] == "Regionalbahn, S-Bahn"
    assert body["treffer"][2]["art"] == "Regionalbahn, S-Bahn, Bus"

    status = {entry["kategorie"]: entry for entry in body["kategorien"]}
    assert status["sbahn"]["anzahl"] == 3
    assert status["bahnhof"]["anzahl"] == 3
    assert status["sbahn"]["hinweis"] is None


@respx.mock
def test_asking_only_for_sbahn_still_returns_the_sbahn_stops(client: TestClient):
    """The dedupe happens after the per-category ranking, so a caller that asks
    one question gets exactly what it asked for."""

    _mock_citytunnel()
    respx.post(MATRIX_URL).mock(side_effect=_by_air)

    body = client.post(
        "/api/nearby",
        json={"origin": CITYTUNNEL, "kategorien": ["sbahn"], "treffer_je_kategorie": 3},
    ).json()

    assert [hit["name"] for hit in body["treffer"]] == [
        "Leipzig Wilhelm-Leuschner-Platz",
        "Leipzig Markt",
        "Leipzig Bayerischer Bahnhof",
    ]
    assert all(hit["kategorie"] == "sbahn" for hit in body["treffer"])
    assert all(hit["kategorien"] == ["sbahn"] for hit in body["treffer"])


@respx.mock
def test_every_stop_appears_exactly_once_across_all_categories(client: TestClient):
    """Seven physical stops, four categories, seven rows -- not twelve."""

    _mock_citytunnel()
    respx.post(MATRIX_URL).mock(side_effect=_by_air)

    body = client.post(
        "/api/nearby",
        json={
            "origin": CITYTUNNEL,
            "kategorien": ["tram", "sbahn", "bus", "bahnhof"],
            "treffer_je_kategorie": 3,
        },
    ).json()

    stop_ids = [hit["stop_id"] for hit in body["treffer"]]
    assert len(stop_ids) == len(set(stop_ids)) == 7
    by_name = {hit["name"]: hit for hit in body["treffer"]}
    assert by_name["Leipzig, Wilhelm-Leuschner-Platz (Tram/Bus)"]["kategorien"] == ["tram", "bus"]
    assert by_name["Leipzig Markt"]["kategorien"] == ["sbahn", "bahnhof"]
    assert by_name["Leipzig Markt"]["kategorie"] == "bahnhof"
    # Two names, two ids, two physical stops: the S-Bahn station under the
    # market square and the bus stop on it are not the same place.
    assert by_name["Leipzig, Markt (Bus)"]["kategorien"] == ["bus"]
    assert by_name["Leipzig, Markt (Bus)"]["stop_id"] != by_name["Leipzig Markt"]["stop_id"]
    # Leipzig Hbf is here as one of the three nearest tram stops -- the three
    # nearer stations beat it in `bahnhof`. The label says why the row is in the
    # list; `art` still says everything that calls there.
    assert by_name["Leipzig Hbf"]["kategorie"] == "tram"
    assert (
        by_name["Leipzig Hbf"]["art"]
        == "Fernverkehr, Regionalbahn, S-Bahn, Straßenbahn, Fernbus, Bus"
    )

    status = {entry["kategorie"]: entry for entry in body["kategorien"]}
    assert [status[k]["anzahl"] for k in ("tram", "sbahn", "bus", "bahnhof")] == [3, 3, 3, 3]


@respx.mock
def test_a_regional_stop_is_a_bahnhof_and_never_an_sbahn(client: TestClient):
    """Leipzig-Liebertwolkwitz carries REGIONAL_RAIL and is served by RB113 to
    Geithain. That is a regional train, not an S-Bahn -- the real S-Bahn stops
    carry SUBURBAN as well, and neither of these does."""

    _mock_stops()
    respx.post(MATRIX_URL).mock(side_effect=_by_air)

    body = client.post(
        "/api/nearby",
        json={"origin": ORIGIN, "kategorien": ["sbahn", "bahnhof"], "umkreis_m": 5000},
    ).json()

    bahnhoefe = [hit for hit in body["treffer"] if hit["kategorie"] == "bahnhof"]
    assert {hit["name"] for hit in bahnhoefe} == {
        "Leipzig-Liebertwolkwitz",
        "Leipzig-Holzhausen",
    }
    assert all(hit["kategorien"] == ["bahnhof"] for hit in bahnhoefe)
    status = {entry["kategorie"]: entry for entry in body["kategorien"]}
    assert status["sbahn"]["verfuegbar"] is True
    assert status["sbahn"]["anzahl"] == 0
    assert "Umkreis" in status["sbahn"]["hinweis"]


@respx.mock
def test_a_merged_stop_shows_the_lines_of_every_mode_it_serves(client: TestClient):
    """Otherwise merging would lose exactly the lines it merged the row for.

    The row is labelled `bahnhof`; filtering on that category alone would drop
    every S-Bahn line at the stop and leave an empty list, which reads as "hier
    faehrt nichts".
    """

    _mock_citytunnel()
    respx.post(MATRIX_URL).mock(side_effect=_by_air)
    stop = respx.get(STOP_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("motis_stop_citytunnel.json"))
    )

    body = client.post(
        "/api/nearby",
        json={
            "origin": CITYTUNNEL,
            "kategorien": ["sbahn", "bahnhof"],
            "treffer_je_kategorie": 1,
            "linien": True,
        },
    ).json()

    assert stop.call_count == 1
    assert body["treffer"][0]["name"] == "Leipzig Wilhelm-Leuschner-Platz"
    assert body["treffer"][0]["kategorie"] == "bahnhof"
    assert body["treffer"][0]["linien"] == ["S1", "S2", "S3", "S4", "S5", "S5X"]


@respx.mock
def test_an_osm_place_carries_exactly_its_own_category(poi_index, client: TestClient):
    """A school is a school. Only stops can be several things at once."""

    respx.post(MATRIX_URL).mock(side_effect=_by_air)

    treffer = client.post(
        "/api/nearby", json={"origin": ORIGIN, "kategorien": ["schule", "supermarkt"]}
    ).json()["treffer"]

    assert treffer
    assert all(hit["kategorien"] == [hit["kategorie"]] for hit in treffer)
    assert all(hit["stop_id"] is None for hit in treffer)


@respx.mock
def test_a_category_a_stop_was_not_found_for_is_not_claimed(client: TestClient):
    """`kategorien` lists what the hit was found for, not every mode it serves.

    Leipzig-Liebertwolkwitz carries REGIONAL_RAIL *and* BUS, but two bus stops
    in the village are nearer, so it is not one of the two nearest bus stops and
    does not claim to be. `art` still says "Regionalbahn, Bus".
    """

    _mock_stops()
    respx.post(MATRIX_URL).mock(side_effect=_by_air)

    body = client.post(
        "/api/nearby",
        json={
            "origin": ORIGIN,
            "kategorien": ["bus", "bahnhof"],
            "umkreis_m": 5000,
            "treffer_je_kategorie": 2,
        },
    ).json()

    station = next(hit for hit in body["treffer"] if hit["name"] == "Leipzig-Liebertwolkwitz")
    assert station["kategorien"] == ["bahnhof"]
    assert station["art"] == "Regionalbahn, Bus"
    status = {entry["kategorie"]: entry for entry in body["kategorien"]}
    # Never more than treffer_je_kategorie, whatever the merging did.
    assert status["bus"]["anzahl"] == 2
    assert status["bahnhof"]["anzahl"] == 2
