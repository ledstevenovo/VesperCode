"""T24.1 legacy step 24.A: structured bounded feedback construction/selection.

``build_feedback`` normalizes only typed check, action, and stable control
failures into bounded source-attributed records with stable occurrence
ids (the source identity plus the canonical observation time), closed
severity, canonical timestamps, bounded summaries, structured source
attribution, canonical payloads, and evidence references; PASS/NOT_RUN
checks and SUCCEEDED actions normalize to the empty sequence, and inputs
that cannot be encoded canonically (lone surrogates) fail closed.
``select_feedback`` deterministically selects unconsumed records under the
exact 10-record and 32 KiB limits (SPEC 4.5) in closed
severity/recency/id order, preserving the newest required failure — the
record with the latest canonical timestamp — as the last selected record
so it can never be dropped by either limit.  Message assembly, record
consumption, LLM calls, Run lifecycle mutation, raw bodies, and secrets
remain out of scope (GREEN-4).
"""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)

from vespercode.canonical.clock import ClockV1
from vespercode.canonical.json_v1 import (
    CanonicalJsonErrorV1,
    CanonicalValueV1,
    canonical_json_bytes,
)
from vespercode.canonical.path_v1 import (
    CanonicalPathErrorV1,
    CanonicalRelativePathV1,
)
from vespercode.audit.event import _contains_secret
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.action import ActionResultV1, CheckPlanIdV1
from vespercode.contracts.evidence import StableControlErrorV1
from vespercode.contracts.optional import (
    AbsentV1,
    OptionalCanonicalPathV1,
    PresentV1,
)
from vespercode.validation.check_result import CheckResultV1

FEEDBACK_MAX_RECORDS_V1 = 10
"""SPEC 4.5: the next turn receives at most 10 feedback records."""

FEEDBACK_MAX_BYTES_V1 = 32768
"""SPEC 4.5: the next turn receives at most 32 KiB of feedback."""

FEEDBACK_ID_MAX_BYTES_V1 = 128
"""One bounded record id (the same bound as a Harness action id)."""

FEEDBACK_SUMMARY_MAX_CHARS_V1 = 512
"""One bounded record summary (characters; deterministic truncation)."""

FEEDBACK_PAYLOAD_MAX_BYTES_V1 = 4096
"""One bounded canonical payload (UTF-8 bytes)."""

FEEDBACK_EVIDENCE_REF_MAX_CHARS_V1 = 128
"""One bounded evidence reference (characters)."""

FEEDBACK_EVIDENCE_REFS_MAX_V1 = 8
"""The bounded evidence-reference cardinality of one record."""

FEEDBACK_EVIDENCE_REFS_JSON_MAX_CHARS_V1 = 2048
"""The bounded canonical evidence-refs JSON text (the v0008 column bound)."""

FEEDBACK_ERROR_CODE_MAX_CHARS_V1 = 64
"""The bounded stable control error code (characters)."""

FEEDBACK_SOURCE_REF_MAX_CHARS_V1 = 256
"""The bounded canonical source attribution (the v0008 column bound)."""

FeedbackSeverityV1: TypeAlias = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
"""The closed severity ladder (SPEC 4.2.4 orders feedback by severity)."""

FeedbackKindV1: TypeAlias = Literal["CHECK", "ACTION", "CONTROL"]
"""The closed record kinds (SPEC 7 FeedbackRecord)."""

_SEVERITY_RANK: dict[str, int] = {
    "CRITICAL": 0,
    "HIGH": 1,
    "MEDIUM": 2,
    "LOW": 3,
}
"""The closed severity ordering (lower rank selects first)."""


def _utf8_bytes(value: str) -> bytes:
    """The exact UTF-8 bytes of one value, or fail closed on surrogates."""
    try:
        return value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("value must be a sequence of Unicode scalar values") from exc


