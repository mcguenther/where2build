"""GET /api/landvalue."""

from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from .conftest import BORIS_URL, fixture_text


@respx.mock
def test_land_value_for_a_coordinate(client: TestClient):
    respx.get(BORIS_URL).mock(
        return_value=httpx.Response(
            200,
            text=fixture_text("boris_getfeatureinfo.txt"),
            headers={"content-type": "text/plain"},
        )
    )

    answer = client.get("/api/landvalue", params={"lat": 51.3397, "lon": 12.3731})

    assert answer.status_code == 200
    body = answer.json()
    assert body["euro_per_sqm"] == 2400.0
    assert body["zone"] == "71300402"
    assert body["reference_date"] == "2026-01-01"
    assert body["source_url"].startswith(BORIS_URL)


@respx.mock
def test_coordinate_without_a_zone_is_a_404(client: TestClient):
    respx.get(BORIS_URL).mock(
        return_value=httpx.Response(
            200, text=fixture_text("boris_leer.txt"), headers={"content-type": "text/plain"}
        )
    )

    answer = client.get("/api/landvalue", params={"lat": 51.0, "lon": 13.0})

    assert answer.status_code == 404
    assert "Bodenrichtwert" in answer.json()["detail"]


def test_missing_parameters_are_a_422(client: TestClient):
    assert client.get("/api/landvalue").status_code == 422


def test_impossible_coordinate_is_a_422(client: TestClient):
    assert client.get("/api/landvalue", params={"lat": 200, "lon": 13}).status_code == 422


@respx.mock
def test_unavailable_service_is_a_502(client: TestClient):
    respx.get(BORIS_URL).mock(side_effect=httpx.ConnectError("weg"))

    answer = client.get("/api/landvalue", params={"lat": 51.0, "lon": 13.0})

    assert answer.status_code == 502
    assert "Traceback" not in answer.text


@respx.mock
def test_slow_service_is_a_504(client: TestClient):
    respx.get(BORIS_URL).mock(side_effect=httpx.ConnectTimeout("langsam"))

    assert client.get("/api/landvalue", params={"lat": 51.0, "lon": 13.0}).status_code == 504
