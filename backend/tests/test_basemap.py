"""GET /api/basemap/... -- the vector basemap proxy.

The point of the proxy is that a browser can draw the map while reaching
nothing but this API, so these tests care about two things above all: that no
upstream host survives in what we hand out, and that a gzipped vector tile
arrives on the other side byte for byte.
"""

from __future__ import annotations

import gzip
import json

import httpx
import respx
from fastapi.testclient import TestClient

from .conftest import BASEMAP_URL, fixture_json, fixture_text

STYLE_URL = f"{BASEMAP_URL}/styles/liberty"
TILEJSON_URL = f"{BASEMAP_URL}/planet"
TILE_PATH = "planet/20260823_080002_pt/14/8798/5484.pbf"
TILE_URL = f"{BASEMAP_URL}/{TILE_PATH}"

# A vector tile is delivered gzipped; the bytes below stand in for one.
TILE_PLAIN = b"\x1a\x0bmocked vector tile payload" * 4
TILE_GZIPPED = gzip.compress(TILE_PLAIN)


def _style_answer() -> httpx.Response:
    return httpx.Response(
        200,
        content=fixture_text("openfreemap_style.json").encode("utf-8"),
        headers={"content-type": "application/json"},
    )


def _tile_answer() -> httpx.Response:
    return httpx.Response(
        200,
        content=TILE_GZIPPED,
        headers={
            "content-type": "application/vnd.mapbox-vector-tile",
            "content-encoding": "gzip",
        },
    )


@respx.mock
def test_style_carries_no_upstream_url_any_more(client: TestClient):
    respx.get(STYLE_URL).mock(return_value=_style_answer())

    answer = client.get("/api/basemap/style.json")

    assert answer.status_code == 200
    assert "tiles.openfreemap.org" not in answer.text
    body = answer.json()
    assert body["glyphs"] == "/api/basemap/fonts/{fontstack}/{range}.pbf"
    assert body["sources"]["openmaptiles"]["url"] == "/api/basemap/planet"
    assert body["sources"]["ne2_shaded"]["tiles"] == [
        "/api/basemap/natural_earth/ne2sr/{z}/{x}/{y}.png"
    ]
    assert answer.headers["x-cache"] == "MISS"


@respx.mock
def test_sprite_as_a_list_of_entries_is_rewritten_too(client: TestClient):
    # MapLibre allows both spellings of `sprite`; the array form is the one
    # that is easy to miss.
    respx.get(STYLE_URL).mock(return_value=_style_answer())

    sprite = client.get("/api/basemap/style.json").json()["sprite"]

    assert [entry["url"] for entry in sprite] == [
        "/api/basemap/sprites/ofm_f384/ofm",
        "/api/basemap/sprites/ofm_f384/extra",
    ]


@respx.mock
def test_style_is_served_from_the_cache_on_the_second_call(client: TestClient):
    route = respx.get(STYLE_URL).mock(return_value=_style_answer())

    client.get("/api/basemap/style.json")
    answer = client.get("/api/basemap/style.json")

    assert route.call_count == 1
    assert answer.headers["x-cache"] == "HIT"


@respx.mock
def test_tilejson_tile_urls_are_rewritten_but_the_attribution_is_not(client: TestClient):
    # The TileJSON behind `sources[*].url` names its tiles absolutely -- miss
    # this and the map leaves our origin on the very first tile.
    respx.get(TILEJSON_URL).mock(
        return_value=httpx.Response(
            200,
            json=fixture_json("openfreemap_tilejson.json"),
            headers={"content-type": "application/json"},
        )
    )

    body = client.get("/api/basemap/planet").json()

    assert body["tiles"] == ["/api/basemap/planet/20260823_080002_pt/{z}/{x}/{y}.pbf"]
    # Links inside prose stay links: they are for the user, not for MapLibre.
    assert "https://openfreemap.org" in body["attribution"]
    assert body["description"] == "https://openfreemap.org"


@respx.mock
def test_vector_tile_keeps_its_compression_and_content_type(client: TestClient):
    respx.get(TILE_URL).mock(return_value=_tile_answer())

    answer = client.get(f"/api/basemap/{TILE_PATH}")

    assert answer.status_code == 200
    assert answer.headers["content-type"] == "application/vnd.mapbox-vector-tile"
    assert answer.headers["content-encoding"] == "gzip"
    # httpx decompresses on the way in, so equality here proves the proxy
    # passed the gzip stream through instead of decoding it a second time.
    assert answer.content == TILE_PLAIN


@respx.mock
def test_second_request_for_the_same_tile_comes_from_the_disk_cache(client: TestClient):
    route = respx.get(TILE_URL).mock(return_value=_tile_answer())

    first = client.get(f"/api/basemap/{TILE_PATH}")
    second = client.get(f"/api/basemap/{TILE_PATH}")

    assert route.call_count == 1
    assert first.headers["x-cache"] == "MISS"
    assert second.headers["x-cache"] == "HIT"
    assert second.content == first.content
    assert second.headers["content-encoding"] == "gzip"


