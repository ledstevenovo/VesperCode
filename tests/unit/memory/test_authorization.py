"""T22.1 legacy step 22.A: authorized memory creator/source matrix tests.

Pins the exact RED (a model-originated project convention is rejected
with ``MEMORY_CREATOR_FORBIDDEN``), the full SPEC 4.7 creator/kind
matrix (project conventions are created only by the user, control-plane
kinds only by the control plane, model-originated writes are always
forbidden), the source-variant/kind matching, and the bounded-content
rejections (empty/over-limit summaries, secret content, over-limit
references) with zero persisted rows.  Selection, clearing, registry
edits, audit, and governance authority remain out of scope (GREEN-4).
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
    MemoryCreatorV1,
    MemoryKindV1,
    MemorySourceV1,
    UserDecisionSourceV1,
    UserVisibleTextSourceV1,
)
from src.vespercode.memory.repository import (
    CreateMemoryCommandV1,
    MemoryRepository,
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
    return MemoryRepository(control_database)


def user_text_source(reference: str = "conv-1") -> UserVisibleTextSourceV1:
    return UserVisibleTextSourceV1(kind="USER_VISIBLE_TEXT", reference=reference)


def user_decision_source() -> UserDecisionSourceV1:
    return UserDecisionSourceV1(
        kind="USER_DECISION", decision="APPROVE", reference="wait-1"
    )


def _source_for(kind: MemoryKindV1) -> MemorySourceV1:
    """One matching bounded source variant per kind (helper duplication is
    deliberate: the card's exact Files list forbids a shared helper module)."""
    if kind == "PROJECT_CONVENTION":
        return UserVisibleTextSourceV1(kind="USER_VISIBLE_TEXT", reference="conv-1")
    if kind == "USER_DECISION":
        return UserDecisionSourceV1(
            kind="USER_DECISION", decision="APPROVE", reference="wait-1"
        )
    from src.vespercode.memory.entry import (
        KnownFailureSourceV1,
        RunSummarySourceV1,
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


def create_command(
    *,
    kind: MemoryKindV1 = "PROJECT_CONVENTION",
    creator: MemoryCreatorV1 = "USER",
    source: MemorySourceV1 | None = None,
    summary: str = "always run ruff before committing",
    workspace_identity: str = "workspace-a",
    entry_id: str = "mem-1",
) -> CreateMemoryCommandV1:
    return CreateMemoryCommandV1(
        workspace_identity=workspace_identity,
        kind=kind,
        summary=summary,
        creator=creator,
        source=source if source is not None else _source_for(kind),
        entry_id=entry_id,
        created_at=_CREATED_AT,
    )


def model_project_convention_command() -> CreateMemoryCommandV1:
    return create_command(kind="PROJECT_CONVENTION", creator="MODEL")


def test_model_originated_project_convention_is_rejected(
    repository: MemoryRepository,
) -> None:
    result = repository.create(model_project_convention_command())
    assert result.error_code == "MEMORY_CREATOR_FORBIDDEN"


def test_memory_authorization_matrix(repository: MemoryRepository) -> None:
    """SPEC 4.7: only the sole authorized creator may write each kind."""
    cases: tuple[tuple[MemoryKindV1, MemoryCreatorV1, str], ...] = (
        ("PROJECT_CONVENTION", "USER", "CREATED"),
        ("PROJECT_CONVENTION", "CONTROL_PLANE", "MEMORY_CREATOR_FORBIDDEN"),
        ("PROJECT_CONVENTION", "MODEL", "MEMORY_CREATOR_FORBIDDEN"),
        ("USER_DECISION", "CONTROL_PLANE", "CREATED"),
        ("USER_DECISION", "USER", "MEMORY_CREATOR_FORBIDDEN"),
        ("USER_DECISION", "MODEL", "MEMORY_CREATOR_FORBIDDEN"),
        ("RUN_SUMMARY", "CONTROL_PLANE", "CREATED"),
        ("RUN_SUMMARY", "USER", "MEMORY_CREATOR_FORBIDDEN"),
        ("RUN_SUMMARY", "MODEL", "MEMORY_CREATOR_FORBIDDEN"),
        ("KNOWN_FAILURE", "CONTROL_PLANE", "CREATED"),
        ("KNOWN_FAILURE", "USER", "MEMORY_CREATOR_FORBIDDEN"),
        ("KNOWN_FAILURE", "MODEL", "MEMORY_CREATOR_FORBIDDEN"),
    )
    for kind, creator, expected in cases:
        result = repository.create(
            create_command(
                kind=kind,
                creator=creator,
                entry_id=f"mem-{kind}-{creator}",
                summary="bounded summary",
            )
        )
        if result.error_code is None:
            assert result.kind == expected, (kind, creator)
        else:
            assert result.error_code == expected, (kind, creator)
    # Only the four authorized combinations persisted, all in the exact
    # workspace identity carried by the command.
    assert repository.entry_count() == 4
    assert all(
        entry.workspace_identity == "workspace-a"
        for entry in repository.list("workspace-a")
    )
    assert repository.list("workspace-b") == ()

    # Source-variant/kind mismatches and bounded-content violations are
    # rejected with zero rows (SPEC 4.7 "内容来源" mapping).
    mismatched = repository.create(
        create_command(
            kind="PROJECT_CONVENTION",
            creator="USER",
            source=user_decision_source(),
            entry_id="mem-mismatch",
        )
    )
    assert mismatched.error_code == "MEMORY_CONTENT_REJECTED"
    secret = repository.create(
        create_command(
            summary="rotate the " + "API_KEY" + "=" + "sk-test-secret-value",
            entry_id="mem-secret",
        )
    )
    assert secret.error_code == "MEMORY_CONTENT_REJECTED"
    over_limit = repository.create(
        create_command(summary="x" * 2049, entry_id="mem-over")
    )
    assert over_limit.error_code == "MEMORY_CONTENT_REJECTED"
    empty = repository.create(create_command(summary="", entry_id="mem-empty"))
    assert empty.error_code == "MEMORY_CONTENT_REJECTED"
    assert repository.entry_count() == 4
