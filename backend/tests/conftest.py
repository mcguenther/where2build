"""Shared test setup.

No test may touch the network: every external service is stubbed with respx,
and the fixtures under ``tests/fixtures`` follow the shapes recorded in
``docs/research``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.deps import reset_services
from app.main import app as fastapi_app

FIXTURES = Path(__file__).parent / "fixtures"

ALKIS_URL = "https://alkis.example.org/wfs"
BORIS_URL = "https://boris.example.org/wms"
MOTIS_URL = "https://motis.example.org"
LLM_URL = "https://llm.example.org/v1"
DOP_URL = "https://wms.example.org/dop"
BASEMAP_URL = "https://tiles.openfreemap.org"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str) -> Any:
    return json.loads(fixture_text(name))


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point every service at a test endpoint and give each test its own cache."""

    monkeypatch.setenv("APP_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("ALKIS_WFS_URL", ALKIS_URL)
    monkeypatch.setenv("BORIS_WMS_URL", BORIS_URL)
    monkeypatch.setenv("MOTIS_BASE_URL", MOTIS_URL)
    monkeypatch.setenv("TILES_DOP_URL", DOP_URL)
    monkeypatch.setenv("BASEMAP_UPSTREAM_URL", BASEMAP_URL)
    monkeypatch.setenv("LLM_BASE_URL", LLM_URL)
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test/model")
    reset_services()
    yield
    reset_services()


@pytest.fixture
def without_llm(monkeypatch: pytest.MonkeyPatch):
    """A deployment without an extraction provider configured.

    Set to empty rather than deleted: a developer's own ``backend/.env`` would
    otherwise supply a real key and the test would silently stop testing
    anything.
    """

    monkeypatch.setenv("LLM_API_KEY", "")
    reset_services()
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(fastapi_app)
