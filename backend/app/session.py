"""Signed cookies, with nothing in them a browser may not see.

Two cookies are signed this way: the session that says who is signed in, and
the short-lived one that carries ``state``, ``nonce`` and the PKCE verifier
from ``/api/auth/login`` to ``/api/auth/callback``.

The handshake cookie is *why* there is a signing helper at all. Keeping that
half-finished login in a dict in the process would break in both of the shapes
this deployment actually has: uvicorn restarts during development, and more
than one worker in production would hand the callback to a process that never
saw the login. A cookie travels with the browser that started the handshake,
which is exactly the scope the value has.

Signing is HMAC-SHA256 from the standard library. No encryption, so nothing
secret goes in -- the payload is issuer, subject, a display name and an expiry,
all of which the person the cookie belongs to already knows. What the signature
buys is that they cannot change any of it. Tokens never travel to the browser:
this is a backend-for-frontend, and the access token lives no longer than the
request that fetched it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

_SEPARATOR = "."


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _signature(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def sign(claims: dict[str, Any], secret: str, *, ttl_s: int, now: float | None = None) -> str:
    """One cookie value: the claims plus an expiry, signed.

    The expiry is inside the signature rather than left to the cookie's own
    ``Max-Age``, because a browser is free to keep sending an expired cookie
    and only the server's copy of the deadline can be trusted.
    """

    payload = dict(claims)
    payload["exp"] = int((time.time() if now is None else now) + ttl_s)
    encoded = _b64encode(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())
    return f"{encoded}{_SEPARATOR}{_signature(encoded, secret)}"


def read(value: str | None, secret: str, *, now: float | None = None) -> dict[str, Any] | None:
    """The claims of a valid, unexpired cookie -- otherwise ``None``.

    Every way of failing answers the same way on purpose: a forged signature, a
    truncated cookie and one signed with the previous secret are all simply
    "not signed in", which is the only thing the caller can do anything about.
    """

    if not value or _SEPARATOR not in value:
        return None
    encoded, _, signature = value.rpartition(_SEPARATOR)
    if not hmac.compare_digest(signature, _signature(encoded, secret)):
        return None
    try:
        claims = json.loads(_b64decode(encoded))
    except (ValueError, TypeError):
        return None
    if not isinstance(claims, dict):
        return None
    expires_at = claims.get("exp")
    if not isinstance(expires_at, (int, float)):
        return None
    if (time.time() if now is None else now) >= expires_at:
        return None
    return claims
