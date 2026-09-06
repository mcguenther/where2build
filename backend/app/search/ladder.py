"""The tolerance staircase: start hard, open up only when a rung comes back empty.

A fixed area tolerance is always wrong. Too tight and the right parcel falls
out; too wide and dozens remain. So the search does not choose one -- it starts
at the tightest band the listing's *wording* justifies and widens only when the
cadastre answers with nothing.

Measured against Gemarkung Großbothen (1 131 parcels) around the reference
listing's 502 m², re-verified 05.09.2026:

    +-0 %      502-502     1 candidate, and it is the right one
    +-0,5 %    500-504     2
    +-1 %      497-507     5
    +-2 %      492-512     12
    +-5 %      477-527     25
    +-10 %     452-552     46
    +-20 %     402-602     83

Each rung is one ``resultType=hits`` request, so an empty rung costs a round
trip and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass

from .indicia import AreaStatement

# The rungs for a figure written exactly. Zero first: an exact area is an
# official fact and may filter hard.
EXACT_STEPS: tuple[float, ...] = (0.0, 0.005, 0.01, 0.02, 0.05)

# The rungs for a rounded figure. Zero is meaningless here -- „ca. 500 m²“ is
# precisely the claim that the true value is not 500 -- so the ladder starts at
# one per cent and reaches further, because the rounding itself is unknown.
ROUNDED_STEPS: tuple[float, ...] = (0.01, 0.02, 0.05, 0.10)

# Words that turn a number into a bound rather than a value.
_LOWER_BOUND_WORDS = ("ab", "mind", "mindestens")
_ROUNDING_WORDS = ("ca", "ca.", "circa", "rund", "etwa", "ungefähr", "ungefaehr", "gut", "knapp")


@dataclass(frozen=True, slots=True)
class Rung:
    """One step of the staircase.

    ``hard`` says whether surviving this rung is an official fact or merely a
    good sign. Only the zero rung of an exactly written area is hard; every
    other band is a tolerance somebody chose, and a chosen tolerance may order
    the list but must never delete from it.
    """

    lower: float
    upper: float
    label: str
    hard: bool

    @property
    def text(self) -> str:
        if self.lower == self.upper:
            return f"genau {self.lower:g} m²"
        return f"{self.lower:g} bis {self.upper:g} m²"


def tolerance_ladder(statement: AreaStatement | None) -> list[Rung]:
    """The rungs to try, tightest first, derived from how the area is written.

    The staircase comes from the wording, not from a constant: „502 m²“ starts
    at zero, „ca. 500 m²“ at one per cent, „ab 450 m²“ is a one-sided bound and
    never a band at all, and „450-600 m²“ is taken literally.
    """

    if statement is None:
        return []

    wording = statement.wording.rstrip(".").lower()

    # An explicit range is the listing's own band. Nothing to widen.
    if statement.upper is not None and statement.upper > statement.value:
        return [
            Rung(
                lower=statement.value,
                upper=statement.upper,
                label="wie angegeben",
                hard=False,
            )
        ]

    # A lower bound is not a band. Everything at least this large qualifies,
    # and the upper end is left open rather than invented.
    if any(wording.startswith(word) for word in _LOWER_BOUND_WORDS):
        return [
            Rung(
                lower=statement.value,
                upper=statement.value * 20,
                label="untere Schranke",
                hard=False,
            )
        ]

    rounded = any(wording.startswith(word) for word in _ROUNDING_WORDS)
    steps = ROUNDED_STEPS if rounded else EXACT_STEPS
    rungs: list[Rung] = []
    for step in steps:
        margin = statement.value * step
        rungs.append(
            Rung(
                lower=round(statement.value - margin, 2),
                upper=round(statement.value + margin, 2),
                label="exakt" if step == 0 else f"±{step * 100:g} %".replace(".", ","),
                # Only an exactly written figure at zero tolerance is an
                # official fact. Everything else is a tolerance somebody chose.
                hard=step == 0 and not rounded,
            )
        )
    return rungs


def confirmation_rung(rungs: list[Rung], stopped_at: int) -> Rung | None:
    """The next rung out, opened once the loop has stopped.

    The loop halts at the first rung that returns anything, which risks halting
    on a coincidence. So one more request is spent widening by a step and the
    extra candidates are scored: on the reference listing the zero rung yields
    790/11 alone and the half-per-cent rung adds 238/3 at 500 m², 1 730 m away
    and on another street -- it loses clearly, so the halt stands.

    It only catches the neighbouring-rung case. A parcel far outside the band
    is not recovered by this and never was.
    """

    return rungs[stopped_at + 1] if stopped_at + 1 < len(rungs) else None
