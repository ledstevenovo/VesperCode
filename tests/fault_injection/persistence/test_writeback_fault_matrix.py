"""T26.1 legacy step 26.E: deterministic writeback fault matrix tests.

Arms every injected interruption point of the approval-bound atomic
writeback protocol (PREPARED, WRITING, per-path REPLACE and PROGRESS,
TERMINAL, each BEFORE and AFTER) and pins the durable classifiable
observation every interruption leaves: the transaction state, the
per-path durable states, and the exact workspace byte/write facts.  No
interruption ever reports false success — the injected fault propagates
and every durable fact is honest, including the lagging write count
(SPEC 4.6 item 8: durable facts are progress facts, never an authority
over current bytes).
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
from vespercode.persistence.transaction import (
    PersistencePathRecordRepositoryV1,
    PersistenceTransactionRepositoryV1,
)
from vespercode.persistence.writeback import (
    PersistenceCommandFactoryV1,
    PersistenceCoordinator,
    PersistenceFaultInjectedError,
    PersistVerifiedCandidateV1,
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
_TEXT_METADATA = TextMetadataV1(encoding="UTF8", newline="LF", final_newline=True)

_BODIES = {
    "src/a.py": b"new a\n",
    "src/b.py": b"new b\n",
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


def final_diff() -> FinalDiffV1:
    """One sealed two-path diff: CREATE src/a.py, REPLACE src/b.py."""
    entries = (
        FinalDiffEntryV1(
            operation="CREATE",
            path=CanonicalRelativePathV1("src/a.py"),
            preimage=FinalDiffPreimageV1(kind="ABSENT"),
            postimage_digest=hashlib.sha256(_BODIES["src/a.py"]).hexdigest(),
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
            postimage_digest=hashlib.sha256(_BODIES["src/b.py"]).hexdigest(),
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
            "added_and_replacement_text_bytes": sum(
                len(_BODIES[entry.path.value]) for entry in entries
            ),
        },
    )
    return FinalDiffV1(
        schema_version=1,
        snapshot_tree_digest=_SNAPSHOT_DIGEST,
        entries=entries,
        added_and_replacement_text_bytes=sum(
            len(_BODIES[entry.path.value]) for entry in entries
        ),
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


class SpyWorkspace:
    """In-memory workspace port: bytes, identities, and write counting."""

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}
        self._identities: dict[str, str] = {}
        self._writes: list[tuple[str, bytes]] = []
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

    def replace(self, path: CanonicalRelativePathV1, body: bytes) -> None:
        self._files[path.value] = body
        self._writes.append((path.value, body))

    def delete(self, path: CanonicalRelativePathV1) -> None:
        del self._files[path.value]
        self._deletes.append(path.value)

    def verify_postimage(self, path: CanonicalRelativePathV1, digest: str) -> bool:
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


class ArmedFaultPort:
    """A deterministic fault port that interrupts exactly one armed point."""

    def __init__(self, point: WritebackFaultPointV1) -> None:
        self._point = point

    def raise_at(self, point: WritebackFaultPointV1) -> None:
        if point == self._point:
            raise PersistenceFaultInjectedError(f"armed fault point: {point}")


def _command(event_id: str = "evt-fault") -> PersistVerifiedCandidateV1:
    approval = FinalWritebackApprovalV1(
        schema_version=1,
        approval_id="approval-1",
        subject_digest=DigestV1(value=_SUBJECT.digest),
        run_id="run-1",
        wait_id="wait-1",
        created_at=_DECIDED_AT,
        status="PENDING",
    )
    return PersistenceCommandFactoryV1(
        final_diff=_DIFF,
        candidate_digest=_CANDIDATE_DIGEST,
        policy_digest=_EDITABLE_DIGEST,
        workspace_identity_digest=_WORKSPACE_IDENTITY_DIGEST,
        workspace_preimage_digest=_WORKSPACE_PREIMAGE_DIGEST,
        approval=approval,
        approval_subject=_SUBJECT,
        run_deadline=_RUN_DEADLINE,
        postimage_bodies=(
            WritebackBodyV1(
                schema_version=1,
                path=CanonicalRelativePathV1("src/a.py"),
                operation="CREATE",
                body=_BODIES["src/a.py"],
            ),
            WritebackBodyV1(
                schema_version=1,
                path=CanonicalRelativePathV1("src/b.py"),
                operation="REPLACE",
                body=_BODIES["src/b.py"],
            ),
        ),
    ).for_approved_run(run_id="run-1", approval_id="approval-1", event_id=event_id)


def _open_environment(tmp_path: Path, name: str) -> ControlDatabase:
    database = open_control_database(tmp_path / f"{name}.db")
    assert apply_migrations(database, _ALL_MIGRATIONS).kind == "APPLIED"
    _seed_run_and_approval(database)
    return database


def _coordinator(
    database: ControlDatabase,
    workspace: SpyWorkspace,
    tmp_path: Path,
    fault: WritebackFaultPointV1 | None,
) -> PersistenceCoordinator:
    return PersistenceCoordinator(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=PersistenceArtifactStoreV1(tmp_path / "artifacts"),
        approval_repository=WritebackApprovalRepository(database),
        workspace=workspace,
        policy=_MANIFEST.editable_path_policy,
        clock=FakeClockV1.from_epoch_milliseconds(_CONSUMED_AT.epoch_milliseconds),
        faults=ArmedFaultPort(fault) if fault is not None else None,
    )


def _durable_facts(
    database: ControlDatabase,
    workspace: SpyWorkspace,
) -> tuple[str, tuple[str, ...], dict[str, bytes]]:
    """The (transaction state, per-path durable states, workspace bytes)."""
    with database.immediate_transaction() as tx:
        row = tx.execute(
            "SELECT state FROM persistence_transactions ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        records = tx.execute(
            "SELECT path, durable_state FROM persistence_path_records ORDER BY sequence"
        ).fetchall()
    state = str(row[0]) if row is not None else "NONE"
    path_states = tuple(str(record[1]) for record in records)
    return state, path_states, workspace.files


def test_writeback_fault_matrix(tmp_path: Path) -> None:
    """Every injected interruption leaves an honest durable observation.

    The complete fault sequence for the two-path transaction: the armed
    point that matches the first protocol step halts the run; the durable
    facts at the stop are the last durably persisted facts (never an
    authority over current bytes) and no interruption reports success.
    """
    cases: list[tuple[WritebackFaultPointV1 | None, str, int, tuple[str, ...]]] = [
        # (fault point, expected transaction state, expected writes,
        #  expected per-path durable states in sequence order)
        (WritebackFaultPointV1("PREPARED", "BEFORE"), "NONE", 0, ()),
        (
            WritebackFaultPointV1("PREPARED", "AFTER"),
            "PREPARED",
            0,
            ("NOT_STARTED", "NOT_STARTED"),
        ),
        (
            WritebackFaultPointV1("WRITING", "BEFORE"),
            "PREPARED",
            0,
            ("NOT_STARTED", "NOT_STARTED"),
        ),
        (
            WritebackFaultPointV1("WRITING", "AFTER"),
            "WRITING",
            0,
            ("NOT_STARTED", "NOT_STARTED"),
        ),
        (
            WritebackFaultPointV1("REPLACE", "BEFORE", 1),
            "WRITING",
            0,
            ("NOT_STARTED", "NOT_STARTED"),
        ),
        # File replaced but the REPLACED state not yet durable: the path
        # state honestly lags (SPEC 4.6 item 8).
        (
            WritebackFaultPointV1("REPLACE", "AFTER", 1),
            "WRITING",
            1,
            ("NOT_STARTED", "NOT_STARTED"),
        ),
        (
            WritebackFaultPointV1("PROGRESS", "BEFORE", 1),
            "WRITING",
            1,
            ("NOT_STARTED", "NOT_STARTED"),
        ),
        # PROGRESS wraps the REPLACED + VERIFIED progress writes, so the
        # AFTER stop leaves the completed progress durably recorded.
        (
            WritebackFaultPointV1("PROGRESS", "AFTER", 1),
            "WRITING",
            1,
            ("VERIFIED", "NOT_STARTED"),
        ),
        (
            WritebackFaultPointV1("REPLACE", "BEFORE", 2),
            "WRITING",
            1,
            ("VERIFIED", "NOT_STARTED"),
        ),
        (
            WritebackFaultPointV1("REPLACE", "AFTER", 2),
            "WRITING",
            2,
            ("VERIFIED", "NOT_STARTED"),
        ),
        (
            WritebackFaultPointV1("PROGRESS", "BEFORE", 2),
            "WRITING",
            2,
            ("VERIFIED", "NOT_STARTED"),
        ),
        (
            WritebackFaultPointV1("PROGRESS", "AFTER", 2),
            "WRITING",
            2,
            ("VERIFIED", "VERIFIED"),
        ),
        (
            WritebackFaultPointV1("TERMINAL", "BEFORE"),
            "WRITING",
            2,
            ("VERIFIED", "VERIFIED"),
        ),
        # TERMINAL_AFTER: the COMMITTED record is durable; the injected
        # interruption still surfaces (no false success to the caller).
        (
            WritebackFaultPointV1("TERMINAL", "AFTER"),
            "COMMITTED",
            2,
            ("VERIFIED", "VERIFIED"),
        ),
        (None, "COMMITTED", 2, ("VERIFIED", "VERIFIED")),
    ]
    for index, (
        fault,
        expected_state,
        expected_writes,
        expected_path_states,
    ) in enumerate(cases):
        database = _open_environment(tmp_path, f"fault-{index}")
        workspace = SpyWorkspace()
        workspace.seed("src/b.py", _ORIGINAL)
        coordinator = _coordinator(database, workspace, tmp_path, fault)
        if fault is not None:
            with pytest.raises(PersistenceFaultInjectedError):
                coordinator.persist(_command(event_id=f"evt-fault-{index}"))
        else:
            result = coordinator.persist(_command(event_id=f"evt-fault-{index}"))
            assert result.outcome == "SUCCEEDED"
        state, path_states, files = _durable_facts(database, workspace)
        assert state == expected_state, f"case {fault}: transaction state {state}"
        assert path_states == expected_path_states, f"case {fault}: path states"
        assert workspace.write_count == expected_writes, f"case {fault}: write count"
        if expected_writes >= 1:
            assert files["src/a.py"] == _BODIES["src/a.py"]
        else:
            assert "src/a.py" not in files
        if expected_writes >= 2:
            assert files["src/b.py"] == _BODIES["src/b.py"]
        else:
            assert files["src/b.py"] == _ORIGINAL
        database.close()
