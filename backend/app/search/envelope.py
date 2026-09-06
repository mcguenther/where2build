"""The smallest unit every surviving candidate shares.

"Ambiguous" is not a failure as long as the answer says what *is* settled. Five
candidates that all lie on one street mean the street is the answer -- and for
the land value and for travel times that is often the whole answer, because the
Bodenrichtwert is zonal and routes from one street differ by metres. Only the
area and the boundaries genuinely need the individual parcel.

Measured on the reference listing's own candidate sets:

    area band +-5 %      25 candidates   Gemarkung Großbothen
    + both rings          8              Gemarkung Großbothen
    + street buffer       5              Wiesenstraße in Großbothen
    + exact area          1              Flurstück 790/11

The envelope must never look like a hit. No halo and no drawn contour -- those
stay reserved for a confirmed parcel, because a shaded street is a statement
about a street, not about a plot.
"""

from __future__ import annotations

from typing import Sequence

from shapely.ops import unary_union

from .. import geo
from ..schemas import Huelle
from ..services.alkis import Flurstueck
from .scoring import normalise_street, parcel_number


def _shared(parcels: Sequence[Flurstueck], attribute: str) -> str | None:
    """The value every parcel carries for an attribute, or ``None``."""

    values = {parcel.attributes.get(attribute) for parcel in parcels}
    if len(values) != 1:
        return None
    value = values.pop()
    return value or None


def _shared_street(parcels: Sequence[Flurstueck]) -> str | None:
    """The street every candidate is addressed on, if they all are.

    ``"ohne Lage"`` is missing data, not an address: a set where some parcels
    name a street and the rest name nothing shares no street, and claiming one
    would be inventing an answer out of a gap.
    """

    streets: set[str] = set()
    display: dict[str, str] = {}
    for parcel in parcels:
        raw = (parcel.attributes.get("lagebeztxt") or "").strip()
        if not raw or "ohne lage" in raw.lower():
            return None
        # The cadastre writes "Wiesenstraße 12"; the street is what is shared.
        name = raw.rstrip("0123456789 -/").strip() or raw
        key = normalise_street(name)
        streets.add(key)
        display.setdefault(key, name)
    if len(streets) != 1:
        return None
    return display[streets.pop()]


def common_envelope(
    parcels: Sequence[Flurstueck], *, district_outline: object | None = None
) -> Huelle:
    """What is settled about the location, whatever is not settled about the parcel.

    Searched from the bottom up: one parcel, else one street, else one
    cadastral district, else one municipality, else nothing.
    """

    if not parcels:
        return Huelle(art="offen", text="Die Lage ließ sich nicht eingrenzen.")

    if len(parcels) == 1:
        parcel = parcels[0]
        district = parcel.attributes.get("gemarkung") or ""
        number = parcel_number(parcel)
        return Huelle(
            art="flurstueck",
            text=f"Flurstück {number} in der Gemarkung {district}".strip(),
            geometry=_geojson(parcel.geometry),
        )

    district = _shared(parcels, "gemarkung")
    street = _shared_street(parcels)
    if street and district:
        return Huelle(
            art="strasse",
            text=(
                f"An der {street} in der Gemarkung {district} — welches der "
                f"{len(parcels)} Flurstücke, ist offen."
            ),
            geometry=_geojson(unary_union([parcel.geometry for parcel in parcels])),
        )

    if district:
        return Huelle(
            art="gemarkung",
            text=(
                f"In der Gemarkung {district} — {len(parcels)} Flurstücke kommen "
                "in Frage."
            ),
            geometry=_geojson(
                getattr(district_outline, "geometry", None)
                or unary_union([parcel.geometry for parcel in parcels])
            ),
        )

    municipality = _shared(parcels, "gemeinde")
    if municipality:
        return Huelle(
            art="gemeinde",
            text=(
                f"In {municipality} — {len(parcels)} Flurstücke kommen in Frage, "
                "verteilt über mehrere Gemarkungen."
            ),
            geometry=_geojson(unary_union([parcel.geometry for parcel in parcels])),
        )

    return Huelle(
        art="offen",
        text=(
            f"{len(parcels)} Flurstücke kommen in Frage, ohne gemeinsame Gemarkung "
            "oder Gemeinde. Für eine Eingrenzung fehlt eine Ortsangabe."
        ),
    )


def next_question(parcels: Sequence[Flurstueck], huelle: Huelle) -> str | None:
    """The cheapest thing a person could add, given what is already settled.

    Out of the envelope follows the next question: with five parcels on one
    street the house number is the missing statement, and asking for that beats
    asking generally for "Gemarkung und Nummer".
    """

    if huelle.art == "flurstueck":
        return None
    if huelle.art == "strasse":
        return (
            "Steht in der Anzeige eine Hausnummer? Sie entscheidet zwischen den "
            f"{len(parcels)} Flurstücken an dieser Straße."
        )
    if huelle.art in ("gemarkung", "gemeinde"):
        return (
            "Steht in der Anzeige eine Straße oder eine genaue Fläche? Beides "
            "grenzt hier am stärksten ein."
        )
    return (
        "Für eine Eingrenzung fehlt eine Ortsangabe — Gemarkung und "
        "Flurstücksnummer stehen im Kaufvertrag oder im Katasterauszug."
    )


def _geojson(geometry: object | None) -> dict | None:
    """A UTM33 geometry as WGS84 GeoJSON, the way every other answer travels."""

    if geometry is None:
        return None
    return geo.to_geojson(geo.reproject_geometry(geometry, geo.UTM33, geo.WGS84))
