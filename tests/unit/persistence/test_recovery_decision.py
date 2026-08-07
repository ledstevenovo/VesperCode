"""T26.2 legacy step 26.B: read-only recovery preview and three-value tests.

Pins the read-only recovery preview: the exact non-terminal transaction,
ordered path records, verified artifact metadata, and current workspace
object/byte identities are read into bounded source-attributed
observations with zero writes; the pure classifier produces only
completely-proven ``COMMITTED``, all-preimage ``ROLLED_BACK``, and
``UNRESOLVED`` for every mixed, missing, ambiguous, corrupt, or
external-change state (SPEC 4.6 / AC-29 / AC-22).

The operative matrix authority is the card Expected (26.B) line per the
SPEC_PROCESS §49 precedent ("exact §5.1 matrix" is a dangling reference).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("pydantic")

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.persistence.path_record import PersistencePathRecordV1
from vespercode.persistence.recovery_preview import (
    RecoveryDispositionV1,
    RecoveryPathObservationV1,
    RecoveryPreviewService,
)
from vespercode.persistence.transaction import (
    PersistencePathRecordRepositoryV1,
    PersistenceTransactionRepositoryV1,
    PersistenceTransactionV1,
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
)

_PREIMAGE_DIGEST = hashlib.sha256(b"original b\n").hexdigest()
_POLICY_DIGEST = "33" * 32
_IDENTITY_DIGEST = "44" * 32
_OTHER_IDENTITY_DIGEST = "77" * 32
_WORKSPACE_DIGEST = "55" * 32
_FINAL_DIFF_DIGEST = "66" * 32
_DEADLINE = "2026-08-05T09:15:00.000Z"
_PREPARED_AT = "2026-08-05T09:00:00.000Z"

_BODY_A = b"new a\n"
_BODY_B = b"new b\n"
_ORIGINAL_B = b"original b\n"
_ORIGINAL_A = b"original a\n"
_EXTERNAL_A = b"external a\n"


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
    control_database = open_control_database(tmp_path / "recovery.db")
    assert apply_migrations(control_database, _ALL_MIGRATIONS).kind == "APPLIED"
    _seed_approval_chain(control_database)
    yield control_database
    control_database.close()


class SpyWorkspace:
    """In-memory workspace bytes/identities with a literal write counter."""

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}
        self._identities: dict[str, str] = {}
        self._writes: list[str] = []

    def seed(self, path: str, body: bytes, identity: str = _IDENTITY_DIGEST) -> None:
        self._files[path] = body
        self._identities[path] = identity

    def read_bytes(self, path: CanonicalRelativePathV1) -> bytes:
        if path.value not in self._files:
            raise FileNotFoundError(path.value)
        return self._files[path.value]

    def is_absent(self, path: CanonicalRelativePathV1) -> bool:
        return path.value not in self._files

    def object_identity_digest(self, path: CanonicalRelativePathV1) -> str:
        if path.value not in self._identities:
            raise KeyError(path.value)
        return self._identities[path.value]

    @property
    def write_count(self) -> int:
        return len(self._writes)

    def record_write(self) -> None:
        self._writes.append("write")

    def break_identity(self, path: str) -> None:
        """Remove one path's identity fact (unprovable-observer seam)."""
        del self._identities[path]


class SpyObserver:
    """Observes the spy workspace with byte and identity facts."""

    def __init__(self, workspace: SpyWorkspace) -> None:
        self._workspace = workspace

    def observe(self, path: CanonicalRelativePathV1) -> RecoveryPathObservationV1:
        if self._workspace.is_absent(path):
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
            raw = self._workspace.read_bytes(path)
            identity = self._workspace.object_identity_digest(path)
        except (OSError, KeyError):
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
                    "value": {"value": hashlib.sha256(raw).hexdigest()},
                },
                "object_identity_digest": {
                    "kind": "PRESENT",
                    "value": {"value": identity},
                },
                "object_kind": "FILE",
                "supported": True,
            }
        )


