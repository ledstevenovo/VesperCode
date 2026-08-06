"""T30.2 legacy step 30.D: shared-core Demo runner composition tests.

The exact displayed RED test ``test_demo_step_invokes_shared_core_and_only_demo_tool_ports``
is copied from the T30.2 card.  The ``demo_session`` fixture positions the
session at step 2 (the fixed ``src/example.py`` patch) so the first
advance dispatches an ALLOWed action and observes the full shared-core
provenance — the two preceding DENY steps cannot dispatch (policy DENY
short-circuits before the dispatcher, SPEC §4.2.5/§10.4), so a fresh
session could never produce the card's asserted tuple.  The already-RED
matrix test ``test_demo_shared_core_trace_matrix`` pins the PLAN 30.D
row: shared-call provenance, fixed repeated trace, limit/expiry/reset,
in-memory-only lifecycle, and zero formal-capability calls.
"""

from __future__ import annotations

from typing import Any, Final, Literal

import pytest

pytest.importorskip("pydantic")

from src.vespercode.canonical.clock import FakeClockV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.evidence import DigestV1
from src.vespercode.credentials.service import CredentialService
from src.vespercode.demo.runner import (
    DEMO_SHARED_CORE_MODULES_V1,
    DemoScenarioRunner,
)
from src.vespercode.demo.scenario import FIXED_DEMO_SCENARIO_V1
from src.vespercode.demo.types import (
    DemoDecisionV1,
    DemoSessionV1,
)
from src.vespercode.execution.docker_executor import DockerExecutor
from src.vespercode.llm.mock_adapter import MockLLMAdapter
from src.vespercode.llm.openai_adapter import OpenAILLMAdapter
from src.vespercode.storage.run_repository import RunRepository

import src.vespercode.demo.runner as _demo_runner
import src.vespercode.governance.policy as _policy
import src.vespercode.loop.action_pipeline as _action_pipeline
from src.vespercode.loop.action_parser import ActionParser
import src.vespercode.loop.feedback as _feedback
import src.vespercode.loop.feedback_consumption as _feedback_consumption
import src.vespercode.loop.stopping as _stopping
import src.vespercode.tools.dispatcher as _dispatcher

_CLOCK_EPOCH = CanonicalTimestampV1("2026-08-06T09:00:00.000Z").epoch_milliseconds
_FIXED_DIGEST: Final = "ab" * 32
_FIXED_DECISION_TS = CanonicalTimestampV1("2026-08-05T09:30:15.000Z")

_STAGE_NAMES_V1: Final = (
    "ActionPipeline.execute",
    "ActionParser.parse",
    "bind_action",
    "PolicyEngine.evaluate",
    "ToolDispatcher.dispatch",
    "build_feedback",
    "select_feedback",
    "consume_feedback",
    "StopEvaluator.evaluate",
)
"""The closed shared-core stage names of the card's exact RED tuple."""

_FORMAL_ADAPTER_PROBES: Final = (
    RunRepository,
    CredentialService,
    MockLLMAdapter,
    OpenAILLMAdapter,
    DockerExecutor,
)


