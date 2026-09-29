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
# the price on ImmoScout's own main criteria. The unit stands on either side of
# the number and German portals use both sides:
#
#   „Kaufpreis 370,62 €/m²"       -- behind it
#   „Kaufpreis pro m²: 92,00 €"   -- in front, as part of the label
#
# so there are two patterns, one per side, and a value that either of them
# touches is a rate. The question is asked about the *value*, never about a
# value-and-label pair: a rate does not become a price because some other word
# happens to stand nearer to it, and asking per pair let „Kaufpreis (Preis pro
# m²: 92 €) 199.000 €" answer 92.
#
# Neither carries „^". Measured 18.09.2026: the original did, and never matched
# anything. `pattern.match(text, pos)` anchors the match at `pos`, but „^"
# inside the pattern still means the start of the *string*, so the guard was
# dead from the day it was written and „Kaufpreis: 92,00 €/m²" read as a
# purchase price of 92 €. Its two tests passed throughout, because on both
# recordings the real price stands nearer its label than the rate does and
# `_nearest` wins without the guard ever being consulted.
_UNIT = r"(?:m²|m2|qm|Quadratmeter)"
_PER_UNIT_AFTER = re.compile(rf"[\s|]*(?:/|pro\b|je\b)[\s|]*{_UNIT}", re.IGNORECASE)
# „…pro m²:  92,00 €". Anchored at the end of the span so only a marker that
# actually touches the number counts -- „Fläche je m² bebaubar, Kaufpreis
# 199.000 €" has the words but not the adjacency.
_PER_UNIT_BEFORE = re.compile(
    rf"(?:/|\bpro\b|\bje\b)[\s|]*{_UNIT}[\s|:.,\-–—]*\Z", re.IGNORECASE
)
# How far back a label's own unit may stand. „pro Quadratmeter: " is 19.
_UNIT_LOOKBACK = 32

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


def _is_rate(text: str, value: re.Match[str], *, lookback: int = _UNIT_LOOKBACK) -> bool:
    """Whether this number is a rate per square metre rather than a price."""

    if _PER_UNIT_AFTER.match(text, value.end()):
        return True
    return bool(
        _PER_UNIT_BEFORE.search(text, max(0, value.start() - lookback), value.start())
    )


def _nearest(
    text: str,
    label_re: re.Pattern[str],
    value_re: re.Pattern[str],
    *,
    drop_rates: bool = False,
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
            if drop_rates and _is_rate(text, value):
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

    value = _nearest(flat_text(html), _PRICE_LABEL_RE, _PRICE_VALUE, drop_rates=True)
    if value is None or not 0 < value < 100_000_000:
        return None
    return int(round(value))


# A German location line, and the portals write it four ways:
#
#   ohne-makler    „Maschinenhausstraße, | 01587 Riesa | – Sachsen"
#   ImmoScout      „Grünau-Siedlung, 04207 Leipzig"
#   Kleinanzeigen  „04668 Sachsen – Grimma"
#   immowelt       „… zum Kauf Naunhof,Naunhof(04683)"  -- Ortsteil, Gemeinde,
#                  and the postcode *behind* them in brackets
#
# The postcode is the anchor -- five digits are unambiguous in a German page in
# a way no name is. What follows it is the place *unless* it is a Bundesland, in
# which case the place is behind the dash: that is Kleinanzeigen's order, and
# reading „Sachsen" as the town is how „600 m² in Brehna" once resolved to a
# parcel 100 km away.
_WORD = r"[A-ZÄÖÜ][\wäöüß.'-]*"
_NAME = rf"{_WORD}(?:[ -]{_WORD}){{0,3}}"
_LOCATION_RE = re.compile(
    rf"(?<!\d)(?P<plz>\d{{5}})(?!\d)[\s|]*(?P<tail>{_NAME})?"
    rf"(?:[\s|]*[-–—][\s|]*(?P<behind>{_NAME}))?"
)
# immowelt's order, measured on its exposé titles as the search index holds
# them („Haus 49.34 m² 99000 € zum Kauf Naunhof,Naunhof(04683)") -- the page
# itself answers every request of ours with DataDome's 403. With the postcode
# in brackets behind the place, the pattern above finds it and nothing after
# it, so the first postcode *with* a name was the broker's address further
# down: „04463 Großpösna" for a plot in Naunhof.
#
# Scanned leftwards from the bracket, a name has no natural start -- German
# nouns are capitalised too, and „Einfamilienhaus Bad Lausick (04651)" is
# three capitalised words. So the place is at most two words and the Ortsteil
# in front of the comma one: „Kauf Naunhof,Naunhof" gives Naunhof and Naunhof,
# not „Kauf Naunhof". A multi-word Ortsteil loses its first word; the search
# only takes that slot when the Gemarkung directory knows the name anyway.
_PLACE_FIRST_RE = re.compile(
    rf"(?:(?P<ortsteil>{_WORD})[\s|]*,[\s|]*)?(?P<ort>{_WORD}(?:[ -]{_WORD})?)"
    r"[\s|]*\([\s|]*(?P<plz>\d{5})[\s|]*\)"
)
# Case-sensitive in the name, and only the suffix may be either case. With the
# whole pattern case-insensitive, „[A-ZÄÖÜ]" matched lower case as well, and
# „zum Kauf Naunhof," in that same immowelt title read as a street: three words
# and a town ending in „-hof".
_STREET_RE = re.compile(
    rf"(?P<street>{_NAME}(?i:straße|strasse|str\.|weg|gasse|allee|platz|ring|damm|ufer|"
    r"chaussee|steig|pfad|hof|berg|winkel|zeile|graben))[\s|,]*\Z"
)
# How far in front of the location line its street may begin.
_STREET_LOOKBACK = 80


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
    # one that yields a *name* wins, with a bare postcode as the fallback. Both
    # orders are tried in one pass, in the order they stand in the page: the
    # listing's own location comes before the broker's address on every portal
    # recorded, and that holds only if neither order is asked first.
    matches = sorted(
        [*_LOCATION_RE.finditer(text), *_PLACE_FIRST_RE.finditer(text)],
        key=lambda m: m.start(),
    )
    named = [m for m in matches if m.re is _PLACE_FIRST_RE or m.group("tail")]
    match = named[0] if named else (matches[0] if matches else None)
    if match and match.re is _PLACE_FIRST_RE:
        found["plz"] = match.group("plz")
        found["ort"] = match.group("ort")
        ortsteil = match.group("ortsteil")
        # „Naunhof,Naunhof(04683)": the portal names the Ortsteil even where it
        # is the town itself, and saying it twice says nothing.
        if ortsteil and ortsteil != found["ort"]:
            found["ortsteil"] = ortsteil
    elif match:
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

    # The street of *this* line, standing directly in front of it. Searched
    # anywhere, the first street-shaped phrase in the page won, and it was
    # joined to whatever postcode the line above had picked -- a street from
    # one address and a town from another.
    if match:
        street = _STREET_RE.search(text, max(0, match.start() - _STREET_LOOKBACK), match.start())
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
    # The Ortsteil in front of the postcode, which is ImmoScout's order and the
    # slot the search reads a district out of.
    parts = [
        part
        for part in (read.get("strasse"), read.get("ortsteil"), head, read.get("bundesland"))
        if part
    ]
    return ", ".join(parts) or None
