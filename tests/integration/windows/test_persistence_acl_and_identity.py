"""T26.2 legacy step 26.C: real Windows persistence ACL/identity production proof.

Runs only under ``-m windows_integration`` on the project Windows host.
Proves the production protocol with real NTFS objects and Win32
machinery: the full approval-bound writeback commits real files with
current-user-only artifact ACLs; an interrupted writeback is recovered
under the real workspace mutex; external byte changes, replaced object
identities, widened artifact ACLs, and expired deadlines are never
overwritten and stay UNRESOLVED; and the recovery apply refuses to run
when another holder owns the lease.  Every handle and lease is closed
and every artifact is ACL-probed on real NTFS (SPEC 4.6 / AC-07 /
AC-21–22 / AC-29 / AC-31).
"""

from __future__ import annotations

import ctypes
import hashlib
import threading
from pathlib import Path

import pytest

from ctypes import wintypes

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
from vespercode.persistence.artifacts import (
    PersistenceArtifactStoreV1,
)
from vespercode.persistence.recovery import RecoveryService
from vespercode.persistence.recovery_apply import (
    ApplyRecoveryV1,
    RealRecoveryLeasePort,
    RecoveryApplyService,
    RecoveryResultRepositoryV1,
)
from vespercode.persistence.recovery_preview import (
    RealWorkspaceObserver,
    RecoveryPathObservationV1,
    RecoveryPreviewService,
)
from vespercode.persistence.transaction import (
    PersistencePathRecordRepositoryV1,
    PersistenceTransactionRepositoryV1,
)
from vespercode.persistence.writeback import (
    ArmedFaultPort,
    PersistenceCommandFactoryV1,
    PersistenceCoordinator,
    PersistenceFaultInjectedError,
    PersistVerifiedCandidateV1,
    RealWorkspacePort,
    WritebackBodyV1,
    WritebackFaultPointV1,
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
from vespercode.trees.snapshot import SnapshotTreeV1
from vespercode.trees.text_classifier import TextMetadataV1
from vespercode.workspace.identity_win32 import (
    WorkspaceIdentityV1,
    resolve_workspace_identity,
)
from vespercode.workspace.mutex_win32 import (
    WorkspaceLeaseV1,
    WorkspaceMutex,
)

pytest.importorskip("pydantic")
pytestmark = pytest.mark.windows_integration

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
_EXPIRES_AT = CanonicalTimestampV1("2026-08-05T09:30:00.000Z")
_DECIDED_AT = CanonicalTimestampV1("2026-08-05T09:01:00.000Z")
_CONSUMED_AT = CanonicalTimestampV1("2026-08-05T09:02:00.000Z")
_RUN_DEADLINE = CanonicalTimestampV1("2026-08-05T09:15:00.000Z")
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
_TEXT_METADATA = TextMetadataV1(encoding="UTF8", newline="LF", final_newline=True)

_BODY_A = b"new a\n"
_BODY_B = b"new b\n"
_ORIGINAL_B = b"original b\n"
_FOREIGN = b"foreign external bytes\n"


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


def final_diff() -> FinalDiffV1:
    """One sealed two-path diff: CREATE src/a.py, REPLACE src/b.py."""
    entries = (
        FinalDiffEntryV1(
            operation="CREATE",
            path=CanonicalRelativePathV1("src/a.py"),
            preimage=FinalDiffPreimageV1(kind="ABSENT"),
            postimage_digest=hashlib.sha256(_BODY_A).hexdigest(),
            postimage_text_metadata=_TEXT_METADATA,
        ),
        FinalDiffEntryV1(
            operation="REPLACE",
            path=CanonicalRelativePathV1("src/b.py"),
            preimage=FinalDiffPreimageV1(
                kind="PRESENT",
                content_digest=_PREIMAGE_DIGEST,
                text_metadata=_TEXT_METADATA,
            ),
            postimage_digest=hashlib.sha256(_BODY_B).hexdigest(),
            postimage_text_metadata=_TEXT_METADATA,
        ),
    )
    digest = domain_digest(
        "FinalDiffV1",
        1,
        {
            "schema_version": 1,
            "snapshot_tree_digest": _SNAPSHOT_DIGEST,
            "entries": tuple(_canonical_entry(entry) for entry in entries),
            "added_and_replacement_text_bytes": len(_BODY_A) + len(_BODY_B),
        },
    )
    return FinalDiffV1(
        schema_version=1,
        snapshot_tree_digest=_SNAPSHOT_DIGEST,
        entries=entries,
        added_and_replacement_text_bytes=len(_BODY_A) + len(_BODY_B),
        digest=digest,
    )


_DIFF = final_diff()


def subject() -> FinalWritebackSubjectV1:
    return build_final_writeback_subject(
        FinalWritebackBindingV1(
            run_id="run-1",
            candidate_digest=_CANDIDATE_DIGEST,
            final_diff=_DIFF,
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
        _EXPIRES_AT,
    )


_SUBJECT = subject()


def _seed_run_and_approval(database: ControlDatabase) -> None:
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
            subject_digest=DigestV1(value=_SUBJECT.digest),
            created_at=_CREATED_AT,
            expires_at=_EXPIRES_AT,
        )
    )
    result = FinalWritebackDecisionServiceV1(database).decide(
        DecideFinalWritebackV1(
            decision=WaitDecisionV1(
                wait_id="wait-1",
                run_id="run-1",
                wait_kind="FINAL_WRITEBACK",
                subject_digest=DigestV1(value=_SUBJECT.digest),
                decision="APPROVE",
                event_id="evt-approve",
                decided_at=_DECIDED_AT,
            ),
            subject=_SUBJECT,
            approval_id="approval-1",
        )
    )
    assert result.kind == "APPROVED"


