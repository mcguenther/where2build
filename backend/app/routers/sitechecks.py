"""POST /api/site-checks -- the environmental record of one parcel.

A POST because the question is a parcel outline, which does not belong in a
URL, and because the answer is not a document a browser should cache -- the
disk cache behind the services is the one that matters.

The endpoint asks two authorities at once: the Saxon environmental server for
noise, water, nature, flood, radon, slope and ground, and the UBA for the air.
Neither can sink the other, and inside the first each check fails on its own:
what a service does not answer comes back as a `fehler` on that block, and the
interface shows an open check rather than a green one.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from ..deps import air_quality_service, luis_service
from ..schemas import StandortPruefungen, StandortRequest
from ..services.airquality import AirQualityService
from ..services.luis import LuisService

router = APIRouter(prefix="/api", tags=["Standort"])


@router.post("/site-checks", response_model=StandortPruefungen, summary="Standort prüfen")
async def site_checks(
    payload: StandortRequest,
    luis: LuisService = Depends(luis_service),
    air: AirQualityService = Depends(air_quality_service),
) -> StandortPruefungen:
    # The air is measured at a station, so that one check does take a point --
    # the mean of the outline, which is inside the plot for any ordinary shape
    # and is only used to rank stations kilometres away.
    lon = sum(point[0] for point in payload.ring) / len(payload.ring)
    lat = sum(point[1] for point in payload.ring) / len(payload.ring)

    blocks, luftqualitaet = await asyncio.gather(
        luis.site_checks(payload.ring), air.at(lat, lon)
    )
    return StandortPruefungen(
        **blocks,
        luftqualitaet=luftqualitaet,
        abgerufen_am=datetime.now(timezone.utc),
    )
