"""GET /api/tiles/{layer}/{z}/{x}/{y}.png -- cached proxy in front of the GeoSN WMS."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Response

from ..deps import tile_service
from ..services.tiles import TileService

router = APIRouter(prefix="/api/tiles", tags=["Karten"])


@router.get(
    "/{layer}/{z}/{x}/{y}.png",
    summary="Kartenkachel abrufen",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}, "description": "Kachelbild"}},
)
async def tile(
    layer: str = Path(description="luftbild | dop | webatlas | deutschland | alkis | …"),
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
            "X-Attribution": tiles.attribution(layer),
        },
    )
