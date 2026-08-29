"""POST /api/geocode -- free text to coordinates the user can check.

The routing geocoder is confidently wrong often enough that a single silent
coordinate would be worse than none: it answers a Saxon street name with a
village in Bavaria. So these tests care that the labels travel with the
coordinates and that the answer says where the coordinates come from.
"""

from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from .conftest import MOTIS_URL, fixture_json

GEOCODE_URL = f"{MOTIS_URL}/api/v1/geocode"


def _answer() -> httpx.Response:
    return httpx.Response(200, json=fixture_json("motis_geocode_kandidaten.json"))


@respx.mock
def test_candidates_arrive_with_the_label_that_was_matched(client: TestClient):
    respx.get(GEOCODE_URL).mock(return_value=_answer())

    answer = client.post("/api/geocode", json={"text": "Bahnhof Wurzen"})

    assert answer.status_code == 200
    treffer = answer.json()["treffer"]
    assert treffer[0]["name"] == "Wurzen, Bahnhof (Bus)"
    assert treffer[0]["art"] == "haltestelle"
    assert treffer[0]["lat"] == 51.364662
    assert treffer[0]["lon"] == 12.737755


@respx.mock
def test_the_description_tells_two_hits_apart(client: TestClient):
    respx.get(GEOCODE_URL).mock(return_value=_answer())

    treffer = client.post("/api/geocode", json={"text": "Bahnhof Wurzen"}).json()["treffer"]
    nach_name = {hit["name"]: hit for hit in treffer}

    assert nach_name["Alte Dorfstraße 12"]["beschreibung"] == "04808 Wurzen, Dehnitz, Sachsen"
    assert nach_name["Alte Dorfstraße 12"]["art"] == "adresse"
    # The state is what gives the classic wrong hit away.
    assert "Bayern" in nach_name["Am Kirschberg"]["beschreibung"]
    assert nach_name["Am Kirschberg"]["art"] == "ort"


@respx.mock
def test_at_most_five_candidates_come_back(client: TestClient):
    respx.get(GEOCODE_URL).mock(return_value=_answer())

    treffer = client.post("/api/geocode", json={"text": "Bahnhof Wurzen"}).json()["treffer"]

    assert len(treffer) == 5
    # Entries without a coordinate or without a label are of no use to anyone.
    assert all(hit["name"] for hit in treffer)
    assert "Ohne Koordinate" not in [hit["name"] for hit in treffer]


@respx.mock
def test_the_answer_says_the_coordinate_is_not_an_official_one(client: TestClient):
    respx.get(GEOCODE_URL).mock(return_value=_answer())

    body = client.post("/api/geocode", json={"text": "Bahnhof Wurzen"}).json()

    assert "Hauskoordinaten" in body["hinweis"]
    assert "Transitous" in body["quelle"]


@respx.mock
def test_a_coordinate_biases_the_search_without_filtering_it(client: TestClient):
    route = respx.get(GEOCODE_URL).mock(return_value=_answer())

    answer = client.post(
        "/api/geocode", json={"text": "Am Kirschberg", "lat": 51.366, "lon": 12.735}
    )

    assert answer.status_code == 200
    assert route.calls[0].request.url.params["place"] == "51.366,12.735"


@respx.mock
def test_without_a_bias_no_place_parameter_is_sent(client: TestClient):
    route = respx.get(GEOCODE_URL).mock(return_value=_answer())

    client.post("/api/geocode", json={"text": "Bahnhof Wurzen"})

    assert "place" not in route.calls[0].request.url.params


@respx.mock
def test_nothing_found_is_a_404_that_says_what_to_try(client: TestClient):
    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=[]))

    answer = client.post("/api/geocode", json={"text": "Gibtsnichtstraße 1"})

    assert answer.status_code == 404
    detail = answer.json()["detail"]
    assert "Gibtsnichtstraße 1" in detail
    assert "Karte" in detail


@respx.mock
def test_the_second_call_for_the_same_text_comes_from_the_cache(client: TestClient):
    route = respx.get(GEOCODE_URL).mock(return_value=_answer())

    first = client.post("/api/geocode", json={"text": "Bahnhof Wurzen"})
    second = client.post("/api/geocode", json={"text": "Bahnhof Wurzen"})

    assert route.call_count == 1
    assert first.json() == second.json()


@respx.mock
def test_a_bias_is_part_of_the_cache_key(client: TestClient):
    # Same text, different reference point -- that is a different question.
    route = respx.get(GEOCODE_URL).mock(return_value=_answer())

    client.post("/api/geocode", json={"text": "Am Kirschberg"})
    client.post("/api/geocode", json={"text": "Am Kirschberg", "lat": 51.3, "lon": 12.3})

    assert route.call_count == 2


def test_half_a_bias_is_refused_in_german(client: TestClient):
    answer = client.post("/api/geocode", json={"text": "Bahnhof Wurzen", "lat": 51.3})

    assert answer.status_code == 422
    assert "gemeinsam" in answer.json()["detail"]


def test_an_empty_search_text_is_refused(client: TestClient):
    answer = client.post("/api/geocode", json={"text": "a"})

    assert answer.status_code == 422
    assert "text" in answer.json()["detail"]


@respx.mock
def test_an_unreachable_geocoder_is_a_502_that_names_the_other_ways_in(client: TestClient):
    respx.get(GEOCODE_URL).mock(side_effect=httpx.ConnectError("kein Netz"))

    answer = client.post("/api/geocode", json={"text": "Bahnhof Wurzen"})

    assert answer.status_code == 502
    detail = answer.json()["detail"]
    assert "Flurstücksnummer" in detail
    assert "Traceback" not in answer.text


@respx.mock
def test_a_slow_geocoder_is_a_504(client: TestClient):
    respx.get(GEOCODE_URL).mock(side_effect=httpx.ReadTimeout("langsam"))

    assert client.post("/api/geocode", json={"text": "Bahnhof Wurzen"}).status_code == 504


@respx.mock
def test_resolving_an_address_to_a_parcel_still_uses_the_best_hit(client: TestClient):
    # /api/parcels/resolve keeps its one-coordinate behaviour.
    from .conftest import ALKIS_URL, fixture_bytes

    respx.get(GEOCODE_URL).mock(return_value=_answer())
    respx.get(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_single.gml"))
    )

    answer = client.post("/api/parcels/resolve", json={"address": "Bahnhof Wurzen"})

    assert answer.status_code == 200
    assert "Hauskoordinaten" in answer.json()["hinweis"]
