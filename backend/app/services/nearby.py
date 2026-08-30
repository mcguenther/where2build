""""Wie weit ist die nächste Schule?" -- everyday destinations around a plot.

Two sources, because no single one answers the question well
(``docs/research/poi.md``):

* **Stops come from the timetable**, through MOTIS. It knows what actually
  calls at a stop and with which mode, so tram, S-Bahn, bus and railway station
  separate cleanly. OpenStreetMap cannot do this in Saxony at all -- there is
  no S-Bahn tag in the whole state, `service=suburban` has zero objects.
* **Everything else comes from a local OSM index** (``app/poi_index.py``),
  built offline -- or, on a server that has never built one, from a live
  Overpass query (``services/overpass.py``, opt-in). The name-indexed geocoders
  are no alternative to either: 88 % of Saxon playgrounds have no name to be
  indexed under.

Both halves are ranked by **walking time, never by air distance**. That is not
pedantry: measured in Dresden-Johannstadt, the nearest playground by air, 172 m
away, cannot be walked to at all -- the Elbe is in between and the crossing is a
ferry -- and detour ratios reach 2.88. One extra request buys an answer that is
simply correct instead of plausibly wrong.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Iterable, Sequence

from ..errors import AppError
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
from .overpass import OverpassService

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

# One physical stop serves several of these -- the City-Tunnel halts in Leipzig
# carry REGIONAL_RAIL and SUBURBAN, so they are a Bahnhof *and* an S-Bahn-Halt.
# They are listed once and labelled with the first of these the caller asked
# for: longest range first, the same order `_stop_kind` lists the modes in.
# Note what this is NOT: REGIONAL_RAIL alone is a Bahnhof and nothing else.
# Leipzig-Liebertwolkwitz is served by RB113 to Geithain, which is a regional
# train, not an S-Bahn -- real S-Bahn stops carry SUBURBAN in addition.
KATEGORIE_RANG: tuple[str, ...] = ("bahnhof", "sbahn", "tram", "bus")

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

# When the live source was asked and did not answer, the category is unavailable
# for a third reason -- neither "kein Datenbestand" nor "nichts gefunden". The
# sentence comes from the service that failed and already says what to do.


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

    def __init__(
        self,
        settings: NearbySettings,
        motis: MotisService,
        overpass: OverpassService | None = None,
    ) -> None:
        self.settings = settings
        self.motis = motis
        self.overpass = overpass
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
        """What ``/api/health`` reports about the six OpenStreetMap categories.

        ``konfiguriert`` answers one question: can this server say anything at
        all about schools, parks and the rest? A live Overpass source answers it
        as well as a built index does, so it counts -- and ``quelle`` says which
        of the two the frontend is going to get.
        """

        overpass = self.overpass.status() if self.overpass is not None else {"aktiv": False}
        index = self.index
        if index is None:
            return {
                "konfiguriert": bool(overpass["aktiv"]),
                "quelle": "overpass" if overpass["aktiv"] else None,
                "pfad": str(self.settings.poi_index_path),
                "fehler": self._index_error,
                "overpass": overpass,
            }
        return {
            "konfiguriert": True,
            "quelle": "index",
            "pfad": str(index.path or self.settings.poi_index_path),
            "anzahl": index.count,
            "datenstand": index.datenstand,
            "overpass": overpass,
        }

    # -- candidates --------------------------------------------------------

    def _poi_candidates(
        self,
        index: PoiIndex,
        kategorie: str,
        origin: Koordinate,
        radius_m: int,
        limit: int,
        quelle: str,
    ) -> list[_Candidate]:
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
                    quelle=quelle,
                    osm_id=entry.osm_id,
                )
            )
        return candidates

    async def _poi_source(
        self, kategorien: list[str], origin: Koordinate, radius_m: int
    ) -> tuple[PoiIndex | None, str, str | None]:
        """Which source answers the OSM categories, and what to say if none can.

        Index first, live Overpass second, nothing third -- in that order and
        never both. The built index is the production answer; the live query is
        the stand-in for a server that has none, and is off unless someone set
        ``OVERPASS_ENABLED``.

        Returns ``(index, quelle, fehler)``. ``fehler`` is a German sentence and
        is set only when a source was asked and did not answer -- which is a
        third statement, neither "kein Datenbestand" nor "nichts gefunden".
        """

        index = self.index
        if index is not None or not kategorien:
            return index, "osm", None
        if self.overpass is None or not self.overpass.enabled:
            return None, "osm", None
        try:
            return await self.overpass.places(origin, radius_m, kategorien), "overpass", None
        except AppError as exc:
            # An overloaded or rate-limited Overpass must not take the stops
            # down with it: they come from the timetable and are unaffected.
            logger.warning("Overpass did not answer: %s", exc.message)
            return None, "overpass", exc.message

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

        index, poi_quelle, poi_fehler = await self._poi_source(
            poi_kategorien, payload.origin, payload.umkreis_m
        )
        for kategorie in poi_kategorien:
            if index is None:
                status[kategorie] = KategorieStatus(
                    kategorie=kategorie,
                    verfuegbar=False,
                    hinweis=poi_fehler or KEIN_INDEX_HINWEIS,
                )
                continue
            pools[kategorie] = self._poi_candidates(
                index, kategorie, payload.origin, payload.umkreis_m, per_category, poi_quelle
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

        shortlist: dict[str, list[UmgebungTreffer]] = {}
        for kategorie in requested:
            if kategorie in status:
                continue
            found = hits.get(kategorie, [])
            # Reachable first, then by walking time; an unreachable hit still
            # travels, ordered by air distance, because "die nächste Schule
            # liegt jenseits des Flusses" is an answer worth showing.
            found.sort(key=_rank)
            shortlist[kategorie] = found[: payload.treffer_je_kategorie]

        treffer = _merge_duplicate_stops(shortlist, requested)

        for kategorie in requested:
            if kategorie in status:
                continue
            # Counted over `kategorien`, not over the label: a stop listed once
            # as `bahnhof` still counts for `sbahn` when the S-Bahn calls there.
            anzahl = sum(1 for hit in treffer if kategorie in hit.kategorien)
            status[kategorie] = KategorieStatus(
                kategorie=kategorie,
                verfuegbar=True,
                anzahl=anzahl,
                hinweis=(
                    None
                    if anzahl
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
            # Every category this stop was listed for, not just its label: the
            # S-Bahn lines of a merged Bahnhof/S-Bahn stop belong on it too.
            wanted = {
                mode
                for kategorie in (hit.kategorien or [hit.kategorie])
                for mode in TRANSIT_MODES.get(kategorie, ())
            }
            names = {
                str(route.get("routeShortName") or "").strip()
                for route in await self.motis.stop_routes(hit.stop_id)
                if str(route.get("mode") or "") in wanted
            }
            hit.linien = sorted((name for name in names if name), key=_line_sort_key)


def _rank(hit: UmgebungTreffer) -> tuple[bool, int, int]:
    """Reachable first, then by walking time, then by air distance."""

    return (not hit.erreichbar, hit.duration_s or 0, hit.luftlinie_m)


def _primary_category(kategorien: list[str]) -> str:
    """The one category a row is labelled with when it satisfies several."""

    for kategorie in KATEGORIE_RANG:
        if kategorie in kategorien:
            return kategorie
    return kategorien[0]


def _merge_duplicate_stops(
    shortlist: dict[str, list[UmgebungTreffer]], requested: Sequence[str]
) -> list[UmgebungTreffer]:
    """One row per physical place, carrying every category it satisfies.

    Verified around Wilhelm-Leuschner-Platz: Leipzig Markt and Leipzig
    Bayerischer Bahnhof each carry REGIONAL_RAIL *and* SUBURBAN, so both were
    listed twice -- four rows for two stations. The categorisation was right and
    the list was still noise. Merging happens after the per-category ranking, so
    asking only for `sbahn` gives exactly the same S-Bahn stops as before; what
    changes is only that asking for both no longer repeats them.

    Stops are the same place when they share a ``stop_id`` -- MOTIS' ``grouped``
    id, one per physical stop across all feeds. Places from OpenStreetMap belong
    to exactly one category and are never merged.
    """

    merged: dict[tuple[str, Any], UmgebungTreffer] = {}
    order: list[tuple[str, Any]] = []
    for kategorie in requested:
        for position, hit in enumerate(shortlist.get(kategorie, [])):
            key = ("stop", hit.stop_id) if hit.stop_id else ("einzeln", (kategorie, position))
            first = merged.get(key)
            if first is None:
                hit.kategorien = [hit.kategorie]
                merged[key] = hit
                order.append(key)
            elif kategorie not in first.kategorien:
                first.kategorien.append(kategorie)  # type: ignore[arg-type]

    for key in order:
        hit = merged[key]
        hit.kategorie = _primary_category(list(hit.kategorien))  # type: ignore[assignment]

    # Grouped by the label each row ended up with, in the order the categories
    # were asked for -- the frontend renders `treffer` as one flat list.
    treffer: list[UmgebungTreffer] = []
    for kategorie in requested:
        block = [merged[key] for key in order if merged[key].kategorie == kategorie]
        block.sort(key=_rank)
        treffer.extend(block)
    return treffer


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
        kategorien=[candidate.kategorie],  # type: ignore[list-item]
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
    "KATEGORIE_RANG",
    "MODE_LABELS",
    "NearbyService",
    "TRANSIT_CATEGORIES",
    "TRANSIT_MODES",
    "bounding_box",
]
