"""T29.3 legacy step 29.C: Milestone 29 typed workflow-port aggregate.

``RunGovernanceWorkflowPortsV1`` aggregates the three typed Milestone 29
workflow port sets (run lifecycle, disclosure decision, final writeback)
and ``RunGovernanceRouteInstallerV1`` installs all Milestone 29 routes in
the exact deterministic order — run lifecycle routes first, then the
disclosure routes, then the final-writeback routes — onto one composed
app (GREEN-4: deterministic Milestone 29 installer composition only).
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI

from src.vespercode.web.disclosure_workflow import (
    DisclosureDecisionWorkflowPortV1,
    WorkflowIdentityPortV1,
)
from src.vespercode.web.routes_disclosure import DisclosureRouteInstallerV1
from src.vespercode.web.routes_runs import RunLifecycleRouteInstallerV1
from src.vespercode.web.routes_writeback import FinalWritebackRouteInstallerV1
from src.vespercode.web.run_lifecycle_workflow import RunLifecycleWorkflowPortsV1
from src.vespercode.web.writeback_workflow import FinalWritebackWorkflowPortV1


@dataclass(frozen=True)
class RunGovernanceWorkflowPortsV1:
    """The immutable Milestone 29 typed workflow-port aggregate.

    The installers receive the three port sets explicitly — there is no
    service locator or hidden workflow lookup (GREEN-1/Boundary).
    """

    run_lifecycle: RunLifecycleWorkflowPortsV1
    disclosure: DisclosureDecisionWorkflowPortV1
    final_writeback: FinalWritebackWorkflowPortV1


class RunGovernanceRouteInstallerV1:
    """The deterministic Milestone 29 route installer composition.

    Applies the run lifecycle installer, then the disclosure installer,
    then the final-writeback installer, in the exact order, so every
    Milestone 29 route is installed exactly once on the composed app.
    """

    def __init__(
        self,
        ports: RunGovernanceWorkflowPortsV1,
        identity: WorkflowIdentityPortV1,
    ) -> None:
        self._ports = ports
        self._identity = identity

    def install(self, app: FastAPI) -> None:
        RunLifecycleRouteInstallerV1(self._ports.run_lifecycle).install(app)
        DisclosureRouteInstallerV1(self._ports.disclosure, self._identity).install(app)
        FinalWritebackRouteInstallerV1(
            self._ports.final_writeback, self._identity
        ).install(app)
