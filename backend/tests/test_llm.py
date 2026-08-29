"""The extraction client: two separate calls, a strict schema, a permanent cache."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.deps import llm_client
from app.errors import NotConfiguredError, UpstreamError
from app.schemas import HaustypFelder, InseratFelder
from app.services.llm import domain_of, normalize_url, strict_json_schema

from .conftest import LLM_URL, fixture_text

CHAT_URL = f"{LLM_URL}/chat/completions"
PAGE_URL = "https://www.beispiel-hersteller.de/einfamilienhaus/all-in-one-159/"

HAUSTYP_JSON = {
    "hersteller": "Beispiel",
    "typenbezeichnung": "All in One 159",
    "bebaute_flaeche_m2": 96.88,
    "wohnflaeche_gesamt_m2": 159.21,
    "wohnflaeche_eg_m2": 79.6,
    "wohnflaeche_og_m2": 79.61,
    "aussenmass_laenge_m": None,
    "aussenmass_breite_m": None,
    "dachformen": ["satteldach"],
    "traufhoehe_m": None,
    "firsthoehe_m": None,
    "grundstueck_ab_m2": None,
    "preis_ab_eur": 329000,
}


def completion(content: str, tool_calls_executed: int = 1) -> dict:
    return {
        "id": "gen-1",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
        "usage": {
            "prompt_tokens": 10_713,
            "completion_tokens": 210,
            "cost": 0.0017558,
            "server_tool_use_details": {
                "tool_calls_requested": 1,
                "tool_calls_executed": tool_calls_executed,
            },
        },
    }


def test_url_normalisation_ignores_campaign_parameters():
    assert normalize_url("https://WWW.Example.de/Haus/?utm_source=mail&b=2#anker") == (
        "https://www.example.de/Haus?b=2"
    )
    assert normalize_url("https://example.de/haus/") == normalize_url("https://example.de/haus")


def test_domain_of_strips_www():
    assert domain_of("https://www.kleinanzeigen.de/s-anzeige/x") == "kleinanzeigen.de"


def test_strict_schema_has_no_refs_and_requires_every_property():
    schema = strict_json_schema(HaustypFelder, "haustyp")["schema"]

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert "$defs" not in schema
    assert "$ref" not in json.dumps(schema)
    # Optionality is expressed as a nullable type, not as an absent field.
    assert schema["properties"]["traufhoehe_m"]["type"] == ["number", "null"]
    # Bounds stay in Pydantic; strict schemas reject several of those keywords.
    assert "minimum" not in schema["properties"]["bebaute_flaeche_m2"]


def test_strict_schema_inlines_nested_models():
    schema = strict_json_schema(InseratFelder, "inserat")["schema"]

    parcel = schema["properties"]["flurstuecke"]["items"]
    assert parcel["additionalProperties"] is False
    assert "zaehler" in parcel["properties"]


@respx.mock
async def test_extraction_uses_two_calls_and_never_mixes_tools_with_response_format():
    # docs/research/openrouter.md, section 5: with tools active in the same
    # call, none of the tested models honoured the json_schema.
    route = respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json=completion(fixture_text("hersteller_haustyp.html"))),
            httpx.Response(200, json=completion(json.dumps(HAUSTYP_JSON))),
        ]
    )

    client = llm_client()
    text = await client.fetch_page_text(PAGE_URL, "Fertighaus")
    felder = await client.structure(text, HaustypFelder, "haustyp", "Extrahiere")

    assert route.call_count == 2
    first = json.loads(route.calls[0].request.content)
    second = json.loads(route.calls[1].request.content)

    assert first["tools"][0]["type"] == "openrouter:web_fetch"
    assert "response_format" not in first

    assert second["response_format"]["type"] == "json_schema"
    assert second["response_format"]["json_schema"]["strict"] is True
    assert "tools" not in second

    assert felder.bebaute_flaeche_m2 == 96.88


@respx.mock
async def test_web_fetch_is_limited_to_the_pages_own_domain():
    respx.post(CHAT_URL).mock(return_value=httpx.Response(200, json=completion("Seitentext")))

    await llm_client().fetch_page_text(PAGE_URL, "Fertighaus")

    parameters = json.loads(respx.calls[0].request.content)["tools"][0]["parameters"]
    assert parameters["allowed_domains"] == ["beispiel-hersteller.de"]
    assert parameters["engine"] == "openrouter"


@respx.mock
async def test_page_text_is_cached_per_normalised_url():
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=completion("Seitentext"))
    )

    client = llm_client()
    await client.fetch_page_text(PAGE_URL, "Fertighaus")
    await client.fetch_page_text(PAGE_URL + "?utm_source=newsletter", "Fertighaus")

    assert route.call_count == 1


@respx.mock
async def test_a_failed_fetch_is_not_visible_in_the_http_status():
    # The outer call stays 200; only the tool usage reveals the failure.
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200, json=completion("Ich konnte die Seite nicht abrufen.", tool_calls_executed=0)
        )
    )

    with pytest.raises(UpstreamError):
        await llm_client().fetch_page_text(PAGE_URL, "Fertighaus")


@respx.mock
async def test_implausible_values_are_rejected_rather_than_passed_on():
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200, json=completion(json.dumps({**HAUSTYP_JSON, "bebaute_flaeche_m2": 500}))
        )
    )

    with pytest.raises(UpstreamError):
        await llm_client().structure("text", HaustypFelder, "haustyp", "Extrahiere")


@respx.mock
async def test_non_json_answer_is_an_upstream_error():
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=completion("Hier ist das Ergebnis: kein JSON"))
    )

    with pytest.raises(UpstreamError):
        await llm_client().structure("text", HaustypFelder, "haustyp", "Extrahiere")


async def test_without_an_api_key_nothing_is_requested(without_llm):
    with pytest.raises(NotConfiguredError):
        await llm_client().fetch_page_text(PAGE_URL, "Fertighaus")
