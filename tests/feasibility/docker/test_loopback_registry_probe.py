"""T02.2 step 2.C: loopback registry round-trip and three-way digest."""

from __future__ import annotations

import dataclasses
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from spikes.docker_reference_boundary import registry_probe
from spikes.docker_reference_boundary.image_builder import (
    ReferenceImageBuildEvidenceV1,
    build_reference_image,
)
from spikes.docker_reference_boundary.input_contract import (
    REGISTRY_IMAGE_DIGEST,
    freeze_reference_build_input,
)
from spikes.docker_reference_boundary.registry_probe import (
    LoopbackRegistryDigestMismatchV1,
    LoopbackRegistryEvidenceV1,
    probe_loopback_registry,
)


def reference_root() -> Path:
    return Path(__file__).resolve().parents[3]


def transformed_registry_fixture() -> ReferenceImageBuildEvidenceV1:
    """A real frozen build evidence whose local manifest digest is transformed.

    The probe reproduces the exact manifest, pushes it, and pulls it by
    digest; the registry and digest-pull digests are therefore the real ones,
    and the transformed local digest is the only differing observed digest.
    """
    build = build_reference_image(freeze_reference_build_input(reference_root()))
    local_digest = build.local_oci_manifest_digest
    transformed = ("0" if local_digest[0] != "0" else "1") + local_digest[1:]
    return dataclasses.replace(build, local_oci_manifest_digest=transformed)


@pytest.fixture(scope="module")
def build_evidence() -> ReferenceImageBuildEvidenceV1:
    return build_reference_image(freeze_reference_build_input(reference_root()))


def test_registry_digest_transformation_fails() -> None:
    with pytest.raises(LoopbackRegistryDigestMismatchV1) as captured:
        probe_loopback_registry(transformed_registry_fixture())

    rejection = captured.value
    assert rejection.error_code == "OCI_REGISTRY_DIGEST_MISMATCH"
    assert rejection.external_push_count == 0
    assert rejection.cleanup_verified is True
    assert rejection.accepted_evidence_returned is False


def test_loopback_registry_roundtrip_preserves_three_way_digest(
    build_evidence: ReferenceImageBuildEvidenceV1,
) -> None:
    result = probe_loopback_registry(build_evidence)
    assert result.registry_image_digest == REGISTRY_IMAGE_DIGEST
    assert result.bind_host == "127.0.0.1"
    assert result.assigned_port > 0
    assert result.credentials_used is False
    assert result.external_push_count == 0
    assert result.local_oci_manifest_digest == build_evidence.local_oci_manifest_digest
    assert result.registry_repo_digest == build_evidence.local_oci_manifest_digest
    assert result.digest_pull_repo_digest == build_evidence.local_oci_manifest_digest
    assert result.cleanup_verified is True


def test_cleanup_registry_removes_anonymous_volume_and_verifies_container_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    results: Iterator[subprocess.CompletedProcess[str]] = iter(
        [
            subprocess.CompletedProcess[str](args=[], returncode=0),
            subprocess.CompletedProcess[str](args=[], returncode=1),
        ]
    )

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return next(results)

    monkeypatch.setattr(subprocess, "run", run)

    assert registry_probe._cleanup_registry("registry-container") is True
    assert calls == [
        ["docker", "rm", "-f", "-v", "registry-container"],
        ["docker", "inspect", "registry-container"],
    ]


def test_cleanup_registry_remove_failure_is_not_reported_as_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess[str](args=argv, returncode=1)

    monkeypatch.setattr(subprocess, "run", run)

    assert registry_probe._cleanup_registry("registry-container") is False
    assert calls == [["docker", "rm", "-f", "-v", "registry-container"]]


def _assert_exact_rejection(rejection: LoopbackRegistryDigestMismatchV1) -> None:
    assert rejection.error_code == "OCI_REGISTRY_DIGEST_MISMATCH"
    assert rejection.external_push_count == 0
    assert rejection.cleanup_verified is True
    assert rejection.accepted_evidence_returned is False


