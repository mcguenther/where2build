"""OpenID Connect, spoken by the backend on the browser's behalf.

Backend-for-frontend: the authorization code, the PKCE verifier, the client
secret and every token stay on this side. What the browser gets is a signed
HttpOnly cookie holding issuer, subject and a display name, and nothing else --
see ``app/session.py``.

No provider is hard-wired. The issuer is configuration, and the authorization,
token and userinfo endpoints are read from its discovery document rather than
guessed: ``/.well-known/openid-configuration`` is the one path a provider
promises, everything below it is the provider's own business.

Only the minimum is kept: issuer, subject, display name. The ``email`` scope is
not asked for at all -- this project holds no contact detail, and a claim that
is never requested is one that cannot be stored by accident.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from fastapi import Response

from .. import session
from ..cache import DiskCache
from ..errors import AppError, BadRequestError, NotConfiguredError, UpstreamError
from ..settings import AppSettings, OidcSettings
from ..upstream import request

logger = logging.getLogger(__name__)

SERVICE_NAME = "Der Anmeldedienst"
ADVICE = "Bitte später erneut anmelden; ohne Konto lässt sich die Anwendung weiter benutzen."

# Length of the PKCE verifier in random bytes. RFC 7636 asks for 43 to 128
# characters after base64url encoding; 32 bytes gives 43.
_VERIFIER_BYTES = 32
# A display name is a greeting, not a data field. Long enough for any real one,
# short enough that a provider cannot use it to grow the cookie.
_MAX_NAME_LENGTH = 120
# Tolerated clock difference between this server and the provider when the
# expiry of an ID token is checked. Without it a provider whose clock runs a
# minute behind ours would have every one of its tokens rejected.
_CLOCK_SKEW_S = 60


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def new_verifier() -> str:
    """A fresh PKCE code verifier."""

    return _b64url(secrets.token_bytes(_VERIFIER_BYTES))


def challenge_for(verifier: str) -> str:
    """The S256 code challenge for a verifier.

    S256 and not ``plain``: the challenge travels through the browser, and with
    ``plain`` it *is* the verifier, so anyone who saw the authorization request
    could redeem the code.
    """

    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


@dataclass(frozen=True)
class Provider:
    """The endpoints of one issuer, as its discovery document states them."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str | None
    auth_methods: tuple[str, ...]

    @property
    def uses_basic_auth(self) -> bool:
        """Whether the client authenticates with HTTP Basic at the token endpoint.

        ``client_secret_basic`` is the one method every OpenID provider must
        support, so it is also what a provider that lists no methods at all
        gets. Only a provider that says it takes ``client_secret_post`` and not
        Basic is talked to the other way.
        """

        return not self.auth_methods or "client_secret_basic" in self.auth_methods


@dataclass(frozen=True)
class Identity:
    """Who signed in. The whole of what this application learns about a person."""

    issuer: str
    subject: str
    name: str | None

    @property
    def account_key(self) -> str:
        """A stable, non-speaking identifier for this person at this issuer.

        Issuer and subject together are the pair OpenID Connect guarantees to be
        unique and never reassigned; hashing them keeps a provider's own
        identifier -- which at some providers is a mail address -- out of the
        API, the frontend and later the database, while staying the same value
        on every sign-in.
        """

        digest = hashlib.sha256(f"{self.issuer}\n{self.subject}".encode("utf-8")).hexdigest()
        return digest[:32]


def _text(value: Any) -> str | None:
    """A non-empty string, or nothing. Never truncated: this also reads URLs."""

    if not isinstance(value, str):
        return None
    return value.strip() or None


def _name(value: Any) -> str | None:
    """A display name: whitespace folded, and capped so a provider cannot
    grow the session cookie with it."""

    found = _text(value)
    return " ".join(found.split())[:_MAX_NAME_LENGTH] if found else None


