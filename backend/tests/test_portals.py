"""Portal adapters: meta tags first, and no request at all to a blocking portal."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.errors import BadRequestError
from app.services.portals import (
    fetch_page,
    is_blocked,
    is_kleinanzeigen,
    parse_meta_tags,
    parse_page,
)
from app.settings import get_settings

from .conftest import fixture_text

KLEINANZEIGEN_URL = (
    "https://www.kleinanzeigen.de/s-anzeige/-wohnbaugrundstueck-fuer-efh-mit-b-plan-688-m-/"
    "3425157266-207-4059"
)
IMMOSCOUT_URL = "https://www.immobilienscout24.de/expose/110185322"


def test_meta_tags_are_read_as_a_dictionary():
    meta = parse_meta_tags(fixture_text("kleinanzeigen_inserat.html"))

    assert meta["og:latitude"] == "51.39235087498254"
    assert meta["og:title"].startswith("Wohnbaugrundstück")


def test_kleinanzeigen_page_yields_coordinates_without_a_model_call():
    seite = parse_page(KLEINANZEIGEN_URL, fixture_text("kleinanzeigen_inserat.html"))

    assert seite.has_coordinates
    assert seite.lat == pytest.approx(51.39235, abs=1e-5)
    assert seite.lon == pytest.approx(13.38684, abs=1e-5)
    assert seite.adresse == "01589, Riesa"
    assert "Flurstück 790 sowie 706" in seite.text
    # Scripts do not belong in the text handed to a model.
    assert "var tracking" not in seite.text


def test_domain_classification():
    assert is_kleinanzeigen(KLEINANZEIGEN_URL)
    assert is_blocked(IMMOSCOUT_URL)
    assert is_blocked("https://immobilienscout24.de/expose/1")
    assert not is_blocked(KLEINANZEIGEN_URL)


@respx.mock
async def test_immobilienscout24_is_never_requested():
    # Live-confirmed 401 through httpx and all three fetch engines -- so the
    # adapter does not even try; the paste field is the way in.
    route = respx.get(url__startswith="https://www.immobilienscout24.de").mock(
        return_value=httpx.Response(200, text="<html></html>")
    )

    with pytest.raises(BadRequestError) as error:
        await fetch_page(IMMOSCOUT_URL, get_settings().app)

    assert route.call_count == 0
    assert "Einfügefeld" in error.value.message


@respx.mock
async def test_listing_pages_are_requested_as_a_browser():
    respx.get(KLEINANZEIGEN_URL).mock(
        return_value=httpx.Response(
            200,
            text=fixture_text("kleinanzeigen_inserat.html"),
            headers={"content-type": "text/html; charset=utf-8"},
        )
    )

    seite = await fetch_page(KLEINANZEIGEN_URL, get_settings().app)

    assert seite.has_coordinates
    assert "Mozilla" in respx.calls[0].request.headers["user-agent"]


def test_json_ld_supplies_coordinates_when_meta_tags_do_not():
    html = (
        '<html><head><script type="application/ld+json">'
        '{"@type":"Place","geo":{"@type":"GeoCoordinates","latitude":51.05,"longitude":13.74}}'
        "</script></head><body>Text</body></html>"
    )

    seite = parse_page("https://beispiel.de/x", html)

    assert seite.lat == pytest.approx(51.05)
    assert seite.lon == pytest.approx(13.74)
