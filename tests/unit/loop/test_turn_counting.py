"""T25.1 legacy step 25.B: exact active-turn/call-counting boundary tests.

The exact RED test pins the zero-count abort path; the matrix pins every
credential/Grant/readiness/transport pre-call boundary with an explicit
exact count outcome (SPEC 5.1), the one-winner concurrent begin, the
revision compare-and-update call-start/close, and the close/replay
conflicts against the PLAN Registry row for 25.B.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

# The boundary consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips cleanly
# there (formal env runs it fully).
pytest.importorskip("pydantic")

from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.contracts.run import RunStateV1
from vespercode.loop.turn_boundary import (
    TurnBoundary,
    TurnBoundaryErrorV1,
    TurnCounterMissingErrorV1,
    TurnOutcomeV1,
)
from vespercode.storage.connection import (
    ControlDatabase,
    open_control_database,
)
from vespercode.storage.migration_engine import MigrationV1, apply_migrations
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

RUNNING_PREFLIGHT = RunStateV1(
    status="RUNNING", phase=PresentV1(kind="PRESENT", value="PREFLIGHT")
)
RUNNING_AGENT_LOOP = RunStateV1(
    status="RUNNING", phase=PresentV1(kind="PRESENT", value="AGENT_LOOP")
)
WAITING_USER = RunStateV1(status="WAITING_USER", phase=AbsentV1(kind="ABSENT"))


def _prefix() -> tuple[MigrationV1, ...]:
    return (
        RUN_WAIT_V1_MIGRATION,
        IDEMPOTENCY_V1_MIGRATION,
        DISCLOSURE_GRANTS_V1_MIGRATION,
        DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
        MEMORY_V1_MIGRATION,
        AUDIT_V1_MIGRATION,
    )


def _insert_run(database: ControlDatabase, run_id: str, state: RunStateV1) -> None:
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
                f"d-{run_id}",
                "mock-deterministic-v1",
                "python-src-py312-v1",
                "PYTHON_SRC_ONLY_V1",
                "[]",
                "c" * 64,
                "2026-08-06T09:00:00.000Z",
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
                "2026-08-06T09:00:00.000Z",
                "2026-08-06T09:15:00.000Z",
            ),
        )


def _turn_row_count(database: ControlDatabase, run_id: str) -> int:
    rows = database.read_rows(
        "SELECT COUNT(*) FROM agent_turns WHERE run_id = ?",
        (run_id,),
    )
    return int(rows[0][0])


def _counter_row(
    database: ControlDatabase,
    run_id: str,
) -> tuple[int, int] | None:
    rows = database.read_rows(
        "SELECT turn_count, call_count FROM run_turn_call_counters WHERE run_id = ?",
        (run_id,),
    )
    if not rows:
        return None
    return (int(rows[0][0]), int(rows[0][1]))


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "turn_counting.db")
    apply_migrations(database, _prefix() + (AGENT_TURNS_V1_MIGRATION,))
    yield database
    database.close()


@pytest.fixture
def boundary(control_database: ControlDatabase) -> TurnBoundary:
    return TurnBoundary(control_database)


def test_pre_call_failure_does_not_increment_turn_or_call(
    boundary: TurnBoundary,
) -> None:
    result = boundary.abort_before_call("run-1", "CREDENTIAL_MISSING")
    assert result.turn_count == 0
    assert result.call_count == 0


class _FixedIdGenerator:
    """One deterministic turn id generator for the rejection pins."""

    def __init__(self, value: str) -> None:
        self._value = value

    def next_id(self) -> str:
        return self._value


def test_turn_boundary_closed_rejections(
    control_database: ControlDatabase,
    boundary: TurnBoundary,
) -> None:
    """The closed rejection vocabulary covers every invalid call path."""
    _insert_run(control_database, "run-rejects", RUNNING_AGENT_LOOP)

    # A close with a stale expected revision on an ACTIVE turn is STALE.
    begun = boundary.begin("run-rejects", RUNNING_AGENT_LOOP)
    assert begun.kind == "APPLIED"
    assert begun.turn_id is not None
    stale_close = boundary.close_turn("run-rejects", begun.turn_id, "SUCCEEDED", 2)
    assert stale_close.kind == "STALE"
    assert stale_close.turn_count == 1
    assert stale_close.call_count == 0
    assert _counter_row(control_database, "run-rejects") == (1, 0)

    # Non-positive expected revisions fail closed before any mutation.
    with pytest.raises(TurnBoundaryErrorV1, match="revision"):
        boundary.record_call_started("run-rejects", begun.turn_id, 0)
    with pytest.raises(TurnBoundaryErrorV1, match="revision"):
        boundary.close_turn("run-rejects", begun.turn_id, "SUCCEEDED", 0)
    assert _counter_row(control_database, "run-rejects") == (1, 0)

    # The ACTIVE turn closes exactly once with the exact revision.
    closed = boundary.close_turn("run-rejects", begun.turn_id, "SUCCEEDED", 1)
    assert closed.kind == "APPLIED"

    # A duplicate Harness turn id fails closed (no raw sqlite error escapes).
    duplicate = TurnBoundary(
        control_database, turn_id_generator=_FixedIdGenerator("turn-fixed")
    )
    first = duplicate.begin("run-rejects", RUNNING_AGENT_LOOP)
    assert first.kind == "APPLIED"
    assert first.turn_id == "turn-fixed"
    closed_fixed = duplicate.close_turn("run-rejects", "turn-fixed", "FAILED", 1)
    assert closed_fixed.kind == "APPLIED"
    with pytest.raises(TurnBoundaryErrorV1, match="already exists"):
        duplicate.begin("run-rejects", RUNNING_AGENT_LOOP)
    assert _counter_row(control_database, "run-rejects") == (2, 0)

    # An empty generated turn id fails closed before any insert.
    empty = TurnBoundary(control_database, turn_id_generator=_FixedIdGenerator(""))
    with pytest.raises(TurnBoundaryErrorV1, match="turn id"):
        empty.begin("run-rejects", RUNNING_AGENT_LOOP)
    assert _counter_row(control_database, "run-rejects") == (2, 0)

    # An oversized abort reason fails closed.
    with pytest.raises(TurnBoundaryErrorV1, match="reason"):
        boundary.abort_before_call("run-rejects", "X" * 65)

    # A missing counter row (out-of-band corruption) fails closed.
    fresh = boundary.begin("run-rejects", RUNNING_AGENT_LOOP)
    assert fresh.kind == "APPLIED"
    assert fresh.turn_id is not None
    with control_database.immediate_transaction() as tx:
        tx.execute("DELETE FROM run_turn_call_counters WHERE run_id = 'run-rejects'")
    with pytest.raises(TurnCounterMissingErrorV1, match="counter row missing"):
        boundary.record_call_started("run-rejects", fresh.turn_id, 1)


def test_turn_count_transaction_matrix(
    tmp_path: Path,
    control_database: ControlDatabase,
    boundary: TurnBoundary,
) -> None:
    """PLAN Registry row 25.B: the exact 5.1 pre-call counting matrix.

    Per the SPEC_PROCESS 49 precedent the card Expected line is the
    operative matrix authority: every credential/Grant/readiness/transport
    boundary has an explicit exact count outcome and concurrent starts
    admit one active turn.
    """
    _insert_run(control_database, "run-matrix", RUNNING_AGENT_LOOP)

    # --- Every pre-call failure boundary: zero increments, zero effects. ---
    for reason in (
        "CREDENTIAL_MISSING",
        "CREDENTIAL_BACKEND_UNSAFE",
        "DISCLOSURE_SCOPE_EXCEEDED",
        "REQUEST_NOT_FROZEN",
        "PROFILE_ADAPTER_MISMATCH",
        "LLM_ENDPOINT_MISMATCH",
        "WAITING_USER",
    ):
        aborted = boundary.abort_before_call("run-matrix", reason)
        assert aborted.reason == reason
        assert aborted.turn_count == 0
        assert aborted.call_count == 0
    assert _turn_row_count(control_database, "run-matrix") == 0
    assert _counter_row(control_database, "run-matrix") is None

    # --- begin guards: only RUNNING(AGENT_LOOP) expectations are legal. ---
    # WAITING_USER never creates a turn or consumes a call (SPEC 4.2.5).
    invalid = boundary.begin("run-matrix", WAITING_USER)
    assert invalid.kind == "INVALID"
    assert invalid.turn_count == 0
    assert invalid.call_count == 0
    assert _turn_row_count(control_database, "run-matrix") == 0
    assert _counter_row(control_database, "run-matrix") is None

    # A run not in the expected state: stale, no mutation.
    _insert_run(control_database, "run-preflight", RUNNING_PREFLIGHT)
    stale = boundary.begin("run-preflight", RUNNING_AGENT_LOOP)
    assert stale.kind == "STALE"
    assert stale.turn_count == 0
    assert stale.call_count == 0
    assert _turn_row_count(control_database, "run-preflight") == 0
    assert _counter_row(control_database, "run-preflight") is None

    # A missing run: not found, zero counts.
    missing = boundary.begin("run-missing", RUNNING_AGENT_LOOP)
    assert missing.kind == "NOT_FOUND"
    assert missing.turn_count == 0
    assert missing.call_count == 0

    # --- The successful boundaries advance exactly one counter each. ---
    begun = boundary.begin("run-matrix", RUNNING_AGENT_LOOP)
    assert begun.kind == "APPLIED"
    assert begun.turn_count == 1
    assert begun.call_count == 0
    assert begun.turn_id is not None
    turn_id = begun.turn_id

    # One active turn per Run: a second begin conflicts without mutation.
    second = boundary.begin("run-matrix", RUNNING_AGENT_LOOP)
    assert second.kind == "ALREADY_ACTIVE"
    assert second.turn_count == 1
    assert second.call_count == 0
    assert _turn_row_count(control_database, "run-matrix") == 1

    # The partial unique index is the DDL backstop.
    with pytest.raises(Exception, match="UNIQUE constraint failed"):
        with control_database.immediate_transaction() as tx:
            tx.execute(
                "INSERT INTO agent_turns (turn_id, run_id, revision, status,"
                " outcome, closed_at, request_ref, result_ref)"
                " VALUES ('turn-backstop', 'run-matrix', 1, 'ACTIVE', NULL,"
                " NULL, NULL, NULL)"
            )

    # --- record_call_started is the exact call-start CAS boundary. ---
    stale_call = boundary.record_call_started("run-matrix", turn_id, 2)
    assert stale_call.kind == "STALE"
    assert stale_call.call_count == 0
    wrong_run = boundary.record_call_started("run-other", turn_id, 1)
    assert wrong_run.kind == "RUN_MISMATCH"
    assert wrong_run.call_count == 0
    missing_call = boundary.record_call_started("run-matrix", "turn-missing", 1)
    assert missing_call.kind == "NOT_FOUND"
    assert missing_call.call_count == 0
    started = boundary.record_call_started("run-matrix", turn_id, 1)
    assert started.kind == "APPLIED"
    assert started.turn_count == 1
    assert started.call_count == 1

    # --- Post-boundary failures keep the consumed counts. ---
    closed_not_attempted = boundary.close_turn(
        "run-matrix", turn_id, "NOT_ATTEMPTED", expected_revision=2
    )
    assert closed_not_attempted.kind == "APPLIED"
    assert closed_not_attempted.outcome == "NOT_ATTEMPTED"
    assert closed_not_attempted.turn_count == 1
    assert closed_not_attempted.call_count == 1

    # Close replay conflicts: a closed turn never closes again.
    replay = boundary.close_turn("run-matrix", turn_id, "SUCCEEDED", 3)
    assert replay.kind == "CLOSED"
    assert replay.turn_count == 1
    assert replay.call_count == 1
    replay_stale = boundary.close_turn("run-matrix", turn_id, "SUCCEEDED", 2)
    assert replay_stale.kind == "CLOSED"
    assert replay_stale.turn_count == 1
    assert replay_stale.call_count == 1
    after_close = boundary.record_call_started("run-matrix", turn_id, 3)
    assert after_close.kind == "CLOSED"
    assert after_close.call_count == 1

    # A missing or run-mismatched close fails without mutation.
    missing_close = boundary.close_turn("run-matrix", "turn-missing", "FAILED", 1)
    assert missing_close.kind == "NOT_FOUND"
    wrong_run_close = boundary.close_turn("run-other", turn_id, "FAILED", 3)
    assert wrong_run_close.kind == "RUN_MISMATCH"

    # --- A second turn: begin advances only the turn counter. ---
    begun2 = boundary.begin("run-matrix", RUNNING_AGENT_LOOP)
    assert begun2.kind == "APPLIED"
    assert begun2.turn_count == 2
    assert begun2.call_count == 1
    assert begun2.turn_id is not None
    started2 = boundary.record_call_started("run-matrix", begun2.turn_id, 1)
    assert started2.kind == "APPLIED"
    assert started2.call_count == 2
    closed2 = boundary.close_turn("run-matrix", begun2.turn_id, "FAILED", 2)
    assert closed2.kind == "APPLIED"
    assert closed2.outcome == "FAILED"
    assert closed2.turn_count == 2
    assert closed2.call_count == 2

    # --- Every closed outcome value closes exactly one active turn. ---
    outcomes: tuple[TurnOutcomeV1, ...] = (
        "SUCCEEDED",
        "FAILED",
        "NOT_ATTEMPTED",
        "ABORTED",
    )
    for index, outcome in enumerate(outcomes):
        each = boundary.begin("run-matrix", RUNNING_AGENT_LOOP)
        assert each.kind == "APPLIED"
        assert each.turn_id is not None
        assert each.turn_count == 3 + index
        assert each.call_count == 2
        closed_each = boundary.close_turn(
            "run-matrix", each.turn_id, outcome, expected_revision=1
        )
        assert closed_each.kind == "APPLIED"
        assert closed_each.outcome == outcome

    # An unknown outcome value is rejected before any mutation.
    each = boundary.begin("run-matrix", RUNNING_AGENT_LOOP)
    assert each.kind == "APPLIED"
    assert each.turn_id is not None
    with pytest.raises(TurnBoundaryErrorV1, match="outcome"):
        boundary.close_turn("run-matrix", each.turn_id, cast(TurnOutcomeV1, "MAYBE"), 1)
    assert _turn_row_count(control_database, "run-matrix") == 7
    assert _counter_row(control_database, "run-matrix") == (7, 2)
    # The rejected close did not close the turn: it stays active and can
    # still close exactly once with a legal outcome.
    closed_legal = boundary.close_turn("run-matrix", each.turn_id, "ABORTED", 1)
    assert closed_legal.kind == "APPLIED"

    # --- abort after counts: zero side effects, exact unchanged counts. ---
    before = _counter_row(control_database, "run-matrix")
    assert before == (7, 2)
    aborted = boundary.abort_before_call("run-matrix", "CREDENTIAL_BACKEND_UNSAFE")
    assert aborted.turn_count == 7
    assert aborted.call_count == 2
    assert _counter_row(control_database, "run-matrix") == before
    assert _turn_row_count(control_database, "run-matrix") == 7

    # --- Concurrent starts admit exactly one active turn. ---
    database_path = tmp_path / "turn_counting.db"
    begin_outcomes: list[str] = []
    barrier = threading.Barrier(2)

    def _begin() -> None:
        database = open_control_database(database_path)
        try:
            contender = TurnBoundary(database)
            barrier.wait()
            begin_outcomes.append(
                contender.begin("run-matrix", RUNNING_AGENT_LOOP).kind
            )
        finally:
            database.close()

    threads = [
        threading.Thread(target=_begin),
        threading.Thread(target=_begin),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(begin_outcomes) == ["ALREADY_ACTIVE", "APPLIED"]
    assert _counter_row(control_database, "run-matrix") == (8, 2)
