"""T30.1 legacy step 30.A: Demo-only immutable type tests.

The exact displayed RED test ``test_fixed_scenario_rejects_formal_identity_types``
is copied verbatim from the T30.1 card; the ``fixed_demo_scenario`` fixture and
the already-RED matrix test ``test_demo_type_serialization_matrix`` complete the
card's declared Test file.  The matrix pins the PLAN 30.A row: only fixed demo
scenario ids/data and closed demo variants serialize; formal identities,
arbitrary body, unknown variant, nondeterministic field, or extra field is
rejected.  Executor, shared-core sequencing, session storage, Web behavior,
local files, credentials, Docker, recovery, persistence, and real providers
remain out of scope (GREEN-4).
"""

from __future__ import annotations

# The card's exact RED test and the matrix's formal-identity probes must pass
# undeclared keywords (``run_id=...`` etc.) that the pydantic runtime must
# reject; mypy's dataclass-transform signature would otherwise refuse those
# intentional probes, so the call-arg code is disabled for this test module.
# mypy: disable-error-code="call-arg"

import pytest

# The Demo models are pydantic runtime contracts; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from src.vespercode.canonical.digest import domain_digest
from src.vespercode.canonical.json_v1 import canonical_json_bytes
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.evidence import DigestV1
from src.vespercode.contracts.optional import AbsentV1
from src.vespercode.demo.scenario import FIXED_DEMO_SCENARIO_V1
from src.vespercode.demo.types import (
    DemoDecisionV1,
    DemoScenarioV1,
    DemoSessionV1,
    DemoStepResultV1,
    DemoTraceV1,
    DemoTypeIsolationError,
    RepositoryIdentityV1,
    RunIdV1,
    TurnIdV1,
)

_FIXED_DIGEST = "ab" * 32
_FIXED_TS = CanonicalTimestampV1("2026-08-05T09:30:15.000Z")
_SCENARIO_DIGEST = "4979ba30b988024b8101b57873b87092219e5515daafe3ab30d2e4b70afc1f54"


@pytest.fixture
def fixed_demo_scenario() -> DemoScenarioV1:
    return FIXED_DEMO_SCENARIO_V1


def test_fixed_scenario_rejects_formal_identity_types(
    fixed_demo_scenario: DemoScenarioV1,
) -> None:
    assert fixed_demo_scenario.input_kinds == (
        "FIXED_SOURCE",
        "FIXED_FAILURE",
        "FIXED_PATCH",
    )
    with pytest.raises(DemoTypeIsolationError):
        DemoSessionV1(run_id=RunIdV1("formal-run"))


