"""T34.1 legacy step 34.B: Demo image capability-separation tests.

The exact displayed RED test
``test_demo_image_contains_shared_core_but_no_formal_adapters`` is copied
from the T34.1 card with its body byte-identical (every assert line fits
the 88-char ruff line length, so no ruff-wrapping precedent is needed).
The already-RED matrix test ``test_demo_image_runtime_matrix`` pins the
PLAN 34.B row: curated import closure, non-root PORT/health/fixed trace,
no persistence, and capability absence pass.

The ``built_demo_image`` fixture builds the image from the reviewed
recipe when the recipe exists (the pre-implementation state has no
recipe, so the inspection stays empty and the exact RED's first
task-owned assertion fails on the missing allowlist/prohibited-prefix
image contract).  The ``demo_container`` fixture runs one fresh
container from the built image on a free host port and removes it on
teardown (zero residue).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Final

import pytest

from scripts.run_demo_image_smoke import (
    DEMO_IMAGE_TAG_V1,
    DEMO_SHARED_CORE_MODULES_V1,
    OCIImageInspection,
    PROHIBITED_DEMO_MODULE_PREFIXES_V1,
    allowlist_from_dockerfile,
    container_filesystem_violations,
    container_fixed_trace,
    container_non_root_uid,
    container_sessions_are_ephemeral,
    ensure_demo_image,
    image_import_docker_hits,
    lock_docker_sdk_present,
    probe_container_healthz,
    start_demo_container,
    stop_demo_container,
)

_REPO_ROOT: Final = Path(__file__).resolve().parents[3]
_DEMO_DOCKERFILE: Final = _REPO_ROOT / "containers" / "demo" / "Dockerfile"


@pytest.fixture(scope="session")
def built_demo_image() -> OCIImageInspection:
    """Inspect the built local Demo image (building it from the reviewed
    recipe when the recipe exists and the image is absent).  Before the
    allowlist/prohibited-prefix image contract is implemented there is no
    recipe, so no build happens and the inspection is empty.
    """
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
def test_demo_image_contains_shared_core_but_no_formal_adapters(
    built_demo_image: OCIImageInspection,
) -> None:
    assert set(DEMO_SHARED_CORE_MODULES_V1) <= built_demo_image.python_members
    assert not any(
        member == prefix or member.startswith(prefix + ".")
        for member in built_demo_image.python_members
        for prefix in PROHIBITED_DEMO_MODULE_PREFIXES_V1
    )


@pytest.mark.oci_smoke
def test_demo_image_runtime_matrix(
    built_demo_image: OCIImageInspection,
    demo_container: str,
) -> None:
    """PLAN 34.B row: curated import closure, non-root PORT/health/fixed
    trace, no persistence, and capability absence pass.
    """
    # Curated import closure: non-vacuous, exactly the reviewed
    # allowlist, shared core present, zero prohibited-prefix members.
    assert built_demo_image.python_members
    assert built_demo_image.image_id is not None
    assert built_demo_image.python_members == allowlist_from_dockerfile(
        _DEMO_DOCKERFILE
    )
    # Non-root PORT/health: the container serves /healthz on the
    # platform-injected port as the non-root vesper user.
    assert container_non_root_uid(demo_container) == 10001
    assert probe_container_healthz(demo_container) == 200
    # Fixed trace: the six fixed Mock scenario steps complete with the
    # exact outcomes and the post-completion advance is rejected.
    assert container_fixed_trace(demo_container) == (
        "DENIED",
        "DENIED",
        "CHECK_FAILED",
        "DENIED",
        "REJECTED(DEMO_WAITING_USER)",
        "COMPLETED(DEMO_COMPLETED)",
    )
    # No persistence: a container restart drops every in-memory session.
    assert container_sessions_are_ephemeral(demo_container)
    # Capability absence: the exact fixed simulation registry, no docker
    # SDK in the lock, no import docker in the boot closure, and no
    # sockets/secrets/repositories in the filesystem.
    assert container_filesystem_violations(demo_container) == []
    assert not lock_docker_sdk_present(_REPO_ROOT / "requirements" / "demo.lock")
    assert image_import_docker_hits(DEMO_IMAGE_TAG_V1) == []
