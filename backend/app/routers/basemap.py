"""GET /api/basemap/... -- cached proxy in front of the OpenFreeMap vector basemap.

The browser must be able to draw the map while reaching nothing but this API.
``style.json`` is therefore rewritten so every URL in it comes back here, and
the catch-all below serves whatever the map then asks for: TileJSON, vector
tiles, glyph ranges, sprite sheet and the raster hillshade.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Request, Response
from fastapi.responses import JSONResponse

from ..deps import basemap_service
from ..services.basemap import BasemapService

router = APIRouter(prefix="/api/basemap", tags=["Karten"])

# HTTP headers travel as latin-1, so this one stays plain ASCII.
ATTRIBUTION = "OpenFreeMap, OpenMapTiles, OpenStreetMap-Mitwirkende (ODbL)"


def _headers(service: BasemapService, from_cache: bool) -> dict[str, str]:
    return {
        "Cache-Control": f"public, max-age={service.settings.cache_ttl_s}",
        "X-Cache": "HIT" if from_cache else "MISS",
        "X-Attribution": ATTRIBUTION,
    }


@router.get(
    "/style.json",
    summary="Kartenstil abrufen",
    response_class=JSONResponse,
    responses={200: {"content": {"application/json": {}}, "description": "MapLibre-Style"}},
)
async def style(basemap: BasemapService = Depends(basemap_service)) -> Response:
    document, from_cache = await basemap.style()
    return JSONResponse(content=document, headers=_headers(basemap, from_cache))


@router.get(
    "/{path:path}",
    summary="Kacheln, Glyphen und Sprites durchreichen",
    response_class=Response,
    responses={
        200: {
            "content": {"application/x-protobuf": {}, "application/json": {}, "image/png": {}},
            "description": "Antwort des Kartendienstes, Header unverändert",
        }
    },
)
async def passthrough(
    request: Request,
    path: str = Path(description="Pfad auf dem Kartendienst, z. B. planet/…/14/8798/5484.pbf"),
    basemap: BasemapService = Depends(basemap_service),
) -> Response:
    proxied = await basemap.fetch(path, request.url.query)
    headers = _headers(basemap, proxied.from_cache)

    if proxied.is_json:
        # A TileJSON names its tile URLs absolutely; those have to come back
        # here too, or the map leaves our origin on the first tile.
        return JSONResponse(content=basemap.json_document(proxied), headers=headers)

    if proxied.content_encoding:
        # Vector tiles and glyph ranges are served gzipped and stay that way:
        # the body is handed on untouched together with its encoding.
        headers["Content-Encoding"] = proxied.content_encoding
    return Response(content=proxied.body, media_type=proxied.content_type, headers=headers)
