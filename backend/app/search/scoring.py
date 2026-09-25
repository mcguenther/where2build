"""Ordering the candidates that survived the hard filters.

Nothing here decides anything, with one named exception -- `not_a_plot`,
which the area search uses to take road parcels out. The verdict is settled by the hard filters
alone -- a parcel number resolved against ALKIS, the cadastral district, an
exactly stated ``ave:flaeche`` -- and this module only puts what is left into a
useful order. That is what lets the weights ship uncalibrated: with no corpus
of solved listings to fit them to, a wrong weight can produce an unhelpful
ordering and nothing worse.

Two rules are measured, not chosen:

* **Never multiply the memberships.** Station, bus and school all sit in the
  village centre, so their errors are correlated; a product counts one error
  three times.
* **Never cut hard on a claim.** The reference listing's own distances were
  12 % and 32 % out. Read as an equation they delete the right candidate; read
  as a membership with a floor they merely push it down the list. That is
  exactly how the distance bands enter: ``search.distance`` turns a stated
  figure into an interval and a candidate into an interval, and what arrives
  here is how well the two overlap -- one number for all of a listing's
  distances together, because station, bus stop and school sit in the same
  village and their errors are one error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence

from ..services.alkis import TRAFFIC_USES, Flurstueck, dominant_use

# Below this a feature contributes nothing but never deletes anybody. It is the
# whole difference between "ranks last" and "was never shown".
FLOOR = 0.05

WEIGHTS = {
    # An exact area that could not be used as a hard filter -- a rounded
    # figure -- still orders well: closer is better.
    "flaeche": 1.0,
    # Measured the strongest second feature there is: 25 candidates down to 5.
    "strasse": 0.9,
    # Official value, inferred conclusion. 25 down to 16, and it would
    # occasionally delete the right answer, so it only ever ranks.
    "nutzung": 0.5,
    # A broker's sentence about a drive, measured against an outline this
    # search resolved itself. Below the official values on purpose: it is the
    # only feature here whose *input* is somebody's estimate.
    "entfernung": 0.4,
    # The same class of input -- a width somebody paced out -- against an
    # interval this search derived from the outline the cadastre answered.
    "front": 0.4,
}

# What a building plot is normally recorded as. The inference
# "Baugrundstück ⇒ Wohnbaufläche" is not official, which is exactly why this
# list ranks and never filters: an unbuilt plot can legitimately be recorded as
# farmland or as a garden.
BUILDING_LAND = ("wohnbau", "gemischte nutzung", "gartenland", "sport-, freizeit")

# The one exception to "land use only ranks": a parcel whose *dominant* use is
# traffic is taken out of an area search. A listing's figure matches road
# parcels as readily as plots -- 400 of the 3 688 parcels in Großbothen, Mölkau
# and Plagwitz are mostly Straßenverkehr, measured 24.09.2026 -- and none of
# them is what an advert sells. Dominant, not any mention:
# „Industrie- und Gewerbefläche …;2164|Straßenverkehr;0.00" is a works, and in
# the B7 case „Weg;0.00|Landwirtschaft;577" was the plot. Flugverkehr and
# Schiffsverkehr did not occur in those three districts; they are the other two
# traffic kinds of the AAA catalogue.
NOT_A_PLOT = (*TRAFFIC_USES, "Bahnverkehr", "Flugverkehr", "Schiffsverkehr")

_STREET_NORMALISE = (
    ("straße", "str"), ("strasse", "str"), ("str.", "str"),
    ("ß", "ss"), ("ä", "ae"), ("ö", "oe"), ("ü", "ue"),
)


@dataclass(frozen=True, slots=True)
class Contribution:
    """One feature's verdict on one candidate: a membership and a German phrase."""

    key: str
    value: float
    text: str


