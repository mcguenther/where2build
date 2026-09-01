"""GET /api/health reports which services are configured."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_lists_every_service(client: TestClient):
    answer = client.get("/api/health")

    assert answer.status_code == 200
    body = answer.json()
    assert body["status"] == "ok"
    dienste = {entry["name"]: entry for entry in body["dienste"]}
    assert set(dienste) == {"alkis", "gemarkungen", "boris", "motis", "poi", "tiles", "basemap", "llm"}
    assert dienste["llm"]["konfiguriert"] is True
    assert dienste["alkis"]["endpunkt"].endswith("/wfs")
    assert dienste["basemap"]["endpunkt"].endswith("/styles/liberty")


def test_health_reports_a_missing_llm_key(without_llm, client: TestClient):
    dienste = {entry["name"]: entry for entry in client.get("/api/health").json()["dienste"]}

    assert dienste["llm"]["konfiguriert"] is False
    assert "LLM_API_KEY" in dienste["llm"]["hinweis"]


def test_health_says_when_the_poi_index_has_not_been_built(client: TestClient):
    """Without it the frontend has to be able to say "nicht eingerichtet"
    instead of showing an empty list that reads as "hier gibt es nichts"."""

    dienste = {entry["name"]: entry for entry in client.get("/api/health").json()["dienste"]}

    assert dienste["poi"]["konfiguriert"] is False
    assert "build_poi_index.py" in dienste["poi"]["hinweis"]
    # The transit half does not depend on it, and the message says so.
    assert "Fahrplan" in dienste["poi"]["hinweis"]


def test_health_reports_the_built_index_with_its_age(poi_index, client: TestClient):
    dienste = {entry["name"]: entry for entry in client.get("/api/health").json()["dienste"]}

    assert dienste["poi"]["konfiguriert"] is True
    assert "7 Orte" in dienste["poi"]["hinweis"]
    assert "2026-08-22" in dienste["poi"]["hinweis"]


def test_health_reports_the_live_overpass_source_as_a_prototype_shortcut(
    overpass, client: TestClient
):
    """With no index but Overpass switched on the six categories *can* be
    answered, so the service counts as configured -- and the sentence says by
    what, and that it is not the production answer."""

    dienste = {entry["name"]: entry for entry in client.get("/api/health").json()["dienste"]}

    assert dienste["poi"]["konfiguriert"] is True
    assert dienste["poi"]["endpunkt"] == "https://overpass.example.org/api/interpreter"
    assert "Overpass" in dienste["poi"]["hinweis"]
    assert "Prototyp" in dienste["poi"]["hinweis"]


def test_health_offers_the_overpass_switch_when_nothing_is_set_up(client: TestClient):
    dienste = {entry["name"]: entry for entry in client.get("/api/health").json()["dienste"]}

    assert dienste["poi"]["konfiguriert"] is False
    assert "OVERPASS_ENABLED" in dienste["poi"]["hinweis"]


def test_health_prefers_the_built_index_over_the_live_source(
    poi_index, overpass, client: TestClient
):
    dienste = {entry["name"]: entry for entry in client.get("/api/health").json()["dienste"]}

    assert dienste["poi"]["endpunkt"].endswith("poi_index.json")
    assert "7 Orte" in dienste["poi"]["hinweis"]


def test_openapi_document_is_served(client: TestClient):
    schema = client.get("/openapi.json")

    assert schema.status_code == 200
    paths = schema.json()["paths"]
    assert "/api/parcels/resolve" in paths
    assert "/api/nearby" in paths
