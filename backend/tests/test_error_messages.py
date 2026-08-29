"""Every failure has to say, in German, what the user can do next.

The frontend renders ``detail`` and nothing else (``src/lib/api.js``), so a
message that only names the fault leaves the user staring at a dead end. These
tests walk the endpoints with their service switched off and insist on two
things: German, and a way forward.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from .conftest import ALKIS_URL, BORIS_URL, DOP_URL, LLM_URL, MOTIS_URL

# Fragments that would give away an untranslated framework or library message.
ENGLISH_GIVEAWAYS = (
    "Value error",
    "Assertion failed",
    "Input should",
    "Field required",
    "Not Found",
    "Method Not Allowed",
    "Internal Server Error",
    "Traceback",
    "Exception",
    "None",
)

REACHABILITY_BODY = {
    "origin": {"lat": 51.2829, "lon": 12.4628},
    "destinations": [{"id": "arbeit", "lat": 51.3397, "lon": 12.3731}],
    "modes": ["car"],
}


def assert_speaks_german(detail: str) -> None:
    assert detail and detail.strip(), "Es gab überhaupt keine Meldung."
    for fragment in ENGLISH_GIVEAWAYS:
        assert fragment not in detail, f"Englischer Rohtext in der Meldung: {fragment!r}"
    assert detail.rstrip().endswith((".", "!", "?")), detail


def assert_offers_a_way_out(detail: str) -> None:
    """A failure message names the fault *and* what to do about it."""

    assert_speaks_german(detail)
    sentences = [part for part in detail.split(". ") if part.strip()]
    assert len(sentences) >= 2, f"Meldung nennt nur den Fehler, keinen Ausweg: {detail}"


@respx.mock
def test_alkis_outage_points_at_manual_entry(client: TestClient):
    respx.get(ALKIS_URL).mock(side_effect=httpx.ConnectError("kein Netz"))

    answer = client.post("/api/parcels/resolve", json={"lat": 51.3397, "lon": 12.3731})

    assert answer.status_code == 502
    detail = answer.json()["detail"]
    assert_offers_a_way_out(detail)
    assert "von Hand" in detail


@respx.mock
def test_boris_outage_points_at_the_public_portal(client: TestClient):
    respx.get(BORIS_URL).mock(side_effect=httpx.ConnectError("kein Netz"))

    answer = client.get("/api/landvalue", params={"lat": 51.3397, "lon": 12.3731})

    assert answer.status_code == 502
    detail = answer.json()["detail"]
    assert_offers_a_way_out(detail)
    assert "boris.sachsen.de" in detail


@respx.mock
def test_a_coordinate_without_a_land_value_explains_the_usual_reason(client: TestClient):
    from .conftest import fixture_text

    respx.get(BORIS_URL).mock(
        return_value=httpx.Response(
            200, text=fixture_text("boris_leer.txt"), headers={"content-type": "text/plain"}
        )
    )

    answer = client.get("/api/landvalue", params={"lat": 51.3397, "lon": 12.3731})

    assert answer.status_code == 404
    assert_offers_a_way_out(answer.json()["detail"])


@respx.mock
def test_routing_outage_says_the_rest_of_the_appraisal_still_holds(client: TestClient):
    respx.get(f"{MOTIS_URL}/api/v6/plan").mock(side_effect=httpx.ConnectError("kein Netz"))

    answer = client.post("/api/reachability", json=REACHABILITY_BODY)

    assert answer.status_code == 502
    detail = answer.json()["detail"]
    assert_offers_a_way_out(detail)
    assert "Bodenrichtwert" in detail


@respx.mock
def test_geocoder_outage_names_the_other_ways_in(client: TestClient):
    respx.get(f"{MOTIS_URL}/api/v1/geocode").mock(side_effect=httpx.ConnectError("kein Netz"))

    answer = client.post("/api/parcels/resolve", json={"address": "Markt 1, 04109 Leipzig"})

    assert answer.status_code == 502
    detail = answer.json()["detail"]
    assert_offers_a_way_out(detail)
    assert "Flurstücksnummer" in detail


@respx.mock
def test_wms_outage_says_which_numbers_are_unaffected(client: TestClient):
    respx.get(DOP_URL).mock(side_effect=httpx.ConnectError("kein Netz"))

    answer = client.get("/api/tiles/dop/15/17540/10986.png")

    assert answer.status_code == 502
    assert_offers_a_way_out(answer.json()["detail"])


@respx.mock
def test_extraction_outage_points_at_manual_entry(client: TestClient):
    respx.post(f"{LLM_URL}/chat/completions").mock(side_effect=httpx.ConnectError("kein Netz"))

    answer = client.post(
        "/api/housetypes/extract", json={"url": "https://hersteller.example.org/haus"}
    )

    assert answer.status_code == 502
    detail = answer.json()["detail"]
    assert_offers_a_way_out(detail)
    assert "von Hand" in detail


def test_an_unconfigured_extraction_provider_says_so_in_german(
    without_llm, client: TestClient
):
    answer = client.post(
        "/api/housetypes/extract", json={"url": "https://hersteller.example.org/haus"}
    )

    assert answer.status_code == 503
    assert_offers_a_way_out(answer.json()["detail"])


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [("get", "/api/gibtsnicht", 404), ("post", "/api/health", 405)],
)
def test_the_frameworks_own_answers_are_german_too(
    client: TestClient, method: str, path: str, status: int
):
    answer = getattr(client, method)(path)

    assert answer.status_code == status
    assert_speaks_german(answer.json()["detail"])


def test_a_field_out_of_range_is_explained_in_german(client: TestClient):
    answer = client.get("/api/landvalue", params={"lat": 200, "lon": 12.3})

    assert answer.status_code == 422
    detail = answer.json()["detail"]
    assert_speaks_german(detail)
    assert "lat" in detail and "90" in detail


def test_a_missing_field_is_explained_in_german(client: TestClient):
    answer = client.post("/api/reachability", json={"origin": {"lat": 51.3, "lon": 12.3}})

    assert answer.status_code == 422
    detail = answer.json()["detail"]
    assert_speaks_german(detail)
    assert "destinations" in detail


def test_an_unknown_mode_lists_the_known_ones(client: TestClient):
    body = dict(REACHABILITY_BODY, modes=["rakete"])

    answer = client.post("/api/reachability", json=body)

    assert answer.status_code == 422
    detail = answer.json()["detail"]
    assert_speaks_german(detail)
    assert "car" in detail and "transit" in detail
