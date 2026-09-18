"""Where the deterministic readers and a model disagree, written down.

A model in this project is a *teacher* whose answer is never trusted and always
checked. That makes it something better than a fallback: every place it reads
something the patterns in `search.indicia` did not, and every place the two
disagree, is a sentence somebody could write a pattern against — and the Beleg
gate has already proved that sentence stands verbatim in the page. So the
disagreement is not noise to be smoothed over. It is the corpus.

Four kinds, and each says something different:

* **Lücke** — the deterministic reader found nothing and the model found
  something the gate accepted. The pattern that is missing, with the sentence
  it is missing on. This is the one that improves the pipeline.
* **Widerspruch** — both found something and they differ. Either the pattern is
  wrong or the model is; which one is a question for a person, which is exactly
  why the Beleg travels.
* **Verworfen** — the model produced something the gate refused. The teacher
  being wrong, and worth as much as the other two: it is the measurement that
  says how far a model may be trusted here, and it is the only one that can
  show the gate earning its keep.
* **Einig** — both read the same thing. Nothing to learn from one row of it,
  and everything to learn from how many there are: „the model found six things
  the patterns missed" means nothing without the denominator. Kept as
  statistics and kept *out* of the listing, because a log that lists the cases
  where the pipeline was already right is a log nobody reads — the read view
  counts them and shows the rest.

Where it goes. Postgres when the deployment has one (`DATABASE_URL`), a JSONL
file under the cache directory otherwise — a development machine must not need
Postgres before it can resolve a parcel, and this is a diagnostic log, not
somebody's data. Both are written the same way and read the same way.

What it must never hold. The extraction schema carries no contact details, so
none reach a value here; a *Beleg* is a whole sentence out of the page, though,
and a sentence can carry a telephone number whatever the schema says. Every
Beleg is therefore scrubbed of the two shapes that matter and capped, before it
is written anywhere. The rule in `CLAUDE.md` is that no contact details are
stored, and it holds for a diagnostic log too.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

logger = logging.getLogger(__name__)

# What a divergence can be. German, like every other value that crosses the
# wire or lands in the database.
ARTEN = ("luecke", "widerspruch", "verworfen", "einig")

# The kinds worth reading row by row. „einig" is the denominator, not a
# finding, so the listing leaves it out unless it is asked for by name.
BEFUNDE = ("luecke", "widerspruch", "verworfen")

# How much of a sentence is kept. Long enough for the clause a pattern would be
# written against, short enough that a whole paragraph cannot arrive by way of
# one greedy Beleg.
MAX_BELEG_CHARS = 300

# The two shapes a sentence can carry that this project does not store. Not a
# general anonymiser -- a German telephone number and an e-mail address are what
# an advert's contact block actually contains.
_PHONE = re.compile(r"(?:\+49|0)[\d\s/().-]{6,}\d")
_MAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_REDACTED = "[entfernt]"


def scrub(text: str | None) -> str | None:
    """A sentence with the two shapes this project does not keep taken out."""

    if not text:
        return None
    cleaned = _MAIL.sub(_REDACTED, " ".join(text.split()))
    cleaned = _PHONE.sub(_REDACTED, cleaned)
    return cleaned[:MAX_BELEG_CHARS]


def fingerprint(text: str) -> str:
    """A short, stable name for one listing's text.

    So a listing read three times is one row and not three -- and so the row
    can say *which* listing without the listing having to be stored.
    """

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class Abweichung:
    """One disagreement between the two readers, with what a person needs to judge it."""

    art: str
    feld: str
    regulaer: str | None
    modell: str | None
    beleg: str | None
    grund: str | None
    text_hash: str
    quelle_url: str | None = None
    modell_id: str | None = None
    vorlage: str | None = None
    gesehen_am: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def as_row(self) -> dict[str, Any]:
        data = asdict(self)
        data["gesehen_am"] = self.gesehen_am.isoformat()
        return data


# The fields a plot has exactly one of. Two different values there are two
# claims about one slot, so they contradict. Everywhere else — places, parcel
# numbers — there is no slot: an advert may legitimately name Großbothen *and*
# Grimma, and treating the second as a contradiction of the first is how one
# model answer and one pattern run turned into a cross product of rows.
SINGLE_VALUED = ("adresse", "kaufpreis_eur", "grundstuecksflaeche_m2")

# The kinds of Indiz that are all statements about one thing — a named place —
# and therefore share a slot. A Gemarkung and a Gemeinde of the same name are
# two readings of it; a Flurstück and a Fläche are not, however equal their
# digits happen to be. Measured 18.09.2026: without this, „flaeche 577" and
# „flurstueck 577" keyed alike and contradicted each other.
_PLACE_ARTEN = ("gemarkung", "gemeinde", "ortsteil", "ort", "strasse")

# „ort" is what a model reports when it will not say which level. It is a
# weaker claim about the same name, not a rival one, so it agrees with any
# level the patterns gave rather than disputing it.
_ANY_LEVEL = "ort"


def _slot(art: str) -> str:
    """Which slot a kind of Indiz speaks about."""

    return "ort" if art in _PLACE_ARTEN else art


def compare(
    *,
    deterministic: Iterable[tuple[str, str | None]],
    accepted: Iterable[tuple[str, str | None, str | None]],
    refused: Iterable[tuple[str, str | None, str | None, str | None]],
    text_hash: str,
    quelle_url: str | None = None,
    modell_id: str | None = None,
    vorlage: str | None = None,
) -> list[Abweichung]:
    """Every divergence between what the patterns read and what the model read.

    ``deterministic`` is ``(feld, wert)`` from the readers this project owns,
    ``accepted`` is ``(feld, wert, beleg)`` from the model after the gate, and
    ``refused`` is ``(feld, wert, beleg, grund)`` from the model before it.

    **A contradiction needs a slot**, and that is what decides how a pair is
    compared. The address, the price and the area are one each, so a second
    value is a rival reading of the same thing. A place is not: the slot there
    is the *name*, and what the two readers may disagree about is the level
    they put it on. Keyed the other way round — every model place against every
    pattern place of the same kind — „Großbothen" came back as a contradiction
    of „Grimma" although the advert names both, and 16 adverts produced 25
    contradictions of which almost none were one (measured 18.09.2026).

    So for a place: the same name on the same level is „einig", the same name
    on a different level is „widerspruch" and carries both, and a name only the
    model has is „luecke" — the row that improves the pipeline. A name only the
    patterns have is not recorded; it is the pipeline working, and this log
    exists to find what it misses.

    An agreement produces an „einig" row: it is the denominator every other
    number here needs — „six gaps" says nothing without „out of how many" — and
    the read view counts it rather than listing it.
    """

    # feld -> {key: spelling}, for the three that have one value each.
    fields: dict[str, dict[str, str]] = {}
    # (slot, value key) -> {art: spelling}, for everything that is a set.
    places: dict[tuple[str, str], dict[str, str]] = {}
    for name, value in deterministic:
        if not value:
            continue
        if name in SINGLE_VALUED:
            fields.setdefault(name, {})[_key(value)] = value
        else:
            places.setdefault((_slot(name), _key(value)), {})[name] = value

    def stated(name: str, value: str) -> dict[str, str]:
        """What the patterns said about this slot, as {label: spelling}."""

        if name in SINGLE_VALUED:
            return fields.get(name, {})
        return places.get((_slot(name), _key(value)), {})

    def reading(claims: dict[str, str], name: str) -> str | None:
        if not claims:
            return None
        if name in SINGLE_VALUED:
            return ", ".join(sorted(claims.values()))
        return ", ".join(f"{level} {spelling}" for level, spelling in sorted(claims.items()))

    out: list[Abweichung] = []
    common = dict(
        text_hash=text_hash, quelle_url=quelle_url, modell_id=modell_id, vorlage=vorlage
    )

    for name, value, beleg in accepted:
        if not value:
            continue
        claims = stated(name, value)
        if not claims:
            art = "luecke"
        elif name in SINGLE_VALUED:
            art = "einig" if _key(value) in claims else "widerspruch"
        elif name == _ANY_LEVEL or _ANY_LEVEL in claims:
            # One side would not say which level. That is not a dispute.
            art = "einig"
        else:
            art = "einig" if name in claims else "widerspruch"
        out.append(
            Abweichung(
                art=art,
                feld=name,
                regulaer=reading(claims, name),
                modell=value,
                beleg=scrub(beleg),
                grund=None,
                **common,
            )
        )

    for name, value, beleg, reason in refused:
        out.append(
            Abweichung(
                art="verworfen",
                feld=name,
                regulaer=reading(stated(name, value or ""), name),
                modell=value,
                beleg=scrub(beleg),
                grund=reason,
                **common,
            )
        )
    return out


def _key(value: str) -> str:
    return " ".join(str(value).split()).casefold()


class Lehrbuch:
    """The log itself: Postgres where there is one, a file where there is not.

    Writing never fails a request. A listing that was read is read whether or
    not the note about it could be filed, and an extraction that returned 502
    because a diagnostic table was missing would be the tail wagging the dog.
    """

    def __init__(self, path: Path, pool: Callable[[], Any | None] | None = None) -> None:
        self.path = path
        # A callable rather than the pool itself: the storage opens in the
        # application lifespan and this is built before it, so a captured pool
        # would be `None` for the whole run of a server that has a database.
        self.pool = pool or (lambda: None)

    async def record(self, entries: list[Abweichung]) -> int:
        if not entries:
            return 0
        try:
            pool = self.pool()
            if pool is not None:
                return await self._to_postgres(pool, entries)
            return self._to_file(entries)
        except Exception as exc:  # noqa: BLE001 -- see the class docstring
            logger.warning("Abweichungen konnten nicht notiert werden: %s", exc)
            return 0

    async def _to_postgres(self, pool: Any, entries: list[Abweichung]) -> int:
        async with pool.acquire() as connection:
            await connection.executemany(
                """
                insert into abweichungen
                    (art, feld, regulaer, modell, beleg, grund, text_hash,
                     quelle_url, modell_id, vorlage, gesehen_am)
                values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                on conflict (text_hash, art, feld, modell) do nothing
                """,
                [
                    (
                        entry.art, entry.feld, entry.regulaer, entry.modell,
                        entry.beleg, entry.grund, entry.text_hash,
                        entry.quelle_url, entry.modell_id, entry.vorlage,
                        entry.gesehen_am,
                    )
                    for entry in entries
                ],
            )
        return len(entries)

    def _to_file(self, entries: list[Abweichung]) -> int:
        """One JSON object per line, appended.

        Deduplicated on read rather than on write: a file is not a database,
        and an append that first has to read the whole file is a file that
        stops being appended to.
        """

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry.as_row(), ensure_ascii=False) + "\n")
        return len(entries)

    async def rows(
        self, *, art: str | None = None, feld: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """The log, newest first, wherever it is kept.

        Without an ``art`` this answers the findings and leaves the agreements
        out — they are the denominator, and ``tally`` is where they are read.
        """

        pool = self.pool()
        if pool is not None:
            return await self._from_postgres(art, feld, limit)
        rows = sorted(
            self.read_file(), key=lambda row: str(row.get("gesehen_am")), reverse=True
        )
        wanted = (art,) if art else BEFUNDE
        rows = [row for row in rows if row.get("art") in wanted]
        if feld:
            rows = [row for row in rows if row.get("feld") == feld]
        return rows[:limit]

    async def tally(self) -> dict[str, dict[str, int]]:
        """How many of each kind, per field. The statistics, including „einig".

        Two numbers make every other one readable: how often the model agreed,
        and how often it was refused. Without them „six gaps" is a count with
        no denominator, and „the gate refused four" is a rate with no base.
        """

        pool = self.pool()
        if pool is not None:
            async with pool.acquire() as connection:
                found = await connection.fetch(
                    "select art, feld, count(*) as anzahl from abweichungen "
                    "group by art, feld"
                )
            rows = [dict(row) for row in found]
        else:
            counted: dict[tuple[str, str], int] = {}
            for row in self.read_file():
                key = (str(row.get("art")), str(row.get("feld")))
                counted[key] = counted.get(key, 0) + 1
            rows = [
                {"art": art, "feld": feld, "anzahl": anzahl}
                for (art, feld), anzahl in counted.items()
            ]

        out: dict[str, dict[str, int]] = {}
        for row in rows:
            out.setdefault(str(row["art"]), {})[str(row["feld"])] = int(row["anzahl"])
        return out

    async def _from_postgres(
        self, art: str | None, feld: str | None, limit: int
    ) -> list[dict[str, Any]]:
        pool = self.pool()
        conditions, values = [], []
        if art:
            values.append(art)
            conditions.append(f"art = ${len(values)}")
        else:
            values.append(list(BEFUNDE))
            conditions.append(f"art = any(${len(values)})")
        if feld:
            values.append(feld)
            conditions.append(f"feld = ${len(values)}")
        where = f"where {' and '.join(conditions)}"
        values.append(limit)
        async with pool.acquire() as connection:
            found = await connection.fetch(
                f"""
                select art, feld, regulaer, modell, beleg, grund, text_hash,
                       quelle_url, modell_id, vorlage, gesehen_am
                from abweichungen {where}
                order by gesehen_am desc
                limit ${len(values)}
                """,
                *values,
            )
        return [
            {**dict(row), "gesehen_am": row["gesehen_am"].isoformat()} for row in found
        ]

    def read_file(self) -> list[dict[str, Any]]:
        """Everything the file holds, newest reading of each divergence kept.

        For evaluating the log where there is no Postgres -- which is every
        development machine and this project's own sandbox.
        """

        if not self.path.exists():
            return []
        seen: dict[tuple[str, ...], dict[str, Any]] = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            key = (
                str(row.get("text_hash")),
                str(row.get("art")),
                str(row.get("feld")),
                str(row.get("modell")),
            )
            seen[key] = row
        return list(seen.values())


__all__ = ["ARTEN", "BEFUNDE", "Abweichung", "Lehrbuch", "MAX_BELEG_CHARS", "compare", "fingerprint", "scrub"]
