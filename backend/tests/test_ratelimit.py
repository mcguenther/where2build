"""The per-account ceiling on calls that leave this server.

What is being tested here is mostly *who pays*, not the arithmetic. The number
is a setting and a deployment will change it; the two things that must not be
wrong are that a signed-in account is counted as itself, and that a signed-out
caller is counted by an address nobody can forge -- ``X-Forwarded-For`` is a
header, and a header is whatever the sender typed.

Time is moved by hand. The limiter's ``clock`` is an attribute for exactly this
reason: a test that waits out a real window is a test nobody runs.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app import session
from app.deps import map_limiter, reset_services, service_limiter

from .conftest import BORIS_URL, DOP_URL, OIDC_ISSUER, fixture_text

SESSION_COOKIE = "w2b_sitzung"
SESSION_SECRET = "sitzungsschluessel-fuer-den-test"

# The cheapest endpoint that really goes outward: one GET, one WMS answer.
LANDVALUE = "/api/landvalue"
COORDINATE = {"lat": 51.3397, "lon": 12.3731}

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6360000002000100ffff0300000600"
    "05fe02fe0000000049454e44ae426082"
)


class Clock:
    """A clock the test winds forward itself."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def budget(monkeypatch: pytest.MonkeyPatch):
    """A deployment with a small budget, so the line is reachable in a test."""

    monkeypatch.setenv("RATELIMIT_ENABLED", "true")
    monkeypatch.setenv("RATELIMIT_SERVICE_CALLS", "3")
    monkeypatch.setenv("RATELIMIT_MAP_TILES", "5")
    monkeypatch.setenv("RATELIMIT_WINDOW_S", "3600")
    reset_services()
    yield


@pytest.fixture
def clock(budget) -> Clock:
    """The same clock in both limiters, wound by hand."""

    fake = Clock()
    service_limiter().clock = fake
    map_limiter().clock = fake
    return fake


@pytest.fixture
def switched_off(monkeypatch: pytest.MonkeyPatch):
    """The single-seat setting: no budget at all."""

    monkeypatch.setenv("RATELIMIT_ENABLED", "false")
    monkeypatch.setenv("RATELIMIT_SERVICE_CALLS", "3")
    reset_services()
    yield


def _boris() -> None:
    respx.get(BORIS_URL).mock(
        return_value=httpx.Response(
            200,
            text=fixture_text("boris_getfeatureinfo.txt"),
            headers={"content-type": "text/plain"},
        )
    )


def _sign_in(client: TestClient, subject: str) -> None:
    client.cookies.set(
        SESSION_COOKIE,
        session.sign(
            {"iss": OIDC_ISSUER, "sub": subject, "name": "Erika Musterfrau"},
            SESSION_SECRET,
            ttl_s=3600,
        ),
    )


@respx.mock
def test_calls_below_the_limit_all_go_through(budget, client: TestClient):
    _boris()

    for _ in range(3):
        assert client.get(LANDVALUE, params=COORDINATE).status_code == 200


@respx.mock
def test_the_call_past_the_limit_is_a_429_with_retry_after(budget, client: TestClient):
    _boris()
    for _ in range(3):
        client.get(LANDVALUE, params=COORDINATE)

    answer = client.get(LANDVALUE, params=COORDINATE)

    assert answer.status_code == 429
    # The seconds are the machine-readable half of what the sentence says.
    assert 0 < int(answer.headers["retry-after"]) <= 3600
    detail = answer.json()["detail"]
    assert "3 Abrufe je Stunde" in detail
    # It explains the budget rather than blaming the caller, and it says when.
    assert "fremde Dienste" in detail
    assert "Weiter geht es in" in detail


