"""T19.1 legacy step 19.C: stable target failure fingerprints.

``build_failure_fingerprint`` produces one stable ``FailureFingerprintV1``
only for a complete exact target ``CALL``/``FAIL`` from authoritative
``PytestEvidenceV1`` (SPEC §4.5).  Normalization replaces only the
declared execution root, temporary root, run/container id, and the
reporter-marked runtime object addresses with fixed placeholders while
user numbers, times, hexadecimal text, and assertion content are
preserved — no broad regex ever deletes user content, and missing
assertion evidence or inapplicable diffs fail closed deterministically.

Owns deterministic target-failure normalization and fingerprint output
only.  Raw report parsing, check execution, Baseline comparison, and
non-target classification remain out of scope (GREEN-4).
"""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.canonical.digest import domain_digest
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.validation.pytest_evidence import (
    PytestEvidenceV1,
    StructuredExceptionV1,
)

# The fixed placeholders for the allowlisted volatility (SPEC §4.5 rule 2).
EXECUTION_ROOT_PLACEHOLDER = "<EXECUTION_ROOT>"
TMP_ROOT_PLACEHOLDER = "<TMP_ROOT>"
RUN_ID_PLACEHOLDER = "<RUN_ID>"
CONTAINER_ID_PLACEHOLDER = "<CONTAINER_ID>"

FingerprintErrorCodeV1 = Literal["TARGET_NOT_FOUND", "TARGET_NOT_REPRODUCED"]
FingerprintOutcomeKindV1 = Literal["STABLE", "NOT_FINGERPRINTABLE"]


class ProjectFrameSignatureV1(BaseModel):
    """One project stack-frame signature of the fingerprint (SPEC §4.5)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    relative_path: CanonicalRelativePathV1
    function_name: StrictStr
    line_number: Annotated[int, Strict()]

    @field_validator("function_name")
    @classmethod
    def _function_name_is_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("function names must not be empty")
        return value

    @field_validator("line_number", mode="before")
    @classmethod
    def _line_number_is_positive(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError("line numbers must be positive decimal integers")
        return value


OptionalAssertionDiffV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[StrictStr], Field(discriminator="kind")
]
"""The fingerprint's closed assertion-diff field (SPEC §4.5 rule 5)."""


class FailureFingerprintV1(BaseModel):
    """One stable target failure fingerprint (SPEC §4.5).

    ``failure_phase`` is exactly ``CALL``; the digest is the §0.1 identity
    of every field except itself over the canonical report form, so equal
    normalized failures always yield equal digests.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    node_id: StrictStr
    failure_phase: Literal["CALL"]
    exception_type: StrictStr
    normalized_message: StrictStr
    normalized_assertion_diff: OptionalAssertionDiffV1
    project_frame_signatures: tuple[ProjectFrameSignatureV1, ...]
    digest: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("node_id", "exception_type", "normalized_message")
    @classmethod
    def _fingerprint_fields_are_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("fingerprint text fields must not be empty")
        return value

    @field_validator("digest")
    @classmethod
    def _digest_is_64_lowercase_hex(cls, value: str) -> str:
        if len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError(
                "digest must be exactly 64 lowercase hexadecimal characters"
            )
        return value

    @model_validator(mode="after")
    def _require_binding_digest(self) -> FailureFingerprintV1:
        diff = self.normalized_assertion_diff
        if isinstance(diff, PresentV1):
            diff_document: dict[str, object] = {
                "kind": "PRESENT",
                "value": diff.value,
            }
        else:
            diff_document = {"kind": "ABSENT"}
        body = _fingerprint_digest_body(
            schema_version=self.schema_version,
            node_id=self.node_id,
            failure_phase=self.failure_phase,
            exception_type=self.exception_type,
            normalized_message=self.normalized_message,
            normalized_assertion_diff=diff_document,
            project_frame_signatures=[
                {
                    "relative_path": frame.relative_path.value,
                    "function_name": frame.function_name,
                    "line_number": frame.line_number,
                }
                for frame in self.project_frame_signatures
            ],
        )
        if self.digest != domain_digest("FailureFingerprintV1", 1, body):  # type: ignore[arg-type]
            raise ValueError("digest does not bind the fingerprint fields")
        return self


def _fingerprint_digest_body(
    *,
    schema_version: int,
    node_id: str,
    failure_phase: str,
    exception_type: str,
    normalized_message: str,
    normalized_assertion_diff: dict[str, object],
    project_frame_signatures: list[dict[str, object]],
) -> dict[str, object]:
    """Every field except the digest, in the canonical document form.

    The relative path is the plain canonical string (the document form),
    never the pydantic dataclass wrapper, so the recomputed digest binds
    the exact canonical fingerprint bytes.
    """
    return {
        "schema_version": schema_version,
        "node_id": node_id,
        "failure_phase": failure_phase,
        "exception_type": exception_type,
        "normalized_message": normalized_message,
        "normalized_assertion_diff": normalized_assertion_diff,
        "project_frame_signatures": tuple(project_frame_signatures),
    }


class FingerprintNormalizationContextV1(BaseModel):
    """The declared allowlist for one fingerprint normalization (SPEC §4.5).

    Carries exactly the execution root, temporary root, run id, and
    container id the harness knows are volatile for this run; nothing else
    may ever be normalized away.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    execution_root: StrictStr
    tmp_root: StrictStr
    run_id: StrictStr
    container_id: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("execution_root", "tmp_root", "run_id", "container_id")
    @classmethod
    def _context_fields_are_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("normalization context fields must not be empty")
        return value


