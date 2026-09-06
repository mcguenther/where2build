"""POST /api/neighbours -- the building outlines around a plot.

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

from ..deps import alkis_service, overpass_service
from ..errors import AppError
from ..schemas import NACHBARN_HINWEIS_KATASTER, NachbarnRequest, NachbarnResponse
from ..services.alkis import SERVICE_NAME as ALKIS_NAME
from ..services.alkis import AlkisService
from ..services.overpass import OverpassService

router = APIRouter(prefix="/api", tags=["Umgebung"])

ALKIS_SOURCE = "ALKIS (ave:GebaeudeBauwerk), GeoSN — dl-de/by-2-0"


@router.post("/neighbours", response_model=NachbarnResponse, summary="Nachbargebäude")
async def neighbours(
    payload: NachbarnRequest,
    alkis: AlkisService = Depends(alkis_service),
    overpass: OverpassService = Depends(overpass_service),
) -> NachbarnResponse:
    """The outlines around a plot, from the cadastre.

    The register that delivers the parcel delivers the buildings too, on the
    same WFS: no OpenStreetMap source, no Overpass instance, no key. Overpass
    stays as the fallback for whoever has one configured -- it maps garden
    sheds the cadastre leaves out, and it is the only way to get storeys at all.
    """

    try:
        buildings = await alkis.buildings_around(
            payload.origin.lat, payload.origin.lon, payload.umkreis_m
        )
        return NachbarnResponse(
            gebaeude=buildings, quelle=ALKIS_SOURCE, hinweis=NACHBARN_HINWEIS_KATASTER
        )
    except AppError:
        if not overpass.enabled:
            raise
        answer = await overpass.buildings(payload.origin, payload.umkreis_m)
        return NachbarnResponse(**answer)
