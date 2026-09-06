"""POST /api/neighbours -- the building outlines the neighbour hint is drawn from.

The outlines come from the cadastre; ``fixtures/alkis_gebaeude_moelkau.gml`` is a
real GetFeature answer for ``ave:GebaeudeBauwerk`` over Mölkau 204. The Overpass
path stays as the fallback, and its tests run against
``fixtures/overpass_moelkau_buildings.json``, a **real**
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

from .conftest import ALKIS_URL, OVERPASS_URL, fixture_bytes, fixture_json

ANSWER = "overpass_moelkau_buildings.json"
# A real GetFeature answer for ave:GebaeudeBauwerk over the same plot: a 90 m
# box around Mölkau 204, 25 outlines, eleven of them with a Lagebezeichnung.
CADASTRE = "alkis_gebaeude_moelkau.gml"

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
        assert building["id"].startswith("W")
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
def test_the_outlines_come_from_the_cadastre_without_any_osm_source(client: TestClient):
    """The register that delivers the parcel delivers the buildings: same WFS,
    same proxy, same disk cache — and nothing to configure."""

    route = respx.get(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes(CADASTRE))
    )

    answer = client.post("/api/neighbours", json={"origin": ORIGIN, "umkreis_m": 80})

    assert answer.status_code == 200
    body = answer.json()
    assert len(body["gebaeude"]) == 25
    assert "ALKIS" in body["quelle"]
    first = body["gebaeude"][0]
    assert first["umriss"][0] == first["umriss"][-1]
    assert first["id"].startswith("DESNALK")
    assert {b["adresse"] for b in body["gebaeude"]} & {"Lessingweg 48", "Lessingweg 33"}
    assert {b["funktion"] for b in body["gebaeude"]} >= {"Wohngebäude"}
    # The simplified ALKIS carries no storeys, so nothing is invented from it.
    assert all(b["geschosse"] is None for b in body["gebaeude"])
    # The sentence names the source it actually had, and what is computable
    # from it: no wall heights here either, so 3 m and never 0,4 H.
    assert "Liegenschaftskataster" in body["hinweis"]
    assert "OpenStreetMap" not in body["hinweis"]
    assert "3 m" in body["hinweis"]

    sent = route.calls.last.request.url.params
    assert sent["TYPENAMES"] == "ave:GebaeudeBauwerk"
    assert "BBOX" in sent


@respx.mock
def test_the_same_plot_asked_twice_costs_one_query(client: TestClient):
    route = respx.get(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes(CADASTRE))
    )

    for _ in range(3):
        client.post("/api/neighbours", json={"origin": ORIGIN, "umkreis_m": 80})

    assert route.call_count == 1


@respx.mock
def test_overpass_answers_when_the_cadastre_cannot(overpass, client: TestClient):
    """Whoever has an Overpass instance keeps it: OSM maps garden sheds the
    cadastre leaves out, and it is the only source of storeys at all."""

    respx.get(ALKIS_URL).mock(return_value=httpx.Response(503, text="weg"))
    route = respx.post(OVERPASS_URL).mock(return_value=_answer())

    body = client.post("/api/neighbours", json={"origin": ORIGIN, "umkreis_m": 80}).json()

    assert len(body["gebaeude"]) == 59
    assert body["quelle"] == OVERPASS_URL
    assert body["datenstand"] == "2026-08-31T15:31:03Z"
    assert route.called


@respx.mock
def test_a_plot_sized_question_is_not_turned_into_a_city_sized_one(
    overpass, client: TestClient
):
    """The POI rounding would answer 80 m with 1 200 m -- 1 670 buildings."""

    respx.get(ALKIS_URL).mock(return_value=httpx.Response(503, text="weg"))
    route = respx.post(OVERPASS_URL).mock(return_value=_answer())

    client.post("/api/neighbours", json={"origin": ORIGIN, "umkreis_m": 80})

    sent = unquote_plus(route.calls.last.request.content.decode())
    assert "around:125," in sent


@respx.mock
def test_without_any_source_the_cadastre_error_is_what_is_shown(client: TestClient):
    """No Overpass configured is no longer a missing source — it only means the
    fallback is missing, and what the user reads is why ALKIS said no."""

    respx.get(ALKIS_URL).mock(return_value=httpx.Response(503, text="weg"))

    answer = client.post("/api/neighbours", json={"origin": ORIGIN, "umkreis_m": 80})

    assert answer.status_code >= 400
    assert "Liegenschaftskataster" in answer.json()["detail"]


@pytest.mark.parametrize("radius", [10, 500])
def test_an_implausible_radius_is_refused(radius: int, client: TestClient):
    answer = client.post("/api/neighbours", json={"origin": ORIGIN, "umkreis_m": radius})

    assert answer.status_code == 422
