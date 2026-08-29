"""BORIS: parsing the GetFeatureInfo answer into a land reference value."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from app.deps import boris_service
from app.errors import NotFoundError, UpstreamError
from app.services.boris import parse_feature_info

from .conftest import BORIS_URL, fixture_text


def test_text_plain_answer_is_split_into_features():
    features = parse_feature_info(fixture_text("boris_getfeatureinfo.txt"))

    assert len(features) == 1
    assert features[0]["BODENRICHTWERT_TEXT"] == "2400"
    assert features[0]["NUTZUNG_TEXT"] == "Kerngebiet"


@respx.mock
async def test_land_value_is_read_from_the_wms():
    route = respx.get(BORIS_URL).mock(
        return_value=httpx.Response(
            200,
            text=fixture_text("boris_getfeatureinfo.txt"),
            headers={"content-type": "text/plain"},
        )
    )

    value = await boris_service().land_value(51.3397, 12.3731)

    assert value.euro_per_sqm == 2400.0
    assert value.zone == "71300402"
    assert value.reference_date == date(2026, 1, 1)
    assert value.nutzung == "Kerngebiet"
    assert value.gutachterausschuss.startswith("Gutachterausschuss")
    assert value.source_url.startswith(BORIS_URL)
    # The zone value does not necessarily apply to a single plot -- § 15 (2) ImmoWertV.
    assert "ImmoWertV" in value.hinweis

    params = route.calls[0].request.url.params
    assert params["REQUEST"] == "GetFeatureInfo"
    assert params["CRS"] == "EPSG:25833"
    # application/json would be UTFGrid rather than GeoJSON.
    assert params["INFO_FORMAT"] == "text/plain"
    assert params["I"] == params["J"] == "50"


@respx.mock
async def test_area_without_a_zone_is_a_not_found():
    respx.get(BORIS_URL).mock(
        return_value=httpx.Response(
            200, text=fixture_text("boris_leer.txt"), headers={"content-type": "text/plain"}
        )
    )

    with pytest.raises(NotFoundError):
        await boris_service().land_value(51.0, 13.0)


@respx.mock
async def test_service_exception_becomes_an_upstream_error():
    respx.get(BORIS_URL).mock(
        return_value=httpx.Response(
            200,
            text="<ServiceExceptionReport><ServiceException>utfgridStartLayer()</ServiceException></ServiceExceptionReport>",
            headers={"content-type": "text/xml"},
        )
    )

    with pytest.raises(UpstreamError):
        await boris_service().land_value(51.0, 13.0)


@respx.mock
async def test_second_query_for_the_same_point_uses_the_cache():
    route = respx.get(BORIS_URL).mock(
        return_value=httpx.Response(
            200,
            text=fixture_text("boris_getfeatureinfo.txt"),
            headers={"content-type": "text/plain"},
        )
    )

    service = boris_service()
    await service.land_value(51.3397, 12.3731)
    await service.land_value(51.3397, 12.3731)

    assert route.call_count == 1
