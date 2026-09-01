"""The official Saxon address coordinates -- the GeoSN's Hauskoordinaten.

Until now ``POST /api/geocode`` had nothing but the routing geocoder, and said
so in its own answer: MOTIS knows stops and it knows OpenStreetMap, so it
answers a Saxon street name with a Bavarian village often enough that the
endpoint hands back a list of labelled candidates rather than one coordinate.

Saxony publishes the other half as a plain download: every address in the state
with the coordinate the cadastre holds for it. ``scripts/build_address_index.py``
turns that into the file this module reads. What it buys:

* the house number is real. MOTIS interpolates along a street where it has no
  building; a Hauskoordinate is the point the surveying office recorded.
* it works with Transitous down, and without asking a volunteer service for
  something an offline file answers.

Two decisions worth stating:

* The built file is a **build artefact and may be absent** -- the same
  first-class answer as the POI index. Absent means geocoding falls back to
  MOTIS alone, which is what it did before, and ``/api/health`` says so.
* Addresses are grouped **by street**, not kept as 990 090 loose records. A
  street is the unit a query names and the unit an answer is filtered by, the
  grouping shrinks the file by the repeated place columns, and 51 408 groups
  keep the per-load work in the thousands rather than the millions.
"""

from __future__ import annotations

import gzip
import json
import math
import re
from array import array
from bisect import bisect_left
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

# The folding rules are the district directory's, deliberately shared: a user
# who reaches Mölkau by typing "moelkau" in one input mask must reach
# Mölkauer Straße the same way in the other.
from .gemarkung_index import fold, fold_expanded
from .poi_index import haversine_m

# Coordinates are stored as integers, 1e-6 deg -- about 0,11 m north-south,
# finer than the data. Six decimals is also what the source gives in metres.
MICRODEGREES = 1_000_000

# Grid cell for the reverse lookup, in degrees. 0.005 deg is roughly 550 m
# north-south and 350 m east-west here, so "which address is this" touches
# nine cells and scans a few streets.
_CELL_DEG = 0.005

# House numbers of one street, joined into a single string. 990 090 separate
# Python strings cost about 50 MB of heap for text that is never all needed at
# once; one string per street is 51 408 of them and splits in microseconds.
_NUMBER_SEPARATOR = ";"

# "Kirchstr. 5", "Kirchstr 5" and "Kirchstraße 5" are the same address typed
# three ways. Applied to the indexed name as well as to the query, so both
# sides meet in the middle.
_ABBREVIATION = re.compile(r"str\.?(?=\s|,|$)")

# Everything that is not a letter or a digit separates words: a hyphen in
# Karl-Marx-Straße is a space to whoever types it.
_SEPARATORS = re.compile(r"[^0-9a-z]+")

_HOUSE_NUMBER = re.compile(r"^(\d{1,4})([a-z]{0,2})$")
_POSTCODE = re.compile(r"^\d{5}$")

# Shortest span of query text that may be matched as the beginning of a street
# name. "am" or "an der" name hundreds of streets and rank none of them.
_MIN_PREFIX_LENGTH = 4
# And how many names one prefix may pull in before it stops being a search.
_MAX_PREFIX_NAMES = 40


def normalise(text: str) -> str:
    """Fold, expand "Str.", and reduce every separator to a single space."""

    return _SEPARATORS.sub(" ", _ABBREVIATION.sub("strasse", fold(text))).strip()


def normalise_expanded(text: str) -> str:
    """The same with the umlauts written out, so "Moelkauer" finds "Mölkauer"."""

    return _SEPARATORS.sub(" ", _ABBREVIATION.sub("strasse", fold_expanded(text))).strip()


def house_number(hnr: str, adz: str) -> str:
    """The number as it is written on the house: 3 + "a" -> "3a"."""

    return f"{hnr.strip()}{adz.strip()}"


