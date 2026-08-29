"""Plausibility bounds and validators of the extraction schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import (
    Flurstueckskennung,
    Haustyp,
    HaustypVorschlaege,
    Inserat,
    InseratVorschlaege,
    Vorschlag,
    as_vorschlaege,
)

URL = "https://www.beispiel-hersteller.de/haus/all-in-one-159/"


def _haustyp(**overrides) -> Haustyp:
    data = {
        "hersteller": "Beispiel",
        "typenbezeichnung": "All in One 159",
        "bebaute_flaeche_m2": 96.88,
        "quelle_url": URL,
    }
    data.update(overrides)
    return Haustyp(**data)


def test_built_up_area_within_bounds_is_accepted():
    assert _haustyp().bebaute_flaeche_m2 == 96.88


@pytest.mark.parametrize("area", [25, 500])
def test_built_up_area_outside_bounds_is_rejected(area: float):
    with pytest.raises(ValidationError):
        _haustyp(bebaute_flaeche_m2=area)


@pytest.mark.parametrize("length", [3.5, 31])
def test_outer_dimensions_outside_bounds_are_rejected(length: float):
    with pytest.raises(ValidationError):
        _haustyp(aussenmass_laenge_m=length)


def test_outer_dimensions_within_bounds_are_accepted():
    haustyp = _haustyp(aussenmass_laenge_m=11.4, aussenmass_breite_m=8.5)
    assert haustyp.abgeleitete_masse() == (11.4, 8.5)


def test_dimensions_are_derived_from_built_up_area():
    laenge, breite = _haustyp().abgeleitete_masse()
    assert laenge == pytest.approx(11.4, abs=0.1)
    assert breite == pytest.approx(8.5, abs=0.1)
    assert laenge * breite == pytest.approx(96.88, abs=0.2)


def test_empty_listing_is_rejected():
    with pytest.raises(ValidationError):
        Inserat()


def test_listing_with_address_only_is_accepted():
    assert Inserat(adresse="Muldentalstraße 12, 04288 Leipzig").adresse


def test_listing_with_coordinates_only_is_accepted():
    assert Inserat(lat=51.28, lon=12.48).lat == 51.28


def test_listing_with_parcels_only_is_accepted():
    inserat = Inserat(flurstuecke=[Flurstueckskennung(zaehler=790), Flurstueckskennung(zaehler=706)])
    assert [parcel.zaehler for parcel in inserat.flurstuecke] == [790, 706]


def test_half_a_coordinate_is_not_a_locator():
    with pytest.raises(ValidationError):
        Inserat(lat=51.28)


def test_extracted_fields_arrive_as_unconfirmed_suggestions():
    inserat = Inserat(adresse="Muldentalstraße 12", kaufpreis_eur=89000, quelle_url=URL)
    vorschlaege = as_vorschlaege(inserat, InseratVorschlaege, URL)

    assert isinstance(vorschlaege.adresse, Vorschlag)
    assert vorschlaege.adresse.wert == "Muldentalstraße 12"
    assert str(vorschlaege.adresse.quelle_url) == URL
    assert vorschlaege.adresse.bestaetigt is False
    assert vorschlaege.kaufpreis_eur.wert == 89000
    # The source URL itself is not a suggestion.
    assert "quelle_url" not in InseratVorschlaege.model_fields


def test_house_type_suggestions_carry_the_source():
    vorschlaege = as_vorschlaege(_haustyp(), HaustypVorschlaege, URL)
    assert vorschlaege.bebaute_flaeche_m2.wert == 96.88
    assert vorschlaege.bebaute_flaeche_m2.bestaetigt is False
    assert str(vorschlaege.hersteller.quelle_url) == URL


def test_listing_schema_carries_no_contact_fields():
    # A deliberate decision of the spec: no personal data in the database.
    forbidden = {"makler", "ansprechpartner", "telefon", "email", "name"}
    assert forbidden.isdisjoint(Inserat.model_fields)
