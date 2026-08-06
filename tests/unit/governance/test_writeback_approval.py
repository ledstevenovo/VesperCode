"""T14.1 legacy step 14.C: one-time concurrent writeback approval consume.

Pins the transaction-bound consume-once semantics of
``WritebackApprovalRepository.consume`` over one exact current PENDING
approval: the in-transaction reverification against the stored subject
row (candidate/validation/policy binding and Run identity), the
expiry/rejection/stale/already-consumed closed outcomes with zero
persistence calls, the pure ``verify_consumable`` pre-check, and the
idempotent exact replay.  Wait decisions, subject construction, DENY
override, and workspace persistence remain out of scope (GREEN-4).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

# The repository consumes pydantic runtime contracts; the hash-locked
# gate toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from src.vespercode.candidate.final_diff import (
    FinalDiffEntryV1,
    FinalDiffPreimageV1,
    FinalDiffV1,
)
from src.vespercode.canonical.digest import domain_digest
from src.vespercode.canonical.json_v1 import CanonicalValueV1
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.evidence import DigestV1
from src.vespercode.contracts.run import WaitContextV1, WaitDecisionV1
from src.vespercode.governance.writeback_approval import (
    ApprovalNotConsumableErrorV1,
    ApprovalConsumptionResultV1,
    ConsumeWritebackApprovalV1,
    WritebackApprovalRepository,
    verify_consumable,
)
from src.vespercode.governance.writeback_decision import (
    DecideFinalWritebackV1,
    FinalWritebackApprovalV1,
    FinalWritebackDecisionServiceV1,
)
from src.vespercode.governance.writeback_subject import (
    FinalWritebackBindingV1,
    FinalWritebackSubjectV1,
    build_final_writeback_subject,
)
from src.vespercode.profiles.reference import (
    ReferenceProfileManifestV1,
    load_reference_profile,
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
from src.vespercode.storage.run_repository import RunRepository
from src.vespercode.trees.text_classifier import TextMetadataV1

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
    expires_at: CanonicalTimestampV1 = _EXPIRES_AT,
    candidate_digest: str = _CANDIDATE_DIGEST,
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


def _setup(database: ControlDatabase) -> None:
    """One run, one pending final-writeback wait, one PENDING approval."""
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
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "approval.db")
    apply_migrations(database, _ALL_MIGRATIONS)
    _setup(database)
    yield database
    database.close()


@pytest.fixture
def repository(
    control_database: ControlDatabase,
) -> WritebackApprovalRepository:
    return WritebackApprovalRepository(control_database)


def consumable_command(
    *,
    approval_id: str = "approval-1",
    subject: FinalWritebackSubjectV1 = _SUBJECT,
    event_id: str = "evt-consume",
    consumed_at: CanonicalTimestampV1 = _CONSUMED_AT,
) -> ConsumeWritebackApprovalV1:
    """One exact current consumption command."""
    return ConsumeWritebackApprovalV1(
        approval_id=approval_id,
        subject=subject,
        event_id=event_id,
        consumed_at=consumed_at,
    )


def _approval_status(
    control_database: ControlDatabase, approval_id: str = "approval-1"
) -> str:
    rows = control_database.read_rows(
        "SELECT status FROM writeback_approvals WHERE approval_id = ?",
        (approval_id,),
    )
    assert len(rows) == 1
    return str(rows[0][0])


def _approval_row_count(control_database: ControlDatabase) -> int:
    return len(control_database.read_rows("SELECT 1 FROM writeback_approvals"))


def test_exact_current_pending_approval_consumes_once(
    control_database: ControlDatabase,
    repository: WritebackApprovalRepository,
) -> None:
    """GREEN-1/GREEN-2: the exact current PENDING approval transitions
    to CONSUMED exactly once; the exact replay is stable and performs no
    second consumption."""
    first = repository.consume(consumable_command())
    assert first.kind == "CONSUMED"
    assert _approval_status(control_database) == "CONSUMED"
    second = repository.consume(consumable_command())
    assert second.kind == "ALREADY_CONSUMED"
    assert _approval_status(control_database) == "CONSUMED"
    assert _approval_row_count(control_database) == 1


def test_verify_consumable_pure_precheck(
    repository: WritebackApprovalRepository,
) -> None:
    """The pure pre-check accepts the exact consumable command and
    rejects every non-consumable state with its closed code."""
    approval = FinalWritebackApprovalV1(
        schema_version=1,
        approval_id="approval-1",
        subject_digest=DigestV1(value=_SUBJECT.digest),
        run_id="run-1",
        wait_id="wait-1",
        created_at=_DECIDED_AT,
        status="PENDING",
    )
    verify_consumable(approval, consumable_command())
    with pytest.raises(ApprovalNotConsumableErrorV1) as exc:
        verify_consumable(
            approval.model_copy(update={"status": "CONSUMED"}),
            consumable_command(),
        )
    assert exc.value.error_code == "ALREADY_CONSUMED"
    with pytest.raises(ApprovalNotConsumableErrorV1) as exc:
        verify_consumable(
            approval.model_copy(update={"status": "REJECTED"}),
            consumable_command(),
        )
    assert exc.value.error_code == "REJECTED"
    with pytest.raises(ApprovalNotConsumableErrorV1) as exc:
        verify_consumable(
            approval.model_copy(update={"status": "EXPIRED"}),
            consumable_command(),
        )
    assert exc.value.error_code == "EXPIRED"
    with pytest.raises(ApprovalNotConsumableErrorV1) as exc:
        verify_consumable(
            approval,
            consumable_command(subject=subject(run_id="run-other")),
        )
    assert exc.value.error_code == "STALE"
    with pytest.raises(ApprovalNotConsumableErrorV1) as exc:
        verify_consumable(approval, consumable_command(consumed_at=_LATE_CONSUMED_AT))
    assert exc.value.error_code == "EXPIRED"


def test_missing_approval_rejected(
    repository: WritebackApprovalRepository,
) -> None:
    result = repository.consume(consumable_command(approval_id="approval-missing"))
    assert result.kind == "NOT_FOUND"


def test_stale_subject_rejected(
    control_database: ControlDatabase,
    repository: WritebackApprovalRepository,
) -> None:
    """A subject whose facts drifted (different digest) consumes nothing."""
    drifted = subject(candidate_digest=hashlib.sha256(b"other").hexdigest())
    result = repository.consume(
        consumable_command(subject=drifted, event_id="evt-drift")
    )
    assert result.kind == "STALE"
    assert _approval_status(control_database) == "PENDING"
    assert _approval_row_count(control_database) == 1


def test_expired_approval_rejected(
    control_database: ControlDatabase,
    repository: WritebackApprovalRepository,
) -> None:
    """A consumption past the subject expiry consumes nothing and performs
    zero persistence calls (the status stays PENDING; Registry row 14.C)."""
    result = repository.consume(consumable_command(consumed_at=_LATE_CONSUMED_AT))
    assert result.kind == "EXPIRED"
    assert _approval_status(control_database) == "PENDING"
    assert _approval_row_count(control_database) == 1


def test_rejected_approval_rejected(
    control_database: ControlDatabase,
    repository: WritebackApprovalRepository,
) -> None:
    """A REJECTED-status approval row consumes nothing (no decision path
    creates one in T14.1; the status is schema vocabulary for recovery)."""
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE writeback_approvals SET status = 'REJECTED'"
            " WHERE approval_id = 'approval-1'"
        )
    result = repository.consume(consumable_command())
    assert result.kind == "REJECTED"
    assert _approval_status(control_database) == "REJECTED"
    assert _approval_row_count(control_database) == 1


def test_approval_row_missing_subject_row_fails_closed(
    control_database: ControlDatabase,
    repository: WritebackApprovalRepository,
) -> None:
    """A PENDING approval whose subject row is missing fails closed with
    zero persistence (storage corruption is never consumable)."""
    # The DDL FK makes the missing-row state reachable only through
    # corruption; disable FK enforcement on this connection to model it.
    control_database.read_rows("PRAGMA foreign_keys = OFF")
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "DELETE FROM writeback_approval_subjects WHERE subject_digest = ?",
            (_SUBJECT.digest,),
        )
    result = repository.consume(consumable_command())
    assert result.kind == "STALE"
    assert _approval_status(control_database) == "PENDING"
    assert _approval_row_count(control_database) == 1


def test_stored_subject_field_drift_fails_closed(
    control_database: ControlDatabase,
    repository: WritebackApprovalRepository,
) -> None:
    """A PENDING approval whose stored subject facts were tampered fails
    closed with zero persistence (only a fully matching current subject
    consumes, SPEC §4.4.2)."""
    # The DDL FK makes the drifted-row state reachable only through
    # corruption; disable FK enforcement on this connection to model it.
    control_database.read_rows("PRAGMA foreign_keys = OFF")
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE writeback_approval_subjects SET candidate_digest = ?"
            " WHERE subject_digest = ?",
            (hashlib.sha256(b"tampered").hexdigest(), _SUBJECT.digest),
        )
    result = repository.consume(consumable_command())
    assert result.kind == "STALE"
    assert _approval_status(control_database) == "PENDING"
    assert _approval_row_count(control_database) == 1


def test_stored_expired_status_rejected(
    control_database: ControlDatabase,
    repository: WritebackApprovalRepository,
) -> None:
    """An approval row already settled EXPIRED consumes nothing and
    performs zero persistence calls."""
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE writeback_approvals SET status = 'EXPIRED'"
            " WHERE approval_id = 'approval-1'"
        )
    result = repository.consume(consumable_command())
    assert result.kind == "EXPIRED"
    assert _approval_status(control_database) == "EXPIRED"
    assert _approval_row_count(control_database) == 1


def test_consume_result_model_is_closed() -> None:
    """The closed result vocabulary carries exactly the declared kinds."""
    assert (
        ApprovalConsumptionResultV1(kind="CONSUMED", message="consumed").kind
        == "CONSUMED"
    )
    assert (
        ApprovalConsumptionResultV1(
            kind="ALREADY_CONSUMED", message="already consumed"
        ).kind
        == "ALREADY_CONSUMED"
    )
    assert ApprovalConsumptionResultV1(kind="NOT_FOUND", message="missing").kind == (
        "NOT_FOUND"
    )
    assert ApprovalConsumptionResultV1(kind="STALE", message="stale").kind == "STALE"
    assert ApprovalConsumptionResultV1(kind="EXPIRED", message="expired").kind == (
        "EXPIRED"
    )
    assert ApprovalConsumptionResultV1(kind="REJECTED", message="rejected").kind == (
        "REJECTED"
    )
