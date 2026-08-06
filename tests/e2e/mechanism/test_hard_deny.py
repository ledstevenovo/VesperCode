"""T32.1 legacy step 32.A: hard-DENY mechanism trace tests.

The exact displayed RED test ``test_outside_scope_patch_is_denied_before_dispatch_or_publish``
is copied from the T32.1 card.  The already-RED matrix test
``test_mechanism_hard_deny_matrix`` pins the PLAN 32.A row: an
outside-scope/protected-artifact action is denied before
dispatch/publish/approval, the report records the bounded reason, and a
repeated run has the same trace and zero workspace mutation.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

from scripts.run_mechanism_demo import (
    MechanismDemoConfigV1,
    MechanismHarness,
)


@pytest.fixture
def mechanism_harness() -> MechanismHarness:
    return MechanismHarness()


def test_outside_scope_patch_is_denied_before_dispatch_or_publish(
    mechanism_harness: MechanismHarness,
) -> None:
    trace = mechanism_harness.run_step("outside-scope-create")
    assert trace.error_code == "PATCH_PATH_NOT_EDITABLE"
    assert trace.dispatch_count == trace.candidate_publish_count == 0


def test_mechanism_run_is_once_only_per_harness(
    mechanism_harness: MechanismHarness,
) -> None:
    """One mechanism run is once-only per harness (the production
    feedback replay semantics make a second run on the same harness a
    different, not a repeated, trace); a config mismatch is a closed
    rejection (quality-review M5 pin)."""
    mechanism_harness.run()
    with pytest.raises(ValueError, match="once-only"):
        mechanism_harness.run()
    with pytest.raises(ValueError, match="must match the harness config"):
        mechanism_harness.run(
            MechanismDemoConfigV1(
                schema_version=1,
                scenario_id="mock-demo-v1",
                run_id="another-run",
                clock_epoch="2026-08-07T09:00:00.000Z",
            )
        )


def test_mechanism_hard_deny_matrix(
    mechanism_harness: MechanismHarness,
) -> None:
    """PLAN 32.A row: outside-scope/protected-artifact action is denied
    before dispatch/publish/approval; report records bounded reason;
    repeated run has same trace and zero workspace mutation.
    """
    outside = mechanism_harness.run_step("outside-scope-create")
    assert outside.error_code == "PATCH_PATH_NOT_EDITABLE"
    assert (
        outside.dispatch_count
        == outside.candidate_publish_count
        == outside.approval_consumption_count
        == outside.workspace_write_count
        == 0
    )
    readme = mechanism_harness.run_step("readme-modify")
    assert readme.error_code == "PATCH_PATH_NOT_EDITABLE"
    assert (
        readme.dispatch_count
        == readme.candidate_publish_count
        == readme.approval_consumption_count
        == readme.workspace_write_count
        == 0
    )
    protected = mechanism_harness.run_step("protected-tests-patch")
    assert protected.error_code == "PROTECTED_ARTIFACT_CHANGED"
    assert (
        protected.dispatch_count
        == protected.candidate_publish_count
        == protected.approval_consumption_count
        == protected.check_invocation_count
        == protected.formal_validation_count
        == protected.workspace_write_count
        == 0
    )
    # The report records the bounded reason: the full trace serializes
    # into the closed bounded report and binds the denied steps' codes.
    first = MechanismHarness().run()
    denied_by_id = {stage.step_id: stage for stage in first.trace.stages}
    assert denied_by_id["outside-scope-create"].error_code == (
        "PATCH_PATH_NOT_EDITABLE"
    )
    assert denied_by_id["readme-modify"].error_code == "PATCH_PATH_NOT_EDITABLE"
    assert denied_by_id["protected-tests-patch"].error_code == (
        "PROTECTED_ARTIFACT_CHANGED"
    )
    assert first.trace.stages[0].step_id == "readme-read"
    assert first.trace.digest == first.trace.trace_id
    # A repeated run (fresh harness, the once-only run contract) has the
    # same trace and zero workspace mutation.
    repeated = MechanismHarness().run()
    assert repeated.trace.stages == first.trace.stages
    assert repeated.report_text == first.report_text
    assert all(stage.workspace_write_count == 0 for stage in repeated.trace.stages)
