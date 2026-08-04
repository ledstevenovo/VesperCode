"""T02.1 legacy step 2.B: reproducible OCI build and no-self-reference proof.

Consumes only ``ReferenceBuildInputV1`` to build the frozen single-platform
reference image and returns its OCI manifest, config, recipe, platform, and
self-reference evidence.  Owns local OCI build/reproduction and
no-self-reference inspection only; registry lifecycle and validation-check
execution remain out of scope.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from spikes.docker_reference_boundary.input_contract import (
    ReferenceBuildInputV1,
    freeze_reference_build_input,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RECIPE_RELATIVE = Path("containers") / "reference" / "Dockerfile"
FIXTURE_RELATIVE = Path("reference") / "fixture"
REFERENCE_LOCK_RELATIVE = Path("requirements") / "reference.lock"

# Fixed builder/output/media-type/compression/attestation parameters.
BUILD_PLATFORM = "linux/amd64"
SOURCE_DATE_EPOCH = "1700000000"
BUILDX_VERSION = "0.30.1"

_SHA256 = hashlib.sha256
_FROM_DIGEST_RE = re.compile(r"^FROM\s+\S+@sha256:([0-9a-f]{64})(\s+AS\s+\S+)?\s*$")
_BUILDX_VERSION_RE = re.compile(r"^github\.com/docker/buildx v(\d+\.\d+\.\d+)")


@dataclass(frozen=True)
class ReferenceImageBuildEvidenceV1:
    """Immutable evidence of one frozen single-platform OCI build."""

    local_oci_manifest_digest: str
    image_config_digest: str
    recipe_digest: str
    platform: str
    self_reference_scan_passed: bool


def _read_required(path: Path) -> bytes:
    if not path.is_file():
        raise ValueError(f"missing frozen reference input: {path}")
    return path.read_bytes()


def _sha256_hex(data: bytes) -> str:
    return _SHA256(data).hexdigest()


def _recipe_path() -> Path:
    return REPO_ROOT / RECIPE_RELATIVE


def _from_digest(dockerfile_bytes: bytes) -> str:
    """Return the sha256 hex digest pinned by the recipe's FROM line."""
    for raw_line in dockerfile_bytes.decode("utf-8").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("FROM"):
            match = _FROM_DIGEST_RE.match(stripped)
            if match is None:
                raise ValueError("recipe FROM line must pin a sha256:<64 hex> digest")
            return match.group(1)
    raise ValueError("recipe must contain a FROM line")


def scan_image_members_for_self_reference(
    members: Sequence[bytes],
    annotations: Sequence[str],
    final_manifest_digest: str,
    final_manifest_bytes: bytes,
) -> bool:
    """Return False when any member carries the final manifest's own identity.

    Scans every layer blob and the image config for the final manifest digest
    (with and without the ``sha256:`` prefix) and for the final manifest bytes
    themselves, then scans every annotation value the same way.  The scan
    fails closed: one hit anywhere means no-self-reference is not proven.
    """
    needles = (
        final_manifest_digest.encode("utf-8"),
        f"sha256:{final_manifest_digest}".encode("utf-8"),
        final_manifest_bytes,
    )
    for member in members:
        for needle in needles:
            if needle in member:
                return False
    for annotation in annotations:
        for needle in needles:
            if needle in annotation.encode("utf-8"):
                return False
    return True


def build_reference_image(
    build_input: ReferenceBuildInputV1,
) -> ReferenceImageBuildEvidenceV1:
    """Build the frozen single-platform reference image from *build_input*.

    Fails closed before any build when the frozen input no longer matches the
    current repository state or when the recipe's pinned base image differs
    from the frozen base-image identity.  The build consumes only the frozen
    input, the recipe bytes, and the fixture/lock bytes they bind.
    """
    current = freeze_reference_build_input(REPO_ROOT)
    if current != build_input:
        raise ValueError("build input no longer matches the frozen repository state")
    recipe_bytes = _read_required(_recipe_path())
    if _from_digest(recipe_bytes) != build_input.base_image_digest:
        raise ValueError("recipe base image digest does not match frozen build input")
    recipe_digest = _sha256_hex(recipe_bytes)

    with tempfile.TemporaryDirectory(prefix="vesper-reference-build-") as tmp:
        context = Path(tmp) / "context"
        output_tar = Path(tmp) / "layout.tar"
        layout = Path(tmp) / "layout"
        context.mkdir()
        (context / "Dockerfile").write_bytes(recipe_bytes)
        shutil.copytree(REPO_ROOT / FIXTURE_RELATIVE, context / "fixture")
        (context / "requirements.lock").write_bytes(
            _read_required(REPO_ROOT / REFERENCE_LOCK_RELATIVE)
        )
        _run_docker_build(context, output_tar)
        layout.mkdir()
        with tarfile.open(output_tar, "r") as archive:
            archive.extractall(layout, filter="data")
        manifest_digest, manifest_bytes = _read_single_manifest(layout)
        config_digest, config_bytes, layer_bytes, annotations = _read_members(
            layout, manifest_bytes
        )
        platform = _platform_from_config(config_bytes)
        if platform != BUILD_PLATFORM:
            raise ValueError(f"built image platform {platform!r} != {BUILD_PLATFORM!r}")
        scan_passed = scan_image_members_for_self_reference(
            members=(config_bytes, *layer_bytes),
            annotations=annotations,
            final_manifest_digest=manifest_digest,
            final_manifest_bytes=manifest_bytes,
        )
        return ReferenceImageBuildEvidenceV1(
            local_oci_manifest_digest=manifest_digest,
            image_config_digest=config_digest,
            recipe_digest=recipe_digest,
            platform=platform,
            self_reference_scan_passed=scan_passed,
        )


