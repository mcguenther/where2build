"""GET /api/landvalue -- the land reference value at a coordinate."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..deps import boris_service
from ..schemas import LandValue
from ..services.boris import BorisService

router = APIRouter(prefix="/api", tags=["Bodenrichtwert"])


@router.get("/landvalue", response_model=LandValue, summary="Bodenrichtwert abfragen")
async def land_value(
    lat: float = Query(ge=-90, le=90, description="Breitengrad (WGS84)"),
    lon: float = Query(ge=-180, le=180, description="Längengrad (WGS84)"),
    boris: BorisService = Depends(boris_service),
) -> LandValue:
    return await boris.land_value(lat, lon)
