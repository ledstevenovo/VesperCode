"""T08.1 legacy step 8.B: ordered PREFLIGHT admission coordinator.

``AdmissionCoordinator.start_run`` atomically moves one existing CREATED
Run into ``RUNNING(PREFLIGHT)`` through the Task 7.B lifecycle repository
and then invokes the declared admission ports in the exact frozen
SPEC §4.1 order — workspace identity/lease, recovery gate, Snapshot
precheck, Snapshot create/seal, ``detect_static``, reference
image/execution profile readiness, OpenAI credential/endpoint readiness,
BASELINE.  Every rejection returns after an exact prefix of that order,
prevents every later port call, performs no Agent action, LLM call,
execution, install, image build, or workspace write, and settles the run
to STOPPED (§4.2.7: a PREFLIGHT run ends in BASELINE or STOPPED).
Concrete Win32, Docker, credential, Snapshot, baseline, Agent, LLM,
install, build, and workspace-write behavior remain out of scope
(GREEN-4).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, model_validator

from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.contracts.run import RunStateV1
from vespercode.storage.run_repository import (
    RunRepository,
    TransitionCommandV1,
)

_CREATED = RunStateV1(status="CREATED", phase=AbsentV1(kind="ABSENT"))
_RUNNING_PREFLIGHT = RunStateV1(
    status="RUNNING", phase=PresentV1(kind="PRESENT", value="PREFLIGHT")
)
_STOPPED = RunStateV1(status="STOPPED", phase=AbsentV1(kind="ABSENT"))


class AdmissionResultV1(BaseModel):
    """One closed admission outcome: ACCEPTED or REJECTED with guidance.

    A REJECTED result always carries the stable error code, a
    user-understandable reason, and a next-step suggestion (SPEC §5.3);
    an ACCEPTED result carries none of the rejection fields.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["ACCEPTED", "REJECTED"]
    error_code: str | None = None
    reason: str | None = None
    suggestion: str | None = None

    @model_validator(mode="after")
    def _require_exact_rejection(self) -> AdmissionResultV1:
        if self.kind == "REJECTED":
            if (
                self.error_code is None
                or self.reason is None
                or self.suggestion is None
            ):
                raise ValueError(
                    "REJECTED results require error code, reason, and suggestion"
                )
        elif (
            self.error_code is not None
            or self.reason is not None
            or self.suggestion is not None
        ):
            raise ValueError("ACCEPTED results must not carry rejection fields")
        return self


class WorkspaceAdmissionPortV1(Protocol):
    """Workspace identity and lease port (SPEC §4.1 behavior 6)."""

    def acquire_workspace(self) -> AdmissionResultV1: ...


class RecoveryAdmissionPortV1(Protocol):
    """Recovery gate port (SPEC §4.1 behavior 7)."""

    def check_recovery(self) -> AdmissionResultV1: ...


class SnapshotAdmissionPortV1(Protocol):
    """Snapshot precheck and create/seal port (SPEC §4.1 behaviors 8-9)."""

    def precheck(self) -> AdmissionResultV1: ...

    def create(self) -> AdmissionResultV1: ...


class StaticProfileAdmissionPortV1(Protocol):
    """Static project profile port (SPEC §4.1 behavior 10)."""

    def detect_static(self) -> AdmissionResultV1: ...


class ExecutionReadinessPortV1(Protocol):
    """Reference image/execution profile readiness port (SPEC §4.1
    behavior 11)."""

    def check_execution_readiness(self) -> AdmissionResultV1: ...


class CredentialReadinessPortV1(Protocol):
    """OpenAI credential/endpoint readiness port (SPEC §4.1 behavior 12)."""

    def check_credential_readiness(self) -> AdmissionResultV1: ...


class BaselineAdmissionPortV1(Protocol):
    """BASELINE entry port (SPEC §4.1 behavior 13)."""

    def enter_baseline(self) -> AdmissionResultV1: ...


