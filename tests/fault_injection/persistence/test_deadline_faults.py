"""T26.2 legacy step 26.C: production deadline fault matrix.

Pins the run-deadline semantics across the production protocol: the
writeback checks the deadline before every authoritative workspace write
(expiry before the first write stops with zero writes and a durable
ROLLED_BACK; expiry after a replace stops with no further writes and a
durable UNRESOLVED / RECOVERY_REQUIRED), and the recovery apply refuses
any authoritative workspace change after the deadline while still
recording a no-change service-proven terminal (SPEC 4.6 item 11:
deadline 后只允许持久化该控制面终态，不得再修改权威工作区).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

pytest.importorskip("pydantic")

from vespercode.candidate.final_diff import (
    FinalDiffEntryV1,
    FinalDiffPreimageV1,
    FinalDiffV1,
)
from vespercode.canonical.clock import FakeClockV1
from vespercode.canonical.digest import domain_digest
from vespercode.canonical.json_v1 import CanonicalValueV1
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import DigestV1
from vespercode.contracts.run import WaitContextV1, WaitDecisionV1
from vespercode.governance.writeback_approval import (
    WritebackApprovalRepository,
)
from vespercode.governance.writeback_decision import (
    DecideFinalWritebackV1,
    FinalWritebackApprovalV1,
    FinalWritebackDecisionServiceV1,
)
from vespercode.governance.writeback_subject import (
    FinalWritebackBindingV1,
    FinalWritebackSubjectV1,
    build_final_writeback_subject,
)
from vespercode.persistence.artifacts import PersistenceArtifactStoreV1
from vespercode.persistence.recovery import RecoveryService
from vespercode.persistence.recovery_apply import (
    ApplyRecoveryV1,
    RecoveryApplyService,
    RecoveryResultRepositoryV1,
)
from vespercode.persistence.recovery_preview import (
    RecoveryPathObservationV1,
    RecoveryPreviewService,
)
from vespercode.workspace.identity_win32 import WorkspaceIdentityV1
from vespercode.persistence.transaction import (
    PersistencePathRecordRepositoryV1,
    PersistenceTransactionRepositoryV1,
    PersistenceTransactionV1,
)
from vespercode.persistence.writeback import (
    PersistenceCommandFactoryV1,
    PersistenceCoordinator,
    PersistVerifiedCandidateV1,
    WritebackBodyV1,
)
from vespercode.profiles.reference import (
    ReferenceProfileManifestV1,
    load_reference_profile,
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
from vespercode.storage.migrations.v0012_recovery import (
    RECOVERY_V1_MIGRATION,
)
from vespercode.storage.run_repository import RunRepository
from vespercode.trees.text_classifier import TextMetadataV1

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

_CREATED_AT = CanonicalTimestampV1("2026-08-05T09:00:00.000Z")
_EXPIRES_AT = CanonicalTimestampV1("2026-08-05T09:05:00.000Z")
_DECIDED_AT = CanonicalTimestampV1("2026-08-05T09:01:00.000Z")
_CONSUMED_AT = CanonicalTimestampV1("2026-08-05T09:02:00.000Z")
_RUN_DEADLINE = CanonicalTimestampV1("2026-08-05T09:15:00.000Z")
_LATE_EXPIRES_AT = CanonicalTimestampV1("2026-08-05T09:30:00.000Z")
_REFERENCE_MANIFEST = (
    Path(__file__).resolve().parents[3] / "reference/manifest/reference-profile-v1.json"
)

_SNAPSHOT_DIGEST = hashlib.sha256(b"sealed-snapshot").hexdigest()
_CANDIDATE_DIGEST = hashlib.sha256(b"verified-candidate").hexdigest()
_VALIDATION_DIGEST = hashlib.sha256(b"validation-manifest").hexdigest()
_FORMAL_EVIDENCE_DIGEST = hashlib.sha256(b"formal-evidence").hexdigest()
_PREIMAGE_DIGEST = hashlib.sha256(b"original b\n").hexdigest()
_WORKSPACE_PREIMAGE_DIGEST = hashlib.sha256(b"frozen-workspace-preimage").hexdigest()
_RUN_CONFIG_DIGEST = hashlib.sha256(b"run-config").hexdigest()
_WORKSPACE_IDENTITY_DIGEST = "55" * 32
_IDENTITY_DIGEST = "44" * 32
_TEXT_METADATA = TextMetadataV1(encoding="UTF8", newline="LF", final_newline=True)

_BODIES = {
    "src/a.py": b"new a\n",
    "src/b.py": b"new b\n",
    "src/c.py": b"new c\n",
}
_ORIGINAL = b"original b\n"


def manifest() -> ReferenceProfileManifestV1:
    loaded = load_reference_profile(_REFERENCE_MANIFEST.read_bytes())
    assert isinstance(loaded, ReferenceProfileManifestV1)
    return loaded


_MANIFEST = manifest()
_EDITABLE_DIGEST = _MANIFEST.editable_path_policy.digest


def _canonical_entry(entry: FinalDiffEntryV1) -> dict[str, CanonicalValueV1]:
    if entry.preimage.kind == "ABSENT":
        preimage: CanonicalValueV1 = {"kind": "ABSENT"}
    else:
        content_digest = entry.preimage.content_digest
        metadata = entry.preimage.text_metadata
        assert content_digest is not None
        assert metadata is not None
        preimage = {
            "kind": "PRESENT",
            "content_digest": content_digest,
            "text_metadata": {
                "encoding": metadata.encoding,
                "newline": metadata.newline,
                "final_newline": metadata.final_newline,
            },
        }
    post_metadata = entry.postimage_text_metadata
    return {
        "operation": entry.operation,
        "path": entry.path.value,
        "preimage": preimage,
        "postimage_digest": entry.postimage_digest,
        "postimage_text_metadata": {
            "encoding": post_metadata.encoding,
            "newline": post_metadata.newline,
            "final_newline": post_metadata.final_newline,
        },
    }


def final_diff(paths: tuple[str, ...]) -> FinalDiffV1:
    """One sealed diff: first path CREATE, the rest REPLACE."""
    entries: list[FinalDiffEntryV1] = []
    for index, path in enumerate(paths):
        if index == 0:
            entries.append(
                FinalDiffEntryV1(
                    operation="CREATE",
                    path=CanonicalRelativePathV1(path),
                    preimage=FinalDiffPreimageV1(kind="ABSENT"),
                    postimage_digest=hashlib.sha256(_BODIES[path]).hexdigest(),
                    postimage_text_metadata=_TEXT_METADATA,
                )
            )
        else:
            entries.append(
                FinalDiffEntryV1(
                    operation="REPLACE",
                    path=CanonicalRelativePathV1(path),
                    preimage=FinalDiffPreimageV1(
                        kind="PRESENT",
                        content_digest=_PREIMAGE_DIGEST,
                        text_metadata=_TEXT_METADATA,
                    ),
                    postimage_digest=hashlib.sha256(_BODIES[path]).hexdigest(),
                    postimage_text_metadata=_TEXT_METADATA,
                )
            )
    digest = domain_digest(
        "FinalDiffV1",
        1,
        {
            "schema_version": 1,
            "snapshot_tree_digest": _SNAPSHOT_DIGEST,
            "entries": tuple(_canonical_entry(entry) for entry in entries),
            "added_and_replacement_text_bytes": sum(
                len(_BODIES[entry.path.value]) for entry in entries
            ),
        },
    )
    return FinalDiffV1(
        schema_version=1,
        snapshot_tree_digest=_SNAPSHOT_DIGEST,
        entries=tuple(entries),
        added_and_replacement_text_bytes=sum(
            len(_BODIES[entry.path.value]) for entry in entries
        ),
        digest=digest,
    )


def subject_for(diff: FinalDiffV1) -> FinalWritebackSubjectV1:
    return build_final_writeback_subject(
        FinalWritebackBindingV1(
            run_id="run-1",
            candidate_digest=_CANDIDATE_DIGEST,
            final_diff=diff,
            validation_manifest_digest=_VALIDATION_DIGEST,
            validation_repository_policy_digest=_EDITABLE_DIGEST,
            formal_evidence_digest=_FORMAL_EVIDENCE_DIGEST,
            workspace_preimage_digest=_WORKSPACE_PREIMAGE_DIGEST,
            run_config_digest=_RUN_CONFIG_DIGEST,
            run_config_reference_profile_digest=_MANIFEST.digest,
            run_config_policy_id="PYTHON_SRC_ONLY_V1",
            reference_profile_digest=_MANIFEST.digest,
            reference_policy_digest=_EDITABLE_DIGEST,
            policy=_MANIFEST.editable_path_policy,
        ),
        _LATE_EXPIRES_AT,
    )


_DIFF_TWO = final_diff(("src/a.py", "src/b.py"))
_DIFF_THREE = final_diff(("src/a.py", "src/b.py", "src/c.py"))
_SUBJECT_TWO = subject_for(_DIFF_TWO)
_SUBJECT_THREE = subject_for(_DIFF_THREE)


def _seed_run_and_approval(
    database: ControlDatabase, subject: FinalWritebackSubjectV1
) -> None:
    with database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots"
            " (config_snapshot_id, digest, llm_profile_id, reference_profile_id,"
            " policy_id, target_test_ids, limits_digest, frozen_at)"
            " VALUES ('snap-1', ?, 'mock-deterministic-v1', 'python-src-py312-v1',"
            " 'PYTHON_SRC_ONLY_V1', '[]', ?, ?)",
            ("a" * 64, "c" * 64, _CREATED_AT.value),
        )
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES ('run-1', 'ws-1', 'snap-1', 'WAITING_USER', NULL, 1, ?, ?)",
            (_CREATED_AT.value, _RUN_DEADLINE.value),
        )
    RunRepository(database).create_wait(
        WaitContextV1(
            wait_id="wait-1",
            run_id="run-1",
            wait_kind="FINAL_WRITEBACK",
            source_phase="FORMAL_VALIDATION",
            subject_digest=DigestV1(value=subject.digest),
            created_at=_CREATED_AT,
            expires_at=subject.expires_at,
        )
    )
    result = FinalWritebackDecisionServiceV1(database).decide(
        DecideFinalWritebackV1(
            decision=WaitDecisionV1(
                wait_id="wait-1",
                run_id="run-1",
                wait_kind="FINAL_WRITEBACK",
                subject_digest=DigestV1(value=subject.digest),
                decision="APPROVE",
                event_id="evt-approve",
                decided_at=_DECIDED_AT,
            ),
            subject=subject,
            approval_id="approval-1",
        )
    )
    assert result.kind == "APPROVED"


class StepClock:
    """A deterministic clock that expires exactly after ``limit`` calls."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._calls = 0
        self._before = CanonicalTimestampV1("2026-08-05T09:14:00.000Z")
        self._after = CanonicalTimestampV1("2026-08-05T09:17:00.000Z")

    def now(self) -> CanonicalTimestampV1:
        self._calls += 1
        return self._before if self._calls <= self._limit else self._after


