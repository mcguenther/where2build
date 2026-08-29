"""The local point-of-interest index -- everyday destinations from OpenStreetMap.

MOTIS answers "which is the nearest stop" from the timetable itself (see
``services/nearby.py``); it knows nothing about schools, parks or supermarkets.
Those come from an OSM extract that ``scripts/build_poi_index.py`` turns into a
flat point file, which this module loads into a coarse lat/lon grid.

Two decisions are worth stating, both from ``docs/research/poi.md``:

* The extract is a **build artefact and may be absent.** That is a first-class
  answer, not an error -- a caller has to be able to tell "this server holds no
  such data" from "nothing within the search radius". An empty list would read
  as the second when it is the first.
* The public Overpass instances are **not** an alternative at request time.
  Their manual names "an app for more than just OSM mappers relying on the
  public instances as backend" as problematic behaviour, and the rate limit is
  per IP -- ours, shared by every user.
"""

from __future__ import annotations

import gzip
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

# Categories served from this index. The transit ones live in services/nearby.py
# because they come from the timetable, not from OSM.
POI_CATEGORIES = ("schule", "kindergarten", "park", "spielplatz", "supermarkt", "arzt")

# Grid cell for the lookup, in degrees. 0.02 deg is roughly 2.2 km north-south
# and 1.4 km east-west at Saxon latitudes -- a 3 km query touches ~20 cells.
_CELL_DEG = 0.02

_EARTH_RADIUS_M = 6_371_008.8

# Two objects of the same category this close together are the same place seen
# twice: OSM maps a school as the named node *and* as the way of its grounds.
DEDUPE_RADIUS_M = 60.0

# No OSM tag tells a Grundschule from a Gymnasium in Saxony -- `school:DE` does
# not exist here at all and `isced:level` covers under a fifth of the objects,
# in two incompatible spellings. The type is in the name, every time, so that is
# what is read. The result is a hint shown next to the name, never a fact.
_SCHOOL_KINDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"grundschule", re.I), "Grundschule"),
    (re.compile(r"oberschule|mittelschule", re.I), "Oberschule"),
    (re.compile(r"gymnasium", re.I), "Gymnasium"),
    (re.compile(r"gemeinschaftsschule", re.I), "Gemeinschaftsschule"),
    (re.compile(r"f(ö|oe)rderschule|f(ö|oe)rderzentrum", re.I), "Förderschule"),
    (re.compile(r"beruf(liche|s)?[a-zäöüß]*\s*(schul|zentrum)", re.I), "Berufliche Schule"),
    (re.compile(r"berufsschule|berufsfachschule|fachoberschule", re.I), "Berufliche Schule"),
    (re.compile(r"waldorfschule", re.I), "Freie Schule"),
)


def classify_school(name: str | None) -> str | None:
    """The school type as far as the name gives it away, or ``None``."""

    if not name:
        return None
    for pattern, label in _SCHOOL_KINDS:
        if pattern.search(name):
            return label
    return None


