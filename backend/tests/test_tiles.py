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

from .conftest import ALKIS_WMS_URL, DOP_URL, NOISE_EXPORT_URL

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
        "dop", "webatlas", "alkis", "liegenschaftskarte", "flurstuecke", "strassen", "umgebung",
        "laerm", "laerm-nacht"
    }


def test_the_parcel_outlines_are_asked_for_in_the_overlay_style():
    """„Gelb“ draws contours and no fills, which is the point over a photo.

    The cadastral *ground* is the other one: there the buildings are wanted,
    because nothing underneath is being hidden by them.
    """

    layers = tile_service().layers

    assert layers["flurstuecke"].layers == "adv_alkis_flurstuecke"
    assert layers["flurstuecke"].styles == "Gelb"
    assert "gebaeude" in layers["alkis"].layers


def test_the_two_cadastral_overlays_solve_the_same_limit_differently():
    """One picture across a district, one picture of a plot.

    `adv_alkis_flurstuecke` stops drawing at 1:2000 either way. The search map
    needs its outlines five zoom steps above that, so its tile is rendered
    oversized and scaled back — which scales the labels down with it. The
    picker needs the *numbers*, so its tile stays 256 px and the limit is moved
    with `MAP_RESOLUTION` instead. Measured at z18 over Liebertwolkwitz: the
    plain tile carries 101/2, 85/1 and „Wiesengasse“, the oversampled one
    carries neither.
    """

    layers = tile_service().layers
    outlines, map_ = layers["flurstuecke"], layers["liegenschaftskarte"]

    assert outlines.layers == map_.layers  # the same layer of the same service
    assert outlines.max_scale_denominator and not outlines.min_scale
    assert map_.min_scale and not map_.max_scale_denominator
    assert map_.styles == ""  # the service's own symbology, labels and all
    assert map_.min_zoom == 0  # nothing to run out of: the tile stays one tile


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


@respx.mock
def test_changing_which_layers_a_ground_stands_for_invalidates_its_tiles(client: TestClient):
    """The cache key carried the layer's *name* only, so a tile drawn from the
    land-use layers was still served after the ground became the parcels --
    which looks exactly like a change that did not work."""

    route = respx.get(ALKIS_WMS_URL).mock(return_value=_wms_answer())
    service = tile_service()
    alkis, parcels = service.layers["alkis"], service.layers["flurstuecke"]

    client.get("/api/tiles/alkis/20/561296/351568.png")
    second = client.get("/api/tiles/flurstuecke/20/561296/351568.png")

    # Same service, same tile, different layers: the second is fetched again.
    assert second.headers["x-cache"] == "MISS"
    assert len(route.calls) == 2
    assert route.calls[1].request.url.params["STYLES"] == parcels.styles != alkis.styles


# --------------------------------------------------------------------------
# The noise layer, which is not a WMS
# --------------------------------------------------------------------------


@respx.mock
def test_the_noise_layer_goes_through_the_arcgis_export_endpoint(client: TestClient):
    """Its own service offers EPSG:4326 and 25833 but not 3857, so a WMS raster
    source gets nothing at all. `export` reprojects server-side."""

    route = respx.get(NOISE_EXPORT_URL).mock(return_value=_wms_answer())

    answer = client.get("/api/tiles/laerm/16/35081/21973.png")

    assert answer.status_code == 200
    params = route.calls[0].request.url.params
    assert params["bboxSR"] == params["imageSR"] == "3857"
    assert params["layers"] == "show:4"
    assert params["format"] == "png32"
    assert params["f"] == "image"
    assert "SERVICE" not in params  # not a WMS request


@respx.mock
def test_the_night_layer_asks_for_the_other_one(client: TestClient):
    route = respx.get(NOISE_EXPORT_URL).mock(return_value=_wms_answer())

    client.get("/api/tiles/laerm-nacht/16/35081/21973.png")

    assert route.calls[0].request.url.params["layers"] == "show:5"


@respx.mock
def test_the_dpi_keeps_the_layer_under_its_own_minscale(client: TestClient):
    """`minScale: 50000` makes the service answer with an empty image and no
    error above that scale. ArcGIS derives the scale as
    (bbox_width_m / image_width_px) * dpi / 0.0254, so the dpi is what keeps
    the layer visible -- measured: at 10 km over 512 px, dpi 65 draws and 66
    comes back blank."""

    route = respx.get(NOISE_EXPORT_URL).mock(return_value=_wms_answer())

    # Zoom 10 covers 39 km across one tile; zoom 16 covers 611 m.
    for zoom, x, y in ((10, 548, 343), (16, 35081, 21973)):
        client.get(f"/api/tiles/laerm/{zoom}/{x}/{y}.png")

    for call in route.calls:
        params = call.request.url.params
        minx, _, maxx, _ = (float(value) for value in params["bbox"].split(","))
        scale = (maxx - minx) / 256 * int(params["dpi"]) / 0.0254
        assert scale <= 50000, f"1:{scale:.0f} would draw nothing"
        assert 1 <= int(params["dpi"]) <= 96


