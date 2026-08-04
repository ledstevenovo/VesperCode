"""T01.2 step 1.E: workspace boundary GO report assembler, serializer, and loader.

Owns the terminal GO/NO_GO decision and the fixed-path evidence file.  Never
re-probes Windows or mutates the immutable Task 1.A–1.D evidence records.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from spikes.win32_workspace_boundary.evaluator import (
    BoundaryEvaluationV1,
    evaluate_workspace_observations,
)
from spikes.win32_workspace_boundary.object_probe import (
    WorkspaceObjectProbeResultV1,
)
from spikes.win32_workspace_boundary.mutex_probe import (
    WorkspaceMutexProbeResultV1,
)

WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH = Path(
    "gates/evidence/workspace-boundary-go-v1.json"
)

_SHA256 = hashlib.sha256


@dataclass(frozen=True)
class GateToolchainEvidenceV1:
    """Immutable record of the frozen Task 1.A gate-toolchain identity."""

    schema_version: int
    evidence_type: str
    python_version: str
    pytest_version: str
    ruff_version: str
    mypy_version: str
    gate_input_sha256: str
    gate_lock_sha256: str
    gate_scan_sha256: str
    gate_scan_core_sha256: str
    runner_sha256: str
    pytest_config_sha256: str
    ruff_config_sha256: str
    mypy_config_sha256: str
    evidence_digest: str


@dataclass(frozen=True)
class WorkspaceBoundaryGateReportV1:
    """Immutable GO/NO_GO decision binding all Task 1 evidence.

    Serialized to the fixed terminal path only for a terminal GO.
    """

    outcome: Literal["GO", "NO_GO"]
    gate_toolchain: GateToolchainEvidenceV1
    object_probe: WorkspaceObjectProbeResultV1
    mutex_probe: WorkspaceMutexProbeResultV1
    evaluation: BoundaryEvaluationV1
    evidence_digest: str


def _canonical_json_bytes(obj: object) -> bytes:
    """Serialize *obj* to deterministic UTF-8 JSON with stable key order."""
    return json.dumps(
        obj,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        separators=(",", ": "),
    ).encode("utf-8")


def _object_probe_json(probe: WorkspaceObjectProbeResultV1) -> object:
    observations = []
    for obs in probe.observations:
        observations.append(
            {
                "code": obs.code,
                "lexical_path": obs.lexical_path,
                "final_path": obs.final_path,
                "expected_volume_serial": obs.expected_volume_serial,
                "observed_volume_serial": obs.observed_volume_serial,
                "expected_file_id_128": obs.expected_file_id_128.hex(),
                "observed_file_id_128": obs.observed_file_id_128.hex(),
                "object_kind": obs.object_kind,
                "link_count": obs.link_count,
                "reparse_tag": obs.reparse_tag,
                "acl_observable": obs.acl_observable,
            }
        )
    return {
        "observations": observations,
        "cleanup_verified": probe.cleanup_verified,
    }


def _mutex_probe_json(probe: WorkspaceMutexProbeResultV1) -> object:
    return {
        "workspace_identity_digest": probe.workspace_identity_digest,
        "contender_count": probe.contender_count,
        "maximum_concurrent_holders": probe.maximum_concurrent_holders,
        "timeout_count": probe.timeout_count,
        "cleanup_verified": probe.cleanup_verified,
    }


def _evaluation_json(evaluation: BoundaryEvaluationV1) -> object:
    return {
        "passed": evaluation.passed,
        "failed_codes": list(evaluation.failed_codes),
    }


def _toolchain_json(toolchain: GateToolchainEvidenceV1) -> object:
    return {
        "schema_version": toolchain.schema_version,
        "evidence_type": toolchain.evidence_type,
        "python_version": toolchain.python_version,
        "pytest_version": toolchain.pytest_version,
        "ruff_version": toolchain.ruff_version,
        "mypy_version": toolchain.mypy_version,
        "gate_input_sha256": toolchain.gate_input_sha256,
        "gate_lock_sha256": toolchain.gate_lock_sha256,
        "gate_scan_sha256": toolchain.gate_scan_sha256,
        "gate_scan_core_sha256": toolchain.gate_scan_core_sha256,
        "runner_sha256": toolchain.runner_sha256,
        "pytest_config_sha256": toolchain.pytest_config_sha256,
        "ruff_config_sha256": toolchain.ruff_config_sha256,
        "mypy_config_sha256": toolchain.mypy_config_sha256,
        "evidence_digest": toolchain.evidence_digest,
    }


def _compute_evidence_digest(report_data: object) -> str:
    """Return the SHA-256 hex digest of the canonical JSON report body."""
    return _SHA256(_canonical_json_bytes(report_data)).hexdigest()


def _assemble_report_body(
    toolchain: GateToolchainEvidenceV1,
    object_probe: WorkspaceObjectProbeResultV1,
    mutex_probe: WorkspaceMutexProbeResultV1,
    evaluation: BoundaryEvaluationV1,
    outcome: Literal["GO", "NO_GO"],
) -> WorkspaceBoundaryGateReportV1:
    """Build the immutable report and compute its digest from the body."""
    body = {
        "outcome": outcome,
        "gate_toolchain": _toolchain_json(toolchain),
        "object_probe": _object_probe_json(object_probe),
        "mutex_probe": _mutex_probe_json(mutex_probe),
        "evaluation": _evaluation_json(evaluation),
    }
    digest = _compute_evidence_digest(body)
    return WorkspaceBoundaryGateReportV1(
        outcome=outcome,
        gate_toolchain=toolchain,
        object_probe=object_probe,
        mutex_probe=mutex_probe,
        evaluation=evaluation,
        evidence_digest=digest,
    )


def assemble_workspace_boundary_report(
    toolchain: GateToolchainEvidenceV1,
    object_probe: WorkspaceObjectProbeResultV1,
    mutex_probe: WorkspaceMutexProbeResultV1,
) -> WorkspaceBoundaryGateReportV1:
    """Assemble the closed boundary gate report from all Task 1 evidence.

    Returns GO only when every required evidence item is present, identity-
    matched, and internally consistent (evaluation passed, object cleanup
    verified, and mutex exclusivity proven).
    """
    if not object_probe.observations:
        raise ValueError("object probe observations must not be empty")
    evaluation = evaluate_workspace_observations(object_probe.observations)
    go = (
        evaluation.passed
        and object_probe.cleanup_verified
        and mutex_probe.cleanup_verified
        and mutex_probe.maximum_concurrent_holders == 1
    )
    outcome: Literal["GO", "NO_GO"] = "GO" if go else "NO_GO"
    return _assemble_report_body(
        toolchain, object_probe, mutex_probe, evaluation, outcome
    )


def _report_to_serializable(
    report: WorkspaceBoundaryGateReportV1,
) -> dict[str, object]:
    return {
        "outcome": report.outcome,
        "gate_toolchain": _toolchain_json(report.gate_toolchain),
        "object_probe": _object_probe_json(report.object_probe),
        "mutex_probe": _mutex_probe_json(report.mutex_probe),
        "evaluation": _evaluation_json(report.evaluation),
        "evidence_digest": report.evidence_digest,
    }


def _ensure_object_kind(raw: object) -> Literal["FILE", "DIRECTORY"]:
    if raw not in ("FILE", "DIRECTORY"):
        raise ValueError(f"object_kind must be FILE or DIRECTORY, got {raw!r}")
    return raw


def _compute_toolchain_digest(tc: dict[str, object]) -> str:
    """Recompute the toolchain evidence_digest from the embedded fields.

    Uses the same compact canonical convention as
    ``probe.py:_load_toolchain_evidence``: all fields except
    ``evidence_digest`` itself, sorted keys, no whitespace.
    """
    body = {k: v for k, v in tc.items() if k != "evidence_digest"}
    return _SHA256(
        json.dumps(
            body,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _validate_toolchain_digest(tc: dict[str, object]) -> None:
    """Validate the embedded toolchain evidence_digest.

    Raises ValueError when the digest is missing, malformed, or mismatched.
    """
    stored = tc.get("evidence_digest")
    if not isinstance(stored, str) or len(stored) != 64:
        raise ValueError("toolchain evidence_digest must be a 64-char hex string")
    computed = _compute_toolchain_digest(tc)
    if computed != stored:
        raise ValueError(
            "toolchain evidence digest mismatch — toolchain evidence has been drifted"
        )


def _deserialize_report(data: object) -> WorkspaceBoundaryGateReportV1:
    if not isinstance(data, dict):
        raise ValueError("report must be a JSON object")
    outcome = data.get("outcome")
    if outcome not in ("GO", "NO_GO"):
        raise ValueError("report outcome must be GO or NO_GO")
    tc = data.get("gate_toolchain")
    if not isinstance(tc, dict):
        raise ValueError("gate_toolchain must be a JSON object")
    _validate_toolchain_digest(tc)
    op = data.get("object_probe")
    if not isinstance(op, dict):
        raise ValueError("object_probe must be a JSON object")
    mp = data.get("mutex_probe")
    if not isinstance(mp, dict):
        raise ValueError("mutex_probe must be a JSON object")
    ev = data.get("evaluation")
    if not isinstance(ev, dict):
        raise ValueError("evaluation must be a JSON object")
    stored_digest = data.get("evidence_digest")
    if not isinstance(stored_digest, str) or len(stored_digest) != 64:
        raise ValueError("evidence_digest must be a 64-char hex string")

    toolchain = GateToolchainEvidenceV1(
        schema_version=int(tc.get("schema_version", 0)),
        evidence_type=str(tc.get("evidence_type", "")),
        python_version=str(tc.get("python_version", "")),
        pytest_version=str(tc.get("pytest_version", "")),
        ruff_version=str(tc.get("ruff_version", "")),
        mypy_version=str(tc.get("mypy_version", "")),
        gate_input_sha256=str(tc.get("gate_input_sha256", "")),
        gate_lock_sha256=str(tc.get("gate_lock_sha256", "")),
        gate_scan_sha256=str(tc.get("gate_scan_sha256", "")),
        gate_scan_core_sha256=str(tc.get("gate_scan_core_sha256", "")),
        runner_sha256=str(tc.get("runner_sha256", "")),
        pytest_config_sha256=str(tc.get("pytest_config_sha256", "")),
        ruff_config_sha256=str(tc.get("ruff_config_sha256", "")),
        mypy_config_sha256=str(tc.get("mypy_config_sha256", "")),
        evidence_digest=str(tc.get("evidence_digest", "")),
    )

    from spikes.win32_workspace_boundary.evaluator import (
        BoundaryObservationV1,
    )

    obs_list = op.get("observations")
    if not isinstance(obs_list, list) or not obs_list:
        raise ValueError("object_probe.observations must be a non-empty list")
    observations = []
    for obs_data in obs_list:
        if not isinstance(obs_data, dict):
            raise ValueError("each observation must be a JSON object")
        observations.append(
            BoundaryObservationV1(
                code=str(obs_data.get("code", "")),
                lexical_path=str(obs_data.get("lexical_path", "")),
                final_path=str(obs_data.get("final_path", "")),
                expected_volume_serial=int(obs_data.get("expected_volume_serial", 0)),
                observed_volume_serial=int(obs_data.get("observed_volume_serial", 0)),
                expected_file_id_128=bytes.fromhex(
                    str(obs_data.get("expected_file_id_128", ""))
                ),
                observed_file_id_128=bytes.fromhex(
                    str(obs_data.get("observed_file_id_128", ""))
                ),
                object_kind=_ensure_object_kind(obs_data.get("object_kind", "FILE")),
                link_count=int(obs_data.get("link_count", 0)),
                reparse_tag=int(obs_data.get("reparse_tag", 0)),
                acl_observable=bool(obs_data.get("acl_observable", False)),
            )
        )
    object_probe = WorkspaceObjectProbeResultV1(
        observations=tuple(observations),
        cleanup_verified=bool(op.get("cleanup_verified", False)),
    )
    mutex_probe = WorkspaceMutexProbeResultV1(
        workspace_identity_digest=str(mp.get("workspace_identity_digest", "")),
        contender_count=int(mp.get("contender_count", 0)),
        maximum_concurrent_holders=int(mp.get("maximum_concurrent_holders", 0)),
        timeout_count=int(mp.get("timeout_count", 0)),
        cleanup_verified=bool(mp.get("cleanup_verified", False)),
    )
    evaluation = BoundaryEvaluationV1(
        passed=bool(ev.get("passed", False)),
        failed_codes=tuple(str(c) for c in ev.get("failed_codes", [])),
    )

    body = {
        "outcome": outcome,
        "gate_toolchain": tc,
        "object_probe": op,
        "mutex_probe": mp,
        "evaluation": ev,
    }
    computed_digest = _compute_evidence_digest(body)
    if computed_digest != stored_digest:
        raise ValueError("evidence digest mismatch — evidence has been drifted")

    return WorkspaceBoundaryGateReportV1(
        outcome=outcome,
        gate_toolchain=toolchain,
        object_probe=object_probe,
        mutex_probe=mutex_probe,
        evaluation=evaluation,
        evidence_digest=computed_digest,
    )


def write_workspace_boundary_gate_report(
    report: WorkspaceBoundaryGateReportV1,
    path: Path = WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH,
) -> None:
    """Atomically serialize the report to *path* (only for terminal GO).

    Uses a tempfile + atomic rename to prevent partial writes.  The report is
    written only when ``outcome == "GO"``; otherwise a ``ValueError`` is raised.
    """
    if report.outcome != "GO":
        raise ValueError(
            "only a terminal GO report may be written to the fixed evidence path"
        )
    target = path
    payload = _canonical_json_bytes(_report_to_serializable(report))
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    try:
        temp.write_bytes(payload)
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink(missing_ok=True)


def load_workspace_boundary_gate_report(
    root: Path,
) -> WorkspaceBoundaryGateReportV1:
    """Load and validate the terminal GO evidence from *root*.

    Rejects missing files, malformed JSON, digest-drifted evidence, non-GO
    outcomes, and toolchain-drifted records.
    """
    path = root / WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH
    if not path.is_file():
        raise FileNotFoundError(f"terminal GO evidence file not found: {path}")
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"invalid JSON in terminal evidence: {exc}") from exc
    report = _deserialize_report(data)
    if report.outcome != "GO":
        raise ValueError("terminal evidence file must record a GO outcome")
    return report