class CheckFeedbackSourceV1(BaseModel):
    """One closed check attribution: check plan plus optional repo path.

    The path is the finding's exact reported repo path when it forms a
    valid ``CanonicalRelativePathV1`` (SPEC 4.4.4 FEEDBACK path-presence
    contract); non-canonical or missing locations stay ``ABSENT``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["CHECK"]
    check_kind: CheckPlanIdV1
    path: OptionalCanonicalPathV1


class ActionFeedbackSourceV1(BaseModel):
    """One closed action attribution: the exact instance and semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["ACTION"]
    action_id: StrictStr
    semantic_digest: StrictStr

    @field_validator("action_id")
    @classmethod
    def _action_id_is_bounded(cls, value: str) -> str:
        if value == "":
            raise ValueError("action_id must be non-empty")
        if len(_utf8_bytes(value)) > 128:
            raise ValueError("action_id must be at most 128 UTF-8 bytes")
        return value

    @field_validator("semantic_digest")
    @classmethod
    def _semantic_digest_is_64_hex(cls, value: str) -> str:
        if len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError(
                "semantic_digest must be exactly 64 lowercase hexadecimal characters"
            )
        return value


class ControlFeedbackSourceV1(BaseModel):
    """One closed control attribution: the exact stable error code."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["CONTROL"]
    error_code: StrictStr

    @field_validator("error_code")
    @classmethod
    def _error_code_is_bounded(cls, value: str) -> str:
        if value == "":
            raise ValueError("error_code must be non-empty")
        if len(value) > FEEDBACK_ERROR_CODE_MAX_CHARS_V1:
            raise ValueError("error_code must be at most 64 characters")
        _utf8_bytes(value)  # lone surrogates fail closed at the boundary
        return value


FeedbackSourceV1: TypeAlias = Annotated[
    CheckFeedbackSourceV1 | ActionFeedbackSourceV1 | ControlFeedbackSourceV1,
    Field(discriminator="kind"),
]
"""SPEC 7: the closed structured source attribution of one record."""


class FeedbackRecordV1(BaseModel):
    """One bounded structured feedback record (SPEC 7 FeedbackRecord).

    Exactly the semantic fields of the card: a stable id, the closed
    kind, the closed severity, the canonical observation timestamp, a
    bounded summary, the structured source attribution, the bounded
    canonical payload, the bounded ordered evidence references, and the
    nullable consumption binding (None = unconsumed).  The record never
    carries a raw check body, a raw tool output, or a secret.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: StrictStr
    kind: FeedbackKindV1
    severity: FeedbackSeverityV1
    created_at: CanonicalTimestampV1
    summary: StrictStr
    source_ref: FeedbackSourceV1
    bounded_payload: StrictStr
    evidence_refs: tuple[StrictStr, ...] = ()
    consumed_by_turn: StrictStr | None = None

    @field_validator("id")
    @classmethod
    def _id_is_bounded(cls, value: str) -> str:
        if value == "":
            raise ValueError("feedback ids must be non-empty")
        if len(_utf8_bytes(value)) > FEEDBACK_ID_MAX_BYTES_V1:
            raise ValueError("feedback ids must be at most 128 UTF-8 bytes")
        return value

    @field_validator("summary")
    @classmethod
    def _summary_is_bounded(cls, value: str) -> str:
        if value == "":
            raise ValueError("feedback summaries must be non-empty")
        if len(value) > FEEDBACK_SUMMARY_MAX_CHARS_V1:
            raise ValueError("feedback summaries must be at most 512 characters")
        _utf8_bytes(value)  # lone surrogates fail closed at the boundary
        return value

    @field_validator("bounded_payload")
    @classmethod
    def _payload_is_bounded(cls, value: str) -> str:
        if value == "":
            raise ValueError("feedback payloads must be non-empty")
        if len(_utf8_bytes(value)) > FEEDBACK_PAYLOAD_MAX_BYTES_V1:
            raise ValueError("feedback payloads must be at most 4096 UTF-8 bytes")
        return value

    @field_validator("evidence_refs")
    @classmethod
    def _evidence_refs_are_bounded(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) > FEEDBACK_EVIDENCE_REFS_MAX_V1:
            raise ValueError("a feedback record carries at most 8 evidence refs")
        for ref in value:
            if ref == "":
                raise ValueError("evidence refs must be non-empty")
            if len(ref) > FEEDBACK_EVIDENCE_REF_MAX_CHARS_V1:
                raise ValueError("evidence refs must be at most 128 characters")
            _utf8_bytes(ref)  # lone surrogates fail closed at the boundary
        return value

    @field_validator("consumed_by_turn")
    @classmethod
    def _consumption_binding_is_bounded(cls, value: str | None) -> str | None:
        if value is not None:
            if value == "":
                raise ValueError("consumed_by_turn must be non-empty when present")
            if len(_utf8_bytes(value)) > FEEDBACK_ID_MAX_BYTES_V1:
                raise ValueError("consumed_by_turn must be at most 128 UTF-8 bytes")
        return value

    @model_validator(mode="after")
    def _source_kind_matches_record_kind(self) -> FeedbackRecordV1:
        if self.source_ref.kind != self.kind:
            raise ValueError("source_ref kind must match the record kind")
        return self

    @model_validator(mode="after")
    def _source_ref_is_bounded(self) -> FeedbackRecordV1:
        """The canonical source attribution obeys the stored row bound.

        The v0008 ``source_ref`` column backstops the attribution at 256
        characters, so the record itself rejects any attribution whose
        canonical text exceeds that exact bound (a closed rejection
        before any append exists — Task 24.A's bounded records are
        always appendable by Task 24.C).
        """
        try:
            text = serialize_feedback_source(self.source_ref)
        except CanonicalJsonErrorV1 as exc:
            raise ValueError(
                "source attribution must be a sequence of Unicode scalar values"
            ) from exc
        if len(text) > FEEDBACK_SOURCE_REF_MAX_CHARS_V1:
            raise ValueError("source attribution must be at most 256 characters")
        return self

    @model_validator(mode="after")
    def _evidence_refs_json_is_bounded(self) -> FeedbackRecordV1:
        """The canonical evidence-refs JSON obeys the stored row bound.

        The v0008 ``evidence_refs`` column backstops the canonical JSON
        array text at 2048 characters, so the record itself rejects any
        reference set whose canonical text exceeds that exact bound (the
        closed rejection mirrors the source-attribution bound, keeping
        Task 24.A's bounded records always appendable by Task 24.C).
        """
        try:
            text = canonical_json_bytes(tuple(self.evidence_refs)).decode("utf-8")
        except CanonicalJsonErrorV1 as exc:
            raise ValueError(
                "evidence refs must be a sequence of Unicode scalar values"
            ) from exc
        if len(text) > FEEDBACK_EVIDENCE_REFS_JSON_MAX_CHARS_V1:
            raise ValueError("evidence refs must fit the 2048-character stored bound")
        return self


