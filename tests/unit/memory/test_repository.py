"""T22.1 legacy step 22.A: transactional create/confirm repository tests.

Pins the create/confirm happy paths and every zero-row rejection:
creator/kind matrix violations, source-variant mismatches, empty and
over-limit content, secret content, over-limit references, duplicate
entry ids, and the confirm authority/scope/replay/conflict contract
under the T07.3 idempotency ledger.  Selection, clearing, registry
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

from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.memory.entry import (
    KnownFailureSourceV1,
    MemorySourceV1,
    RunSummarySourceV1,
    UserDecisionSourceV1,
    UserVisibleTextSourceV1,
)
from vespercode.memory.repository import (
    ConfirmProjectConventionV1,
    CreateMemoryCommandV1,
    MemoryRepository,
)
from vespercode.storage.connection import (
    ControlDatabase,
    open_control_database,
)
from vespercode.storage.migration_engine import apply_migrations
from vespercode.storage.migrations.v0001_run_wait import RUN_WAIT_V1_MIGRATION
from vespercode.storage.migrations.v0002_idempotency import (
    IDEMPOTENCY_V1_MIGRATION,
)
from vespercode.storage.migrations.v0003_disclosure_grants import (
    DISCLOSURE_GRANTS_V1_MIGRATION,
)
from vespercode.storage.migrations.v0004_disclosure_authorizations import (
    DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
)
from vespercode.storage.migrations.v0005_memory import MEMORY_V1_MIGRATION

_CREATED_AT = CanonicalTimestampV1("2026-08-06T09:00:00.000Z")
_CONFIRMED_AT = CanonicalTimestampV1("2026-08-06T10:30:00.000Z")


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


def _source_for(kind: str) -> MemorySourceV1:
    if kind == "USER_DECISION":
        return UserDecisionSourceV1(
            kind="USER_DECISION", decision="APPROVE", reference="wait-1"
        )
    if kind == "RUN_SUMMARY":
        return RunSummarySourceV1(
            kind="RUN_SUMMARY", run_id="run-1", result="SUCCEEDED"
        )
    if kind == "KNOWN_FAILURE":
        return KnownFailureSourceV1(
            kind="KNOWN_FAILURE",
            check_result_digest="a" * 64,
            failure_fingerprint_digest="b" * 64,
        )
    return UserVisibleTextSourceV1(kind="USER_VISIBLE_TEXT", reference="conv-1")


def create_command(
    *,
    kind: str = "PROJECT_CONVENTION",
    creator: str = "USER",
    summary: str = "always run ruff before committing",
    source: MemorySourceV1 | None = None,
    workspace_identity: str = "workspace-a",
    entry_id: str = "mem-1",
    created_at: CanonicalTimestampV1 = _CREATED_AT,
) -> CreateMemoryCommandV1:
    return CreateMemoryCommandV1(
        workspace_identity=workspace_identity,
        kind=kind,  # type: ignore[arg-type]
        summary=summary,
        creator=creator,  # type: ignore[arg-type]
        source=source if source is not None else _source_for(kind),
        entry_id=entry_id,
        created_at=created_at,
    )


def confirm_command(
    *,
    entry_id: str = "mem-1",
    workspace_identity: str = "workspace-a",
    creator: str = "USER",
    event_id: str = "confirm-1",
    decided_at: CanonicalTimestampV1 = _CONFIRMED_AT,
) -> ConfirmProjectConventionV1:
    return ConfirmProjectConventionV1(
        workspace_identity=workspace_identity,
        entry_id=entry_id,
        creator=creator,  # type: ignore[arg-type]
        event_id=event_id,
        decided_at=decided_at,
    )


def test_create_persists_authorized_entry_in_exact_workspace(
    repository: MemoryRepository,
) -> None:
    result = repository.create(create_command())
    assert result.kind == "CREATED"
    assert result.error_code is None
    assert result.entry is not None
    assert result.entry.workspace_identity == "workspace-a"
    assert result.entry.kind == "PROJECT_CONVENTION"
    assert result.entry.creator == "USER"
    assert result.entry.created_at == _CREATED_AT
    assert result.entry.updated_at == _CREATED_AT
    # User-visible convention text is untrusted until the user confirms.
    assert result.entry.untrusted is True
    listed = repository.list("workspace-a")
    assert [entry.entry_id for entry in listed] == ["mem-1"]
    assert repository.list("workspace-b") == ()


def test_control_plane_kinds_are_trusted_structured_facts(
    repository: MemoryRepository,
) -> None:
    for index, (kind, source) in enumerate(
        (
            ("USER_DECISION", _source_for("USER_DECISION")),
            ("RUN_SUMMARY", _source_for("RUN_SUMMARY")),
            ("KNOWN_FAILURE", _source_for("KNOWN_FAILURE")),
        )
    ):
        result = repository.create(
            create_command(
                kind=kind,
                creator="CONTROL_PLANE",
                source=source,
                entry_id=f"mem-control-{index}",
            )
        )
        assert result.kind == "CREATED"
        assert result.entry is not None
        assert result.entry.untrusted is False
        assert result.entry.source.kind == source.kind


def test_create_duplicate_entry_id_fails_closed(
    repository: MemoryRepository,
) -> None:
    assert repository.create(create_command()).kind == "CREATED"
    duplicate = repository.create(create_command(entry_id="mem-1", summary="other"))
    assert duplicate.error_code == "MEMORY_STORE_FAILED"
    rows = repository.database.read_rows(
        "SELECT summary FROM memory_entries WHERE entry_id = 'mem-1'"
    )
    assert len(rows) == 1
    assert str(rows[0][0]) == "always run ruff before committing"


def test_create_rejects_empty_and_over_limit_content_with_zero_rows(
    repository: MemoryRepository,
) -> None:
    empty = repository.create(create_command(summary=""))
    assert empty.error_code == "MEMORY_CONTENT_REJECTED"
    over = repository.create(create_command(summary="x" * 2049))
    assert over.error_code == "MEMORY_CONTENT_REJECTED"
    long_reference = repository.create(
        create_command(
            source=UserVisibleTextSourceV1(
                kind="USER_VISIBLE_TEXT", reference="r" * 257
            )
        )
    )
    assert long_reference.error_code == "MEMORY_CONTENT_REJECTED"
    empty_reference = repository.create(
        create_command(
            source=UserVisibleTextSourceV1(kind="USER_VISIBLE_TEXT", reference="")
        )
    )
    assert empty_reference.error_code == "MEMORY_CONTENT_REJECTED"
    assert repository.entry_count() == 0


def test_create_rejects_secret_content_with_zero_rows(
    repository: MemoryRepository,
) -> None:
    api_key = repository.create(
        create_command(summary="rotate the " + "API_KEY" + "=" + "sk-test-secret-value")
    )
    assert api_key.error_code == "MEMORY_CONTENT_REJECTED"
    token = repository.create(
        create_command(summary="use " + "SECRET_KEY" + "=" + "value-1")
    )
    assert token.error_code == "MEMORY_CONTENT_REJECTED"
    private_key = repository.create(
        create_command(summary="-----BEGIN " + "RSA PRIVATE KEY-----" + "\nbody")
    )
    assert private_key.error_code == "MEMORY_CONTENT_REJECTED"
    url = repository.create(
        create_command(summary="mirror at https://user:" + "pass@example.com" + "/repo")
    )
    assert url.error_code == "MEMORY_CONTENT_REJECTED"
    # A prefixed env-var spelling is a secret value too (the boundary rule
    # allows the underscore prefix).
    prefixed = repository.create(
        create_command(summary="set " + "OPENAI_API_KEY" + "=sk-prefixed-secret")
    )
    assert prefixed.error_code == "MEMORY_CONTENT_REJECTED"
    prefixed_token = repository.create(
        create_command(summary="set " + "AWS_ACCESS_TOKEN" + "=aws-token")
    )
    assert prefixed_token.error_code == "MEMORY_CONTENT_REJECTED"
    # A YAML/TOML-style spaced assignment is a secret value too.
    spaced = repository.create(
        create_command(summary="set " + "API_KEY" + " = sk-spaced-secret")
    )
    assert spaced.error_code == "MEMORY_CONTENT_REJECTED"
    # A secret smuggled in the source reference is rejected too.
    source_secret = repository.create(
        create_command(
            source=UserVisibleTextSourceV1(
                kind="USER_VISIBLE_TEXT", reference="see " + "AUTH_TOKEN" + "=t-1"
            )
        )
    )
    assert source_secret.error_code == "MEMORY_CONTENT_REJECTED"
    assert repository.entry_count() == 0


def test_confirm_marks_user_endorsed_convention(
    repository: MemoryRepository,
) -> None:
    assert repository.create(create_command()).kind == "CREATED"
    result = repository.confirm(confirm_command())
    assert result.kind == "CONFIRMED"
    assert result.error_code is None
    assert result.entry is not None
    assert result.entry.untrusted is False
    assert result.entry.updated_at == _CONFIRMED_AT
    listed = repository.list("workspace-a")
    assert len(listed) == 1
    assert listed[0].untrusted is False
    assert listed[0].updated_at == _CONFIRMED_AT


def test_confirm_replay_is_free_even_after_a_later_clear(
    repository: MemoryRepository,
) -> None:
    assert repository.create(create_command()).kind == "CREATED"
    assert repository.confirm(confirm_command()).kind == "CONFIRMED"
    # A later clear excludes the entry, but an exact replay of the
    # recorded confirmation event still replays the recorded outcome.
    with repository.database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE memory_entries SET cleared_at = ?, clear_transaction_id = ?"
            " WHERE entry_id = 'mem-1'",
            (_CONFIRMED_AT.value, "clear-1"),
        )
    replay = repository.confirm(confirm_command())
    assert replay.kind == "REPLAY"
    # A NEW confirmation event for the cleared entry is rejected and
    # leaves no ledger record behind.
    new_event = repository.confirm(confirm_command(event_id="confirm-2"))
    assert new_event.error_code == "MEMORY_SCOPE_VIOLATION"
    assert (
        len(
            repository.database.read_rows(
                "SELECT 1 FROM idempotency_events WHERE event_id = 'confirm-2'"
            )
        )
        == 0
    )


def test_create_rejects_non_canonical_surrogate_content_with_zero_rows(
    repository: MemoryRepository,
) -> None:
    surrogate_summary = repository.create(create_command(summary="\ud800"))
    assert surrogate_summary.error_code == "MEMORY_CONTENT_REJECTED"
    surrogate_reference = repository.create(
        create_command(
            source=UserVisibleTextSourceV1(
                kind="USER_VISIBLE_TEXT", reference="ref-\udfff"
            )
        )
    )
    assert surrogate_reference.error_code == "MEMORY_CONTENT_REJECTED"
    assert repository.entry_count() == 0


def test_confirm_replay_and_conflict_are_mutation_free(
    repository: MemoryRepository,
) -> None:
    assert repository.create(create_command()).kind == "CREATED"
    assert repository.confirm(confirm_command()).kind == "CONFIRMED"
    replay = repository.confirm(confirm_command())
    assert replay.kind == "REPLAY"
    assert replay.entry is not None
    assert replay.entry.updated_at == _CONFIRMED_AT
    # The same event id for a different entry is a conflict with zero rows.
    assert repository.create(create_command(entry_id="mem-2")).kind == "CREATED"
    conflict = repository.confirm(
        confirm_command(entry_id="mem-2", event_id="confirm-1")
    )
    assert conflict.kind == "EVENT_ID_REUSE_CONFLICT"
    rows = repository.database.read_rows(
        "SELECT untrusted FROM memory_entries WHERE entry_id = 'mem-2'"
    )
    assert int(rows[0][0]) == 1


def test_confirm_rejects_wrong_authority_and_scope(
    repository: MemoryRepository,
) -> None:
    assert repository.create(create_command()).kind == "CREATED"
    model = repository.confirm(confirm_command(creator="MODEL"))
    assert model.error_code == "MEMORY_CREATOR_FORBIDDEN"
    unknown = repository.confirm(confirm_command(entry_id="no-such-entry"))
    assert unknown.error_code == "MEMORY_SCOPE_VIOLATION"
    # An entry belonging to another workspace cannot be confirmed here.
    assert (
        repository.create(
            create_command(workspace_identity="workspace-b", entry_id="mem-b")
        ).kind
        == "CREATED"
    )
    cross = repository.confirm(
        confirm_command(entry_id="mem-b", workspace_identity="workspace-a")
    )
    assert cross.error_code == "MEMORY_SCOPE_VIOLATION"
    # Confirm authorizes only project conventions.
    assert (
        repository.create(
            create_command(
                kind="RUN_SUMMARY",
                creator="CONTROL_PLANE",
                source=_source_for("RUN_SUMMARY"),
                entry_id="mem-run",
            )
        ).kind
        == "CREATED"
    )
    not_convention = repository.confirm(confirm_command(entry_id="mem-run"))
    assert not_convention.error_code == "MEMORY_WRITE_NOT_AUTHORIZED"
    # A cleared convention can no longer be confirmed.
    with repository.database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE memory_entries SET cleared_at = ?, clear_transaction_id = ?"
            " WHERE entry_id = 'mem-1'",
            (_CONFIRMED_AT.value, "clear-1"),
        )
    cleared = repository.confirm(confirm_command())
    assert cleared.error_code == "MEMORY_SCOPE_VIOLATION"


def test_list_is_stable_creation_order_and_excludes_cleared(
    repository: MemoryRepository,
) -> None:
    assert repository.create(create_command(entry_id="mem-2")).kind == "CREATED"
    assert (
        repository.create(create_command(entry_id="mem-1", summary="first")).kind
        == "CREATED"
    )
    assert (
        repository.create(create_command(entry_id="mem-0", summary="zeroth")).kind
        == "CREATED"
    )
    assert [entry.entry_id for entry in repository.list("workspace-a")] == [
        "mem-0",
        "mem-1",
        "mem-2",
    ]
    with repository.database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE memory_entries SET cleared_at = ?, clear_transaction_id = ?"
            " WHERE entry_id = 'mem-1'",
            (_CONFIRMED_AT.value, "clear-1"),
        )
    assert [entry.entry_id for entry in repository.list("workspace-a")] == [
        "mem-0",
        "mem-2",
    ]