@dataclass(frozen=True)
class AdmissionPortsV1:
    """The exact seven declared PREFLIGHT admission ports."""

    workspace: WorkspaceAdmissionPortV1
    recovery: RecoveryAdmissionPortV1
    snapshot: SnapshotAdmissionPortV1
    static_profile: StaticProfileAdmissionPortV1
    execution_readiness: ExecutionReadinessPortV1
    credential_readiness: CredentialReadinessPortV1
    baseline: BaselineAdmissionPortV1


def _reject(error_code: str, reason: str, suggestion: str) -> AdmissionResultV1:
    """One closed rejection with the stable code and next-step guidance."""
    return AdmissionResultV1(
        kind="REJECTED",
        error_code=error_code,
        reason=reason,
        suggestion=suggestion,
    )


class AdmissionCoordinator:
    """One ordered PREFLIGHT coordinator over declared ports only."""

    def __init__(self, ports: AdmissionPortsV1, repository: RunRepository) -> None:
        self._ports = ports
        self._repository = repository

    def start_run(self, run_id: str) -> AdmissionResultV1:
        """Move one existing CREATED Run through the exact PREFLIGHT order.

        The run first transitions atomically into RUNNING(PREFLIGHT)
        (SPEC §4.1 behavior 5), then the declared ports run in the exact
        frozen order; the first rejection returns after an exact prefix
        with no later port call and settles the run to STOPPED.
        """
        transition = self._repository.compare_and_transition(
            TransitionCommandV1(
                run_id=run_id,
                expected=_CREATED,
                target=_RUNNING_PREFLIGHT,
            )
        )
        if transition.kind == "NOT_FOUND":
            return _reject(
                "RUN_NOT_FOUND",
                f"run {run_id!r} does not exist",
                "create the run before starting it",
            )
        if transition.kind != "APPLIED":
            return _reject(
                "RUN_NOT_CREATED",
                f"run {run_id!r} is not in CREATED state",
                "only a CREATED run can enter PREFLIGHT",
            )
        workspace = self._ports.workspace.acquire_workspace()
        if workspace.kind == "REJECTED":
            return self._settle_failed(run_id, workspace)
        recovery = self._ports.recovery.check_recovery()
        if recovery.kind == "REJECTED":
            return self._settle_failed(run_id, recovery)
        snapshot_precheck = self._ports.snapshot.precheck()
        if snapshot_precheck.kind == "REJECTED":
            return self._settle_failed(run_id, snapshot_precheck)
        snapshot_create = self._ports.snapshot.create()
        if snapshot_create.kind == "REJECTED":
            return self._settle_failed(run_id, snapshot_create)
        static_profile = self._ports.static_profile.detect_static()
        if static_profile.kind == "REJECTED":
            return self._settle_failed(run_id, static_profile)
        execution_readiness = (
            self._ports.execution_readiness.check_execution_readiness()
        )
        if execution_readiness.kind == "REJECTED":
            return self._settle_failed(run_id, execution_readiness)
        credential_readiness = (
            self._ports.credential_readiness.check_credential_readiness()
        )
        if credential_readiness.kind == "REJECTED":
            return self._settle_failed(run_id, credential_readiness)
        baseline = self._ports.baseline.enter_baseline()
        if baseline.kind == "REJECTED":
            return self._settle_failed(run_id, baseline)
        return AdmissionResultV1(kind="ACCEPTED")

    def _settle_failed(
        self, run_id: str, result: AdmissionResultV1
    ) -> AdmissionResultV1:
        """Settle the failed PREFLIGHT run to STOPPED and return the
        rejection unchanged.

        The settlement is the coordinator's own fail-closed lifecycle
        action (SPEC §4.2.7) and never blocks the rejection: it touches
        only the run row, never the ports or any forbidden effect.
        """
        self._repository.compare_and_transition(
            TransitionCommandV1(
                run_id=run_id,
                expected=_RUNNING_PREFLIGHT,
                target=_STOPPED,
            )
        )
        return AdmissionResultV1(
            kind="REJECTED",
            error_code=result.error_code,
            reason=result.reason,
            suggestion=result.suggestion,
        )
