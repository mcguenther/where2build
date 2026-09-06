"""Air quality from the UBA's own measurements.

Nationwide and without a key -- the one check in this set that is not Saxon.
Two things about it are easy to get wrong, both measured rather than read:

* **The API is not on ``umweltbundesamt.de``.** The documented path there is a
  301 to ``luftdaten.umweltbundesamt.de``, and the path spells ``air-data``,
  not ``air_data``. Following neither is how the API comes to look dead.
* **The nearest station is not the station to use.** The list mixes in research
  and historic sites whose "active to" field is empty anyway. Around Moelkau
  the three nearest (1,9-3,0 km, prefixed ``z_GUAN`` and ``zDDR_``) answer with
  no measurements at all, while Leipzig-Mitte at 4,6 km answers with four
  pollutants. Verified again on 05.09.2026: stations 1690 and 10427 returned an
  empty document, station 1613 returned 89 hourly values. So the stations are
  tried in order of distance and the first one that actually carries values is
  the answer -- and the finding says how far away it is, because that is the
  price of the choice.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from ..cache import DiskCache
from ..errors import AppError, UpstreamError
from ..schemas import Luftqualitaet
from ..settings import AirQualitySettings, AppSettings
from ..upstream import request

SERVICE_NAME = "Die Luftdaten-API des Umweltbundesamtes"
PORTAL_URL = "https://www.umweltbundesamt.de/daten/luft/luftdaten"
ADVICE = f"Die Messwerte lassen sich unter {PORTAL_URL} nachsehen."
QUELLE = "Umweltbundesamt, Luftdaten-API v3 (Stundenmittel)"

# Component ids as the API numbers them, keyed by the short name the finding
# uses. Four of twelve: the ones every urban station measures.
COMPONENTS = {"no2": 5, "pm10": 1, "pm25": 9, "o3": 3}
# Scope 2 is the one-hour mean.
HOURLY_SCOPE = 2

# Positions inside the station row, which the API documents as `indices`.
_STATION_ID = 0
_STATION_NAME = 2
_STATION_ACTIVE_TO = 6
_STATION_LON = 7
_STATION_LAT = 8
# Position of the measured value inside a measurement row.
_MEASURE_VALUE = 2

EARTH_RADIUS_KM = 6371.0088


def distance_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Great-circle distance. Air distance is right here: what is being chosen
    is a place to measure the air, not a place to walk to."""

    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    d_phi = phi_b - phi_a
    d_lambda = math.radians(lon_b - lon_a)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


class AirQualityService:
    def __init__(self, settings: AirQualitySettings, app_settings: AppSettings) -> None:
        self.settings = settings
        self.app_settings = app_settings
        self.stations_cache = DiskCache(
            app_settings.cache_dir / "airquality" / "stations",
            ttl_s=settings.stations_cache_ttl_s,
        )
        self.measures_cache = DiskCache(
            app_settings.cache_dir / "airquality" / "measures",
            ttl_s=settings.measures_cache_ttl_s,
        )

    async def _get(self, path: str, params: dict[str, str], cache: DiskCache) -> dict[str, Any]:
        key = f"{path}?{sorted(params.items())}"
        cached = cache.get_json(key)
        if cached is not None:
            return cached
        response = await request(
            "GET",
            f"{self.settings.base_url}/{path}",
            service=SERVICE_NAME,
            advice=ADVICE,
            timeout_s=self.settings.timeout_s,
            user_agent=self.app_settings.user_agent,
            params=params,
        )
        try:
            answer = response.json()
        except ValueError as exc:
            raise UpstreamError(
                f"{SERVICE_NAME} hat keine verwertbare Antwort geliefert. {ADVICE}"
            ) from exc
        cache.set_json(key, answer)
        return answer

    async def _stations(self) -> list[dict[str, Any]]:
        answer = await self._get(
            "stations/json", {"lang": "de", "use_all_stations": "false"}, self.stations_cache
        )
        stations = []
        for row in (answer.get("data") or {}).values():
            try:
                stations.append({
                    "id": str(row[_STATION_ID]),
                    "name": str(row[_STATION_NAME]),
                    "lat": float(row[_STATION_LAT]),
                    "lon": float(row[_STATION_LON]),
                    "bis": row[_STATION_ACTIVE_TO],
                })
            except (IndexError, TypeError, ValueError):
                # A malformed row is one station, not a failed answer.
                continue
        return stations

    async def _values(self, station_id: str) -> tuple[dict[str, float], int, str | None]:
        """Hourly means per pollutant at one station, and how many went in."""

        today = date.today()
        window = {
            "date_from": (today - timedelta(days=max(1, self.settings.hours // 24))).isoformat(),
            "date_to": today.isoformat(),
            "time_from": "1",
            "time_to": "24",
            "station": station_id,
            "scope": str(HOURLY_SCOPE),
        }
        values: dict[str, float] = {}
        hours = 0
        latest: str | None = None
        for name, component in COMPONENTS.items():
            answer = await self._get(
                "measures/json", {**window, "component": str(component)}, self.measures_cache
            )
            rows = (answer.get("data") or {}).get(station_id) or {}
            measured = []
            for stamp, row in rows.items():
                try:
                    measured.append(float(row[_MEASURE_VALUE]))
                except (IndexError, TypeError, ValueError):
                    continue
                if latest is None or stamp > latest:
                    latest = stamp
            if not measured:
                continue
            recent = measured[-self.settings.hours:]
            values[name] = round(sum(recent) / len(recent), 1)
            hours = max(hours, len(recent))
        return values, hours, latest

    async def at(self, lat: float, lon: float) -> Luftqualitaet:
        """The nearest station that actually answers with values."""

        # Only an upstream failure becomes a row. A bug in here has to keep
        # travelling: turned into a `fehler` it would read to the user as "the
        # UBA is down", which is the one thing it is not.
        try:
            stations = await self._stations()
        except AppError as error:
            return Luftqualitaet(quelle=QUELLE, fehler=error.message)

        ranked = sorted(
            (
                (distance_km(lat, lon, station["lat"], station["lon"]), station)
                for station in stations
                if not station["bis"]
            ),
            key=lambda entry: entry[0],
        )
        within = [
            entry for entry in ranked[: self.settings.max_stations]
            if entry[0] <= self.settings.max_distance_km
        ]
        skipped = 0
        for distance, station in within:
            try:
                values, hours, latest = await self._values(station["id"])
            except AppError as error:
                return Luftqualitaet(quelle=QUELLE, fehler=error.message)
            if not values:
                # Silent station: counted, so the finding can say the nearest
                # one on the map is not the one that answered.
                skipped += 1
                continue
            return Luftqualitaet(
                station=station["name"],
                entfernung_km=round(distance, 1),
                werte=values,
                stunden=hours,
                stand=latest,
                uebersprungen=skipped,
                quelle=QUELLE,
            )
        return Luftqualitaet(uebersprungen=skipped, quelle=QUELLE)
