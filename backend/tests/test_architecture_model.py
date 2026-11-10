"""The C4 model in docs/architektur/workspace.dsl names the code it describes.

The model is written by hand, so nothing keeps it current on its own. These
tests make the drift loud instead: a router, a service adapter, a search module
or a compose service that the model does not mention fails here, and so does a
path the model mentions that no longer exists. They check *coverage*, not
whether the arrows are right -- that still needs a person who reads the
diagram. After fixing the DSL, run `node scripts/architecture.mjs`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"
FRONTEND = ROOT / "frontend" / "src"
DSL = ROOT / "docs" / "architektur" / "workspace.dsl"

# Glue every request passes through; a box of its own would say nothing.
GLUE = {"__init__", "main", "deps", "settings", "schemas", "validation", "geo"}

HINT = "add it to docs/architektur/workspace.dsl, then run `node scripts/architecture.mjs`"


@pytest.fixture(scope="module")
def dsl() -> str:
    return DSL.read_text(encoding="utf-8")


def _modules(folder: Path) -> list[str]:
    return sorted(p.stem for p in folder.glob("*.py") if p.stem != "__init__")


@pytest.mark.parametrize("package", ["routers", "services", "search"])
def test_every_module_of_a_package_is_in_the_model(dsl: str, package: str):
    missing = [name for name in _modules(APP / package) if f"{package}/{name}.py" not in dsl]
    assert not missing, f"{package}/: {', '.join(missing)} not in the model -- {HINT}"


def test_every_top_level_backend_module_is_in_the_model(dsl: str):
    missing = [
        name
        for name in _modules(APP)
        if name not in GLUE and not re.search(rf"(?<![/\w]){re.escape(name)}\.py", dsl)
    ]
    assert not missing, f"app/: {', '.join(missing)} not in the model -- {HINT}"


def test_every_backend_path_the_model_names_exists(dsl: str):
    named = set(re.findall(r"(?<![\w/.])((?:routers/|services/|search/|scripts/)?[a-z_]+\.py)\b", dsl))
    gone = sorted(
        path for path in named if not (APP / path).is_file() and not (APP.parent / path).is_file()
    )
    assert not gone, f"the model names {', '.join(gone)}, which backend/app no longer has"


def test_every_frontend_path_the_model_names_exists(dsl: str):
    gone = []
    for path in set(re.findall(r"(?<![\w/])((?:lib|views|components)/[\w/*]+\.(?:js|vue))", dsl)):
        if not list(FRONTEND.glob(path)):
            gone.append(path)
    for name in set(re.findall(r"(?<![\w/*])([A-Z]\w+\.vue)", dsl)):
        if not list(FRONTEND.rglob(name)):
            gone.append(name)
    assert not gone, f"the model names {', '.join(sorted(gone))}, which frontend/src no longer has"


def _compose_services() -> list[str]:
    """Service names from docker-compose.yml, without a YAML parser.

    PyYAML is not a backend dependency, and the shape needed here is fixed:
    two-space keys under the top-level ``services:`` block.
    """

    names, inside = [], False
    for line in (ROOT / "docker-compose.yml").read_text(encoding="utf-8").splitlines():
        if re.match(r"^\S", line):
            inside = line.startswith("services:")
            continue
        match = re.match(r"^  ([a-z0-9-]+):", line)
        if inside and match:
            names.append(match.group(1))
    return names


def test_every_compose_service_is_a_deployment_node(dsl: str):
    services = _compose_services()
    assert "backend" in services and "scheduler" in services, "the compose file was not read"
    nodes = {
        part.strip()
        for name in re.findall(r'deploymentNode "([^"]+)"', dsl)
        for part in name.split(",")
    }
    missing = [name for name in services if name not in nodes]
    assert not missing, f"docker-compose.yml: {', '.join(missing)} not a deployment node -- {HINT}"
