"""T24.1 legacy step 24.B: deterministic context projection tests.

Pins the frozen assembly (SYSTEM protocol message followed by the USER
message in the exact SPEC 4.2.4 category order), the one-to-one segment/
source projection with exact zero-based indices, the exact canonical byte
accounting, the deterministic projection digest over the final messages
and attribution, the impossible-mandatory-content zero-side-effect budget
failure, and the ordered FEEDBACK reference projection.
"""

from __future__ import annotations

import pytest

# The projector consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips cleanly
# there (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.canonical.path_v1 import (
    CanonicalPathErrorV1,
    CanonicalRelativePathV1,
)
from vespercode.loop.context_projection import (
    ContextBudgetFailureV1,
    ContextProjectionErrorV1,
    ContextProjectionInputsV1,
    ContextProjectionV1,
    FileFragmentInputV1,
    MemoryInputV1,
    SnapshotFactsV1,
    TaskFactsV1,
    ToolResultInputV1,
    build_context,
)
from vespercode.loop.feedback import (
    CheckFeedbackSourceV1,
    FeedbackRecordV1,
)
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.optional import AbsentV1


def feedback_record(record_id: str, created_at: str) -> FeedbackRecordV1:
    """One deterministic feedback record."""
    return FeedbackRecordV1(
        id=record_id,
        kind="CHECK",
        severity="HIGH",
        created_at=CanonicalTimestampV1(created_at),
        summary=f"failure {record_id}",
        source_ref=CheckFeedbackSourceV1(
            kind="CHECK",
            check_kind="TARGET_TESTS",
            path=AbsentV1(kind="ABSENT"),
        ),
        bounded_payload='{"check_kind":"TARGET_TESTS","status":"FAIL"}',
    )


def make_inputs() -> ContextProjectionInputsV1:
    """One deterministic input set covering every allowed category."""
    return ContextProjectionInputsV1(
        protocol="protocol and action schema",
        task=TaskFactsV1(
            task="fix the failing tests",
            target_test_ids=("tests/test_a.py::test_a", "tests/test_b.py::test_b"),
            run_budget_summary="turns 20 / calls 20 / wall 900s",
        ),
        snapshot=SnapshotFactsV1(
            candidate_digest="c" * 64,
            final_diff_stats="2 files / 1024 bytes",
        ),
        policy_facts="policy PYTHON_SRC_ONLY_V1",
        control_facts="RUNNING(AGENT_LOOP)",
        action_results=(),
        feedback=(
            feedback_record("failure-1", "2026-08-06T09:00:00.000Z"),
            feedback_record("failure-2", "2026-08-06T09:01:00.000Z"),
        ),
        memory=(MemoryInputV1(summary="memory note", sequence=0),),
        file_fragments=(
            FileFragmentInputV1(
                path=CanonicalRelativePathV1("src/a.py"),
                content="def a(): pass",
                sequence=0,
            ),
        ),
        tool_results=(
            ToolResultInputV1(
                path=CanonicalRelativePathV1("src/b.py"),
                content="b.py:3:1: F401 unused import",
                sequence=0,
            ),
        ),
        budget_bytes=65536,
    )


def test_projection_assembly_frozen_order_and_roles() -> None:
    projection = build_context(make_inputs())
    assert isinstance(projection, ContextProjectionV1)
    assert [message.role for message in projection.messages] == [
        "SYSTEM",
        "USER",
    ]
    # The SYSTEM message carries only the Harness protocol.
    assert projection.messages[0].segments[0].source_category == "HARNESS_PROTOCOL"
    # The USER message follows the exact frozen category order (SPEC
    # 4.2.4 steps 2-6 with the card's policy/control facts in place).
    user_categories = [
        segment.source_category for segment in projection.messages[1].segments
    ]
    assert user_categories == [
        "TASK",
        "TASK",
        "TASK",
        "TOOL_RESULT",
        "TOOL_RESULT",
        "FEEDBACK",
        "FEEDBACK",
        "TOOL_RESULT",
        "MEMORY",
        "FILE_CONTENT",
        "TOOL_RESULT",
    ]