def normalise_street(name: str) -> str:
    """„Wiesenstraße“, „Wiesenstr.“ and „Wiesen-Strasse“ to one key."""

    text = name.strip().lower().replace("-", "").replace(" ", "")
    for source, target in _STREET_NORMALISE:
        text = text.replace(source, target)
    return text


def area_fit(official: float | None, stated: float | None) -> float:
    """Closeness of the official area to the one the listing states."""

    if not official or not stated:
        return FLOOR
    return max(FLOOR, 1.0 - min(1.0, abs(official - stated) / stated / 0.2))


def front_interval(geometry: Any) -> tuple[float, float] | None:
    """How wide a parcel can be, from its own outline: ``(mean, widest)``.

    A frontage is the length of the boundary along the street, and without the
    street nobody knows which boundary that is. What the outline *does* bound
    is the range. The plot cannot be narrower on average than its area over
    its length, and it cannot be wider anywhere than the short side of the
    smallest rectangle around it.

    Measured 19.09.2026 on Plagwitz 309/6, the right answer of advert
    3375124391 and the one parcel in the corpus whose listing states a
    frontage: 1 489 m² in a 39,8 x 71,5 m rectangle, mean width 20,8 m,
    stated „Frontbreite ca. 26 m". A wedge — its frontage matches *neither*
    rectangle side, which is why `_shape_objection` refuses to object on a
    width and why this is an interval rather than a number.
    """

    if geometry is None or getattr(geometry, "is_empty", True) or not geometry.area:
        return None
    try:
        corners = list(geometry.minimum_rotated_rectangle.exterior.coords)[:4]
    except (AttributeError, IndexError, ValueError):
        return None
    if len(corners) < 4:
        return None
    edges = sorted(
        ((corners[i][0] - corners[(i + 1) % 4][0]) ** 2
         + (corners[i][1] - corners[(i + 1) % 4][1]) ** 2) ** 0.5
        for i in range(4)
    )
    short, long = edges[0], edges[3]
    if short < 1 or long < 1:
        return None
    mean = geometry.area / long
    return (min(mean, short), short)


def front_fit(geometry: Any, stated: float | None) -> tuple[float, str | None]:
    """Whether a candidate can have the frontage the listing states.

    Inside the interval is a full match, outside it falls away over the
    interval's own width — a plot twice as wide as it can be is no match, one
    a metre off is nearly one. It may promote and never demote: a frontage is
    what a seller paced out, and `Dimensions` already refuses to *object* on
    one for the same reason.
    """

    interval = front_interval(geometry)
    if not stated or interval is None:
        return FLOOR, None
    low, high = interval
    if low <= stated <= high:
        return 1.0, f"{stated:g} m Front passen zu {low:.0f}–{high:.0f} m am Flurstück"
    span = max(high - low, 1.0)
    miss = (low - stated) if stated < low else (stated - high)
    return max(FLOOR, 1.0 - miss / span), None


def land_use(tntxt: str | None) -> tuple[float, str | None]:
    """What ``ave:tntxt`` says, as a membership and a phrase.

    The field carries the actual land use with its area share -- 790/11 is
    ``Wohnbaufläche;502``, a carriageway parcel ``Straßenverkehr;1062``. The
    value is official; the conclusion drawn from it is not.
    """

    if not tntxt:
        return FLOOR, None
    kinds = [part.split(";")[0].strip() for part in tntxt.split("|") if part.strip()]
    first = kinds[0] if kinds else ""
    lowered = first.lower()
    if any(marker in lowered for marker in BUILDING_LAND):
        return 1.0, first
    # A watercourse or a wood is not a building plot either -- but saying so is
    # still an inference, so it sinks rather than disappears. Traffic is the
    # exception, and it is made before scoring: see `NOT_A_PLOT`.
    return FLOOR, first


def not_a_plot(tntxt: str | None) -> str | None:
    """The dominant use when it rules a parcel out of an area search, else ``None``."""

    use = dominant_use(tntxt)
    if use is None:
        return None
    return use if use.split(" / ")[0].strip() in NOT_A_PLOT else None


