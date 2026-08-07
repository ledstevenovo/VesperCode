"""T31.1 legacy step 31.B: zero workspace writes across the harness.

Every harness scenario leaves the workspace byte-identical: the happy
path, the denial path, and the cleared-credential path write nothing
(SPEC §4.5 zero-workspace-write discipline).
"""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

from scripts.run_reference_e2e import ReferenceE2EHarness


pytestmark = pytest.mark.reference_e2e


def test_happy_path_leaves_zero_workspace_writes(
    reference_e2e_harness: ReferenceE2EHarness,
) -> None:
    result = reference_e2e_harness.run_until_final_wait()
    assert result.verified_candidate_created is True
    assert result.workspace_write_count == 0


def test_denial_path_leaves_zero_workspace_writes(
    reference_e2e_harness: ReferenceE2EHarness,
) -> None:
    result = reference_e2e_harness.run_hard_deny_scenario()
    assert result.error_code == "PATCH_PATH_NOT_EDITABLE"
    assert result.workspace_write_count == 0
    assert result.publish_count == 0


def test_credential_path_leaves_zero_workspace_writes(
    reference_e2e_harness: ReferenceE2EHarness,
) -> None:
    result = reference_e2e_harness.run_cleared_credential_call_gate()
    assert result.error_code == "CREDENTIAL_MISSING"
    assert result.workspace_write_count == 0
    assert result.real_call_side_effect_counts == (0, 0, 0, 0, 0)
