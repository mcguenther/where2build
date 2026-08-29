"""Projections and tile maths.

Rule from the spec: compute in EPSG:25833, transform only for display.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform as shapely_transform

WGS84 = "EPSG:4326"
UTM33 = "EPSG:25833"
WEB_MERCATOR = "EPSG:3857"

# WMS 1.3.0 uses the CRS' own axis order. Geographic CRS are latitude first.
_LATLON_FIRST = {"EPSG:4326", "EPSG:4258", "CRS:84"}


@lru_cache(maxsize=32)
def _transformer(from_crs: str, to_crs: str) -> Transformer:
    return Transformer.from_crs(from_crs, to_crs, always_xy=True)


def utm33_to_wgs84(easting: float, northing: float) -> tuple[float, float]:
    """(E, N) in EPSG:25833 -> (lon, lat)."""

    return _transformer(UTM33, WGS84).transform(easting, northing)


def wgs84_to_utm33(lon: float, lat: float) -> tuple[float, float]:
    """(lon, lat) -> (E, N) in EPSG:25833."""

    return _transformer(WGS84, UTM33).transform(lon, lat)


def reproject_geometry(geometry: Any, from_crs: str, to_crs: str) -> Any:
    """Reproject a shapely geometry."""

    transformer = _transformer(from_crs, to_crs)
    return shapely_transform(lambda xs, ys: transformer.transform(xs, ys), geometry)


def to_geojson(geometry: Any) -> dict[str, Any]:
    return mapping(geometry)


def from_geojson(data: dict[str, Any]) -> Any:
    return shape(data)


def tile_bounds_3857(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Web-Mercator bounds (minx, miny, maxx, maxy) of an XYZ tile."""

    half = 20037508.342789244
    span = 2 * half / (2**z)
    minx = -half + x * span
    maxx = minx + span
    maxy = half - y * span
    miny = maxy - span
    return minx, miny, maxx, maxy


def tile_bounds_4326(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Geographic bounds (minlon, minlat, maxlon, maxlat) of an XYZ tile."""

    n = 2.0**z
    minlon = x / n * 360.0 - 180.0
    maxlon = (x + 1) / n * 360.0 - 180.0
    maxlat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    minlat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return minlon, minlat, maxlon, maxlat


def wms_bbox(crs: str, z: int, x: int, y: int) -> str:
    """BBOX parameter for a WMS 1.3.0 GetMap of one XYZ tile."""

    crs_upper = crs.upper()
    if crs_upper in _LATLON_FIRST:
        minlon, minlat, maxlon, maxlat = tile_bounds_4326(z, x, y)
        return f"{minlat},{minlon},{maxlat},{maxlon}"
    if crs_upper in (WEB_MERCATOR, "EPSG:900913"):
        minx, miny, maxx, maxy = tile_bounds_3857(z, x, y)
        return f"{minx},{miny},{maxx},{maxy}"
    # Any other projected CRS: reproject the tile corners. The result is the
    # enclosing rectangle, which is slightly larger than the tile.
    minlon, minlat, maxlon, maxlat = tile_bounds_4326(z, x, y)
    transformer = _transformer(WGS84, crs_upper)
    xs, ys = transformer.transform(
        [minlon, maxlon, minlon, maxlon], [minlat, minlat, maxlat, maxlat]
    )
    return f"{min(xs)},{min(ys)},{max(xs)},{max(ys)}"
