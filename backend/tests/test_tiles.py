"""GET /api/tiles/{layer}/{z}/{x}/{y}.png -- the WMS proxy and its disk cache."""

from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from app import geo
from app.deps import tile_service

from .conftest import DOP_URL

# Smallest valid PNG, enough to prove the bytes travel through unchanged.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6360000002000100ffff0300000600"
    "05fe02fe0000000049454e44ae426082"
)


def _wms_answer() -> httpx.Response:
    return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})


@respx.mock
def test_tile_is_proxied_from_the_wms(client: TestClient):
    route = respx.get(DOP_URL).mock(return_value=_wms_answer())

    answer = client.get("/api/tiles/dop/15/17540/10986.png")

    assert answer.status_code == 200
    assert answer.headers["content-type"] == "image/png"
    assert answer.content == PNG
    assert answer.headers["x-cache"] == "MISS"
    assert "GeoSN" in answer.headers["x-attribution"]

    params = route.calls[0].request.url.params
    assert params["REQUEST"] == "GetMap"
    assert params["LAYERS"] == "sn_dop_020"
    assert params["WIDTH"] == params["HEIGHT"] == "256"
    assert params["CRS"] == "EPSG:3857"


@respx.mock
def test_second_request_for_the_same_tile_comes_from_the_disk_cache(client: TestClient):
    route = respx.get(DOP_URL).mock(return_value=_wms_answer())

    client.get("/api/tiles/dop/15/17540/10986.png")
    answer = client.get("/api/tiles/dop/15/17540/10986.png")

    assert route.call_count == 1
    assert answer.headers["x-cache"] == "HIT"


def test_unknown_layer_is_a_400(client: TestClient):
    answer = client.get("/api/tiles/katasterX/15/17540/10986.png")

    assert answer.status_code == 400
    assert "dop" in answer.json()["detail"]


def test_tile_outside_the_zoom_level_is_a_400(client: TestClient):
    assert client.get("/api/tiles/dop/2/99/99.png").status_code == 400


def test_negative_tile_index_is_a_422(client: TestClient):
    assert client.get("/api/tiles/dop/15/-1/10986.png").status_code == 422


@respx.mock
def test_a_wms_error_document_is_a_502(client: TestClient):
    # WMS reports errors as XML with HTTP 200 -- that is not a tile.
    respx.get(DOP_URL).mock(
        return_value=httpx.Response(
            200,
            text="<ServiceExceptionReport/>",
            headers={"content-type": "application/vnd.ogc.se_xml"},
        )
    )

    answer = client.get("/api/tiles/dop/15/17540/10986.png")

    assert answer.status_code == 502
    assert "Traceback" not in answer.text


@respx.mock
def test_slow_wms_is_a_504(client: TestClient):
    respx.get(DOP_URL).mock(side_effect=httpx.ReadTimeout("langsam"))

    assert client.get("/api/tiles/dop/15/17540/10986.png").status_code == 504


def test_tile_bounds_land_in_saxony():
    # z15/17540/10986 covers Leipzig; the proxy must ask for that area.
    minlon, minlat, maxlon, maxlat = geo.tile_bounds_4326(15, 17540, 10986)

    assert 12.0 < minlon < maxlon < 15.0
    assert 50.0 < minlat < maxlat < 52.0


def test_geographic_crs_uses_latitude_first():
    # WMS 1.3.0 orders a BBOX by the CRS' own axis order.
    bbox = geo.wms_bbox("EPSG:4326", 15, 17540, 10986)

    first, second = (float(value) for value in bbox.split(",")[:2])
    assert 50.0 < first < 52.0
    assert 12.0 < second < 15.0


def test_layer_configuration_covers_the_three_switchable_layers():
    assert set(tile_service().layers) == {"dop", "webatlas", "alkis"}
