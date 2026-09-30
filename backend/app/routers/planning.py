"""POST /api/planning -- the Bauleitplanung RAPIS Sachsen knows for a plot.

A POST for the same reason as ``/api/site-checks``: the question is an
outline, which does not belong in a URL, and the body is the same one.

The answer is a set of yes/no statements per layer, and the sentence under the
check is composed in the browser (``frontend/src/lib/findings.js``). What this
route guarantees is that an empty list is an answer: it either heard back from
every layer or it fails as a whole.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import rapis_service
from ..schemas import PlanungRequest, PlanungResponse
from ..services.rapis import RapisService

router = APIRouter(prefix="/api", tags=["Standort"])


@router.post("/planning", response_model=PlanungResponse, summary="Bauleitplanung")
async def planning(
    payload: PlanungRequest,
    rapis: RapisService = Depends(rapis_service),
) -> PlanungResponse:
    return await rapis.planning(payload.ring)
