"""T22.1 legacy step 22.B: exact-workspace list/selection boundary tests.

Pins the exact RED (``repository.list("workspace-b")`` is empty) and the
full selection matrix: exact workspace matching with no fallback to
neighboring workspaces, frozen kind priority, recency, stable entry-id
tie-breaks, count and canonical byte limits, cleared-entry exclusion,
and retained source attribution.  Memory creation/confirmation/clearing
and current Snapshot/check overrides remain out of scope (GREEN-4).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

# The repository consumes pydantic runtime contracts; the hash-locked
# gate toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.memory.entry import (
    KnownFailureSourceV1,
    MemoryKindV1,
    MemorySourceV1,
    RunSummarySourceV1,
    UserDecisionSourceV1,
    UserVisibleTextSourceV1,
    serialize_source,
)
from src.vespercode.memory.repository import (
    CreateMemoryCommandV1,
    MemoryRepository,
)
from src.vespercode.memory.selection import (
    FROZEN_MEMORY_KIND_PRIORITY_V1,
    MemorySelectionQueryV1,
    MemorySelectorV1,
    select_memory,
)
from src.vespercode.storage.connection import (
    ControlDatabase,
    open_control_database,
)
from src.vespercode.storage.migration_engine import apply_migrations
from src.vespercode.storage.migrations.v0001_run_wait import RUN_WAIT_V1_MIGRATION
from src.vespercode.storage.migrations.v0002_idempotency import (
    IDEMPOTENCY_V1_MIGRATION,
)
from src.vespercode.storage.migrations.v0003_disclosure_grants import (
    DISCLOSURE_GRANTS_V1_MIGRATION,
)
from src.vespercode.storage.migrations.v0004_disclosure_authorizations import (
    DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
)
from src.vespercode.storage.migrations.v0005_memory import MEMORY_V1_MIGRATION

_CREATED_AT = CanonicalTimestampV1("2026-08-06T09:00:00.000Z")
_OTHER_AT = CanonicalTimestampV1("2026-08-06T10:00:00.000Z")


def _source_for(kind: MemoryKindV1) -> MemorySourceV1:
    """One matching bounded source variant per kind (helper duplication is
    deliberate: the card's exact Files list forbids a shared helper module)."""
    if kind == "PROJECT_CONVENTION":
        return UserVisibleTextSourceV1(kind="USER_VISIBLE_TEXT", reference="conv-1")
    if kind == "USER_DECISION":
        return UserDecisionSourceV1(
            kind="USER_DECISION", decision="APPROVE", reference="wait-1"
        )
    if kind == "RUN_SUMMARY":
        return RunSummarySourceV1(
            kind="RUN_SUMMARY", run_id="run-1", result="SUCCEEDED"
        )
    return KnownFailureSourceV1(
        kind="KNOWN_FAILURE",
        check_result_digest="a" * 64,
        failure_fingerprint_digest="b" * 64,
    )


def _insert(
    repository: MemoryRepository,
    workspace: str,
    kind: MemoryKindV1,
    summary: str,
    entry_id: str,
    created_at: CanonicalTimestampV1,
) -> None:
    created = repository.create(
        CreateMemoryCommandV1(
            workspace_identity=workspace,
            kind=kind,
            summary=summary,
            creator="USER" if kind == "PROJECT_CONVENTION" else "CONTROL_PLANE",
            source=_source_for(kind),
            entry_id=entry_id,
            created_at=created_at,
        )
    )
    assert created.kind == "CREATED"


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "memory.db")
    apply_migrations(
        database,
        (
            RUN_WAIT_V1_MIGRATION,
            IDEMPOTENCY_V1_MIGRATION,
            DISCLOSURE_GRANTS_V1_MIGRATION,
            DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
            MEMORY_V1_MIGRATION,
        ),
    )
    yield database
    database.close()


@pytest.fixture
def repository(control_database: ControlDatabase) -> MemoryRepository:
    repository = MemoryRepository(control_database)
    # Workspace-a owns one entry of every kind; workspace-b stays empty.
    fixture_kinds: tuple[MemoryKindV1, ...] = (
        "PROJECT_CONVENTION",
        "USER_DECISION",
    )
    for index, kind in enumerate(fixture_kinds):
        _insert(
            repository,
            "workspace-a",
            kind,
            f"entry {index}",
            f"mem-{index}",
            _CREATED_AT,
        )
    return repository


def test_selection_never_crosses_workspace_identity(
    repository: MemoryRepository,
) -> None:
    assert repository.list("workspace-b") == ()


