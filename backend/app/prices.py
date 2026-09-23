"""What a model call costs, read from a file somebody can look at.

The tokens are counted in ``app/telemetry.py``; this turns them into money.
Deliberately two steps, because they fail differently: a token count is a fact
this server measured, and a price is a claim about somebody else's price list
that is stale the moment it is written down. So the price list is a file with a
date on it (``ops/llm-preise.json``, refreshed by
``scripts/update_llm_prices.py``), and everything it cannot answer comes out as
``None`` rather than as a number.

**A missing model is not a free model.** The one thing this module must never
do is return 0,00 € for a model the file does not list -- that is the same
mistake as computing a figure from a missing input, and it would show up as a
deployment that costs nothing. The interface shows dashes and says the file has
no price for that model.

Euros, because that is what the bill is read in, converted with the ECB's daily
reference rate that travels in the same file. The rate carries its own date and
the interface says both -- a conversion whose rate nobody can see is a number
nobody can check.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PER_MILLION = 1_000_000


@dataclass(frozen=True)
class Prices:
    """The price list as it was loaded, or an empty one."""

    stand: str | None = None
    usd_per_euro: float | None = None
    rate_day: str | None = None
    sources: dict[str, str] = field(default_factory=dict)
    models: dict[str, dict[str, float]] = field(default_factory=dict)
    problem: str | None = None

    @property
    def usable(self) -> bool:
        return bool(self.models) and bool(self.usd_per_euro)

    def euro(self, model: str, tokens_in: int, tokens_out: int) -> float | None:
        """What those tokens cost at that model's price -- or ``None``.

        ``None`` for a model the file does not know, for a file that could not
        be read, and for a rate that is missing. Every one of those is "cannot
        say", and none of them is zero.
        """

        entry = self.models.get(model)
        if entry is None or not self.usd_per_euro:
            return None
        usd = (
            tokens_in * entry.get("ein_je_mio_usd", 0.0) + tokens_out * entry.get("aus_je_mio_usd", 0.0)
        ) / PER_MILLION
        return usd / self.usd_per_euro


def load_prices(path: Path | str) -> Prices:
    """Read the price list. A missing or broken file is a state, not a crash.

    The whole application works without it; what is lost is the column that
    says money, and the interface says why rather than showing zeroes.
    """

    target = Path(path)
    if not target.is_file():
        return Prices(problem=f"Keine Preisliste unter {target}.")
    try:
        raw: Any = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        logger.warning("Price list unreadable (%s): %s", target, error)
        return Prices(problem=f"Die Preisliste {target.name} ist unlesbar: {error}")
    models = raw.get("modelle")
    if not isinstance(models, dict):
        return Prices(problem=f"Die Preisliste {target.name} enthält kein Feld „modelle“.")
    rate = raw.get("usd_je_eur")
    return Prices(
        stand=raw.get("stand"),
        usd_per_euro=float(rate) if isinstance(rate, (int, float)) and rate > 0 else None,
        rate_day=raw.get("kurs_stand"),
        sources=raw.get("quellen") or {},
        models={
            name: {
                "ein_je_mio_usd": float(entry.get("ein_je_mio_usd", 0.0)),
                "aus_je_mio_usd": float(entry.get("aus_je_mio_usd", 0.0)),
            }
            for name, entry in models.items()
            if isinstance(entry, dict)
        },
    )
