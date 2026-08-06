"""T20.2 legacy step 20.B: runtime compatibility check tests.

``evaluate_runtime_compatibility`` evaluates the SPEC §1.4.1 runtime
compatibility items over the complete closed Baseline evidence bundle:
stable non-empty collections (``COLLECTION_UNSTABLE``), post-execution
project-tree writes (``PROJECT_TREE_WRITE``), and pytest session errors
(``CHECK_ENVIRONMENT_ERROR``).  The remaining §1.4.1 violation kinds are
closed vocabulary entries constructible in the structured
``RuntimeBaselineBlockedV1`` but not emitted by the evaluator (an
incomplete report fails closed at the parse layer before a bundle exists;
external-service and VCS dependencies are not differentially observable
from the closed report schema — their observable class is the session
error).
"""

from __future__ import annotations

import hashlib
import json

import pytest

# The Baseline contracts are pydantic runtime models; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from src.vespercode.validation.baseline import (
    BaselineEvidenceBundleV1,
    RuntimeBaselineBlockedV1,
    RuntimeCompatibleV1,
    evaluate_runtime_compatibility,
)
from src.vespercode.validation.check_result import CheckResultV1
from src.vespercode.validation.pytest_evidence import PytestEvidenceV1

_ADD = "tests/test_calculator.py::test_add_returns_sum"
_MULTIPLY = "tests/test_calculator.py::test_multiply_returns_product"
_PLAN_DIGEST = "a" * 64
_REFERENCE_PROFILE_DIGEST = "b" * 64


def _absent() -> dict[str, str]:
    return {"kind": "ABSENT"}


def _present_text(value: str) -> dict[str, object]:
    return {"kind": "PRESENT", "value": value}


