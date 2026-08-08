"""T34.2 legacy step 34.A: reference OCI reproduction contract tests.

The exact displayed RED test
``test_rebuilt_reference_manifest_matches_frozen_task2_digest`` is copied
from the T34.2 card with its body byte-identical; the card's second
assert line is 90 characters, so it is ruff-wrapped (assertions unchanged,
wrapping only — the documented T17.1/T24.1 precedent class).  The
already-RED matrix test ``test_reference_image_reproduction_matrix`` pins
the PLAN 34.A row (Expected 34.A): exact digest continuity, no
self-reference, non-root/no-network/read-only/resource/report/fixture
smoke, registry cleanup, and the read-only NO-GO mismatch disposition.

The frozen Task 2 digest is bound through the packaged production
manifest (``src/vespercode/profiles/builtin/reference-profile-v1.json``),
loaded through the T06.2 integrity loader against the embedded Task 2.G
gate identity (SPEC_PROCESS §80: rebuilt twice byte-identical as
cf0b6c5c…, SPEC_PROCESS 86 re-freeze).  The ``reference/manifest/reference-profile-v1.json``
copy was re-frozen to the same digest set under the §86 determinism
normalization and the loader verifies the two copies agree; the packaged
manifest remains the authoritative frozen identity source.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Final

import pytest

from scripts.run_reference_image_smoke import (
    ContainerIsolationEvidenceV1,
    FROZEN_TASK2_MANIFEST_DIGEST_V1,
    GatePytestReportV1,
    LoopbackRegistryDigestMismatchV1,
    LoopbackRegistryEvidenceV1,
    OCIImageInspection,
    ProductionExecutorEvidenceV1,
    ReferenceBuildInputV1,
    ReferenceImageBuildEvidenceV1,
    TARGET_TEST_NODE_ID,
    build_reference_image,
    freeze_reference_build_input,
    packaged_reference_manifest_digest,
    probe_loopback_registry,
    task2_go_digest,
    validate_gate_pytest_report,
)

_REPO_ROOT: Final = Path(__file__).resolve().parents[3]

_FROZEN_CPU_LIMIT: Final = 2
_FROZEN_MEMORY_LIMIT_BYTES: Final = 2 * 1024**3
_FROZEN_PID_LIMIT: Final = 256
_FROZEN_NON_ROOT_UID: Final = 10001
_FROZEN_WORKSPACE_WRITE_ERRNO: Final = 30  # EROFS


@pytest.mark.oci_smoke
def test_rebuilt_reference_manifest_matches_frozen_task2_digest(
    rebuilt_reference_image: OCIImageInspection,
) -> None:
    assert rebuilt_reference_image.manifest_digest == task2_go_digest()
    # The card's second assert is ruff-wrapped (90-char card line > 88;
    # assertions unchanged — the T17.1/T24.1 precedent class).
    assert (
        rebuilt_reference_image.manifest_digest == packaged_reference_manifest_digest()
    )


@pytest.mark.oci_smoke
def test_reference_image_reproduction_matrix(
    rebuilt_reference_build: ReferenceImageBuildEvidenceV1,
    rebuilt_reference_image: OCIImageInspection,
    reference_isolation_evidence: ContainerIsolationEvidenceV1,
    reference_registry_evidence: LoopbackRegistryEvidenceV1,
    reference_pytest_report_evidence: GatePytestReportV1,
    reference_workspace_listing_evidence: tuple[str, ...],
    production_executor_evidence: ProductionExecutorEvidenceV1,
) -> None:
    """PLAN 34.A row: exact digest continuity, no self-reference, non-root/
    no-network/read-only/resource/report/fixture smoke, registry cleanup,
    and the read-only NO-GO mismatch disposition.
    """
    rebuilt = rebuilt_reference_image.manifest_digest
    assert rebuilt is not None
    # Row 1: exact digest continuity — the rebuilt manifest equals the
    # Task 2.G GO identity and the packaged manifest identity, both pinned
    # to the frozen Task 2 digest.
    assert rebuilt == task2_go_digest()
    assert rebuilt == packaged_reference_manifest_digest()
    assert rebuilt == FROZEN_TASK2_MANIFEST_DIGEST_V1
    # Row 2: fixed build identity and no self-reference.
    assert rebuilt_reference_image.platform == "linux/amd64"
    assert rebuilt_reference_image.image_config_digest is not None
    assert len(rebuilt_reference_image.recipe_digest or "") == 64
    assert rebuilt_reference_image.self_reference_scan_passed is True
    # Row 3: loopback registry round-trip preserves the three-way digest
    # with zero credentials, zero external push, and verified cleanup.
    assert reference_registry_evidence.local_oci_manifest_digest == rebuilt
    assert reference_registry_evidence.registry_repo_digest == rebuilt
    assert reference_registry_evidence.digest_pull_repo_digest == rebuilt
    assert reference_registry_evidence.credentials_used is False
    assert reference_registry_evidence.external_push_count == 0
    assert reference_registry_evidence.cleanup_verified is True
    # Row 4: non-root, no-network, read-only, bounded-resource isolation.
    isolation = reference_isolation_evidence
    assert isolation.network_disabled is True
    assert isolation.non_root is True
    assert isolation.root_read_only is True
    assert isolation.capabilities_dropped is True
    assert isolation.docker_socket_absent is True
    assert isolation.workspace_read_only is True
    assert isolation.tmpfs_bounded is True
    assert isolation.cpu_limit == _FROZEN_CPU_LIMIT
    assert isolation.memory_limit_bytes == _FROZEN_MEMORY_LIMIT_BYTES
    assert isolation.pid_limit == _FROZEN_PID_LIMIT
    assert isolation.cleanup_verified is True
    # Row 5: the report channel carries the stable failing target and the
    # frozen fixture bytes are served read-only at /workspace.
    assert validate_gate_pytest_report(reference_pytest_report_evidence).passed is True
    assert reference_pytest_report_evidence.exit_code == 1
    assert TARGET_TEST_NODE_ID in reference_pytest_report_evidence.collected_node_ids
    assert set(reference_workspace_listing_evidence) == {
        "pyproject.toml",
        "requirements.lock",
        "src",
        "tests",
    }
    # Row 6: the production executor enforces the frozen profile over the
    # fresh materialized fixture candidate bytes.
    assert production_executor_evidence.error_code is None
    assert production_executor_evidence.exit_code == 0
    assert production_executor_evidence.observed_uid == _FROZEN_NON_ROOT_UID
    assert (
        production_executor_evidence.workspace_write_errno
        == _FROZEN_WORKSPACE_WRITE_ERRNO
    )
    assert production_executor_evidence.candidate_bytes_match is True
    assert production_executor_evidence.cleanup_verified is True
    # Row 7: the frozen identity chain binds the clean source (dual lock
    # byte-identical, fixture tree frozen) before any inspection; the
    # freeze fails closed on drift, so its success is the identity proof.
    build_input = freeze_reference_build_input(_REPO_ROOT)
    assert len(build_input.requirements_digest) == 64
    assert len(build_input.fixture_tree_digest) == 64
    assert build_input.requirements_digest == (
        "67a6b630fb418344bea58ed0b98c1006391bbc947b36356188a1e01fa5fe9a64"
    )
    # Row 8: mismatch disposition is read-only NO-GO — a drifted build
    # input is rejected before any build, and an observed loopback digest
    # transformation raises the exact rejection after verified cleanup,
    # with zero external push and no accepted evidence.
    drifted = ReferenceBuildInputV1(
        base_image_digest="f" * 64,
        registry_image_digest=build_input.registry_image_digest,
        requirements_digest=build_input.requirements_digest,
        fixture_tree_digest=build_input.fixture_tree_digest,
        tool_versions_digest=build_input.tool_versions_digest,
        build_recipe_version=build_input.build_recipe_version,
    )
    with pytest.raises(ValueError, match="no longer matches"):
        build_reference_image(drifted)
    transformed = dataclasses.replace(
        rebuilt_reference_build,
        local_oci_manifest_digest=("0" if rebuilt[0] != "0" else "1") + rebuilt[1:],
    )
    with pytest.raises(LoopbackRegistryDigestMismatchV1) as captured:
        probe_loopback_registry(transformed)
    rejection = captured.value
    assert rejection.error_code == "OCI_REGISTRY_DIGEST_MISMATCH"
    assert rejection.external_push_count == 0
    assert rejection.cleanup_verified is True
    assert rejection.accepted_evidence_returned is False
