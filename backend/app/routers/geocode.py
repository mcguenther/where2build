"""POST /api/geocode -- free text to coordinates, with the labels that were matched.

Destinations are entered as text ("Arbeit: Bahnhof Wurzen") but routing needs
coordinates. This is the step between the two. It deliberately answers with a
list rather than one coordinate: the routing geocoder is imprecise -- a Saxon
street name can come back as a village in Bavaria -- and a silent guess would
put an invented location on the map, which is exactly what this project does
not do.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import motis_service
from ..errors import NotFoundError
from ..schemas import GeocodeRequest, GeocodeResponse, Koordinate
from ..services.motis import MotisService

router = APIRouter(prefix="/api", tags=["Erreichbarkeit"])

NOT_FOUND = (
    "Zu „{text}“ wurde keine Koordinate gefunden. Bitte Postleitzahl und Ort "
    "ergänzen, die Schreibweise prüfen — oder den Punkt direkt auf der Karte setzen."
)


@router.post("/geocode", response_model=GeocodeResponse, summary="Adresse zu Koordinaten")
async def geocode(
    payload: GeocodeRequest,
    motis: MotisService = Depends(motis_service),
) -> GeocodeResponse:
    bias = (
        Koordinate(lat=payload.lat, lon=payload.lon)
        if payload.lat is not None and payload.lon is not None
        else None
    )
    treffer = await motis.geocode_candidates(payload.text, bias)
    if not treffer:
        raise NotFoundError(NOT_FOUND.format(text=payload.text.strip()))
    return GeocodeResponse(treffer=treffer)