def test_loopback_registry_boundary_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exact local/registry/pull digests return one immutable evidence; any
    observed digest transformation raises the exact rejection after verified
    cleanup; credential, external bind/push, cleanup, and injected-failure
    cases close deterministically."""
    exact_digest = "ab" * 32
    build = ReferenceImageBuildEvidenceV1(
        local_oci_manifest_digest=exact_digest,
        image_config_digest="cd" * 32,
        recipe_digest="ef" * 32,
        platform="linux/amd64",
        self_reference_scan_passed=True,
    )
    transformed_local = ("0" if exact_digest[0] != "0" else "1") + exact_digest[1:]

    monkeypatch.setattr(
        registry_probe, "_start_loopback_registry", lambda: ("fake-container", 54321)
    )
    monkeypatch.setattr(
        registry_probe,
        "_reproduce_oci_layout",
        lambda tmp: (b'{"schemaVersion":2}', b"{}", [b"layer"]),
    )
    monkeypatch.setattr(
        registry_probe,
        "_pull_manifest_by_digest",
        lambda port, digest: (digest, b'{"schemaVersion":2}'),
    )

    # Row 1: exact local/registry/pull digests return one immutable evidence.
    monkeypatch.setattr(
        registry_probe,
        "_push_exact_manifest",
        lambda port, manifest, config, layers: exact_digest,
    )
    monkeypatch.setattr(registry_probe, "_cleanup_registry", lambda container_id: True)
    result = probe_loopback_registry(build)
    assert result == LoopbackRegistryEvidenceV1(
        registry_image_digest=REGISTRY_IMAGE_DIGEST,
        bind_host="127.0.0.1",
        assigned_port=54321,
        credentials_used=False,
        external_push_count=0,
        local_oci_manifest_digest=exact_digest,
        registry_repo_digest=exact_digest,
        digest_pull_repo_digest=exact_digest,
        cleanup_verified=True,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.assigned_port = 1  # type: ignore[misc]

    # Row 2: a transformed local digest is rejected after verified cleanup.
    transformed_build = dataclasses.replace(
        build, local_oci_manifest_digest=transformed_local
    )
    with pytest.raises(LoopbackRegistryDigestMismatchV1) as local_rejection:
        probe_loopback_registry(transformed_build)
    _assert_exact_rejection(local_rejection.value)

    # Row 3: a transformed registry digest (raw case preserved) is rejected.
    monkeypatch.setattr(
        registry_probe,
        "_push_exact_manifest",
        lambda port, manifest, config, layers: exact_digest.upper(),
    )
    with pytest.raises(LoopbackRegistryDigestMismatchV1) as registry_rejection:
        probe_loopback_registry(build)
    _assert_exact_rejection(registry_rejection.value)

    # Row 4: a transformed digest-pull digest (raw whitespace preserved) is
    # rejected.
    monkeypatch.setattr(
        registry_probe,
        "_push_exact_manifest",
        lambda port, manifest, config, layers: exact_digest,
    )
    monkeypatch.setattr(
        registry_probe,
        "_pull_manifest_by_digest",
        lambda port, digest: (digest + " ", b'{"schemaVersion":2}'),
    )
    with pytest.raises(LoopbackRegistryDigestMismatchV1) as pull_rejection:
        probe_loopback_registry(build)
    _assert_exact_rejection(pull_rejection.value)

    # Row 5: unverified cleanup closes deterministically on the success path
    # with no evidence and no rejection claim.
    monkeypatch.setattr(
        registry_probe,
        "_pull_manifest_by_digest",
        lambda port, digest: (digest, b'{"schemaVersion":2}'),
    )
    monkeypatch.setattr(registry_probe, "_cleanup_registry", lambda container_id: False)
    with pytest.raises(RuntimeError, match="cleanup"):
        probe_loopback_registry(build)

    # Row 6: unverified cleanup closes deterministically on the injected
    # failure path before any rejection is claimed.
    monkeypatch.setattr(
        registry_probe,
        "_push_exact_manifest",
        lambda port, manifest, config, layers: exact_digest.upper(),
    )
    with pytest.raises(RuntimeError, match="cleanup"):
        probe_loopback_registry(build)

    # Row 7: the registry starts credential-free with the frozen image
    # identity, bound only to loopback.
    run_argv = registry_probe._registry_run_argv()
    assert run_argv == [
        "docker",
        "run",
        "-d",
        "-p",
        "127.0.0.1::5000",
        f"registry:2@sha256:{REGISTRY_IMAGE_DIGEST}",
    ]
    assert registry_probe.REGISTRY_IMAGE_REF == (
        f"registry:2@sha256:{REGISTRY_IMAGE_DIGEST}"
    )

    # Row 8: the push targets only the loopback registry and never counts an
    # external push.
    assert (
        registry_probe._registry_base_url(54321)
        == "http://127.0.0.1:54321/v2/vesper-reference"
    )

    # Row 9: observed digest tokens are preserved raw, without normalization.
    assert registry_probe._digest_token(f"sha256:{exact_digest}") == exact_digest
    assert (
        registry_probe._digest_token("SHA256:" + exact_digest)
        == "SHA256:" + exact_digest
    )
    assert (
        registry_probe._digest_token(f"sha256:{exact_digest.upper()}")
        == exact_digest.upper()
    )
    assert (
        registry_probe._digest_token(" sha256:" + exact_digest)
        == " sha256:" + exact_digest
    )
    with pytest.raises(RuntimeError, match="Docker-Content-Digest"):
        registry_probe._digest_token(None)