@dataclass(frozen=True, slots=True)
class AddressHit:
    """One official address.

    German field names throughout: these mirror the columns of the source file
    (``str``, ``hnr``, ``postplz``, ``postonm``, ``postott``, ``gmd``) and go
    on to the wire in the same spelling.
    """

    strasse: str
    postplz: str
    postonm: str
    lat: float
    lon: float
    hnr: str | None = None
    postott: str | None = None
    gmd: str | None = None
    # How many addresses the street has, on a hit that names no house number.
    anzahl: int = 1

    @property
    def name(self) -> str:
        return f"{self.strasse} {self.hnr}" if self.hnr else self.strasse

    @property
    def beschreibung(self) -> str:
        place = f"{self.postplz} {self.postonm}"
        if self.postott and self.postott != self.postonm:
            place = f"{place}, {self.postott}"
        if self.hnr:
            return f"{place} · amtliche Hauskoordinate"
        return f"{place} · {self.anzahl} amtliche Hausnummern"


@dataclass(slots=True)
class StreetGroup:
    """One street within one postal place, with its house numbers.

    The three parallel sequences are index-aligned: ``numbers[i]`` sits at
    ``lat[i]``/``lon[i]``.
    """

    strasse: str
    postplz: str
    postonm: str
    postott: str | None
    gmd: str | None
    numbers: str
    lat: array
    lon: array
    _split: list[str] | None = field(default=None, repr=False, compare=False)

    def __len__(self) -> int:
        return len(self.lat)

    @property
    def house_numbers(self) -> list[str]:
        if self._split is None:
            self._split = self.numbers.split(_NUMBER_SEPARATOR)
        return self._split

    def position(self, i: int) -> tuple[float, float]:
        return self.lat[i] / MICRODEGREES, self.lon[i] / MICRODEGREES

    def hit(self, i: int) -> AddressHit:
        lat, lon = self.position(i)
        return AddressHit(
            strasse=self.strasse,
            postplz=self.postplz,
            postonm=self.postonm,
            postott=self.postott,
            gmd=self.gmd,
            hnr=self.house_numbers[i],
            lat=lat,
            lon=lon,
        )

    def representative(self) -> AddressHit:
        """The street as a whole, placed at the address nearest its middle.

        Deliberately not the mean of the coordinates: that point can fall in a
        neighbour's garden or, on a bent street, outside the street altogether.
        An address that exists is always somewhere the street is.
        """

        mid_lat = sum(self.lat) / len(self.lat) / MICRODEGREES
        mid_lon = sum(self.lon) / len(self.lon) / MICRODEGREES
        best = min(
            range(len(self.lat)),
            key=lambda i: haversine_m(mid_lat, mid_lon, *self.position(i)),
        )
        lat, lon = self.position(best)
        return AddressHit(
            strasse=self.strasse,
            postplz=self.postplz,
            postonm=self.postonm,
            postott=self.postott,
            gmd=self.gmd,
            hnr=None,
            lat=lat,
            lon=lon,
            anzahl=len(self.lat),
        )

    @property
    def place_text(self) -> str:
        parts = (self.postonm, self.postott or "", self.gmd or "")
        return normalise_expanded(" ".join(parts))


def _cell(lat: float, lon: float) -> tuple[int, int]:
    return int(math.floor(lat / _CELL_DEG)), int(math.floor(lon / _CELL_DEG))


