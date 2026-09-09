"""A ceiling on how many calls one account may send through this proxy.

Why this exists is not a formality. This backend owns no data: every answer it
gives comes from somebody else's infrastructure -- the Saxon cadastre, BORIS,
the LUIS environmental server, the UBA, Transitous and, where it is switched
on, a public Overpass instance. As long as the app was a single-seat prototype
that was uncontested; the Overpass manual even says occasional manual requests
are fine. A deployment with accounts is precisely what the same manual calls
"relying on the public instances as backend", and Transitous, a volunteer
service, is in the same position. So one account must not be able to trigger an
unbounded number of outbound calls.

Two things are counted separately and both are per client:

* the **service calls** -- everything that asks an authority, a router or the
  model a question,
* the **map tiles**, which are far more numerous per screen and are covered by
  the shared disk cache, so they get their own, much wider budget.

**Who pays.** Signed in, it is the account: ``Identity.account_key``, the same
stable, non-speaking identifier the rest of the app uses. Signed out, it is the
peer, as well as that can be established -- see ``peer_address``, where the
whole point is that a header a browser can write must not be believed unless a
setting says a proxy put it there.

**In memory, on purpose.** No Redis, no table. That makes the count per worker
process rather than per deployment: with ``--workers 4`` each worker holds its
own tally and the effective ceiling is up to four times the configured one.
That is accepted for a prototype whose documented start is a single uvicorn
process, and it fails in the harmless direction (too permissive, never too
strict). The moment more than one worker is real, the counter has to move into
something the workers share -- Redis with ``INCR`` and ``EXPIRE`` is the usual
answer, and the ``RateLimiter`` interface below is the seam to swap.

The window is a sliding log rather than a fixed bucket: a fixed window lets
twice the limit through across its boundary, and it cannot say when the caller
may continue, which is the one thing a 429 owes the person reading it.
"""

from __future__ import annotations

import math
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Callable

from fastapi import Request

from .services.oidc import Identity

# What a client is called in a bucket key. Only ever used for the key, so the
# two kinds cannot collide: an account never counts against a peer address.
# These are code, not wire format and not anything a user reads, so they are
# English like the rest of it.
ACCOUNT_PREFIX = "account"
PEER_PREFIX = "peer"
UNKNOWN_PEER = "unknown"


@dataclass(frozen=True)
class Decision:
    """The answer to "may this call go out?", with what a 429 has to say."""

    allowed: bool
    limit: int
    window_s: int
    remaining: int
    # Whole seconds until the oldest call leaves the window. Zero while allowed.
    retry_after_s: int


