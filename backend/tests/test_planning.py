"""POST /api/planning -- what RAPIS Sachsen knows about a plot's Bauleitplanung.

Every fixture is a recorded answer of the real service on 30.09.2026, one file
per plot with the ring that was sent and the answer of each layer:

* ``rapis_moelkau_204.json`` -- Lessingweg 44, the reference plot: no plan in
  force, none in procedure, no statute, FNP Wohnbaufläche.
* ``rapis_zweinaundorf_479.json`` -- Buchenweg 20, inside B-Pl. E-215, the
  control that shows the in-force layer answering at all.
* ``rapis_moelkau_520.json`` -- the parcel V-BPlan Nr. 424 names, in procedure.
* ``rapis_gundorf_36_13.json`` -- inside the Ergänzungssatzung E-276, which
  RAPIS returns on the plan layer *and* on the statute layer.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.deps import rapis_service
from app.schemas import PLANUNG_HINWEIS
from app.services import rapis as R

from .conftest import RAPIS_URL, fixture_json


def recorded(name: str) -> dict:
    return fixture_json(f"rapis_{name}.json")


def _layer_of(request: httpx.Request) -> str:
    """`.../services/<service>/MapServer/<layer>/query` -> `<service>/<layer>`."""

    service, _, layer, _ = str(request.url).split("/rest/services/")[1].split("/")
    return f"{service}/{layer}"


def rapis_answers(plot: str):
    answers = recorded(plot)["antworten"]

    def dispatch(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=answers[_layer_of(request)])

    return respx.post(url__startswith=RAPIS_URL).mock(side_effect=dispatch)


def ask(client: TestClient, plot: str):
    return client.post("/api/planning", json={"ring": recorded(plot)["ring"]})


# --------------------------------------------------------------------------
# The four recorded plots
# --------------------------------------------------------------------------


@respx.mock
def test_moelkau_204_has_no_known_plan_but_an_fnp(client: TestClient):
    route = rapis_answers("moelkau_204")

    answer = ask(client, "moelkau_204")

    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["bebauungsplaene"] == []
    assert body["satzungen"] == []
    assert body["fnp"] == [
        {
            "name": "FNP der Stadt Leipzig, Fortschreibung",
            "darstellungen": ["Wohnbaufläche"],
            "gemeinde": "Leipzig, Stadt",
            "bekanntgemacht_am": "2015-05-16",
            "info": "wirksam 16.05.2015, letzte Änd.Verfahren 2023",
        }
    ]
    assert body["datenstand"] == "2026-09-28"
    assert body["quelle"] == "RAPIS Sachsen 09/2026, Landesdirektion Sachsen — dl-de/by-2-0"
    assert body["quelle_url"] == "https://rapis.sachsen.de"
    assert body["hinweis"] == PLANUNG_HINWEIS
    # All six layers, and each once.
    assert sorted(_layer_of(call.request) for call in route.calls) == sorted(
        recorded("moelkau_204")["antworten"]
    )


@respx.mock
def test_the_frontend_fixtures_are_this_endpoints_answer(client: TestClient):
    """The two `frontend/tests/fixtures/planung-*.json` were written from the
    live endpoint; the recorded upstream answers must still produce them."""

    frontend = Path(__file__).parents[2] / "frontend" / "tests" / "fixtures"
    for plot, name in (("moelkau_204", "moelkau"), ("zweinaundorf_479", "zweinaundorf-e215")):
        respx.reset()
        rapis_answers(plot)
        written = json.loads((frontend / f"planung-{name}.json").read_text(encoding="utf-8"))
        assert ask(client, plot).json() == written


@respx.mock
def test_a_plan_in_force_is_named_with_its_use_and_dates(client: TestClient):
    rapis_answers("zweinaundorf_479")

    body = ask(client, "zweinaundorf_479").json()

    assert body["satzungen"] == []
    [plan] = body["bebauungsplaene"]
    assert plan["name"] == "B-Pl. E-215 Wohngebiet Zweinaundf.Str."
    assert plan["status"] == "in Kraft"
    assert plan["verfahrensstand"] == "rechtskräftig"
    assert plan["gemeinde"] == "Leipzig, Stadt"
    assert plan["standort"] == "Mölkau"
    assert plan["plantyp"] == "W"
    assert plan["rok_nr"] == 3940008
    # From the use layer, matched to the plan by ROK_NR.
    assert plan["art_der_nutzung"] == ["Wohnbaufläche (W)"]
    assert plan["info"] == "Teile von 1.Änderung überplant (2014)"
    # A blank RAPIS text field is no value, not a space.
    assert plan["rechtsgrundlage"] is None


@respx.mock
def test_dates_are_read_in_saxon_time(client: TestClient):
    """The layers declare Europe/Berlin. Read in UTC, every date is a day early --
    the FNP's own free text says 16.05.2015, and so must the date field."""

    rapis_answers("zweinaundorf_479")

    body = ask(client, "zweinaundorf_479").json()

    assert body["bebauungsplaene"][0]["genehmigt_am"] == "1995-03-08"
    assert body["bebauungsplaene"][0]["bekanntgemacht_am"] == "1995-05-05"
    assert body["fnp"][0]["bekanntgemacht_am"] == "2015-05-16"
    assert "16.05.2015" in body["fnp"][0]["info"]


