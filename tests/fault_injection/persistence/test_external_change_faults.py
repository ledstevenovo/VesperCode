"""T26.2 legacy step 26.C: explicit recovery apply and external-change faults.

Pins the stale-preview rejection (zero writes), the explicit recovery
apply under the lease, and the complete production fault matrix: only
the three declared dispositions are produced, service-proven terminals
are recorded exactly once with the v0012 body-free result, and stale,
external-change, missing/corrupt/unsafe backup, identity-drift, lease,
workspace-mismatch, and terminal states never overwrite an unproven
external change.

The operative matrix authority is the card Expected (26.C) line per the
SPEC_PROCESS §49 precedent ("exact §5.1 matrix" is a dangling reference).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("pydantic")

from src.vespercode.canonical.clock import FakeClockV1
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.persistence.artifacts import PersistenceArtifactStoreV1
from src.vespercode.persistence.path_record import PersistencePathRecordV1
from src.vespercode.persistence.recovery import RecoveryService
from src.vespercode.persistence.recovery_apply import (
    ApplyRecoveryV1,
    RecoveryApplyService,
    RecoveryLeaseUnavailableV1,
    RecoveryResultRepositoryV1,
)
from src.vespercode.persistence.recovery_preview import (
    RecoveryPathObservationV1,
    RecoveryPreviewService,
)
from src.vespercode.persistence.transaction import (
    PersistencePathRecordRepositoryV1,
    PersistenceTransactionRepositoryV1,
    PersistenceTransactionV1,
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
from src.vespercode.storage.migrations.v0012_recovery import (
    RECOVERY_V1_MIGRATION,
)

_ALL_MIGRATIONS = (
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
    PERSISTENCE_V1_MIGRATION,
    RECOVERY_V1_MIGRATION,
)

_PREIMAGE_DIGEST = hashlib.sha256(b"original b\n").hexdigest()
_POLICY_DIGEST = "33" * 32
_IDENTITY_DIGEST = "44" * 32
_OTHER_IDENTITY_DIGEST = "77" * 32
_WORKSPACE_DIGEST = "55" * 32
_FINAL_DIFF_DIGEST = "66" * 32
_DEADLINE = "2026-08-05T09:15:00.000Z"
_PREPARED_AT = "2026-08-05T09:00:00.000Z"
_NOW = "2026-08-05T09:02:00.000Z"

_BODY_A = b"new a\n"
_BODY_B = b"new b\n"
_ORIGINAL_B = b"original b\n"
_FOREIGN = b"foreign external bytes\n"


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


def _open_environment(tmp_path: Path, name: str) -> ControlDatabase:
    database = open_control_database(tmp_path / f"{name}.db")
    assert apply_migrations(database, _ALL_MIGRATIONS).kind == "APPLIED"
    _seed_approval_chain(database)
    return database


class SpyLease:
    """The injected lease port; unavailable exactly when requested."""

    def __init__(self, available: bool = True) -> None:
        self._available = available
        self._held = False

    def acquire(self) -> None:
        if not self._available:
            raise RecoveryLeaseUnavailableV1("lease unavailable")
        self._held = True

    def release(self) -> None:
        self._held = False

    def is_held(self) -> bool:
        return self._held


class SpyWorkspace:
    """In-memory workspace: observe, replace, delete, and write counting."""

    def __init__(self, *, lease_held: bool = True) -> None:
        self._files: dict[str, bytes] = {}
        self._identities: dict[str, str] = {}
        self._writes: list[str] = []
        self._deletes: list[str] = []
        self._lease_held = lease_held
        self._delete_fails = False

    def seed(self, path: str, body: bytes, identity: str = _IDENTITY_DIGEST) -> None:
        self._files[path] = body
        self._identities[path] = identity

    def break_identity(self, path: str) -> None:
        del self._identities[path]

    def observe(self, path: CanonicalRelativePathV1) -> RecoveryPathObservationV1:
        if path.value not in self._files:
            return RecoveryPathObservationV1.model_validate(
                {
                    "schema_version": 1,
                    "path": path.value,
                    "source": "WORKSPACE_BYTES",
                    "content_digest": {"kind": "ABSENT"},
                    "object_identity_digest": {"kind": "ABSENT"},
                    "object_kind": "ABSENT",
                    "supported": True,
                }
            )
        try:
            identity = self._identities[path.value]
        except KeyError:
            return RecoveryPathObservationV1.model_validate(
                {
                    "schema_version": 1,
                    "path": path.value,
                    "source": "WORKSPACE_BYTES",
                    "content_digest": {"kind": "ABSENT"},
                    "object_identity_digest": {"kind": "ABSENT"},
                    "object_kind": "ABSENT",
                    "supported": False,
                }
            )
        return RecoveryPathObservationV1.model_validate(
            {
                "schema_version": 1,
                "path": path.value,
                "source": "WORKSPACE_BYTES",
                "content_digest": {
                    "kind": "PRESENT",
                    "value": {
                        "value": hashlib.sha256(self._files[path.value]).hexdigest()
                    },
                },
                "object_identity_digest": {
                    "kind": "PRESENT",
                    "value": {"value": identity},
                },
                "object_kind": "FILE",
                "supported": True,
            }
        )

    def replace(self, path: CanonicalRelativePathV1, body: bytes) -> None:
        self._files[path.value] = body
        self._writes.append(path.value)

    def delete(self, path: CanonicalRelativePathV1) -> None:
        if self._delete_fails:
            raise OSError("injected delete failure")
        del self._files[path.value]
        self._deletes.append(path.value)

    def fail_delete(self) -> None:
        """Make every delete raise (authoritative-change fault seam)."""
        self._delete_fails = True

    @property
    def write_count(self) -> int:
        return len(self._writes) + len(self._deletes)

    def lease_held(self) -> bool:
        return self._lease_held

    @property
    def files(self) -> dict[str, bytes]:
        return dict(self._files)

    @property
    def deletes(self) -> list[str]:
        return list(self._deletes)


def persistence_transaction(
    transaction_id: str,
    *,
    deadline: str = _DEADLINE,
) -> PersistenceTransactionV1:
    """One valid PREPARED transaction value for the declared id."""
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
        run_deadline=CanonicalTimestampV1.parse(deadline),
        prepared_at=CanonicalTimestampV1.parse(_PREPARED_AT),
        updated_at=CanonicalTimestampV1.parse(_PREPARED_AT),
        workspace_write_count=0,
    )


def path_record(
    sequence: int,
    path: str,
    *,
    operation: str = "CREATE",
    preimage_digest: str = _PREIMAGE_DIGEST,
    postimage_digest: str = "",
) -> PersistencePathRecordV1:
    """One body-free record for the declared path/operation."""
    if postimage_digest == "":
        postimage_digest = hashlib.sha256(_BODY_B).hexdigest()
    if operation == "CREATE":
        preimage: dict[str, object] = {"kind": "ABSENT"}
        backup: dict[str, object] = {"kind": "ABSENT"}
    else:
        preimage = {
            "kind": "PRESENT",
            "raw_bytes_digest": preimage_digest,
            "text_metadata": {
                "encoding": "UTF8",
                "newline": "LF",
                "final_newline": True,
            },
            "object_identity_digest": _IDENTITY_DIGEST,
        }
        backup = {
            "kind": "PRESENT",
            "value": {
                "artifact_id": "BACKUP-" + preimage_digest,
                "digest": {"value": preimage_digest},
            },
        }
    return PersistencePathRecordV1.model_validate(
        {
            "schema_version": 1,
            "path": CanonicalRelativePathV1(path),
            "operation": operation,
            "preimage": preimage,
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
            "backup_ref": backup,
            "last_evidence_digest": {"kind": "ABSENT"},
        }
    )


def _records() -> tuple[PersistencePathRecordV1, ...]:
    return (
        path_record(
            1, "src/a.py", postimage_digest=hashlib.sha256(_BODY_A).hexdigest()
        ),
        path_record(2, "src/b.py", operation="REPLACE"),
    )


def _seed_transaction(
    database: ControlDatabase,
    workspace: SpyWorkspace,
    *,
    records: tuple[PersistencePathRecordV1, ...] | None = None,
    transaction_id: str = "tx-1",
    deadline: str = _DEADLINE,
) -> None:
    if records is None:
        records = _records()
    transaction_repository = PersistenceTransactionRepositoryV1(database)
    path_repository = PersistencePathRecordRepositoryV1(database)
    transaction = transaction_repository.create(
        persistence_transaction(transaction_id, deadline=deadline)
    )
    for record in records:
        path_repository.append(transaction.transaction_id, record)


def _backup_artifacts(artifact_store: PersistenceArtifactStoreV1) -> None:
    artifact_store.put("BACKUP", _ORIGINAL_B)


def _build_recovery(
    database: ControlDatabase,
    workspace: SpyWorkspace,
    tmp_path: Path,
    *,
    lease: SpyLease | None = None,
    clock: FakeClockV1 | None = None,
    artifact_store: PersistenceArtifactStoreV1 | None = None,
) -> RecoveryService:
    store = artifact_store or PersistenceArtifactStoreV1(tmp_path / "artifacts")
    preview_service = RecoveryPreviewService(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=store,
        workspace_identity_digest=_WORKSPACE_DIGEST,
        observer=workspace,
    )
    apply_service = RecoveryApplyService(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=store,
        preview_service=preview_service,
        workspace=workspace,
        lease=lease if lease is not None else SpyLease(),
        results=RecoveryResultRepositoryV1(database),
        clock=clock
        or FakeClockV1.from_epoch_milliseconds(
            CanonicalTimestampV1.parse(_NOW).epoch_milliseconds
        ),
        workspace_identity_digest=_WORKSPACE_DIGEST,
    )
    return RecoveryService(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        preview_service=preview_service,
        apply_service=apply_service,
    )


def apply_command(
    preview_digest: str,
    *,
    disposition: str = "ROLLED_BACK",
    transaction_id: str = "tx-1",
    workspace_identity_digest: str = _WORKSPACE_DIGEST,
) -> ApplyRecoveryV1:
    return ApplyRecoveryV1(
        schema_version=1,
        transaction_id=transaction_id,
        workspace_identity_digest=workspace_identity_digest,
        preview_digest=preview_digest,
        requested_disposition=disposition,  # type: ignore[arg-type]
        explicit_apply=True,
    )


def command_with_stale_preview_digest() -> ApplyRecoveryV1:
    """One command whose preview digest cannot match any current preview."""
    return apply_command("0" * 64)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[ControlDatabase]:
    control_database = _open_environment(tmp_path, "recovery")
    yield control_database
    control_database.close()


@pytest.fixture
def workspace() -> SpyWorkspace:
    spy = SpyWorkspace()
    spy.seed("src/b.py", _ORIGINAL_B)
    return spy


@pytest.fixture
def recovery(
    database: ControlDatabase,
    workspace: SpyWorkspace,
    tmp_path: Path,
) -> RecoveryService:
    _seed_transaction(database, workspace)
    service = _build_recovery(database, workspace, tmp_path)
    return service


def _preview_digest(
    database: ControlDatabase,
    workspace: SpyWorkspace,
    tmp_path: Path,
    transaction_id: str = "tx-1",
    *,
    artifact_store: PersistenceArtifactStoreV1 | None = None,
) -> str:
    store = artifact_store or PersistenceArtifactStoreV1(tmp_path / "artifacts")
    preview_service = RecoveryPreviewService(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=store,
        workspace_identity_digest=_WORKSPACE_DIGEST,
        observer=workspace,
    )
    return preview_service.preview_transaction(transaction_id).preview_digest


def _result_row(database: ControlDatabase) -> tuple[str, ...] | None:
    with database.immediate_transaction() as tx:
        row = tx.execute(
            "SELECT transaction_id, disposition, evidence_digest,"
            " changed_paths, workspace_write_count, applied_at"
            " FROM recovery_results"
        ).fetchone()
    if row is None:
        return None
    return tuple(str(value) for value in row)


def test_stale_preview_cannot_apply_recovery(
    recovery: RecoveryService,
    workspace: SpyWorkspace,
) -> None:
    result = recovery.apply(command_with_stale_preview_digest())
    assert result.error_code == "RECOVERY_PREVIEW_STALE"
    assert workspace.write_count == 0


def test_recovery_apply_fault_matrix(
    database: ControlDatabase,
    tmp_path: Path,
) -> None:
    """The exact §5.1-Expected (26.C) matrix: exact v0012 schema and the
    complete production matrix produce only the three declared
    dispositions and never overwrite an unproven external change."""
    # COMMITTED apply: every path exactly matches its postimage; the
    # write-after verification is redone and the terminal is recorded
    # with zero workspace writes.
    fresh = _open_environment(tmp_path, "m-committed")
    committed_workspace = SpyWorkspace()
    committed_workspace.seed("src/a.py", _BODY_A)
    committed_workspace.seed("src/b.py", _BODY_B)
    _seed_transaction(fresh, committed_workspace)
    store = PersistenceArtifactStoreV1(tmp_path / "artifacts-m-committed")
    _backup_artifacts(store)
    committed_service = _build_recovery(
        fresh, committed_workspace, tmp_path, artifact_store=store
    )
    digest = _preview_digest(fresh, committed_workspace, tmp_path, artifact_store=store)
    committed = committed_service.apply(apply_command(digest, disposition="COMMITTED"))
    assert committed.error_code is None and committed.disposition == "COMMITTED"
    assert committed.changed_paths == () and committed.workspace_write_count == 0
    assert _result_row(fresh) is not None
    row = _result_row(fresh)
    assert row is not None and row[1] == "COMMITTED"
    with fresh.immediate_transaction() as tx:
        state = tx.execute(
            "SELECT state FROM persistence_transactions WHERE transaction_id = 'tx-1'"
        ).fetchone()
        path_states = tx.execute(
            "SELECT durable_state FROM persistence_path_records ORDER BY sequence"
        ).fetchall()
    assert str(state[0]) == "COMMITTED"
    assert [str(r[0]) for r in path_states] == ["VERIFIED", "VERIFIED"]
    # A second apply of the terminal transaction is refused.
    again = committed_service.apply(apply_command(digest, disposition="COMMITTED"))
    assert again.error_code == "RECOVERY_ALREADY_TERMINAL"
    fresh.close()

    # ROLLED_BACK zero-change: every path already at its preimage; the
    # terminal is recorded with zero changes.
    fresh = _open_environment(tmp_path, "m-rolled-zero")
    zero_workspace = SpyWorkspace()
    zero_workspace.seed("src/b.py", _ORIGINAL_B)
    _seed_transaction(fresh, zero_workspace)
    store = PersistenceArtifactStoreV1(tmp_path / "artifacts-m-rolled-zero")
    _backup_artifacts(store)
    zero_service = _build_recovery(
        fresh, zero_workspace, tmp_path, artifact_store=store
    )
    zero_digest = _preview_digest(fresh, zero_workspace, tmp_path, artifact_store=store)
    zero = zero_service.apply(apply_command(zero_digest, disposition="ROLLED_BACK"))
    assert zero.error_code is None and zero.disposition == "ROLLED_BACK"
    assert zero.changed_paths == () and zero.workspace_write_count == 0
    fresh.close()

    # ROLLED_BACK with a CREATE applied: the safe ABSENT rollback deletes
    # only the file that still exactly matches its postimage.
    fresh = _open_environment(tmp_path, "m-rolled-create")
    create_workspace = SpyWorkspace()
    create_workspace.seed("src/a.py", _BODY_A)
    create_workspace.seed("src/b.py", _ORIGINAL_B)
    _seed_transaction(fresh, create_workspace)
    store = PersistenceArtifactStoreV1(tmp_path / "artifacts-m-rolled-create")
    _backup_artifacts(store)
    create_service = _build_recovery(
        fresh, create_workspace, tmp_path, artifact_store=store
    )
    create_digest = _preview_digest(
        fresh, create_workspace, tmp_path, artifact_store=store
    )
    rolled = create_service.apply(
        apply_command(create_digest, disposition="ROLLED_BACK")
    )
    assert rolled.error_code is None and rolled.disposition == "ROLLED_BACK"
    assert rolled.changed_paths == ("src/a.py",)
    assert "src/a.py" not in create_workspace.files
    assert create_workspace.deletes == ["src/a.py"]
    fresh.close()

    # ROLLED_BACK with a REPLACE applied: a mid-writeback transaction
    # whose CREATE was never applied but whose REPLACE path is at its
    # postimage restores the path from its verified backup artifact.
    fresh = _open_environment(tmp_path, "m-rolled-restore")
    restore_workspace = SpyWorkspace()
    restore_workspace.seed("src/b.py", _BODY_B)
    _seed_transaction(fresh, restore_workspace)
    store = PersistenceArtifactStoreV1(tmp_path / "artifacts-m-rolled-restore")
    _backup_artifacts(store)
    restore_service = _build_recovery(
        fresh, restore_workspace, tmp_path, artifact_store=store
    )
    restore_digest = _preview_digest(
        fresh, restore_workspace, tmp_path, artifact_store=store
    )
    restored = restore_service.apply(
        apply_command(restore_digest, disposition="ROLLED_BACK")
    )
    assert restored.error_code is None and restored.disposition == "ROLLED_BACK"
    assert restored.changed_paths == ("src/b.py",)
    assert restore_workspace.files == {"src/b.py": _ORIGINAL_B}
    assert restore_workspace.write_count == 1
    with restore_service.transaction_repository.database.immediate_transaction() as tx:
        state = tx.execute(
            "SELECT state FROM persistence_transactions WHERE transaction_id = 'tx-1'"
        ).fetchone()
    assert str(state[0]) == "ROLLED_BACK"
    fresh.close()

    # A fully-applied transaction previews COMMITTED: a ROLLED_BACK
    # request on it is refused (RECOVERY_DISPOSITION_MISMATCH) and a
    # COMMITTED apply records the terminal with zero workspace writes.
    fresh = _open_environment(tmp_path, "m-fully-applied")
    fully_workspace = SpyWorkspace()
    fully_workspace.seed("src/a.py", _BODY_A)
    fully_workspace.seed("src/b.py", _BODY_B)
    _seed_transaction(fresh, fully_workspace)
    store = PersistenceArtifactStoreV1(tmp_path / "artifacts-m-fully-applied")
    _backup_artifacts(store)
    fully_service = _build_recovery(
        fresh, fully_workspace, tmp_path, artifact_store=store
    )
    fully_digest = _preview_digest(
        fresh, fully_workspace, tmp_path, artifact_store=store
    )
    refused = fully_service.apply(
        apply_command(fully_digest, disposition="ROLLED_BACK")
    )
    assert refused.error_code == "RECOVERY_DISPOSITION_MISMATCH"
    assert refused.workspace_write_count == 0
    committed = fully_service.apply(
        apply_command(fully_digest, disposition="COMMITTED")
    )
    assert committed.error_code is None and committed.disposition == "COMMITTED"
    assert committed.workspace_write_count == 0
    fresh.close()

    # External change: an unproven external byte state never gets
    # overwritten and never produces a terminal.
    fresh = _open_environment(tmp_path, "m-external")
    external_workspace = SpyWorkspace()
    external_workspace.seed("src/a.py", _FOREIGN)
    external_workspace.seed("src/b.py", _ORIGINAL_B)
    _seed_transaction(fresh, external_workspace)
    store = PersistenceArtifactStoreV1(tmp_path / "artifacts-m-external")
    _backup_artifacts(store)
    external_service = _build_recovery(
        fresh, external_workspace, tmp_path, artifact_store=store
    )
    external_digest = _preview_digest(
        fresh, external_workspace, tmp_path, artifact_store=store
    )
    external = external_service.apply(
        apply_command(external_digest, disposition="ROLLED_BACK")
    )
    assert external.error_code == "RECOVERY_UNRESOLVED"
    assert external.changed_paths == () and external.workspace_write_count == 0
    assert external_workspace.files["src/a.py"] == _FOREIGN
    assert _result_row(fresh) is None
    fresh.close()

    # Identity drift: preimage bytes behind a replaced object identity
    # are never overwritten (byte text alone never authorizes).
    fresh = _open_environment(tmp_path, "m-identity")
    identity_workspace = SpyWorkspace()
    identity_workspace.seed("src/a.py", _BODY_A)
    identity_workspace.seed("src/b.py", _ORIGINAL_B, identity=_OTHER_IDENTITY_DIGEST)
    _seed_transaction(fresh, identity_workspace)
    store = PersistenceArtifactStoreV1(tmp_path / "artifacts-m-identity")
    _backup_artifacts(store)
    identity_service = _build_recovery(
        fresh, identity_workspace, tmp_path, artifact_store=store
    )
    identity_digest = _preview_digest(
        fresh, identity_workspace, tmp_path, artifact_store=store
    )
    identity = identity_service.apply(
        apply_command(identity_digest, disposition="ROLLED_BACK")
    )
    assert identity.error_code == "RECOVERY_UNRESOLVED"
    assert identity.changed_paths == () and identity.workspace_write_count == 0
    fresh.close()

    # Missing backup: a REPLACE path at its postimage with no backup
    # artifact cannot be proven and is never restored.
    fresh = _open_environment(tmp_path, "m-missing-backup")
    missing_workspace = SpyWorkspace()
    missing_workspace.seed("src/b.py", _BODY_B)
    _seed_transaction(fresh, missing_workspace)
    missing_service = _build_recovery(fresh, missing_workspace, tmp_path)
    missing_digest = _preview_digest(fresh, missing_workspace, tmp_path)
    missing = missing_service.apply(
        apply_command(missing_digest, disposition="ROLLED_BACK")
    )
    assert missing.error_code == "RECOVERY_UNRESOLVED"
    assert missing.changed_paths == () and missing.workspace_write_count == 0
    assert missing_workspace.files["src/b.py"] == _BODY_B
    fresh.close()

    # Stale preview: the bound digest no longer matches the current
    # preview; zero writes, zero terminal.
    fresh = _open_environment(tmp_path, "m-stale")
    stale_workspace = SpyWorkspace()
    stale_workspace.seed("src/a.py", _BODY_A)
    stale_workspace.seed("src/b.py", _ORIGINAL_B)
    _seed_transaction(fresh, stale_workspace)
    store = PersistenceArtifactStoreV1(tmp_path / "artifacts-m-stale")
    _backup_artifacts(store)
    stale_service = _build_recovery(
        fresh, stale_workspace, tmp_path, artifact_store=store
    )
    stale = stale_service.apply(apply_command("0" * 64, disposition="ROLLED_BACK"))
    assert stale.error_code == "RECOVERY_PREVIEW_STALE"
    assert stale.changed_paths == () and stale.workspace_write_count == 0
    assert _result_row(fresh) is None
    fresh.close()

    # Disposition mismatch: the requested disposition must equal the
    # proven disposition.
    fresh = _open_environment(tmp_path, "m-mismatch")
    mismatch_workspace = SpyWorkspace()
    mismatch_workspace.seed("src/a.py", _BODY_A)
    mismatch_workspace.seed("src/b.py", _ORIGINAL_B)
    _seed_transaction(fresh, mismatch_workspace)
    store = PersistenceArtifactStoreV1(tmp_path / "artifacts-m-mismatch")
    _backup_artifacts(store)
    mismatch_service = _build_recovery(
        fresh, mismatch_workspace, tmp_path, artifact_store=store
    )
    mismatch_digest = _preview_digest(
        fresh, mismatch_workspace, tmp_path, artifact_store=store
    )
    mismatch = mismatch_service.apply(
        apply_command(mismatch_digest, disposition="COMMITTED")
    )
    assert mismatch.error_code == "RECOVERY_DISPOSITION_MISMATCH"
    assert mismatch.workspace_write_count == 0
    fresh.close()

    # Workspace mismatch: the command must bind the transaction workspace.
    fresh = _open_environment(tmp_path, "m-workspace")
    workspace_mismatch = SpyWorkspace()
    workspace_mismatch.seed("src/b.py", _ORIGINAL_B)
    _seed_transaction(fresh, workspace_mismatch)
    mismatched_service = _build_recovery(fresh, workspace_mismatch, tmp_path)
    wrong_workspace = mismatched_service.apply(
        apply_command("0" * 64, workspace_identity_digest="99" * 32)
    )
    assert wrong_workspace.error_code == "WORKSPACE_MISMATCH"
    assert wrong_workspace.workspace_write_count == 0
    fresh.close()

    # Lease unavailable: the apply cannot proceed without the lease.
    fresh = _open_environment(tmp_path, "m-lease")
    lease_workspace = SpyWorkspace()
    lease_workspace.seed("src/b.py", _ORIGINAL_B)
    _seed_transaction(fresh, lease_workspace)
    lease_service = _build_recovery(
        fresh, lease_workspace, tmp_path, lease=SpyLease(available=False)
    )
    no_lease = lease_service.apply(apply_command("0" * 64))
    assert no_lease.error_code == "WORKSPACE_LOCK_LOST"
    assert no_lease.workspace_write_count == 0
    fresh.close()

    # Authoritative-change fault: a failed delete returns a closed
    # RECOVERY_UNRESOLVED result with the honest changed paths and no
    # terminal record (quality review I-1).
    fresh = _open_environment(tmp_path, "m-delete-fault")
    delete_workspace = SpyWorkspace()
    delete_workspace.seed("src/a.py", _BODY_A)
    delete_workspace.seed("src/b.py", _ORIGINAL_B)
    delete_workspace.fail_delete()
    _seed_transaction(fresh, delete_workspace)
    store = PersistenceArtifactStoreV1(tmp_path / "artifacts-m-delete-fault")
    _backup_artifacts(store)
    delete_service = _build_recovery(
        fresh, delete_workspace, tmp_path, artifact_store=store
    )
    delete_digest = _preview_digest(
        fresh, delete_workspace, tmp_path, artifact_store=store
    )
    delete_fault = delete_service.apply(
        apply_command(delete_digest, disposition="ROLLED_BACK")
    )
    assert delete_fault.error_code == "RECOVERY_UNRESOLVED"
    assert delete_fault.changed_paths == ()
    assert delete_fault.workspace_write_count == 0
    assert delete_workspace.files["src/a.py"] == _BODY_A
    assert _result_row(fresh) is None
    fresh.close()

    # Missing transaction: recovery of an unknown transaction fails closed.
    fresh = _open_environment(tmp_path, "m-missing-tx")
    missing_tx_service = _build_recovery(fresh, SpyWorkspace(), tmp_path)
    missing_tx = missing_tx_service.apply(apply_command("0" * 64))
    assert missing_tx.error_code == "PERSISTENCE_FAILED"
    fresh.close()

    # v0012 result rows exist only for service-proven terminals and the
    # changed paths are honestly recorded in canonical JSON.
    fresh = _open_environment(tmp_path, "m-v0012")
    v12_workspace = SpyWorkspace()
    v12_workspace.seed("src/b.py", _BODY_B)
    _seed_transaction(fresh, v12_workspace)
    store = PersistenceArtifactStoreV1(tmp_path / "artifacts-m-v0012")
    _backup_artifacts(store)
    v12_service = _build_recovery(fresh, v12_workspace, tmp_path, artifact_store=store)
    v12_digest = _preview_digest(fresh, v12_workspace, tmp_path, artifact_store=store)
    v12 = v12_service.apply(apply_command(v12_digest, disposition="ROLLED_BACK"))
    assert v12.error_code is None and v12.disposition == "ROLLED_BACK"
    row = _result_row(fresh)
    assert row is not None
    assert row[1] == "ROLLED_BACK"
    assert json.loads(row[3]) == ["src/b.py"]
    assert row[4] == "1"
    fresh.close()
