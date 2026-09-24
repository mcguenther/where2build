"""Raster tile proxy in front of the GeoSN WMS services.

The proxy exists for two reasons: a browser should not have to depend on an
authority service's CORS behaviour, and every tile belongs in a disk cache --
an orthophoto does not change between two page views.
"""

from __future__ import annotations

import hashlib
import io
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
    # WMS `STYLES`. Empty means the service's own default, which is what every
    # layer here wanted until the parcel outlines: those are meant to sit over
    # an orthophoto, and the service offers a style for exactly that
    # („In der Gelb-Darstellung werden keine Flaechen sondern nur Konturen
    # dargestellt“).
    styles: str = ""
    # Below this zoom the service draws nothing that oversampling can rescue.
    min_zoom: int = 0
    # Scale from which the layer draws nothing. ``None`` means it draws at
    # every scale. Both kinds have one, and both answer an empty image rather
    # than an error -- see ``_dpi_for`` and ``_map_resolution_for``.
    min_scale: float | None = None
    # The same limit, taken the other way round. A layer that carries one
    # answers HTTP 200 with a fully transparent PNG above it rather than an
    # error -- `adv_alkis_flurstuecke` has 2000, and at 256 px a z18 tile is
    # 1:2133 and comes back empty. The way round it is the service's own
    # arithmetic: the denominator is (bbox_width / image_width) / 0.00028, so
    # asking for a *larger image over the same box* pushes it under the limit.
    # The oversized render is then scaled back to a tile here, which is why the
    # browser still receives an ordinary 256 px PNG.
    #
    # Two ways to the same end, and they are not interchangeable: oversampling
    # keeps the layer's own symbology at its intended size, `min_scale` keeps
    # the request to one tile. A layer sets whichever was measured for it.
    max_scale_denominator: float | None = None


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


# The pixel size a WMS scale denominator is defined against: 0,28 mm, from the
# OGC specification. It is what makes the denominator computable from the box
# and the image alone, and therefore steerable -- either by asking for a larger
# image (``render_size``) or by saying the pixel is a different size
# (``MAP_RESOLUTION``).
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

    seed = (
        f"{config.url}|{config.layers}|{config.kind}|{config.styles}"
        f"|{config.min_scale}|{config.max_scale_denominator}"
    )
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]


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
            # The cadastral ground: parcels and buildings, in the service's own
            # symbology. The land-use layers (`tatsaechliche_nutzung`,
            # `verkehr`, `siedlung`) draw areas that cut straight across parcel
            # boundaries, which is the opposite of what a ground called
            # "Kataster" is for.
            "alkis": LayerConfig(
                self.settings.alkis_url,
                self.settings.alkis_layers,
                min_scale=self.settings.alkis_min_scale,
            ),
            # The Liegenschaftskarte over the photograph, at plot scale: the
            # numbers are the point of it, so the tile stays 256 px and the
            # scale limit is moved with `MAP_RESOLUTION` instead. Measured at
            # z18 over Liebertwolkwitz: this draws 101/2, 85/1 and the street
            # name legibly where the oversampled render below draws neither.
            "liegenschaftskarte": LayerConfig(
                self.settings.alkis_url,
                self.settings.cadastral_map_layers,
                min_scale=self.settings.alkis_min_scale,
            ),
            # The two that make an orthophoto readable as a cadastral map
            # across a district: parcel outlines, and the roads with their
            # names. Contours only — the buildings' fills would cover the roofs
            # the photograph is there to show — and rendered large so they
            # still draw five zoom steps above the layer's own limit.
            "flurstuecke": LayerConfig(
                self.settings.alkis_url,
                self.settings.parcel_layers,
                styles=self.settings.parcel_styles,
                min_zoom=self.settings.parcel_min_zoom,
                max_scale_denominator=self.settings.parcel_max_scale_denominator,
            ),
            "strassen": LayerConfig(self.settings.webatlas_url, self.settings.street_layers),
            "umgebung": LayerConfig(self.settings.webatlas_url, self.settings.surroundings_layers),
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
        needed = width_m / (config.max_scale_denominator * _STANDARD_PIXEL_M)
        # Rounded up to whole tiles rather than doubled: z15 needs 2184 px, and
        # the next power of two is 4096 — over the 4000 the service will render.
        # 2304 fits and draws at 1:1893, so a factor of nine is worth having.
        steps = max(1, math.ceil(needed / tile))
        return min(steps * tile, self.settings.max_render_size)

    def _params(self, config: LayerConfig, z: int, x: int, y: int, size: int) -> dict[str, str]:
        if config.kind == "arcgis":
            return self._arcgis_params(config, z, x, y)
        params = {
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
        if z < config.min_zoom:
            raise BadRequestError(
                f"Die Ebene „{layer}“ zeichnet erst ab Zoomstufe {config.min_zoom}; "
                f"darunter liefert der Dienst ein leeres Bild."
            )
        crs = "EPSG:3857" if config.kind == "arcgis" else self.settings.crs
        size = self.render_size(config, z)
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
