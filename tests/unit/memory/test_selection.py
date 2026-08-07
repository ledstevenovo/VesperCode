"""T22.1 legacy step 22.B: pure bounded memory selection tests.

Pins the pure ``select_memory`` contract directly on entry sequences:
exact workspace filtering, cleared-entry exclusion, frozen kind priority,
recency, stable entry-id tie-breaks, count and canonical byte limits,
retained source attribution, and byte-identical determinism.  Creation,
confirmation, clearing, and current-evidence overrides remain out of
scope (GREEN-4).
"""

from __future__ import annotations

import pytest

# The models are pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.memory.entry import (
    KnownFailureSourceV1,
    MemoryEntryV1,
    RunSummarySourceV1,
    UserDecisionSourceV1,
    UserVisibleTextSourceV1,
    canonical_memory_byte_count,
)
from vespercode.memory.selection import (
    FROZEN_MEMORY_KIND_PRIORITY_V1,
    MemorySelectionQueryV1,
    select_memory,
)

_CREATED_AT = CanonicalTimestampV1("2026-08-06T09:00:00.000Z")
_NEWER_AT = CanonicalTimestampV1("2026-08-06T10:00:00.000Z")

_A_DIGEST = "a" * 64
_B_DIGEST = "b" * 64


def entry(
    *,
    entry_id: str,
    kind: str = "PROJECT_CONVENTION",
    summary: str = "convention",
    workspace_identity: str = "workspace-a",
    updated_at: CanonicalTimestampV1 = _CREATED_AT,
    cleared: bool = False,
) -> MemoryEntryV1:
    if kind == "USER_DECISION":
        source: (
            UserDecisionSourceV1
            | KnownFailureSourceV1
            | RunSummarySourceV1
            | UserVisibleTextSourceV1
        ) = UserDecisionSourceV1(
            kind="USER_DECISION", decision="APPROVE", reference="wait-1"
        )
    elif kind == "KNOWN_FAILURE":
        source = KnownFailureSourceV1(
            kind="KNOWN_FAILURE",
            check_result_digest="a" * 64,
            failure_fingerprint_digest="b" * 64,
        )
    elif kind == "RUN_SUMMARY":
        source = RunSummarySourceV1(
            kind="RUN_SUMMARY", run_id="run-1", result="SUCCEEDED"
        )
    else:
        source = UserVisibleTextSourceV1(kind="USER_VISIBLE_TEXT", reference="conv-1")
    return MemoryEntryV1(
        entry_id=entry_id,
        workspace_identity=workspace_identity,
        kind=kind,  # type: ignore[arg-type]
        summary=summary,
        creator="USER" if kind == "PROJECT_CONVENTION" else "CONTROL_PLANE",
        source=source,
        created_at=_CREATED_AT,
        updated_at=updated_at,
        untrusted=kind == "PROJECT_CONVENTION",
        cleared_at=_NEWER_AT if cleared else None,
        clear_transaction_id="clear-1" if cleared else None,
    )


def query(
    workspace_identity_digest: str = "workspace-a",
    count_limit: int = 20,
    byte_limit: int = 16384,
) -> MemorySelectionQueryV1:
    return MemorySelectionQueryV1(
        workspace_identity_digest=workspace_identity_digest,
        count_limit=count_limit,
        byte_limit=byte_limit,
    )


def test_query_limits_are_frozen_within_the_hard_caps() -> None:
    assert query().count_limit == 20
    assert query().byte_limit == 16384
    with pytest.raises(ValidationError):
        MemorySelectionQueryV1(workspace_identity_digest="workspace-a", count_limit=21)
    with pytest.raises(ValidationError):
        MemorySelectionQueryV1(
            workspace_identity_digest="workspace-a", byte_limit=16385
        )
    with pytest.raises(ValidationError):
        MemorySelectionQueryV1(workspace_identity_digest="workspace-a", count_limit=0)
    with pytest.raises(ValidationError):
        MemorySelectionQueryV1(workspace_identity_digest="workspace-a", byte_limit=0)


