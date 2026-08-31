"""POST /api/neighbours -- the building outlines the neighbour hint is drawn from.

Every test runs against ``fixtures/overpass_moelkau_buildings.json``, a **real**
``[out:json]`` answer from ``overpass-api.de`` (generator 0.7.62.11,
``timestamp_osm_base`` 2026-08-31T15:31:03Z) for a 125 m circle around Mölkau
Flurstück 204, Lessingweg 44 -- the plot the frontend fixture
``parcel-moelkau.json`` describes. 59 ways, mostly addressed, and 48 of them
without any ``building:levels`` -- which is the fact the whole feature has to
live with.
"""

from __future__ import annotations

from urllib.parse import unquote_plus

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.services.overpass import build_building_query, rings_from_elements

from .conftest import OVERPASS_URL, fixture_json

ANSWER = "overpass_moelkau_buildings.json"

# The anchor of Mölkau 204.
ORIGIN = {"lat": 51.33653, "lon": 12.44180}


def _answer(name: str = ANSWER) -> httpx.Response:
    return httpx.Response(200, json=fixture_json(name))


def test_the_query_asks_for_outlines_not_centres():
    query = build_building_query(51.3365, 12.4418, 125, 25)

    assert 'way["building"](around:125,51.3365,12.4418)' in query
    # `out center` would give a point per building, which cannot be measured
    # against a boundary.
    assert "out tags geom;" in query
    assert "[timeout:25]" in query


def test_rings_are_closed_and_carry_the_address():
    buildings = rings_from_elements(fixture_json(ANSWER)["elements"])

    assert len(buildings) == 59
    for building in buildings:
        assert building["umriss"][0] == building["umriss"][-1]
        assert len(building["umriss"]) >= 4
        assert building["osm_id"].startswith("W")
    addresses = {building["adresse"] for building in buildings}
    assert "Lessingweg 30" in addresses


def test_a_way_without_geometry_is_not_an_outline():
    assert rings_from_elements(
        [
            {"type": "way", "id": 1, "tags": {"building": "yes"}},
            {"type": "way", "id": 2, "geometry": [{"lat": 51.0, "lon": 12.0}]},
            {"type": "node", "id": 3, "lat": 51.0, "lon": 12.0},
        ]
    ) == []


def test_wall_heights_are_passed_on_only_where_osm_has_them():
    buildings = rings_from_elements(fixture_json(ANSWER)["elements"])

    with_levels = [b for b in buildings if b["geschosse"] is not None]
    # 11 of 59 in an ordinary Leipzig residential street, and a storey count is
    # not a wall height anyway. Nothing is guessed for the other 48 -- see
    # docs/research/abstandsflaechen-nachbargebaeude.md.
    assert len(with_levels) == 11
    assert all(1 <= b["geschosse"] <= 60 for b in with_levels)


def test_an_absurd_level_count_is_dropped_rather_than_believed():
    buildings = rings_from_elements(
        [
            {
                "type": "way",
                "id": 7,
                "tags": {"building": "yes", "building:levels": "0"},
                "geometry": [
                    {"lat": 51.0, "lon": 12.0},
                    {"lat": 51.0, "lon": 12.001},
                    {"lat": 51.001, "lon": 12.001},
                    {"lat": 51.0, "lon": 12.0},
                ],
            }
        ]
    )

    assert buildings[0]["geschosse"] is None


@respx.mock
def test_the_endpoint_answers_with_outlines_and_says_where_they_came_from(
    overpass, client: TestClient
):
    route = respx.post(OVERPASS_URL).mock(return_value=_answer())

    answer = client.post("/api/neighbours", json={"origin": ORIGIN, "umkreis_m": 80})

    assert answer.status_code == 200
    body = answer.json()
    assert len(body["gebaeude"]) == 59
    assert body["quelle"] == OVERPASS_URL
    assert body["datenstand"] == "2026-08-31T15:31:03Z"
    assert "OpenStreetMap" in body["hinweis"]
    assert "3 m" in body["hinweis"]
    assert route.called


@respx.mock
def test_a_plot_sized_question_is_not_turned_into_a_city_sized_one(
    overpass, client: TestClient
):
    """The POI rounding would answer 80 m with 1 200 m -- 1 670 buildings."""

    route = respx.post(OVERPASS_URL).mock(return_value=_answer())

    client.post("/api/neighbours", json={"origin": ORIGIN, "umkreis_m": 80})

    sent = unquote_plus(route.calls.last.request.content.decode())
    assert "around:125," in sent


@respx.mock
def test_two_views_of_one_plot_cost_one_query(overpass, client: TestClient):
    route = respx.post(OVERPASS_URL).mock(return_value=_answer())

    for _ in range(3):
        client.post("/api/neighbours", json={"origin": ORIGIN, "umkreis_m": 80})

    assert route.call_count == 1


def test_without_a_source_the_answer_says_how_to_get_one(client: TestClient):
    answer = client.post("/api/neighbours", json={"origin": ORIGIN, "umkreis_m": 80})

    assert answer.status_code >= 400
    detail = answer.json()["detail"]
    assert "OVERPASS_ENABLED" in detail
    assert "OpenStreetMap" in detail


@pytest.mark.parametrize("radius", [10, 500])
def test_an_implausible_radius_is_refused(radius: int, overpass, client: TestClient):
    answer = client.post("/api/neighbours", json={"origin": ORIGIN, "umkreis_m": radius})

    assert answer.status_code == 422
