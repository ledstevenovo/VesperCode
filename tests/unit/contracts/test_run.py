"""T05.1 legacy step 5.B: closed Run state/phase/wait/limit contract tests.

The matrix pins every legal state/phase/wait/limit combination round-trip
and every illegal combination rejection; lifecycle transitions,
repositories, decision services, and clock behavior remain out of scope
(GREEN-4).
"""

from __future__ import annotations

import pytest

# The Run models are pydantic runtime contracts; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.run import (
    RunLimitsV1,
    RunStateV1,
    WaitContextV1,
    WaitDecisionV1,
)

_TS = CanonicalTimestampV1("2026-08-05T09:30:15.123Z")
_LATER_TS = CanonicalTimestampV1("2026-08-05T09:31:15.123Z")
_DIGEST = "a" * 64


def test_running_state_requires_exact_phase() -> None:
    with pytest.raises(ValidationError):
        RunStateV1.model_validate({"status": "RUNNING"})


def test_run_state_phase_limit_matrix() -> None:
    """SPEC §4.2.1/§4.2.7/§4.1 state/phase/wait/limit matrix (Expected 5.B).

    Every legal state/phase/wait/limit combination round-trips and every
    illegal combination rejects deterministically.
    """
    # RunStateV1: RUNNING requires its exact phase; other statuses ABSENT.
    for phase in (
        "PREFLIGHT",
        "BASELINE",
        "AGENT_LOOP",
        "FORMAL_VALIDATION",
        "PERSISTENCE",
    ):
        state = RunStateV1.model_validate(
            {"status": "RUNNING", "phase": {"kind": "PRESENT", "value": phase}}
        )
        assert state.status == "RUNNING" and state.phase.kind == "PRESENT"
    for status in (
        "CREATED",
        "WAITING_USER",
        "RECOVERY_REQUIRED",
        "SUCCEEDED",
        "STOPPED",
    ):
        state = RunStateV1.model_validate(
            {"status": status, "phase": {"kind": "ABSENT"}}
        )
        assert state.status == status and state.phase.kind == "ABSENT"
    for payload in (
        {"status": "RUNNING", "phase": {"kind": "ABSENT"}},  # RUNNING without phase
        {"status": "CREATED", "phase": {"kind": "PRESENT", "value": "PREFLIGHT"}},
        {"status": "SUCCEEDED", "phase": {"kind": "PRESENT", "value": "PERSISTENCE"}},
        {"status": "RUNNING", "phase": {"kind": "PRESENT", "value": "CLEANUP"}},
        {"status": "PAUSED", "phase": {"kind": "ABSENT"}},
        {"status": "RUNNING", "phase": None},
        {"status": "RUNNING"},  # missing phase (RED)
        {"status": "RUNNING", "phase": {"kind": "ABSENT"}, "extra": 1},
    ):
        with pytest.raises(ValidationError):
            RunStateV1.model_validate(payload)

    # WaitContextV1: wait kind binds its exact source phase and time order.
    context_base: dict[str, object] = {
        "wait_id": "w1",
        "run_id": "r1",
        "subject_digest": {"value": _DIGEST},
        "created_at": _TS,
        "expires_at": _LATER_TS,
    }
    for wait_kind, source_phase in (
        ("DISCLOSURE_GRANT", "AGENT_LOOP"),
        ("FINAL_WRITEBACK", "FORMAL_VALIDATION"),
    ):
        context = WaitContextV1.model_validate(
            {**context_base, "wait_kind": wait_kind, "source_phase": source_phase}
        )
        assert context.wait_kind == wait_kind
    for payload in (
        {
            **context_base,
            "wait_kind": "DISCLOSURE_GRANT",
            "source_phase": "FORMAL_VALIDATION",
        },
        {**context_base, "wait_kind": "FINAL_WRITEBACK", "source_phase": "AGENT_LOOP"},
        {**context_base, "wait_kind": "FINAL_WRITEBACK", "source_phase": "PERSISTENCE"},
        {**context_base, "wait_kind": "APPROVAL", "source_phase": "AGENT_LOOP"},
        {
            **context_base,
            "wait_kind": "DISCLOSURE_GRANT",
            "source_phase": "AGENT_LOOP",
            "expires_at": CanonicalTimestampV1("2026-08-05T09:29:15.123Z"),
        },
        {
            k: v
            for k, v in {
                **context_base,
                "wait_kind": "DISCLOSURE_GRANT",
                "source_phase": "AGENT_LOOP",
            }.items()
            if k != "wait_id"
        },
        {
            **context_base,
            "wait_kind": "DISCLOSURE_GRANT",
            "source_phase": "AGENT_LOOP",
            "extra": 1,
        },
        {
            **context_base,
            "wait_kind": "DISCLOSURE_GRANT",
            "source_phase": "AGENT_LOOP",
            "subject_digest": {"value": "x"},
        },
        {
            **context_base,
            "wait_kind": "DISCLOSURE_GRANT",
            "source_phase": "AGENT_LOOP",
            "wait_id": "",
        },
        {
            **context_base,
            "wait_kind": "DISCLOSURE_GRANT",
            "source_phase": "AGENT_LOOP",
            "run_id": "",
        },
    ):
        with pytest.raises(ValidationError):
            WaitContextV1.model_validate(payload)

    # WaitDecisionV1: closed APPROVE/REJECT bound to wait/run/kind/subject/time.
    decision_base: dict[str, object] = {
        "wait_id": "w1",
        "run_id": "r1",
        "wait_kind": "DISCLOSURE_GRANT",
        "subject_digest": {"value": _DIGEST},
        "event_id": "evt-1",
        "decided_at": _TS,
    }
    for choice in ("APPROVE", "REJECT"):
        decision = WaitDecisionV1.model_validate({**decision_base, "decision": choice})
        assert decision.decision == choice
    for payload in (
        {**decision_base, "decision": "approve"},
        {**decision_base, "decision": "SKIP"},
        {**decision_base, "decision": None},
        {
            k: v
            for k, v in {**decision_base, "decision": "APPROVE"}.items()
            if k != "subject_digest"
        },
        {**decision_base, "decision": "APPROVE", "subject_digest": {"value": "A" * 64}},
        {
            **decision_base,
            "decision": "APPROVE",
            "decided_at": "2026-08-05T09:30:15.12Z",
        },
        {
            **decision_base,
            "decision": "APPROVE",
            "decided_at": "2026-08-05T09:30:15.123+00:00",
        },
        {**decision_base, "decision": "APPROVE", "extra": 1},
        {**decision_base, "decision": "APPROVE", "wait_id": ""},
        {**decision_base, "decision": "APPROVE", "run_id": ""},
        {**decision_base, "decision": "APPROVE", "event_id": ""},
    ):
        with pytest.raises(ValidationError):
            WaitDecisionV1.model_validate(payload)

    # RunLimitsV1: every value must sit inside the §4.1 hard bounds.
    limits_fields = (
        "max_turns",
        "max_llm_calls",
        "max_run_wall_clock_seconds",
        "user_wait_timeout_seconds",
        "tool_timeout_seconds",
        "target_check_timeout_seconds",
        "full_check_timeout_seconds",
        "baseline_timeout_seconds",
        "formal_validation_timeout_seconds",
    )
    full: dict[str, object] = {field: 10 for field in limits_fields}
    upper: dict[str, int] = {
        "max_turns": 20,
        "max_llm_calls": 20,
        "max_run_wall_clock_seconds": 900,
        "user_wait_timeout_seconds": 300,
        "tool_timeout_seconds": 60,
        "target_check_timeout_seconds": 120,
        "full_check_timeout_seconds": 300,
        "baseline_timeout_seconds": 600,
        "formal_validation_timeout_seconds": 600,
    }
    RunLimitsV1.model_validate(full)
    RunLimitsV1.model_validate(upper)
    RunLimitsV1.model_validate({field: 1 for field in limits_fields})
    for field in limits_fields:
        with pytest.raises(ValidationError):
            RunLimitsV1.model_validate({**full, field: upper[field] + 1})
        with pytest.raises(ValidationError):
            RunLimitsV1.model_validate({**full, field: 0})
        with pytest.raises(ValidationError):
            RunLimitsV1.model_validate({**full, field: "5"})
        with pytest.raises(ValidationError):
            RunLimitsV1.model_validate({**full, field: 5.0})
        with pytest.raises(ValidationError):
            RunLimitsV1.model_validate({**full, field: True})
    with pytest.raises(ValidationError):
        RunLimitsV1.model_validate({k: v for k, v in full.items() if k != "max_turns"})
    with pytest.raises(ValidationError):
        RunLimitsV1.model_validate({**full, "extra": 1})


