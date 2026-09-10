"""/api/auth/... -- signing in through an OpenID provider, backend-for-frontend.

Two properties matter more than the rest here and are checked from several
sides: that a deployment *without* a provider is a complete, working
deployment, and that no token ever reaches the browser.

The provider is invented (``https://auth.example.org``). Every request to it is
stubbed with respx, as everywhere else in this suite.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import respx
from fastapi.testclient import TestClient

from app import session
from app.deps import reset_services

from .conftest import OIDC_ISSUER

CLIENT_ID = "where2build"
DISCOVERY_URL = f"{OIDC_ISSUER}/.well-known/openid-configuration"
AUTHORIZE_URL = f"{OIDC_ISSUER}/anmelden"
TOKEN_URL = f"{OIDC_ISSUER}/token"
USERINFO_URL = f"{OIDC_ISSUER}/userinfo"

DISCOVERY = {
    "issuer": OIDC_ISSUER,
    "authorization_endpoint": AUTHORIZE_URL,
    "token_endpoint": TOKEN_URL,
    "userinfo_endpoint": USERINFO_URL,
    "jwks_uri": f"{OIDC_ISSUER}/jwks",
    "response_types_supported": ["code"],
    "subject_types_supported": ["public"],
    "id_token_signing_alg_values_supported": ["RS256"],
    "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
    "code_challenge_methods_supported": ["S256"],
}


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _id_token(**claims) -> str:
    """A JWT whose signature is not checked -- see OidcService._read_id_token.

    The token arrives over a direct TLS connection to the token endpoint, which
    OpenID Connect Core 1.0 § 3.1.3.7 item 6 lets stand in for the signature.
    So the third part is a placeholder here, exactly as the production code
    treats it.
    """

    payload = {
        "iss": OIDC_ISSUER,
        "aud": CLIENT_ID,
        "sub": "8f1c-4711",
        "name": "Erika Musterfrau",
        "exp": int(time.time()) + 300,
        "iat": int(time.time()),
        **claims,
    }
    # A claim passed as None is one this provider did not send at all.
    payload = {key: value for key, value in payload.items() if value is not None}
    header = _b64(json.dumps({"alg": "RS256", "typ": "JWT", "kid": "test"}).encode())
    return f"{header}.{_b64(json.dumps(payload).encode())}.{_b64(b'nicht-geprueft')}"


def _discovery_route():
    return respx.get(DISCOVERY_URL).mock(return_value=httpx.Response(200, json=DISCOVERY))


def _token_route(id_token: str, **extra):
    return respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "zugang-nur-fuer-diesen-augenblick",
                "refresh_token": "erneuerung",
                "token_type": "Bearer",
                "expires_in": 300,
                "id_token": id_token,
                **extra,
            },
        )
    )


def _begin(client: TestClient, ziel: str = "/") -> dict[str, str]:
    """Run /login and hand back what the provider would have received."""

    answer = client.get("/api/auth/login", params={"ziel": ziel}, follow_redirects=False)
    assert answer.status_code in (302, 307)
    query = parse_qs(urlsplit(answer.headers["location"]).query)
    return {key: value[0] for key, value in query.items()}


# --------------------------------------------------------------------------
# Without a provider the app is complete
# --------------------------------------------------------------------------


def test_me_says_no_sign_in_is_set_up_here(client: TestClient):
    answer = client.get("/api/auth/me")

    assert answer.status_code == 200
    assert answer.json() == {
        "eingerichtet": False,
        "angemeldet": False,
        "name": None,
        "kennung": None,
    }


def test_login_without_a_provider_answers_503_in_german(client: TestClient):
    answer = client.get("/api/auth/login", follow_redirects=False)

    assert answer.status_code == 503
    detail = answer.json()["detail"]
    assert "keine Anmeldung eingerichtet" in detail
    # And it says the app still works, because it does.
    assert "ohne Konto" in detail


def test_health_names_the_missing_variables(client: TestClient):
    dienste = {entry["name"]: entry for entry in client.get("/api/health").json()["dienste"]}

    assert dienste["anmeldung"]["konfiguriert"] is False
    assert "OIDC_ISSUER" in dienste["anmeldung"]["hinweis"]
    assert "ohne Konto" in dienste["anmeldung"]["hinweis"]


def test_health_reports_a_configured_provider(oidc, client: TestClient):
    dienste = {entry["name"]: entry for entry in client.get("/api/health").json()["dienste"]}

    assert dienste["anmeldung"]["konfiguriert"] is True
    assert dienste["anmeldung"]["endpunkt"] == OIDC_ISSUER
    assert "PKCE" in dienste["anmeldung"]["hinweis"]


def test_logout_without_a_provider_is_still_a_204(client: TestClient):
    assert client.post("/api/auth/logout").status_code == 204


# --------------------------------------------------------------------------
# Beginning a sign-in
# --------------------------------------------------------------------------


@respx.mock
def test_login_redirects_to_the_authorization_endpoint(oidc, client: TestClient):
    _discovery_route()

    answer = client.get("/api/auth/login", follow_redirects=False)

    assert answer.status_code == 307
    location = answer.headers["location"]
    assert location.startswith(AUTHORIZE_URL)
    query = {key: value[0] for key, value in parse_qs(urlsplit(location).query).items()}
    assert query["response_type"] == "code"
    assert query["client_id"] == CLIENT_ID
    assert query["redirect_uri"] == "http://testserver/api/auth/callback"
    assert query["scope"] == "openid profile"
    assert query["code_challenge_method"] == "S256"
    assert query["state"] and query["nonce"] and query["code_challenge"]
    # Not the verifier itself: with `plain` the challenge would be the secret.
    assert len(query["code_challenge"]) == 43


@respx.mock
def test_login_keeps_the_handshake_in_a_signed_httponly_cookie(oidc, client: TestClient):
    _discovery_route()

    answer = client.get("/api/auth/login", follow_redirects=False)

    cookie = answer.headers["set-cookie"]
    assert cookie.startswith("w2b_anmeldung=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie.lower().replace("samesite=lax", "SameSite=lax")
    assert "Path=/api/auth" in cookie
    # The verifier is in there, signed, and the browser cannot reach it.
    assert "Max-Age=600" in cookie


@respx.mock
def test_the_discovery_document_is_fetched_once_and_then_cached(oidc, client: TestClient):
    route = _discovery_route()

    client.get("/api/auth/login", follow_redirects=False)
    client.get("/api/auth/login", follow_redirects=False)

    assert route.call_count == 1


@respx.mock
def test_a_foreign_target_is_bent_back_to_the_start_page(oidc, client: TestClient):
    """An open redirect would turn this endpoint into a phishing hop."""

    _discovery_route()
    handshake = _begin(client, ziel="https://example.org")
    _token_route(_id_token(nonce=handshake["nonce"]))

    answer = client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": handshake["state"]},
        follow_redirects=False,
    )

    assert answer.headers["location"] == "/"


@respx.mock
def test_a_protocol_relative_target_is_bent_back_too(oidc, client: TestClient):
    _discovery_route()
    handshake = _begin(client, ziel="//example.org/übernahme")
    _token_route(_id_token(nonce=handshake["nonce"]))

    answer = client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": handshake["state"]},
        follow_redirects=False,
    )

    assert answer.headers["location"] == "/"


@respx.mock
def test_an_own_path_survives_the_round_trip(oidc, client: TestClient):
    _discovery_route()
    handshake = _begin(client, ziel="/grundstuecke/17")
    _token_route(_id_token(nonce=handshake["nonce"]))

    answer = client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": handshake["state"]},
        follow_redirects=False,
    )

    assert answer.headers["location"] == "/grundstuecke/17"


# --------------------------------------------------------------------------
# Coming back
# --------------------------------------------------------------------------


@respx.mock
def test_a_wrong_state_fails_the_sign_in_and_starts_no_session(oidc, client: TestClient):
    _discovery_route()
    token = _token_route(_id_token())
    _begin(client)

    answer = client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": "nicht-der-begonnene-versuch"},
        follow_redirects=False,
    )

    assert answer.headers["location"] == "/?anmeldung=fehlgeschlagen"
    assert token.call_count == 0
    assert client.get("/api/auth/me").json()["angemeldet"] is False


@respx.mock
def test_a_callback_without_a_begun_sign_in_fails(oidc, client: TestClient):
    _discovery_route()

    answer = client.get(
        "/api/auth/callback", params={"code": "abc", "state": "x"}, follow_redirects=False
    )

    assert answer.headers["location"] == "/?anmeldung=fehlgeschlagen"
    assert client.get("/api/auth/me").json()["angemeldet"] is False


@respx.mock
def test_an_error_from_the_provider_fails_quietly(oidc, client: TestClient):
    _discovery_route()
    handshake = _begin(client)

    answer = client.get(
        "/api/auth/callback",
        params={"error": "access_denied", "state": handshake["state"]},
        follow_redirects=False,
    )

    assert answer.headers["location"] == "/?anmeldung=fehlgeschlagen"
    # Nothing about the provider's complaint travels in the URL.
    assert "access_denied" not in answer.headers["location"]


@respx.mock
def test_a_successful_callback_signs_the_person_in(oidc, client: TestClient):
    _discovery_route()
    handshake = _begin(client)
    token = _token_route(_id_token(nonce=handshake["nonce"], name="Erika Musterfrau"))

    answer = client.get(
        "/api/auth/callback",
        params={"code": "der-code", "state": handshake["state"]},
        follow_redirects=False,
    )

    assert answer.status_code == 303
    assert answer.headers["location"] == "/"
    cookie = answer.headers["set-cookie"]
    assert cookie.startswith("w2b_sitzung=")
    assert "HttpOnly" in cookie
    assert "Path=/" in cookie

    body = client.get("/api/auth/me").json()
    assert body == {
        "eingerichtet": True,
        "angemeldet": True,
        "name": "Erika Musterfrau",
        "kennung": body["kennung"],
    }
    assert len(body["kennung"]) == 32
    # Non-speaking: neither the subject nor the issuer is readable from it.
    assert "8f1c-4711" not in body["kennung"]
    assert token.call_count == 1


@respx.mock
def test_the_code_is_exchanged_with_the_pkce_verifier_that_made_the_challenge(
    oidc, client: TestClient
):
    _discovery_route()
    handshake = _begin(client)
    token = _token_route(_id_token(nonce=handshake["nonce"]))

    client.get(
        "/api/auth/callback",
        params={"code": "der-code", "state": handshake["state"]},
        follow_redirects=False,
    )

    sent = {k: v[0] for k, v in parse_qs(token.calls.last.request.content.decode()).items()}
    assert sent["grant_type"] == "authorization_code"
    assert sent["code"] == "der-code"
    assert sent["redirect_uri"] == "http://testserver/api/auth/callback"
    challenge = _b64(hashlib.sha256(sent["code_verifier"].encode("ascii")).digest())
    assert challenge == handshake["code_challenge"]
    # client_secret_basic is what this provider lists first, so the secret does
    # not travel in the body.
    assert "client_secret" not in sent
    assert token.calls.last.request.headers["authorization"].startswith("Basic ")


@respx.mock
def test_no_token_ever_reaches_the_browser(oidc, client: TestClient):
    _discovery_route()
    handshake = _begin(client)
    _token_route(_id_token(nonce=handshake["nonce"]))

    answer = client.get(
        "/api/auth/callback",
        params={"code": "der-code", "state": handshake["state"]},
        follow_redirects=False,
    )

    everything = answer.headers["set-cookie"] + str(answer.headers.get("location"))
    assert "zugang-nur-fuer-diesen-augenblick" not in everything
    assert "erneuerung" not in everything
    # The cookie carries issuer, subject, name and an expiry -- nothing else.
    payload = json.loads(
        base64.urlsafe_b64decode(
            client.cookies["w2b_sitzung"].split(".")[0] + "=="
        ).decode("utf-8")
    )
    assert set(payload) == {"iss", "sub", "name", "exp"}


@respx.mock
def test_a_nonce_that_does_not_match_is_refused(oidc, client: TestClient):
    _discovery_route()
    handshake = _begin(client)
    _token_route(_id_token(nonce="ein-anderer-anmeldeversuch"))

    answer = client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": handshake["state"]},
        follow_redirects=False,
    )

    assert answer.headers["location"] == "/?anmeldung=fehlgeschlagen"
    assert client.get("/api/auth/me").json()["angemeldet"] is False


@respx.mock
def test_an_id_token_for_another_client_is_refused(oidc, client: TestClient):
    _discovery_route()
    handshake = _begin(client)
    _token_route(_id_token(nonce=handshake["nonce"], aud="eine-andere-anwendung"))

    answer = client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": handshake["state"]},
        follow_redirects=False,
    )

    assert answer.headers["location"] == "/?anmeldung=fehlgeschlagen"
    assert client.get("/api/auth/me").json()["angemeldet"] is False


@respx.mock
def test_an_id_token_from_another_issuer_is_refused(oidc, client: TestClient):
    _discovery_route()
    handshake = _begin(client)
    _token_route(_id_token(nonce=handshake["nonce"], iss="https://woanders.example.org"))

    answer = client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": handshake["state"]},
        follow_redirects=False,
    )

    assert answer.headers["location"] == "/?anmeldung=fehlgeschlagen"


@respx.mock
def test_an_expired_id_token_is_refused(oidc, client: TestClient):
    _discovery_route()
    handshake = _begin(client)
    _token_route(_id_token(nonce=handshake["nonce"], exp=int(time.time()) - 3600))

    answer = client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": handshake["state"]},
        follow_redirects=False,
    )

    assert answer.headers["location"] == "/?anmeldung=fehlgeschlagen"


@respx.mock
def test_a_token_endpoint_that_fails_does_not_sign_anybody_in(oidc, client: TestClient):
    _discovery_route()
    handshake = _begin(client)
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(400, json={"error": "invalid_grant"}))

    answer = client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": handshake["state"]},
        follow_redirects=False,
    )

    assert answer.headers["location"] == "/?anmeldung=fehlgeschlagen"
    assert client.get("/api/auth/me").json()["angemeldet"] is False


@respx.mock
def test_a_provider_without_a_name_claim_leaves_the_name_empty(oidc, client: TestClient):
    """No invented greeting: the frontend says „Angemeldet“ and that is true."""

    _discovery_route()
    handshake = _begin(client)
    _token_route(_id_token(nonce=handshake["nonce"], name=None))
    respx.get(USERINFO_URL).mock(return_value=httpx.Response(200, json={"sub": "8f1c-4711"}))

    client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": handshake["state"]},
        follow_redirects=False,
    )

    body = client.get("/api/auth/me").json()
    assert body["angemeldet"] is True
    assert body["name"] is None


@respx.mock
def test_the_display_name_may_come_from_userinfo(oidc, client: TestClient):
    _discovery_route()
    handshake = _begin(client)
    _token_route(_id_token(nonce=handshake["nonce"], name=None))
    respx.get(USERINFO_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "sub": "8f1c-4711",
                "preferred_username": "erika",
                "email": "erika@post.example.net",
            },
        )
    )

    client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": handshake["state"]},
        follow_redirects=False,
    )

    assert client.get("/api/auth/me").json()["name"] == "erika"
    # The mail address was answered and is not kept anywhere.
    payload = base64.urlsafe_b64decode(client.cookies["w2b_sitzung"].split(".")[0] + "==")
    assert b"post.example.net" not in payload


# --------------------------------------------------------------------------
# Ending it
# --------------------------------------------------------------------------


@respx.mock
def test_logout_deletes_the_session(oidc, client: TestClient):
    _discovery_route()
    handshake = _begin(client)
    _token_route(_id_token(nonce=handshake["nonce"], name="Erika Musterfrau"))
    client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": handshake["state"]},
        follow_redirects=False,
    )
    assert client.get("/api/auth/me").json()["angemeldet"] is True

    answer = client.post("/api/auth/logout")

    assert answer.status_code == 204
    assert "w2b_sitzung=" in answer.headers["set-cookie"]
    assert client.get("/api/auth/me").json()["angemeldet"] is False


@respx.mock
def test_a_forged_session_cookie_is_not_a_session(oidc, client: TestClient):
    _discovery_route()
    client.cookies.set("w2b_sitzung", "eyJzdWIiOiAiZnJlbWQifQ.gefaelscht")

    assert client.get("/api/auth/me").json()["angemeldet"] is False


# --------------------------------------------------------------------------
# The cookie itself
# --------------------------------------------------------------------------


@respx.mock
def test_the_session_cookie_is_secure_where_the_deployment_says_so(
    oidc, client: TestClient, monkeypatch
):
    """The test client speaks http, so the suite otherwise switches this off."""

    monkeypatch.setenv("OIDC_COOKIE_SECURE", "true")
    reset_services()
    _discovery_route()
    handshake = _begin(client)
    _token_route(_id_token(nonce=handshake["nonce"]))

    answer = client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": handshake["state"]},
        follow_redirects=False,
    )

    assert "Secure" in answer.headers["set-cookie"]


def test_a_changed_payload_invalidates_the_signature():
    secret = "sitzungsschluessel-fuer-den-test"
    cookie = session.sign({"iss": OIDC_ISSUER, "sub": "8f1c-4711"}, secret, ttl_s=60)
    payload, _, signature = cookie.rpartition(".")
    forged = base64.urlsafe_b64encode(
        json.dumps({"iss": OIDC_ISSUER, "sub": "jemand-anderes", "exp": 9999999999}).encode()
    ).decode().rstrip("=")

    assert session.read(cookie, secret) is not None
    assert session.read(f"{forged}.{signature}", secret) is None
    assert session.read(cookie, "ein-anderer-schluessel") is None
    # A payload that lost its signature is not a session either.
    assert session.read(payload, secret) is None


def test_an_expired_cookie_is_no_longer_a_session():
    """The deadline is inside the signature: a browser may keep sending a
    cookie past its own Max-Age, and only the server's copy can be trusted."""

    secret = "sitzungsschluessel-fuer-den-test"
    cookie = session.sign({"sub": "8f1c-4711"}, secret, ttl_s=3600)

    assert session.read(cookie, secret) is not None
    assert session.read(cookie, secret, now=time.time() + 3601) is None


