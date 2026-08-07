"""T34.1 legacy step 34.B: Demo container health tests.

The container health facts of the PLAN 34.B row (GREEN-2): one fresh
container runs non-root on the platform-injected PORT, serves the exact
``/healthz``, executes the fixed Mock trace with the exact six outcomes
and rejects the post-completion advance, drops every in-memory session on
restart (no persistence, no mounted volumes), keeps a filesystem free of
sockets/secrets/repositories, and registers exactly the fixed simulation
capability set (zero formal adapter construction or calls).
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import pytest

from scripts.run_demo_image_smoke import (
    DEMO_IMAGE_TAG_V1,
    OCIImageInspection,
    container_capability_registry_ok,
    container_filesystem_violations,
    container_fixed_trace,
    container_healthz_body,
    container_host_port,
    container_non_root_uid,
    container_post_completion_rejected,
    container_sessions_are_ephemeral,
    ensure_demo_image,
    probe_container_healthz,
    start_demo_container,
    stop_demo_container,
)

_REPO_ROOT: Final = Path(__file__).resolve().parents[3]
_DEMO_DOCKERFILE: Final = _REPO_ROOT / "containers" / "demo" / "Dockerfile"


@pytest.fixture(scope="session")
def built_demo_image() -> OCIImageInspection:
    """Inspect the built local Demo image (building it from the reviewed
    recipe when the recipe exists and the image is absent)."""
    return ensure_demo_image(DEMO_IMAGE_TAG_V1, _DEMO_DOCKERFILE)


@pytest.fixture(scope="session")
def demo_container(built_demo_image: OCIImageInspection) -> Iterator[str]:
    """One fresh Demo container on a free host port (removed on exit)."""
    container_id = start_demo_container(DEMO_IMAGE_TAG_V1)
    try:
        yield container_id
    finally:
        stop_demo_container(container_id)


@pytest.mark.oci_smoke
def test_demo_container_healthz_ok(demo_container: str) -> None:
    """GREEN-2: GET /healthz returns 200 with the exact closed body."""
    port = container_host_port(demo_container)
    assert probe_container_healthz(demo_container) == 200
    assert container_healthz_body(f"http://127.0.0.1:{port}") == (
        '{"mode": "simulation", "status": "ok"}'
    )


@pytest.mark.oci_smoke
def test_demo_container_runs_non_root(demo_container: str) -> None:
    """GREEN-2: the container process runs as the fixed non-root user."""
    assert container_non_root_uid(demo_container) == 10001


@pytest.mark.oci_smoke
def test_demo_container_fixed_mock_trace(demo_container: str) -> None:
    """GREEN-2: the fixed Mock scenario completes with the exact six
    outcomes and the post-completion advance is rejected (404)."""
    assert container_fixed_trace(demo_container) == (
        "DENIED",
        "DENIED",
        "CHECK_FAILED",
        "DENIED",
        "REJECTED(DEMO_WAITING_USER)",
        "COMPLETED(DEMO_COMPLETED)",
    )
    assert container_post_completion_rejected(demo_container)


@pytest.mark.oci_smoke
def test_demo_container_sessions_are_ephemeral(demo_container: str) -> None:
    """GREEN-2: a container restart drops every in-memory session."""
    assert container_sessions_are_ephemeral(demo_container)


@pytest.mark.oci_smoke
def test_demo_container_has_no_persistence(demo_container: str) -> None:
    """GREEN-2: no volume is mounted and sessions live only in process
    memory (SPEC §8.3 no persistent disk / §5.6)."""
    proc = subprocess.run(
        ["docker", "inspect", "--format", "{{json .Mounts}}", demo_container],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0
    assert (json.loads(proc.stdout.strip() or "[]") or []) == []
    assert container_sessions_are_ephemeral(demo_container)


@pytest.mark.oci_smoke
def test_demo_container_filesystem_clean(demo_container: str) -> None:
    """GREEN-2: no sockets, secrets, or repositories in the container."""
    assert container_filesystem_violations(demo_container) == []


@pytest.mark.oci_smoke
def test_demo_container_registers_only_demo_capabilities(
    demo_container: str,
) -> None:
    """GREEN-2: the capability registry is exactly the fixed simulation
    set — zero formal adapter construction or calls."""
    assert container_capability_registry_ok(demo_container)
