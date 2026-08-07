"""T26.1 legacy step 26.A: immutable v0011 transaction repository tests.

Covers the transaction repository contracts beyond the shared matrix:
PREPARED-only creation with a unique id, the unique active workspace
transaction across every non-terminal state (and the terminal release),
the closed transition table including recovery terminals, read-only
recovery-gate queries, concurrent creation with exactly one winner, and
the path-repository edge cases (missing transaction, empty listing,
frozen records after the PREPARED state).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("pydantic")

from typing import Literal

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.persistence.path_record import (
    DuplicatePersistencePath,
    PersistencePathRecordV1,
)
from vespercode.persistence.transaction import (
    PersistencePathRecordRepositoryV1,
    PersistenceTransactionRepositoryV1,
    PersistenceTransactionV1,
    TransactionTransitionErrorV1,
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
from vespercode.storage.migrations.v0006_audit import AUDIT_V1_MIGRATION
from vespercode.storage.migrations.v0007_agent_turns import (
    AGENT_TURNS_V1_MIGRATION,
)
from vespercode.storage.migrations.v0008_feedback import FEEDBACK_V1_MIGRATION
from vespercode.storage.migrations.v0009_actions import ACTIONS_V1_MIGRATION
from vespercode.storage.migrations.v0010_writeback_approvals import (
    WRITEBACK_APPROVALS_V1_MIGRATION,
)
from vespercode.storage.migrations.v0011_persistence import (
    PERSISTENCE_V1_MIGRATION,
)

_PREFIX_MIGRATIONS = (
    RUN_WAIT_V1_MIGRATION,
    IDEMPOTENCY_V1_MIGRATION,
    DISCLOSURE_GRANTS_V1_MIGRATION,
    DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
    MEMORY_V1_MIGRATION,
    AUDIT_V1_MIGRATION,
    AGENT_TURNS_V1_MIGRATION,
    FEEDBACK_V1_MIGRATION,
    ACTIONS_V1_MIGRATION,
    WRITEBACK_APPROVALS_V1_MIGRATION,
)

_POSTIMAGE_DIGEST = "22" * 32
_POLICY_DIGEST = "33" * 32
_WORKSPACE_DIGEST = "55" * 32
_OTHER_WORKSPACE_DIGEST = "77" * 32
_FINAL_DIFF_DIGEST = "66" * 32
_DEADLINE = "2026-08-05T09:15:00.000Z"
_PREPARED_AT = "2026-08-05T09:00:00.000Z"
_UPDATED_AT = CanonicalTimestampV1.parse(_PREPARED_AT)


def _seed_approval_chain(control_database: ControlDatabase) -> None:
    """Seed the exact run/wait/subject/approval rows the FK chain needs."""
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots (config_snapshot_id, digest,"
            " llm_profile_id, reference_profile_id, policy_id, target_test_ids,"
            " limits_digest, frozen_at) VALUES ('snap-1', ?, 'mock-deterministic-v1',"
            " 'python-src-py312-v1', 'PYTHON_SRC_ONLY_V1', '[]', ?,"
            " '2026-08-05T09:00:00.000Z')",
            ("a" * 64, "b" * 64),
        )
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES ('run-1', 'ws-1', 'snap-1', 'WAITING_USER', NULL, 1,"
            " '2026-08-05T09:00:00.000Z', '2026-08-05T09:15:00.000Z')"
        )
        tx.execute(
            "INSERT INTO wait_contexts (wait_id, run_id, wait_kind,"
            " source_phase, subject_digest, created_at, expires_at, status)"
            " VALUES ('wait-1', 'run-1', 'FINAL_WRITEBACK',"
            " 'FORMAL_VALIDATION', 'c' * 64, '2026-08-05T09:00:00.000Z',"
            " '2026-08-05T09:05:00.000Z', 'PENDING')"
        )
        tx.execute(
            "INSERT INTO writeback_approval_subjects (subject_digest, run_id,"
            " candidate_digest, final_diff_digest, validation_manifest_digest,"
            " formal_evidence_digest, workspace_preimage_digest, run_config_digest,"
            " policy_digest, reference_profile_digest, action_semantic_digest,"
            " expires_at) VALUES ('c' * 64, 'run-1', 'd' * 64, 'e' * 64,"
            " 'f' * 64, '0' * 64, '1' * 64, '2' * 64, '3' * 64, '4' * 64,"
            " '5' * 64, '2026-08-05T09:05:00.000Z')"
        )
        tx.execute(
            "INSERT INTO writeback_approvals (approval_id, subject_digest,"
            " run_id, wait_id, created_at, status) VALUES"
            " ('approval-1', 'c' * 64, 'run-1', 'wait-1',"
            " '2026-08-05T09:01:00.000Z', 'PENDING')"
        )


@pytest.fixture
def database(tmp_path: Path) -> Iterator[ControlDatabase]:
    control_database = open_control_database(tmp_path / "persistence.db")
    assert (
        apply_migrations(
            control_database, (*_PREFIX_MIGRATIONS, PERSISTENCE_V1_MIGRATION)
        ).kind
        == "APPLIED"
    )
    _seed_approval_chain(control_database)
    yield control_database
    control_database.close()


@pytest.fixture
def transaction_repository(
    database: ControlDatabase,
) -> PersistenceTransactionRepositoryV1:
    return PersistenceTransactionRepositoryV1(database)


@pytest.fixture
def path_repository(database: ControlDatabase) -> PersistencePathRecordRepositoryV1:
    return PersistencePathRecordRepositoryV1(database)


def persistence_transaction(
    transaction_id: str,
    *,
    workspace_identity_digest: str = _WORKSPACE_DIGEST,
) -> PersistenceTransactionV1:
    """One valid PREPARED transaction value for the declared id/workspace."""
    return PersistenceTransactionV1(
        schema_version=1,
        transaction_id=transaction_id,
        run_id="run-1",
        approval_id="approval-1",
        workspace_identity_digest=workspace_identity_digest,
        workspace_path="C:\\work\\vesper",
        final_diff_digest=_FINAL_DIFF_DIGEST,
        policy_digest=_POLICY_DIGEST,
        state="PREPARED",
        run_deadline=CanonicalTimestampV1.parse(_DEADLINE),
        prepared_at=CanonicalTimestampV1.parse(_PREPARED_AT),
        updated_at=CanonicalTimestampV1.parse(_PREPARED_AT),
        workspace_write_count=0,
    )


def path_record(sequence: int, path: str) -> PersistencePathRecordV1:
    """One valid body-free CREATE record for the declared sequence/path."""
    return PersistencePathRecordV1.model_validate(
        {
            "schema_version": 1,
            "path": CanonicalRelativePathV1(path),
            "operation": "CREATE",
            "preimage": {"kind": "ABSENT"},
            "postimage": {
                "raw_bytes_digest": _POSTIMAGE_DIGEST,
                "text_metadata": {
                    "encoding": "UTF8",
                    "newline": "LF",
                    "final_newline": True,
                },
                "required_object_policy_digest": _POLICY_DIGEST,
            },
            "sequence": sequence,
            "durable_state": "NOT_STARTED",
            "backup_ref": {"kind": "ABSENT"},
            "last_evidence_digest": {"kind": "ABSENT"},
        }
    )


def test_creation_requires_prepared_and_unique_id(
    transaction_repository: PersistenceTransactionRepositoryV1,
) -> None:
    with pytest.raises(ValueError):
        transaction_repository.create(
            persistence_transaction("tx-1").model_copy(update={"state": "WRITING"})
        )
    with pytest.raises(ValueError):
        transaction_repository.create(
            persistence_transaction("tx-1").model_copy(update={"state": "UNRESOLVED"})
        )
    with pytest.raises(ValueError):
        transaction_repository.create(
            persistence_transaction("tx-1").model_copy(update={"state": "COMMITTED"})
        )
    created = transaction_repository.create(persistence_transaction("tx-1"))
    assert created == persistence_transaction("tx-1")
    with pytest.raises(ValueError):
        transaction_repository.create(persistence_transaction("tx-1"))
    assert transaction_repository.get("tx-1") == persistence_transaction("tx-1")
    assert transaction_repository.get("tx-missing") is None
    # The frozen value round-trips through the row exactly.
    stored = transaction_repository.get("tx-1")
    assert stored is not None
    assert stored.model_dump() == persistence_transaction("tx-1").model_dump()


def test_creation_rejects_missing_run_or_approval_binding(
    transaction_repository: PersistenceTransactionRepositoryV1,
) -> None:
    """A missing run/approval row fails closed as a ValueError, never a
    raw sqlite exception (quality review I-1)."""
    with pytest.raises(ValueError):
        transaction_repository.create(
            persistence_transaction("tx-missing-run").model_copy(
                update={"run_id": "run-missing"}
            )
        )
    with pytest.raises(ValueError):
        transaction_repository.create(
            persistence_transaction("tx-missing-approval").model_copy(
                update={"approval_id": "approval-missing"}
            )
        )
    assert transaction_repository.get("tx-missing-run") is None
    assert transaction_repository.get("tx-missing-approval") is None


def test_one_active_workspace_transaction_in_every_non_terminal_state(
    transaction_repository: PersistenceTransactionRepositoryV1,
) -> None:
    first = transaction_repository.create(persistence_transaction("tx-1"))
    for state in ("WRITING", "UNRESOLVED"):
        transaction_repository.transition(
            "tx-1",
            expected=first.state,
            target=state,
            updated_at=_UPDATED_AT,
            workspace_write_count=1,
        )
        first = first.model_copy(update={"state": state})
        assert transaction_repository.has_active_for_workspace(_WORKSPACE_DIGEST)
        with pytest.raises(ValueError):
            transaction_repository.create(persistence_transaction("tx-2"))
    # Terminal release: COMMITTED and ROLLED_BACK no longer block.
    transaction_repository.transition(
        "tx-1",
        expected="UNRESOLVED",
        target="COMMITTED",
        updated_at=_UPDATED_AT,
        workspace_write_count=1,
    )
    assert not transaction_repository.has_active_for_workspace(_WORKSPACE_DIGEST)
    second = transaction_repository.create(persistence_transaction("tx-2"))
    assert second.transaction_id == "tx-2"
    transaction_repository.transition(
        "tx-2",
        expected="PREPARED",
        target="ROLLED_BACK",
        updated_at=_UPDATED_AT,
        workspace_write_count=0,
    )
    third = transaction_repository.create(persistence_transaction("tx-3"))
    assert third.transaction_id == "tx-3"
    # A different workspace is never blocked.
    other = transaction_repository.create(
        persistence_transaction(
            "tx-other", workspace_identity_digest=_OTHER_WORKSPACE_DIGEST
        )
    )
    assert other.workspace_identity_digest == _OTHER_WORKSPACE_DIGEST


def test_find_active_and_unresolved_gate(
    transaction_repository: PersistenceTransactionRepositoryV1,
) -> None:
    assert transaction_repository.find_active_by_workspace(_WORKSPACE_DIGEST) is None
    assert not transaction_repository.has_unresolved(_WORKSPACE_DIGEST)
    transaction_repository.create(persistence_transaction("tx-1"))
    active = transaction_repository.find_active_by_workspace(_WORKSPACE_DIGEST)
    assert active is not None and active.transaction_id == "tx-1"
    assert not transaction_repository.has_unresolved(_WORKSPACE_DIGEST)
    transaction_repository.transition(
        "tx-1",
        expected="PREPARED",
        target="UNRESOLVED",
        updated_at=_UPDATED_AT,
        workspace_write_count=1,
    )
    assert transaction_repository.has_unresolved(_WORKSPACE_DIGEST)
    assert not transaction_repository.has_unresolved(_OTHER_WORKSPACE_DIGEST)
    active = transaction_repository.find_active_by_workspace(_WORKSPACE_DIGEST)
    assert active is not None and active.state == "UNRESOLVED"


def test_transition_table_legal_pairs_only(
    transaction_repository: PersistenceTransactionRepositoryV1,
) -> None:
    transaction_repository.create(persistence_transaction("tx-1"))
    # Every legal pair applies exactly once and refreshes the facts.
    legal_pairs: tuple[
        tuple[
            Literal["PREPARED", "WRITING", "COMMITTED", "ROLLED_BACK", "UNRESOLVED"],
            Literal["PREPARED", "WRITING", "COMMITTED", "ROLLED_BACK", "UNRESOLVED"],
        ],
        ...,
    ] = (
        ("PREPARED", "WRITING"),
        ("WRITING", "UNRESOLVED"),
        ("UNRESOLVED", "ROLLED_BACK"),
    )
    for expected, target in legal_pairs:
        transaction_repository.transition(
            "tx-1",
            expected=expected,
            target=target,
            updated_at=_UPDATED_AT,
            workspace_write_count=1,
        )
        stored = transaction_repository.get("tx-1")
        assert stored is not None
        assert stored.state == target
        assert stored.workspace_write_count == 1
        assert stored.updated_at == _UPDATED_AT
    # Every illegal pair rejects with the closed INVALID_TRANSITION code.
    illegal_pairs: tuple[
        tuple[
            Literal["PREPARED", "WRITING", "COMMITTED", "ROLLED_BACK", "UNRESOLVED"],
            Literal["PREPARED", "WRITING", "COMMITTED", "ROLLED_BACK", "UNRESOLVED"],
        ],
        ...,
    ] = (
        ("WRITING", "PREPARED"),
        ("COMMITTED", "WRITING"),
        ("ROLLED_BACK", "WRITING"),
        ("UNRESOLVED", "PREPARED"),
        ("PREPARED", "PREPARED"),
    )
    for expected, target in illegal_pairs:
        with pytest.raises(TransactionTransitionErrorV1) as error:
            transaction_repository.transition(
                "tx-1",
                expected=expected,
                target=target,
                updated_at=_UPDATED_AT,
                workspace_write_count=0,
            )
        assert error.value.error_code == "INVALID_TRANSITION"
    # Terminal states are immutable; stale expectations never mutate.
    with pytest.raises(TransactionTransitionErrorV1) as error:
        transaction_repository.transition(
            "tx-1",
            expected="ROLLED_BACK",
            target="COMMITTED",
            updated_at=_UPDATED_AT,
            workspace_write_count=1,
        )
    assert error.value.error_code == "INVALID_TRANSITION"
    with pytest.raises(TransactionTransitionErrorV1) as error:
        transaction_repository.transition(
            "tx-1",
            expected="WRITING",
            target="COMMITTED",
            updated_at=_UPDATED_AT,
            workspace_write_count=1,
        )
    assert error.value.error_code == "STALE"
    with pytest.raises(TransactionTransitionErrorV1) as error:
        transaction_repository.transition(
            "tx-missing",
            expected="PREPARED",
            target="WRITING",
            updated_at=_UPDATED_AT,
            workspace_write_count=0,
        )
    assert error.value.error_code == "NOT_FOUND"


def test_path_repository_edge_cases(
    transaction_repository: PersistenceTransactionRepositoryV1,
    path_repository: PersistencePathRecordRepositoryV1,
) -> None:
    assert path_repository.list_ordered("tx-missing") == ()
    with pytest.raises(ValueError):
        path_repository.append("tx-missing", path_record(1, "src/a.py"))
    transaction_repository.create(persistence_transaction("tx-1"))
    # Records are frozen once the transaction leaves PREPARED.
    transaction_repository.transition(
        "tx-1",
        expected="PREPARED",
        target="WRITING",
        updated_at=_UPDATED_AT,
        workspace_write_count=0,
    )
    with pytest.raises(ValueError):
        path_repository.append("tx-1", path_record(1, "src/a.py"))
    # A second transaction (different workspace) keeps its own records;
    # appends never touch another transaction's rows.
    transaction_repository.create(
        persistence_transaction(
            "tx-2", workspace_identity_digest=_OTHER_WORKSPACE_DIGEST
        )
    )
    path_repository.append("tx-2", path_record(1, "src/a.py"))
    assert len(path_repository.list_ordered("tx-2")) == 1
    assert path_repository.list_ordered("tx-1") == ()
    with pytest.raises(DuplicatePersistencePath):
        path_repository.append("tx-2", path_record(2, "src/a.py"))


def test_concurrent_creation_yields_exactly_one_winner(
    tmp_path: Path,
) -> None:
    """Two threads creating for the same workspace admit exactly one.

    BEGIN IMMEDIATE serializes the writers and the active-workspace
    pre-check runs inside the same transaction, so the second creator
    observes the first's row and fails closed (SPEC 5.2 concurrency
    boundary).  Each thread opens its own connection to the same on-disk
    file (sqlite3 connections are thread-bound; T07.2/T14.1 precedent).
    """
    path = tmp_path / "concurrent.db"
    database = open_control_database(path)
    assert (
        apply_migrations(database, (*_PREFIX_MIGRATIONS, PERSISTENCE_V1_MIGRATION)).kind
        == "APPLIED"
    )
    _seed_approval_chain(database)
    database.close()
    outcomes: list[str] = []
    barrier = threading.Barrier(2, timeout=60)

    def creator(transaction_id: str) -> None:
        worker_database = open_control_database(path)
        try:
            worker = PersistenceTransactionRepositoryV1(worker_database)
            barrier.wait()
            try:
                worker.create(persistence_transaction(transaction_id))
                outcomes.append("CREATED")
            except ValueError:
                outcomes.append("REJECTED")
        finally:
            worker_database.close()

    threads = [
        threading.Thread(target=creator, args=(f"tx-{index}",)) for index in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert sorted(outcomes) == ["CREATED", "REJECTED"]
    verifier_database = open_control_database(path)
    try:
        active = PersistenceTransactionRepositoryV1(
            verifier_database
        ).find_active_by_workspace(_WORKSPACE_DIGEST)
        assert active is not None and active.state == "PREPARED"
    finally:
        verifier_database.close()