def test_projection_source_projection_is_one_to_one() -> None:
    projection = build_context(make_inputs())
    assert isinstance(projection, ContextProjectionV1)
    segments = [
        segment for message in projection.messages for segment in message.segments
    ]
    assert len(projection.source_projection) == len(segments)
    expected_indices = [
        (message_index, segment_index)
        for message_index, message in enumerate(projection.messages)
        for segment_index in range(len(message.segments))
    ]
    assert [
        (source.message_index, source.segment_index)
        for source in projection.source_projection
    ] == expected_indices
    for source, segment in zip(projection.source_projection, segments):
        assert source.source_category == segment.source_category
        assert source.source_path == segment.source_path
        assert source.content_digest == segment.content_digest
        assert source.byte_count == segment.byte_count


def test_projection_canonical_byte_count_is_exact() -> None:
    projection = build_context(make_inputs())
    assert isinstance(projection, ContextProjectionV1)
    expected = sum(
        len(segment.content.encode("utf-8"))
        for message in projection.messages
        for segment in message.segments
    )
    assert projection.canonical_byte_count == expected
    assert 0 < projection.canonical_byte_count <= 65536
    for message in projection.messages:
        for segment in message.segments:
            assert segment.byte_count == len(segment.content.encode("utf-8"))


def test_projection_digest_is_deterministic_and_binds_content() -> None:
    first = build_context(make_inputs())
    second = build_context(make_inputs())
    assert isinstance(first, ContextProjectionV1)
    assert isinstance(second, ContextProjectionV1)
    assert first.projection_digest == second.projection_digest
    assert len(first.projection_digest) == 64
    assert all(character in "0123456789abcdef" for character in first.projection_digest)
    # Any content change changes the digest.
    changed = build_context(
        make_inputs().model_copy(update={"protocol": "protocol and schema v2"})
    )
    assert isinstance(changed, ContextProjectionV1)
    assert changed.projection_digest != first.projection_digest
    # The source projection is bound: identical messages with a different
    # attribution cannot occur, but a rebuilt projection with a different
    # feedback order produces a different digest.
    reordered = build_context(
        make_inputs().model_copy(
            update={
                "feedback": (
                    feedback_record("failure-2", "2026-08-06T09:01:00.000Z"),
                    feedback_record("failure-1", "2026-08-06T09:00:00.000Z"),
                )
            }
        )
    )
    assert isinstance(reordered, ContextProjectionV1)
    assert reordered.projection_digest != first.projection_digest


def test_projection_feedback_refs_are_ordered() -> None:
    projection = build_context(make_inputs())
    assert isinstance(projection, ContextProjectionV1)
    assert projection.feedback_refs == ("failure-1", "failure-2")
    empty = build_context(make_inputs().model_copy(update={"feedback": ()}))
    assert isinstance(empty, ContextProjectionV1)
    assert empty.feedback_refs == ()


def test_impossible_mandatory_content_returns_budget_failure() -> None:
    inputs = make_inputs().model_copy(
        update={
            "protocol": "P" * 60000,
            "task": TaskFactsV1(
                task="X" * 60000,
                target_test_ids=("tests/test_a.py::test_a",),
                run_budget_summary="turns 20",
            ),
        }
    )
    failure = build_context(inputs)
    assert isinstance(failure, ContextBudgetFailureV1)
    assert failure.error_code == "CONTEXT_BUDGET_EXCEEDED"
    assert failure.mandatory_byte_count > failure.budget_bytes
    assert failure.budget_bytes == inputs.budget_bytes
    # Zero side effects: the same inputs always fail identically.
    assert build_context(inputs) == failure


