""""Wie weit ist die nächste Schule?" -- everyday destinations around a plot.

Two sources, because no single one answers the question well
(``docs/research/poi.md``):

* **Stops come from the timetable**, through MOTIS. It knows what actually
  calls at a stop and with which mode, so tram, S-Bahn, bus and railway station
  separate cleanly. OpenStreetMap cannot do this in Saxony at all -- there is
  no S-Bahn tag in the whole state, `service=suburban` has zero objects.
* **Everything else comes from a local OSM index** (``app/poi_index.py``),
  built offline. The public Overpass instances forbid exactly our kind of use,
  and the name-indexed geocoders miss most of the objects: 88 % of Saxon
  playgrounds have no name to be indexed under.

Both halves are ranked by **walking time, never by air distance**. That is not
pedantry: measured in Dresden-Johannstadt, the nearest playground by air, 172 m
away, cannot be walked to at all -- the Elbe is in between and the crossing is a
ferry -- and detour ratios reach 2.88. One extra request buys an answer that is
simply correct instead of plausibly wrong.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Iterable

from ..poi_index import POI_CATEGORIES, PoiEntry, PoiIndex, haversine_m, load_index
from ..schemas import (
    KATEGORIE_LABELS,
    Kategorie,
    KategorieStatus,
    Koordinate,
    NearbyRequest,
    NearbyResponse,
    UmgebungTreffer,
)
from ..settings import NearbySettings
from .motis import ONE_TO_MANY_MAX, MotisService

logger = logging.getLogger(__name__)

# Which MOTIS modes make a stop count as which category. The names are the
# service's own enum; SUBURBAN is what it calls the S-Bahn.
TRANSIT_MODES: dict[str, tuple[str, ...]] = {
    "tram": ("TRAM",),
    "sbahn": ("SUBURBAN",),
    "bus": ("BUS",),
    "bahnhof": (
        "REGIONAL_RAIL",
        "REGIONAL_FAST_RAIL",
        "LONG_DISTANCE",
        "HIGHSPEED_RAIL",
        "NIGHT_RAIL",
    ),
}

TRANSIT_CATEGORIES = tuple(TRANSIT_MODES)

# MOTIS' mode vocabulary in the words a user reads.
MODE_LABELS: dict[str, str] = {
    "TRAM": "Straßenbahn",
    "SUBURBAN": "S-Bahn",
    "SUBWAY": "U-Bahn",
    "BUS": "Bus",
    "COACH": "Fernbus",
    "REGIONAL_RAIL": "Regionalbahn",
    "REGIONAL_FAST_RAIL": "Regionalexpress",
    "LONG_DISTANCE": "Fernverkehr",
    "HIGHSPEED_RAIL": "Fernverkehr",
    "NIGHT_RAIL": "Nachtzug",
    "FERRY": "Fähre",
    "FUNICULAR": "Standseilbahn",
    "AERIAL_LIFT": "Seilbahn",
    "OTHER": "Sonstiges",
}

# How the answer explains a category it could not answer at all. Not an empty
# list: "hier gibt es keine Schule" and "dieser Server kennt keine Schulen" are
# different statements and only one of them is true.
KEIN_INDEX_HINWEIS = (
    "Für diese Kategorie ist auf dem Server kein Datenbestand eingerichtet — "
    "das Umgebungsverzeichnis aus OpenStreetMap fehlt. Es bedeutet nicht, dass "
    "es hier nichts gibt."
)

NICHTS_GEFUNDEN = "Im Umkreis von {umkreis} m wurde nichts gefunden."


def _thousands(value: int) -> str:
    """German thousands separator, without depending on a process locale."""

    return f"{value:,}".replace(",", ".")

NICHT_ERREICHBAR = "Nicht zu Fuß erreichbar — nur die Luftlinie ist bekannt."
NICHT_ERREICHBAR_RAD = "Mit dem Rad wurde kein Weg gefunden — nur die Luftlinie ist bekannt."

_METRES_PER_DEGREE_LAT = 111_320.0


def bounding_box(
    origin: Koordinate, radius_m: float, grid_deg: float = 0.0
) -> tuple[float, float, float, float]:
    """(south, west, north, east) around a point, optionally snapped to a grid.

    Snapping is what makes the stop cache worth having: two plots in the same
    village then ask for the same box instead of each cutting its own.
    """

    d_lat = radius_m / _METRES_PER_DEGREE_LAT
    d_lon = radius_m / max(1.0, _METRES_PER_DEGREE_LAT * math.cos(math.radians(origin.lat)))
    south, north = origin.lat - d_lat, origin.lat + d_lat
    west, east = origin.lon - d_lon, origin.lon + d_lon
    if grid_deg > 0:
        south = math.floor(south / grid_deg) * grid_deg
        west = math.floor(west / grid_deg) * grid_deg
        north = math.ceil(north / grid_deg) * grid_deg
        east = math.ceil(east / grid_deg) * grid_deg
    return south, west, north, east


def _stop_kind(modes: Iterable[str]) -> str | None:
    """What calls here, in German, longest-range first: "S-Bahn, Bus"."""

    order = (
        "HIGHSPEED_RAIL",
        "LONG_DISTANCE",
        "NIGHT_RAIL",
        "REGIONAL_FAST_RAIL",
        "REGIONAL_RAIL",
        "SUBURBAN",
        "SUBWAY",
        "TRAM",
        "FERRY",
        "FUNICULAR",
        "AERIAL_LIFT",
        "COACH",
        "BUS",
    )
    present = set(modes)
    labels: list[str] = []
    for mode in order:
        label = MODE_LABELS.get(mode)
        if mode in present and label and label not in labels:
            labels.append(label)
    for mode in sorted(present - set(order)):
        labels.append(MODE_LABELS.get(mode, mode.title()))
    return ", ".join(labels) or None


def _line_sort_key(short_name: str) -> tuple[int, int, str]:
    """Line numbers in the order a human expects: 2, 11, 15, S1, RB113."""

    digits = "".join(character for character in short_name if character.isdigit())
    return (0 if short_name[:1].isdigit() else 1, int(digits) if digits else 0, short_name)


class _Candidate:
    """A place on its way into the routing call, before it has a walking time."""

    __slots__ = (
        "art",
        "kategorie",
        "lat",
        "lon",
        "luftlinie_m",
        "modes",
        "name",
        "osm_id",
        "quelle",
        "stop_id",
    )

    def __init__(
        self,
        *,
        kategorie: str,
        lat: float,
        lon: float,
        luftlinie_m: float,
        quelle: str,
        name: str | None = None,
        art: str | None = None,
        osm_id: str | None = None,
        stop_id: str | None = None,
        modes: tuple[str, ...] = (),
    ) -> None:
        self.kategorie = kategorie
        self.lat = lat
        self.lon = lon
        self.name = name
        self.art = art
        self.luftlinie_m = luftlinie_m
        self.quelle = quelle
        self.osm_id = osm_id
        self.stop_id = stop_id
        self.modes = modes


class NearbyService:
    """The endpoint's whole flow: candidates, one routing call, ranking."""

    def __init__(self, settings: NearbySettings, motis: MotisService) -> None:
        self.settings = settings
        self.motis = motis
        self._index: PoiIndex | None = None
        self._index_error: str | None = None
        self._loaded = False

    # -- the index ---------------------------------------------------------

    @property
    def index(self) -> PoiIndex | None:
        """The POI index, loaded once. ``None`` when it was never built here."""

        if not self._loaded:
            self._loaded = True
            try:
                self._index = load_index(self.settings.poi_index_path)
            except (OSError, ValueError) as exc:
                # A broken file must not take the transit half down with it.
                logger.warning("POI index at %s unusable: %s", self.settings.poi_index_path, exc)
                self._index = None
                self._index_error = str(exc)
        return self._index

    def index_status(self) -> dict[str, Any]:
        """What ``/api/health`` reports about the index."""

        index = self.index
        if index is None:
            return {
                "konfiguriert": False,
                "pfad": str(self.settings.poi_index_path),
                "fehler": self._index_error,
            }
        return {
            "konfiguriert": True,
            "pfad": str(index.path or self.settings.poi_index_path),
            "anzahl": index.count,
            "datenstand": index.datenstand,
        }

    # -- candidates --------------------------------------------------------

    def _poi_candidates(
        self, kategorie: str, origin: Koordinate, radius_m: int, limit: int
    ) -> list[_Candidate]:
        index = self.index
        if index is None:
            return []
        candidates: list[_Candidate] = []
        for entry, distance in index.nearest(kategorie, origin.lat, origin.lon, radius_m, limit):
            candidates.append(
                _Candidate(
                    kategorie=kategorie,
                    lat=entry.lat,
                    lon=entry.lon,
                    name=entry.name,
                    art=self._poi_kind(entry),
                    luftlinie_m=distance,
                    quelle="osm",
                    osm_id=entry.osm_id,
                )
            )
        return candidates

    @staticmethod
    def _poi_kind(entry: PoiEntry) -> str | None:
        return entry.art or KATEGORIE_LABELS.get(entry.kategorie)

    async def _stop_candidates(
        self, kategorien: list[str], origin: Koordinate, radius_m: int, limit: int
    ) -> dict[str, list[_Candidate]]:
        south, west, north, east = bounding_box(origin, radius_m, self.settings.bbox_grid_deg)
        stops = await self.motis.stops_in_box(south, west, north, east)

        by_category: dict[str, list[_Candidate]] = {kategorie: [] for kategorie in kategorien}
        for stop in stops:
            lat, lon = stop.get("lat"), stop.get("lon")
            if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
                continue
            modes = tuple(str(mode) for mode in (stop.get("modes") or []))
            # The box was snapped to the cache grid and is a rectangle either
            # way, so the radius is applied here.
            distance = haversine_m(origin.lat, origin.lon, float(lat), float(lon))
            if distance > radius_m:
                continue
            for kategorie in kategorien:
                if not set(modes) & set(TRANSIT_MODES[kategorie]):
                    continue
                by_category[kategorie].append(
                    _Candidate(
                        kategorie=kategorie,
                        lat=float(lat),
                        lon=float(lon),
                        name=str(stop.get("name") or "").strip() or None,
                        art=_stop_kind(modes),
                        luftlinie_m=distance,
                        quelle="motis",
                        stop_id=str(stop.get("stopId") or "") or None,
                        modes=modes,
                    )
                )
        for kategorie, found in by_category.items():
            found.sort(key=lambda candidate: candidate.luftlinie_m)
            by_category[kategorie] = found[:limit]
        return by_category

    # -- the whole answer --------------------------------------------------

    async def nearby(self, payload: NearbyRequest) -> NearbyResponse:
        requested = list(payload.kategorien)
        poi_kategorien = [k for k in requested if k in POI_CATEGORIES]
        transit_kategorien = [k for k in requested if k in TRANSIT_CATEGORIES]

        # Route to six times as many candidates per category as are shown. Air
        # distance and walking time disagree from the first position onwards,
        # so the winner is regularly not the nearest one as the crow flies --
        # and a wider net costs nothing, since one call carries 128 of them.
        per_category = min(payload.treffer_je_kategorie * 6, self.settings.max_candidates)

        pools: dict[str, list[_Candidate]] = {}
        status: dict[str, KategorieStatus] = {}

        index = self.index
        for kategorie in poi_kategorien:
            if index is None:
                status[kategorie] = KategorieStatus(
                    kategorie=kategorie, verfuegbar=False, hinweis=KEIN_INDEX_HINWEIS
                )
                continue
            pools[kategorie] = self._poi_candidates(
                kategorie, payload.origin, payload.umkreis_m, per_category
            )

        if transit_kategorien:
            for kategorie, found in (
                await self._stop_candidates(
                    transit_kategorien, payload.origin, payload.umkreis_m, per_category
                )
            ).items():
                pools[kategorie] = found

        # Never below one slot per category: a configured budget smaller than
        # the number of categories would make a category with candidates report
        # "nichts gefunden", which is the one thing this endpoint must not do.
        budget = min(ONE_TO_MANY_MAX, max(self.settings.max_candidates, len(pools)))
        selected = _round_robin(pools, budget)

        durations: list[tuple[int, int] | None] = []
        if selected:
            durations = await self.motis.travel_time_matrix(
                payload.origin,
                [Koordinate(lat=c.lat, lon=c.lon) for c in selected],
                mode=payload.modus,
                max_time_s=self.settings.max_time_s,
                max_matching_distance_m=self.settings.max_matching_distance_m,
            )

        hits: dict[str, list[UmgebungTreffer]] = {kategorie: [] for kategorie in pools}
        for candidate, result in zip(selected, durations):
            hits[candidate.kategorie].append(_as_treffer(candidate, result, payload.modus))

        treffer: list[UmgebungTreffer] = []
        for kategorie in requested:
            if kategorie in status:
                continue
            found = hits.get(kategorie, [])
            # Reachable first, then by walking time; an unreachable hit still
            # travels, ordered by air distance, because "die nächste Schule
            # liegt jenseits des Flusses" is an answer worth showing.
            found.sort(key=lambda hit: (not hit.erreichbar, hit.duration_s or 0, hit.luftlinie_m))
            found = found[: payload.treffer_je_kategorie]
            treffer.extend(found)
            status[kategorie] = KategorieStatus(
                kategorie=kategorie,
                verfuegbar=True,
                anzahl=len(found),
                hinweis=(
                    None
                    if found
                    else NICHTS_GEFUNDEN.format(umkreis=_thousands(payload.umkreis_m))
                ),
            )

        if payload.linien:
            await self._attach_lines(treffer)

        return NearbyResponse(
            treffer=treffer,
            kategorien=[status[kategorie] for kategorie in requested],
            datenstand=index.datenstand if index is not None else None,
        )

    async def _attach_lines(self, treffer: list[UmgebungTreffer]) -> None:
        """Fill in the line numbers calling at each stop, one request per stop.

        Bounded on purpose: this is the only part of the answer whose cost grows
        with the number of hits, against a volunteer service that asks callers
        to be light on it.
        """

        budget = self.settings.max_line_lookups
        for hit in treffer:
            if hit.quelle != "motis" or not hit.stop_id:
                continue
            if budget <= 0:
                # `linien` stays None, so the answer says "nicht abgefragt"
                # rather than showing an empty list that reads as "keine Linie".
                break
            budget -= 1
            wanted = set(TRANSIT_MODES.get(hit.kategorie, ()))
            names = {
                str(route.get("routeShortName") or "").strip()
                for route in await self.motis.stop_routes(hit.stop_id)
                if str(route.get("mode") or "") in wanted
            }
            hit.linien = sorted((name for name in names if name), key=_line_sort_key)


