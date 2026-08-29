"""ALKIS: GML parsing, reprojection and the union of several parcels."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.deps import alkis_service
from app.errors import NotFoundError, UpstreamError
from app.services.alkis import parse_feature_collection, to_collection

from .conftest import ALKIS_URL, fixture_bytes

# Saxony's rough extent -- a coordinate outside it means the reprojection is wrong.
SACHSEN_LAT = (50.0, 52.0)
SACHSEN_LON = (12.0, 15.0)


def test_gml_is_parsed_into_parcels():
    parcels = parse_feature_collection(fixture_bytes("alkis_flurstueck_single.gml"))

    assert len(parcels) == 1
    parcel = parcels[0]
    assert parcel.attributes["flstkennz"] == "140415___00604000202"
    assert parcel.attributes["gemarkung"] == "Leipzig"
    assert parcel.attributes["gemaschl"] == "140415"
    assert parcel.attributes["flstnrzae"] == "604"
    assert parcel.attributes["flstnrnen"] == "2"
    # The official area comes from the attribute, not from the polygon.
    assert parcel.flaeche_amtlich_m2 == 39.0
    assert parcel.geometry.area == pytest.approx(39.04, abs=0.01)


def test_geometry_is_reprojected_from_25833_to_wgs84():
    collection = to_collection(parse_feature_collection(fixture_bytes("alkis_flurstueck_single.gml")))

    ring = collection.features[0].geometry.coordinates[0]
    for lon, lat in ring:
        assert SACHSEN_LON[0] < lon < SACHSEN_LON[1]
        assert SACHSEN_LAT[0] < lat < SACHSEN_LAT[1]


def test_several_parcels_are_unioned_and_official_areas_summed():
    parcels = parse_feature_collection(fixture_bytes("alkis_flurstueck_zwei.gml"))
    collection = to_collection(parcels)

    grundstueck = collection.grundstueck.properties
    assert grundstueck.anzahl_flurstuecke == 2
    # 520 + 282 from the ALKIS attribute -- the plot the listing advertises.
    assert grundstueck.flaeche_amtlich_m2 == 802.0
    # The polygons compute to 799.2 m2; that number must not be the answer.
    assert grundstueck.flaeche_berechnet_m2 == pytest.approx(799.2, abs=0.01)
    assert grundstueck.flaeche_amtlich_m2 != grundstueck.flaeche_berechnet_m2
    assert sum(f.properties.flaeche_amtlich_m2 for f in collection.features) == 802.0
    # Two adjacent parcels union into a single polygon.
    assert collection.grundstueck.geometry.type == "Polygon"
    assert set(grundstueck.kennzeichen) == {"141234___00790______", "141234___00706______"}


def test_empty_response_is_a_not_found():
    with pytest.raises(NotFoundError):
        to_collection(parse_feature_collection(fixture_bytes("alkis_leer.gml")))


def test_service_exception_is_an_upstream_error():
    body = (
        b'<?xml version="1.0"?><ServiceExceptionReport><ServiceException>'
        b"Fehler</ServiceException></ServiceExceptionReport>"
    )
    with pytest.raises(UpstreamError):
        parse_feature_collection(body)


def test_broken_xml_is_an_upstream_error():
    with pytest.raises(UpstreamError):
        parse_feature_collection(b"<html><body>400</body></html")


@respx.mock
async def test_point_query_sends_bbox_in_utm33():
    route = respx.get(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_single.gml"))
    )

    parcels = await alkis_service().by_point(51.3397, 12.3731)

    assert len(parcels) == 1
    params = route.calls[0].request.url.params
    assert params["TYPENAMES"] == "ave:Flurstueck"
    assert params["BBOX"].endswith("urn:ogc:def:crs:EPSG::25833")
    easting = float(params["BBOX"].split(",")[0])
    assert 300_000 < easting < 500_000


@respx.mock
async def test_stored_query_carries_the_mandatory_crs_parameter():
    route = respx.get(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_single.gml"))
    )

    await alkis_service().by_kennzeichen("140415___00604000202")

    params = route.calls[0].request.url.params
    # Without CRS the service answers 400 with a generic HTML page.
    assert params["CRS"] == "urn:ogc:def:crs:EPSG::25833"
    assert params["STOREDQUERY_ID"].endswith("flst-by-kennzeichen")


@respx.mock
async def test_ad_hoc_filter_uses_the_ave_namespace_prefix():
    route = respx.post(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_zwei.gml"))
    )

    parcels = await alkis_service().by_gemarkung("140415", 604, 2)

    body = route.calls[0].request.content.decode("utf-8")
    # Without the prefix the service answers 400.
    assert "<fes:ValueReference>ave:gemaschl</fes:ValueReference>" in body
    assert "<fes:ValueReference>ave:flstnrzae</fes:ValueReference>" in body
    assert "<fes:ValueReference>ave:flstnrnen</fes:ValueReference>" in body
    assert len(parcels) == 2


@respx.mock
async def test_non_numeric_district_is_matched_by_name():
    respx.post(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_zwei.gml"))
    )

    await alkis_service().by_gemarkung("Liebertwolkwitz", 790)

    body = respx.calls[0].request.content.decode("utf-8")
    assert "<fes:ValueReference>ave:gemarkung</fes:ValueReference>" in body
    assert "Liebertwolkwitz" in body


@respx.mock
async def test_second_identical_query_is_served_from_the_cache():
    route = respx.get(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_single.gml"))
    )

    service = alkis_service()
    await service.by_kennzeichen("140415___00604000202")
    await service.by_kennzeichen("140415___00604000202")

    assert route.call_count == 1
