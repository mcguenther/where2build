"""/api/verwaltung/... -- the administration area.

Split the same way ``test_storage.py`` is, and for the same reason. The first
half is about who is let in and what a deployment without a database answers;
it runs everywhere. The second half is about SQL -- a full outer join, an
``on conflict`` that adds rather than replaces, a ``truncate`` -- and skips
itself unless ``TEST_DATABASE_URL`` names a database to throw away::

    TEST_DATABASE_URL=postgresql://where2build@127.0.0.1:5433/where2build \\
        backend/.venv/bin/python -m pytest backend/tests/test_admin.py -q

The burst guard is tested against the recorder directly rather than by sending
three hundred requests: what is being checked is when it fires and that the
next request is refused, and a test that spends a minute proving arithmetic is
a test nobody runs.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app import session, telemetry
from app.deps import reset_services
from app.main import app as fastapi_app
from app.services.oidc import Identity

from .conftest import OIDC_ISSUER

SESSION_COOKIE = "w2b_sitzung"
SESSION_SECRET = "sitzungsschluessel-fuer-den-test"

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

needs_database = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Kein TEST_DATABASE_URL gesetzt: ohne Postgres lässt sich nur der Fall ohne Speicher prüfen.",
)

# Two people. The keys are what the API and the configuration both speak in,
# so they are derived the same way the application derives them rather than
# written out -- a literal here would go stale the day the hash changes.
CHIEF = Identity(issuer=OIDC_ISSUER, subject="8f1c-4711", name="Erika Musterfrau")
OTHER = Identity(issuer=OIDC_ISSUER, subject="2b7d-0815", name="Jonas Beispiel")


def _cookie(identity: Identity) -> str:
    return session.sign(
        {"iss": identity.issuer, "sub": identity.subject, "name": identity.name},
        SESSION_SECRET,
        ttl_s=3600,
    )


def _sign_in(client: TestClient, identity: Identity) -> None:
    client.cookies.set(SESSION_COOKIE, _cookie(identity))


def _run(coroutine) -> Any:
    async def go() -> Any:
        connection = await asyncpg.connect(TEST_DATABASE_URL)
        try:
            return await coroutine(connection)
        finally:
            await connection.close()

    return asyncio.run(go())


@pytest.fixture
def database(oidc, monkeypatch: pytest.MonkeyPatch):
    """An empty database, and the configured administrator signed in."""

    _run(
        lambda connection: connection.execute(
            """
            do $$ declare t record; begin
              for t in select tablename from pg_tables where schemaname = 'public' loop
                execute format('drop table if exists %I cascade', t.tablename);
              end loop;
            end $$;
            """
        )
    )
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("ADMIN_ACCOUNTS", CHIEF.account_key)
    reset_services()
    yield


@pytest.fixture
def admin(database):
    with TestClient(fastapi_app) as client:
        _sign_in(client, CHIEF)
        yield client


# --------------------------------------------------------------------------
# Who is let in -- no database needed for any of this
# --------------------------------------------------------------------------


def test_without_a_sign_in_the_area_answers_401(client: TestClient):
    for path in (
        "/api/verwaltung/uebersicht",
        "/api/verwaltung/statistik",
        "/api/verwaltung/konten",
        "/api/verwaltung/protokoll",
        "/api/verwaltung/dienste",
    ):
        answer = client.get(path)
        assert answer.status_code == 401, path


def test_signed_in_is_not_administering(oidc, client: TestClient):
    """403 and a German sentence -- not 404, and not a blank page.

    Hiding the area behind a 404 would leave an administrator who lost the flag
    looking for a bug in the router.
    """

    _sign_in(client, CHIEF)

    answer = client.get("/api/verwaltung/dienste")

    assert answer.status_code == 403
    assert "nicht freigegeben" in answer.json()["detail"]


def test_the_configured_account_gets_in_without_a_database(
    oidc, client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """ADMIN_ACCOUNTS is what survives an empty table -- including after a wipe."""

    monkeypatch.setenv("ADMIN_ACCOUNTS", f"{CHIEF.account_key}, andere-kennung")
    reset_services()
    _sign_in(client, CHIEF)

    answer = client.get("/api/verwaltung/dienste")

    assert answer.status_code == 200
    body = answer.json()
    assert body["sperre_ab"] > 0
    assert body["kontingent_dienste"] > 0


def test_me_reports_the_flag_the_menu_is_drawn_from(
    oidc, client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("ADMIN_ACCOUNTS", CHIEF.account_key)
    reset_services()
    _sign_in(client, CHIEF)

    assert client.get("/api/auth/me").json()["verwalter"] is True

    _sign_in(client, OTHER)
    assert client.get("/api/auth/me").json()["verwalter"] is False


def test_without_a_database_the_numbers_say_so_and_the_failures_do_not(
    oidc, client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """The statistics need a database; the error list deliberately does not.

    An operations page that goes blank exactly when something is wrong is worse
    than one that says where its numbers come from.
    """

    monkeypatch.setenv("ADMIN_ACCOUNTS", CHIEF.account_key)
    reset_services()
    _sign_in(client, CHIEF)
    telemetry.recorder().error("dienst", "ALKIS hat nicht geantwortet.", dienst="ALKIS", status=502)

    assert client.get("/api/verwaltung/uebersicht").status_code == 503
    assert client.get("/api/verwaltung/statistik").status_code == 503

    answer = client.get("/api/verwaltung/fehler")
    assert answer.status_code == 200
    body = answer.json()
    assert body["quelle"] == "speicher"
    assert body["eintraege"][0]["meldung"] == "ALKIS hat nicht geantwortet."


def test_a_window_that_ends_before_it_begins_is_refused(
    oidc, client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("ADMIN_ACCOUNTS", CHIEF.account_key)
    reset_services()
    _sign_in(client, CHIEF)

    answer = client.get(
        "/api/verwaltung/fehler",
        params={"von": "2026-09-18T10:00:00Z", "bis": "2026-09-18T09:00:00Z"},
    )

    assert answer.status_code == 400
    assert "Ende" in answer.json()["detail"]


# --------------------------------------------------------------------------
# The burst guard, against the recorder itself
# --------------------------------------------------------------------------


def test_the_burst_guard_blocks_inside_the_window_not_at_the_end_of_the_hour():
    """Three calls in the window, and the third one is already refused.

    The whole point of the short window: an hourly counter cannot stop
    anything, because by the time it shows the hour, the hour has happened.
    """

    tally = telemetry.Recorder(burst_calls=3, burst_window_s=60, auto_block_minutes=15)

    assert tally.spend("kennung-1") is None
    assert tally.spend("kennung-1") is None
    block = tally.spend("kennung-1")

    assert block is not None
    assert block.automatisch is True
    assert tally.blocked("kennung-1") is not None
    # And somebody else in the same window is untouched.
    assert tally.blocked("kennung-2") is None


def test_tiles_are_counted_for_the_account_and_kept_out_of_the_window():
    """One screen of a map is dozens of tiles; a guard that counted them would
    fire on somebody simply looking at the map."""

    tally = telemetry.Recorder(burst_calls=3, burst_window_s=60)

    for _ in range(10):
        assert tally.spend("kennung-1", burst=False) is None

    assert tally.blocked("kennung-1") is None
    counted = sum(entry.anzahl for entry in tally.live_accounts().values())
    assert counted == 10


def test_a_blocked_account_is_refused_before_it_spends_anything(oidc, client: TestClient):
    """The block bites on a route that goes outward, with a German reason."""

    _sign_in(client, CHIEF)
    telemetry.recorder().set_block(
        telemetry.Block(
            kennung=CHIEF.account_key,
            bis=datetime.now(timezone.utc) + timedelta(minutes=5),
            grund="Automatisch gesperrt: zu viele Anfragen.",
            automatisch=True,
        )
    )

    answer = client.post("/api/geocode", json={"text": "Mölkau 204"})

    assert answer.status_code == 403
    assert "gesperrt" in answer.json()["detail"]


def test_lifting_a_block_also_forgets_the_window_that_caused_it():
    """Otherwise the next request trips the same guard and the block is back.

    Measured the hard way: a screenshot run spent 347 calls in an hour, the
    guard fired, and the block placed by hand right after it came straight back
    with nothing on screen saying why.
    """

    tally = telemetry.Recorder(burst_calls=3, burst_window_s=600)
    for _ in range(3):
        tally.spend("kennung-1")
    assert tally.blocked("kennung-1") is not None

    tally.clear_block("kennung-1")

    assert tally.blocked("kennung-1") is None
    assert tally.spend("kennung-1") is None
    assert tally.blocked("kennung-1") is None


def test_a_block_that_is_over_stops_blocking(oidc, client: TestClient):
    _sign_in(client, CHIEF)
    telemetry.recorder().set_block(
        telemetry.Block(
            kennung=CHIEF.account_key,
            bis=datetime.now(timezone.utc) - timedelta(seconds=1),
            grund="abgelaufen",
            automatisch=True,
        )
    )

    assert telemetry.recorder().blocked(CHIEF.account_key) is None


def test_what_the_flush_could_not_write_is_not_lost():
    """A database down for a minute must not cost the minute."""

    tally = telemetry.Recorder()
    tally.count("dienst", "ALKIS")
    tally.spend("kennung-1")
    snapshot = tally.drain()
    assert tally.drain().empty

    tally.put_back(snapshot)

    assert sum(counter.anzahl for counter in tally.live_hours().values()) == 1
    assert sum(entry.anzahl for entry in tally.live_accounts().values()) == 1


# --------------------------------------------------------------------------
# With a real database
# --------------------------------------------------------------------------


@needs_database
def test_the_migration_gives_users_the_key_the_rest_of_the_app_speaks(admin: TestClient):
    """The account key in the row is the one ``Identity`` computes.

    Two spellings of one identifier is the failure this column exists to
    prevent, so the test compares them rather than trusting that they match.
    """

    admin.put(
        "/api/plots/plot-1",
        json={"dokument": {"id": "plot-1", "name": "Wiesenstraße"}, "geaendert_am": None},
    )

    stored = _run(
        lambda connection: connection.fetchval(
            "select kennung from users where subject = $1", CHIEF.subject
        )
    )

    assert stored == CHIEF.account_key


@needs_database
def test_promotion_and_the_last_administrator(admin: TestClient, monkeypatch: pytest.MonkeyPatch):
    """Somebody who stored something can be promoted; somebody who has not, cannot."""

    # The same client with another cookie, never a second one: two TestClients
    # are two event loops on one asyncpg pool, and the failure that produces
    # names neither of them.
    _sign_in(admin, OTHER)
    admin.put("/api/plots/plot-2", json={"dokument": {"id": "plot-2"}, "geaendert_am": None})
    assert admin.get("/api/verwaltung/uebersicht").status_code == 403

    _sign_in(admin, CHIEF)
    answer = admin.post(
        f"/api/verwaltung/konten/{OTHER.account_key}/rolle", json={"ist_admin": True}
    )
    assert answer.status_code == 200
    assert answer.json()["ist_admin"] is True

    # And now they are in, by the flag alone -- their key is not configured.
    _sign_in(admin, OTHER)
    assert admin.get("/api/verwaltung/uebersicht").status_code == 200

    _sign_in(admin, CHIEF)
    unknown = "0" * 32
    missing = admin.post(f"/api/verwaltung/konten/{unknown}/rolle", json={"ist_admin": True})
    assert missing.status_code == 404
    assert "gesichert" in missing.json()["detail"]


@needs_database
def test_the_last_administrator_cannot_be_demoted_without_one_in_the_configuration(
    database, monkeypatch: pytest.MonkeyPatch
):
    """Otherwise the area is reachable by nobody, from inside the area itself."""

    monkeypatch.setenv("ADMIN_ACCOUNTS", "")
    reset_services()
    with TestClient(fastapi_app) as client:
        _sign_in(client, CHIEF)
        client.put(
            "/api/plots/plot-1", json={"dokument": {"id": "plot-1"}, "geaendert_am": None}
        )
        _run(
            lambda connection: connection.execute(
                "update users set ist_admin = true where kennung = $1", CHIEF.account_key
            )
        )

        answer = client.post(
            f"/api/verwaltung/konten/{CHIEF.account_key}/rolle", json={"ist_admin": False}
        )

    assert answer.status_code == 409
    assert "letzte Verwalter" in answer.json()["detail"]


@needs_database
def test_blocking_an_account_stops_it_and_lifting_it_lets_it_through(admin: TestClient):
    blocked = admin.post(
        f"/api/verwaltung/konten/{OTHER.account_key}/sperre",
        json={"minuten": 30, "grund": "Auffällig viele Anfragen"},
    )
    assert blocked.status_code == 200
    assert blocked.json()["automatisch"] is False

    _sign_in(admin, OTHER)
    refused = admin.get("/api/plots")
    assert refused.status_code == 403
    assert "gesperrt" in refused.json()["detail"]

    stored = _run(lambda connection: connection.fetchval("select count(*) from sperren"))
    assert stored == 1

    _sign_in(admin, CHIEF)
    assert admin.delete(f"/api/verwaltung/konten/{OTHER.account_key}/sperre").status_code == 204

    _sign_in(admin, OTHER)
    assert admin.get("/api/plots").status_code == 200


@needs_database
def test_an_administrator_cannot_lock_themselves_out(admin: TestClient):
    answer = admin.post(
        f"/api/verwaltung/konten/{CHIEF.account_key}/sperre", json={"minuten": 5, "grund": ""}
    )

    assert answer.status_code == 409
    assert "eigene" in answer.json()["detail"]


@needs_database
def test_the_counters_add_up_over_a_flush_rather_than_replacing_each_other(database):
    """Two flushes of the same hour are one row with the sum in it.

    Driven from a loop of this test's own rather than through the client: an
    asyncpg pool belongs to the loop that made it, and the store is what is
    being tested here, not a route.
    """

    from app.deps import admin_store

    async def go() -> None:
        store = admin_store()
        tally = telemetry.Recorder()
        tally.count("dienst", "ALKIS", "ok", duration_ms=120)
        await store.flush(tally.drain())
        tally.count("dienst", "ALKIS", "ok", duration_ms=80)
        await store.flush(tally.drain())
        await store.storage.close()

    asyncio.run(go())

    row = _run(
        lambda connection: connection.fetchrow(
            "select anzahl, dauer_ms from nutzung where dienst = 'ALKIS' and ergebnis = 'ok'"
        )
    )
    assert row["anzahl"] == 2
    assert row["dauer_ms"] == 200


@needs_database
def test_the_statistics_answer_the_window_that_was_asked_for(admin: TestClient):
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    _run(
        lambda connection: connection.executemany(
            """
            insert into nutzung (stunde, bereich, dienst, ergebnis, anzahl, dauer_ms,
                                 tokens_ein, tokens_aus)
            values ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            [
                (now - timedelta(hours=1), "dienst", "ALKIS", "ok", 10, 1000, 0, 0),
                (now - timedelta(hours=1), "dienst", "ALKIS", "fehler", 2, 400, 0, 0),
                (now - timedelta(days=40), "dienst", "ALKIS", "ok", 99, 9900, 0, 0),
                (now, "modell", "test/model", "ok", 3, 300, 1200, 450),
            ],
        )
    )

    answer = admin.get(
        "/api/verwaltung/statistik",
        params={
            "von": (now - timedelta(hours=2)).isoformat(),
            "bis": (now + timedelta(hours=1)).isoformat(),
        },
    )

    assert answer.status_code == 200
    body = answer.json()
    # The row from forty days ago is outside the window and is not in the sum.
    assert body["summe"]["anfragen"] == 15
    assert body["summe"]["fehler"] == 2
    assert body["summe"]["tokens_ein"] == 1200
    assert body["summe"]["tokens_aus"] == 450
    services = {row["dienst"]: row for row in body["nach_dienst"]}
    assert services["ALKIS"]["anfragen"] == 12
    assert services["test/model"]["bereich"] == "modell"