class SpyWorkspace:
    """In-memory workspace satisfying the writeback and recovery ports."""

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}
        self._identities: dict[str, str] = {}
        self._writes: list[str] = []
        self._deletes: list[str] = []
        self._untouched_ok = True

    def seed(self, path: str, body: bytes, identity: str = _IDENTITY_DIGEST) -> None:
        self._files[path] = body
        self._identities[path] = identity

    def identity_digest(self) -> str:
        return _WORKSPACE_IDENTITY_DIGEST

    def lease_held(self) -> bool:
        return True

    def verify_untouched(
        self, snapshot_tree_digest: str, involved_paths: tuple[str, ...]
    ) -> bool:
        return self._untouched_ok

    def flip_untouched(self) -> None:
        self._untouched_ok = False

    def workspace_path(self) -> str:
        return "C:\\work\\vesper"

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

    def verify_postimage(self, path: CanonicalRelativePathV1, digest: str) -> bool:
        if path.value not in self._files:
            return False
        return hashlib.sha256(self._files[path.value]).hexdigest() == digest

    def replace(self, path: CanonicalRelativePathV1, body: bytes) -> None:
        self._files[path.value] = body
        self._writes.append(path.value)
        # A replaced file provably carries a new object identity (the real
        # port's os.replace does the same), so recovery observations of a
        # replaced path stay provable.
        self._identities.setdefault(path.value, _IDENTITY_DIGEST)

    def delete(self, path: CanonicalRelativePathV1) -> None:
        del self._files[path.value]
        self._deletes.append(path.value)

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
                    "value": {"value": self._identities[path.value]},
                },
                "object_kind": "FILE",
                "supported": True,
            }
        )

    @property
    def write_count(self) -> int:
        return len(self._writes) + len(self._deletes)

    @property
    def files(self) -> dict[str, bytes]:
        return dict(self._files)


