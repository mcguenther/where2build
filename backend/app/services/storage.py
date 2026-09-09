"""The account's copy of the document, in Postgres.

The backend owns no geometry and, until now, no database. This is the one
exception the plan makes (``docs/entscheidungen/startseite-und-konten.md`` § 4)
and it is deliberately the smallest one that works: a place to put the
frontend's document for whoever is signed in, so it is there on the next
machine.

Three decisions shape everything below.

**The document is stored, not read.** What arrives is the document
``lib/store.js`` produces, and it goes into ``jsonb`` byte for byte. The
backend checks that it is an object and that it is not absurdly large, and
nothing else. Its schema, its ``version`` field and its migration live in the
frontend, which is the only place that has ever needed to understand them; a
second reader here would be a second thing to keep in step, and two places that
know one schema drift apart. That is also why the limits below are about size
and count rather than about shape.

**No ORM.** Plain SQL over asyncpg. There are three tables and eight
statements; a mapper would be more code than it replaces, and the statements
are the interesting part -- the optimistic-concurrency UPDATE says exactly what
it does.

**Absent is a complete state.** Without ``DATABASE_URL`` no pool is opened, no
connection is attempted, the schema is not applied, and every route here
answers 503 with a German sentence. The application then is what it was before:
everything stays in the browser.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator

import asyncpg

from ..errors import (
    NotConfiguredError,
    PayloadTooLargeError,
    ConflictError,
    UpstreamError,
    VersionConflictError,
)
from ..settings import StorageSettings
from .oidc import Identity

logger = logging.getLogger(__name__)

# Applied on every start with CREATE TABLE IF NOT EXISTS; see the file itself
# for why that is enough today and what has to replace it before the first
# change to a column.
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"

NOT_CONFIGURED = (
    "Auf diesem Server ist kein Speicher für Konten eingerichtet. Die Grundstücke "
    "bleiben in diesem Browser; zum Einrichten wird DATABASE_URL auf eine "
    "Postgres-Datenbank gesetzt."
)

# Postgres is an upstream service like any other here, so an outage answers 502
# and not 503: 503 is the frontend's signal for "this deployment has no server
# storage", under which it quietly stays local. A database that is down must
# not look like a deployment that never had one.
UNAVAILABLE = (
    "Der Serverspeicher hat nicht geantwortet. Der Stand in diesem Browser ist "
    "unverändert; bitte später erneut speichern."
)


@dataclass(frozen=True)
class StoredPlot:
    """One plot as it is stored: the id it was written under, and its stand."""

    id: str
    dokument: dict[str, Any]
    geaendert_am: datetime


@dataclass(frozen=True)
class StoredDocument:
    """The settings row: everything that is not a plot."""

    dokument: dict[str, Any]
    geaendert_am: datetime


def document_size(document: dict[str, Any]) -> int:
    """How many bytes this document takes as JSON.

    The compact spelling, because that is what goes into ``jsonb`` -- Postgres
    keeps the parsed value, not the whitespace it arrived with.
    """

    return len(json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


async def _register_json(connection: asyncpg.Connection) -> None:
    """Hand ``jsonb`` over as a dict in both directions."""

    await connection.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


class Storage:
    """The pool, the schema and the eight statements. One instance per process."""

    def __init__(self, settings: StorageSettings) -> None:
        self.settings = settings
        self._pool: asyncpg.Pool | None = None
        # Two requests arriving together on a cold process would otherwise both
        # build a pool, and the second one would be dropped on the floor with
        # its connections still open.
        self._lock = asyncio.Lock()

    # -- lifecycle ---------------------------------------------------------

    @property
    def configured(self) -> bool:
        return self.settings.configured

    def require_configured(self) -> None:
        if not self.configured:
            raise NotConfiguredError(NOT_CONFIGURED)

    async def start(self) -> None:
        """Open the pool and apply the schema. Does nothing when unconfigured.

        Called from the application lifespan, and again lazily from the first
        request that needs a connection: a test client that never enters the
        lifespan context must still be able to store something, and a database
        that was down at start-up must not stay unusable until a restart.
        """

        if not self.configured or self._pool is not None:
            return
        async with self._lock:
            if self._pool is not None:
                return
            try:
                pool = await asyncpg.create_pool(
                    self.settings.database_url,
                    min_size=self.settings.pool_min_size,
                    max_size=self.settings.pool_max_size,
                    command_timeout=self.settings.timeout_s,
                    timeout=self.settings.timeout_s,
                    init=_register_json,
                )
                async with pool.acquire() as connection:
                    await connection.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
            except (asyncpg.PostgresError, OSError, TimeoutError) as exc:
                logger.warning("Server storage is not reachable: %s", exc)
                raise UpstreamError(UNAVAILABLE) from exc
            self._pool = pool

    async def close(self) -> None:
        pool, self._pool = self._pool, None
        if pool is not None:
            await pool.close()

    async def _pool_or_open(self) -> asyncpg.Pool:
        self.require_configured()
        await self.start()
        assert self._pool is not None  # start() raises rather than returning None
        return self._pool

    # -- accounts ----------------------------------------------------------

    async def _account_id(
        self, connection: asyncpg.Connection, identity: Identity, *, create: bool
    ) -> int | None:
        """The row id of this account, created on demand.

        Created here rather than at sign-in, and only for a request that stores
        something: the sign-in path stays free of the database entirely, and
        somebody who signs in, looks around and leaves does not leave an empty
        account behind. Reads and deletes therefore pass ``create=False`` and
        answer "nothing stored" from the absence of the row.

        The display name is refreshed on the way through, but never cleared: a
        provider that grants no ``profile`` scope this time must not wipe the
        name it granted last time.
        """

        if not create:
            return await connection.fetchval(
                "select id from users where issuer = $1 and subject = $2",
                identity.issuer,
                identity.subject,
            )
        return await connection.fetchval(
            """
            insert into users (issuer, subject, anzeigename)
            values ($1, $2, $3)
            on conflict (issuer, subject) do update
                set anzeigename = coalesce(excluded.anzeigename, users.anzeigename)
            returning id
            """,
            identity.issuer,
            identity.subject,
            identity.name,
        )

    # -- plots -------------------------------------------------------------

    async def plots(self, identity: Identity) -> list[StoredPlot]:
        """Every plot of this account, newest first."""

        pool = await self._pool_or_open()
        async with _translated(), pool.acquire() as connection:
            account = await self._account_id(connection, identity, create=False)
            if account is None:
                return []
            rows = await connection.fetch(
                """
                select id, dokument, geaendert_am
                from plots
                where user_id = $1
                -- The id breaks a tie so the order is total; two rows written
                -- in the same transaction share a now().
                order by geaendert_am desc, id desc
                """,
                account,
            )
        return [
            StoredPlot(id=row["id"], dokument=row["dokument"], geaendert_am=row["geaendert_am"])
            for row in rows
        ]

    async def save_plot(
        self,
        identity: Identity,
        plot_id: str,
        document: dict[str, Any],
        *,
        expected: datetime | None,
    ) -> datetime:
        """Write one plot and answer with its new stand.

        ``expected`` is the stand the sender is building on. ``None`` means
        "this is new"; anything else has to still be what is stored. Either way
        a mismatch is a 409 carrying what *is* stored, never a merge and never
        a last-write-wins.
        """

        self._check_size(document)
        pool = await self._pool_or_open()
        async with _translated(), pool.acquire() as connection, connection.transaction():
            account = await self._account_id(connection, identity, create=True)
            if expected is None:
                await self._check_count(connection, account)
                stand = await connection.fetchval(
                    """
                    insert into plots (id, user_id, dokument, geaendert_am)
                    values ($1, $2, $3, now())
                    on conflict (user_id, id) do nothing
                    returning geaendert_am
                    """,
                    plot_id,
                    account,
                    document,
                )
            else:
                stand = await connection.fetchval(
                    """
                    update plots
                    set dokument = $3, geaendert_am = now()
                    where user_id = $2 and id = $1 and geaendert_am = $4
                    returning geaendert_am
                    """,
                    plot_id,
                    account,
                    document,
                    expected,
                )
            if stand is not None:
                return stand
            current = await self._plot(connection, account, plot_id)
        raise _plot_conflict(plot_id, current, expected=expected)

    async def delete_plot(self, identity: Identity, plot_id: str) -> None:
        """Remove one plot. Idempotent: gone is the outcome, not a precondition."""

        pool = await self._pool_or_open()
        async with _translated(), pool.acquire() as connection:
            account = await self._account_id(connection, identity, create=False)
            if account is None:
                return
            await connection.execute(
                "delete from plots where user_id = $1 and id = $2", account, plot_id
            )

    async def _plot(
        self, connection: asyncpg.Connection, account: int, plot_id: str
    ) -> StoredPlot | None:
        row = await connection.fetchrow(
            "select id, dokument, geaendert_am from plots where user_id = $1 and id = $2",
            account,
            plot_id,
        )
        if row is None:
            return None
        return StoredPlot(id=row["id"], dokument=row["dokument"], geaendert_am=row["geaendert_am"])

    # -- settings ----------------------------------------------------------

    async def settings_document(self, identity: Identity) -> StoredDocument | None:
        """The rest of the document, or nothing stored yet."""

        pool = await self._pool_or_open()
        async with _translated(), pool.acquire() as connection:
            account = await self._account_id(connection, identity, create=False)
            if account is None:
                return None
            row = await connection.fetchrow(
                "select dokument, geaendert_am from settings where user_id = $1", account
            )
        if row is None:
            return None
        return StoredDocument(dokument=row["dokument"], geaendert_am=row["geaendert_am"])

    async def save_settings(
        self, identity: Identity, document: dict[str, Any], *, expected: datetime | None
    ) -> datetime:
        """Write the settings row. Same concurrency rule as a plot."""

        self._check_size(document)
        pool = await self._pool_or_open()
        async with _translated(), pool.acquire() as connection, connection.transaction():
            account = await self._account_id(connection, identity, create=True)
            if expected is None:
                stand = await connection.fetchval(
                    """
                    insert into settings (user_id, dokument, geaendert_am)
                    values ($1, $2, now())
                    on conflict (user_id) do nothing
                    returning geaendert_am
                    """,
                    account,
                    document,
                )
            else:
                stand = await connection.fetchval(
                    """
                    update settings
                    set dokument = $2, geaendert_am = now()
                    where user_id = $1 and geaendert_am = $3
                    returning geaendert_am
                    """,
                    account,
                    document,
                    expected,
                )
            if stand is not None:
                return stand
            row = await connection.fetchrow(
                "select dokument, geaendert_am from settings where user_id = $1", account
            )
        current = (
            StoredDocument(dokument=row["dokument"], geaendert_am=row["geaendert_am"])
            if row is not None
            else None
        )
        raise _settings_conflict(current, expected=expected)

    # -- limits ------------------------------------------------------------

    def _check_size(self, document: dict[str, Any]) -> None:
        size = document_size(document)
        if size <= self.settings.max_document_bytes:
            return
        limit = self.settings.max_document_bytes / (1024 * 1024)
        raise PayloadTooLargeError(
            f"Dieser Eintrag ist mit {size / (1024 * 1024):.1f} MiB zu groß; "
            f"gespeichert werden höchstens {limit:.1f} MiB je Eintrag."
        )

    async def _check_count(self, connection: asyncpg.Connection, account: int) -> None:
        """The per-account ceiling, checked before a row is added.

        Racy by construction: two inserts arriving together both see the count
        below the limit. That is accepted rather than serialised, because the
        number is a guard against one account filling the disk, not a rule
        anybody counts on to the last row.
        """

        limit = self.settings.max_plots_per_account
        count = await connection.fetchval(
            "select count(*) from plots where user_id = $1", account
        )
        if count < limit:
            return
        raise ConflictError(
            f"In diesem Konto sind bereits {count} Grundstücke gespeichert; mehr als "
            f"{limit} nimmt der Server nicht auf. Bitte zuerst eines löschen."
        )


def _plot_conflict(
    plot_id: str, current: StoredPlot | None, *, expected: datetime | None
) -> VersionConflictError:
    """The 409, worded for the case that actually happened."""

    aktuell = (
        {
            "id": current.id,
            "geaendert_am": current.geaendert_am.isoformat(),
            "dokument": current.dokument,
        }
        if current is not None
        else None
    )
    if expected is None:
        message = (
            "Dieses Grundstück ist im Konto bereits vorhanden und wurde nicht "
            "überschrieben. Bitte den gespeicherten Stand ansehen und entscheiden."
        )
    elif current is None:
        message = (
            "Dieses Grundstück wurde an anderer Stelle gelöscht und deshalb nicht "
            "gespeichert. Es lässt sich als neuer Eintrag wieder anlegen."
        )
    else:
        message = (
            "Dieses Grundstück wurde an anderer Stelle geändert; der Stand hier ist "
            "älter. Es wurde nichts überschrieben."
        )
    logger.info("Write conflict on plot %s", plot_id)
    return VersionConflictError(message, aktuell=aktuell)


def _settings_conflict(
    current: StoredDocument | None, *, expected: datetime | None
) -> VersionConflictError:
    aktuell = (
        {"dokument": current.dokument, "geaendert_am": current.geaendert_am.isoformat()}
        if current is not None
        else None
    )
    if expected is None:
        message = (
            "Für dieses Konto sind bereits Haustypen und Ziele gespeichert; sie wurden "
            "nicht überschrieben."
        )
    elif current is None:
        message = (
            "Die gespeicherten Haustypen und Ziele wurden an anderer Stelle gelöscht "
            "und deshalb nicht überschrieben."
        )
    else:
        message = (
            "Haustypen und Ziele wurden an anderer Stelle geändert; der Stand hier ist "
            "älter. Es wurde nichts überschrieben."
        )
    return VersionConflictError(message, aktuell=aktuell)


@asynccontextmanager
async def _translated() -> AsyncIterator[None]:
    """Turn a database that did not answer into the German sentence for an outage.

    Only the transport-level failures. A ``PostgresError`` raised by one of the
    statements above is a bug in this file and has no business being reported
    as "please try again later", so what is caught is named rather than
    wholesale.
    """

    try:
        yield
    except (asyncpg.PostgresConnectionError, OSError, TimeoutError) as exc:
        logger.warning("Server storage is not reachable: %s", exc)
        raise UpstreamError(UNAVAILABLE) from exc