@needs_database
def test_the_account_list_holds_somebody_who_never_stored_anything(admin: TestClient):
    """The full outer join is the point: the account worth looking at may have
    no row in ``users`` at all."""

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    _run(
        lambda connection: connection.execute(
            """
            insert into nutzung_konto (stunde, kennung, anzahl, fehler, tokens_ein, tokens_aus)
            values ($1, $2, 4711, 3, 0, 0)
            """,
            now,
            OTHER.account_key,
        )
    )

    answer = admin.get("/api/verwaltung/konten")

    assert answer.status_code == 200
    rows = {row["kennung"]: row for row in answer.json()["konten"]}
    assert rows[OTHER.account_key]["anfragen"] == 4711
    assert rows[OTHER.account_key]["angelegt"] is None
    assert rows[OTHER.account_key]["grundstuecke"] == 0


@needs_database
def test_the_shared_links_are_listed_without_what_is_in_them(admin: TestClient):
    admin.put("/api/plots/plot-1", json={"dokument": {"id": "plot-1"}, "geaendert_am": None})
    created = admin.post(
        "/api/shares",
        json={"dokument": {"id": "plot-1", "name": "Wiesenstraße", "note": "geheim"}, "umfang": {}},
    )
    assert created.status_code in (200, 201)
    token = created.json()["id"]

    listed = admin.get("/api/verwaltung/freigaben").json()["freigaben"]

    assert [row["token"] for row in listed] == [token]
    assert "dokument" not in listed[0]
    assert "geheim" not in str(listed[0])

    assert admin.delete(f"/api/verwaltung/freigaben/{token}").status_code == 204
    assert admin.get("/api/verwaltung/freigaben").json()["freigaben"] == []


