"""GET /api/tiles/{layer}/{z}/{x}/{y}.png -- the WMS proxy and its disk cache."""

from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from app import geo
from app.deps import tile_service

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
        "dop", "webatlas", "alkis", "flurstuecke", "laerm", "laerm-nacht"
    }


def test_the_parcel_layer_is_the_cadastre_without_the_building_fills():
    """It lies over the aerial photograph, where a grey building fill would
    hide the roof somebody switched the photo on to see."""

    layers = tile_service().layers
    assert layers["flurstuecke"].layers == "adv_alkis_flurstuecke"
    assert "gebaeude" in layers["alkis"].layers
    assert layers["flurstuecke"].min_scale == layers["alkis"].min_scale


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
    assert route.calls[1].request.url.params["LAYERS"] == parcels.layers != alkis.layers


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
    tile, 85 draws and 86 comes back blank."""

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


@respx.mock
def test_a_wms_layer_keeps_its_own_request_shape(client: TestClient):
    """The two kinds live in one table; adding the second must not have turned
    the first into an ArcGIS request."""

    route = respx.get(DOP_URL).mock(return_value=_wms_answer())

    client.get("/api/tiles/dop/16/35081/21973.png")

    params = route.calls[0].request.url.params
    assert params["REQUEST"] == "GetMap"
    assert "bboxSR" not in params