def _open_environment(tmp_path: Path, name: str) -> ControlDatabase:
    database = open_control_database(tmp_path / f"{name}.db")
    assert apply_migrations(database, _ALL_MIGRATIONS).kind == "APPLIED"
    _seed_approval_chain(database)
    return database


def persistence_transaction(transaction_id: str) -> PersistenceTransactionV1:
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
        run_deadline=CanonicalTimestampV1.parse(_DEADLINE),
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
    backup_ref: dict[str, object] | None = None,
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
        backup = (
            backup_ref
            if backup_ref is not None
            else {
                "kind": "PRESENT",
                "value": {
                    "artifact_id": "BACKUP-" + preimage_digest,
                    "digest": {"value": preimage_digest},
                },
            }
        )
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


def _seed_transaction(
    database: ControlDatabase,
    workspace: SpyWorkspace,
    *,
    records: tuple[PersistencePathRecordV1, ...] | None = None,
    transaction_id: str = "tx-1",
) -> None:
    """One PREPARED transaction with the declared frozen records."""
    if records is None:
        records = _matrix_records()
    transaction_repository = PersistenceTransactionRepositoryV1(database)
    path_repository = PersistencePathRecordRepositoryV1(database)
    transaction = transaction_repository.create(persistence_transaction(transaction_id))
    for record in records:
        path_repository.append(transaction.transaction_id, record)


def _matrix_records() -> tuple[PersistencePathRecordV1, ...]:
    return (
        path_record(
            1, "src/a.py", postimage_digest=hashlib.sha256(_BODY_A).hexdigest()
        ),
        path_record(2, "src/b.py", operation="REPLACE"),
    )


@pytest.fixture
def workspace() -> SpyWorkspace:
    return SpyWorkspace()


@pytest.fixture
def recovery(
    database: ControlDatabase,
    workspace: SpyWorkspace,
    tmp_path: Path,
) -> RecoveryPreviewService:
    from vespercode.persistence.artifacts import PersistenceArtifactStoreV1

    workspace.seed("src/b.py", _ORIGINAL_B)
    _seed_transaction(database, workspace)
    return RecoveryPreviewService(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=PersistenceArtifactStoreV1(tmp_path / "artifacts"),
        workspace_identity_digest=_WORKSPACE_DIGEST,
        observer=SpyObserver(workspace),
    )


def test_recovery_preview_is_read_only(
    recovery: RecoveryPreviewService,
    workspace: SpyWorkspace,
) -> None:
    preview = recovery.preview_transaction("tx-1")
    assert preview.disposition in ("COMMITTED", "ROLLED_BACK", "UNRESOLVED")
    assert workspace.write_count == 0


