"""The extraction client: two separate calls, a strict schema, a permanent cache."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.deps import llm_client, reset_services
from app.errors import NotConfiguredError, UpstreamError
from app.schemas import HaustypFelder, InseratBefund, InseratFelder
from app.settings import LLMSettings
from app.services.llm import domain_of, fingerprint, normalize_url, strict_json_schema

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


@respx.mock
async def test_a_cached_answer_names_what_answered_it():
    """The rule this cache has broken twice. It has no expiry, so an entry
    written by one model, prompt or schema outlives all three — and an
    extraction cached before the price parser existed survived the parser and
    kept the field empty on exactly the listings the fix was written for.

    Model, prompt and schema therefore ride in the key, and a change to any of
    them simply never asks the old entry again.
    """

    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200, json=completion(json.dumps({"vorlage": "inserat-befund/1"}))
        )
    )
    client = llm_client()

    await client.structure("ein Text", InseratBefund, "befund", "Lies das aus.")
    await client.structure("ein Text", InseratBefund, "befund", "Lies das aus.")
    assert route.call_count == 1, "derselbe Auftrag fragt nicht zweimal"

    await client.structure("ein Text", InseratBefund, "befund", "Lies etwas anderes aus.")
    assert route.call_count == 2, "ein anderer Auftrag ist eine andere Antwort"

    client.settings.model = "ein/anderes-modell"
    await client.structure("ein Text", InseratBefund, "befund", "Lies das aus.")
    assert route.call_count == 3, "ein anderes Modell ist eine andere Antwort"


def test_the_fingerprint_separates_its_parts():
    """„ab“ + „c“ and „a“ + „bc“ are two different keys, or a prompt ending in
    a word the text begins with would collide with it."""

    assert fingerprint("ab", "c") != fingerprint("a", "bc")


# ----------------------------------------------------------------------
# The providers a deployment may point this at
# ----------------------------------------------------------------------

ANTHROPIC_URL = "https://anthropic.example.org/v1/messages"


@pytest.fixture
def anthropic(monkeypatch):
    """A deployment pointed at the Anthropic API."""

    monkeypatch.setenv("LLM_ANBIETER", "anthropic")
    monkeypatch.setenv("LLM_BASE_URL", "https://anthropic.example.org/v1")
    monkeypatch.setenv("LLM_MODEL", "claude-opus-5")
    reset_services()
    yield
    reset_services()


def _anthropic_answer(text: str, **extra) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            **extra,
        },
    )


def _settings(**fields) -> LLMSettings:
    """Settings built from these fields alone.

    The suite's autouse fixture sets `LLM_*` in the environment for every test,
    and these assertions are about the resolution rules rather than about which
    of the two wins.
    """

    return LLMSettings(
        _env_file=None, **{"anbieter": "auto", "base_url": "", "model": "", **fields}
    )


def test_the_provider_is_read_off_the_endpoint_when_it_is_not_named(monkeypatch):
    """Somebody who pastes a key and an endpoint expects it to work out."""

    for name in ("LLM_ANBIETER", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    assert _settings(base_url="https://api.anthropic.com/v1").provider == "anthropic"
    assert _settings(base_url="https://api.openai.com/v1").provider == "openai"
    assert _settings(base_url="http://localhost:11434/v1").provider == "ollama"
    assert _settings(base_url="https://mein-server/v1").provider == "kompatibel"
    # And naming it always wins over the host.
    assert _settings(anbieter="openai", base_url="https://openrouter.ai/api/v1").provider == "openai"


def test_a_local_ollama_needs_no_key(monkeypatch):
    """The one provider that costs nothing must not be the one nobody can try."""

    for name in ("LLM_ANBIETER", "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    settings = _settings(anbieter="ollama")
    assert settings.configured and not settings.needs_key
    assert settings.endpoint == "http://127.0.0.1:11434/v1"
    assert settings.model_id == "llama3.1"
    # Everybody else still does.
    assert not _settings(anbieter="openai").configured


@respx.mock
async def test_anthropic_speaks_its_own_api_and_not_a_translation_of_another(anthropic):
    """Different path, different auth header, different place for the schema.
    A shim that pretended otherwise would break the first time either side
    changed — and would break silently."""

    route = respx.post(ANTHROPIC_URL).mock(
        return_value=_anthropic_answer(json.dumps({"vorlage": "inserat-befund/1"}))
    )

    await llm_client().structure("ein Text", InseratBefund, "befund", "Lies das aus.")

    assert route.call_count == 1
    request = route.calls[0].request
    assert request.headers["x-api-key"] == "test-key"
    assert request.headers["anthropic-version"]
    assert "authorization" not in request.headers
    payload = json.loads(request.content)
    # The schema goes in output_config.format, and max_tokens is required here.
    assert payload["output_config"]["format"]["type"] == "json_schema"
    assert "response_format" not in payload
    assert payload["max_tokens"] > 0
    assert payload["model"] == "claude-opus-5"


@respx.mock
async def test_an_anthropic_answer_is_a_list_of_blocks(anthropic):
    """Taking content[0] would read whichever block happened to come first —
    and a thinking block can be one of them."""

    respx.post(ANTHROPIC_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "content": [
                    {"type": "thinking", "thinking": ""},
                    {"type": "text", "text": json.dumps({"vorlage": "inserat-befund/1"})},
                ],
                "stop_reason": "end_turn",
            },
        )
    )

    answer = await llm_client().structure("x", InseratBefund, "befund", "Lies das aus.")
    assert answer.vorlage == "inserat-befund/1"


@respx.mock
async def test_a_refusal_is_said_out_loud_and_not_read_as_an_empty_answer(anthropic):
    """HTTP 200 with no text. „Leere Antwort" would be true and useless."""

    respx.post(ANTHROPIC_URL).mock(
        return_value=httpx.Response(200, json={"content": [], "stop_reason": "refusal"})
    )

    with pytest.raises(UpstreamError) as failure:
        await llm_client().structure("x", InseratBefund, "befund", "Lies das aus.")
    assert "abgelehnt" in failure.value.message