FeedbackRecordSequenceV1: TypeAlias = tuple[FeedbackRecordV1, ...]
"""The immutable ordered tuple of feedback records (card Interface)."""


class FeedbackSelectionV1(BaseModel):
    """One deterministic selection: ordered records plus their refs.

    ``refs`` is the immutable ordered tuple of the selected record ids —
    the exact feedback references a new turn binds (card 24.C consumes
    this shape).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    records: FeedbackRecordSequenceV1

    @property
    def refs(self) -> tuple[str, ...]:
        """The ordered stable ids of the selected records."""
        return tuple(record.id for record in self.records)


class FeedbackConstructionErrorV1(ValueError):
    """Closed rejection when one failure source cannot be normalized."""


def _path_canonical(path: OptionalCanonicalPathV1) -> CanonicalValueV1:
    """One source-path union into its canonical encoding."""
    if path.kind == "ABSENT":
        return {"kind": "ABSENT"}
    return {"kind": "PRESENT", "value": path.value.value}


def _source_ref_canonical(source_ref: FeedbackSourceV1) -> CanonicalValueV1:
    """One structured source attribution into its canonical encoding."""
    if source_ref.kind == "CHECK":
        return {
            "kind": "CHECK",
            "check_kind": source_ref.check_kind,
            "path": _path_canonical(source_ref.path),
        }
    if source_ref.kind == "ACTION":
        return {
            "kind": "ACTION",
            "action_id": source_ref.action_id,
            "semantic_digest": source_ref.semantic_digest,
        }
    return {"kind": "CONTROL", "error_code": source_ref.error_code}


def serialize_feedback_source(source_ref: FeedbackSourceV1) -> str:
    """The canonical JSON text of one structured source attribution.

    The stored ``source_ref`` column of a feedback row carries exactly
    this text, so the attribution is deterministic and replayable.
    """
    return canonical_json_bytes(_source_ref_canonical(source_ref)).decode("utf-8")


def serialize_feedback_record(record: FeedbackRecordV1) -> str:
    """The canonical JSON text of one record's semantic facts (SPEC 0.1).

    ``consumed_by_turn`` is storage state and never enters the semantic
    serialization.  The canonical text is the single authority for the
    32 KiB selection bound, the FEEDBACK request-segment content (24.B),
    and the stored feedback row (24.C).
    """
    return canonical_json_bytes(
        {
            "id": record.id,
            "kind": record.kind,
            "severity": record.severity,
            "created_at": record.created_at.value,
            "summary": record.summary,
            "source_ref": _source_ref_canonical(record.source_ref),
            "bounded_payload": record.bounded_payload,
            "evidence_refs": tuple(record.evidence_refs),
        }
    ).decode("utf-8")


def feedback_canonical_bytes(record: FeedbackRecordV1) -> int:
    """The exact UTF-8 byte length of one record's canonical serialization."""
    return len(serialize_feedback_record(record).encode("utf-8"))


