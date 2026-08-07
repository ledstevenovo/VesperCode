"""T22.1 legacy step 22.A: bounded structured memory entry vocabulary tests.

Pins the closed kind/creator/source unions, the bounded immutable
``MemoryEntryV1`` value (workspace identity, kind, summary, creator,
source, timestamps, untrusted marker, clear tombstone fields; no secret,
permission, or full-body field), the canonical storage round-trip of
sources, the deterministic canonical byte accounting, and the closed
mutation result/error vocabulary.
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
    MemoryMutationResultV1,
    RunSummarySourceV1,
    UserDecisionSourceV1,
    UserVisibleTextSourceV1,
    canonical_memory_byte_count,
    parse_source,
    serialize_source,
)

_CREATED_AT = CanonicalTimestampV1("2026-08-06T09:00:00.000Z")
_UPDATED_AT = CanonicalTimestampV1("2026-08-06T10:00:00.000Z")


def user_text_entry(
    *,
    entry_id: str = "mem-1",
    summary: str = "always run ruff before committing",
) -> MemoryEntryV1:
    return MemoryEntryV1(
        entry_id=entry_id,
        workspace_identity="workspace-a",
        kind="PROJECT_CONVENTION",
        summary=summary,
        creator="USER",
        source=UserVisibleTextSourceV1(kind="USER_VISIBLE_TEXT", reference="conv-1"),
        created_at=_CREATED_AT,
        updated_at=_UPDATED_AT,
        untrusted=True,
    )


def test_kind_creator_and_source_unions_are_closed() -> None:
    # Kind/creator accept only the exact SPEC 4.7 vocabulary.
    with pytest.raises(ValidationError):
        MemoryEntryV1(
            entry_id="mem-bad-kind",
            workspace_identity="workspace-a",
            kind="MODEL_OUTPUT",  # type: ignore[arg-type]
            summary="s",
            creator="USER",
            source=UserVisibleTextSourceV1(
                kind="USER_VISIBLE_TEXT", reference="conv-1"
            ),
            created_at=_CREATED_AT,
            updated_at=_UPDATED_AT,
            untrusted=True,
        )
    with pytest.raises(ValidationError):
        MemoryEntryV1(
            entry_id="mem-bad-creator",
            workspace_identity="workspace-a",
            kind="PROJECT_CONVENTION",
            summary="s",
            creator="AGENT",  # type: ignore[arg-type]
            source=UserVisibleTextSourceV1(
                kind="USER_VISIBLE_TEXT", reference="conv-1"
            ),
            created_at=_CREATED_AT,
            updated_at=_UPDATED_AT,
            untrusted=True,
        )
    # The source union is a discriminated union on kind; an unknown kind
    # and missing variant fields are rejected.
    with pytest.raises(ValidationError):
        UserVisibleTextSourceV1(  # type: ignore[call-arg]
            kind="CHAT_LOG"  # type: ignore[arg-type]
        )
    with pytest.raises(ValidationError):
        UserVisibleTextSourceV1(kind="USER_VISIBLE_TEXT")  # type: ignore[call-arg]
    # Every variant's structured facts are required.
    with pytest.raises(ValidationError):
        RunSummarySourceV1(kind="RUN_SUMMARY", run_id="run-1")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        KnownFailureSourceV1(  # type: ignore[call-arg]
            kind="KNOWN_FAILURE", check_result_digest="a" * 64
        )


def test_entry_fields_are_bounded_and_unknown_fields_rejected() -> None:
    # No secret/permission/full-body field exists on the entry value.
    with pytest.raises(ValidationError):
        MemoryEntryV1(
            entry_id="mem-secret-field",
            workspace_identity="workspace-a",
            kind="PROJECT_CONVENTION",
            summary="s",
            creator="USER",
            source=UserVisibleTextSourceV1(
                kind="USER_VISIBLE_TEXT", reference="conv-1"
            ),
            created_at=_CREATED_AT,
            updated_at=_UPDATED_AT,
            untrusted=True,
            secret="sk-value",  # type: ignore[call-arg]
        )
    # The summary is bounded to the 2048-character contract bound.
    with pytest.raises(ValidationError):
        MemoryEntryV1(
            entry_id="mem-over",
            workspace_identity="workspace-a",
            kind="PROJECT_CONVENTION",
            summary="x" * 2049,
            creator="USER",
            source=UserVisibleTextSourceV1(
                kind="USER_VISIBLE_TEXT", reference="conv-1"
            ),
            created_at=_CREATED_AT,
            updated_at=_UPDATED_AT,
            untrusted=True,
        )
    # Timestamps: updated_at must not precede created_at.
    with pytest.raises(ValidationError):
        MemoryEntryV1(
            entry_id="mem-time",
            workspace_identity="workspace-a",
            kind="PROJECT_CONVENTION",
            summary="s",
            creator="USER",
            source=UserVisibleTextSourceV1(
                kind="USER_VISIBLE_TEXT", reference="conv-1"
            ),
            created_at=_UPDATED_AT,
            updated_at=_CREATED_AT,
            untrusted=True,
        )
    # Clear tombstone fields are present and nullable.
    cleared = MemoryEntryV1(
        entry_id="mem-cleared",
        workspace_identity="workspace-a",
        kind="KNOWN_FAILURE",
        summary="stable failure",
        creator="CONTROL_PLANE",
        source=KnownFailureSourceV1(
            kind="KNOWN_FAILURE",
            check_result_digest="a" * 64,
            failure_fingerprint_digest="b" * 64,
        ),
        created_at=_CREATED_AT,
        updated_at=_CREATED_AT,
        untrusted=False,
        cleared_at=_UPDATED_AT,
        clear_transaction_id="clear-1",
    )
    assert cleared.cleared_at == _UPDATED_AT
    assert cleared.clear_transaction_id == "clear-1"
    entry = user_text_entry()
    assert entry.cleared_at is None
    assert entry.clear_transaction_id is None
    assert entry.untrusted is True


def test_source_storage_round_trip_and_canonical_bytes() -> None:
    sources = (
        UserVisibleTextSourceV1(kind="USER_VISIBLE_TEXT", reference="conv-1"),
        UserDecisionSourceV1(
            kind="USER_DECISION", decision="REJECT", reference="wait-9"
        ),
        RunSummarySourceV1(kind="RUN_SUMMARY", run_id="run-1", result="SUCCEEDED"),
        KnownFailureSourceV1(
            kind="KNOWN_FAILURE",
            check_result_digest="a" * 64,
            failure_fingerprint_digest="b" * 64,
        ),
    )
    for source in sources:
        text = serialize_source(source)
        assert parse_source(text).kind == source.kind
        assert parse_source(text).model_dump_json() == source.model_dump_json()

    # Structurally incomplete stored text fails closed as ValueError
    # (never a raw KeyError).
    with pytest.raises(ValueError):
        parse_source('{"kind": "USER_VISIBLE_TEXT"}')
    with pytest.raises(ValueError):
        parse_source('{"kind": "RUN_SUMMARY", "run_id": "run-1"}')

    # Canonical byte accounting is the strict UTF-8 content bytes
    # (summary + stored source text), deterministic per entry.
    ascii_entry = user_text_entry()
    multibyte = MemoryEntryV1(
        entry_id="mem-utf8",
        workspace_identity="workspace-a",
        kind="PROJECT_CONVENTION",
        summary="中文符号三个",
        creator="USER",
        source=UserVisibleTextSourceV1(kind="USER_VISIBLE_TEXT", reference="conv-1"),
        created_at=_CREATED_AT,
        updated_at=_UPDATED_AT,
        untrusted=True,
    )
    assert canonical_memory_byte_count(ascii_entry) == len(
        ascii_entry.summary.encode("utf-8")
    ) + len(serialize_source(ascii_entry.source).encode("utf-8"))
    assert canonical_memory_byte_count(multibyte) == len(
        multibyte.summary.encode("utf-8")
    ) + len(serialize_source(multibyte.source).encode("utf-8"))
    assert canonical_memory_byte_count(ascii_entry) == canonical_memory_byte_count(
        user_text_entry()
    )


def test_mutation_result_vocabulary_is_closed() -> None:
    created = MemoryMutationResultV1(
        kind="CREATED", message="memory entry created", entry=user_text_entry()
    )
    assert created.error_code is None
    assert created.entry is not None
    rejected = MemoryMutationResultV1(
        kind="REJECTED",
        message="creator is not authorized for this memory kind",
        error_code="MEMORY_CREATOR_FORBIDDEN",
    )
    assert rejected.error_code == "MEMORY_CREATOR_FORBIDDEN"
    with pytest.raises(ValidationError):
        MemoryMutationResultV1.model_validate(
            {"kind": "SOMETIMES", "message": "unknown"}
        )
    with pytest.raises(ValidationError):
        MemoryMutationResultV1.model_validate(
            {"kind": "CREATED", "message": "x", "error_code": "MEMORY_UNDEFINED"}
        )
