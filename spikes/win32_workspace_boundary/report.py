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
    BoundaryObservationV1,
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


def _go_predicate(
    evaluation: BoundaryEvaluationV1,
    object_probe: WorkspaceObjectProbeResultV1,
    mutex_probe: WorkspaceMutexProbeResultV1,
) -> bool:
    """Return True when every required evidence item signals GO.

    Shared by the assembler and the loader so the two can never diverge.
    """
    return (
        evaluation.passed
        and object_probe.cleanup_verified
        and mutex_probe.cleanup_verified
        and mutex_probe.maximum_concurrent_holders == 1
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
    go = _go_predicate(evaluation, object_probe, mutex_probe)
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
        raise ValueError("toolchain evidence_digest must be a 64-character string")
    computed = _compute_toolchain_digest(tc)
    if computed != stored:
        raise ValueError(
            "toolchain evidence digest mismatch — toolchain evidence has been drifted"
        )


_ROOT_TOOLCHAIN_PATH = Path("gates/evidence/gate-toolchain-v1.json")

_REPORT_FIELDS = frozenset(
    {
        "outcome",
        "gate_toolchain",
        "object_probe",
        "mutex_probe",
        "evaluation",
        "evidence_digest",
    }
)
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
_OBJECT_PROBE_FIELDS = frozenset({"observations", "cleanup_verified"})
_OBSERVATION_FIELDS = frozenset(
    {
        "code",
        "lexical_path",
        "final_path",
        "expected_volume_serial",
        "observed_volume_serial",
        "expected_file_id_128",
        "observed_file_id_128",
        "object_kind",
        "link_count",
        "reparse_tag",
        "acl_observable",
    }
)
_MUTEX_PROBE_FIELDS = frozenset(
    {
        "workspace_identity_digest",
        "contender_count",
        "maximum_concurrent_holders",
        "timeout_count",
        "cleanup_verified",
    }
)
_EVALUATION_FIELDS = frozenset({"passed", "failed_codes"})


def _require_exact_keys(
    obj: dict[str, object], expected: frozenset[str], path: str
) -> None:
    """Reject missing or unknown fields in one closed JSON object."""
    actual = frozenset(obj)
    missing = sorted(expected - actual)
    if missing:
        raise ValueError(f"{path} missing JSON fields: {', '.join(missing)}")
    unknown = sorted(actual - expected)
    if unknown:
        raise ValueError(f"{path} contains unknown JSON fields: {', '.join(unknown)}")


def _read_and_validate_root_toolchain(root: Path) -> dict[str, object]:
    """Read the root gate-toolchain evidence, validate its self-digest, and
    return the parsed dict."""
    path = root / _ROOT_TOOLCHAIN_PATH
    if not path.is_file():
        raise ValueError(f"root toolchain evidence file not found: {path}")
    raw = path.read_bytes()
    try:
        root_tc: dict[str, object] = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"invalid JSON in root toolchain evidence: {exc}") from exc
    if not isinstance(root_tc, dict):
        raise ValueError("root toolchain evidence must be a JSON object")
    _require_exact_keys(root_tc, _TOOLCHAIN_FIELDS, "root gate_toolchain")
    if root_tc.get("evidence_type") != "GATE_TOOLCHAIN_EVIDENCE_V1":
        raise ValueError("root toolchain evidence has wrong type")
    _require_schema_version(root_tc, "root gate_toolchain")
    _validate_toolchain_digest(root_tc)
    return root_tc


def _require_bool(obj: dict[str, object], key: str) -> bool:
    """Return the JSON boolean at *key*, rejecting every other JSON type.

    *key* may be a dotted path used only for error messages; the field is
    looked up by its final segment.
    """
    field = key.rsplit(".", 1)[-1]
    value = obj.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a JSON boolean")
    return value


def _require_int(obj: dict[str, object], key: str) -> int:
    """Return the JSON integer at *key*, rejecting bools, floats, strings.

    *key* may be a dotted path used only for error messages; the field is
    looked up by its final segment.
    """
    field = key.rsplit(".", 1)[-1]
    value = obj.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be a JSON integer")
    return value