_SECRET_REDACTED_SUMMARY = (
    "[feedback summary omitted: contains secret-like content]"
)
"""The fixed bounded summary replacing a secret-bearing check message."""


def _bounded_summary(text: str) -> str:
    """Truncate one summary deterministically at the bounded length."""
    if len(text) <= FEEDBACK_SUMMARY_MAX_CHARS_V1:
        return text
    bounded = text[:FEEDBACK_SUMMARY_MAX_CHARS_V1]
    # A character slice can never split a decoded scalar, but a directly
    # constructed message may end in a dangling surrogate code unit at
    # the cut; never emit a summary that fails the scalar check because
    # of the slice boundary (mid-string lone surrogates still fail
    # closed at the record validator).
    if bounded and "\ud800" <= bounded[-1] <= "\udfff":
        bounded = bounded[:-1]
    return bounded


def _canonical_payload(facts: CanonicalValueV1) -> str:
    """One bounded canonical payload text, or fail closed on surrogates."""
    try:
        return canonical_json_bytes(facts).decode("utf-8")
    except CanonicalJsonErrorV1 as exc:
        raise FeedbackConstructionErrorV1(
            "feedback facts cannot be encoded canonically"
        ) from exc


def _finding_path(path: str | None) -> OptionalCanonicalPathV1:
    """One reported finding path into the closed optional canonical path.

    Only a valid canonical repository-relative path is attributed; any
    other spelling stays ABSENT (SPEC 4.4.4 FEEDBACK path presence).
    """
    if path is None:
        return AbsentV1(kind="ABSENT")
    try:
        return PresentV1(kind="PRESENT", value=CanonicalRelativePathV1(path))
    except CanonicalPathErrorV1:
        return AbsentV1(kind="ABSENT")