def _active_transaction_id(
    database: ControlDatabase, identity: WorkspaceIdentityV1
) -> str:
    from vespercode.persistence.transaction import (
        PersistenceTransactionRepositoryV1,
    )

    active = PersistenceTransactionRepositoryV1(database).find_active_by_workspace(
        identity.digest
    )
    assert active is not None
    return active.transaction_id


def _workspace_snapshot() -> SnapshotTreeV1:
    """One minimal sealed SnapshotTree binding the preimage file.

    The root digest equals the frozen ``_SNAPSHOT_DIGEST`` the writeback
    commands bind; only ``src/b.py`` is tracked, so the writeback's
    untouched recheck (which excludes the involved paths) verifies
    trivially while still exercising the real re-scan.
    """
    return SnapshotTreeV1.model_validate(
        {
            "root_digest": _SNAPSHOT_DIGEST,
            "repository_policy_digest": _EDITABLE_DIGEST,
            "entries": (
                {
                    "kind": "DIRECTORY",
                    "path": CanonicalRelativePathV1("src"),
                },
                {
                    "kind": "TEXT_FILE",
                    "path": CanonicalRelativePathV1("src/b.py"),
                    "size_bytes": len(_ORIGINAL_B),
                    "content_ref": {
                        "sha256": _PREIMAGE_DIGEST,
                        "byte_count": len(_ORIGINAL_B),
                    },
                    "text_profile": {
                        "kind": "PRESENT",
                        "value": {
                            "encoding": "UTF8",
                            "newline": "LF",
                            "final_newline": True,
                        },
                    },
                },
            ),
            "file_bytes": (("src/b.py", _ORIGINAL_B),),
        }
    )


def _open_database(tmp_path: Path, name: str) -> ControlDatabase:
    database = open_control_database(tmp_path / f"{name}.db")
    assert apply_migrations(database, _ALL_MIGRATIONS).kind == "APPLIED"
    _seed_run_and_approval(database)
    return database


def _command(
    approval: FinalWritebackApprovalV1,
    event_id: str,
) -> PersistVerifiedCandidateV1:
    return PersistenceCommandFactoryV1(
        final_diff=_DIFF,
        candidate_digest=_CANDIDATE_DIGEST,
        policy_digest=_EDITABLE_DIGEST,
        workspace_identity_digest="0" * 64,
        workspace_preimage_digest=_WORKSPACE_PREIMAGE_DIGEST,
        approval=approval,
        approval_subject=_SUBJECT,
        run_deadline=_RUN_DEADLINE,
        postimage_bodies=(
            WritebackBodyV1(
                schema_version=1,
                path=CanonicalRelativePathV1("src/a.py"),
                operation="CREATE",
                body=_BODY_A,
            ),
            WritebackBodyV1(
                schema_version=1,
                path=CanonicalRelativePathV1("src/b.py"),
                operation="REPLACE",
                body=_BODY_B,
            ),
        ),
    ).for_approved_run(run_id="run-1", approval_id="approval-1", event_id=event_id)


