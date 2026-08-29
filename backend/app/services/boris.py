"""BORIS Sachsen: the land reference value (Bodenrichtwert) for a coordinate.

BORIS offers no WFS and no vector download -- the only programmatic way in is
a WMS ``GetFeatureInfo``. ``INFO_FORMAT=application/json`` is UTFGrid rather
than GeoJSON and fails outright on the combined layer, so ``text/plain`` it is.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urlencode

from .. import geo
from ..cache import DiskCache
from ..errors import NotFoundError, UpstreamError
from ..schemas import LandValue
from ..settings import AppSettings, BorisSettings
from ..upstream import request

SERVICE_NAME = "Der BORIS-Dienst des GeoSN"

_FIELD_PATTERN = re.compile(r"^\s*([A-Z0-9_]+)\s*=\s*'(.*)'\s*$")
# Half-edge of the query window in metres; the pixel we ask about is its centre.
_WINDOW_M = 50.0
_PIXELS = 101


def parse_feature_info(text: str) -> list[dict[str, str]]:
    """Split a ``text/plain`` GetFeatureInfo body into one dict per feature."""

    features: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in text.splitlines():
        if line.strip().startswith("Feature "):
            current = {}
            features.append(current)
            continue
        match = _FIELD_PATTERN.match(line)
        if match and current is not None:
            current[match.group(1)] = match.group(2).strip()
    return [feature for feature in features if feature]


def _as_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace(".", "").replace(",", ".") if "," in value else value)
    except ValueError:
        return None


def _as_date(value: str | None) -> date | None:
    if not value:
        return None
    for pattern in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


class BorisService:
    def __init__(self, settings: BorisSettings, app_settings: AppSettings) -> None:
        self.settings = settings
        self.app_settings = app_settings
        self.cache = DiskCache(app_settings.cache_dir / "boris", ttl_s=settings.cache_ttl_s)

    def _params(self, lat: float, lon: float) -> dict[str, str]:
        easting, northing = geo.wgs84_to_utm33(lon, lat)
        centre = (_PIXELS - 1) // 2
        return {
            "SERVICE": "WMS",
            "VERSION": "1.3.0",
            "REQUEST": "GetFeatureInfo",
            "LAYERS": self.settings.layer,
            "QUERY_LAYERS": self.settings.layer,
            "CRS": "EPSG:25833",
            "BBOX": (
                f"{easting - _WINDOW_M},{northing - _WINDOW_M},"
                f"{easting + _WINDOW_M},{northing + _WINDOW_M}"
            ),
            "WIDTH": str(_PIXELS),
            "HEIGHT": str(_PIXELS),
            "I": str(centre),
            "J": str(centre),
            "INFO_FORMAT": "text/plain",
            "FEATURE_COUNT": "5",
        }

    async def land_value(self, lat: float, lon: float) -> LandValue:
        params = self._params(lat, lon)
        source_url = f"{self.settings.wms_url}?{urlencode(params)}"

        cached = self.cache.get_bytes(source_url)
        if cached is not None:
            body = cached.decode("utf-8", errors="replace")
        else:
            response = await request(
                "GET",
                self.settings.wms_url,
                service=SERVICE_NAME,
                timeout_s=self.app_settings.http_timeout_s,
                user_agent=self.app_settings.user_agent,
                params=params,
            )
            body = response.text
            if "ServiceException" in body:
                raise UpstreamError(f"{SERVICE_NAME} hat die Anfrage abgelehnt.")
            self.cache.set_bytes(source_url, response.content)

        for feature in parse_feature_info(body):
            value = _as_float(feature.get("BODENRICHTWERT_TEXT"))
            if value is None:
                continue
            return LandValue(
                euro_per_sqm=value,
                zone=feature.get("BODENRICHTWERTNUMMER") or None,
                reference_date=_as_date(feature.get("STICHTAG_TXT")),
                source_url=source_url,
                nutzung=feature.get("NUTZUNG_TEXT") or feature.get("NUTZUNG") or None,
                entwicklungszustand=feature.get("ENTWICKLUNGSZUSTAND_TEXT") or None,
                gutachterausschuss=feature.get("GA_POST_NAME") or None,
            )

        raise NotFoundError(
            "Für diese Koordinate liegt in BORIS Sachsen kein Bodenrichtwert vor."
        )
