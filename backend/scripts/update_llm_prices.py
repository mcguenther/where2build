#!/usr/bin/env python3
"""Refreshes ``ops/llm-preise.json`` from the provider's own price list.

    python scripts/update_llm_prices.py            # write the file
    python scripts/update_llm_prices.py --json     # and report what changed

Why a fetch and not a model. The obvious way to keep prices current is to ask
an LLM what they are, and it is the wrong way round: OpenRouter *publishes*
them, as data, at ``/api/v1/models``, and a model asked the same question would
be reciting a page it fetched at best and remembering one at worst. A number
that ends up on a bill is worth reading from the source that issues it. The
same holds for the exchange rate, which comes from the ECB's daily reference
rates rather than from any conversion service.

A provider without such an endpoint is the case where asking a model earns its
keep, and this script is the place that would go -- one function, writing the
same file. Nothing else has to change, because everything downstream reads the
file and not the provider.

The file is committed, so this runs and the change is reviewed like any other:
a price that moves is a diff somebody can see. It is also listed in
``ops/jobs.json``, monthly, for a deployment that would rather not wait for
somebody to remember.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import xml.etree.ElementTree as ElementTree
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = BACKEND_DIR.parent / "ops" / "llm-preise.json"

MODELS_URL = "https://openrouter.ai/api/v1/models"
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
TIMEOUT_S = 60

# Prices arrive per token and are stored per million, which is how every
# provider quotes them and the only form in which the numbers are readable.
PER_MILLION = 1_000_000


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "where2build/preise"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as answer:  # noqa: S310
        return answer.read()


def usd_per_euro() -> tuple[float, str]:
    """The ECB's reference rate, and the day it is from."""

    root = ElementTree.fromstring(fetch(ECB_URL))
    namespace = {"ecb": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}
    day = root.find(".//ecb:Cube[@time]", namespace)
    if day is None:
        raise ValueError("Die EZB-Datei enthält keinen Tageskurs.")
    for entry in day:
        if entry.get("currency") == "USD":
            return float(entry.get("rate", "")), day.get("time", "")
    raise ValueError("Die EZB-Datei nennt keinen USD-Kurs.")


def prices() -> dict[str, dict[str, float]]:
    """Every model with a price, per million tokens, in USD."""

    answer = json.loads(fetch(MODELS_URL))
    found: dict[str, dict[str, float]] = {}
    for model in answer.get("data", []):
        pricing = model.get("pricing") or {}
        try:
            prompt = float(pricing.get("prompt", 0)) * PER_MILLION
            completion = float(pricing.get("completion", 0)) * PER_MILLION
        except (TypeError, ValueError):
            continue
        # A free model is priced, at zero; a model with no price at all is one
        # this file cannot say anything about, and a zero there would read as
        # "costs nothing" rather than "unknown".
        if "prompt" not in pricing or "completion" not in pricing:
            continue
        found[model["id"]] = {"ein_je_mio_usd": round(prompt, 6), "aus_je_mio_usd": round(completion, 6)}
    if not found:
        raise ValueError("Die Modellliste enthielt keinen einzigen Preis.")
    return dict(sorted(found.items()))


def build() -> dict:
    rate, rate_day = usd_per_euro()
    return {
        "_comment": [
            "Preise je Million Tokens, in USD, wie der Anbieter sie veröffentlicht,",
            "plus der Tageskurs der EZB, mit dem die Oberfläche in Euro umrechnet.",
            "Erzeugt von backend/scripts/update_llm_prices.py -- nicht von Hand",
            "pflegen, sondern das Skript laufen lassen und den Diff ansehen.",
            "Ein Modell, das hier fehlt, kostet nicht null: die Oberfläche zeigt",
            "dann Striche statt eines Betrags.",
        ],
        "stand": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "quellen": {"preise": MODELS_URL, "kurs": ECB_URL},
        "usd_je_eur": rate,
        "kurs_stand": rate_day,
        "modelle": prices(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--json", action="store_true", help="Report the result as JSON.")
    args = parser.parse_args(argv)

    try:
        fresh = build()
    except Exception as error:  # noqa: BLE001 -- a job reports, it does not trace
        print(f"Preise nicht aktualisiert: {error}", file=sys.stderr)
        return 1

    before = {}
    if args.target.exists():
        try:
            before = json.loads(args.target.read_text(encoding="utf-8")).get("modelle", {})
        except (OSError, ValueError):
            before = {}

    args.target.parent.mkdir(parents=True, exist_ok=True)
    args.target.write_text(json.dumps(fresh, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    after = fresh["modelle"]
    changed = [name for name, value in after.items() if before.get(name) != value]
    report = {
        "datei": str(args.target),
        "modelle": len(after),
        "neu_oder_geaendert": len(changed),
        "kurs": fresh["usd_je_eur"],
        "kurs_stand": fresh["kurs_stand"],
    }
    print(json.dumps(report, ensure_ascii=False) if args.json else
          f"{len(after)} Modelle, davon {len(changed)} neu oder geändert; "
          f"Kurs {fresh['usd_je_eur']} USD je Euro vom {fresh['kurs_stand']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
