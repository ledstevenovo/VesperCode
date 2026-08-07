"""T34.2 legacy step 34.A: shared reference-image smoke fixtures.

The session-scoped fixtures reproduce the frozen reference OCI manifest
exactly once per pytest session and expose the immutable build evidence,
inspection, and real probe evidence the two task test files consume
(rebuilt digest identity, loopback round-trip, isolation, workspace
listing, pytest report channel, and the production executor run).  Before
the exact reproduction path is implemented, ``rebuilt_reference_image``
yields the empty pre-implementation inspection so the exact RED's first
task-owned assertion fails on the missing reproduction contract (the
T30.1 vocabulary-shell precedent); the build-evidence fixture raises
``NotImplementedError`` on the same missing path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.run_reference_image_smoke import (
    ContainerIsolationEvidenceV1,
    GatePytestReportV1,
    LoopbackRegistryEvidenceV1,
    OCIImageInspection,
    ProductionExecutorEvidenceV1,
    ReferenceImageBuildEvidenceV1,
    TARGET_TEST_NODE_ID,
    ensure_reference_tag,
    inspection_from_evidence,
    probe_loopback_registry,
    rebuild_reference_build_evidence,
    reference_container_isolation,
    reference_pytest_report,
    reference_workspace_listing,
    run_production_executor_probe,
)

_REFERENCE_TAG = "vespercode-reference:local"


def reference_repo_root() -> Path:
    """The repository root of this worktree."""
    return Path(__file__).resolve().parents[3]


def reference_fixture_path() -> Path:
    """The frozen reference fixture tree (SPEC §4.5; Task 2 input, read-only)."""
    return reference_repo_root() / "reference" / "fixture"


@pytest.fixture(scope="session")
def rebuilt_reference_build() -> ReferenceImageBuildEvidenceV1:
    """One frozen reference OCI build evidence, reproduced exactly once."""
    return rebuild_reference_build_evidence()


@pytest.fixture(scope="session")
def rebuilt_reference_image(
    rebuilt_reference_build: ReferenceImageBuildEvidenceV1,
) -> OCIImageInspection:
    """The closed inspection of the reproduced reference image, derived
    from the session's single build evidence (no second build)."""
    return inspection_from_evidence(rebuilt_reference_build)


@pytest.fixture(scope="session")
def ensure_reference_tagged(
    rebuilt_reference_build: ReferenceImageBuildEvidenceV1,
) -> None:
    """Ensure the frozen reference image is loaded and tagged once per
    session: the isolation, workspace-listing, and production-executor
    probes all create containers from the daemon-held image, so a fresh
    daemon must hold it before any of them runs."""
    ensure_reference_tag(_REFERENCE_TAG, rebuilt_reference_build)


@pytest.fixture(scope="session")
def reference_isolation_evidence(
    rebuilt_reference_build: ReferenceImageBuildEvidenceV1,
) -> ContainerIsolationEvidenceV1:
    """One fresh frozen reference container's isolation evidence (T02.3)."""
    return reference_container_isolation(
        rebuilt_reference_build, reference_fixture_path()
    )


@pytest.fixture(scope="session")
def reference_workspace_listing_evidence(
    rebuilt_reference_build: ReferenceImageBuildEvidenceV1,
    ensure_reference_tagged: None,
) -> tuple[str, ...]:
    """The sorted /workspace entries of one fresh frozen container."""
    return reference_workspace_listing(
        rebuilt_reference_build, reference_fixture_path()
    )


@pytest.fixture(scope="session")
def reference_registry_evidence(
    rebuilt_reference_build: ReferenceImageBuildEvidenceV1,
) -> LoopbackRegistryEvidenceV1:
    """One credential-free loopback registry round-trip (T02.2)."""
    return probe_loopback_registry(rebuilt_reference_build)


@pytest.fixture(scope="session")
def reference_pytest_report_evidence(
    rebuilt_reference_build: ReferenceImageBuildEvidenceV1,
) -> GatePytestReportV1:
    """One explicitly loaded pytest lifecycle of the stable failing
    target in a fresh reference container with the fixed report channel."""
    return reference_pytest_report(
        rebuilt_reference_build,
        reference_fixture_path(),
        reference_repo_root(),
        (TARGET_TEST_NODE_ID,),
        target_node_ids=(TARGET_TEST_NODE_ID,),
    )


@pytest.fixture(scope="session")
def production_executor_evidence(
    ensure_reference_tagged: None,
) -> ProductionExecutorEvidenceV1:
    """One real production-executor run over a fresh materialized
    fixture candidate."""
    return run_production_executor_probe()
