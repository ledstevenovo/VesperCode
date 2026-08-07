"""T08.1 legacy step 8.B: ordered PREFLIGHT admission coordinator tests.

The coordinator composes only the declared admission ports and the Task
7.B lifecycle repository; the success trace invokes every port exactly
once in the frozen SPEC §4.1 order, and every failure returns after an
exact prefix with zero later calls and zero forbidden side effects.
Concrete Win32, Docker, credential, Snapshot, baseline, Agent, LLM,
install, build, and workspace-write behavior remain out of scope
(GREEN-4).
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

# The coordinator consumes pydantic runtime contracts; the hash-locked
# gate toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.contracts.run import RunPhase, RunStateV1, RunStatus
from vespercode.runs.admission import (
    AdmissionCoordinator,
    AdmissionPortsV1,
    AdmissionResultV1,
)
from vespercode.storage.connection import ControlDatabase, open_control_database
from vespercode.storage.migration_engine import apply_migrations
from vespercode.storage.migrations.v0001_run_wait import RUN_WAIT_V1_MIGRATION
from vespercode.storage.run_repository import (
    RunRepository,
    TransitionCommandV1,
)

CREATED = RunStateV1(status="CREATED", phase=AbsentV1(kind="ABSENT"))
RUNNING_PREFLIGHT = RunStateV1(
    status="RUNNING", phase=PresentV1(kind="PRESENT", value="PREFLIGHT")
)
STOPPED = RunStateV1(status="STOPPED", phase=AbsentV1(kind="ABSENT"))

_CREATED_AT = CanonicalTimestampV1("2026-08-05T09:00:00.000Z")
_RUN_DEADLINE = CanonicalTimestampV1("2026-08-05T09:15:00.000Z")

# The exact frozen SPEC §4.1 PREFLIGHT order (behavior 5 and the
# determinism success-path list): workspace identity/lease, recovery
# gate, Snapshot precheck, Snapshot create/seal, ``detect_static``,
# reference image/execution profile readiness, OpenAI credential/endpoint
# readiness, BASELINE.
EXPECTED_ORDER: tuple[str, ...] = (
    "workspace",
    "recovery",
    "snapshot_precheck",
    "snapshot_create",
    "static_profile",
    "execution_readiness",
    "credential_readiness",
    "baseline",
)


def accepted() -> AdmissionResultV1:
    """One ACCEPTED port result."""
    return AdmissionResultV1(kind="ACCEPTED")


def rejected(error_code: str) -> AdmissionResultV1:
    """One REJECTED port result with the stable code and guidance."""
    return AdmissionResultV1(
        kind="REJECTED",
        error_code=error_code,
        reason=f"{error_code}: the admission step was rejected",
        suggestion="resolve the reported preflight condition and retry",
    )


class RecordingAdmissionPorts:
    """Records every port call in order; each result is injectable."""

    def __init__(self) -> None:
        self._calls: list[str] = []
        self.workspace_result: AdmissionResultV1 = accepted()
        self.recovery_result: AdmissionResultV1 = accepted()
        self.snapshot_precheck_result: AdmissionResultV1 = accepted()
        self.snapshot_create_result: AdmissionResultV1 = accepted()
        self.static_profile_result: AdmissionResultV1 = accepted()
        self.execution_readiness_result: AdmissionResultV1 = accepted()
        self.credential_readiness_result: AdmissionResultV1 = accepted()
        self.baseline_result: AdmissionResultV1 = accepted()

    @property
    def calls(self) -> tuple[str, ...]:
        return tuple(self._calls)

    def acquire_workspace(self) -> AdmissionResultV1:
        self._calls.append("workspace")
        return self.workspace_result

    def check_recovery(self) -> AdmissionResultV1:
        self._calls.append("recovery")
        return self.recovery_result

    def precheck(self) -> AdmissionResultV1:
        self._calls.append("snapshot_precheck")
        return self.snapshot_precheck_result

    def create(self) -> AdmissionResultV1:
        self._calls.append("snapshot_create")
        return self.snapshot_create_result

    def detect_static(self) -> AdmissionResultV1:
        self._calls.append("static_profile")
        return self.static_profile_result

    def check_execution_readiness(self) -> AdmissionResultV1:
        self._calls.append("execution_readiness")
        return self.execution_readiness_result

    def check_credential_readiness(self) -> AdmissionResultV1:
        self._calls.append("credential_readiness")
        return self.credential_readiness_result

    def enter_baseline(self) -> AdmissionResultV1:
        self._calls.append("baseline")
        return self.baseline_result


def open_prepared_admission_database(path: Path) -> ControlDatabase:
    """Open a migrated v0001 database with one CREATED run-1 (and its
    frozen snapshot row) ready for admission."""
    database = open_control_database(path)
    apply_migrations(database, (RUN_WAIT_V1_MIGRATION,))
    with database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots (config_snapshot_id, digest,"
            " llm_profile_id, reference_profile_id, policy_id,"
            " target_test_ids, limits_digest, frozen_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "snap-run-1",
                "a" * 64,
                "mock-deterministic-v1",
                "python-src-py312-v1",
                "PYTHON_SRC_ONLY_V1",
                "[]",
                "c" * 64,
                _CREATED_AT.value,
            ),
        )
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES (?, ?, ?, 'CREATED', NULL, 1, ?, ?)",
            (
                "run-1",
                "workspace-1",
                "snap-run-1",
                _CREATED_AT.value,
                _RUN_DEADLINE.value,
            ),
        )
    return database


def build_admission_harness(
    ports: RecordingAdmissionPorts, database: ControlDatabase
) -> AdmissionCoordinator:
    """One coordinator composing the recording ports and the real Task 7.B
    lifecycle repository over the prepared database."""
    return AdmissionCoordinator(
        AdmissionPortsV1(
            workspace=ports,
            recovery=ports,
            snapshot=ports,
            static_profile=ports,
            execution_readiness=ports,
            credential_readiness=ports,
            baseline=ports,
        ),
        RunRepository(database),
    )


@pytest.fixture
def ports() -> RecordingAdmissionPorts:
    return RecordingAdmissionPorts()


@pytest.fixture
def admission(ports: RecordingAdmissionPorts, tmp_path: Path) -> AdmissionCoordinator:
    return build_admission_harness(
        ports, open_prepared_admission_database(tmp_path / "admission.db")
    )


def _run_state(database: ControlDatabase, run_id: str) -> RunStateV1:
    rows = database.read_rows(
        "SELECT status, phase FROM runs WHERE run_id = ?",
        (run_id,),
    )
    assert len(rows) == 1
    status = cast(RunStatus, str(rows[0][0]))
    phase = rows[0][1]
    if phase is None:
        return RunStateV1(status=status, phase=AbsentV1(kind="ABSENT"))
    return RunStateV1(
        status=status,
        phase=PresentV1(kind="PRESENT", value=cast(RunPhase, str(phase))),
    )


def test_all_ports_accepted_returns_accepted(tmp_path: Path) -> None:
    ports = RecordingAdmissionPorts()
    database = open_prepared_admission_database(tmp_path / "success.db")
    admission = build_admission_harness(ports, database)
    result = admission.start_run("run-1")
    assert result.kind == "ACCEPTED"
    assert result.error_code is None
    assert ports.calls == EXPECTED_ORDER
    # The BASELINE port's adapter owns the entry into BASELINE (GREEN-4);
    # the coordinator leaves the run in RUNNING(PREFLIGHT) on success.
    assert _run_state(database, "run-1") == RUNNING_PREFLIGHT


def test_start_run_rejects_an_unknown_run_without_calling_ports(
    tmp_path: Path,
) -> None:
    ports = RecordingAdmissionPorts()
    database = open_prepared_admission_database(tmp_path / "unknown.db")
    admission = build_admission_harness(ports, database)
    result = admission.start_run("run-unknown")
    assert result.kind == "REJECTED"
    assert result.error_code == "RUN_NOT_FOUND"
    assert ports.calls == ()
    # The existing CREATED run is untouched by a rejected start.
    assert _run_state(database, "run-1") == CREATED


def test_start_run_rejects_a_run_that_is_not_created(tmp_path: Path) -> None:
    ports = RecordingAdmissionPorts()
    database = open_prepared_admission_database(tmp_path / "running.db")
    repository = RunRepository(database)
    assert (
        repository.compare_and_transition(
            TransitionCommandV1(
                run_id="run-1", expected=CREATED, target=RUNNING_PREFLIGHT
            )
        ).kind
        == "APPLIED"
    )
    admission = build_admission_harness(ports, database)
    result = admission.start_run("run-1")
    assert result.kind == "REJECTED"
    assert result.error_code == "RUN_NOT_CREATED"
    assert ports.calls == ()


def test_rejected_result_requires_the_exact_rejection_fields() -> None:
    with pytest.raises(ValidationError):
        AdmissionResultV1(kind="REJECTED")
    with pytest.raises(ValidationError):
        AdmissionResultV1(kind="ACCEPTED", error_code="WORKSPACE_LOCKED")