def _open_environment(tmp_path: Path, name: str) -> ControlDatabase:
    database = open_control_database(tmp_path / f"{name}.db")
    assert apply_migrations(database, _ALL_MIGRATIONS).kind == "APPLIED"
    return database


def _command(
    diff: FinalDiffV1,
    subject: FinalWritebackSubjectV1,
    event_id: str,
) -> PersistVerifiedCandidateV1:
    approval = FinalWritebackApprovalV1(
        schema_version=1,
        approval_id="approval-1",
        subject_digest=DigestV1(value=subject.digest),
        run_id="run-1",
        wait_id="wait-1",
        created_at=_DECIDED_AT,
        status="PENDING",
    )
    return PersistenceCommandFactoryV1(
        final_diff=diff,
        candidate_digest=_CANDIDATE_DIGEST,
        policy_digest=_EDITABLE_DIGEST,
        workspace_identity_digest=_WORKSPACE_IDENTITY_DIGEST,
        workspace_preimage_digest=_WORKSPACE_PREIMAGE_DIGEST,
        approval=approval,
        approval_subject=subject,
        run_deadline=_RUN_DEADLINE,
        postimage_bodies=tuple(
            WritebackBodyV1(
                schema_version=1,
                path=CanonicalRelativePathV1(path),
                operation=("CREATE" if index == 0 else "REPLACE"),
                body=_BODIES[path],
            )
            for index, path in enumerate(entry.path.value for entry in diff.entries)
        ),
    ).for_approved_run(run_id="run-1", approval_id="approval-1", event_id=event_id)


