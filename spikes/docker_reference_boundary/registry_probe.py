"""T02.2 legacy step 2.C: loopback registry round-trip and three-way digest.

Starts one credential-free ``registry:2`` bound only to ``127.0.0.1`` on an
assigned port, reproduces the exact frozen OCI layout with the builder's own
fixed parameters, pushes the exact manifest and blob bytes, pulls the
manifest by digest, and compares the three raw observed digest bytes without
normalization or replacement.  Returns one immutable
``LoopbackRegistryEvidenceV1`` only when the local OCI, registry RepoDigest,
and digest-pull RepoDigest are byte-identical and cleanup is verified; any
observed digest transformation raises ``LoopbackRegistryDigestMismatchV1``
only after verified cleanup, with zero external push and no partial
accepted evidence.

Owns loopback bind, push, pull, digest comparison, and cleanup evidence
only.  Image building, fixture checks, and external publication remain out
of scope: the layout reproduction below re-runs the builder's own frozen
build machinery (same fixed parameters, same builder-identity assert) solely
to obtain the exact manifest and blob bytes that SPEC §1.4.1 requires to be
pushed, never as a second build contract or new build evidence.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from typing import Literal, NoReturn

from spikes.docker_reference_boundary.image_builder import (
    FIXTURE_RELATIVE,
    RECIPE_RELATIVE,
    REFERENCE_LOCK_RELATIVE,
    REPO_ROOT,
    ReferenceImageBuildEvidenceV1,
    _read_members,
    _read_required,
    _read_single_manifest,
    _run_docker_build,
    _sha256_hex,
    normalize_layout_tar,
)
from spikes.docker_reference_boundary.input_contract import REGISTRY_IMAGE_DIGEST

REGISTRY_IMAGE_REF = f"registry:2@sha256:{REGISTRY_IMAGE_DIGEST}"
REGISTRY_CONTAINER_PORT = "5000"
REPOSITORY = "vesper-reference"
PUSH_TAG = "roundtrip"
BIND_HOST: Literal["127.0.0.1"] = "127.0.0.1"
MANIFEST_MEDIA_TYPE = "application/vnd.oci.image.manifest.v1+json"
_SHA256_PREFIX = "sha256:"
# RFC 7230 header names are case-insensitive; the header map keys are
# lowercased, so lookups use the lowercased canonical name.
_DIGEST_HEADER = "docker-content-digest"
_REGISTRY_START_TIMEOUT_SECONDS = 30.0
_HTTP_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class LoopbackRegistryEvidenceV1:
    """Immutable evidence of one credential-free loopback registry round-trip."""

    registry_image_digest: str
    bind_host: Literal["127.0.0.1"]
    assigned_port: int
    credentials_used: Literal[False]
    external_push_count: Literal[0]
    local_oci_manifest_digest: str
    registry_repo_digest: str
    digest_pull_repo_digest: str
    cleanup_verified: bool


@dataclass(frozen=True)
class LoopbackRegistryDigestMismatchV1(Exception):
    """Task-owned rejection raised after verified cleanup on any observed
    three-way digest transformation; carries no accepted evidence."""

    error_code: Literal["OCI_REGISTRY_DIGEST_MISMATCH"]
    external_push_count: Literal[0]
    cleanup_verified: Literal[True]
    accepted_evidence_returned: Literal[False]


def probe_loopback_registry(
    build: ReferenceImageBuildEvidenceV1,
) -> LoopbackRegistryEvidenceV1:
    """Round-trip the exact local OCI manifest through a loopback registry.

    Starts one credential-free ``registry:2`` bound only to ``127.0.0.1`` on
    an assigned port, reproduces the exact frozen manifest and blob bytes,
    pushes them, pulls the manifest by digest, and compares the three raw
    observed digest bytes.  The registry container is removed on every exit
    path; ``LoopbackRegistryDigestMismatchV1`` is raised only after verified
    cleanup when any of the three observed digests differ, and no partial
    ``LoopbackRegistryEvidenceV1`` is ever returned.
    """
    container_id, assigned_port = _start_loopback_registry()
    registry_digest = ""
    pull_digest = ""
    try:
        with tempfile.TemporaryDirectory(prefix="vesper-registry-probe-") as tmp:
            manifest_bytes, config_bytes, layer_bytes = _reproduce_oci_layout(Path(tmp))
            registry_digest = _push_exact_manifest(
                assigned_port, manifest_bytes, config_bytes, layer_bytes
            )
            pull_digest, _ = _pull_manifest_by_digest(assigned_port, registry_digest)
    finally:
        try:
            cleanup_verified = _cleanup_registry(container_id)
        except BaseException:
            cleanup_verified = False
    if not cleanup_verified:
        raise RuntimeError("loopback registry cleanup not verified")
    local_digest = build.local_oci_manifest_digest
    if not _digests_byte_identical(local_digest, registry_digest, pull_digest):
        raise LoopbackRegistryDigestMismatchV1(
            error_code="OCI_REGISTRY_DIGEST_MISMATCH",
            external_push_count=0,
            cleanup_verified=True,
            accepted_evidence_returned=False,
        )
    return LoopbackRegistryEvidenceV1(
        registry_image_digest=REGISTRY_IMAGE_DIGEST,
        bind_host=BIND_HOST,
        assigned_port=assigned_port,
        credentials_used=False,
        external_push_count=0,
        local_oci_manifest_digest=local_digest,
        registry_repo_digest=registry_digest,
        digest_pull_repo_digest=pull_digest,
        cleanup_verified=True,
    )


def _registry_run_argv() -> list[str]:
    """The credential-free, loopback-only ``docker run`` command."""
    return [
        "docker",
        "run",
        "-d",
        "-p",
        f"{_loopback_bind_host()}::{REGISTRY_CONTAINER_PORT}",
        REGISTRY_IMAGE_REF,
    ]


def _loopback_bind_host() -> str:
    """Daemon-side publish address for the loopback registry.

    ``127.0.0.1`` by default; ``VESPER_LOOPBACK_BIND_HOST`` overrides it
    for a dind sibling topology (the GitLab jobs publish inside the
    daemon service container, so the daemon-side bind must be reachable
    from the job container through the service alias).
    """
    return os.environ.get("VESPER_LOOPBACK_BIND_HOST", BIND_HOST)


def _loopback_probe_host() -> str:
    """Job-side address used to reach the published registry port.

    ``127.0.0.1`` by default; ``VESPER_LOOPBACK_PROBE_HOST`` overrides it
    for the dind topology, where ``docker`` resolves to the daemon
    service container from the job container.
    """
    return os.environ.get("VESPER_LOOPBACK_PROBE_HOST", BIND_HOST)


def _registry_base_url(port: int) -> str:
    """Loopback-only registry API base for one repository."""
    return f"http://{_loopback_probe_host()}:{port}/v2/{REPOSITORY}"


def _start_loopback_registry() -> tuple[str, int]:
    """Start one credential-free registry bound only to ``127.0.0.1``.

    Returns the container id and the assigned host port once the registry
    answers an anonymous ``/v2/`` ping; fails closed by removing the
    container when the port cannot be read or readiness is not reached.
    """
    proc = subprocess.run(
        _registry_run_argv(), capture_output=True, text=True, timeout=60
    )
    if proc.returncode != 0:
        tail = proc.stderr[-2000:] if proc.stderr else ""
        raise RuntimeError(
            f"docker run registry failed (exit {proc.returncode}): {tail}"
        )
    container_id = proc.stdout.strip().splitlines()[-1].strip()
    if not container_id:
        raise RuntimeError("docker run registry returned no container id")
    assigned_port = _read_assigned_port(container_id)
    if assigned_port is None:
        _fail_start_with_cleanup(
            container_id, "failed to read the assigned loopback registry port"
        )
    if not _wait_until_ready(assigned_port):
        _fail_start_with_cleanup(
            container_id, "loopback registry did not become ready in time"
        )
    return container_id, assigned_port


def _fail_start_with_cleanup(container_id: str, message: str) -> NoReturn:
    """Remove the registry container and raise *message*; fail closed when
    the removal itself cannot be verified."""
    if not _cleanup_registry(container_id):
        raise RuntimeError(f"{message}; registry cleanup not verified")
    raise RuntimeError(message)


def _read_assigned_port(container_id: str) -> int | None:
    """Read the host port mapped by ``-p 127.0.0.1::5000``, loopback only."""
    proc = subprocess.run(
        ["docker", "port", container_id, f"{REGISTRY_CONTAINER_PORT}/tcp"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    bind_part = proc.stdout.strip().splitlines()[-1].strip()
    if not bind_part.startswith(f"{_loopback_bind_host()}:"):
        return None
    try:
        return int(bind_part.rsplit(":", 1)[1])
    except ValueError:
        return None


def _wait_until_ready(assigned_port: int) -> bool:
    deadline = time.monotonic() + _REGISTRY_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://{_loopback_probe_host()}:{assigned_port}/v2/", timeout=2
            ) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.25)
    return False


def _cleanup_registry(container_id: str) -> bool:
    """Remove the registry container and its anonymous data volume, then verify."""
    proc = subprocess.run(
        ["docker", "rm", "-f", "-v", container_id],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        return False
    verify = subprocess.run(
        ["docker", "inspect", container_id],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return verify.returncode != 0


def _reproduce_oci_layout(tmp: Path) -> tuple[bytes, bytes, list[bytes]]:
    """Reproduce the frozen OCI layout and return its exact manifest, config,
    and layer bytes.

    Re-runs the builder's own frozen build machinery (fixed
    builder/output/media-type/compression/attestation parameters and the
    builder-identity assert) so the exact manifest bytes live in exactly one
    place; reproduction exists solely to obtain the bytes to push.

    The layout is deterministically normalized (SPEC_PROCESS 86) before
    the bytes are read: pushing the raw buildkit layout would carry
    wall-clock layer mtimes and drift the pushed digest away from the
    frozen build-evidence identity.
    """
    context = tmp / "context"
    output_tar = tmp / "output.tar"
    context.mkdir()
    (context / "Dockerfile").write_bytes(_read_required(REPO_ROOT / RECIPE_RELATIVE))
    shutil.copytree(REPO_ROOT / FIXTURE_RELATIVE, context / "fixture")
    (context / "requirements.lock").write_bytes(
        _read_required(REPO_ROOT / REFERENCE_LOCK_RELATIVE)
    )
    _run_docker_build(context, output_tar)
    normalize_layout_tar(output_tar)
    layout = output_tar.with_name(f"{output_tar.name}.layout")
    _, manifest_bytes = _read_single_manifest(layout)
    _, config_bytes, layer_bytes, _ = _read_members(layout, manifest_bytes)
    return manifest_bytes, config_bytes, layer_bytes


def _push_exact_manifest(
    port: int,
    manifest_bytes: bytes,
    config_bytes: bytes,
    layer_bytes: Sequence[bytes],
) -> str:
    """Push the exact manifest and blob bytes; return the observed token.

    The digest token is observed from the registry's ``Docker-Content-Digest``
    response header without normalization.
    """
    base_url = _registry_base_url(port)
    for blob in (config_bytes, *layer_bytes):
        upload_url = _blob_upload_start(base_url)
        digest = f"{_SHA256_PREFIX}{_sha256_hex(blob)}"
        separator = "&" if "?" in upload_url else "?"
        status, _, _ = _registry_request(
            f"{upload_url}{separator}digest={digest}",
            method="PUT",
            body=blob,
            content_type="application/octet-stream",
        )
        if status != 201:
            raise RuntimeError(f"blob upload failed with HTTP {status}")
    status, headers, _ = _registry_request(
        f"{base_url}/manifests/{PUSH_TAG}",
        method="PUT",
        body=manifest_bytes,
        content_type=MANIFEST_MEDIA_TYPE,
    )
    if status != 201:
        raise RuntimeError(f"manifest push failed with HTTP {status}")
    return _digest_token(headers.get(_DIGEST_HEADER))


def _blob_upload_start(base_url: str) -> str:
    status, headers, _ = _registry_request(f"{base_url}/blobs/uploads/", method="POST")
    if status != 202:
        raise RuntimeError(f"blob upload start failed with HTTP {status}")
    location = headers.get("location")
    if not location:
        raise RuntimeError("blob upload start returned no Location header")
    return urllib.parse.urljoin(f"{base_url}/", location)


def _pull_manifest_by_digest(port: int, digest_token: str) -> tuple[str, bytes]:
    """Pull the manifest by digest; return the observed token and raw bytes.

    Fails closed unless the pulled bytes re-hash to the observed token, so
    the digest-pull RepoDigest is bound to the actual pulled manifest.
    """
    url = f"{_registry_base_url(port)}/manifests/{_SHA256_PREFIX}{digest_token}"
    status, headers, body = _registry_request(
        url, method="GET", accept=MANIFEST_MEDIA_TYPE
    )
    if status != 200:
        raise RuntimeError(f"digest pull failed with HTTP {status}")
    token = _digest_token(headers.get(_DIGEST_HEADER))
    if _sha256_hex(body) != token:
        raise RuntimeError("digest pull bytes do not match the observed RepoDigest")
    return token, body


def _registry_request(
    url: str,
    *,
    method: str,
    body: bytes | None = None,
    content_type: str | None = None,
    accept: str | None = None,
) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, data=body, method=method)
    if content_type is not None:
        request.add_header("Content-Type", content_type)
    if accept is not None:
        request.add_header("Accept", accept)
    try:
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_SECONDS) as response:
            return response.status, _header_map(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        headers = exc.headers if exc.headers is not None else {}
        return exc.code, _header_map(headers), exc.read()


def _header_map(message: Message) -> dict[str, str]:
    """Flatten HTTP headers into a case-insensitive lookup map."""
    return {name.lower(): value for name, value in message.items()}


def _digest_token(value: str | None) -> str:
    """Return the digest token exactly as observed, without normalization.

    A strict ``sha256:`` prefix is parsed once at observation time; every
    other observed form (case, whitespace, prefix, length) is preserved as-is
    so later raw byte comparison rejects it.
    """
    if value is None:
        raise RuntimeError("registry response missing Docker-Content-Digest")
    if value.startswith(_SHA256_PREFIX):
        return value[len(_SHA256_PREFIX) :]
    return value


def _digests_byte_identical(local: str, registry: str, pull: str) -> bool:
    """True only when the three raw observed digest byte strings are equal."""
    local_bytes = local.encode("utf-8")
    registry_bytes = registry.encode("utf-8")
    pull_bytes = pull.encode("utf-8")
    return local_bytes == registry_bytes and registry_bytes == pull_bytes
