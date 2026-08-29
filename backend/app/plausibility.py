"""Is the parcel that was found plausibly the plot the listing describes?

Resolving an address hands ALKIS one point and keeps whatever parcel covers
it. For a street address that parcel is the plot; for a district address
("Plaußig-Portitz, 04349 Leipzig") it is whatever the geocoder's point happened
to fall on -- and the answer looks exactly as official either way. That silence
is what this module removes: it never refuses a parcel, it says out loud when
the parcel cannot be the plot the caller expected.

The thresholds are read off a live ALKIS sample taken on 29.08.2026: 14 286
parcels from six Saxon places (Plaußig-Portitz, Moritzburg,
Leipzig-Holzhausen, Wurzen, Radebeul, Freiberg), each joined to its official
land use from ``ave:NutzungFlurstueck``.

* 7 947 of them are used purely as ``Wohnbaufläche`` -- building land. Median
  area 572 m2, 95 % below 1 790 m2, 99 % below 4 384 m2.
* Their longest extent (the long side of the minimum rotated rectangle) has a
  median of 36 m and a 99th percentile of 111 m. Not one of the 7 947 exceeds
  464 m, and only 4 (0.05 %) are both longer than 200 m and more than five
  times as long as they are wide -- three of those are 440-520 m2 slivers
  along a street rather than building plots.
* A point dropped at random lands on a parcel of 9 631 m2 median area, fifteen
  times the unweighted median of 630 m2: what a coordinate hits is decided by
  area, not by count. That is the whole reason a district address ends up on a
  field.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from shapely.ops import unary_union

from .schemas import GeocodeTreffer, Plausibility, PlausibilityIssue
from .services.alkis import Flurstueck

# A parcel this many times larger than the stated plot area cannot be that
# plot. Against a 908 m2 listing the rule fires on 1.5 % of real Wohnbau
# parcels but on 65 % of the parcels a random point hits, and a factor of four
# is far outside what rounding or a different area basis can explain.
AREA_FACTOR_TOO_LARGE = 4.0

# The other direction is much weaker evidence: a plot is a set of parcels, so
# an address resolving to one parcel of several is the normal case. Half the
# stated area is therefore a note about a possibly incomplete plot, not a
# warning about the wrong land.
AREA_FACTOR_TOO_SMALL = 0.5

# Strip test, both conditions together: 0.05 % of real building parcels match,
# and none of them is longer than 464 m in the first place.
STRIP_MIN_LENGTH_M = 200.0
STRIP_MIN_ELONGATION = 5.0

ADVICE = (
    "Bitte die Lage auf der Karte prüfen oder Gemarkung und Flurstücksnummer "
    "direkt eintragen."
)

# What the geocoder matched, for the sentence that says it was not an address.
_MATCH_LABELS = {
    "ort": "Ort",
    "haltestelle": "Haltestelle",
    "sonstiges": "unbestimmten Treffer",
}


def _thousands(value: float) -> str:
    """German thousands separator: 21609 -> „21.609“."""

    return f"{value:,.0f}".replace(",", ".")


def _ratio(value: float) -> str:
    if value >= 10:
        return _thousands(value)
    return f"{value:.1f}".replace(".", ",")


def extents(geometry: Any) -> tuple[float, float]:
    """Long and short side of the tightest rectangle around the geometry.

    The rotated rectangle, not the axis-aligned envelope: a strip running
    diagonally has a bounding box nearly as wide as it is long, which hides
    exactly the shape this is looking for. The Portitz field measures
    1 583 x 198 m as an envelope and 1 594 x 30 m as a rotated rectangle.

    A geometry in several pieces is measured on its largest piece -- a
    rectangle around scattered parcels says how far apart they lie, not what
    shape they have.
    """

    parts = list(getattr(geometry, "geoms", [geometry]))
    largest = max(parts, key=lambda part: part.area)
    corners = list(largest.minimum_rotated_rectangle.exterior.coords)
    sides = [math.dist(corners[i], corners[i + 1]) for i in range(4)]
    return max(sides), min(sides)


def assess(
    parcels: Sequence[Flurstueck],
    expected_area_m2: int | None = None,
    address_match: GeocodeTreffer | None = None,
) -> Plausibility:
    """Judge the answer against what the caller said to expect.

    ``expected_area_m2`` is the plot area from the listing; without it only the
    shape and the kind of address match can be judged. Nothing here is ever an
    error -- a caller who really wants this parcel keeps it.
    """

    geometry = unary_union([parcel.geometry for parcel in parcels])
    official_area = (
        sum(parcel.flaeche_amtlich_m2 or 0.0 for parcel in parcels) or geometry.area
    )
    longest, shortest = extents(geometry)
    elongation = longest / shortest if shortest else None

    issues: list[PlausibilityIssue] = []
    sentences: list[str] = []
    factor: float | None = None

    if expected_area_m2:
        factor = official_area / expected_area_m2
        if factor >= AREA_FACTOR_TOO_LARGE:
            issues.append("area_too_large")
            sentences.append(
                f"Das gefundene Flurstück ist mit {_thousands(official_area)} m² rund "
                f"{_ratio(factor)}-mal so groß wie die angegebene Grundstücksfläche von "
                f"{_thousands(expected_area_m2)} m². Sehr wahrscheinlich ist das nicht "
                "das Grundstück aus dem Inserat."
            )
        elif factor <= AREA_FACTOR_TOO_SMALL:
            issues.append("area_too_small")
            sentences.append(
                f"Das gefundene Flurstück ist mit {_thousands(official_area)} m² nur "
                f"{round(factor * 100)} % der angegebenen Grundstücksfläche von "
                f"{_thousands(expected_area_m2)} m². Ein Grundstück besteht oft aus "
                "mehreren Flurstücken — möglicherweise gehören weitere dazu."
            )

    if (
        elongation is not None
        and longest > STRIP_MIN_LENGTH_M
        and elongation > STRIP_MIN_ELONGATION
    ):
        issues.append("shape_atypical")
        sentences.append(
            f"Das Flurstück ist {_thousands(longest)} m lang und nur "
            f"{_thousands(shortest)} m breit (Verhältnis {_ratio(elongation)} zu 1) — "
            "die Form eines Feld- oder Wegflurstücks, nicht die eines Baugrundstücks."
        )

    if address_match is not None and address_match.art != "adresse":
        label = _MATCH_LABELS.get(address_match.art, "unbestimmten Treffer")
        issues.append("address_is_not_a_street_address")
        sentences.append(
            f"Der Geocoder hat „{address_match.name}“ als {label} erkannt, nicht als "
            "Hausadresse. Gezeigt wird das Flurstück unter diesem Punkt; ein Ortsteil "
            "ist kein Grundstück."
        )

    return Plausibility(
        plausible=not issues,
        issues=issues,
        expected_area_m2=expected_area_m2,
        flaeche_amtlich_m2=round(official_area, 2),
        area_factor=round(factor, 2) if factor is not None else None,
        longest_extent_m=round(longest, 1),
        shortest_extent_m=round(shortest, 1),
        elongation=round(elongation, 2) if elongation is not None else None,
        warning=" ".join([*sentences, ADVICE]) if sentences else None,
    )
