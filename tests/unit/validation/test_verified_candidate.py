"""T21.1 legacy step 21.C: ``VerifiedCandidateV1`` schema tests.

The verified-candidate surface proves the closed result vocabulary is
immutable and closed (unknown fields and type-confused spellings
reject), the SPEC §7 row (``candidate_id``/``manifest_id``/
``formal_result_digest``; only complete formal validation creates it) is
machine-enforced, and the discriminated outcome is exactly
``VerifiedCandidateV1 | FormalValidationFailureV1``.  The predicate
matrix lives in ``test_formal_predicate.py``.
"""

from __future__ import annotations

import pytest

# The VerifiedCandidate contracts are pydantic runtime models; the
# hash-locked gate toolchain does not install runtime dependencies, so
# this module skips cleanly there instead of failing at collection
# (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import TypeAdapter, ValidationError

from vespercode.validation.formal import (
    FormalValidationFailureV1,
    FormalValidationOutcomeV1,
    VerifiedCandidateV1,
)

_A = "a" * 64
_B = "b" * 64
_C = "c" * 64


def _verified() -> VerifiedCandidateV1:
    return VerifiedCandidateV1(
        schema_version=1,
        kind="VERIFIED",
        candidate_id=_A,
        manifest_id=_B,
        formal_result_digest=_C,
    )


def test_verified_candidate_is_immutable_closed_and_digest_bound() -> None:
    verified = _verified()
    assert verified.schema_version == 1
    assert verified.kind == "VERIFIED"
    assert verified.candidate_id == _A
    assert verified.manifest_id == _B
    assert verified.formal_result_digest == _C
    with pytest.raises(ValidationError):
        VerifiedCandidateV1.model_validate(
            {
                "schema_version": 1,
                "kind": "VERIFIED",
                "candidate_id": _A,
                "manifest_id": _B,
                "formal_result_digest": "not-a-digest",
            }
        )
    with pytest.raises(ValidationError):
        VerifiedCandidateV1.model_validate(
            {
                "schema_version": 1,
                "kind": "VERIFIED",
                "candidate_id": _A,
                "manifest_id": _B,
                "formal_result_digest": _C,
                "unexpected": 1,
            }
        )
    with pytest.raises(ValidationError):
        VerifiedCandidateV1.model_validate(
            {
                "schema_version": 1,
                "kind": "VERIFIED",
                "candidate_id": "not-a-digest",
                "manifest_id": _B,
                "formal_result_digest": _C,
            }
        )
    with pytest.raises(ValidationError):
        verified.__setattr__("manifest_id", _C)


def test_failure_is_closed_and_typed() -> None:
    failure = FormalValidationFailureV1(
        schema_version=1,
        kind="FAILED",
        error_code="EXECUTION_WORKSPACE_MUTATED",
        error_message="teardown evidence missing",
    )
    assert failure.kind == "FAILED"
    assert failure.error_code == "EXECUTION_WORKSPACE_MUTATED"
    with pytest.raises(ValidationError):
        FormalValidationFailureV1.model_validate(
            {
                "schema_version": 1,
                "kind": "FAILED",
                "error_code": "UNKNOWN_CODE",
                "error_message": "unknown",
            }
        )
    with pytest.raises(ValidationError):
        FormalValidationFailureV1.model_validate(
            {
                "schema_version": 1,
                "kind": "FAILED",
                "error_code": "EXECUTION_WORKSPACE_MUTATED",
                "error_message": "",
            }
        )
    with pytest.raises(ValidationError):
        FormalValidationFailureV1.model_validate(
            {
                "schema_version": 1,
                "kind": "FAILED",
                "error_code": "EXECUTION_WORKSPACE_MUTATED",
                "error_message": "x",
                "unexpected": 1,
            }
        )


def test_outcome_is_exactly_the_closed_discriminated_union() -> None:
    adapter: TypeAdapter[FormalValidationOutcomeV1] = TypeAdapter(
        FormalValidationOutcomeV1
    )
    verified = adapter.validate_python(
        {
            "schema_version": 1,
            "kind": "VERIFIED",
            "candidate_id": _A,
            "manifest_id": _B,
            "formal_result_digest": _C,
        }
    )
    assert isinstance(verified, VerifiedCandidateV1)
    failure = adapter.validate_python(
        {
            "schema_version": 1,
            "kind": "FAILED",
            "error_code": "CHECK_ERROR",
            "error_message": "ruff did not pass",
        }
    )
    assert isinstance(failure, FormalValidationFailureV1)
    assert verified.kind != failure.kind  # type: ignore[comparison-overlap]
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "schema_version": 1,
                "kind": "UNKNOWN",
                "candidate_id": _A,
                "manifest_id": _B,
                "formal_result_digest": _C,
            }
        )
