"""POST /api/listings/extract -- a listing URL or pasted text becomes an Inserat."""

from __future__ import annotations

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

_NO_LOCATOR = (
    "Aus dieser Seite ließ sich weder eine Adresse noch eine Koordinate noch ein "
    "Flurstück lesen. Bitte den Seiteninhalt einfügen oder die Angaben von Hand eintragen."
)


def _merge(deterministic: InseratFelder, extracted: InseratFelder | None) -> InseratFelder:
    """Deterministic values win; the model only fills the gaps."""

    if extracted is None:
        return deterministic
    merged = deterministic.model_dump()
    for name, value in extracted.model_dump().items():
        if merged.get(name) in (None, "", []):
            merged[name] = value
    return InseratFelder.model_validate(merged)


def _answer(
    felder: InseratFelder,
    quelle_url: str | None,
    weg: Extraktionsweg,
    hinweis: str | None = None,
    titel: str | None = None,
) -> ListingExtractResponse:
    try:
        inserat = Inserat(**felder.model_dump(), quelle_url=quelle_url)
    except ValidationError as exc:
        raise BadRequestError(_NO_LOCATOR) from exc
    return ListingExtractResponse(
        felder=as_vorschlaege(inserat, InseratVorschlaege, quelle_url),
        quelle_url=quelle_url,
        weg=weg,
        hinweis=hinweis or titel,
    )


async def _from_url(url: str, llm: LLMClient, settings: Settings) -> ListingExtractResponse:
    if is_blocked(url):
        # No request goes out at all -- the answer is known to be 401.
        raise BadRequestError(PASTE_HINT)

    if is_kleinanzeigen(url):
        seite = await fetch_page(url, settings.app)
        deterministic = InseratFelder(adresse=seite.adresse, lat=seite.lat, lon=seite.lon)
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
        return _answer(_merge(deterministic, extracted), url, weg, hinweis, seite.titel)

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
    return _answer(_merge(deterministic, extracted), url, "llm", titel=seite.titel if seite else None)


@router.post("/extract", response_model=ListingExtractResponse, summary="Inserat auslesen")
async def extract(
    payload: ListingExtractRequest,
    llm: LLMClient = Depends(llm_client),
    settings: Settings = Depends(settings_dep),
) -> ListingExtractResponse:
    if payload.url is not None:
        url = str(payload.url)
        cache_key = f"inserat:{normalize_url(url)}"
        cached = llm.cache.get_json(cache_key)
        if cached is not None:
            return ListingExtractResponse.model_validate(cached)
        answer = await _from_url(url, llm, settings)
        llm.cache.set_json(cache_key, answer.model_dump(mode="json"))
        return answer

    assert payload.text is not None
    if not llm.settings.configured:
        raise NotConfiguredError(
            "Das Auswerten eingefügter Texte ist nicht konfiguriert (LLM_API_KEY fehlt)."
        )
    # Pasted HTML still carries meta tags and JSON-LD; use them before the model.
    seite = parse_page("", payload.text) if "<" in payload.text else None
    text = seite.text if seite and seite.text else payload.text
    extracted = await llm.structure(text, InseratFelder, "inserat", _STRUCTURE_TASK)
    deterministic = (
        InseratFelder(adresse=seite.adresse, lat=seite.lat, lon=seite.lon)
        if seite is not None
        else InseratFelder()
    )
    return _answer(_merge(deterministic, extracted), None, "eingefuegter-text")
