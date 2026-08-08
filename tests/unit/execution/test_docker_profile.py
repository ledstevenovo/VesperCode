"""T18.1 legacy step 18.A: Docker execution profile/readiness domain tests.

Closed argv, environment-whitelist, resource-limit, execution-profile,
and readiness-result contracts, the frozen-built-in binding of
``ExecutionRequestV1``, and the real SDK probe's digest extraction run
deterministically offline with no Docker daemon or container (GREEN-1,
GREEN-2, GREEN-4).
"""

from __future__ import annotations

from pathlib import Path

import pytest

# The execution contracts are pydantic runtime contracts; the hash-locked
# gate toolchain does not install runtime dependencies, so this module
# skips cleanly there instead of failing at collection (formal env runs
# it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.execution.docker_profile import (
    DockerDaemonUnavailableErrorV1,
    DockerEnvironmentV1,
    DockerExecutionProfileV1,
    DockerReadinessService,
    DockerResourceLimitsV1,
    DockerSDKImageProbeV1,
    ExecutionArgumentSequenceV1,
    ExecutionReadinessResultV1,
    ExecutionRequestV1,
)
from vespercode.profiles.reference import (
    ReferenceProfileManifestV1,
    load_reference_profile,
)

# The frozen T02.4 manifest identity (SPEC §1.4.1/§1.4.5).
_MANIFEST_DIGEST = "841e9d55359c4007cd53b4b50a2ff10572b955650847bfb545ea2f4aa661443b"
_IMAGE_DIGEST = "71e931b58316637d1cbe647a57fc4c3588837f9451f7fbad391c34b3b1b43905"


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


def builtin_environment_dict() -> dict[str, list[dict[str, str]]]:
    """The exact profile v1 environment whitelist (SPEC §1.4.5)."""
    return {
        "variables": [
            {"name": "LANG", "value": "C.UTF-8"},
            {"name": "LC_ALL", "value": "C.UTF-8"},
            {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
            {"name": "PYTHONHASHSEED", "value": "0"},
            {"name": "TZ", "value": "UTC"},
        ]
    }


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
        "docker_execution_profile_version": 1,
        "profile": builtin_profile_dict(),
        "argv": {"arguments": ("python", "-m", "pytest", "-q")},
    }


def test_execution_argument_sequence_contract() -> None:
    argv = ExecutionArgumentSequenceV1.model_validate(
        {"arguments": ("python", "-m", "pytest", "-q")}
    )
    assert argv.arguments == ("python", "-m", "pytest", "-q")
    from_list = ExecutionArgumentSequenceV1.model_validate(
        {"arguments": ["pytest", "-q"]}
    )
    assert from_list.arguments == ("pytest", "-q")
    with pytest.raises(ValidationError):
        argv.arguments = ("pytest",)
    for payload in [
        {"arguments": ()},
        {"arguments": ("python", "")},
        {"arguments": ("python", 42)},
        {"arguments": ("python",), "executable": "python"},
    ]:
        with pytest.raises(ValidationError):
            ExecutionArgumentSequenceV1.model_validate(payload)


