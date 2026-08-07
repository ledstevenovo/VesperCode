"""T14.1 legacy step 14.C: writeback approval consumption race tests.

Pins the exact RED (two concurrent consumers of the same exact current
PENDING approval yield exactly one CONSUMED success) and the consumption
matrix over the PLAN Registry row 14.C: two exact concurrent consumers
produce exactly one CONSUMED success, and stale, expired, rejected,
subject-mismatched, or already-consumed approval performs zero
persistence calls.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

# The repository consumes pydantic runtime contracts; the hash-locked
# gate toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from vespercode.candidate.final_diff import (
    FinalDiffEntryV1,
    FinalDiffPreimageV1,
    FinalDiffV1,
)
from vespercode.canonical.digest import domain_digest
from vespercode.canonical.json_v1 import CanonicalValueV1
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import DigestV1
from vespercode.contracts.run import WaitContextV1, WaitDecisionV1
from vespercode.governance.writeback_approval import (
    ApprovalConsumptionResultV1,
    ConsumeWritebackApprovalV1,
    WritebackApprovalRepository,
)
from vespercode.governance.writeback_decision import (
    DecideFinalWritebackV1,
    FinalWritebackDecisionServiceV1,
)
from vespercode.governance.writeback_subject import (
    FinalWritebackBindingV1,
    FinalWritebackSubjectV1,
    build_final_writeback_subject,
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
)

_CREATED_AT = CanonicalTimestampV1("2026-08-05T09:00:00.000Z")
_EXPIRES_AT = CanonicalTimestampV1("2026-08-05T09:05:00.000Z")
_DECIDED_AT = CanonicalTimestampV1("2026-08-05T09:01:00.000Z")
_CONSUMED_AT = CanonicalTimestampV1("2026-08-05T09:02:00.000Z")
_LATE_CONSUMED_AT = CanonicalTimestampV1("2026-08-05T09:06:00.000Z")
_RUN_DEADLINE = CanonicalTimestampV1("2026-08-05T09:15:00.000Z")
_REFERENCE_MANIFEST = (
    Path(__file__).resolve().parents[3] / "reference/manifest/reference-profile-v1.json"
)


def manifest() -> ReferenceProfileManifestV1:
    """The frozen packaged reference profile (digest-verified)."""
    loaded = load_reference_profile(_REFERENCE_MANIFEST.read_bytes())
    assert isinstance(loaded, ReferenceProfileManifestV1)
    return loaded


_MANIFEST = manifest()
_EDITABLE_DIGEST = _MANIFEST.editable_path_policy.digest
_SNAPSHOT_DIGEST = hashlib.sha256(b"sealed-snapshot").hexdigest()
_CANDIDATE_DIGEST = hashlib.sha256(b"candidate-identity").hexdigest()
_VALIDATION_DIGEST = hashlib.sha256(b"validation-manifest").hexdigest()
_FORMAL_EVIDENCE_DIGEST = hashlib.sha256(b"formal-evidence").hexdigest()
_PREIMAGE_DIGEST = hashlib.sha256(b"workspace-preimage").hexdigest()
_RUN_CONFIG_DIGEST = hashlib.sha256(b"run-config").hexdigest()
_TEXT_METADATA = TextMetadataV1(encoding="UTF8", newline="LF", final_newline=True)


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


def _final_diff() -> FinalDiffV1:
    """One sealed current FinalDiff whose digest binds its exact rows."""
    raw = b"x = 1\n"
    entry = FinalDiffEntryV1(
        operation="REPLACE",
        path=CanonicalRelativePathV1("src/a.py"),
        preimage=FinalDiffPreimageV1(
            kind="PRESENT",
            content_digest=hashlib.sha256(raw).hexdigest(),
            text_metadata=_TEXT_METADATA,
        ),
        postimage_digest=hashlib.sha256(raw).hexdigest(),
        postimage_text_metadata=_TEXT_METADATA,
    )
    digest = domain_digest(
        "FinalDiffV1",
        1,
        {
            "schema_version": 1,
            "snapshot_tree_digest": _SNAPSHOT_DIGEST,
            "entries": tuple(_canonical_entry(entry) for entry in (entry,)),
            "added_and_replacement_text_bytes": len(raw),
        },
    )
    return FinalDiffV1(
        schema_version=1,
        snapshot_tree_digest=_SNAPSHOT_DIGEST,
        entries=(entry,),
        added_and_replacement_text_bytes=len(raw),
        digest=digest,
    )


def subject(
    run_id: str = "run-1",
    candidate_digest: str = _CANDIDATE_DIGEST,
    expires_at: CanonicalTimestampV1 = _EXPIRES_AT,
) -> FinalWritebackSubjectV1:
    """One exact current writeback subject for the declared facts."""
    return build_final_writeback_subject(
        FinalWritebackBindingV1(
            run_id=run_id,
            candidate_digest=candidate_digest,
            final_diff=_final_diff(),
            validation_manifest_digest=_VALIDATION_DIGEST,
            validation_repository_policy_digest=_EDITABLE_DIGEST,
            formal_evidence_digest=_FORMAL_EVIDENCE_DIGEST,
            workspace_preimage_digest=_PREIMAGE_DIGEST,
            run_config_digest=_RUN_CONFIG_DIGEST,
            run_config_reference_profile_digest=_MANIFEST.digest,
            run_config_policy_id="PYTHON_SRC_ONLY_V1",
            reference_profile_digest=_MANIFEST.digest,
            reference_policy_digest=_EDITABLE_DIGEST,
            policy=_MANIFEST.editable_path_policy,
        ),
        expires_at,
    )


_SUBJECT = subject()
_SUBJECT_RUN2 = subject(run_id="run-2")


def _create_approved_approval(database: ControlDatabase) -> None:
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


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "approval_race.db"
    database = open_control_database(path)
    apply_migrations(database, _ALL_MIGRATIONS)
    _create_approved_approval(database)
    database.close()
    return path


@pytest.fixture
def repository(database_path: Path) -> Iterator[WritebackApprovalRepository]:
    database = open_control_database(database_path)
    yield WritebackApprovalRepository(database, database_path)
    database.close()


def consumable_command() -> ConsumeWritebackApprovalV1:
    """One exact current consumption command."""
    return ConsumeWritebackApprovalV1(
        approval_id="approval-1",
        subject=_SUBJECT,
        event_id="evt-consume",
        consumed_at=_CONSUMED_AT,
    )


def run_two_consumers(
    repository: WritebackApprovalRepository,
    command: ConsumeWritebackApprovalV1,
) -> list[ApprovalConsumptionResultV1]:
    """Two concurrent consumers of the same exact command; each thread
    opens its own connection to the same on-disk file (sqlite3
    connections are thread-bound) so BEGIN IMMEDIATE serializes them."""
    results: list[ApprovalConsumptionResultV1] = []
    barrier = threading.Barrier(2, timeout=60)
    database_path = repository.database_path

    def _consume_once() -> None:
        database = open_control_database(database_path)
        try:
            worker = WritebackApprovalRepository(database)
            barrier.wait()
            results.append(worker.consume(command))
        finally:
            database.close()

    threads = [threading.Thread(target=_consume_once) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return results


def test_concurrent_consumers_get_exactly_one_success(
    repository: WritebackApprovalRepository,
) -> None:
    results = run_two_consumers(repository, consumable_command())
    assert sorted(result.kind for result in results) == ["ALREADY_CONSUMED", "CONSUMED"]


def test_writeback_approval_consumption_matrix(
    database_path: Path,
    repository: WritebackApprovalRepository,
) -> None:
    """PLAN Registry row 14.C.

    Two exact concurrent consumers produce exactly one CONSUMED success;
    stale, expired, rejected, subject-mismatched, or already-consumed
    approval performs zero persistence calls.
    """
    # Two exact concurrent consumers: exactly one CONSUMED success.
    results = run_two_consumers(repository, consumable_command())
    assert sorted(result.kind for result in results) == ["ALREADY_CONSUMED", "CONSUMED"]
    statuses = repository.database.read_rows(
        "SELECT status FROM writeback_approvals WHERE approval_id = 'approval-1'"
    )
    assert len(statuses) == 1
    assert str(statuses[0][0]) == "CONSUMED"

    # Already-consumed: the exact replay performs zero persistence calls.
    replay = repository.consume(consumable_command())
    assert replay.kind == "ALREADY_CONSUMED"
    assert len(repository.database.read_rows("SELECT 1 FROM writeback_approvals")) == 1

    # A second approved approval for a fresh run/wait:
    # stale (drifted candidate), expired (late clock), rejected (status),
    # and subject-mismatched (different subject) each consume zero rows.
    with repository.database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots"
            " (config_snapshot_id, digest, llm_profile_id, reference_profile_id,"
            " policy_id, target_test_ids, limits_digest, frozen_at)"
            " VALUES ('snap-2', ?, 'mock-deterministic-v1', 'python-src-py312-v1',"
            " 'PYTHON_SRC_ONLY_V1', '[]', ?, ?)",
            ("b" * 64, "d" * 64, _CREATED_AT.value),
        )
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES ('run-2', 'ws-1', 'snap-2', 'WAITING_USER', NULL, 1, ?, ?)",
            (_CREATED_AT.value, _RUN_DEADLINE.value),
        )
    RunRepository(repository.database).create_wait(
        WaitContextV1(
            wait_id="wait-2",
            run_id="run-2",
            wait_kind="FINAL_WRITEBACK",
            source_phase="FORMAL_VALIDATION",
            subject_digest=DigestV1(value=_SUBJECT_RUN2.digest),
            created_at=_CREATED_AT,
            expires_at=_EXPIRES_AT,
        )
    )
    second = FinalWritebackDecisionServiceV1(repository.database).decide(
        DecideFinalWritebackV1(
            decision=WaitDecisionV1(
                wait_id="wait-2",
                run_id="run-2",
                wait_kind="FINAL_WRITEBACK",
                subject_digest=DigestV1(value=_SUBJECT_RUN2.digest),
                decision="APPROVE",
                event_id="evt-approve-2",
                decided_at=_DECIDED_AT,
            ),
            subject=_SUBJECT_RUN2,
            approval_id="approval-2",
        )
    )
    assert second.kind == "APPROVED"

    # Stale: a drifted candidate identity (new subject digest).
    drifted = subject(
        run_id="run-2", candidate_digest=hashlib.sha256(b"other").hexdigest()
    )
    stale = repository.consume(
        ConsumeWritebackApprovalV1(
            approval_id="approval-2",
            subject=drifted,
            event_id="evt-stale",
            consumed_at=_CONSUMED_AT,
        )
    )
    assert stale.kind == "STALE"
    assert (
        repository.database.read_rows(
            "SELECT status FROM writeback_approvals WHERE approval_id = 'approval-2'"
        )[0][0]
        == "PENDING"
    )

    # Expired: a consumption past the subject expiry.
    expired = repository.consume(
        ConsumeWritebackApprovalV1(
            approval_id="approval-2",
            subject=_SUBJECT_RUN2,
            event_id="evt-expired",
            consumed_at=_LATE_CONSUMED_AT,
        )
    )
    assert expired.kind == "EXPIRED"
    # Zero persistence calls: the status stays PENDING (Registry row 14.C).
    assert (
        repository.database.read_rows(
            "SELECT status FROM writeback_approvals WHERE approval_id = 'approval-2'"
        )[0][0]
        == "PENDING"
    )

    # Subject-mismatched: the stored subject row no longer exists.
    # (The DDL FK makes the missing-row state reachable only through
    # corruption; FK enforcement is disabled on this connection to model
    # it, and the consume fails closed with zero persistence.)
    repository.database.read_rows("PRAGMA foreign_keys = OFF")
    with repository.database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE writeback_approvals SET status = 'PENDING'"
            " WHERE approval_id = 'approval-2'"
        )
        tx.execute(
            "DELETE FROM writeback_approval_subjects WHERE subject_digest = ?",
            (_SUBJECT_RUN2.digest,),
        )
    mismatched = repository.consume(
        ConsumeWritebackApprovalV1(
            approval_id="approval-2",
            subject=_SUBJECT_RUN2,
            event_id="evt-mismatch",
            consumed_at=_CONSUMED_AT,
        )
    )
    assert mismatched.kind == "STALE"
    assert (
        repository.database.read_rows(
            "SELECT status FROM writeback_approvals WHERE approval_id = 'approval-2'"
        )[0][0]
        == "PENDING"
    )

    # Rejected: a REJECTED-status approval row consumes nothing.
    with repository.database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE writeback_approvals SET status = 'REJECTED'"
            " WHERE approval_id = 'approval-2'"
        )
    rejected = repository.consume(
        ConsumeWritebackApprovalV1(
            approval_id="approval-2",
            subject=_SUBJECT_RUN2,
            event_id="evt-rejected",
            consumed_at=_CONSUMED_AT,
        )
    )
    assert rejected.kind == "REJECTED"
    assert (
        repository.database.read_rows(
            "SELECT status FROM writeback_approvals WHERE approval_id = 'approval-2'"
        )[0][0]
        == "REJECTED"
    )

    # Zero extra persistence across every failure row.
    assert len(repository.database.read_rows("SELECT 1 FROM writeback_approvals")) == 2
    assert (
        len(repository.database.read_rows("SELECT 1 FROM writeback_approval_subjects"))
        == 1
    )
