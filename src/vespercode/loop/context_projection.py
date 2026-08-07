"""T24.1 legacy step 24.B: deterministic bounded context projection.

``build_context`` assembles every allowed source category from exact typed
inputs into source-attributed messages in the frozen SPEC 4.2.4 order
(SYSTEM Harness protocol first, then TASK, the current Snapshot/candidate
binding, action results, policy facts, the selected feedback records,
control facts, selected memory, and finally file fragments and path-bound
tool results), derives the one-to-one source projection through the shared
T15.1 source validator, and computes the exact canonical byte count and
one canonical projection digest over the final messages and attribution.

Trimming removes only the declared optional categories in the fixed
SPEC 4.2.4 order (oldest memory summaries, then oldest SUCCEEDED action
results, then non-recent file fragments and path-bound tool results) with
exact byte accounting; protocol, task, the candidate binding, policy and
control facts, feedback, FAILED/REJECTED action results, and the most
recent fragment are never trimmed.  When the mandatory content alone
exceeds the frozen 64 KiB context budget the pure function returns the
zero-side-effect ``ContextBudgetFailureV1`` (CONTEXT_BUDGET_EXCEEDED).
Feedback consumption, turn creation, disclosure authorization, adapter
calls, raw restricted content, and secret inclusion remain out of scope
(GREEN-4).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Annotated, Literal

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
from vespercode.canonical.json_v1 import (
    CanonicalJsonErrorV1,
    CanonicalValueV1,
    canonical_json_bytes,
)
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.action import ActionResultV1
from vespercode.contracts.optional import (
    AbsentV1,
    OptionalCanonicalPathV1,
    PresentV1,
)
from vespercode.governance.request_sources import (
    RequestContentSegmentV1,
    RequestMessageV1,
    RequestMessageSequenceV1,
    RequestSourceCategoryV1,
    SourceProjectionV1,
    SourceValidationError,
    validate_segment_sources,
)
from vespercode.loop.feedback import (
    FeedbackRecordSequenceV1,
    FeedbackRecordV1,
    serialize_feedback_record,
)

CONTEXT_BUDGET_MAX_BYTES_V1 = 65536
"""SPEC 4.2.4/5.1: the frozen context budget is 64 KiB."""


class TaskFactsV1(BaseModel):
    """Frozen task facts (SPEC 4.2.4 step 2): task, targets, budget."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    task: StrictStr
    target_test_ids: tuple[StrictStr, ...]
    run_budget_summary: StrictStr


class SnapshotFactsV1(BaseModel):
    """Current Snapshot/candidate binding (SPEC 4.2.4 step 3)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_digest: StrictStr
    final_diff_stats: StrictStr


class ActionResultInputV1(BaseModel):
    """One action result with its recency ordinal (0 = oldest)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    result: ActionResultV1
    sequence: Annotated[int, Strict(), Field(ge=0)]


class MemoryInputV1(BaseModel):
    """One selected memory summary with its recency ordinal (0 = oldest)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    summary: StrictStr
    sequence: Annotated[int, Strict(), Field(ge=0)]

    @field_validator("summary")
    @classmethod
    def _summary_is_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("memory summaries must be non-empty")
        return value


class FileFragmentInputV1(BaseModel):
    """One bounded file fragment with its recency ordinal (0 = oldest)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    path: CanonicalRelativePathV1
    content: StrictStr
    sequence: Annotated[int, Strict(), Field(ge=0)]


class ToolResultInputV1(BaseModel):
    """One path-bound tool result with its recency ordinal (0 = oldest)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    path: CanonicalRelativePathV1
    content: StrictStr
    sequence: Annotated[int, Strict(), Field(ge=0)]


class ContextProjectionInputsV1(BaseModel):
    """The exact typed inputs of one context projection (SPEC 4.2.4).

    Every allowed source category arrives as an exact typed value; the
    frozen ``budget_bytes`` context budget (at most 64 KiB) is the sole
    trimming authority.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    protocol: StrictStr
    task: TaskFactsV1
    snapshot: SnapshotFactsV1
    policy_facts: StrictStr
    control_facts: StrictStr
    action_results: tuple[ActionResultInputV1, ...] = ()
    feedback: FeedbackRecordSequenceV1 = ()
    memory: tuple[MemoryInputV1, ...] = ()
    file_fragments: tuple[FileFragmentInputV1, ...] = ()
    tool_results: tuple[ToolResultInputV1, ...] = ()
    budget_bytes: Annotated[
        int, Strict(), Field(ge=1, le=CONTEXT_BUDGET_MAX_BYTES_V1)
    ] = CONTEXT_BUDGET_MAX_BYTES_V1


