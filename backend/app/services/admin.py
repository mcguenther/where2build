"""The statements the administration area runs.

Apart from ``services/storage.py`` on purpose: that file holds the rules about
one person's own document, and everything here is about the deployment --
counters, blocks, failures, the audit trail and the button that empties the
lot. They share one connection pool and nothing else.

Three things are worth knowing before reading the SQL.

**The hour is UTC, the day is Saxon.** Buckets are stored as UTC hours, because
a stored bucket must not depend on anyone's time zone. A statistics page
grouped by day is read by somebody in Germany, for whom a day starts at
midnight in Berlin, so the grouping converts on the way out. Grouping by hour
does not, because an hour is an hour either way.

**A block is keyed by the account key, not by ``users.id``.** The row in
``users`` appears on first write, and an account worth blocking is exactly one
that is spending this deployment's upstream budget without necessarily having
stored anything.

**The audit trail survives the red button.** Everything else the wipe touches
is data somebody put there; the record of who wiped it is the one row that
would otherwise be erased by the act it describes.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Sequence

import asyncpg

from ..telemetry import Block, Snapshot
from .storage import Storage, _translated

logger = logging.getLogger(__name__)

# Where a day begins for whoever reads the statistics. The whole application is
# Saxony-only, so this is not a setting waiting to happen.
ZONE = "Europe/Berlin"

# What a caller may group by. Checked against this rather than passed through:
# the value ends up inside date_trunc, and date_trunc takes a field name.
GRIDS = {"stunde": "hour", "tag": "day"}

# What the red button may empty. The audit trail is deliberately not here.
SCOPES = {
    # Everything an account is: the documents, the shared links, the settings
    # and the accounts themselves.
    "konten": ("freigaben", "plots", "settings", "users"),
    # The counters and the failures -- the deployment's own record of itself.
    "statistik": ("nutzung", "nutzung_konto", "fehler"),
    # And the blocks, which are neither: lifting them all at once is its own
    # decision.
    "sperren": ("sperren",),
}


@dataclass(frozen=True)
class AccountRow:
    """One line of the account list."""

    kennung: str
    anzeigename: str | None
    angelegt: datetime | None
    ist_admin: bool
    grundstuecke: int
    freigaben: int
    bytes: int
    anfragen: int
    fehler: int
    tokens_ein: int
    tokens_aus: int
    zuletzt_aktiv: datetime | None
    gesperrt_bis: datetime | None
    gesperrt_grund: str | None
    gesperrt_automatisch: bool


class AdminStore:
    """Everything the administration area asks the database."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    @property
    def configured(self) -> bool:
        return self.storage.configured

    def require_configured(self) -> None:
        self.storage.require_configured()

    # -- the flush ---------------------------------------------------------

    async def flush(self, snapshot: Snapshot) -> None:
        """Write one round of counters, failures and blocks.

        One transaction: a flush that wrote the counters and then failed on the
        blocks would leave an account counted but not stopped, and the retry
        would count it twice.
        """

        if snapshot.empty:
            return
        pool = await self.storage.open_pool()
        async with _translated(), pool.acquire() as connection:
            async with connection.transaction():
                if snapshot.usage:
                    await connection.executemany(
                        """
                        insert into nutzung
                            (stunde, bereich, dienst, ergebnis, anzahl, dauer_ms,
                             tokens_ein, tokens_aus)
                        values ($1, $2, $3, $4, $5, $6, $7, $8)
                        on conflict (stunde, bereich, dienst, ergebnis) do update set
                            anzahl     = nutzung.anzahl     + excluded.anzahl,
                            dauer_ms   = nutzung.dauer_ms   + excluded.dauer_ms,
                            tokens_ein = nutzung.tokens_ein + excluded.tokens_ein,
                            tokens_aus = nutzung.tokens_aus + excluded.tokens_aus
                        """,
                        [
                            (
                                hour,
                                area,
                                service,
                                result,
                                counter.anzahl,
                                counter.dauer_ms,
                                counter.tokens_ein,
                                counter.tokens_aus,
                            )
                            for (hour, area, service, result), counter in snapshot.usage.items()
                        ],
                    )
                if snapshot.accounts:
                    await connection.executemany(
                        """
                        insert into nutzung_konto
                            (stunde, kennung, anzahl, fehler, tokens_ein, tokens_aus)
                        values ($1, $2, $3, $4, $5, $6)
                        on conflict (stunde, kennung) do update set
                            anzahl     = nutzung_konto.anzahl     + excluded.anzahl,
                            fehler     = nutzung_konto.fehler     + excluded.fehler,
                            tokens_ein = nutzung_konto.tokens_ein + excluded.tokens_ein,
                            tokens_aus = nutzung_konto.tokens_aus + excluded.tokens_aus
                        """,
                        [
                            (
                                hour,
                                kennung,
                                entry.anzahl,
                                entry.fehler,
                                entry.tokens_ein,
                                entry.tokens_aus,
                            )
                            for (hour, kennung), entry in snapshot.accounts.items()
                        ],
                    )
                if snapshot.errors:
                    await connection.executemany(
                        """
                        insert into fehler (zeit, bereich, dienst, status, route, kennung, meldung)
                        values ($1, $2, $3, $4, $5, $6, $7)
                        """,
                        [
                            (
                                entry.zeit,
                                entry.bereich,
                                entry.dienst,
                                entry.status,
                                entry.route,
                                entry.kennung,
                                entry.meldung,
                            )
                            for entry in snapshot.errors
                        ],
                    )
                if snapshot.blocks:
                    await connection.executemany(_BLOCK_UPSERT, [_block_row(b) for b in snapshot.blocks])

    async def blocks(self) -> list[Block]:
        """Every block that is still in force, for the whole deployment."""

        pool = await self.storage.open_pool()
        async with _translated(), pool.acquire() as connection:
            rows = await connection.fetch(
                "select kennung, bis, grund, automatisch, durch from sperren where bis > now()"
            )
        return [_block(row) for row in rows]

    async def set_block(
        self, kennung: str, *, minutes: int, grund: str, durch: str | None
    ) -> Block:
        block = Block(
            kennung=kennung,
            bis=datetime.now(timezone.utc) + timedelta(minutes=max(1, minutes)),
            grund=grund,
            automatisch=False,
            durch=durch,
        )
        pool = await self.storage.open_pool()
        async with _translated(), pool.acquire() as connection:
            await connection.execute(_BLOCK_UPSERT, *_block_row(block))
        return block

    async def clear_block(self, kennung: str) -> None:
        pool = await self.storage.open_pool()
        async with _translated(), pool.acquire() as connection:
            await connection.execute("delete from sperren where kennung = $1", kennung)

    # -- who may open the area --------------------------------------------

    async def is_admin(self, kennung: str) -> bool:
        pool = await self.storage.open_pool()
        async with _translated(), pool.acquire() as connection:
            return bool(
                await connection.fetchval(
                    "select ist_admin from users where kennung = $1", kennung
                )
            )

    async def set_admin(self, kennung: str, value: bool) -> bool:
        """Promote or demote. False when there is no such account here.

        No row means somebody who has signed in but never stored anything, and
        there is nothing to hang the flag on -- the interface says so rather
        than pretending it worked.
        """

        pool = await self.storage.open_pool()
        async with _translated(), pool.acquire() as connection:
            updated = await connection.fetchval(
                "update users set ist_admin = $2 where kennung = $1 returning id", kennung, value
            )
        return updated is not None

    async def admin_count(self) -> int:
        pool = await self.storage.open_pool()
        async with _translated(), pool.acquire() as connection:
            return int(await connection.fetchval("select count(*) from users where ist_admin") or 0)

    # -- the account list --------------------------------------------------

    async def accounts(self, start: datetime, end: datetime, *, limit: int = 500) -> list[AccountRow]:
        """Everybody this deployment knows, with what they used in the window.

        A full outer join, and that is the point: ``users`` holds whoever
        stored something, ``nutzung_konto`` whoever called something, and the
        two sets overlap without either containing the other. Somebody who has
        never saved a plot but is spending the upstream budget appears here --
        that is precisely the row an operator is looking for.
        """

        pool = await self.storage.open_pool()
        async with _translated(), pool.acquire() as connection:
            rows = await connection.fetch(
                """
                with verbrauch as (
                    select kennung,
                           sum(anzahl)     as anfragen,
                           sum(fehler)     as fehler,
                           sum(tokens_ein) as tokens_ein,
                           sum(tokens_aus) as tokens_aus,
                           max(stunde)     as zuletzt
                    from nutzung_konto
                    where stunde >= $1 and stunde < $2
                    group by kennung
                )
                select coalesce(u.kennung, v.kennung)      as kennung,
                       u.anzeigename,
                       u.angelegt,
                       coalesce(u.ist_admin, false)        as ist_admin,
                       coalesce(v.anfragen, 0)             as anfragen,
                       coalesce(v.fehler, 0)               as fehler,
                       coalesce(v.tokens_ein, 0)           as tokens_ein,
                       coalesce(v.tokens_aus, 0)           as tokens_aus,
                       v.zuletzt                           as zuletzt_aktiv,
                       coalesce((select count(*) from plots p where p.user_id = u.id), 0)
                                                           as grundstuecke,
                       coalesce((select count(*) from freigaben f
                                  where f.user_id = u.id and f.laeuft_ab > now()), 0)
                                                           as freigaben,
                       coalesce((select sum(pg_column_size(p.dokument))
                                   from plots p where p.user_id = u.id), 0)
                                                           as bytes,
                       s.bis                               as gesperrt_bis,
                       s.grund                             as gesperrt_grund,
                       coalesce(s.automatisch, false)      as gesperrt_automatisch
                from users u
                full outer join verbrauch v on v.kennung = u.kennung
                left join sperren s
                       on s.kennung = coalesce(u.kennung, v.kennung) and s.bis > now()
                order by coalesce(v.anfragen, 0) desc, u.angelegt desc nulls last
                limit $3
                """,
                start,
                end,
                limit,
            )
        return [
            AccountRow(
                kennung=row["kennung"],
                anzeigename=row["anzeigename"],
                angelegt=row["angelegt"],
                ist_admin=row["ist_admin"],
                grundstuecke=int(row["grundstuecke"]),
                freigaben=int(row["freigaben"]),
                bytes=int(row["bytes"]),
                anfragen=int(row["anfragen"]),
                fehler=int(row["fehler"]),
                tokens_ein=int(row["tokens_ein"]),
                tokens_aus=int(row["tokens_aus"]),
                zuletzt_aktiv=row["zuletzt_aktiv"],
                gesperrt_bis=row["gesperrt_bis"],
                gesperrt_grund=row["gesperrt_grund"],
                gesperrt_automatisch=row["gesperrt_automatisch"],
            )
            for row in rows
        ]

    async def delete_account(self, kennung: str) -> bool:
        """Erase one account and everything hanging off it."""

        pool = await self.storage.open_pool()
        async with _translated(), pool.acquire() as connection:
            deleted = await connection.fetchval(
                "delete from users where kennung = $1 returning id", kennung
            )
        return deleted is not None

    # -- the numbers -------------------------------------------------------

    async def series(
        self, start: datetime, end: datetime, *, grid: str = "stunde", area: str | None = None
    ) -> list[dict[str, Any]]:
        """One point per hour or per day over the window."""

        field = GRIDS.get(grid, "hour")
        pool = await self.storage.open_pool()
        async with _translated(), pool.acquire() as connection:
            rows = await connection.fetch(
                f"""
                select (date_trunc('{field}', stunde at time zone $4) at time zone $4) as zeit,
                       sum(anzahl)                                                     as anfragen,
                       sum(anzahl) filter (where ergebnis = 'fehler')                  as fehler,
                       sum(anzahl) filter (where ergebnis = 'limit')                   as limitiert,
                       sum(dauer_ms)                                                   as dauer_ms,
                       sum(tokens_ein)                                                 as tokens_ein,
                       sum(tokens_aus)                                                 as tokens_aus
                from nutzung
                where stunde >= $1 and stunde < $2
                  and ($3::text is null or bereich = $3)
                group by 1
                order by 1
                """,
                start,
                end,
                area,
                ZONE,
            )
        return [_series_point(row) for row in rows]

    async def by_service(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """Every area and service in the window, busiest first."""

        pool = await self.storage.open_pool()
        async with _translated(), pool.acquire() as connection:
            rows = await connection.fetch(
                """
                select bereich,
                       dienst,
                       sum(anzahl)                                    as anfragen,
                       sum(anzahl) filter (where ergebnis = 'fehler') as fehler,
                       sum(anzahl) filter (where ergebnis = 'limit')  as limitiert,
                       sum(dauer_ms)                                  as dauer_ms,
                       sum(tokens_ein)                                as tokens_ein,
                       sum(tokens_aus)                                as tokens_aus
                from nutzung
                where stunde >= $1 and stunde < $2
                group by bereich, dienst
                order by sum(anzahl) desc
                """,
                start,
                end,
            )
        return [
            {
                "bereich": row["bereich"],
                "dienst": row["dienst"],
                **_numbers(row),
            }
            for row in rows
        ]

    # -- the failures ------------------------------------------------------

    async def errors(
        self, start: datetime, end: datetime, *, limit: int = 200, service: str | None = None
    ) -> list[dict[str, Any]]:
        pool = await self.storage.open_pool()
        async with _translated(), pool.acquire() as connection:
            rows = await connection.fetch(
                """
                select zeit, bereich, dienst, status, route, kennung, meldung
                from fehler
                where zeit >= $1 and zeit < $2
                  and ($3::text is null or dienst = $3)
                order by zeit desc
                limit $4
                """,
                start,
                end,
                service,
                limit,
            )
        return [dict(row) for row in rows]

    # -- the audit trail ---------------------------------------------------

    async def note(
        self,
        *,
        kennung: str,
        name: str | None,
        action: str,
        target: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record what an administrator did. Never raises into the request.

        An action that happened and was not written down is bad; an action that
        was refused *because* it could not be written down would be worse --
        the red button would stop working the moment this table did.
        """

        try:
            pool = await self.storage.open_pool()
            async with _translated(), pool.acquire() as connection:
                await connection.execute(
                    """
                    insert into pruefprotokoll (kennung, name, aktion, ziel, details)
                    values ($1, $2, $3, $4, $5)
                    """,
                    kennung,
                    name,
                    action,
                    target,
                    json.dumps(details, ensure_ascii=False) if details else None,
                )
        except Exception:  # noqa: BLE001 -- see the docstring
            logger.exception("Could not write the audit entry for %s", action)

    async def audit(self, *, limit: int = 200) -> list[dict[str, Any]]:
        pool = await self.storage.open_pool()
        async with _translated(), pool.acquire() as connection:
            rows = await connection.fetch(
                """
                select zeit, kennung, name, aktion, ziel, details
                from pruefprotokoll
                order by zeit desc
                limit $1
                """,
                limit,
            )
        return [
            {
                **dict(row),
                "details": json.loads(row["details"]) if isinstance(row["details"], str) else row["details"],
            }
            for row in rows
        ]

    # -- shared links, seen by the operator --------------------------------

    async def shares(self, *, limit: int = 200) -> list[dict[str, Any]]:
        """Every link that is still open, without what is inside it.

        The token, the owner, the dates and the size -- enough to see how many
        there are and to withdraw one, and nothing about the plot. An operator
        who has to withdraw a link does not have to read it.
        """

        pool = await self.storage.open_pool()
        async with _translated(), pool.acquire() as connection:
            rows = await connection.fetch(
                """
                select f.id, f.angelegt, f.laeuft_ab, u.kennung, u.anzeigename,
                       pg_column_size(f.dokument) as bytes
                from freigaben f
                join users u on u.id = f.user_id
                where f.laeuft_ab > now()
                order by f.angelegt desc
                limit $1
                """,
                limit,
            )
        return [dict(row) for row in rows]

    async def delete_share(self, token: str) -> bool:
        pool = await self.storage.open_pool()
        async with _translated(), pool.acquire() as connection:
            deleted = await connection.fetchval(
                "delete from freigaben where id = $1 returning id", token
            )
        return deleted is not None

    # -- housekeeping ------------------------------------------------------

    async def sweep(self, retention_days: int) -> dict[str, int]:
        """Drop what is past its end: counters, failures, expired blocks.

        The audit trail keeps its own, longer life -- it is the one table whose
        point is that it is still there later -- but it is not unbounded
        either: twice the retention, so a year-old promotion is still
        answerable for and nothing grows for ever.
        """

        horizon = datetime.now(timezone.utc) - timedelta(days=retention_days)
        pool = await self.storage.open_pool()
        removed: dict[str, int] = {}
        async with _translated(), pool.acquire() as connection:
            for table, column, cutoff in (
                ("nutzung", "stunde", horizon),
                ("nutzung_konto", "stunde", horizon),
                ("fehler", "zeit", horizon),
                ("sperren", "bis", datetime.now(timezone.utc)),
                ("pruefprotokoll", "zeit", horizon - timedelta(days=retention_days)),
            ):
                status = await connection.execute(
                    f"delete from {table} where {column} < $1", cutoff
                )
                removed[table] = _affected(status)
        return removed

    async def counts(self) -> dict[str, int]:
        """How many rows each table holds, for the overview."""

        pool = await self.storage.open_pool()
        async with _translated(), pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                select (select count(*) from users)         as konten,
                       (select count(*) from plots)         as grundstuecke,
                       (select count(*) from freigaben
                         where laeuft_ab > now())           as freigaben,
                       (select count(*) from sperren
                         where bis > now())                 as sperren,
                       (select count(*) from fehler)        as fehler,
                       (select count(*) from nutzung)       as nutzung,
                       (select count(*) from pruefprotokoll) as protokoll,
                       pg_database_size(current_database()) as bytes
                """
            )
        return {key: int(value) for key, value in dict(row).items()}

    async def wipe(self, scopes: Sequence[str]) -> dict[str, int]:
        """The red button. Counts first, then empties.

        Counted before rather than after so the answer can say what was
        actually removed; ``truncate`` reports nothing of its own. ``cascade``
        because ``plots``, ``settings`` and ``freigaben`` reference ``users``,
        and restarting the identities so a fresh deployment looks fresh.
        """

        tables: list[str] = []
        for scope in scopes:
            tables.extend(SCOPES.get(scope, ()))
        if not tables:
            return {}
        pool = await self.storage.open_pool()
        removed: dict[str, int] = {}
        async with _translated(), pool.acquire() as connection:
            async with connection.transaction():
                for table in tables:
                    removed[table] = int(
                        await connection.fetchval(f"select count(*) from {table}") or 0
                    )
                await connection.execute(
                    "truncate table " + ", ".join(tables) + " restart identity cascade"
                )
        return removed


_BLOCK_UPSERT = """
    insert into sperren (kennung, bis, grund, automatisch, durch)
    values ($1, $2, $3, $4, $5)
    on conflict (kennung) do update set
        bis         = excluded.bis,
        grund       = excluded.grund,
        automatisch = excluded.automatisch,
        durch       = excluded.durch
"""


def _block_row(block: Block) -> tuple[Any, ...]:
    return (block.kennung, block.bis, block.grund, block.automatisch, block.durch)


def _block(row: asyncpg.Record) -> Block:
    return Block(
        kennung=row["kennung"],
        bis=row["bis"],
        grund=row["grund"],
        automatisch=row["automatisch"],
        durch=row["durch"],
    )


def _numbers(row: asyncpg.Record) -> dict[str, int]:
    return {
        "anfragen": int(row["anfragen"] or 0),
        "fehler": int(row["fehler"] or 0),
        "limitiert": int(row["limitiert"] or 0),
        "dauer_ms": int(row["dauer_ms"] or 0),
        "tokens_ein": int(row["tokens_ein"] or 0),
        "tokens_aus": int(row["tokens_aus"] or 0),
    }


def _series_point(row: asyncpg.Record) -> dict[str, Any]:
    return {"zeit": row["zeit"], **_numbers(row)}


def _affected(status: str) -> int:
    """The row count out of a ``DELETE n`` command tag."""

    parts = status.split()
    return int(parts[-1]) if parts and parts[-1].isdigit() else 0