@respx.mock
def test_nothing_about_a_sign_in_may_be_cached(oidc, client: TestClient):
    """A cached /me hands one person's name to the next; a cached redirect
    hands out its Set-Cookie with it."""

    _discovery_route()

    assert client.get("/api/auth/me").headers["cache-control"] == "no-store"
    login = client.get("/api/auth/login", follow_redirects=False)
    assert login.headers["cache-control"] == "no-store"


# --------------------------------------------------------------------------
# The provider on two addresses: one for the browser, one for this server
# --------------------------------------------------------------------------

INTERNAL = "http://auth:5556"


@respx.mock
def test_the_backend_may_reach_the_provider_at_another_address(
    oidc, client: TestClient, monkeypatch
):
    """An issuer is one string doing two jobs, and in a container they part.

    The browser knows the provider as `http://localhost:8080/dex`; from inside
    the backend's container that address is the backend itself. So the
    discovery document and the token endpoint are fetched at
    `OIDC_INTERNAL_BASE_URL`, while the address the browser is *sent* to and
    the `iss` an ID token is checked against stay public. Get it wrong and
    sign-in fails at the token exchange, after the password was already typed.
    """

    monkeypatch.setenv("OIDC_INTERNAL_BASE_URL", INTERNAL)
    reset_services()
    inside_discovery = respx.get(f"{INTERNAL}/.well-known/openid-configuration").mock(
        return_value=httpx.Response(200, json=DISCOVERY)
    )
    # The public addresses must not be called at all.
    outside_discovery = _discovery_route()
    outside_token = _token_route(_id_token())

    handshake = _begin(client, "/grundstuecke")
    inside_token = respx.post(f"{INTERNAL}/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "zugang",
                "token_type": "Bearer",
                "expires_in": 300,
                "id_token": _id_token(nonce=handshake["nonce"]),
            },
        )
    )
    answer = client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": handshake["state"]},
        follow_redirects=False,
    )

    assert answer.status_code in (302, 303, 307)
    assert inside_discovery.called and inside_token.called
    assert not outside_discovery.called and not outside_token.called
    # And somebody is signed in, rather than sent to the failure page.
    assert client.get("/api/auth/me").json()["angemeldet"] is True