class FingerprintOutcomeV1(BaseModel):
    """The closed fingerprint outcome: STABLE or NOT_FINGERPRINTABLE.

    A STABLE outcome carries the fingerprint and the normalized exception
    text; a NOT_FINGERPRINTABLE outcome carries exactly one stable error
    code and no fingerprint.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    kind: FingerprintOutcomeKindV1
    normalized_exception_text: StrictStr
    fingerprint: FailureFingerprintV1 | None
    error_code: FingerprintErrorCodeV1 | None

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @model_validator(mode="after")
    def _require_closed_outcome(self) -> FingerprintOutcomeV1:
        if self.kind == "STABLE":
            if self.fingerprint is None or self.error_code is not None:
                raise ValueError("STABLE outcomes carry a fingerprint and no error")
        else:
            if self.fingerprint is not None or self.error_code is None:
                raise ValueError(
                    "NOT_FINGERPRINTABLE outcomes carry an error and no fingerprint"
                )
        return self


def _normalize_volatile_text(
    text: str, normalization: FingerprintNormalizationContextV1
) -> str:
    """LF-unify and replace only the four allowlisted volatilities.

    Each declared volatile value is replaced in both its exact spelling
    and its slash-converted variant (the same value can appear in
    Windows or POSIX form); empty values are rejected by the context
    model, so no replacement can ever corrupt user text.  Replacements
    run in descending value-length order so a value that is a substring
    of another (e.g., a tmp root nested under the execution root) can
    never make the result order-dependent.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    pairs: list[tuple[str, str]] = []
    for value, placeholder in (
        (normalization.execution_root, EXECUTION_ROOT_PLACEHOLDER),
        (normalization.tmp_root, TMP_ROOT_PLACEHOLDER),
        (normalization.run_id, RUN_ID_PLACEHOLDER),
        (normalization.container_id, CONTAINER_ID_PLACEHOLDER),
    ):
        pairs.append((value, placeholder))
        slash_variant = value.replace("\\", "/")
        if slash_variant != value:
            pairs.append((slash_variant, placeholder))
    for value, placeholder in sorted(
        pairs, key=lambda pair: len(pair[0]), reverse=True
    ):
        normalized = normalized.replace(value, placeholder)
    return normalized


def _frame_signatures(
    exception: StructuredExceptionV1,
) -> tuple[ProjectFrameSignatureV1, ...]:
    """One signature per project frame, in the report's call order."""
    return tuple(
        ProjectFrameSignatureV1(
            relative_path=frame.relative_path,
            function_name=frame.function_name,
            line_number=frame.line_number,
        )
        for frame in exception.project_frames
    )