@needs_database
def test_the_red_button_needs_both_confirmations(admin: TestClient):
    admin.put("/api/plots/plot-1", json={"dokument": {"id": "plot-1"}, "geaendert_am": None})

    # Without a key at all.
    assert (
        admin.post(
            "/api/verwaltung/datenbank/leeren",
            json={"schluessel": "erfunden", "bestaetigung": "ALLES LÖSCHEN", "umfang": ["konten"]},
        ).status_code
        == 400
    )

    prepared = admin.post("/api/verwaltung/datenbank/vorbereiten").json()

    # With the key, and the sentence typed wrong.
    wrong = admin.post(
        "/api/verwaltung/datenbank/leeren",
        json={"schluessel": prepared["schluessel"], "bestaetigung": "ja", "umfang": ["konten"]},
    )
    assert wrong.status_code == 400
    assert prepared["satz"] in wrong.json()["detail"]

    # A used key is used up, so the wrong attempt above cannot be corrected by
    # sending it again -- the dialog starts over.
    again = admin.post("/api/verwaltung/datenbank/vorbereiten").json()
    done = admin.post(
        "/api/verwaltung/datenbank/leeren",
        json={
            "schluessel": again["schluessel"],
            "bestaetigung": again["satz"],
            "umfang": ["konten"],
        },
    )

    assert done.status_code == 200
    assert done.json()["geleert"]["plots"] == 1
    assert _run(lambda connection: connection.fetchval("select count(*) from users")) == 0
    # And the record of who pressed it is still there.
    assert _run(lambda connection: connection.fetchval("select count(*) from pruefprotokoll")) >= 1


