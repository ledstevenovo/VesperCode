"""T05.1 legacy step 5.C: closed action/result/policy-decision contract tests.

The matrix pins every legal action/result envelope round-trip and every
unknown, mixed, or contradictory envelope rejection; model JSON parsing,
policy evaluation, dispatch, and check execution remain out of scope
(GREEN-4).
"""

from __future__ import annotations

import pytest

# The action models are pydantic runtime contracts; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import TypeAdapter, ValidationError

from vespercode.canonical.digest import domain_digest
from vespercode.contracts.action import (
    ActionErrorV1,
    ActionInstanceV1,
    ActionResultV1,
    ActionStatusV1,
    CheckPlanIdV1,
    PolicyDecisionV1,
    SharedActionV1,
    _require_action_id,
)

_DIGEST = "a" * 64
_INSTANCE_DIGEST = "14b169de03043df4b712ea949fe87bc0f73fcad61ea30ae18fda2ea671c5d1fe"


def success_with_error_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "action_id": "action-1",
        "semantic_digest": _DIGEST,
        "instance_digest": _INSTANCE_DIGEST,
        "status": "SUCCEEDED",
        "result_type": "list_files",
        "payload_ref": {
            "kind": "PRESENT",
            "value": {"artifact_id": "art-1", "digest": {"value": "c" * 64}},
        },
        "error": {
            "kind": "PRESENT",
            "value": {
                "error_code": "INTERNAL_ERROR",
                "bounded_message": "boom",
                "evidence_ref": {"kind": "ABSENT"},
            },
        },
    }


def test_success_result_rejects_error_payload() -> None:
    with pytest.raises(ValidationError):
        ActionResultV1.model_validate(success_with_error_payload())


