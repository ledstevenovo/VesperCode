"""T26.1 legacy step 26.A: immutable v0011 transaction/path record tests.

Pins the exact immutable value contracts and repository behavior of the
v0011 persistence schema: repository creation (PREPARED only, unique
transaction id), the unique active workspace transaction, the unique
ordered per-path identity (duplicate-path rejection and strictly sorted
1-based sequences), the closed transaction/path state vocabulary with
immutable transitions, ordered repository access, and body-free evidence
references.  Every matrix row runs with zero artifact I/O and zero
workspace bytes (the repositories touch only the control database).

The operative matrix authority is the card Expected (26.A) line per the
SPEC_PROCESS §49 precedent ("exact §5.1 matrix" is a dangling reference).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

# The value contracts consume pydantic runtime models; the hash-locked
# gate toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.persistence.path_record import (
    DuplicatePersistencePath,
    PersistencePathRecordV1,
)
from src.vespercode.persistence.transaction import (
    PersistencePathRecordRepositoryV1,
    PersistenceTransactionRepositoryV1,
    PersistenceTransactionV1,
    TransactionTransitionErrorV1,
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
from src.vespercode.storage.migrations.v0006_audit import AUDIT_V1_MIGRATION
from src.vespercode.storage.migrations.v0007_agent_turns import (
    AGENT_TURNS_V1_MIGRATION,
)
from src.vespercode.storage.migrations.v0008_feedback import FEEDBACK_V1_MIGRATION
from src.vespercode.storage.migrations.v0009_actions import ACTIONS_V1_MIGRATION
from src.vespercode.storage.migrations.v0010_writeback_approvals import (
    WRITEBACK_APPROVALS_V1_MIGRATION,
)
from src.vespercode.storage.migrations.v0011_persistence import (
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

_PREIMAGE_DIGEST = "11" * 32
_POSTIMAGE_DIGEST = "22" * 32
_POLICY_DIGEST = "33" * 32
_IDENTITY_DIGEST = "44" * 32
_WORKSPACE_DIGEST = "55" * 32
_FINAL_DIFF_DIGEST = "66" * 32
_DEADLINE = "2026-08-05T09:15:00.000Z"
_PREPARED_AT = "2026-08-05T09:00:00.000Z"
_UPDATED_AT = CanonicalTimestampV1.parse(_PREPARED_AT)


def _seed_approval_chain(control_database: ControlDatabase) -> None:
    """Seed the exact run/wait/subject/approval rows the FK chain needs.

    Every persistence transaction binds ``runs(run_id)`` and
    ``writeback_approvals(approval_id)`` (v0011 FKs); the tests use the
    fixed ``run-1`` / ``approval-1`` identities, so one chain is seeded
    once per database.
    """
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


def persistence_transaction(transaction_id: str) -> PersistenceTransactionV1:
    """One valid PREPARED transaction value for the declared transaction id."""
    return PersistenceTransactionV1(
        schema_version=1,
        transaction_id=transaction_id,
        run_id="run-1",
        approval_id="approval-1",
        workspace_identity_digest=_WORKSPACE_DIGEST,
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
    """One valid body-free path record for the declared sequence/path."""
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


def replace_path_record(
    sequence: int,
    path: str,
    *,
    preimage_digest: str = _PREIMAGE_DIGEST,
    postimage_digest: str = _POSTIMAGE_DIGEST,
    identity_digest: str = _IDENTITY_DIGEST,
    backup_artifact_id: str = "BACKUP-" + _PREIMAGE_DIGEST,
) -> PersistencePathRecordV1:
    """One valid REPLACE record binding a PRESENT preimage and backup ref."""
    return PersistencePathRecordV1.model_validate(
        {
            "schema_version": 1,
            "path": CanonicalRelativePathV1(path),
            "operation": "REPLACE",
            "preimage": {
                "kind": "PRESENT",
                "raw_bytes_digest": preimage_digest,
                "text_metadata": {
                    "encoding": "UTF8",
                    "newline": "LF",
                    "final_newline": True,
                },
                "object_identity_digest": identity_digest,
            },
            "postimage": {
                "raw_bytes_digest": postimage_digest,
                "text_metadata": {
                    "encoding": "UTF8",
                    "newline": "LF",
                    "final_newline": True,
                },
                "required_object_policy_digest": _POLICY_DIGEST,
            },
            "sequence": sequence,
            "durable_state": "NOT_STARTED",
            "backup_ref": {
                "kind": "PRESENT",
                "value": {
                    "artifact_id": backup_artifact_id,
                    "digest": {"value": _PREIMAGE_DIGEST},
                },
            },
            "last_evidence_digest": {"kind": "ABSENT"},
        }
    )


def test_path_records_are_unique_and_ordered_with_body_free_evidence(
    transaction_repository: PersistenceTransactionRepositoryV1,
    path_repository: PersistencePathRecordRepositoryV1,
) -> None:
    tx = transaction_repository.create(persistence_transaction("tx-1"))
    path_repository.append(tx.transaction_id, path_record(sequence=1, path="src/a.py"))
    with pytest.raises(DuplicatePersistencePath):
        path_repository.append(
            tx.transaction_id, path_record(sequence=2, path="src/a.py")
        )
    assert path_repository.list_ordered(tx.transaction_id)[0].sequence == 1


def test_persistence_path_record_matrix(
    transaction_repository: PersistenceTransactionRepositoryV1,
    path_repository: PersistencePathRecordRepositoryV1,
) -> None:
    """The exact §5.1-Expected (26.A) matrix: exact v0011 schema, keys,
    uniqueness, state vocabulary, ordered repository access, and body-free
    evidence refs pass without artifact or workspace I/O."""
    # State vocabulary: every transaction state constructs; unknown states
    # reject before any repository call.
    for state in ("PREPARED", "WRITING", "COMMITTED", "ROLLED_BACK", "UNRESOLVED"):
        with pytest.raises(ValueError):
            PersistenceTransactionV1.model_validate(
                {
                    **persistence_transaction(f"tx-{state}").model_dump(),
                    "state": state + "-EXTRA",
                }
            )
    for durable_state in ("NOT_STARTED", "REPLACED", "VERIFIED", "ROLLED_BACK"):
        with pytest.raises(ValueError):
            PersistencePathRecordV1.model_validate(
                {
                    **path_record(1, "src/a.py").model_dump(),
                    "durable_state": durable_state + "-EXTRA",
                }
            )

    # Repository creation: PREPARED only and unique transaction ids.
    with pytest.raises(ValueError):
        transaction_repository.create(
            persistence_transaction("tx-dup").model_copy(update={"state": "WRITING"})
        )
    created = transaction_repository.create(persistence_transaction("tx-1"))
    assert created.state == "PREPARED" and created.workspace_write_count == 0
    with pytest.raises(ValueError):
        transaction_repository.create(persistence_transaction("tx-1"))
    assert transaction_repository.get("tx-1") is not None
    assert transaction_repository.get("tx-missing") is None

    # Unique active workspace transaction: a second non-terminal transaction
    # for the same workspace is rejected, a terminal one is not.
    with pytest.raises(ValueError):
        transaction_repository.create(persistence_transaction("tx-2"))
    assert transaction_repository.has_active_for_workspace(_WORKSPACE_DIGEST)
    transaction_repository.transition(
        "tx-1",
        expected="PREPARED",
        target="COMMITTED",
        updated_at=_UPDATED_AT,
        workspace_write_count=0,
    )
    assert not transaction_repository.has_active_for_workspace(_WORKSPACE_DIGEST)
    terminal = transaction_repository.create(persistence_transaction("tx-2"))
    assert terminal.transaction_id == "tx-2"

    # Unique ordered path identity: strictly sorted append, duplicate-path
    # rejection, and sequence continuation.
    path_repository.append(
        terminal.transaction_id, path_record(sequence=1, path="src/a.py")
    )
    with pytest.raises(DuplicatePersistencePath):
        path_repository.append(
            terminal.transaction_id, path_record(sequence=2, path="src/a.py")
        )
    with pytest.raises(ValueError):
        path_repository.append(
            terminal.transaction_id, path_record(sequence=3, path="src/b.py")
        )
    with pytest.raises(ValueError):
        path_repository.append(
            terminal.transaction_id, path_record(sequence=2, path="src/0a.py")
        )
    path_repository.append(
        terminal.transaction_id, path_record(sequence=2, path="src/b.py")
    )
    ordered = path_repository.list_ordered(terminal.transaction_id)
    assert [record.sequence for record in ordered] == [1, 2]
    assert [record.path.value for record in ordered] == ["src/a.py", "src/b.py"]

    # Body-free evidence refs: records carry digests and refs only, never
    # bodies; the repository appends and lists without touching any
    # artifact or workspace byte.
    replace = replace_path_record(sequence=3, path="src/c.py")
    assert replace.backup_ref.kind == "PRESENT"
    assert replace.backup_ref.value.digest.value == _PREIMAGE_DIGEST
    assert replace.preimage.kind == "PRESENT"
    assert replace.preimage.raw_bytes_digest == _PREIMAGE_DIGEST
    assert replace.preimage.object_identity_digest == _IDENTITY_DIGEST

    # Path-level immutable progress: NOT_STARTED -> REPLACED -> VERIFIED,
    # any of the first three into ROLLED_BACK, never back into a write
    # state, never a second REPLACED.
    assert (
        path_repository.update_durable_state(
            "tx-2",
            "src/b.py",
            expected="NOT_STARTED",
            target="REPLACED",
        ).durable_state
        == "REPLACED"
    )
    with pytest.raises(TransactionTransitionErrorV1):
        path_repository.update_durable_state(
            "tx-2",
            "src/b.py",
            expected="NOT_STARTED",
            target="REPLACED",
        )
    assert (
        path_repository.update_durable_state(
            "tx-2",
            "src/b.py",
            expected="REPLACED",
            target="VERIFIED",
        ).durable_state
        == "VERIFIED"
    )
    with pytest.raises(TransactionTransitionErrorV1):
        path_repository.update_durable_state(
            "tx-2",
            "src/b.py",
            expected="VERIFIED",
            target="REPLACED",
        )
    assert (
        path_repository.update_durable_state(
            "tx-2",
            "src/b.py",
            expected="VERIFIED",
            target="ROLLED_BACK",
        ).durable_state
        == "ROLLED_BACK"
    )
    with pytest.raises(TransactionTransitionErrorV1):
        path_repository.update_durable_state(
            "tx-2",
            "src/b.py",
            expected="ROLLED_BACK",
            target="NOT_STARTED",
        )
    with pytest.raises(TransactionTransitionErrorV1):
        path_repository.update_durable_state(
            "tx-2",
            "src/missing.py",
            expected="NOT_STARTED",
            target="REPLACED",
        )

    # Immutable transitions: only the legal pairs apply; illegal or stale
    # transitions reject with zero mutation; terminal states are immutable.
    with pytest.raises(ValueError):
        transaction_repository.transition(
            "tx-missing",
            expected="PREPARED",
            target="WRITING",
            updated_at=_UPDATED_AT,
            workspace_write_count=0,
        )
    with pytest.raises(TransactionTransitionErrorV1):
        transaction_repository.transition(
            "tx-2",
            expected="PREPARED",
            target="PREPARED",
            updated_at=_UPDATED_AT,
            workspace_write_count=0,
        )
    transaction_repository.transition(
        "tx-2",
        expected="PREPARED",
        target="WRITING",
        updated_at=_UPDATED_AT,
        workspace_write_count=1,
    )
    with pytest.raises(TransactionTransitionErrorV1):
        transaction_repository.transition(
            "tx-2",
            expected="PREPARED",
            target="WRITING",
            updated_at=_UPDATED_AT,
            workspace_write_count=0,
        )
    with pytest.raises(TransactionTransitionErrorV1):
        transaction_repository.transition(
            "tx-2",
            expected="WRITING",
            target="PREPARED",
            updated_at=_UPDATED_AT,
            workspace_write_count=1,
        )
    with pytest.raises(TransactionTransitionErrorV1):
        transaction_repository.transition(
            "tx-2",
            expected="COMMITTED",
            target="ROLLED_BACK",
            updated_at=_UPDATED_AT,
            workspace_write_count=1,
        )
    transaction_repository.transition(
        "tx-2",
        expected="WRITING",
        target="ROLLED_BACK",
        updated_at=_UPDATED_AT,
        workspace_write_count=1,
    )
    with pytest.raises(TransactionTransitionErrorV1):
        transaction_repository.transition(
            "tx-2",
            expected="ROLLED_BACK",
            target="COMMITTED",
            updated_at=_UPDATED_AT,
            workspace_write_count=1,
        )
    with pytest.raises(ValueError):
        path_repository.append("tx-2", path_record(sequence=3, path="src/d.py"))
