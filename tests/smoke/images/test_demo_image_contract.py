"""T34.1 legacy step 34.B: Demo image contract tests.

The image contract pins allowlist/lock identity (GREEN-1): the recipe
COPYs are the single reviewed allowlist source, the built image ships
exactly those modules (no extra, no missing), the hash-locked demo lock
carries no docker SDK, the boot closure imports no docker, and the local
image carries a fresh digest identity.  The exact shared-core/prohibited
assertions live in ``test_image_capability_separation.py``; this module
owns the allowlist/lock/digest identity facts of the PLAN 34.B row.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Final

import pytest

from scripts.run_demo_image_smoke import (
    DEMO_IMAGE_TAG_V1,
    DEMO_SHARED_CORE_MODULES_V1,
    OCIImageInspection,
    PROHIBITED_DEMO_MODULE_PREFIXES_V1,
    allowlist_from_dockerfile,
    ensure_demo_image,
    image_import_docker_hits,
    lock_docker_sdk_present,
    lock_is_hash_locked,
)

_REPO_ROOT: Final = Path(__file__).resolve().parents[3]
_DEMO_DOCKERFILE: Final = _REPO_ROOT / "containers" / "demo" / "Dockerfile"
_DEMO_LOCK: Final = _REPO_ROOT / "requirements" / "demo.lock"


@pytest.fixture(scope="session")
def built_demo_image() -> OCIImageInspection:
    """Inspect the built local Demo image (building it from the reviewed
    recipe when the recipe exists and the image is absent)."""
    return ensure_demo_image(DEMO_IMAGE_TAG_V1, _DEMO_DOCKERFILE)


@pytest.mark.oci_smoke
def test_demo_lock_is_hash_locked_without_docker_sdk() -> None:
    """GREEN-1: hash-locked Demo requirements only, no docker SDK."""
    assert lock_is_hash_locked(_DEMO_LOCK)
    assert not lock_docker_sdk_present(_DEMO_LOCK)


@pytest.mark.oci_smoke
def test_demo_image_ships_exactly_the_curated_allowlist(
    built_demo_image: OCIImageInspection,
) -> None:
    """GREEN-1: the image's module set equals exactly the reviewed
    recipe allowlist, contains the shared pure core, and the allowlist
    itself has zero prohibited formal-capability prefixes."""
    allowlist = allowlist_from_dockerfile(_DEMO_DOCKERFILE)
    assert set(DEMO_SHARED_CORE_MODULES_V1) <= allowlist
    assert allowlist
    assert not any(
        member == prefix or member.startswith(prefix + ".")
        for member in allowlist
        for prefix in PROHIBITED_DEMO_MODULE_PREFIXES_V1
    )
    assert built_demo_image.python_members == allowlist


@pytest.mark.oci_smoke
def test_demo_image_has_fresh_digest(
    built_demo_image: OCIImageInspection,
) -> None:
    """GREEN-2/quality: the local image carries a fresh digest identity
    that matches docker's own record."""
    assert built_demo_image.image_id is not None
    proc = subprocess.run(
        ["docker", "image", "inspect", DEMO_IMAGE_TAG_V1],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0
    info = json.loads(proc.stdout)[0]
    assert built_demo_image.image_id == info["Id"]


@pytest.mark.oci_smoke
def test_demo_image_boot_closure_has_no_docker_import(
    built_demo_image: OCIImageInspection,
) -> None:
    """§75 ruling: Docker absence is proven behaviorally — the boot
    import closure of the image code contains no ``import docker``."""
    assert image_import_docker_hits(DEMO_IMAGE_TAG_V1) == []
