"""T07.2 legacy step 7.B: transactional Run/wait lifecycle repository tests.

The exact RED test pins the one-winner wait decision contract; the matrix
pins every SPEC legal transition, the stale/wrong-kind/cancelled/
expired-commit/duplicate/terminal-reopen failures, and the one-APPLIED
concurrency row against the PLAN Registry row for 7.B.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

# The repository consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips cleanly
# there (formal env runs it fully).
pytest.importorskip("pydantic")

from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import DigestV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.contracts.run import (
    RunPhase,
    RunStateV1,
    RunStatus,
    WaitContextV1,
    WaitDecisionV1,
)
from vespercode.runs.lifecycle import (
    LifecycleEventV1,
    LifecycleRules,
)
from vespercode.storage.connection import (
    ControlDatabase,
    open_control_database,
)
from vespercode.storage.migration_engine import apply_migrations
from vespercode.storage.migrations.v0001_run_wait import RUN_WAIT_V1_MIGRATION
from vespercode.storage.run_repository import (
    RunAlreadyExistsErrorV1,
    RunRecordV1,
    RunRepository,
    TransitionCommandV1,
    WaitAlreadyExistsErrorV1,
    WaitDecisionLockResultV1,
    WaitDecisionResultV1,
)

_CREATED_AT = CanonicalTimestampV1("2026-08-05T09:00:00.000Z")
_EXPIRES_AT = CanonicalTimestampV1("2026-08-05T09:05:00.000Z")
_DECIDED_AT = CanonicalTimestampV1("2026-08-05T09:01:00.000Z")
_RUN_DEADLINE = CanonicalTimestampV1("2026-08-05T09:15:00.000Z")
_LATE_DECIDED_AT = CanonicalTimestampV1("2026-08-05T09:06:00.000Z")
_SUBJECT_DIGEST = DigestV1(value="a" * 64)

CREATED = RunStateV1(status="CREATED", phase=AbsentV1(kind="ABSENT"))
RUNNING_PREFLIGHT = RunStateV1(
    status="RUNNING", phase=PresentV1(kind="PRESENT", value="PREFLIGHT")
)
RUNNING_BASELINE = RunStateV1(
    status="RUNNING", phase=PresentV1(kind="PRESENT", value="BASELINE")
)
RUNNING_AGENT_LOOP = RunStateV1(
    status="RUNNING", phase=PresentV1(kind="PRESENT", value="AGENT_LOOP")
)
RUNNING_FORMAL_VALIDATION = RunStateV1(
    status="RUNNING", phase=PresentV1(kind="PRESENT", value="FORMAL_VALIDATION")
)
RUNNING_PERSISTENCE = RunStateV1(
    status="RUNNING", phase=PresentV1(kind="PRESENT", value="PERSISTENCE")
)
WAITING_USER = RunStateV1(status="WAITING_USER", phase=AbsentV1(kind="ABSENT"))
RECOVERY_REQUIRED = RunStateV1(
    status="RECOVERY_REQUIRED", phase=AbsentV1(kind="ABSENT")
)
SUCCEEDED = RunStateV1(status="SUCCEEDED", phase=AbsentV1(kind="ABSENT"))
STOPPED = RunStateV1(status="STOPPED", phase=AbsentV1(kind="ABSENT"))

# Every SPEC 4.2.7 legal transition: (expected, event, target).
LEGAL_CASES: tuple[tuple[RunStateV1, LifecycleEventV1, RunStateV1], ...] = (
    (CREATED, LifecycleEventV1(kind="START"), RUNNING_PREFLIGHT),
    (CREATED, LifecycleEventV1(kind="STOP"), STOPPED),
    (
        RUNNING_PREFLIGHT,
        LifecycleEventV1(kind="PHASE", phase="BASELINE"),
        RUNNING_BASELINE,
    ),
    (RUNNING_PREFLIGHT, LifecycleEventV1(kind="STOP"), STOPPED),
    (
        RUNNING_BASELINE,
        LifecycleEventV1(kind="PHASE", phase="AGENT_LOOP"),
        RUNNING_AGENT_LOOP,
    ),
    (RUNNING_BASELINE, LifecycleEventV1(kind="STOP"), STOPPED),
    (
        RUNNING_AGENT_LOOP,
        LifecycleEventV1(kind="PHASE", phase="AGENT_LOOP"),
        RUNNING_AGENT_LOOP,
    ),
    (
        RUNNING_AGENT_LOOP,
        LifecycleEventV1(kind="WAIT", wait_kind="DISCLOSURE_GRANT"),
        WAITING_USER,
    ),
    (
        RUNNING_AGENT_LOOP,
        LifecycleEventV1(kind="PHASE", phase="FORMAL_VALIDATION"),
        RUNNING_FORMAL_VALIDATION,
    ),
    (RUNNING_AGENT_LOOP, LifecycleEventV1(kind="STOP"), STOPPED),
    (
        RUNNING_FORMAL_VALIDATION,
        LifecycleEventV1(kind="PHASE", phase="AGENT_LOOP"),
        RUNNING_AGENT_LOOP,
    ),
    (
        RUNNING_FORMAL_VALIDATION,
        LifecycleEventV1(kind="WAIT", wait_kind="FINAL_WRITEBACK"),
        WAITING_USER,
    ),
    (RUNNING_FORMAL_VALIDATION, LifecycleEventV1(kind="STOP"), STOPPED),
    (
        WAITING_USER,
        LifecycleEventV1(kind="WAIT_APPROVED", wait_kind="DISCLOSURE_GRANT"),
        RUNNING_AGENT_LOOP,
    ),
    (
        WAITING_USER,
        LifecycleEventV1(kind="WAIT_APPROVED", wait_kind="FINAL_WRITEBACK"),
        RUNNING_PERSISTENCE,
    ),
    (
        WAITING_USER,
        LifecycleEventV1(kind="WAIT_TERMINATED", wait_kind="DISCLOSURE_GRANT"),
        STOPPED,
    ),
    (WAITING_USER, LifecycleEventV1(kind="STOP"), STOPPED),
    (RUNNING_PERSISTENCE, LifecycleEventV1(kind="SUCCEED"), SUCCEEDED),
    (RUNNING_PERSISTENCE, LifecycleEventV1(kind="STOP"), STOPPED),
    (
        RUNNING_PERSISTENCE,
        LifecycleEventV1(kind="PERSISTENCE_FAILED"),
        RECOVERY_REQUIRED,
    ),
    (
        RECOVERY_REQUIRED,
        LifecycleEventV1(kind="RECOVER", recover_outcome="SUCCEEDED"),
        SUCCEEDED,
    ),
    (
        RECOVERY_REQUIRED,
        LifecycleEventV1(kind="RECOVER", recover_outcome="STOPPED"),
        STOPPED,
    ),
    (
        RECOVERY_REQUIRED,
        LifecycleEventV1(kind="RECOVER", recover_outcome="KEEP"),
        RECOVERY_REQUIRED,
    ),
)


def _insert_snapshot(
    database: ControlDatabase,
    config_snapshot_id: str,
) -> None:
    """Insert one v0001 run_config_snapshots row (runs.config FK requires it).

    The canonical digest is derived from the id so every snapshot is unique
    (the digest column is UNIQUE) and deterministic.
    """
    digest = hashlib.sha256(config_snapshot_id.encode("utf-8")).hexdigest()
    with database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots"
            " (config_snapshot_id, digest, llm_profile_id, reference_profile_id,"
            " policy_id, target_test_ids, limits_digest, frozen_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                config_snapshot_id,
                digest,
                "mock-deterministic-v1",
                "python-src-py312-v1",
                "PYTHON_SRC_ONLY_V1",
                "[]",
                "c" * 64,
                _CREATED_AT.value,
            ),
        )


def _insert_run(
    database: ControlDatabase,
    run_id: str,
    state: RunStateV1,
) -> None:
    """Insert one v0001 runs row directly at the given state (matrix setup)."""
    phase = state.phase.value if state.phase.kind == "PRESENT" else None
    with database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots"
            " (config_snapshot_id, digest, llm_profile_id, reference_profile_id,"
            " policy_id, target_test_ids, limits_digest, frozen_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"snap-{run_id}",
                hashlib.sha256(f"snap-{run_id}".encode("utf-8")).hexdigest(),
                "mock-deterministic-v1",
                "python-src-py312-v1",
                "PYTHON_SRC_ONLY_V1",
                "[]",
                "c" * 64,
                _CREATED_AT.value,
            ),
        )
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
            (
                run_id,
                "workspace-1",
                f"snap-{run_id}",
                state.status,
                phase,
                _CREATED_AT.value,
                _RUN_DEADLINE.value,
            ),
        )


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "run_wait.db")
    apply_migrations(database, (RUN_WAIT_V1_MIGRATION,))
    yield database
    database.close()


@pytest.fixture
def run_repository(control_database: ControlDatabase) -> RunRepository:
    return RunRepository(control_database)


@pytest.fixture
def run_record() -> RunRecordV1:
    return RunRecordV1(
        run_id="run-1",
        workspace_identity="workspace-1",
        status="CREATED",
        phase=AbsentV1(kind="ABSENT"),
        config_snapshot_id="snap-run-1",
        started_at=_CREATED_AT,
        run_deadline=_RUN_DEADLINE,
    )


@pytest.fixture
def decision(
    control_database: ControlDatabase,
    run_repository: RunRepository,
    run_record: RunRecordV1,
) -> WaitDecisionV1:
    """One run row, one pending wait row, and a decision exactly bound to it."""
    _insert_snapshot(control_database, run_record.config_snapshot_id)
    run_repository.insert_created(run_record)
    run_repository.create_wait(
        WaitContextV1(
            wait_id="wait-1",
            run_id=run_record.run_id,
            wait_kind="DISCLOSURE_GRANT",
            source_phase="AGENT_LOOP",
            subject_digest=_SUBJECT_DIGEST,
            created_at=_CREATED_AT,
            expires_at=_EXPIRES_AT,
        )
    )
    return WaitDecisionV1(
        wait_id="wait-1",
        run_id=run_record.run_id,
        wait_kind="DISCLOSURE_GRANT",
        subject_digest=_SUBJECT_DIGEST,
        decision="APPROVE",
        event_id="evt-1",
        decided_at=_DECIDED_AT,
    )


def decide_wait_once(
    repository: RunRepository,
    decision: WaitDecisionV1,
) -> WaitDecisionResultV1:
    """Lock and commit one decision inside one immediate transaction."""
    with repository.database.immediate_transaction() as tx:
        lock_result = repository.lock_wait_for_decision(tx, decision)
        assert lock_result.kind == "LOCKED"
        assert lock_result.lock is not None
        return repository.commit_wait_decision(tx, lock_result.lock, decision)


def lock_wait_once(
    repository: RunRepository,
    decision: WaitDecisionV1,
) -> WaitDecisionLockResultV1:
    """Lock one decision inside one immediate transaction."""
    with repository.database.immediate_transaction() as tx:
        return repository.lock_wait_for_decision(tx, decision)


def test_same_wait_decision_can_win_only_once(
    run_repository: RunRepository, decision: WaitDecisionV1
) -> None:
    first = decide_wait_once(run_repository, decision)
    second = lock_wait_once(run_repository, decision)
    assert first.kind == "APPLIED"
    assert second.kind == "ALREADY_DECIDED"


def _wait_row_status(database: ControlDatabase, wait_id: str) -> str:
    rows = database.read_rows(
        "SELECT status FROM wait_contexts WHERE wait_id = ?",
        (wait_id,),
    )
    assert len(rows) == 1
    return str(rows[0][0])


def _run_row_state(database: ControlDatabase, run_id: str) -> RunStateV1:
    rows = database.read_rows(
        "SELECT status, phase FROM runs WHERE run_id = ?",
        (run_id,),
    )
    assert len(rows) == 1
    status = cast(RunStatus, str(rows[0][0]))
    phase = rows[0][1]
    if phase is None:
        return RunStateV1(status=status, phase=AbsentV1(kind="ABSENT"))
    return RunStateV1(
        status=status,
        phase=PresentV1(kind="PRESENT", value=cast(RunPhase, str(phase))),
    )


def test_run_wait_lifecycle_matrix(
    tmp_path: Path,
    control_database: ControlDatabase,
    run_repository: RunRepository,
    run_record: RunRecordV1,
    decision: WaitDecisionV1,
) -> None:
    """PLAN Registry row 7.B.

    Every SPEC legal transition succeeds once; stale, wrong-kind,
    cancelled, expired-commit, duplicate, and terminal-reopen transitions
    fail without mutation; concurrent decisions yield exactly one APPLIED.
    """
    _insert_snapshot(control_database, "snap-matrix")

    # --- Every SPEC 4.2.7 legal transition succeeds once. ---
    for index, (expected, event, target) in enumerate(LEGAL_CASES):
        run_id = f"run-legal-{index}"
        assert LifecycleRules.evaluate(expected, event) == target
        _insert_run(control_database, run_id, expected)
        first = run_repository.compare_and_transition(
            TransitionCommandV1(run_id=run_id, expected=expected, target=target)
        )
        assert first.kind == "APPLIED"
        assert _run_row_state(control_database, run_id) == target
        # The same transition cannot win twice: a repeated command with the
        # same expected state is either stale (state moved on) or, for the
        # SPEC "continue" self-transition, an allowed repeat.
        second = run_repository.compare_and_transition(
            TransitionCommandV1(run_id=run_id, expected=expected, target=target)
        )
        if expected == target:
            assert second.kind == "APPLIED"
        else:
            assert second.kind == "STALE"
            assert _run_row_state(control_database, run_id) == target

    # --- Stale transition: expected state does not match, no mutation. ---
    # (run-1 exists in CREATED state from the decision fixture.)
    stale = run_repository.compare_and_transition(
        TransitionCommandV1(
            run_id=run_record.run_id,
            expected=RUNNING_PREFLIGHT,
            target=RUNNING_BASELINE,
        )
    )
    assert stale.kind == "STALE"
    assert _run_row_state(control_database, run_record.run_id) == CREATED

    # --- Wrong-kind wait decision: lock fails closed without mutation. ---
    # A fresh run carries the wait (one active wait per run).
    _insert_run(control_database, "run-wrong-kind", CREATED)
    run_repository.create_wait(
        WaitContextV1(
            wait_id="wait-wrong-kind",
            run_id="run-wrong-kind",
            wait_kind="FINAL_WRITEBACK",
            source_phase="FORMAL_VALIDATION",
            subject_digest=_SUBJECT_DIGEST,
            created_at=_CREATED_AT,
            expires_at=_EXPIRES_AT,
        )
    )
    wrong_kind = WaitDecisionV1(
        wait_id="wait-wrong-kind",
        run_id=run_record.run_id,
        wait_kind="DISCLOSURE_GRANT",
        subject_digest=_SUBJECT_DIGEST,
        decision="APPROVE",
        event_id="evt-wrong-kind",
        decided_at=_DECIDED_AT,
    )
    with control_database.immediate_transaction() as tx:
        wrong_kind_lock = run_repository.lock_wait_for_decision(tx, wrong_kind)
    assert wrong_kind_lock.kind == "BINDING_MISMATCH"
    assert _wait_row_status(control_database, "wait-wrong-kind") == "PENDING"

    # --- Cancelled: WAIT_TERMINATED from WAITING_USER stops the run. ---
    cancelled_run_id = "run-cancelled"
    _insert_run(control_database, cancelled_run_id, WAITING_USER)
    cancelled = run_repository.compare_and_transition(
        TransitionCommandV1(
            run_id=cancelled_run_id,
            expected=WAITING_USER,
            target=STOPPED,
        )
    )
    assert cancelled.kind == "APPLIED"
    assert _run_row_state(control_database, cancelled_run_id) == STOPPED

    # --- Expired-commit: a decision after expires_at fails without mutation. ---
    _insert_run(control_database, "run-expiry", CREATED)
    run_repository.create_wait(
        WaitContextV1(
            wait_id="wait-expiry",
            run_id="run-expiry",
            wait_kind="DISCLOSURE_GRANT",
            source_phase="AGENT_LOOP",
            subject_digest=_SUBJECT_DIGEST,
            created_at=_CREATED_AT,
            expires_at=_EXPIRES_AT,
        )
    )
    early_decision = WaitDecisionV1(
        wait_id="wait-expiry",
        run_id="run-expiry",
        wait_kind="DISCLOSURE_GRANT",
        subject_digest=_SUBJECT_DIGEST,
        decision="APPROVE",
        event_id="evt-early",
        decided_at=_DECIDED_AT,
    )
    late_decision = WaitDecisionV1(
        wait_id="wait-expiry",
        run_id="run-expiry",
        wait_kind="DISCLOSURE_GRANT",
        subject_digest=_SUBJECT_DIGEST,
        decision="APPROVE",
        event_id="evt-late",
        decided_at=_LATE_DECIDED_AT,
    )
    with control_database.immediate_transaction() as tx:
        expiry_lock = run_repository.lock_wait_for_decision(tx, early_decision)
        assert expiry_lock.kind == "LOCKED"
        assert expiry_lock.lock is not None
        expired = run_repository.commit_wait_decision(
            tx, expiry_lock.lock, late_decision
        )
    assert expired.kind == "EXPIRED"
    assert _wait_row_status(control_database, "wait-expiry") == "DECIDING"
    assert _run_row_state(control_database, "run-expiry") == CREATED

    # --- Duplicate: a second decision on the same wait cannot win. ---
    _insert_run(control_database, "run-duplicate", CREATED)
    run_repository.create_wait(
        WaitContextV1(
            wait_id="wait-duplicate",
            run_id="run-duplicate",
            wait_kind="DISCLOSURE_GRANT",
            source_phase="AGENT_LOOP",
            subject_digest=_SUBJECT_DIGEST,
            created_at=_CREATED_AT,
            expires_at=_EXPIRES_AT,
        )
    )
    duplicate_decision = WaitDecisionV1(
        wait_id="wait-duplicate",
        run_id="run-duplicate",
        wait_kind="DISCLOSURE_GRANT",
        subject_digest=_SUBJECT_DIGEST,
        decision="APPROVE",
        event_id="evt-duplicate",
        decided_at=_DECIDED_AT,
    )
    assert decide_wait_once(run_repository, duplicate_decision).kind == "APPLIED"
    assert lock_wait_once(run_repository, duplicate_decision).kind == "ALREADY_DECIDED"

    # --- Terminal-reopen: a terminal run rejects every further transition. ---
    _insert_run(control_database, "run-succeeded", SUCCEEDED)
    reopen = run_repository.compare_and_transition(
        TransitionCommandV1(
            run_id="run-succeeded",
            expected=SUCCEEDED,
            target=RUNNING_AGENT_LOOP,
        )
    )
    assert reopen.kind == "INVALID"
    assert _run_row_state(control_database, "run-succeeded") == SUCCEEDED
    _insert_run(control_database, "run-stopped", STOPPED)
    reopen_stopped = run_repository.compare_and_transition(
        TransitionCommandV1(
            run_id="run-stopped",
            expected=STOPPED,
            target=CREATED,
        )
    )
    assert reopen_stopped.kind == "INVALID"
    assert _run_row_state(control_database, "run-stopped") == STOPPED

    # --- Concurrent decisions yield exactly one APPLIED. ---
    # Each thread opens its own connection to the same on-disk file
    # (sqlite3 connections are thread-bound); BEGIN IMMEDIATE serializes
    # the writers so exactly one decision wins.
    database_path = tmp_path / "run_wait.db"
    outcomes: list[str] = []
    barrier = threading.Barrier(2)

    def _decide() -> None:
        candidate = WaitDecisionV1(
            wait_id=decision.wait_id,
            run_id=decision.run_id,
            wait_kind=decision.wait_kind,
            subject_digest=_SUBJECT_DIGEST,
            decision="APPROVE",
            event_id=decision.event_id,
            decided_at=_DECIDED_AT,
        )
        database = open_control_database(database_path)
        try:
            repo = RunRepository(database)
            barrier.wait()
            with database.immediate_transaction() as tx:
                lock_result = repo.lock_wait_for_decision(tx, candidate)
                if lock_result.kind == "LOCKED" and lock_result.lock is not None:
                    outcomes.append(
                        repo.commit_wait_decision(tx, lock_result.lock, candidate).kind
                    )
                else:
                    outcomes.append(lock_result.kind)
        finally:
            database.close()

    threads = [
        threading.Thread(target=_decide),
        threading.Thread(target=_decide),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["ALREADY_DECIDED", "APPLIED"]


def test_insert_created_requires_created_state(
    run_repository: RunRepository,
) -> None:
    with pytest.raises(ValueError, match="CREATED"):
        run_repository.insert_created(
            RunRecordV1(
                run_id="run-bad",
                workspace_identity="workspace-1",
                status="RUNNING",
                phase=PresentV1(kind="PRESENT", value="PREFLIGHT"),
                config_snapshot_id="snap-run-bad",
                started_at=_CREATED_AT,
                run_deadline=_RUN_DEADLINE,
            )
        )


def test_insert_created_rejects_duplicate_run_id(
    control_database: ControlDatabase,
    run_repository: RunRepository,
    run_record: RunRecordV1,
) -> None:
    _insert_snapshot(control_database, run_record.config_snapshot_id)
    run_repository.insert_created(run_record)
    with pytest.raises(RunAlreadyExistsErrorV1):
        run_repository.insert_created(run_record)


def test_compare_and_transition_not_found(
    run_repository: RunRepository,
) -> None:
    result = run_repository.compare_and_transition(
        TransitionCommandV1(
            run_id="run-missing",
            expected=CREATED,
            target=RUNNING_PREFLIGHT,
        )
    )
    assert result.kind == "NOT_FOUND"


def test_compare_and_transition_rejects_illegal_pair(
    run_repository: RunRepository,
) -> None:
    result = run_repository.compare_and_transition(
        TransitionCommandV1(
            run_id="run-any",
            expected=SUCCEEDED,
            target=RUNNING_PREFLIGHT,
        )
    )
    assert result.kind == "INVALID"


def test_create_wait_rejects_duplicate_wait_id(
    control_database: ControlDatabase,
    run_repository: RunRepository,
    run_record: RunRecordV1,
    decision: WaitDecisionV1,
) -> None:
    with pytest.raises(WaitAlreadyExistsErrorV1):
        run_repository.create_wait(
            WaitContextV1(
                wait_id="wait-1",
                run_id=run_record.run_id,
                wait_kind="DISCLOSURE_GRANT",
                source_phase="AGENT_LOOP",
                subject_digest=_SUBJECT_DIGEST,
                created_at=_CREATED_AT,
                expires_at=_EXPIRES_AT,
            )
        )


def test_locked_but_uncommitted_decision_rolls_back_to_pending(
    control_database: ControlDatabase,
    run_repository: RunRepository,
    decision: WaitDecisionV1,
) -> None:
    """An aborted caller transaction reverts the DECIDING reservation.

    The lock lives inside the caller transaction: after a raise the
    reservation rolls back to PENDING and a fresh decision can lock again.
    """
    with pytest.raises(RuntimeError, match="abort"):
        with control_database.immediate_transaction() as tx:
            first = run_repository.lock_wait_for_decision(tx, decision)
            assert first.kind == "LOCKED"
            raise RuntimeError("abort")
    assert _wait_row_status(control_database, decision.wait_id) == "PENDING"
    assert lock_wait_once(run_repository, decision).kind == "LOCKED"


def test_expire_wait_settles_an_expired_wait(
    control_database: ControlDatabase,
    run_repository: RunRepository,
) -> None:
    _insert_run(control_database, "run-expire-me", CREATED)
    run_repository.create_wait(
        WaitContextV1(
            wait_id="wait-expire-me",
            run_id="run-expire-me",
            wait_kind="DISCLOSURE_GRANT",
            source_phase="AGENT_LOOP",
            subject_digest=_SUBJECT_DIGEST,
            created_at=_CREATED_AT,
            expires_at=_EXPIRES_AT,
        )
    )
    candidate = WaitDecisionV1(
        wait_id="wait-expire-me",
        run_id="run-expire-me",
        wait_kind="DISCLOSURE_GRANT",
        subject_digest=_SUBJECT_DIGEST,
        decision="APPROVE",
        event_id="evt-expire",
        decided_at=_DECIDED_AT,
    )
    with control_database.immediate_transaction() as tx:
        lock_result = run_repository.lock_wait_for_decision(tx, candidate)
        assert lock_result.kind == "LOCKED"
        assert lock_result.lock is not None
        not_yet = run_repository.expire_wait(tx, lock_result.lock, _CREATED_AT)
        assert not_yet.kind == "NOT_EXPIRED"
        expired = run_repository.expire_wait(tx, lock_result.lock, _LATE_DECIDED_AT)
        assert expired.kind == "EXPIRED"
        already = run_repository.expire_wait(tx, lock_result.lock, _LATE_DECIDED_AT)
        assert already.kind == "ALREADY_DECIDED"
    assert _wait_row_status(control_database, "wait-expire-me") == "EXPIRED"