class ContextProjectionV1(BaseModel):
    """One frozen source-attributed context projection (SPEC 4.2.4).

    ``canonical_byte_count`` is the exact total UTF-8 content bytes of the
    final messages (each segment binds its own exact byte count and
    content digest); ``projection_digest`` is the one canonical digest
    over the final messages and attribution.  ``feedback_refs`` derives
    the ordered stable ids of every FEEDBACK segment.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    messages: RequestMessageSequenceV1
    source_projection: SourceProjectionV1
    canonical_byte_count: Annotated[
        int, Strict(), Field(ge=0, le=CONTEXT_BUDGET_MAX_BYTES_V1)
    ]
    projection_digest: StrictStr

    @field_validator("projection_digest")
    @classmethod
    def _digest_is_64_lowercase_hex(cls, value: str) -> str:
        if len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError(
                "projection_digest must be exactly 64 lowercase hexadecimal characters"
            )
        return value

    @model_validator(mode="after")
    def _self_bind_identity(self) -> ContextProjectionV1:
        actual_bytes = sum(
            len(segment.content.encode("utf-8"))
            for message in self.messages
            for segment in message.segments
        )
        if actual_bytes != self.canonical_byte_count:
            raise ValueError(
                "canonical_byte_count does not bind the exact message bytes"
            )
        try:
            projection = validate_segment_sources(self.messages)
        except SourceValidationError as exc:
            raise ValueError(
                "the source projection cannot be derived from the messages"
            ) from exc
        if projection != self.source_projection:
            raise ValueError(
                "source_projection must be the one-to-one segment projection"
            )
        if self.projection_digest != _projection_digest(self.messages, projection):
            raise ValueError(
                "projection_digest must bind the exact messages and projection"
            )
        return self

    @property
    def feedback_refs(self) -> tuple[str, ...]:
        """The ordered feedback ids of every FEEDBACK segment."""
        refs: list[str] = []
        for message in self.messages:
            for segment in message.segments:
                if segment.source_category == "FEEDBACK":
                    refs.append(_feedback_id_of(segment.content))
        return tuple(refs)


class ContextBudgetFailureV1(BaseModel):
    """One zero-side-effect budget failure (SPEC 4.2.4).

    Returned only when the mandatory content alone — after every allowed
    optional category has been trimmed — still exceeds the frozen context
    budget; the exact mandatory byte total and the frozen budget are
    reported and nothing is mutated or persisted.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    error_code: Literal["CONTEXT_BUDGET_EXCEEDED"]
    message: StrictStr
    mandatory_byte_count: Annotated[int, Strict(), Field(ge=0)]
    budget_bytes: Annotated[int, Strict(), Field(ge=1)]


class ContextProjectionErrorV1(ValueError):
    """Closed rejection of one context-projection construction contract.

    A control-plane construction error (non-UTF-8 content, non-canonical
    facts, or an invalid assembled source) fails closed; it is never
    confused with the budget failure.
    """


@dataclass(frozen=True)
class _AssembledSegment:
    """One assembled segment plus its optional trim metadata."""

    category: RequestSourceCategoryV1
    path: OptionalCanonicalPathV1
    content: str
    trim_group: Literal["NONE", "MEMORY", "ACTION", "FRAGMENT"]
    sequence: int
    trimmable: bool


def _path_canonical(path: OptionalCanonicalPathV1) -> CanonicalValueV1:
    """One source-path union into its canonical encoding."""
    if path.kind == "ABSENT":
        return {"kind": "ABSENT"}
    return {"kind": "PRESENT", "value": path.value.value}


def _canonical_text(facts: CanonicalValueV1) -> str:
    """One canonical JSON text (the closed-union rule rejects nulls)."""
    return canonical_json_bytes(facts).decode("utf-8")


def _action_result_text(result: ActionResultV1) -> str:
    """One action result summary into canonical JSON text."""
    error_code: CanonicalValueV1 = {"kind": "ABSENT"}
    if result.error.kind == "PRESENT":
        error_code = {"kind": "PRESENT", "value": result.error.value.error_code}
    return canonical_json_bytes(
        {
            "action_id": result.action_id,
            "semantic_digest": result.semantic_digest,
            "status": result.status,
            "result_type": result.result_type,
            "error_code": error_code,
        }
    ).decode("utf-8")


def _feedback_path(record: FeedbackRecordV1) -> OptionalCanonicalPathV1:
    """The FEEDBACK segment path follows the record's attributed source.

    SPEC 4.4.4: a FEEDBACK fact attributable to one concrete repository
    path must be PRESENT; the only path-bearing feedback sources are
    check findings whose reported path forms a valid canonical path.
    """
    if record.source_ref.kind == "CHECK" and record.source_ref.path.kind == "PRESENT":
        return PresentV1(kind="PRESENT", value=record.source_ref.path.value)
    return AbsentV1(kind="ABSENT")