@respx.mock
async def test_a_provider_that_cannot_fetch_pages_says_so_before_it_asks(anthropic, monkeypatch):
    """OpenAI's endpoint, a local Ollama and an unknown host have no server-side
    fetch tool. The app's own way in is the paste field, and saying that costs
    no request at all."""

    monkeypatch.setenv("LLM_ANBIETER", "ollama")
    reset_services()
    route = respx.post(url__startswith="http").mock(return_value=httpx.Response(200, json={}))

    with pytest.raises(UpstreamError) as failure:
        await llm_client().fetch_page_text("https://beispiel.de/x", "Grundstück")
    assert "einfügen" in failure.value.message
    assert route.call_count == 0


@respx.mock
async def test_anthropic_fetches_with_its_own_tool_and_notices_when_it_did_not(anthropic):
    """A failed fetch stays HTTP 200 on both providers — what differs is where
    they say so."""

    route = respx.post(ANTHROPIC_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "content": [
                    {"type": "web_fetch_tool_result", "content": {}},
                    {"type": "text", "text": "Der Seitentext."},
                ],
                "stop_reason": "end_turn",
            },
        )
    )

    text = await llm_client().fetch_page_text("https://beispiel.de/x", "Grundstück")
    assert text == "Der Seitentext."
    tool = json.loads(route.calls[0].request.content)["tools"][0]
    assert tool["name"] == "web_fetch"
    assert tool["allowed_domains"] == ["beispiel.de"]

    # And the same answer without the result block is a failure, not a text.
    reset_services()
    respx.post(ANTHROPIC_URL).mock(
        return_value=_anthropic_answer("Ich konnte die Seite nicht abrufen.")
    )
    with pytest.raises(UpstreamError):
        await llm_client().fetch_page_text("https://beispiel.de/y", "Grundstück")
