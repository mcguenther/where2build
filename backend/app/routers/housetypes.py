"""POST /api/housetypes/extract -- a manufacturer link becomes a Haustyp."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import llm_client
from ..schemas import (
    Haustyp,
    HaustypFelder,
    HaustypVorschlaege,
    HousetypeExtractRequest,
    HousetypeExtractResponse,
    as_vorschlaege,
)
from ..services.llm import LLMClient, normalize_url

router = APIRouter(prefix="/api/housetypes", tags=["Haustypen"])

_FETCH_TASK = (
    "Es geht um einen Fertighaus-Typ: bebaute Fläche (Grundfläche), Wohnflächen "
    "je Geschoss, Außenmaße, Dachform, Trauf- und Firsthöhe sowie Preise."
)
_STRUCTURE_TASK = (
    "Lies aus dem folgenden Text einer Fertighaus-Herstellerseite die Angaben zum "
    "Haustyp aus. Wichtig: „bebaute_flaeche_m2“ ist die Grundfläche des Baukörpers, "
    "NICHT die Wohnfläche über alle Geschosse — beim ELK All in One 159 sind das "
    "96,88 m² bebaute Fläche gegenüber 159,21 m² Wohnfläche. Trage nur ein, was im "
    "Text tatsächlich steht, sonst null."
)

_ESTIMATE_HINT = (
    "Außenmaße wurden aus der bebauten Fläche mit Seitenverhältnis 1,35 geschätzt "
    "und sind im Frontend korrigierbar."
)


@router.post("/extract", response_model=HousetypeExtractResponse, summary="Haustyp auslesen")
async def extract(
    payload: HousetypeExtractRequest,
    llm: LLMClient = Depends(llm_client),
) -> HousetypeExtractResponse:
    url = str(payload.url)
    # Permanent cache per normalised URL: a house type does not change weekly.
    cache_key = f"haustyp:{normalize_url(url)}"
    cached = llm.cache.get_json(cache_key)
    if cached is not None:
        return HousetypeExtractResponse.model_validate(cached)

    # web_fetch is restricted to the manufacturer's own domain (see LLMClient).
    text = await llm.fetch_page_text(url, _FETCH_TASK)
    felder = await llm.structure(text, HaustypFelder, "haustyp", _STRUCTURE_TASK)
    haustyp = Haustyp(**felder.model_dump(), quelle_url=url)
    laenge, breite = haustyp.abgeleitete_masse()
    geschaetzt = not (haustyp.aussenmass_laenge_m and haustyp.aussenmass_breite_m)

    answer = HousetypeExtractResponse(
        felder=as_vorschlaege(haustyp, HaustypVorschlaege, url),
        quelle_url=url,
        gelesen_am=haustyp.gelesen_am,
        abgeleitete_laenge_m=laenge,
        abgeleitete_breite_m=breite,
        weg="llm",
        hinweis=_ESTIMATE_HINT if geschaetzt else None,
    )
    llm.cache.set_json(cache_key, answer.model_dump(mode="json"))
    return answer