@respx.mock
def test_glyph_range_with_a_space_in_the_font_stack(client: TestClient):
    route = respx.get(f"{BASEMAP_URL}/fonts/Noto%20Sans%20Regular/0-255.pbf").mock(
        return_value=httpx.Response(
            200, content=b"glyphs", headers={"content-type": "application/x-protobuf"}
        )
    )

    answer = client.get("/api/basemap/fonts/Noto%20Sans%20Regular/0-255.pbf")

    assert answer.status_code == 200
    assert route.called
    assert answer.headers["content-type"] == "application/x-protobuf"


@respx.mock
def test_sprite_sheet_travels_as_an_image(client: TestClient):
    respx.get(f"{BASEMAP_URL}/sprites/ofm_f384/ofm@2x.png").mock(
        return_value=httpx.Response(
            200, content=b"\x89PNG\r\n\x1a\n", headers={"content-type": "image/png"}
        )
    )

    answer = client.get("/api/basemap/sprites/ofm_f384/ofm@2x.png")

    assert answer.status_code == 200
    assert answer.headers["content-type"] == "image/png"
    assert answer.content.startswith(b"\x89PNG")


def test_an_absolute_target_is_refused(client: TestClient):
    answer = client.get("/api/basemap/https://boese.example.org/a")

    assert answer.status_code == 400
    assert "Kartendienst" in answer.json()["detail"]


def test_a_traversal_attempt_is_refused(client: TestClient):
    # Sent unencoded a client would collapse the dot segments itself, so the
    # encoded form is the one that reaches the route.
    answer = client.get("/api/basemap/planet/..%2f..%2fetc%2fpasswd")

    assert answer.status_code == 400
    assert "ungültig" in answer.json()["detail"]


def test_a_protocol_relative_target_is_refused(client: TestClient):
    answer = client.get("/api/basemap//boese.example.org/a")

    assert answer.status_code == 400


@respx.mock
def test_an_unreachable_upstream_is_a_502_with_advice(client: TestClient):
    respx.get(STYLE_URL).mock(side_effect=httpx.ConnectError("kein Netz"))

    answer = client.get("/api/basemap/style.json")

    assert answer.status_code == 502
    detail = answer.json()["detail"]
    assert "nicht erreichbar" in detail
    assert "Luftbild" in detail  # says what still works
    assert "Traceback" not in answer.text


@respx.mock
def test_a_slow_upstream_is_a_504(client: TestClient):
    respx.get(TILE_URL).mock(side_effect=httpx.ReadTimeout("langsam"))

    answer = client.get(f"/api/basemap/{TILE_PATH}")

    assert answer.status_code == 504
    assert "rechtzeitig" in answer.json()["detail"]


@respx.mock
def test_a_missing_tile_is_a_404_in_german(client: TestClient):
    respx.get(TILE_URL).mock(return_value=httpx.Response(404))

    answer = client.get(f"/api/basemap/{TILE_PATH}")

    assert answer.status_code == 404
    assert "Kachel" in answer.json()["detail"]


@respx.mock
def test_something_that_is_not_a_style_is_a_502(client: TestClient):
    respx.get(STYLE_URL).mock(
        return_value=httpx.Response(
            200, json={"nichts": "davon"}, headers={"content-type": "application/json"}
        )
    )

    answer = client.get("/api/basemap/style.json")

    assert answer.status_code == 502
    assert "Stildokument" in answer.json()["detail"]


@respx.mock
def test_a_self_hosted_upstream_still_rewrites_openfreemap_urls(
    client: TestClient, monkeypatch
):
    # A mirror serves the OpenFreeMap style unchanged; those URLs have to be
    # caught as well, or the browser leaves our origin after all.
    from app.deps import reset_services

    monkeypatch.setenv("BASEMAP_UPSTREAM_URL", "https://karten.example.org")
    reset_services()
    respx.get("https://karten.example.org/styles/liberty").mock(
        return_value=_style_answer()
    )

    answer = client.get("/api/basemap/style.json")

    assert answer.status_code == 200
    assert "openfreemap.org" not in answer.text
    assert json.loads(answer.text)["sources"]["openmaptiles"]["url"] == "/api/basemap/planet"


@respx.mock
def test_a_redirect_off_the_upstream_is_refused(client: TestClient):
    # The path comes from the browser; an open redirect on the upstream must
    # not turn this proxy into one.
    respx.get(TILE_URL).mock(
        return_value=httpx.Response(302, headers={"location": "https://boese.example.org/x"})
    )
    respx.get("https://boese.example.org/x").mock(
        return_value=httpx.Response(200, content=b"beute", headers={"content-type": "text/plain"})
    )

    answer = client.get(f"/api/basemap/{TILE_PATH}")

    assert answer.status_code == 502
    assert "fremden Server" in answer.json()["detail"]
    assert b"beute" not in answer.content
