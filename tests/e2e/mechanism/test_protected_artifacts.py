"""T32.1 legacy step 32.A: protected-artifact precedence mechanism tests.

A patch to a protected acceptance artifact — the fixed tests file or the
Ruff/Mypy configuration — is hard-denied with the stable
``PROTECTED_ARTIFACT_CHANGED`` code before dispatch, candidate publish,
check invocation, or formal validation (SPEC §10.4 item 4 / AC-04 / AC-31
protected-artifact precedence over the editable policy).
"""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

from scripts.run_mechanism_demo import MechanismHarness


@pytest.fixture
def mechanism_harness() -> MechanismHarness:
    return MechanismHarness()


def test_protected_tests_patch_cannot_enter_check_or_formal_validation(
    mechanism_harness: MechanismHarness,
) -> None:
    trace = mechanism_harness.run_step("protected-tests-patch")
    assert trace.error_code == "PROTECTED_ARTIFACT_CHANGED"
    assert (
        trace.dispatch_count
        == trace.candidate_publish_count
        == trace.check_invocation_count
        == trace.formal_validation_count
        == trace.approval_consumption_count
        == trace.workspace_write_count
        == 0
    )


def test_protected_config_patch_cannot_enter_check_or_formal_validation(
    mechanism_harness: MechanismHarness,
) -> None:
    trace = mechanism_harness.run_step("protected-config-patch")
    assert trace.error_code == "PROTECTED_ARTIFACT_CHANGED"
    assert (
        trace.dispatch_count
        == trace.candidate_publish_count
        == trace.check_invocation_count
        == trace.formal_validation_count
        == trace.approval_consumption_count
        == trace.workspace_write_count
        == 0
    )


def test_protected_artifact_denials_precede_the_legal_src_patch_dispatch(
    mechanism_harness: MechanismHarness,
) -> None:
    """Both protected denials fire before any ALLOWed src patch can
    dispatch, and the legal patch's dispatch does not retroactively
    publish a protected change (SPEC §4.3 pre-policy priority)."""
    for step_id in ("protected-tests-patch", "protected-config-patch"):
        denied = mechanism_harness.run_step(step_id)
        assert denied.error_code == "PROTECTED_ARTIFACT_CHANGED"
        assert denied.dispatch_count == 0
    allowed = mechanism_harness.run_step("src-patch")
    assert allowed.error_code is None
    assert allowed.dispatch_count == 1
    assert allowed.candidate_publish_count == 1
    assert allowed.check_invocation_count == 0
    assert allowed.formal_validation_count == 0