class RateLimiter:
    """A sliding-window log per client, bounded in both directions.

    Bounded in time by the window, and bounded in memory by ``max_clients``:
    without that second bound an anonymous deployment would grow one deque per
    address that ever called, which is a memory leak with a friendly name. The
    least recently seen client is dropped, which at worst grants somebody a
    fresh budget after a flood -- the flood itself is what the limit stopped.
    """

    def __init__(
        self,
        *,
        limit: int,
        window_s: int,
        max_clients: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = max(1, limit)
        self.window_s = max(1, window_s)
        self.max_clients = max(1, max_clients)
        # Monotonic, not wall clock: a system clock that jumps backwards over
        # an NTP correction would freeze every budget until it caught up.
        # Replaceable so a test can move time on without sleeping through it.
        self.clock = clock
        # Insertion order is recency order: every access moves its key to the
        # end, so the front is what gets evicted.
        self._calls: OrderedDict[str, deque[float]] = OrderedDict()

    def check(self, key: str) -> Decision:
        """Count one call against ``key``, unless it would cross the line.

        A refused call is not recorded. Otherwise a client that keeps trying
        would keep pushing its own window forward and never get back in.
        """

        now = self.clock()
        calls = self._calls.get(key)
        if calls is None:
            calls = deque()
            self._calls[key] = calls
        self._calls.move_to_end(key)

        horizon = now - self.window_s
        while calls and calls[0] <= horizon:
            calls.popleft()

        if len(calls) >= self.limit:
            return Decision(
                allowed=False,
                limit=self.limit,
                window_s=self.window_s,
                remaining=0,
                retry_after_s=max(1, math.ceil(calls[0] + self.window_s - now)),
            )

        calls.append(now)
        self._forget_idle_clients()
        return Decision(
            allowed=True,
            limit=self.limit,
            window_s=self.window_s,
            remaining=self.limit - len(calls),
            retry_after_s=0,
        )

    def _forget_idle_clients(self) -> None:
        while len(self._calls) > self.max_clients:
            self._calls.popitem(last=False)


def peer_address(request: Request, proxy_hops: int) -> str:
    """The address to count an unauthenticated call against.

    ``X-Forwarded-For`` is a header, and a header is whatever the sender typed:
    read straight off the request it lets anybody spend somebody else's budget,
    or dodge their own with a fresh value per call. So it is only read when
    ``APP_PROXY_HOPS`` says how many proxies of our own stand in front, and then
    from the *right*, not the left. nginx appends the peer it saw
    (``$proxy_add_x_forwarded_for``), so with one hop the last entry is the one
    our own proxy vouched for and everything left of it is the caller's text.

    With hops configured but no such header, the request did not come through
    the proxy at all -- a health check on the container network, say -- and the
    socket peer is then both available and true.
    """

    if proxy_hops > 0:
        forwarded = [
            part.strip()
            for part in request.headers.get("x-forwarded-for", "").split(",")
            if part.strip()
        ]
        if len(forwarded) >= proxy_hops:
            return forwarded[-proxy_hops]
    client = request.client
    return client.host if client and client.host else UNKNOWN_PEER


def client_key(request: Request, identity: Identity | None, proxy_hops: int) -> str:
    """Whose budget this call is drawn from."""

    if identity is not None:
        return f"{ACCOUNT_PREFIX}:{identity.account_key}"
    return f"{PEER_PREFIX}:{peer_address(request, proxy_hops)}"


# German, and deliberately not an accusation: the usual reason for seeing this
# is a tab left open on a busy page, not abuse. It says what applies, when it
# continues, and why there is a budget at all.
DENIED = (
    "Das Abrufkontingent für diesen Zugang ist erreicht: höchstens {allowance} "
    "{window}. Weiter geht es in {wait}. Diese Anwendung fragt für jeden Abruf "
    "fremde Dienste (Kataster, Bodenrichtwerte, Routing, Umweltdaten), die sie nur "
    "mitbenutzen darf; deshalb haushaltet sie mit den Anfragen."
)


def allowance_text(limit: int) -> str:
    """„ein Abruf“, „600 Abrufe“ -- how many the budget is.

    A limit of one is reachable: a deployment may set it, and a test does. The
    number alone next to a plural noun („1 Abrufe“) is the same slip as
    „liegen 1 Grundstück“ -- the noun is declined and the numeral is not.
    """

    return "ein Abruf" if limit == 1 else f"{limit} Abrufe"


def tile_allowance_text(limit: int) -> str:
    """The same for the tile budget, which needs its own article and plural."""

    return "eine Kartenkachel" if limit == 1 else f"{limit} Kartenkacheln"


def window_text(window_s: int) -> str:
    """„je Stunde“, „je 15 Minuten“ -- the period the limit is stated over."""

    if window_s % 3600 == 0:
        hours = window_s // 3600
        return "je Stunde" if hours == 1 else f"je {hours} Stunden"
    if window_s % 60 == 0:
        minutes = window_s // 60
        return "je Minute" if minutes == 1 else f"je {minutes} Minuten"
    return f"je {window_s} Sekunden"


def wait_text(seconds: int) -> str:
    """How long until it continues, rounded up so the number is never optimistic."""

    if seconds <= 1:
        return "einer Sekunde"
    if seconds < 90:
        return f"{seconds} Sekunden"
    minutes = math.ceil(seconds / 60)
    if minutes < 90:
        return f"{minutes} Minuten"
    return f"{math.ceil(minutes / 60)} Stunden"


def denied_message(decision: Decision) -> str:
    return DENIED.format(
        allowance=allowance_text(decision.limit),
        window=window_text(decision.window_s),
        wait=wait_text(decision.retry_after_s),
    )
