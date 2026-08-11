"""T36.3 legacy step 36.C: public Demo static contract tests.

The static public-Demo contract T37.1's live deployment smoke must
satisfy (SPEC §8.3): the exact Task 34.B image identity and platform
PORT, the exact ``/healthz`` body, the exact fixed Mock trace, and the
capability-isolated absence of formal/local/recovery capabilities — all
bound from committed sources (``render.yaml``, ``containers/demo/
Dockerfile``, and the reviewed 34.B image-contract constants) with zero
network, platform query, deployment, or evidence write.  The
``_HEALTHZ_OK_BODY_V1`` / ``_EXPECTED_FIXED_TRACE_V1`` imports are the
reviewed 34.B image-contract observations (private by naming, not by
contract): the public deployment must serve exactly those bodies, and
the live check of them belongs to T37.1 alone (GREEN-4).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

import pytest

from tests.smoke.release.test_render_contract import _parse_render_yaml

# The hash-locked gate toolchain does not install runtime
# dependencies (pydantic), so this module skips cleanly there
# instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from scripts.run_demo_image_smoke import (
    DEMO_DOCKERFILE_RELATIVE_V1,
    DEMO_IMAGE_TAG_V1,
    PROHIBITED_DEMO_MODULE_PREFIXES_V1,
    _EXPECTED_FIXED_TRACE_V1,
    _HEALTHZ_OK_BODY_V1,
)

_REPO_ROOT: Final = Path(__file__).resolve().parents[3]
_RENDER_YAML: Final = _REPO_ROOT / "render.yaml"
_DEMO_DOCKERFILE: Final = _REPO_ROOT / DEMO_DOCKERFILE_RELATIVE_V1

pytestmark = pytest.mark.deployment_smoke

# The committed public Demo service identity (SPEC §8.3; the render.yaml
# service T37.1 deploys).
PUBLIC_DEMO_SERVICE_NAME_V1: Final = "vespercode-demo"
PUBLIC_DEMO_IMAGE_TAG_V1: Final = "vespercode-demo:local"
PUBLIC_DEMO_NON_ROOT_UID_V1: Final = 10001

# The platform-injected PORT the Demo app binds (SPEC §8.3; the
# Dockerfile EXPOSEs 8000 and the launcher reads ``PORT`` with default
# "8000").
PUBLIC_DEMO_PLATFORM_PORT_V1: Final = 8000

# The exact platform health check path and the exact canonical body
# ``GET /healthz`` must serve (SPEC §8.3 simulation mode; the 34.B
# container smoke observes this exact sorted-key body).
PUBLIC_DEMO_HEALTH_PATH_V1: Final = "/healthz"
PUBLIC_DEMO_HEALTHZ_BODY_V1: Final = '{"mode": "simulation", "status": "ok"}'

# The exact six fixed Mock trace labels the public Demo must serve
# (T30.2 fixed trace; the 34.B container smoke observes them).
PUBLIC_DEMO_FIXED_TRACE_V1: Final[tuple[str, ...]] = (
    "DENIED",
    "DENIED",
    "CHECK_FAILED",
    "DENIED",
    "REJECTED(DEMO_WAITING_USER)",
    "COMPLETED(DEMO_COMPLETED)",
)


def _render_service() -> dict[str, object]:
    """The one committed render.yaml service mapping (static read)."""
    payload = _parse_render_yaml(_RENDER_YAML.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    services = payload["services"]
    assert isinstance(services, list)
    assert len(services) == 1
    service = services[0]
    assert isinstance(service, dict)
    return service


def _env_keys(service: dict[str, object]) -> tuple[str, ...]:
    env_vars = service["envVars"]
    assert isinstance(env_vars, list)
    return tuple(str(entry["key"]) for entry in env_vars if isinstance(entry, dict))


def test_public_demo_image_identity_contract() -> None:
    """The committed configuration binds exactly the Task 34.B Demo
    image recipe and local tag (the digest is T37.1's live observation)."""
    service = _render_service()
    assert service["type"] == "web"
    assert service["runtime"] == "docker"
    assert service["dockerfilePath"] == DEMO_DOCKERFILE_RELATIVE_V1
    assert service["dockerfilePath"] == "containers/demo/Dockerfile"
    assert _DEMO_DOCKERFILE.is_file()
    assert DEMO_IMAGE_TAG_V1 == PUBLIC_DEMO_IMAGE_TAG_V1


def test_public_demo_platform_port_contract() -> None:
    """The Dockerfile EXPOSE, the launcher's PORT default, and the
    committed platform PORT are the exact same 8000 (SPEC §8.3)."""
    dockerfile = _DEMO_DOCKERFILE.read_text(encoding="utf-8")
    assert "EXPOSE 8000" in dockerfile
    # The launcher CMD keeps the quotes escaped inside the JSON CMD
    # array, so the raw recipe text carries the escaped form.
    assert 'os.environ.get(\\"PORT\\", \\"8000\\")' in dockerfile
    assert f"useradd --system --uid {PUBLIC_DEMO_NON_ROOT_UID_V1}" in dockerfile
    service = _render_service()
    assert "PORT" in _env_keys(service)
    env_vars = service["envVars"]
    assert isinstance(env_vars, list)
    for entry in env_vars:
        if isinstance(entry, dict) and entry.get("key") == "PORT":
            assert str(entry["value"]) == str(PUBLIC_DEMO_PLATFORM_PORT_V1)
            break
    else:
        raise AssertionError("render.yaml must inject the platform PORT")


def test_public_demo_healthz_contract() -> None:
    """The public Demo serves exactly the canonical simulation health
    body on the exact /healthz path the platform probes."""
    assert _HEALTHZ_OK_BODY_V1 == PUBLIC_DEMO_HEALTHZ_BODY_V1
    assert json.loads(PUBLIC_DEMO_HEALTHZ_BODY_V1) == {
        "mode": "simulation",
        "status": "ok",
    }
    assert _render_service()["healthCheckPath"] == PUBLIC_DEMO_HEALTH_PATH_V1


def test_public_demo_fixed_trace_contract() -> None:
    """The public Demo serves the exact six fixed Mock trace labels
    (the 34.B image contract observes them in-container)."""
    assert _EXPECTED_FIXED_TRACE_V1 == PUBLIC_DEMO_FIXED_TRACE_V1


def test_public_demo_capability_absence_contract() -> None:
    """The committed configuration carries no persistent disk, no
    real-provider secret, and no repository credential, and the image
    cannot reach any formal/local/recovery capability (SPEC §8.3)."""
    service = _render_service()
    assert not service.get("disk")
    assert not service.get("envVarsFromFile")
    assert not service.get("secretFiles")
    repo = service["repo"]
    assert isinstance(repo, str)
    assert urlsplit(repo).username is None
    assert not urlsplit(repo).password
    env_keys = _env_keys(service)
    for prohibited_key in ("API_KEY", "TOKEN", "PASSWORD", "SECRET", "CREDENTIAL"):
        assert not any(prohibited_key in key for key in env_keys)
    assert "SOURCE_COMMIT" in env_keys
    assert "PORT" in env_keys

    # The curated image never ships a formal/local/recovery capability:
    # the exact formal families are prohibited module prefixes (34.B).
    required_prohibited = {
        "vespercode.credentials",
        "vespercode.llm.openai_adapter",
        "vespercode.loop.call_orchestrator",
        "vespercode.loop.engine",
        "vespercode.loop.turn_boundary",
        "vespercode.memory",
        "vespercode.persistence",
        "vespercode.storage.run_repository",
        "vespercode.tools.read_file",
        "vespercode.tools.list_files",
        "vespercode.tools.search_text",
        "vespercode.web",
        "vespercode.workspace.mutex_win32",
        "vespercode.cli_composition",
    }
    assert required_prohibited <= PROHIBITED_DEMO_MODULE_PREFIXES_V1

    # No formal/local/recovery endpoint exists in the closed Task 34.B
    # route surface (health, the fixed scenario page, and the two
    # session routes); the closed route set is pinned by the 30.B
    # capability-isolation tests and T37.1's live smoke verifies the
    # deployed surface.
    assert _render_service()["healthCheckPath"] == PUBLIC_DEMO_HEALTH_PATH_V1
    assert _render_service()["name"] == PUBLIC_DEMO_SERVICE_NAME_V1
