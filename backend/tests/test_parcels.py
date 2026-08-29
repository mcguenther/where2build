"""POST /api/parcels/resolve -- the three ways in and their error answers."""

from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

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
    assert answer.json()["detail"] == "Die Anfrage ist unvollständig oder ungültig."


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
