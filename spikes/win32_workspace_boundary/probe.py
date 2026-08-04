"""T01.2 step 1.E: real-environment workspace boundary probe coordinator.

Runs the 1.C object probe against a disposable NTFS workspace and the 1.D
mutex probe against real contender processes, then assembles the terminal
GO/NO_GO report.  This module is the sole entry-point for producing the
committed ``gates/evidence/workspace-boundary-go-v1.json``.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from spikes.win32_workspace_boundary.object_probe import (
    BoundaryCaseManifestV1,
    WorkspaceBoundaryCaseV1,
    probe_workspace_objects,
)
from spikes.win32_workspace_boundary.mutex_probe import probe_workspace_mutex
from spikes.win32_workspace_boundary.report import (
    GateToolchainEvidenceV1,
    WorkspaceBoundaryGateReportV1,
    assemble_workspace_boundary_report,
)

_SHA256 = hashlib.sha256


def _identity_digest(workspace_root: Path) -> str:
    """Derive a workspace identity digest from the canonical root path."""
    canonical = os.path.normcase(os.path.abspath(str(workspace_root)))
    return _SHA256(canonical.encode("utf-8")).hexdigest()


def _create_disposable_workspace(parent: Path) -> Path:
    """Create a clean disposable NTFS workspace for the real GO probe."""
    root = Path(tempfile.mkdtemp(dir=parent, prefix="vesper_boundary_"))
    (root / "safe.txt").write_text("safe\n", encoding="utf-8")
    (root / "ordinary.txt").write_text("ordinary\n", encoding="utf-8")
    ordinary_dir = root / "ordinary-directory"
    ordinary_dir.mkdir()
    nested = root / "nested"
    nested.mkdir()
    (nested / "deep.txt").write_text("deep\n", encoding="utf-8")
    return root


def _object_case_manifest(root: Path) -> BoundaryCaseManifestV1:
    """Return the closed case manifest for the clean disposable workspace."""
    return BoundaryCaseManifestV1(
        cases=(
            WorkspaceBoundaryCaseV1("FILE_OBJECT_OBSERVED", "safe.txt"),
            WorkspaceBoundaryCaseV1("FILE_OBJECT_OBSERVED", "ordinary.txt"),
            WorkspaceBoundaryCaseV1("DIRECTORY_OBJECT_OBSERVED", "ordinary-directory"),
            WorkspaceBoundaryCaseV1("DIRECTORY_OBJECT_OBSERVED", "nested"),
            WorkspaceBoundaryCaseV1("FILE_OBJECT_OBSERVED", "nested/deep.txt"),
        )
    )


def _load_toolchain_evidence() -> GateToolchainEvidenceV1:
    """Load the immutable Task 1.A gate-toolchain evidence."""
    path = Path("gates/evidence/gate-toolchain-v1.json")
    if not path.is_file():
        raise FileNotFoundError(f"toolchain evidence not found: {path}")
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if data.get("evidence_type") != "GATE_TOOLCHAIN_EVIDENCE_V1":
        raise ValueError("toolchain evidence has wrong type")
    computed = _SHA256(
        json.dumps(
            {k: v for k, v in data.items() if k != "evidence_digest"},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    if computed != data.get("evidence_digest"):
        raise ValueError("toolchain evidence digest mismatch")
    return GateToolchainEvidenceV1(
        schema_version=int(data.get("schema_version", 0)),
        evidence_type=str(data.get("evidence_type", "")),
        python_version=str(data.get("python_version", "")),
        pytest_version=str(data.get("pytest_version", "")),
        ruff_version=str(data.get("ruff_version", "")),
        mypy_version=str(data.get("mypy_version", "")),
        gate_input_sha256=str(data.get("gate_input_sha256", "")),
        gate_lock_sha256=str(data.get("gate_lock_sha256", "")),
        gate_scan_sha256=str(data.get("gate_scan_sha256", "")),
        gate_scan_core_sha256=str(data.get("gate_scan_core_sha256", "")),
        runner_sha256=str(data.get("runner_sha256", "")),
        pytest_config_sha256=str(data.get("pytest_config_sha256", "")),
        ruff_config_sha256=str(data.get("ruff_config_sha256", "")),
        mypy_config_sha256=str(data.get("mypy_config_sha256", "")),
        evidence_digest=str(data.get("evidence_digest", "")),
    )


def run_real_probes() -> WorkspaceBoundaryGateReportV1:
    """Run 1.C and 1.D probes against the real Windows environment.

    Creates a disposable NTFS workspace in the system temp directory, runs
    the object and mutex probes, cleans up the workspace, and returns the
    assembled gate report.

    The report outcome is GO only when every required evidence item is
    present, identity-matched, and internally consistent.
    """
    toolchain = _load_toolchain_evidence()
    tmp_root = Path(tempfile.gettempdir())
    workspace = _create_disposable_workspace(tmp_root)
    workspace_clean = False
    try:
        manifest = _object_case_manifest(workspace)
        object_result = probe_workspace_objects(workspace, manifest)
        digest = _identity_digest(workspace)
        mutex_result = probe_workspace_mutex(
            digest, contender_count=2, timeout_ms=2_000
        )
        report = assemble_workspace_boundary_report(
            toolchain, object_result, mutex_result
        )
        shutil.rmtree(workspace, ignore_errors=True)
        workspace_clean = True
        return report
    finally:
        if not workspace_clean:
            shutil.rmtree(workspace, ignore_errors=True)