def test_demo_type_serialization_matrix() -> None:
    """PLAN 30.A matrix row: only fixed demo ids/data and closed demo variants
    serialize; formal identities, arbitrary body, unknown variant,
    nondeterministic field, or extra field is rejected.
    """
    scenario = FIXED_DEMO_SCENARIO_V1

    # Fixed scenario ids/data serialize to one deterministic canonical form:
    # byte-identical across separate constructions and dump round-trips, and
    # equal to the §0.1 canonical encoder over the dumped fields.
    first = scenario.to_canonical_bytes()
    second = DemoScenarioV1.model_validate(scenario.model_dump()).to_canonical_bytes()
    assert first == second
    assert first == canonical_json_bytes(scenario.model_dump())

    # Every closed demo variant serializes deterministically.
    session = DemoSessionV1(
        demo_session_id="demo-session-v1",
        scenario_version=1,
        status="DEMO_RUNNING",
        state_digest=DigestV1(value=_FIXED_DIGEST),
        expires_at=_FIXED_TS,
    )
    reject_decision = DemoDecisionV1(
        demo_session_id="demo-session-v1",
        subject_digest=DigestV1(value=_FIXED_DIGEST),
        decision="REJECT",
        created_at=_FIXED_TS,
    )
    step = DemoStepResultV1(
        step_index=0,
        action_label="PATCH docs/outside-scope.md",
        outcome="DENIED",
        status="DEMO_RUNNING",
        decision=AbsentV1(kind="ABSENT"),
    )
    trace = DemoTraceV1(scenario_id="mock-demo-v1", steps=(step,))
    for value in (session, reject_decision, step, trace):
        assert value.to_canonical_bytes() == canonical_json_bytes(value.model_dump())

    # The fixed scenario canonical form is pinned by its §0.1 binding digest.
    assert domain_digest("DemoScenarioV1", 1, scenario.model_dump()) == _SCENARIO_DIGEST

    # Formal Run/turn/repository identities are rejected with the closed
    # DemoTypeIsolationError, never validated into any demo field.
    for identity in (RunIdV1("r"), TurnIdV1("t"), RepositoryIdentityV1("repo")):
        with pytest.raises(DemoTypeIsolationError):
            DemoSessionV1(demo_session_id=identity)  # type: ignore[arg-type]
        with pytest.raises(DemoTypeIsolationError):
            DemoSessionV1(run_id=identity)
        with pytest.raises(DemoTypeIsolationError):
            DemoSessionV1(turn_id=identity)
        with pytest.raises(DemoTypeIsolationError):
            DemoSessionV1(repository=identity)
    with pytest.raises(DemoTypeIsolationError):
        DemoDecisionV1(subject_digest=RunIdV1("r"))  # type: ignore[arg-type]
    # Identities nested inside containers never enter a field either: the
    # strict closed field types reject them before validation completes.
    with pytest.raises(ValidationError):
        DemoDecisionV1.model_validate(
            {
                "demo_session_id": "s",
                "subject_digest": {"value": RunIdV1("x")},
                "decision": "REJECT",
                "created_at": _FIXED_TS,
            }
        )

    # Arbitrary body and unknown variants are rejected deterministically.
    with pytest.raises(ValidationError):
        DemoSessionV1.model_validate(
            {"demo_session_id": 1, "scenario_version": 1, "status": "DEMO_RUNNING"}
        )
    with pytest.raises(ValidationError):
        DemoSessionV1.model_validate(
            {"demo_session_id": "s", "scenario_version": 1, "status": "DEMO_PAUSED"}
        )
    with pytest.raises(ValidationError):
        DemoDecisionV1.model_validate(
            {
                "demo_session_id": "s",
                "subject_digest": {"value": _FIXED_DIGEST},
                "decision": "SKIP",
                "created_at": _FIXED_TS,
            }
        )
    with pytest.raises(ValidationError):
        DemoStepResultV1.model_validate(
            {
                "step_index": 0,
                "action_label": "x",
                "outcome": "FAILED",
                "status": "DEMO_RUNNING",
                "decision": {"kind": "ABSENT"},
            }
        )
    with pytest.raises(ValidationError):
        DemoScenarioV1.model_validate(
            {
                **scenario.model_dump(),
                "input_kinds": ("FORMAL_SOURCE", "FIXED_FAILURE", "FIXED_PATCH"),
            }
        )
    with pytest.raises(ValidationError):
        DemoScenarioV1.model_validate(
            {**scenario.model_dump(), "prompt": "prompt the model"}
        )
    with pytest.raises(ValidationError):
        DemoSessionV1.model_validate(session.model_dump() | {"run_id": "formal-run"})
    with pytest.raises(ValidationError):
        DemoSessionV1.model_validate(session.model_dump() | {"extra": 1})
    with pytest.raises(ValidationError):
        DemoDecisionV1.model_validate(
            reject_decision.model_dump() | {"provider": "openai"}
        )
    with pytest.raises(ValidationError):
        DemoScenarioV1.model_validate(
            {**scenario.model_dump(), "secret": "sk-super-secret"}
        )

    # No nondeterministic field: identical inputs give byte-identical
    # canonical output, and the fixed data carries no live clock or random id.
    assert DemoDecisionV1(
        demo_session_id="demo-session-v1",
        subject_digest=DigestV1(value=_FIXED_DIGEST),
        decision="APPROVE",
        created_at=CanonicalTimestampV1("2026-08-05T09:30:20.000Z"),
    ).to_canonical_bytes() == canonical_json_bytes(
        {
            "demo_session_id": "demo-session-v1",
            "subject_digest": {"value": _FIXED_DIGEST},
            "decision": "APPROVE",
            "created_at": {"value": "2026-08-05T09:30:20.000Z"},
        }
    )
