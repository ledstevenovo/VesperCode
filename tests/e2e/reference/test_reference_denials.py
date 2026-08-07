"""T31.1 legacy step 31.B: hard DENY and protected-artifact defense.

The production patch engine denies an outside-scope patch before any
dispatch, publication, artifact, workspace write, or authorization
effect; the harness proves zero publications through the counting
fixture publisher port.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

from scripts.run_reference_e2e import (
    ReferenceE2EConfigV1,
    ReferenceE2EHarness,
)


pytestmark = pytest.mark.reference_e2e


def test_outside_scope_patch_is_denied_before_any_publication(
    reference_e2e_harness: ReferenceE2EHarness,
) -> None:
    result = reference_e2e_harness.run_hard_deny_scenario()
    assert result.error_code == "PATCH_PATH_NOT_EDITABLE"
    assert result.publish_count == 0
    assert result.workspace_write_count == 0


def test_hard_deny_trace_is_stable(
    reference_e2e_harness: ReferenceE2EHarness,
) -> None:
    """The denial trace is content-addressed and stable across runs."""
    first = reference_e2e_harness.run_hard_deny_scenario()
    assert first.error_code == "PATCH_PATH_NOT_EDITABLE"
    assert first.publish_count == 0
    assert first.trace_digest is not None
    second = ReferenceE2EHarness(
        ReferenceE2EConfigV1(
            schema_version=1,
            run_id="t31-1-reference-e2e",
            clock_epoch="2026-08-07T00:00:00.000Z",
        )
    ).run_hard_deny_scenario()
    assert second.trace_digest == first.trace_digest


def test_protected_artifact_patch_is_denied_before_any_publication(
    reference_e2e_harness: ReferenceE2EHarness,
) -> None:
    """SPEC §1.4.2: a patch under ``tests/**`` is a protected-artifact
    change and is denied before any dispatch, publication, artifact,
    workspace write, or authorization effect."""
    result = reference_e2e_harness.run_protected_artifact_scenario()
    assert result.error_code == "PROTECTED_ARTIFACT_CHANGED"
    assert result.publish_count == 0
    assert result.workspace_write_count == 0
