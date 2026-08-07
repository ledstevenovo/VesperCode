"""T31.1 reference E2E fixture: one disposable ReferenceE2EHarness.

Each test receives a fresh harness bound to deterministic identities
(the fixed run id and clock epoch make every trace content-addressed
and repeatable); the harness owns no persistent state between tests.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

from scripts.run_reference_e2e import (
    ReferenceE2EConfigV1,
    ReferenceE2EHarness,
)


@pytest.fixture
def reference_e2e_harness() -> ReferenceE2EHarness:
    return ReferenceE2EHarness(
        ReferenceE2EConfigV1(
            schema_version=1,
            run_id="t31-1-reference-e2e",
            clock_epoch="2026-08-07T00:00:00.000Z",
        )
    )
