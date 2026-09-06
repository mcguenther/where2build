"""POST /api/parcels/resolve -- the three ways in and their error answers."""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.schemas import parse_flurstuecksnummer

from .conftest import ALKIS_URL, MOTIS_URL, fixture_bytes, fixture_json

GEOCODE_URL = f"{MOTIS_URL}/api/v1/geocode"


@respx.mock
def test_resolve_by_coordinate_returns_a_feature_collection(client: TestClient):
    respx.get(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_single.gml"))
    )

    answer = client.post("/api/parcels/resolve", json={"lat": 51.3397, "lon": 12.3731})

    assert answer.status_code == 200
    body = answer.json()
    assert body["type"] == "FeatureCollection"
    properties = body["features"][0]["properties"]
    assert properties["kennzeichen"] == "140415___00604000202"
    assert properties["gemarkung"] == "Leipzig"
    assert properties["zaehler"] == "604"
    assert properties["nenner"] == "2"
    assert properties["flaeche_amtlich_m2"] == 39.0
    assert "GeoSN" in body["quelle"]


@respx.mock
def test_resolve_by_identifier_unions_several_parcels(client: TestClient):
    respx.post(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_zwei.gml"))
    )

    answer = client.post(
        "/api/parcels/resolve", json={"gemarkung": "141234", "zaehler": 790}
    )

    assert answer.status_code == 200
    grundstueck = answer.json()["grundstueck"]["properties"]
    assert grundstueck["anzahl_flurstuecke"] == 2
    assert grundstueck["flaeche_amtlich_m2"] == 802.0
    assert grundstueck["flaeche_berechnet_m2"] != grundstueck["flaeche_amtlich_m2"]


@respx.mock
def test_resolve_by_address_geocodes_first(client: TestClient):
    respx.get(GEOCODE_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("motis_geocode.json"))
    )
    respx.get(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_single.gml"))
    )

    answer = client.post(
        "/api/parcels/resolve", json={"address": "Muldentalstraße 12, 04288 Leipzig"}
    )

    assert answer.status_code == 200
    assert "Hauskoordinaten" in answer.json()["hinweis"]


@respx.mock
def test_address_without_a_hit_is_a_404(client: TestClient):
    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=[]))

    answer = client.post("/api/parcels/resolve", json={"address": "Gibtsnicht 1"})

    assert answer.status_code == 404
    assert "Adresse" in answer.json()["detail"]


@respx.mock
def test_unknown_parcel_is_a_404(client: TestClient):
    respx.post(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_leer.gml"))
    )

    answer = client.post("/api/parcels/resolve", json={"gemarkung": "141234", "zaehler": 1})

    assert answer.status_code == 404


def test_empty_request_is_a_422_with_a_german_message(client: TestClient):
    answer = client.post("/api/parcels/resolve", json={})

    assert answer.status_code == 422
    # The frontend shows `detail` and nothing else, so `detail` names the ways in.
    detail = answer.json()["detail"]
    assert "Adresse" in detail and "Flurstücksnummer" in detail
    assert answer.json()["felder"][0]["pfad"] == ["body"]


def test_two_ways_in_at_once_are_rejected(client: TestClient):
    answer = client.post(
        "/api/parcels/resolve",
        json={"address": "Markt 1", "lat": 51.3, "lon": 12.3},
    )

    assert answer.status_code == 422


def test_half_a_coordinate_is_rejected(client: TestClient):
    assert client.post("/api/parcels/resolve", json={"lat": 51.3}).status_code == 422


def test_impossible_coordinate_is_rejected(client: TestClient):
    assert client.post("/api/parcels/resolve", json={"lat": 100, "lon": 12}).status_code == 422


@respx.mock
def test_rejected_wfs_request_becomes_a_502(client: TestClient):
    respx.get(ALKIS_URL).mock(
        return_value=httpx.Response(400, html="<html>400 Fehler</html>")
    )

    answer = client.post("/api/parcels/resolve", json={"lat": 51.3397, "lon": 12.3731})

    assert answer.status_code == 502
    assert "ALKIS" in answer.json()["detail"]
    assert "Traceback" not in answer.text