class SharedCoreSpies:
    """Recording spies over the exact shared pure-core stages.

    ``calls`` is the ordered FIRST-call sequence of the nine declared
    stages (a stage name is recorded once, so the shared dispatcher's own
    policy re-evaluation and the runner's direct feedback calls cannot
    duplicate an entry); ``formal_capability_calls`` counts every formal
    capability adapter construction.  Every wrapper delegates to the real
    production function, so the composed pipeline behaves exactly as in
    production.
    """

    def __init__(self) -> None:
        self._calls: list[str] = []
        self._seen: set[str] = set()
        self._formal_calls: list[str] = []

    @property
    def calls(self) -> tuple[str, ...]:
        """The ordered first-call stage sequence (the card's exact RED
        reads ``shared_core_spies.calls == (...tuple...)``)."""
        return tuple(self._calls)

    @property
    def formal_capability_calls(self) -> int:
        return len(self._formal_calls)

    def reset(self) -> None:
        """Clear the recorded stages and formal-call count.

        The demo_session fixture advances the two DENY steps during setup
        and then resets, so the test observes exactly the next advance.
        """
        self._calls.clear()
        self._seen.clear()
        self._formal_calls.clear()

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The shared stages: the pipeline's own call sites (module globals
        # and constructed class methods) and the runner's direct call
        # sites, all delegating to the real implementations.
        self._patch(
            monkeypatch,
            _action_pipeline.ActionPipeline,
            "execute",
            "ActionPipeline.execute",
        )
        self._patch(monkeypatch, ActionParser, "parse", "ActionParser.parse")
        self._patch(monkeypatch, _action_pipeline, "bind_action", "bind_action")
        self._patch(
            monkeypatch, _policy.PolicyEngine, "evaluate", "PolicyEngine.evaluate"
        )
        self._patch(
            monkeypatch,
            _dispatcher.ToolDispatcher,
            "dispatch",
            "ToolDispatcher.dispatch",
        )
        self._patch(monkeypatch, _action_pipeline, "build_feedback", "build_feedback")
        self._patch(monkeypatch, _feedback, "build_feedback", "build_feedback")
        self._patch(monkeypatch, _demo_runner, "build_feedback", "build_feedback")
        self._patch(monkeypatch, _feedback, "select_feedback", "select_feedback")
        self._patch(monkeypatch, _demo_runner, "select_feedback", "select_feedback")
        self._patch(
            monkeypatch, _action_pipeline, "consume_feedback", "consume_feedback"
        )
        self._patch(
            monkeypatch, _feedback_consumption, "consume_feedback", "consume_feedback"
        )
        self._patch(monkeypatch, _demo_runner, "consume_feedback", "consume_feedback")
        self._patch(
            monkeypatch, _stopping.StopEvaluator, "evaluate", "StopEvaluator.evaluate"
        )
        # The formal capability adapters: count every construction.
        for cls in _FORMAL_ADAPTER_PROBES:
            name = cls.__name__

            def _counting_init(
                self: object,
                *args: Any,
                _spies: SharedCoreSpies = self,
                _name: str = name,
                **kwargs: Any,
            ) -> None:
                _spies._formal_calls.append(_name)

            monkeypatch.setattr(cls, "__init__", _counting_init)

    def _patch(
        self,
        monkeypatch: pytest.MonkeyPatch,
        target: Any,
        attribute: str,
        name: str,
    ) -> None:
        """Wrap one real production call site with a recording delegate.

        The original is captured before the patch so the spy always
        delegates to the real implementation.
        """
        original = getattr(target, attribute)

        def _recording(*args: Any, **kwargs: Any) -> Any:
            if name not in self._seen:
                self._seen.add(name)
                self._calls.append(name)
            return original(*args, **kwargs)

        monkeypatch.setattr(target, attribute, _recording)


@pytest.fixture
def shared_core_spies(
    monkeypatch: pytest.MonkeyPatch,
) -> SharedCoreSpies:
    spies = SharedCoreSpies()
    spies.install(monkeypatch)
    return spies


@pytest.fixture
def demo_runner(shared_core_spies: SharedCoreSpies) -> DemoScenarioRunner:
    return DemoScenarioRunner(clock=FakeClockV1(_CLOCK_EPOCH))


@pytest.fixture
def demo_session(
    demo_runner: DemoScenarioRunner,
    shared_core_spies: SharedCoreSpies,
) -> DemoSessionV1:
    """A session positioned at step 2 (the fixed ``src/example.py``
    patch): the two preceding DENY steps are advanced during setup, then
    the spy log is reset so the test observes exactly the next advance."""
    session = demo_runner.create_session("demo-session-v1")
    for _ in range(2):
        demo_runner.advance(session, None)
        session = demo_runner.session("demo-session-v1")
    shared_core_spies.reset()
    return session


def test_demo_step_invokes_shared_core_and_only_demo_tool_ports(
    shared_core_spies: SharedCoreSpies,
    demo_runner: DemoScenarioRunner,
    demo_session: DemoSessionV1,
) -> None:
    result = demo_runner.advance(demo_session, decision=None)
    assert shared_core_spies.calls == (
        "ActionPipeline.execute",
        "ActionParser.parse",
        "bind_action",
        "PolicyEngine.evaluate",
        "ToolDispatcher.dispatch",
        "build_feedback",
        "select_feedback",
        "consume_feedback",
        "StopEvaluator.evaluate",
    )
    assert result.executor_kind == "DEMO_EXECUTOR"
    assert shared_core_spies.formal_capability_calls == 0


def _decision(choice: Literal["APPROVE", "REJECT"]) -> DemoDecisionV1:
    return DemoDecisionV1(
        demo_session_id="demo-session-v1",
        subject_digest=DigestV1(value=_FIXED_DIGEST),
        decision=choice,
        created_at=_FIXED_DECISION_TS,
    )