def _check_records(
    result: CheckResultV1,
    created_at: CanonicalTimestampV1,
) -> tuple[FeedbackRecordV1, ...]:
    """Normalize one typed check failure into bounded records.

    PASS and NOT_RUN are not failures and normalize to the empty
    sequence; FAIL produces one record per structured finding and
    ERROR/TIMEOUT produce exactly one record (their single closed
    finding).  The occurrence id binds the check plan, the finding
    index, and the canonical observation time, so the same evidence at
    the same time always yields the same record and two occurrences are
    never confused.
    """
    if result.status == "PASS" or result.status == "NOT_RUN":
        return ()
    severity: FeedbackSeverityV1 = "MEDIUM" if result.status == "FAIL" else "HIGH"
    records: list[FeedbackRecordV1] = []
    for index, finding in enumerate(result.structured_findings):
        # The record never carries a secret (SPEC 7 FeedbackRecord): a
        # check finding message can echo a source line containing a
        # credential, so the summary is scanned with the frozen secret
        # vocabulary and redacted to a fixed bounded marker instead of
        # flowing into the next context.
        summary = _bounded_summary(finding.message)
        try:
            if _contains_secret(summary):
                summary = _SECRET_REDACTED_SUMMARY
        except UnicodeEncodeError:
            # A lone surrogate cannot be canonically encoded for the
            # scan; the record validator's closed rejection owns that
            # case (never a raw UnicodeEncodeError out of the builder).
            pass
        # The payload facts are closed: the optional location is an
        # explicit ABSENT/PRESENT union, never null.
        location: CanonicalValueV1 = {"kind": "ABSENT"}
        if finding.location is not None:
            column: CanonicalValueV1 = (
                {"kind": "ABSENT"}
                if finding.location.column.kind == "ABSENT"
                else {
                    "kind": "PRESENT",
                    "value": finding.location.column.value,
                }
            )
            location = {
                "kind": "PRESENT",
                "value": {
                    "path": finding.location.path,
                    "line": finding.location.line,
                    "column": column,
                },
            }
        records.append(
            FeedbackRecordV1(
                id=f"check:{result.check_kind}:{index}:{created_at.value}",
                kind="CHECK",
                severity=severity,
                created_at=created_at,
                summary=summary,
                source_ref=CheckFeedbackSourceV1(
                    kind="CHECK",
                    check_kind=result.check_kind,
                    path=_finding_path(
                        finding.location.path if finding.location is not None else None
                    ),
                ),
                bounded_payload=_canonical_payload(
                    {
                        "check_kind": result.check_kind,
                        "status": result.status,
                        "raw_digest": result.raw_digest,
                        "finding_index": index,
                        "location": location,
                    }
                ),
            )
        )
    return tuple(records)


def _action_records(
    result: ActionResultV1,
    created_at: CanonicalTimestampV1,
) -> tuple[FeedbackRecordV1, ...]:
    """Normalize one typed action failure into exactly one bounded record.

    SUCCEEDED actions are not failures and normalize to the empty
    sequence; REJECTED and FAILED actions must carry the closed action
    error (the contract enforces it), whose stable code, bounded message,
    and optional evidence reference are normalized into one record.  The
    occurrence id binds a short digest of the Harness action id and the
    canonical observation time.
    """
    if result.status == "SUCCEEDED":
        return ()
    error = result.error
    if error.kind == "ABSENT":  # unreachable for FAILED/REJECTED (contract)
        raise FeedbackConstructionErrorV1(
            "failed and rejected actions must carry a closed action error"
        )
    evidence_refs: tuple[str, ...] = ()
    if error.value.evidence_ref.kind == "PRESENT":
        evidence_refs = (error.value.evidence_ref.value.artifact_id,)
    action_identity = hashlib.sha256(_utf8_bytes(result.action_id)).hexdigest()[:24]
    return (
        FeedbackRecordV1(
            id=f"action:{action_identity}:{created_at.value}",
            kind="ACTION",
            severity="HIGH",
            created_at=created_at,
            summary=_bounded_summary(error.value.bounded_message),
            source_ref=ActionFeedbackSourceV1(
                kind="ACTION",
                action_id=result.action_id,
                semantic_digest=result.semantic_digest,
            ),
            bounded_payload=_canonical_payload(
                {
                    "action_id": result.action_id,
                    "semantic_digest": result.semantic_digest,
                    "status": result.status,
                    "result_type": result.result_type,
                    "error_code": error.value.error_code,
                }
            ),
            evidence_refs=evidence_refs,
        ),
    )