@respx.mock
def test_slow_wfs_becomes_a_504(client: TestClient):
    respx.get(ALKIS_URL).mock(side_effect=httpx.ReadTimeout("zu langsam"))

    answer = client.post("/api/parcels/resolve", json={"lat": 51.3397, "lon": 12.3731})

    assert answer.status_code == 504
    assert "rechtzeitig" in answer.json()["detail"]


# --------------------------------------------------------------------------
# Flurstücksnummer: what the official geoportal prints is one number, not two
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("nummer", "erwartet"),
    [
        ("85/1", (85, "1")),
        ("476", (476, None)),
        ("41/e", (41, "e")),  # letter denominators are valid, not a typo
        ("207/b", (207, "b")),
        (" 85 / 1 ", (85, "1")),
        ("1", (1, None)),
    ],
)
def test_a_parcel_number_splits_into_numerator_and_denominator(nummer, erwartet):
    assert parse_flurstuecksnummer(nummer) == erwartet


@pytest.mark.parametrize("nummer", ["", "   ", "abc", "/5", "85/", "85/1/2", "-3", "85//1", "e/41"])
def test_nonsense_is_rejected_with_a_german_message(nummer):
    with pytest.raises(ValueError) as fehler:
        parse_flurstuecksnummer(nummer)

    assert "Flurstücksnummer" in str(fehler.value)


@respx.mock
def test_resolve_accepts_a_parcel_number_instead_of_numerator_and_denominator(
    client: TestClient,
):
    route = respx.post(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_single.gml"))
    )

    answer = client.post(
        "/api/parcels/resolve", json={"gemarkung": "Leipzig", "flurstuecksnummer": "604/2"}
    )

    assert answer.status_code == 200
    body = route.calls[0].request.content.decode("utf-8")
    assert "<fes:Literal>604</fes:Literal>" in body
    assert "<fes:Literal>2</fes:Literal>" in body


@respx.mock
def test_a_parcel_number_without_a_denominator_asks_for_the_numerator_only(
    client: TestClient,
):
    route = respx.post(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_single.gml"))
    )

    client.post("/api/parcels/resolve", json={"gemarkung": "Leipzig", "flurstuecksnummer": "476"})

    body = route.calls[0].request.content.decode("utf-8")
    assert "flstnrzae" in body
    assert "flstnrnen" not in body


@respx.mock
def test_a_letter_denominator_reaches_the_wfs_as_text(client: TestClient):
    route = respx.post(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_single.gml"))
    )

    client.post("/api/parcels/resolve", json={"gemarkung": "Leipzig", "flurstuecksnummer": "41/e"})

    body = route.calls[0].request.content.decode("utf-8")
    assert "<fes:Literal>e</fes:Literal>" in body


def test_an_unparsable_parcel_number_is_a_422_with_an_example(client: TestClient):
    answer = client.post(
        "/api/parcels/resolve", json={"gemarkung": "Leipzig", "flurstuecksnummer": "acht/fünf"}
    )

    assert answer.status_code == 422
    detail = answer.json()["detail"]
    assert "keine gültige Flurstücksnummer" in detail
    assert "85/1" in detail  # the message shows what a valid one looks like


def test_both_spellings_at_once_are_refused(client: TestClient):
    answer = client.post(
        "/api/parcels/resolve",
        json={"gemarkung": "Leipzig", "flurstuecksnummer": "85/1", "zaehler": 85},
    )

    assert answer.status_code == 422
    assert "nicht beides" in answer.json()["detail"]


def test_a_parcel_number_without_a_gemarkung_is_refused(client: TestClient):
    answer = client.post("/api/parcels/resolve", json={"flurstuecksnummer": "85/1"})

    assert answer.status_code == 422
    assert "Gemarkung" in answer.json()["detail"]


@respx.mock
def test_a_numeric_denominator_still_works_as_before(client: TestClient):
    route = respx.post(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_single.gml"))
    )

    answer = client.post(
        "/api/parcels/resolve", json={"gemarkung": "141234", "zaehler": 604, "nenner": 2}
    )

    assert answer.status_code == 200
    assert "<fes:Literal>2</fes:Literal>" in route.calls[0].request.content.decode("utf-8")


