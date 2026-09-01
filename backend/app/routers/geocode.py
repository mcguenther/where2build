"""POST /api/geocode -- free text to coordinates, with the labels that were matched.

Destinations are entered as text ("Arbeit: Bahnhof Wurzen") but routing needs
coordinates. This is the step between the two. It deliberately answers with a
list rather than one coordinate: a geocoder is imprecise -- a Saxon street name
can come back as a village in Bavaria -- and a silent guess would put an
invented location on the map, which is exactly what this project does not do.

Two sources, in this order:

1. the **official Hauskoordinaten** of the GeoSN, when the server holds them
   (``app/address_index.py``). A house number there is the coordinate the
   cadastre recorded, not a point interpolated along a street.
2. **MOTIS**, for everything the first cannot answer: stops, places, addresses
   outside Saxony, and anything spelled too far from the official name.

The second is still asked when the first answered, because "Bahnhof Wurzen" and
"Bahnhofstraße 3" are both plausible readings of what someone typed and the
list is the user's to choose from. It is only *required* when the first found
nothing -- an official address must not stop working because a volunteer
routing service is down.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from ..address_index import AddressHit, AddressIndex
from ..deps import address_index, motis_service
from ..errors import NotFoundError, UpstreamError, UpstreamTimeout
from ..schemas import (
    GEOCODE_HINWEIS,
    GEOCODE_HINWEIS_AMTLICH,
    GEOCODE_QUELLE,
    GEOCODE_QUELLE_AMTLICH,
    GeocodeRequest,
    GeocodeResponse,
    GeocodeTreffer,
    Koordinate,
)
from ..services.motis import MAX_GEOCODE_RESULTS, MotisService
from ..settings import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Erreichbarkeit"])

NOT_FOUND = (
    "Zu „{text}“ wurde keine Koordinate gefunden. Bitte Postleitzahl und Ort "
    "ergänzen, die Schreibweise prüfen — oder den Punkt direkt auf der Karte setzen."
)


def _as_treffer(hit: AddressHit) -> GeocodeTreffer:
    return GeocodeTreffer(
        lat=hit.lat,
        lon=hit.lon,
        name=hit.name,
        beschreibung=hit.beschreibung,
        # "adresse" for a house the cadastre placed, "ort" for a whole street:
        # the street's coordinate is one of its addresses, not the building
        # somebody meant, and must not be labelled as one.
        art="adresse" if hit.hnr else "ort",
    )


@router.post("/geocode", response_model=GeocodeResponse, summary="Adresse zu Koordinaten")
async def geocode(
    payload: GeocodeRequest,
    motis: MotisService = Depends(motis_service),
    addresses: AddressIndex | None = Depends(address_index),
    settings: Settings = Depends(get_settings),
) -> GeocodeResponse:
    bias = (
        Koordinate(lat=payload.lat, lon=payload.lon)
        if payload.lat is not None and payload.lon is not None
        else None
    )

    amtlich: list[GeocodeTreffer] = []
    if addresses is not None:
        amtlich = [
            _as_treffer(hit)
            for hit in addresses.search(
                payload.text,
                bias=(bias.lat, bias.lon) if bias is not None else None,
                limit=settings.addresses.max_candidates,
            )
        ]

    try:
        aus_motis = await motis.geocode_candidates(payload.text, bias)
    except (UpstreamError, UpstreamTimeout):
        # An official address is answerable without Transitous, and saying so
        # is better than handing the user an error next to a coordinate the
        # server already holds. With nothing official, the error is the answer.
        if not amtlich:
            raise
        logger.warning("Geocoder unreachable; answering from the official addresses alone.")
        aus_motis = []

    # Same coordinate from both sources is one place found twice. Rounded to
    # about a metre, because the two datasets place the same house a little
    # differently and an exact comparison would never fire.
    seen = {(round(hit.lat, 5), round(hit.lon, 5)) for hit in amtlich}
    treffer = amtlich + [
        hit for hit in aus_motis if (round(hit.lat, 5), round(hit.lon, 5)) not in seen
    ]
    if not treffer:
        raise NotFoundError(NOT_FOUND.format(text=payload.text.strip()))

    if amtlich:
        stand = f" (Stand {addresses.stand})" if addresses and addresses.stand else ""
        quelle = GEOCODE_QUELLE_AMTLICH
        if len(treffer) > len(amtlich):
            quelle = f"{quelle} und {GEOCODE_QUELLE}"
        return GeocodeResponse(
            treffer=treffer[:MAX_GEOCODE_RESULTS],
            hinweis=GEOCODE_HINWEIS_AMTLICH.format(stand=stand),
            quelle=quelle,
        )
    return GeocodeResponse(treffer=treffer[:MAX_GEOCODE_RESULTS], hinweis=GEOCODE_HINWEIS)
