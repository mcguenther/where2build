"""POST /api/site-checks -- the environmental record of one parcel.

Every fixture in here is a recorded answer of the real service for Flurstück
204 in Mölkau, the plot the research was measured on: two overlapping noise
bands, a Landschaftsschutzgebiet a few hundred metres away, the BK50 wording,
air capacity class LK_IV and the boreholes around it. Nothing is invented, so a
test that fails means the contract moved, not that a made-up number drifted.
"""

from __future__ import annotations

import json

import httpx
import respx
from fastapi.testclient import TestClient

from app.services import luis as L

from .conftest import LUIS_URL, UBA_URL, fixture_json

# The outline as ALKIS delivers it, in WGS84 -- six points, 650 m².
MOELKAU_RING = [
    [12.441369, 51.336196],
    [12.441984, 51.336147],
    [12.442096, 51.336611],
    [12.441795, 51.336635],
    [12.441481, 51.336660],
    [12.441369, 51.336196],
]

EMPTY = {"features": []}


def _layer_of(request: httpx.Request) -> tuple[str, int]:
    """`.../services/<folder>/<name>/MapServer/<layer>/query` -> the two parts."""

    parts = str(request.url).split("/rest/services/")[1].split("/")
    return "/".join(parts[:2]), int(parts[3])


def luis_answers(answers: dict[tuple[str, int], dict], default: dict | None = None):
    """Route every LUIS query by the service and layer it addresses."""

    def dispatch(request: httpx.Request) -> httpx.Response:
        service, layer = _layer_of(request)
        body = answers.get((service, layer), EMPTY if default is None else default)
        if b"returnCountOnly=true" in request.content:
            body = {"count": len(body.get("features", []))}
        return httpx.Response(200, json=body)

    return respx.post(url__startswith=LUIS_URL).mock(side_effect=dispatch)


def uba_answers(stations="uba_stationen.json", values="uba_messwerte_no2.json"):
    respx.get(url__startswith=f"{UBA_URL}/stations").mock(
        return_value=httpx.Response(200, json=fixture_json(stations))
    )

    def measures(request: httpx.Request) -> httpx.Response:
        station = request.url.params.get("station")
        component = request.url.params.get("component")
        # Only Leipzig-Mitte answers; the nearer stations are silent, as they
        # are in reality.
        if station != "1613":
            return httpx.Response(200, json=fixture_json("uba_messwerte_stumm.json"))
        name = values if component == "5" else "uba_messwerte_pm10.json"
        return httpx.Response(200, json=fixture_json(name))

    return respx.get(url__startswith=f"{UBA_URL}/measures").mock(side_effect=measures)


def moelkau_answers():
    return {
        (L.NOISE_SERVICE, 4): fixture_json("luis_laerm_lden.json"),
        (L.NOISE_SERVICE, 5): fixture_json("luis_laerm_lnight.json"),
        (L.PROTECTION_SERVICE, 5): fixture_json("luis_schutzgebiet.json"),
        (L.SOIL_SERVICE, L.SOIL_LAYER): fixture_json("luis_bk50.json"),
        (L.SOIL_PARAMETER_SERVICE, L.SOIL_PARAMETER_LAYER): fixture_json(
            "luis_bodenkennwerte.json"
        ),
        (L.BOREHOLE_SERVICE, L.BOREHOLE_LAYER): fixture_json("luis_bohrungen.json"),
    }


def check(client: TestClient, ring=None) -> dict:
    answer = client.post("/api/site-checks", json={"ring": ring or MOELKAU_RING})
    assert answer.status_code == 200, answer.text
    return answer.json()


# --------------------------------------------------------------------------
# Noise
# --------------------------------------------------------------------------


@respx.mock
def test_noise_answers_with_the_bands_the_survey_holds(client: TestClient):
    luis_answers(moelkau_answers())
    uba_answers()

    laerm = check(client)["laerm"]

    # Two bands, because the isophone crosses the plot -- the whole reason the
    # query uses the outline and not a point.
    assert laerm["tag"]["strasse"] == ["Lden5559", "Lden5054"]
    assert laerm["nacht"]["strasse"] == ["Lnight4549"]
    assert laerm["tag"]["strassenbahn"] == []
    assert laerm["tag"]["flughafen"] == []
    assert laerm["fehler"] is None


