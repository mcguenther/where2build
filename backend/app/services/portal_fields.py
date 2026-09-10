"""Reading a listing without knowing the portal.

Three portals were recorded to derive this, and they agree about nothing except
the German words:

* ``immobilienscout24.de`` — ``<dt>Grundstücksfläche ca.</dt><dd>742  m²</dd>``
* ``kleinanzeigen.de`` — ``<li …>Grundstücksfläche 1.025 m²</li>``
* ``ohne-makler.net`` — ``<span>5.366 m²</span><span>Grundstücksfläche</span>``

So **structure is the wrong thing to key on.** The third puts the value *before*
its label, in Tailwind spans with no semantic hook, and has no ``<dt>``, no
``<th>``, no price meta tag and no coordinate anywhere. What all three share is
the word and a value whose *unit* says what it is. This reader therefore
flattens the document to text, finds the label, and takes the nearest value of
the right shape on either side of it.

That is deliberately less clever than a per-portal selector and much harder to
break: a redesign moves elements around, and this does not care. Where a portal
*does* name its own fields the specific block still wins — see the ImmoScout
section of ``portals.py`` — because a structured field beats a rendered one.
Everything here is the floor under that, so an unknown portal is read rather
than refused.

Every pattern is asserted against all three recordings in
``tests/test_portal_fields.py``.
"""

from __future__ import annotations

import html as html_module
import re

from ..search.indicia import federal_state

