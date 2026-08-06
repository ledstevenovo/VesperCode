"""T14.1 legacy step 14.B: atomic final-writeback wait decision tests.

Pins the exact RED (an expired final-writeback wait creates no PENDING
approval), the one-winner approve/reject semantics over the T07.2 wait
lock, the expiry/stale/wrong-binding/cancelled/duplicate/replay-conflict
rejections with zero approval creation, the immutable subject-row
persistence, the WAITING_USER → RUNNING(PERSISTENCE) return transition
on approval, and the decision state matrix (PLAN Registry row 14.B).
Final registry edits, approval consumption, candidate-byte persistence,
and any DENY override remain out of scope (GREEN-4).
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Iterator
from pathlib import Path
import pytest

# The service consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips cleanly
# there (formal env runs it fully).
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
from src.vespercode.trees.text_classifier import TextMetadataV1
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

from pydantic import ValidationError

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
_LATE_DECIDED_AT = CanonicalTimestampV1("2026-08-05T09:06:00.000Z")
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
_TEXT_METADATA = TextMetadataV1(encoding="UTF8", newline="LF", final_newline=True)
_SNAPSHOT_DIGEST = hashlib.sha256(b"sealed-snapshot").hexdigest()
_CANDIDATE_DIGEST = hashlib.sha256(b"candidate-identity").hexdigest()
_VALIDATION_DIGEST = hashlib.sha256(b"validation-manifest").hexdigest()
_FORMAL_EVIDENCE_DIGEST = hashlib.sha256(b"formal-evidence").hexdigest()
_PREIMAGE_DIGEST = hashlib.sha256(b"workspace-preimage").hexdigest()
_RUN_CONFIG_DIGEST = hashlib.sha256(b"run-config").hexdigest()


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


def _final_diff(path: str = "src/a.py", raw: bytes = b"x = 1\n") -> FinalDiffV1:
    """One sealed current FinalDiff whose digest binds its exact rows."""
    entry = FinalDiffEntryV1(
        operation="REPLACE",
        path=CanonicalRelativePathV1(path),
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
    """One exact current writeback subject for the declared run/expiry."""
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


def _insert_run(database: ControlDatabase, run_id: str, status: str) -> None:
    """Insert one v0001 runs row directly at the given state."""
    with database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots"
            " (config_snapshot_id, digest, llm_profile_id, reference_profile_id,"
            " policy_id, target_test_ids, limits_digest, frozen_at)"
            " VALUES (?, ?, 'mock-deterministic-v1', 'python-src-py312-v1',"
            " 'PYTHON_SRC_ONLY_V1', '[]', ?, ?)",
            (
                f"snap-{run_id}",
                hashlib.sha256(f"snap-{run_id}".encode("utf-8")).hexdigest(),
                "c" * 64,
                _CREATED_AT.value,
            ),
        )
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES (?, 'ws-1', ?, ?, NULL, 1, ?, ?)",
            (
                run_id,
                f"snap-{run_id}",
                status,
                _CREATED_AT.value,
                _RUN_DEADLINE.value,
            ),
        )


def _create_wait(
    database: ControlDatabase,
    wait_id: str,
    run_id: str,
    subject_digest: DigestV1 = DigestV1(value=_SUBJECT.digest),
    expires_at: CanonicalTimestampV1 = _EXPIRES_AT,
) -> None:
    RunRepository(database).create_wait(
        WaitContextV1(
            wait_id=wait_id,
            run_id=run_id,
            wait_kind="FINAL_WRITEBACK",
            source_phase="FORMAL_VALIDATION",
            subject_digest=subject_digest,
            created_at=_CREATED_AT,
            expires_at=expires_at,
        )
    )


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "decision.db")
    apply_migrations(database, _ALL_MIGRATIONS)
    _insert_run(database, "run-1", "WAITING_USER")
    _create_wait(database, "wait-1", "run-1")
    yield database
    database.close()


@pytest.fixture
def service(control_database: ControlDatabase) -> FinalWritebackDecisionServiceV1:
    return FinalWritebackDecisionServiceV1(control_database)


def decide(
    *,
    wait_id: str = "wait-1",
    run_id: str = "run-1",
    subject_digest: DigestV1 = DigestV1(value=_SUBJECT.digest),
    decision: str = "APPROVE",
    event_id: str = "evt-1",
    decided_at: CanonicalTimestampV1 = _DECIDED_AT,
    subject: FinalWritebackSubjectV1 = _SUBJECT,
    approval_id: str = "approval-1",
) -> DecideFinalWritebackV1:
    return DecideFinalWritebackV1(
        decision=WaitDecisionV1(
            wait_id=wait_id,
            run_id=run_id,
            wait_kind="FINAL_WRITEBACK",
            subject_digest=subject_digest,
            decision=decision,  # type: ignore[arg-type]
            event_id=event_id,
            decided_at=decided_at,
        ),
        subject=subject,
        approval_id=approval_id,
    )


def approve_expired_wait() -> DecideFinalWritebackV1:
    return decide(decided_at=_LATE_DECIDED_AT)


def test_expired_wait_cannot_create_pending_approval(
    service: FinalWritebackDecisionServiceV1,
) -> None:
    result = service.decide(approve_expired_wait())
    assert result.kind == "EXPIRED"
    assert service.approval_count() == 0


def _wait_row(
    control_database: ControlDatabase, wait_id: str
) -> tuple[str, str | None]:
    rows = control_database.read_rows(
        "SELECT status, decision FROM wait_contexts WHERE wait_id = ?",
        (wait_id,),
    )
    assert len(rows) == 1
    decision: str | None = rows[0][1]
    return str(rows[0][0]), decision


def _run_state(
    control_database: ControlDatabase, run_id: str
) -> tuple[str, str | None]:
    rows = control_database.read_rows(
        "SELECT status, phase FROM runs WHERE run_id = ?", (run_id,)
    )
    assert len(rows) == 1
    phase: str | None = rows[0][1]
    return str(rows[0][0]), phase


def _approval_row(
    control_database: ControlDatabase, approval_id: str
) -> tuple[str, str, str]:
    rows = control_database.read_rows(
        "SELECT approval_id, subject_digest, status"
        " FROM writeback_approvals WHERE approval_id = ?",
        (approval_id,),
    )
    assert len(rows) == 1
    return str(rows[0][0]), str(rows[0][1]), str(rows[0][2])


def test_approve_creates_exactly_one_pending_approval(
    control_database: ControlDatabase,
    service: FinalWritebackDecisionServiceV1,
) -> None:
    result = service.decide(decide())
    assert result.kind == "APPROVED"
    assert result.approval is not None
    assert service.approval_count() == 1
    assert _approval_row(control_database, "approval-1") == (
        "approval-1",
        _SUBJECT.digest,
        "PENDING",
    )
    # The wait decision is recorded and the run enters PERSISTENCE.
    assert _wait_row(control_database, "wait-1") == ("DECIDED", "APPROVE")
    assert _run_state(control_database, "run-1") == ("RUNNING", "PERSISTENCE")
    # The immutable subject facts are persisted (no candidate body).
    rows = control_database.read_rows(
        "SELECT run_id, candidate_digest, final_diff_digest,"
        " validation_manifest_digest, formal_evidence_digest,"
        " workspace_preimage_digest, run_config_digest, policy_digest,"
        " reference_profile_digest, action_semantic_digest, expires_at"
        " FROM writeback_approval_subjects WHERE subject_digest = ?",
        (_SUBJECT.digest,),
    )
    assert len(rows) == 1
    assert rows[0][0] == "run-1"
    assert rows[0][1] == _CANDIDATE_DIGEST
    assert rows[0][2] == _final_diff().digest
    assert rows[0][3] == _VALIDATION_DIGEST
    assert rows[0][4] == _FORMAL_EVIDENCE_DIGEST
    assert rows[0][5] == _PREIMAGE_DIGEST
    assert rows[0][6] == _RUN_CONFIG_DIGEST
    assert rows[0][7] == _EDITABLE_DIGEST
    assert rows[0][8] == _MANIFEST.digest
    assert rows[0][9] == _SUBJECT.action_semantic_digest
    assert rows[0][10] == _EXPIRES_AT.value


def test_reject_records_decision_without_approval(
    control_database: ControlDatabase,
    service: FinalWritebackDecisionServiceV1,
) -> None:
    result = service.decide(decide(decision="REJECT"))
    assert result.kind == "REJECTED"
    assert result.approval is None
    assert service.approval_count() == 0
    assert _wait_row(control_database, "wait-1") == ("DECIDED", "REJECT")
    # No resume: the run stays WAITING_USER for the loop to terminate.
    assert _run_state(control_database, "run-1") == ("WAITING_USER", None)


def test_approve_replay_is_stable_without_second_approval(
    control_database: ControlDatabase,
    service: FinalWritebackDecisionServiceV1,
) -> None:
    first = service.decide(decide())
    second = service.decide(decide())
    assert first.kind == "APPROVED"
    assert second.kind == "REPLAY"
    assert second.approval is not None
    assert second.approval.approval_id == "approval-1"
    assert service.approval_count() == 1
    assert _approval_row(control_database, "approval-1")[2] == "PENDING"
    assert _run_state(control_database, "run-1") == ("RUNNING", "PERSISTENCE")


def test_reject_replay_is_stable(
    control_database: ControlDatabase,
    service: FinalWritebackDecisionServiceV1,
) -> None:
    first = service.decide(decide(decision="REJECT"))
    second = service.decide(decide(decision="REJECT"))
    assert first.kind == "REJECTED"
    assert second.kind == "REPLAY"
    assert service.approval_count() == 0


def test_conflicting_decision_on_decided_wait_rejected(
    control_database: ControlDatabase,
    service: FinalWritebackDecisionServiceV1,
) -> None:
    assert service.decide(decide()).kind == "APPROVED"
    conflict = service.decide(decide(decision="REJECT", event_id="evt-other"))
    assert conflict.kind == "CONFLICT"
    assert service.approval_count() == 1
    assert _wait_row(control_database, "wait-1") == ("DECIDED", "APPROVE")


def test_stale_subject_digest_rejected(
    control_database: ControlDatabase,
    service: FinalWritebackDecisionServiceV1,
) -> None:
    stale = decide(subject_digest=DigestV1(value="f" * 64))
    assert service.decide(stale).kind == "STALE"
    assert service.approval_count() == 0
    assert _wait_row(control_database, "wait-1") == ("PENDING", None)


def test_subject_expiry_must_equal_wait_expiry(
    control_database: ControlDatabase,
    service: FinalWritebackDecisionServiceV1,
) -> None:
    drifted = subject(expires_at=CanonicalTimestampV1("2026-08-05T09:10:00.000Z"))
    command = decide(subject=drifted, subject_digest=DigestV1(value=drifted.digest))
    assert service.decide(command).kind == "STALE"
    assert service.approval_count() == 0


def test_carried_subject_must_match_decision_subject(
    control_database: ControlDatabase,
    service: FinalWritebackDecisionServiceV1,
) -> None:
    """Contradictory evidence fails closed (SPEC §5.2): the decision binds
    subject S (the wait subject) but the command carries subject T whose
    expiry coincidentally equals the wait expiry — no approval for T may
    be created."""
    drifted = subject(candidate_digest=hashlib.sha256(b"other").hexdigest())
    command = decide(
        subject=drifted,
        # The decision still binds the wait's exact subject digest.
        subject_digest=DigestV1(value=_SUBJECT.digest),
    )
    result = service.decide(command)
    assert result.kind == "STALE"
    assert service.approval_count() == 0
    assert _wait_row(control_database, "wait-1") == ("PENDING", None)


def test_wrong_run_binding_rejected(
    control_database: ControlDatabase,
    service: FinalWritebackDecisionServiceV1,
) -> None:
    assert service.decide(decide(run_id="run-other")).kind == "BINDING_MISMATCH"
    assert service.approval_count() == 0


def test_wrong_wait_kind_rejected(
    control_database: ControlDatabase,
    service: FinalWritebackDecisionServiceV1,
) -> None:
    command = DecideFinalWritebackV1(
        decision=WaitDecisionV1(
            wait_id="wait-1",
            run_id="run-1",
            wait_kind="DISCLOSURE_GRANT",
            subject_digest=DigestV1(value=_SUBJECT.digest),
            decision="APPROVE",
            event_id="evt-kind",
            decided_at=_DECIDED_AT,
        ),
        subject=_SUBJECT,
        approval_id="approval-1",
    )
    assert service.decide(command).kind == "BINDING_MISMATCH"
    assert service.approval_count() == 0


def test_missing_wait_rejected(
    control_database: ControlDatabase,
    service: FinalWritebackDecisionServiceV1,
) -> None:
    assert service.decide(decide(wait_id="wait-missing")).kind == "NOT_FOUND"
    assert service.approval_count() == 0


def test_cancelled_run_rejected(
    control_database: ControlDatabase,
    service: FinalWritebackDecisionServiceV1,
) -> None:
    # The run already left WAITING_USER (cancelled by the loop).
    _insert_run(control_database, "run-cancelled", "STOPPED")
    _create_wait(
        database=control_database, wait_id="wait-cancelled", run_id="run-cancelled"
    )
    result = service.decide(
        decide(wait_id="wait-cancelled", run_id="run-cancelled", event_id="evt-cancel")
    )
    assert result.kind == "CANCELLED"
    assert service.approval_count() == 0
    assert _run_state(control_database, "run-cancelled") == ("STOPPED", None)


def test_approve_at_exact_expiry_commits(
    control_database: ControlDatabase,
    service: FinalWritebackDecisionServiceV1,
) -> None:
    # A decision at exactly expires_at is not late (strict > comparison).
    result = service.decide(decide(decided_at=_EXPIRES_AT, event_id="evt-exact"))
    assert result.kind == "APPROVED"
    assert service.approval_count() == 1


def test_already_expired_wait_rejected(
    control_database: ControlDatabase,
    service: FinalWritebackDecisionServiceV1,
) -> None:
    _insert_run(control_database, "run-expired", "WAITING_USER")
    _create_wait(
        database=control_database,
        wait_id="wait-expired",
        run_id="run-expired",
        expires_at=CanonicalTimestampV1("2026-08-05T09:00:30.000Z"),
    )
    result = service.decide(
        decide(
            wait_id="wait-expired",
            run_id="run-expired",
            event_id="evt-expired",
            decided_at=_LATE_DECIDED_AT,
        )
    )
    assert result.kind == "EXPIRED"
    assert service.approval_count() == 0
    assert _wait_row(control_database, "wait-expired") == ("EXPIRED", None)


def test_concurrent_decisions_yield_exactly_one_approval(
    tmp_path: Path,
    control_database: ControlDatabase,
    service: FinalWritebackDecisionServiceV1,
) -> None:
    # Each thread opens its own connection to the same on-disk file
    # (sqlite3 connections are thread-bound); BEGIN IMMEDIATE serializes
    # the writers so exactly one decision wins and one approval is created.
    database_path = tmp_path / "decision.db"
    outcomes: list[str] = []
    barrier = threading.Barrier(2, timeout=60)

    def _decide_once() -> None:
        database = open_control_database(database_path)
        try:
            worker_service = FinalWritebackDecisionServiceV1(database)
            barrier.wait()
            outcomes.append(worker_service.decide(decide(event_id="evt-race")).kind)
        finally:
            database.close()

    threads = [threading.Thread(target=_decide_once) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert sorted(outcomes) == ["APPROVED", "REPLAY"]
    assert service.approval_count() == 1


def test_writeback_decision_state_matrix(
    control_database: ControlDatabase,
    service: FinalWritebackDecisionServiceV1,
) -> None:
    """PLAN Registry row 14.B.

    Exact pending approval may approve or reject once; expired, stale,
    wrong-subject, cancelled, duplicate, or replay-conflict input creates
    no pending/new write authority.  A hard DENY never reaches the
    decision layer (the T13.1 policy blocks it before a wait exists), so
    no decision input can create an approval for a DENY'd writeback.
    """
    # Exact pending approve: once, one PENDING approval, run -> PERSISTENCE.
    approved = service.decide(decide())
    assert approved.kind == "APPROVED"
    assert service.approval_count() == 1
    assert _run_state(control_database, "run-1") == ("RUNNING", "PERSISTENCE")

    # Duplicate/replay of the exact decision: stable, no second approval.
    replayed = service.decide(decide())
    assert replayed.kind == "REPLAY"
    assert replayed.approval is not None
    assert service.approval_count() == 1

    # Replay-conflict (different decision on the same wait): no mutation.
    assert service.decide(decide(decision="REJECT", event_id="evt-other")).kind == (
        "CONFLICT"
    )
    assert service.approval_count() == 1
    assert _wait_row(control_database, "wait-1") == ("DECIDED", "APPROVE")

    # Expired: a decision past expires_at creates no approval and no resume.
    _insert_run(control_database, "run-expiry", "WAITING_USER")
    _create_wait(database=control_database, wait_id="wait-expiry", run_id="run-expiry")
    expired = service.decide(
        decide(
            wait_id="wait-expiry",
            run_id="run-expiry",
            event_id="evt-expired",
            decided_at=_LATE_DECIDED_AT,
        )
    )
    assert expired.kind == "EXPIRED"
    assert service.approval_count() == 1
    assert _run_state(control_database, "run-expiry") == ("WAITING_USER", None)

    # Stale: a different subject digest on a pending wait.
    _insert_run(control_database, "run-stale", "WAITING_USER")
    _create_wait(database=control_database, wait_id="wait-stale", run_id="run-stale")
    stale = service.decide(
        decide(
            wait_id="wait-stale",
            run_id="run-stale",
            subject_digest=DigestV1(value="f" * 64),
            event_id="evt-stale",
        )
    )
    assert stale.kind == "STALE"
    assert service.approval_count() == 1

    # Wrong-subject: the subject expiry must equal the wait expiry.
    _insert_run(control_database, "run-wrong-subject", "WAITING_USER")
    _create_wait(
        database=control_database,
        wait_id="wait-wrong-subject",
        run_id="run-wrong-subject",
    )
    drifted = subject(expires_at=CanonicalTimestampV1("2026-08-05T09:10:00.000Z"))
    wrong_subject = service.decide(
        decide(
            wait_id="wait-wrong-subject",
            run_id="run-wrong-subject",
            subject=drifted,
            subject_digest=DigestV1(value=drifted.digest),
            event_id="evt-wrong-subject",
        )
    )
    assert wrong_subject.kind == "STALE"
    assert service.approval_count() == 1

    # Wrong-binding: a mismatched run id on a pending wait.
    _insert_run(control_database, "run-wrong", "WAITING_USER")
    _create_wait(database=control_database, wait_id="wait-wrong", run_id="run-wrong")
    wrong = service.decide(
        decide(
            wait_id="wait-wrong",
            run_id="run-1",
            event_id="evt-wrong",
        )
    )
    assert wrong.kind == "BINDING_MISMATCH"
    assert service.approval_count() == 1

    # Cancelled: the run is no longer WAITING_USER.
    _insert_run(control_database, "run-cancel", "STOPPED")
    _create_wait(database=control_database, wait_id="wait-cancel", run_id="run-cancel")
    cancelled = service.decide(
        decide(wait_id="wait-cancel", run_id="run-cancel", event_id="evt-cancel")
    )
    assert cancelled.kind == "CANCELLED"
    assert service.approval_count() == 1

    # Missing wait.
    assert service.decide(decide(wait_id="wait-missing")).kind == "NOT_FOUND"
    assert service.approval_count() == 1

    # Exact reject once: no approval, decision recorded, no resume.
    _insert_run(control_database, "run-reject", "WAITING_USER")
    _create_wait(database=control_database, wait_id="wait-reject", run_id="run-reject")
    rejected = service.decide(
        decide(
            wait_id="wait-reject",
            run_id="run-reject",
            decision="REJECT",
            event_id="evt-reject",
        )
    )
    assert rejected.kind == "REJECTED"
    assert service.approval_count() == 1
    assert _wait_row(control_database, "wait-reject") == ("DECIDED", "REJECT")
    assert _run_state(control_database, "run-reject") == ("WAITING_USER", None)


def test_final_writeback_approval_value_model() -> None:
    """The closed approval value model: approval_id/subject/created_at/status
    only; the mutable status never enters the subject (AC-03)."""
    approval = FinalWritebackApprovalV1(
        schema_version=1,
        approval_id="approval-1",
        subject_digest=DigestV1(value=_SUBJECT.digest),
        run_id="run-1",
        wait_id="wait-1",
        created_at=_DECIDED_AT,
        status="PENDING",
    )
    assert approval.status == "PENDING"
    assert FinalWritebackApprovalV1.model_fields.keys() == {
        "schema_version",
        "approval_id",
        "subject_digest",
        "run_id",
        "wait_id",
        "created_at",
        "status",
    }
    # Identities must never be empty (they cannot bind).
    for empty in ("approval_id", "run_id", "wait_id"):
        with pytest.raises(ValidationError):
            FinalWritebackApprovalV1(
                schema_version=1,
                approval_id="" if empty == "approval_id" else "approval-1",
                subject_digest=DigestV1(value=_SUBJECT.digest),
                run_id="" if empty == "run_id" else "run-1",
                wait_id="" if empty == "wait_id" else "wait-1",
                created_at=_DECIDED_AT,
                status="PENDING",
            )
