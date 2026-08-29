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