@respx.mock
def test_the_issuer_that_is_checked_is_still_the_public_one(
    oidc, client: TestClient, monkeypatch
):
    """The internal address is a route, not an identity.

    An ID token says `iss: https://auth.example.org` however it was fetched, so
    believing the internal address here would reject every token the provider
    ever issues. The nonce is the correct one on purpose: the issuer has to be
    the only thing wrong, or this passes without testing anything.
    """

    monkeypatch.setenv("OIDC_INTERNAL_BASE_URL", INTERNAL)
    reset_services()
    respx.get(f"{INTERNAL}/.well-known/openid-configuration").mock(
        return_value=httpx.Response(200, json=DISCOVERY)
    )

    handshake = _begin(client)
    respx.post(f"{INTERNAL}/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "zugang",
                "token_type": "Bearer",
                "expires_in": 300,
                "id_token": _id_token(nonce=handshake["nonce"], iss=INTERNAL),
            },
        )
    )
    client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": handshake["state"]},
        follow_redirects=False,
    )

    assert client.get("/api/auth/me").json()["angemeldet"] is False


@respx.mock
def test_without_the_internal_address_nothing_changes(oidc, client: TestClient):
    # The default is empty, and then every call goes to the issuer itself.
    discovery = _discovery_route()

    handshake = _begin(client)
    token = _token_route(_id_token(nonce=handshake["nonce"]))
    client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": handshake["state"]},
        follow_redirects=False,
    )

    assert discovery.called and token.called
    assert client.get("/api/auth/me").json()["angemeldet"] is True


@respx.mock
def test_a_provider_without_userinfo_still_works_at_the_other_address(
    oidc, client: TestClient, monkeypatch
):
    """`userinfo_endpoint` is optional, and rewriting it must survive that.

    Dex advertises one, several providers do not, and the rewrite reached for
    `.startswith` on whatever the document held. With the internal address set
    and the key missing that is an attribute error inside discovery -- i.e.
    the whole sign-in falls over on a provider that is entirely within spec.
    """

    monkeypatch.setenv("OIDC_INTERNAL_BASE_URL", INTERNAL)
    reset_services()
    without_userinfo = {k: v for k, v in DISCOVERY.items() if k != "userinfo_endpoint"}
    respx.get(f"{INTERNAL}/.well-known/openid-configuration").mock(
        return_value=httpx.Response(200, json=without_userinfo)
    )

    handshake = _begin(client)
    respx.post(f"{INTERNAL}/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "zugang",
                "token_type": "Bearer",
                "expires_in": 300,
                "id_token": _id_token(nonce=handshake["nonce"]),
            },
        )
    )
    client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": handshake["state"]},
        follow_redirects=False,
    )

    assert client.get("/api/auth/me").json()["angemeldet"] is True