def test_memory_selection_matrix(
    repository: MemoryRepository,
    control_database: ControlDatabase,
) -> None:
    """Expected (22.B): exact workspace/count/byte/priority/recency order."""
    # Exact workspace matching: workspace-b has no entries and the
    # selector over workspace-b never sees workspace-a entries.
    query_b = MemorySelectionQueryV1(workspace_identity_digest="workspace-b")
    assert MemorySelectorV1(repository).select(query_b).entries == ()
    assert select_memory(query_b, repository.list("workspace-a")).entries == ()

    # Workspace-a entries are eligible, carry their source, and repeated
    # selection is byte-identical (deterministic).
    query_a = MemorySelectionQueryV1(workspace_identity_digest="workspace-a")
    first = MemorySelectorV1(repository).select(query_a)
    second = MemorySelectorV1(repository).select(query_a)
    assert [entry.entry_id for entry in first.entries] == ["mem-0", "mem-1"]
    assert all(
        entry.source.kind in ("USER_VISIBLE_TEXT", "USER_DECISION")
        for entry in first.entries
    )
    assert first.model_dump_json() == second.model_dump_json()
    assert first.total_canonical_bytes == sum(
        len(entry.summary.encode("utf-8"))
        + len(serialize_source(entry.source).encode("utf-8"))
        for entry in first.entries
    )

    # Frozen kind priority: with identical recency, kinds order by the
    # frozen priority constant.
    assert tuple(FROZEN_MEMORY_KIND_PRIORITY_V1) == (
        "KNOWN_FAILURE",
        "PROJECT_CONVENTION",
        "USER_DECISION",
        "RUN_SUMMARY",
    )
    fresh = MemoryRepository(control_database)
    for rank, kind in enumerate(FROZEN_MEMORY_KIND_PRIORITY_V1):
        _insert(
            fresh,
            "workspace-priority",
            kind,
            f"priority {rank}",
            f"prio-{kind}",
            _OTHER_AT,
        )
    priority = MemorySelectorV1(fresh).select(
        MemorySelectionQueryV1(workspace_identity_digest="workspace-priority")
    )
    assert [entry.kind for entry in priority.entries] == list(
        FROZEN_MEMORY_KIND_PRIORITY_V1
    )

    # Recency: same kind, newer updated_at selected first.
    recency_repository = MemoryRepository(control_database)
    for index, at in enumerate((_CREATED_AT, _OTHER_AT)):
        _insert(
            recency_repository,
            "workspace-recency",
            "KNOWN_FAILURE",
            f"failure {index}",
            f"fail-{index}",
            at,
        )
    recency = MemorySelectorV1(recency_repository).select(
        MemorySelectionQueryV1(workspace_identity_digest="workspace-recency")
    )
    assert [entry.entry_id for entry in recency.entries] == ["fail-1", "fail-0"]

    # Stable tie-break: identical kind/recency orders by entry_id.
    tie_repository = MemoryRepository(control_database)
    for index in (2, 0, 1):
        _insert(
            tie_repository,
            "workspace-tie",
            "RUN_SUMMARY",
            f"summary {index}",
            f"tie-{index}",
            _CREATED_AT,
        )
    tie = MemorySelectorV1(tie_repository).select(
        MemorySelectionQueryV1(workspace_identity_digest="workspace-tie")
    )
    assert [entry.entry_id for entry in tie.entries] == ["tie-0", "tie-1", "tie-2"]

    # Count limit: at most 20 entries are ever selected.
    count_repository = MemoryRepository(control_database)
    for index in range(25):
        _insert(
            count_repository,
            "workspace-count",
            "RUN_SUMMARY",
            "s",
            f"count-{index:02d}",
            _CREATED_AT,
        )
    count = MemorySelectorV1(count_repository).select(
        MemorySelectionQueryV1(workspace_identity_digest="workspace-count")
    )
    assert len(count.entries) == 20

    # Canonical byte limit: greedy sorted inclusion stops before the next
    # entry would exceed the query's frozen byte budget.
    byte_repository = MemoryRepository(control_database)
    for index in range(10):
        _insert(
            byte_repository,
            "workspace-bytes",
            "KNOWN_FAILURE",
            "b" * 2000,
            f"bytes-{index:02d}",
            _CREATED_AT,
        )
    byte_query = MemorySelectionQueryV1(
        workspace_identity_digest="workspace-bytes", byte_limit=4000
    )
    byte_selection = MemorySelectorV1(byte_repository).select(byte_query)
    assert byte_selection.total_canonical_bytes <= 4000
    assert len(byte_selection.entries) == 1
    assert byte_selection.entries[0].entry_id == "bytes-00"

    # Cleared entries are excluded from future selection.
    clear_repository = MemoryRepository(control_database)
    for index in (0, 1):
        _insert(
            clear_repository,
            "workspace-cleared",
            "PROJECT_CONVENTION",
            f"convention {index}",
            f"conv-{index}",
            _CREATED_AT,
        )
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE memory_entries SET cleared_at = ?, clear_transaction_id = ?"
            " WHERE entry_id = 'conv-0'",
            (_OTHER_AT.value, "clear-1"),
        )
    cleared = MemorySelectorV1(clear_repository).select(
        MemorySelectionQueryV1(workspace_identity_digest="workspace-cleared")
    )
    assert [entry.entry_id for entry in cleared.entries] == ["conv-1"]
