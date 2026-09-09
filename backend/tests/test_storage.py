"""/api/plots and /api/settings -- the account's copy of the document.

Two halves, and the split is deliberate.

The first half needs no database at all: a deployment without ``DATABASE_URL``
is a complete deployment, and a request without a session is refused before
anything is looked up. Those tests run everywhere, like the rest of the suite.

The second half needs a real Postgres, because what is being tested is SQL --
an ``ON CONFLICT DO NOTHING``, an ``UPDATE ... WHERE geaendert_am = $4`` and a
foreign key. A stub for those would test the stub. They skip themselves unless
``TEST_DATABASE_URL`` names a database to throw away, the same way the image
tests skip without Tesseract::

    TEST_DATABASE_URL=postgresql://where2build@127.0.0.1:5433/where2build \\
        backend/.venv/bin/python -m pytest backend/tests/test_storage.py -q

Everything in that database is dropped between tests, so do not point it at
anything you want to keep.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app import session
from app.deps import reset_services, storage_service
from app.services.oidc import Identity
from app.main import app as fastapi_app

from .conftest import OIDC_ISSUER

SESSION_COOKIE = "w2b_sitzung"
SESSION_SECRET = "sitzungsschluessel-fuer-den-test"

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

needs_database = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Kein TEST_DATABASE_URL gesetzt: ohne Postgres kann nur der Fall ohne Speicher geprüft werden.",
)

# A plot as the frontend writes it: the backend never looks inside, so the
# shape here only has to be a plausible one, not a valid one.
PLOT = {
    "id": "plot-x7k2a9f",
    "name": "Wiesenstraße, Großbothen",
    "gemarkung": "Großbothen",
    "flaeche_amtlich_m2": 502,
    "ring": [[12.7, 51.2], [12.7, 51.3], [12.8, 51.3], [12.7, 51.2]],
    "routes": {},
}

REST = {
    "version": 2,
    "houseTypes": [{"id": "ht-1", "name": "ELK All in One 159", "builtArea": 96.88}],
    "destinations": [{"id": "dest-1", "name": "Arbeit", "address": "Leipzig, Markt"}],
    "selection": [],
}


def _cookie(subject: str, name: str | None = "Erika Musterfrau") -> str:
    """A session cookie for a made-up person, signed the way /callback signs one."""

    return session.sign(
        {"iss": OIDC_ISSUER, "sub": subject, "name": name}, SESSION_SECRET, ttl_s=3600
    )


def _sign_in(client: TestClient, subject: str, name: str | None = "Erika Musterfrau") -> None:
    client.cookies.set(SESSION_COOKIE, _cookie(subject, name))


def _run(coroutine) -> Any:
    """One statement against the test database, outside the app entirely.

    Its own connection and its own event loop: this is the outside view, used
    to check what the API actually left behind rather than what it said it did.
    """

    async def go() -> Any:
        connection = await asyncpg.connect(TEST_DATABASE_URL)
        try:
            return await coroutine(connection)
        finally:
            await connection.close()

    return asyncio.run(go())


@pytest.fixture
def database(oidc, monkeypatch: pytest.MonkeyPatch):
    """A deployment with server storage, on an empty database.

    The tables are dropped rather than emptied, so every test also exercises
    the schema being applied at start-up.
    """

    _run(lambda connection: connection.execute("drop table if exists plots, settings, users"))
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    reset_services()
    yield


@pytest.fixture
def account(database):
    """A signed-in browser against that deployment.

    Entered as a context manager on purpose: that is what runs the lifespan,
    which is where the pool is opened and the schema applied, and it keeps
    every request of one test on one event loop -- an asyncpg pool belongs to
    the loop that made it.
    """

    with TestClient(fastapi_app) as client:
        _sign_in(client, "8f1c-4711")
        yield client


# --------------------------------------------------------------------------
# Without a database, and without a session
# --------------------------------------------------------------------------


def test_without_storage_every_route_says_so_in_german(oidc, client: TestClient):
    """No DATABASE_URL is a working deployment, and the answer says which one."""

    _sign_in(client, "8f1c-4711")

    for method, path in (
        ("GET", "/api/plots"),
        ("PUT", "/api/plots/plot-1"),
        ("DELETE", "/api/plots/plot-1"),
        ("GET", "/api/settings"),
        ("PUT", "/api/settings"),
    ):
        answer = client.request(method, path, json={"dokument": {}, "geaendert_am": None})
        assert answer.status_code == 503, path
        detail = answer.json()["detail"]
        assert "DATABASE_URL" in detail
        assert "Browser" in detail


def test_without_a_sign_in_every_route_answers_401(client: TestClient):
    for method, path in (
        ("GET", "/api/plots"),
        ("PUT", "/api/plots/plot-1"),
        ("DELETE", "/api/plots/plot-1"),
        ("GET", "/api/settings"),
        ("PUT", "/api/settings"),
    ):
        answer = client.request(method, path, json={"dokument": {}, "geaendert_am": None})
        assert answer.status_code == 401, path
        assert "Anmeldung" in answer.json()["detail"]


def test_a_forged_cookie_is_not_a_sign_in(oidc, client: TestClient):
    client.cookies.set(SESSION_COOKIE, session.sign({"iss": OIDC_ISSUER, "sub": "fremd"}, "anderer-schluessel", ttl_s=3600))

    assert client.get("/api/plots").status_code == 401


def test_a_database_that_does_not_answer_is_not_a_deployment_without_one(
    oidc, monkeypatch: pytest.MonkeyPatch
):
    """502, not 503, and not a stack trace.

    The frontend reads 503 as "this deployment keeps everything in the
    browser" and quietly stays local. An outage must not look like that, or a
    day of work goes unsaved without anybody being told.
    """

    monkeypatch.setenv("DATABASE_URL", "postgresql://niemand@127.0.0.1:1/gibtesnicht")
    reset_services()

    with TestClient(fastapi_app) as client:
        _sign_in(client, "8f1c-4711")

        answer = client.get("/api/plots")

    assert answer.status_code == 502
    assert "nicht geantwortet" in answer.json()["detail"]


def test_health_says_the_storage_is_not_set_up(client: TestClient):
    dienste = {entry["name"]: entry for entry in client.get("/api/health").json()["dienste"]}

    assert dienste["speicher"]["konfiguriert"] is False
    assert dienste["speicher"]["endpunkt"] is None
    assert "DATABASE_URL" in dienste["speicher"]["hinweis"]


def test_health_names_the_limits_and_hides_the_password(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    monkeypatch.setenv("DATABASE_URL", "postgresql://konto:streng-geheim@db.example.org:5432/w2b")
    reset_services()

    dienste = {entry["name"]: entry for entry in client.get("/api/health").json()["dienste"]}
    speicher = dienste["speicher"]

    assert speicher["konfiguriert"] is True
    # The health answer is public; a DSN is not.
    assert "streng-geheim" not in speicher["endpunkt"]
    assert speicher["endpunkt"] == "postgresql://konto@db.example.org:5432/w2b"
    assert "200 Grundstücke" in speicher["hinweis"]
    assert "2,0 MiB" in speicher["hinweis"]


# --------------------------------------------------------------------------
# With a database
# --------------------------------------------------------------------------


@needs_database
def test_the_schema_is_applied_at_start(account: TestClient):
    """The lifespan ran CREATE TABLE IF NOT EXISTS on a database with nothing in it."""

    tables = _run(
        lambda connection: connection.fetch(
            "select tablename from pg_tables where schemaname = 'public'"
        )
    )
    assert {row["tablename"] for row in tables} >= {"users", "plots", "settings"}

    indexes = _run(
        lambda connection: connection.fetch(
            "select indexname from pg_indexes where tablename = 'plots'"
        )
    )
    assert "plots_user_geaendert_idx" in {row["indexname"] for row in indexes}


@needs_database
def test_an_empty_account_is_empty_and_leaves_no_row(account: TestClient):
    """Signing in and looking around must not create an account."""

    assert account.get("/api/plots").json() == {"eintraege": []}
    assert account.get("/api/settings").json() == {"dokument": {}, "geaendert_am": None}

    users = _run(lambda connection: connection.fetchval("select count(*) from users"))
    assert users == 0


@needs_database
def test_a_plot_is_stored_and_read_back_verbatim(account: TestClient):
    written = account.put("/api/plots/plot-x7k2a9f", json={"dokument": PLOT, "geaendert_am": None})

    assert written.status_code == 200
    assert written.json()["id"] == "plot-x7k2a9f"
    stand = written.json()["geaendert_am"]
    assert stand

    read = account.get("/api/plots")
    assert read.json() == {
        "eintraege": [{"id": "plot-x7k2a9f", "geaendert_am": stand, "dokument": PLOT}]
    }
    # Umlauts, nesting and numbers survive the trip through jsonb unchanged.
    assert read.json()["eintraege"][0]["dokument"]["name"] == "Wiesenstraße, Großbothen"

    # And the account was created on the way, with the name from the cookie.
    row = _run(lambda connection: connection.fetchrow("select * from users"))
    assert row["issuer"] == OIDC_ISSUER
    assert row["subject"] == "8f1c-4711"
    assert row["anzeigename"] == "Erika Musterfrau"


@needs_database
def test_a_change_needs_the_stand_it_builds_on(account: TestClient):
    first = account.put("/api/plots/plot-1", json={"dokument": PLOT, "geaendert_am": None}).json()

    changed = {**PLOT, "name": "Anderer Name"}
    second = account.put(
        "/api/plots/plot-1", json={"dokument": changed, "geaendert_am": first["geaendert_am"]}
    )

    assert second.status_code == 200
    assert second.json()["geaendert_am"] != first["geaendert_am"]
    assert account.get("/api/plots").json()["eintraege"][0]["dokument"]["name"] == "Anderer Name"


@needs_database
def test_a_stale_stand_is_a_conflict_that_carries_what_is_stored(account: TestClient):
    """A contradiction is shown, never resolved quietly."""

    first = account.put("/api/plots/plot-1", json={"dokument": PLOT, "geaendert_am": None}).json()
    account.put(
        "/api/plots/plot-1",
        json={"dokument": {**PLOT, "name": "Vom anderen Gerät"}, "geaendert_am": first["geaendert_am"]},
    )

    late = account.put(
        "/api/plots/plot-1",
        json={"dokument": {**PLOT, "name": "Von hier"}, "geaendert_am": first["geaendert_am"]},
    )

    assert late.status_code == 409
    body = late.json()
    assert "geändert" in body["detail"]
    assert body["aktuell"]["id"] == "plot-1"
    assert body["aktuell"]["dokument"]["name"] == "Vom anderen Gerät"
    assert body["aktuell"]["geaendert_am"]
    # Nothing was overwritten.
    stored = account.get("/api/plots").json()["eintraege"][0]
    assert stored["dokument"]["name"] == "Vom anderen Gerät"
    assert stored["geaendert_am"] == body["aktuell"]["geaendert_am"]
    # And the stand it carries is the one to write against next: whoever the
    # user decides for, the answer they were shown is enough to act on.
    resolved = account.put(
        "/api/plots/plot-1",
        json={"dokument": {**PLOT, "name": "Von hier"}, "geaendert_am": body["aktuell"]["geaendert_am"]},
    )
    assert resolved.status_code == 200


@needs_database
def test_creating_something_that_is_already_there_is_a_conflict(account: TestClient):
    """`null` means "new". It must never turn into an overwrite."""

    account.put("/api/plots/plot-1", json={"dokument": PLOT, "geaendert_am": None})

    again = account.put(
        "/api/plots/plot-1", json={"dokument": {**PLOT, "name": "Zweiter"}, "geaendert_am": None}
    )

    assert again.status_code == 409
    assert again.json()["aktuell"]["dokument"]["name"] == PLOT["name"]


@needs_database
def test_a_plot_deleted_elsewhere_is_a_conflict_with_nothing_to_show(account: TestClient):
    first = account.put("/api/plots/plot-1", json={"dokument": PLOT, "geaendert_am": None}).json()
    account.delete("/api/plots/plot-1")

    late = account.put(
        "/api/plots/plot-1", json={"dokument": PLOT, "geaendert_am": first["geaendert_am"]}
    )

    assert late.status_code == 409
    # Null is the truthful answer here, and the sentence says what happened
    # rather than leaving the interface to guess from an empty object.
    assert late.json()["aktuell"] is None
    assert "gelöscht" in late.json()["detail"]


@needs_database
def test_deleting_is_idempotent(account: TestClient):
    account.put("/api/plots/plot-1", json={"dokument": PLOT, "geaendert_am": None})

    assert account.delete("/api/plots/plot-1").status_code == 204
    assert account.delete("/api/plots/plot-1").status_code == 204
    assert account.delete("/api/plots/gab-es-nie").status_code == 204
    assert account.get("/api/plots").json() == {"eintraege": []}


@needs_database
def test_the_list_is_newest_first(account: TestClient):
    for number in ("1", "2", "3"):
        account.put(f"/api/plots/plot-{number}", json={"dokument": PLOT, "geaendert_am": None})
    # Touch the oldest one again; it belongs at the front afterwards.
    stand = account.get("/api/plots").json()["eintraege"][-1]["geaendert_am"]
    account.put("/api/plots/plot-1", json={"dokument": PLOT, "geaendert_am": stand})

    ids = [entry["id"] for entry in account.get("/api/plots").json()["eintraege"]]

    assert ids == ["plot-1", "plot-3", "plot-2"]


@needs_database
def test_one_account_sees_nothing_of_another(account: TestClient):
    account.put("/api/plots/plot-1", json={"dokument": PLOT, "geaendert_am": None})
    account.put("/api/settings", json={"dokument": REST, "geaendert_am": None})

    _sign_in(account, "andere-person", name="Max Mustermann")

    assert account.get("/api/plots").json() == {"eintraege": []}
    assert account.get("/api/settings").json() == {"dokument": {}, "geaendert_am": None}
    # The same id in the other account is a different plot, and writing it
    # neither collides with nor changes the first one.
    written = account.put(
        "/api/plots/plot-1", json={"dokument": {**PLOT, "name": "Meins"}, "geaendert_am": None}
    )
    assert written.status_code == 200
    assert account.get("/api/plots").json()["eintraege"][0]["dokument"]["name"] == "Meins"
    # Deleting it must not reach into the first account either.
    account.delete("/api/plots/plot-1")

    _sign_in(account, "8f1c-4711")
    eintraege = account.get("/api/plots").json()["eintraege"]
    assert [entry["dokument"]["name"] for entry in eintraege] == [PLOT["name"]]
    assert account.get("/api/settings").json()["dokument"] == REST


@needs_database
def test_settings_are_one_row_with_the_same_conflict_rule(account: TestClient):
    empty = account.get("/api/settings").json()
    assert empty == {"dokument": {}, "geaendert_am": None}

    first = account.put("/api/settings", json={"dokument": REST, "geaendert_am": None})
    assert first.status_code == 200
    stand = first.json()["geaendert_am"]

    read = account.get("/api/settings").json()
    assert read == {"dokument": REST, "geaendert_am": stand}

    changed = {**REST, "selection": ["plot-1"]}
    second = account.put("/api/settings", json={"dokument": changed, "geaendert_am": stand})
    assert second.status_code == 200

    late = account.put("/api/settings", json={"dokument": REST, "geaendert_am": stand})
    assert late.status_code == 409
    assert late.json()["aktuell"]["dokument"] == changed
    # Same shape as GET /api/settings, so the interface reads it the same way.
    assert set(late.json()["aktuell"]) == {"dokument", "geaendert_am"}

    # And there is exactly one row, however often it is written.
    assert _run(lambda connection: connection.fetchval("select count(*) from settings")) == 1


@needs_database
def test_a_second_creation_of_the_settings_row_is_a_conflict(account: TestClient):
    account.put("/api/settings", json={"dokument": REST, "geaendert_am": None})

    again = account.put("/api/settings", json={"dokument": {"version": 2}, "geaendert_am": None})

    assert again.status_code == 409
    assert again.json()["aktuell"]["dokument"] == REST


@needs_database
def test_the_plot_ceiling_is_a_409_that_names_the_limit(
    monkeypatch: pytest.MonkeyPatch, database
):
    """Three instead of two hundred: what is tested is the ceiling, not the number.

    The shipped default is asserted through /api/health, where it is a
    sentence, rather than by writing two hundred rows.
    """

    monkeypatch.setenv("STORAGE_MAX_PLOTS_PER_ACCOUNT", "3")
    reset_services()

    with TestClient(fastapi_app) as client:
        _sign_in(client, "8f1c-4711")
        for number in range(3):
            assert (
                client.put(
                    f"/api/plots/plot-{number}", json={"dokument": PLOT, "geaendert_am": None}
                ).status_code
                == 200
            )

        refused = client.put("/api/plots/plot-4", json={"dokument": PLOT, "geaendert_am": None})

        assert refused.status_code == 409
        assert "3" in refused.json()["detail"]
        assert "löschen" in refused.json()["detail"]
        # A plot that is already there can still be changed; only growing stops.
        stand = client.get("/api/plots").json()["eintraege"][0]["geaendert_am"]
        assert (
            client.put(
                "/api/plots/plot-2", json={"dokument": PLOT, "geaendert_am": stand}
            ).status_code
            == 200
        )
        assert len(client.get("/api/plots").json()["eintraege"]) == 3


@needs_database
def test_a_document_over_the_size_limit_is_a_413(account: TestClient):
    """Against the shipped 2 MiB, not against a lowered one."""

    too_large = {**PLOT, "notiz": "ü" * 1_200_000}

    answer = account.put("/api/plots/plot-1", json={"dokument": too_large, "geaendert_am": None})

    assert answer.status_code == 413
    assert "2,0 MiB" in answer.json()["detail"]
    assert account.get("/api/plots").json() == {"eintraege": []}


@needs_database
def test_the_size_limit_is_configurable(monkeypatch: pytest.MonkeyPatch, database):
    monkeypatch.setenv("STORAGE_MAX_DOCUMENT_BYTES", str(4 * 1024))
    reset_services()

    with TestClient(fastapi_app) as client:
        _sign_in(client, "8f1c-4711")

        answer = client.put(
            "/api/plots/plot-1",
            json={"dokument": {**PLOT, "notiz": "x" * 5000}, "geaendert_am": None},
        )

        assert answer.status_code == 413
        assert client.put(
            "/api/plots/plot-1", json={"dokument": PLOT, "geaendert_am": None}
        ).status_code == 200


@needs_database
def test_a_dokument_that_is_not_an_object_is_refused(account: TestClient):
    for value in ([], "text", 5, None):
        answer = account.put("/api/plots/plot-1", json={"dokument": value, "geaendert_am": None})
        assert answer.status_code == 422, value


@needs_database
def test_nothing_stored_for_an_account_may_be_cached(account: TestClient):
    """Every answer here is one person's."""

    assert account.get("/api/plots").headers["cache-control"] == "no-store"
    assert account.get("/api/settings").headers["cache-control"] == "no-store"
    written = account.put("/api/plots/plot-1", json={"dokument": PLOT, "geaendert_am": None})
    assert written.headers["cache-control"] == "no-store"


