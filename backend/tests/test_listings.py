"""POST /api/listings/extract -- portal adapters, paste path, error answers."""

from __future__ import annotations

import json

import httpx
import respx
from fastapi.testclient import TestClient

from .conftest import LLM_URL, fixture_text
from .test_llm import completion

CHAT_URL = f"{LLM_URL}/chat/completions"
KLEINANZEIGEN_URL = (
    "https://www.kleinanzeigen.de/s-anzeige/-wohnbaugrundstueck-fuer-efh-mit-b-plan-688-m-/"
    "3425157266-207-4059"
)
IMMOSCOUT_URL = "https://www.immobilienscout24.de/expose/110185322"

INSERAT_JSON = {
    "adresse": "Muldentalstraße, 01589 Riesa",
    "lat": None,
    "lon": None,
    "flurstuecke": [
        {"gemarkung": None, "flur": None, "zaehler": 790, "nenner": None},
        {"gemarkung": None, "flur": None, "zaehler": 706, "nenner": None},
    ],
    "kaufpreis_eur": 89000,
    "grundstuecksflaeche_m2": 688,
}


def _kleinanzeigen_page() -> httpx.Response:
    return httpx.Response(
        200,
        text=fixture_text("kleinanzeigen_inserat.html"),
        headers={"content-type": "text/html; charset=utf-8"},
    )


@respx.mock
def test_immobilienscout24_is_not_fetched_and_points_at_the_paste_field(client: TestClient):
    portal = respx.get(url__startswith="https://www.immobilienscout24.de").mock(
        return_value=httpx.Response(200, text="<html></html>")
    )
    llm = respx.post(CHAT_URL).mock(return_value=httpx.Response(200, json=completion("x")))

    answer = client.post("/api/listings/extract", json={"url": IMMOSCOUT_URL})

    assert answer.status_code == 400
    assert "Einfügefeld" in answer.json()["detail"]
    assert portal.call_count == 0
    assert llm.call_count == 0


@respx.mock
def test_kleinanzeigen_coordinates_come_from_meta_tags_without_a_model_call(
    without_llm, client: TestClient
):
    respx.get(KLEINANZEIGEN_URL).mock(return_value=_kleinanzeigen_page())
    llm = respx.post(CHAT_URL).mock(return_value=httpx.Response(200, json=completion("x")))

    answer = client.post("/api/listings/extract", json={"url": KLEINANZEIGEN_URL})

    assert answer.status_code == 200
    body = answer.json()
    assert body["weg"] == "meta-tags"
    assert body["felder"]["lat"]["wert"] == 51.39235087498254
    assert body["felder"]["lon"]["wert"] == 13.3868408203125
    assert body["felder"]["lat"]["bestaetigt"] is False
    assert llm.call_count == 0


@respx.mock
def test_kleinanzeigen_description_is_structured_by_the_model(client: TestClient):
    respx.get(KLEINANZEIGEN_URL).mock(return_value=_kleinanzeigen_page())
    llm = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=completion(json.dumps(INSERAT_JSON)))
    )

    answer = client.post("/api/listings/extract", json={"url": KLEINANZEIGEN_URL})

    assert answer.status_code == 200
    body = answer.json()
    # One call only: the page is already in hand, so no web_fetch is needed.
    assert llm.call_count == 1
    payload = json.loads(llm.calls[0].request.content)
    assert "tools" not in payload
    assert payload["response_format"]["json_schema"]["strict"] is True

    assert body["weg"] == "meta-tags"
    assert body["felder"]["kaufpreis_eur"]["wert"] == 89000
    assert body["felder"]["grundstuecksflaeche_m2"]["wert"] == 688
    assert [p["wert"] for p in [body["felder"]["flurstuecke"]]][0][0]["zaehler"] == 790
    # The deterministic coordinate wins over anything the model produces.
    assert body["felder"]["lat"]["wert"] == 51.39235087498254


@respx.mock
def test_unknown_domain_goes_through_web_fetch_then_structuring(client: TestClient):
    llm = respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json=completion("Baugrundstück in Riesa, 89.000 €, 688 m²")),
            httpx.Response(200, json=completion(json.dumps(INSERAT_JSON))),
        ]
    )

    answer = client.post(
        "/api/listings/extract", json={"url": "https://www.beispielportal.de/objekt/17"}
    )

    assert answer.status_code == 200
    assert llm.call_count == 2
    first = json.loads(llm.calls[0].request.content)
    second = json.loads(llm.calls[1].request.content)
    assert "response_format" not in first and "tools" in first
    assert "tools" not in second and "response_format" in second
    assert answer.json()["weg"] == "llm"


@respx.mock
def test_pasted_text_needs_no_url(client: TestClient):
    llm = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=completion(json.dumps(INSERAT_JSON)))
    )

    answer = client.post(
        "/api/listings/extract",
        json={"text": "Baugrundstück 688 m², Flurstück 790 sowie 706, 89.000 €"},
    )

    assert answer.status_code == 200
    body = answer.json()
    assert body["weg"] == "eingefuegter-text"
    assert body["quelle_url"] is None
    assert body["felder"]["adresse"]["quelle_url"] is None
    # Pasting must not trigger a fetch, only the structuring call.
    assert llm.call_count == 1
    assert "tools" not in json.loads(llm.calls[0].request.content)


@respx.mock
def test_second_request_for_the_same_url_is_served_from_the_cache(client: TestClient):
    respx.get(KLEINANZEIGEN_URL).mock(return_value=_kleinanzeigen_page())
    llm = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=completion(json.dumps(INSERAT_JSON)))
    )

    first = client.post("/api/listings/extract", json={"url": KLEINANZEIGEN_URL})
    second = client.post("/api/listings/extract", json={"url": KLEINANZEIGEN_URL + "?utm_source=x"})

    assert first.json() == second.json()
    assert llm.call_count == 1


def test_request_without_url_or_text_is_a_422(client: TestClient):
    answer = client.post("/api/listings/extract", json={})

    assert answer.status_code == 422
    assert answer.json()["detail"] == "Die Anfrage ist unvollständig oder ungültig."


@respx.mock
def test_page_without_any_locator_is_a_400(client: TestClient):
    llm = respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json=completion("Nur Werbetext ohne Angaben")),
            httpx.Response(
                200,
                json=completion(
                    json.dumps(
                        {
                            "adresse": None,
                            "lat": None,
                            "lon": None,
                            "flurstuecke": [],
                            "kaufpreis_eur": None,
                            "grundstuecksflaeche_m2": None,
                        }
                    )
                ),
            ),
        ]
    )

    answer = client.post(
        "/api/listings/extract", json={"url": "https://www.beispielportal.de/objekt/18"}
    )

    assert answer.status_code == 400
    assert "Einfügefeld" in answer.json()["detail"] or "eintragen" in answer.json()["detail"]
    assert llm.call_count == 2


@respx.mock
def test_pasting_without_a_configured_provider_is_a_503(without_llm, client: TestClient):
    answer = client.post("/api/listings/extract", json={"text": "Baugrundstück 688 m²"})

    assert answer.status_code == 503
    assert "nicht konfiguriert" in answer.json()["detail"]


@respx.mock
def test_provider_timeout_becomes_a_504(client: TestClient):
    respx.post(CHAT_URL).mock(side_effect=httpx.ReadTimeout("zu langsam"))

    answer = client.post("/api/listings/extract", json={"text": "Baugrundstück"})

    assert answer.status_code == 504