@needs_database
def test_the_audit_trail_says_who_did_what(admin: TestClient):
    admin.post(
        f"/api/verwaltung/konten/{OTHER.account_key}/sperre",
        json={"minuten": 5, "grund": "Test"},
    )

    entries = admin.get("/api/verwaltung/protokoll").json()["eintraege"]

    assert entries[0]["aktion"] == "sperre"
    assert entries[0]["ziel"] == OTHER.account_key
    assert entries[0]["kennung"] == CHIEF.account_key
    assert entries[0]["details"]["grund"] == "Test"


@needs_database
def test_the_sweep_drops_what_is_past_its_retention(database):
    from app.deps import admin_store

    async def go() -> dict[str, int]:
        store = admin_store()
        # Opens the pool and applies the schema, which is what puts the table
        # there for the statement below.
        await store.storage.start()
        await _insert_old_row()
        removed = await store.sweep(90)
        await store.storage.close()
        return removed

    async def _insert_old_row() -> None:
        connection = await asyncpg.connect(TEST_DATABASE_URL)
        try:
            await connection.execute(
                """
                insert into nutzung (stunde, bereich, dienst, ergebnis, anzahl)
                values ($1, 'dienst', 'ALKIS', 'ok', 1)
                """,
                datetime.now(timezone.utc) - timedelta(days=200),
            )
        finally:
            await connection.close()

    removed = asyncio.run(go())

    assert removed["nutzung"] == 1
    assert _run(lambda connection: connection.fetchval("select count(*) from nutzung")) == 0