def _coordinator(
    database: ControlDatabase,
    workspace: SpyWorkspace,
    tmp_path: Path,
    clock: object,
) -> PersistenceCoordinator:
    return PersistenceCoordinator(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=PersistenceArtifactStoreV1(tmp_path / "artifacts"),
        approval_repository=WritebackApprovalRepository(database),
        workspace=workspace,
        policy=_MANIFEST.editable_path_policy,
        clock=clock,  # type: ignore[arg-type]
    )


def _approval_status(database: ControlDatabase) -> str:
    with database.immediate_transaction() as tx:
        row = tx.execute(
            "SELECT status FROM writeback_approvals WHERE approval_id = 'approval-1'"
        ).fetchone()
    assert row is not None
    return str(row[0])


def _transaction_state(database: ControlDatabase) -> tuple[str, ...]:
    with database.immediate_transaction() as tx:
        rows = tx.execute(
            "SELECT state FROM persistence_transactions ORDER BY rowid"
        ).fetchall()
    return tuple(str(row[0]) for row in rows)


def test_writeback_deadline_matrix(tmp_path: Path) -> None:
    """Every deadline stop point of the writeback protocol is honest:
    zero writes with a durable ROLLED_BACK before the first write, and
    exactly the completed writes with a durable UNRESOLVED afterwards."""
    # Deadline expired before the first write: zero writes, durable
    # ROLLED_BACK, approval stays PENDING, outcome STOPPED.
    database = _open_environment(tmp_path, "deadline-zero")
    _seed_run_and_approval(database, _SUBJECT_TWO)
    workspace = SpyWorkspace()
    workspace.seed("src/b.py", _ORIGINAL)
    late_clock = FakeClockV1.from_epoch_milliseconds(
        _RUN_DEADLINE.epoch_milliseconds + 1
    )
    result = _coordinator(database, workspace, tmp_path, late_clock).persist(
        _command(_DIFF_TWO, _SUBJECT_TWO, "evt-deadline-zero")
    )
    assert result.outcome == "STOPPED" and result.error_code is None
    assert workspace.write_count == 0
    assert _approval_status(database) == "PENDING"
    assert _transaction_state(database) == ("ROLLED_BACK",)
    database.close()

    # Deadline expiring between the first and second replace of a 2-path
    # transaction: exactly one write, no further writes, durable
    # UNRESOLVED, outcome RECOVERY_REQUIRED.
    database = _open_environment(tmp_path, "deadline-mid-two")
    _seed_run_and_approval(database, _SUBJECT_TWO)
    workspace = SpyWorkspace()
    workspace.seed("src/b.py", _ORIGINAL)
    result = _coordinator(database, workspace, tmp_path, StepClock(limit=6)).persist(
        _command(_DIFF_TWO, _SUBJECT_TWO, "evt-deadline-mid-two")
    )
    assert result.outcome == "RECOVERY_REQUIRED"
    assert result.error_code == "PERSISTENCE_UNCERTAIN"
    assert workspace.write_count == 1
    assert workspace.files == {
        "src/a.py": _BODIES["src/a.py"],
        "src/b.py": _ORIGINAL,
    }
    assert _transaction_state(database) == ("UNRESOLVED",)
    database.close()

    # Deadline crossing between the step-11 check and the first replace
    # (after the WRITING transition, still zero writes): the provably
    # zero-write transaction ends ROLLED_BACK with outcome STOPPED
    # (SPEC 4.6 item 11; review I-1).
    database = _open_environment(tmp_path, "deadline-window-zero")
    _seed_run_and_approval(database, _SUBJECT_TWO)
    workspace = SpyWorkspace()
    workspace.seed("src/b.py", _ORIGINAL)
    result = _coordinator(database, workspace, tmp_path, StepClock(limit=5)).persist(
        _command(_DIFF_TWO, _SUBJECT_TWO, "evt-deadline-window-zero")
    )
    assert result.outcome == "STOPPED" and result.error_code is None
    assert workspace.write_count == 0
    assert workspace.files == {"src/b.py": _ORIGINAL}
    assert _transaction_state(database) == ("ROLLED_BACK",)
    database.close()

    # Deadline expiring between the second and third replace of a 3-path
    # transaction: exactly two writes and a durable UNRESOLVED.
    database = _open_environment(tmp_path, "deadline-mid-three")
    _seed_run_and_approval(database, _SUBJECT_THREE)
    workspace = SpyWorkspace()
    workspace.seed("src/b.py", _ORIGINAL)
    workspace.seed("src/c.py", _ORIGINAL)
    result = _coordinator(database, workspace, tmp_path, StepClock(limit=7)).persist(
        _command(_DIFF_THREE, _SUBJECT_THREE, "evt-deadline-mid-three")
    )
    assert result.outcome == "RECOVERY_REQUIRED"
    assert result.error_code == "PERSISTENCE_UNCERTAIN"
    assert workspace.write_count == 2
    assert workspace.files == {
        "src/a.py": _BODIES["src/a.py"],
        "src/b.py": _BODIES["src/b.py"],
        "src/c.py": _ORIGINAL,
    }
    assert _transaction_state(database) == ("UNRESOLVED",)
    database.close()


