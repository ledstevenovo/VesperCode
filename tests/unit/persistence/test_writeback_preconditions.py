"""T26.1 legacy step 26.E: approval-bound atomic writeback preconditions.

Pins the thin protocol composition over the 26.A repositories and 26.D
artifact store: the exact current binding (Run, verified candidate, final
diff, workspace identity, event, unconsumed approval, ordered 1–3
canonical paths), the approval precondition (missing/non-consumable
approval performs zero workspace writes), preimage/byte/identity
re-verification, backup-before-replace artifact publication, consume-once
immediately before the first atomic replace, per-path progress and
postimage verification, cancellation and deadline safe points, and the
closed result vocabulary.

The operative matrix authority is the card Expected (26.E) line per the
SPEC_PROCESS §49 precedent ("exact §5.1 matrix" is a dangling reference).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
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
from vespercode.persistence.transaction import (
    PersistencePathRecordRepositoryV1,
    PersistenceTransactionRepositoryV1,
)
from vespercode.persistence.writeback import (
    ClockPort,
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
)

_CREATED_AT = CanonicalTimestampV1("2026-08-05T09:00:00.000Z")
_EXPIRES_AT = CanonicalTimestampV1("2026-08-05T09:05:00.000Z")
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
_WORKSPACE_IDENTITY_DIGEST = "55" * 32
_IDENTITY_DIGEST = "44" * 32
_OTHER_IDENTITY_DIGEST = "77" * 32
_WORKSPACE_PATH = "C:\\work\\vesper"

_TEXT_METADATA = TextMetadataV1(encoding="UTF8", newline="LF", final_newline=True)

_BODIES = {
    "src/a.py": b"new a\n",
    "src/b.py": b"new b\n",
    "src/c.py": b"new c\n",
    "tests/x.md": b"out of scope\n",
}
_ORIGINAL = b"original b\n"


def manifest() -> ReferenceProfileManifestV1:
    """The frozen packaged reference profile (digest-verified)."""
    loaded = load_reference_profile(_REFERENCE_MANIFEST.read_bytes())
    assert isinstance(loaded, ReferenceProfileManifestV1)
    return loaded


_MANIFEST = manifest()
_EDITABLE_DIGEST = _MANIFEST.editable_path_policy.digest


def _canonical_entry(entry: FinalDiffEntryV1) -> dict[str, CanonicalValueV1]:
    """The §0.1 canonical value shape of one sealed diff row."""
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


def final_diff(paths: tuple[str, ...] = ("src/a.py", "src/b.py")) -> FinalDiffV1:
    """One sealed diff over the declared sorted paths.

    The first path is a CREATE and every following path a REPLACE whose
    preimage is the ``_ORIGINAL`` bytes; the digest self-binds the rows.
    """
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


def subject_for(
    diff: FinalDiffV1, expires_at: CanonicalTimestampV1 = _EXPIRES_AT
) -> FinalWritebackSubjectV1:
    """One immutable approval subject bound to the exact diff facts."""
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
        expires_at,
    )


_DIFF = final_diff()
_DIFF_ONE = final_diff(("src/a.py",))
_DIFF_THREE = final_diff(("src/a.py", "src/b.py", "src/c.py"))
_LATE_EXPIRES_AT = CanonicalTimestampV1("2026-08-05T09:30:00.000Z")
_SUBJECT = subject_for(_DIFF)
_SUBJECT_ONE = subject_for(_DIFF_ONE)
_SUBJECT_THREE = subject_for(_DIFF_THREE)


def _seed_run_and_approval(
    database: ControlDatabase,
    subject: FinalWritebackSubjectV1,
    approval_id: str = "approval-1",
) -> None:
    """One run, one pending wait, one PENDING approval (decided)."""
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
            approval_id=approval_id,
        )
    )
    assert result.kind == "APPROVED"


class StepClock:
    """A deterministic clock that expires exactly after ``limit`` calls.

    The first ``limit`` ``now()`` calls report the pre-deadline instant
    and every later call reports a post-deadline instant, so a deadline
    can be injected precisely between two protocol steps.
    """

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._calls = 0
        self._before = CanonicalTimestampV1("2026-08-05T09:14:00.000Z")
        self._after = CanonicalTimestampV1("2026-08-05T09:17:00.000Z")

    def now(self) -> CanonicalTimestampV1:
        self._calls += 1
        return self._before if self._calls <= self._limit else self._after


class SpyWorkspace:
    """In-memory workspace port: bytes, identities, and write counting."""

    def __init__(
        self,
        *,
        identity_digest: str = _WORKSPACE_IDENTITY_DIGEST,
        lease_held: bool = True,
    ) -> None:
        self._identity_digest = identity_digest
        self._lease_held = lease_held
        self._files: dict[str, bytes] = {}
        self._identities: dict[str, str] = {}
        self._identity_reads: dict[str, int] = {}
        self._identity_flips: dict[str, tuple[int, str]] = {}
        self._writes: list[tuple[str, bytes]] = []
        self._deletes: list[str] = []
        self._untouched_ok = True
        self._postimage_verification_ok = True

    def seed(self, path: str, body: bytes, identity: str = _IDENTITY_DIGEST) -> None:
        self._files[path] = body
        self._identities[path] = identity

    def remove(self, path: str) -> None:
        """Remove one path (replay-state seam)."""
        self._files.pop(path, None)
        self._identities.pop(path, None)

    def flip_identity_on_read(
        self, path: str, new_identity: str, at_read: int = 2
    ) -> None:
        """Flip one path's identity from the nth read onward (drift seam)."""
        self._identity_flips[path] = (at_read, new_identity)

    def identity_digest(self) -> str:
        return self._identity_digest

    def lease_held(self) -> bool:
        return self._lease_held

    def verify_untouched(
        self, snapshot_tree_digest: str, involved_paths: tuple[str, ...]
    ) -> bool:
        return self._untouched_ok

    def flip_untouched(self) -> None:
        self._untouched_ok = False

    def flip_postimage_verification(self) -> None:
        """Make every postimage verification fail (WRITEBACK_MISMATCH seam)."""
        self._postimage_verification_ok = False

    def workspace_path(self) -> str:
        return _WORKSPACE_PATH

    def release_lease(self) -> None:
        self._lease_held = False

    def read_bytes(self, path: CanonicalRelativePathV1) -> bytes:
        if path.value not in self._files:
            raise FileNotFoundError(path.value)
        return self._files[path.value]

    def is_absent(self, path: CanonicalRelativePathV1) -> bool:
        return path.value not in self._files

    def object_identity_digest(self, path: CanonicalRelativePathV1) -> str:
        self._identity_reads[path.value] = self._identity_reads.get(path.value, 0) + 1
        flip = self._identity_flips.get(path.value)
        if flip is not None and self._identity_reads[path.value] >= flip[0]:
            return flip[1]
        if path.value not in self._identities:
            raise KeyError(path.value)
        return self._identities[path.value]

    def replace(self, path: CanonicalRelativePathV1, body: bytes) -> None:
        self._files[path.value] = body
        self._writes.append((path.value, body))

    def delete(self, path: CanonicalRelativePathV1) -> None:
        del self._files[path.value]
        self._deletes.append(path.value)

    def verify_postimage(self, path: CanonicalRelativePathV1, digest: str) -> bool:
        if not self._postimage_verification_ok:
            return False
        if path.value not in self._files:
            return False
        return hashlib.sha256(self._files[path.value]).hexdigest() == digest

    @property
    def write_count(self) -> int:
        return len(self._writes) + len(self._deletes)

    @property
    def files(self) -> dict[str, bytes]:
        return dict(self._files)

    @property
    def writes(self) -> list[tuple[str, bytes]]:
        return list(self._writes)