def _require_schema_version(obj: dict[str, object], path: str) -> int:
    """Require the exact closed schema version understood by this V1 loader."""
    version = _require_int(obj, f"{path}.schema_version")
    if version != 1:
        raise ValueError(f"{path}.schema_version must equal 1")
    return version


def _require_str(obj: dict[str, object], key: str) -> str:
    """Return the JSON string at *key*, rejecting every other JSON type.

    *key* may be a dotted path used only for error messages; the field is
    looked up by its final segment.
    """
    field = key.rsplit(".", 1)[-1]
    value = obj.get(field)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a JSON string")
    return value


def _deserialize_report(
    data: object,
    root: Path,
) -> WorkspaceBoundaryGateReportV1:
    if not isinstance(data, dict):
        raise ValueError("report must be a JSON object")
    _require_exact_keys(data, _REPORT_FIELDS, "report")
    outcome = data.get("outcome")
    if outcome not in ("GO", "NO_GO"):
        raise ValueError("report outcome must be GO or NO_GO")
    tc = data.get("gate_toolchain")
    if not isinstance(tc, dict):
        raise ValueError("gate_toolchain must be a JSON object")
    _require_exact_keys(tc, _TOOLCHAIN_FIELDS, "gate_toolchain")
    _validate_toolchain_digest(tc)

    # Strict field type checks first, so type errors are never misreported
    # as binding failures and bool values can never slip past ``tc != root_tc``
    # via Python's ``True == 1`` equality.
    toolchain = GateToolchainEvidenceV1(
        schema_version=_require_schema_version(tc, "gate_toolchain"),
        evidence_type=_require_str(tc, "gate_toolchain.evidence_type"),
        python_version=_require_str(tc, "gate_toolchain.python_version"),
        pytest_version=_require_str(tc, "gate_toolchain.pytest_version"),
        ruff_version=_require_str(tc, "gate_toolchain.ruff_version"),
        mypy_version=_require_str(tc, "gate_toolchain.mypy_version"),
        gate_input_sha256=_require_str(tc, "gate_toolchain.gate_input_sha256"),
        gate_lock_sha256=_require_str(tc, "gate_toolchain.gate_lock_sha256"),
        gate_scan_sha256=_require_str(tc, "gate_toolchain.gate_scan_sha256"),
        gate_scan_core_sha256=_require_str(tc, "gate_toolchain.gate_scan_core_sha256"),
        runner_sha256=_require_str(tc, "gate_toolchain.runner_sha256"),
        pytest_config_sha256=_require_str(tc, "gate_toolchain.pytest_config_sha256"),
        ruff_config_sha256=_require_str(tc, "gate_toolchain.ruff_config_sha256"),
        mypy_config_sha256=_require_str(tc, "gate_toolchain.mypy_config_sha256"),
        evidence_digest=_require_str(tc, "gate_toolchain.evidence_digest"),
    )

    # P1-2: bind embedded toolchain to the root fixed evidence file
    root_tc = _read_and_validate_root_toolchain(root)
    if tc != root_tc:
        raise ValueError(
            "toolchain evidence does not bind root evidence — embedded record "
            "differs from root gate-toolchain evidence"
        )

    op = data.get("object_probe")
    if not isinstance(op, dict):
        raise ValueError("object_probe must be a JSON object")
    mp = data.get("mutex_probe")
    if not isinstance(mp, dict):
        raise ValueError("mutex_probe must be a JSON object")
    ev = data.get("evaluation")
    if not isinstance(ev, dict):
        raise ValueError("evaluation must be a JSON object")
    _require_exact_keys(op, _OBJECT_PROBE_FIELDS, "object_probe")
    _require_exact_keys(mp, _MUTEX_PROBE_FIELDS, "mutex_probe")
    _require_exact_keys(ev, _EVALUATION_FIELDS, "evaluation")
    stored_digest = data.get("evidence_digest")
    if not isinstance(stored_digest, str) or len(stored_digest) != 64:
        raise ValueError("evidence_digest must be a 64-character string")

    obs_list = op.get("observations")
    if not isinstance(obs_list, list) or not obs_list:
        raise ValueError("object_probe.observations must be a non-empty list")
    observations: list[BoundaryObservationV1] = []
    for i, obs_data in enumerate(obs_list):
        if not isinstance(obs_data, dict):
            raise ValueError("each observation must be a JSON object")
        obs_key = f"object_probe.observations[{i}]"
        _require_exact_keys(obs_data, _OBSERVATION_FIELDS, obs_key)
        observations.append(
            BoundaryObservationV1(
                code=_require_str(obs_data, f"{obs_key}.code"),
                lexical_path=_require_str(obs_data, f"{obs_key}.lexical_path"),
                final_path=_require_str(obs_data, f"{obs_key}.final_path"),
                expected_volume_serial=_require_int(
                    obs_data, f"{obs_key}.expected_volume_serial"
                ),
                observed_volume_serial=_require_int(
                    obs_data, f"{obs_key}.observed_volume_serial"
                ),
                expected_file_id_128=bytes.fromhex(
                    _require_str(obs_data, f"{obs_key}.expected_file_id_128")
                ),
                observed_file_id_128=bytes.fromhex(
                    _require_str(obs_data, f"{obs_key}.observed_file_id_128")
                ),
                object_kind=_ensure_object_kind(obs_data.get("object_kind")),
                link_count=_require_int(obs_data, f"{obs_key}.link_count"),
                reparse_tag=_require_int(obs_data, f"{obs_key}.reparse_tag"),
                acl_observable=_require_bool(obs_data, f"{obs_key}.acl_observable"),
            )
        )
    object_probe = WorkspaceObjectProbeResultV1(
        observations=tuple(observations),
        cleanup_verified=_require_bool(op, "object_probe.cleanup_verified"),
    )
    mutex_probe = WorkspaceMutexProbeResultV1(
        workspace_identity_digest=_require_str(
            mp, "mutex_probe.workspace_identity_digest"
        ),
        contender_count=_require_int(mp, "mutex_probe.contender_count"),
        maximum_concurrent_holders=_require_int(
            mp, "mutex_probe.maximum_concurrent_holders"
        ),
        timeout_count=_require_int(mp, "mutex_probe.timeout_count"),
        cleanup_verified=_require_bool(mp, "mutex_probe.cleanup_verified"),
    )

    # P1-1: recompute evaluation from observations and require equality
    recomputed_evaluation = evaluate_workspace_observations(tuple(observations))
    stored_passed = _require_bool(ev, "evaluation.passed")
    failed_codes_raw = ev.get("failed_codes")
    if not isinstance(failed_codes_raw, list):
        raise ValueError("evaluation.failed_codes must be a JSON array")
    stored_codes: list[str] = []
    for i, code in enumerate(failed_codes_raw):
        if not isinstance(code, str):
            raise ValueError(f"evaluation.failed_codes[{i}] must be a JSON string")
        stored_codes.append(code)
    if (
        recomputed_evaluation.passed != stored_passed
        or recomputed_evaluation.failed_codes != tuple(stored_codes)
    ):
        raise ValueError(
            "evaluation inconsistent with observations — stored evaluation "
            "does not match recomputed evaluation"
        )

    evaluation = recomputed_evaluation

    # P1-1: re-derive outcome from evidence using the shared predicate
    derived_go = _go_predicate(evaluation, object_probe, mutex_probe)
    derived_outcome: Literal["GO", "NO_GO"] = "GO" if derived_go else "NO_GO"
    if outcome != derived_outcome:
        raise ValueError(
            "outcome inconsistent with evidence — stored outcome does not "
            "match derived outcome from observations"
        )

    body: dict[str, object] = {
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
    report = _deserialize_report(data, root)
    if report.outcome != "GO":
        raise ValueError("terminal evidence file must record a GO outcome")
    return report
