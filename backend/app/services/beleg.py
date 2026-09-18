"""The gate a model value has to pass before it becomes an Indiz.

A language model is the last reader in this chain, not the first, and this
module is what makes that safe rather than merely stated. Four tests, in this
order, and the first is the cheapest and catches the case the whole thing
exists for:

1. **The Beleg stands verbatim in the text.** Normalised over whitespace,
   quotation marks and case — and over nothing else. A sentence the page does
   not contain did not come off the page.
2. **The value stands in the Beleg.** In German notation, so „1.076" and „1076"
   are one number and „748,50" is 748.5. A Beleg that quotes a real sentence
   about something else is a real sentence about something else.
3. **The value is within bounds.** The same bounds the deterministic readers
   have. A plot of 4 m² and one of 90 000 m² are reading errors, not plots.
4. **It agrees with what was read deterministically.** Where the two disagree
   the deterministic value wins and the difference is shown, never resolved
   quietly — the rule this project applies to every other contradiction.

Test 1 is the one that matters. Advert 2418686487 states 748,50 m² and „92,00 €
pro m²“ and never states a price; 748,5 x 92 is 68 862 €, which a model rounds
to 69 000 € and writes a Beleg for that stands nowhere on the page. Computing
is not reading, and a price nobody wrote is not a statement in a listing.

Nothing here talks to a service, and nothing here is German-language-aware
beyond number notation. It is a string comparison, which is exactly why it can
be trusted to police a component that cannot be.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

# What a value of each kind may be. The same figures the deterministic readers
# use: `read_area` refuses below 10 m², `InseratFelder` refuses a negative
# price. Generous on purpose — this test is here to catch a misread decimal
# point, not to have an opinion about the property market.
BOUNDS: dict[str, tuple[float, float]] = {
    "grundstuecksflaeche_m2": (10.0, 100_000.0),
    "kaufpreis_eur": (1_000.0, 50_000_000.0),
}

# How close two readings of the same number have to be to count as one. Half a
# square metre: „748,50" and „748,5" are the same figure written twice.
TOLERANCE = 0.005

# How far a deterministic and a model value may differ before it is a
# contradiction rather than a rounding. One percent — „ca. 1.025 qm" against
# „1.025 m²" is not a disagreement.
AGREEMENT = 0.01

# A number as German writes it: thousands dots or spaces, a decimal comma.
_NUMBER = re.compile(r"\d{1,3}(?:[.\s]\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?")

# Everything a quotation mark can be, and a dash can be, on the four recorded
# portals. A model normalises these silently; so does this.
_QUOTES = "„“”\"'‚‘’«»‹›"
_DASHES = "–—−‑‐"


def normalise(text: str) -> str:
    """One spelling of a piece of text, for comparing it against another.

    Case, whitespace, quotation marks and dash shapes — and nothing else. A
    normalisation that also dropped punctuation would let „6 km entfernt." pass
    for „6 km entfernt?", and the point of this test is that it is strict.
    """

    folded = unicodedata.normalize("NFKC", text).casefold()
    for quote in _QUOTES:
        folded = folded.replace(quote, "")
    for dash in _DASHES:
        folded = folded.replace(dash, "-")
    return " ".join(folded.split())


def quotes_the_text(beleg: str | None, text: str) -> bool:
    """Test 1: whether the Beleg stands in the page verbatim."""

    if not beleg or not beleg.strip():
        return False
    return normalise(beleg) in normalise(text)


def german_numbers(text: str) -> list[float]:
    """Every number in a piece of German-written text, as floats.

    „1.076 m²“ is 1076 and „748,50 m²“ is 748.5. A thousands dot only counts as
    one when it is followed by exactly three digits, which is what separates
    „1.076“ from „1.5“ — and a listing writes both.
    """

    out: list[float] = []
    for raw in _NUMBER.findall(text):
        cleaned = raw.replace(" ", "")
        if re.fullmatch(r"\d{1,3}(?:[.]\d{3})+(?:,\d+)?", cleaned):
            cleaned = cleaned.replace(".", "")
        cleaned = cleaned.replace(",", ".")
        try:
            out.append(float(cleaned))
        except ValueError:
            continue
    return out


def states_the_value(value: Any, beleg: str) -> bool:
    """Test 2: whether the Beleg actually carries the value the model reported.

    A number has to stand there as a number; a piece of text has to stand there
    as text. „Der Kaufpreis beträgt 199.000 €“ is a Beleg for 199000 and for
    nothing else, however plausible the other figure is.
    """

    if isinstance(value, str):
        return normalise(value) in normalise(beleg)
    if isinstance(value, (int, float)):
        return any(abs(found - float(value)) <= TOLERANCE for found in german_numbers(beleg))
    return False


def within_bounds(field: str, value: Any) -> bool:
    """Test 3: whether the value is one this field can have at all."""

    if not isinstance(value, (int, float)):
        return True
    low, high = BOUNDS.get(field, (float("-inf"), float("inf")))
    return low <= float(value) <= high


def agrees_with(value: Any, known: Any) -> bool:
    """Test 4: whether a model value says the same as one already read.

    ``None`` on either side is not a disagreement — that is the gap the model
    was asked to fill.
    """

    if value is None or known is None:
        return True
    if isinstance(value, (int, float)) and isinstance(known, (int, float)):
        if not known:
            return not value
        return abs(float(value) - float(known)) / abs(float(known)) <= AGREEMENT
    return normalise(str(value)) == normalise(str(known))


@dataclass(frozen=True, slots=True)
class Urteil:
    """What the gate decided about one value, and why.

    ``grund`` is German because it is shown: a value the search quietly dropped
    is a value nobody can argue with. Composed from the templates below, never
    written by the model whose answer it is about.
    """

    feld: str
    wert: Any
    beleg: str | None
    angenommen: bool
    grund: str | None = None

    @property
    def verworfen(self) -> bool:
        return not self.angenommen


def _zahl(value: Any) -> str:
    """A number as German writes it, for a sentence a person reads.

    „748,5" and „50.000.000", never „748.5" or „5e+07" — the refusal is shown
    to whoever has to decide whether the model or the page is right, and a
    figure in the wrong notation is one more thing for them to decode.
    """

    if not isinstance(value, (int, float)):
        return str(value)
    text = f"{float(value):,.2f}".rstrip("0").rstrip(".")
    whole, _, fraction = text.partition(".")
    whole = whole.replace(",", ".")
    return f"{whole},{fraction}" if fraction else whole


def _excerpt(beleg: str | None, limit: int = 80) -> str:
    if not beleg:
        return ""
    text = " ".join(beleg.split())
    return text if len(text) <= limit else f"{text[:limit].rstrip()}…"


def check(
    field: str,
    value: Any,
    beleg: str | None,
    text: str,
    known: Any = None,
) -> Urteil:
    """The four tests on one value, in order, stopping at the first refusal."""

    if value is None:
        return Urteil(field, None, beleg, False, "Kein Wert gelesen.")
    if not quotes_the_text(beleg, text):
        return Urteil(
            field,
            value,
            beleg,
            False,
            (
                f"Der Beleg „{_excerpt(beleg)}“ steht so nicht im Anzeigentext."
                if beleg and beleg.strip()
                else "Ohne Beleg aus dem Anzeigentext wird der Wert nicht übernommen."
            ),
        )
    assert beleg is not None
    if not states_the_value(value, beleg):
        return Urteil(
            field,
            value,
            beleg,
            False,
            f"Im belegten Satz steht „{_zahl(value)}“ nicht — der Beleg passt nicht zum Wert.",
        )
    if not within_bounds(field, value):
        low, high = BOUNDS[field]
        return Urteil(
            field, value, beleg, False,
            f"„{_zahl(value)}“ liegt außerhalb des Bereichs, den dieses Feld haben "
            f"kann ({_zahl(low)} bis {_zahl(high)}) — das ist ein Lesefehler, "
            "kein Grundstück.",
        )
    if not agrees_with(value, known):
        return Urteil(
            field, value, beleg, False,
            f"Die Seite selbst nennt „{_zahl(known)}“, das Modell „{_zahl(value)}“. "
            "Die Angabe der Seite gilt.",
        )
    return Urteil(field, value, beleg, True)


def refusal_note(verdicts: list[Urteil]) -> str | None:
    """One German sentence about everything the gate turned away.

    Said out loud rather than counted: „drei Werte verworfen“ tells nobody
    which three, and the whole reason a model value carries its Beleg is that a
    person can look the disagreement up.
    """

    refused = [verdict for verdict in verdicts if verdict.verworfen and verdict.wert is not None]
    if not refused:
        return None
    reasons = " ".join(f"{verdict.feld}: {verdict.grund}" for verdict in refused)
    lead = (
        "Eine Angabe des Modells wurde nicht übernommen."
        if len(refused) == 1
        else f"{len(refused)} Angaben des Modells wurden nicht übernommen."
    )
    return f"{lead} {reasons}"


__all__ = [
    "AGREEMENT",
    "BOUNDS",
    "TOLERANCE",
    "Urteil",
    "agrees_with",
    "check",
    "german_numbers",
    "normalise",
    "quotes_the_text",
    "refusal_note",
    "states_the_value",
    "within_bounds",
]