def identity_for_workspace_digest() -> WorkspaceIdentityV1:
    """One sealed identity whose digest matches the test workspace."""
    return WorkspaceIdentityV1(
        schema_version=1,
        canonical_absolute_path="C:\\work\\vesper",
        volume_serial_number=1,
        final_object_file_id_128_hex="01" * 16,
        final_object_kind="DIRECTORY",
        link_count=1,
        acl_observable=True,
        digest=_WORKSPACE_IDENTITY_DIGEST,
    )


def test_recovery_applies_durable_unresolved_transaction(tmp_path: Path) -> None:
    """SPEC 4.6 item 10: a durable UNRESOLVED transaction (mid-writeback
    deadline fault) is resolved only by explicit recovery — the ROLLED_BACK
    apply deletes the applied CREATE and records the terminal
    (quality review M-4)."""
    import json

    from tests.fault_injection.persistence.test_external_change_faults import (
        SpyLease,
    )

    # Mid-writeback deadline fault: a.py replaced+verified, b.py at
    # preimage, transaction durable UNRESOLVED.
    database = _open_environment(tmp_path, "unresolved-recovery")
    _seed_run_and_approval(database, _SUBJECT_TWO)
    workspace = SpyWorkspace()
    workspace.seed("src/b.py", _ORIGINAL)
    result = _coordinator(database, workspace, tmp_path, StepClock(limit=6)).persist(
        _command(_DIFF_TWO, _SUBJECT_TWO, "evt-unresolved-recovery")
    )
    assert result.outcome == "RECOVERY_REQUIRED"
    assert _transaction_state(database) == ("UNRESOLVED",)
    assert workspace.files == {
        "src/a.py": _BODIES["src/a.py"],
        "src/b.py": _ORIGINAL,
    }

    # Explicit recovery of the UNRESOLVED transaction: preview ROLLED_BACK,
    # apply deletes the applied CREATE and records the terminal.
    store = PersistenceArtifactStoreV1(tmp_path / "artifacts")
    preview_service = RecoveryPreviewService(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=store,
        workspace_identity_digest=_WORKSPACE_IDENTITY_DIGEST,
        observer=workspace,
    )
    apply_service = RecoveryApplyService(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=store,
        preview_service=preview_service,
        workspace=workspace,
        lease=SpyLease(),
        results=RecoveryResultRepositoryV1(database),
        clock=FakeClockV1.from_epoch_milliseconds(_CONSUMED_AT.epoch_milliseconds),
        workspace_identity_digest=_WORKSPACE_IDENTITY_DIGEST,
    )
    recovery = RecoveryService(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        preview_service=preview_service,
        apply_service=apply_service,
    )
    preview = recovery.preview(identity_for_workspace_digest())
    assert preview.disposition == "ROLLED_BACK"
    applied = recovery.apply(
        ApplyRecoveryV1(
            schema_version=1,
            transaction_id=preview.transaction_id,
            workspace_identity_digest=_WORKSPACE_IDENTITY_DIGEST,
            preview_digest=preview.preview_digest,
            requested_disposition="ROLLED_BACK",
            explicit_apply=True,
        )
    )
    assert applied.error_code is None and applied.disposition == "ROLLED_BACK"
    assert applied.changed_paths == ("src/a.py",)
    assert workspace.files == {"src/b.py": _ORIGINAL}
    with database.immediate_transaction() as tx:
        state = tx.execute(
            "SELECT state FROM persistence_transactions WHERE transaction_id = ?",
            (preview.transaction_id,),
        ).fetchone()
        row = tx.execute(
            "SELECT disposition, changed_paths FROM recovery_results"
        ).fetchone()
    assert str(state[0]) == "ROLLED_BACK"
    assert str(row[0]) == "ROLLED_BACK"
    assert json.loads(str(row[1])) == ["src/a.py"]
    database.close()