@respx.mock
def test_a_number_without_a_denominator_that_matched_several_parcels_says_so(
    client: TestClient,
):
    # 604 alone also finds 604/1 to 604/c -- the union is then an artefact of
    # the search key, not a plot the user picked.
    respx.post(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_zwei.gml"))
    )

    answer = client.post(
        "/api/parcels/resolve", json={"gemarkung": "141234", "flurstuecksnummer": "790"}
    )

    hinweis = answer.json()["hinweis"]
    assert "mehrere" in hinweis
    assert "Nenner" in hinweis


@respx.mock
def test_a_unique_parcel_gets_no_such_hint(client: TestClient):
    respx.post(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_single.gml"))
    )

    answer = client.post(
        "/api/parcels/resolve", json={"gemarkung": "140415", "flurstuecksnummer": "604/2"}
    )

    assert answer.json()["hinweis"] is None


# --------------------------------------------------------------------------
# Gemarkungsschlüssel: the Geoportal shows the same district two ways
# --------------------------------------------------------------------------


@respx.mock
def test_a_four_digit_gemarkung_key_reaches_the_wfs_as_six(client: TestClient):
    # The 'Flurstueck' layer prints 3044 for Moritzburg, the 'Gemarkung' layer
    # 143044. Only the second one is in ALKIS, and a user reading the first has
    # no way to know that.
    route = respx.post(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_moritzburg.gml"))
    )

    answer = client.post(
        "/api/parcels/resolve", json={"gemarkung": "3044", "flurstuecksnummer": "1"}
    )

    assert answer.status_code == 200
    body = route.calls[0].request.content.decode("utf-8")
    assert "<fes:Literal>143044</fes:Literal>" in body
    assert "<fes:ValueReference>ave:gemaschl</fes:ValueReference>" in body
    grundstueck = answer.json()["grundstueck"]["properties"]
    assert grundstueck["flaeche_amtlich_m2"] == 34799.0  # as in the Geoportal
    assert grundstueck["gemarkung"] == "Moritzburg"


@respx.mock
def test_the_expanded_key_is_named_in_the_answer(client: TestClient):
    respx.post(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_moritzburg.gml"))
    )

    answer = client.post(
        "/api/parcels/resolve", json={"gemarkung": "3044", "flurstuecksnummer": "1"}
    )

    hinweis = answer.json()["hinweis"]
    assert "3044" in hinweis and "143044" in hinweis


@respx.mock
def test_a_six_digit_key_is_left_alone(client: TestClient):
    route = respx.post(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_moritzburg.gml"))
    )

    answer = client.post(
        "/api/parcels/resolve", json={"gemarkung": "143044", "flurstuecksnummer": "1"}
    )

    assert "<fes:Literal>143044</fes:Literal>" in route.calls[0].request.content.decode("utf-8")
    assert answer.json()["hinweis"] is None


@respx.mock
def test_a_district_name_is_never_expanded(client: TestClient):
    route = respx.post(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_moritzburg.gml"))
    )

    answer = client.post(
        "/api/parcels/resolve", json={"gemarkung": "Moritzburg", "flurstuecksnummer": "1"}
    )

    body = route.calls[0].request.content.decode("utf-8")
    assert "<fes:ValueReference>ave:gemarkung</fes:ValueReference>" in body
    assert "14Moritzburg" not in body
    assert answer.json()["hinweis"] is None


@respx.mock
def test_a_key_below_four_digits_is_zero_padded(client: TestClient):
    # 183 of Saxony's 5 339 districts have a leading zero (Borna is 140101);
    # a key that has been through a number field has lost it.
    route = respx.post(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_single.gml"))
    )

    client.post("/api/parcels/resolve", json={"gemarkung": "101", "flurstuecksnummer": "1"})

    assert "<fes:Literal>140101</fes:Literal>" in route.calls[0].request.content.decode("utf-8")


@respx.mock
def test_a_wrong_key_is_a_404_that_names_the_key_it_searched(client: TestClient):
    respx.post(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_leer.gml"))
    )

    answer = client.post(
        "/api/parcels/resolve", json={"gemarkung": "9999", "flurstuecksnummer": "1"}
    )

    assert answer.status_code == 404
    detail = answer.json()["detail"]
    assert "9999" in detail and "149999" in detail
    # The sentence teaches the rule that cost a user the guessing in the first place.
    assert "sechsstellig" in detail


