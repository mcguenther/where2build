"""Multimodal routing through MOTIS (public Transitous instance by default).

Two things about the response are easy to get wrong and both are handled here:
direct car/bike/foot routes arrive in ``direct[]`` rather than ``itineraries[]``,
and ``legGeometry`` is a Google polyline with **precision 6** -- decoding it
with the usual precision 5 puts the coordinates off by a factor of ten.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from ..cache import DiskCache
from ..errors import UpstreamError
from ..schemas import (
    Geocodeart,
    GeocodeTreffer,
    Koordinate,
    Modus,
    ReachabilityResponse,
    RouteErgebnis,
    Teilstrecke,
    Ziel,
)
from ..settings import AppSettings, MotisSettings
from ..upstream import request

SERVICE_NAME = "Der Routing-Dienst (MOTIS/Transitous)"
# Routing is the one part of the appraisal nothing else depends on.
ADVICE = (
    "Die Erreichbarkeiten lassen sich später erneut berechnen; Fläche, "
    "Bodenrichtwert und Bebauung des Grundstücks sind davon nicht betroffen."
)
GEOCODE_ADVICE = (
    "Die Adresssuche steht damit nicht zur Verfügung — Koordinate oder "
    "Gemarkung mit Flurstücksnummer lassen sich direkt eintragen."
)

DEFAULT_PRECISION = 6

# The picker in the UI shows a handful of candidates, not a page of them.
MAX_GEOCODE_RESULTS = 5

# How each API mode maps onto MOTIS query parameters.
_DIRECT_MODES: dict[str, str] = {"car": "CAR", "bike": "BIKE", "walk": "WALK"}


def decode_polyline(encoded: str, precision: int = DEFAULT_PRECISION) -> list[tuple[float, float]]:
    """Decode a Google-encoded polyline into (lat, lon) pairs.

    MOTIS reports the precision in ``legGeometry.precision``; use that value
    rather than assuming one.
    """

    factor = float(10**precision)
    coordinates: list[tuple[float, float]] = []
    index = 0
    lat = 0
    lon = 0
    length = len(encoded)
    while index < length:
        for axis in range(2):
            shift = 0
            result = 0
            while True:
                if index >= length:
                    raise ValueError("Polyline ist unvollständig.")
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else (result >> 1)
            if axis == 0:
                lat += delta
            else:
                lon += delta
        coordinates.append((lat / factor, lon / factor))
    return coordinates


def leg_geometry_to_coordinates(leg_geometry: dict[str, Any] | None) -> list[list[float]]:
    """One leg's geometry as GeoJSON coordinates ([lon, lat], mind the order)."""

    if not leg_geometry or not leg_geometry.get("points"):
        return []
    precision = int(leg_geometry.get("precision") or DEFAULT_PRECISION)
    return [[lon, lat] for lat, lon in decode_polyline(leg_geometry["points"], precision)]


def itinerary_to_linestring(itinerary: dict[str, Any]) -> dict[str, Any] | None:
    """Concatenate all leg geometries of an itinerary into one LineString."""

    coordinates: list[list[float]] = []
    for leg in itinerary.get("legs", []):
        for point in leg_geometry_to_coordinates(leg.get("legGeometry")):
            if not coordinates or coordinates[-1] != point:
                coordinates.append(point)
    if len(coordinates) < 2:
        return None
    return {"type": "LineString", "coordinates": coordinates}


def _teilstrecken(itinerary: dict[str, Any]) -> list[Teilstrecke]:
    strecken: list[Teilstrecke] = []
    for leg in itinerary.get("legs", []):
        strecken.append(
            Teilstrecke(
                mode=str(leg.get("mode", "")),
                duration_s=int(leg.get("duration") or 0),
                von=(leg.get("from") or {}).get("name"),
                nach=(leg.get("to") or {}).get("name"),
            )
        )
    return strecken


