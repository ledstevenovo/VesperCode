"""T30.1 legacy step 30.A: exact fixed Mock scenario data tests.

Pins the sole frozen Mock scenario (card GREEN-2): its source, injected
failure, expected patch, visitor decisions, statuses, and canonical trace
are exact fixed values; prompts, URLs, uploads, provider, secret,
filesystem, Docker, persistence, and recovery inputs are rejected; the
scenario is immutable, deterministic, and carries no formal Run/turn/
repository identity or Demo-to-formal conversion path.  Executor, shared-core
sequencing, session storage, Web behavior, local files, credentials, Docker,
recovery, persistence, and real providers remain out of scope (GREEN-4).
"""

from __future__ import annotations

# Formal-identity probes must pass undeclared keywords (``run_id=...``) that
# the pydantic runtime must reject; mypy's dataclass-transform signature would
# otherwise refuse those intentional probes, so call-arg is disabled here.
# mypy: disable-error-code="call-arg"

import pytest

pytest.importorskip("pydantic")

from pydantic import ValidationError

from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.evidence import DigestV1
from src.vespercode.demo.scenario import FIXED_DEMO_SCENARIO_V1
from src.vespercode.demo.types import (
    DemoDecisionV1,
    DemoScenarioV1,
    DemoSessionV1,
    DemoTraceV1,
    DemoTypeIsolationError,
    RunIdV1,
)

_FIXED_DIGEST = "ab" * 32


def test_fixed_scenario_is_sole_and_frozen() -> None:
    scenario = FIXED_DEMO_SCENARIO_V1
    assert scenario.scenario_id == "mock-demo-v1"
    assert scenario.scenario_version == 1
    assert scenario.input_kinds == ("FIXED_SOURCE", "FIXED_FAILURE", "FIXED_PATCH")
    assert scenario.statuses == (
        "DEMO_CREATED",
        "DEMO_RUNNING",
        "DEMO_WAITING_USER",
        "DEMO_COMPLETED",
    )


def test_fixed_scenario_exact_source_failure_and_expected_patch() -> None:
    scenario = FIXED_DEMO_SCENARIO_V1
    assert scenario.source == (
        "README.md\n"
        "VesperCode Mock Demo\n"
        "\n"
        "Fix the failing test in tests/test_example.py."
    )
    assert scenario.injected_failure == "tests/test_example.py::test_example_success"
    assert scenario.expected_patch == (
        "--- a/src/example.py\n"
        "+++ b/src/example.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def example():\n"
        "-    return 0\n"
        "+    return 1\n"
    )


def test_fixed_scenario_exact_decisions() -> None:
    scenario = FIXED_DEMO_SCENARIO_V1
    assert scenario.decisions == (
        DemoDecisionV1(
            demo_session_id="demo-session-v1",
            subject_digest=DigestV1(value=_FIXED_DIGEST),
            decision="REJECT",
            created_at=CanonicalTimestampV1("2026-08-05T09:30:15.000Z"),
        ),
        DemoDecisionV1(
            demo_session_id="demo-session-v1",
            subject_digest=DigestV1(value=_FIXED_DIGEST),
            decision="APPROVE",
            created_at=CanonicalTimestampV1("2026-08-05T09:30:20.000Z"),
        ),
    )