@respx.mock
def test_a_refused_call_never_reaches_the_upstream(budget, client: TestClient):
    route = respx.get(BORIS_URL).mock(
        return_value=httpx.Response(
            200,
            text=fixture_text("boris_getfeatureinfo.txt"),
            headers={"content-type": "text/plain"},
        )
    )
    # A different coordinate each time, or the disk cache would answer the
    # second and third itself and the count would prove nothing.
    for step in range(4):
        client.get(LANDVALUE, params={"lat": 51.3 + step / 10, "lon": 12.37})

    # Three went through, the fourth was refused before anything went out --
    # which is the whole point: the budget protects the other end, not us.
    assert route.call_count == 3


@respx.mock
def test_after_the_window_it_continues(clock: Clock, client: TestClient):
    _boris()
    for _ in range(3):
        client.get(LANDVALUE, params=COORDINATE)
    refused = client.get(LANDVALUE, params=COORDINATE)
    assert refused.status_code == 429

    # One second short of the window is still too early ...
    clock.advance(3599)
    assert client.get(LANDVALUE, params=COORDINATE).status_code == 429

    # ... and once the oldest call has left it, the budget is there again.
    clock.advance(2)
    assert client.get(LANDVALUE, params=COORDINATE).status_code == 200


@respx.mock
def test_retry_after_counts_down_as_the_window_slides(clock: Clock, client: TestClient):
    _boris()
    for _ in range(3):
        client.get(LANDVALUE, params=COORDINATE)

    first = int(client.get(LANDVALUE, params=COORDINATE).headers["retry-after"])
    clock.advance(600)
    later = int(client.get(LANDVALUE, params=COORDINATE).headers["retry-after"])

    assert first == 3600
    assert later == 3000


@respx.mock
def test_two_accounts_count_separately(budget, oidc, client: TestClient):
    _boris()
    _sign_in(client, "erika")
    for _ in range(3):
        client.get(LANDVALUE, params=COORDINATE)
    assert client.get(LANDVALUE, params=COORDINATE).status_code == 429

    # Same browser, same address, other account: an untouched budget.
    _sign_in(client, "moritz")

    assert client.get(LANDVALUE, params=COORDINATE).status_code == 200


@respx.mock
def test_switched_off_nothing_is_counted(switched_off, client: TestClient):
    _boris()

    for _ in range(10):
        assert client.get(LANDVALUE, params=COORDINATE).status_code == 200


def test_an_endpoint_that_asks_nobody_does_not_pay_in(budget, client: TestClient):
    """/api/health and the district directory answer from this server alone.

    The budget exists to protect the services this one borrows. A route that
    borrows nothing has no reason to be inside it, and putting it there would
    mean a page could lock itself out by describing its own state.
    """

    for _ in range(20):
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/gemarkungen", params={"q": "Mölkau"}).status_code in (200, 503)


@respx.mock
def test_map_tiles_have_their_own_budget(budget, client: TestClient):
    """Five tiles here, three service calls: neither eats the other."""

    respx.get(DOP_URL).mock(
        return_value=httpx.Response(200, content=PNG, headers={"content-type": "image/png"})
    )
    _boris()

    for x in range(5):
        assert client.get(f"/api/tiles/dop/15/{17540 + x}/10986.png").status_code == 200
    assert client.get("/api/tiles/dop/15/17550/10986.png").status_code == 429

    # The service budget was never touched by any of that.
    assert client.get(LANDVALUE, params=COORDINATE).status_code == 200


# --------------------------------------------------------------------------
# Who pays: the peer, and how far it may be believed
# --------------------------------------------------------------------------


@respx.mock
def test_a_forwarded_header_is_ignored_when_no_proxy_is_configured(
    budget, client: TestClient
):
    """Otherwise anybody could spend a fresh budget per made-up address.

    APP_PROXY_HOPS defaults to 0, meaning nothing of ours stands in front, so
    the only address that has been established is the socket peer.
    """

    _boris()
    for index in range(3):
        client.get(
            LANDVALUE, params=COORDINATE, headers={"X-Forwarded-For": f"10.0.0.{index}"}
        )

    answer = client.get(
        LANDVALUE, params=COORDINATE, headers={"X-Forwarded-For": "10.0.0.99"}
    )

    assert answer.status_code == 429


