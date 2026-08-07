"""T30.1 legacy step 30.A: the sole frozen Mock Demo scenario.

``FIXED_DEMO_SCENARIO_V1`` is the exact fixed scenario data (card GREEN-2):
its source, injected failure, expected patch, visitor decisions, statuses,
and canonical trace are frozen literals with no live clock, random id,
prompt, URL, upload, provider, secret, filesystem, Docker, persistence, or
recovery input.  The scenario only stores immutable fixed data; this module
imports no formal Run/turn/repository identity, executor, adapter, session
store, Web, disk, credential, Docker, recovery, or persistence capability
(GREEN-4 boundary).  Demo execution, shared-core sequencing, session
storage, and Web behavior remain out of scope (GREEN-4).
"""

from __future__ import annotations

from typing import Final

from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import DigestV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.demo.types import (
    DemoDecisionV1,
    DemoScenarioV1,
    DemoStepResultV1,
    DemoTraceV1,
)

_FIXED_DIGEST: Final = "ab" * 32
_FIXED_SESSION_ID: Final = "demo-session-v1"
_FIXED_SCENARIO_ID: Final = "mock-demo-v1"

_REJECT_DECISION: Final = DemoDecisionV1(
    demo_session_id=_FIXED_SESSION_ID,
    subject_digest=DigestV1(value=_FIXED_DIGEST),
    decision="REJECT",
    created_at=CanonicalTimestampV1("2026-08-05T09:30:15.000Z"),
)
_APPROVE_DECISION: Final = DemoDecisionV1(
    demo_session_id=_FIXED_SESSION_ID,
    subject_digest=DigestV1(value=_FIXED_DIGEST),
    decision="APPROVE",
    created_at=CanonicalTimestampV1("2026-08-05T09:30:20.000Z"),
)

FIXED_DEMO_SCENARIO_V1: Final = DemoScenarioV1(
    scenario_id=_FIXED_SCENARIO_ID,
    scenario_version=1,
    input_kinds=("FIXED_SOURCE", "FIXED_FAILURE", "FIXED_PATCH"),
    source=(
        "README.md\n"
        "VesperCode Mock Demo\n"
        "\n"
        "Fix the failing test in tests/test_example.py."
    ),
    injected_failure="tests/test_example.py::test_example_success",
    expected_patch=(
        "--- a/src/example.py\n"
        "+++ b/src/example.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def example():\n"
        "-    return 0\n"
        "+    return 1\n"
    ),
    decisions=(_REJECT_DECISION, _APPROVE_DECISION),
    statuses=("DEMO_CREATED", "DEMO_RUNNING", "DEMO_WAITING_USER", "DEMO_COMPLETED"),
    trace=DemoTraceV1(
        scenario_id=_FIXED_SCENARIO_ID,
        steps=(
            DemoStepResultV1(
                step_index=0,
                action_label="PATCH docs/outside-scope.md",
                outcome="DENIED",
                status="DEMO_RUNNING",
                decision=AbsentV1(kind="ABSENT"),
            ),
            DemoStepResultV1(
                step_index=1,
                action_label="PATCH README.md",
                outcome="DENIED",
                status="DEMO_RUNNING",
                decision=AbsentV1(kind="ABSENT"),
            ),
            DemoStepResultV1(
                step_index=2,
                action_label="PATCH src/example.py",
                outcome="CHECK_FAILED",
                status="DEMO_RUNNING",
                decision=AbsentV1(kind="ABSENT"),
            ),
            DemoStepResultV1(
                step_index=3,
                action_label="PATCH tests/test_example.py",
                outcome="DENIED",
                status="DEMO_RUNNING",
                decision=AbsentV1(kind="ABSENT"),
            ),
            DemoStepResultV1(
                step_index=4,
                action_label="FINAL_WRITEBACK",
                outcome="REJECTED",
                status="DEMO_WAITING_USER",
                decision=PresentV1(kind="PRESENT", value=_REJECT_DECISION),
            ),
            DemoStepResultV1(
                step_index=5,
                action_label="FINAL_WRITEBACK",
                outcome="COMPLETED",
                status="DEMO_COMPLETED",
                decision=PresentV1(kind="PRESENT", value=_APPROVE_DECISION),
            ),
        ),
    ),
)