def street_match(
    lagebeztxt: str | None, streets: str | Sequence[str] | None
) -> tuple[float, str | None]:
    """Whether the cadastre's own address names a street the listing does.

    Measured 05.09.2026: in Gemarkung Großbothen 71 of 1 131 parcels carry
    ``Wiesenstr*`` in ``ave:lagebeztxt`` and 577 carry ``"ohne Lage"`` -- and
    the parcel actually being sold is one of the 577. So this may promote a
    candidate and must never demote one: a missing address is missing data, not
    a contradiction, and hard-filtering on it would have deleted the answer.

    Several names, because a listing does not say which of its phrases is the
    address. „Naturnah wohnen am Kurpark" and „Wiesenstraße" arrive as equals
    and this is where they stop being equal: the official value decides, and a
    phrase no parcel carries simply never matches anything.
    """

    if not streets or not lagebeztxt:
        return FLOOR, None
    if "ohne lage" in lagebeztxt.lower():
        return FLOOR, None
    official = normalise_street(lagebeztxt)
    for street in [streets] if isinstance(streets, str) else streets:
        if street and normalise_street(street) in official:
            return 1.0, lagebeztxt.strip()
    return FLOOR, None


def score(
    parcel: Flurstueck,
    *,
    stated_area: float | None = None,
    street: str | Sequence[str] | None = None,
    distance_fit: tuple[float, str] | None = None,
    stated_front: float | None = None,
) -> tuple[float, list[str]]:
    """Points and reasons for one candidate.

    A weighted sum, deliberately: the features are correlated, and a product
    would count one correlated error several times over.
    """

    contributions: list[Contribution] = []

    if stated_area is not None:
        fit = area_fit(parcel.flaeche_amtlich_m2, stated_area)
        official = parcel.flaeche_amtlich_m2
        contributions.append(
            Contribution(
                "flaeche",
                fit,
                f"{official:g} m² gegen {stated_area:g} m² im Inserat" if official else "",
            )
        )

    fit, name = street_match(parcel.attributes.get("lagebeztxt"), street)
    if name:
        contributions.append(Contribution("strasse", fit, f"amtliche Lage: {name}"))

    fit, kind = land_use(parcel.attributes.get("tntxt"))
    if kind:
        contributions.append(Contribution("nutzung", fit, f"Nutzung: {kind}"))

    if stated_front is not None:
        fit, phrase = front_fit(parcel.geometry, stated_front)
        if phrase or fit > FLOOR:
            contributions.append(Contribution("front", fit, phrase or ""))

    if distance_fit is not None:
        value, phrase = distance_fit
        contributions.append(Contribution("entfernung", max(FLOOR, value), phrase))

    if not contributions:
        return 0.0, []

    total = sum(WEIGHTS.get(c.key, 0.2) * c.value for c in contributions)
    weight = sum(WEIGHTS.get(c.key, 0.2) for c in contributions)
    reasons = [c.text for c in contributions if c.text and c.value > FLOOR]
    return round(total / weight, 4), reasons


def parcel_number(parcel: Flurstueck) -> str:
    zaehler = parcel.attributes.get("flstnrzae", "")
    nenner = parcel.attributes.get("flstnrnen")
    return f"{zaehler}/{nenner}" if nenner else zaehler


def clean_use(tntxt: str | None) -> str | None:
    """``"Wohnbaufläche;502"`` to ``"Wohnbaufläche"`` for display.

    Split on the semicolon only. The kind and its area share are separated by
    one; the *name* may well contain a comma -- "Sport-, Freizeit- und
    Erholungsfläche" is a real value, and splitting on commas leaves "Sport-"
    standing in a table as if that were a land use.
    """

    if not tntxt:
        return None
    parts = [part.split(";")[0].strip() for part in tntxt.split("|")]
    kept = [part for part in parts if part]
    return " · ".join(dict.fromkeys(kept)) or None