# What MOTIS calls a result, in the words the UI uses.
_GEOCODE_KINDS: dict[str, Geocodeart] = {
    "ADDRESS": "adresse",
    "STOP": "haltestelle",
    "PLACE": "ort",
}
# Administrative levels of the OSM areas MOTIS attaches to every hit:
# 4 is the federal state, 8 the municipality, 9/10 the part of it.
_STATE_LEVEL = 4.0
_MUNICIPALITY_LEVEL = 8.0
_DISTRICT_LEVELS = (9.0, 10.0)


def _area(entry: dict[str, Any], levels: tuple[float, ...]) -> str | None:
    for area in entry.get("areas") or []:
        if area.get("adminLevel") in levels and area.get("name"):
            return str(area["name"])
    return None


def _description(entry: dict[str, Any]) -> str | None:
    """Where the hit is, in enough detail to tell two of them apart.

    The federal state is in there on purpose: a Saxon street name answered with
    a village in Bavaria is this geocoder's most common failure, and it is only
    visible if the state is on screen.
    """

    municipality = _area(entry, (_MUNICIPALITY_LEVEL,))
    district = _area(entry, _DISTRICT_LEVELS)
    parts = [
        " ".join(part for part in (entry.get("zip"), municipality) if part) or None,
        district if district and district != municipality else None,
        _area(entry, (_STATE_LEVEL,)),
    ]
    return ", ".join(part for part in parts if part) or None


