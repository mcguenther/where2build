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

**No ORM.** Plain SQL over asyncpg. Three tables and a dozen statements; a
mapper would be more code than it replaces, and the statements are the
interesting part -- the optimistic-concurrency UPDATE says exactly what it
does, where a mapper would hide it behind a version column.

**Absent is a complete state.** Without ``DATABASE_URL`` no pool is opened, no
connection is attempted, the schema is not applied, and every route here
answers 503 with a German sentence. The application then is what it was before:
everything stays in the browser.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
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
from ..schemas import EinstellungenAntwort, GespeichertesGrundstueck
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


@dataclass(frozen=True)
class Share:
    """One shared plot: the token it lives under, and what it holds."""

    id: str
    dokument: dict[str, Any]
    angelegt: datetime
    laeuft_ab: datetime


@dataclass(frozen=True)
class AccountOverview:
    """Everything held about one account, for the person it is about.

    The three identifying fields are the whole of what a sign-in leaves here:
    which provider vouched, the identifier it vouched with, and the display
    name it granted. Nothing else about a person is stored anywhere in this
    application, which is what makes the account page able to say so.
    """

    issuer: str
    subject: str
    anzeigename: str | None
    angelegt: datetime
    grundstuecke: int
    groesse_bytes: int


# 16 bytes of randomness, 22 characters of URL. The token is the whole of the
# access control on a shared link, so it has to be past guessing: 2^128 is not
# something anybody walks through, and it stays short enough to paste into a
# chat.
SHARE_TOKEN_BYTES = 16

# What a shared link may carry beyond the plot itself, and which fields each
# switch governs. Everything here is *off* unless the sharer turned it on: a
# link is public, and the safe default for a public thing is the least it can
# be. What is always in it -- the outline, the official area, the Gemarkung,
# the Bodenrichtwert -- are facts about a piece of land that the registers
# publish anyway.
#
# Enforced here and not in the browser, because a promise the frontend keeps is
# one a bug in the frontend can break. The switches arrive as a request field;
# the cutting happens at the door, so the row never holds what the link must
# not show.
#
# `wege` is the one worth explaining. `routes` is keyed by destination id and
# holds the travel times, and `sharedDestinations` is what the frontend adds so
# the reader can see which destination a row is about -- somebody's work
# address, their children's school. Both belong to the same switch, and without
# it a reader could still count the destinations and read off the distances.
SHARE_OPTIONS: dict[str, tuple[str, ...]] = {
    "preis": ("askingPrice",),
    "haus": ("house", "placedBuilding", "houseTypeName", "houseTypeId", "customSize"),
    "wege": ("routes", "sharedDestinations"),
    # The trailing comma is not style. `("note")` is the string "note", and
    # iterating it yields "n", "o", "t", "e" -- so nothing named `note` is ever
    # withheld and the personal note goes out with every link. Caught by
    # running it, not by reading it.
    "notiz": ("note",),
}


def for_sharing(dokument: dict[str, Any], include: dict[str, bool] | None = None) -> dict[str, Any]:
    """The plot as it may be shared, given what the sharer switched on."""

    chosen = include or {}
    withheld = {
        field
        for option, fields in SHARE_OPTIONS.items()
        if not chosen.get(option, False)
        for field in fields
    }
    return {key: value for key, value in dokument.items() if key not in withheld}


