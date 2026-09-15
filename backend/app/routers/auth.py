"""/api/auth/... -- signing in, as a backend-for-frontend.

Four endpoints and one cookie. ``/login`` starts an authorization code flow with
PKCE, ``/callback`` finishes it, ``/logout`` ends the session and ``/me`` says
which of the three states the deployment is in: no provider configured, a
provider but nobody signed in, or somebody signed in.

Nothing here is a precondition for anything else in this API. Without
``OIDC_ISSUER`` the app is what it has always been, a tool that keeps its work
in the browser, and every other route behaves identically.
"""

from __future__ import annotations

import hmac
import logging
import secrets

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse

from .. import session
from ..deps import oidc_service
from ..errors import AppError
from ..schemas import AnmeldungStatus
from ..services.oidc import OidcService, challenge_for, new_verifier
from ..settings import OidcSettings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Anmeldung"])

CALLBACK_PATH = "/api/auth/callback"

# Where the login cookie is readable. Narrower than the session's ``/`` because
# nothing outside these four endpoints has any business seeing a PKCE verifier.
_LOGIN_COOKIE_PATH = "/api/auth"

# What the browser is told when a sign-in did not work. Deliberately one value
# and no detail: the reason belongs in the server log, not in a URL that gets
# pasted into a bug report or kept in the browser's history.
_FAILED = "/?anmeldung=fehlgeschlagen"

# Nothing here may sit in a cache: /me is per person, and the two redirects
# carry a Set-Cookie whose value must never be handed to a second browser.
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}

# A return path is a path, not a document. Long enough for any route this app
# has, short enough that nobody stores anything in it.
_MAX_TARGET_LENGTH = 512


def _safe_target(target: str | None) -> str:
    """The path to return to after signing in -- or ``/``.

    An open redirect is the classic way to turn a login endpoint into a
    phishing hop: ``?ziel=https://example.org`` sends the browser off this site
    right after it authenticated. Only a path on this very origin is accepted,
    which rules out an absolute URL (no leading slash), a protocol-relative one
    (``//example.org``) and the backslash spelling some browsers normalise into
    it (``/\\example.org``).
    """

    if not target or not target.startswith("/"):
        return "/"
    if target.startswith("//") or target.startswith("/\\"):
        return "/"
    if any(character < " " or character == "\x7f" for character in target):
        # A newline in a Location header is a response-splitting attempt.
        return "/"
    return target[:_MAX_TARGET_LENGTH]


def _redirect_uri(request: Request, settings: OidcSettings) -> str:
    """The ``redirect_uri`` registered with the provider.

    Derived from the request unless configured, because a development server
    knows its own address and a deployment behind a TLS-terminating proxy does
    not: the request arrives as plain http there, and a redirect_uri that says
    http will not match the registered one. That is what
    ``OIDC_PUBLIC_BASE_URL`` is for.
    """

    base = settings.public_base_url.strip().rstrip("/")
    if not base:
        base = str(request.base_url).rstrip("/")
    return f"{base}{CALLBACK_PATH}"


def _set_cookie(
    response: Response, name: str, value: str, *, max_age: int, path: str, settings: OidcSettings
) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path=path,
        httponly=True,
        # Lax and not Strict: the browser arrives at /callback from the
        # provider's domain, and Strict would withhold the cookie on exactly
        # that navigation. Lax sends it on a top-level GET, which this is.
        samesite="lax",
        secure=settings.cookie_secure,
    )


def _clear_cookie(response: Response, name: str, *, path: str, settings: OidcSettings) -> None:
    response.delete_cookie(
        name, path=path, httponly=True, samesite="lax", secure=settings.cookie_secure
    )


def _clear_login_cookie(response: Response, service: OidcService) -> None:
    """The handshake is single-use: it goes the moment the callback is over."""

    _clear_cookie(
        response,
        service.settings.login_cookie_name,
        path=_LOGIN_COOKIE_PATH,
        settings=service.settings,
    )


def _session_secret(service: OidcService) -> str:
    secret = service.settings.session_secret
    return secret.get_secret_value() if secret else ""


def _failed(service: OidcService) -> RedirectResponse:
    """Back to the start page, with the one thing the frontend may show."""

    answer = RedirectResponse(_FAILED, status_code=303, headers=dict(_NO_STORE))
    _clear_login_cookie(answer, service)
    return answer


@router.get(
    "/me",
    response_model=AnmeldungStatus,
    summary="Anmeldezustand",
)
async def me(
    request: Request,
    response: Response,
    service: OidcService = Depends(oidc_service),
) -> AnmeldungStatus:
    response.headers.update(_NO_STORE)
    if not service.configured:
        return AnmeldungStatus(eingerichtet=False, angemeldet=False)
    identity = service.session_identity(request.cookies.get(service.settings.cookie_name))
    if identity is None:
        return AnmeldungStatus(eingerichtet=True, angemeldet=False)
    return AnmeldungStatus(
        eingerichtet=True,
        angemeldet=True,
        name=identity.name,
        kennung=identity.account_key,
    )