def _as_treffer(entry: Any) -> GeocodeTreffer | None:
    if not isinstance(entry, dict):
        return None
    lat, lon = entry.get("lat"), entry.get("lon")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    name = str(entry.get("name") or "").strip()
    if not name:
        # Without a label the user cannot check the hit, so it is of no use.
        return None
    return GeocodeTreffer(
        lat=float(lat),
        lon=float(lon),
        name=name,
        beschreibung=_description(entry),
        art=_GEOCODE_KINDS.get(str(entry.get("type") or ""), "sonstiges"),
    )


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class MotisService:
    def __init__(self, settings: MotisSettings, app_settings: AppSettings) -> None:
        self.settings = settings
        self.app_settings = app_settings
        self.cache = DiskCache(app_settings.cache_dir / "motis", ttl_s=settings.cache_ttl_s)
        self._semaphore = asyncio.Semaphore(max(1, settings.max_concurrency))

    def _plan_params(
        self, origin: Koordinate, destination: Koordinate, mode: Modus, time: datetime | None
    ) -> dict[str, str]:
        params: dict[str, str] = {
            "fromPlace": f"{origin.lat},{origin.lon}",
            "toPlace": f"{destination.lat},{destination.lon}",
        }
        if time is not None:
            params["time"] = time.isoformat()

        if mode in _DIRECT_MODES:
            params["directModes"] = _DIRECT_MODES[mode]
            # An empty value keeps public transport out of a car/bike/foot query.
            params["transitModes"] = ""
            params["maxDirectTime"] = str(self.settings.max_direct_time_s)
            params["numItineraries"] = "1"
        else:
            params["transitModes"] = "TRANSIT"
            params["preTransitModes"] = "BIKE" if mode == "bike_transit" else "WALK"
            params["postTransitModes"] = "WALK"
            params["maxPreTransitTime"] = str(self.settings.max_pre_transit_time_s)
            params["numItineraries"] = "2"
        return params

    async def _plan(self, params: dict[str, str]) -> dict[str, Any]:
        cache_key = repr(sorted(params.items()))
        cached = self.cache.get_json(cache_key)
        if cached is not None:
            return cached
        async with self._semaphore:
            response = await request(
                "GET",
                f"{self.settings.base_url.rstrip('/')}/api/v6/plan",
                service=SERVICE_NAME,
                advice=ADVICE,
                timeout_s=self.settings.timeout_s,
                user_agent=self.app_settings.user_agent,
                params=params,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise UpstreamError(
                f"{SERVICE_NAME} hat kein gültiges JSON geliefert. {ADVICE}"
            ) from exc
        self.cache.set_json(cache_key, payload)
        return payload

    async def route(
        self, origin: Koordinate, destination: Ziel, mode: Modus, time: datetime | None = None
    ) -> RouteErgebnis:
        payload = await self._plan(self._plan_params(origin, destination, mode, time))
        # Direct modes never appear in `itineraries`; transit results never in `direct`.
        candidates = payload.get("direct") or [] if mode in _DIRECT_MODES else payload.get("itineraries") or []
        if not candidates:
            return RouteErgebnis(
                destination_id=destination.id,
                mode=mode,
                erreichbar=False,
                hinweis="Für dieses Ziel wurde keine Verbindung gefunden.",
            )
        itinerary = min(candidates, key=lambda entry: entry.get("duration") or 10**9)
        geometry = itinerary_to_linestring(itinerary)
        return RouteErgebnis(
            destination_id=destination.id,
            mode=mode,
            erreichbar=True,
            duration_s=int(itinerary.get("duration") or 0),
            umstiege=itinerary.get("transfers"),
            startzeit=_parse_time(itinerary.get("startTime")),
            ankunftszeit=_parse_time(itinerary.get("endTime")),
            geometry=geometry,
            teilstrecken=_teilstrecken(itinerary),
        )

    async def reachability(
        self,
        origin: Koordinate,
        destinations: list[Ziel],
        modes: list[Modus],
        time: datetime | None = None,
    ) -> ReachabilityResponse:
        tasks = [
            self.route(origin, destination, mode, time)
            for destination in destinations
            for mode in modes
        ]
        return ReachabilityResponse(ergebnisse=list(await asyncio.gather(*tasks)))

    async def geocode_candidates(
        self, text: str, bias: Koordinate | None = None, limit: int = MAX_GEOCODE_RESULTS
    ) -> list[GeocodeTreffer]:
        """Free text -> candidates, best first.

        A stopgap: the spec wants the official Hauskoordinaten dataset in
        PostGIS for this, which is step 1 of the implementation order and not
        part of this backend yet. MOTIS ships a geocoder, so an address entry
        works in the meantime -- with a lower hit rate on new developments and
        a habit of answering a Saxon street name with a Bavarian village. That
        is why the candidates travel with their labels instead of the caller
        getting one silent guess.
        """

        params = {"text": text, "language": "de"}
        if bias is not None:
            # MOTIS ranks results near `place` higher; it does not filter by it.
            params["place"] = f"{bias.lat},{bias.lon}"

        cache_key = f"geocode:{repr(sorted(params.items())).casefold()}"
        cached = self.cache.get_json(cache_key)
        if cached is None:
            async with self._semaphore:
                response = await request(
                    "GET",
                    f"{self.settings.base_url.rstrip('/')}/api/v1/geocode",
                    service=SERVICE_NAME,
                    advice=GEOCODE_ADVICE,
                    timeout_s=self.settings.timeout_s,
                    user_agent=self.app_settings.user_agent,
                    params=params,
                )
            try:
                cached = response.json()
            except ValueError as exc:
                raise UpstreamError(
                    f"{SERVICE_NAME} hat kein gültiges JSON geliefert. {GEOCODE_ADVICE}"
                ) from exc
            self.cache.set_json(cache_key, cached)

        treffer: list[GeocodeTreffer] = []
        for entry in cached if isinstance(cached, list) else []:
            hit = _as_treffer(entry)
            if hit is not None:
                treffer.append(hit)
            if len(treffer) >= limit:
                break
        return treffer

    async def geocode(self, text: str, bias: Koordinate | None = None) -> Koordinate | None:
        """The best candidate's coordinate, or None when nothing matched."""

        treffer = await self.geocode_candidates(text, bias, limit=1)
        return Koordinate(lat=treffer[0].lat, lon=treffer[0].lon) if treffer else None