class _AlwaysCancel:
    def is_cancelled(self) -> bool:
        return True


class _NeverCancel:
    def is_cancelled(self) -> bool:
        return False


def _open_environment(tmp_path: Path, name: str) -> ControlDatabase:
    """One fresh migrated database with the seeded approval chain."""
    database = open_control_database(tmp_path / f"{name}.db")
    assert apply_migrations(database, _ALL_MIGRATIONS).kind == "APPLIED"
    return database


def _grant_everyone(path: Path) -> None:
    """Widen one real object's ACL with an Everyone allowed-FULL ACE.

    The unsafe-root fixture the coordinator's ARTIFACT_ACL_UNSAFE mapping
    must reject (replicated from the 26.D artifact tests).
    """
    import ctypes

    from ctypes import wintypes

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


def _coordinator(
    database: ControlDatabase,
    workspace: SpyWorkspace,
    tmp_path: Path,
    *,
    clock: ClockPort | None = None,
    cancelled: bool = False,
) -> PersistenceCoordinator:
    if clock is None:
        clock = FakeClockV1.from_epoch_milliseconds(_CONSUMED_AT.epoch_milliseconds)
    return PersistenceCoordinator(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=PersistenceArtifactStoreV1(tmp_path / "artifacts"),
        approval_repository=WritebackApprovalRepository(database),
        workspace=workspace,
        policy=_MANIFEST.editable_path_policy,
        clock=clock,
        cancel=_AlwaysCancel() if cancelled else _NeverCancel(),
    )