@respx.mock
def test_a_wrong_full_key_does_not_explain_an_expansion_that_did_not_happen(
    client: TestClient,
):
    respx.post(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_leer.gml"))
    )

    answer = client.post(
        "/api/parcels/resolve", json={"gemarkung": "149999", "flurstuecksnummer": "1"}
    )

    assert answer.status_code == 404
    assert "sechsstellig" not in answer.json()["detail"]


# --------------------------------------------------------------------------
# Plausibility: an address alone is not a plot
# --------------------------------------------------------------------------


@respx.mock
def test_a_district_address_lands_on_a_field_and_the_answer_says_so(client: TestClient):
    # Recorded live: "Plaußig-Portitz, 04349 Leipzig" geocodes to a PLACE, and
    # the parcel under that point is a 21 609 m2 field along Tauchaer Straße.
    respx.get(GEOCODE_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("motis_geocode_ortsteil.json"))
    )
    respx.get(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_feldstreifen.gml"))
    )

    answer = client.post(
        "/api/parcels/resolve",
        json={"address": "Plaußig-Portitz, 04349 Leipzig", "expected_area_m2": 908},
    )

    assert answer.status_code == 200  # a warning, never an error
    plausibility = answer.json()["plausibility"]
    assert plausibility["plausible"] is False
    assert set(plausibility["issues"]) == {
        "area_too_large",
        "shape_atypical",
        "address_is_not_a_street_address",
    }
    assert plausibility["area_factor"] == pytest.approx(23.8, abs=0.1)
    assert plausibility["expected_area_m2"] == 908
    assert "21.609 m²" in plausibility["warning"]


@respx.mock
def test_the_flagged_parcel_is_still_returned_in_full(client: TestClient):
    respx.get(GEOCODE_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("motis_geocode_ortsteil.json"))
    )
    respx.get(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_feldstreifen.gml"))
    )

    body = client.post(
        "/api/parcels/resolve",
        json={"address": "Plaußig-Portitz, 04349 Leipzig", "expected_area_m2": 908},
    ).json()

    # A caller who really wants this parcel keeps it.
    assert body["features"][0]["properties"]["kennzeichen"] == "140428___00165000101"
    assert body["grundstueck"]["properties"]["flaeche_amtlich_m2"] == 21609.0


@respx.mock
def test_a_house_address_on_a_matching_plot_is_plausible(client: TestClient):
    respx.get(GEOCODE_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("motis_geocode.json"))
    )
    respx.get(ALKIS_URL).mock(
        return_value=httpx.Response(
            200, content=fixture_bytes("alkis_flurstueck_baugrundstueck.gml")
        )
    )

    answer = client.post(
        "/api/parcels/resolve",
        json={"address": "Plaußiger Dorfstraße 21, 04349 Leipzig", "expected_area_m2": 911},
    )

    plausibility = answer.json()["plausibility"]
    assert plausibility["plausible"] is True
    assert plausibility["issues"] == []
    assert plausibility["warning"] is None


@respx.mock
def test_the_plausibility_block_travels_without_an_expected_area(client: TestClient):
    respx.post(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_feldstreifen.gml"))
    )

    plausibility = client.post(
        "/api/parcels/resolve", json={"gemarkung": "140428", "flurstuecksnummer": "165/1"}
    ).json()["plausibility"]

    assert plausibility["issues"] == ["shape_atypical"]
    assert plausibility["area_factor"] is None
    assert plausibility["longest_extent_m"] > 1500


@respx.mock
def test_an_expected_area_works_on_the_coordinate_way_in_too(client: TestClient):
    respx.get(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_feldstreifen.gml"))
    )

    plausibility = client.post(
        "/api/parcels/resolve",
        json={"lat": 51.3866, "lon": 12.4485, "expected_area_m2": 908},
    ).json()["plausibility"]

    assert "area_too_large" in plausibility["issues"]
    # No geocoder was involved, so nothing is claimed about the address.
    assert "address_is_not_a_street_address" not in plausibility["issues"]


def test_an_expected_area_of_zero_is_refused(client: TestClient):
    answer = client.post(
        "/api/parcels/resolve", json={"lat": 51.3, "lon": 12.3, "expected_area_m2": 0}
    )

    assert answer.status_code == 422
    assert answer.json()["felder"][0]["pfad"] == ["body", "expected_area_m2"]


# --------------------------------------------------------------------------
# POST /api/parcels/nearby -- the candidates, for the user to choose between
# --------------------------------------------------------------------------


