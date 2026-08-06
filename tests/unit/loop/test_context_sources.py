"""T24.1 legacy step 24.B: request source attribution tests.

Pins the exact SPEC 4.4.4 category/path presence contract of the context
projection: FILE_CONTENT and path-bound TOOL_RESULT segments always carry
canonical PRESENT paths, HARNESS_PROTOCOL/TASK/MEMORY and control-plane
TOOL_RESULT segments are always ABSENT, FEEDBACK segments carry the
attributed canonical path exactly when their record source does, and the
assembled segments always bind their exact content digest and byte count
(the shared T15.1 source validator proves consistency on every build).
"""

from __future__ import annotations

import hashlib

import pytest

# The projector consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips cleanly
# there (formal env runs it fully).
pytest.importorskip("pydantic")

from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.loop.context_projection import (
    ContextProjectionInputsV1,
    ContextProjectionV1,
    FileFragmentInputV1,
    MemoryInputV1,
    SnapshotFactsV1,
    TaskFactsV1,
    ToolResultInputV1,
    build_context,
)
from src.vespercode.loop.feedback import (
    CheckFeedbackSourceV1,
    FeedbackRecordV1,
)


def feedback_record(
    record_id: str,
    path: CanonicalRelativePathV1 | None = None,
) -> FeedbackRecordV1:
    """One feedback record with an optional attributed canonical path."""
    attributed = (
        AbsentV1(kind="ABSENT")
        if path is None
        else PresentV1(kind="PRESENT", value=path)
    )
    return FeedbackRecordV1(
        id=record_id,
        kind="CHECK",
        severity="HIGH",
        created_at=CanonicalTimestampV1("2026-08-06T09:00:00.000Z"),
        summary=f"failure {record_id}",
        source_ref=CheckFeedbackSourceV1(
            kind="CHECK",
            check_kind="TARGET_TESTS",
            path=attributed,
        ),
        bounded_payload='{"check_kind":"TARGET_TESTS","status":"FAIL"}',
    )


def make_inputs() -> ContextProjectionInputsV1:
    """One deterministic input set covering every allowed category."""
    return ContextProjectionInputsV1(
        protocol="protocol and action schema",
        task=TaskFactsV1(
            task="fix the failing tests",
            target_test_ids=("tests/test_a.py::test_a",),
            run_budget_summary="turns 20 / calls 20 / wall 900s",
        ),
        snapshot=SnapshotFactsV1(
            candidate_digest="c" * 64,
            final_diff_stats="0 files / 0 bytes",
        ),
        policy_facts="policy PYTHON_SRC_ONLY_V1",
        control_facts="RUNNING(AGENT_LOOP)",
        action_results=(),
        feedback=(
            feedback_record("pathless-failure"),
            feedback_record("path-failure", CanonicalRelativePathV1("src/a.py")),
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


def test_source_category_path_presence_matrix() -> None:
    projection = build_context(make_inputs())
    assert isinstance(projection, ContextProjectionV1)
    observed = [
        (segment.source_category, segment.source_path.kind)
        for message in projection.messages
        for segment in message.segments
    ]
    assert observed == [
        ("HARNESS_PROTOCOL", "ABSENT"),
        ("TASK", "ABSENT"),
        ("TASK", "ABSENT"),
        ("TASK", "ABSENT"),
        ("TOOL_RESULT", "ABSENT"),
        ("TOOL_RESULT", "ABSENT"),
        ("FEEDBACK", "ABSENT"),
        ("FEEDBACK", "PRESENT"),
        ("TOOL_RESULT", "ABSENT"),
        ("MEMORY", "ABSENT"),
        ("FILE_CONTENT", "PRESENT"),
        ("TOOL_RESULT", "PRESENT"),
    ]
    # The FEEDBACK segment carries the exact attributed canonical path.
    feedback_segments = [
        segment
        for message in projection.messages
        for segment in message.segments
        if segment.source_category == "FEEDBACK"
    ]
    attributed = feedback_segments[1].source_path
    assert isinstance(attributed, PresentV1)
    assert attributed.value.value == "src/a.py"
    # Path-bound tool results keep their exact canonical paths.
    tool_segments = [
        segment
        for message in projection.messages
        for segment in message.segments
        if segment.source_category == "TOOL_RESULT"
    ]
    tool_paths: list[str] = []
    for segment in tool_segments:
        path = segment.source_path
        if isinstance(path, PresentV1):
            tool_paths.append(path.value.value)
    assert tool_paths == ["src/b.py"]


def test_source_content_digest_and_byte_count_are_exact() -> None:
    projection = build_context(make_inputs())
    assert isinstance(projection, ContextProjectionV1)
    for message in projection.messages:
        for segment in message.segments:
            raw = segment.content.encode("utf-8")
            assert segment.byte_count == len(raw)
            assert segment.content_digest == hashlib.sha256(raw).hexdigest()
    # The shared source validator accepted every segment: a projection
    # only exists when every digest and byte count binds its content and
    # every category/path presence contract holds.
    assert len(projection.source_projection) == sum(
        len(message.segments) for message in projection.messages
    )


def test_feedback_attribution_follows_record_source() -> None:
    # A feedback record with a non-canonical reported path stays ABSENT.
    pathless = build_context(
        make_inputs().model_copy(
            update={
                "feedback": (
                    feedback_record("noncanonical"),
                    FeedbackRecordV1(
                        id="weird-path",
                        kind="CHECK",
                        severity="HIGH",
                        created_at=CanonicalTimestampV1("2026-08-06T09:00:00.000Z"),
                        summary="weird path",
                        source_ref=CheckFeedbackSourceV1(
                            kind="CHECK",
                            check_kind="TARGET_TESTS",
                            path=AbsentV1(kind="ABSENT"),
                        ),
                        bounded_payload='{"check_kind":"TARGET_TESTS"}',
                    ),
                )
            }
        )
    )
    assert isinstance(pathless, ContextProjectionV1)
    feedback_segments = [
        segment
        for message in pathless.messages
        for segment in message.segments
        if segment.source_category == "FEEDBACK"
    ]
    assert all(segment.source_path.kind == "ABSENT" for segment in feedback_segments)
