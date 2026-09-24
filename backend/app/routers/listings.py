"""POST /api/listings/extract -- a listing URL or pasted text becomes an Inserat."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from pydantic import ValidationError

from ..deps import gemarkung_directory, lehrbuch, llm_client, settings_dep
from ..errors import BadRequestError, NotConfiguredError, UpstreamError
from ..schemas import (
    BEFUND_VORLAGE,
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
from ..search.indicia import collect_indicia, price_check, stated_values, district_matches
from ..services import befund as befund_service
from ..services import prompts
from ..services import lehrbuch as lehrbuch_service
from ..services.beleg import Urteil, refusal_note
from ..services.llm import LLMClient, fingerprint, normalize_url
from ..services.portals import (
    Seite,
    blocked_hint,
    fetch_page,
    is_kleinanzeigen,
    parse_page,
)
from ..settings import Settings

router = APIRouter(prefix="/api/listings", tags=["Inserate"])

# A capitalised word, which in German is every noun — the register is what
# decides whether one of them is a place.
_WORDS = re.compile(r"\b[A-ZÄÖÜ][\wäöüßÄÖÜ-]{2,}\b")

# What the model is told lives in `services/prompts.py`: it is content rather
# than plumbing, and it is the one part of this channel that has to know what a
# German property advert looks like.
_FETCH_TASK = prompts.FETCH

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


# A fetched page with nothing to go on. Not „nicht konfiguriert“: that sent
# people looking for a server setting, when what the page lacks is a place --
# and what usually happened is that the server was served less than the
# browser shows, which the bookmarklet gets round.
_NOTHING_SEARCHABLE = (
    "Auf dieser Seite steht weder eine Adresse noch eine Koordinate noch ein "
    "Flurstück, und die Beschreibung nennt keinen Ort, von dem die "
    "Flurstückssuche ausgehen könnte. Zeigt die Anzeige im Browser mehr, hilft "
    "das Lesezeichen unter „Seite einfügen“: ein Klick auf der Anzeigenseite "
    "schickt sie so herüber, wie der Browser sie zeigt."
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
    llm: LLMClient,
    text: str,
    known: InseratFelder,
    start: int = 0,
    quelle_url: str | None = None,
) -> tuple[InseratFelder, list[Indiz], str | None]:
    """One model call, gated: the fields it may fill, the Indizien, the refusals.

    Every value comes back with the sentence it was read from, and every one of
    them is checked against `text` before it is used — which is why this is the
    only place the model's answer is ever unpacked.

    And every disagreement between the two readers is written down on the way
    past. A model here is a teacher whose answer is never trusted: where it
    reads something the patterns did not, that is the pattern that is missing,
    with the sentence it is missing on — and the gate has already proved the
    sentence stands in the page. See `services/lehrbuch.py`.
    """

    befund = await llm.structure(
        text=prompts.user_message(text, _known_districts(text)),
        model=InseratBefund,
        name="inserat-befund",
        auftrag="",
        system=prompts.SYSTEM,
    )
    fields, field_verdicts = befund_service.fields_from(befund, text, known)
    indicia, indiz_verdicts = befund_service.indicia_from(befund, text, start)
    verdicts = [*field_verdicts, *indiz_verdicts]
    await _note_divergences(text, known, indicia, verdicts, llm, quelle_url)
    return fields, indicia, refusal_note(verdicts)


async def _note_divergences(
    text: str,
    known: InseratFelder,
    indicia: list[Indiz],
    verdicts: list[Urteil],
    llm: LLMClient,
    quelle_url: str | None,
) -> None:
    """File what the two readers disagreed about. Never fails the request.

    The comparison is fair because both sides read the *same* text: the
    deterministic side is asked here, with the reader the search itself uses,
    rather than taken from whatever a portal's attribute list happened to
    carry.
    """

    patterns = [
        (indiz.art, indiz.wert)
        for indiz in collect_indicia(text=text, directory=gemarkung_directory())
    ]
    patterns += [
        ("adresse", known.adresse),
        ("kaufpreis_eur", _as_text(known.kaufpreis_eur)),
        ("grundstuecksflaeche_m2", _as_text(known.grundstuecksflaeche_m2)),
    ]
    accepted = [(indiz.art, indiz.wert, indiz.beleg) for indiz in indicia]
    accepted += [
        (verdict.feld, _as_text(verdict.wert), verdict.beleg)
        for verdict in verdicts
        if verdict.angenommen and ":" not in verdict.feld
    ]
    refused = [
        (verdict.feld.split(":")[0], _as_text(verdict.wert), verdict.beleg, verdict.grund)
        for verdict in verdicts
        if verdict.verworfen and verdict.wert is not None
    ]
    await lehrbuch().record(
        lehrbuch_service.compare(
            deterministic=patterns,
            accepted=accepted,
            refused=refused,
            text_hash=lehrbuch_service.fingerprint(text),
            quelle_url=quelle_url,
            modell_id=llm.settings.model,
            vorlage=BEFUND_VORLAGE,
        )
    )


def _known_districts(text: str) -> list[str]:
    """The names in this text that the Saxon district register actually carries.

    Reference material, not an answer: which of them the advert means, and on
    which level, is precisely what the model is being asked. A closed list of
    names that exist is worth sending — it is data about Saxony — and it costs
    one pass over a file that is already in memory.

    What is *not* sent is anything our own readers concluded. Handing the model
    our findings would make it agree with us, and the divergence log in
    `services/lehrbuch.py` would then measure nothing at all. This function
    therefore reads the register, never `collect_indicia`.
    """

    directory = gemarkung_directory()
    if directory is None:
        return []
    found: list[str] = []
    for word in dict.fromkeys(_WORDS.findall(text)):
        if district_matches(directory, word):
            found.append(word)
        if len(found) >= prompts.MAX_DISTRICT_HINTS:
            break
    return found


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    return f"{value:g}" if isinstance(value, float) else str(value)


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
    stated = stated_values(text)
    mismatch = price_check(stated, felder.kaufpreis_eur, felder.grundstuecksflaeche_m2)
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
        hinweis=" ".join(part for part in (hinweis or titel, mismatch) if part) or None,
        beschreibung=text[:_DESCRIPTION_LIMIT] or None,
        bilder=bilder or [],
        indizien=indizien or [],
        angaben=stated,
    )


def _read_off(seite: Seite) -> InseratFelder:
    """What the page states in markup, before anybody reads its prose."""

    return InseratFelder(
        adresse=seite.adresse,
        lat=seite.lat,
        lon=seite.lon,
        grundstuecksflaeche_m2=_area_from(seite.angaben),
        kaufpreis_eur=seite.kaufpreis_eur,
    )


def _without_a_model(seite: Seite, felder: InseratFelder, url: str) -> ListingExtractResponse:
    """A fetched page, read by our own parsers alone.

    The same test the paste path makes: the search needs a place to start
    from, not a coordinate. A portal's coordinate is the municipality's at
    best, and requiring one refused as a link exactly the page that went
    through when it was pasted.
    """

    # The description, not the whole page: without this the search reads a
    # portal's navigation and cookie banner as evidence.
    beschreibung = seite.beschreibung or seite.text
    prose = " ".join(part for part in (seite.titel, beschreibung) if part)
    if not _has_locator(felder) and not _is_searchable(prose):
        raise NotConfiguredError(_NOTHING_SEARCHABLE)
    return _answer(
        felder,
        url,
        "meta-tags" if seite.has_coordinates else "abgerufene-seite",
        titel=seite.titel,
        beschreibung=beschreibung,
        bilder=seite.bilder,
    )


async def _from_url(url: str, llm: LLMClient, settings: Settings) -> ListingExtractResponse:
    hint = blocked_hint(url)
    if hint:
        # No request goes out at all, not even the model's fetch -- the
        # portal's answer is known.
        raise BadRequestError(hint)

    if is_kleinanzeigen(url):
        seite = await fetch_page(url, settings.app)
        deterministic = _read_off(seite)
        if not llm.settings.configured:
            return _without_a_model(seite, deterministic, url)
        weg: Extraktionsweg = "meta-tags" if seite.has_coordinates else "llm"
        hinweis = None
        extracted: InseratFelder | None = None
        indizien: list[Indiz] = []
        if seite.text:
            try:
                extracted, indizien, hinweis = await _ask_the_model(
                    llm, seite.text, deterministic, quelle_url=url
                )
            except UpstreamError as exc:
                if not seite.has_coordinates:
                    raise
                hinweis = f"Nur die Meta-Angaben der Seite konnten gelesen werden: {exc.message}"
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
            return _without_a_model(seite, _read_off(seite), url)

    deterministic = (
        InseratFelder(adresse=seite.adresse, lat=seite.lat, lon=seite.lon)
        if seite is not None
        else InseratFelder()
    )
    extracted, indizien, hinweis = await _ask_the_model(
        llm, text, deterministic, quelle_url=url
    )
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
        # answer, and this cache has no expiry. So does its absence -- a page
        # read without one must not outlive the key being set.
        reader = fingerprint(llm.settings.model) if llm.settings.configured else "ohne-modell"
        cache_key = f"inserat:v{EXTRACTION_VERSION}:{reader}:{normalize_url(url)}"
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
