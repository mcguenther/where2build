"""OpenAI-compatible extraction client.

**Why two calls instead of one.** The provider research
(``docs/research/openrouter.md``, section 5) tested the combined call sketched
in the specification -- ``tools: [web_fetch]`` *and*
``response_format: json_schema, strict: true`` in one request -- against three
models. None of them honoured the schema while a server tool was active; all
three invented their own field names, so ``model_validate_json`` would have
failed on every answer. The fetching itself worked, and the models even got the
hard part right (built-up area, not living area).

Hence the split kept here:

1. one call with ``tools: [web_fetch]`` and **no** ``response_format`` -- it
   brings back the page text,
2. one call with ``response_format`` and **no** ``tools`` -- it structures that
   text against the Pydantic schema.

A fetch failure does not surface as an HTTP error either: the outer call stays
200 and only ``usage.server_tool_use_details`` reveals whether anything was
fetched at all.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, TypeVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ValidationError

from ..cache import DiskCache
from ..errors import NotConfiguredError, UpstreamError
from ..settings import AppSettings, LLMSettings
from ..telemetry import AREA_MODEL, RESULT_OK, recorder
from ..upstream import request

SERVICE_NAME = "Der Extraktionsdienst"
# Extraction only ever produces suggestions, so its failure never blocks
# anything -- the same fields can be typed in.
ADVICE = "Die Angaben lassen sich von Hand eintragen."

M = TypeVar("M", bound=BaseModel)

# Query parameters that identify a campaign, not a page.
_TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "ref",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}


def normalize_url(url: str) -> str:
    """Cache key for a page: the same listing must not be paid for twice."""

    parts = urlsplit(url.strip())
    host = parts.hostname or ""
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_PARAMS
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), host.lower(), path, urlencode(query), ""))


def domain_of(url: str) -> str:
    """Registrable-ish host of a URL, without a leading ``www.``."""

    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def strict_json_schema(
    model: type[BaseModel], name: str, exclude: Iterable[str] = ()
) -> dict[str, Any]:
    """Pydantic schema -> a schema an OpenAI-strict endpoint accepts.

    Strict mode wants every property listed in ``required``, no
    ``additionalProperties`` and no ``$ref`` indirection, and it expresses
    optionality as a nullable type rather than an absent field.
    """

    source = model.model_json_schema()
    definitions = source.get("$defs", {})
    excluded = set(exclude)

    def convert(node: Any) -> Any:
        if isinstance(node, list):
            return [convert(item) for item in node]
        if not isinstance(node, dict):
            return node

        if "$ref" in node:
            key = node["$ref"].rsplit("/", 1)[-1]
            return convert(definitions[key])

        node = {key: value for key, value in node.items() if key != "$defs"}

        any_of = node.get("anyOf")
        if any_of:
            non_null = [item for item in any_of if item.get("type") != "null"]
            nullable = len(non_null) < len(any_of)
            if len(non_null) == 1:
                merged = convert(non_null[0])
                if nullable and isinstance(merged.get("type"), str):
                    merged["type"] = [merged["type"], "null"]
                for key in ("description", "title"):
                    if key in node and key not in merged:
                        merged[key] = node[key]
                return merged
            node["anyOf"] = [convert(item) for item in non_null]
            return node

        converted = {key: convert(value) for key, value in node.items()}
        if converted.get("type") == "object" and "properties" in converted:
            converted["properties"] = {
                key: value
                for key, value in converted["properties"].items()
                if key not in excluded
            }
            converted["required"] = list(converted["properties"])
            converted["additionalProperties"] = False
        # Bounds are enforced by Pydantic after the call; strict schemas reject
        # several of these keywords outright.
        for keyword in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "default"):
            converted.pop(keyword, None)
        return converted

    schema = convert(source)
    return {"name": name, "strict": True, "schema": schema}


def _count_tokens(model: str, answer: Any) -> None:
    """Record what one call to the model cost.

    Counted here rather than beside the outward request in ``app/upstream.py``,
    because the number is in the *answer*: the call itself is one request like
    any other, and only the body says how many tokens it was. A provider that
    reports no usage at all is counted as a call with no tokens rather than not
    counted -- that the call happened is the more important of the two facts.
    """

    usage = answer.get("usage") if isinstance(answer, dict) else None
    usage = usage if isinstance(usage, dict) else {}
    recorder().count(
        AREA_MODEL,
        model or "unbekannt",
        RESULT_OK,
        tokens_in=_whole(usage.get("prompt_tokens") or usage.get("input_tokens")),
        tokens_out=_whole(usage.get("completion_tokens") or usage.get("output_tokens")),
    )


def _whole(value: Any) -> int:
    return int(value) if isinstance(value, (int, float)) and value > 0 else 0


class LLMClient:
    """Talks to any OpenAI-compatible ``/chat/completions`` endpoint."""

    def __init__(self, settings: LLMSettings, app_settings: AppSettings) -> None:
        self.settings = settings
        self.app_settings = app_settings
        # No TTL: a house type does not change from one week to the next, and
        # every fetch costs money.
        self.cache = DiskCache(app_settings.cache_dir / "llm", ttl_s=None)

    def _require_key(self) -> str:
        if not self.settings.configured:
            raise NotConfiguredError(
                "Das Auslesen von Seiten ist nicht konfiguriert (LLM_API_KEY fehlt). "
                "Bitte den Seitentext einfügen."
            )
        assert self.settings.api_key is not None
        return self.settings.api_key.get_secret_value()

    async def _chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        api_key = self._require_key()
        response = await request(
            "POST",
            f"{self.settings.base_url.rstrip('/')}/chat/completions",
            service=SERVICE_NAME,
            advice=ADVICE,
            timeout_s=self.settings.timeout_s,
            user_agent=self.app_settings.user_agent,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        try:
            answer = response.json()
        except ValueError as exc:
            raise UpstreamError(
                f"{SERVICE_NAME} hat kein gültiges JSON geliefert. {ADVICE}"
            ) from exc
        _count_tokens(self.settings.model, answer)
        return answer

    @staticmethod
    def _message_content(payload: dict[str, Any]) -> str:
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise UpstreamError(
                f"{SERVICE_NAME} hat eine unerwartete Antwort geliefert. {ADVICE}"
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise UpstreamError(f"{SERVICE_NAME} hat eine leere Antwort geliefert. {ADVICE}")
        return content

    async def fetch_page_text(self, url: str, auftrag: str) -> str:
        """Call 1 -- tools only, no response_format."""

        cache_key = f"seitentext:{normalize_url(url)}"
        cached = self.cache.get_json(cache_key)
        if isinstance(cached, str):
            return cached

        payload = {
            "model": self.settings.model,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Rufe {url} mit dem Web-Fetch-Werkzeug ab und gib den relevanten "
                        f"Seitentext vollständig und unverändert wieder. {auftrag} "
                        "Fasse nicht zusammen und erfinde nichts."
                    ),
                }
            ],
            "tools": [
                {
                    "type": "openrouter:web_fetch",
                    "parameters": {
                        "engine": self.settings.fetch_engine,
                        "max_content_tokens": self.settings.max_content_tokens,
                        # Keep the model on the page the user asked about.
                        "allowed_domains": [domain_of(url)],
                    },
                }
            ],
        }
        answer = await self._chat(payload)

        usage = answer.get("usage") or {}
        tool_use = usage.get("server_tool_use_details") or {}
        if tool_use.get("tool_calls_executed") == 0:
            raise UpstreamError(
                "Die Seite konnte nicht abgerufen werden. Bitte den Seitentext einfügen."
            )

        text = self._message_content(answer)
        self.cache.set_json(cache_key, text)
        return text

    async def structure(
        self,
        text: str,
        model: type[M],
        name: str,
        auftrag: str,
        exclude: Iterable[str] = (),
    ) -> M:
        """Call 2 -- response_format only, no tools."""

        payload = {
            "model": self.settings.model,
            "messages": [
                {
                    "role": "user",
                    "content": f"{auftrag}\n\nSeitentext:\n\n{text}",
                }
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": strict_json_schema(model, name, exclude),
            },
        }
        answer = await self._chat(payload)
        content = self._message_content(answer)
        try:
            data = json.loads(content)
        except ValueError as exc:
            raise UpstreamError(
                f"{SERVICE_NAME} hat kein auswertbares JSON geliefert. {ADVICE}"
            ) from exc
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            # A value outside the plausibility bounds is an extraction error,
            # not a house -- say so instead of passing it on.
            raise UpstreamError(
                "Die ausgelesenen Werte sind nicht plausibel. "
                "Bitte die Angaben von Hand eintragen."
            ) from exc