# --------------------------------------------------------------------------
# What a model call cost, and what it must never claim to have cost
# --------------------------------------------------------------------------


def test_a_model_without_a_price_costs_nothing_that_can_be_said():
    """The one mistake this must not make is „0,00 €“ for an unknown model."""

    from app.prices import Prices

    prices = Prices(
        usd_per_euro=1.25,
        models={"openai/gpt-4o-mini": {"ein_je_mio_usd": 0.15, "aus_je_mio_usd": 0.60}},
    )

    assert prices.euro("openai/gpt-4o-mini", 1_000_000, 0) == pytest.approx(0.12)
    assert prices.euro("gibt/es-nicht", 1_000_000, 1_000_000) is None
    # And without a rate there is nothing to convert with, so still not zero.
    assert Prices(models=prices.models).euro("openai/gpt-4o-mini", 1_000_000, 0) is None


def test_a_missing_price_list_is_a_state_and_not_a_crash(tmp_path):
    from app.prices import load_prices

    prices = load_prices(tmp_path / "gibt-es-nicht.json")

    assert prices.usable is False
    assert "Keine Preisliste" in (prices.problem or "")


def test_the_shipped_price_list_prices_the_model_this_project_defaults_to():
    """The file is committed, so this is checkable rather than assumed.

    Against the *default* model rather than the configured one: the test suite
    points LLM_MODEL at an invented endpoint, and what is worth pinning is that
    the price list a fresh deployment gets covers the model a fresh deployment
    uses.
    """

    from pathlib import Path

    from app.prices import load_prices
    from app.settings import LLM_DEFAULTS, LLMSettings

    # Not `model_fields["model"].default`: that field is empty on purpose since
    # the provider became a choice, and the model a deployment actually gets
    # comes from `LLM_DEFAULTS`. The price list is OpenRouter's, so it is
    # OpenRouter's default that has to be in it — the others are priced by
    # whoever serves them, and Ollama runs on the deployment's own machine.
    assert LLMSettings.model_fields["model"].default == ""
    shipped = LLM_DEFAULTS["openrouter"][1]
    prices = load_prices(Path(__file__).resolve().parents[2] / "ops" / "llm-preise.json")

    assert prices.usable
    assert prices.euro(shipped, 1_000, 1_000) is not None