def _control_records(
    error: StableControlErrorV1,
    created_at: CanonicalTimestampV1,
) -> tuple[FeedbackRecordV1, ...]:
    """Normalize one stable control failure into exactly one record.

    Control failures are the most severe (CRITICAL): the exact stable
    error code and bounded message become the record, with the occurrence
    id binding the code and the canonical observation time.
    """
    return (
        FeedbackRecordV1(
            id=f"control:{error.error_code}:{created_at.value}",
            kind="CONTROL",
            severity="CRITICAL",
            created_at=created_at,
            summary=_bounded_summary(error.bounded_message),
            source_ref=ControlFeedbackSourceV1(
                kind="CONTROL",
                error_code=error.error_code,
            ),
            bounded_payload=_canonical_payload({"error_code": error.error_code}),
        ),
    )


def build_feedback(
    source: CheckResultV1 | ActionResultV1 | StableControlErrorV1,
    clock: ClockV1,
) -> FeedbackRecordSequenceV1:
    """Convert one typed failure source into bounded feedback records.

    Deterministic: the same source observed at the same canonical time
    produces the identical ordered record sequence.  Non-failures
    normalize to the empty sequence; lone surrogates, unbounded source
    codes, and unknown source types fail closed with
    ``FeedbackConstructionErrorV1`` before any record exists.
    """
    created_at = clock.now()
    try:
        if isinstance(source, CheckResultV1):
            return _check_records(source, created_at)
        if isinstance(source, ActionResultV1):
            return _action_records(source, created_at)
        if isinstance(source, StableControlErrorV1):
            return _control_records(source, created_at)
    except FeedbackConstructionErrorV1:
        raise
    except ValidationError as exc:
        raise FeedbackConstructionErrorV1(
            "feedback source cannot be normalized into a bounded record"
        ) from exc
    raise FeedbackConstructionErrorV1(
        f"unsupported feedback source type {type(source).__name__}"
    )


def select_feedback(records: FeedbackRecordSequenceV1) -> FeedbackSelectionV1:
    """Select the most relevant unconsumed records under the exact limits.

    Unconsumed records (``consumed_by_turn`` is None) are ordered by the
    closed severity ladder, then newest canonical time, then stable id
    (SPEC 4.2.4); at most 10 records and at most 32 KiB (SPEC 4.5) are
    selected, and the newest required failure — the unconsumed record
    with the latest canonical timestamp (id tie-break) — is always
    retained as the last selected record so neither limit can drop it.
    Byte drops remove the least relevant non-mandatory records from the
    end of the severity/recency order.  Deterministic: stable inputs
    always produce the identical selection.
    """
    unconsumed = tuple(record for record in records if record.consumed_by_turn is None)
    if not unconsumed:
        return FeedbackSelectionV1(records=())
    ordered = sorted(
        unconsumed,
        key=lambda record: (
            _SEVERITY_RANK[record.severity],
            -record.created_at.epoch_milliseconds,
            record.id,
        ),
    )
    newest = max(
        unconsumed,
        key=lambda record: (
            record.created_at.epoch_milliseconds,
            record.id,
        ),
    )
    others = [record for record in ordered if record.id != newest.id]
    candidates = list(others[: FEEDBACK_MAX_RECORDS_V1 - 1]) + [newest]
    total = sum(feedback_canonical_bytes(record) for record in candidates)
    while total > FEEDBACK_MAX_BYTES_V1 and len(candidates) > 1:
        removed = candidates.pop(-2)
        total -= feedback_canonical_bytes(removed)
    if feedback_canonical_bytes(newest) > FEEDBACK_MAX_BYTES_V1:
        # Unreachable for bounded records; keep the mandatory failure.
        candidates = [newest]
    return FeedbackSelectionV1(records=tuple(candidates))