@respx.mock
def test_with_a_proxy_the_address_is_read_from_the_right(
    budget, monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    """nginx appends the peer it saw, so the last entry is the one it vouched for.

    Everything to the left of it is text the caller wrote. Reading the header
    from the left -- the usual mistake -- would hand out a budget per invented
    value, which is worse than not reading it at all.
    """

    monkeypatch.setenv("APP_PROXY_HOPS", "1")
    reset_services()
    _boris()

    for index in range(3):
        # Same real peer (203.0.113.7), a different lie in front of it each time.
        answer = client.get(
            LANDVALUE,
            params=COORDINATE,
            headers={"X-Forwarded-For": f"10.0.0.{index}, 203.0.113.7"},
        )
        assert answer.status_code == 200

    assert (
        client.get(
            LANDVALUE,
            params=COORDINATE,
            headers={"X-Forwarded-For": "10.0.0.99, 203.0.113.7"},
        ).status_code
        == 429
    )
    # Another peer behind the same proxy still has its own budget.
    assert (
        client.get(
            LANDVALUE,
            params=COORDINATE,
            headers={"X-Forwarded-For": "203.0.113.8"},
        ).status_code
        == 200
    )


@respx.mock
def test_a_request_that_bypassed_the_proxy_falls_back_to_the_socket_peer(
    budget, monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    """A health check on the container network arrives without the header."""

    monkeypatch.setenv("APP_PROXY_HOPS", "1")
    reset_services()
    _boris()

    for _ in range(3):
        assert client.get(LANDVALUE, params=COORDINATE).status_code == 200
    assert client.get(LANDVALUE, params=COORDINATE).status_code == 429


# --------------------------------------------------------------------------
# What /api/health says about it
# --------------------------------------------------------------------------


def test_health_names_the_budget_and_how_it_is_counted(budget, client: TestClient):
    dienste = {entry["name"]: entry for entry in client.get("/api/health").json()["dienste"]}

    kontingent = dienste["kontingent"]
    assert kontingent["konfiguriert"] is True
    assert "3 Abrufe je Stunde" in kontingent["hinweis"]
    assert "5 Kartenkacheln" in kontingent["hinweis"]
    # The imprecision belongs in the answer, not only in a comment.
    assert "Arbeitsprozess" in kontingent["hinweis"]
    assert "APP_PROXY_HOPS=0" in kontingent["hinweis"]


@respx.mock
def test_a_budget_of_one_is_still_written_in_German(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    """„1 Abrufe" is the same slip as „liegen 1 Grundstück".

    A ceiling of one is reachable -- a deployment may set it, and the sentence
    is the whole answer a person gets, so the numeral has to agree with the
    noun. Both budgets are checked, because each carries its own article.
    """

    monkeypatch.setenv("RATELIMIT_ENABLED", "true")
    monkeypatch.setenv("RATELIMIT_SERVICE_CALLS", "1")
    monkeypatch.setenv("RATELIMIT_MAP_TILES", "1")
    reset_services()
    _boris()

    client.get(LANDVALUE, params=COORDINATE)
    detail = client.get(LANDVALUE, params=COORDINATE).json()["detail"]
    assert "höchstens ein Abruf je Stunde" in detail
    assert "1 Abrufe" not in detail

    hinweis = {
        entry["name"]: entry for entry in client.get("/api/health").json()["dienste"]
    }["kontingent"]["hinweis"]
    assert "ein Abruf je Stunde" in hinweis
    assert "eine Kartenkachel je Stunde" in hinweis


def test_health_says_when_there_is_no_budget(switched_off, client: TestClient):
    dienste = {entry["name"]: entry for entry in client.get("/api/health").json()["dienste"]}

    kontingent = dienste["kontingent"]
    assert kontingent["konfiguriert"] is False
    assert "Einzelplatz" in kontingent["hinweis"]
    assert "RATELIMIT_ENABLED=true" in kontingent["hinweis"]