def _run_docker_build(context: Path, output_tar: Path) -> None:
    _assert_builder_identity()
    argv = [
        "docker",
        "buildx",
        "build",
        "--output",
        (
            "type=oci,oci-mediatypes=true,compression=gzip,"
            f"force-compression=true,dest={output_tar}"
        ),
        "--provenance=false",
        "--sbom=false",
        "--platform",
        BUILD_PLATFORM,
        "--build-arg",
        f"SOURCE_DATE_EPOCH={SOURCE_DATE_EPOCH}",
        "-f",
        str(context / "Dockerfile"),
        str(context),
    ]
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = proc.stderr[-2000:] if proc.stderr else ""
        raise RuntimeError(f"docker build failed (exit {proc.returncode}): {tail}")


def _assert_builder_identity() -> None:
    """Fail closed unless the observed buildx builder matches the frozen one."""
    proc = subprocess.run(
        ["docker", "buildx", "version"], capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise RuntimeError("docker buildx version query failed")
    first_line = proc.stdout.splitlines()[0] if proc.stdout else ""
    match = _BUILDX_VERSION_RE.match(first_line.strip())
    observed = match.group(1) if match is not None else "unknown"
    if observed != BUILDX_VERSION:
        raise RuntimeError(
            f"docker buildx version {observed} != frozen {BUILDX_VERSION}"
        )


def _read_blob(layout: Path, descriptor_digest: str) -> bytes:
    """Read one OCI blob and re-verify its bytes against its descriptor."""
    hex_digest = descriptor_digest.split(":", 1)[1]
    blob = _read_required(layout / "blobs" / "sha256" / hex_digest)
    if _sha256_hex(blob) != hex_digest:
        raise ValueError("OCI blob digest mismatch in layout")
    return blob


def _read_single_manifest(layout: Path) -> tuple[str, bytes]:
    index = json.loads(_read_required(layout / "index.json").decode("utf-8"))
    manifests = index.get("manifests")
    if not isinstance(manifests, list) or len(manifests) != 1:
        raise ValueError("OCI layout must contain exactly one manifest")
    descriptor = manifests[0]
    if not isinstance(descriptor, dict):
        raise ValueError("manifest descriptor must be an object")
    digest = descriptor.get("digest")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise ValueError("manifest descriptor digest must be sha256:<hex>")
    return digest.split(":", 1)[1], _read_blob(layout, digest)


def _read_members(
    layout: Path, manifest_bytes: bytes
) -> tuple[str, bytes, list[bytes], list[str]]:
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    config = manifest.get("config")
    if not isinstance(config, dict):
        raise ValueError("OCI manifest must contain a config descriptor")
    config_digest = config.get("digest")
    if not isinstance(config_digest, str) or not config_digest.startswith("sha256:"):
        raise ValueError("config descriptor digest must be sha256:<hex>")
    config_bytes = _read_blob(layout, config_digest)
    layers = manifest.get("layers")
    if not isinstance(layers, list):
        raise ValueError("OCI manifest must contain a layers list")
    layer_bytes: list[bytes] = []
    for layer in layers:
        if not isinstance(layer, dict):
            raise ValueError("layer descriptor must be an object")
        layer_digest = layer.get("digest")
        if not isinstance(layer_digest, str) or not layer_digest.startswith("sha256:"):
            raise ValueError("layer descriptor digest must be sha256:<hex>")
        layer_bytes.append(_read_blob(layout, layer_digest))
    annotations_raw = manifest.get("annotations", {})
    if not isinstance(annotations_raw, dict):
        raise ValueError("manifest annotations must be an object")
    annotations = [
        value for value in annotations_raw.values() if isinstance(value, str)
    ]
    return (
        config_digest.split(":", 1)[1],
        config_bytes,
        layer_bytes,
        annotations,
    )


def _platform_from_config(config_bytes: bytes) -> str:
    config = json.loads(config_bytes.decode("utf-8"))
    os_name = config.get("os")
    architecture = config.get("architecture")
    if not isinstance(os_name, str) or not isinstance(architecture, str):
        raise ValueError("image config must declare os and architecture")
    return f"{os_name}/{architecture}"