class AddressIndex:
    """Streets by name, with a lazy grid for the reverse question.

    The name lookup is a dictionary because an address query names its street
    exactly far more often than not; the sorted key list behind it turns a
    half-typed name into a prefix range. Neither needs the coordinates, which
    is why the grid is only built when something actually asks for it -- today
    nothing on the request path does.
    """

    def __init__(
        self,
        groups: Iterable[StreetGroup],
        *,
        stand: str | None = None,
        quelle: str | None = None,
        path: Path | None = None,
    ) -> None:
        self.stand = stand
        self.quelle = quelle
        self.path = path
        self.groups = list(groups)
        self.count = sum(len(group) for group in self.groups)
        self._by_name: dict[str, list[int]] = {}
        for position, group in enumerate(self.groups):
            for key in {normalise(group.strasse), normalise_expanded(group.strasse)}:
                self._by_name.setdefault(key, []).append(position)
        self._names = sorted(self._by_name)
        self._grid: dict[tuple[int, int], list[int]] | None = None

    def __len__(self) -> int:
        return self.count

    @property
    def street_count(self) -> int:
        return len(self.groups)

    # -- text -> candidates -------------------------------------------------

    def search(
        self,
        text: str,
        bias: tuple[float, float] | None = None,
        limit: int = 5,
    ) -> list[AddressHit]:
        """Official addresses for a typed street and house number, best first.

        An empty list is the ordinary answer for "Bahnhof Wurzen" or for an
        address outside Saxony -- this index holds houses, and the caller has
        the routing geocoder for everything else.
        """

        tokens = normalise(text).split()
        expanded = normalise_expanded(text).split()
        if not tokens:
            return []

        match = self._match_street(tokens, expanded)
        if match is None:
            return []
        start, end, positions = match

        rest = tokens[:start] + tokens[end:]
        number = _adjacent_number(tokens, start, end)
        postcode = next((token for token in rest if _POSTCODE.match(token)), None)
        place = [
            token
            for token in expanded[:start] + expanded[end:]
            if not _POSTCODE.match(token) and not _HOUSE_NUMBER.match(token)
        ]

        groups = [self.groups[position] for position in positions]
        if postcode:
            narrowed = [group for group in groups if group.postplz == postcode]
            # A postcode that matches nothing is a typo or a neighbouring one;
            # dropping every candidate over it would answer worse than ignoring it.
            groups = narrowed or groups

        scored = [(group, _place_score(group, place)) for group in groups]
        best_place = max((score for _, score in scored), default=0)
        if place and not best_place:
            # The query named a place and this street is in none of them. Five
            # "Bahnhof" in five other towns is not an answer to "Bahnhof
            # Wurzen" -- the routing geocoder gets that one.
            return []
        if best_place:
            scored = [pair for pair in scored if pair[1] == best_place]
        if len(scored) > limit and not place and not postcode and bias is None:
            # 110 streets are called Kirchstraße here. With nothing to tell
            # them apart -- no place, no postcode, no plot to measure from --
            # any four of them would be a guess wearing an official label.
            return []

        hits: list[tuple[tuple[Any, ...], AddressHit]] = []
        for group, score in scored:
            for exact, hit in _hits_for(group, number):
                distance = (
                    haversine_m(bias[0], bias[1], hit.lat, hit.lon)
                    if bias is not None
                    else 0.0
                )
                hits.append(((0 if exact else 1, -score, distance, hit.name), hit))
        hits.sort(key=lambda pair: pair[0])
        return [hit for _, hit in hits[:limit]]

    def _match_street(
        self, tokens: list[str], expanded: list[str]
    ) -> tuple[int, int, list[int]] | None:
        """The longest span of the query that names a street, exact before prefix."""

        spans = [
            (start, start + length)
            for length in range(len(tokens), 0, -1)
            for start in range(0, len(tokens) - length + 1)
        ]
        for start, end in spans:
            for words in (tokens, expanded):
                positions = self._by_name.get(" ".join(words[start:end]))
                if positions:
                    return start, end, positions
        for start, end in spans:
            for words in (tokens, expanded):
                prefix = " ".join(words[start:end])
                if len(prefix) < _MIN_PREFIX_LENGTH:
                    continue
                positions = self._by_prefix(prefix)
                if positions:
                    return start, end, positions
        return None

    def _by_prefix(self, prefix: str) -> list[int]:
        """Streets whose name begins with ``prefix``, or nothing when too many.

        Too many is not a match: "am" begins 900 street names and ranking them
        against each other would put an arbitrary one first.
        """

        positions: list[int] = []
        for offset in range(bisect_left(self._names, prefix), len(self._names)):
            name = self._names[offset]
            if not name.startswith(prefix):
                break
            positions.extend(self._by_name[name])
            if len(positions) > _MAX_PREFIX_NAMES:
                return []
        return positions

    # -- coordinate -> nearest address --------------------------------------

    def nearest(self, lat: float, lon: float, radius_m: float = 250.0) -> AddressHit | None:
        """The official address closest to a point, or ``None`` within radius.

        Not on the request path today; it is here because the grid it needs is
        twenty lines and the question ("what is this plot's address?") is one
        the data answers better than anything else this backend talks to.
        """

        best: tuple[float, AddressHit] | None = None
        for position in self._cells_around(lat, lon, radius_m):
            group = self.groups[position]
            for i in range(len(group)):
                point_lat, point_lon = group.position(i)
                distance = haversine_m(lat, lon, point_lat, point_lon)
                if distance <= radius_m and (best is None or distance < best[0]):
                    best = (distance, group.hit(i))
        return best[1] if best is not None else None

    def _cells_around(self, lat: float, lon: float, radius_m: float) -> Iterator[int]:
        grid = self._ensure_grid()
        d_lat = radius_m / 111_320.0
        d_lon = radius_m / max(1.0, 111_320.0 * math.cos(math.radians(lat)))
        lat_from, lon_from = _cell(lat - d_lat, lon - d_lon)
        lat_to, lon_to = _cell(lat + d_lat, lon + d_lon)
        seen: set[int] = set()
        for lat_cell in range(lat_from, lat_to + 1):
            for lon_cell in range(lon_from, lon_to + 1):
                for position in grid.get((lat_cell, lon_cell), ()):
                    if position not in seen:
                        seen.add(position)
                        yield position

    def _ensure_grid(self) -> dict[tuple[int, int], list[int]]:
        if self._grid is None:
            grid: dict[tuple[int, int], list[int]] = {}
            for position, group in enumerate(self.groups):
                for lat_micro, lon_micro in zip(group.lat, group.lon):
                    bucket = grid.setdefault(
                        _cell(lat_micro / MICRODEGREES, lon_micro / MICRODEGREES), []
                    )
                    # The points of one street arrive together, so comparing
                    # against the last entry is enough to keep it out twice.
                    if not bucket or bucket[-1] != position:
                        bucket.append(position)
            self._grid = grid
        return self._grid


