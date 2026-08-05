"""T03.2 legacy step 3.G: real NTFS persistence-recovery GO gate tests.

The gate runs the complete fault/deadline/external-change/preview/apply
case matrix against disposable real NTFS objects under the given
workspace and emits the Task 3 GO/NO_GO report.  GO requires complete
matrix coverage, gate-toolchain identity, workspace-probe identity,
per-case evidence, and cleanup; any missing external-identity case,
missing/drifted identity evidence, or failed case yields NO_GO.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from spikes.persistence_recovery import report as report_module
from spikes.persistence_recovery.report import (
    REQUIRED_CASE_MANIFEST,
    PersistenceRecoveryGateReportV1,
    run_persistence_recovery_gate,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]

_DECLARED_CASE_MANIFEST = (
    "PREVIEW_BYTE_IDENTITY",
    "PREVIEW_ROLLED_BACK_ZERO_WRITE",
    "SAFE_ABSENT_ROLLBACK",
    "FAULT_PROGRESS_BEFORE_UNRESOLVED",
    "FAULT_TERMINAL_BEFORE_COMMITTED",
    "DEADLINE_PRE_WRITE",
    "DEADLINE_POST_WRITE",
    "EXTERNAL_CREATE",
    "EXTERNAL_IDENTITY",
    "EXTERNAL_DIRECTORY",
    "UNPROVABLE_LOCKED_FILE",
    "STALE_PREVIEW_DIGEST",
    "TAMPERED_RECORD_ZERO_WRITE",
)


def test_required_case_manifest_is_pinned() -> None:
    """The declared 13-case matrix cannot be silently reduced, and every
    runner must be reachable from the manifest (no silent case drop)."""
    assert REQUIRED_CASE_MANIFEST == _DECLARED_CASE_MANIFEST
    assert set(report_module._CASE_RUNNERS) == set(REQUIRED_CASE_MANIFEST)


def _seed_gate_evidence(workspace: Path) -> None:
    """Copy the real repo gate identity evidence into the workspace."""
    evidence_dir = workspace / "gates" / "evidence"
    evidence_dir.mkdir(parents=True)
    for name in ("gate-toolchain-v1.json", "workspace-boundary-go-v1.json"):
        source = _REPO_ROOT / "gates" / "evidence" / name
        assert source.is_file(), source
        (evidence_dir / name).write_bytes(source.read_bytes())


@pytest.fixture
def ntfs_workspace(tmp_path: Path) -> Path:
    """A real NTFS workspace whose external identity case object is
    missing (no ``src/a.py``), with the gate identity evidence present."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _seed_gate_evidence(workspace)
    return workspace


@pytest.fixture
def complete_ntfs_workspace(tmp_path: Path) -> Path:
    """A real NTFS workspace with every required case object present."""
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "a.py").write_bytes(b"preimage a\n")
    _seed_gate_evidence(workspace)
    return workspace


def test_missing_external_identity_case_forces_no_go(ntfs_workspace: Path) -> None:
    assert run_persistence_recovery_gate(ntfs_workspace).outcome == "NO_GO"


def test_complete_matrix_yields_go(complete_ntfs_workspace: Path) -> None:
    first = run_persistence_recovery_gate(complete_ntfs_workspace)
    assert first.outcome == "GO"
    assert len(first.cases) == len(REQUIRED_CASE_MANIFEST)
    assert [case.case_name for case in first.cases] == list(REQUIRED_CASE_MANIFEST)
    assert all(case.passed for case in first.cases)
    assert len(first.evidence_digest) == 64
    assert len(first.workspace_probe_digest) == 64
    # The gate is re-runnable on the same workspace: every case cleans up
    # its own records and case directories, and the GO outcome and
    # per-case pass status are stable.  (Real-object case evidence binds
    # freshly observed Win32 identities, so the exact report digest is
    # not stable across runs — outcome stability is the gate contract.)
    assert not any(
        entry.name.startswith("case-") for entry in complete_ntfs_workspace.iterdir()
    )
    second = run_persistence_recovery_gate(complete_ntfs_workspace)
    assert second.outcome == "GO"
    assert [case.case_name for case in second.cases] == list(REQUIRED_CASE_MANIFEST)
    assert all(case.passed for case in second.cases)
    assert second.workspace_probe_digest == first.workspace_probe_digest