def _feedback_id_of(content: str) -> str:
    """The stable id of one FEEDBACK segment's canonical record text."""
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ContextProjectionErrorV1(
            "FEEDBACK segment content must be canonical feedback JSON"
        ) from exc
    record_id = parsed.get("id")
    if not isinstance(record_id, str) or record_id == "":
        raise ContextProjectionErrorV1(
            "FEEDBACK segment content must carry a stable feedback id"
        )
    return record_id


def _assemble(
    inputs: ContextProjectionInputsV1,
) -> tuple[list[_AssembledSegment], int]:
    """Assemble every category in the frozen order with trim metadata."""
    protocol = _AssembledSegment(
        "HARNESS_PROTOCOL",
        AbsentV1(kind="ABSENT"),
        inputs.protocol,
        "NONE",
        0,
        False,
    )
    user: list[_AssembledSegment] = []
    # Frozen order step 2: the frozen task, targets, and run budget.
    user.append(
        _AssembledSegment(
            "TASK", AbsentV1(kind="ABSENT"), inputs.task.task, "NONE", 0, False
        )
    )
    user.append(
        _AssembledSegment(
            "TASK",
            AbsentV1(kind="ABSENT"),
            _canonical_text({"target_test_ids": tuple(inputs.task.target_test_ids)}),
            "NONE",
            0,
            False,
        )
    )
    user.append(
        _AssembledSegment(
            "TASK",
            AbsentV1(kind="ABSENT"),
            inputs.task.run_budget_summary,
            "NONE",
            0,
            False,
        )
    )
    # Frozen order step 3: the current Snapshot/candidate binding.
    user.append(
        _AssembledSegment(
            "TOOL_RESULT",
            AbsentV1(kind="ABSENT"),
            _canonical_text(
                {
                    "candidate_digest": inputs.snapshot.candidate_digest,
                    "final_diff_stats": inputs.snapshot.final_diff_stats,
                }
            ),
            "NONE",
            0,
            False,
        )
    )
    # Action results, oldest first; only SUCCEEDED summaries are
    # trimmable (SPEC 4.2.4 drops the oldest successful action summaries).
    for action_entry in sorted(inputs.action_results, key=lambda item: item.sequence):
        user.append(
            _AssembledSegment(
                "TOOL_RESULT",
                AbsentV1(kind="ABSENT"),
                _action_result_text(action_entry.result),
                "ACTION",
                action_entry.sequence,
                action_entry.result.status == "SUCCEEDED",
            )
        )
    # Policy facts (card mandatory order, control-plane, pathless).
    user.append(
        _AssembledSegment(
            "TOOL_RESULT",
            AbsentV1(kind="ABSENT"),
            inputs.policy_facts,
            "NONE",
            0,
            False,
        )
    )
    # Frozen order step 4: the selected unconsumed feedback records.
    # Feedback is never trimmed: Task 24.A already bounds the selection to
    # 10 records / 32 KiB and the SPEC trim list does not include it.
    for record in inputs.feedback:
        user.append(
            _AssembledSegment(
                "FEEDBACK",
                _feedback_path(record),
                serialize_feedback_record(record),
                "NONE",
                0,
                False,
            )
        )
    # Control facts (card mandatory order, control-plane, pathless).
    user.append(
        _AssembledSegment(
            "TOOL_RESULT",
            AbsentV1(kind="ABSENT"),
            inputs.control_facts,
            "NONE",
            0,
            False,
        )
    )
    # Frozen order step 5: selected memory, oldest first, trimmable.
    for memory_entry in sorted(inputs.memory, key=lambda item: item.sequence):
        user.append(
            _AssembledSegment(
                "MEMORY",
                AbsentV1(kind="ABSENT"),
                memory_entry.summary,
                "MEMORY",
                memory_entry.sequence,
                True,
            )
        )
    # Frozen order step 6: file fragments and path-bound tool results,
    # oldest first; only the most recent fragment is never trimmable.
    fragment_units = [
        _AssembledSegment(
            "FILE_CONTENT",
            PresentV1(kind="PRESENT", value=fragment.path),
            fragment.content,
            "FRAGMENT",
            fragment.sequence,
            True,
        )
        for fragment in sorted(inputs.file_fragments, key=lambda item: item.sequence)
    ]
    fragment_units.extend(
        _AssembledSegment(
            "TOOL_RESULT",
            PresentV1(kind="PRESENT", value=tool.path),
            tool.content,
            "FRAGMENT",
            tool.sequence,
            True,
        )
        for tool in sorted(inputs.tool_results, key=lambda item: item.sequence)
    )
    if fragment_units:
        most_recent = max(unit.sequence for unit in fragment_units)
        fragment_units = [
            _AssembledSegment(
                unit.category,
                unit.path,
                unit.content,
                unit.trim_group,
                unit.sequence,
                unit.sequence != most_recent,
            )
            for unit in fragment_units
        ]
    user.extend(fragment_units)
    all_segments = [protocol] + user
    total = sum(len(unit.content.encode("utf-8")) for unit in all_segments)
    return all_segments, total


