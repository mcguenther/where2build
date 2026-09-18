"""POST /api/listings/extract -- a listing URL or pasted text becomes an Inserat."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from pydantic import ValidationError

from ..deps import gemarkung_directory, llm_client, settings_dep
from ..errors import BadRequestError, NotConfiguredError, UpstreamError
from ..schemas import (
    Extraktionsweg,
    Indiz,
    Inserat,
    InseratBefund,
    InseratFelder,
    InseratVorschlaege,
    ListingExtractRequest,
    ListingExtractResponse,
    as_vorschlaege,
)
from ..search.indicia import collect_indicia
from ..services import befund as befund_service
from ..services.beleg import refusal_note
from ..services.llm import LLMClient, fingerprint, normalize_url
from ..services.portals import PASTE_HINT, fetch_page, is_blocked, is_kleinanzeigen, parse_page
from ..settings import Settings

router = APIRouter(prefix="/api/listings", tags=["Inserate"])

_FETCH_TASK = (
    "Es geht um ein Grundstücksinserat: Adresse, Flurstücksnummern, Kaufpreis "
    "und Grundstücksfläche."
)
# What the model is asked for, and the rule it is asked under. The rule is not
# enforced here -- `services.beleg` enforces it, and it does so by comparing
# strings rather than by trusting this paragraph. Saying it anyway costs
# nothing and makes the refusals rarer.
_STRUCTURE_TASK = (
    "Lies aus dem folgenden Text eines Grundstücksinserats aus, was darin steht: "
    "Adresse, Kaufpreis in Euro, Grundstücksfläche in Quadratmetern, die genannten "
    "Orte mit ihrer Ebene (Gemarkung, Ortsteil, Gemeinde, Straße) und ihrer "
    "Beziehung zum Grundstück (liegt_in, liegt_an, entfernt_von, erwaehnt) sowie "
    "Flurstückskennungen (etwa „Flurstück 790 sowie 706“).\n\n"
    "Zu jedem Wert gehört ein Beleg: der Satz oder Satzteil aus dem Text, in dem "
    "der Wert wörtlich steht. Der Beleg wird gegen den Text geprüft und muss "
    "deshalb Zeichen für Zeichen aus ihm stammen — nicht umformuliert, nicht "
    "zusammengefasst, nicht gekürzt um die Zahl herum.\n\n"
    "Rechne nichts aus. Ein Kaufpreis, der sich aus Fläche mal Preis pro "
    "Quadratmeter ergibt, steht nicht im Inserat und wird nicht eingetragen. "
    "Ohne Beleg bleibt das Feld null. Namen, Telefonnummern und andere "
    "Kontaktdaten werden nicht erfasst."
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
#   3  the model answers a Befund with a Beleg per value, and what passes the
#      gate arrives as Indizien beside the fields
EXTRACTION_VERSION = 3

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


async def _ask_the_model(
    llm: LLMClient, text: str, known: InseratFelder, start: int = 0
) -> tuple[InseratFelder, list[Indiz], str | None]:
    """One model call, gated: the fields it may fill, the Indizien, the refusals.

    Every value comes back with the sentence it was read from, and every one of
    them is checked against `text` before it is used — which is why this is the
    only place the model's answer is ever unpacked.
    """

    befund = await llm.structure(text, InseratBefund, "inserat-befund", _STRUCTURE_TASK)
    fields, field_verdicts = befund_service.fields_from(befund, text, known)
    indicia, indiz_verdicts = befund_service.indicia_from(befund, text, start)
    return fields, indicia, refusal_note([*field_verdicts, *indiz_verdicts])


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


# What the search can actually start from. A district, a municipality or a
# named place anchors it; a bare parcel number is probed against the whole
# state. An *area* alone is not an anchor -- „Baugrundstück 688 m²“ names
# nowhere, and every parcel in Saxony of that size is not a candidate set. Nor
# is a street: without a containing area a street name is a 1-in-500 shot.
_ANCHORS = ("gemarkung", "gemeinde", "ort", "flurstueck")


def _is_searchable(text: str) -> bool:
    """Whether the parcel search could do anything with this prose.

    Not a length test. The search reads a district, a street, an area and the
    relation between the places named out of the text — a page with none of the
    three locators is perfectly usable if it carries any of those, which is
    exactly what the „Text durchsuchen“ way in relies on. Asked with the same
    reader the search itself uses, so the answer cannot drift away from it.

    An ImmoScout page is the case: no coordinate, often only a district for an
    address, never a parcel number, and prose that names the Ortsteil.
    """

    if not text or not text.strip():
        return False
    return any(
        indiz.art in _ANCHORS
        for indiz in collect_indicia(text=text, directory=gemarkung_directory())
    )


def _answer(
    felder: InseratFelder,
    quelle_url: str | None,
    weg: Extraktionsweg,
    hinweis: str | None = None,
    titel: str | None = None,
    beschreibung: str | None = None,
    bilder: list[str] | None = None,
    indizien: list[Indiz] | None = None,
) -> ListingExtractResponse:
    text = " ".join(part for part in (titel, beschreibung) if part).strip()
    try:
        inserat = Inserat(**felder.model_dump(), quelle_url=quelle_url)
    except ValidationError as exc:
        # A locator is what a *stored plot* needs, not what the search needs.
        # An ImmoScout page carries no coordinate, often only a district as its
        # address and never a parcel number -- and its prose names the Ortsteil,
        # the area and the street, which is everything the search runs on.
        if not _is_searchable(text):
            raise BadRequestError(_NO_LOCATOR) from exc
        inserat = None
    return ListingExtractResponse(
        felder=as_vorschlaege(inserat or felder, InseratVorschlaege, quelle_url),
        quelle_url=quelle_url,
        weg=weg,
        hinweis=hinweis or titel,
        beschreibung=text[:_DESCRIPTION_LIMIT] or None,
        bilder=bilder or [],
        indizien=indizien or [],
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
        indizien: list[Indiz] = []
        if llm.settings.configured and seite.text:
            try:
                extracted, indizien, hinweis = await _ask_the_model(
                    llm, seite.text, deterministic
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
            indizien,
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

    deterministic = (
        InseratFelder(adresse=seite.adresse, lat=seite.lat, lon=seite.lon)
        if seite is not None
        else InseratFelder()
    )
    extracted, indizien, hinweis = await _ask_the_model(llm, text, deterministic)
    return _answer(
        _merge(deterministic, extracted),
        url,
        "llm",
        hinweis,
        titel=seite.titel if seite else None,
        beschreibung=(seite.beschreibung if seite and seite.beschreibung else text),
        bilder=seite.bilder if seite else None,
        indizien=indizien,
    )


@router.post("/extract", response_model=ListingExtractResponse, summary="Inserat auslesen")
async def extract(
    payload: ListingExtractRequest,
    llm: LLMClient = Depends(llm_client),
    settings: Settings = Depends(settings_dep),
) -> ListingExtractResponse:
    if payload.url is not None:
        url = str(payload.url)
        # The model rides in the key too: a different one gives a different
        # answer, and this cache has no expiry.
        cache_key = (
            f"inserat:v{EXTRACTION_VERSION}:{fingerprint(llm.settings.model)}"
            f":{normalize_url(url)}"
        )
        cached = llm.cache.get_json(cache_key)
        if cached is not None:
            return ListingExtractResponse.model_validate(cached)
        answer = await _from_url(url, llm, settings)
        llm.cache.set_json(cache_key, answer.model_dump(mode="json"))
        return answer

    assert payload.text is not None
    # Pasted or handed-over content is parsed deterministically first, and that
    # is usually the whole job. How much of it there is depends on how it got
    # here: a document from the bookmarklet is complete, meta tags and JSON-LD
    # included, while a clipboard copy is the body alone -- price, attribute
    # list, images and prose, but nothing from `<head>`. Both go through the
    # same parsers, which is the point. Requiring a model here was what turned a
    # portal that refuses a server-side fetch -- the very case this way in
    # exists for -- into „nicht konfiguriert“.
    #
    # Unconditionally, markup or not. This used to run only when the text
    # contained a „<“, which was true of the parsers when it was written and is
    # not true of them now: the reader in `portal_fields` goes by the German
    # word and the value's unit, so it reads a *rendered* listing as well as a
    # marked-up one. The gate therefore answered every field empty for the
    # plainest paste there is -- „Grundstücksfläche ca. 866 m²“ and „199.000 €“
    # standing in the text, and „Gelesene Werte“ showing nothing.
    seite = parse_page("", payload.text)
    text = seite.text or payload.text
    deterministic = InseratFelder(
        adresse=seite.adresse,
        lat=seite.lat,
        lon=seite.lon,
        grundstuecksflaeche_m2=_area_from(seite.angaben),
        kaufpreis_eur=seite.kaufpreis_eur,
    )
    beschreibung = seite.beschreibung or text

    extracted: InseratFelder | None = None
    hinweis: str | None = None
    indizien: list[Indiz] = []
    if llm.settings.configured:
        try:
            extracted, indizien, hinweis = await _ask_the_model(llm, text, deterministic)
        except UpstreamError as exc:
            hinweis = f"Nur die Angaben der Seite konnten gelesen werden: {exc.message}"
    elif not _has_locator(deterministic) and not _is_searchable(beschreibung):
        raise NotConfiguredError(
            "Aus dem eingefügten Text ließ sich weder eine Adresse noch eine Koordinate "
            "noch ein Flurstück lesen, und es steht auch kein Beschreibungstext darin, "
            "den die Flurstückssuche lesen könnte. Ein Modell ist auf diesem Server "
            "nicht eingerichtet (LLM_API_KEY fehlt). Am zuverlässigsten ist das "
            "Lesezeichen unter „Seite einfügen“: es schickt die Anzeigenseite "
            "vollständig herüber, mit Meta-Angaben und Koordinate. Beim Kopieren mit "
            "Strg+A, Strg+C kommt nur der Rumpf der Seite mit — Preis, Fläche und "
            "Bilder also, aber keine Meta-Angaben."
        )

    return _answer(
        _merge(deterministic, extracted),
        None,
        "eingefuegter-text",
        hinweis=hinweis,
        beschreibung=beschreibung,
        bilder=seite.bilder,
        titel=seite.titel,
        indizien=indizien,
    )