@needs_database
def test_the_statistics_carry_the_cost_of_the_model_and_only_of_the_model(admin: TestClient):
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    _run(
        lambda connection: connection.executemany(
            """
            insert into nutzung (stunde, bereich, dienst, ergebnis, anzahl, dauer_ms,
                                 tokens_ein, tokens_aus)
            values ($1, $2, $3, 'ok', 1, 10, $4, $5)
            """,
            [
                (now, "modell", "openai/gpt-4o-mini", 1_000_000, 1_000_000),
                (now, "dienst", "ALKIS", 0, 0),
            ],
        )
    )

    body = admin.get("/api/verwaltung/statistik").json()

    rows = {row["dienst"]: row for row in body["nach_dienst"]}
    assert rows["openai/gpt-4o-mini"]["kosten_eur"] > 0
    # A call to the cadastre has no price per request, and a 0,00 € beside it
    # would read as a measurement.
    assert rows["ALKIS"]["kosten_eur"] is None
    assert body["preise"]["vorhanden"] is True
    assert body["preise"]["usd_je_eur"] > 0


@needs_database
def test_the_comparison_is_asked_for_and_is_the_period_before(admin: TestClient):
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    _run(
        lambda connection: connection.executemany(
            """
            insert into nutzung (stunde, bereich, dienst, ergebnis, anzahl)
            values ($1, 'dienst', 'ALKIS', 'ok', $2)
            """,
            [(now - timedelta(hours=1), 5), (now - timedelta(hours=30), 11)],
        )
    )
    window = {
        "von": (now - timedelta(hours=24)).isoformat(),
        "bis": (now + timedelta(hours=1)).isoformat(),
    }

    plain = admin.get("/api/verwaltung/statistik", params=window).json()
    assert plain["vergleich"] is None

    compared = admin.get("/api/verwaltung/statistik", params={**window, "vergleich": "true"}).json()
    assert compared["summe"]["anfragen"] == 5
    # The 25 hours before hold the other row.
    assert compared["vergleich_summe"]["anfragen"] == 11