@respx.mock
def test_a_plan_in_procedure_says_so_and_keeps_rapis_own_status(client: TestClient):
    rapis_answers("moelkau_520")

    body = ask(client, "moelkau_520").json()

    [plan] = body["bebauungsplaene"]
    assert plan["name"] == "V-BPlan Nr. 424 Handels- und Dienstleistungszentrum Mölkau-Mitte"
    assert plan["status"] == "im Verfahren"
    assert plan["verfahrensstand"] == "im Verfahren"
    assert plan["rechtsgrundlage"] == "§12 BauGB"
    assert plan["planstand"] == "Vorentwurf"
    assert plan["art_der_nutzung"] == ["Sondergebiet Handel"]
    assert plan["bekanntgemacht_am"] is None
    # The FNP boundary runs through this parcel: both designations, not one.
    assert body["fnp"][0]["darstellungen"] == ["Straßenverkehrsfläche", "Wohnbaufläche"]


@respx.mock
def test_a_statute_on_the_plan_layer_is_reported_once_as_a_statute(client: TestClient):
    answers = recorded("gundorf_36_13")["antworten"]
    # The recording shows the trap: E-276 is on layer 3 as well as on layer 5.
    assert [f["attributes"]["ROK_NR"] for f in answers["WMS_BPLAN/3"]["features"]] == [3980335]
    rapis_answers("gundorf_36_13")

    body = ask(client, "gundorf_36_13").json()

    assert body["bebauungsplaene"] == []
    [statute] = body["satzungen"]
    assert statute["name"] == "ErgS Entlang der Schönauer Str. E-276"
    assert statute["status"] == "in Kraft"
    assert statute["rechtsgrundlage"] == "§34(4) Nr.3 BauGB"
    assert statute["bekanntgemacht_am"] == "1998-12-17"


# --------------------------------------------------------------------------
# The request that goes out
# --------------------------------------------------------------------------


@respx.mock
def test_the_ring_goes_out_clockwise_in_utm33_on_the_rest_layer_numbers(client: TestClient):
    route = rapis_answers("moelkau_204")

    ask(client, "moelkau_204")

    layers = {_layer_of(call.request) for call in route.calls}
    # WMS layer "4 Satzungsbereiche" is REST layer 5; REST layer 4 is a 404.
    assert layers == {
        "WMS_BPLAN/0",
        "WMS_BPLAN/1",
        "WMS_BPLAN/2",
        "WMS_BPLAN/3",
        "WMS_BPLAN/5",
        "RO_FNP_wirksam/1",
    }
    form = parse_qs(route.calls[0].request.content.decode())
    assert form["inSR"] == ["25833"]
    assert form["returnGeometry"] == ["false"]
    assert form["spatialRel"] == ["esriSpatialRelIntersects"]
    ring = json.loads(form["geometry"][0])["rings"][0]
    assert ring[0] == ring[-1]
    # Easting/northing, not degrees.
    assert 321_700 < ring[0][0] < 321_900 and 5_690_300 < ring[0][1] < 5_690_400
    twice_area = sum(
        ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1)
    )
    assert twice_area < 0, "ArcGIS reads a counter-clockwise outer ring as a hole"
    # The fixture ring measures 645.57 m² in EPSG:25833, like the parcel fixture.
    assert abs(abs(twice_area) / 2 - 645.57) < 0.5


# --------------------------------------------------------------------------
# Failures: never an empty "no plan"
# --------------------------------------------------------------------------