@respx.mock
def test_the_noise_query_uses_the_outline_and_never_identify(client: TestClient):
    route = luis_answers(moelkau_answers())
    uba_answers()

    check(client)

    noise = [
        call for call in route.calls
        if f"{L.NOISE_SERVICE}/MapServer/4/query" in str(call.request.url)
    ]
    assert noise, "the road noise layer was never asked"
    body = httpx.QueryParams(noise[0].request.content.decode())
    assert body["geometryType"] == "esriGeometryPolygon"
    assert body["spatialRel"] == "esriSpatialRelIntersects"
    assert len(json.loads(body["geometry"])["rings"][0]) == len(MOELKAU_RING)
    assert not any("identify" in str(call.request.url) for call in route.calls)


@respx.mock
def test_no_band_inside_a_mapped_area_is_a_measured_quiet(client: TestClient):
    # Nothing on the plot, but the survey has drawn 1 792 polygons within 2 km.
    coverage = fixture_json("luis_anzahl.json")

    def dispatch(request: httpx.Request) -> httpx.Response:
        if b"returnCountOnly=true" in request.content:
            return httpx.Response(200, json=coverage)
        return httpx.Response(200, json=fixture_json("luis_leer.json"))

    respx.post(url__startswith=LUIS_URL).mock(side_effect=dispatch)
    uba_answers()

    laerm = check(client)["laerm"]

    assert laerm["tag"]["strasse"] == []
    assert laerm["kartiert_umkreis"] is True
    assert laerm["unterste_stufe_db"] == 45


@respx.mock
def test_nothing_mapped_within_two_kilometres_is_not_quiet(client: TestClient):
    # Geithain, 6 000 inhabitants: no polygon at all. "No value" must stay
    # distinguishable from "quiet" all the way through the contract.
    luis_answers({})
    uba_answers()

    laerm = check(client)["laerm"]

    assert laerm["tag"]["strasse"] == []
    assert laerm["kartiert_umkreis"] is False
    assert laerm["umkreis_m"] == 2000


@respx.mock
def test_the_coverage_question_is_only_asked_when_nothing_was_found(client: TestClient):
    route = luis_answers(moelkau_answers())
    uba_answers()

    check(client)

    assert not any(b"distance=2000" in call.request.content for call in route.calls)


# --------------------------------------------------------------------------
# Designations
# --------------------------------------------------------------------------


@respx.mock
def test_a_protected_area_nearby_comes_back_as_a_bracket(client: TestClient):
    # The recorded answer holds both areas within a kilometre; the ladder is
    # walked down until only the 400 m rung still has one.
    def dispatch(request: httpx.Request) -> httpx.Response:
        service, layer = _layer_of(request)
        body = httpx.QueryParams(request.content.decode())
        distance = float(body.get("distance", 0))
        hit = service == L.PROTECTION_SERVICE and layer == 5 and distance >= 400
        found = fixture_json("luis_schutzgebiet.json")["features"][:1] if hit else []
        if body.get("returnCountOnly") == "true":
            return httpx.Response(200, json={"count": len(found)})
        return httpx.Response(200, json={"features": found})

    respx.post(url__startswith=LUIS_URL).mock(side_effect=dispatch)
    uba_answers()

    schutz = check(client)["schutzgebiet"]

    assert schutz["betroffen"] is False
    assert schutz["naechstes"]["name"] == "Östliche Rietzschke - Stünz"
    assert schutz["naechstes"]["kategorie"] == "Landschaftsschutzgebiet"
    assert (schutz["abstand_von_m"], schutz["abstand_bis_m"]) == (300, 400)


@respx.mock
def test_a_plot_inside_a_designation_says_so_and_names_it(client: TestClient):
    luis_answers({
        (L.RADON_SERVICE, 0): {
            "features": [{"attributes": {"NAME": "Stadt Johanngeorgenstadt"}}]
        }
    })
    uba_answers()

    radon = check(client)["radon"]

    assert radon["betroffen"] is True
    assert radon["gebiete"][0]["name"] == "Stadt Johanngeorgenstadt"
    assert radon["gebiete"][0]["kategorie"] == "Radonvorsorgegebiet"


