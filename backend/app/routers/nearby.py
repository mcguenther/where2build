"""POST /api/nearby -- "wie weit ist die nächste Schule, der nächste Park, die
nächste Straßenbahnhaltestelle".

One coordinate in, one list of hits per category out, each with the walking
time that decided its position. Deliberately not a GET: the category list makes
the request a body, and the answer is not a document a browser should cache.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import nearby_service
from ..schemas import NearbyRequest, NearbyResponse
from ..services.nearby import NearbyService

router = APIRouter(prefix="/api", tags=["Umgebung"])


@router.post("/nearby", response_model=NearbyResponse, summary="Was ist in der Nähe?")
async def nearby(
    payload: NearbyRequest,
    service: NearbyService = Depends(nearby_service),
) -> NearbyResponse:
    return await service.nearby(payload)
