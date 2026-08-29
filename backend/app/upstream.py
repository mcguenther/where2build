"""One place to talk to external services -- and one place to translate their
failures into HTTP answers a user can understand."""

from __future__ import annotations

from typing import Any

import httpx

from .errors import UpstreamError, UpstreamTimeout


async def request(
    method: str,
    url: str,
    *,
    service: str,
    timeout_s: float,
    user_agent: str,
    expect: str | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """Perform one upstream request.

    ``expect`` narrows the accepted content type; authority services answer a
    rejected request with a generic HTML error page and HTTP 400, so a wrong
    content type is as much a failure as a wrong status code.
    """

    headers = {"User-Agent": user_agent, **(kwargs.pop("headers", None) or {})}
    try:
        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
            response = await client.request(method, url, headers=headers, **kwargs)
    except httpx.TimeoutException as exc:
        raise UpstreamTimeout(
            f"{service} hat nicht rechtzeitig geantwortet. Bitte später erneut versuchen."
        ) from exc
    except httpx.HTTPError as exc:
        raise UpstreamError(f"{service} ist derzeit nicht erreichbar.") from exc

    if response.status_code >= 400:
        raise UpstreamError(
            f"{service} hat die Anfrage mit Status {response.status_code} abgelehnt."
        )
    if expect and expect not in response.headers.get("content-type", ""):
        raise UpstreamError(
            f"{service} hat ein unerwartetes Format geliefert "
            f"({response.headers.get('content-type', 'ohne Angabe')})."
        )
    return response
