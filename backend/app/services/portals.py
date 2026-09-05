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
ADVICE = (
    "Bitte die Anzeige im Browser öffnen, den Seiteninhalt kopieren und in "
    "das Einfügefeld einsetzen."
)

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

# The listing's own description, as the portals mark it up. Measured on
# Kleinanzeigen 05.09.2026: without this the page's *whole* text goes to the
# search -- navigation, cookie banner, category tree -- and the words that
# matter („Ortsteil Plagwitz von Machern", „1.489 m²") sit in a paragraph of
# their own that is trivially findable. The generic fallbacks cover portals
# whose markup is not known here.
_DESCRIPTION_PATTERNS = (
    re.compile(r'id="viewad-description-text"[^>]*>(.*?)</p>', re.IGNORECASE | re.DOTALL),
    re.compile(r'itemprop="description"[^>]*>(.*?)</(?:div|p|section)>', re.IGNORECASE | re.DOTALL),
    re.compile(r'class="[^"]*\bdescription\b[^"]*"[^>]*>(.*?)</(?:div|p|section)>',
               re.IGNORECASE | re.DOTALL),
)

# The attribute list a portal renders next to the description. Its area is the
# structured one, and it is the figure the tolerance staircase should start
# from -- the title may hedge („ca. 1.025qm") where the attribute does not.
_DETAIL_PATTERN = re.compile(
    r'<li class="addetailslist--detail">(.*?)</li>', re.IGNORECASE | re.DOTALL
)

# Listing images. Kleinanzeigen serves the same picture at half a dozen named
# sizes, so only the largest variant of each is kept -- reading one image six
# times is six seconds for nothing.
_KLEINANZEIGEN_IMAGE = re.compile(
    r'https://img\.kleinanzeigen\.de/api/v1/prod-ads/images/[0-9a-f]{2}/[0-9a-f\-]+'
    r'\?rule=\$_\d+\.(?:JPG|AUTO)',
    re.IGNORECASE,
)
# Anything else: the ordinary picture URLs on the page. This is what makes the
# paste field work for a portal that refuses a server-side fetch -- the user's
# browser has the page, and the pictures usually sit on a CDN that does not
# refuse us. Icons, logos and tracking pixels are dropped by extension and by
# an obvious-name filter, because reading them costs seconds each.
_GENERIC_IMAGE = re.compile(
    r'https?://[^\s"\'<>]+?\.(?:jpe?g|png|webp)(?:\?[^\s"\'<>]*)?', re.IGNORECASE
)
_NOT_A_PHOTO = ("logo", "icon", "sprite", "avatar", "placeholder", "pixel", "badge", "banner")
_IMAGE_LIMIT = 24


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


def parse_description(html: str) -> str | None:
    """The listing's own text, without the page it is embedded in."""

    for pattern in _DESCRIPTION_PATTERNS:
        match = pattern.search(html)
        if not match:
            continue
        text = re.sub(r"<br\s*/?>", "\n", match.group(1))
        text = html_module.unescape(_TAG_PATTERN.sub("", text)).strip()
        if len(text) > 80:
            return text
    return None


def parse_details(html: str) -> dict[str, str]:
    """The portal's own attribute list, as label -> value."""

    found: dict[str, str] = {}
    for match in _DETAIL_PATTERN.finditer(html):
        line = " ".join(html_module.unescape(_TAG_PATTERN.sub(" ", match.group(1))).split())
        # The markup separates label and value only by whitespace, and the
        # labels are a closed set; splitting on the known ones keeps a value
        # that contains a space („Mit Provision") intact.
        for label in ("Grundstücksfläche", "Wohnfläche", "Grundstücksart", "Angebotsart", "Zimmer"):
            if line.startswith(label):
                found[label] = line[len(label):].strip()
    return found


def parse_images(html: str) -> list[str]:
    """The listing's pictures, largest variant of each, in page order."""

    largest: dict[str, tuple[int, str]] = {}
    for url in _KLEINANZEIGEN_IMAGE.findall(html):
        identifier = url.rsplit("/", 1)[-1].split("?")[0]
        rule = int(re.search(r"rule=\$_(\d+)", url).group(1))
        if identifier not in largest or rule > largest[identifier][0]:
            largest[identifier] = (rule, url)
    if largest:
        return [url for _, url in largest.values()][:_IMAGE_LIMIT]

    found: list[str] = []
    for url in _GENERIC_IMAGE.findall(html):
        cleaned = html_module.unescape(url)
        if any(marker in cleaned.lower() for marker in _NOT_A_PHOTO):
            continue
        if cleaned not in found:
            found.append(cleaned)
    return found[:_IMAGE_LIMIT]


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
    # The listing's own prose, without the page around it. What the parcel
    # search reads: the cadastral district, the street and the relation between
    # the places named all live here and in no attribute.
    beschreibung: str | None = None
    # The portal's structured fields, „Grundstücksfläche" above all.
    angaben: dict[str, str] = field(default_factory=dict)
    bilder: list[str] = field(default_factory=list)

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
        beschreibung=parse_description(html) or meta.get("og:description") or None,
        angaben=parse_details(html),
        bilder=parse_images(html),
    )


async def fetch_page(url: str, app_settings: AppSettings) -> Seite:
    """Fetch a listing page directly -- no model, no fetch fee.

    Refuses domains that are known to block server-side retrieval, so no
    request goes out for those at all.
    """

    if is_blocked(url):
        raise BadRequestError(PASTE_HINT)

    # Kleinanzeigen answers the *first* request with 403 and the second with
    # the page -- reproduced on three adverts on 05.09.2026, each time exactly
    # once. Not a block: a warm-up. One retry costs a round trip and is the
    # difference between "the portal refuses us" and a working read.
    try:
        response = await request(
            "GET",
            url,
            service=SERVICE_NAME,
            advice=ADVICE,
            timeout_s=app_settings.http_timeout_s,
            user_agent=app_settings.portal_user_agent,
            headers={"Accept": "text/html,application/xhtml+xml"},
        )
    except UpstreamError:
        response = await request(
            "GET",
            url,
            service=SERVICE_NAME,
            advice=ADVICE,
            timeout_s=app_settings.http_timeout_s,
            user_agent=app_settings.portal_user_agent,
            headers={"Accept": "text/html,application/xhtml+xml"},
        )
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and "text" not in content_type:
        raise UpstreamError(
            "Unter dieser Adresse liegt keine lesbare Seite "
            f"({content_type or 'ohne Angabe'}). {ADVICE}"
        )
    return parse_page(url, response.text)
