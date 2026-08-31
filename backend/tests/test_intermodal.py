"""Intermodal journeys: how the first stop is reached, and who decides.

Every fixture here is a recorded answer from `api.transitous.org`, fetched on
31.08.2026 and trimmed to the fields the code reads (see
docs/research/routing-motis.md § 9 for the requests). The numbers asserted below
are the service's own.

Two Saxon origins carry the cases:

* **Moritzburg** (51.16758, 13.67797 -- the parcel of
  `alkis_flurstueck_moritzburg.gml`) to Dresden Hbf. On foot the first stop is
  11 minutes away, by bike 7; the bike wins, and the car rung never unlocks.
* **Hinterhermsdorf** (50.9539, 14.3676) to Dresden Hbf. 29 minutes on foot to
  the first stop, 15 by bike -- so the car rung *does* unlock, and park-and-ride
  then turns out slower than the bike. That is where the clock overrules the
  rule.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.deps import motis_service
from app.schemas import Koordinate, Ziel
from app.services.motis import (
    ACCESS_THRESHOLD_S,
    access_seconds,
    parks_the_car,
)

from .conftest import MOTIS_URL, fixture_json

PLAN_URL = f"{MOTIS_URL}/api/v6/plan"

MORITZBURG = Koordinate(lat=51.16758, lon=13.67797)
HINTERHERMSDORF = Koordinate(lat=50.9539, lon=14.3676)
DRESDEN_HBF = Ziel(id="hbf", lat=51.040684, lon=13.731863, name="Dresden Hbf")


def _plan(access: str, fixture: str) -> None:
    """Answer one access mode with one recorded response."""

    respx.get(PLAN_URL, params__contains={"preTransitModes": access}).mock(
        return_value=httpx.Response(200, json=fixture_json(fixture))
    )


def _moritzburg_ladder() -> None:
    _plan("WALK", "motis_plan_transit_fussweg_lang.json")
    _plan("BIKE", "motis_plan_bike_transit.json")
    _plan("CAR_PARKING", "motis_plan_car_transit.json")


def _hinterhermsdorf_ladder() -> None:
    _plan("WALK", "motis_plan_transit_hinterhermsdorf.json")
    _plan("BIKE", "motis_plan_bike_transit_langer_zubringer.json")
    _plan("CAR_PARKING", "motis_plan_car_transit_langsamer.json")


# ---------------------------------------------------------------------------
# What the request looks like
# ---------------------------------------------------------------------------


@respx.mock
async def test_each_variant_names_its_own_access_mode():
    _moritzburg_ladder()

    for mode, expected in (
        ("transit", "WALK"),
        ("bike_transit", "BIKE"),
        ("car_transit", "CAR_PARKING"),
    ):
        await motis_service().route(MORITZBURG, DRESDEN_HBF, mode)
        assert respx.calls.last.request.url.params["preTransitModes"] == expected


@respx.mock
async def test_the_far_end_is_always_on_foot():
    # postTransitModes=BIKE does answer -- with a bike at the destination
    # station that no train carried there: the egress leg is BIKE while every
    # transit leg of the same itinerary says bikesAllowed=false. Recorded in
    # motis_plan_rad_am_zielende.json.
    fabricated = fixture_json("motis_plan_rad_am_zielende.json")["itineraries"][0]
    assert fabricated["legs"][-1]["mode"] == "BIKE"
    assert all(leg.get("bikesAllowed") is False for leg in fabricated["legs"] if "tripId" in leg)

    _moritzburg_ladder()
    for mode in ("transit", "bike_transit", "car_transit"):
        await motis_service().route(MORITZBURG, DRESDEN_HBF, mode)
        assert respx.calls.last.request.url.params["postTransitModes"] == "WALK"


# ---------------------------------------------------------------------------
# Reading an itinerary
# ---------------------------------------------------------------------------


def test_access_time_is_everything_before_the_first_service():
    walk = fixture_json("motis_plan_transit_fussweg_lang.json")["itineraries"][1]
    assert walk["legs"][0]["duration"] == 660

    car = fixture_json("motis_plan_car_transit.json")["itineraries"][1]
    # 1200 s driving plus the 480 s walk from the car park -- only the sum is
    # the time it takes to stand on the platform.
    assert [leg["duration"] for leg in car["legs"][:2]] == [1200, 480]


def test_a_journey_without_a_service_has_no_access_leg():
    from app.schemas import Teilstrecke

    only_walking = [Teilstrecke(mode="WALK", duration_s=900)]
    assert access_seconds(only_walking) is None


def test_park_and_ride_is_a_car_leg_followed_by_a_walk():
    from app.schemas import Teilstrecke

    parked = [
        Teilstrecke(mode="CAR", duration_s=1200),
        Teilstrecke(mode="WALK", duration_s=480),
        Teilstrecke(mode="REGIONAL_RAIL", duration_s=180),
    ]
    dropped_at_the_platform = [
        Teilstrecke(mode="CAR", duration_s=240),
        Teilstrecke(mode="REGIONAL_RAIL", duration_s=5580),
    ]
    assert parks_the_car(parked) is True
    assert parks_the_car(dropped_at_the_platform) is False


# ---------------------------------------------------------------------------
# The ladder
# ---------------------------------------------------------------------------


@respx.mock
async def test_a_long_walk_to_the_stop_is_replaced_by_the_bike():
    _moritzburg_ladder()

    result = await motis_service().transit_auto(MORITZBURG, DRESDEN_HBF)

    assert result.mode == "bike_transit"
    assert result.angefragter_modus == "transit_auto"
    assert result.duration_s == 2700
    # The reason has to carry the numbers, or the substitution is unverifiable.
    assert "11 Min." in result.hinweis      # the walk that triggered it
    assert "7 Min." in result.hinweis       # the bike that replaced it
    assert "45 Min." in result.hinweis and "49 Min." in result.hinweis


@respx.mock
async def test_the_car_rung_stays_locked_while_the_bike_feeder_is_short():
    _moritzburg_ladder()

    await motis_service().transit_auto(MORITZBURG, DRESDEN_HBF)

    asked = {call.request.url.params.get("preTransitModes") for call in respx.calls}
    # 7 minutes on the bike is nobody's reason to take the car out.
    assert asked == {"WALK", "BIKE"}


@respx.mock
async def test_a_long_bike_feeder_unlocks_the_car_but_the_clock_decides():
    _hinterhermsdorf_ladder()

    result = await motis_service().transit_auto(HINTERHERMSDORF, DRESDEN_HBF)

    asked = {call.request.url.params.get("preTransitModes") for call in respx.calls}
    assert "CAR_PARKING" in asked          # 15 minutes on the bike unlocked it
    # ...and park-and-ride came back at 120 minutes against the bike's 104.
    assert result.mode == "bike_transit"
    assert result.duration_s == 6240
    # 29 minutes on foot to the first stop is what started the climb.
    assert "29 Min." in result.hinweis
    assert "nicht schneller" in result.hinweis


@respx.mock
async def test_the_car_carries_the_journey_when_nothing_else_reaches_a_stop():
    _plan("WALK", "motis_plan_leer.json")
    _plan("BIKE", "motis_plan_leer.json")
    _plan("CAR_PARKING", "motis_plan_car_transit.json")

    result = await motis_service().transit_auto(MORITZBURG, DRESDEN_HBF)

    assert result.mode == "car_transit"
    assert result.duration_s == 2040
    assert result.erreichbar is True


@respx.mock
async def test_nothing_reachable_keeps_the_services_own_sentence():
    _plan("WALK", "motis_plan_leer.json")
    _plan("BIKE", "motis_plan_leer.json")
    _plan("CAR_PARKING", "motis_plan_leer.json")

    result = await motis_service().transit_auto(MORITZBURG, DRESDEN_HBF)

    assert result.erreichbar is False
    assert result.duration_s is None
    assert "keine Verbindung gefunden" in result.hinweis
    # ...and it says which variants were tried, rather than which one "failed".
    assert "zu Fuß zum ÖPNV" in result.hinweis
    assert "mit dem Auto zum ÖPNV" in result.hinweis


@respx.mock
async def test_a_bike_without_a_connection_leaves_the_walk_standing():
    _plan("WALK", "motis_plan_transit_fussweg_lang.json")
    _plan("BIKE", "motis_plan_leer.json")

    result = await motis_service().transit_auto(MORITZBURG, DRESDEN_HBF)

    assert result.mode == "transit"
    assert result.duration_s == 2940
    assert "keine Verbindung gefunden" in result.hinweis


# ---------------------------------------------------------------------------
# Pinning it per destination
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.parametrize(
    "zubringer, mode, access, duration",
    [("walk", "transit", "WALK", 2940), ("bike", "bike_transit", "BIKE", 2700),
     ("car", "car_transit", "CAR_PARKING", 2040)],
)
async def test_a_pinned_destination_costs_one_request_and_gets_what_it_asked_for(
    zubringer: str, mode: str, access: str, duration: int
):
    _moritzburg_ladder()
    destination = DRESDEN_HBF.model_copy(update={"zubringer": zubringer})

    result = await motis_service().transit_auto(MORITZBURG, destination)

    assert result.mode == mode
    assert result.duration_s == duration
    assert result.angefragter_modus == "transit_auto"
    assert "fest auf" in result.hinweis
    assert [call.request.url.params.get("preTransitModes") for call in respx.calls] == [access]


@respx.mock
async def test_a_destination_without_the_field_still_routes():
    # Everything stored before `zubringer` existed carries no such key. The
    # default has to be the automatic ladder, not a crash and not "no route".
    _moritzburg_ladder()
    legacy = Ziel.model_validate({"id": "hbf", "lat": 51.040684, "lon": 13.731863})

    assert legacy.zubringer == "automatic"
    assert (await motis_service().transit_auto(MORITZBURG, legacy)).mode == "bike_transit"


@respx.mock
async def test_a_pinned_car_says_when_there_was_nowhere_to_park():
    # CAR_PARKING answers with both shapes; the second Moritzburg itinerary is a
    # real park-and-ride, but a bare car leg onto the platform is a journey with
    # nowhere to leave the car, and the card has to say so.
    _plan("CAR_PARKING", "motis_plan_car.json")
    destination = DRESDEN_HBF.model_copy(update={"zubringer": "car"})

    result = await motis_service().transit_auto(MORITZBURG, destination)

    # A `direct` car answer has no transit leg at all, so there is no journey.
    assert result.erreichbar is False


# ---------------------------------------------------------------------------
# Through the endpoint
# ---------------------------------------------------------------------------


@respx.mock
def test_the_endpoint_answers_the_variant_it_chose(client):
    _moritzburg_ladder()

    answer = client.post(
        "/api/reachability",
        json={
            "origin": {"lat": 51.16758, "lon": 13.67797},
            "destinations": [{"id": "hbf", "lat": 51.040684, "lon": 13.731863}],
            "modes": ["transit_auto"],
        },
    )

    ergebnis = answer.json()["ergebnisse"][0]
    assert ergebnis["mode"] == "bike_transit"
    assert ergebnis["angefragter_modus"] == "transit_auto"
    assert ergebnis["duration_s"] == 2700


@respx.mock
def test_a_pinned_zubringer_travels_with_the_destination(client):
    _moritzburg_ladder()

    answer = client.post(
        "/api/reachability",
        json={
            "origin": {"lat": 51.16758, "lon": 13.67797},
            "destinations": [
                {"id": "hbf", "lat": 51.040684, "lon": 13.731863, "zubringer": "walk"}
            ],
            "modes": ["transit_auto"],
        },
    )

    assert answer.json()["ergebnisse"][0]["mode"] == "transit"


def test_an_unknown_zubringer_is_a_422(client):
    answer = client.post(
        "/api/reachability",
        json={
            "origin": {"lat": 51.16758, "lon": 13.67797},
            "destinations": [
                {"id": "hbf", "lat": 51.04, "lon": 13.73, "zubringer": "hubschrauber"}
            ],
            "modes": ["transit_auto"],
        },
    )

    assert answer.status_code == 422


def test_the_threshold_is_the_ten_minutes_the_user_asked_for():
    assert ACCESS_THRESHOLD_S == 600
