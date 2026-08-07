"""T38.2 legacy step 38.F: local operations route composition.

``LocalOperationsWorkflowPortsV1`` aggregates the four typed operations
port sets (credential, memory, audit, recovery — the T38.1/T38.2
workflow seams) and ``LocalOperationsRouteInstallerV1`` installs all
four operations route families in the exact deterministic order —
credentials first, then memory, then audit, then recovery — onto one
composed app (GREEN-2: Credential/Memory/Audit/Recovery routes behind
the exact governance-then-operations installer tuple).  The installer
owns the production control-plane identity seam
(``ProductionLocalIdentityPortV1``), so the routes can never construct,
widen, or mutate an event id, entry id, grant, approval, or clock value
(SPEC §5.4); no service locator or hidden workflow lookup exists, and
DDL, migration, parser, and repository rules stay out of scope
(GREEN-4).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import FastAPI

from vespercode.canonical.clock import SystemClockV1
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.web.routes_audit import (
    AuditRouteInstallerV1,
    AuditWorkflowPortsV1,
)
from vespercode.web.routes_credentials import (
    CredentialRouteInstallerV1,
    CredentialWorkflowPortsV1,
)
from vespercode.web.routes_memory import (
    MemoryRouteInstallerV1,
    MemoryWorkflowPortsV1,
)
from vespercode.web.routes_recovery import (
    RecoveryRouteInstallerV1,
    RecoveryWorkflowPortsV1,
)


class ProductionLocalIdentityPortV1:
    """The concrete production control-plane identity seam.

    Every id is a fresh UUID hex and every time comes from the system
    clock, so the Web routes can never supply, widen, or reuse an event
    identity (SPEC §5.4); the class satisfies the governance, credential,
    memory, audit, and recovery identity protocols structurally.
    """

    def __init__(self) -> None:
        self._clock = SystemClockV1()

    def new_grant_id(self) -> str:
        """One fresh production grant identity."""
        return f"grant-{uuid.uuid4().hex}"

    def new_approval_id(self) -> str:
        """One fresh production approval identity."""
        return f"approval-{uuid.uuid4().hex}"

    def new_event_id(self) -> str:
        """One fresh production mutation/decision event identity."""
        return f"event-{uuid.uuid4().hex}"

    def new_entry_id(self) -> str:
        """One fresh production memory entry identity."""
        return f"entry-{uuid.uuid4().hex}"

    def now(self) -> CanonicalTimestampV1:
        """The production current time."""
        return self._clock.now()


@dataclass(frozen=True)
class LocalOperationsWorkflowPortsV1:
    """The immutable typed operations workflow-port aggregate.

    The installer receives the four port sets explicitly — there is no
    service locator or hidden workflow lookup (GREEN-1/Boundary).
    """

    credentials: CredentialWorkflowPortsV1
    memory: MemoryWorkflowPortsV1
    audit: AuditWorkflowPortsV1
    recovery: RecoveryWorkflowPortsV1


class LocalOperationsRouteInstallerV1:
    """The deterministic operations route installer composition.

    Applies the credential installer, then the memory installer, then
    the audit installer, then the recovery installer, in the exact
    order, so every operations route is installed exactly once on the
    composed app (GREEN-2).
    """

    def __init__(self, ports: LocalOperationsWorkflowPortsV1) -> None:
        self._ports = ports
        self._identity = ProductionLocalIdentityPortV1()

    def install(self, app: FastAPI) -> None:
        CredentialRouteInstallerV1(self._ports.credentials, self._identity).install(app)
        MemoryRouteInstallerV1(self._ports.memory, self._identity).install(app)
        AuditRouteInstallerV1(self._ports.audit, self._identity).install(app)
        RecoveryRouteInstallerV1(self._ports.recovery, self._identity).install(app)
