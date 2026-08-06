"""T32.1 legacy step 32.C: shared-core provenance and real-call zero-side-effect
tests.

The exact displayed RED test ``test_formal_and_demo_execute_same_core_implementations``
is copied from the T32.1 card.  The already-RED matrix test
``test_mechanism_shared_core_matrix`` pins the PLAN 32.C row: formal and
demo use identical core implementation identities; only the formal path
may pass the real-call gate; presentation/capability/report differ only
at declared adapters; repeated traces are stable.
"""

from __future__ import annotations

from typing import Callable, Final, Literal

import pytest

pytest.importorskip("pydantic")

from src.vespercode.canonical.clock import FakeClockV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.credentials.service import CredentialService
from src.vespercode.demo.runner import DemoScenarioRunner
from src.vespercode.demo.types import DemoSessionV1
from src.vespercode.execution.docker_executor import DockerExecutor
from src.vespercode.llm.mock_adapter import MockLLMAdapter
from src.vespercode.llm.openai_adapter import OpenAILLMAdapter
from src.vespercode.governance.policy import PolicyEngine
from src.vespercode.loop.action_binding import bind_action
from src.vespercode.loop.action_parser import ActionParser
from src.vespercode.loop.action_pipeline import ActionPipeline
from src.vespercode.loop.feedback import build_feedback, select_feedback
from src.vespercode.loop.feedback_consumption import consume_feedback
from src.vespercode.loop.stopping import StopEvaluator
from src.vespercode.storage.run_repository import RunRepository
from src.vespercode.tools.dispatcher import ToolDispatcher

import scripts.run_mechanism_demo as _mechanism
import src.vespercode.demo.runner as _demo_runner
import src.vespercode.governance.policy as _policy
import src.vespercode.loop.action_pipeline as _action_pipeline
import src.vespercode.loop.feedback as _feedback
import src.vespercode.loop.feedback_consumption as _feedback_consumption
import src.vespercode.loop.stopping as _stopping
import src.vespercode.tools.dispatcher as _dispatcher
from scripts.run_mechanism_demo import MechanismHarness

_CLOCK_EPOCH = CanonicalTimestampV1("2026-08-07T09:00:00.000Z").epoch_milliseconds

_FORMAL_ADAPTER_PROBES: Final = (
    RunRepository,
    CredentialService,
    MockLLMAdapter,
    OpenAILLMAdapter,
    DockerExecutor,
)

_EXPECTED_SHARED_PURE_IMPLEMENTATIONS: Final = (
    _action_pipeline.ActionPipeline.execute,
    ActionParser.parse,
    bind_action,
    _policy.PolicyEngine.evaluate,
    _dispatcher.ToolDispatcher.dispatch,
    _feedback.build_feedback,
    _feedback.select_feedback,
    _feedback_consumption.consume_feedback,
    _stopping.StopEvaluator.evaluate,
)