def _command(
    diff: FinalDiffV1,
    subject: FinalWritebackSubjectV1,
    approval: FinalWritebackApprovalV1,
    *,
    approval_id: str = "approval-1",
    event_id: str = "evt-writeback",
    run_deadline: CanonicalTimestampV1 = _RUN_DEADLINE,
) -> PersistVerifiedCandidateV1:
    return PersistenceCommandFactoryV1(
        final_diff=diff,
        candidate_digest=_CANDIDATE_DIGEST,
        policy_digest=_EDITABLE_DIGEST,
        workspace_identity_digest=_WORKSPACE_IDENTITY_DIGEST,
        workspace_preimage_digest=_WORKSPACE_PREIMAGE_DIGEST,
        approval=approval,
        approval_subject=subject,
        run_deadline=run_deadline,
        postimage_bodies=tuple(
            WritebackBodyV1(
                schema_version=1,
                path=CanonicalRelativePathV1(path),
                operation=("CREATE" if index == 0 else "REPLACE"),
                body=_BODIES[path],
            )
            for index, path in enumerate(entry.path.value for entry in diff.entries)
        ),
    ).for_approved_run(run_id="run-1", approval_id=approval_id, event_id=event_id)


def _pending_approval(subject: FinalWritebackSubjectV1) -> FinalWritebackApprovalV1:
    return FinalWritebackApprovalV1(
        schema_version=1,
        approval_id="approval-1",
        subject_digest=DigestV1(value=subject.digest),
        run_id="run-1",
        wait_id="wait-1",
        created_at=_DECIDED_AT,
        status="PENDING",
    )


def _approval_status(database: ControlDatabase, approval_id: str = "approval-1") -> str:
    with database.immediate_transaction() as tx:
        row = tx.execute(
            "SELECT status FROM writeback_approvals WHERE approval_id = ?",
            (approval_id,),
        ).fetchone()
    assert row is not None
    return str(row[0])


def _transaction_state(database: ControlDatabase) -> tuple[str, ...]:
    """The recorded transaction states in insertion order."""
    with database.immediate_transaction() as tx:
        rows = tx.execute(
            "SELECT state FROM persistence_transactions ORDER BY prepared_at, rowid"
        ).fetchall()
    return tuple(str(row[0]) for row in rows)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[ControlDatabase]:
    control_database = _open_environment(tmp_path, "writeback")
    _seed_run_and_approval(control_database, _SUBJECT)
    yield control_database
    control_database.close()


@pytest.fixture
def workspace() -> SpyWorkspace:
    spy = SpyWorkspace()
    spy.seed("src/b.py", _ORIGINAL)
    return spy