@respx.mock
def test_the_flood_check_asks_every_extent_not_only_hq100(client: TestClient):
    route = luis_answers({})
    uba_answers()

    check(client)

    asked = {
        _layer_of(call.request)[1]
        for call in route.calls
        if L.FLOOD_SERVICE in str(call.request.url)
    }
    assert asked == set(L.FLOOD_LAYERS)


@respx.mock
def test_an_untouched_designation_is_not_affected_rather_than_unknown(client: TestClient):
    luis_answers({})
    uba_answers()

    answer = check(client)

    for name in ("trinkwasserschutz", "hochwasser", "radon", "hangneigung"):
        assert answer[name]["betroffen"] is False
        assert answer[name]["fehler"] is None
        assert answer[name]["quelle"]


# --------------------------------------------------------------------------
# Ground
# --------------------------------------------------------------------------


@respx.mock
def test_ground_carries_the_soil_wording_the_class_and_the_boreholes(client: TestClient):
    luis_answers(moelkau_answers())
    uba_answers()

    baugrund = check(client)["baugrund"]

    assert baugrund["bodenart_text"].startswith("Hortisol ueber erodierter Parabraunerde")
    assert baugrund["luftkapazitaet_stufe"] == "LK_IV"
    assert baugrund["bohrungen_umkreis"] == 6
    # Distance from the parcel's edge, not from a point inside it.
    assert 0 < baugrund["naechste"]["entfernung_m"] < 300
    assert baugrund["naechste"]["endteufe_m"] == 5.0
    assert baugrund["naechste"]["jahr"] == 1972


@respx.mock
def test_the_soil_wording_travels_untranslated(client: TestClient):
    """The class key is data. Turning it into German is the browser's job, and
    doing it here would put UI copy in a Python module."""

    luis_answers(moelkau_answers())
    uba_answers()

    baugrund = check(client)["baugrund"]

    assert baugrund["luftkapazitaet_stufe"] == "LK_IV"
    assert "bindig" not in json.dumps(baugrund)
    assert "Baugrunduntersuchung" not in json.dumps(baugrund)


# --------------------------------------------------------------------------
# Air quality
# --------------------------------------------------------------------------


@respx.mock
def test_the_nearest_station_that_answers_is_the_one_reported(client: TestClient):
    luis_answers(moelkau_answers())
    uba_answers()

    luft = check(client)["luftqualitaet"]

    # z_GUAN and zDDR_ sit nearer and carry no values at all.
    assert luft["station"] == "Leipzig-Mitte"
    assert luft["uebersprungen"] >= 1
    assert luft["entfernung_km"] > 4
    assert luft["werte"]["no2"] > 0
    assert luft["werte"]["pm10"] > 0


@respx.mock
def test_no_station_with_values_leaves_the_check_empty_not_green(client: TestClient):
    luis_answers({})
    respx.get(url__startswith=f"{UBA_URL}/stations").mock(
        return_value=httpx.Response(200, json=fixture_json("uba_stationen.json"))
    )
    respx.get(url__startswith=f"{UBA_URL}/measures").mock(
        return_value=httpx.Response(200, json=fixture_json("uba_messwerte_stumm.json"))
    )

    luft = check(client)["luftqualitaet"]

    assert luft["station"] is None
    assert luft["werte"] == {}
    assert luft["uebersprungen"] > 0


# --------------------------------------------------------------------------
# Failure, and what it must not take with it
# --------------------------------------------------------------------------


@respx.mock
def test_one_failing_service_costs_its_own_row_and_no_other(client: TestClient):
    def dispatch(request: httpx.Request) -> httpx.Response:
        service, layer = _layer_of(request)
        if service == L.RADON_SERVICE:
            return httpx.Response(500, text="nope")
        body = moelkau_answers().get((service, layer), EMPTY)
        if b"returnCountOnly=true" in request.content:
            body = {"count": len(body.get("features", []))}
        return httpx.Response(200, json=body)

    respx.post(url__startswith=LUIS_URL).mock(side_effect=dispatch)
    uba_answers()

    answer = check(client)

    assert answer["radon"]["fehler"]
    assert "LUIS" in answer["radon"]["fehler"]
    assert answer["radon"]["betroffen"] is False
    assert answer["laerm"]["tag"]["strasse"] == ["Lden5559", "Lden5054"]
    assert answer["baugrund"]["luftkapazitaet_stufe"] == "LK_IV"


