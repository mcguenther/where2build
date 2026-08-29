"""GET /api/health reports which services are configured."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_lists_every_service(client: TestClient):
    answer = client.get("/api/health")

    assert answer.status_code == 200
    body = answer.json()
    assert body["status"] == "ok"
    dienste = {entry["name"]: entry for entry in body["dienste"]}
    assert set(dienste) == {"alkis", "boris", "motis", "tiles", "basemap", "llm"}
    assert dienste["llm"]["konfiguriert"] is True
    assert dienste["alkis"]["endpunkt"].endswith("/wfs")
    assert dienste["basemap"]["endpunkt"].endswith("/styles/liberty")


def test_health_reports_a_missing_llm_key(without_llm, client: TestClient):
    dienste = {entry["name"]: entry for entry in client.get("/api/health").json()["dienste"]}

    assert dienste["llm"]["konfiguriert"] is False
    assert "LLM_API_KEY" in dienste["llm"]["hinweis"]


def test_openapi_document_is_served(client: TestClient):
    schema = client.get("/openapi.json")

    assert schema.status_code == 200
    assert "/api/parcels/resolve" in schema.json()["paths"]