class _RecoveryWorkspacePort(RealWorkspacePort):
    """RealWorkspacePort plus the read-only observation the apply needs."""

    def observe(self, path: CanonicalRelativePathV1) -> RecoveryPathObservationV1:
        return RealWorkspaceObserver(self._identity).observe(path)


class _LeaseHoldingThread:
    """One thread that holds the workspace mutex until released."""

    def __init__(self, identity: WorkspaceIdentityV1, timeout_ms: int) -> None:
        self._identity = identity
        self._timeout_ms = timeout_ms
        self._lease: WorkspaceLeaseV1 | None = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        from vespercode.workspace.mutex_win32 import WorkspaceMutex

        self._lease = WorkspaceMutex.acquire(self._identity, self._timeout_ms)
        self._ready.set()
        while self._lease is not None:
            threading.Event().wait(0.05)

    def start(self) -> None:
        self._thread.start()
        assert self._ready.wait(timeout=30), "lease holder did not acquire"

    def stop(self) -> None:
        from vespercode.workspace.mutex_win32 import WorkspaceMutex

        if self._lease is not None:
            WorkspaceMutex.release(self._lease)
            self._lease = None
        self._thread.join(timeout=30)


def _grant_everyone(path: Path) -> None:
    """Widen one real object's ACL with an Everyone allowed-FULL ACE."""
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi32.ConvertStringSidToSidW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.ConvertStringSidToSidW.restype = wintypes.BOOL
    advapi32.InitializeAcl.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD]
    advapi32.InitializeAcl.restype = wintypes.BOOL
    advapi32.AddAccessAllowedAce.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    advapi32.AddAccessAllowedAce.restype = wintypes.BOOL
    advapi32.InitializeSecurityDescriptor.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    advapi32.InitializeSecurityDescriptor.restype = wintypes.BOOL
    advapi32.SetSecurityDescriptorDacl.argtypes = [
        ctypes.c_void_p,
        wintypes.BOOL,
        ctypes.c_void_p,
        wintypes.BOOL,
    ]
    advapi32.SetSecurityDescriptorDacl.restype = wintypes.BOOL
    advapi32.SetFileSecurityW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    advapi32.SetFileSecurityW.restype = wintypes.BOOL
    everyone = ctypes.c_void_p()
    if not advapi32.ConvertStringSidToSidW("S-1-1-0", ctypes.byref(everyone)):
        raise OSError(ctypes.get_last_error(), "ConvertStringSidToSidW")
    try:
        acl = ctypes.create_string_buffer(256)
        if not advapi32.InitializeAcl(acl, ctypes.sizeof(acl), 2):
            raise OSError(ctypes.get_last_error(), "InitializeAcl")
        if not advapi32.AddAccessAllowedAce(acl, 2, 0x001F01FF, everyone):
            raise OSError(ctypes.get_last_error(), "AddAccessAllowedAce")
        descriptor = ctypes.create_string_buffer(256)
        if not advapi32.InitializeSecurityDescriptor(descriptor, 1):
            raise OSError(ctypes.get_last_error(), "InitializeSecurityDescriptor")
        if not advapi32.SetSecurityDescriptorDacl(descriptor, True, acl, False):
            raise OSError(ctypes.get_last_error(), "SetSecurityDescriptorDacl")
        if not advapi32.SetFileSecurityW(str(path), 4, descriptor):
            raise OSError(ctypes.get_last_error(), "SetFileSecurityW")
    finally:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.LocalFree.argtypes = [wintypes.HANDLE]
        kernel32.LocalFree.restype = wintypes.HANDLE
        kernel32.LocalFree(everyone)


def _fresh_workspace(tmp_path: Path, name: str) -> Path:
    """One real NTFS workspace with ``src`` and the preimage file."""
    workspace = tmp_path / name
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "b.py").write_bytes(_ORIGINAL_B)
    return workspace


