"""Raster tile proxy in front of the GeoSN WMS services.

The proxy exists for two reasons: a browser should not have to depend on an
authority service's CORS behaviour, and every tile belongs in a disk cache --
an orthophoto does not change between two page views.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from .. import geo
from ..cache import DiskCache
from ..errors import BadRequestError, UpstreamError
from ..settings import AppSettings, TilesSettings

SERVICE_NAME = "Der Kartendienst des GeoSN"
ADVICE = (
    "Die Kartenebene bleibt leer; auf eine andere Ebene umschalten hilft meist. "
    "Fläche, Bodenrichtwert und Bebauungsplanung sind davon nicht betroffen."
)


@dataclass(frozen=True)
class LayerConfig:
    url: str
    layers: str
    # "wms" is a WMS 1.3.0 GetMap; "arcgis" is an ArcGIS ``export`` request,
    # which is a different set of parameter names for the same picture.
    kind: str = "wms"
    # Scale from which the layer draws nothing. ``None`` means it draws at
    # every scale. Both kinds have one, and both answer an empty image rather
    # than an error -- see ``_dpi_for`` and ``_map_resolution_for``.
    min_scale: float | None = None


# ArcGIS' own maximum; asking for more only enlarges the symbology.
_MAX_DPI = 96
# The inch, in metres. ArcGIS derives the map scale with it.
_METRES_PER_INCH = 0.0254


def _dpi_for(bbox_width_m: float, image_width_px: int, min_scale: float | None) -> int:
    """The highest dpi at which a ``minScale`` layer still draws.

    ArcGIS computes the scale as ``(bbox_width_m / image_width_px) * dpi /
    0.0254``, so the dpi is the one term the caller controls. Above the layer's
    ``minScale`` the service answers with an empty image and no error -- the
    failure mode this exists to prevent. Floored rather than rounded, because
    the threshold is exclusive: measured at 10 km over 512 px, dpi 65 draws and
    dpi 66 comes back blank.
    """

    if min_scale is None or bbox_width_m <= 0:
        return _MAX_DPI
    allowed = math.floor(min_scale * _METRES_PER_INCH * image_width_px / bbox_width_m)
    # A dpi below 1 is not a request ArcGIS accepts. It cannot arise for a tile
    # of any real zoom -- at zoom 0 the whole world is one tile -- but the
    # clamp keeps the arithmetic from ever producing one.
    return max(1, min(_MAX_DPI, allowed))


# The OGC standard pixel: 0,28 mm. A WMS derives the scale a request asks for
# from it, and ``MAP_RESOLUTION`` is how a caller says the pixel is a different
# size.
_STANDARD_PIXEL_M = 0.00028
_STANDARD_RESOLUTION = round(_METRES_PER_INCH / _STANDARD_PIXEL_M)


def _map_resolution_for(
    bbox_width_m: float, image_width_px: int, min_scale: float | None
) -> int | None:
    """The resolution that keeps a tile inside a WMS layer's own scale range.

    ``None`` when the standard pixel is already inside it, and the parameter is
    then left off the request altogether.

    The service computes the scale as ``bbox_width_m * resolution /
    (image_width_px * 0.0254)``. The ALKIS layers stop drawing at 1:2000 and
    answer with an empty image -- no error, nothing in the log -- so the
    resolution is what keeps the cadastral ground from silently disappearing
    two zoom steps out. Measured on a z18 tile over Liebertwolkwitz on
    05.09.2026: 85 draws, 86 is blank, and the threshold itself is excluded
    (1:1990 draws, 1:2000 does not), which is why this is one below the exact
    solution rather than its floor.
    """

    if min_scale is None or bbox_width_m <= 0:
        return None
    at_standard = bbox_width_m / (image_width_px * _STANDARD_PIXEL_M)
    if at_standard < min_scale:
        return None
    exact = min_scale * _METRES_PER_INCH * image_width_px / bbox_width_m
    return max(1, min(_STANDARD_RESOLUTION, math.ceil(exact) - 1))


def _fingerprint(config: LayerConfig) -> str:
    """A short digest of what this layer actually asks the service for."""

    seed = f"{config.url}|{config.layers}|{config.kind}|{config.min_scale}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]


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
            "alkis": LayerConfig(
                self.settings.alkis_url,
                self.settings.alkis_layers,
                min_scale=self.settings.alkis_min_scale,
            ),
            "flurstuecke": LayerConfig(
                self.settings.alkis_url,
                self.settings.alkis_parcel_layers,
                min_scale=self.settings.alkis_min_scale,
            ),
            "laerm": LayerConfig(
                self.settings.noise_url,
                self.settings.noise_layers,
                kind="arcgis",
                min_scale=self.settings.noise_min_scale,
            ),
            "laerm-nacht": LayerConfig(
                self.settings.noise_url,
                self.settings.noise_night_layers,
                kind="arcgis",
                min_scale=self.settings.noise_min_scale,
            ),
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

    def _params(self, config: LayerConfig, z: int, x: int, y: int) -> dict[str, str]:
        if config.kind == "arcgis":
            return self._arcgis_params(config, z, x, y)
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.3.0",
            "REQUEST": "GetMap",
            "LAYERS": config.layers,
            "STYLES": "",
            "CRS": self.settings.crs,
            "BBOX": geo.wms_bbox(self.settings.crs, z, x, y),
            "WIDTH": str(self.settings.tile_size),
            "HEIGHT": str(self.settings.tile_size),
            "FORMAT": self.settings.image_format,
            "TRANSPARENT": "TRUE" if self.settings.transparent else "FALSE",
        }
        resolution = self._map_resolution(config, z, x, y)
        if resolution is not None:
            params["MAP_RESOLUTION"] = str(resolution)
        return params

    def _map_resolution(self, config: LayerConfig, z: int, x: int, y: int) -> int | None:
        """The pixel size for this tile, or ``None`` to leave it to the service.

        Only for a metric CRS: in EPSG:4326 the BBOX is degrees, and the scale
        the service derives from it is not the arithmetic above.
        """

        if self.settings.crs.upper() not in (geo.WEB_MERCATOR, "EPSG:900913"):
            return None
        minx, _, maxx, _ = geo.tile_bounds_3857(z, x, y)
        return _map_resolution_for(maxx - minx, self.settings.tile_size, config.min_scale)

    def _arcgis_params(self, config: LayerConfig, z: int, x: int, y: int) -> dict[str, str]:
        """An ArcGIS ``export`` request for one XYZ tile.

        Always in Web Mercator: the service reprojects server-side, which is
        the whole reason this path exists next to the WMS one.
        """

        minx, miny, maxx, maxy = geo.tile_bounds_3857(z, x, y)
        return {
            "bbox": f"{minx},{miny},{maxx},{maxy}",
            "bboxSR": "3857",
            "imageSR": "3857",
            "size": f"{self.settings.tile_size},{self.settings.tile_size}",
            "layers": config.layers,
            "format": "png32",
            "transparent": "true" if self.settings.transparent else "false",
            "dpi": str(_dpi_for(maxx - minx, self.settings.tile_size, config.min_scale)),
            "f": "image",
        }

    async def tile(self, layer: str, z: int, x: int, y: int) -> tuple[bytes, bool]:
        """Return the tile image and whether it came from the cache."""

        config = self._config(layer)
        self._check_tile(z, x, y)
        crs = "EPSG:3857" if config.kind == "arcgis" else self.settings.crs
        # The layer list is part of the key, not just the name: changing which
        # ALKIS layers "alkis" stands for kept serving the old picture until
        # someone deleted the cache by hand -- and a stale tile of the *previous*
        # configuration looks exactly like a change that did not work.
        cache_key = f"{layer}/{_fingerprint(config)}/{crs}/{z}/{x}/{y}"
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
            params=self._params(config, z, x, y),
        )
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            # WMS reports errors as XML with HTTP 200.
            raise UpstreamError(
                f"{SERVICE_NAME} hat statt einer Kachel eine Fehlermeldung geliefert. {ADVICE}"
            )
        self.cache.set_bytes(cache_key, response.content)
        return response.content, False