def _one_layer_fails(plot: str, failing: str, failure: httpx.Response | Exception):
    answers = recorded(plot)["antworten"]

    def dispatch(request: httpx.Request) -> httpx.Response:
        if _layer_of(request) == failing:
            if isinstance(failure, Exception):
                raise failure
            return failure
        return httpx.Response(200, json=answers[_layer_of(request)])

    return respx.post(url__startswith=RAPIS_URL).mock(side_effect=dispatch)


@respx.mock
def test_an_upstream_500_is_a_german_error_not_an_empty_list(client: TestClient):
    _one_layer_fails("moelkau_204", "WMS_BPLAN/3", httpx.Response(500, text="Server Error"))

    answer = ask(client, "moelkau_204")

    assert answer.status_code == 502
    body = answer.json()
    assert "bebauungsplaene" not in body
    assert body["detail"].startswith(R.SERVICE_NAME)
    assert "Status 500" in body["detail"]
    assert "rapis.sachsen.de" in body["detail"]


@respx.mock
def test_a_timeout_is_a_german_504(client: TestClient):
    _one_layer_fails("moelkau_204", "WMS_BPLAN/5", httpx.ReadTimeout("slow"))

    answer = ask(client, "moelkau_204")

    assert answer.status_code == 504
    assert "hat nicht rechtzeitig geantwortet" in answer.json()["detail"]


@respx.mock
def test_an_arcgis_error_with_http_200_is_an_error(client: TestClient):
    _one_layer_fails(
        "moelkau_204",
        "WMS_BPLAN/1",
        httpx.Response(200, json={"error": {"code": 400, "message": "Unable to complete operation."}}),
    )

    answer = ask(client, "moelkau_204")

    assert answer.status_code == 502
    assert "Unable to complete operation." in answer.json()["detail"]


@respx.mock
def test_an_answer_without_features_is_not_read_as_none(client: TestClient):
    _one_layer_fails("moelkau_204", "WMS_BPLAN/3", httpx.Response(200, json={}))

    answer = ask(client, "moelkau_204")

    assert answer.status_code == 502
    assert "ohne Treffermenge" in answer.json()["detail"]


@respx.mock
def test_a_failed_answer_is_not_cached(client: TestClient):
    _one_layer_fails("moelkau_204", "WMS_BPLAN/3", httpx.Response(200, json={"error": {}}))
    assert ask(client, "moelkau_204").status_code == 502

    respx.reset()
    route = rapis_answers("moelkau_204")

    assert ask(client, "moelkau_204").status_code == 200
    # The layers that answered were kept; the one that failed is asked again.
    assert [_layer_of(call.request) for call in route.calls] == ["WMS_BPLAN/3"]


def test_a_ring_outside_germany_is_refused(client: TestClient):
    answer = client.post("/api/planning", json={"ring": [[0, 0], [1, 0], [1, 1], [0, 0]]})

    assert answer.status_code == 422
    assert "außerhalb Deutschlands" in answer.text


# --------------------------------------------------------------------------
# The cache
# --------------------------------------------------------------------------


@respx.mock
def test_the_second_ask_is_served_from_the_cache(client: TestClient):
    route = rapis_answers("moelkau_204")

    first = ask(client, "moelkau_204").json()
    calls = route.call_count
    second = ask(client, "moelkau_204").json()

    assert calls == 6
    assert route.call_count == calls
    assert first == second


def test_the_cache_key_is_the_layer_and_the_projected_ring():
    service = rapis_service()
    ring = recorded("moelkau_204")["ring"]
    geometry = service._geometry(ring)

    # Float noise below a millimetre and the ring's orientation make the same key.
    jittered = [[lon + 1e-11, lat - 1e-11] for lon, lat in ring]
    assert service._geometry(jittered) == geometry
    assert service._geometry(list(reversed(ring))) == geometry

    key = service.cache_key("WMS_BPLAN", 3, geometry)
    assert key.startswith("WMS_BPLAN/3/")
    assert key != service.cache_key("WMS_BPLAN", 1, geometry)
    assert service.cache.ttl_s == 7 * 24 * 3600


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("LD Sachsen, ROK 28.09.2026, letzter RAPIS-Upload", date(2026, 9, 28)),
        (" ", None),
        (None, None),
    ],
)
def test_the_upload_date_is_read_from_dat_rapis(text, expected):
    assert R._upload_date(text) == expected
