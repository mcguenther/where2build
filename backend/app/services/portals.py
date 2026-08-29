"""Portal adapters -- the fallback chain per domain.

Live-tested on 29.08.2026 (``docs/research/openrouter.md``):

* ``kleinanzeigen.de`` serves the full page including ``og:latitude`` and
  ``og:longitude``. Reading those meta tags saves both the model call and the
  geocoding step, so that is what happens first.
* ``immobilienscout24.de`` answers every server-side request with HTTP 401
  (AWS WAF challenge) -- through plain httpx and through all three
  OpenRouter fetch engines alike. It is therefore not requested at all; the
  user is pointed at the paste field instead.
* Unknown domains: web_fetch first, then meta tags and JSON-LD, then the full
  text to the model.
"""

from __future__ import annotations

import html as html_module
import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..errors import BadRequestError, UpstreamError
from ..settings import AppSettings
from ..upstream import request
from .llm import domain_of

SERVICE_NAME = "Die Anzeigenseite"

# Domains whose server-side retrieval is known to fail; the paste field (F-12)
# is the only reliable way in.
BLOCKED_DOMAINS = {"immobilienscout24.de"}

PASTE_HINT = (
    "immobilienscout24.de lässt keinen Serverabruf zu (HTTP 401, live bestätigt "
    "am 29.08.2026). Bitte die Anzeige im Browser öffnen, den Seiteninhalt "
    "kopieren und in das Einfügefeld einsetzen."
)

_META_PATTERN = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_ATTR_PATTERN = re.compile(
    r"""(\w[\w:.\-]*)\s*=\s*("([^"]*)"|'([^']*)'|([^\s"'>]+))""", re.IGNORECASE
)
_SCRIPT_STYLE_PATTERN = re.compile(
    r"<(script|style|noscript)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
_JSON_LD_PATTERN = re.compile(
    r"""<script\b[^>]*type\s*=\s*["']application/ld\+json["'][^>]*>(.*?)</script>""",
    re.IGNORECASE | re.DOTALL,
)
_TAG_PATTERN = re.compile(r"<[^>]+>")


def is_blocked(url: str) -> bool:
    domain = domain_of(url)
    return any(domain == blocked or domain.endswith(f".{blocked}") for blocked in BLOCKED_DOMAINS)


def is_kleinanzeigen(url: str) -> bool:
    domain = domain_of(url)
    return domain == "kleinanzeigen.de" or domain.endswith(".kleinanzeigen.de")


def _attributes(tag: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for match in _ATTR_PATTERN.finditer(tag):
        value = match.group(3) or match.group(4) or match.group(5) or ""
        found[match.group(1).lower()] = html_module.unescape(value)
    return found


def parse_meta_tags(html: str) -> dict[str, str]:
    """All ``<meta>`` tags as ``property|name|itemprop -> content``."""

    meta: dict[str, str] = {}
    for tag in _META_PATTERN.findall(html):
        attributes = _attributes(tag)
        content = attributes.get("content")
        if content is None:
            continue
        for key in ("property", "name", "itemprop"):
            if attributes.get(key):
                meta.setdefault(attributes[key].lower(), content)
    return meta


def parse_json_ld(html: str) -> list[Any]:
    """Every parseable JSON-LD block on the page."""

    blocks: list[Any] = []
    for raw in _JSON_LD_PATTERN.findall(html):
        try:
            blocks.append(json.loads(raw.strip()))
        except ValueError:
            continue
    return blocks


def html_to_text(html: str, limit: int = 40_000) -> str:
    """Readable text of a page -- what gets handed to the model."""

    without_code = _SCRIPT_STYLE_PATTERN.sub(" ", html)
    text = _TAG_PATTERN.sub(" ", without_code)
    text = html_module.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()[:limit]


def _as_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _coordinates_from_json_ld(blocks: list[Any]) -> tuple[float | None, float | None]:
    stack: list[Any] = list(blocks)
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            if "latitude" in node and "longitude" in node:
                latitude = _as_float(str(node["latitude"]))
                longitude = _as_float(str(node["longitude"]))
                if latitude is not None and longitude is not None:
                    return latitude, longitude
            stack.extend(node.values())
    return None, None


@dataclass
class Seite:
    """What could be read off a listing page without asking a model."""

    url: str
    text: str = ""
    meta: dict[str, str] = field(default_factory=dict)
    json_ld: list[Any] = field(default_factory=list)
    lat: float | None = None
    lon: float | None = None
    titel: str | None = None
    adresse: str | None = None

    @property
    def has_coordinates(self) -> bool:
        return self.lat is not None and self.lon is not None


def parse_page(url: str, html: str) -> Seite:
    """Deterministic pass over the HTML: meta tags first, then JSON-LD."""

    meta = parse_meta_tags(html)
    json_ld = parse_json_ld(html)

    latitude = _as_float(meta.get("og:latitude") or meta.get("place:location:latitude"))
    longitude = _as_float(meta.get("og:longitude") or meta.get("place:location:longitude"))
    if latitude is None or longitude is None:
        latitude, longitude = _coordinates_from_json_ld(json_ld)

    street = meta.get("og:street-address") or meta.get("street-address")
    locality = meta.get("og:locality") or meta.get("og:region")
    postal = meta.get("og:postal-code")
    address_parts = [part for part in (street, postal, locality) if part]

    return Seite(
        url=url,
        text=html_to_text(html),
        meta=meta,
        json_ld=json_ld,
        lat=latitude,
        lon=longitude,
        titel=meta.get("og:title"),
        adresse=", ".join(address_parts) if address_parts else None,
    )


async def fetch_page(url: str, app_settings: AppSettings) -> Seite:
    """Fetch a listing page directly -- no model, no fetch fee.

    Refuses domains that are known to block server-side retrieval, so no
    request goes out for those at all.
    """

    if is_blocked(url):
        raise BadRequestError(PASTE_HINT)

    response = await request(
        "GET",
        url,
        service=SERVICE_NAME,
        timeout_s=app_settings.http_timeout_s,
        user_agent=app_settings.portal_user_agent,
        headers={"Accept": "text/html,application/xhtml+xml"},
    )
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and "text" not in content_type:
        raise UpstreamError(
            "Unter dieser Adresse liegt keine lesbare Seite "
            f"({content_type or 'ohne Angabe'})."
        )
    return parse_page(url, response.text)
