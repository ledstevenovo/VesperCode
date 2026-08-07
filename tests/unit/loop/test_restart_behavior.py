"""T25.2 legacy step 25.F: non-persistent restart fail-close tests.

The exact RED test pins the unfinished-turn disposition (an interrupted
ACTIVE turn stops with ``PROCESS_RESTART_DURING_TURN`` and forbids
resend); the matrix pins the exact disposition table of the 25.F
Expected line — every interrupted non-persistent phase fails closed with
zero resend, active-turn precedence over every status, clean boundaries,
and the persistent-phase/recovery deferral.
"""

from __future__ import annotations

import pytest

# The guard consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from vespercode.contracts.run import RunPhase
from vespercode.loop.restart import (
    RestartDispositionV1,
    RestartGuard,
    RestartStopReasonV1,
    RunEvidenceV1,
)

PHASES: tuple[RunPhase, ...] = (
    "PREFLIGHT",
    "BASELINE",
    "AGENT_LOOP",
    "FORMAL_VALIDATION",
    "PERSISTENCE",
)


def run_with_unfinished_turn() -> RunEvidenceV1:
    """One persisted RUNNING(AGENT_LOOP) run with an ACTIVE turn row."""
    return RunEvidenceV1(
        schema_version=1,
        run_id="run-1",
        status="RUNNING",
        phase="AGENT_LOOP",
        active_turn=True,
    )


@pytest.fixture
def restart_guard() -> RestartGuard:
    return RestartGuard()


def test_restart_during_active_turn_stops_without_resend(
    restart_guard: RestartGuard,
) -> None:
    result = restart_guard.inspect(run_with_unfinished_turn())
    assert result.stop_reason == "PROCESS_RESTART_DURING_TURN"
    assert result.resend_allowed is False


def test_restart_disposition_matrix(restart_guard: RestartGuard) -> None:
    """PLAN Registry row 25.F: the exact restart disposition matrix.

    Per the SPEC_PROCESS 49 precedent the card Expected line is the
    operative matrix authority: every interrupted non-persistent phase
    fails closed with zero resend.
    """

    def inspect(
        status: str,
        phase: RunPhase | None = None,
        active_turn: bool = False,
    ) -> RestartDispositionV1:
        return restart_guard.inspect(
            RunEvidenceV1(
                schema_version=1,
                run_id="run-1",
                status=status,
                phase=phase,
                active_turn=active_turn,
            )
        )

    # --- Interrupted non-persistent phases: fail-closed stops, no resend. ---
    for phase in ("PREFLIGHT", "BASELINE", "AGENT_LOOP", "FORMAL_VALIDATION"):
        disposition = inspect("RUNNING", phase)
        assert disposition.kind == "STOP"
        assert disposition.stop_reason == "PROCESS_RESTARTED_DURING_RUN"
        assert disposition.resend_allowed is False
        assert disposition.run_id == "run-1"

    # --- The unfinished-turn stop (the card's exact RED) in every phase,
    #     with active-turn precedence over every status. ---
    for phase in PHASES:
        disposition = inspect("RUNNING", phase, active_turn=True)
        assert disposition.kind == "STOP"
        assert disposition.stop_reason == "PROCESS_RESTART_DURING_TURN"
        assert disposition.resend_allowed is False

    # --- The two WAITING_USER kinds restart-stop without turn recovery. ---
    waiting = inspect("WAITING_USER")
    assert waiting.kind == "STOP"
    assert waiting.stop_reason == "PROCESS_RESTARTED_DURING_RUN"
    assert waiting.resend_allowed is False
    waiting_turn = inspect("WAITING_USER", active_turn=True)
    assert waiting_turn.stop_reason == "PROCESS_RESTART_DURING_TURN"

    # --- Clean boundaries: terminal runs and never-started runs continue. ---
    for status in ("SUCCEEDED", "STOPPED"):
        clean = inspect(status)
        assert clean.kind == "CONTINUE"
        assert clean.stop_reason is None
        assert clean.resend_allowed is False
    created = inspect("CREATED")
    assert created.kind == "CONTINUE"
    assert created.stop_reason is None
    # Contradictory terminal evidence with an ACTIVE turn still fails
    # closed: the interrupted turn always takes precedence.
    terminal_turn = inspect("SUCCEEDED", active_turn=True)
    assert terminal_turn.kind == "STOP"
    assert terminal_turn.stop_reason == "PROCESS_RESTART_DURING_TURN"

    # --- The persistent phase and recovery-required defer to the
    #     persistence recovery machinery (Task 3, out of scope). ---
    persistence = inspect("RUNNING", "PERSISTENCE")
    assert persistence.kind == "DEFER_RECOVERY"
    assert persistence.stop_reason is None
    assert persistence.resend_allowed is False
    recovery = inspect("RECOVERY_REQUIRED")
    assert recovery.kind == "DEFER_RECOVERY"
    assert recovery.stop_reason is None

    # --- Incomplete evidence fails closed (SPEC 5.2): a RUNNING run
    #     without a phase is an interrupted non-persistent run. ---
    incomplete = inspect("RUNNING")
    assert incomplete.kind == "STOP"
    assert incomplete.stop_reason == "PROCESS_RESTARTED_DURING_RUN"

    # --- Resend is forbidden on every disposition by construction. ---
    for disposition in (
        inspect("RUNNING", "AGENT_LOOP"),
        inspect("RUNNING", "AGENT_LOOP", active_turn=True),
        inspect("SUCCEEDED"),
        inspect("RECOVERY_REQUIRED"),
    ):
        assert disposition.resend_allowed is False


def test_restart_disposition_contract_is_closed(restart_guard: RestartGuard) -> None:
    """The disposition envelope rejects invalid stop commands."""
    with pytest.raises(Exception, match="stop reason"):
        RestartDispositionV1(
            schema_version=1, kind="STOP", stop_reason=None, run_id="run-1"
        )
    with pytest.raises(Exception, match="stop reason"):
        RestartDispositionV1(
            schema_version=1,
            kind="CONTINUE",
            stop_reason="PROCESS_RESTART_DURING_TURN",
            run_id="run-1",
        )
    with pytest.raises(Exception, match="resend"):
        RestartDispositionV1(
            schema_version=1,
            kind="STOP",
            stop_reason="PROCESS_RESTART_DURING_TURN",
            resend_allowed=True,  # type: ignore[arg-type]
            run_id="run-1",
        )
    with pytest.raises(Exception, match="status"):
        RunEvidenceV1(schema_version=1, run_id="run-1", status="PAUSED")


def test_restart_disposition_reasons_are_closed() -> None:
    """The two stop reasons are the exact SPEC §4.2.7 vocabulary."""
    reasons: tuple[RestartStopReasonV1, ...] = (
        "PROCESS_RESTART_DURING_TURN",
        "PROCESS_RESTARTED_DURING_RUN",
    )
    for reason in reasons:
        disposition = RestartDispositionV1(
            schema_version=1, kind="STOP", stop_reason=reason, run_id="run-1"
        )
        assert disposition.stop_reason == reason
        assert disposition.resend_allowed is False
