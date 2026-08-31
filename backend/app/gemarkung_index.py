"""The directory of Saxon cadastral districts served by ``GET /api/gemarkungen``.

A parcel is addressed by its Gemarkung plus a parcel number, and the Gemarkung
is the half a buyer cannot guess: 5 339 of them, spelled exactly as the cadastre
spells them. A blank text field turns that into a lookup task; a picklist turns
it into a choice. So the whole list is served at once and the browser filters.

The list itself comes from the ALKIS layer ``ave:KatasterBezirk``, pulled once
by ``scripts/build_gemarkung_index.py``. Not per request: the layer carries the
district boundary geometry, ``PROPERTYNAME`` does not suppress it (with the
``ave:`` prefix the request is accepted and the geometry arrives anyway,
without it the service answers ``ErrorInPropertyName``). Measured on
30.08.2026: 56 MB of GML for the 503 kB of text that matters. Once a quarter is
right for a list that changes on the order of a district merger.

Unlike the POI index, the built file **is committed**: it is a few hundred
kilobytes of official data with no licence obstacle, and an input mask that
silently loses its picklist on a fresh checkout is worse than one that never
had it.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ``ave:KatasterBezirk`` is the layer for cadastral districts of every kind;
# ``art`` separates them. Only Gemarkungen address a parcel.
GEMARKUNG_ART = "Gemarkung"

# Attributes carried over from a ``ave:KatasterBezirk`` feature. The geometry
# is dropped: this directory answers "how is it spelled and what is its key",
# and the boundary of a district has no place in an input mask.
SOURCE_FIELDS = ("art", "name", "schluessel", "gemeinde")

_UMLAUT_EXPANSIONS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def fold(text: str) -> str:
    """Lowercase and without diacritics, so "Molkau" can find "Mölkau".

    ``casefold`` already turns ß into ss, which is why Großschirma is reachable
    as "grossschirma" without a rule of its own.
    """

    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def fold_expanded(text: str) -> str:
    """The same, but with the umlauts written out: Mölkau -> "moelkau".

    Both spellings are in everyday use, and a searcher picks one without
    thinking about it. Matching one folded query against both forms of the
    name covers "Mölkau", "Molkau" and "Moelkau" with two comparisons.
    """

    return fold(text.casefold().translate(_UMLAUT_EXPANSIONS))


def sort_key(name: str) -> tuple[str, str]:
    """German-ish order without a locale: Ö sorts with O, not after Z."""

    return fold(name), name


@dataclass(frozen=True, slots=True)
class GemarkungEntry:
    """One cadastral district.

    German field names on purpose: these three go out over the wire unchanged
    and mirror the ALKIS attributes ``name``, ``schluessel`` and ``gemeinde``.
    """

    name: str
    schluessel: str
    gemeinde: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "schluessel": self.schluessel, "gemeinde": self.gemeinde}


class GemarkungDirectory:
    """The districts, sorted by name, with a substring search over name and key."""

    def __init__(self, entries: list[GemarkungEntry], *, stand: str | None = None) -> None:
        self.stand = stand
        self.entries = sorted(entries, key=lambda entry: sort_key(entry.name))
        # Folded once at load rather than per query: 5 339 names times two
        # normalisations is measurable work to repeat on every keystroke.
        self._haystacks = [
            (fold(entry.name), fold_expanded(entry.name), entry.schluessel)
            for entry in self.entries
        ]

    def __len__(self) -> int:
        return len(self.entries)

    def search(self, query: str | None) -> list[GemarkungEntry]:
        """Districts whose name or key contains ``query``, in name order.

        An empty or missing query is the normal case and returns everything --
        the browser then filters the list it already holds.
        """

        needle = fold((query or "").strip())
        if not needle:
            return list(self.entries)
        return [
            entry
            for entry, (name, expanded, schluessel) in zip(self.entries, self._haystacks)
            if needle in name or needle in expanded or needle in schluessel
        ]


def read_directory_file(path: Path) -> dict[str, Any]:
    """Read the built file, rejecting anything that is not one."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("gemarkungen"), list):
        raise ValueError(f"{path} is not a Gemarkung directory (no 'gemarkungen' array).")
    return payload


def load_directory(path: Path) -> GemarkungDirectory | None:
    """Load the directory, or ``None`` when it has not been built on this server.

    ``None`` rather than an empty directory: the endpoint has to be able to say
    "this server holds no such list", which is a different sentence from "no
    district matched".
    """

    if not path.is_file():
        return None
    payload = read_directory_file(path)
    entries = [
        GemarkungEntry(
            name=str(item["name"]),
            schluessel=str(item["schluessel"]),
            gemeinde=(item.get("gemeinde") or None),
        )
        for item in payload["gemarkungen"]
        if item.get("name") and item.get("schluessel")
    ]
    return GemarkungDirectory(entries, stand=payload.get("stand") or None)
