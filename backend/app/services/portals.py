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
from .portal_fields import (
    location_line,
    read_area_m2,
    read_location,
    read_price_eur,
)

SERVICE_NAME = "Die Anzeigenseite"
ADVICE = (
    "Bitte die Anzeige im Browser öffnen, den Seiteninhalt kopieren und in "
    "das Einfügefeld einsetzen."
)

# Domains whose server-side retrieval is known to fail; the paste field (F-12)
# is the only reliable way in.
BLOCKED_DOMAINS = {"immobilienscout24.de"}

PASTE_HINT = (
    "immobilienscout24.de lässt keinen Serverabruf zu und antwortet mit „Ich bin "
    "kein Roboter“ (HTTP 401, zuletzt bestätigt am 09.09.2026). Der Weg führt über "
    "„Seite einfügen“: dort einmal das Lesezeichen einrichten, dann schickt ein "
    "Klick auf der Anzeigenseite sie vollständig herüber. Ohne Lesezeichen die "
    "Seite kopieren und einfügen — Fläche, Preis und Beschreibung kommen mit, die "
    "Meta-Angaben nicht."
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
# The listing's own gallery. The same page carries „Ähnliche Anzeigen“ below it,
# with their pictures in the same CDN and in its JSON-LD -- measured on two
# adverts, three of nine and three of eleven URLs belonged to *other* listings,
# one of them a plot in Großbothen. Read as this listing's evidence, a
# Geoportal print among them hands the search another seller's parcel number.
# Only the gallery's pictures carry `itemprop="image"`.
_GALLERY_IMAGE_TAG = re.compile(r'<img\b[^>]*\bitemprop="image"[^>]*>', re.IGNORECASE)
_IMAGE_IDENTIFIER = re.compile(r"prod-ads/images/[0-9a-f]{2}/([0-9a-f\-]+)", re.IGNORECASE)
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

# The asking price. On the wire twice on every advert measured -- as a
# machine-readable ``itemprop`` and as the displayed „60.000 €" -- so it never
# needed a model to find it, and the model is exactly what was not configured
# when it went missing.
_PRICE_PATTERNS = (
    re.compile(r'itemprop="price"[^>]*content="([^"]*)"', re.IGNORECASE),
    re.compile(r'<meta[^>]+property="product:price:amount"[^>]+content="([^"]*)"', re.IGNORECASE),
    re.compile(r'id="viewad-price"[^>]*>(.*?)<', re.IGNORECASE | re.DOTALL),
    re.compile(r'"price"\s*:\s*"?([\d.,]+)"?', re.IGNORECASE),
)

# What separates „1.489" (one thousand) from „51.189265" (a coordinate): a dot
# is a thousands separator only where it groups exactly three digits.
_THOUSANDS = re.compile(r"^-?\d{1,3}(\.\d{3})+$")


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


_HEADING_PATTERN = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
TITLE_LIMIT = 500


def parse_heading(html: str) -> str | None:
    """The page's first non-empty `<h1>`, which on a listing is its title.

    Only a fallback for `og:title`: that tag lives in `<head>`, and `Strg+A`
    selects the body alone, so a clipboard copy arrived with no title at all
    while the heading stood right above the price.
    """

    for markup in _HEADING_PATTERN.findall(html):
        text = _clean(markup)
        if len(text) >= 3:
            return text[:TITLE_LIMIT]
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


def german_number(raw: str) -> float | None:
    """A number out of what a German page wrote.

    The dot is a thousands separator only where it groups threes; anywhere else
    it is a decimal point. Stripping every dot turns „1.489" into 1489 correctly
    and „51.189265" into 51 189 265, which is how a coordinate became a
    validation error with no hint as to why.
    """

    match = re.search(r"-?\d[\d.,]*", raw.replace(" ", "").replace("\u00a0", ""))
    if not match:
        return None
    digits = match.group(0)
    if "," in digits:
        digits = digits.replace(".", "").replace(",", ".")
    elif _THOUSANDS.match(digits):
        digits = digits.replace(".", "")
    try:
        return float(digits)
    except ValueError:
        return None


def _area_of(angaben: dict[str, str]) -> str | None:
    """Whether an area was already read, whatever it looks like."""

    return angaben.get("Grundstücksfläche") or None


def parse_price(html: str) -> int | None:
    """The asking price in euro, from whichever of the four spellings is there."""

    for pattern in _PRICE_PATTERNS:
        match = pattern.search(html)
        if not match:
            continue
        text = html_module.unescape(_TAG_PATTERN.sub(" ", match.group(1)))
        # „VB", „Zu verschenken", „auf Anfrage" are not prices.
        value = german_number(text)
        if value is not None and 0 < value < 100_000_000:
            return int(round(value))
    return None


def parse_images(html: str) -> list[str]:
    """The listing's pictures, largest variant of each, in page order."""

    gallery = {
        identifier
        for tag in _GALLERY_IMAGE_TAG.findall(html)
        for identifier in _IMAGE_IDENTIFIER.findall(tag)
    }
    largest: dict[str, tuple[int, str]] = {}
    for url in _KLEINANZEIGEN_IMAGE.findall(html):
        identifier = url.rsplit("/", 1)[-1].split("?")[0]
        # A page saved without its gallery markup still yields its pictures;
        # only where the gallery is visible does it decide.
        if gallery and identifier not in gallery:
            continue
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
    kaufpreis_eur: int | None = None

    @property
    def has_coordinates(self) -> bool:
        return self.lat is not None and self.lon is not None


# ---------------------------------------------------------------------------
# immobilienscout24.de
#
# Its own field names, kept together in one place so they can be re-derived
# from a fresh recording without touching anything around them. Read off
# `tests/fixtures/inserat-immoscout.html` (advert 167953918, Grünau-Siedlung
# in Leipzig, 09.09.2026) and every one of them is asserted against that file
# in `tests/test_portals.py`. When the portal renames something, the failing
# test says which name, and only this block changes.
#
# Two shapes arrive and they are not the same page:
#
#   * **The whole document**, handed over by the bookmarklet. Its analytics
#     block carries the plot area, the price, the Bundesland, the Kreis and the
#     Ortsteil as *separate fields* — `obj_lotArea: "742"`, `geo_bln: "sachsen"`,
#     `geo_krs: "leipzig"`, `obj_regio4: "Grünau_Siedlung"`. That is better than
#     the same numbers read out of prose: the title hedges („ca. 742 m²") where
#     the field states 742, and the Bundesland is the cheapest hard filter the
#     search has. Same block twice, in `keyValues` and in `<s24-ad-targeting>`.
#   * **The body alone**, out of the clipboard. The same numbers as rendered
#     text in the portal's own `is24qa-*` elements, which survive a selection.
#
# What is deliberately *not* read: the coordinate. `exposeMap` carries one
# (51.30595, 12.27605) next to `showFullAddress: false` and `isFullAddress:
# false` — it is the *quarter's* point, not the plot's, the same class of thing
# as Kleinanzeigen's municipality pin that measured 6 235 m from the parcel
# actually offered. This app treats a coordinate as a locator and resolves the
# parcel under it, so a quarter centroid is worse than no coordinate at all.
# It is taken only when the portal says the address is complete.
_IS24_MARKER = re.compile(r"IS24\.expose\s*=|is24qa-|immobilienscout24\.de/expose", re.IGNORECASE)

# The analytics block: `"name":"value"`, present in the whole document only.
def _is24_field(name: str) -> re.Pattern[str]:
    return re.compile(rf'"{name}"\s*:\s*"([^"]*)"')

_IS24_AREA = _is24_field("obj_lotArea")
_IS24_PRICE = _is24_field("obj_purchasePrice")
_IS24_STATE = _is24_field("obj_regio1")
_IS24_ADDRESS = _is24_field("zipRegionAndCountry")
_IS24_FULL_ADDRESS = re.compile(r'"?isFullAddress"?\s*:\s*(true|false)', re.IGNORECASE)
_IS24_COORDINATE = re.compile(
    r'"latitude"\s*:\s*(-?\d+(?:\.\d+)?)\s*,\s*"coordinateAvailable"\s*:\s*true'
    r'[^}]*?"longitude"\s*:\s*(-?\d+(?:\.\d+)?)'
)
# The picture the gallery would show at full size, largest variant of each.
_IS24_IMAGE = re.compile(r'"fullSizePictureUrl"\s*:\s*"([^"]+)"')

# The rendered body, which is all a clipboard copy brings.
# `(?![-\w])` is load-bearing: every value element has a `…-label` sibling
# carrying the same class plus a suffix, and it comes first in the document.
# Without the guard the label matched and `.*?</dd>` swallowed through to the
# value, so the area read „Grundstücksfläche ca. 742 m²" — label and all.
_IS24_BODY_AREA = re.compile(
    r'class="[^"]*is24qa-grundstueck-ca(?![-\w])[^"]*"[^>]*>(.*?)</dd>',
    re.IGNORECASE | re.DOTALL,
)
_IS24_BODY_PRICE = re.compile(
    r'class="[^"]*is24qa-kaufpreis(?![-\w])[^"]*"[^>]*>(.*?)</dd>',
    re.IGNORECASE | re.DOTALL,
)
_IS24_BODY_ADDRESS = re.compile(
    r'class="[^"]*address-text[^"]*"[^>]*>(.*?)</span>', re.IGNORECASE | re.DOTALL
)
# Both description blocks: the object's own text and the one about the area.
# The search reads the district, the street and the relation between the places
# named out of exactly these two.
_IS24_BODY_PROSE = re.compile(
    r'class="[^"]*expose-(?:description-body|location-description)[^"]*"[^>]*>(.*?)</span>',
    re.IGNORECASE | re.DOTALL,
)


def is_immoscout(html: str) -> bool:
    """Whether this markup is an ImmoScout24 exposé, whole or body only."""

    return bool(_IS24_MARKER.search(html))


def _json_string(name: str, html: str) -> str | None:
    """One JSON string value out of an inline script, escapes and all.

    `objectDescription` carries its paragraph breaks as `\n` inside the JSON,
    so the value has to be decoded rather than sliced out -- otherwise the
    prose reaches the search as one line with literal backslash-n in it, and
    the sentence boundaries the reader keys on are gone.
    """

    match = re.search(rf'"{name}"\s*:\s*"((?:[^"\\]|\\.)*)"', html)
    if not match:
        return None
    try:
        return json.loads(f'"{match.group(1)}"')
    except ValueError:
        return None


def _clean(markup: str) -> str:
    """The text of one element: tags, comments and runs of space removed.

    React separates adjacent text nodes with an empty comment, so the address
    line really is `<span> <!-- -->Grünau-Siedlung, 04207 Leipzig</span>`.
    """

    without_comments = re.sub(r"<!--.*?-->", "", markup, flags=re.DOTALL)
    text = html_module.unescape(_TAG_PATTERN.sub(" ", without_comments))
    return " ".join(text.split())


def parse_immoscout(html: str) -> dict[str, Any]:
    """What an ImmoScout24 exposé gives up, from whichever shape arrived.

    The whole document first, because its fields are structured; the rendered
    body second, because that is all a paste has. Only keys that were actually
    found are returned, so a caller can overlay this on the generic pass.
    """

    found: dict[str, Any] = {}

    # --- the whole document
    area = _IS24_AREA.search(html)
    price = _IS24_PRICE.search(html)
    address = _IS24_ADDRESS.search(html)
    state = _IS24_STATE.search(html)
    if area:
        found["flaeche"] = f"{area.group(1)} m²"
    if price:
        found["kaufpreis_eur"] = int(float(price.group(1)))
    if address:
        # The Bundesland is not in the page's own address line, and it is the
        # cheapest hard filter the search has -- ALKIS is state-specific, so a
        # plot in Sachsen-Anhalt has no Saxon Flurstück. Composed from the
        # portal's two fields, not written.
        parts = [address.group(1)] + ([state.group(1)] if state else [])
        found["adresse"] = ", ".join(part for part in parts if part)

    prose = [
        text
        for text in (_json_string("objectDescription", html), _json_string("locationDescription", html))
        if text
    ]
    if prose:
        found["beschreibung"] = "\n\n".join(prose)

    pictures: list[str] = []
    for url in _IS24_IMAGE.findall(html):
        if url not in pictures:
            pictures.append(url)
    if pictures:
        found["bilder"] = pictures[:_IMAGE_LIMIT]

    complete = _IS24_FULL_ADDRESS.search(html)
    coordinate = _IS24_COORDINATE.search(html)
    if coordinate and complete and complete.group(1).lower() == "true":
        found["lat"] = float(coordinate.group(1))
        found["lon"] = float(coordinate.group(2))

    # --- the body alone, for whatever the document did not answer
    if "flaeche" not in found:
        body_area = _IS24_BODY_AREA.search(html)
        if body_area:
            found["flaeche"] = _clean(body_area.group(1))
    if "kaufpreis_eur" not in found:
        body_price = _IS24_BODY_PRICE.search(html)
        if body_price:
            value = german_number(_clean(body_price.group(1)))
            if value is not None and 0 < value < 100_000_000:
                found["kaufpreis_eur"] = int(round(value))
    if "adresse" not in found:
        body_address = _IS24_BODY_ADDRESS.search(html)
        if body_address:
            found["adresse"] = _clean(body_address.group(1)) or None
    if "beschreibung" not in found:
        blocks = [_clean(block) for block in _IS24_BODY_PROSE.findall(html)]
        # „Wir machen die obigen Angaben nach bestem Wissen …" is the agent's
        # disclaimer, not a statement about the plot. Anything short is a
        # heading or a legal note; the two texts the search wants are long.
        long_enough = [block for block in blocks if len(block) > 120]
        if long_enough:
            found["beschreibung"] = "\n\n".join(long_enough)

    return {name: value for name, value in found.items() if value not in (None, "", [])}


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

    seite = Seite(
        url=url,
        text=html_to_text(html),
        meta=meta,
        json_ld=json_ld,
        lat=latitude,
        lon=longitude,
        titel=meta.get("og:title") or parse_heading(html),
        adresse=", ".join(address_parts) if address_parts else None,
        beschreibung=parse_description(html) or meta.get("og:description") or None,
        angaben=parse_details(html),
        bilder=parse_images(html),
        kaufpreis_eur=parse_price(html),
    )

    # A portal that names its own fields beats every generic pattern, so its
    # answers are laid over the pass above rather than merged into it. The
    # generic ones stay underneath for whatever the portal block did not find.
    if is_immoscout(html):
        read = parse_immoscout(html)
        if "flaeche" in read:
            seite.angaben = {**seite.angaben, "Grundstücksfläche": read["flaeche"]}
        for name in ("adresse", "beschreibung", "kaufpreis_eur", "lat", "lon", "bilder"):
            if name in read:
                setattr(seite, name, read[name])
        # `og:description` is the portal's own summary line („742 qm -
        # Grünau-Siedlung"), which is not prose the search can read a relation
        # out of. Better nothing than that.
        if "beschreibung" not in read and seite.beschreibung == meta.get("og:description"):
            seite.beschreibung = None

    # The floor: whatever nothing above answered is read without knowing the
    # portal at all — the label and the value's unit, wherever on the page they
    # stand. That is what makes an unrecorded portal usable instead of refused.
    # Only gaps are filled, because a portal's own field or a meta tag is a
    # statement while this is a reading.
    if not _area_of(seite.angaben):
        area = read_area_m2(html)
        if area is not None:
            seite.angaben = {**seite.angaben, "Grundstücksfläche": f"{area} m²"}
    if seite.kaufpreis_eur is None:
        seite.kaufpreis_eur = read_price_eur(html)
    if not seite.adresse:
        seite.adresse = location_line(read_location(html))

    return seite


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
