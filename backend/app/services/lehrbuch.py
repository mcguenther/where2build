"""Where the deterministic readers and a model disagree, written down.

A model in this project is a *teacher* whose answer is never trusted and always
checked. That makes it something better than a fallback: every place it reads
something the patterns in `search.indicia` did not, and every place the two
disagree, is a sentence somebody could write a pattern against — and the Beleg
gate has already proved that sentence stands verbatim in the page. So the
disagreement is not noise to be smoothed over. It is the corpus.

Three kinds, and each says something different:

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
ARTEN = ("luecke", "widerspruch", "verworfen")

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

    An agreement produces nothing. That is the point: a log that also holds the
    cases where the pipeline was already right is a log nobody reads.
    """

    known: dict[str, set[str]] = {}
    for name, value in deterministic:
        if value:
            known.setdefault(name, set()).add(_key(value))

    out: list[Abweichung] = []
    common = dict(
        text_hash=text_hash, quelle_url=quelle_url, modell_id=modell_id, vorlage=vorlage
    )

    for name, value, beleg in accepted:
        if not value:
            continue
        seen = known.get(name)
        if seen and _key(value) in seen:
            continue  # both readers agree; nothing to learn
        out.append(
            Abweichung(
                art="widerspruch" if seen else "luecke",
                feld=name,
                regulaer=", ".join(sorted(seen)) if seen else None,
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
                regulaer=", ".join(sorted(known.get(name, ()))) or None,
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
        """The log, newest first, wherever it is kept."""

        pool = self.pool()
        if pool is not None:
            return await self._from_postgres(art, feld, limit)
        rows = sorted(
            self.read_file(), key=lambda row: str(row.get("gesehen_am")), reverse=True
        )
        if art:
            rows = [row for row in rows if row.get("art") == art]
        if feld:
            rows = [row for row in rows if row.get("feld") == feld]
        return rows[:limit]

    async def _from_postgres(
        self, art: str | None, feld: str | None, limit: int
    ) -> list[dict[str, Any]]:
        pool = self.pool()
        conditions, values = [], []
        for column, value in (("art", art), ("feld", feld)):
            if value:
                values.append(value)
                conditions.append(f"{column} = ${len(values)}")
        where = f"where {' and '.join(conditions)}" if conditions else ""
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


__all__ = ["ARTEN", "Abweichung", "Lehrbuch", "MAX_BELEG_CHARS", "compare", "fingerprint", "scrub"]