def test_run_state_phase_round_trip() -> None:
    running = RunStateV1.model_validate(
        {"status": "RUNNING", "phase": {"kind": "PRESENT", "value": "AGENT_LOOP"}}
    )
    assert RunStateV1.model_validate(running.model_dump()) == running
    created = RunStateV1.model_validate(
        {"status": "CREATED", "phase": {"kind": "ABSENT"}}
    )
    assert RunStateV1.model_validate(created.model_dump()) == created


def test_wait_decision_requires_canonical_time() -> None:
    for value in (
        "2026-08-05T09:30:15.12Z",  # two-digit milliseconds
        "2026-08-05T09:30:15.1234Z",  # four-digit milliseconds
        "2026-08-05T09:30:15.123z",  # lowercase z
        "2026-08-05T09:30:15.123",  # missing Z
        "2026-02-30T09:30:15.123Z",  # invalid Gregorian date
        "2026-08-05T09:30:60.123Z",  # leap second
    ):
        with pytest.raises(ValidationError):
            WaitDecisionV1.model_validate(
                {
                    "wait_id": "w1",
                    "run_id": "r1",
                    "wait_kind": "DISCLOSURE_GRANT",
                    "subject_digest": {"value": _DIGEST},
                    "decision": "APPROVE",
                    "event_id": "evt-1",
                    "decided_at": value,
                }
            )


def test_run_models_are_immutable() -> None:
    state = RunStateV1.model_validate(
        {"status": "CREATED", "phase": {"kind": "ABSENT"}}
    )
    with pytest.raises(ValidationError):
        state.status = "STOPPED"
    limits = RunLimitsV1.model_validate(
        {
            "max_turns": 1,
            "max_llm_calls": 1,
            "max_run_wall_clock_seconds": 1,
            "user_wait_timeout_seconds": 1,
            "tool_timeout_seconds": 1,
            "target_check_timeout_seconds": 1,
            "full_check_timeout_seconds": 1,
            "baseline_timeout_seconds": 1,
            "formal_validation_timeout_seconds": 1,
        }
    )
    with pytest.raises(ValidationError):
        limits.max_turns = 2
