"""GET /api/tiles/{layer}/{z}/{x}/{y}.png -- cached proxy in front of the GeoSN WMS.

POST /api/tiles/warm puts tiles into that cache before anyone draws them.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Request, Response

from ..deps import oidc_service, spend_map_tiles, tile_service
from ..schemas import KachelnVorwaermen, VorwaermenErgebnis
from ..services.oidc import OidcService
from ..services.tiles import TileService

router = APIRouter(prefix="/api/tiles", tags=["Karten"])


@router.get(
    "/{layer}/{z}/{x}/{y}.png",
    summary="Kartenkachel abrufen",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}, "description": "Kachelbild"}},
)
async def tile(
    layer: str = Path(description="dop | webatlas | alkis"),
    z: int = Path(ge=0, le=24),
    x: int = Path(ge=0),
    y: int = Path(ge=0),
    tiles: TileService = Depends(tile_service),
) -> Response:
    image, from_cache = await tiles.tile(layer, z, x, y)
    return Response(
        content=image,
        media_type=tiles.settings.image_format,
        headers={
            "Cache-Control": f"public, max-age={tiles.settings.cache_ttl_s}",
            "X-Cache": "HIT" if from_cache else "MISS",
            "X-Attribution": "GeoSN, dl-de/by-2-0",
        },
    )


@router.post(
    "/warm",
    summary="Kacheln vorab in den Zwischenspeicher holen",
    status_code=202,
    response_model=VorwaermenErgebnis,
)
async def warm(
    body: KachelnVorwaermen,
    request: Request,
    background: BackgroundTasks,
    tiles: TileService = Depends(tile_service),
    oidc: OidcService = Depends(oidc_service),
) -> VorwaermenErgebnis:
    """Answer at once and fetch what is missing after the answer has gone.

    For the thumbnails of plots: a new plot's surroundings are otherwise first
    fetched when its card is drawn, at a second or more per tile from the GeoSN.
    Only the missing tiles are charged to the tile budget -- they are what goes
    outward -- on top of the one call this request is itself.
    """

    wanted = list(dict.fromkeys((t.ebene, t.z, t.x, t.y) for t in body.kacheln))
    missing = tiles.missing(wanted)
    if missing:
        spend_map_tiles(request, oidc, len(missing))
        background.add_task(tiles.warm, missing)
    return VorwaermenErgebnis(angefragt=len(wanted), geholt_werden=len(missing))