def _adjacent_number(tokens: list[str], start: int, end: int) -> tuple[int, str] | None:
    """The house number written next to the street name, if there is one.

    After the name is the German order; before it is what a caller who pasted
    an English-style address gives, and costs one more comparison.
    """

    for position in (end, start - 1):
        if 0 <= position < len(tokens):
            match = _HOUSE_NUMBER.match(tokens[position])
            if match:
                return int(match.group(1)), match.group(2)
    return None


def _place_score(group: StreetGroup, place: list[str]) -> int:
    """How many of the query's leftover words name this street's place."""

    if not place:
        return 0
    text = group.place_text
    return sum(1 for token in place if token and token in text)


def _hits_for(
    group: StreetGroup, number: tuple[int, str] | None
) -> list[tuple[bool, AddressHit]]:
    """The addresses of one street a query asks for, each flagged exact or not.

    A number with no letter matches "12" as well as "12a" and "12b": the
    building is one of them and the data does not say which, so all are
    offered. A number that does carry a letter matches only itself.
    """

    if number is None:
        return [(False, group.representative())]
    wanted, suffix = number
    exact: list[tuple[bool, AddressHit]] = []
    variants: list[tuple[bool, AddressHit]] = []
    for i, written in enumerate(group.house_numbers):
        match = _HOUSE_NUMBER.match(written)
        if match is None or int(match.group(1)) != wanted:
            continue
        if match.group(2) == suffix:
            exact.append((True, group.hit(i)))
        elif not suffix:
            variants.append((False, group.hit(i)))
    return exact + variants


def read_index_file(path: Path) -> dict[str, Any]:
    """Read the build artefact. ``.gz`` is unpacked transparently."""

    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:  # type: ignore[operator]
        payload = json.load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("strassen"), list):
        raise ValueError(f"{path} is not an address index file (no 'strassen' array).")
    return payload


def load_index(path: Path) -> AddressIndex | None:
    """Load the index, or ``None`` when it has not been built on this server.

    ``None`` rather than an empty index: geocoding has to be able to say "this
    server holds no official addresses", which is a different sentence from
    "no address matched".
    """

    if not path.is_file():
        return None
    payload = read_index_file(path)
    groups = [
        StreetGroup(
            strasse=str(item["str"]),
            postplz=str(item["postplz"]),
            postonm=str(item["postonm"]),
            postott=(item.get("postott") or None),
            gmd=(item.get("gmd") or None),
            numbers=str(item["hnr"]),
            lat=array("i", item["lat"]),
            lon=array("i", item["lon"]),
        )
        for item in payload["strassen"]
        if item.get("str") and item.get("lat")
    ]
    return AddressIndex(
        groups,
        stand=payload.get("stand") or None,
        quelle=payload.get("quelle") or None,
        path=path,
    )
