"""T07.2 legacy step 7.B: pure Run/wait lifecycle rules tests.

``LifecycleRules.evaluate`` is the pure target-state derivation over the
closed SPEC 4.2.7 transition set: every legal transition maps exactly, and
every illegal combination (wrong phase, wrong wait kind, terminal reopen,
stale source) fails closed with the closed transition error.
"""

from __future__ import annotations

import pytest

# The rules consume pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips cleanly
# there (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.contracts.run import RunStateV1
from vespercode.runs.lifecycle import (
    LifecycleEventV1,
    LifecycleRules,
    LifecycleTransitionErrorV1,
)

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

# Every SPEC 4.2.7 legal (expected, event, target) triple.
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

# Every illegal (current, event) combination pinned from SPEC 4.2.7.
ILLEGAL_CASES: tuple[tuple[RunStateV1, LifecycleEventV1], ...] = (
    (RUNNING_PREFLIGHT, LifecycleEventV1(kind="START")),
    (SUCCEEDED, LifecycleEventV1(kind="START")),
    (STOPPED, LifecycleEventV1(kind="START")),
    (CREATED, LifecycleEventV1(kind="PHASE", phase="BASELINE")),
    (RUNNING_AGENT_LOOP, LifecycleEventV1(kind="PHASE", phase="PREFLIGHT")),
    (RUNNING_AGENT_LOOP, LifecycleEventV1(kind="PHASE", phase="BASELINE")),
    (RUNNING_BASELINE, LifecycleEventV1(kind="PHASE", phase="PREFLIGHT")),
    (
        RUNNING_FORMAL_VALIDATION,
        LifecycleEventV1(kind="PHASE", phase="FORMAL_VALIDATION"),
    ),
    (WAITING_USER, LifecycleEventV1(kind="PHASE", phase="BASELINE")),
    (CREATED, LifecycleEventV1(kind="WAIT", wait_kind="DISCLOSURE_GRANT")),
    (
        RUNNING_FORMAL_VALIDATION,
        LifecycleEventV1(kind="WAIT", wait_kind="DISCLOSURE_GRANT"),
    ),
    (RUNNING_AGENT_LOOP, LifecycleEventV1(kind="WAIT", wait_kind="FINAL_WRITEBACK")),
    (
        RUNNING_AGENT_LOOP,
        LifecycleEventV1(kind="WAIT_APPROVED", wait_kind="DISCLOSURE_GRANT"),
    ),
    (CREATED, LifecycleEventV1(kind="WAIT_APPROVED", wait_kind="DISCLOSURE_GRANT")),
    (
        RUNNING_AGENT_LOOP,
        LifecycleEventV1(kind="WAIT_TERMINATED", wait_kind="DISCLOSURE_GRANT"),
    ),
    (CREATED, LifecycleEventV1(kind="WAIT_TERMINATED", wait_kind="DISCLOSURE_GRANT")),
    (SUCCEEDED, LifecycleEventV1(kind="STOP")),
    (STOPPED, LifecycleEventV1(kind="STOP")),
    (RECOVERY_REQUIRED, LifecycleEventV1(kind="STOP")),
    (CREATED, LifecycleEventV1(kind="SUCCEED")),
    (RUNNING_AGENT_LOOP, LifecycleEventV1(kind="SUCCEED")),
    (RUNNING_AGENT_LOOP, LifecycleEventV1(kind="PERSISTENCE_FAILED")),
    (CREATED, LifecycleEventV1(kind="RECOVER", recover_outcome="SUCCEEDED")),
    (RUNNING_PERSISTENCE, LifecycleEventV1(kind="RECOVER", recover_outcome="KEEP")),
)


def test_lifecycle_event_is_closed() -> None:
    for payload in (
        {"kind": "PHASE", "phase": "BASELINE", "extra": 1},
        {"kind": "PHASE"},
        {"kind": "PHASE", "phase": None},
        {"kind": "WAIT"},
        {"kind": "WAIT", "wait_kind": "UNKNOWN_KIND"},
        {"kind": "STOP", "phase": "BASELINE"},
        {"kind": "STOP", "wait_kind": "DISCLOSURE_GRANT"},
        {"kind": "RECOVER"},
        {"kind": "RECOVER", "recover_outcome": "MAYBE"},
        {"kind": "RECOVER", "phase": "BASELINE"},
        {"kind": "START", "recover_outcome": "KEEP"},
    ):
        with pytest.raises(ValidationError):
            LifecycleEventV1.model_validate(payload)


def test_every_spec_legal_transition_derives_exactly() -> None:
    for expected, event, target in LEGAL_CASES:
        assert LifecycleRules.evaluate(expected, event) == target
        assert LifecycleRules.is_legal_transition(expected, target)


def test_every_illegal_transition_fails_closed() -> None:
    for current, event in ILLEGAL_CASES:
        with pytest.raises(LifecycleTransitionErrorV1):
            LifecycleRules.evaluate(current, event)


def test_terminal_states_never_reopen() -> None:
    for terminal in (SUCCEEDED, STOPPED):
        for event in (
            LifecycleEventV1(kind="START"),
            LifecycleEventV1(kind="SUCCEED"),
            LifecycleEventV1(kind="STOP"),
            LifecycleEventV1(kind="PHASE", phase="PREFLIGHT"),
        ):
            with pytest.raises(LifecycleTransitionErrorV1):
                LifecycleRules.evaluate(terminal, event)
        assert not LifecycleRules.is_legal_transition(terminal, RUNNING_AGENT_LOOP)
        assert not LifecycleRules.is_legal_transition(terminal, CREATED)
        assert not LifecycleRules.is_legal_transition(terminal, WAITING_USER)
