"""GET /api/tiles/{layer}/{z}/{x}/{y}.png -- the WMS proxy and its disk cache."""

from __future__ import annotations

import io

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app import geo
from app.deps import tile_service
from app.errors import BadRequestError

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


def test_layer_configuration_covers_every_switchable_layer():
    assert set(tile_service().layers) == {
        "dop", "webatlas", "alkis", "flurstuecke", "strassen"
    }


def test_the_parcel_outlines_are_asked_for_in_the_overlay_style():
    """„Gelb“ draws contours and no fills, which is the point over a photo."""

    config = tile_service().layers["flurstuecke"]

    assert config.layers == "adv_alkis_flurstuecke"
    assert config.styles == "Gelb"


def test_the_parcel_layer_is_rendered_large_enough_to_draw():
    """MaxScaleDenominator 2000: the service answers 200 with an empty PNG.

    The way round it is the service's own arithmetic — the denominator is
    (bbox / image_width) / 0,00028, so a *larger image over the same box* falls
    under the limit. Verified against the live service at Flurstück 790/11:
    every one of these renders and comes back with content.
    """

    service = tile_service()
    config = service.layers["flurstuecke"]

    for zoom, expected in ((19, 256), (18, 512), (17, 768), (16, 1280), (15, 2304)):
        size = service.render_size(config, zoom)
        assert size == expected, zoom
        denominator = (geo.tile_width_3857_m(zoom) / size) / 0.00028
        assert denominator <= config.max_scale_denominator, zoom


def test_oversampling_stops_where_the_service_stops_rendering():
    """z14 needs 4368 px for one tile and `MaxWidth` is 4000.

    So the floor is a measured fact and not a preference, and the layer says so
    rather than serving a transparent tile that looks like a broken overlay.
    """

    service = tile_service()
    config = service.layers["flurstuecke"]

    assert config.min_zoom == 15
    assert service.render_size(config, 14) == service.settings.max_render_size
    denominator = (geo.tile_width_3857_m(14) / service.settings.max_render_size) / 0.00028
    assert denominator > config.max_scale_denominator


@pytest.mark.asyncio
async def test_the_parcel_layer_is_not_asked_for_below_its_floor():
    with pytest.raises(BadRequestError) as raised:
        await tile_service().tile("flurstuecke", 14, 8771, 5471)

    assert "Zoomstufe 15" in raised.value.message


def test_an_oversized_render_reaches_the_browser_as_one_tile():
    """The point of the larger image is the scale, not the detail.

    A screenful of half-megabyte tiles is megabytes; the proxy scales each one
    back to the tile size before it caches or returns it.
    """

    from PIL import Image

    from app.services.tiles import _downscale

    big = Image.new("RGBA", (1280, 1280), (0, 0, 0, 0))
    for i in range(0, 1280, 64):
        for j in range(1280):
            big.putpixel((i, j), (255, 255, 0, 255))
    buffer = io.BytesIO()
    big.save(buffer, format="PNG")

    small = Image.open(io.BytesIO(_downscale(buffer.getvalue(), 256)))

    assert small.size == (256, 256)
    # The lines survive the reduction rather than falling between samples.
    assert any(pixel[3] > 0 for pixel in small.convert("RGBA").get_flattened_data())
