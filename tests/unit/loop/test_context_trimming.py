"""T24.1 legacy step 24.B: deterministic context trimming tests.

The exact RED test pins the mandatory most-recent-failure retention; the
matrix pins the exact trim contract (SPEC 4.2.4): optional categories are
dropped in the fixed order (oldest memory, then oldest successful action
results, then non-recent file fragments) with exact byte accounting,
mandatory facts and source paths are preserved, and impossible mandatory
content returns the zero-side-effect budget failure.
"""

from __future__ import annotations

import pytest

# The projector consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips cleanly
# there (formal env runs it fully).
pytest.importorskip("pydantic")

from vespercode.canonical.digest import domain_digest
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.action import (
    ActionErrorV1,
    ActionResultV1,
    ActionStatusV1,
)
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.loop.context_projection import (
    ActionResultInputV1,
    ContextBudgetFailureV1,
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

_CREATED_AT = "2026-08-06T09:00:00.000Z"


def feedback_record(record_id: str, created_at: str = _CREATED_AT) -> FeedbackRecordV1:
    """One deterministic unconsumed feedback record."""
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


def memory_input(sequence: int, size: int) -> MemoryInputV1:
    """One memory summary of the exact content size."""
    return MemoryInputV1(summary="M" * size, sequence=sequence)


def fragment_input(sequence: int, size: int) -> FileFragmentInputV1:
    """One bounded file fragment of the exact content size."""
    return FileFragmentInputV1(
        path=CanonicalRelativePathV1(f"src/frag_{sequence}.py"),
        content="F" * size,
        sequence=sequence,
    )


def tool_result_input(sequence: int, size: int) -> ToolResultInputV1:
    """One path-bound tool result of the exact content size."""
    return ToolResultInputV1(
        path=CanonicalRelativePathV1(f"src/tool_{sequence}.py"),
        content="T" * size,
        sequence=sequence,
    )


def action_result_input(
    sequence: int,
    status: ActionStatusV1,
    action_id: str,
) -> ActionResultInputV1:
    """One deterministic action result input."""
    semantic_digest = "e" * 64
    instance_digest = domain_digest(
        "ActionInstanceDigestV1",
        1,
        {
            "schema_version": 1,
            "action_id": action_id,
            "semantic_digest": semantic_digest,
        },
    )
    return ActionResultInputV1(
        result=ActionResultV1(
            schema_version=1,
            action_id=action_id,
            semantic_digest=semantic_digest,
            instance_digest=instance_digest,
            status=status,
            result_type="ApplyCandidatePatchResult",
            payload_ref=AbsentV1(kind="ABSENT"),
            error=(
                AbsentV1(kind="ABSENT")
                if status == "SUCCEEDED"
                else PresentV1(
                    kind="PRESENT",
                    value=ActionErrorV1(
                        error_code="ACTION_FAILED",
                        bounded_message="action failed",
                        evidence_ref=AbsentV1(kind="ABSENT"),
                    ),
                )
            ),
        ),
        sequence=sequence,
    )


def make_inputs(
    *,
    protocol: str = "P" * 200,
    task: TaskFactsV1 = TaskFactsV1(
        task="fix the failing tests",
        target_test_ids=("tests/test_a.py::test_a",),
        run_budget_summary="turns 20 / calls 20 / wall 900s",
    ),
    snapshot: SnapshotFactsV1 = SnapshotFactsV1(
        candidate_digest="c" * 64,
        final_diff_stats="0 files / 0 bytes",
    ),
    policy_facts: str = "policy PYTHON_SRC_ONLY_V1",
    control_facts: str = "RUNNING(AGENT_LOOP)",
    action_results: tuple[ActionResultInputV1, ...] = (),
    feedback: tuple[FeedbackRecordV1, ...] = (feedback_record("most-recent-failure"),),
    memory: tuple[MemoryInputV1, ...] = (),
    file_fragments: tuple[FileFragmentInputV1, ...] = (),
    tool_results: tuple[ToolResultInputV1, ...] = (),
    budget_bytes: int = 65536,
) -> ContextProjectionInputsV1:
    """One deterministic input set; the fields are small by default."""
    return ContextProjectionInputsV1(
        protocol=protocol,
        task=task,
        snapshot=snapshot,
        policy_facts=policy_facts,
        control_facts=control_facts,
        action_results=action_results,
        feedback=feedback,
        memory=memory,
        file_fragments=file_fragments,
        tool_results=tool_results,
        budget_bytes=budget_bytes,
    )


def oversized_context_inputs() -> ContextProjectionInputsV1:
    """Inputs whose total content exceeds the frozen 64 KiB budget.

    Eight 8 KiB memory summaries and two 8 KiB file fragments push the
    total well over the budget; after the fixed trim order (memory first)
    the projection fits and the most recent failure feedback must remain.
    """
    return make_inputs(
        feedback=(
            feedback_record("older-failure"),
            feedback_record("most-recent-failure", "2026-08-06T10:00:00.000Z"),
        ),
        memory=tuple(memory_input(index, 8192) for index in range(8)),
        file_fragments=(fragment_input(0, 8192), fragment_input(1, 8192)),
    )


def test_trimming_never_removes_most_recent_failure_feedback() -> None:
    projection = build_context(oversized_context_inputs())
    # The card Interface returns the union; the card body accesses the
    # member directly, so the union attribute needs the tooling ignore.
    assert "most-recent-failure" in projection.feedback_refs  # type: ignore[union-attr]


def test_context_trim_matrix() -> None:
    """PLAN Registry row 24.B: the exact deterministic trim matrix.

    Per the SPEC_PROCESS 49 precedent the card Expected line is the
    operative matrix authority: mandatory facts remain, trim order,
    budgets, and source paths are exact, and impossible mandatory content
    returns the zero-side-effect budget failure.
    """
    base = build_context(make_inputs())
    assert isinstance(base, ContextProjectionV1)
    mandatory_bytes = base.canonical_byte_count
    assert mandatory_bytes < 65536

    # --- Within budget: every category stays in the frozen order. ---
    assert base.messages[0].role == "SYSTEM"
    assert base.messages[1].role == "USER"
    categories = [
        (segment.source_category, segment.source_path.kind)
        for message in base.messages
        for segment in message.segments
    ]
    assert categories == [
        ("HARNESS_PROTOCOL", "ABSENT"),
        ("TASK", "ABSENT"),
        ("TASK", "ABSENT"),
        ("TASK", "ABSENT"),
        ("TOOL_RESULT", "ABSENT"),
        ("TOOL_RESULT", "ABSENT"),
        ("FEEDBACK", "ABSENT"),
        ("TOOL_RESULT", "ABSENT"),
    ]

    # --- Trim step 1: oldest memory summaries drop first. ---
    mem_projection = build_context(
        make_inputs(
            memory=tuple(memory_input(index, 30000) for index in range(3)),
        )
    )
    assert isinstance(mem_projection, ContextProjectionV1)
    mem_ids = [
        segment.content
        for message in mem_projection.messages
        for segment in message.segments
        if segment.source_category == "MEMORY"
    ]
    assert mem_ids == ["M" * 30000] * 2  # memory-0 dropped, 1 and 2 remain

    # --- Trim steps 1-3: memory, then successful actions, then fragments.
    # The FAILED action result and the most recent fragment are never
    # trimmable, and every mandatory fact stays. ---
    big = build_context(
        make_inputs(
            memory=tuple(memory_input(index, 30000) for index in range(3)),
            action_results=(
                action_result_input(0, "SUCCEEDED", "action-ok-0"),
                action_result_input(1, "FAILED", "action-bad-1"),
                action_result_input(2, "SUCCEEDED", "action-ok-2"),
                action_result_input(3, "SUCCEEDED", "action-ok-3"),
            ),
            file_fragments=(fragment_input(0, 40000), fragment_input(1, 40000)),
            tool_results=(tool_result_input(0, 40000),),
            feedback=(
                feedback_record("older-failure"),
                feedback_record("most-recent-failure", "2026-08-06T10:00:00.000Z"),
            ),
        )
    )
    assert isinstance(big, ContextProjectionV1)
    remaining = [
        segment.content for message in big.messages for segment in message.segments
    ]
    assert not any("M" * 30000 in content for content in remaining)
    assert not any("action-ok-0" in content for content in remaining)
    assert not any("action-ok-2" in content for content in remaining)
    assert not any("action-ok-3" in content for content in remaining)
    assert any("action-bad-1" in content for content in remaining)
    # Mandatory facts remain with their exact content.
    assert any("P" * 200 in content for content in remaining)
    assert any("fix the failing tests" in content for content in remaining)
    assert any("c" * 64 in content for content in remaining)
    assert any("policy PYTHON_SRC_ONLY_V1" in content for content in remaining)
    assert any("RUNNING(AGENT_LOOP)" in content for content in remaining)
    # Only the most recent fragment (src/frag_1.py) survives the trim.
    remaining_paths = {
        segment.source_path.value.value
        for message in big.messages
        for segment in message.segments
        if segment.source_category in ("FILE_CONTENT", "TOOL_RESULT")
        and segment.source_path.kind == "PRESENT"
    }
    assert remaining_paths == {"src/frag_1.py"}
    assert "most-recent-failure" in big.feedback_refs
    assert "older-failure" in big.feedback_refs  # feedback is never trimmed

    # --- Trim order is exact: memory is the first priority. ---
    ordered = build_context(
        make_inputs(
            memory=(memory_input(0, 20000), memory_input(1, 20000)),
            action_results=(action_result_input(0, "SUCCEEDED", "action-early"),),
            file_fragments=(fragment_input(0, 20000), fragment_input(1, 20000)),
        )
    )
    assert isinstance(ordered, ContextProjectionV1)
    ordered_remaining = [
        segment.content for message in ordered.messages for segment in message.segments
    ]
    # Exactly the oldest memory summary drops; the action result and both
    # fragments survive because memory alone fits the budget.
    assert ordered_remaining.count("M" * 20000) == 1
    assert any("action-early" in content for content in ordered_remaining)
    assert ordered_remaining.count("F" * 20000) == 2

    # --- Determinism: identical inputs produce identical projections. ---
    again = build_context(oversized_context_inputs())
    assert isinstance(again, ContextProjectionV1)
    third = build_context(oversized_context_inputs())
    assert isinstance(third, ContextProjectionV1)
    assert again == third
    assert again.projection_digest == third.projection_digest

    # --- Impossible mandatory content: the zero-side-effect budget
    # failure, even when no trimmable category exists. ---
    failure = build_context(
        make_inputs(
            protocol="P" * 60000,
            task=TaskFactsV1(
                task="X" * 60000,
                target_test_ids=("tests/test_a.py::test_a",),
                run_budget_summary="turns 20",
            ),
            budget_bytes=65536,
        )
    )
    assert isinstance(failure, ContextBudgetFailureV1)
    assert failure.error_code == "CONTEXT_BUDGET_EXCEEDED"
    assert failure.mandatory_byte_count > failure.budget_bytes
    assert failure.budget_bytes == 65536
    # Zero side effects: the identical failure returns on every build.
    assert (
        build_context(
            make_inputs(
                protocol="P" * 60000,
                task=TaskFactsV1(
                    task="X" * 60000,
                    target_test_ids=("tests/test_a.py::test_a",),
                    run_budget_summary="turns 20",
                ),
                budget_bytes=65536,
            )
        )
        == failure
    )

    # --- The most recent fragment protection covers path-bound tool
    # results too: a TOOL_RESULT with the highest recency ordinal is the
    # protected unit while older FILE_CONTENT fragments drop. ---
    tool_most_recent = build_context(
        make_inputs(
            memory=tuple(memory_input(index, 30000) for index in range(2)),
            file_fragments=(fragment_input(0, 40000),),
            tool_results=(
                tool_result_input(0, 40000),
                tool_result_input(1, 40000),
            ),
        )
    )
    assert isinstance(tool_most_recent, ContextProjectionV1)
    tool_paths = {
        segment.source_path.value.value
        for message in tool_most_recent.messages
        for segment in message.segments
        if segment.source_category in ("FILE_CONTENT", "TOOL_RESULT")
        and isinstance(segment.source_path, PresentV1)
    }
    assert tool_paths == {"src/tool_1.py"}

    # --- A protected most recent fragment alone over the budget still
    # fails closed (non-recent trimming cannot reach it). ---
    fragment_failure = build_context(
        make_inputs(
            memory=tuple(memory_input(index, 30000) for index in range(2)),
            file_fragments=(fragment_input(0, 70000),),
        )
    )
    assert isinstance(fragment_failure, ContextBudgetFailureV1)
    assert fragment_failure.error_code == "CONTEXT_BUDGET_EXCEEDED"