def test_recovery_decision_matrix(
    database: ControlDatabase,
    tmp_path: Path,
) -> None:
    """The exact §5.1-Expected (26.B) matrix: only completely proven
    all-postimage is ``COMMITTED``, all-preimage is ``ROLLED_BACK``, and
    every mixed, missing, ambiguous, corrupt, or external-change state is
    ``UNRESOLVED`` (the fail-closed default)."""
    from vespercode.persistence.artifacts import PersistenceArtifactStoreV1

    def preview(
        workspace: SpyWorkspace,
        *,
        backups: dict[str, bytes] | None = None,
        records: tuple[PersistencePathRecordV1, ...] | None = None,
    ) -> RecoveryDispositionV1:
        case_index = _matrix_index[0]
        _matrix_index[0] += 1
        fresh = _open_environment(tmp_path, f"matrix-{case_index}")
        artifact_store = PersistenceArtifactStoreV1(
            tmp_path / f"artifacts-{case_index}"
        )
        if backups is not None:
            for digest, body in backups.items():
                artifact_store.put("BACKUP", body)
                assert artifact_store.resolve("BACKUP", digest).artifact_id.startswith(
                    "BACKUP-"
                )
        _seed_transaction(fresh, workspace, records=records)
        service = RecoveryPreviewService(
            transaction_repository=PersistenceTransactionRepositoryV1(fresh),
            path_repository=PersistencePathRecordRepositoryV1(fresh),
            artifact_store=artifact_store,
            workspace_identity_digest=_WORKSPACE_DIGEST,
            observer=SpyObserver(workspace),
        )
        try:
            return service.preview_transaction("tx-1").disposition
        finally:
            fresh.close()

    backups = {_PREIMAGE_DIGEST: _ORIGINAL_B}

    # All-postimage evidence: every path exactly matches its postimage.
    committed_workspace = SpyWorkspace()
    committed_workspace.seed("src/a.py", _BODY_A)
    committed_workspace.seed("src/b.py", _BODY_B)
    assert preview(committed_workspace, backups=backups) == "COMMITTED"

    # All-preimage evidence: every path exactly matches its preimage
    # (including the unapplied CREATE as ABSENT).
    rolled_workspace = SpyWorkspace()
    rolled_workspace.seed("src/b.py", _ORIGINAL_B)
    assert preview(rolled_workspace, backups=backups) == "ROLLED_BACK"

    # A CREATE path exactly at its postimage is restorable to ABSENT
    # (SPEC 4.6 / AC-29 safe ABSENT rollback) -> ROLLED_BACK.
    create_applied = SpyWorkspace()
    create_applied.seed("src/a.py", _BODY_A)
    create_applied.seed("src/b.py", _ORIGINAL_B)
    assert preview(create_applied, backups=backups) == "ROLLED_BACK"

    # Mixed evidence (one postimage, one preimage) is contradictory and
    # never coerced into a terminal safe disposition.
    mixed = SpyWorkspace()
    mixed.seed("src/a.py", _ORIGINAL_A)
    mixed.seed("src/b.py", _BODY_B)
    assert preview(mixed, backups=backups) == "UNRESOLVED"

    # External change: unknown bytes at a path classify UNRESOLVED.
    external = SpyWorkspace()
    external.seed("src/a.py", _EXTERNAL_A)
    external.seed("src/b.py", _ORIGINAL_B)
    assert preview(external, backups=backups) == "UNRESOLVED"

    # Identity drift: preimage bytes behind a replaced object identity
    # classify UNRESOLVED (byte text alone never authorizes).
    identity_drift = SpyWorkspace()
    identity_drift.seed("src/b.py", _ORIGINAL_B, identity=_OTHER_IDENTITY_DIGEST)
    assert preview(identity_drift, backups=backups) == "UNRESOLVED"

    # Missing backup: a REPLACE record whose backup artifact is absent
    # classifies UNRESOLVED (SPEC 4.6: 缺失备份).
    assert preview(rolled_workspace, backups=None) == "UNRESOLVED"

    # Unprovable observation: a failed identity read classifies
    # UNRESOLVED.
    unprovable = SpyWorkspace()
    unprovable.seed("src/b.py", _ORIGINAL_B)
    unprovable.break_identity("src/b.py")
    assert preview(unprovable, backups=backups) == "UNRESOLVED"

    # Corrupt artifact: the backup envelope fails verified metadata and
    # the path cannot be proven -> UNRESOLVED.
    corrupt = SpyWorkspace()
    corrupt.seed("src/b.py", _ORIGINAL_B)
    fresh = _open_environment(tmp_path, "matrix-corrupt")
    artifact_store = PersistenceArtifactStoreV1(tmp_path / "artifacts-corrupt")
    artifact_store.put("BACKUP", _ORIGINAL_B)
    artifact_store.artifact_path(
        artifact_store.resolve("BACKUP", _PREIMAGE_DIGEST)
    ).write_bytes(b"corrupted")
    _seed_transaction(fresh, corrupt)
    service = RecoveryPreviewService(
        transaction_repository=PersistenceTransactionRepositoryV1(fresh),
        path_repository=PersistencePathRecordRepositoryV1(fresh),
        artifact_store=artifact_store,
        workspace_identity_digest=_WORKSPACE_DIGEST,
        observer=SpyObserver(corrupt),
    )
    assert service.preview_transaction("tx-1").disposition == "UNRESOLVED"
    fresh.close()


_matrix_index: list[int] = [0]
