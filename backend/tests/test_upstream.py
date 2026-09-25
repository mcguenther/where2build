"""The shared upstream client: one per event loop, and it survives its connections.

A client per request built an SSL context on the event loop every time, which
stalled every other request while a block of tiles was fetched. The pooled one
must still recover from a connection the server has dropped -- the failure the
old one-shot clients could never have.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app import upstream
from app.errors import UpstreamError
from app.upstream import request, shared_client

pytestmark = pytest.mark.anyio

_ANSWER = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: text/plain\r\n"
    b"Content-Length: 2\r\n"
    b"\r\n"
    b"ok"
)


async def _serve(handle) -> tuple[asyncio.AbstractServer, str]:
    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, f"http://127.0.0.1:{port}/"


async def _read_request(reader: asyncio.StreamReader) -> bool:
    """Read one request head; False once the client has gone."""

    try:
        await reader.readuntil(b"\r\n\r\n")
    except (asyncio.IncompleteReadError, ConnectionError):
        return False
    return True


async def _get(url: str) -> httpx.Response:
    return await request(
        "GET", url, service="Testdienst", timeout_s=5, user_agent="w2b-test", advice="Später."
    )


async def test_one_client_serves_every_request_on_a_loop():
    first = shared_client()
    assert shared_client() is first

    await upstream.close_shared_client()
    assert first.is_closed
    # Closed is not final: the next request makes a new one.
    assert shared_client() is not first
    await upstream.close_shared_client()


@respx.mock
async def test_timeout_and_user_agent_still_travel_with_each_request():
    route = respx.get("https://dienst.example.org/a").mock(return_value=httpx.Response(200))

    await request(
        "GET",
        "https://dienst.example.org/a",
        service="Testdienst",
        timeout_s=7,
        user_agent="w2b-eins",
    )
    await request(
        "GET",
        "https://dienst.example.org/a",
        service="Testdienst",
        timeout_s=3,
        user_agent="w2b-zwei",
    )

    first, second = (call.request for call in route.calls)
    assert first.headers["user-agent"] == "w2b-eins"
    assert second.headers["user-agent"] == "w2b-zwei"
    assert first.extensions["timeout"]["read"] == 7
    assert second.extensions["timeout"]["read"] == 3


async def test_a_connection_the_server_closed_while_idle_is_not_reused():
    """The server hangs up after each answer without saying so in a header."""

    connections = 0

    async def handle(reader, writer):
        nonlocal connections
        connections += 1
        if await _read_request(reader):
            writer.write(_ANSWER)
            await writer.drain()
        writer.close()

    server, url = await _serve(handle)
    async with server:
        for _ in range(3):
            assert (await _get(url)).text == "ok"
            # Time for the FIN to arrive; without it the retry would catch the
            # reuse instead of the pool refusing it, and this would test that.
            await asyncio.sleep(0.05)
    await upstream.close_shared_client()

    assert connections == 3


async def test_a_connection_that_dies_on_reuse_is_retried_on_a_new_one():
    """Keep-alive honoured once, then the reused connection drops the request.

    That is what a pooled connection to a restarted server looks like: idle and
    quiet in the pool, dead the moment it is written to. The pool cannot see it
    coming, so the retry in ``request`` is what has to catch it.
    """

    connections = 0

    async def handle(reader, writer):
        nonlocal connections
        connections += 1
        if await _read_request(reader):
            writer.write(_ANSWER)
            await writer.drain()
        # The second request on this connection is read and never answered.
        await _read_request(reader)
        writer.close()

    server, url = await _serve(handle)
    async with server:
        assert (await _get(url)).text == "ok"
        assert (await _get(url)).text == "ok"
    await upstream.close_shared_client()

    assert connections == 2


async def test_a_server_that_is_gone_is_still_reported_in_german():
    server, url = await _serve(lambda reader, writer: writer.close())
    server.close()
    await server.wait_closed()

    with pytest.raises(UpstreamError, match="Testdienst ist derzeit nicht erreichbar. Später."):
        await _get(url)
    await upstream.close_shared_client()


def test_the_app_closes_the_client_when_it_shuts_down():
    from app.main import create_app

    with TestClient(create_app()) as client:
        opened = client.portal.call(shared_client)
        assert not opened.is_closed

    assert opened.is_closed