@respx.mock
def test_the_cadastral_layer_keeps_its_parcels_at_every_zoom(client: TestClient):
    """The ALKIS layers stop drawing at 1:2000 and answer with an empty image,
    so a ground called "Kataster" loses its parcel boundaries two zoom steps out
    and says nothing about it. A WMS derives the scale from the standard 0,28 mm
    pixel, and MAP_RESOLUTION is what a caller can change: measured on a z18
    tile, 85 draws and 86 comes back blank.

    The other way round the same limit is `render_size`, which the overlay uses:
    a larger image over the same box. Both are measured; this one keeps the
    request to a single tile, which is what a full-screen ground wants."""

    route = respx.get(ALKIS_WMS_URL).mock(return_value=_wms_answer())

    # z20 is inside the layer's own range; z18 and z16 are not.
    for zoom, x, y in ((20, 561296, 351568), (18, 140324, 87892), (16, 35081, 21973)):
        client.get(f"/api/tiles/alkis/{zoom}/{x}/{y}.png")

    for call in route.calls:
        params = call.request.url.params
        minx, _, maxx, _ = (float(value) for value in params["BBOX"].split(","))
        # Without the parameter the service measures in its own standard pixel.
        resolution = float(params.get("MAP_RESOLUTION", 0.0254 / 0.00028))
        scale = (maxx - minx) * resolution / (256 * 0.0254)
        assert scale < 2000, f"1:{scale:.0f} would draw nothing"
        assert 1 <= resolution <= 91


@respx.mock
def test_a_layer_inside_its_scale_range_is_asked_without_a_resolution(client: TestClient):
    """The parameter is a correction, not a habit: where the standard pixel
    already draws, the request carries the service's own default."""

    route = respx.get(ALKIS_WMS_URL).mock(return_value=_wms_answer())

    client.get("/api/tiles/alkis/20/561296/351568.png")

    assert "MAP_RESOLUTION" not in route.calls[0].request.url.params


@respx.mock
def test_the_photo_layer_has_no_scale_limit_and_is_asked_plainly(client: TestClient):
    route = respx.get(DOP_URL).mock(return_value=_wms_answer())

    client.get("/api/tiles/dop/16/35081/21973.png")

    assert "MAP_RESOLUTION" not in route.calls[0].request.url.params


# --------------------------------------------------------------------------
# POST /api/tiles/warm -- the cache filled before anything draws
# --------------------------------------------------------------------------

WARM = "/api/tiles/warm"


def _refs(*columns: int) -> dict:
    return {"kacheln": [{"ebene": "dop", "z": 15, "x": x, "y": 10986} for x in columns]}


@respx.mock
def test_warming_fetches_the_missing_tiles_and_the_next_draw_is_a_hit(client: TestClient):
    route = respx.get(DOP_URL).mock(return_value=_wms_answer())

    answer = client.post(WARM, json=_refs(17540, 17541, 17542))

    assert answer.status_code == 202
    assert answer.json() == {"angefragt": 3, "geholt_werden": 3}
    # The test client runs the background task before it returns.
    assert route.call_count == 3
    drawn = client.get("/api/tiles/dop/15/17541/10986.png")
    assert drawn.headers["x-cache"] == "HIT"
    assert route.call_count == 3


@respx.mock
def test_warming_skips_what_the_cache_already_has(client: TestClient):
    route = respx.get(DOP_URL).mock(return_value=_wms_answer())
    client.get("/api/tiles/dop/15/17540/10986.png")

    answer = client.post(WARM, json=_refs(17540, 17540, 17541))

    # Named twice, counted once; cached, not fetched again.
    assert answer.json() == {"angefragt": 2, "geholt_werden": 1}
    assert route.call_count == 2


@respx.mock
def test_one_bad_tile_refuses_the_whole_warm_up(client: TestClient):
    route = respx.get(DOP_URL).mock(return_value=_wms_answer())
    body = _refs(17540)
    body["kacheln"].append({"ebene": "katasterX", "z": 15, "x": 17541, "y": 10986})

    answer = client.post(WARM, json=body)

    assert answer.status_code == 400
    assert route.call_count == 0


def test_a_warm_up_past_any_list_is_a_422(client: TestClient):
    assert client.post(WARM, json=_refs(*range(17000, 17401))).status_code == 422
    assert client.post(WARM, json={"kacheln": []}).status_code == 422


@respx.mock
def test_a_tile_that_fails_to_warm_is_fetched_when_drawn(client: TestClient):
    route = respx.get(DOP_URL).mock(side_effect=httpx.ReadTimeout("langsam"))

    answer = client.post(WARM, json=_refs(17540))

    # The answer went out before the fetch, so the failure cannot reach it.
    assert answer.status_code == 202
    route.mock(side_effect=None, return_value=_wms_answer())
    drawn = client.get("/api/tiles/dop/15/17540/10986.png")
    assert drawn.status_code == 200
    assert drawn.headers["x-cache"] == "MISS"


@pytest.mark.asyncio
@respx.mock
async def test_overlapping_warm_ups_fetch_a_tile_once():
    """The list warms, then a tick for the comparison warms again."""

    import asyncio

    async def slow(_request):
        await asyncio.sleep(0.05)
        return _wms_answer()

    route = respx.get(DOP_URL).mock(side_effect=slow)
    service = tile_service()
    tile = ("dop", 15, 17540, 10986)

    first = asyncio.create_task(service.warm([tile]))
    await asyncio.sleep(0)
    assert service.missing([tile]) == []
    await asyncio.gather(first, service.warm([tile]))

    assert route.call_count == 1