def _display_name(claims: dict[str, Any]) -> str | None:
    """The friendliest name the claims offer, or nothing.

    Nothing is a legitimate answer: the ``profile`` scope is optional and a
    provider may grant none of it. The frontend then greets the person as
    „Angemeldet“, which is true and needs no invented name.
    """

    for key in ("name", "preferred_username", "nickname", "given_name"):
        found = _name(claims.get(key))
        if found:
            return found
    return None


class OidcService:
    """One configured OpenID provider, or none at all."""

    def __init__(self, settings: OidcSettings, app_settings: AppSettings) -> None:
        self.settings = settings
        self.app_settings = app_settings
        # The discovery document is the only thing worth caching here: it is
        # public, identical for every user, and asked for on every sign-in.
        # Nothing user-related may enter the shared disk cache.
        self.cache = DiskCache(
            app_settings.cache_dir / "oidc", ttl_s=settings.discovery_cache_ttl_s
        )

    @property
    def configured(self) -> bool:
        return self.settings.configured

    def end_session(self, response: Response) -> None:
        """Drop the session cookie on this response.

        Here rather than in a router, because the flags have to match the ones
        it was set with or the browser keeps the old cookie: a delete is only a
        `Set-Cookie` with an empty value, and the path, `httponly`, `samesite`
        and `secure` are part of the identity of the thing being replaced. Two
        endpoints end a session -- signing out and deleting the account -- and
        they must not each carry their own copy of that list.
        """

        response.delete_cookie(
            self.settings.cookie_name,
            path="/",
            httponly=True,
            samesite="lax",
            secure=self.settings.cookie_secure,
        )

    def session_identity(self, cookie: str | None) -> Identity | None:
        """Who this request belongs to, read from the session cookie.

        The one place a cookie becomes an identity, so ``/api/auth/me`` and
        every route that stores something for an account agree on what counts
        as signed in. Every way of failing answers the same: no provider
        configured, no cookie, a forged one, one signed with the previous
        secret and an expired one are all simply "nobody", which is the only
        thing a caller can act on.
        """

        if not self.configured:
            return None
        secret = self.settings.session_secret
        claims = session.read(cookie, secret.get_secret_value() if secret else "")
        if claims is None:
            return None
        issuer = _text(claims.get("iss"))
        subject = _text(claims.get("sub"))
        if not issuer or not subject:
            return None
        return Identity(issuer=issuer, subject=subject, name=_name(claims.get("name")))

    def require_configured(self) -> None:
        if not self.configured:
            raise NotConfiguredError(
                "Auf diesem Server ist keine Anmeldung eingerichtet. Die Anwendung "
                "lässt sich ohne Konto vollständig benutzen; die Grundstücke bleiben "
                "dann in diesem Browser."
            )

    def _reachable(self, url: str | None) -> str | None:
        """The same endpoint, as this backend can reach it.

        Only for the calls this server makes itself. The authorization URL is
        left alone -- it goes into the browser's address bar -- and so is the
        issuer, which is what an ID token is checked against. ``None`` passes
        through: ``userinfo_endpoint`` is optional and a provider that omits
        it must not turn this into an attribute error.
        """

        base = self.settings.internal_base_url.rstrip("/")
        public = self.settings.issuer.rstrip("/")
        if not url or not base or not public or not url.startswith(public):
            return url
        return base + url[len(public) :]

    async def provider(self) -> Provider:
        """The issuer's endpoints, from its discovery document."""

        self.require_configured()
        issuer = self.settings.issuer.rstrip("/")
        # The internal address belongs in the key: pointing this at another
        # provider while the issuer stays the same would otherwise keep
        # serving the first one's endpoints out of the cache.
        key = f"discovery:{issuer}:{self.settings.internal_base_url}"
        document = self.cache.get_json(key)
        if document is None:
            response = await request(
                "GET",
                self._reachable(f"{issuer}/.well-known/openid-configuration"),
                service=SERVICE_NAME,
                advice=ADVICE,
                timeout_s=self.settings.timeout_s,
                user_agent=self.app_settings.user_agent,
            )
            try:
                document = response.json()
            except ValueError as exc:
                raise UpstreamError(
                    f"{SERVICE_NAME} hat keine verwertbare Konfiguration geliefert. {ADVICE}"
                ) from exc
            if not isinstance(document, dict):
                raise UpstreamError(
                    f"{SERVICE_NAME} hat keine verwertbare Konfiguration geliefert. {ADVICE}"
                )
            self.cache.set_json(key, document)

        authorization = _text(document.get("authorization_endpoint"))
        token = _text(document.get("token_endpoint"))
        if not authorization or not token:
            raise UpstreamError(
                f"{SERVICE_NAME} nennt in seiner Konfiguration keinen Anmelde- oder "
                f"Token-Endpunkt. {ADVICE}"
            )
        methods = document.get("token_endpoint_auth_methods_supported")
        return Provider(
            # The issuer the document states, not the one configured: an ID
            # token's `iss` is checked against this, and section 3.1.3.7 asks
            # for the identifier "typically obtained during Discovery".
            issuer=_text(document.get("issuer")) or issuer,
            authorization_endpoint=authorization,
            token_endpoint=self._reachable(token),
            userinfo_endpoint=self._reachable(_text(document.get("userinfo_endpoint"))),
            auth_methods=tuple(m for m in methods if isinstance(m, str))
            if isinstance(methods, list)
            else (),
        )

    def authorization_url(
        self,
        provider: Provider,
        *,
        redirect_uri: str,
        state: str,
        nonce: str,
        challenge: str,
    ) -> str:
        """Where to send the browser to sign in."""

        query = urlencode({
            "response_type": "code",
            "client_id": self.settings.client_id,
            "redirect_uri": redirect_uri,
            "scope": self.settings.scopes,
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        })
        separator = "&" if "?" in provider.authorization_endpoint else "?"
        return f"{provider.authorization_endpoint}{separator}{query}"

    async def exchange(
        self,
        provider: Provider,
        *,
        code: str,
        verifier: str,
        redirect_uri: str,
        nonce: str,
    ) -> Identity:
        """Trade the authorization code for an identity.

        Everything the token endpoint hands back leaves this method again except
        issuer, subject and a display name: no access token, no refresh token
        and no ID token is kept beyond this request.
        """

        secret = self.settings.client_secret
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
            "client_id": self.settings.client_id,
        }
        kwargs: dict[str, Any] = {}
        if provider.uses_basic_auth:
            kwargs["auth"] = (self.settings.client_id, secret.get_secret_value() if secret else "")
        else:
            form["client_secret"] = secret.get_secret_value() if secret else ""

        response = await request(
            "POST",
            provider.token_endpoint,
            service=SERVICE_NAME,
            advice=ADVICE,
            timeout_s=self.settings.timeout_s,
            user_agent=self.app_settings.user_agent,
            data=form,
            headers={"Accept": "application/json"},
            **kwargs,
        )
        try:
            answer = response.json()
        except ValueError as exc:
            raise UpstreamError(
                f"{SERVICE_NAME} hat auf den Code-Tausch keine verwertbare Antwort "
                f"geliefert. {ADVICE}"
            ) from exc
        if not isinstance(answer, dict) or not isinstance(answer.get("id_token"), str):
            raise UpstreamError(
                f"{SERVICE_NAME} hat kein ID-Token geliefert. {ADVICE}"
            )

        claims = self._read_id_token(answer["id_token"], provider=provider, nonce=nonce)
        subject = _text(claims.get("sub"))
        if not subject:
            raise BadRequestError("Die Anmeldung nennt keine Kennung des Kontos.")

        name = _display_name(claims)
        if name is None:
            name = await self._userinfo_name(provider, answer.get("access_token"))
        return Identity(issuer=provider.issuer, subject=subject, name=name)

    def _read_id_token(self, token: str, *, provider: Provider, nonce: str) -> dict[str, Any]:
        """The ID token's claims, checked -- but its signature is not verified.

        That is a decision, not an omission, and OpenID Connect Core 1.0 makes
        it explicitly. Section 3.1.3.7 ("ID Token Validation"), item 6, reads
        verbatim:

            "If the ID Token is received via direct communication between the
            Client and the Token Endpoint (which it is in this flow), the TLS
            server validation MAY be used to validate the issuer in place of
            checking the token signature. The Client MUST validate the signature
            of all other ID Tokens according to [JWS] using the algorithm
            specified in the JWT alg Header Parameter. The Client MUST use the
            keys provided by the Issuer."

        This is that flow and only that flow: the token arrives in the body of a
        POST this backend itself makes to the token endpoint named by the
        issuer's own discovery document, over HTTPS with certificate validation
        left on (httpx's default). It never passes through the browser, so
        nothing between here and the provider could have substituted it. The
        exemption therefore applies, and the alternative -- fetching the JWKS,
        matching the kid, and adding pyjwt[crypto] plus a key-rotation cache --
        would verify a channel that is already authenticated.
        The moment an ID token arrives any other way (an implicit or hybrid
        response, or one forwarded from elsewhere), item 6 stops applying and
        the signature has to be checked properly. That is why no other way in
        exists here.

        Everything else in 3.1.3.7 that this flow can check is checked below:
        the issuer (item 2), the audience (item 3, with the azp rule from items
        4 and 5), the expiry (item 9) and the nonce (item 11).
        """

        parts = token.split(".")
        if len(parts) != 3:
            raise BadRequestError("Die Antwort des Anmeldedienstes war nicht lesbar.")
        try:
            claims = json.loads(_b64url_decode(parts[1]))
        except (ValueError, TypeError) as exc:
            raise BadRequestError("Die Antwort des Anmeldedienstes war nicht lesbar.") from exc
        if not isinstance(claims, dict):
            raise BadRequestError("Die Antwort des Anmeldedienstes war nicht lesbar.")

        # 3.1.3.7 item 2: the issuer identifier obtained during discovery MUST
        # exactly match the `iss` claim.
        if claims.get("iss") != provider.issuer:
            raise BadRequestError("Die Anmeldung stammt von einem anderen Anmeldedienst.")

        # Item 3: the audience must list this client, and no audience this
        # client does not trust -- which, with an `azp` naming us, is what a
        # second audience is (items 4 and 5).
        audience = claims.get("aud")
        audiences = audience if isinstance(audience, list) else [audience]
        if self.settings.client_id not in audiences:
            raise BadRequestError("Die Anmeldung war für eine andere Anwendung ausgestellt.")
        if len(audiences) > 1 and claims.get("azp") != self.settings.client_id:
            raise BadRequestError("Die Anmeldung war für eine andere Anwendung ausgestellt.")

        # Item 9: the current time must be before `exp`.
        expires_at = claims.get("exp")
        if not isinstance(expires_at, (int, float)):
            raise BadRequestError("Die Anmeldung nennt keine Gültigkeitsdauer.")
        if time.time() - _CLOCK_SKEW_S >= expires_at:
            raise BadRequestError("Die Anmeldung ist abgelaufen. Bitte erneut versuchen.")

        # Item 11: a nonce was sent, so a matching nonce claim must be present.
        if claims.get("nonce") != nonce:
            raise BadRequestError("Die Anmeldung ließ sich diesem Anmeldeversuch nicht zuordnen.")
        return claims

    async def _userinfo_name(self, provider: Provider, access_token: Any) -> str | None:
        """A display name from the userinfo endpoint, if the ID token had none.

        Best effort on purpose: the sign-in has already succeeded at this point,
        and a provider that answers nothing here costs a greeting, not a
        session. Only the name is read; no mail address is requested and none
        would be kept.
        """

        if not provider.userinfo_endpoint or not isinstance(access_token, str) or not access_token:
            return None
        try:
            response = await request(
                "GET",
                provider.userinfo_endpoint,
                service=SERVICE_NAME,
                advice=ADVICE,
                timeout_s=self.settings.timeout_s,
                user_agent=self.app_settings.user_agent,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
            claims = response.json()
        except (AppError, ValueError):
            logger.info("Userinfo brought no display name", exc_info=True)
            return None
        return _display_name(claims) if isinstance(claims, dict) else None
