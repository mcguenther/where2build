"""Raster tile proxy in front of the GeoSN WMS services.

The proxy exists for two reasons: a browser should not have to depend on an
authority service's CORS behaviour, and every tile belongs in a disk cache --
an orthophoto does not change between two page views.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass

from .. import geo
from ..cache import DiskCache
from ..errors import BadRequestError, UpstreamError
from ..settings import AppSettings, TilesSettings

SERVICE_NAME = "Der Kartendienst des GeoSN"

# The pixel size a WMS scale denominator is defined against: 0,28 mm, from the
# OGC specification. It is what makes the denominator computable from the box
# and the image alone, and therefore steerable.
_METRES_PER_PIXEL_UNIT = 0.00028
ADVICE = (
    "Die Kartenebene bleibt leer; auf eine andere Ebene umschalten hilft meist. "
    "Fläche, Bodenrichtwert und Bebauungsplanung sind davon nicht betroffen."
)


@dataclass(frozen=True)
class LayerConfig:
    url: str
    layers: str
    # WMS `STYLES`. Empty means the service's own default, which is what every
    # layer here wanted until the parcel outlines: those are meant to sit over
    # an orthophoto, and the service offers a style for exactly that
    # („In der Gelb-Darstellung werden keine Flaechen sondern nur Konturen
    # dargestellt“).
    styles: str = ""
    # Below this zoom the service draws nothing that oversampling can rescue.
    min_zoom: int = 0
    # The scale the layer stops drawing at, as a WMS scale denominator. A layer
    # that carries one answers HTTP 200 with a fully transparent PNG above it
    # rather than an error -- `adv_alkis_flurstuecke` has 2000, and at 256 px a
    # z18 tile is 1:2133 and comes back empty. The way round it is the service's
    # own arithmetic: the denominator is (bbox_width / image_width) / 0.00028,
    # so asking for a *larger image over the same box* pushes it under the limit.
    # The oversized render is then scaled back to a tile here, which is why the
    # browser still receives an ordinary 256 px PNG.
    max_scale_denominator: float | None = None


def _downscale(data: bytes, target: int) -> bytes:
    """An oversized render back down to one tile.

    The whole point of asking for the larger image is the scale denominator, not
    the detail: what comes back has to reach the browser as an ordinary tile, or
    a screenful of them is megabytes. Downscaled with an area filter, so the
    thin cadastral lines survive as grey rather than disappearing between
    samples.

    Pillow is a hard dependency of this backend for exactly this. Without it the
    oversized image would still be *correct*, only large, so the failure is not
    worth an error -- it goes out as it came.
    """

    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is a declared dependency
        return data
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        if image.width <= target:
            return data
        smaller = image.convert("RGBA").resize((target, target), Image.BOX)
        buffer = io.BytesIO()
        smaller.save(buffer, format="PNG")
        return buffer.getvalue()


class TileService:
    def __init__(self, settings: TilesSettings, app_settings: AppSettings) -> None:
        self.settings = settings
        self.app_settings = app_settings
        self.cache = DiskCache(app_settings.cache_dir / "tiles", ttl_s=settings.cache_ttl_s)

    @property
    def layers(self) -> dict[str, LayerConfig]:
        return {
            "dop": LayerConfig(self.settings.dop_url, self.settings.dop_layers),
            "webatlas": LayerConfig(self.settings.webatlas_url, self.settings.webatlas_layers),
            "alkis": LayerConfig(self.settings.alkis_url, self.settings.alkis_layers),
            # The two that make an orthophoto readable as a cadastral map:
            # parcel outlines, and the roads with their names.
            "flurstuecke": LayerConfig(
                self.settings.alkis_url,
                self.settings.parcel_layers,
                styles=self.settings.parcel_styles,
                min_zoom=self.settings.parcel_min_zoom,
                max_scale_denominator=self.settings.parcel_max_scale_denominator,
            ),
            "strassen": LayerConfig(self.settings.webatlas_url, self.settings.street_layers),
        }

    def _config(self, layer: str) -> LayerConfig:
        try:
            return self.layers[layer]
        except KeyError:
            known = ", ".join(sorted(self.layers))
            raise BadRequestError(f"Unbekannte Ebene „{layer}“. Verfügbar: {known}.") from None

    def _check_tile(self, z: int, x: int, y: int) -> None:
        if not 0 <= z <= self.settings.max_zoom:
            raise BadRequestError(f"Zoomstufe {z} liegt außerhalb des gültigen Bereichs.")
        limit = 2**z
        if not (0 <= x < limit and 0 <= y < limit):
            raise BadRequestError(f"Kachel {x}/{y} liegt außerhalb der Zoomstufe {z}.")

    def render_size(self, config: LayerConfig, z: int) -> int:
        """How many pixels to ask the service for, for one tile of this layer.

        The tile size itself unless the layer has a scale limit, in which case
        it is the smallest multiple of the tile size that puts the WMS scale
        denominator under it -- capped by what the service will render at all.

        Measured at Flurstück 790/11: z18 needs 512 (1:1066), z17 needs 1024,
        z16 needs 2048. z14 would need 4368 and the service refuses anything
        over 4000, which is why the layer has a floor as well as a factor.
        """

        tile = self.settings.tile_size
        if not config.max_scale_denominator:
            return tile
        width_m = geo.tile_width_3857_m(z)
        needed = width_m / (config.max_scale_denominator * _METRES_PER_PIXEL_UNIT)
        # Rounded up to whole tiles rather than doubled: z15 needs 2184 px, and
        # the next power of two is 4096 — over the 4000 the service will render.
        # 2304 fits and draws at 1:1893, so a factor of nine is worth having.
        steps = max(1, math.ceil(needed / tile))
        return min(steps * tile, self.settings.max_render_size)

    def _params(self, config: LayerConfig, z: int, x: int, y: int, size: int) -> dict[str, str]:
        return {
            "SERVICE": "WMS",
            "VERSION": "1.3.0",
            "REQUEST": "GetMap",
            "LAYERS": config.layers,
            "STYLES": config.styles,
            "CRS": self.settings.crs,
            "BBOX": geo.wms_bbox(self.settings.crs, z, x, y),
            "WIDTH": str(size),
            "HEIGHT": str(size),
            "FORMAT": self.settings.image_format,
            "TRANSPARENT": "TRUE" if self.settings.transparent else "FALSE",
        }

    async def tile(self, layer: str, z: int, x: int, y: int) -> tuple[bytes, bool]:
        """Return the tile image and whether it came from the cache."""

        config = self._config(layer)
        self._check_tile(z, x, y)
        if z < config.min_zoom:
            raise BadRequestError(
                f"Die Ebene „{layer}“ zeichnet erst ab Zoomstufe {config.min_zoom}; "
                f"darunter liefert der Dienst ein leeres Bild."
            )
        size = self.render_size(config, z)
        cache_key = f"{layer}/{self.settings.crs}/{z}/{x}/{y}"
        cached = self.cache.get_bytes(cache_key)
        if cached is not None:
            return cached, True

        # Imported here so tests can patch app.upstream.request in one place.
        from ..upstream import request

        response = await request(
            "GET",
            config.url,
            service=SERVICE_NAME,
            advice=ADVICE,
            timeout_s=self.app_settings.http_timeout_s,
            user_agent=self.app_settings.user_agent,
            params=self._params(config, z, x, y, size),
        )
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            # WMS reports errors as XML with HTTP 200.
            raise UpstreamError(
                f"{SERVICE_NAME} hat statt einer Kachel eine Fehlermeldung geliefert. {ADVICE}"
            )
        image = (
            response.content
            if size == self.settings.tile_size
            else _downscale(response.content, self.settings.tile_size)
        )
        self.cache.set_bytes(cache_key, image)
        return image, False
