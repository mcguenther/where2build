"""GET /api/tiles/{layer}/{z}/{x}/{y}.png -- cached proxy in front of the GeoSN WMS.

GET /api/tiles/{layer}/block/{z}/{west}/{north}/{east}/{south}.png is a
rectangle of those tiles as one image -- a thumbnail's whole ground -- and
POST /api/tiles/warm builds such images before anyone draws them.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Request, Response

from ..deps import oidc_service, spend_map_tiles, tile_service
from ..schemas import BloeckeVorwaermen, VorwaermenErgebnis
from ..services.oidc import OidcService
from ..services.tiles import TileBlock, TileService

router = APIRouter(prefix="/api/tiles", tags=["Karten"])


def _image(tiles: TileService, image: bytes, from_cache: bool) -> Response:
    return Response(
        content=image,
        media_type=tiles.settings.image_format,
        headers={
            "Cache-Control": f"public, max-age={tiles.settings.cache_ttl_s}",
            "X-Cache": "HIT" if from_cache else "MISS",
            "X-Attribution": "GeoSN, dl-de/by-2-0",
        },
    )


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
    return _image(tiles, image, from_cache)


@router.get(
    "/{layer}/block/{z}/{west}/{north}/{east}/{south}.png",
    summary="Rechteck aus Kartenkacheln als ein Bild abrufen",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}, "description": "Zusammengesetztes Bild"}},
)
async def block(
    request: Request,
    layer: str = Path(description="Kartenebene, wie bei einer Einzelkachel"),
    z: int = Path(ge=0, le=24),
    west: int = Path(ge=0),
    north: int = Path(ge=0),
    east: int = Path(ge=0),
    south: int = Path(ge=0),
    tiles: TileService = Depends(tile_service),
    oidc: OidcService = Depends(oidc_service),
) -> Response:
    """The ground of a thumbnail: one request and one image instead of a dozen tiles.

    Besides the call itself, every tile it has to fetch from the GeoSN is
    charged to the tile budget, as the warm-up does -- those are what go
    outward.
    """

    wanted = TileBlock(layer, z, west, north, east, south)
    outward = tiles.tiles_to_fetch([wanted])
    if outward:
        spend_map_tiles(request, oidc, len(outward))
    image, from_cache = await tiles.block(wanted)
    return _image(tiles, image, from_cache)


@router.post(
    "/warm",
    summary="Kachelblöcke vorab zusammensetzen und zwischenspeichern",
    status_code=202,
    response_model=VorwaermenErgebnis,
)
async def warm(
    body: BloeckeVorwaermen,
    request: Request,
    background: BackgroundTasks,
    tiles: TileService = Depends(tile_service),
    oidc: OidcService = Depends(oidc_service),
) -> VorwaermenErgebnis:
    """Answer at once and build what is missing after the answer has gone.

    For the thumbnails of plots: a new plot's surroundings are otherwise first
    fetched when its card is drawn, at a second or more per tile from the GeoSN.
    Only the missing tiles are charged to the tile budget -- they are what goes
    outward -- on top of the one call this request is itself.
    """

    named = list(
        dict.fromkeys(
            TileBlock(b.ebene, b.z, b.west, b.nord, b.ost, b.sued) for b in body.bloecke
        )
    )
    outward = tiles.tiles_to_fetch(named)
    pending = tiles.blocks_to_build(named)
    if outward:
        spend_map_tiles(request, oidc, len(outward))
    if pending:
        background.add_task(tiles.warm, pending)
    return VorwaermenErgebnis(
        angefragt=len(named), zusammengesetzt_werden=len(pending), geholt_werden=len(outward)
    )