class SharedCoreSpies:
    """Recording spies over the exact shared pure-core stages.

    ``formal_shared_pure_implementations`` and
    ``demo_shared_pure_implementations`` are the ordered FIRST-call
    call-site identities of the nine declared stages for the formal
    harness and the Demo runner respectively — the same objects the
    card's exact RED reads through the patched production attributes —
    and ``formal_delegated_implementations`` /
    ``demo_delegated_implementations`` are the real production callables
    every wrapper delegates to (identity, never a label; the matrix
    pins these against the import-time constants).
    ``demo_formal_capability_calls`` counts every formal capability
    adapter construction that happens while the demo side records.
    Every wrapper delegates to the real production function, so the
    composed pipeline behaves exactly as in production.
    """

    def __init__(self) -> None:
        self._formal_calls: list[object] = []
        self._demo_calls: list[object] = []
        self._formal_delegated: list[object] = []
        self._demo_delegated: list[object] = []
        self._formal_seen: set[str] = set()
        self._demo_seen: set[str] = set()
        self._formal_capability_calls: list[str] = []
        self._recording: Literal["formal", "demo"] = "formal"

    @property
    def formal_shared_pure_implementations(self) -> tuple[object, ...]:
        return tuple(self._formal_calls)

    @property
    def demo_shared_pure_implementations(self) -> tuple[object, ...]:
        return tuple(self._demo_calls)

    @property
    def formal_delegated_implementations(self) -> tuple[object, ...]:
        return tuple(self._formal_delegated)

    @property
    def demo_delegated_implementations(self) -> tuple[object, ...]:
        return tuple(self._demo_delegated)

    @property
    def demo_formal_capability_calls(self) -> int:
        return len(self._formal_capability_calls)

    def record_formal(self) -> None:
        self._recording = "formal"

    def record_demo(self) -> None:
        self._recording = "demo"

    def reset(self) -> None:
        self._formal_calls.clear()
        self._demo_calls.clear()
        self._formal_delegated.clear()
        self._demo_delegated.clear()
        self._formal_seen.clear()
        self._demo_seen.clear()
        self._formal_capability_calls.clear()
        self._recording = "formal"

    def reset_demo(self) -> None:
        self._demo_calls.clear()
        self._demo_delegated.clear()
        self._demo_seen.clear()

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Wrap every shared pure-core call site and the formal
        capability adapter constructors with recording delegates.

        Every call site of one stage receives the SAME wrapper object,
        and the wrapper records the identity the card's exact RED reads
        for that stage at assert time: the patched class attribute (the
        wrapper itself) for the class-method stages, and the original
        production callable (the import-time module value the RED's bare
        names hold) for the module-function stages — plus the original
        in the delegated list, and always delegates to the real
        implementation.  The constructor wrappers count only the
        constructions that happen while the demo side records, and also
        delegate to the real ``__init__`` so real wiring (the formal
        harness's adapters) keeps working.
        """
        # (stage name) -> ((sites), record_self) where record_self marks
        # the class-method stages whose patched attribute the RED reads.
        sites: dict[str, tuple[tuple[tuple[object, str], ...], bool]] = {
            "ActionPipeline.execute": (
                ((_action_pipeline.ActionPipeline, "execute"),),
                True,
            ),
            "ActionParser.parse": (((ActionParser, "parse"),), True),
            "bind_action": (((_action_pipeline, "bind_action"),), False),
            "PolicyEngine.evaluate": (((_policy.PolicyEngine, "evaluate"),), True),
            "ToolDispatcher.dispatch": (
                ((_dispatcher.ToolDispatcher, "dispatch"),),
                True,
            ),
            "build_feedback": (
                (
                    (_action_pipeline, "build_feedback"),
                    (_feedback, "build_feedback"),
                    (_demo_runner, "build_feedback"),
                    (_mechanism, "build_feedback"),
                ),
                False,
            ),
            "select_feedback": (
                (
                    (_feedback, "select_feedback"),
                    (_demo_runner, "select_feedback"),
                    (_mechanism, "select_feedback"),
                ),
                False,
            ),
            "consume_feedback": (
                (
                    (_action_pipeline, "consume_feedback"),
                    (_feedback_consumption, "consume_feedback"),
                    (_demo_runner, "consume_feedback"),
                    (_mechanism, "consume_feedback"),
                ),
                False,
            ),
            "StopEvaluator.evaluate": (((_stopping.StopEvaluator, "evaluate"),), True),
        }
        for name, (site_list, record_self) in sites.items():
            # Every site of one stage holds the same production callable
            # (the imports alias one object), so one wrapper suffices;
            # the factory keeps one closure cell per stage, so the
            # wrapper records ITSELF (never the last stage's wrapper).
            original = getattr(site_list[0][0], site_list[0][1])
            wrapper = self._make_stage_wrapper(name, original, record_self)
            for target, attribute in site_list:
                monkeypatch.setattr(target, attribute, wrapper)
        for cls in _FORMAL_ADAPTER_PROBES:
            original_init = cls.__init__
            name = cls.__name__

            def _counting_init(
                self_obj: object,
                *args: object,
                _spies: SharedCoreSpies = self,
                _name: str = name,
                _original: Callable[..., object] = original_init,
                **kwargs: object,
            ) -> None:
                if _spies._recording == "demo":
                    _spies._formal_capability_calls.append(_name)
                _original(self_obj, *args, **kwargs)

            monkeypatch.setattr(cls, "__init__", _counting_init)

    def _make_stage_wrapper(
        self,
        name: str,
        original: Callable[..., object],
        record_self: bool,
    ) -> Callable[..., object]:
        """One recording wrapper for one stage (fresh closure cells)."""

        def _recording(
            *args: object,
            _original: Callable[..., object] = original,
            _spies: SharedCoreSpies = self,
            _name: str = name,
            _record_self: bool = record_self,
            **kwargs: object,
        ) -> object:
            identity = _recording if _record_self else _original
            if _spies._recording == "formal":
                if _name not in _spies._formal_seen:
                    _spies._formal_seen.add(_name)
                    _spies._formal_calls.append(identity)
                    _spies._formal_delegated.append(_original)
            else:
                if _name not in _spies._demo_seen:
                    _spies._demo_seen.add(_name)
                    _spies._demo_calls.append(identity)
                    _spies._demo_delegated.append(_original)
            return _original(*args, **kwargs)

        return _recording


# The card's exact RED calls ``new_demo_session()`` as a plain function
# (it is not a fixture parameter), so the module registers the current
# per-test runner and spies here (T30.2 precedent: the fixture-time
# position-at-step-2 interpretation, resolved to a plain callable).
_current_demo_runner: DemoScenarioRunner | None = None
_current_spies: SharedCoreSpies | None = None
_session_counter = 0


@pytest.fixture
def shared_core_spies(monkeypatch: pytest.MonkeyPatch) -> SharedCoreSpies:
    global _current_spies
    spies = SharedCoreSpies()
    spies.install(monkeypatch)
    spies.record_formal()
    _current_spies = spies
    return spies


@pytest.fixture
def formal_harness() -> MechanismHarness:
    return MechanismHarness()


@pytest.fixture
def demo_runner() -> DemoScenarioRunner:
    global _current_demo_runner
    runner = DemoScenarioRunner(clock=FakeClockV1(_CLOCK_EPOCH))
    _current_demo_runner = runner
    return runner


def new_demo_session() -> DemoSessionV1:
    """One fresh Demo session positioned at step 2 (the fixed src
    patch): the two preceding DENY steps are advanced during setup, then
    the demo spy log is cleared so the test observes exactly the next
    advance (the T30.2 demo_session precedent; a fresh session's first
    advance is a policy DENY that cannot dispatch, and the card's
    asserted tuple requires an ALLOWed dispatched step)."""
    global _session_counter
    runner = _current_demo_runner
    spies = _current_spies
    assert runner is not None
    assert spies is not None
    spies.record_demo()
    _session_counter += 1
    session_id = f"shared-core-demo-{_session_counter}"
    session = runner.create_session(session_id)
    for _ in range(2):
        runner.advance(session, None)
        session = runner.session(session_id)
    spies.reset_demo()
    return session


def test_formal_and_demo_execute_same_core_implementations(
    formal_harness: MechanismHarness,
    demo_runner: DemoScenarioRunner,
    shared_core_spies: SharedCoreSpies,
) -> None:
    formal_harness.run_step("feedback-correction")
    demo_runner.advance(new_demo_session(), decision=None)
    assert shared_core_spies.formal_shared_pure_implementations == (
        ActionPipeline.execute,
        ActionParser.parse,
        bind_action,
        PolicyEngine.evaluate,
        ToolDispatcher.dispatch,
        build_feedback,
        select_feedback,
        consume_feedback,
        StopEvaluator.evaluate,
    )
    assert (
        shared_core_spies.demo_shared_pure_implementations
        == shared_core_spies.formal_shared_pure_implementations
    )
    assert shared_core_spies.demo_formal_capability_calls == 0


def test_mechanism_shared_core_matrix(
    formal_harness: MechanismHarness,
    demo_runner: DemoScenarioRunner,
    shared_core_spies: SharedCoreSpies,
) -> None:
    """PLAN 32.C row: formal and demo use identical core implementation
    identities; only the formal path may pass the real-call gate;
    presentation/capability/report differ only at declared adapters;
    repeated traces are stable.
    """
    formal_harness.run_step("feedback-correction")
    demo_runner.advance(new_demo_session(), decision=None)
    # Identical core implementation identities: both paths invoke the
    # same nine call-site identities in the same first-call order, and
    # every wrapper delegates to the exact declared pure-core
    # implementations (the import-time constants, never a label).
    assert shared_core_spies.formal_shared_pure_implementations == (
        shared_core_spies.demo_shared_pure_implementations
    )
    assert shared_core_spies.formal_delegated_implementations == (
        _EXPECTED_SHARED_PURE_IMPLEMENTATIONS
    )
    assert shared_core_spies.demo_delegated_implementations == (
        _EXPECTED_SHARED_PURE_IMPLEMENTATIONS
    )
    # Only the formal path may pass the real-call gate: the demo path
    # never constructs or calls a formal capability adapter, while the
    # formal harness's failing real-call probes keep every counter zero
    # and the authorized probe performs exactly one transport through
    # the declared counting stub (zero real network).
    assert shared_core_spies.demo_formal_capability_calls == 0
    shared_core_spies.record_formal()
    real_call = MechanismHarness().run_step("real-call-gate")
    by_id = {probe.probe_id: probe for probe in real_call.real_call_probes}
    for probe_id in (
        "missing-disclosure",
        "grant-expired",
        "scope-exceeded",
        "credential-missing",
        "credential-backend-unsafe",
    ):
        probe = by_id[probe_id]
        assert probe.gate_error_code is not None
        assert (
            probe.authorization_record_count
            == probe.turn_count
            == probe.call_count
            == probe.charge_bytes
            == probe.transport_count
            == probe.network_count
            == 0
        )
    authorized = by_id["authorized"]
    assert authorized.gate_error_code is None
    assert authorized.authorization_record_count == 1
    assert authorized.turn_count == 1
    assert authorized.call_count == 1
    assert authorized.charge_bytes > 0
    assert authorized.transport_count == 1
    assert authorized.network_count == 0
    # Presentation/capability/report differ only at declared adapters:
    # the demo trace carries the DEMO_EXECUTOR capability and zero
    # formal-capability calls, and the formal report carries the real-call
    # gate probes; both compose the same shared core stage sequence.
    demo_result = demo_runner.advance(
        demo_runner.create_session("capability-session"), None
    )
    assert demo_result.executor_kind == "DEMO_EXECUTOR"
    assert demo_result.formal_capability_calls == 0
    formal_result = MechanismHarness().run()
    # The fixed stage sequence is exact (quality-review M6 pin).
    assert [stage.step_id for stage in formal_result.trace.stages] == [
        "readme-read",
        "readme-modify",
        "outside-scope-create",
        "src-patch",
        "protected-tests-patch",
        "protected-config-patch",
        "feedback-correction",
        "final-approval-no-write",
        "paged-continuation",
        "real-call-gate",
    ]
    # Repeated traces are stable: the fixed mechanism and Demo traces
    # are byte-identical across fresh runs.
    repeated = MechanismHarness().run()
    assert repeated.trace.stages == formal_result.trace.stages
    second_demo = demo_runner.advance(
        demo_runner.create_session("capability-session-2"), None
    )
    assert (
        second_demo.step.to_canonical_bytes() == demo_result.step.to_canonical_bytes()
    )