def test_recovery_apply_deadline_faults(tmp_path: Path) -> None:
    """After the deadline only the no-change control-plane terminal may
    persist: a restore that needs workspace changes is refused, while an
    all-postimage COMMITTED terminal is still recorded."""
    from tests.fault_injection.persistence.test_external_change_faults import (
        SpyLease,
    )

    def build_recovery(
        database: ControlDatabase,
        workspace: SpyWorkspace,
        deadline: str,
    ) -> RecoveryService:
        store = PersistenceArtifactStoreV1(tmp_path / "artifacts-recovery")
        preview_service = RecoveryPreviewService(
            transaction_repository=PersistenceTransactionRepositoryV1(database),
            path_repository=PersistencePathRecordRepositoryV1(database),
            artifact_store=store,
            workspace_identity_digest=_WORKSPACE_IDENTITY_DIGEST,
            observer=workspace,
        )
        apply_service = RecoveryApplyService(
            transaction_repository=PersistenceTransactionRepositoryV1(database),
            path_repository=PersistencePathRecordRepositoryV1(database),
            artifact_store=store,
            preview_service=preview_service,
            workspace=workspace,
            lease=SpyLease(),
            results=RecoveryResultRepositoryV1(database),
            clock=FakeClockV1.from_epoch_milliseconds(
                CanonicalTimestampV1.parse(deadline).epoch_milliseconds
            ),
            workspace_identity_digest=_WORKSPACE_IDENTITY_DIGEST,
        )
        return RecoveryService(
            transaction_repository=PersistenceTransactionRepositoryV1(database),
            preview_service=preview_service,
            apply_service=apply_service,
        )

    def seed_recovery_transaction(
        database: ControlDatabase,
        workspace: SpyWorkspace,
        *,
        deadline: str,
        backups: bool,
    ) -> None:
        from vespercode.persistence.path_record import PersistencePathRecordV1

        def record(
            sequence: int,
            path: str,
            operation: str,
            postimage_digest: str,
        ) -> PersistencePathRecordV1:
            if operation == "CREATE":
                preimage: dict[str, object] = {"kind": "ABSENT"}
                backup: dict[str, object] = {"kind": "ABSENT"}
            else:
                preimage = {
                    "kind": "PRESENT",
                    "raw_bytes_digest": _PREIMAGE_DIGEST,
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
                        "artifact_id": "BACKUP-" + _PREIMAGE_DIGEST,
                        "digest": {"value": _PREIMAGE_DIGEST},
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
                        "required_object_policy_digest": _EDITABLE_DIGEST,
                    },
                    "sequence": sequence,
                    "durable_state": "NOT_STARTED",
                    "backup_ref": backup,
                    "last_evidence_digest": {"kind": "ABSENT"},
                }
            )

        transaction_repository = PersistenceTransactionRepositoryV1(database)
        path_repository = PersistencePathRecordRepositoryV1(database)
        transaction = transaction_repository.create(
            PersistenceTransactionV1(
                schema_version=1,
                transaction_id="tx-1",
                run_id="run-1",
                approval_id="approval-1",
                workspace_identity_digest=_WORKSPACE_IDENTITY_DIGEST,
                workspace_path="C:\\work\\vesper",
                final_diff_digest="66" * 32,
                policy_digest=_EDITABLE_DIGEST,
                state="PREPARED",
                run_deadline=CanonicalTimestampV1.parse(deadline),
                prepared_at=CanonicalTimestampV1.parse("2026-08-05T09:00:00.000Z"),
                updated_at=CanonicalTimestampV1.parse("2026-08-05T09:00:00.000Z"),
                workspace_write_count=0,
            )
        )
        path_repository.append(
            transaction.transaction_id,
            record(
                1,
                "src/a.py",
                "CREATE",
                hashlib.sha256(_BODIES["src/a.py"]).hexdigest(),
            ),
        )
        path_repository.append(
            transaction.transaction_id,
            record(
                2,
                "src/b.py",
                "REPLACE",
                hashlib.sha256(_BODIES["src/b.py"]).hexdigest(),
            ),
        )
        if backups:
            PersistenceArtifactStoreV1(tmp_path / "artifacts-recovery").put(
                "BACKUP", _ORIGINAL
            )

    def command(preview_digest: str, disposition: str) -> ApplyRecoveryV1:
        return ApplyRecoveryV1(
            schema_version=1,
            transaction_id="tx-1",
            workspace_identity_digest=_WORKSPACE_IDENTITY_DIGEST,
            preview_digest=preview_digest,
            requested_disposition=disposition,  # type: ignore[arg-type]
            explicit_apply=True,
        )

    def preview_digest(database: ControlDatabase, workspace: SpyWorkspace) -> str:
        store = PersistenceArtifactStoreV1(tmp_path / "artifacts-recovery")
        preview_service = RecoveryPreviewService(
            transaction_repository=PersistenceTransactionRepositoryV1(database),
            path_repository=PersistencePathRecordRepositoryV1(database),
            artifact_store=store,
            workspace_identity_digest=_WORKSPACE_IDENTITY_DIGEST,
            observer=workspace,
        )
        return preview_service.preview_transaction("tx-1").preview_digest

    # Expired deadline + restore needed: the ROLLED_BACK apply refuses
    # every authoritative workspace change and records no terminal.
    database = _open_environment(tmp_path, "recovery-deadline-expired")
    _seed_run_and_approval(database, _SUBJECT_TWO)
    workspace = SpyWorkspace()
    workspace.seed("src/b.py", _BODIES["src/b.py"])
    seed_recovery_transaction(
        database, workspace, deadline="2026-08-05T09:03:00.000Z", backups=True
    )
    service = build_recovery(database, workspace, "2026-08-05T09:04:00.000Z")
    digest = preview_digest(database, workspace)
    result = service.apply(command(digest, "ROLLED_BACK"))
    assert result.error_code == "RECOVERY_UNRESOLVED"
    assert result.changed_paths == () and result.workspace_write_count == 0
    assert workspace.files == {"src/b.py": _BODIES["src/b.py"]}
    with database.immediate_transaction() as tx:
        rows = tx.execute("SELECT COUNT(*) FROM recovery_results").fetchone()
    assert int(rows[0]) == 0
    database.close()

    # Expired deadline + all postimages: the no-change COMMITTED terminal
    # is still recorded (only the control-plane terminal persists).
    database = _open_environment(tmp_path, "recovery-deadline-committed")
    _seed_run_and_approval(database, _SUBJECT_TWO)
    workspace = SpyWorkspace()
    workspace.seed("src/a.py", _BODIES["src/a.py"])
    workspace.seed("src/b.py", _BODIES["src/b.py"])
    seed_recovery_transaction(
        database, workspace, deadline="2026-08-05T09:03:00.000Z", backups=True
    )
    service = build_recovery(database, workspace, "2026-08-05T09:04:00.000Z")
    digest = preview_digest(database, workspace)
    committed = service.apply(command(digest, "COMMITTED"))
    assert committed.error_code is None and committed.disposition == "COMMITTED"
    assert committed.workspace_write_count == 0
    with database.immediate_transaction() as tx:
        row = tx.execute(
            "SELECT state FROM persistence_transactions WHERE transaction_id = 'tx-1'"
        ).fetchone()
        results = tx.execute("SELECT COUNT(*) FROM recovery_results").fetchone()
    assert str(row[0]) == "COMMITTED"
    assert int(results[0]) == 1
    database.close()