def test_persistence_acl_and_identity_production_faults(
    tmp_path: Path,
) -> None:
    """The complete real-Windows production proof across deadline,
    external-change, ACL, and Windows identity faults."""
    # --- Full writeback commit with real files and real artifact ACLs ---
    workspace_path = _fresh_workspace(tmp_path, "commit-workspace")
    identity = resolve_workspace_identity(workspace_path)
    database = _open_database(tmp_path, "commit")
    lease = WorkspaceMutex.acquire(identity, 10_000)
    port = RealWorkspacePort(identity, lease, snapshot=_workspace_snapshot())
    store = PersistenceArtifactStoreV1(tmp_path / "artifacts-commit")
    coordinator = PersistenceCoordinator(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=store,
        approval_repository=WritebackApprovalRepository(database),
        workspace=port,
        policy=_MANIFEST.editable_path_policy,
        clock=FakeClockV1.from_epoch_milliseconds(_CONSUMED_AT.epoch_milliseconds),
    )
    approval = FinalWritebackApprovalV1(
        schema_version=1,
        approval_id="approval-1",
        subject_digest=DigestV1(value=_SUBJECT.digest),
        run_id="run-1",
        wait_id="wait-1",
        created_at=_DECIDED_AT,
        status="PENDING",
    )
    command = _command(approval, "evt-commit")
    command = command.model_copy(update={"workspace_identity_digest": identity.digest})
    result = coordinator.persist(command)
    assert result.outcome == "SUCCEEDED" and result.error_code is None
    assert result.workspace_write_count == 2
    assert (workspace_path / "src" / "a.py").read_bytes() == _BODY_A
    assert (workspace_path / "src" / "b.py").read_bytes() == _BODY_B
    preimage_ref = store.resolve("PREIMAGE", _PREIMAGE_DIGEST)
    backup_ref = store.resolve("BACKUP", _PREIMAGE_DIGEST)
    assert store.read_verified(preimage_ref) == _ORIGINAL_B
    assert store.read_verified(backup_ref) == _ORIGINAL_B
    assert store.verify_acl(preimage_ref).current_user_only is True
    assert store.verify_acl(backup_ref).current_user_only is True
    port.release()
    database.close()

    # --- Interrupted writeback recovered under the real lease ---
    workspace_path = _fresh_workspace(tmp_path, "recover-workspace")
    identity = resolve_workspace_identity(workspace_path)
    database = _open_database(tmp_path, "recover")
    lease = WorkspaceMutex.acquire(identity, 10_000)
    port = RealWorkspacePort(identity, lease, snapshot=_workspace_snapshot())
    store = PersistenceArtifactStoreV1(tmp_path / "artifacts-recover")
    coordinator = PersistenceCoordinator(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=store,
        approval_repository=WritebackApprovalRepository(database),
        workspace=port,
        policy=_MANIFEST.editable_path_policy,
        clock=FakeClockV1.from_epoch_milliseconds(_CONSUMED_AT.epoch_milliseconds),
        faults=ArmedFaultPort(WritebackFaultPointV1("REPLACE", "AFTER", 1)),
    )
    command = _command(approval, "evt-interrupted")
    command = command.model_copy(update={"workspace_identity_digest": identity.digest})
    with pytest.raises(PersistenceFaultInjectedError):
        coordinator.persist(command)
    assert (workspace_path / "src" / "a.py").read_bytes() == _BODY_A
    assert (workspace_path / "src" / "b.py").read_bytes() == _ORIGINAL_B
    preview_service = RecoveryPreviewService(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=store,
        workspace_identity_digest=identity.digest,
        observer=RealWorkspaceObserver(identity),
    )
    recovery_port = _RecoveryWorkspacePort(identity)
    apply_service = RecoveryApplyService(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=store,
        preview_service=preview_service,
        workspace=recovery_port,
        lease=RealRecoveryLeasePort(identity, 10_000),
        results=RecoveryResultRepositoryV1(database),
        clock=FakeClockV1.from_epoch_milliseconds(_CONSUMED_AT.epoch_milliseconds),
        workspace_identity_digest=identity.digest,
    )
    recovery = RecoveryService(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        preview_service=preview_service,
        apply_service=apply_service,
    )
    preview = recovery.preview(identity)
    assert preview.disposition == "ROLLED_BACK"
    rolled_back = recovery.apply(
        ApplyRecoveryV1(
            schema_version=1,
            transaction_id=_active_transaction_id(database, identity),
            workspace_identity_digest=identity.digest,
            preview_digest=preview.preview_digest,
            requested_disposition="ROLLED_BACK",
            explicit_apply=True,
        )
    )
    assert rolled_back.error_code is None and rolled_back.disposition == "ROLLED_BACK"
    assert rolled_back.changed_paths == ("src/a.py",)
    assert not (workspace_path / "src" / "a.py").exists()
    assert (workspace_path / "src" / "b.py").read_bytes() == _ORIGINAL_B
    port.release()
    database.close()

    # --- External byte change: never overwritten, stays UNRESOLVED ---
    workspace_path = _fresh_workspace(tmp_path, "external-workspace")
    identity = resolve_workspace_identity(workspace_path)
    database = _open_database(tmp_path, "external")
    lease = WorkspaceMutex.acquire(identity, 10_000)
    port = RealWorkspacePort(identity, lease, snapshot=_workspace_snapshot())
    store = PersistenceArtifactStoreV1(tmp_path / "artifacts-external")
    coordinator = PersistenceCoordinator(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=store,
        approval_repository=WritebackApprovalRepository(database),
        workspace=port,
        policy=_MANIFEST.editable_path_policy,
        clock=FakeClockV1.from_epoch_milliseconds(_CONSUMED_AT.epoch_milliseconds),
        faults=ArmedFaultPort(WritebackFaultPointV1("REPLACE", "AFTER", 1)),
    )
    command = _command(approval, "evt-external")
    command = command.model_copy(update={"workspace_identity_digest": identity.digest})
    with pytest.raises(PersistenceFaultInjectedError):
        coordinator.persist(command)
    (workspace_path / "src" / "a.py").write_bytes(_FOREIGN)
    preview_service = RecoveryPreviewService(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=store,
        workspace_identity_digest=identity.digest,
        observer=RealWorkspaceObserver(identity),
    )
    apply_service = RecoveryApplyService(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=store,
        preview_service=preview_service,
        workspace=_RecoveryWorkspacePort(identity),
        lease=RealRecoveryLeasePort(identity, 10_000),
        results=RecoveryResultRepositoryV1(database),
        clock=FakeClockV1.from_epoch_milliseconds(_CONSUMED_AT.epoch_milliseconds),
        workspace_identity_digest=identity.digest,
    )
    recovery = RecoveryService(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        preview_service=preview_service,
        apply_service=apply_service,
    )
    preview = recovery.preview(identity)
    assert preview.disposition == "UNRESOLVED"
    external = recovery.apply(
        ApplyRecoveryV1(
            schema_version=1,
            transaction_id=preview.transaction_id,
            workspace_identity_digest=identity.digest,
            preview_digest=preview.preview_digest,
            requested_disposition="ROLLED_BACK",
            explicit_apply=True,
        )
    )
    assert external.error_code == "RECOVERY_UNRESOLVED"
    assert external.changed_paths == () and external.workspace_write_count == 0
    assert (workspace_path / "src" / "a.py").read_bytes() == _FOREIGN
    assert (workspace_path / "src" / "b.py").read_bytes() == _ORIGINAL_B
    port.release()
    database.close()

    # --- Windows identity fault: same bytes behind a replaced object
    # identity are never overwritten ---
    workspace_path = _fresh_workspace(tmp_path, "identity-workspace")
    identity = resolve_workspace_identity(workspace_path)
    database = _open_database(tmp_path, "identity")
    lease = WorkspaceMutex.acquire(identity, 10_000)
    port = RealWorkspacePort(identity, lease, snapshot=_workspace_snapshot())
    store = PersistenceArtifactStoreV1(tmp_path / "artifacts-identity")
    coordinator = PersistenceCoordinator(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=store,
        approval_repository=WritebackApprovalRepository(database),
        workspace=port,
        policy=_MANIFEST.editable_path_policy,
        clock=FakeClockV1.from_epoch_milliseconds(_CONSUMED_AT.epoch_milliseconds),
        faults=ArmedFaultPort(WritebackFaultPointV1("REPLACE", "AFTER", 1)),
    )
    command = _command(approval, "evt-identity")
    command = command.model_copy(update={"workspace_identity_digest": identity.digest})
    with pytest.raises(PersistenceFaultInjectedError):
        coordinator.persist(command)
    # Delete and recreate the preimage file: identical bytes, new object.
    (workspace_path / "src" / "b.py").unlink()
    (workspace_path / "src" / "b.py").write_bytes(_ORIGINAL_B)
    preview_service = RecoveryPreviewService(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=store,
        workspace_identity_digest=identity.digest,
        observer=RealWorkspaceObserver(identity),
    )
    apply_service = RecoveryApplyService(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=store,
        preview_service=preview_service,
        workspace=_RecoveryWorkspacePort(identity),
        lease=RealRecoveryLeasePort(identity, 10_000),
        results=RecoveryResultRepositoryV1(database),
        clock=FakeClockV1.from_epoch_milliseconds(_CONSUMED_AT.epoch_milliseconds),
        workspace_identity_digest=identity.digest,
    )
    recovery = RecoveryService(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        preview_service=preview_service,
        apply_service=apply_service,
    )
    preview = recovery.preview(identity)
    assert preview.disposition == "UNRESOLVED"
    identity_fault = recovery.apply(
        ApplyRecoveryV1(
            schema_version=1,
            transaction_id=preview.transaction_id,
            workspace_identity_digest=identity.digest,
            preview_digest=preview.preview_digest,
            requested_disposition="ROLLED_BACK",
            explicit_apply=True,
        )
    )
    assert identity_fault.error_code == "RECOVERY_UNRESOLVED"
    assert (workspace_path / "src" / "b.py").read_bytes() == _ORIGINAL_B
    port.release()
    database.close()

    # --- ACL fault: a widened backup ACL makes the recovery unprovable
    # and the backup is never used ---
    workspace_path = _fresh_workspace(tmp_path, "acl-workspace")
    identity = resolve_workspace_identity(workspace_path)
    database = _open_database(tmp_path, "acl")
    lease = WorkspaceMutex.acquire(identity, 10_000)
    port = RealWorkspacePort(identity, lease, snapshot=_workspace_snapshot())
    store = PersistenceArtifactStoreV1(tmp_path / "artifacts-acl")
    coordinator = PersistenceCoordinator(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=store,
        approval_repository=WritebackApprovalRepository(database),
        workspace=port,
        policy=_MANIFEST.editable_path_policy,
        clock=FakeClockV1.from_epoch_milliseconds(_CONSUMED_AT.epoch_milliseconds),
        faults=ArmedFaultPort(WritebackFaultPointV1("PROGRESS", "AFTER", 1)),
    )
    command = _command(approval, "evt-acl")
    command = command.model_copy(update={"workspace_identity_digest": identity.digest})
    with pytest.raises(PersistenceFaultInjectedError):
        coordinator.persist(command)
    assert store.verify_acl(store.resolve("BACKUP", _PREIMAGE_DIGEST)).current_user_only
    _grant_everyone(store.artifact_path(store.resolve("BACKUP", _PREIMAGE_DIGEST)))
    assert (
        store.verify_acl(store.resolve("BACKUP", _PREIMAGE_DIGEST)).current_user_only
        is False
    )
    preview_service = RecoveryPreviewService(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=store,
        workspace_identity_digest=identity.digest,
        observer=RealWorkspaceObserver(identity),
    )
    apply_service = RecoveryApplyService(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=store,
        preview_service=preview_service,
        workspace=_RecoveryWorkspacePort(identity),
        lease=RealRecoveryLeasePort(identity, 10_000),
        results=RecoveryResultRepositoryV1(database),
        clock=FakeClockV1.from_epoch_milliseconds(_CONSUMED_AT.epoch_milliseconds),
        workspace_identity_digest=identity.digest,
    )
    recovery = RecoveryService(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        preview_service=preview_service,
        apply_service=apply_service,
    )
    preview = recovery.preview(identity)
    assert preview.disposition == "UNRESOLVED"
    acl_fault = recovery.apply(
        ApplyRecoveryV1(
            schema_version=1,
            transaction_id=preview.transaction_id,
            workspace_identity_digest=identity.digest,
            preview_digest=preview.preview_digest,
            requested_disposition="ROLLED_BACK",
            explicit_apply=True,
        )
    )
    assert acl_fault.error_code == "RECOVERY_UNRESOLVED"
    assert (workspace_path / "src" / "a.py").read_bytes() == _BODY_A
    port.release()
    database.close()

    # --- Deadline fault: expiry before the first write stops with zero
    # writes and a durable ROLLED_BACK ---
    workspace_path = _fresh_workspace(tmp_path, "deadline-workspace")
    identity = resolve_workspace_identity(workspace_path)
    database = _open_database(tmp_path, "deadline")
    lease = WorkspaceMutex.acquire(identity, 10_000)
    port = RealWorkspacePort(identity, lease, snapshot=_workspace_snapshot())
    store = PersistenceArtifactStoreV1(tmp_path / "artifacts-deadline")
    coordinator = PersistenceCoordinator(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=store,
        approval_repository=WritebackApprovalRepository(database),
        workspace=port,
        policy=_MANIFEST.editable_path_policy,
        clock=FakeClockV1.from_epoch_milliseconds(_RUN_DEADLINE.epoch_milliseconds + 1),
    )
    command = _command(approval, "evt-deadline")
    command = command.model_copy(update={"workspace_identity_digest": identity.digest})
    expired = coordinator.persist(command)
    assert expired.outcome == "STOPPED" and expired.error_code is None
    assert expired.workspace_write_count == 0
    assert not (workspace_path / "src" / "a.py").exists()
    assert (workspace_path / "src" / "b.py").read_bytes() == _ORIGINAL_B
    with database.immediate_transaction() as tx:
        state = tx.execute(
            "SELECT state FROM persistence_transactions ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
    assert str(state[0]) == "ROLLED_BACK"
    port.release()
    database.close()

    # --- Lease fault: the apply cannot acquire the workspace mutex while
    # another holder owns it ---
    workspace_path = _fresh_workspace(tmp_path, "lease-workspace")
    identity = resolve_workspace_identity(workspace_path)
    database = _open_database(tmp_path, "lease")
    lease = WorkspaceMutex.acquire(identity, 10_000)
    port = RealWorkspacePort(identity, lease, snapshot=_workspace_snapshot())
    store = PersistenceArtifactStoreV1(tmp_path / "artifacts-lease")
    coordinator = PersistenceCoordinator(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=store,
        approval_repository=WritebackApprovalRepository(database),
        workspace=port,
        policy=_MANIFEST.editable_path_policy,
        clock=FakeClockV1.from_epoch_milliseconds(_CONSUMED_AT.epoch_milliseconds),
        faults=ArmedFaultPort(WritebackFaultPointV1("REPLACE", "AFTER", 1)),
    )
    command = _command(approval, "evt-lease")
    command = command.model_copy(update={"workspace_identity_digest": identity.digest})
    with pytest.raises(PersistenceFaultInjectedError):
        coordinator.persist(command)
    port.release()
    preview_service = RecoveryPreviewService(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=store,
        workspace_identity_digest=identity.digest,
        observer=RealWorkspaceObserver(identity),
    )
    preview = preview_service.preview_transaction(
        _active_transaction_id(database, identity)
    )
    assert preview.disposition == "ROLLED_BACK"
    holder = _LeaseHoldingThread(identity, 10_000)
    holder.start()
    try:
        apply_service = RecoveryApplyService(
            transaction_repository=PersistenceTransactionRepositoryV1(database),
            path_repository=PersistencePathRecordRepositoryV1(database),
            artifact_store=store,
            preview_service=preview_service,
            workspace=_RecoveryWorkspacePort(identity),
            lease=RealRecoveryLeasePort(identity, 500),
            results=RecoveryResultRepositoryV1(database),
            clock=FakeClockV1.from_epoch_milliseconds(_CONSUMED_AT.epoch_milliseconds),
            workspace_identity_digest=identity.digest,
        )
        recovery = RecoveryService(
            transaction_repository=PersistenceTransactionRepositoryV1(database),
            preview_service=preview_service,
            apply_service=apply_service,
        )
        locked = recovery.apply(
            ApplyRecoveryV1(
                schema_version=1,
                transaction_id=preview.transaction_id,
                workspace_identity_digest=identity.digest,
                preview_digest=preview.preview_digest,
                requested_disposition="ROLLED_BACK",
                explicit_apply=True,
            )
        )
        assert locked.error_code == "WORKSPACE_LOCK_LOST"
        assert locked.workspace_write_count == 0
        assert (workspace_path / "src" / "a.py").read_bytes() == _BODY_A
    finally:
        holder.stop()
    database.close()
