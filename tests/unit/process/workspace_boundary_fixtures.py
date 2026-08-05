"""Test-only synthetic workspace-boundary GO report builder (T04.1 step 1).

Builds a loader-valid terminal GO report under a supplied temporary root
using only the T01.2 public assembler/writer/loader APIs.  Reads the
committed Task 1 gate-toolchain evidence read-only, overrides the recorded
Python patch, recomputes every nested and final digest, writes synthetic
evidence only under the supplied root, and returns only after the detached
report round-trips through the Task 1.E loader.  It never changes committed
Task 1 evidence.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from spikes.win32_workspace_boundary.evaluator import BoundaryObservationV1
from spikes.win32_workspace_boundary.mutex_probe import WorkspaceMutexProbeResultV1
from spikes.win32_workspace_boundary.object_probe import WorkspaceObjectProbeResultV1
from spikes.win32_workspace_boundary.report import (
    WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH,
    GateToolchainEvidenceV1,
    WorkspaceBoundaryGateReportV1,
    assemble_workspace_boundary_report,
    load_workspace_boundary_gate_report,
    write_workspace_boundary_gate_report,
)

_ROOT_TOOLCHAIN_REL_PATH = Path("gates/evidence/gate-toolchain-v1.json")

_TOOLCHAIN_FIELDS = frozenset(
    {
        "schema_version",
        "evidence_type",
        "python_version",
        "pytest_version",
        "ruff_version",
        "mypy_version",
        "gate_input_sha256",
        "gate_lock_sha256",
        "gate_scan_sha256",
        "gate_scan_core_sha256",
        "runner_sha256",
        "pytest_config_sha256",
        "ruff_config_sha256",
        "mypy_config_sha256",
        "evidence_digest",
    }
)


def _canonical_compact_json(value: dict[str, object]) -> str:
    """Serialize to the compact canonical convention used by Task 1 evidence."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _toolchain_digest(toolchain: dict[str, object]) -> str:
    """Recompute the toolchain evidence digest from all non-digest fields."""
    body = {key: value for key, value in toolchain.items() if key != "evidence_digest"}
    return hashlib.sha256(_canonical_compact_json(body).encode("utf-8")).hexdigest()


def _require_str(obj: dict[str, object], key: str) -> str:
    value = obj[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a JSON string")
    return value


def _require_int(obj: dict[str, object], key: str) -> int:
    value = obj[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be a JSON integer")
    return value


def _synthetic_toolchain(root: Path, python_version: str) -> GateToolchainEvidenceV1:
    """Read the committed gate toolchain read-only, override the Python patch,
    recompute the nested digest, and write the synthetic copy under *root*."""
    repo_root = Path(__file__).resolve().parents[3]
    raw = json.loads((repo_root / _ROOT_TOOLCHAIN_REL_PATH).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("committed gate toolchain evidence is not a JSON object")
    if set(raw) != _TOOLCHAIN_FIELDS:
        raise ValueError("committed gate toolchain evidence has unexpected fields")
    synthetic: dict[str, object] = {key: value for key, value in raw.items()}
    synthetic["python_version"] = python_version
    synthetic["evidence_digest"] = _toolchain_digest(synthetic)
    target = root / _ROOT_TOOLCHAIN_REL_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_canonical_compact_json(synthetic) + "\n", encoding="utf-8")
    return GateToolchainEvidenceV1(
        schema_version=_require_int(synthetic, "schema_version"),
        evidence_type=_require_str(synthetic, "evidence_type"),
        python_version=_require_str(synthetic, "python_version"),
        pytest_version=_require_str(synthetic, "pytest_version"),
        ruff_version=_require_str(synthetic, "ruff_version"),
        mypy_version=_require_str(synthetic, "mypy_version"),
        gate_input_sha256=_require_str(synthetic, "gate_input_sha256"),
        gate_lock_sha256=_require_str(synthetic, "gate_lock_sha256"),
        gate_scan_sha256=_require_str(synthetic, "gate_scan_sha256"),
        gate_scan_core_sha256=_require_str(synthetic, "gate_scan_core_sha256"),
        runner_sha256=_require_str(synthetic, "runner_sha256"),
        pytest_config_sha256=_require_str(synthetic, "pytest_config_sha256"),
        ruff_config_sha256=_require_str(synthetic, "ruff_config_sha256"),
        mypy_config_sha256=_require_str(synthetic, "mypy_config_sha256"),
        evidence_digest=_require_str(synthetic, "evidence_digest"),
    )


def _synthetic_object_probe() -> WorkspaceObjectProbeResultV1:
    """One closed observation that evaluates PASS with a unique identity."""
    observation = BoundaryObservationV1(
        code="FILE_OBJECT_OBSERVED",
        lexical_path="C:\\synthetic\\workspace\\safe.txt",
        final_path="C:\\synthetic\\workspace\\safe.txt",
        expected_volume_serial=1,
        observed_volume_serial=1,
        expected_file_id_128=bytes.fromhex("0102030405060708090a0b0c0d0e0f10"),
        observed_file_id_128=bytes.fromhex("0102030405060708090a0b0c0d0e0f10"),
        object_kind="FILE",
        link_count=1,
        reparse_tag=0,
        acl_observable=True,
    )
    return WorkspaceObjectProbeResultV1(
        observations=(observation,), cleanup_verified=True
    )


def _synthetic_mutex_probe(root: Path) -> WorkspaceMutexProbeResultV1:
    """A deterministic per-root 64-hex workspace identity and exclusivity."""
    return WorkspaceMutexProbeResultV1(
        workspace_identity_digest=hashlib.sha256(str(root).encode("utf-8")).hexdigest(),
        contender_count=2,
        maximum_concurrent_holders=1,
        timeout_count=0,
        cleanup_verified=True,
    )


def build_workspace_boundary_gate_test_fixture(
    root: Path, python_version: str
) -> WorkspaceBoundaryGateReportV1:
    """Assemble, write, and load-verify one synthetic terminal GO report.

    The report and its nested toolchain copy are written only under *root*;
    the returned value is the loader-validated report itself.
    """
    toolchain = _synthetic_toolchain(root, python_version)
    report = assemble_workspace_boundary_report(
        toolchain, _synthetic_object_probe(), _synthetic_mutex_probe(root)
    )
    write_workspace_boundary_gate_report(
        report, root / WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH
    )
    return load_workspace_boundary_gate_report(root)
