"""One place to talk to external services -- and one place to translate their
failures into HTTP answers a user can understand."""

from __future__ import annotations

import asyncio
import time
import weakref
from typing import Any

import httpx

from .errors import UpstreamError, UpstreamTimeout
from .telemetry import AREA_SERVICE, RESULT_ERROR, RESULT_OK, recorder

# A public routing or authority service answers 5xx now and then, and the
# request that follows a second later usually succeeds. One retry turns that
# into a hiccup rather than a failed page; more than one would only make a real
# outage take longer to report.
_RETRY_ON = (500, 502, 503, 504)
_RETRY_AFTER_S = 0.6

# One client per event loop, made on first use. Building an AsyncClient loads
# the CA bundle into a fresh SSL context -- 50 to 70 ms of synchronous work on
# the event loop, measured here -- and a client per request did that six times
# over while a block of tiles was fetched, stalling every other request behind
# it. Per loop rather than per process because a client's pool is bound to the
# loop it first ran on, and the test suite starts a loop per test; the weak
# keys let a finished loop take its client with it.
#
# Pooling does not keep dead connections: httpcore drops an idle connection
# after the keep-alive expiry (httpx' default, 5 s) and one whose socket turned
# readable while idle, which is the server having hung up. What is left -- a
# connection that dies in the few seconds it sits reused -- is a transport
# error, and the retry below then runs on a new one.
_clients: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient] = (
    weakref.WeakKeyDictionary()
)


def shared_client() -> httpx.AsyncClient:
    """The running loop's client, created the first time it is asked for."""

    loop = asyncio.get_running_loop()
    client = _clients.get(loop)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(follow_redirects=True)
        _clients[loop] = client
    return client


async def close_shared_client() -> None:
    """Close the running loop's client, if it has one. Called on shutdown."""

    client = _clients.pop(asyncio.get_running_loop(), None)
    if client is not None:
        await client.aclose()


def _sentence(*parts: str | None) -> str:
    """Join the parts of a message, dropping the ones a caller left out."""

    return " ".join(part.strip() for part in parts if part and part.strip())


async def request(
    method: str,
    url: str,
    *,
    service: str,
    timeout_s: float,
    user_agent: str,
    expect: str | None = None,
    advice: str | None = None,
    status_hints: dict[int, str] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """Perform one upstream request.

    ``expect`` narrows the accepted content type; authority services answer a
    rejected request with a generic HTML error page and HTTP 400, so a wrong
    content type is as much a failure as a wrong status code.

    ``advice`` is the sentence appended to every failure: what the user can do
    now that this service is unavailable. Every caller passes one -- an error
    that only states the fault leaves the user stuck.

    ``status_hints`` replaces the generic "Status N abgelehnt" for the codes a
    service uses to mean something specific -- Overpass' 429 is "you are over
    your slot quota", which is a different piece of advice from a 500.

    Every call through here is counted -- one per outward request, by service
    and outcome, in ``app/telemetry.py``. This is the choke point every
    authority, router and model request already passes through, so counting
    anywhere else would count some of them twice and others not at all. The
    name counted is the one passed in, which is the German label the caller
    already uses in its own error messages, and which is what an operator
    reads in the statistics.
    """

    started = time.perf_counter()
    outcome = RESULT_ERROR
    try:
        headers = {"User-Agent": user_agent, **(kwargs.pop("headers", None) or {})}
        response: httpx.Response | None = None
        for attempt in range(2):
            last = attempt == 1
            try:
                response = await shared_client().request(
                    method, url, headers=headers, timeout=timeout_s, **kwargs
                )
            except httpx.TimeoutException as exc:
                if last:
                    raise UpstreamTimeout(
                        _sentence(f"{service} hat nicht rechtzeitig geantwortet.", advice)
                    ) from exc
            except httpx.HTTPError as exc:
                if last:
                    raise UpstreamError(
                        _sentence(f"{service} ist derzeit nicht erreichbar.", advice)
                    ) from exc
            else:
                if response.status_code not in _RETRY_ON or last:
                    break
            await asyncio.sleep(_RETRY_AFTER_S)

        assert response is not None
        if response.status_code >= 400:
            raise UpstreamError(
                _sentence(
                    (status_hints or {}).get(response.status_code)
                    or f"{service} hat die Anfrage mit Status {response.status_code} abgelehnt.",
                    advice,
                )
            )
        if expect and expect not in response.headers.get("content-type", ""):
            raise UpstreamError(
                _sentence(
                    f"{service} hat ein unerwartetes Format geliefert "
                    f"({response.headers.get('content-type', 'ohne Angabe')}).",
                    advice,
                )
            )
        outcome = RESULT_OK
        return response
    finally:
        recorder().count(
            AREA_SERVICE,
            service,
            outcome,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