@respx.mock
def test_nearby_lists_the_parcels_around_a_coordinate(client: TestClient):
    """`/resolve` answers with one plot; this answers with the candidates.

    An address coordinate is not a parcel boundary — the register puts it on the
    building. Measured on Lessingweg 44 in Mölkau, where the routing geocoder's
    point sits 7 m away, inside number 46.
    """

    route = respx.get(ALKIS_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_zwei.gml"))
    )

    answer = client.post(
        "/api/parcels/nearby", json={"lat": 51.336612, "lon": 12.441776, "umkreis_m": 60}
    )

    assert answer.status_code == 200
    body = answer.json()
    assert len(body["features"]) == 2
    assert "Adresskoordinate ist keine Flurstücksgrenze" in body["hinweis"] \
        or "Nachbarflurstück" in body["hinweis"]
    # The window is the one that was asked for, not the 1 m the point query uses.
    bbox = route.calls[0].request.url.params["BBOX"].split(",")
    assert float(bbox[2]) - float(bbox[0]) == pytest.approx(120, abs=1)


def test_nearby_refuses_a_window_that_is_not_a_neighbourhood(client: TestClient):
    answer = client.post(
        "/api/parcels/nearby", json={"lat": 51.33, "lon": 12.44, "umkreis_m": 5000}
    )

    assert answer.status_code == 422


# --------------------------------------------------------------------------
# The fourth way in: a set of parcel keys, as the picker assembles it
# --------------------------------------------------------------------------

SINGLE_KEY = "140415___00604000202"
MORITZBURG_KEY = "143044___00001____01"


def _by_key(request: httpx.Request) -> httpx.Response:
    """The stored query, answering per key like the WFS does."""

    wanted = request.url.params.get("kennzeichen")
    fixtures = {
        SINGLE_KEY: "alkis_flurstueck_single.gml",
        MORITZBURG_KEY: "alkis_flurstueck_moritzburg.gml",
    }
    return httpx.Response(200, content=fixture_bytes(fixtures.get(wanted, "alkis_leer.gml")))


@respx.mock
def test_resolve_by_keys_makes_one_plot_of_several_parcels(client: TestClient):
    """A plot is a set of parcels, and this is the set a user clicked together:
    the union is the outline, the official areas are summed."""

    respx.get(ALKIS_URL).mock(side_effect=_by_key)

    answer = client.post(
        "/api/parcels/resolve", json={"kennzeichen": [SINGLE_KEY, MORITZBURG_KEY]}
    )

    assert answer.status_code == 200
    body = answer.json()
    assert [f["properties"]["kennzeichen"] for f in body["features"]] == [
        SINGLE_KEY, MORITZBURG_KEY
    ]
    grundstueck = body["grundstueck"]["properties"]
    assert grundstueck["anzahl_flurstuecke"] == 2
    assert grundstueck["flaeche_amtlich_m2"] == 34838.0   # 39 + 34 799
    assert "2 Flurstücken" in body["hinweis"]


@respx.mock
def test_the_same_key_twice_is_one_parcel(client: TestClient):
    """Otherwise a double click would double the plot's official area."""

    respx.get(ALKIS_URL).mock(side_effect=_by_key)

    body = client.post(
        "/api/parcels/resolve", json={"kennzeichen": [SINGLE_KEY, SINGLE_KEY]}
    ).json()

    assert body["grundstueck"]["properties"]["anzahl_flurstuecke"] == 1
    assert body["grundstueck"]["properties"]["flaeche_amtlich_m2"] == 39.0


@respx.mock
def test_a_key_nobody_knows_is_a_404_that_names_it(client: TestClient):
    respx.get(ALKIS_URL).mock(side_effect=_by_key)

    answer = client.post(
        "/api/parcels/resolve", json={"kennzeichen": [SINGLE_KEY, "140415___09999000000"]}
    )

    assert answer.status_code == 404
    assert "140415___09999000000" in answer.json()["detail"]


def test_keys_do_not_mix_with_the_other_ways_in(client: TestClient):
    answer = client.post(
        "/api/parcels/resolve", json={"kennzeichen": [SINGLE_KEY], "lat": 51.3, "lon": 12.4}
    )

    assert answer.status_code == 422