def test_selection_never_includes_foreign_or_cleared_entries() -> None:
    entries = (
        entry(entry_id="a-1", kind="RUN_SUMMARY"),
        entry(entry_id="b-1", workspace_identity="workspace-b"),
        entry(entry_id="a-2", kind="KNOWN_FAILURE", cleared=True),
    )
    # The repository list already excludes cleared rows; the pure function
    # defends the same boundary against any supplied sequence.
    selected = select_memory(query("workspace-b"), entries)
    assert [e.entry_id for e in selected.entries] == ["b-1"]
    selected_a = select_memory(query(), entries)
    assert [e.entry_id for e in selected_a.entries] == ["a-1"]


def test_selection_orders_by_frozen_priority_then_recency_then_id() -> None:
    entries = (
        entry(entry_id="sum-1", kind="RUN_SUMMARY"),
        entry(entry_id="fail-1", kind="KNOWN_FAILURE", updated_at=_NEWER_AT),
        entry(entry_id="conv-1", kind="PROJECT_CONVENTION"),
        entry(entry_id="dec-1", kind="USER_DECISION"),
        entry(entry_id="fail-2", kind="KNOWN_FAILURE"),
        entry(entry_id="fail-3", kind="KNOWN_FAILURE"),
    )
    selected = select_memory(query(), entries)
    # KNOWN_FAILURE rank 0 (newest first, then entry id), then the frozen
    # priority order for the remaining kinds.
    assert [e.entry_id for e in selected.entries] == [
        "fail-1",
        "fail-2",
        "fail-3",
        "conv-1",
        "dec-1",
        "sum-1",
    ]
    assert tuple(FROZEN_MEMORY_KIND_PRIORITY_V1) == (
        "KNOWN_FAILURE",
        "PROJECT_CONVENTION",
        "USER_DECISION",
        "RUN_SUMMARY",
    )


def test_selection_applies_count_and_byte_limits_deterministically() -> None:
    entries = tuple(
        entry(
            entry_id=f"fail-{index:02d}",
            kind="KNOWN_FAILURE",
            summary="f" * 2000,
        )
        for index in range(10)
    )
    count_bounded = select_memory(query(count_limit=3, byte_limit=16384), entries)
    assert [e.entry_id for e in count_bounded.entries] == [
        "fail-00",
        "fail-01",
        "fail-02",
    ]
    assert count_bounded.total_canonical_bytes == sum(
        canonical_memory_byte_count(e) for e in count_bounded.entries
    )
    byte_bounded = select_memory(query(count_limit=20, byte_limit=4000), entries)
    assert len(byte_bounded.entries) == 1
    assert byte_bounded.entries[0].entry_id == "fail-00"
    assert byte_bounded.total_canonical_bytes <= 4000
    # Multibyte UTF-8 counts canonical bytes, not characters: the six
    # characters of the summary contribute 18 bytes, so one full entry
    # (summary + stored source text) exceeds the 30-byte limit.
    multibyte = (
        entry(entry_id="mb-1", kind="RUN_SUMMARY", summary="中文符号三个"),
        entry(entry_id="mb-2", kind="RUN_SUMMARY", summary="中文符号三个"),
    )
    assert canonical_memory_byte_count(multibyte[0]) > 30
    mb_bounded = select_memory(query(byte_limit=100), multibyte)
    assert len(mb_bounded.entries) == 1
    assert mb_bounded.entries[0].entry_id == "mb-1"
    assert mb_bounded.total_canonical_bytes == canonical_memory_byte_count(multibyte[0])
    # Deterministic: identical inputs produce byte-identical outputs.
    assert (
        select_memory(query(), entries).model_dump_json()
        == select_memory(query(), entries).model_dump_json()
    )


def test_selection_retains_source_attribution() -> None:
    entries = (
        entry(entry_id="conv-1", kind="PROJECT_CONVENTION"),
        entry(entry_id="sum-1", kind="RUN_SUMMARY"),
    )
    selected = select_memory(query(), entries)
    assert {e.entry_id: e.source.kind for e in selected.entries} == {
        "conv-1": "USER_VISIBLE_TEXT",
        "sum-1": "RUN_SUMMARY",
    }
    assert selected.workspace_identity_digest == "workspace-a"


def test_selection_empty_results_are_deterministic() -> None:
    empty = select_memory(query(), ())
    assert empty.entries == ()
    assert empty.total_canonical_bytes == 0
    assert select_memory(query(), ()).model_dump_json() == empty.model_dump_json()
