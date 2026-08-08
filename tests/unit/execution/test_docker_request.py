"""T18.1 legacy step 18.A: closed Docker execution request tests.

The card's exact RED test and the 18.A profile/readiness matrix: only
the frozen adapter-built executable/argv/env/workdir/mount/resource
fields validate inside ``ExecutionRequestV1``; model executable/argv,
unknown profile, widened env, and failed readiness are rejected before
any container creation (GREEN-2/GREEN-3).  The card Target runs the
exact RED test and the Matrix runs
``test_execution_request_profile_readiness_matrix``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# The execution request is a pydantic runtime contract; the hash-locked
# gate toolchain does not install runtime dependencies, so this module
# skips cleanly there instead of failing at collection (formal env runs
# it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.contracts.optional import PresentV1
from vespercode.execution.docker_profile import (
    DockerDaemonUnavailableErrorV1,
    DockerReadinessService,
    ExecutionRequestV1,
    LocalImageDigestProbeV1,
)
from vespercode.profiles.reference import (
    ReferenceProfileManifestV1,
    _compute_manifest_digest,
    load_reference_profile,
)

# The frozen T02.4 manifest identity (SPEC §1.4.1/§1.4.5): the §0.1 digest
# and the bound docker image digest of
# reference/manifest/reference-profile-v1.json, independently recomputed
# by the T06.2 review stages.
_MANIFEST_DIGEST = "b02bfc24c91b0013bc466e14b9f133d4d7e89e08c738980c6bbffd18ee8b0048"
_IMAGE_DIGEST = "86443f5297b268f0cd8046b09652acb3b6b1d7e4275a743c34e7908bf1d7156d"
_PROFILE_VERSION = 1

# The exact profile v1 environment whitelist (SPEC §1.4.5), shown in a
# non-canonical input order to pin order-insensitive validation.
_ENVIRONMENT_VARIABLES = (
    {"name": "TZ", "value": "UTC"},
    {"name": "PYTHONHASHSEED", "value": "0"},
    {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
    {"name": "LC_ALL", "value": "C.UTF-8"},
    {"name": "LANG", "value": "C.UTF-8"},
)


def packaged_reference_profile_bytes() -> bytes:
    """The packaged production manifest bytes (the frozen GO identity)."""
    path = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "vespercode"
        / "profiles"
        / "builtin"
        / "reference-profile-v1.json"
    )
    return path.read_bytes()


def frozen_reference_manifest() -> ReferenceProfileManifestV1:
    """The exact frozen production manifest (T02.4 bytes, T06.2 verified)."""
    return load_reference_profile(packaged_reference_profile_bytes())


def builtin_environment_dict() -> dict[str, object]:
    """The exact profile v1 environment whitelist (SPEC §1.4.5)."""
    return {"variables": list(_ENVIRONMENT_VARIABLES)}


def builtin_resources_dict() -> dict[str, object]:
    """The exact profile v1 resource limits (SPEC §1.4.5)."""
    return {
        "cpus": 2,
        "memory_bytes": 2 * 1024**3,
        "pids_limit": 256,
        "tmpfs_size_bytes": 256 * 1024**2,
        "max_output_bytes": 4 * 1024**2,
    }


def builtin_profile_dict() -> dict[str, object]:
    """The exact frozen Docker execution profile v1 (SPEC §1.4.5)."""
    return {
        "schema_version": 1,
        "profile_version": 1,
        "network_mode": "none",
        "user": "10001:10001",
        "read_only_rootfs": True,
        "capabilities_dropped": "ALL",
        "docker_socket_mounted": False,
        "workdir": "/workspace",
        "workspace_mount": {"target": "/workspace", "read_only": True},
        "tmpfs_mount": {"path": "/tmp"},
        "resources": builtin_resources_dict(),
        "environment": builtin_environment_dict(),
        "fresh_container_per_check": True,
        "pytest_plugin_autoload_disabled": True,
    }


def builtin_request_dict() -> dict[str, object]:
    """The canonical valid request: frozen built-ins plus adapter argv."""
    return {
        "schema_version": 1,
        "request_id": "req-18-a-1",
        "reference_profile_digest": _MANIFEST_DIGEST,
        "docker_image_digest": _IMAGE_DIGEST,
        "docker_execution_profile_version": _PROFILE_VERSION,
        "profile": builtin_profile_dict(),
        "argv": {"arguments": ("python", "-m", "pytest", "-q")},
    }


def request_with_executable() -> dict[str, object]:
    """The smallest forbidden model-supplied field: an executable key."""
    return {**builtin_request_dict(), "executable": "/bin/rm"}


def test_execution_request_rejects_model_executable_field() -> None:
    with pytest.raises(ValidationError):
        ExecutionRequestV1.model_validate(request_with_executable())


class _FakeProbe:
    """Injected readiness probe returning a fixed local digest set."""

    def __init__(self, digests: frozenset[str]) -> None:
        self._digests = digests

    def local_image_digests(self) -> frozenset[str]:
        return self._digests


class _FailingProbe:
    """Injected readiness probe whose daemon is unreachable."""

    def local_image_digests(self) -> frozenset[str]:
        raise DockerDaemonUnavailableErrorV1("daemon down")


def test_execution_request_profile_readiness_matrix() -> None:
    """18.A matrix (PLAN 18.A): the closed request/readiness behavior.

    Only the adapter-built frozen executable/argv/env/workdir/mount/
    resource fields validate; model executable/argv, unknown profile,
    widened env, and failed readiness are rejected before Docker, and the
    exact frozen manifest plus a matching local image digest is READY.
    """
    request = ExecutionRequestV1.model_validate(builtin_request_dict())
    assert request.reference_profile_digest == _MANIFEST_DIGEST
    assert request.docker_image_digest == _IMAGE_DIGEST
    assert request.docker_execution_profile_version == _PROFILE_VERSION
    assert request.argv.arguments == ("python", "-m", "pytest", "-q")
    with pytest.raises(ValidationError):
        request.argv.arguments = ("rm", "-rf", "/")

    rejected = [
        ("model executable field", request_with_executable()),
        (
            "model argv as shell string",
            {**builtin_request_dict(), "argv": "python -m pytest"},
        ),
        ("empty argv", {**builtin_request_dict(), "argv": {"arguments": ()}}),
        (
            "empty-string argv element",
            {**builtin_request_dict(), "argv": {"arguments": ("python", "")}},
        ),
        (
            "non-string argv element",
            {**builtin_request_dict(), "argv": {"arguments": ("python", 42)}},
        ),
        (
            "unknown reference profile digest",
            {**builtin_request_dict(), "reference_profile_digest": "0" * 64},
        ),
        (
            "missing reference profile digest",
            {
                key: value
                for key, value in builtin_request_dict().items()
                if key != "reference_profile_digest"
            },
        ),
        (
            "unknown docker image digest",
            {**builtin_request_dict(), "docker_image_digest": "0" * 64},
        ),
        (
            "execution profile version drift",
            {**builtin_request_dict(), "docker_execution_profile_version": 2},
        ),
        (
            "widened environment",
            {
                **builtin_request_dict(),
                "profile": {
                    **builtin_profile_dict(),
                    "environment": {
                        "variables": [
                            {"name": "LANG", "value": "C.UTF-8"},
                            {"name": "LC_ALL", "value": "C.UTF-8"},
                            {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
                            {"name": "PYTHONHASHSEED", "value": "0"},
                            {"name": "TZ", "value": "UTC"},
                            {"name": "EXTRA_VAR", "value": "1"},
                        ]
                    },
                },
            },
        ),
        (
            "environment value drift",
            {
                **builtin_request_dict(),
                "profile": {
                    **builtin_profile_dict(),
                    "environment": {
                        "variables": [
                            {"name": "LANG", "value": "C.UTF-8"},
                            {"name": "LC_ALL", "value": "C.UTF-8"},
                            {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
                            {"name": "PYTHONHASHSEED", "value": "1"},
                            {"name": "TZ", "value": "UTC"},
                        ]
                    },
                },
            },
        ),
        (
            "resource limit drift",
            {
                **builtin_request_dict(),
                "profile": {
                    **builtin_profile_dict(),
                    "resources": {**builtin_resources_dict(), "cpus": 3},
                },
            },
        ),
        (
            "writable workspace mount",
            {
                **builtin_request_dict(),
                "profile": {
                    **builtin_profile_dict(),
                    "workspace_mount": {"target": "/workspace", "read_only": False},
                },
            },
        ),
        (
            "docker socket mount",
            {
                **builtin_request_dict(),
                "profile": {**builtin_profile_dict(), "docker_socket_mounted": True},
            },
        ),
        (
            "model-supplied shell field",
            {**builtin_request_dict(), "shell": "/bin/sh -c pytest"},
        ),
    ]
    for label, payload in rejected:
        with pytest.raises(ValidationError):
            ExecutionRequestV1.model_validate(payload)
        assert isinstance(label, str)

    manifest = frozen_reference_manifest()

    ready = DockerReadinessService(probe=_FakeProbe(frozenset({_IMAGE_DIGEST}))).verify(
        manifest
    )
    assert ready.status == "READY"
    assert ready.reason.kind == "ABSENT"
    assert ready.reference_profile_digest == _MANIFEST_DIGEST
    assert ready.docker_image_digest == _IMAGE_DIGEST

    readiness_cases: list[tuple[str, LocalImageDigestProbeV1, str]] = [
        ("daemon unavailable", _FailingProbe(), "DAEMON_UNAVAILABLE"),
        ("image not found", _FakeProbe(frozenset()), "IMAGE_NOT_FOUND"),
        (
            "image digest mismatch",
            _FakeProbe(frozenset({"0" * 64})),
            "IMAGE_DIGEST_MISMATCH",
        ),
    ]
    for label, probe, reason in readiness_cases:
        result = DockerReadinessService(probe=probe).verify(manifest)
        assert result.status == "NOT_READY", label
        assert isinstance(result.reason, PresentV1)
        assert result.reason.value == reason, label

    stale = manifest.model_copy(update={"mypy_version": "2.3.1"})
    stale_result = DockerReadinessService(
        probe=_FakeProbe(frozenset({_IMAGE_DIGEST}))
    ).verify(stale)
    assert stale_result.status == "NOT_READY"
    assert isinstance(stale_result.reason, PresentV1)
    assert stale_result.reason.value == "MANIFEST_DIGEST_MISMATCH"

    version_drift = manifest.model_copy(update={"docker_execution_profile_version": 2})
    version_drift = version_drift.model_copy(
        update={"digest": _compute_manifest_digest(version_drift)}
    )
    version_result = DockerReadinessService(
        probe=_FakeProbe(frozenset({_IMAGE_DIGEST}))
    ).verify(version_drift)
    assert version_result.status == "NOT_READY"
    assert isinstance(version_result.reason, PresentV1)
    assert version_result.reason.value == "EXECUTION_PROFILE_VERSION_MISMATCH"

    image_drift = manifest.model_copy(update={"docker_image_digest": "0" * 64})
    image_drift = image_drift.model_copy(
        update={"digest": _compute_manifest_digest(image_drift)}
    )
    image_result = DockerReadinessService(
        probe=_FakeProbe(frozenset({"0" * 64}))
    ).verify(image_drift)
    assert image_result.status == "NOT_READY"
    assert isinstance(image_result.reason, PresentV1)
    assert image_result.reason.value == "IMAGE_DIGEST_MISMATCH"

    non_frozen = manifest.model_copy(update={"mypy_version": "2.3.1"})
    non_frozen = non_frozen.model_copy(
        update={"digest": _compute_manifest_digest(non_frozen)}
    )
    non_frozen_result = DockerReadinessService(
        probe=_FakeProbe(frozenset({_IMAGE_DIGEST}))
    ).verify(non_frozen)
    assert non_frozen_result.status == "NOT_READY"
    assert isinstance(non_frozen_result.reason, PresentV1)
    assert non_frozen_result.reason.value == "MANIFEST_DIGEST_MISMATCH"
