"""The extraction client, for the providers a deployment may point it at.

Four names and one escape hatch, and they fall into two wire formats:

* **OpenRouter, OpenAI, Ollama** and anything else OpenAI-compatible answer
  ``POST /chat/completions``, take ``Authorization: Bearer`` and put the schema
  in ``response_format``. One transport serves all of them.
* **Anthropic** answers ``POST /v1/messages``, takes ``x-api-key`` plus a dated
  ``anthropic-version`` header, puts the schema in ``output_config.format``,
  requires ``max_tokens``, and returns ``content`` as a list of blocks rather
  than one message string.

Those differences are small and they are real, so Anthropic gets an adapter of
its own rather than a shim. A translation layer that pretends one API is the
other is exactly the thing that breaks silently the first time either side
changes -- and this project has a rule about services that answer wrongly but
successfully.

Both go out through ``upstream.request`` like every other service here: it owns
the user agent, the timeout, the single retry and the German sentence a failure
turns into. That is also why the official ``anthropic`` SDK is not used for the
Anthropic path -- it would be the one call in this backend that bypasses all of
it.



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

import hashlib
import json
from typing import Any, Iterable, TypeVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ValidationError

from ..cache import DiskCache
from ..errors import NotConfiguredError, UpstreamError
from ..settings import AppSettings, LLMSettings
from ..upstream import request

SERVICE_NAME = "Der Extraktionsdienst"

# What an Anthropic request has to declare and the OpenAI-compatible one does
# not. Generous rather than tuned: a Befund carries a Beleg per value, so it is
# several times longer than the fields alone, and a truncated answer is not a
# short answer but an unparseable one.
ANTHROPIC_MAX_TOKENS = 16000

# Anthropic's server-side fetch tool. The dated type is the API's own
# versioning: this variant needs Opus 4.6 or newer, which the default model
# for this provider is.
ANTHROPIC_FETCH_TOOL = "web_fetch_20260209"
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


def fingerprint(*parts: str) -> str:
    """A short, stable name for everything that shaped an answer.

    A cache entry outlives the code that produced it -- this one has no expiry
    at all -- so its key has to name what answered, not only what was asked.
    The rule has been broken twice here: an extraction cached before the price
    parser existed survived the parser and kept the field empty on exactly the
    listings the fix was written for, and a page text cached under a bare URL
    survived a change of prompt. Model, template and prompt therefore ride in
    the key, and a changed one simply never asks the old entry again.
    """

    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


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

    @property
    def provider(self) -> str:
        return self.settings.provider

    @property
    def speaks_anthropic(self) -> bool:
        return self.provider == "anthropic"

    def _headers(self) -> dict[str, str]:
        """Who this request says it is, in the shape this provider wants.

        Anthropic takes the key in ``x-api-key`` and versions its API by
        header; everybody else takes ``Authorization: Bearer``. A local Ollama
        takes neither, which is why the key is only demanded where it is
        actually needed.
        """

        headers = {"Content-Type": "application/json"}
        if not self.settings.needs_key:
            return headers
        api_key = self._require_key()
        if self.speaks_anthropic:
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = self.settings.anthropic_version
        else:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = await request(
            "POST",
            f"{self.settings.endpoint}{path}",
            service=SERVICE_NAME,
            advice=ADVICE,
            timeout_s=self.settings.timeout_s,
            user_agent=self.app_settings.user_agent,
            headers=self._headers(),
            json=payload,
        )
        try:
            return response.json()
        except ValueError as exc:
            raise UpstreamError(
                f"{SERVICE_NAME} hat kein gültiges JSON geliefert. {ADVICE}"
            ) from exc

    async def _chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/chat/completions", payload)

    async def _messages(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/messages", payload)

    def _message_content(self, payload: dict[str, Any]) -> str:
        """The text of an answer, from whichever shape this provider returns.

        OpenAI-compatible: one string at ``choices[0].message.content``.
        Anthropic: a list of blocks, of which the text ones are joined —
        a refusal or a thinking block sits in that list too, and taking
        ``content[0]`` would read whichever happened to come first.
        """

        content = (
            self._anthropic_text(payload)
            if self.speaks_anthropic
            else self._openai_text(payload)
        )
        if not content or not content.strip():
            raise UpstreamError(f"{SERVICE_NAME} hat eine leere Antwort geliefert. {ADVICE}")
        return content

    @staticmethod
    def _openai_text(payload: dict[str, Any]) -> str:
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise UpstreamError(
                f"{SERVICE_NAME} hat eine unerwartete Antwort geliefert. {ADVICE}"
            ) from exc
        return content if isinstance(content, str) else ""

    @staticmethod
    def _anthropic_text(payload: dict[str, Any]) -> str:
        """The text blocks of a Messages answer, joined.

        A refusal is not an error here: the call returns 200 with
        ``stop_reason: "refusal"`` and no text, and saying so is more use than
        „leere Antwort".
        """

        if payload.get("stop_reason") == "refusal":
            raise UpstreamError(
                f"{SERVICE_NAME} hat die Anfrage abgelehnt. {ADVICE}"
            )
        blocks = payload.get("content")
        if not isinstance(blocks, list):
            raise UpstreamError(
                f"{SERVICE_NAME} hat eine unerwartete Antwort geliefert. {ADVICE}"
            )
        return "".join(
            block.get("text", "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        )

    @property
    def can_fetch_pages(self) -> bool:
        """Whether this provider can go and get a page itself.

        A server-side fetch tool, not a capability of the model: OpenRouter has
        one and Anthropic has one, and they are different tools. OpenAI's
        endpoint, a local Ollama and an unknown compatible host have none — and
        for those the app's own way in is the paste field, which is not a
        degradation but the route the two blocked portals need anyway.
        """

        return self.provider in ("openrouter", "anthropic")

    async def fetch_page_text(self, url: str, auftrag: str) -> str:
        """Call 1 -- tools only, no schema."""

        if not self.can_fetch_pages:
            raise UpstreamError(
                f"Der eingestellte Dienst ({self.provider}) kann Seiten nicht selbst "
                "abrufen. Bitte den Seiteninhalt einfügen."
            )

        cache_key = (
            f"seitentext:{fingerprint(self.provider, self.settings.model_id, auftrag)}"
            f":{normalize_url(url)}"
        )
        cached = self.cache.get_json(cache_key)
        if isinstance(cached, str):
            return cached

        prompt = (
            f"Rufe {url} mit dem Web-Fetch-Werkzeug ab und gib den relevanten "
            f"Seitentext vollständig und unverändert wieder. {auftrag} "
            "Fasse nicht zusammen und erfinde nichts."
        )
        if self.speaks_anthropic:
            answer = await self._messages(
                {
                    "model": self.settings.model_id,
                    "max_tokens": ANTHROPIC_MAX_TOKENS,
                    "messages": [{"role": "user", "content": prompt}],
                    "tools": [
                        {
                            # The current variant. A model older than Opus 4.6
                            # wants `web_fetch_20250910` instead and answers 400
                            # to this one — which surfaces as the German
                            # sentence every other upstream failure does.
                            "type": ANTHROPIC_FETCH_TOOL,
                            "name": "web_fetch",
                            "max_content_tokens": self.settings.max_content_tokens,
                            "allowed_domains": [domain_of(url)],
                        }
                    ],
                }
            )
        else:
            answer = await self._chat(
                {
                    "model": self.settings.model_id,
                    "messages": [{"role": "user", "content": prompt}],
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
            )

        if not self._fetched_anything(answer):
            raise UpstreamError(
                "Die Seite konnte nicht abgerufen werden. Bitte den Seitentext einfügen."
            )

        text = self._message_content(answer)
        self.cache.set_json(cache_key, text)
        return text

    def _fetched_anything(self, answer: dict[str, Any]) -> bool:
        """Whether the fetch tool actually ran.

        A failed fetch does not surface as an HTTP error on either provider:
        the outer call stays 200 and answers prose about not being able to
        reach the page. OpenRouter says so in ``usage``; Anthropic says so by
        whether a ``web_fetch_tool_result`` block is in the answer at all.
        """

        if self.speaks_anthropic:
            blocks = answer.get("content")
            if not isinstance(blocks, list):
                return False
            return any(
                isinstance(block, dict) and block.get("type") == "web_fetch_tool_result"
                for block in blocks
            )
        usage = answer.get("usage") or {}
        tool_use = usage.get("server_tool_use_details") or {}
        return tool_use.get("tool_calls_executed") != 0

    async def structure(
        self,
        text: str,
        model: type[M],
        name: str,
        auftrag: str,
        exclude: Iterable[str] = (),
    ) -> M:
        """Call 2 -- response_format only, no tools."""

        schema = strict_json_schema(model, name, exclude)
        # Everything that shaped the answer: the model, the prompt, the schema
        # this exact call asks for, and the text itself.
        cache_key = "befund:" + fingerprint(
            self.provider,
            self.settings.model_id,
            name,
            auftrag,
            json.dumps(schema, sort_keys=True),
            text,
        )
        cached = self.cache.get_json(cache_key)
        if isinstance(cached, dict):
            try:
                return model.model_validate(cached)
            except ValidationError:
                # A cached answer from an older shape of the same schema. Ask
                # again rather than fail -- the key should have caught it, and
                # if it did not, the entry is simply worthless.
                pass

        prompt = f"{auftrag}\n\nSeitentext:\n\n{text}"
        if self.speaks_anthropic:
            answer = await self._messages(
                {
                    "model": self.settings.model_id,
                    # Required by this API, and not by the other one. Generous:
                    # a Befund with its Belege is longer than the fields alone.
                    "max_tokens": ANTHROPIC_MAX_TOKENS,
                    "messages": [{"role": "user", "content": prompt}],
                    "output_config": {
                        "format": {
                            "type": "json_schema",
                            "schema": schema["schema"],
                            "name": schema["name"],
                        }
                    },
                }
            )
        else:
            answer = await self._chat(
                {
                    "model": self.settings.model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_schema", "json_schema": schema},
                }
            )
        content = self._message_content(answer)
        try:
            data = json.loads(content)
        except ValueError as exc:
            raise UpstreamError(
                f"{SERVICE_NAME} hat kein auswertbares JSON geliefert. {ADVICE}"
            ) from exc
        try:
            structured = model.model_validate(data)
        except ValidationError as exc:
            # A value outside the plausibility bounds is an extraction error,
            # not a house -- say so instead of passing it on.
            raise UpstreamError(
                "Die ausgelesenen Werte sind nicht plausibel. "
                "Bitte die Angaben von Hand eintragen."
            ) from exc
        self.cache.set_json(cache_key, structured.model_dump(mode="json"))
        return structured
