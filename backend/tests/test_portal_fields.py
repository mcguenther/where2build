"""Reading a listing without knowing the portal, against three recordings.

The point of this file is the third portal. ImmoScout and Kleinanzeigen have
adapters; ohne-makler.net has none and never will, and it is here to prove that
an unrecorded portal is read rather than refused. Its shape is deliberately the
awkward one: no ``<dt>``, no ``<th>``, the area's value standing *before* its
label in Tailwind spans, no price meta tag, no coordinate anywhere, and a
JSON-LD block that describes the portal company rather than the listing.
"""

from __future__ import annotations

import pytest

from app.services.portal_fields import (
    flat_text,
    german_number,
    location_line,
    read_area_m2,
    read_fields,
    read_location,
    read_price_eur,
)
from app.services.portals import parse_page

from .conftest import fixture_text

# name, area, price, the location line the reader composes
PORTALS = [
    ("inserat-immoscout.html", 742, 275_000, "04207 Leipzig, Sachsen"),
    ("inserat-ohne-makler.html", 5_366, 115_000, "Maschinenhausstraße, 01587 Riesa, Sachsen"),
    ("inserat-kleinanzeigen.html", 1_025, None, "04575 Neukieritzsch, Sachsen"),
]


@pytest.mark.parametrize("name, area, price, line", PORTALS)
def test_every_recorded_portal_gives_up_its_area(name, area, price, line):
    assert read_area_m2(fixture_text(name)) == area


@pytest.mark.parametrize("name, area, price, line", PORTALS)
def test_the_composed_location_line(name, area, price, line):
    assert location_line(read_location(fixture_text(name))) == line


def test_the_price_where_a_label_stands_near_it():
    """Two of the three write „Kaufpreis" next to the figure.

    Kleinanzeigen does not -- its price stands alone in a heading -- and that is
    why this reader is a floor under the meta-tag channel rather than a
    replacement for it: `parse_page` gets 80 000 € there from
    `<meta itemprop="price">`.
    """

    assert read_price_eur(fixture_text("inserat-immoscout.html")) == 275_000
    assert read_price_eur(fixture_text("inserat-ohne-makler.html")) == 115_000
    assert parse_page("", fixture_text("inserat-kleinanzeigen.html")).kaufpreis_eur == 80_000


def test_the_value_may_stand_before_its_label():
    """ohne-makler writes `<span>5.366 m²</span><span>Grundstücksfläche</span>`.

    Structure is therefore the wrong thing to key on, and this is the assertion
    that says so: the same reader gets ImmoScout's label-then-value and this
    one's value-then-label, because it goes by proximity and by the unit.
    """

    text = flat_text(fixture_text("inserat-ohne-makler.html"))
    assert text.index("5.366 m²") < text.index("Grundstücksfläche")
    assert read_area_m2(fixture_text("inserat-ohne-makler.html")) == 5_366


def test_a_rate_per_square_metre_is_not_the_asking_price():
    """ImmoScout prints „370,62 €/m²" one element from the price itself."""

    page = fixture_text("inserat-immoscout.html")
    assert "370,62 €/m²" in page
    assert read_price_eur(page) == 275_000


def test_prose_about_the_area_contributes_nothing():
    """„Die großzügige Grundstücksfläche bietet ideale Voraussetzungen …"

    The word appears three times on the ohne-makler page, twice of them in
    sentences. Only the occurrence with a value near it may count, or a
    description would decide the hard filter.
    """

    prose = (
        "<html><body><p>Die großzügige Grundstücksfläche bietet ideale "
        "Voraussetzungen, um Wohnen und Natur zu verbinden.</p></body></html>"
    )

    assert read_area_m2(prose) is None


def test_a_living_space_is_not_a_plot_area():
    """„Wohnfläche" and „Nutzfläche" both end in the bare label „Fläche"."""

    markup = (
        "<html><body><dl><dt>Wohnfläche</dt><dd>128 m²</dd>"
        "<dt>Nutzfläche</dt><dd>44 m²</dd></dl></body></html>"
    )

    assert read_area_m2(markup) is None


def test_the_portals_own_address_is_not_the_plots():
    """ohne-makler's JSON-LD is an `Organization` in Reinbek, Schleswig-Holstein.

    Reading a schema.org address without looking at whose it is would place
    this Saxon plot 400 km north -- and „600 m² in Brehna" already showed what
    a wrong state costs: eleven requests spent on an answer no request could
    have got right.
    """

    page = fixture_text("inserat-ohne-makler.html")
    assert "Reinbek" in page and "21465" in page

    read = read_location(page)

    assert read["plz"] == "01587"
    assert read["ort"] == "Riesa"
    assert read["bundesland"] == "Sachsen"


def test_the_state_may_stand_where_the_place_would():
    """Kleinanzeigen writes „04668 Sachsen – Grimma": state first, place behind.

    Reading „Sachsen" as the town is not a cosmetic error -- the state is the
    cheapest hard filter this app has, and a town called Sachsen would take
    part in it.
    """

    read = read_location("<html><body><p>04668 Sachsen – Grimma</p></body></html>")

    assert read == {"plz": "04668", "bundesland": "Sachsen", "ort": "Grimma"}


def test_a_thousands_dot_and_a_decimal_dot_are_told_apart():
    """The trap that once made every listing answer 422: a dot groups thousands
    only in threes, and a comma settles it outright."""

    assert german_number("1.025") == 1025
    assert german_number("51.189265") == pytest.approx(51.189265)
    assert german_number("1.025,50") == pytest.approx(1025.5)
    assert german_number("5.366") == 5366


def test_nothing_is_invented_from_an_empty_page():
    assert read_fields("<html><body><p>Ein Grundstück in schöner Lage.</p></body></html>") == {}