# --------------------------------------------------------------------------
# Many accounts: a page, a search, and a total
# --------------------------------------------------------------------------


@needs_database
def test_the_account_list_is_paged_and_searchable(admin: TestClient):
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    _run(
        lambda connection: connection.executemany(
            "insert into nutzung_konto (stunde, kennung, anzahl) values ($1, $2, $3)",
            [(now, f"{index:032x}", 100 - index) for index in range(40)],
        )
    )

    first = admin.get("/api/verwaltung/konten", params={"limit": 10}).json()
    assert len(first["konten"]) == 10
    assert first["gesamt"] == 40
    assert first["konten"][0]["anfragen"] == 100

    second = admin.get("/api/verwaltung/konten", params={"limit": 10, "offset": 10}).json()
    # A total order, so no row appears on two pages.
    assert not {row["kennung"] for row in first["konten"]} & {
        row["kennung"] for row in second["konten"]
    }

    found = admin.get("/api/verwaltung/konten", params={"suche": f"{7:032x}"}).json()
    assert [row["kennung"] for row in found["konten"]] == [f"{7:032x}"]
    assert found["gesamt"] == 1


@needs_database
def test_the_auskunft_holds_everything_stored_about_one_account(admin: TestClient):
    admin.put(
        "/api/plots/plot-1",
        json={"dokument": {"id": "plot-1", "name": "Wiesenstraße"}, "geaendert_am": None},
    )

    answer = admin.get(f"/api/verwaltung/konten/{CHIEF.account_key}/auskunft")

    assert answer.status_code == 200
    assert "auskunft-" in answer.headers["content-disposition"]
    record = answer.json()
    assert record["konto"]["kennung"] == CHIEF.account_key
    # Verbatim, not summarised.
    assert record["grundstuecke"][0]["dokument"]["name"] == "Wiesenstraße"
    # And the act itself is in the audit trail, like every other.
    assert admin.get("/api/verwaltung/protokoll").json()["eintraege"][0]["aktion"] == "auskunft-erteilt"