def test_gate_binds_toolchain_and_workspace_probe_identity(
    complete_ntfs_workspace: Path,
) -> None:
    report = run_persistence_recovery_gate(complete_ntfs_workspace)
    toolchain_path = (
        complete_ntfs_workspace / "gates" / "evidence" / "gate-toolchain-v1.json"
    )
    toolchain_data = json.loads(toolchain_path.read_bytes())
    assert report.gate_toolchain.evidence_digest == toolchain_data["evidence_digest"]
    probe_path = (
        complete_ntfs_workspace / "gates" / "evidence" / "workspace-boundary-go-v1.json"
    )
    probe_data = json.loads(probe_path.read_bytes())
    assert report.workspace_probe_digest == probe_data["evidence_digest"]


def test_missing_gate_identity_evidence_forces_no_go(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "a.py").write_bytes(b"preimage a\n")
    report = run_persistence_recovery_gate(workspace)
    assert report.outcome == "NO_GO"
    assert not any(case.passed for case in report.cases)


def test_drifted_gate_identity_evidence_forces_no_go(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "a.py").write_bytes(b"preimage a\n")
    _seed_gate_evidence(workspace)
    toolchain_path = workspace / "gates" / "evidence" / "gate-toolchain-v1.json"
    drifted = bytearray(toolchain_path.read_bytes())
    drifted[0] ^= 0x01
    toolchain_path.write_bytes(bytes(drifted))
    report = run_persistence_recovery_gate(workspace)
    assert report.outcome == "NO_GO"
    assert not any(case.passed for case in report.cases)


def test_gate_on_missing_workspace_forces_no_go(tmp_path: Path) -> None:
    report = run_persistence_recovery_gate(tmp_path / "does-not-exist")
    assert report.outcome == "NO_GO"
    assert not any(case.passed for case in report.cases)


def test_gate_report_is_immutable(complete_ntfs_workspace: Path) -> None:
    report = run_persistence_recovery_gate(complete_ntfs_workspace)
    assert isinstance(report, PersistenceRecoveryGateReportV1)
    with pytest.raises(Exception):
        report.outcome = "NO_GO"  # type: ignore[misc]
    with pytest.raises(Exception):
        report.cases = ()  # type: ignore[misc]
    with pytest.raises(Exception):
        report.evidence_digest = "00" * 32  # type: ignore[misc]
    with pytest.raises(Exception):
        report.cases[0].passed = False  # type: ignore[misc]


def test_gate_cleans_up_every_case_artifact(complete_ntfs_workspace: Path) -> None:
    report = run_persistence_recovery_gate(complete_ntfs_workspace)
    assert report.outcome == "GO"
    assert sorted(
        path.relative_to(complete_ntfs_workspace).as_posix()
        for path in complete_ntfs_workspace.rglob("*")
        if path.is_file()
    ) == [
        "gates/evidence/gate-toolchain-v1.json",
        "gates/evidence/workspace-boundary-go-v1.json",
        "src/a.py",
    ]
    shutil.rmtree(complete_ntfs_workspace)
    assert not complete_ntfs_workspace.exists()


def _workspace_bytes_digest(workspace: Path) -> str:
    payload = bytearray()
    for path in sorted(workspace.rglob("*")):
        if path.is_file():
            payload += path.read_bytes()
    return hashlib.sha256(bytes(payload)).hexdigest()


def test_gate_leaves_given_workspace_byte_identical(
    complete_ntfs_workspace: Path,
) -> None:
    """The gate's disposable-object contract: after a GO run the given
    workspace is byte-for-byte identical (case directories and records
    removed, the external-identity object restored)."""
    before = _workspace_bytes_digest(complete_ntfs_workspace)
    report = run_persistence_recovery_gate(complete_ntfs_workspace)
    assert report.outcome == "GO"
    assert _workspace_bytes_digest(complete_ntfs_workspace) == before