@respx.mock
def test_an_arcgis_error_inside_a_200_is_a_failure(client: TestClient):
    """ArcGIS reports its own refusals with HTTP 200, so the status code alone
    would have called this a success."""

    respx.post(url__startswith=LUIS_URL).mock(
        return_value=httpx.Response(200, json={"error": {"code": 400, "message": "Invalid URL"}})
    )
    uba_answers()

    answer = check(client)

    assert "Invalid URL" in answer["laerm"]["fehler"]


@respx.mock
def test_a_second_look_at_the_same_plot_comes_from_the_disk_cache(client: TestClient):
    route = luis_answers(moelkau_answers())
    uba_answers()

    check(client)
    calls = route.call_count
    check(client)

    assert route.call_count == calls


def test_a_ring_outside_germany_is_refused_with_a_german_sentence(client: TestClient):
    answer = client.post(
        "/api/site-checks",
        json={"ring": [[2.35, 48.85], [2.36, 48.85], [2.36, 48.86]]},
    )

    assert answer.status_code == 422
    assert "außerhalb Deutschlands" in json.dumps(answer.json(), ensure_ascii=False)


def test_a_point_is_not_a_plot(client: TestClient):
    """There is deliberately no way to ask this endpoint with one coordinate."""

    answer = client.post("/api/site-checks", json={"ring": [[12.44176, 51.33652]]})

    assert answer.status_code == 422


@respx.mock
def test_an_unreachable_uba_costs_the_air_row_and_no_more(client: TestClient):
    luis_answers(moelkau_answers())
    respx.get(url__startswith=UBA_URL).mock(return_value=httpx.Response(503, text="down"))

    answer = check(client)

    assert answer["luftqualitaet"]["fehler"]
    assert "Umweltbundesamt" in answer["luftqualitaet"]["fehler"]
    assert answer["luftqualitaet"]["station"] is None
    assert answer["laerm"]["tag"]["strasse"] == ["Lden5559", "Lden5054"]


# --------------------------------------------------------------------------
# The ring, as ArcGIS reads it
# --------------------------------------------------------------------------


@respx.mock
def test_the_ring_goes_out_clockwise(client: TestClient):
    """ALKIS delivers counter-clockwise rings and ArcGIS reads one of those as a
    *hole*. Measured on 05.09.2026: an 86 m² parcel sent that way made every
    `distance` query answer `{"code": 400, "message": ""}`, while the same ring
    reversed returned 114 boreholes — and a 650 m² parcel survived either way,
    which is what kept it hidden."""

    route = luis_answers(moelkau_answers())
    uba_answers()

    check(client)

    sent = json.loads(
        httpx.QueryParams(route.calls[0].request.content.decode())["geometry"]
    )["rings"][0]
    twice_area = sum(
        sent[i][0] * sent[i + 1][1] - sent[i + 1][0] * sent[i][1]
        for i in range(len(sent) - 1)
    )
    assert twice_area < 0, "counter-clockwise: ArcGIS would take this for a hole"
    # Same points, same count — only the direction is ours to choose.
    assert len(sent) == len(MOELKAU_RING)


@respx.mock
def test_a_refused_borehole_query_leaves_the_soil_answer_standing(client: TestClient):
    def dispatch(request: httpx.Request) -> httpx.Response:
        service, layer = _layer_of(request)
        if service == L.BOREHOLE_SERVICE:
            # How this service refuses: HTTP 200, an error with no message.
            return httpx.Response(200, json={"error": {"code": 400, "message": "", "details": []}})
        body = moelkau_answers().get((service, layer), EMPTY)
        if b"returnCountOnly=true" in request.content:
            body = {"count": len(body.get("features", []))}
        return httpx.Response(200, json=body)

    respx.post(url__startswith=LUIS_URL).mock(side_effect=dispatch)
    uba_answers()

    baugrund = check(client)["baugrund"]

    assert baugrund["bodenart_text"].startswith("Hortisol")
    assert baugrund["luftkapazitaet_stufe"] == "LK_IV"
    # Zero boreholes and an unanswered layer are different statements.
    assert baugrund["bohrungen_gefragt"] is False
    assert baugrund["bohrungen_umkreis"] == 0
    assert baugrund["fehler"] is None
