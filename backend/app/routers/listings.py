"""POST /api/listings/extract -- a listing URL or pasted text becomes an Inserat."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from pydantic import ValidationError

from ..deps import llm_client, settings_dep
from ..errors import BadRequestError, NotConfiguredError, UpstreamError
from ..schemas import (
    Extraktionsweg,
    Inserat,
    InseratFelder,
    InseratVorschlaege,
    ListingExtractRequest,
    ListingExtractResponse,
    as_vorschlaege,
)
from ..services.llm import LLMClient, normalize_url
from ..services.portals import PASTE_HINT, fetch_page, is_blocked, is_kleinanzeigen, parse_page
from ..settings import Settings

router = APIRouter(prefix="/api/listings", tags=["Inserate"])

_FETCH_TASK = (
    "Es geht um ein Grundstücksinserat: Adresse, Flurstücksnummern, Kaufpreis "
    "und Grundstücksfläche."
)
_STRUCTURE_TASK = (
    "Lies aus dem folgenden Text eines Grundstücksinserats aus: Adresse, "
    "Koordinaten, Flurstückskennungen (etwa „Flurstück 790 sowie 706“), Kaufpreis "
    "in Euro und Grundstücksfläche in Quadratmetern. Trage nur ein, was im Text "
    "tatsächlich steht, sonst null. Namen, Telefonnummern und andere Kontaktdaten "
    "werden nicht erfasst."
)

# What the reader produces, as a number. It rides in the cache key, because the
# cache that holds an extracted listing has no expiry (`ttl_s=None`) and is
# keyed on the URL alone -- so an answer produced before the price parser
# existed outlived the parser, and the field stayed empty on the very listings
# the fix was written for. Bump this whenever the extraction's *output* changes:
# a new field, a new source for one, a corrected parse. Old entries are then
# simply never asked for again, and the sweeper clears them.
#
#   1  the original reader
#   2  asking price, plot area from the attribute list, description and images
EXTRACTION_VERSION = 2

_NO_LOCATOR = (
    "Aus dieser Seite ließ sich weder eine Adresse noch eine Koordinate noch ein "
    "Flurstück lesen. Bitte den Seiteninhalt einfügen oder die Angaben von Hand eintragen."
)


def _has_locator(felder: InseratFelder) -> bool:
    """Whether the deterministic pass found enough to place the plot at all."""

    return bool(
        felder.adresse
        or felder.flurstuecke
        or (felder.lat is not None and felder.lon is not None)
    )


def _area_from(angaben: dict[str, str]) -> int | None:
    """The plot area out of the portal's own attribute list.

    Structured and therefore better than the same number read out of the prose:
    a title may hedge („ca. 1.025qm") where the field states 1.025 m², and the
    tolerance staircase starts where the *wording* says.
    """

    raw = angaben.get("Grundstücksfläche")
    if not raw:
        return None
    match = re.search(r"\d[\d.\s]*", raw)
    if not match:
        return None
    try:
        return int(float(match.group(0).replace(".", "").replace(" ", "")))
    except ValueError:
        return None


def _merge(deterministic: InseratFelder, extracted: InseratFelder | None) -> InseratFelder:
    """Deterministic values win; the model only fills the gaps."""

    if extracted is None:
        return deterministic
    merged = deterministic.model_dump()
    for name, value in extracted.model_dump().items():
        if merged.get(name) in (None, "", []):
            merged[name] = value
    return InseratFelder.model_validate(merged)


# How much of a page's prose travels back. Enough for a description with its
# location sentences; not a whole portal page with its navigation.
_DESCRIPTION_LIMIT = 20_000


def _answer(
    felder: InseratFelder,
    quelle_url: str | None,
    weg: Extraktionsweg,
    hinweis: str | None = None,
    titel: str | None = None,
    beschreibung: str | None = None,
    bilder: list[str] | None = None,
) -> ListingExtractResponse:
    try:
        inserat = Inserat(**felder.model_dump(), quelle_url=quelle_url)
    except ValidationError as exc:
        raise BadRequestError(_NO_LOCATOR) from exc
    text = " ".join(part for part in (titel, beschreibung) if part).strip()
    return ListingExtractResponse(
        felder=as_vorschlaege(inserat, InseratVorschlaege, quelle_url),
        quelle_url=quelle_url,
        weg=weg,
        hinweis=hinweis or titel,
        beschreibung=text[:_DESCRIPTION_LIMIT] or None,
        bilder=bilder or [],
    )


async def _from_url(url: str, llm: LLMClient, settings: Settings) -> ListingExtractResponse:
    if is_blocked(url):
        # No request goes out at all -- the answer is known to be 401.
        raise BadRequestError(PASTE_HINT)

    if is_kleinanzeigen(url):
        seite = await fetch_page(url, settings.app)
        deterministic = InseratFelder(
            adresse=seite.adresse, lat=seite.lat, lon=seite.lon,
            grundstuecksflaeche_m2=_area_from(seite.angaben),
            kaufpreis_eur=seite.kaufpreis_eur,
        )
        weg: Extraktionsweg = "meta-tags" if seite.has_coordinates else "llm"
        hinweis = None
        extracted: InseratFelder | None = None
        if llm.settings.configured and seite.text:
            try:
                extracted = await llm.structure(
                    seite.text, InseratFelder, "inserat", _STRUCTURE_TASK
                )
            except UpstreamError as exc:
                if not seite.has_coordinates:
                    raise
                hinweis = f"Nur die Meta-Angaben der Seite konnten gelesen werden: {exc.message}"
        elif not seite.has_coordinates:
            raise NotConfiguredError(
                "Das Auslesen von Seiten ist nicht konfiguriert und die Seite trägt "
                "keine Koordinaten. Bitte den Seiteninhalt einfügen."
            )
        return _answer(
            _merge(deterministic, extracted),
            url,
            weg,
            hinweis,
            seite.titel,
            # The description, not the whole page: without this the search
            # reads a portal's navigation and cookie banner as evidence.
            seite.beschreibung or seite.text,
            seite.bilder,
        )

    # Unknown domain: the spec's chain is web_fetch first, then meta tags and
    # JSON-LD from a direct request, then the full text to the model.
    seite = None
    text = ""
    if llm.settings.configured:
        try:
            text = await llm.fetch_page_text(url, _FETCH_TASK)
        except UpstreamError:
            text = ""
    if not text:
        seite = await fetch_page(url, settings.app)
        text = seite.text
        if not llm.settings.configured:
            if seite.has_coordinates:
                return _answer(
                    InseratFelder(adresse=seite.adresse, lat=seite.lat, lon=seite.lon),
                    url,
                    "meta-tags",
                    titel=seite.titel,
                    beschreibung=seite.beschreibung or seite.text,
                    bilder=seite.bilder,
                )
            raise NotConfiguredError(
                "Das Auslesen von Seiten ist nicht konfiguriert. "
                "Bitte den Seiteninhalt einfügen."
            )

    extracted = await llm.structure(text, InseratFelder, "inserat", _STRUCTURE_TASK)
    deterministic = (
        InseratFelder(adresse=seite.adresse, lat=seite.lat, lon=seite.lon)
        if seite is not None
        else InseratFelder()
    )
    return _answer(
        _merge(deterministic, extracted),
        url,
        "llm",
        titel=seite.titel if seite else None,
        beschreibung=(seite.beschreibung if seite and seite.beschreibung else text),
        bilder=seite.bilder if seite else None,
    )


@router.post("/extract", response_model=ListingExtractResponse, summary="Inserat auslesen")
async def extract(
    payload: ListingExtractRequest,
    llm: LLMClient = Depends(llm_client),
    settings: Settings = Depends(settings_dep),
) -> ListingExtractResponse:
    if payload.url is not None:
        url = str(payload.url)
        cache_key = f"inserat:v{EXTRACTION_VERSION}:{normalize_url(url)}"
        cached = llm.cache.get_json(cache_key)
        if cached is not None:
            return ListingExtractResponse.model_validate(cached)
        answer = await _from_url(url, llm, settings)
        llm.cache.set_json(cache_key, answer.model_dump(mode="json"))
        return answer

    assert payload.text is not None
    # Pasted content is parsed deterministically first, and that is usually the
    # whole job: a page copied out of a browser carries its meta tags, its
    # JSON-LD, its price and its attribute list, and the parcel search reads the
    # prose itself. Requiring a model here was what turned a portal that refuses
    # a server-side fetch -- the very case this field exists for -- into
    # „nicht konfiguriert“.
    seite = parse_page("", payload.text) if "<" in payload.text else None
    text = seite.text if seite and seite.text else payload.text
    deterministic = (
        InseratFelder(
            adresse=seite.adresse,
            lat=seite.lat,
            lon=seite.lon,
            grundstuecksflaeche_m2=_area_from(seite.angaben),
            kaufpreis_eur=seite.kaufpreis_eur,
        )
        if seite is not None
        else InseratFelder()
    )
    beschreibung = (seite.beschreibung if seite and seite.beschreibung else text)

    extracted: InseratFelder | None = None
    hinweis: str | None = None
    if llm.settings.configured:
        try:
            extracted = await llm.structure(text, InseratFelder, "inserat", _STRUCTURE_TASK)
        except UpstreamError as exc:
            hinweis = f"Nur die Angaben der Seite konnten gelesen werden: {exc.message}"
    elif not _has_locator(deterministic):
        raise NotConfiguredError(
            "Aus dem eingefügten Text ließ sich weder eine Adresse noch eine Koordinate "
            "noch ein Flurstück lesen, und das Auswerten durch ein Modell ist auf diesem "
            "Server nicht eingerichtet (LLM_API_KEY fehlt). Am zuverlässigsten ist die "
            "kopierte Seite selbst: im Browser Strg+A, Strg+C — dann kommt das HTML mit "
            "Meta-Angaben, Preis und Bildern mit, und es braucht kein Modell."
        )

    return _answer(
        _merge(deterministic, extracted),
        None,
        "eingefuegter-text",
        hinweis=hinweis,
        beschreibung=beschreibung,
        bilder=seite.bilder if seite else None,
    )