@needs_database
def test_deleting_an_account_takes_its_rows_with_it(account: TestClient):
    """The foreign keys cascade, which is what makes deleting an account one statement."""

    account.put("/api/plots/plot-1", json={"dokument": PLOT, "geaendert_am": None})
    account.put("/api/settings", json={"dokument": REST, "geaendert_am": None})

    _run(lambda connection: connection.execute("delete from users"))

    assert _run(lambda connection: connection.fetchval("select count(*) from plots")) == 0
    assert _run(lambda connection: connection.fetchval("select count(*) from settings")) == 0


@needs_database
def test_der_upsert_auf_das_konto_serialisiert(database):
    """Two writes for one account queue at the account row, and that is what
    keeps the plot ceiling from being a suggestion.

    Measured on the two statements themselves, because the service cannot show
    it: both of its calls take the same pooled connection and would queue up
    even if nothing locked anything. The second upsert on a held row runs into
    `lock_timeout`; two inserts into `plots` next to each other do not, since a
    foreign key only takes `for key share` and that is compatible with itself.

    The test exists for the day somebody turns the upsert into "select, and
    insert if missing" because the row usually exists by then.
    """

    upsert = """
        insert into users (issuer, subject, anzeigename) values ($1, $2, $3)
        on conflict (issuer, subject) do update
            set anzeigename = coalesce(excluded.anzeigename, users.anzeigename)
        returning id
    """
    key = (OIDC_ISSUER, "serialisiert", "Erika Musterfrau")

    async def scenario() -> tuple[bool, bool]:
        first = await asyncpg.connect(TEST_DATABASE_URL)
        second = await asyncpg.connect(TEST_DATABASE_URL)
        try:
            await first.execute(
                (Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text(encoding="utf-8")
            )
            account = await first.fetchval(upsert, *key)

            held = first.transaction()
            await held.start()
            await first.fetchval(upsert, *key)

            waited = second.transaction()
            await waited.start()
            await second.execute("set local lock_timeout = '400ms'")
            account_blocked = False
            try:
                await second.fetchval(upsert, *key)
            except asyncpg.LockNotAvailableError:
                account_blocked = True
            await waited.rollback()
            await held.rollback()

            # And the counter-check: the plots themselves do not serialise.
            held = first.transaction()
            await held.start()
            await first.execute(
                "insert into plots (id, user_id, dokument, geaendert_am) values ('eins', $1, '{}', now())",
                account,
            )
            waited = second.transaction()
            await waited.start()
            await second.execute("set local lock_timeout = '400ms'")
            plots_blocked = False
            try:
                await second.execute(
                    "insert into plots (id, user_id, dokument, geaendert_am) values ('zwei', $1, '{}', now())",
                    account,
                )
            except asyncpg.LockNotAvailableError:
                plots_blocked = True
            await waited.rollback()
            await held.rollback()
            return account_blocked, plots_blocked
        finally:
            await first.close()
            await second.close()

    account_blocked, plots_blocked = asyncio.run(scenario())
    assert account_blocked is True
    assert plots_blocked is False