def _trim(
    segments: list[_AssembledSegment],
    total: int,
    budget_bytes: int,
) -> tuple[list[_AssembledSegment], int]:
    """Drop only the declared optional categories in the fixed order.

    SPEC 4.2.4: oldest memory first, then oldest successful action
    summaries, then non-recent file fragments — each trimmable unit is
    removed whole (no partial truncation) while the total exceeds the
    frozen budget.
    """
    for group in ("MEMORY", "ACTION", "FRAGMENT"):
        candidates = sorted(
            (unit for unit in segments if unit.trim_group == group and unit.trimmable),
            key=lambda unit: unit.sequence,
        )
        for candidate in candidates:
            if total <= budget_bytes:
                return segments, total
            segments = [unit for unit in segments if unit is not candidate]
            total -= len(candidate.content.encode("utf-8"))
    return segments, total


def _to_segment(unit: _AssembledSegment) -> RequestContentSegmentV1:
    """One assembled unit into a segment binding its exact content."""
    raw = unit.content.encode("utf-8")
    return RequestContentSegmentV1(
        source_category=unit.category,
        source_path=unit.path,
        content=unit.content,
        content_digest=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
    )


def _projection_digest(
    messages: RequestMessageSequenceV1,
    source_projection: SourceProjectionV1,
) -> str:
    """The one canonical digest over the final messages and attribution.

    The digest binds the completed, trimmed projection (SPEC 0.1
    ContextProjection): the exact messages with their segments, and the
    one-to-one source projection; any content or attribution change
    changes the digest.
    """
    return domain_digest(
        "ContextProjection",
        1,
        {
            "schema_version": 1,
            "messages": tuple(
                {
                    "role": message.role,
                    "segments": tuple(
                        {
                            "source_category": segment.source_category,
                            "source_path": _path_canonical(segment.source_path),
                            "content": segment.content,
                            "content_digest": segment.content_digest,
                            "byte_count": segment.byte_count,
                        }
                        for segment in message.segments
                    ),
                }
                for message in messages
            ),
            "source_projection": tuple(
                {
                    "message_index": source.message_index,
                    "segment_index": source.segment_index,
                    "source_category": source.source_category,
                    "source_path": _path_canonical(source.source_path),
                    "content_digest": source.content_digest,
                    "byte_count": source.byte_count,
                }
                for source in source_projection
            ),
        },
    )


def build_context(
    inputs: ContextProjectionInputsV1,
) -> ContextProjectionV1 | ContextBudgetFailureV1:
    """Assemble, trim, and freeze one deterministic context projection.

    Pure: never mutates the inputs, consumes feedback, creates turns,
    authorizes disclosure, or calls adapters.  When the mandatory content
    alone still exceeds the frozen budget after every allowed optional
    category has been trimmed, the zero-side-effect
    ``CONTEXT_BUDGET_EXCEEDED`` failure is returned; a control-plane
    construction contract violation (surrogate content, non-canonical
    facts, invalid assembled sources) fails closed with
    ``ContextProjectionErrorV1``.
    """
    try:
        segments, total = _assemble(inputs)
        if total > inputs.budget_bytes:
            segments, total = _trim(segments, total, inputs.budget_bytes)
            if total > inputs.budget_bytes:
                return ContextBudgetFailureV1(
                    error_code="CONTEXT_BUDGET_EXCEEDED",
                    message="mandatory context content exceeds the frozen budget",
                    mandatory_byte_count=total,
                    budget_bytes=inputs.budget_bytes,
                )
        protocol_segment = segments[0]
        user_segments = segments[1:]
        messages = (
            RequestMessageV1(role="SYSTEM", segments=(_to_segment(protocol_segment),)),
            RequestMessageV1(
                role="USER",
                segments=tuple(_to_segment(unit) for unit in user_segments),
            ),
        )
        source_projection = validate_segment_sources(messages)
        canonical_byte_count = sum(
            segment.byte_count for message in messages for segment in message.segments
        )
        return ContextProjectionV1(
            messages=messages,
            source_projection=source_projection,
            canonical_byte_count=canonical_byte_count,
            projection_digest=_projection_digest(messages, source_projection),
        )
    except (UnicodeEncodeError, CanonicalJsonErrorV1, SourceValidationError) as exc:
        raise ContextProjectionErrorV1(
            "context projection cannot be constructed from the given inputs"
        ) from exc