def mib(byte_count: float) -> str:
    """A byte count as German MiB: „2,0 MiB“, with a comma for the decimal."""

    return f"{byte_count / (1024 * 1024):.1f} MiB".replace(".", ",")


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
    """The pool, the schema and the statements. One instance per process."""

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
            pool = None
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
                # A pool that was built and then failed on the schema has open
                # connections; leaving it to the garbage collector would hold
                # them until the next restart, and the next attempt would open
                # more.
                if pool is not None:
                    await pool.close()
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
        if self._pool is None:  # start() raises rather than leaving it unset
            raise UpstreamError(UNAVAILABLE)
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

    async def account_overview(self, identity: Identity) -> AccountOverview | None:
        """What is held about this account, for the person it is about.

        Every field the ``users`` row carries plus what hangs off it, so the
        account page can show the whole of it rather than a summary somebody
        has to trust. ``None`` means nothing has ever been stored under this
        sign-in, which is a real state: the row is created on first write.
        """

        pool = await self._pool_or_open()
        async with _translated(), pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                select u.id, u.issuer, u.subject, u.anzeigename, u.angelegt,
                       (select count(*) from plots p where p.user_id = u.id) as grundstuecke,
                       (select coalesce(sum(pg_column_size(p.dokument)), 0)
                          from plots p where p.user_id = u.id) as groesse_grundstuecke,
                       (select coalesce(sum(pg_column_size(s.dokument)), 0)
                          from settings s where s.user_id = u.id) as groesse_rest
                  from users u
                 where u.issuer = $1 and u.subject = $2
                """,
                identity.issuer,
                identity.subject,
            )
            if row is None:
                return None
            return AccountOverview(
                issuer=row["issuer"],
                subject=row["subject"],
                anzeigename=row["anzeigename"],
                angelegt=row["angelegt"],
                grundstuecke=row["grundstuecke"],
                groesse_bytes=int(row["groesse_grundstuecke"]) + int(row["groesse_rest"]),
            )

    async def delete_account(self, identity: Identity) -> bool:
        """Erase the account and everything under it. Says whether there was one.

        One statement: ``plots`` and ``settings`` both reference ``users`` with
        ``on delete cascade``, so the row going means the rest goes with it in
        the same transaction. There is nothing left to keep -- the display name
        is the only personal datum here, and it lives in exactly this row.

        Idempotent, like ``delete_plot``: gone is the outcome, not a
        precondition. The boolean is for the caller's wording, not for a
        status code.
        """

        pool = await self._pool_or_open()
        async with _translated(), pool.acquire() as connection:
            gone = await connection.execute(
                "delete from users where issuer = $1 and subject = $2",
                identity.issuer,
                identity.subject,
            )
            return gone != "DELETE 0"

    # -- shares ------------------------------------------------------------

    async def create_share(
        self, identity: Identity, dokument: dict[str, Any], include: dict[str, bool] | None = None
    ) -> Share:
        """Freeze a plot under a fresh token.

        The note is cut here and not in the browser. "Without the note" is a
        promise made to whoever shares, and a promise the frontend keeps is one
        a bug in the frontend can break; cut on the way in, the row simply
        never holds it, and no later reader has to remember to leave it out.
        """

        self._check_size(dokument)
        token = secrets.token_urlsafe(SHARE_TOKEN_BYTES)
        pool = await self._pool_or_open()
        async with _translated(), pool.acquire() as connection:
            account = await self._account_id(connection, identity, create=True)
            await self._check_share_count(connection, account)
            row = await connection.fetchrow(
                """
                insert into freigaben (id, user_id, dokument, laeuft_ab)
                values ($1, $2, $3, now() + ($4 || ' days')::interval)
                returning id, dokument, angelegt, laeuft_ab
                """,
                token,
                account,
                # No json.dumps here: the pool's jsonb codec encodes, and
                # doing it twice stores a JSON *string* that reads back as one.
                for_sharing(dokument, include),
                str(self.settings.share_days),
            )
            return _share(row)

    async def share(self, token: str) -> Share | None:
        """One share by its token, for anybody at all.

        No identity: the token *is* the access. An expired one answers as
        missing rather than as gone, because the two are the same to the reader
        and the second would say that something was once there.
        """

        pool = await self._pool_or_open()
        async with _translated(), pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                select id, dokument, angelegt, laeuft_ab from freigaben
                 where id = $1 and laeuft_ab > now()
                """,
                token,
            )
            return _share(row) if row is not None else None

    async def shares(self, identity: Identity) -> list[Share]:
        """This account's own shares, newest first. Expired ones stay out."""

        pool = await self._pool_or_open()
        async with _translated(), pool.acquire() as connection:
            account = await self._account_id(connection, identity, create=False)
            if account is None:
                return []
            rows = await connection.fetch(
                """
                select id, dokument, angelegt, laeuft_ab from freigaben
                 where user_id = $1 and laeuft_ab > now()
                 order by angelegt desc
                """,
                account,
            )
            return [_share(row) for row in rows]

    async def delete_share(self, identity: Identity, token: str) -> None:
        """Withdraw a link. Idempotent, and scoped to the account that made it."""

        pool = await self._pool_or_open()
        async with _translated(), pool.acquire() as connection:
            account = await self._account_id(connection, identity, create=False)
            if account is None:
                return
            await connection.execute(
                "delete from freigaben where user_id = $1 and id = $2", account, token
            )

    async def sweep_shares(self) -> int:
        """Drop what is past its end. Says how many, for the job's own report."""

        pool = await self._pool_or_open()
        async with _translated(), pool.acquire() as connection:
            gone = await connection.execute("delete from freigaben where laeuft_ab <= now()")
            return int(gone.rsplit(" ", 1)[-1])

    async def _check_share_count(self, connection: asyncpg.Connection, account: int) -> None:
        """A ceiling per account, like the one on plots and for the same reason.

        Serialised the same way too: `_account_id(create=True)` took a row lock
        on `users` before this runs, so two shares for one account queue there
        and the second counts what the first stored. See the note on
        `_check_count`.
        """

        held = await connection.fetchval(
            "select count(*) from freigaben where user_id = $1 and laeuft_ab > now()",
            account,
        )
        limit = self.settings.max_shares_per_account
        if held >= limit:
            raise ConflictError(
                f"Mehr als {limit} offene Freigaben gehen nicht. "
                "Bitte einen nicht mehr gebrauchten Link zurückziehen."
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

        # In this order: "this server has no storage" is the more fundamental
        # answer than "your document is too big for it".
        self.require_configured()
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

        # In this order: "this server has no storage" is the more fundamental
        # answer than "your document is too big for it".
        self.require_configured()
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
        raise PayloadTooLargeError(
            f"Dieser Eintrag ist mit {mib(size)} zu groß; gespeichert werden "
            f"höchstens {mib(self.settings.max_document_bytes)} je Eintrag."
        )

    async def _check_count(self, connection: asyncpg.Connection, account: int) -> None:
        """The per-account ceiling, checked before a row is added.

        Not racy, and not by luck: `_account_id(create=True)` runs first in the
        same transaction, and its upsert takes a row lock on `users` that is
        incompatible with itself. Two writes for one account therefore queue at
        that statement, and the second counts what the first really stored.
        Measured: a second upsert on a held row waits (and hits `lock_timeout`),
        while two plain inserts into `plots` do not wait on each other at all,
        because the foreign key only takes `for key share`, which is compatible
        with itself.

        So the guard hangs on that upsert staying a write. Turning it into
        "select, and insert if missing" would be the obvious tidy-up once the
        row usually exists, and it would quietly make this ceiling a
        suggestion. `test_der_upsert_auf_das_konto_serialisiert` holds the
        line.
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


def _share(row: asyncpg.Record) -> Share:
    return Share(
        id=row["id"],
        dokument=row["dokument"],
        angelegt=row["angelegt"],
        laeuft_ab=row["laeuft_ab"],
    )


def _plot_conflict(
    plot_id: str, current: StoredPlot | None, *, expected: datetime | None
) -> VersionConflictError:
    """The 409, worded for the case that actually happened."""

    # Serialised through the same model the GET answers with, so `aktuell` is
    # spelled exactly like the entry it stands for -- down to the trailing Z on
    # the moment, which a client is entitled to compare as a string.
    aktuell = (
        GespeichertesGrundstueck(
            id=current.id, geaendert_am=current.geaendert_am, dokument=current.dokument
        ).model_dump(mode="json")
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
        EinstellungenAntwort(
            dokument=current.dokument, geaendert_am=current.geaendert_am
        ).model_dump(mode="json")
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
