"""T34.2 legacy step 34.A: reference fixture isolation smoke tests.

The fixture smoke proves the production executor/profile/fixture isolation
contract of the reproduced reference image (GREEN-2): one fresh frozen
container enforces the SPEC §1.4.5 boundary (non-root, no network, read-only
root and workspace, dropped capabilities, no Docker socket, bounded tmpfs,
2 CPU / 2 GiB / 256 PIDs), serves the frozen fixture bytes at /workspace,
carries the fixed pytest report channel through an explicitly loaded
lifecycle of the stable failing target, and the real production executor
runs the frozen built-in profile over a fresh materialized candidate root
(never the frozen fixture bytes), while the reproduced image carries no
self-reference and every container/registry/image cleanup is verified.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from scripts.run_reference_image_smoke import (
    ContainerIsolationEvidenceV1,
    FROZEN_TASK2_MANIFEST_DIGEST_V1,
    GatePytestReportV1,
    OCIImageInspection,
    ProductionExecutorEvidenceV1,
    TARGET_TEST_NODE_ID,
    load_reference_profile,
    packaged_reference_manifest_digest,
    task2_go_digest,
    validate_gate_pytest_report,
)
from vespercode.execution.docker_profile import ExecutionRequestV1

_REPO_ROOT: Final = Path(__file__).resolve().parents[3]
_PACKAGED_MANIFEST: Final = (
    _REPO_ROOT
    / "src"
    / "vespercode"
    / "profiles"
    / "builtin"
    / "reference-profile-v1.json"
)

_FROZEN_CPU_LIMIT: Final = 2
_FROZEN_MEMORY_LIMIT_BYTES: Final = 2 * 1024**3
_FROZEN_PID_LIMIT: Final = 256
_FROZEN_NON_ROOT_UID: Final = 10001
_FROZEN_WORKSPACE_WRITE_ERRNO: Final = 30  # EROFS

_BUILTIN_PROFILE_DICT_V1: dict[str, object] = {
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
    "resources": {
        "cpus": 2,
        "memory_bytes": 2 * 1024**3,
        "pids_limit": 256,
        "tmpfs_size_bytes": 256 * 1024**2,
        "max_output_bytes": 4 * 1024**2,
    },
    "environment": {
        "variables": [
            {"name": "LANG", "value": "C.UTF-8"},
            {"name": "LC_ALL", "value": "C.UTF-8"},
            {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
            {"name": "PYTHONHASHSEED", "value": "0"},
            {"name": "TZ", "value": "UTC"},
        ]
    },
    "fresh_container_per_check": True,
    "pytest_plugin_autoload_disabled": True,
}
"""The exact built-in profile v1 dict (the T18.2 builtin identity), used
only to prove the request contract rejects drifted profile bindings."""


@pytest.mark.oci_smoke
def test_reference_container_enforces_frozen_isolation_boundary(
    reference_isolation_evidence: ContainerIsolationEvidenceV1,
) -> None:
    """GREEN-2: one fresh reference container enforces every SPEC §1.4.5
    isolation control observed from inside and daemon-side, with verified
    cleanup."""
    evidence = reference_isolation_evidence
    assert evidence.network_disabled is True
    assert evidence.non_root is True
    assert evidence.root_read_only is True
    assert evidence.capabilities_dropped is True
    assert evidence.docker_socket_absent is True
    assert evidence.workspace_read_only is True
    assert evidence.tmpfs_bounded is True
    assert evidence.cpu_limit == _FROZEN_CPU_LIMIT
    assert evidence.memory_limit_bytes == _FROZEN_MEMORY_LIMIT_BYTES
    assert evidence.pid_limit == _FROZEN_PID_LIMIT
    assert evidence.cleanup_verified is True


@pytest.mark.oci_smoke
def test_reference_workspace_serves_frozen_fixture_bytes(
    reference_workspace_listing_evidence: tuple[str, ...],
) -> None:
    """GREEN-2: the frozen fixture tree is the container's read-only
    workspace — exactly pyproject.toml, requirements.lock, src, and tests."""
    assert set(reference_workspace_listing_evidence) == {
        "pyproject.toml",
        "requirements.lock",
        "src",
        "tests",
    }


@pytest.mark.oci_smoke
def test_reference_pytest_report_channel_completes(
    reference_pytest_report_evidence: GatePytestReportV1,
) -> None:
    """GREEN-2: the fixed report channel carries a complete explicitly
    loaded pytest lifecycle of the stable failing target (exit 1) inside
    one fresh reference container."""
    validated = validate_gate_pytest_report(reference_pytest_report_evidence)
    assert validated.passed is True
    assert validated.reason == "COMPLETE"
    assert reference_pytest_report_evidence.exit_code == 1
    assert reference_pytest_report_evidence.normal_end is True
    assert TARGET_TEST_NODE_ID in reference_pytest_report_evidence.collected_node_ids


@pytest.mark.oci_smoke
def test_production_profile_binds_reproduced_image() -> None:
    """GREEN-2: the packaged production profile verifies against the
    frozen Task 2.G gate identity and binds the reproduced image digest."""
    manifest = load_reference_profile(_PACKAGED_MANIFEST.read_bytes())
    assert manifest.docker_image_digest == task2_go_digest()
    assert manifest.docker_image_digest == packaged_reference_manifest_digest()
    assert manifest.docker_image_digest == FROZEN_TASK2_MANIFEST_DIGEST_V1
    assert manifest.docker_execution_profile_version == 1
    # The production request contract rejects any request not bound to the
    # frozen built-in reference profile/image identities.
    with pytest.raises(ValueError, match="frozen built-in reference profile"):
        ExecutionRequestV1.model_validate(
            {
                "schema_version": 1,
                "request_id": "req-34-a-drift",
                "reference_profile_digest": "aa" * 32,
                "docker_image_digest": manifest.docker_image_digest,
                "docker_execution_profile_version": 1,
                "profile": _BUILTIN_PROFILE_DICT_V1,
                "argv": {"arguments": ("python", "-c", "print('x')")},
            }
        )


@pytest.mark.oci_smoke
def test_production_executor_runs_frozen_profile_on_candidate_bytes(
    production_executor_evidence: ProductionExecutorEvidenceV1,
) -> None:
    """GREEN-2: the real production executor runs the frozen built-in
    profile over a fresh materialized candidate root — non-root uid,
    EROFS workspace write, exact candidate bytes, no error code, verified
    cleanup."""
    evidence = production_executor_evidence
    assert evidence.error_code is None
    assert evidence.exit_code == 0
    assert evidence.observed_uid == _FROZEN_NON_ROOT_UID
    assert evidence.workspace_write_errno == _FROZEN_WORKSPACE_WRITE_ERRNO
    assert evidence.candidate_bytes_match is True
    assert evidence.cleanup_verified is True


@pytest.mark.oci_smoke
def test_reproduced_image_has_no_self_reference(
    rebuilt_reference_image: OCIImageInspection,
) -> None:
    """GREEN-2: the reproduced image carries no self-reference — the final
    manifest digest/bytes appear in no layer, config, or annotation."""
    assert rebuilt_reference_image.self_reference_scan_passed is True
    assert rebuilt_reference_image.manifest_digest is not None
