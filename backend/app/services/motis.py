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
    Umgebungsmodus,
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
NEARBY_ADVICE = (
    "Haltestellen und Gehzeiten lassen sich damit gerade nicht ermitteln; "
    "Fläche, Bodenrichtwert und Bebauung des Grundstücks sind davon nicht "
    "betroffen."
)

DEFAULT_PRECISION = 6

# The picker in the UI shows a handful of candidates, not a page of them.
MAX_GEOCODE_RESULTS = 5

# How each API mode maps onto MOTIS query parameters.
_DIRECT_MODES: dict[str, str] = {"car": "CAR", "bike": "BIKE", "walk": "WALK"}

# `one-to-many` routes on the street network. Its `many` list is capped at 128
# by the server ("onetomany_max_many"), which is what the candidate budget in
# services/nearby.py is sized against.
ONE_TO_MANY_MAX = 128
_STREET_MODES: dict[str, str] = {"walk": "WALK", "bike": "BIKE"}

# Enough precision that two points on one parcel share a cache entry (4 decimal
# places is about 11 m) without ever merging two different plots.
_ORIGIN_PRECISION = 4


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
        # Separate directories, because these answers stay valid far longer
        # than a routed itinerary does.
        self.stops_cache = DiskCache(
            app_settings.cache_dir / "motis-stops", ttl_s=settings.stops_cache_ttl_s
        )
        self.matrix_cache = DiskCache(
            app_settings.cache_dir / "motis-matrix", ttl_s=settings.matrix_cache_ttl_s
        )
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
                user_agent=self.app_settings.contact_user_agent,
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

    async def _get_json(
        self, path: str, params: dict[str, Any], cache_key: str, cache: DiskCache
    ) -> Any:
        """One cached GET against MOTIS, returning parsed JSON."""

        cached = cache.get_json(cache_key)
        if cached is not None:
            return cached
        async with self._semaphore:
            response = await request(
                "GET",
                f"{self.settings.base_url.rstrip('/')}{path}",
                service=SERVICE_NAME,
                advice=NEARBY_ADVICE,
                timeout_s=self.settings.timeout_s,
                user_agent=self.app_settings.contact_user_agent,
                params=params,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise UpstreamError(
                f"{SERVICE_NAME} hat kein gültiges JSON geliefert. {NEARBY_ADVICE}"
            ) from exc
        cache.set_json(cache_key, payload)
        return payload

    async def stops_in_box(
        self, south: float, west: float, north: float, east: float
    ) -> list[dict[str, Any]]:
        """Every stop in a bounding box, one entry per physical stop.

        Two things about this endpoint, both measured (docs/research/poi.md § 3.1):
        ``min``/``max`` are **lat,lon** in that order, and ``grouped=true`` is
        not optional -- without it the same stop comes back once per GTFS feed
        (115 entries instead of 27 over Leipzig centre). The ``modes`` query
        parameter validates its enum and is then ignored, so the filtering
        happens here on each stop's own ``modes`` array.
        """

        params = {
            "min": f"{south:.5f},{west:.5f}",
            "max": f"{north:.5f},{east:.5f}",
            "grouped": "true",
        }
        payload = await self._get_json(
            "/api/v6/map/stops",
            params,
            f"stops:{repr(sorted(params.items()))}",
            self.stops_cache,
        )
        if not isinstance(payload, list):
            return []
        return [entry for entry in payload if isinstance(entry, dict)]

    async def stop_routes(self, stop_id: str) -> list[dict[str, Any]]:
        """The lines calling at one stop, with mode, short name and operator."""

        params = {"stopId": stop_id}
        payload = await self._get_json(
            "/api/v6/stop", params, f"stop:{stop_id}", self.stops_cache
        )
        routes = payload.get("routes") if isinstance(payload, dict) else None
        if not isinstance(routes, list):
            return []
        return [entry for entry in routes if isinstance(entry, dict)]

    async def travel_time_matrix(
        self,
        origin: Koordinate,
        destinations: list[Koordinate],
        mode: Umgebungsmodus = "walk",
        max_time_s: int = 5400,
        max_matching_distance_m: int = 250,
    ) -> list[tuple[int, int] | None]:
        """Street-network travel time from one origin to many destinations.

        One request for the lot: 128 destinations cost the same 148 ms as one,
        against eight separate ``/api/v6/plan`` calls at 1 523 ms. That factor
        is why this is here rather than a loop over ``route()`` -- Transitous is
        a volunteer service and asks to be treated as one.

        Returns ``(duration_s, distance_m)`` per destination, positionally
        aligned with ``destinations``; ``None`` where MOTIS answered ``{}``,
        which is its way of saying "not reachable on this network at all".

        Two traps: the coordinate separator is a **semicolon**, not a comma (a
        comma is rejected as "not a valid geo coordinate"), and repeated
        ``many`` parameters on a GET are silently collapsed to one -- verified
        29.08.2026, three ``many`` values returned a single duration. The POST
        form takes a JSON array and is the only one that answers all of them.
        """

        if not destinations:
            return []
        if len(destinations) > ONE_TO_MANY_MAX:
            raise ValueError(f"one-to-many accepts at most {ONE_TO_MANY_MAX} destinations.")

        body: dict[str, Any] = {
            "one": f"{origin.lat};{origin.lon}",
            "many": [f"{point.lat};{point.lon}" for point in destinations],
            "mode": _STREET_MODES[mode],
            "max": int(max_time_s),
            # Required, not optional: leaving it out is answered with
            # "key maxMatchingDistance not found".
            "maxMatchingDistance": int(max_matching_distance_m),
            "arriveBy": False,
            "withDistance": True,
        }
        cache_key = "onetomany:" + repr(
            (
                round(origin.lat, _ORIGIN_PRECISION),
                round(origin.lon, _ORIGIN_PRECISION),
                body["many"],
                body["mode"],
                body["max"],
                body["maxMatchingDistance"],
            )
        )
        payload = self.matrix_cache.get_json(cache_key)
        if payload is None:
            async with self._semaphore:
                response = await request(
                    "POST",
                    f"{self.settings.base_url.rstrip('/')}/api/v1/one-to-many",
                    service=SERVICE_NAME,
                    advice=NEARBY_ADVICE,
                    timeout_s=self.settings.timeout_s,
                    user_agent=self.app_settings.contact_user_agent,
                    json=body,
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise UpstreamError(
                    f"{SERVICE_NAME} hat kein gültiges JSON geliefert. {NEARBY_ADVICE}"
                ) from exc
            self.matrix_cache.set_json(cache_key, payload)

        results: list[tuple[int, int] | None] = []
        for index in range(len(destinations)):
            entry = payload[index] if isinstance(payload, list) and index < len(payload) else None
            duration = entry.get("duration") if isinstance(entry, dict) else None
            if duration is None:
                results.append(None)
                continue
            distance = entry.get("distance")
            results.append((int(round(float(duration))), int(round(float(distance or 0)))))
        return results

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
                    user_agent=self.app_settings.contact_user_agent,
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
