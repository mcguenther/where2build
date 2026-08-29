"""POST /api/housetypes/extract -- two calls, plausibility bounds, permanent cache."""

from __future__ import annotations

import json

import httpx
import respx
from fastapi.testclient import TestClient

from .conftest import LLM_URL, fixture_text
from .test_llm import HAUSTYP_JSON, completion

CHAT_URL = f"{LLM_URL}/chat/completions"
PAGE_URL = "https://www.beispiel-hersteller.de/einfamilienhaus/all-in-one-159/"


def _two_calls(haustyp: dict | None = None):
    return [
        httpx.Response(200, json=completion(fixture_text("hersteller_haustyp.html"))),
        httpx.Response(200, json=completion(json.dumps(haustyp or HAUSTYP_JSON))),
    ]


@respx.mock
def test_house_type_is_read_in_two_separate_calls(client: TestClient):
    llm = respx.post(CHAT_URL).mock(side_effect=_two_calls())

    answer = client.post("/api/housetypes/extract", json={"url": PAGE_URL})

    assert answer.status_code == 200
    assert llm.call_count == 2

    first = json.loads(llm.calls[0].request.content)
    second = json.loads(llm.calls[1].request.content)
    assert "tools" in first and "response_format" not in first
    assert "response_format" in second and "tools" not in second
    # allowed_domains keeps the fetch on the manufacturer's own site.
    assert first["tools"][0]["parameters"]["allowed_domains"] == ["beispiel-hersteller.de"]

    body = answer.json()
    felder = body["felder"]
    # Built-up area, not the advertised living area across all storeys.
    assert felder["bebaute_flaeche_m2"]["wert"] == 96.88
    assert felder["wohnflaeche_gesamt_m2"]["wert"] == 159.21
    assert felder["bebaute_flaeche_m2"]["bestaetigt"] is False
    assert felder["bebaute_flaeche_m2"]["quelle_url"] == PAGE_URL
    assert felder["dachformen"]["wert"] == ["satteldach"]


@respx.mock
def test_missing_dimensions_are_estimated_from_the_built_up_area(client: TestClient):
    respx.post(CHAT_URL).mock(side_effect=_two_calls())

    body = client.post("/api/housetypes/extract", json={"url": PAGE_URL}).json()

    assert body["abgeleitete_laenge_m"] == 11.44
    assert body["abgeleitete_breite_m"] == 8.47
    assert "geschätzt" in body["hinweis"]


@respx.mock
def test_real_dimensions_beat_the_estimate(client: TestClient):
    respx.post(CHAT_URL).mock(
        side_effect=_two_calls(
            {**HAUSTYP_JSON, "aussenmass_laenge_m": 11.99, "aussenmass_breite_m": 8.08}
        )
    )

    body = client.post("/api/housetypes/extract", json={"url": PAGE_URL}).json()

    assert body["abgeleitete_laenge_m"] == 11.99
    assert body["hinweis"] is None


@respx.mock
def test_second_request_for_the_same_url_makes_no_http_call(client: TestClient):
    llm = respx.post(CHAT_URL).mock(side_effect=_two_calls())

    first = client.post("/api/housetypes/extract", json={"url": PAGE_URL})
    second = client.post("/api/housetypes/extract", json={"url": PAGE_URL + "?utm_source=mail"})

    assert first.json() == second.json()
    assert llm.call_count == 2  # from the first request only


@respx.mock
def test_implausible_area_is_a_502_not_a_house(client: TestClient):
    respx.post(CHAT_URL).mock(side_effect=_two_calls({**HAUSTYP_JSON, "bebaute_flaeche_m2": 500}))

    answer = client.post("/api/housetypes/extract", json={"url": PAGE_URL})

    assert answer.status_code == 502
    assert "plausibel" in answer.json()["detail"]


@respx.mock
def test_failed_fetch_is_reported_as_a_502(client: TestClient):
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200, json=completion("Die Seite ließ sich nicht abrufen.", tool_calls_executed=0)
        )
    )

    answer = client.post("/api/housetypes/extract", json={"url": PAGE_URL})

    assert answer.status_code == 502
    assert "Traceback" not in answer.text


def test_missing_url_is_a_422(client: TestClient):
    assert client.post("/api/housetypes/extract", json={}).status_code == 422


def test_a_non_url_is_a_422(client: TestClient):
    assert client.post("/api/housetypes/extract", json={"url": "kein-link"}).status_code == 422


def test_without_a_provider_the_answer_is_a_503(without_llm, client: TestClient):
    answer = client.post("/api/housetypes/extract", json={"url": PAGE_URL})

    assert answer.status_code == 503
    assert "LLM_API_KEY" in answer.json()["detail"]
