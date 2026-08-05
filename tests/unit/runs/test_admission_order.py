"""T08.1 legacy step 8.B: exact RED test and the failure-prefix matrix.

The exact RED test pins the snapshot-precheck short circuit; the matrix
pins the PLAN Registry 8.B row — failure at each admission port stops at
that port, no later port is called, zero Run rows are created, and the
all-success trace calls every port exactly once in declared order.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# The coordinator consumes pydantic runtime contracts; the hash-locked
# gate toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from src.vespercode.runs.admission import AdmissionCoordinator
from tests.unit.runs.test_admission import (
    EXPECTED_ORDER,
    RecordingAdmissionPorts,
    build_admission_harness,
    open_prepared_admission_database,
    rejected,
)


@pytest.fixture
def ports() -> RecordingAdmissionPorts:
    return RecordingAdmissionPorts()


@pytest.fixture
def admission(ports: RecordingAdmissionPorts, tmp_path: Path) -> AdmissionCoordinator:
    return build_admission_harness(
        ports, open_prepared_admission_database(tmp_path / "admission_order.db")
    )


def test_snapshot_precheck_failure_calls_no_later_admission_port(
    admission: AdmissionCoordinator,
    ports: RecordingAdmissionPorts,
) -> None:
    ports.snapshot_precheck_result = rejected("SNAPSHOT_PRECHECK_FAILED")
    result = admission.start_run("run-1")
    assert result.error_code == "SNAPSHOT_PRECHECK_FAILED"
    assert ports.calls == ("workspace", "recovery", "snapshot_precheck")


def test_admission_failure_prefix_matrix(tmp_path: Path) -> None:
    """PLAN Registry 8.B row: failure at each admission port stops at that
    port; no later port is called; zero Run rows are created; the
    all-success trace calls every port exactly once in declared order."""
    failure_points: tuple[tuple[str, str, tuple[str, ...]], ...] = (
        ("workspace", "WORKSPACE_LOCKED", ("workspace",)),
        (
            "recovery",
            "RECOVERY_BLOCKS_NEW_RUN",
            ("workspace", "recovery"),
        ),
        (
            "snapshot_precheck",
            "WORKTREE_DIRTY",
            ("workspace", "recovery", "snapshot_precheck"),
        ),
        (
            "snapshot_precheck",
            "SENSITIVE_TRACKED_FILE",
            ("workspace", "recovery", "snapshot_precheck"),
        ),
        (
            "snapshot_create",
            "TREE_INTEGRITY_FAILED",
            (
                "workspace",
                "recovery",
                "snapshot_precheck",
                "snapshot_create",
            ),
        ),
        (
            "static_profile",
            "UNSUPPORTED_PROJECT",
            (
                "workspace",
                "recovery",
                "snapshot_precheck",
                "snapshot_create",
                "static_profile",
            ),
        ),
        (
            "execution_readiness",
            "EXECUTION_PROFILE_UNAVAILABLE",
            (
                "workspace",
                "recovery",
                "snapshot_precheck",
                "snapshot_create",
                "static_profile",
                "execution_readiness",
            ),
        ),
        (
            "credential_readiness",
            "CREDENTIAL_MISSING",
            (
                "workspace",
                "recovery",
                "snapshot_precheck",
                "snapshot_create",
                "static_profile",
                "execution_readiness",
                "credential_readiness",
            ),
        ),
        (
            "credential_readiness",
            "LLM_ENDPOINT_MISMATCH",
            (
                "workspace",
                "recovery",
                "snapshot_precheck",
                "snapshot_create",
                "static_profile",
                "execution_readiness",
                "credential_readiness",
            ),
        ),
        (
            "baseline",
            "BASELINE_ENTRY_FAILED",
            (
                "workspace",
                "recovery",
                "snapshot_precheck",
                "snapshot_create",
                "static_profile",
                "execution_readiness",
                "credential_readiness",
                "baseline",
            ),
        ),
    )
    for index, (port_attr, error_code, expected_prefix) in enumerate(failure_points):
        ports = RecordingAdmissionPorts()
        setattr(ports, f"{port_attr}_result", rejected(error_code))
        database = open_prepared_admission_database(tmp_path / f"prefix-{index}.db")
        admission = build_admission_harness(ports, database)
        result = admission.start_run("run-1")
        assert result.kind == "REJECTED"
        assert result.error_code == error_code
        assert ports.calls == expected_prefix
        # Zero Run rows are created, and the rejected PREFLIGHT settles
        # the run to STOPPED (SPEC §4.2.7: PREFLIGHT ends in BASELINE or
        # STOPPED).
        rows = database.read_rows("SELECT status, phase FROM runs")
        assert len(rows) == 1
        assert rows[0][0] == "STOPPED"
        assert rows[0][1] is None

    # The all-success trace calls every port exactly once in declared order.
    ports = RecordingAdmissionPorts()
    database = open_prepared_admission_database(tmp_path / "success.db")
    admission = build_admission_harness(ports, database)
    result = admission.start_run("run-1")
    assert result.kind == "ACCEPTED"
    assert result.error_code is None
    assert ports.calls == EXPECTED_ORDER
    assert database.read_rows("SELECT status, phase FROM runs") == [
        ("RUNNING", "PREFLIGHT")
    ]
