"""POST /api/reachability -- travel time and route geometry per destination and mode."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import motis_service
from ..schemas import ReachabilityRequest, ReachabilityResponse
from ..services.motis import MotisService

router = APIRouter(prefix="/api", tags=["Erreichbarkeit"])


@router.post("/reachability", response_model=ReachabilityResponse, summary="Wege durchrechnen")
async def reachability(
    payload: ReachabilityRequest,
    motis: MotisService = Depends(motis_service),
) -> ReachabilityResponse:
    return await motis.reachability(
        payload.origin, payload.destinations, payload.modes, payload.time
    )