@pytest.fixture
def persistence(
    database: ControlDatabase,
    workspace: SpyWorkspace,
    tmp_path: Path,
) -> PersistenceCoordinator:
    return _coordinator(database, workspace, tmp_path)


def approved_command() -> PersistVerifiedCandidateV1:
    """One exact current writeback command bound to the PENDING approval."""
    return _command(_DIFF, _SUBJECT, _pending_approval(_SUBJECT))


def command_without_consumable_approval() -> PersistVerifiedCandidateV1:
    """One command whose carried approval is not consumable."""
    consumed = _pending_approval(_SUBJECT).model_copy(update={"status": "CONSUMED"})
    return _command(_DIFF, _SUBJECT, consumed)


def test_missing_exact_approval_writes_no_workspace_bytes(
    persistence: PersistenceCoordinator,
    workspace: SpyWorkspace,
) -> None:
    result = persistence.persist(command_without_consumable_approval())
    assert result.error_code == "APPROVAL_REQUIRED"
    assert workspace.write_count == 0


def test_writeback_precondition_state_matrix(
    persistence: PersistenceCoordinator,
    workspace: SpyWorkspace,
    database: ControlDatabase,
    tmp_path: Path,
) -> None:
    """The exact §5.1-Expected (26.E) matrix: exact approval, byte/identity,
    1–3-path ordering, backup-before-replace, verification, cancellation,
    and injected interruption cases pass; any interruption leaves a
    durable non-terminal transaction rather than false success."""
    # Exact approval + backup-before-replace + verification: the
    # consumable PENDING approval commits exactly once, the REPLACE
    # preimage bytes are published as PREIMAGE and BACKUP artifacts
    # before any write, and every postimage is verified before COMMITTED.
    result = persistence.persist(approved_command())
    assert result.outcome == "SUCCEEDED" and result.error_code is None
    assert result.workspace_write_count == 2
    assert workspace.files == {
        "src/a.py": _BODIES["src/a.py"],
        "src/b.py": _BODIES["src/b.py"],
    }
    assert workspace.writes == [
        ("src/a.py", _BODIES["src/a.py"]),
        ("src/b.py", _BODIES["src/b.py"]),
    ]
    assert _approval_status(database) == "CONSUMED"
    assert _transaction_state(database) == ("COMMITTED",)
    assert result.transaction_id is not None
    paths = persistence.path_repository.list_ordered(result.transaction_id)
    assert [record.durable_state for record in paths] == ["VERIFIED", "VERIFIED"]
    assert paths[1].backup_ref.kind == "PRESENT"
    backup_store = persistence.artifact_store
    assert (
        backup_store.read_verified(backup_store.resolve("BACKUP", _PREIMAGE_DIGEST))
        == _ORIGINAL
    )
    assert (
        backup_store.read_verified(backup_store.resolve("PREIMAGE", _PREIMAGE_DIGEST))
        == _ORIGINAL
    )

    # Consume-once: a re-attempt over the drifted workspace fails closed
    # on the bytes; a re-attempt over a restored preimage fails on the
    # already-consumed approval with zero additional writes and a durable
    # PREPARED transaction.
    redrift = persistence.persist(approved_command())
    assert redrift.error_code == "WORKSPACE_CHANGED"
    assert workspace.write_count == 2
    replay_workspace = SpyWorkspace()
    replay_workspace.seed("src/b.py", _ORIGINAL)
    replay_coordinator = _coordinator(
        database, replay_workspace, tmp_path / "art-replay"
    )
    replay_command = _command(
        _DIFF, _SUBJECT, _pending_approval(_SUBJECT), event_id="evt-writeback-2"
    )
    replay = replay_coordinator.persist(replay_command)
    assert replay.error_code == "APPROVAL_STALE"
    assert replay_workspace.write_count == 0
    assert _approval_status(database) == "CONSUMED"
    assert _transaction_state(database) == ("COMMITTED", "PREPARED")

    # Missing/non-consumable approval: zero writes, zero records, and the
    # stored approval stays PENDING.
    fresh = _open_environment(tmp_path, "matrix-missing")
    _seed_run_and_approval(fresh, _SUBJECT)
    missing_workspace = SpyWorkspace()
    missing_workspace.seed("src/b.py", _ORIGINAL)
    missing = _coordinator(fresh, missing_workspace, tmp_path / "art-missing").persist(
        command_without_consumable_approval()
    )
    assert missing.error_code == "APPROVAL_REQUIRED"
    assert missing_workspace.write_count == 0
    assert _approval_status(fresh) == "PENDING"
    with fresh.immediate_transaction() as tx:
        count = tx.execute("SELECT COUNT(*) FROM persistence_transactions").fetchone()
    assert int(count[0]) == 0
    fresh.close()

    # Stale approval: a PENDING approval whose subject no longer matches
    # the carried subject performs zero writes.
    fresh = _open_environment(tmp_path, "matrix-stale")
    _seed_run_and_approval(fresh, _SUBJECT)
    stale_workspace = SpyWorkspace()
    stale_workspace.seed("src/b.py", _ORIGINAL)
    stale_approval = _pending_approval(_SUBJECT).model_copy(
        update={"subject_digest": DigestV1(value=_SUBJECT_ONE.digest)}
    )
    stale = _coordinator(fresh, stale_workspace, tmp_path / "art-stale").persist(
        _command(_DIFF, _SUBJECT, stale_approval)
    )
    assert stale.error_code == "APPROVAL_STALE"
    assert stale_workspace.write_count == 0
    assert _approval_status(fresh) == "PENDING"
    fresh.close()

    # Expired approval: a PENDING approval consumed after its subject
    # expiry performs zero writes.
    fresh = _open_environment(tmp_path, "matrix-expired")
    _seed_run_and_approval(fresh, _SUBJECT)
    expired_workspace = SpyWorkspace()
    expired_workspace.seed("src/b.py", _ORIGINAL)
    expired = _coordinator(
        fresh,
        expired_workspace,
        tmp_path / "art-expired",
        clock=FakeClockV1.from_epoch_milliseconds(
            _EXPIRES_AT.epoch_milliseconds + 60_000
        ),
    ).persist(approved_command())
    assert expired.error_code == "APPROVAL_STALE"
    assert expired_workspace.write_count == 0
    assert _approval_status(fresh) == "PENDING"
    fresh.close()

    # Byte drift: preimage bytes that differ from the frozen diff fail
    # closed before any durable write and do not consume the approval.
    fresh = _open_environment(tmp_path, "matrix-bytes")
    _seed_run_and_approval(fresh, _SUBJECT)
    drifted_workspace = SpyWorkspace()
    drifted_workspace.seed("src/b.py", b"external b\n")
    drifted = _coordinator(fresh, drifted_workspace, tmp_path / "art-bytes").persist(
        approved_command()
    )
    assert drifted.error_code == "WORKSPACE_CHANGED"
    assert drifted_workspace.write_count == 0
    assert _approval_status(fresh) == "PENDING"
    fresh.close()

    # Identity drift at the step-3 re-verification: the same bytes with a
    # replaced object identity fail closed with zero writes.
    fresh = _open_environment(tmp_path, "matrix-identity")
    _seed_run_and_approval(fresh, _SUBJECT)
    identity_workspace = SpyWorkspace()
    identity_workspace.seed("src/b.py", _ORIGINAL)
    identity_workspace.flip_identity_on_read(
        "src/b.py", _OTHER_IDENTITY_DIGEST, at_read=2
    )
    identity = _coordinator(
        fresh, identity_workspace, tmp_path / "art-identity"
    ).persist(approved_command())
    assert identity.error_code == "WORKSPACE_CHANGED"
    assert identity_workspace.write_count == 0
    assert _approval_status(fresh) == "PENDING"
    fresh.close()

    # Lost lease: the workspace lease must be held before any write.
    fresh = _open_environment(tmp_path, "matrix-lease")
    _seed_run_and_approval(fresh, _SUBJECT)
    lease_workspace = SpyWorkspace(lease_held=False)
    lease_workspace.seed("src/b.py", _ORIGINAL)
    lease = _coordinator(fresh, lease_workspace, tmp_path / "art-lease").persist(
        approved_command()
    )
    assert lease.error_code == "WORKSPACE_LOCK_LOST"
    assert lease_workspace.write_count == 0
    fresh.close()

    # Non-editable path: the frozen editable policy rejects before any
    # durable write.
    fresh = _open_environment(tmp_path, "matrix-policy")
    _seed_run_and_approval(fresh, _SUBJECT)
    policy_workspace = SpyWorkspace()
    policy_workspace.seed("src/b.py", _ORIGINAL)
    # A self-bound diff whose REPLACE entry lies outside the editable
    # ``src`` root (``tests/x.md`` sorts after ``src/a.py``).
    out_of_scope = final_diff(("src/a.py", "tests/x.md"))
    non_editable = _command(out_of_scope, _SUBJECT, _pending_approval(_SUBJECT))
    policy_result = _coordinator(
        fresh, policy_workspace, tmp_path / "art-policy"
    ).persist(non_editable)
    assert policy_result.error_code == "PATCH_PATH_NOT_EDITABLE"
    assert policy_workspace.write_count == 0
    assert _approval_status(fresh) == "PENDING"
    fresh.close()

    # Cancellation at the safe point: zero writes, a durable ROLLED_BACK
    # transaction, and the approval stays PENDING.
    fresh = _open_environment(tmp_path, "matrix-cancel")
    _seed_run_and_approval(fresh, _SUBJECT)
    cancel_workspace = SpyWorkspace()
    cancel_workspace.seed("src/b.py", _ORIGINAL)
    cancel_result = _coordinator(
        fresh, cancel_workspace, tmp_path / "art-cancel", cancelled=True
    ).persist(approved_command())
    assert cancel_result.outcome == "STOPPED" and cancel_result.error_code is None
    assert cancel_workspace.write_count == 0
    assert _approval_status(fresh) == "PENDING"
    assert _transaction_state(fresh) == ("ROLLED_BACK",)
    fresh.close()

    # Deadline before the first write: zero writes, durable ROLLED_BACK.
    # The approval subject outlives the run deadline so the expiry of the
    # run deadline (not the approval) is the stopping fact.
    late_subject = subject_for(_DIFF, expires_at=_LATE_EXPIRES_AT)
    fresh = _open_environment(tmp_path, "matrix-deadline-zero")
    _seed_run_and_approval(fresh, late_subject)
    late_workspace = SpyWorkspace()
    late_workspace.seed("src/b.py", _ORIGINAL)
    early_deadline = CanonicalTimestampV1("2026-08-05T09:03:00.000Z")
    late = _coordinator(
        fresh,
        late_workspace,
        tmp_path / "art-deadline-zero",
        clock=FakeClockV1.from_epoch_milliseconds(
            early_deadline.epoch_milliseconds + 1
        ),
    ).persist(
        _command(
            _DIFF,
            late_subject,
            _pending_approval(late_subject),
            run_deadline=early_deadline,
        )
    )
    assert late.outcome == "STOPPED" and late.error_code is None
    assert late_workspace.write_count == 0
    assert _approval_status(fresh) == "PENDING"
    assert _transaction_state(fresh) == ("ROLLED_BACK",)
    fresh.close()

    # Deadline after the first replace: no further writes, durable
    # UNRESOLVED, and recovery required.
    fresh = _open_environment(tmp_path, "matrix-deadline-mid")
    _seed_run_and_approval(fresh, late_subject)
    mid_workspace = SpyWorkspace()
    mid_workspace.seed("src/b.py", _ORIGINAL)
    mid = _coordinator(
        fresh,
        mid_workspace,
        tmp_path / "art-deadline-mid",
        clock=StepClock(limit=6),
    ).persist(_command(_DIFF, late_subject, _pending_approval(late_subject)))
    assert mid.outcome == "RECOVERY_REQUIRED"
    assert mid.error_code == "PERSISTENCE_UNCERTAIN"
    assert mid_workspace.write_count == 1
    assert mid_workspace.files == {
        "src/a.py": _BODIES["src/a.py"],
        "src/b.py": _ORIGINAL,
    }
    assert _transaction_state(fresh) == ("UNRESOLVED",)
    fresh.close()

    # Write-after verification failure (SPEC 4.6 item 6): a path whose
    # bytes do not match its postimage after the replace never records
    # REPLACED/VERIFIED and leaves a durable UNRESOLVED transaction with
    # the honest write count (quality review I-3).
    fresh = _open_environment(tmp_path, "matrix-mismatch-verify")
    _seed_run_and_approval(fresh, _SUBJECT)
    mismatch_workspace = SpyWorkspace()
    mismatch_workspace.seed("src/b.py", _ORIGINAL)
    mismatch_workspace.flip_postimage_verification()
    mismatch = _coordinator(
        fresh, mismatch_workspace, tmp_path / "art-mismatch-verify"
    ).persist(approved_command())
    assert mismatch.outcome == "RECOVERY_REQUIRED"
    assert mismatch.error_code == "WRITEBACK_MISMATCH"
    assert mismatch_workspace.write_count == 1
    assert _transaction_state(fresh) == ("UNRESOLVED",)
    with fresh.immediate_transaction() as tx:
        states = tx.execute(
            "SELECT durable_state FROM persistence_path_records ORDER BY sequence"
        ).fetchall()
    assert [str(row[0]) for row in states] == ["NOT_STARTED", "NOT_STARTED"]
    fresh.close()

    # Duplicate-event replay: the same event identity re-derives the same
    # deterministic transaction id and fails closed with zero additional
    # writes (quality review M-6a).
    fresh = _open_environment(tmp_path, "matrix-replay-same-event")
    _seed_run_and_approval(fresh, _SUBJECT)
    replay_workspace = SpyWorkspace()
    replay_workspace.seed("src/b.py", _ORIGINAL)
    replay_coordinator = _coordinator(
        fresh, replay_workspace, tmp_path / "art-replay-same-event"
    )
    first = replay_coordinator.persist(approved_command())
    assert first.outcome == "SUCCEEDED"
    replay_workspace.remove("src/a.py")
    replay_workspace.seed("src/b.py", _ORIGINAL)
    replayed = replay_coordinator.persist(approved_command())
    assert replayed.error_code == "PERSISTENCE_FAILED"
    assert replay_workspace.write_count == 2
    fresh.close()

    # Final-diff digest drift: a command whose bound digest does not
    # self-bind its rows fails closed before any durable write
    # (quality review M-6b).
    fresh = _open_environment(tmp_path, "matrix-diff-drift")
    _seed_run_and_approval(fresh, _SUBJECT)
    drift_workspace = SpyWorkspace()
    drift_workspace.seed("src/b.py", _ORIGINAL)
    drifted_command = approved_command().model_copy(
        update={"final_diff_digest": "99" * 32}
    )
    drifted = _coordinator(fresh, drift_workspace, tmp_path / "art-diff-drift").persist(
        drifted_command
    )
    assert drifted.error_code == "TREE_INTEGRITY_FAILED"
    assert drift_workspace.write_count == 0
    fresh.close()

    # Coordinator ARTIFACT_ACL_UNSAFE mapping: an unsafe artifact root
    # fails the whole writeback closed with zero writes
    # (quality review M-6c).
    fresh = _open_environment(tmp_path, "matrix-acl-mapping")
    _seed_run_and_approval(fresh, _SUBJECT)
    acl_workspace = SpyWorkspace()
    acl_workspace.seed("src/b.py", _ORIGINAL)
    unsafe_root = tmp_path / "art-acl-mapping"
    artifacts_dir = unsafe_root / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    _grant_everyone(artifacts_dir)
    acl_coordinator = _coordinator(fresh, acl_workspace, unsafe_root)
    acl_result = acl_coordinator.persist(approved_command())
    assert acl_result.error_code == "ARTIFACT_ACL_UNSAFE"
    assert acl_workspace.write_count == 0
    fresh.close()

    # Deadline crossing between the step-11 check and the first replace:
    # the provably zero-write transaction ends ROLLED_BACK with outcome
    # STOPPED (SPEC 4.6 item 11; quality review M-5).  The approval
    # subject outlives the deadline so the expiry of the run deadline is
    # the stopping fact.
    fresh = _open_environment(tmp_path, "matrix-deadline-window")
    _seed_run_and_approval(fresh, late_subject)
    window_workspace = SpyWorkspace()
    window_workspace.seed("src/b.py", _ORIGINAL)
    window_command = _command(_DIFF, late_subject, _pending_approval(late_subject))
    window_result = _coordinator(
        fresh,
        window_workspace,
        tmp_path / "art-deadline-window",
        clock=StepClock(limit=5),
    ).persist(window_command)
    assert window_result.outcome == "STOPPED" and window_result.error_code is None
    assert window_workspace.write_count == 0
    assert _transaction_state(fresh) == ("ROLLED_BACK",)
    fresh.close()

    # Untouched tracked-file recheck (SPEC 4.6 item 9): a tracked file
    # outside the writeback that changed prevents COMMITTED and leaves a
    # durable UNRESOLVED transaction with no further writes.
    fresh = _open_environment(tmp_path, "matrix-untouched")
    _seed_run_and_approval(fresh, _SUBJECT)
    untouched_workspace = SpyWorkspace()
    untouched_workspace.seed("src/b.py", _ORIGINAL)
    untouched_workspace.flip_untouched()
    untouched = _coordinator(
        fresh, untouched_workspace, tmp_path / "art-untouched"
    ).persist(approved_command())
    assert untouched.outcome == "RECOVERY_REQUIRED"
    assert untouched.error_code == "WORKSPACE_CHANGED"
    assert untouched_workspace.write_count == 2
    assert _transaction_state(fresh) == ("UNRESOLVED",)
    fresh.close()

    # 1-path and 3-path ordering: CREATE-only and mixed 3-path commands
    # replace in sorted canonical-path order with the exact bodies.
    fresh = _open_environment(tmp_path, "matrix-one")
    _seed_run_and_approval(fresh, _SUBJECT_ONE)
    one_workspace = SpyWorkspace()
    one_result = _coordinator(fresh, one_workspace, tmp_path / "art-one").persist(
        _command(_DIFF_ONE, _SUBJECT_ONE, _pending_approval(_SUBJECT_ONE))
    )
    assert one_result.outcome == "SUCCEEDED"
    assert one_workspace.write_count == 1
    assert one_workspace.files == {"src/a.py": _BODIES["src/a.py"]}
    assert _transaction_state(fresh) == ("COMMITTED",)
    fresh.close()

    fresh = _open_environment(tmp_path, "matrix-three")
    _seed_run_and_approval(fresh, _SUBJECT_THREE)
    three_workspace = SpyWorkspace()
    three_workspace.seed("src/b.py", _ORIGINAL)
    three_workspace.seed("src/c.py", _ORIGINAL)
    three_result = _coordinator(fresh, three_workspace, tmp_path / "art-three").persist(
        _command(_DIFF_THREE, _SUBJECT_THREE, _pending_approval(_SUBJECT_THREE))
    )
    assert three_result.outcome == "SUCCEEDED"
    assert three_workspace.write_count == 3
    assert three_workspace.writes == [
        ("src/a.py", _BODIES["src/a.py"]),
        ("src/b.py", _BODIES["src/b.py"]),
        ("src/c.py", _BODIES["src/c.py"]),
    ]
    assert _transaction_state(fresh) == ("COMMITTED",)
    fresh.close()
