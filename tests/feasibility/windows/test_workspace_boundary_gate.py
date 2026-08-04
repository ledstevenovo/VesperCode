"""T01.2 step 1.E: workspace boundary GO report and identity continuity."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from spikes.win32_workspace_boundary.object_probe import (
    WorkspaceObjectProbeResultV1,
)
from spikes.win32_workspace_boundary.mutex_probe import WorkspaceMutexProbeResultV1
from spikes.win32_workspace_boundary.report import (
    WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH,
    GateToolchainEvidenceV1,
    assemble_workspace_boundary_report,
    load_workspace_boundary_gate_report,
    write_workspace_boundary_gate_report,
)


_TOOLCHAIN_BODY = {
    "schema_version": 1,
    "evidence_type": "GATE_TOOLCHAIN_EVIDENCE_V1",
    "python_version": "3.12.4",
    "pytest_version": "8.4.2",
    "ruff_version": "0.16.1",
    "mypy_version": "2.3.0",
    "gate_input_sha256": "a" * 64,
    "gate_lock_sha256": "b" * 64,
    "gate_scan_sha256": "c" * 64,
    "gate_scan_core_sha256": "d" * 64,
    "runner_sha256": "e" * 64,
    "pytest_config_sha256": "f" * 64,
    "ruff_config_sha256": "0" * 64,
    "mypy_config_sha256": "1" * 64,
}


def _compute_toolchain_digest_from_body(body: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()


def toolchain() -> GateToolchainEvidenceV1:
    digest = _compute_toolchain_digest_from_body(_TOOLCHAIN_BODY)
    return GateToolchainEvidenceV1(
        schema_version=1,
        evidence_type="GATE_TOOLCHAIN_EVIDENCE_V1",
        python_version="3.12.4",
        pytest_version="8.4.2",
        ruff_version="0.16.1",
        mypy_version="2.3.0",
        gate_input_sha256="a" * 64,
        gate_lock_sha256="b" * 64,
        gate_scan_sha256="c" * 64,
        gate_scan_core_sha256="d" * 64,
        runner_sha256="e" * 64,
        pytest_config_sha256="f" * 64,
        ruff_config_sha256="0" * 64,
        mypy_config_sha256="1" * 64,
        evidence_digest=digest,
    )


def object_probe() -> WorkspaceObjectProbeResultV1:
    from spikes.win32_workspace_boundary.evaluator import (
        BoundaryObservationV1,
    )

    return WorkspaceObjectProbeResultV1(
        observations=(
            BoundaryObservationV1(
                code="FILE_OBJECT_OBSERVED",
                lexical_path="safe.txt",
                final_path="safe.txt",
                expected_volume_serial=1,
                observed_volume_serial=1,
                expected_file_id_128=b"\x01" * 16,
                observed_file_id_128=b"\x01" * 16,
                object_kind="FILE",
                link_count=1,
                reparse_tag=0,
                acl_observable=True,
            ),
        ),
        cleanup_verified=True,
    )


def mutex_probe() -> WorkspaceMutexProbeResultV1:
    return WorkspaceMutexProbeResultV1(
        workspace_identity_digest="3" * 64,
        contender_count=2,
        maximum_concurrent_holders=1,
        timeout_count=0,
        cleanup_verified=True,
    )


def missing_mutex_probe() -> WorkspaceMutexProbeResultV1:
    return WorkspaceMutexProbeResultV1(
        workspace_identity_digest="3" * 64,
        contender_count=2,
        maximum_concurrent_holders=0,
        timeout_count=2,
        cleanup_verified=False,
    )


def unprovable_object_probe() -> WorkspaceObjectProbeResultV1:
    from spikes.win32_workspace_boundary.evaluator import (
        BoundaryObservationV1,
    )

    return WorkspaceObjectProbeResultV1(
        observations=(
            BoundaryObservationV1(
                code="IDENTITY_UNPROVEN",
                lexical_path="missing.txt",
                final_path="",
                expected_volume_serial=0,
                observed_volume_serial=0,
                expected_file_id_128=b"",
                observed_file_id_128=b"",
                object_kind="FILE",
                link_count=0,
                reparse_tag=0,
                acl_observable=False,
            ),
        ),
        cleanup_verified=True,
    )


def unclean_object_probe() -> WorkspaceObjectProbeResultV1:
    from spikes.win32_workspace_boundary.evaluator import (
        BoundaryObservationV1,
    )

    return WorkspaceObjectProbeResultV1(
        observations=(
            BoundaryObservationV1(
                code="FILE_OBJECT_OBSERVED",
                lexical_path="safe.txt",
                final_path="safe.txt",
                expected_volume_serial=1,
                observed_volume_serial=1,
                expected_file_id_128=b"\x01" * 16,
                observed_file_id_128=b"\x01" * 16,
                object_kind="FILE",
                link_count=1,
                reparse_tag=0,
                acl_observable=True,
            ),
        ),
        cleanup_verified=False,
    )


def non_exclusive_mutex_probe() -> WorkspaceMutexProbeResultV1:
    return WorkspaceMutexProbeResultV1(
        workspace_identity_digest="3" * 64,
        contender_count=2,
        maximum_concurrent_holders=2,
        timeout_count=0,
        cleanup_verified=True,
    )


# Exact RED tests


def test_gate_refuses_go_when_mutex_evidence_is_missing() -> None:
    report = assemble_workspace_boundary_report(
        toolchain(), object_probe(), missing_mutex_probe()
    )
    assert report.outcome == "NO_GO"


def test_terminal_go_evidence_round_trips_at_fixed_path(tmp_path: Path) -> None:
    report = assemble_workspace_boundary_report(
        toolchain(), object_probe(), mutex_probe()
    )
    path = tmp_path / WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH
    write_workspace_boundary_gate_report(report, path)
    assert load_workspace_boundary_gate_report(tmp_path) == report


# Domain completeness tests


def test_gate_refuses_go_when_object_observations_are_unprovable() -> None:
    report = assemble_workspace_boundary_report(
        toolchain(), unprovable_object_probe(), mutex_probe()
    )
    assert report.outcome == "NO_GO"


def test_gate_refuses_go_when_object_cleanup_is_unverified() -> None:
    report = assemble_workspace_boundary_report(
        toolchain(), unclean_object_probe(), mutex_probe()
    )
    assert report.outcome == "NO_GO"


def test_gate_refuses_go_when_mutex_is_not_exclusive() -> None:
    report = assemble_workspace_boundary_report(
        toolchain(), object_probe(), non_exclusive_mutex_probe()
    )
    assert report.outcome == "NO_GO"


def test_non_go_report_cannot_be_written_to_fixed_path(tmp_path: Path) -> None:
    report = assemble_workspace_boundary_report(
        toolchain(), unprovable_object_probe(), mutex_probe()
    )
    path = tmp_path / WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH
    with pytest.raises(ValueError, match="terminal GO"):
        write_workspace_boundary_gate_report(report, path)


def test_loader_rejects_missing_terminal_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="terminal GO evidence"):
        load_workspace_boundary_gate_report(tmp_path)


def test_loader_rejects_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        load_workspace_boundary_gate_report(tmp_path)


def test_loader_rejects_digest_drifted_evidence(tmp_path: Path) -> None:
    report = assemble_workspace_boundary_report(
        toolchain(), object_probe(), mutex_probe()
    )
    path = tmp_path / WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH
    write_workspace_boundary_gate_report(report, path)
    raw = path.read_bytes()
    tampered = raw.replace(b'"GO"', b'"GO"').replace(
        report.evidence_digest.encode("utf-8"),
        ("f" * 64).encode("utf-8"),
    )
    path.write_bytes(tampered)
    with pytest.raises(ValueError, match="evidence digest mismatch"):
        load_workspace_boundary_gate_report(tmp_path)


def test_complete_evidence_yields_go_with_all_fields_populated() -> None:
    report = assemble_workspace_boundary_report(
        toolchain(), object_probe(), mutex_probe()
    )
    assert report.outcome == "GO"
    assert report.evaluation.passed is True
    assert report.object_probe.cleanup_verified is True
    assert report.mutex_probe.cleanup_verified is True
    assert report.mutex_probe.maximum_concurrent_holders == 1
    assert len(report.evidence_digest) == 64


def test_loader_rejects_non_go_evidence_at_fixed_path(tmp_path: Path) -> None:
    from spikes.win32_workspace_boundary.report import (
        _canonical_json_bytes,
        _report_to_serializable,
    )

    no_go_report = assemble_workspace_boundary_report(
        toolchain(), unprovable_object_probe(), mutex_probe()
    )
    no_go_report_dict = _report_to_serializable(no_go_report)
    no_go_report_dict["outcome"] = "NO_GO"
    path = tmp_path / WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json_bytes(no_go_report_dict))
    with pytest.raises(ValueError, match="GO outcome"):
        load_workspace_boundary_gate_report(tmp_path)


def test_assemble_rejects_empty_object_observations() -> None:
    empty_probe = WorkspaceObjectProbeResultV1(
        observations=(),
        cleanup_verified=True,
    )
    with pytest.raises(ValueError, match="empty"):
        assemble_workspace_boundary_report(toolchain(), empty_probe, mutex_probe())


def test_loader_rejects_toolchain_drifted_evidence(tmp_path: Path) -> None:
    import json

    from spikes.win32_workspace_boundary.report import (
        _canonical_json_bytes,
        _compute_evidence_digest,
    )

    report = assemble_workspace_boundary_report(
        toolchain(), object_probe(), mutex_probe()
    )
    path = tmp_path / WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH
    write_workspace_boundary_gate_report(report, path)
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    tc = data["gate_toolchain"]
    tc["python_version"] = "1.0.0"
    body = {
        "outcome": data["outcome"],
        "gate_toolchain": tc,
        "object_probe": data["object_probe"],
        "mutex_probe": data["mutex_probe"],
        "evaluation": data["evaluation"],
    }
    data["evidence_digest"] = _compute_evidence_digest(body)
    path.write_bytes(_canonical_json_bytes(data))
    with pytest.raises(ValueError, match="toolchain evidence"):
        load_workspace_boundary_gate_report(tmp_path)
