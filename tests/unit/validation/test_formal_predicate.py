"""T21.1 legacy step 21.C: pure formal-success predicate tests.

``evaluate_formal_success`` revalidates the exact Manifest, candidate
revision and bytes, policy/environment, target fingerprint, plan digest,
request identities, and evidence bindings without reading ambient state,
requires the complete formal plan to have one authoritative passing
result and successful teardown/cleanup for every request, and creates
``VerifiedCandidateV1`` only for exact current complete passing evidence;
every skip/error/timeout/missing/duplicate/drift/fingerprint mismatch
returns one typed ``FormalValidationFailureV1`` (SPEC §4.5 formal
success predicate, GREEN-1..GREEN-4).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable, cast

import pytest

# The predicate contracts are pydantic runtime models; the hash-locked
# gate toolchain does not install runtime dependencies, so this module
# skips cleanly there instead of failing at collection (formal env runs
# it fully).
pytest.importorskip("pydantic")

from vespercode.candidate.final_diff import FinalDiffV1, recompute_final_diff
from vespercode.candidate.identity import bind_revision_identity
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.evidence import ArtifactRefV1, DigestV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.execution.cleanup import ExecutionCleanupResultV1
from vespercode.execution.docker_executor import RawExecutionResultV1
from vespercode.profiles.reference import (
    ReferenceProfileManifestV1,
    load_reference_profile,
)
from vespercode.trees.candidate import CandidateRevisionV1, root_candidate_revision
from vespercode.trees.content_store import ContentObjectRefV1, ContentObjectStore
from vespercode.trees.snapshot import (
    SealedSnapshotInputFileV1,
    SnapshotDirectoryEntryV1,
    SnapshotEntryV1,
    SnapshotFileEntryV1,
    SnapshotTreeV1,
    _root_digest,
)
from vespercode.trees.text_classifier import TextMetadataV1, classify_supported_text
from vespercode.validation.baseline import (
    BaselineTestRecordV1,
    PassingBaselineV1,
    RuntimeCompatibleV1,
    compute_environment_whitelist_digest,
    compute_protected_artifact_set_digest,
    compute_resource_parameters_digest,
)
from pydantic import ValidationError

from vespercode.validation.check_result import (
    CheckFindingV1,
    CheckResultV1,
    _raw_evidence_digest,
)
from vespercode.validation.formal import (
    FormalValidationFailureV1,
    VerifiedCandidateV1,
    evaluate_formal_success,
)
from vespercode.validation.formal_execution import (
    FormalRequestEvidenceV1,
    FormalRequestRejectionV1,
    FormalValidationEvidenceV1,
    formal_validation_evidence_digest,
)
from vespercode.validation.formal_plan import (
    FormalValidationPlanV1,
    build_formal_validation_plan,
)
from vespercode.validation.manifest import (
    ManifestBindingsV1,
    ValidationManifestV1,
    create_validation_manifest,
)

_ADD = "tests/test_calculator.py::test_add_returns_sum"
_MULTIPLY = "tests/test_calculator.py::test_multiply_returns_product"
_A = "a" * 64
_B = "b" * 64
_C = "c" * 64
_D = "d" * 64
_E = "e" * 64
_F = "f" * 64
_ZERO = "0" * 64
_PLUGIN_VERSION = "1"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _frozen_manifest() -> ReferenceProfileManifestV1:
    return load_reference_profile(
        (
            _repo_root()
            / "src"
            / "vespercode"
            / "profiles"
            / "builtin"
            / "reference-profile-v1.json"
        ).read_bytes()
    )


def _supported_pyproject_bytes() -> bytes:
    return (
        b"[project]\n"
        b'name = "vesper-fixture"\n'
        b'version = "0.1.0"\n'
        b'requires-python = ">=3.12,<3.13"\n'
        b"\n"
        b"[tool.pytest.ini_options]\n"
        b'testpaths = ["tests"]\n'
        b'pythonpath = ["src"]\n'
        b"\n"
        b"[tool.ruff]\n"
        b"line-length = 88\n"
        b"\n"
        b"[tool.mypy]\n"
        b'python_version = "3.12"\n'
        b"strict = true\n"
    )


def _workspace_files() -> tuple[tuple[str, bytes], ...]:
    fixture = _repo_root() / "reference" / "fixture"
    return (
        ("pyproject.toml", _supported_pyproject_bytes()),
        ("requirements.lock", (fixture / "requirements.lock").read_bytes()),
        (
            "src/vesper_fixture/calculator.py",
            (fixture / "src/vesper_fixture/calculator.py").read_bytes(),
        ),
        (
            "tests/test_calculator.py",
            (fixture / "tests/test_calculator.py").read_bytes(),
        ),
    )


def _sealed_snapshot() -> SnapshotTreeV1:
    """One sealed Snapshot over the supported workspace bytes (T10.2)."""
    store = ContentObjectStore()
    rows: list[SealedSnapshotInputFileV1] = []
    for rel, raw in _workspace_files():
        ref = store.put(raw)
        rows.append(
            SealedSnapshotInputFileV1(
                schema_version=1,
                path=CanonicalRelativePathV1(rel),
                content_sha256=ref.sha256,
                byte_count=ref.byte_count,
            )
        )
    rows.sort(key=lambda row: row.path.value)
    directory_values = {
        "/".join(row.path.value.split("/")[:index])
        for row in rows
        for index in range(1, len(row.path.value.split("/")))
    }
    entries: list[SnapshotEntryV1] = [
        SnapshotDirectoryEntryV1(kind="DIRECTORY", path=CanonicalRelativePathV1(value))
        for value in sorted(directory_values)
    ]
    for row in rows:
        ref = ContentObjectRefV1(sha256=row.content_sha256, byte_count=row.byte_count)
        classification = classify_supported_text(store.get(ref))
        text_profile: PresentV1[TextMetadataV1] | AbsentV1 = (
            classification.text_profile
            if classification.kind == "TEXT_FILE"
            else AbsentV1(kind="ABSENT")
        )
        entries.append(
            SnapshotFileEntryV1(
                kind=classification.kind,
                path=row.path,
                size_bytes=row.byte_count,
                content_ref=ref,
                text_profile=text_profile,
            )
        )
    policy_digest = _frozen_manifest().editable_path_policy.digest
    return SnapshotTreeV1(
        root_digest=_root_digest(policy_digest, tuple(entries)),
        repository_policy_digest=policy_digest,
        entries=tuple(entries),
        file_bytes=tuple(
            (
                row.path.value,
                store.get(
                    ContentObjectRefV1(
                        sha256=row.content_sha256, byte_count=row.byte_count
                    )
                ),
            )
            for row in rows
        ),
    )


def _record(
    node_id: str,
    status: str,
    *,
    fingerprint: str | None = None,
) -> BaselineTestRecordV1:
    return BaselineTestRecordV1(
        schema_version=1,
        node_id=node_id,
        status=status,  # type: ignore[arg-type]
        error_phase=AbsentV1(kind="ABSENT"),
        failure_fingerprint_digest=(
            PresentV1(kind="PRESENT", value=DigestV1(value=fingerprint))
            if fingerprint is not None
            else AbsentV1(kind="ABSENT")
        ),
    )


def _passing_baseline(snapshot: SnapshotTreeV1) -> PassingBaselineV1:
    frozen = _frozen_manifest()
    return PassingBaselineV1(
        schema_version=1,
        kind="PASSING",
        plan_digest=_A,
        check_plan_version=frozen.check_plan_version,
        adapter_version="1",
        python_version=frozen.python_version,
        pytest_version=frozen.pytest_version,
        report_plugin_version=frozen.report_plugin_version,
        ruff_version=frozen.ruff_version,
        mypy_version=frozen.mypy_version,
        docker_image_digest=frozen.docker_image_digest,
        docker_execution_profile_version=1,
        reference_profile_digest=frozen.digest,
        snapshot_root_digest=snapshot.root_digest,
        repository_policy_digest=snapshot.repository_policy_digest,
        target_test_ids=(_ADD,),
        collected_node_ids=(_ADD, _MULTIPLY),
        collect_only_evidence_digests=(_A, _A),
        full_pytest_evidence_digest=_B,
        target_rerun_evidence_digest=_C,
        ruff_result_digest=_D,
        mypy_result_digest=_E,
        baseline_test_records=(
            _record(_ADD, "FAIL", fingerprint=_F),
            _record(_MULTIPLY, "PASS"),
        ),
        protected_artifact_set_digest=compute_protected_artifact_set_digest(snapshot),
        runtime_compatibility=RuntimeCompatibleV1(
            schema_version=1,
            status="COMPATIBLE",
            reference_profile_digest=frozen.digest,
            evidence_digest=_E,
        ),
    )


def _manifest(snapshot: SnapshotTreeV1) -> ValidationManifestV1:
    return create_validation_manifest(
        _passing_baseline(snapshot),
        ManifestBindingsV1(
            schema_version=1,
            resource_parameters_digest=compute_resource_parameters_digest(),
            environment_whitelist_digest=compute_environment_whitelist_digest(),
        ),
    )


def _candidate(snapshot: SnapshotTreeV1) -> tuple[CandidateRevisionV1, FinalDiffV1]:
    store = ContentObjectStore()
    for _path, raw in snapshot.file_bytes:
        store.put(raw)
    revision = root_candidate_revision(snapshot, store)
    diff = recompute_final_diff(
        snapshot, revision.tree, _frozen_manifest().editable_path_policy
    )
    return bind_revision_identity(revision, diff.digest), diff


def _plan(snapshot: SnapshotTreeV1) -> FormalValidationPlanV1:
    revision, diff = _candidate(snapshot)
    result = build_formal_validation_plan(_manifest(snapshot), revision, diff)
    assert isinstance(result, FormalValidationPlanV1)
    return result


def _absent() -> dict[str, str]:
    return {"kind": "ABSENT"}


def _present_text(value: str) -> dict[str, object]:
    return {"kind": "PRESENT", "value": value}


def _exception_document(
    exception_type: str = "AssertionError",
    normalized_message: str = "assert 0 == 4",
    assertion_diff: str | None = "assert 0 == 4\n  where 0 = add(2, 2)",
    frames: tuple[tuple[str, str, int], ...] = (
        ("tests/test_calculator.py", "test_add_returns_sum", 5),
    ),
) -> dict[str, object]:
    return {
        "exception_type": exception_type,
        "normalized_message": normalized_message,
        "normalized_assertion_diff": (
            _present_text(assertion_diff) if assertion_diff is not None else _absent()
        ),
        "project_frames": [
            {
                "relative_path": relative_path,
                "function_name": function_name,
                "line_number": line_number,
            }
            for relative_path, function_name, line_number in frames
        ],
    }


def _event(sequence: int, event_type: str, **fields: object) -> dict[str, object]:
    event: dict[str, object] = {"sequence": sequence, "event_type": event_type}
    for name in (
        "node_id",
        "phase",
        "outcome",
        "wasxfail",
        "exception",
        "display_summary",
    ):
        event[name] = fields.pop(name, _absent())
    if fields:
        raise AssertionError(f"unknown event field: {sorted(fields)}")
    return event


def _phase_event(
    sequence: int,
    node_id: str,
    phase: str,
    outcome: str,
    exception: dict[str, object] | None = None,
) -> dict[str, object]:
    fields: dict[str, object] = {
        "node_id": _present_text(node_id),
        "phase": {"kind": "PRESENT", "value": phase},
        "outcome": {"kind": "PRESENT", "value": outcome},
    }
    if exception is not None:
        fields["exception"] = {"kind": "PRESENT", "value": exception}
    return _event(sequence, "TEST_PHASE", **fields)


def _evidence_document(
    *,
    run_kind: str,
    planned: tuple[str, ...],
    collected: tuple[str, ...],
    events: list[dict[str, object]],
    pytest_exit_code: int,
) -> object:
    """One canonical GATEEV1 report document (the exact §0.1 form)."""
    body: dict[str, object] = {
        "schema_version": 1,
        "report_plugin_version": _PLUGIN_VERSION,
        "run_kind": run_kind,
        "planned_node_ids": list(planned),
        "collected_node_ids": list(collected),
        "events": events,
        "pytest_exit_code": pytest_exit_code,
        "event_count": len(events),
        "normal_end_marker": True,
    }
    digest = hashlib.sha256(
        b"VesperCode\x00PytestEvidenceV1\x001\x00"
        + json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    from vespercode.validation.pytest_evidence import PytestEvidenceV1

    return PytestEvidenceV1.model_validate({**body, "integrity_digest": digest})


def _collect_evidence() -> object:
    events: list[dict[str, object]] = [_event(1, "SESSION_START")]
    for index, node_id in enumerate((_ADD, _MULTIPLY), start=2):
        events.append(_event(index, "COLLECTION_ITEM", node_id=_present_text(node_id)))
    events.append(_event(len(events) + 1, "SESSION_END"))
    return _evidence_document(
        run_kind="COLLECT_ONLY",
        planned=(_ADD, _MULTIPLY),
        collected=(_ADD, _MULTIPLY),
        events=events,
        pytest_exit_code=0,
    )


def _collect_evidence_with_session_error() -> object:
    events: list[dict[str, object]] = [_event(1, "SESSION_START")]
    for index, node_id in enumerate((_ADD, _MULTIPLY), start=2):
        events.append(_event(index, "COLLECTION_ITEM", node_id=_present_text(node_id)))
    events.append(
        _event(
            len(events) + 1,
            "SESSION_ERROR",
            exception={
                "kind": "PRESENT",
                "value": {
                    "exception_type": "CollectionError",
                    "normalized_message": "failed to import test module",
                    "normalized_assertion_diff": _absent(),
                    "project_frames": [],
                },
            },
        )
    )
    events.append(_event(len(events) + 1, "SESSION_END"))
    return _evidence_document(
        run_kind="COLLECT_ONLY",
        planned=(_ADD, _MULTIPLY),
        collected=(_ADD, _MULTIPLY),
        events=events,
        pytest_exit_code=1,
    )


def _full_events(
    add_outcome: str = "PASS",
    multiply_outcome: str = "PASS",
    deselected_node: str | None = None,
    session_error: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    """The production reporter shape: one TEST_PHASE event per phase."""
    events: list[dict[str, object]] = [_event(1, "SESSION_START")]
    events.append(_event(2, "COLLECTION_ITEM", node_id=_present_text(_ADD)))
    events.append(_event(3, "COLLECTION_ITEM", node_id=_present_text(_MULTIPLY)))
    index = 4
    if session_error is not None:
        events.append(_event(index, "SESSION_ERROR", exception=session_error))
        index += 1
    if deselected_node is not None:
        events.append(
            _event(index, "DESELECTED", node_id=_present_text(deselected_node))
        )
        index += 1
    add_events, index = _node_phase_events(_ADD, index, add_outcome)
    events.extend(add_events)
    multiply_events, index = _node_phase_events(
        _MULTIPLY,
        index,
        multiply_outcome,
        frames=(("tests/test_calculator.py", "test_multiply_returns_product", 9),),
    )
    events.extend(multiply_events)
    events.append(_event(index, "SESSION_END"))
    return events


def _node_phase_events(
    node_id: str,
    start: int,
    call_outcome: str,
    call_message: str | None = None,
    frames: tuple[tuple[str, str, int], ...] = (
        ("tests/test_calculator.py", "test_add_returns_sum", 5),
    ),
) -> tuple[list[dict[str, object]], int]:
    if call_outcome == "SKIP":
        return [
            _phase_event(start, node_id, "SETUP", "SKIP"),
            _phase_event(start + 1, node_id, "TEARDOWN", "PASS"),
        ], start + 2
    events = [_phase_event(start, node_id, "SETUP", "PASS")]
    if call_outcome == "FAIL":
        events.append(
            _phase_event(
                start + 1,
                node_id,
                "CALL",
                "FAIL",
                exception=_exception_document(
                    normalized_message=call_message or "assert 0 == 4",
                    frames=frames,
                ),
            )
        )
    else:
        events.append(_phase_event(start + 1, node_id, "CALL", call_outcome))
    events.append(_phase_event(start + 2, node_id, "TEARDOWN", "PASS"))
    return events, start + 3


def _full_evidence(
    add_outcome: str = "PASS",
    multiply_outcome: str = "PASS",
    deselected_node: str | None = None,
    session_error: dict[str, object] | None = None,
    collected: tuple[str, ...] = (_ADD, _MULTIPLY),
) -> object:
    failed = (
        add_outcome in ("FAIL", "ERROR")
        or multiply_outcome in ("FAIL", "ERROR")
        or session_error is not None
    )
    return _evidence_document(
        run_kind="FULL_PYTEST",
        planned=(_ADD, _MULTIPLY),
        collected=collected,
        events=_full_events(
            add_outcome=add_outcome,
            multiply_outcome=multiply_outcome,
            deselected_node=deselected_node,
            session_error=session_error,
        ),
        pytest_exit_code=1 if failed else 0,
    )


def _clean_raw(
    request_id: str, stdout: bytes = b"", exit_code: int = 0
) -> RawExecutionResultV1:
    return RawExecutionResultV1(
        schema_version=1,
        request_id=request_id,
        container_id=f"fake-{request_id}",
        exit_code=exit_code,
        stdout=stdout,
        stderr=b"",
        output_bytes=len(stdout),
        timed_out=False,
        output_limit_exceeded=False,
        container_stopped=False,
        error_code=None,
    )


def _clean_cleanup() -> ExecutionCleanupResultV1:
    return ExecutionCleanupResultV1(
        schema_version=1,
        container_removed=True,
        materialization_removed=True,
        workspace_unchanged=True,
        residual_artifact=None,
    )


def _pytest_row(
    plan: FormalValidationPlanV1,
    index: int,
    *,
    evidence: object | None = None,
    parse_error: str | None = None,
    raw: RawExecutionResultV1 | None = None,
    cleanup: ExecutionCleanupResultV1 | None = None,
) -> FormalRequestEvidenceV1:
    request = plan.execution_requests[index]
    raw_value = raw if raw is not None else _clean_raw(request.request_id)
    cleanup_value = cleanup if cleanup is not None else _clean_cleanup()
    pytest_evidence: AbsentV1 | PresentV1[object]
    parse_error_value: AbsentV1 | PresentV1[str]
    if parse_error is not None:
        pytest_evidence = AbsentV1(kind="ABSENT")
        parse_error_value = PresentV1(kind="PRESENT", value=parse_error)
    else:
        pytest_evidence = PresentV1(kind="PRESENT", value=evidence)
        parse_error_value = AbsentV1(kind="ABSENT")
    return FormalRequestEvidenceV1(
        schema_version=1,
        request_id=request.request_id,
        check_kind=request.check_kind,
        rejection=AbsentV1(kind="ABSENT"),
        raw=raw_value,
        cleanup=cleanup_value,
        pytest_evidence=pytest_evidence,  # type: ignore[arg-type]
        tool_result=AbsentV1(kind="ABSENT"),
        parse_error=parse_error_value,
    )


def _tool_row(
    plan: FormalValidationPlanV1,
    index: int,
    *,
    result: CheckResultV1 | None = None,
    raw: RawExecutionResultV1 | None = None,
    cleanup: ExecutionCleanupResultV1 | None = None,
) -> FormalRequestEvidenceV1:
    request = plan.execution_requests[index]
    raw_value = raw if raw is not None else _clean_raw(request.request_id)
    cleanup_value = cleanup if cleanup is not None else _clean_cleanup()
    return FormalRequestEvidenceV1(
        schema_version=1,
        request_id=request.request_id,
        check_kind=request.check_kind,
        rejection=AbsentV1(kind="ABSENT"),
        raw=raw_value,
        cleanup=cleanup_value,
        pytest_evidence=AbsentV1(kind="ABSENT"),
        tool_result=PresentV1(
            kind="PRESENT",
            value=(
                result
                if result is not None
                else CheckResultV1(
                    status="PASS",
                    check_kind=request.check_kind,  # type: ignore[arg-type]
                    structured_findings=(),
                    raw_digest=_raw_evidence_digest(raw_value),
                )
            ),
        ),
        parse_error=AbsentV1(kind="ABSENT"),
    )


def _passing_evidence(
    plan: FormalValidationPlanV1,
    *,
    add_outcome: str = "PASS",
    multiply_outcome: str = "PASS",
    deselected_node: str | None = None,
    session_error: dict[str, object] | None = None,
    collected: tuple[str, ...] = (_ADD, _MULTIPLY),
    teardown_cleanup: ExecutionCleanupResultV1 | None = None,
) -> FormalValidationEvidenceV1:
    """One complete clean evidence bundle over the frozen plan."""
    rows = (
        _pytest_row(plan, 0, evidence=_collect_evidence()),
        _pytest_row(
            plan,
            1,
            evidence=_full_evidence(
                add_outcome=add_outcome,
                multiply_outcome=multiply_outcome,
                deselected_node=deselected_node,
                session_error=session_error,
                collected=collected,
            ),
            cleanup=teardown_cleanup,
        ),
        _tool_row(plan, 2),
        _tool_row(plan, 3),
    )
    return _evidence(plan, rows=rows)


def _evidence(
    plan: FormalValidationPlanV1,
    rows: tuple[FormalRequestEvidenceV1, ...],
    *,
    executed_request_ids: tuple[str, ...] | None = None,
    missing_request_ids: tuple[str, ...] = (),
    duplicate_request_ids: tuple[str, ...] = (),
) -> FormalValidationEvidenceV1:
    """One closed evidence via the digest two-pass (the model re-validates)."""
    if executed_request_ids is None:
        executed_request_ids = tuple(
            row.request_id for row in rows if isinstance(row.rejection, AbsentV1)
        )
    complete = (
        missing_request_ids == ()
        and duplicate_request_ids == ()
        and all(
            isinstance(row.rejection, AbsentV1)
            and row.raw is not None
            and row.raw.error_code is None
            and row.cleanup is not None
            and row.cleanup.container_removed
            and row.cleanup.materialization_removed
            and row.cleanup.workspace_unchanged
            and isinstance(row.parse_error, AbsentV1)
            for row in rows
        )
    )
    document = {
        "schema_version": 1,
        "plan_digest": plan.digest,
        "executed_request_ids": executed_request_ids,
        "evidence": rows,
        "missing_request_ids": missing_request_ids,
        "duplicate_request_ids": duplicate_request_ids,
        "complete": complete,
    }
    probe = FormalValidationEvidenceV1.model_construct(**document)  # type: ignore[arg-type]
    return FormalValidationEvidenceV1.model_validate(
        {**document, "evidence_digest": formal_validation_evidence_digest(probe)}
    )


def manifest() -> ValidationManifestV1:
    return _manifest(_sealed_snapshot())


def candidate() -> CandidateRevisionV1:
    return _candidate(_sealed_snapshot())[0]


def plan() -> FormalValidationPlanV1:
    return _plan(_sealed_snapshot())


def evidence_without_teardown() -> FormalValidationEvidenceV1:
    """One evidence whose FULL_PYTEST teardown/cleanup failed (the
    container was not removed), so the row is not clean."""
    plan_value = plan()
    failed_cleanup = ExecutionCleanupResultV1(
        schema_version=1,
        container_removed=False,
        materialization_removed=True,
        workspace_unchanged=True,
        residual_artifact=ArtifactRefV1(
            artifact_id="container",
            digest=DigestV1(value=_ZERO),
        ),
    )
    return _passing_evidence(plan_value, teardown_cleanup=failed_cleanup)


def evidence() -> FormalValidationEvidenceV1:
    return _passing_evidence(plan())


def test_swapped_raw_evidence_rejects_at_row_construction() -> None:
    # Raw evidence from another request pasted into this row rejects: the
    # raw identity must bind the exact row identity.
    plan_value = plan()
    with pytest.raises(ValidationError):
        _pytest_row(
            plan_value,
            1,
            evidence=_full_evidence(),
            raw=_clean_raw("some-other-request"),
        )


def test_swapped_pytest_run_kind_rejects_at_row_construction() -> None:
    # A COLLECT_ONLY report pasted into the FULL_PYTEST row rejects: the
    # pytest evidence run_kind must equal the row check kind.
    plan_value = plan()
    with pytest.raises(ValidationError):
        _pytest_row(plan_value, 1, evidence=_collect_evidence())


def test_swapped_tool_result_rejects_at_row_construction() -> None:
    plan_value = plan()
    ruff_request = plan_value.execution_requests[2]
    # A MYPY PASS pasted into the RUFF row rejects: the tool result check
    # kind must equal the row check kind.
    with pytest.raises(ValidationError):
        _tool_row(
            plan_value,
            2,
            result=CheckResultV1(
                status="PASS",
                check_kind="MYPY",
                structured_findings=(),
                raw_digest=_raw_evidence_digest(_clean_raw(ruff_request.request_id)),
            ),
        )
    # A PASS whose raw_digest does not bind the row's raw evidence rejects.
    with pytest.raises(ValidationError):
        _tool_row(
            plan_value,
            2,
            result=CheckResultV1(
                status="PASS",
                check_kind="RUFF",
                structured_findings=(),
                raw_digest=_ZERO,
            ),
        )


def test_missing_teardown_evidence_cannot_verify_candidate() -> None:
    result = evaluate_formal_success(
        manifest(), candidate(), plan(), evidence_without_teardown()
    )
    assert isinstance(result, FormalValidationFailureV1)


def test_complete_passing_evidence_creates_verified_candidate() -> None:
    manifest_value = manifest()
    candidate_value = candidate()
    plan_value = plan()
    result = evaluate_formal_success(
        manifest_value, candidate_value, plan_value, evidence()
    )
    assert isinstance(result, VerifiedCandidateV1)
    assert result.candidate_id == candidate_value.candidate_digest
    assert result.manifest_id == manifest_value.digest
    assert len(result.formal_result_digest) == 64
    # Deterministic: identical inputs create the identical verified
    # candidate (formal_result_digest self-binds the complete result).
    again = evaluate_formal_success(
        manifest_value, candidate_value, plan_value, evidence()
    )
    assert isinstance(again, VerifiedCandidateV1)
    assert again.formal_result_digest == result.formal_result_digest


def _tool_result(
    plan: FormalValidationPlanV1,
    index: int,
    status: str,
    raw: RawExecutionResultV1 | None = None,
) -> CheckResultV1:
    request = plan.execution_requests[index]
    # The result must bind the exact raw evidence of the row it sits in
    # (the row default raw is the clean raw for the same request id).
    raw_value = raw if raw is not None else _clean_raw(request.request_id)
    raw_digest = _raw_evidence_digest(raw_value)
    if status == "PASS":
        return CheckResultV1(
            status="PASS",
            check_kind=request.check_kind,  # type: ignore[arg-type]
            structured_findings=(),
            raw_digest=raw_digest,
        )
    if status == "FAIL":
        return CheckResultV1(
            status="FAIL",
            check_kind=request.check_kind,  # type: ignore[arg-type]
            structured_findings=(
                CheckFindingV1(
                    error_code="CHECK_FAILED",
                    message="found lint errors",
                    location=None,
                ),
            ),
            raw_digest=raw_digest,
        )
    return CheckResultV1(
        status="ERROR",
        check_kind=request.check_kind,  # type: ignore[arg-type]
        structured_findings=(
            CheckFindingV1(
                error_code="CHECK_ERROR",
                message="parse failure",
                location=None,
            ),
        ),
        raw_digest=raw_digest,
    )


_VERIFICATION_MATRIX: tuple[tuple[str, str, str, str, str, str, str], ...] = (
    (
        "complete passing evidence",
        "manifest",
        "candidate",
        "plan",
        "evidence",
        "VERIFIED",
        "",
    ),
    (
        "missing teardown evidence",
        "manifest",
        "candidate",
        "plan",
        "evidence_without_teardown",
        "EXECUTION_WORKSPACE_MUTATED",
        "left execution residue",
    ),
    (
        "stale candidate identity",
        "manifest",
        "stale_candidate",
        "plan",
        "evidence",
        "CANDIDATE_STALE",
        "candidate identity",
    ),
    (
        "plan digest drift",
        "manifest",
        "candidate",
        "drifted_plan",
        "evidence",
        "TREE_INTEGRITY_FAILED",
        "plan digest",
    ),
    (
        "manifest drift",
        "drifted_manifest",
        "candidate",
        "plan",
        "evidence",
        "TREE_INTEGRITY_FAILED",
        "Manifest digest",
    ),
    (
        "evidence binds a different plan",
        "manifest",
        "candidate",
        "plan",
        "foreign_evidence",
        "FORMAL_VALIDATION_FAILED",
        "does not bind the exact executed plan",
    ),
    (
        "missing execution",
        "manifest",
        "candidate",
        "plan",
        "missing_execution_evidence",
        "FORMAL_VALIDATION_FAILED",
        "did not execute completely",
    ),
    (
        "duplicate execution",
        "manifest",
        "candidate",
        "plan",
        "duplicate_execution_evidence",
        "FORMAL_VALIDATION_FAILED",
        "did not execute completely",
    ),
    (
        "raw timeout",
        "manifest",
        "candidate",
        "plan",
        "timeout_evidence",
        "CHECK_TIMEOUT",
        "timed out",
    ),
    (
        "raw execution error",
        "manifest",
        "candidate",
        "plan",
        "execution_error_evidence",
        "CHECK_ERROR",
        "failed at the execution layer",
    ),
    (
        "unparseable report",
        "manifest",
        "candidate",
        "plan",
        "reporter_invalid_evidence",
        "REPORTER_INVALID",
        "REPORTER_INVALID",
    ),
    (
        "workspace mutation",
        "manifest",
        "candidate",
        "plan",
        "workspace_mutated_evidence",
        "EXECUTION_WORKSPACE_MUTATED",
        "mutated the execution workspace",
    ),
    (
        "collection drift",
        "manifest",
        "candidate",
        "plan",
        "collection_drift_evidence",
        "FORMAL_VALIDATION_FAILED",
        "collection",
    ),
    (
        "forbidden deselected state",
        "manifest",
        "candidate",
        "plan",
        "deselected_evidence",
        "FORMAL_VALIDATION_FAILED",
        "deselected",
    ),
    (
        "forbidden skip state",
        "manifest",
        "candidate",
        "plan",
        "skipped_evidence",
        "FORMAL_VALIDATION_FAILED",
        "forbidden state",
    ),
    (
        "session collection error",
        "manifest",
        "candidate",
        "plan",
        "session_error_evidence",
        "FORMAL_VALIDATION_FAILED",
        "session/collection error",
    ),
    (
        "collect run session collection error",
        "manifest",
        "candidate",
        "plan",
        "collect_session_error_evidence",
        "FORMAL_VALIDATION_FAILED",
        "session/collection error",
    ),
    (
        "target still failing",
        "manifest",
        "candidate",
        "plan",
        "target_failing_evidence",
        "FORMAL_VALIDATION_FAILED",
        "did not actually execute and pass",
    ),
    (
        "ruff not passing",
        "manifest",
        "candidate",
        "plan",
        "ruff_failed_evidence",
        "CHECK_ERROR",
        "did not pass its check",
    ),
    (
        "mypy errored",
        "manifest",
        "candidate",
        "plan",
        "mypy_error_evidence",
        "CHECK_ERROR",
        "did not pass its check",
    ),
)


def _stale_candidate() -> CandidateRevisionV1:
    return candidate().model_copy(update={"candidate_digest": _ZERO})


def _drifted_plan() -> FormalValidationPlanV1:
    return plan().model_copy(update={"candidate_digest": _ZERO})


def _drifted_manifest() -> ValidationManifestV1:
    return manifest().model_copy(update={"reference_profile_digest": _ZERO})


def _foreign_evidence() -> FormalValidationEvidenceV1:
    return _passing_evidence(plan()).model_copy(update={"plan_digest": _ZERO})


def _missing_execution_evidence() -> FormalValidationEvidenceV1:
    plan_value = plan()
    rows = _passing_evidence(plan_value).evidence
    rejected = rows[1].model_copy(
        update={
            "rejection": PresentV1(
                kind="PRESENT",
                value=FormalRequestRejectionV1(
                    schema_version=1,
                    code="TREE_INTEGRITY_FAILED",
                    message="materialization failed",
                ),
            ),
            "raw": None,
            "cleanup": None,
            "pytest_evidence": AbsentV1(kind="ABSENT"),
            "tool_result": AbsentV1(kind="ABSENT"),
            "parse_error": AbsentV1(kind="ABSENT"),
        }
    )
    return _evidence(
        plan_value,
        rows=(rows[0], rejected, rows[2], rows[3]),
        missing_request_ids=(plan_value.request_ids[1],),
    )


def _duplicate_execution_evidence() -> FormalValidationEvidenceV1:
    plan_value = plan()
    rows = _passing_evidence(plan_value).evidence
    return _evidence(
        plan_value,
        rows=(rows[0], rows[1], rows[1], rows[2], rows[3]),
        executed_request_ids=(
            plan_value.request_ids[0],
            plan_value.request_ids[1],
            plan_value.request_ids[1],
            plan_value.request_ids[2],
            plan_value.request_ids[3],
        ),
        duplicate_request_ids=(plan_value.request_ids[1],),
    )


def _timeout_evidence() -> FormalValidationEvidenceV1:
    plan_value = plan()
    rows = _passing_evidence(plan_value).evidence
    raw = rows[1].raw
    assert raw is not None
    timed_out = raw.model_copy(
        update={
            "exit_code": None,
            "timed_out": True,
            "container_stopped": True,
            "error_code": "CHECK_TIMEOUT",
        }
    )
    failed = rows[1].model_copy(
        update={
            "raw": timed_out,
            "pytest_evidence": AbsentV1(kind="ABSENT"),
            "parse_error": PresentV1(kind="PRESENT", value="CHECK_TIMEOUT"),
        }
    )
    return _evidence(plan_value, rows=(rows[0], failed, rows[2], rows[3]))


def _execution_error_evidence() -> FormalValidationEvidenceV1:
    plan_value = plan()
    rows = _passing_evidence(plan_value).evidence
    error_raw = RawExecutionResultV1(
        schema_version=1,
        request_id=plan_value.request_ids[2],
        container_id="",
        exit_code=None,
        stdout=b"",
        stderr=b"",
        output_bytes=0,
        timed_out=False,
        output_limit_exceeded=False,
        container_stopped=False,
        error_code="CHECK_EXECUTION_ERROR",
    )
    failed = rows[2].model_copy(
        update={
            "raw": error_raw,
            "tool_result": PresentV1(
                kind="PRESENT",
                value=_tool_result(plan_value, 2, "ERROR", raw=error_raw),
            ),
        }
    )
    return _evidence(plan_value, rows=(rows[0], rows[1], failed, rows[3]))


def _reporter_invalid_evidence() -> FormalValidationEvidenceV1:
    plan_value = plan()
    rows = _passing_evidence(plan_value).evidence
    failed = rows[0].model_copy(
        update={
            "pytest_evidence": AbsentV1(kind="ABSENT"),
            "parse_error": PresentV1(kind="PRESENT", value="REPORTER_INVALID"),
        }
    )
    return _evidence(plan_value, rows=(failed, rows[1], rows[2], rows[3]))


def _workspace_mutated_evidence() -> FormalValidationEvidenceV1:
    plan_value = plan()
    rows = _passing_evidence(plan_value).evidence
    drifted = rows[1].model_copy(
        update={
            "cleanup": ExecutionCleanupResultV1(
                schema_version=1,
                container_removed=True,
                materialization_removed=True,
                workspace_unchanged=False,
                residual_artifact=ArtifactRefV1(
                    artifact_id="workspace",
                    digest=DigestV1(value=_ZERO),
                ),
            )
        }
    )
    return _evidence(plan_value, rows=(rows[0], drifted, rows[2], rows[3]))


def _collection_drift_evidence() -> FormalValidationEvidenceV1:
    plan_value = plan()
    rows = _passing_evidence(plan_value).evidence
    drifted = rows[1].model_copy(
        update={
            "pytest_evidence": PresentV1(
                kind="PRESENT",
                value=_full_evidence(
                    collected=(_ADD, _MULTIPLY, "tests/test_calculator.py::test_extra")
                ),
            )
        }
    )
    return _evidence(plan_value, rows=(rows[0], drifted, rows[2], rows[3]))


def _session_error_evidence() -> FormalValidationEvidenceV1:
    return _passing_evidence(
        plan(),
        session_error={
            "kind": "PRESENT",
            "value": {
                "exception_type": "CollectionError",
                "normalized_message": "failed to import test module",
                "normalized_assertion_diff": _absent(),
                "project_frames": [],
            },
        },
    )


def _collect_session_error_evidence() -> FormalValidationEvidenceV1:
    """One crafted-but-model-valid evidence whose COLLECT_ONLY row
    carries a session/collection error (the scan covers both pytest
    runs)."""
    plan_value = plan()
    rows = _passing_evidence(plan_value).evidence
    collect_error = rows[0].model_copy(
        update={
            "pytest_evidence": PresentV1(
                kind="PRESENT",
                value=_collect_evidence_with_session_error(),
            )
        }
    )
    return _evidence(plan_value, rows=(collect_error, rows[1], rows[2], rows[3]))


def _deselected_evidence() -> FormalValidationEvidenceV1:
    return _passing_evidence(plan(), deselected_node=_MULTIPLY)


def _skipped_evidence() -> FormalValidationEvidenceV1:
    return _passing_evidence(plan(), multiply_outcome="SKIP")


def _target_failing_evidence() -> FormalValidationEvidenceV1:
    return _passing_evidence(plan(), add_outcome="FAIL")


def _ruff_failed_evidence() -> FormalValidationEvidenceV1:
    plan_value = plan()
    rows = _passing_evidence(plan_value).evidence
    failed = rows[2].model_copy(
        update={
            "tool_result": PresentV1(
                kind="PRESENT", value=_tool_result(plan_value, 2, "FAIL")
            )
        }
    )
    return _evidence(plan_value, rows=(rows[0], rows[1], failed, rows[3]))


def _mypy_error_evidence() -> FormalValidationEvidenceV1:
    plan_value = plan()
    rows = _passing_evidence(plan_value).evidence
    failed = rows[3].model_copy(
        update={
            "tool_result": PresentV1(
                kind="PRESENT", value=_tool_result(plan_value, 3, "ERROR")
            )
        }
    )
    return _evidence(plan_value, rows=(rows[0], rows[1], rows[2], failed))


_FIXTURES: dict[str, Callable[[], object]] = {
    "manifest": manifest,
    "candidate": candidate,
    "plan": plan,
    "evidence": evidence,
    "evidence_without_teardown": evidence_without_teardown,
    "stale_candidate": _stale_candidate,
    "drifted_plan": _drifted_plan,
    "drifted_manifest": _drifted_manifest,
    "foreign_evidence": _foreign_evidence,
    "missing_execution_evidence": _missing_execution_evidence,
    "duplicate_execution_evidence": _duplicate_execution_evidence,
    "timeout_evidence": _timeout_evidence,
    "execution_error_evidence": _execution_error_evidence,
    "reporter_invalid_evidence": _reporter_invalid_evidence,
    "workspace_mutated_evidence": _workspace_mutated_evidence,
    "collection_drift_evidence": _collection_drift_evidence,
    "deselected_evidence": _deselected_evidence,
    "session_error_evidence": _session_error_evidence,
    "collect_session_error_evidence": _collect_session_error_evidence,
    "skipped_evidence": _skipped_evidence,
    "target_failing_evidence": _target_failing_evidence,
    "ruff_failed_evidence": _ruff_failed_evidence,
    "mypy_error_evidence": _mypy_error_evidence,
}


@pytest.mark.parametrize(
    "name, manifest_fixture, candidate_fixture, plan_fixture, evidence_fixture, expected, message",
    _VERIFICATION_MATRIX,
    ids=[row[0] for row in _VERIFICATION_MATRIX],
)
def test_formal_verification_predicate_matrix(
    name: str,
    manifest_fixture: str,
    candidate_fixture: str,
    plan_fixture: str,
    evidence_fixture: str,
    expected: str,
    message: str,
) -> None:
    """Only complete passing current evidence verifies; every skip/error/
    timeout/missing/duplicate/drift/fingerprint mismatch returns one
    typed failure (the SPEC §4.5 code with the exact violated condition
    bound deterministically in the message)."""
    result = evaluate_formal_success(
        cast(ValidationManifestV1, _FIXTURES[manifest_fixture]()),
        cast(CandidateRevisionV1, _FIXTURES[candidate_fixture]()),
        cast(FormalValidationPlanV1, _FIXTURES[plan_fixture]()),
        cast(FormalValidationEvidenceV1, _FIXTURES[evidence_fixture]()),
    )
    if expected == "VERIFIED":
        assert isinstance(result, VerifiedCandidateV1)
        return
    assert isinstance(result, FormalValidationFailureV1)
    assert result.error_code == expected
    assert message in result.error_message
