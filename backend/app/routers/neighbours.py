"""POST /api/neighbours -- the mapped building outlines around a plot.

They are drawn as a hint, not as a finding: § 6 SächsBO puts each building's
setback area on its own plot, so a neighbour standing close to the boundary does
not enlarge ours. What the outlines are good for is showing where the two setback
areas would overlap -- the strip where the buildings end up closer than the
3 + 3 m the statute produces in its minimal case. See
docs/research/abstandsflaechen-nachbargebaeude.md.

A POST because the answer is not a document a browser should cache, and because
the origin belongs in a body rather than in a URL.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import overpass_service
from ..errors import UpstreamError
from ..schemas import NachbarnRequest, NachbarnResponse
from ..services.overpass import OverpassService

router = APIRouter(prefix="/api", tags=["Umgebung"])


@router.post("/neighbours", response_model=NachbarnResponse, summary="Nachbargebäude")
async def neighbours(
    payload: NachbarnRequest,
    service: OverpassService = Depends(overpass_service),
) -> NachbarnResponse:
    if not service.enabled:
        raise UpstreamError(
            "Für die Nachbargebäude ist keine OpenStreetMap-Quelle eingerichtet. "
            "Sie lässt sich mit OVERPASS_ENABLED und OVERPASS_URL einschalten."
        )
    answer = await service.buildings(payload.origin, payload.umkreis_m)
    return NachbarnResponse(**answer)
