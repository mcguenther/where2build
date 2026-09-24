"""Portal adapters: meta tags first, and no request at all to a blocking portal."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.errors import BadRequestError
from app.services.portals import (
    fetch_page,
    blocked_hint,
    is_blocked,
    is_immoscout,
    is_kleinanzeigen,
    parse_immoscout,
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
    assert is_blocked("https://www.immowelt.de/expose/c1fc6775-3423-4549-b881-424be15286ac")
    # A suffix match on the domain, not on the string.
    assert not is_blocked("https://www.nichtimmowelt.de/expose/1")


def test_each_blocked_portal_names_itself_in_its_hint():
    immoscout = blocked_hint(IMMOSCOUT_URL)
    immowelt = blocked_hint("https://www.immowelt.de/expose/c1fc6775-3423-4549-b881-424be15286ac")

    assert "immobilienscout24.de" in immoscout and "HTTP 401" in immoscout
    assert "immowelt.de" in immowelt and "HTTP 403" in immowelt
    assert "immobilienscout24" not in immowelt
    assert all("Lesezeichen" in hint for hint in (immoscout, immowelt))
    assert blocked_hint(KLEINANZEIGEN_URL) is None


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
    # The refusal has to name the way that works, not only the one that does not.
    assert "Seite einfügen" in error.value.message
    assert "Lesezeichen" in error.value.message


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


# ---------------------------------------------------------------------------
# immobilienscout24.de
#
# The one portal no server may fetch, so both shapes it can arrive in are
# pinned here: the whole document as the bookmarklet hands it over, and the
# body alone as the clipboard delivers it. The fixture is a recorded exposé
# (167953918, Grünau-Siedlung in Leipzig, 09.09.2026).


def _immoscout_page() -> str:
    return fixture_text("inserat-immoscout.html")


def _immoscout_body() -> str:
    """What `Strg+A, Strg+C` leaves: no `<head>`, and no `<script>` anywhere."""

    page = _immoscout_page()
    body = page[page.index("<body") :]
    assert "obj_lotArea" not in body
    assert "og:description" not in body
    assert "objectDescription" not in body
    return body


def test_an_immoscout_page_is_recognised_in_both_shapes():
    assert is_immoscout(_immoscout_page())
    assert is_immoscout(_immoscout_body())
    assert not is_immoscout(fixture_text("inserat-kleinanzeigen.html"))


def test_the_whole_document_gives_up_its_structured_fields():
    """The analytics block is better than the prose, field by field.

    The listing's own text hedges („eine Fläche von ca. 742 m²") where
    `obj_lotArea` states 742, and the tolerance staircase starts from the
    wording -- so reading the structured field is the difference between an
    exact area, which is a hard filter, and a band, which only ranks.
    """

    seite = parse_page("https://www.immobilienscout24.de/expose/167953918", _immoscout_page())

    assert seite.angaben["Grundstücksfläche"] == "742 m²"
    assert seite.kaufpreis_eur == 275_000
    # The Bundesland is composed in from the portal's own field: ALKIS is
    # state-specific, and this is the cheapest hard filter the search has.
    assert seite.adresse == "Grünau-Siedlung, 04207 Leipzig, Sachsen"
    assert "Leipziger Stadtteil Grünau-Siedlung" in seite.beschreibung
    assert "Kulkwitzer See" in seite.beschreibung
    assert seite.bilder and all(
        url.startswith("https://pictures.immobilienscout24.de/") for url in seite.bilder
    )


def test_a_withheld_address_yields_no_coordinate():
    """`exposeMap` carries one, and taking it would be the 6 235 m mistake.

    The page says `isFullAddress: false` and `showFullAddress: false`, and the
    coordinate next to that is the *quarter's* — the same class of thing as
    Kleinanzeigen's municipality pin, which measured 6 235 m from the parcel
    actually offered. This app resolves the parcel under a coordinate, so a
    quarter centroid is not a coarse locator, it is a wrong one.
    """

    page = _immoscout_page()
    assert '"latitude":51.30595' in page

    seite = parse_page("https://www.immobilienscout24.de/expose/167953918", page)

    assert seite.lat is None
    assert seite.lon is None


def test_the_body_alone_still_gives_the_area_the_price_and_the_prose():
    """What a paste can do, and where it falls short of the handover.

    The numbers survive as rendered text in the portal's own `is24qa-*`
    elements; the Bundesland and the pictures do not, because they live in
    `<head>` and in a `<script>`.
    """

    seite = parse_page("", _immoscout_body())

    assert seite.angaben["Grundstücksfläche"] == "742 m²"
    assert seite.kaufpreis_eur == 275_000
    assert seite.adresse == "Grünau-Siedlung, 04207 Leipzig"
    assert "Kulkwitzer See" in seite.beschreibung
    assert seite.bilder == []


def test_the_value_element_is_read_and_not_its_label():
    """Every `is24qa-*` value has a `…-label` sibling with the same class plus
    a suffix, and it comes first in the document. Without a guard against the
    suffix the area read „Grundstücksfläche ca. 742 m²" — label and all."""

    read = parse_immoscout(_immoscout_body())

    assert read["flaeche"] == "742 m²"
    assert "Grundstücksfläche" not in read["flaeche"]


def test_the_agents_disclaimer_is_not_the_listings_prose():
    """„Wir machen die obigen Angaben nach bestem Wissen …" is a legal note in
    the same element class as the description. It says nothing about where the
    plot is, and it must not crowd out the two texts that do."""

    read = parse_immoscout(_immoscout_body())

    assert "nach bestem Wissen" not in read["beschreibung"]
    assert "Grünau-Siedlung" in read["beschreibung"]
