"""MOTIS: polyline precision, direct vs. transit results, geometry assembly."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.deps import motis_service
from app.schemas import Koordinate, Ziel
from app.services.motis import (
    decode_polyline,
    itinerary_to_linestring,
    leg_geometry_to_coordinates,
)

from .conftest import MOTIS_URL, fixture_json

PLAN_URL = f"{MOTIS_URL}/api/v6/plan"
GEOCODE_URL = f"{MOTIS_URL}/api/v1/geocode"

ORIGIN = Koordinate(lat=51.3397, lon=12.3731)
DESTINATION = Ziel(id="arbeit", lat=51.0400, lon=13.7322, name="Dresden Hbf")


def _train_geometry() -> dict:
    plan = fixture_json("motis_plan_transit.json")
    return plan["itineraries"][0]["legs"][1]["legGeometry"]


def test_precision_six_puts_the_route_in_saxony():
    geometry = _train_geometry()
    assert geometry["precision"] == 6

    points = decode_polyline(geometry["points"], 6)

    first_lat, first_lon = points[0]
    last_lat, last_lon = points[-1]
    assert 50.0 < first_lat < 52.0 and 12.0 < first_lon < 15.0
    assert 50.0 < last_lat < 52.0 and 12.0 < last_lon < 15.0
    assert first_lat == pytest.approx(51.345488, abs=1e-6)
    assert last_lon == pytest.approx(13.731396, abs=1e-6)


def test_precision_five_is_off_by_a_factor_of_ten():
    # The usual Google default is 5; MOTIS uses 6. Getting this wrong moves the
    # route right off the planet instead of failing loudly.
    points = decode_polyline(_train_geometry()["points"], 5)

    first_lat, first_lon = points[0]
    assert first_lat == pytest.approx(513.45488, abs=1e-5)
    assert first_lon == pytest.approx(123.82021, abs=1e-5)
    assert not (50.0 < first_lat < 52.0)


def test_the_precision_from_the_response_is_used():
    coordinates = leg_geometry_to_coordinates(_train_geometry())

    # GeoJSON order is [lon, lat].
    lon, lat = coordinates[0]
    assert 12.0 < lon < 15.0
    assert 50.0 < lat < 52.0


def test_legs_are_concatenated_into_one_linestring():
    itinerary = fixture_json("motis_plan_transit.json")["itineraries"][0]

    geometry = itinerary_to_linestring(itinerary)

    assert geometry["type"] == "LineString"
    # 3 + 4 + 2 points, minus the one duplicate where two legs meet.
    assert len(geometry["coordinates"]) == 8
    assert all(len(point) == 2 for point in geometry["coordinates"])


@respx.mock
async def test_transit_route_is_read_from_itineraries():
    respx.get(PLAN_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("motis_plan_transit.json"))
    )

    result = await motis_service().route(ORIGIN, DESTINATION, "transit")

    assert result.erreichbar is True
    assert result.duration_s == 4860
    assert result.umstiege == 1
    assert result.geometry.type == "LineString"
    assert [leg.mode for leg in result.teilstrecken] == ["WALK", "HIGHSPEED_RAIL", "WALK"]

    params = respx.calls[0].request.url.params
    assert params["transitModes"] == "TRANSIT"
    assert params["preTransitModes"] == "WALK"


@respx.mock
async def test_car_route_is_read_from_direct():
    # Direct modes never appear in `itineraries` -- reading only that array
    # would silently drop every car, bike and foot route.
    respx.get(PLAN_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("motis_plan_car.json"))
    )

    result = await motis_service().route(ORIGIN, DESTINATION, "car")

    assert result.erreichbar is True
    assert result.duration_s == 4676
    assert result.teilstrecken[0].mode == "CAR"

    params = respx.calls[0].request.url.params
    assert params["directModes"] == "CAR"
    assert params["transitModes"] == ""


@respx.mock
async def test_bike_feeder_raises_the_pre_transit_limit():
    respx.get(PLAN_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("motis_plan_transit.json"))
    )

    await motis_service().route(ORIGIN, DESTINATION, "bike_transit")

    params = respx.calls[0].request.url.params
    assert params["preTransitModes"] == "BIKE"
    # The MOTIS default of 900 s would drop most bike feeders.
    assert int(params["maxPreTransitTime"]) > 900


@respx.mock
async def test_missing_connection_is_reported_not_raised():
    respx.get(PLAN_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("motis_plan_leer.json"))
    )

    result = await motis_service().route(ORIGIN, DESTINATION, "transit")

    assert result.erreichbar is False
    assert result.duration_s is None
    assert "keine Verbindung" in result.hinweis


@respx.mock
async def test_every_destination_and_mode_is_routed():
    respx.get(PLAN_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("motis_plan_car.json"))
    )

    answer = await motis_service().reachability(
        ORIGIN,
        [DESTINATION, Ziel(id="schule", lat=51.05, lon=13.74)],
        ["car", "walk"],
    )

    assert len(answer.ergebnisse) == 4
    assert {result.destination_id for result in answer.ergebnisse} == {"arbeit", "schule"}


@respx.mock
async def test_geocoding_returns_the_first_coordinate():
    respx.get(GEOCODE_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("motis_geocode.json"))
    )

    coordinate = await motis_service().geocode("Muldentalstraße 12, 04288 Leipzig")

    assert coordinate.lat == pytest.approx(51.2783)
    assert coordinate.lon == pytest.approx(12.4819)


@respx.mock
async def test_user_agent_is_sent_as_the_usage_policy_requires():
    respx.get(PLAN_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("motis_plan_car.json"))
    )

    await motis_service().route(ORIGIN, DESTINATION, "car")

    assert respx.calls[0].request.headers["user-agent"].startswith("GrundstuecksCheckSachsen")