def _exception_document(
    exception_type: str = "AssertionError",
    normalized_message: str = "assert 0 == 4",
) -> dict[str, object]:
    return {
        "exception_type": exception_type,
        "normalized_message": normalized_message,
        "normalized_assertion_diff": _present_text("assert 0 == 4"),
        "project_frames": [
            {
                "relative_path": "tests/test_calculator.py",
                "function_name": "test_add_returns_sum",
                "line_number": 5,
            }
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


def _evidence(
    *,
    run_kind: str,
    collected: tuple[str, ...],
    planned: tuple[str, ...],
    events: list[dict[str, object]],
    exit_code: int,
) -> PytestEvidenceV1:
    body: dict[str, object] = {
        "schema_version": 1,
        "report_plugin_version": "1",
        "run_kind": run_kind,
        "planned_node_ids": list(planned),
        "collected_node_ids": list(collected),
        "events": events,
        "pytest_exit_code": exit_code,
        "event_count": len(events),
        "normal_end_marker": True,
    }
    digest = hashlib.sha256(
        b"VesperCode\x00PytestEvidenceV1\x001\x00"
        + json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    return PytestEvidenceV1.model_validate({**body, "integrity_digest": digest})


def _collect_evidence(
    collected: tuple[str, ...] = (_ADD, _MULTIPLY),
    session_error: bool = False,
) -> PytestEvidenceV1:
    events: list[dict[str, object]] = [_event(1, "SESSION_START")]
    for index, node_id in enumerate(collected, start=2):
        events.append(_event(index, "COLLECTION_ITEM", node_id=_present_text(node_id)))
    if session_error:
        events.append(
            _event(
                len(events) + 1,
                "SESSION_ERROR",
                exception={
                    "kind": "PRESENT",
                    "value": _exception_document(
                        exception_type="ModuleNotFoundError",
                        normalized_message="import error",
                    ),
                },
            )
        )
    events.append(_event(len(events) + 1, "SESSION_END"))
    return _evidence(
        run_kind="COLLECT_ONLY",
        collected=collected,
        planned=collected,
        events=events,
        exit_code=1 if session_error else 0,
    )


def _full_evidence(session_error: bool = False) -> PytestEvidenceV1:
    events: list[dict[str, object]] = [
        _event(1, "SESSION_START"),
        _event(2, "COLLECTION_ITEM", node_id=_present_text(_ADD)),
        _event(3, "COLLECTION_ITEM", node_id=_present_text(_MULTIPLY)),
    ]
    index = 4
    if session_error:
        events.append(
            _event(
                index,
                "SESSION_ERROR",
                exception={
                    "kind": "PRESENT",
                    "value": _exception_document(
                        exception_type="ModuleNotFoundError",
                        normalized_message="import error",
                    ),
                },
            )
        )
        index += 1
    events.append(
        _event(
            index,
            "TEST_PHASE",
            node_id=_present_text(_ADD),
            phase={"kind": "PRESENT", "value": "CALL"},
            outcome={"kind": "PRESENT", "value": "FAIL"},
            exception={"kind": "PRESENT", "value": _exception_document()},
        )
    )
    events.append(
        _event(
            index + 1,
            "TEST_PHASE",
            node_id=_present_text(_MULTIPLY),
            phase={"kind": "PRESENT", "value": "CALL"},
            outcome={"kind": "PRESENT", "value": "PASS"},
        )
    )
    events.append(_event(index + 2, "SESSION_END"))
    return _evidence(
        run_kind="FULL_PYTEST",
        collected=(_ADD, _MULTIPLY),
        planned=(_ADD, _MULTIPLY),
        events=events,
        exit_code=1 if session_error else 1,
    )


def _target_evidence() -> PytestEvidenceV1:
    events: list[dict[str, object]] = [
        _event(1, "SESSION_START"),
        _event(2, "COLLECTION_ITEM", node_id=_present_text(_ADD)),
        _event(
            3,
            "TEST_PHASE",
            node_id=_present_text(_ADD),
            phase={"kind": "PRESENT", "value": "CALL"},
            outcome={"kind": "PRESENT", "value": "FAIL"},
            exception={"kind": "PRESENT", "value": _exception_document()},
        ),
        _event(4, "SESSION_END"),
    ]
    return _evidence(
        run_kind="TARGET_TESTS",
        collected=(_ADD,),
        planned=(_ADD,),
        events=events,
        exit_code=1,
    )


def _passing_tool_result() -> CheckResultV1:
    return CheckResultV1(
        status="PASS",
        check_kind="RUFF",
        structured_findings=(),
        raw_digest="c" * 64,
    )


def _bundle(
    *,
    collect1: PytestEvidenceV1 | None = None,
    collect2: PytestEvidenceV1 | None = None,
    full: PytestEvidenceV1 | None = None,
    target: PytestEvidenceV1 | None = None,
    unchanged: tuple[bool, ...] = (True, True, True, True, True, True),
    ruff: CheckResultV1 | None = None,
    mypy: CheckResultV1 | None = None,
) -> BaselineEvidenceBundleV1:
    return BaselineEvidenceBundleV1(
        schema_version=1,
        plan_digest=_PLAN_DIGEST,
        reference_profile_digest=_REFERENCE_PROFILE_DIGEST,
        collect_only_evidence=(
            collect1 if collect1 is not None else _collect_evidence(),
            collect2 if collect2 is not None else _collect_evidence(),
        ),
        full_pytest_evidence=full if full is not None else _full_evidence(),
        target_rerun_evidence=target if target is not None else _target_evidence(),
        ruff_result=ruff if ruff is not None else _passing_tool_result(),
        mypy_result=mypy if mypy is not None else _passing_tool_result(),
        workspace_unchanged=unchanged,
    )


def test_compatible_bundle_binds_the_evidence_digest() -> None:
    bundle = _bundle()
    verdict = evaluate_runtime_compatibility(bundle)
    assert isinstance(verdict, RuntimeCompatibleV1)
    assert verdict.status == "COMPATIBLE"
    assert verdict.reference_profile_digest == _REFERENCE_PROFILE_DIGEST
    assert len(verdict.evidence_digest) == 64
    # Determinism: the same closed bundle yields the same evidence digest.
    again = evaluate_runtime_compatibility(_bundle())
    assert isinstance(again, RuntimeCompatibleV1)
    assert again.evidence_digest == verdict.evidence_digest
    # A changed plan identity rotates the evidence digest.
    changed = evaluate_runtime_compatibility(
        BaselineEvidenceBundleV1(
            schema_version=1,
            plan_digest="d" * 64,
            reference_profile_digest=_REFERENCE_PROFILE_DIGEST,
            collect_only_evidence=(_collect_evidence(), _collect_evidence()),
            full_pytest_evidence=_full_evidence(),
            target_rerun_evidence=_target_evidence(),
            ruff_result=_passing_tool_result(),
            mypy_result=_passing_tool_result(),
            workspace_unchanged=(True, True, True, True, True, True),
        )
    )
    assert isinstance(changed, RuntimeCompatibleV1)
    assert changed.evidence_digest != verdict.evidence_digest


def test_collection_drift_is_collection_unstable() -> None:
    bundle = _bundle(
        collect2=_collect_evidence(collected=(_ADD,)),
    )
    verdict = evaluate_runtime_compatibility(bundle)
    assert isinstance(verdict, RuntimeBaselineBlockedV1)
    assert verdict.status == "BASELINE_BLOCKED"
    assert verdict.violation_kind == "COLLECTION_UNSTABLE"
    assert verdict.evidence_refs == (
        _collect_evidence().integrity_digest,
        _collect_evidence(collected=(_ADD,)).integrity_digest,
    )


def test_empty_collection_is_collection_unstable() -> None:
    empty = _collect_evidence(collected=())
    verdict = evaluate_runtime_compatibility(_bundle(collect1=empty))
    assert isinstance(verdict, RuntimeBaselineBlockedV1)
    assert verdict.violation_kind == "COLLECTION_UNSTABLE"


def test_collection_drift_precedes_other_violations() -> None:
    """The collection facts are evaluated first (SPEC §1.4.1 order)."""
    bundle = _bundle(
        collect2=_collect_evidence(collected=(_ADD,)),
        unchanged=(False, True, True, True, True, True),
    )
    verdict = evaluate_runtime_compatibility(bundle)
    assert isinstance(verdict, RuntimeBaselineBlockedV1)
    assert verdict.violation_kind == "COLLECTION_UNSTABLE"


def test_project_tree_write_is_project_tree_write() -> None:
    bundle = _bundle(unchanged=(True, True, False, True, True, True))
    verdict = evaluate_runtime_compatibility(bundle)
    assert isinstance(verdict, RuntimeBaselineBlockedV1)
    assert verdict.violation_kind == "PROJECT_TREE_WRITE"


def test_session_error_is_check_environment_error() -> None:
    bundle = _bundle(full=_full_evidence(session_error=True))
    verdict = evaluate_runtime_compatibility(bundle)
    assert isinstance(verdict, RuntimeBaselineBlockedV1)
    assert verdict.violation_kind == "CHECK_ENVIRONMENT_ERROR"


def test_closed_violation_kind_vocabulary_is_constructible() -> None:
    """The remaining §1.4.1 kinds are closed model values (documented as
    not emitted by the evaluator — see the module docstring)."""
    kinds = (
        "EXTERNAL_SERVICE_REQUIRED",
        "VCS_RUNTIME_DEPENDENCY",
        "REPORT_INCOMPLETE",
    )
    for kind in kinds:
        blocked = RuntimeBaselineBlockedV1(
            schema_version=1,
            status="BASELINE_BLOCKED",
            reason="RUNTIME_PROFILE_VIOLATION",
            violation_kind=kind,  # type: ignore[arg-type]
            evidence_refs=("a" * 64,),
        )
        assert blocked.violation_kind == kind


def test_bundle_schema_is_closed() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        # Six workspace flags are required.
        BaselineEvidenceBundleV1(
            schema_version=1,
            plan_digest=_PLAN_DIGEST,
            reference_profile_digest=_REFERENCE_PROFILE_DIGEST,
            collect_only_evidence=(_collect_evidence(), _collect_evidence()),
            full_pytest_evidence=_full_evidence(),
            target_rerun_evidence=_target_evidence(),
            ruff_result=_passing_tool_result(),
            mypy_result=_passing_tool_result(),
            workspace_unchanged=(True, True, True, True, True),
        )
    with pytest.raises(ValidationError):
        # Unknown fields reject.
        BaselineEvidenceBundleV1.model_validate(
            {
                **_bundle().model_dump(),
                "extra": "forbidden",
            }
        )
    with pytest.raises(ValidationError):
        # Coerced schema versions reject.
        BaselineEvidenceBundleV1.model_validate(
            {
                **_bundle().model_dump(),
                "schema_version": "1",
            }
        )
    with pytest.raises(ValidationError):
        # Malformed identity digests reject.
        BaselineEvidenceBundleV1.model_validate(
            {
                **_bundle().model_dump(),
                "plan_digest": "short",
            }
        )