def test_action_result_union_matrix() -> None:
    """SPEC §4.2.2/§4.4.1 action/result union matrix (Expected 5.C).

    Legal actions and results validate; unknown, mixed, or contradictory
    envelopes reject deterministically.
    """
    # Closed literal vocabularies.
    decisions: TypeAdapter[PolicyDecisionV1] = TypeAdapter(PolicyDecisionV1)
    for value in ("ALLOW", "ASK", "DENY"):
        assert decisions.validate_python(value) == value
    for value in ("allow", "ALLOW ", "SKIP", ""):
        with pytest.raises(ValidationError):
            decisions.validate_python(value)
    plans: TypeAdapter[CheckPlanIdV1] = TypeAdapter(CheckPlanIdV1)
    for value in ("TARGET_TESTS", "FULL_PYTEST", "RUFF", "MYPY"):
        assert plans.validate_python(value) == value
    for value in ("PYTEST", "target_tests", ""):
        with pytest.raises(ValidationError):
            plans.validate_python(value)
    statuses: TypeAdapter[ActionStatusV1] = TypeAdapter(ActionStatusV1)
    for value in ("SUCCEEDED", "REJECTED", "FAILED"):
        assert statuses.validate_python(value) == value
    for value in ("SUCCESS", "OK"):
        with pytest.raises(ValidationError):
            statuses.validate_python(value)

    # SharedActionV1: the shared closed action identity envelope.
    shared = {"schema_version": 1, "action_type": "list_files"}
    assert SharedActionV1.model_validate(shared).action_type == "list_files"
    for shared_payload in (
        {"schema_version": 1, "action_type": ""},
        {"schema_version": 2, "action_type": "list_files"},
        {"schema_version": 1},
        {"schema_version": 1, "action_type": None},
        {"schema_version": 1, "action_type": "list_files", "extra": 1},
    ):
        with pytest.raises(ValidationError):
            SharedActionV1.model_validate(shared_payload)

    # ActionErrorV1: stable code, bounded message, optional evidence ref.
    error = {
        "error_code": "FILE_NOT_TEXT",
        "bounded_message": "not a text file",
        "evidence_ref": {"kind": "ABSENT"},
    }
    assert ActionErrorV1.model_validate(error).error_code == "FILE_NOT_TEXT"
    present_evidence = {
        "error_code": "FILE_NOT_TEXT",
        "bounded_message": "not a text file",
        "evidence_ref": {
            "kind": "PRESENT",
            "value": {"artifact_id": "a1", "digest": {"value": _DIGEST}},
        },
    }
    assert ActionErrorV1.model_validate(present_evidence).evidence_ref.kind == "PRESENT"
    for error_payload in (
        {"bounded_message": "m", "evidence_ref": {"kind": "ABSENT"}},  # missing code
        {"error_code": "", "bounded_message": "m", "evidence_ref": {"kind": "ABSENT"}},
        {"error_code": "E", "evidence_ref": {"kind": "ABSENT"}},  # missing message
        {"error_code": "E", "bounded_message": "", "evidence_ref": {"kind": "ABSENT"}},
        {
            "error_code": None,
            "bounded_message": "m",
            "evidence_ref": {"kind": "ABSENT"},
        },
        {
            "error_code": "E",
            "bounded_message": "m",
            "evidence_ref": {"kind": "PRESENT"},
        },
        {
            "error_code": "E",
            "bounded_message": "m",
            "evidence_ref": {
                "kind": "PRESENT",
                "value": {"artifact_id": "a1", "digest": {"value": ""}},
            },
        },
        {
            "error_code": "E",
            "bounded_message": "m",
            "evidence_ref": {"kind": "ABSENT"},
            "extra": 1,
        },
    ):
        with pytest.raises(ValidationError):
            ActionErrorV1.model_validate(error_payload)

    # ActionResultV1: success cannot carry error data; failure must.
    success: dict[str, object] = {
        "schema_version": 1,
        "action_id": "action-1",
        "semantic_digest": _DIGEST,
        "instance_digest": _INSTANCE_DIGEST,
        "status": "SUCCEEDED",
        "result_type": "list_files",
        "payload_ref": {"kind": "ABSENT"},
        "error": {"kind": "ABSENT"},
    }
    assert ActionResultV1.model_validate(success).status == "SUCCEEDED"
    failed = {
        **success,
        "status": "FAILED",
        "error": {
            "kind": "PRESENT",
            "value": {
                "error_code": "FILE_NOT_TEXT",
                "bounded_message": "x",
                "evidence_ref": {"kind": "ABSENT"},
            },
        },
    }
    assert ActionResultV1.model_validate(failed).status == "FAILED"
    rejected = {**failed, "status": "REJECTED"}
    assert ActionResultV1.model_validate(rejected).status == "REJECTED"
    for result_payload in (
        success_with_error_payload(),  # SUCCEEDED carrying error data (RED)
        {**success, "status": "FAILED", "error": {"kind": "ABSENT"}},
        {**success, "status": "REJECTED", "error": {"kind": "ABSENT"}},
        {**success, "status": "SUCCESS"},
        {**success, "schema_version": 2},
        {k: v for k, v in success.items() if k != "action_id"},
        {**success, "semantic_digest": "x"},
        {**success, "instance_digest": "x"},  # not 64 lowercase hex
        {**success, "instance_digest": "b" * 64},  # not the instance identity digest
        {**success, "action_id": ""},
        {**success, "status": None},
        {**success, "extra": 1},
    ):
        with pytest.raises(ValidationError):
            ActionResultV1.model_validate(result_payload)

    # ActionInstanceV1: instance identity binds action_id and semantic digest.
    instance: dict[str, object] = {
        "action_id": "action-1",
        "semantic_digest": _DIGEST,
        "instance_digest": _INSTANCE_DIGEST,
        "action": {"schema_version": 1, "action_type": "list_files"},
    }
    assert ActionInstanceV1.model_validate(instance).action.action_type == "list_files"
    for instance_payload in (
        {
            **instance,
            "instance_digest": "bcaa7b7fcb3f221a69638178c05cdf9526ceb36c4c01a3a81ccb6018e53ce464",
        },  # digest of a different action identity
        {**instance, "instance_digest": _DIGEST},  # not the digest of these inputs
        {**instance, "instance_digest": "x"},  # not 64 lowercase hex
        {**instance, "semantic_digest": "x"},
        {**instance, "action_id": ""},
        {**instance, "action": {"schema_version": 1, "action_type": ""}},
        {**instance, "action": {"schema_version": 2, "action_type": "list_files"}},
        {k: v for k, v in instance.items() if k != "action"},
        {**instance, "extra": 1},
    ):
        with pytest.raises(ValidationError):
            ActionInstanceV1.model_validate(instance_payload)


def test_action_id_byte_boundary() -> None:
    """SPEC §4.2.2: action_id is a non-empty UTF-8 string of <=128 bytes."""
    assert _require_action_id("a" * 128) == "a" * 128
    for value in ("", "a" * 129, "界" * 43):  # empty; 129 UTF-8 bytes each
        with pytest.raises(ValueError):
            _require_action_id(value)


def test_action_instance_digest_binding() -> None:
    """The instance digest is the exact §0.1 ActionInstanceDigestV1 binding."""
    expected = domain_digest(
        "ActionInstanceDigestV1",
        1,
        {
            "schema_version": 1,
            "action_id": "action-1",
            "semantic_digest": _DIGEST,
        },
    )
    assert expected == _INSTANCE_DIGEST
    instance = ActionInstanceV1.model_validate(
        {
            "action_id": "action-1",
            "semantic_digest": _DIGEST,
            "instance_digest": _INSTANCE_DIGEST,
            "action": {"schema_version": 1, "action_type": "list_files"},
        }
    )
    assert instance.instance_digest == expected


def test_success_result_allows_absent_payload() -> None:
    result = ActionResultV1.model_validate(
        {
            "schema_version": 1,
            "action_id": "action-1",
            "semantic_digest": _DIGEST,
            "instance_digest": _INSTANCE_DIGEST,
            "status": "SUCCEEDED",
            "result_type": "propose_completion",
            "payload_ref": {"kind": "ABSENT"},
            "error": {"kind": "ABSENT"},
        }
    )
    assert result.payload_ref.kind == "ABSENT"