def _not_fingerprintable(
    error_code: FingerprintErrorCodeV1,
) -> FingerprintOutcomeV1:
    return FingerprintOutcomeV1(
        schema_version=1,
        kind="NOT_FINGERPRINTABLE",
        normalized_exception_text="",
        fingerprint=None,
        error_code=error_code,
    )


def build_failure_fingerprint(
    evidence: PytestEvidenceV1,
    node_id: str,
    normalization: FingerprintNormalizationContextV1,
) -> FingerprintOutcomeV1:
    """Build one stable fingerprint for the exact target CALL/FAIL.

    Gates on the complete authoritative evidence, the exact target node,
    the CALL phase with FAIL status, and a complete structured exception
    with the applicable assertion evidence; any missing or inapplicable
    evidence fails closed deterministically.
    """
    target_events = [
        event
        for event in evidence.events
        if event.event_type == "TEST_PHASE"
        and isinstance(event.node_id, PresentV1)
        and event.node_id.value == node_id
    ]
    if not target_events:
        return _not_fingerprintable("TARGET_NOT_FOUND")
    call_events = [
        event
        for event in target_events
        if isinstance(event.phase, PresentV1) and event.phase.value == "CALL"
    ]
    if not call_events:
        return _not_fingerprintable("TARGET_NOT_REPRODUCED")
    call_event = call_events[0]
    if not isinstance(call_event.outcome, PresentV1):
        return _not_fingerprintable("TARGET_NOT_REPRODUCED")
    if call_event.outcome.value != "FAIL":
        return _not_fingerprintable("TARGET_NOT_REPRODUCED")
    if not isinstance(call_event.exception, PresentV1):
        return _not_fingerprintable("TARGET_NOT_REPRODUCED")
    exception = call_event.exception.value
    if not exception.project_frames:
        return _not_fingerprintable("TARGET_NOT_REPRODUCED")
    diff = exception.normalized_assertion_diff
    is_assertion = exception.exception_type == "AssertionError"
    if is_assertion:
        if not isinstance(diff, PresentV1):
            return _not_fingerprintable("TARGET_NOT_REPRODUCED")
        diff_text = diff.value
    else:
        if not isinstance(diff, AbsentV1):
            return _not_fingerprintable("TARGET_NOT_REPRODUCED")
        diff_text = None
    normalized_message = _normalize_volatile_text(
        exception.normalized_message, normalization
    )
    normalized_diff: OptionalAssertionDiffV1
    if diff_text is None:
        normalized_diff = AbsentV1(kind="ABSENT")
        diff_document: dict[str, object] = {"kind": "ABSENT"}
    else:
        normalized_diff = PresentV1(
            kind="PRESENT",
            value=_normalize_volatile_text(diff_text, normalization),
        )
        diff_document = {"kind": "PRESENT", "value": normalized_diff.value}
    body = _fingerprint_digest_body(
        schema_version=1,
        node_id=node_id,
        failure_phase="CALL",
        exception_type=exception.exception_type,
        normalized_message=normalized_message,
        normalized_assertion_diff=diff_document,
        project_frame_signatures=[
            {
                "relative_path": frame.relative_path.value,
                "function_name": frame.function_name,
                "line_number": frame.line_number,
            }
            for frame in exception.project_frames
        ],
    )
    fingerprint = FailureFingerprintV1(
        schema_version=1,
        node_id=node_id,
        failure_phase="CALL",
        exception_type=exception.exception_type,
        normalized_message=normalized_message,
        normalized_assertion_diff=normalized_diff,
        project_frame_signatures=_frame_signatures(exception),
        digest=domain_digest("FailureFingerprintV1", 1, body),  # type: ignore[arg-type]
    )
    if isinstance(normalized_diff, PresentV1):
        exception_text = normalized_message + "\n" + normalized_diff.value
    else:
        exception_text = normalized_message
    return FingerprintOutcomeV1(
        schema_version=1,
        kind="STABLE",
        normalized_exception_text=exception_text,
        fingerprint=fingerprint,
        error_code=None,
    )
