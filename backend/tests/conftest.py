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
OVERPASS_URL = "https://overpass.example.org/api/interpreter"
LLM_URL = "https://llm.example.org/v1"
DOP_URL = "https://wms.example.org/dop"
ALKIS_WMS_URL = "https://wms.example.org/alkis"
LUIS_URL = "https://luis.example.org/arcgis/rest/services"
NOISE_EXPORT_URL = f"{LUIS_URL}/laerm/laermkartierung/MapServer/export"
UBA_URL = "https://luftdaten.example.org/api/air-data/v3"
BASEMAP_URL = "https://tiles.openfreemap.org"
OIDC_ISSUER = "https://auth.example.org"


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
    # Whatever contact address the developer put in .env stays out of the suite:
    # tests that assert who is told it must not depend on a local file.
    monkeypatch.setenv("APP_CONTACT", "")
    monkeypatch.setenv("ALKIS_WFS_URL", ALKIS_URL)
    monkeypatch.setenv("BORIS_WMS_URL", BORIS_URL)
    monkeypatch.setenv("MOTIS_BASE_URL", MOTIS_URL)
    monkeypatch.setenv("TILES_DOP_URL", DOP_URL)
    monkeypatch.setenv("TILES_ALKIS_URL", ALKIS_WMS_URL)
    monkeypatch.setenv("TILES_NOISE_URL", NOISE_EXPORT_URL)
    monkeypatch.setenv("LUIS_BASE_URL", LUIS_URL)
    monkeypatch.setenv("AIRQUALITY_BASE_URL", UBA_URL)
    monkeypatch.setenv("BASEMAP_UPSTREAM_URL", BASEMAP_URL)
    monkeypatch.setenv("LLM_BASE_URL", LLM_URL)
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test/model")
    # No POI index unless a test asks for one. Pointed at a path inside the
    # test's own tmp_path rather than deleted, so a developer's own built index
    # in backend/data cannot make the "index missing" tests pass by accident.
    monkeypatch.setenv("NEARBY_POI_INDEX_PATH", str(tmp_path / "kein-poi-index.json"))
    # Off, like a fresh deployment, and pointed somewhere harmless either way:
    # a developer's own .env must not be able to send a test to a public
    # Overpass instance.
    monkeypatch.setenv("OVERPASS_ENABLED", "false")
    monkeypatch.setenv("OVERPASS_URL", OVERPASS_URL)
    # No sign-in unless a test asks for it, and set to empty rather than left
    # alone: a developer's own backend/.env would otherwise configure a real
    # provider and every "nicht eingerichtet" test would stop testing anything.
    for variable in ("OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "OIDC_SESSION_SECRET"):
        monkeypatch.setenv(variable, "")
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


@pytest.fixture
def poi_index(monkeypatch: pytest.MonkeyPatch):
    """A deployment where scripts/build_poi_index.py has been run.

    The fixture file is the real output of that script, built from
    ``fixtures/poi_extract.osm`` -- so the format the loader reads is the
    format the builder writes, and a change to either breaks a test.
    """

    monkeypatch.setenv("NEARBY_POI_INDEX_PATH", str(FIXTURES / "poi_index.json"))
    reset_services()
    yield


@pytest.fixture
def overpass(monkeypatch: pytest.MonkeyPatch):
    """A deployment that switched the live OpenStreetMap source on.

    The prototype setting: no index built, ``OVERPASS_ENABLED=true``, and every
    request for a school or a park turns into one Overpass query.
    """

    monkeypatch.setenv("OVERPASS_ENABLED", "true")
    reset_services()
    yield


@pytest.fixture
def oidc(monkeypatch: pytest.MonkeyPatch):
    """A deployment with an OpenID provider configured.

    The provider is invented: no test may reach a real authorization server,
    and a made-up issuer makes that impossible rather than merely unlikely.
    ``OIDC_COOKIE_SECURE=false`` is what a plain-HTTP development server sets,
    and the test client is one: a Secure cookie would be stored and then never
    sent back over http://testserver.
    """

    monkeypatch.setenv("OIDC_ISSUER", OIDC_ISSUER)
    monkeypatch.setenv("OIDC_CLIENT_ID", "where2build")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "geheim")
    monkeypatch.setenv("OIDC_SESSION_SECRET", "sitzungsschluessel-fuer-den-test")
    monkeypatch.setenv("OIDC_COOKIE_SECURE", "false")
    reset_services()
    yield
