"""POST /api/reachability."""

from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from .conftest import MOTIS_URL, fixture_json

PLAN_URL = f"{MOTIS_URL}/api/v6/plan"

REQUEST = {
    "origin": {"lat": 51.3397, "lon": 12.3731},
    "destinations": [
        {"id": "arbeit", "lat": 51.0400, "lon": 13.7322, "name": "Dresden Hbf"},
    ],
    "modes": ["car"],
}


@respx.mock
def test_route_duration_and_geometry_per_destination(client: TestClient):
    respx.get(PLAN_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("motis_plan_car.json"))
    )

    answer = client.post("/api/reachability", json=REQUEST)

    assert answer.status_code == 200
    ergebnis = answer.json()["ergebnisse"][0]
    assert ergebnis["destination_id"] == "arbeit"
    assert ergebnis["mode"] == "car"
    assert ergebnis["erreichbar"] is True
    assert ergebnis["duration_s"] == 4676
    assert ergebnis["geometry"]["type"] == "LineString"
    lon, lat = ergebnis["geometry"]["coordinates"][0]
    assert 12.0 < lon < 15.0 and 50.0 < lat < 52.0


@respx.mock
def test_one_result_per_destination_and_mode(client: TestClient):
    respx.get(PLAN_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("motis_plan_transit.json"))
    )

    answer = client.post(
        "/api/reachability",
        json={
            **REQUEST,
            "destinations": REQUEST["destinations"]
            + [{"id": "schule", "lat": 51.05, "lon": 13.74}],
            "modes": ["transit", "bike_transit"],
        },
    )

    ergebnisse = answer.json()["ergebnisse"]
    assert len(ergebnisse) == 4
    assert {(e["destination_id"], e["mode"]) for e in ergebnisse} == {
        ("arbeit", "transit"),
        ("arbeit", "bike_transit"),
        ("schule", "transit"),
        ("schule", "bike_transit"),
    }


@respx.mock
def test_unreachable_destination_is_reported_not_an_error(client: TestClient):
    respx.get(PLAN_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("motis_plan_leer.json"))
    )

    answer = client.post("/api/reachability", json=REQUEST)

    assert answer.status_code == 200
    assert answer.json()["ergebnisse"][0]["erreichbar"] is False


def test_request_without_destinations_is_a_422(client: TestClient):
    answer = client.post(
        "/api/reachability", json={"origin": {"lat": 51.3, "lon": 12.3}, "destinations": []}
    )

    assert answer.status_code == 422


def test_unknown_mode_is_a_422(client: TestClient):
    assert (
        client.post("/api/reachability", json={**REQUEST, "modes": ["helikopter"]}).status_code
        == 422
    )


@respx.mock
def test_broken_json_from_the_router_is_a_502(client: TestClient):
    respx.get(PLAN_URL).mock(return_value=httpx.Response(200, text="kein json"))

    answer = client.post("/api/reachability", json=REQUEST)

    assert answer.status_code == 502
    assert "Traceback" not in answer.text


@respx.mock
def test_slow_router_is_a_504(client: TestClient):
    respx.get(PLAN_URL).mock(side_effect=httpx.ReadTimeout("langsam"))

    assert client.post("/api/reachability", json=REQUEST).status_code == 504
