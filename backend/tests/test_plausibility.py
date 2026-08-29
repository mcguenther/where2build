"""Judging a parcel against the plot area a listing states.

The numbers asserted here come from parcels recorded live from the ALKIS WFS
on 29.08.2026, not from invented geometry: the Portitz field is the parcel a
district address really resolves to, the Plaußig plot is a real 911 m2
building plot in the same district.
"""

from __future__ import annotations

import pytest

from app.plausibility import (
    AREA_FACTOR_TOO_LARGE,
    AREA_FACTOR_TOO_SMALL,
    STRIP_MIN_ELONGATION,
    STRIP_MIN_LENGTH_M,
    assess,
    extents,
)
from app.schemas import GeocodeTreffer
from app.services.alkis import parse_feature_collection

from .conftest import fixture_bytes

FIELD = "alkis_flurstueck_feldstreifen.gml"  # Portitz 165/1, 21 609 m2
PLOT = "alkis_flurstueck_baugrundstueck.gml"  # Plaußig 8/2, 911 m2


def parcels(name: str):
    return parse_feature_collection(fixture_bytes(name))


def test_extents_measure_the_rotated_rectangle_not_the_envelope():
    # The field runs diagonally: its axis-aligned envelope is 1583 x 198 m,
    # which hides the strip. The rotated rectangle sees 1594 x 30 m.
    longest, shortest = extents(parcels(FIELD)[0].geometry)

    assert 1590 < longest < 1600
    assert 25 < shortest < 35


def test_a_matching_plot_is_plausible():
    result = assess(parcels(PLOT), expected_area_m2=911)

    assert result.plausible is True
    assert result.issues == []
    assert result.warning is None
    assert result.area_factor == 1.0


def test_a_field_against_a_listing_area_is_flagged_with_the_factor():
    result = assess(parcels(FIELD), expected_area_m2=908)

    assert result.plausible is False
    assert "area_too_large" in result.issues
    assert result.area_factor == pytest.approx(23.8, abs=0.1)
    assert result.flaeche_amtlich_m2 == 21609.0
    # The frontend shows this sentence; it names both areas and the factor.
    assert "21.609 m²" in result.warning
    assert "908 m²" in result.warning
    assert "24-mal" in result.warning


def test_the_shape_alone_flags_a_field_without_an_expected_area():
    """A district address usually arrives without a listing area."""

    result = assess(parcels(FIELD))

    assert result.plausible is False
    assert result.issues == ["shape_atypical"]
    assert result.area_factor is None  # never derived from a missing input
    assert result.expected_area_m2 is None
    assert "Feld- oder Wegflurstücks" in result.warning


def test_a_compact_plot_is_not_flagged_for_its_shape():
    result = assess(parcels(PLOT))

    assert result.issues == []
    assert result.longest_extent_m < STRIP_MIN_LENGTH_M
    assert result.elongation < STRIP_MIN_ELONGATION


def test_a_parcel_far_below_the_stated_area_is_a_note_about_missing_parcels():
    # A plot is a set of parcels, so this direction is weaker evidence and
    # gets its own wording rather than the "wrong land" one.
    result = assess(parcels(PLOT), expected_area_m2=5000)

    assert result.issues == ["area_too_small"]
    assert "mehreren Flurstücken" in result.warning
    assert "Feld" not in result.warning


@pytest.mark.parametrize(
    ("expected", "flagged"),
    [
        (21609, False),  # exactly right
        (int(21609 / AREA_FACTOR_TOO_LARGE) + 1, False),  # just inside
        (int(21609 / AREA_FACTOR_TOO_LARGE), True),  # exactly at the threshold
        (908, True),
    ],
)
def test_the_area_threshold_is_where_it_says_it_is(expected: int, flagged: bool):
    result = assess(parcels(FIELD), expected_area_m2=expected)

    assert ("area_too_large" in result.issues) is flagged


def test_the_small_threshold_is_where_it_says_it_is():
    just_inside = assess(parcels(PLOT), expected_area_m2=int(911 / AREA_FACTOR_TOO_SMALL) - 1)
    at_threshold = assess(parcels(PLOT), expected_area_m2=int(911 / AREA_FACTOR_TOO_SMALL))

    assert just_inside.issues == []
    assert at_threshold.issues == ["area_too_small"]


def test_a_place_match_says_that_the_address_was_never_an_address():
    treffer = GeocodeTreffer(lat=51.38, lon=12.46, name="Plaußig-Portitz", art="ort")

    result = assess(parcels(PLOT), expected_area_m2=911, address_match=treffer)

    assert result.issues == ["address_is_not_a_street_address"]
    assert "Plaußig-Portitz" in result.warning
    assert "Ort" in result.warning


def test_a_house_number_match_is_not_flagged():
    treffer = GeocodeTreffer(lat=51.38, lon=12.46, name="Plaußiger Dorfstraße 21", art="adresse")

    result = assess(parcels(PLOT), expected_area_m2=911, address_match=treffer)

    assert result.issues == []


def test_every_finding_ends_with_what_to_do_now():
    result = assess(parcels(FIELD), expected_area_m2=908)

    assert result.warning.endswith("direkt eintragen.")