def test_environment_whitelist_contract() -> None:
    environment = DockerEnvironmentV1.model_validate(builtin_environment_dict())
    names = [variable.name for variable in environment.variables]
    assert names == [
        "LANG",
        "LC_ALL",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONHASHSEED",
        "TZ",
    ]
    # Any input order of the exact whitelist is the same closed set.
    reversed_environment = DockerEnvironmentV1.model_validate(
        {"variables": list(reversed(builtin_environment_dict()["variables"]))}
    )
    assert {v.name for v in reversed_environment.variables} == set(names)
    for payload in [
        {
            "variables": [
                *builtin_environment_dict()["variables"],
                {"name": "EXTRA_VAR", "value": "1"},
            ]
        },
        {
            "variables": [
                {"name": "LANG", "value": "C.UTF-8"},
                {"name": "LC_ALL", "value": "C.UTF-8"},
                {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
                {"name": "PYTHONHASHSEED", "value": "1"},
                {"name": "TZ", "value": "UTC"},
            ]
        },
        {
            "variables": [
                {"name": "LANG", "value": "C.UTF-8"},
                {"name": "LC_ALL", "value": "C.UTF-8"},
                {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
                {"name": "PYTHONHASHSEED", "value": "0"},
            ]
        },
        {
            "variables": [
                {"name": "LANG", "value": "C.UTF-8"},
                {"name": "LC_ALL", "value": "C.UTF-8"},
                {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
                {"name": "PYTHONHASHSEED", "value": "0"},
                {"name": "TZ", "value": "UTC"},
                {"name": "TZ", "value": "UTC"},
            ]
        },
        {
            "variables": [
                {"name": "LANG", "value": "C.UTF-8"},
                {"name": "LC_ALL", "value": "C.UTF-8"},
                {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
                {"name": "PYTHONHASHSEED", "value": 0},
                {"name": "TZ", "value": "UTC"},
            ]
        },
    ]:
        with pytest.raises(ValidationError):
            DockerEnvironmentV1.model_validate(payload)


def test_resource_limits_contract() -> None:
    resources = DockerResourceLimitsV1.model_validate(builtin_resources_dict())
    assert resources.cpus == 2
    assert resources.memory_bytes == 2 * 1024**3
    assert resources.pids_limit == 256
    assert resources.tmpfs_size_bytes == 256 * 1024**2
    assert resources.max_output_bytes == 4 * 1024**2
    drift_cases: list[dict[str, object]] = [
        {"cpus": 3},
        {"memory_bytes": 1024**3},
        {"pids_limit": 255},
        {"pids_limit": 257},
        {"tmpfs_size_bytes": 128 * 1024**2},
        {"max_output_bytes": 4 * 1024**2 + 1},
    ]
    for drift in drift_cases:
        with pytest.raises(ValidationError):
            DockerResourceLimitsV1.model_validate({**builtin_resources_dict(), **drift})
    confused_cases: list[dict[str, object]] = [
        {"cpus": True},
        {"memory_bytes": 2147483648.0},
        {"pids_limit": "256"},
    ]
    for confused in confused_cases:
        with pytest.raises(ValidationError):
            DockerResourceLimitsV1.model_validate(
                {**builtin_resources_dict(), **confused}
            )


def test_execution_profile_contract() -> None:
    profile = DockerExecutionProfileV1.model_validate(builtin_profile_dict())
    assert profile.profile_version == 1
    assert profile.network_mode == "none"
    assert profile.user == "10001:10001"
    assert profile.read_only_rootfs is True
    assert profile.capabilities_dropped == "ALL"
    assert profile.docker_socket_mounted is False
    assert profile.workdir == "/workspace"
    assert profile.workspace_mount.target == "/workspace"
    assert profile.workspace_mount.read_only is True
    assert profile.tmpfs_mount.path == "/tmp"
    assert profile.fresh_container_per_check is True
    assert profile.pytest_plugin_autoload_disabled is True
    profile_drift_cases: list[dict[str, object]] = [
        {"network_mode": "bridge"},
        {"user": "root"},
        {"read_only_rootfs": False},
        {"capabilities_dropped": "FOWNER"},
        {"docker_socket_mounted": True},
        {"workdir": "/app"},
        {"workspace_mount": {"target": "/workspace", "read_only": False}},
        {"workspace_mount": {"target": "/work", "read_only": True}},
        {"tmpfs_mount": {"path": "/var/tmp"}},
        {"fresh_container_per_check": False},
        {"pytest_plugin_autoload_disabled": False},
        {"profile_version": 2},
        {"schema_version": 2},
    ]
    for drift in profile_drift_cases:
        with pytest.raises(ValidationError):
            DockerExecutionProfileV1.model_validate({**builtin_profile_dict(), **drift})
    profile_confused_cases: list[dict[str, object]] = [
        {"schema_version": True},
        {"schema_version": 1.0},
        {"schema_version": "1"},
        {"profile_version": True},
        {"read_only_rootfs": 1},
        {"docker_socket_mounted": 1},
    ]
    for confused in profile_confused_cases:
        with pytest.raises(ValidationError):
            DockerExecutionProfileV1.model_validate(
                {**builtin_profile_dict(), **confused}
            )


def test_execution_request_binds_frozen_manifest() -> None:
    manifest = frozen_reference_manifest()
    payload = {
        **builtin_request_dict(),
        "reference_profile_digest": manifest.digest,
        "docker_image_digest": manifest.docker_image_digest,
        "docker_execution_profile_version": manifest.docker_execution_profile_version,
    }
    request = ExecutionRequestV1.model_validate(payload)
    assert request.reference_profile_digest == _MANIFEST_DIGEST
    assert request.docker_image_digest == _IMAGE_DIGEST
    assert request.profile.profile_version == manifest.docker_execution_profile_version


def test_readiness_result_contract() -> None:
    ready = ExecutionReadinessResultV1(
        status="READY",
        reference_profile_digest=_MANIFEST_DIGEST,
        docker_image_digest=_IMAGE_DIGEST,
        reason=AbsentV1(kind="ABSENT"),
    )
    assert ready.status == "READY"
    assert ready.reason.kind == "ABSENT"
    not_ready = ExecutionReadinessResultV1(
        status="NOT_READY",
        reference_profile_digest=_MANIFEST_DIGEST,
        docker_image_digest=_IMAGE_DIGEST,
        reason=PresentV1(kind="PRESENT", value="IMAGE_NOT_FOUND"),
    )
    assert not_ready.reason.kind == "PRESENT"
    for payload in [
        {
            "status": "READY",
            "reference_profile_digest": _MANIFEST_DIGEST,
            "docker_image_digest": _IMAGE_DIGEST,
            "reason": PresentV1(kind="PRESENT", value="IMAGE_NOT_FOUND"),
        },
        {
            "status": "NOT_READY",
            "reference_profile_digest": _MANIFEST_DIGEST,
            "docker_image_digest": _IMAGE_DIGEST,
            "reason": AbsentV1(kind="ABSENT"),
        },
        {
            "status": "PARTIAL",
            "reference_profile_digest": _MANIFEST_DIGEST,
            "docker_image_digest": _IMAGE_DIGEST,
            "reason": AbsentV1(kind="ABSENT"),
        },
        {
            "status": "NOT_READY",
            "reference_profile_digest": _MANIFEST_DIGEST,
            "docker_image_digest": _IMAGE_DIGEST,
            "reason": PresentV1(kind="PRESENT", value="DAEMON_GONE"),
        },
        {
            "status": "NOT_READY",
            "reference_profile_digest": "x" * 64,
            "docker_image_digest": _IMAGE_DIGEST,
            "reason": AbsentV1(kind="ABSENT"),
        },
        {
            "status": "NOT_READY",
            "reference_profile_digest": _MANIFEST_DIGEST,
            "docker_image_digest": _IMAGE_DIGEST,
            "reason": AbsentV1(kind="ABSENT"),
            "extra": "field",
        },
    ]:
        with pytest.raises(ValidationError):
            ExecutionReadinessResultV1.model_validate(payload)


class _FakeDockerClient:
    """Minimal structural fake of the Docker SDK list-images surface."""

    def __init__(self, images: list[dict[str, object]]) -> None:
        self._images = images

    @property
    def api(self) -> _FakeDockerClient:
        return self

    def images(self, all: bool = False) -> list[dict[str, object]]:
        return self._images


def test_docker_sdk_probe_extracts_frozen_digests() -> None:
    fake = _FakeDockerClient(
        [
            {
                "Id": f"sha256:{_IMAGE_DIGEST}",
                "RepoDigests": [
                    f"ghcr.io/ledstevenovo/vespercode-reference@sha256:{_IMAGE_DIGEST}"
                ],
            },
            {
                "Id": "sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de",
                "RepoDigests": [
                    "python@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de",
                    "not-a-digest-token",
                ],
            },
            {"Id": "sha256:1234", "RepoDigests": []},
            {"Id": "", "RepoDigests": []},
        ]
    )
    probe = DockerSDKImageProbeV1(client_factory=lambda: fake)
    digests = probe.local_image_digests()
    assert _IMAGE_DIGEST in digests
    assert "57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de" in digests
    assert "1234" not in digests
    assert len(digests) == 2


class _BoomFactory:
    def __call__(self) -> _FakeDockerClient:
        raise RuntimeError("daemon unreachable")


def test_docker_sdk_probe_daemon_unavailable() -> None:
    probe = DockerSDKImageProbeV1(client_factory=_BoomFactory())
    with pytest.raises(DockerDaemonUnavailableErrorV1):
        probe.local_image_digests()


class _NeverReachedProbe:
    """Probe that must never be called after a manifest drift verdict."""

    def local_image_digests(self) -> frozenset[str]:
        raise AssertionError("probe must not run after a drift verdict")


def test_readiness_verifies_manifest_before_daemon() -> None:
    manifest = frozen_reference_manifest()
    stale = manifest.model_copy(update={"mypy_version": "2.3.1"})
    result = DockerReadinessService(probe=_NeverReachedProbe()).verify(stale)
    assert result.status == "NOT_READY"
    assert isinstance(result.reason, PresentV1)
    assert result.reason.value == "MANIFEST_DIGEST_MISMATCH"