def test_fixed_scenario_exact_trace() -> None:
    scenario = FIXED_DEMO_SCENARIO_V1
    assert scenario.trace == DemoTraceV1.model_validate(
        {
            "scenario_id": "mock-demo-v1",
            "steps": (
                {
                    "step_index": 0,
                    "action_label": "PATCH docs/outside-scope.md",
                    "outcome": "DENIED",
                    "status": "DEMO_RUNNING",
                    "decision": {"kind": "ABSENT"},
                },
                {
                    "step_index": 1,
                    "action_label": "PATCH README.md",
                    "outcome": "DENIED",
                    "status": "DEMO_RUNNING",
                    "decision": {"kind": "ABSENT"},
                },
                {
                    "step_index": 2,
                    "action_label": "PATCH src/example.py",
                    "outcome": "CHECK_FAILED",
                    "status": "DEMO_RUNNING",
                    "decision": {"kind": "ABSENT"},
                },
                {
                    "step_index": 3,
                    "action_label": "PATCH tests/test_example.py",
                    "outcome": "DENIED",
                    "status": "DEMO_RUNNING",
                    "decision": {"kind": "ABSENT"},
                },
                {
                    "step_index": 4,
                    "action_label": "FINAL_WRITEBACK",
                    "outcome": "REJECTED",
                    "status": "DEMO_WAITING_USER",
                    "decision": {
                        "kind": "PRESENT",
                        "value": {
                            "demo_session_id": "demo-session-v1",
                            "subject_digest": {"value": _FIXED_DIGEST},
                            "decision": "REJECT",
                            "created_at": {"value": "2026-08-05T09:30:15.000Z"},
                        },
                    },
                },
                {
                    "step_index": 5,
                    "action_label": "FINAL_WRITEBACK",
                    "outcome": "COMPLETED",
                    "status": "DEMO_COMPLETED",
                    "decision": {
                        "kind": "PRESENT",
                        "value": {
                            "demo_session_id": "demo-session-v1",
                            "subject_digest": {"value": _FIXED_DIGEST},
                            "decision": "APPROVE",
                            "created_at": {"value": "2026-08-05T09:30:20.000Z"},
                        },
                    },
                },
            ),
        }
    )


def test_fixed_scenario_rejects_forbidden_inputs() -> None:
    scenario = FIXED_DEMO_SCENARIO_V1
    for forbidden in (
        "prompt",
        "url",
        "upload",
        "provider",
        "secret",
        "filesystem",
        "docker",
        "persistence",
        "recovery",
    ):
        with pytest.raises(ValidationError):
            DemoScenarioV1.model_validate(
                {**scenario.model_dump(), forbidden: "forbidden input"}
            )


def test_fixed_scenario_closed_field_set_and_immutability() -> None:
    scenario = FIXED_DEMO_SCENARIO_V1
    assert set(scenario.model_dump()) == {
        "scenario_id",
        "scenario_version",
        "input_kinds",
        "source",
        "injected_failure",
        "expected_patch",
        "decisions",
        "statuses",
        "trace",
    }
    with pytest.raises(ValidationError):
        scenario.source = "changed"
    with pytest.raises(ValidationError):
        scenario.trace = DemoTraceV1(scenario_id="x", steps=())
    with pytest.raises(ValidationError):
        scenario.statuses = ("DEMO_FAILED",)


def test_fixed_scenario_serialization_is_deterministic() -> None:
    scenario = FIXED_DEMO_SCENARIO_V1
    first = scenario.to_canonical_bytes()
    round_tripped = DemoScenarioV1.model_validate(scenario.model_dump())
    assert round_tripped == scenario
    assert round_tripped.to_canonical_bytes() == first
    assert scenario.model_dump() == round_tripped.model_dump()


def test_fixed_scenario_contains_no_formal_identity_or_capability_data() -> None:
    scenario = FIXED_DEMO_SCENARIO_V1
    assert scenario.input_kinds == ("FIXED_SOURCE", "FIXED_FAILURE", "FIXED_PATCH")
    for decision in scenario.decisions:
        assert decision.decision in ("APPROVE", "REJECT")
    for step in scenario.trace.steps:
        assert step.status in (
            "DEMO_CREATED",
            "DEMO_RUNNING",
            "DEMO_WAITING_USER",
            "DEMO_COMPLETED",
            "DEMO_FAILED",
        )
        assert step.outcome in ("DENIED", "CHECK_FAILED", "REJECTED", "COMPLETED")
        if step.decision.kind == "PRESENT":
            assert step.decision.value.decision in ("APPROVE", "REJECT")


def test_demo_session_never_accepts_formal_identity_and_round_trips() -> None:
    session = DemoSessionV1(
        demo_session_id="demo-session-v1",
        scenario_version=1,
        status="DEMO_RUNNING",
        state_digest=DigestV1(value=_FIXED_DIGEST),
        expires_at=CanonicalTimestampV1("2026-08-05T09:30:15.000Z"),
    )
    assert DemoSessionV1.model_validate(session.model_dump()) == session
    with pytest.raises(DemoTypeIsolationError):
        DemoSessionV1(run_id=RunIdV1("formal-run"))
    with pytest.raises(DemoTypeIsolationError):
        DemoSessionV1.model_validate(
            {**session.model_dump(), "run_id": RunIdV1("formal-run")}
        )
    with pytest.raises(ValidationError):
        session.status = "DEMO_COMPLETED"
