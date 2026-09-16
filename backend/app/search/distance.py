"""Reading what a listing says about distance, and what that may decide.

A broker's „ca. 6 km bis Grimma" is not a radius. It is a measurement of
something nobody named, from a place nobody located, by a means of travel
nobody stated -- and read as an equation it deletes the right parcel. Measured
against the reference listing: the geocoder's point for Grimma is 5.34 km from
the parcel actually offered, the car route 7.37 km, the edge of the built-up
area 5.32 km and its middle 6.25 km. The stated figure sits inside *that*
interval and outside every single-point reading.

So nothing here picks a reading. A named reference resolves to a set, the
candidate carries the whole interval that set admits, the sentence carries an
interval of its own, and the test is whether the two overlap. Three rules
follow from measuring, and they are what keeps a distance from producing a
confidently wrong answer:

* **Never confirm.** No intersection of bands, however small, makes a verdict.
  „Bestätigt" stays with official statements -- a parcel number, the cadastral
  district, an exact area. A band is a broker's sentence about a drive.
* **Object only outwards.** A route is never shorter than the straight line,
  measured without exception, so a candidate whose straight line already
  exceeds the outer bound cannot satisfy the statement under any reading. That
  is the one direction in which a distance proves something -- and even then it
  only sinks the candidate and writes the sentence next to it.
* **Never multiply.** Station, bus stop and school all sit in the same village,
  so their errors are one error; the memberships join the weighted sum in
  ``scoring`` rather than a product.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

# How far the two unknowns are allowed to stretch a stated figure. Fixed and
# generous by decision, because the band may never confirm: too wide costs
# ordering, too narrow costs the right answer.
#
# ``DETOUR`` is the route-to-straight-line ratio, measured 1.17 to 2.91 over
# the reference listing's own destinations -- a figure a seller measured by car
# may be up to that much longer than the line this search can draw, so the
# inner bound divides by it. ``SLACK`` is the roundness of the sentence itself:
# „ca. 6 km" is not 6 km, and the recorded adverts are out by 12 % and 32 %.
DETOUR = 1.30
SLACK = 0.25

# A walking or driving *time* says even less than a distance: it carries the
# speed of whoever measured it as a third unknown. These are deliberately crude
# -- what they buy is that a stated time still draws a band rather than nothing.
SPEED_M_PER_MIN = {"fuss": 75.0, "auto": 700.0, "rad": 250.0}

# Below this a statement is about the plot itself rather than about where it is
# („20 m Straßenfront"), and above it the reference is a region rather than a
# place („120 km nach Berlin") and the band no longer separates anything.
MIN_DISTANCE_M = 100.0
MAX_DISTANCE_M = 60_000.0

_HEDGE = r"ca\.?|circa|rund|etwa|ungef(?:ä|ae)hr|knapp|gut|nur|ab"
_NUMBER = r"\d{1,3}(?:[.\s]\d{3})*(?:,\d+)?|\d+(?:[.,]\d+)?"
_NAME = r"[A-ZÄÖÜ][\wäöüßÄÖÜ\-]{2,}(?:[ -][A-ZÄÖÜ][\wäöüßÄÖÜ\-]+)?"
# A road number is shorter than any place name and is still a reference worth
# showing: „bis zur A14" is a statement, just not one this search can resolve.
_TARGET = rf"{_NAME}|[AB]\s?\d{{1,3}}"

# The measurement itself. The unit decides the mode: „Autominuten" is a drive,
# „Gehminuten" a walk, a bare kilometre figure says nothing about either.
_MEASURE_RE = re.compile(
    rf"(?:(?P<hedge>{_HEDGE})\s*)?"
    rf"(?P<value>{_NUMBER})\s*"
    r"(?P<unit>km\b|kilometern?\b|m\b|metern?\b|"
    r"(?:auto|fahr|geh|lauf|fuss|fuß|rad|zu\s+fu(?:ß|ss))[\s-]*minuten\b|minuten\b)"
    r"(?![²2])",
    re.IGNORECASE,
)

# What the measurement is measured *to*, where the sentence puts it behind:
# „6 km bis Grimma", „3 km zur A38", „15 Minuten nach Leipzig".
#
# The qualifier („Kreisstadt Grimma") is lazy, and the space after it is a
# literal space rather than ``\s``. Both matter: greedy, it swallows the name
# and takes the next capitalised word instead -- across a paragraph break, so
# „im 3 km entfernten Machern\n\nDie verwendeten Bilder" read as a distance to
# a place called „Die".
_TARGET_AFTER_RE = re.compile(
    rf"[ \t]*(?:entfernt\w*[ \t]*)?"
    # One or two of them: „bis zur A14" and „Entfernung nach Leipzig" both put
    # a second preposition between the measurement and the name.
    rf"(?:(?:bis|nach|zu[rm]?|von|ins?|in|an|entfernung)[ \t]+){{1,2}}"
    rf"(?:(?:der|die|das|den|dem)[ \t]+)?"
    rf"(?:(?P<qualifier>[A-ZÄÖÜ][\wäöüß]+(?:stadt|ort|gemeinde|zentrum))[ \t]+)?"
    rf"(?P<target>{_TARGET})",
)

# „die ca. 6 km entfernte Kreisstadt Grimma": the noun stands behind the
# measurement without a preposition, and one word may separate the two.
_TARGET_ADJECTIVE_RE = re.compile(
    rf"[ \t]*entfernte?[nrs]?[ \t]+(?:[A-ZÄÖÜ][\wäöüß]+[ \t]+)?(?P<target>{_TARGET})",
)

# „Die Grundschule Jesewitz ist nur rund 6 Minuten entfernt": the reference
# stands in front with nothing but function words between. Anchored to the end
# of the window, so only what actually leads into the measurement counts.
_SUBJECT_BEFORE_RE = re.compile(
    rf"(?P<subject>{_NAME})(?:\s+[a-zäöüß]+){{0,4}}\s*$",
)

# A capital letter at the start of a sentence is not a name. German writes one
# on every noun, so the usual signal says nothing here and these have to go by
# list.
_NOT_A_NAME = frozenset(
    "die der das den dem des ein eine einen einem einer ihr ihre sie wir man "
    "hier dort auch nur noch dieses diese dieser alles".split()
)

# „Bushaltestelle: ca. 300 m", „Autobahnanschlussstelle A38 „Leipzig-Südwest":
# ca. 3 km". Here the reference stands in front and the colon binds it.
_LABEL_BEFORE_RE = re.compile(
    rf"(?P<label>{_NAME}(?:[^:;\n\r|]{{0,40}})?)\s*[:–—-]\s*$",
)

# A dimension, not a distance: „14 x 40 m", „ca. 20 m breit".
_DIMENSION_BEFORE = re.compile(r"(?:[x×*]|breit|tief|lang|hoch|front)\s*$", re.IGNORECASE)
_DIMENSION_AFTER = re.compile(r"^\s*(?:[x×*]\s*\d|breit|tief|lang|hoch)", re.IGNORECASE)

# How much of the sentence around a measurement is read for its reference.
_WINDOW = 60

# What a reference names, which is what says how much it can bind. A named
# place resolves to one outline; a bare class („Bushaltestelle") resolves to
# whichever member is nearest, which is weaker but is also exactly what the
# sentence claimed; „unbekannt" is drawn and never computed.
# What a reference names, which is what says how much it can bind. A named
# place resolves to one outline; a bare class („Bushaltestelle") resolves to
# whichever member is nearest, which is weaker but is also exactly what the
# sentence claimed.
#
# Whole words and compound endings, never a substring: „see" and „wald" sit
# inside „Seelitz" and „Waldheim", and reading those as a lake and a forest
# turns two towns into classes nothing can resolve.
_CLASS_WORDS = frozenset(
    "bus busse haltestelle bahnhof busbahnhof autobahn auffahrt anschlussstelle "
    "supermarkt schule grundschule oberschule hauptschule realschule gesamtschule "
    "gymnasium kita kindergarten kindertagesstätte kindertagesstaette arzt ärzte "
    "apotheke bäckerei baeckerei markt gaststätte gaststaette gaststaetten "
    "flughafen see wald spielplatz zentrum ortszentrum stadtzentrum post "
    "sparkasse bank tankstelle klinik krankenhaus schwimmbad bahn s-bahn "
    "umkreis umgebung nähe naehe radius entfernung".split()
)
# „A14", „B 2", „S 1" — a road number, never a settlement.
_ROAD_RE = re.compile(r"[ab]\s?\d{1,3}")

_CLASS_ENDINGS = (
    "haltestelle", "bahnhof", "bahnhöfe", "schule", "schulen", "kita", "kitas",
    "apotheke", "bäckerei", "baeckerei", "zentrum", "einrichtung",
    "einrichtungen", "möglichkeit", "möglichkeiten", "moeglichkeiten",
    "stätte", "staette", "stätten", "staetten", "anschlussstelle", "autobahn",
    "markt", "märkte", "arzt", "ärzte", "kindergarten", "gaststätten",
)


@dataclass(frozen=True, slots=True)
class DistanceStatement:
    """One statement of distance, as the sentence made it.

    ``target`` is the name the text gave, or ``None`` where it gave a class.
    ``mode`` is what the wording implies about how it was measured, and it is
    only ever used to widen: nothing here assumes a seller measured the way
    this search would.
    """

    meters: float
    target: str | None
    label: str
    mode: str
    beleg: str
    hedged: bool

    @property
    def named(self) -> bool:
        return self.target is not None

    @property
    def band(self) -> tuple[float, float]:
        """The interval the statement admits: ``[d / ϱ, d · (1+ε)]``.

        A hedged figure („ca. 6 km") is the normal case and gets the full
        slack. An unhedged one is not meaningfully more precise -- the recorded
        adverts write both and are out by the same amount -- so the only thing
        that narrows the band is a *time*, which cannot be narrowed at all and
        therefore widens instead.
        """

        stretch = SLACK if self.mode != "zeit" else SLACK * 2
        return self.meters / DETOUR, self.meters * (1.0 + stretch)


def read_distances(body: str | None) -> list[DistanceStatement]:
    """Every distance statement a listing's prose makes, in the order it makes them.

    Deliberately literal: it reads the number, the unit and the noun the
    sentence attaches them to, and it resolves nothing. What „Grimma" is, and
    how far away it therefore lies, is a question for a service -- and this
    module never asks one.
    """

    if not body:
        return []

    out: list[DistanceStatement] = []
    seen: set[tuple[float, str]] = set()
    for match in _MEASURE_RE.finditer(body):
        before = body[max(0, match.start() - _WINDOW) : match.start()]
        after = body[match.end() : match.end() + _WINDOW]
        if _DIMENSION_BEFORE.search(before) or _DIMENSION_AFTER.match(after):
            continue

        meters = _to_meters(match.group("value"), match.group("unit"))
        if meters is None or not MIN_DISTANCE_M <= meters <= MAX_DISTANCE_M:
            continue

        target, label = _reference(before, after)
        if label is None:
            continue
        key = (round(meters), label.casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append(
            DistanceStatement(
                meters=meters,
                target=target,
                label=label,
                mode=_mode(match.group("unit")),
                beleg=_excerpt(body, match.start(), match.end()),
                hedged=bool(match.group("hedge")),
            )
        )
    return out


def _to_meters(raw: str, unit: str) -> float | None:
    text = raw.strip().replace(" ", "").replace(".", "").replace(",", ".")
    try:
        value = float(text)
    except ValueError:
        return None
    lowered = unit.casefold()
    if lowered.startswith(("km", "kilometer")):
        return value * 1000.0
    if lowered.startswith(("m", "meter")):
        return value
    return value * SPEED_M_PER_MIN.get(_mode(unit), SPEED_M_PER_MIN["fuss"])


def _mode(unit: str) -> str:
    lowered = unit.casefold().replace(" ", "").replace("-", "")
    if lowered.startswith(("auto", "fahr")):
        return "auto"
    if lowered.startswith("rad"):
        return "rad"
    if lowered.startswith(("geh", "lauf", "fuss", "fuß", "zufuß", "zufuss")):
        return "fuss"
    if lowered.startswith("minuten"):
        return "zeit"
    return "strecke"


def _reference(before: str, after: str) -> tuple[str | None, str | None]:
    """The place or the class a measurement is measured to.

    Returns the proper name where the sentence gave one and ``None`` where it
    gave only a kind of place -- the difference decides whether the reference
    can be resolved to an outline or only drawn. A name here is a *claim* that
    it is one; what settles it is the cadastral district directory, which the
    engine asks and this module does not.
    """

    for pattern in (_TARGET_AFTER_RE, _TARGET_ADJECTIVE_RE):
        match = pattern.match(after)
        if match:
            name = _clean(match.group("target"))
            if name:
                return (None if _class_word(name) else name), name

    tail = _segment_end(before)
    match = _LABEL_BEFORE_RE.search(tail)
    if match:
        label = _clean(match.group("label"))
        if label:
            return (None if _class_word(label) else label), label

    match = _SUBJECT_BEFORE_RE.search(tail)
    if match:
        subject = _clean(match.group("subject"))
        if subject:
            return (None if _class_word(subject) else subject), subject
    return None, None


def _clean(raw: str) -> str | None:
    """A captured reference without its quotation marks, or nothing at all."""

    text = raw.strip().strip(" \t.,;:–—-")
    for quote in "„“”\"'‚‘’":
        text = text.replace(quote, "")
    text = " ".join(text.split())
    if not text or text.split()[0].casefold() in _NOT_A_NAME:
        return None
    return text


def _segment_end(before: str) -> str:
    """The part of the window that belongs to the same sentence as the measurement.

    A bullet list writes one reference per line, so a window that reaches over
    the line break attaches „Grundschule 2 km" to the school above it.
    """

    return re.split(r"[.;\n\r|]", before)[-1].rstrip()


def _class_word(text: str) -> bool:
    """Whether a reference names a kind of place rather than one place.

    Word by word, plus a handful of compound endings. „Bushaltestelle" is a
    class and „Machern" is not, and the difference is a whole word or a German
    compound ending -- never a substring, which would make „Waldheim" a forest.
    """

    for word in re.split(r"[\s/-]+", text.casefold()):
        stripped = word.strip(".,;:!?()")
        if not stripped:
            continue
        if stripped in _CLASS_WORDS or stripped.endswith(_CLASS_ENDINGS):
            return True
        # „A14", „B2" -- a road, and the one kind of reference whose name looks
        # nothing like a place name.
        if _ROAD_RE.fullmatch(stripped):
            return True
    return False


def _excerpt(body: str, start: int, end: int, span: int = 70) -> str:
    left = max(0, start - span)
    right = min(len(body), end + span)
    return ("… " if left else "") + body[left:right].strip() + (" …" if right < len(body) else "")


# ----------------------------------------------------------------------
# The geometry of a band, over intervals rather than over radii
# ----------------------------------------------------------------------


def overlaps(reading: tuple[float, float], band: tuple[float, float]) -> bool:
    """Whether a candidate's readings and a statement's band share anything.

    Both sides are intervals, and neither side is reduced to a number. That is
    the whole design: where it is unclear whether the seller measured to the
    edge of a town or to its middle, both are admitted rather than one chosen.
    """

    return reading[0] <= band[1] and band[0] <= reading[1]


def refuted(reading: tuple[float, float], band: tuple[float, float]) -> bool:
    """Whether the statement is unsatisfiable for this candidate, in every reading.

    True only when even the *nearest* reading, measured as the straight line,
    already exceeds the outer bound. A route is never shorter than the line, so
    no way of travelling and no reading of the reference can bring it back --
    which makes this the one direction in which a broker's figure proves
    anything. It still deletes nobody; it sinks the candidate and says why.
    """

    return reading[0] > band[1]


def membership(reading: tuple[float, float], band: tuple[float, float]) -> float:
    """How well a candidate's readings fit a statement, between 0 and 1.

    A trapezoid: anything inside the band is a 1, and outside it the value
    falls off over the band's own width rather than over a chosen constant --
    a wide statement forgives widely, a narrow one does not.
    """

    if overlaps(reading, band):
        return 1.0
    width = max(band[1] - band[0], 1.0)
    gap = band[0] - reading[1] if reading[1] < band[0] else reading[0] - band[1]
    return max(0.0, 1.0 - gap / width)


def interval(distances: list[float]) -> tuple[float, float] | None:
    """The readings of one reference, as one interval."""

    if not distances:
        return None
    return min(distances), max(distances)


def kilometres(meters: float) -> str:
    """„6 km", „300 m" — the German figure this is written back out as."""

    if meters < 1000:
        return f"{round(meters / 10) * 10:.0f} m"
    value = meters / 1000
    return f"{value:.1f}".replace(".", ",").removesuffix(",0") + " km"


def band_sentence(statement: DistanceStatement) -> str:
    """The German line under a distance Indiz. Composed, never written."""

    inner, outer = statement.band
    where = statement.target or statement.label
    measured = {
        "auto": "mit dem Auto gemessen",
        "fuss": "zu Fuß gemessen",
        "rad": "mit dem Rad gemessen",
        "zeit": "als Fahrzeit angegeben",
    }.get(statement.mode)
    lead = f"{kilometres(statement.meters)} bis {where}"
    if measured:
        lead = f"{lead}, {measured}"
    return (
        f"{lead} — daraus ein Band von {kilometres(inner)} bis {kilometres(outer)}. "
        "Das ordnet die Kandidaten und kann widersprechen, bestätigen kann es nie."
    )


def straight_line_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Metres between two projected points."""

    return math.dist(a, b)


__all__ = [
    "DETOUR",
    "SLACK",
    "DistanceStatement",
    "band_sentence",
    "interval",
    "kilometres",
    "membership",
    "overlaps",
    "read_distances",
    "refuted",
    "straight_line_m",
]
