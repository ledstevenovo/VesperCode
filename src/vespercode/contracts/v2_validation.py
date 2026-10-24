"""Route B / B1: v2 validation run/result contracts and evidence binding.

The v1 validation plane (``validation/manifest.py``,
``validation/formal.py``) closes every record over SHA-256 identities:
the manifest self-binds a digest, and evidence is accepted only when the
digest chain recomputes exactly.  Those modules remain untouched
read-only legacy; nothing here imports them.

The v2 validation plane keys records by control-plane facts instead: a
validation run and its result carry the harness ``run_id``, the
``candidate_id``/``candidate_revision`` that was validated, and the
``reference_profile_id``/``reference_profile_revision`` that executed
the checks, plus a bounded ``status`` and a bounded ``error`` message.
Acceptance of evidence is a pure fail-closed check,
``verify_evidence_binding``: the result must belong to its validation
run, the result and run must agree on all five keys, and the run must
match the currently expected binding.  Evidence from another candidate,
run, or profile — or from a stale revision — is rejected; no digest is
consulted or recomputed.

The module is standard-library only and importable without any
filesystem, network, LLM, or v1 dependency.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any

VALIDATION_RUN_STATUSES_V2 = frozenset({"PENDING", "PASSED", "FAILED"})
"""The closed lifecycle of one validation run: created ``PENDING``, then
terminally ``PASSED`` or ``FAILED``."""

VALIDATION_RESULT_STATUSES_V2 = frozenset({"PASSED", "FAILED"})
"""A result record is terminal only; ``PENDING`` is not an outcome."""

MAX_VALIDATION_ERROR_CHARS = 512
"""The bounded length of one validation error message."""

_MAX_IDENTIFIER_BYTES = 256


def _identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    if len(value.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
        raise ValueError(f"{field_name} is too long")
    return value


def _revision(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _status(value: str, allowed: frozenset[str], field_name: str) -> str:
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {sorted(allowed)}")
    return value


def _error(status: str, value: str | None) -> str | None:
    """An error is required exactly for FAILED outcomes and is bounded."""

    if status == "FAILED":
        if not isinstance(value, str) or not value:
            raise ValueError("FAILED records require a non-empty error message")
        if len(value) > MAX_VALIDATION_ERROR_CHARS:
            raise ValueError(
                "error message exceeds the bounded length of "
                f"{MAX_VALIDATION_ERROR_CHARS} characters"
            )
        return value
    if value is not None:
        raise ValueError("only FAILED records carry an error message")
    return None


def _strict_mapping(data: object, names: tuple[str, ...]) -> dict[str, Any]:
    """Require exactly the given fields: unknown or missing keys reject.

    A v1-shaped digest payload (``digest``, ``manifest_id``,
    ``formal_result_digest``, ...) is rejected here as unknown fields,
    never accepted as v2 authority.
    """

    if not isinstance(data, Mapping):
        raise ValueError("record must be a mapping of exact fields")
    keys = set(data.keys())
    unknown = sorted(str(key) for key in keys - set(names))
    if unknown:
        raise ValueError(f"unknown fields: {unknown}")
    missing = sorted(name for name in names if name not in keys)
    if missing:
        raise ValueError(f"missing fields: {missing}")
    return {name: data[name] for name in names}


@dataclass(frozen=True, slots=True)
class ValidationBindingV2:
    """The exact five control keys a validation record must carry.

    ``run_id`` is the harness run; ``candidate_id``/``candidate_revision``
    are the validated candidate state; ``reference_profile_id``/
    ``reference_profile_revision`` are the executing configuration.  Two
    bindings are equal only when every key is equal, so replacing any
    key — including a revision advance — is a different binding.
    """

    run_id: str
    candidate_id: str
    candidate_revision: int
    reference_profile_id: str
    reference_profile_revision: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _identifier(self.run_id, "run_id"))
        object.__setattr__(
            self, "candidate_id", _identifier(self.candidate_id, "candidate_id")
        )
        object.__setattr__(
            self,
            "candidate_revision",
            _revision(self.candidate_revision, "candidate_revision"),
        )
        object.__setattr__(
            self,
            "reference_profile_id",
            _identifier(self.reference_profile_id, "reference_profile_id"),
        )
        object.__setattr__(
            self,
            "reference_profile_revision",
            _revision(self.reference_profile_revision, "reference_profile_revision"),
        )


@dataclass(frozen=True, slots=True)
class ValidationRunRecordV2:
    """One validation run keyed by its five control-plane facts.

    A run is created ``PENDING`` against a current candidate revision
    and reference profile revision, and becomes terminally ``PASSED``
    or ``FAILED``.  The bounded ``error`` is required exactly for
    ``FAILED``.  No digest of the validated content exists here: the
    record is a control-plane fact, not a content proof.
    """

    validation_run_id: str
    run_id: str
    candidate_id: str
    candidate_revision: int
    reference_profile_id: str
    reference_profile_revision: int
    status: str
    error: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "validation_run_id",
            _identifier(self.validation_run_id, "validation_run_id"),
        )
        object.__setattr__(self, "run_id", _identifier(self.run_id, "run_id"))
        object.__setattr__(
            self, "candidate_id", _identifier(self.candidate_id, "candidate_id")
        )
        object.__setattr__(
            self,
            "candidate_revision",
            _revision(self.candidate_revision, "candidate_revision"),
        )
        object.__setattr__(
            self,
            "reference_profile_id",
            _identifier(self.reference_profile_id, "reference_profile_id"),
        )
        object.__setattr__(
            self,
            "reference_profile_revision",
            _revision(self.reference_profile_revision, "reference_profile_revision"),
        )
        object.__setattr__(
            self,
            "status",
            _status(self.status, VALIDATION_RUN_STATUSES_V2, "status"),
        )
        object.__setattr__(self, "error", _error(self.status, self.error))

    def binding(self) -> ValidationBindingV2:
        """The five keys this run is bound to."""

        return ValidationBindingV2(
            run_id=self.run_id,
            candidate_id=self.candidate_id,
            candidate_revision=self.candidate_revision,
            reference_profile_id=self.reference_profile_id,
            reference_profile_revision=self.reference_profile_revision,
        )


@dataclass(frozen=True, slots=True)
class ValidationResultV2:
    """The terminal outcome of one validation run.

    The result repeats the run's five keys, so a tampered or re-bound
    result can be detected against its own run record, and carries the
    bounded terminal ``status`` and ``error``.  It is the record used as
    evidence; acceptance is ``verify_evidence_binding``.
    """

    validation_run_id: str
    run_id: str
    candidate_id: str
    candidate_revision: int
    reference_profile_id: str
    reference_profile_revision: int
    status: str
    error: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "validation_run_id",
            _identifier(self.validation_run_id, "validation_run_id"),
        )
        object.__setattr__(self, "run_id", _identifier(self.run_id, "run_id"))
        object.__setattr__(
            self, "candidate_id", _identifier(self.candidate_id, "candidate_id")
        )
        object.__setattr__(
            self,
            "candidate_revision",
            _revision(self.candidate_revision, "candidate_revision"),
        )
        object.__setattr__(
            self,
            "reference_profile_id",
            _identifier(self.reference_profile_id, "reference_profile_id"),
        )
        object.__setattr__(
            self,
            "reference_profile_revision",
            _revision(self.reference_profile_revision, "reference_profile_revision"),
        )
        object.__setattr__(
            self,
            "status",
            _status(self.status, VALIDATION_RESULT_STATUSES_V2, "status"),
        )
        object.__setattr__(self, "error", _error(self.status, self.error))

    def binding(self) -> ValidationBindingV2:
        """The five keys this result claims."""

        return ValidationBindingV2(
            run_id=self.run_id,
            candidate_id=self.candidate_id,
            candidate_revision=self.candidate_revision,
            reference_profile_id=self.reference_profile_id,
            reference_profile_revision=self.reference_profile_revision,
        )


def verify_evidence_binding(
    result: ValidationResultV2,
    *,
    run: ValidationRunRecordV2,
    expected: ValidationBindingV2,
) -> None:
    """Accept one result as evidence only when every binding agrees.

    Fail-closed order:

    1. the result must belong to the named validation run
       (``validation_run_id``);
    2. the result's five keys must equal its run's keys — a result
       re-bound to another candidate, run, or profile is rejected;
    3. the run's keys must equal the currently expected binding —
       evidence from another candidate, run, or reference profile, or
       recorded against a stale revision (the candidate advanced after
       the run was recorded) is rejected.

    No digest is consulted; the check is pure key comparison, so it
    stays deterministic and offline.
    """

    if not isinstance(result, ValidationResultV2):
        raise ValueError("result must be a ValidationResultV2")
    if not isinstance(run, ValidationRunRecordV2):
        raise ValueError("run must be a ValidationRunRecordV2")
    if not isinstance(expected, ValidationBindingV2):
        raise ValueError("expected must be a ValidationBindingV2")
    if result.validation_run_id != run.validation_run_id:
        raise ValueError(
            "validation evidence does not belong to the named validation run"
        )
    if result.binding() != run.binding():
        raise ValueError(
            "validation evidence binding disagrees with its validation run"
        )
    if run.binding() != expected:
        raise ValueError(
            "validation evidence binding does not match the current run, "
            "candidate, or reference profile"
        )


def validation_run_from_mapping(data: Mapping[str, Any]) -> ValidationRunRecordV2:
    """Parse a validation run from an exact-field mapping, fail closed."""

    names = tuple(field.name for field in fields(ValidationRunRecordV2))
    values = _strict_mapping(data, names)
    return ValidationRunRecordV2(
        validation_run_id=values["validation_run_id"],
        run_id=values["run_id"],
        candidate_id=values["candidate_id"],
        candidate_revision=values["candidate_revision"],
        reference_profile_id=values["reference_profile_id"],
        reference_profile_revision=values["reference_profile_revision"],
        status=values["status"],
        error=values["error"],
    )


def validation_result_from_mapping(data: Mapping[str, Any]) -> ValidationResultV2:
    """Parse a validation result from an exact-field mapping, fail closed."""

    names = tuple(field.name for field in fields(ValidationResultV2))
    values = _strict_mapping(data, names)
    return ValidationResultV2(
        validation_run_id=values["validation_run_id"],
        run_id=values["run_id"],
        candidate_id=values["candidate_id"],
        candidate_revision=values["candidate_revision"],
        reference_profile_id=values["reference_profile_id"],
        reference_profile_revision=values["reference_profile_revision"],
        status=values["status"],
        error=values["error"],
    )


__all__ = (
    "MAX_VALIDATION_ERROR_CHARS",
    "VALIDATION_RESULT_STATUSES_V2",
    "VALIDATION_RUN_STATUSES_V2",
    "ValidationBindingV2",
    "ValidationResultV2",
    "ValidationRunRecordV2",
    "validation_result_from_mapping",
    "validation_run_from_mapping",
    "verify_evidence_binding",
)