def _round_robin(pools: dict[str, list[_Candidate]], budget: int) -> list[_Candidate]:
    """Fill the routing call fairly: every category gets its nearest first.

    ``one-to-many`` refuses more than 128 destinations, so with ten categories
    the budget has to be shared. Round-robin rather than an equal split, so a
    category with two candidates hands its unused places back instead of
    starving the ones that have more.
    """

    if budget <= 0:
        return []
    selected: list[_Candidate] = []
    depth = 0
    while len(selected) < budget:
        added = False
        for candidates in pools.values():
            if depth >= len(candidates):
                continue
            selected.append(candidates[depth])
            added = True
            if len(selected) >= budget:
                break
        if not added:
            break
        depth += 1
    return selected


def _as_treffer(
    candidate: _Candidate, result: tuple[int, int] | None, modus: str
) -> UmgebungTreffer:
    reachable = result is not None
    return UmgebungTreffer(
        kategorie=candidate.kategorie,  # type: ignore[arg-type]
        name=candidate.name,
        art=candidate.art,
        lat=candidate.lat,
        lon=candidate.lon,
        erreichbar=reachable,
        duration_s=result[0] if result else None,
        distance_m=result[1] if result else None,
        luftlinie_m=int(round(candidate.luftlinie_m)),
        quelle=candidate.quelle,  # type: ignore[arg-type]
        osm_id=candidate.osm_id,
        stop_id=candidate.stop_id,
        hinweis=(
            None if reachable else (NICHT_ERREICHBAR if modus == "walk" else NICHT_ERREICHBAR_RAD)
        ),
    )


# Categories this module can answer without the local index, kept next to the
# ones that need it so a reader sees the split in one place.
__all__ = [
    "MODE_LABELS",
    "NearbyService",
    "TRANSIT_CATEGORIES",
    "TRANSIT_MODES",
    "bounding_box",
]