def _run_full_scenario(
    runner: DemoScenarioRunner, session_id: str
) -> tuple[bytes, ...]:
    """Advance the whole fixed scenario and return the canonical trace."""
    session = runner.create_session(session_id)
    trace: list[bytes] = []
    for index in range(len(FIXED_DEMO_SCENARIO_V1.trace.steps)):
        decision = None
        if index == 4:
            decision = _decision("REJECT")
        elif index == 5:
            decision = _decision("APPROVE")
        result = runner.advance(session, decision)
        trace.append(result.step.to_canonical_bytes())
        if index < len(FIXED_DEMO_SCENARIO_V1.trace.steps) - 1:
            session = runner.session(session_id)
    return tuple(trace)


def test_demo_shared_core_trace_matrix(
    demo_runner: DemoScenarioRunner,
    shared_core_spies: SharedCoreSpies,
) -> None:
    """PLAN 30.D row: shared-call provenance, fixed repeated trace,
    limit/expiry/reset, in-memory-only lifecycle, and zero formal-capability
    calls pass.
    """
    shared_core_spies.reset()
    fixed = tuple(
        step.to_canonical_bytes() for step in FIXED_DEMO_SCENARIO_V1.trace.steps
    )
    first = _run_full_scenario(demo_runner, "trace-run-1")
    # Every emitted step equals the fixed scenario trace step.
    assert first == fixed
    # The repeated trace is byte-identical across a second full run.
    second = _run_full_scenario(demo_runner, "trace-run-2")
    assert second == first
    # Shared-call provenance over the whole run: every declared stage
    # fired, and the only ALLOWed step (the fixed src patch) is the only
    # dispatched step (policy DENY never reaches the dispatcher); the
    # stop evaluation runs at every step boundary (the card's exact RED
    # pins the per-step order).
    assert set(shared_core_spies.calls) == set(_STAGE_NAMES_V1)
    assert shared_core_spies.calls.count("ToolDispatcher.dispatch") == 1
    assert "StopEvaluator.evaluate" in shared_core_spies.calls
    # Zero formal-capability constructions/calls.
    assert shared_core_spies.formal_capability_calls == 0
    # In-memory-only lifecycle: the wiring holds only demo rows and no
    # formal Run row, and the fixed injected check failure was fed back
    # as structured feedback (SPEC §10.4 item 3).
    assert demo_runner.database.read_rows("SELECT COUNT(*) FROM runs")[0][0] == 0
    assert (
        demo_runner.database.read_rows("SELECT COUNT(*) FROM feedback_records")[0][0]
        >= 1
    )
    assert (
        demo_runner.database.read_rows("SELECT COUNT(*) FROM action_records")[0][0] >= 1
    )
    # The declared shared-core module constant is the exact card set.
    assert DEMO_SHARED_CORE_MODULES_V1 == frozenset(
        {
            "vespercode.governance.policy",
            "vespercode.loop.agent_actions",
            "vespercode.loop.action_parser",
            "vespercode.loop.action_binding",
            "vespercode.loop.context_projection",
            "vespercode.loop.feedback",
            "vespercode.loop.stopping",
            "vespercode.loop.action_pipeline",
            "vespercode.tools.dispatcher",
        }
    )


def test_demo_writeback_steps_require_the_fixed_visitor_decision(
    demo_runner: DemoScenarioRunner,
) -> None:
    """The FINAL_WRITEBACK steps advance only through the exact fixed
    visitor decisions (REJECT then APPROVE); a missing or wrong decision
    is a closed rejection and never creates a formal approval."""
    from src.vespercode.demo.runner import DemoAdvanceErrorV1

    session = demo_runner.create_session("writeback-run")
    for _ in range(4):
        demo_runner.advance(session, None)
        session = demo_runner.session("writeback-run")
    with pytest.raises(DemoAdvanceErrorV1) as missing:
        demo_runner.advance(session, None)
    assert missing.value.error_code == "DEMO_DECISION_REQUIRED"
    with pytest.raises(DemoAdvanceErrorV1) as wrong:
        demo_runner.advance(session, _decision("APPROVE"))
    assert wrong.value.error_code == "DEMO_DECISION_MISMATCH"
    rejected = demo_runner.advance(session, _decision("REJECT"))
    assert rejected.step.outcome == "REJECTED"
    assert rejected.step.status == "DEMO_WAITING_USER"
    session = demo_runner.session("writeback-run")
    completed = demo_runner.advance(session, _decision("APPROVE"))
    assert completed.step.outcome == "COMPLETED"
    assert completed.step.status == "DEMO_COMPLETED"
