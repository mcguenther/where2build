"""One place to talk to external services -- and one place to translate their
failures into HTTP answers a user can understand."""

from __future__ import annotations

from typing import Any

import httpx

from .errors import UpstreamError, UpstreamTimeout


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
    """

    headers = {"User-Agent": user_agent, **(kwargs.pop("headers", None) or {})}
    try:
        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
            response = await client.request(method, url, headers=headers, **kwargs)
    except httpx.TimeoutException as exc:
        raise UpstreamTimeout(
            _sentence(f"{service} hat nicht rechtzeitig geantwortet.", advice)
        ) from exc
    except httpx.HTTPError as exc:
        raise UpstreamError(_sentence(f"{service} ist derzeit nicht erreichbar.", advice)) from exc

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
    return response