def haversine_m(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Great-circle distance in metres. Air distance only -- never shown to a user."""

    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    d_phi = phi_b - phi_a
    d_lambda = math.radians(lon_b - lon_a)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


@dataclass(frozen=True, slots=True)
class PoiEntry:
    """One mapped place. ``name`` is routinely absent: only 11.8 % of Saxon
    playgrounds and 31.2 % of its parks carry one."""

    kategorie: str
    lat: float
    lon: float
    name: str | None = None
    art: str | None = None
    osm_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"kategorie": self.kategorie, "lat": self.lat, "lon": self.lon}
        if self.name:
            data["name"] = self.name
        if self.art:
            data["art"] = self.art
        if self.osm_id:
            data["osm_id"] = self.osm_id
        return data


def _same_place(a: PoiEntry, b: PoiEntry) -> bool:
    """Whether two nearby entries of one category describe one place.

    An unnamed object next to a named one is the grounds around the building.
    Two differently named schools 50 m apart are two schools and both are kept.
    """

    if not a.name or not b.name:
        return True
    first, second = a.name.casefold(), b.name.casefold()
    return first == second or first.startswith(second) or second.startswith(first)


def deduplicate(entries: Iterable[PoiEntry]) -> list[PoiEntry]:
    """Collapse the same place mapped several times, keeping the named object.

    Input order decides which survives, so callers sort by air distance first;
    a named entry always beats an unnamed one at the same spot.
    """

    kept: list[PoiEntry] = []
    for entry in sorted(entries, key=lambda item: (item.name is None,)):
        if any(
            other.kategorie == entry.kategorie
            and haversine_m(entry.lat, entry.lon, other.lat, other.lon) <= DEDUPE_RADIUS_M
            and _same_place(entry, other)
            for other in kept
        ):
            continue
        kept.append(entry)
    return kept


def _cell(lat: float, lon: float) -> tuple[int, int]:
    return int(math.floor(lat / _CELL_DEG)), int(math.floor(lon / _CELL_DEG))


class PoiIndex:
    """Points from the extract, bucketed into a lat/lon grid.

    22 622 features for all of Saxony fit in memory several times over, so this
    needs neither PostGIS nor an R-tree -- a grid keeps a radius query down to
    the couple of dozen cells it actually touches.
    """

    def __init__(
        self,
        entries: Iterable[PoiEntry],
        *,
        datenstand: str | None = None,
        quelle: str | None = None,
        path: Path | None = None,
    ) -> None:
        self.datenstand = datenstand
        self.quelle = quelle
        self.path = path
        self._grid: dict[tuple[int, int], list[PoiEntry]] = {}
        self._counts: dict[str, int] = {}
        self.count = 0
        for entry in entries:
            self._grid.setdefault(_cell(entry.lat, entry.lon), []).append(entry)
            self._counts[entry.kategorie] = self._counts.get(entry.kategorie, 0) + 1
            self.count += 1

    @property
    def counts(self) -> dict[str, int]:
        return dict(self._counts)

    def _cells_around(self, lat: float, lon: float, radius_m: float) -> Iterator[list[PoiEntry]]:
        d_lat = radius_m / 111_320.0
        d_lon = radius_m / max(1.0, 111_320.0 * math.cos(math.radians(lat)))
        lat_from, lon_from = _cell(lat - d_lat, lon - d_lon)
        lat_to, lon_to = _cell(lat + d_lat, lon + d_lon)
        for lat_cell in range(lat_from, lat_to + 1):
            for lon_cell in range(lon_from, lon_to + 1):
                bucket = self._grid.get((lat_cell, lon_cell))
                if bucket:
                    yield bucket

    def nearest(
        self, kategorie: str, lat: float, lon: float, radius_m: float, limit: int
    ) -> list[tuple[PoiEntry, float]]:
        """The ``limit`` nearest entries of one category, by air distance.

        Air distance is only how the candidate list is cut down; the order the
        user sees comes from the walking times MOTIS returns for these points.
        """

        found: list[tuple[PoiEntry, float]] = []
        for bucket in self._cells_around(lat, lon, radius_m):
            for entry in bucket:
                if entry.kategorie != kategorie:
                    continue
                distance = haversine_m(lat, lon, entry.lat, entry.lon)
                if distance <= radius_m:
                    found.append((entry, distance))
        found.sort(key=lambda pair: pair[1])
        deduped = deduplicate(entry for entry, _ in found)
        keep = set(map(id, deduped))
        return [pair for pair in found if id(pair[0]) in keep][:limit]


def read_index_file(path: Path) -> dict[str, Any]:
    """Read the build artefact. ``.gz`` is unpacked transparently."""

    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:  # type: ignore[operator]
        payload = json.load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("eintraege"), list):
        raise ValueError(f"{path} is not a POI index file (no 'eintraege' array).")
    return payload


def load_index(path: Path) -> PoiIndex | None:
    """Load the index, or ``None`` when it has not been built on this server.

    A malformed file is treated like a missing one and logged by the caller:
    the endpoint must still answer for the transit categories.
    """

    if not path.is_file():
        return None
    payload = read_index_file(path)
    entries = [
        PoiEntry(
            kategorie=str(item["kategorie"]),
            lat=float(item["lat"]),
            lon=float(item["lon"]),
            name=item.get("name") or None,
            art=item.get("art") or None,
            osm_id=item.get("osm_id") or None,
        )
        for item in payload["eintraege"]
        if item.get("kategorie") in POI_CATEGORIES
    ]
    return PoiIndex(
        entries,
        datenstand=payload.get("datenstand") or None,
        quelle=payload.get("quelle") or None,
        path=path,
    )