def test_surrogate_content_fails_closed() -> None:
    with pytest.raises(ContextProjectionErrorV1, match="cannot be constructed"):
        build_context(
            make_inputs().model_copy(
                update={
                    "file_fragments": (
                        FileFragmentInputV1(
                            path=CanonicalRelativePathV1("src/a.py"),
                            content="bad \ud800",
                            sequence=0,
                        ),
                    )
                }
            )
        )
    with pytest.raises(ContextProjectionErrorV1, match="cannot be constructed"):
        build_context(
            make_inputs().model_copy(
                update={
                    "tool_results": (
                        ToolResultInputV1(
                            path=CanonicalRelativePathV1("src/b.py"),
                            content="bad \udfff",
                            sequence=0,
                        ),
                    )
                }
            )
        )


def test_projection_input_contract_is_closed() -> None:
    with pytest.raises(ValidationError):
        ContextProjectionInputsV1(
            protocol="p",
            task=TaskFactsV1(task="t", target_test_ids=(), run_budget_summary="b"),
            snapshot=SnapshotFactsV1(candidate_digest="c" * 64, final_diff_stats="s"),
            policy_facts="p",
            control_facts="c",
            budget_bytes=0,
        )
    with pytest.raises(ValidationError):
        ContextProjectionInputsV1(
            protocol="p",
            task=TaskFactsV1(task="t", target_test_ids=(), run_budget_summary="b"),
            snapshot=SnapshotFactsV1(candidate_digest="c" * 64, final_diff_stats="s"),
            policy_facts="p",
            control_facts="c",
            budget_bytes=65537,
        )
    with pytest.raises(ValidationError):
        ContextProjectionInputsV1(
            protocol="p",
            task=TaskFactsV1(task="t", target_test_ids=(), run_budget_summary="b"),
            snapshot=SnapshotFactsV1(candidate_digest="c" * 64, final_diff_stats="s"),
            policy_facts="p",
            control_facts="c",
            schema_version=2,  # type: ignore[arg-type]
        )
    with pytest.raises(CanonicalPathErrorV1):
        CanonicalRelativePathV1("C:/windows/absolute.py")
    with pytest.raises(CanonicalPathErrorV1):
        FileFragmentInputV1(
            path=CanonicalRelativePathV1("../escape.py"),
            content="x",
            sequence=0,
        )
    with pytest.raises(ValidationError):
        MemoryInputV1(summary="", sequence=0)
    # Unknown fields and missing mandatory fields are rejected.
    with pytest.raises(ValidationError):
        ContextProjectionInputsV1(
            protocol="p",
            task=TaskFactsV1(task="t", target_test_ids=(), run_budget_summary="b"),
            snapshot=SnapshotFactsV1(candidate_digest="c" * 64, final_diff_stats="s"),
            policy_facts="p",
            control_facts="c",
            extra_field="x",  # type: ignore[call-arg]
        )
    with pytest.raises(ValidationError):
        ContextProjectionInputsV1(
            protocol="p",
            task=TaskFactsV1(task="t", target_test_ids=(), run_budget_summary="b"),
            snapshot=SnapshotFactsV1(candidate_digest="c" * 64, final_diff_stats="s"),
            control_facts="c",  # type: ignore[call-arg]  # policy_facts omitted
        )


def test_projection_trimmed_paths_stay_bound() -> None:
    """Source paths survive trimming exactly as assembled."""
    inputs = make_inputs().model_copy(
        update={
            "memory": (MemoryInputV1(summary="M" * 40000, sequence=0),),
        }
    )
    projection = build_context(inputs)
    assert isinstance(projection, ContextProjectionV1)
    file_segments = [
        segment
        for message in projection.messages
        for segment in message.segments
        if segment.source_category == "FILE_CONTENT"
    ]
    assert len(file_segments) == 1
    assert file_segments[0].source_path.kind == "PRESENT"
    assert file_segments[0].source_path.value.value == "src/a.py"
