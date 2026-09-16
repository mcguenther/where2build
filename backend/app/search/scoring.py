"""Ordering the candidates that survived the hard filters.

Nothing here decides anything. The verdict is settled by the hard filters
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

from ..services.alkis import Flurstueck

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
}

# What a building plot is normally recorded as. The inference
# "Baugrundstück ⇒ Wohnbaufläche" is not official, which is exactly why this
# list ranks and never filters: an unbuilt plot can legitimately be recorded as
# farmland or as a garden.
BUILDING_LAND = ("wohnbau", "gemischte nutzung", "gartenland", "sport-, freizeit")

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
    # A carriageway or a watercourse is not a building plot -- but saying so is
    # still an inference, so it sinks rather than disappears.
    return FLOOR, first


def street_match(lagebeztxt: str | None, street: str | None) -> tuple[float, str | None]:
    """Whether the cadastre's own address names the street the listing does.

    Measured 05.09.2026: in Gemarkung Großbothen 71 of 1 131 parcels carry
    ``Wiesenstr*`` in ``ave:lagebeztxt`` and 577 carry ``"ohne Lage"`` -- and
    the parcel actually being sold is one of the 577. So this may promote a
    candidate and must never demote one: a missing address is missing data, not
    a contradiction, and hard-filtering on it would have deleted the answer.
    """

    if not street or not lagebeztxt:
        return FLOOR, None
    if "ohne lage" in lagebeztxt.lower():
        return FLOOR, None
    if normalise_street(street) in normalise_street(lagebeztxt):
        return 1.0, lagebeztxt.strip()
    return FLOOR, None


def score(
    parcel: Flurstueck,
    *,
    stated_area: float | None = None,
    street: str | None = None,
    distance_fit: tuple[float, str] | None = None,
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
