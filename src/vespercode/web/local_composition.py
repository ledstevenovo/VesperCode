"""T38.2 legacy step 38.F: final local production Web composition.

``ProductionLocalWorkflowPortsV1`` aggregates the typed shell ports, the
Milestone 29 governance ports, and the local operations ports;
``build_local_route_installers`` returns exactly the frozen production
installer tuple — ``RunGovernanceRouteInstallerV1`` first, then
``LocalOperationsRouteInstallerV1`` (GREEN-3) — and
``build_local_application`` composes the production local app over the
Task 28.A security config with that exact tuple (GREEN-2).  The builder
owns the production control-plane identity seam for the governance
installer; DDL, migration reordering, parser changes, recovery
predicates, untyped registries, service locators, duplicate domain
behavior, and alternate package composition remain out of scope
(GREEN-4).
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI

from vespercode.web.app import (
    LocalRouteInstallerSequenceV1,
    LocalShellPortsV1,
    create_local_app,
)
from vespercode.web.routes_operations import (
    LocalOperationsRouteInstallerV1,
    LocalOperationsWorkflowPortsV1,
    ProductionLocalIdentityPortV1,
)
from vespercode.web.run_workflows import (
    RunGovernanceRouteInstallerV1,
    RunGovernanceWorkflowPortsV1,
)
from vespercode.web.security import LocalWebSecurityConfigV1


@dataclass(frozen=True)
class ProductionLocalWorkflowPortsV1:
    """The immutable production local workflow-port aggregate.

    The composition receives the shell ports, the Milestone 29
    governance ports, and the operations ports explicitly — there is no
    service locator or hidden workflow lookup (GREEN-1/Boundary).
    """

    shell: LocalShellPortsV1
    governance: RunGovernanceWorkflowPortsV1
    operations: LocalOperationsWorkflowPortsV1


def build_local_route_installers(
    ports: ProductionLocalWorkflowPortsV1,
) -> LocalRouteInstallerSequenceV1:
    """The frozen production installer tuple (GREEN-3).

    Returns exactly ``RunGovernanceRouteInstallerV1`` followed by
    ``LocalOperationsRouteInstallerV1`` — the governance routes are
    installed first, then the operations routes, both over the same
    production control-plane identity seam.
    """
    identity = ProductionLocalIdentityPortV1()
    return (
        RunGovernanceRouteInstallerV1(ports.governance, identity),
        LocalOperationsRouteInstallerV1(ports.operations),
    )


def build_local_application(
    ports: ProductionLocalWorkflowPortsV1,
    security: LocalWebSecurityConfigV1,
) -> FastAPI:
    """One composed production local app (GREEN-2).

    The Task 28.B shell receives the typed shell ports, the exact
    loopback security config, and the frozen governance-then-operations
    installer tuple; the packaged assets are the Task 28.C composition's
    concern at the serve boundary.
    """
    return create_local_app(ports.shell, security, build_local_route_installers(ports))