# Flattening: scripts and styles out, every tag becomes one separator. The
# separator has to survive, because it is what keeps „Wohnfläche 120" in the
# next cell from being read as this cell's number -- and it has to be crossable,
# because two portals out of three put the number and its unit in *different*
# elements („742" then „m²").
_DROP = re.compile(r"<(script|style|noscript|svg)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_SEPARATORS = re.compile(r"(?:\s*\|\s*)+")


def flat_text(html: str) -> str:
    """The document as one line, with element boundaries kept as ``|``."""

    without_code = _DROP.sub(" ", html)
    without_comments = _COMMENT.sub("", without_code)
    text = html_module.unescape(_TAG.sub(" | ", without_comments))
    text = re.sub(r"[ \t\r\n\f\v ]+", " ", text)
    return _SEPARATORS.sub(" | ", text).strip()


# A number as a German page writes it, and its unit. `[\s|]*` between the two
# because the boundary may be an element boundary.
_AREA_VALUE = re.compile(
    r"(?<![\d,.])(\d{1,3}(?:[.\s]\d{3})*(?:,\d+)?|\d+(?:,\d+)?)[\s|]*(?:m²|m2|qm|Quadratmeter)\b",
    re.IGNORECASE,
)
_PRICE_VALUE = re.compile(
    r"(?<![\d,.])(\d{1,3}(?:[.\s]\d{3})*(?:,\d+)?|\d+(?:,\d+)?)[\s|]*(?:€|EUR\b|Euro\b)",
    re.IGNORECASE,
)
# „370,62 €/m²" is a rate, not the asking price, and it sits one element from
# the price on ImmoScout's own main criteria. Same for „Preis pro m²".
_PER_UNIT = re.compile(r"^[\s|]*(?:/|pro\b|je\b)[\s|]*(?:m²|m2|qm)", re.IGNORECASE)

# The labels, as the three portals write them. A leading boundary that excludes
# German letters is what keeps „Wohnfläche" and „Nutzfläche" out of „Fläche",
# and „Grundstückspreis" out of „Preis" would be wrong -- so the price labels
# are matched with a trailing boundary too.
_LABEL_BOUNDARY = r"(?<![A-Za-zÄÖÜäöüß])"

_AREA_LABELS = (
    "Grundstücksfläche",
    "Grundstücksgröße",
    "Grundstücksfl",
    "Fläche des Grundstücks",
    "Grundfläche",
    "Grundstück",
    "Fläche",
)
_PRICE_LABELS = (
    "Kaufpreis",
    "Angebotspreis",
    "Verkaufspreis",
    "Kaufsumme",
    "Preis",
)

# How far from its label a value may stand. Measured on the three recordings:
# ImmoScout 5 characters („Grundstücksfläche ca. | 742 m²"), Kleinanzeigen 1
# (same element), ohne-makler 3 with the value first. 60 is generous for all of
# them and still tight enough to keep prose out: „Die großzügige
# Grundstücksfläche bietet ideale Voraussetzungen …" carries no m² value near
# the word, so it contributes nothing.
_WINDOW = 60


def _labels(names: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(
        _LABEL_BOUNDARY + "(?:" + "|".join(re.escape(name) for name in names) + ")",
        re.IGNORECASE,
    )


_AREA_LABEL_RE = _labels(_AREA_LABELS)
_PRICE_LABEL_RE = _labels(_PRICE_LABELS)


def german_number(raw: str) -> float | None:
    """A number out of what a German page wrote.

    The dot groups thousands only in threes, and a comma settles it outright:
    „1.025" is 1025, „51.189265" is a coordinate, „1.025,50" is 1025,5. Kept
    here as well as in ``portals.py`` deliberately -- this module is the one an
    unknown portal goes through, and it must not depend on the other's order of
    definitions.
    """

    digits = raw.replace(" ", "").replace(" ", "")
    if "," in digits:
        digits = digits.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", digits):
        digits = digits.replace(".", "")
    try:
        return float(digits)
    except ValueError:
        return None


def _nearest(
    text: str,
    label_re: re.Pattern[str],
    value_re: re.Pattern[str],
    *,
    reject_after: re.Pattern[str] | None = None,
) -> float | None:
    """The value nearest to any occurrence of the label, either side of it.

    Both directions, because one portal in three writes the value first. The
    closest match across every occurrence of the label wins, so a heading far
    from any number loses to the one row that has both.
    """

    best: tuple[int, float] | None = None
    for label in label_re.finditer(text):
        window_start = max(0, label.start() - _WINDOW)
        window_end = min(len(text), label.end() + _WINDOW)
        for value in value_re.finditer(text, window_start, window_end):
            if reject_after and reject_after.match(text, value.end()):
                continue
            number = german_number(value.group(1))
            if number is None:
                continue
            distance = (
                label.start() - value.end()
                if value.end() <= label.start()
                else value.start() - label.end()
            )
            distance = max(distance, 0)
            if best is None or distance < best[0]:
                best = (distance, number)
    return None if best is None else best[1]


def read_area_m2(html: str) -> int | None:
    """The plot area in square metres, from whichever shape the portal uses."""

    value = _nearest(flat_text(html), _AREA_LABEL_RE, _AREA_VALUE)
    if value is None or not 1 <= value <= 10_000_000:
        return None
    return int(round(value))


def read_price_eur(html: str) -> int | None:
    """The asking price in euro. A per-square-metre rate is not a price."""

    value = _nearest(
        flat_text(html), _PRICE_LABEL_RE, _PRICE_VALUE, reject_after=_PER_UNIT
    )
    if value is None or not 0 < value < 100_000_000:
        return None
    return int(round(value))


# A German location line, and the three portals write it three ways:
#
#   ohne-makler    „Maschinenhausstraße, | 01587 Riesa | – Sachsen"
#   ImmoScout      „Grünau-Siedlung, 04207 Leipzig"
#   Kleinanzeigen  „04668 Sachsen – Grimma"
#
# The postcode is the anchor -- five digits are unambiguous in a German page in
# a way no name is. What follows it is the place *unless* it is a Bundesland, in
# which case the place is behind the dash: that is Kleinanzeigen's order, and
# reading „Sachsen" as the town is how „600 m² in Brehna" once resolved to a
# parcel 100 km away.
_NAME = r"[A-ZÄÖÜ][\wäöüß.'-]*(?:[ -][A-ZÄÖÜ][\wäöüß.'-]*){0,3}"
_LOCATION_RE = re.compile(
    rf"(?<!\d)(?P<plz>\d{{5}})(?!\d)[\s|]*(?P<tail>{_NAME})?"
    rf"(?:[\s|]*[-–—][\s|]*(?P<behind>{_NAME}))?"
)
_STREET_RE = re.compile(
    rf"(?P<street>{_NAME}(?:straße|strasse|str\.|weg|gasse|allee|platz|ring|damm|ufer|"
    r"chaussee|steig|pfad|hof|berg|winkel|zeile|graben))(?=[\s|,]*\d{5}|[\s|]*,)",
    re.IGNORECASE,
)


def read_location(html: str) -> dict[str, str]:
    """Postcode, place and Bundesland, from a line every German portal writes.

    Only what was actually found. The Bundesland is the cheapest hard filter
    this app has -- ALKIS is state-specific -- and it is the one field the
    portals put in the most different places, so it is also searched for on its
    own rather than only in the line.
    """

    text = flat_text(html)
    found: dict[str, str] = {}

    # Not the first postcode in the document: the first one on an ImmoScout
    # page sits inside the analytics block, where it is followed by the next
    # JSON key rather than by a town. So every postcode is tried and the first
    # one that yields a *name* wins, with a bare postcode as the fallback.
    matches = list(_LOCATION_RE.finditer(text))
    match = next((m for m in matches if m.group("tail")), matches[0] if matches else None)
    if match:
        found["plz"] = match.group("plz")
        tail, behind = match.group("tail"), match.group("behind")
        if tail and federal_state(tail) == tail:
            # „04668 Sachsen – Grimma": the state stands where the place would.
            found["bundesland"] = tail
            if behind:
                found["ort"] = behind
        elif tail:
            found["ort"] = tail
            if behind and federal_state(behind) == behind:
                found["bundesland"] = behind

    if "bundesland" not in found:
        state = federal_state(text)
        if state:
            found["bundesland"] = state

    street = _STREET_RE.search(text)
    if street:
        found["strasse"] = street.group("street")

    return found


def read_fields(html: str) -> dict[str, object]:
    """Everything this reader can get without knowing the portal."""

    found: dict[str, object] = {}
    area = read_area_m2(html)
    price = read_price_eur(html)
    if area is not None:
        found["grundstuecksflaeche_m2"] = area
    if price is not None:
        found["kaufpreis_eur"] = price
    found.update(read_location(html))
    return found


def location_line(read: dict[str, str]) -> str | None:
    """The location as one German line, composed from the parts that were read.

    Composed, not written: every piece is the portal's own. Street, postcode
    and place in the order a German address has them, the Bundesland last
    because that is where the location field of two of the three portals puts
    it — and because the search reads it from anywhere in the string.
    """

    head = " ".join(part for part in (read.get("plz"), read.get("ort")) if part)
    parts = [part for part in (read.get("strasse"), head, read.get("bundesland")) if part]
    return ", ".join(parts) or None
