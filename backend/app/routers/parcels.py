"""POST /api/parcels/resolve -- address, coordinate or cadastral identifier to parcels."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import alkis_service, motis_service
from ..errors import NotFoundError
from ..schemas import ParcelCollection, ParcelResolveRequest
from ..services.alkis import AlkisService, to_collection
from ..services.motis import MotisService

router = APIRouter(prefix="/api/parcels", tags=["Flurstücke"])

GEOCODING_HINT = (
    "Die Adresse wurde über den Routing-Geocoder aufgelöst. Verbindlich sind die "
    "amtlichen Hauskoordinaten des GeoSN; bitte die Lage auf der Karte prüfen."
)


@router.post("/resolve", response_model=ParcelCollection, summary="Flurstücke auflösen")
async def resolve(
    payload: ParcelResolveRequest,
    alkis: AlkisService = Depends(alkis_service),
    motis: MotisService = Depends(motis_service),
) -> ParcelCollection:
    hinweis: str | None = None

    if payload.gemarkung and payload.zaehler is not None:
        parcels = await alkis.by_gemarkung(payload.gemarkung, payload.zaehler, payload.nenner)
    elif payload.lat is not None and payload.lon is not None:
        parcels = await alkis.by_point(payload.lat, payload.lon)
    else:
        assert payload.address is not None
        coordinate = await motis.geocode(payload.address)
        if coordinate is None:
            raise NotFoundError("Zu dieser Adresse wurde keine Koordinate gefunden.")
        parcels = await alkis.by_point(coordinate.lat, coordinate.lon)
        hinweis = GEOCODING_HINT

    return to_collection(parcels, hinweis=hinweis)