# --------------------------------------------------------------------------
# The announcement, which is the one text a person writes
# --------------------------------------------------------------------------


@needs_database
def test_the_announcement_is_public_only_while_it_is_switched_on(admin: TestClient):
    # Nothing set: a normal deployment, answering 200 with an empty banner
    # rather than 404 on every page load.
    assert admin.get("/api/ansage").json()["sichtbar"] is False

    admin.put(
        "/api/verwaltung/ansage",
        json={"text": "Wartung heute ab 18 Uhr.", "art": "warnung", "sichtbar": True},
    )

    public = admin.get("/api/ansage").json()
    assert public["text"] == "Wartung heute ab 18 Uhr."
    assert public["art"] == "warnung"

    # Switched off, and the text is still there for the next time.
    admin.put(
        "/api/verwaltung/ansage",
        json={"text": "Wartung heute ab 18 Uhr.", "art": "warnung", "sichtbar": False},
    )
    assert admin.get("/api/ansage").json()["sichtbar"] is False
    assert admin.get("/api/verwaltung/ansage").json()["text"] == "Wartung heute ab 18 Uhr."


@needs_database
def test_an_announcement_past_its_end_stops_showing_itself(admin: TestClient):
    admin.put(
        "/api/verwaltung/ansage",
        json={
            "text": "Gestern war Wartung.",
            "sichtbar": True,
            "bis": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        },
    )

    assert admin.get("/api/ansage").json()["sichtbar"] is False
    # Left in the table, so switching it back on is one click.
    assert admin.get("/api/verwaltung/ansage").json()["text"] == "Gestern war Wartung."


# --------------------------------------------------------------------------
# The recurring jobs
# --------------------------------------------------------------------------


def test_the_job_list_is_the_schedulers_own(
    oidc, client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
):
    monkeypatch.setenv("ADMIN_ACCOUNTS", CHIEF.account_key)
    monkeypatch.setenv("JOBS_STATE_DIR", str(tmp_path / "state"))
    reset_services()
    _sign_in(client, CHIEF)

    body = client.get("/api/verwaltung/jobs").json()

    assert {job["name"] for job in body["jobs"]} >= {"cache-sweep", "llm-preise"}
    # No scheduler in a test, and the page says so rather than showing a button
    # whose request nothing would pick up.
    assert body["scheduler_laeuft"] is False
    assert "kein Scheduler" in body["hinweis"]


def test_a_requested_run_is_a_file_the_scheduler_picks_up(
    oidc, client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
):
    """The whole handover, both halves, without a container in sight."""

    from app import jobs as jobslib

    state = tmp_path / "state"
    monkeypatch.setenv("ADMIN_ACCOUNTS", CHIEF.account_key)
    monkeypatch.setenv("JOBS_STATE_DIR", str(state))
    reset_services()
    _sign_in(client, CHIEF)

    answer = client.post("/api/verwaltung/jobs/cache-sweep/starten")

    assert answer.status_code == 200
    assert answer.json()["angefordert"]
    # And the scheduler's side of it: claimed once, and gone afterwards, so a
    # job that fails is not started again on every tick.
    assert jobslib.take_request(state, "cache-sweep") is not None
    assert jobslib.take_request(state, "cache-sweep") is None


def test_an_unknown_job_is_refused_rather_than_written(
    oidc, client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
):
    monkeypatch.setenv("ADMIN_ACCOUNTS", CHIEF.account_key)
    monkeypatch.setenv("JOBS_STATE_DIR", str(tmp_path / "state"))
    reset_services()
    _sign_in(client, CHIEF)

    answer = client.post("/api/verwaltung/jobs/erfundener-lauf/starten")

    assert answer.status_code == 404
    assert not (tmp_path / "state" / "erfundener-lauf.angefordert").exists()
