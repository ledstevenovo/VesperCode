"""T15.2 legacy step 15.D: atomic disclosure Grant decision lifecycle tests.

Pins the exact RED (an expired disclosure wait creates no Grant), the
one-winner approve/reject semantics over the T07.2 wait lock, the
expiry/stale/wrong-binding/cancelled/duplicate/replay-conflict rejections
with zero Grant creation and zero resume, the subject-row persistence, and
the WAITING_USER → RUNNING(AGENT_LOOP) return transition on approval.
Final registry edits, Task 15.F revocation, request-body validation,
prepared-request authorization, and byte charging remain out of scope
(GREEN-4).
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

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import DigestV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.contracts.run import WaitContextV1, WaitDecisionV1
from vespercode.governance.disclosure_decision import (
    DecideDisclosureGrantV1,
    DisclosureDecisionServiceV1,
)
from vespercode.governance.disclosure_scope import (
    DirectoryDisclosureScopeV1,
    DisclosureScopeSequenceV1,
)
from vespercode.governance.disclosure_subject import (
    DisclosureGrantSubjectV1,
    DisclosureSubjectRequestV1,
    build_disclosure_subject,
)
from vespercode.governance.request_sources import (
    RequestSourceV1,
    SourceProjectionV1,
)
from vespercode.profiles.endpoints import OpenAIEndpointV1
from vespercode.profiles.llm import OpenAILLMProfileV1, load_llm_profile
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
from vespercode.storage.run_repository import RunRepository

_CREATED_AT = CanonicalTimestampV1("2026-08-05T09:00:00.000Z")
_EXPIRES_AT = CanonicalTimestampV1("2026-08-05T09:05:00.000Z")
_DECIDED_AT = CanonicalTimestampV1("2026-08-05T09:01:00.000Z")
_LATE_DECIDED_AT = CanonicalTimestampV1("2026-08-05T09:06:00.000Z")
_RUN_DEADLINE = CanonicalTimestampV1("2026-08-05T09:15:00.000Z")
_OPENAI_BUILTIN = (
    Path(__file__).resolve().parents[3]
    / "src/vespercode/profiles/builtin/openai-single-turn-v1.json"
)


def profile() -> OpenAILLMProfileV1:
    loaded = load_llm_profile(_OPENAI_BUILTIN.read_bytes())
    assert isinstance(loaded, OpenAILLMProfileV1)
    return loaded


def endpoint() -> OpenAIEndpointV1:
    return OpenAIEndpointV1(
        endpoint_id="OPENAI_PUBLIC_API_V1",
        scheme="https",
        host="api.openai.com",
        effective_port=443,
        base_path="/v1",
    )


def subject(
    run_id: str = "run-1",
    expires_at: CanonicalTimestampV1 = _EXPIRES_AT,
    budget: int = 1000,
) -> DisclosureGrantSubjectV1:
    raw = b"tool result bytes"
    sources: SourceProjectionV1 = (
        RequestSourceV1(
            message_index=0,
            segment_index=0,
            source_category="TOOL_RESULT",
            source_path=PresentV1(
                kind="PRESENT", value=CanonicalRelativePathV1("src/a.py")
            ),
            content_digest=hashlib.sha256(raw).hexdigest(),
            byte_count=len(raw),
        ),
    )
    scopes: DisclosureScopeSequenceV1 = (
        DirectoryDisclosureScopeV1(
            kind="DIRECTORY", path=CanonicalRelativePathV1("src")
        ),
    )
    return build_disclosure_subject(
        DisclosureSubjectRequestV1(
            run_id=run_id,
            expires_at=expires_at,
            cumulative_byte_budget=budget,
            url=AbsentV1(kind="ABSENT"),
        ),
        sources,
        scopes,
        profile(),
        endpoint(),
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
            wait_kind="DISCLOSURE_GRANT",
            source_phase="AGENT_LOOP",
            subject_digest=subject_digest,
            created_at=_CREATED_AT,
            expires_at=expires_at,
        )
    )


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "decision.db")
    apply_migrations(
        database,
        (
            RUN_WAIT_V1_MIGRATION,
            IDEMPOTENCY_V1_MIGRATION,
            DISCLOSURE_GRANTS_V1_MIGRATION,
        ),
    )
    _insert_run(database, "run-1", "WAITING_USER")
    _create_wait(database, "wait-1", "run-1")
    yield database
    database.close()


@pytest.fixture
def service(control_database: ControlDatabase) -> DisclosureDecisionServiceV1:
    return DisclosureDecisionServiceV1(control_database)


def decide(
    *,
    wait_id: str = "wait-1",
    run_id: str = "run-1",
    subject_digest: DigestV1 = DigestV1(value=_SUBJECT.digest),
    decision: str = "APPROVE",
    event_id: str = "evt-1",
    decided_at: CanonicalTimestampV1 = _DECIDED_AT,
    subject: DisclosureGrantSubjectV1 = _SUBJECT,
    grant_id: str = "grant-1",
) -> DecideDisclosureGrantV1:
    return DecideDisclosureGrantV1(
        decision=WaitDecisionV1(
            wait_id=wait_id,
            run_id=run_id,
            wait_kind="DISCLOSURE_GRANT",
            subject_digest=subject_digest,
            decision=decision,  # type: ignore[arg-type]
            event_id=event_id,
            decided_at=decided_at,
        ),
        subject=subject,
        grant_id=grant_id,
    )


def approve_expired_disclosure() -> DecideDisclosureGrantV1:
    return decide(decided_at=_LATE_DECIDED_AT)


def test_expired_disclosure_wait_creates_no_grant(
    service: DisclosureDecisionServiceV1,
) -> None:
    assert service.decide(approve_expired_disclosure()).kind == "EXPIRED"
    assert service.grant_count() == 0


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


def _grant_row(
    control_database: ControlDatabase, grant_id: str
) -> tuple[str, str, int, str]:
    rows = control_database.read_rows(
        "SELECT grant_id, subject_digest, consumed_bytes, status"
        " FROM disclosure_grants WHERE grant_id = ?",
        (grant_id,),
    )
    assert len(rows) == 1
    return str(rows[0][0]), str(rows[0][1]), int(rows[0][2]), str(rows[0][3])


def test_approve_creates_exactly_one_active_grant(
    control_database: ControlDatabase,
    service: DisclosureDecisionServiceV1,
) -> None:
    result = service.decide(decide())
    assert result.kind == "APPROVED"
    assert result.grant is not None
    assert service.grant_count() == 1
    assert _grant_row(control_database, "grant-1") == (
        "grant-1",
        _SUBJECT.digest,
        0,
        "ACTIVE",
    )
    # The wait decision is recorded and the run returns to the loop.
    assert _wait_row(control_database, "wait-1") == ("DECIDED", "APPROVE")
    assert _run_state(control_database, "run-1") == ("RUNNING", "AGENT_LOOP")
    # The immutable subject facts are persisted (no segment content).
    rows = control_database.read_rows(
        "SELECT provider, endpoint_id, model, request_serializer_version,"
        " redaction_profile_id, cumulative_byte_budget, expires_at"
        " FROM disclosure_grant_subjects WHERE subject_digest = ?",
        (_SUBJECT.digest,),
    )
    assert len(rows) == 1
    assert rows[0][0] == "openai"
    assert rows[0][1] == "OPENAI_PUBLIC_API_V1"
    assert rows[0][2] == "gpt-4.1-mini"
    assert rows[0][3] == "1"
    assert rows[0][4] == "NO_CONTENT_REDACTION_V1"
    assert rows[0][5] == 1000
    assert rows[0][6] == _EXPIRES_AT.value


def test_approve_with_swapped_subject_creates_no_grant(
    control_database: ControlDatabase,
    service: DisclosureDecisionServiceV1,
) -> None:
    # The decision approves subject A (digest matches the wait), but the
    # command carries a different subject B: the Grant must not bind B.
    other = subject(budget=2000)
    assert other.digest != _SUBJECT.digest
    result = service.decide(decide(subject=other))
    assert result.kind == "BINDING_MISMATCH"
    assert result.grant is None
    assert service.grant_count() == 0
    assert _grant_row_count(control_database) == 0
    assert _subject_row_count(control_database) == 0
    # The mismatch check runs before the wait lock: the wait stays PENDING
    # and the exact approved subject can still decide the same wait.
    assert _wait_row(control_database, "wait-1") == ("PENDING", None)
    assert service.decide(decide()).kind == "APPROVED"
    assert service.grant_count() == 1


def _grant_row_count(control_database: ControlDatabase) -> int:
    return len(control_database.read_rows("SELECT 1 FROM disclosure_grants"))


def _subject_row_count(control_database: ControlDatabase) -> int:
    return len(control_database.read_rows("SELECT 1 FROM disclosure_grant_subjects"))


def test_reject_records_decision_without_grant(
    control_database: ControlDatabase,
    service: DisclosureDecisionServiceV1,
) -> None:
    result = service.decide(decide(decision="REJECT"))
    assert result.kind == "REJECTED"
    assert result.grant is None
    assert service.grant_count() == 0
    assert _wait_row(control_database, "wait-1") == ("DECIDED", "REJECT")
    # No resume: the run stays WAITING_USER for the loop to terminate.
    assert _run_state(control_database, "run-1") == ("WAITING_USER", None)


def test_approve_replay_is_stable_without_second_grant(
    control_database: ControlDatabase,
    service: DisclosureDecisionServiceV1,
) -> None:
    first = service.decide(decide())
    second = service.decide(decide())
    assert first.kind == "APPROVED"
    assert second.kind == "REPLAY"
    assert service.grant_count() == 1
    assert _grant_row(control_database, "grant-1")[3] == "ACTIVE"
    assert _run_state(control_database, "run-1") == ("RUNNING", "AGENT_LOOP")


def test_reject_replay_is_stable(
    control_database: ControlDatabase,
    service: DisclosureDecisionServiceV1,
) -> None:
    first = service.decide(decide(decision="REJECT"))
    second = service.decide(decide(decision="REJECT"))
    assert first.kind == "REJECTED"
    assert second.kind == "REPLAY"
    assert service.grant_count() == 0


def test_conflicting_decision_on_decided_wait_rejected(
    control_database: ControlDatabase,
    service: DisclosureDecisionServiceV1,
) -> None:
    assert service.decide(decide()).kind == "APPROVED"
    conflict = service.decide(decide(decision="REJECT", event_id="evt-other"))
    assert conflict.kind == "CONFLICT"
    assert service.grant_count() == 1
    assert _wait_row(control_database, "wait-1") == ("DECIDED", "APPROVE")


def test_stale_subject_digest_rejected(
    control_database: ControlDatabase,
    service: DisclosureDecisionServiceV1,
) -> None:
    stale = decide(subject_digest=DigestV1(value="f" * 64))
    assert service.decide(stale).kind == "STALE"
    assert service.grant_count() == 0
    assert _wait_row(control_database, "wait-1") == ("PENDING", None)


def test_subject_expiry_must_equal_wait_expiry(
    control_database: ControlDatabase,
    service: DisclosureDecisionServiceV1,
) -> None:
    drifted = subject(expires_at=CanonicalTimestampV1("2026-08-05T09:10:00.000Z"))
    command = decide(subject=drifted, subject_digest=DigestV1(value=drifted.digest))
    assert service.decide(command).kind == "STALE"
    assert service.grant_count() == 0


def test_wrong_run_binding_rejected(
    control_database: ControlDatabase,
    service: DisclosureDecisionServiceV1,
) -> None:
    assert service.decide(decide(run_id="run-other")).kind == "BINDING_MISMATCH"
    assert service.grant_count() == 0


def test_wrong_wait_kind_rejected(
    control_database: ControlDatabase,
    service: DisclosureDecisionServiceV1,
) -> None:
    command = DecideDisclosureGrantV1(
        decision=WaitDecisionV1(
            wait_id="wait-1",
            run_id="run-1",
            wait_kind="FINAL_WRITEBACK",
            subject_digest=DigestV1(value=_SUBJECT.digest),
            decision="APPROVE",
            event_id="evt-kind",
            decided_at=_DECIDED_AT,
        ),
        subject=_SUBJECT,
        grant_id="grant-1",
    )
    assert service.decide(command).kind == "BINDING_MISMATCH"
    assert service.grant_count() == 0


def test_final_writeback_wait_kind_rejected(
    control_database: ControlDatabase,
    service: DisclosureDecisionServiceV1,
) -> None:
    """The disclosure service binds only DISCLOSURE_GRANT waits."""
    _insert_run(control_database, "run-wb", "WAITING_USER")
    _create_wait(
        database=control_database,
        wait_id="wait-wb",
        run_id="run-wb",
    )
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE wait_contexts SET wait_kind = 'FINAL_WRITEBACK',"
            " source_phase = 'FORMAL_VALIDATION' WHERE wait_id = 'wait-wb'"
        )
    command = DecideDisclosureGrantV1(
        decision=WaitDecisionV1(
            wait_id="wait-wb",
            run_id="run-wb",
            wait_kind="FINAL_WRITEBACK",
            subject_digest=DigestV1(value=_SUBJECT.digest),
            decision="APPROVE",
            event_id="evt-wb",
            decided_at=_DECIDED_AT,
        ),
        subject=_SUBJECT,
        grant_id="grant-wb",
    )
    assert service.decide(command).kind == "BINDING_MISMATCH"
    assert service.grant_count() == 0
    assert _wait_row(control_database, "wait-wb") == ("PENDING", None)


def test_missing_wait_rejected(
    control_database: ControlDatabase,
    service: DisclosureDecisionServiceV1,
) -> None:
    assert service.decide(decide(wait_id="wait-missing")).kind == "NOT_FOUND"
    assert service.grant_count() == 0


def test_cancelled_run_rejected(
    control_database: ControlDatabase,
    service: DisclosureDecisionServiceV1,
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
    assert service.grant_count() == 0
    assert _run_state(control_database, "run-cancelled") == ("STOPPED", None)


def test_approve_at_exact_expiry_commits(
    control_database: ControlDatabase,
    service: DisclosureDecisionServiceV1,
) -> None:
    # A decision at exactly expires_at is not late (strict > comparison).
    result = service.decide(decide(decided_at=_EXPIRES_AT, event_id="evt-exact"))
    assert result.kind == "APPROVED"
    assert service.grant_count() == 1


def test_already_expired_wait_rejected(
    control_database: ControlDatabase,
    service: DisclosureDecisionServiceV1,
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
    assert service.grant_count() == 0
    assert _wait_row(control_database, "wait-expired") == ("EXPIRED", None)


def test_concurrent_decisions_yield_exactly_one_grant(
    tmp_path: Path,
    control_database: ControlDatabase,
    service: DisclosureDecisionServiceV1,
) -> None:
    # Each thread opens its own connection to the same on-disk file
    # (sqlite3 connections are thread-bound); BEGIN IMMEDIATE serializes
    # the writers so exactly one decision wins and one Grant is created.
    database_path = tmp_path / "decision.db"
    outcomes: list[str] = []
    barrier = threading.Barrier(2, timeout=60)

    def _decide_once() -> None:
        database = open_control_database(database_path)
        try:
            worker_service = DisclosureDecisionServiceV1(database)
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
    assert service.grant_count() == 1


def test_disclosure_decision_state_matrix(
    control_database: ControlDatabase,
    service: DisclosureDecisionServiceV1,
) -> None:
    """PLAN Registry row 15.D.

    Exact pending wait approves or rejects once; expired, stale,
    wrong-binding, cancelled, duplicate, or replay-conflict input creates
    no Grant and no resume.
    """
    # Exact pending approve: once, one Grant, return to the loop.
    approved = service.decide(decide())
    assert approved.kind == "APPROVED"
    assert service.grant_count() == 1
    assert _run_state(control_database, "run-1") == ("RUNNING", "AGENT_LOOP")

    # Duplicate/replay of the exact decision: stable, no second Grant.
    assert service.decide(decide()).kind == "REPLAY"
    assert service.grant_count() == 1

    # Replay-conflict (different decision on the same wait): no mutation.
    assert service.decide(decide(decision="REJECT", event_id="evt-other")).kind == (
        "CONFLICT"
    )
    assert service.grant_count() == 1
    assert _wait_row(control_database, "wait-1") == ("DECIDED", "APPROVE")

    # Expired: a decision past expires_at creates no Grant and no resume.
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
    assert service.grant_count() == 1
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
    assert service.grant_count() == 1

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
    assert service.grant_count() == 1

    # Cancelled: the run is no longer WAITING_USER.
    _insert_run(control_database, "run-cancel", "STOPPED")
    _create_wait(database=control_database, wait_id="wait-cancel", run_id="run-cancel")
    cancelled = service.decide(
        decide(wait_id="wait-cancel", run_id="run-cancel", event_id="evt-cancel")
    )
    assert cancelled.kind == "CANCELLED"
    assert service.grant_count() == 1

    # Missing wait.
    assert service.decide(decide(wait_id="wait-missing")).kind == "NOT_FOUND"
    assert service.grant_count() == 1

    # Exact reject once: no Grant, decision recorded.
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
    assert service.grant_count() == 1
    assert _wait_row(control_database, "wait-reject") == ("DECIDED", "REJECT")
    assert _run_state(control_database, "run-reject") == ("WAITING_USER", None)