@router.get(
    "/login",
    summary="Anmeldung beginnen",
    response_class=RedirectResponse,
    responses={307: {"description": "Weiterleitung zum Anmeldedienst"}},
)
async def login(
    request: Request,
    ziel: str = Query(
        "/",
        description="Pfad, auf den nach der Anmeldung zurückgeleitet wird; nur eigene Pfade.",
    ),
    service: OidcService = Depends(oidc_service),
) -> Response:
    # 503 with a German sentence, not a redirect: a request that got here on a
    # server without a provider is a hand-typed URL, and it deserves the reason.
    service.require_configured()
    try:
        provider = await service.provider()
    except AppError as exc:
        # The browser is in the middle of a navigation, so a JSON error body
        # would be shown as raw text. The start page can say it in German.
        logger.warning("Sign-in could not be started: %s", exc.message)
        return _failed(service)

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = new_verifier()
    redirect_uri = _redirect_uri(request, service.settings)

    answer = RedirectResponse(
        service.authorization_url(
            provider,
            redirect_uri=redirect_uri,
            state=state,
            nonce=nonce,
            challenge=challenge_for(verifier),
        ),
        status_code=307,
        headers=dict(_NO_STORE),
    )
    # The handshake travels with the browser rather than in this process: a
    # reload during development and a second worker in production would both
    # lose an in-memory copy, and the callback would fail for no reason the
    # user could act on. Signed, HttpOnly, and dead in ten minutes.
    _set_cookie(
        answer,
        service.settings.login_cookie_name,
        session.sign(
            {
                "state": state,
                "nonce": nonce,
                "verifier": verifier,
                "target": _safe_target(ziel),
                # The token endpoint checks redirect_uri against the one the
                # authorization request carried, so the two must be the same
                # string even if the request that arrives here looks different.
                "redirect_uri": redirect_uri,
            },
            _session_secret(service),
            ttl_s=service.settings.login_ttl_s,
        ),
        max_age=service.settings.login_ttl_s,
        path=_LOGIN_COOKIE_PATH,
        settings=service.settings,
    )
    return answer


@router.get(
    "/callback",
    summary="Rückkehr vom Anmeldedienst",
    response_class=RedirectResponse,
    responses={303: {"description": "Weiterleitung in die Anwendung"}},
)
async def callback(
    request: Request,
    code: str | None = Query(None, description="Autorisierungscode des Anmeldedienstes."),
    state: str | None = Query(None, description="Muss zum begonnenen Anmeldeversuch passen."),
    error: str | None = Query(None, description="Fehlerschlüssel, falls der Dienst ablehnt."),
    service: OidcService = Depends(oidc_service),
) -> Response:
    service.require_configured()
    secret = _session_secret(service)
    handshake = session.read(request.cookies.get(service.settings.login_cookie_name), secret)

    if error:
        # Truncated: this value comes from the provider through the browser.
        logger.info("The provider refused the sign-in: %s", error[:100])
        return _failed(service)
    if handshake is None:
        logger.info("Callback without a sign-in this server started")
        return _failed(service)
    if not code or not state or not hmac.compare_digest(state, str(handshake.get("state", ""))):
        logger.warning("Callback state does not match the sign-in that was started")
        return _failed(service)

    try:
        provider = await service.provider()
        identity = await service.exchange(
            provider,
            code=code,
            verifier=str(handshake.get("verifier", "")),
            redirect_uri=str(handshake.get("redirect_uri", "")),
            nonce=str(handshake.get("nonce", "")),
        )
    except AppError as exc:
        logger.warning("Code exchange failed: %s", exc.message)
        return _failed(service)

    answer = RedirectResponse(
        _safe_target(handshake.get("target")), status_code=303, headers=dict(_NO_STORE)
    )
    # Issuer, subject, display name. No access token and no refresh token: the
    # browser never sees one, and nothing here outlives this request.
    _set_cookie(
        answer,
        service.settings.cookie_name,
        session.sign(
            {"iss": identity.issuer, "sub": identity.subject, "name": identity.name},
            secret,
            ttl_s=service.settings.session_ttl_s,
        ),
        max_age=service.settings.session_ttl_s,
        path="/",
        settings=service.settings,
    )
    _clear_login_cookie(answer, service)
    return answer


@router.post(
    "/logout",
    status_code=204,
    summary="Abmelden",
    responses={204: {"description": "Sitzung beendet"}},
)
async def logout(service: OidcService = Depends(oidc_service)) -> Response:
    # No round trip to the provider: this ends the session here. Signing out of
    # the provider itself is the provider's own page, and doing it from here
    # would sign the person out of everything else they have open.
    answer = Response(status_code=204)
    service.end_session(answer)
    _clear_login_cookie(answer, service)
    return answer
