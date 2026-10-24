"""v2 composition root for one offline-capable Harness run.

Route A composition: the agent loop keeps staging candidate content in
``InMemoryWorkspacePort`` (deterministic, no filesystem side effects),
while real workspace mutation happens only through the explicit,
approval-gated ``V2WritebackService`` over the real
``LocalDiskWorkspacePort``.  Recovery is restart-safe: a new harness over
the same control database finds durable non-terminal transactions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from vespercode.contracts.v2_identity import CandidateIdentityV2
from vespercode.contracts.v2_writeback import WriteOperationV2
from vespercode.loop.v2_engine import V2AgentLoop, V2LLM, V2LoopResult
from vespercode.memory.v2 import V2Memory
from vespercode.persistence.v2_recovery import V2RecoveryService
from vespercode.persistence.v2_writeback import V2WritebackService
from vespercode.storage.v2_database import (
    V2Database,
    default_v2_database_path,
    initialize_v2_database,
    open_v2_database,
)
from vespercode.tools.v2_dispatcher import InMemoryWorkspacePort, V2ToolDispatcher
from vespercode.workspace.v2_disk import LocalDiskWorkspacePort


@runtime_checkable
class _DiskPort(Protocol):
    """The disk existence probe the runtime needs from the disk port."""

    def exists(self, path: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class V2HarnessConfig:
    workspace: Path
    control_root: Path
    max_turns: int = 20

    @property
    def database_path(self) -> Path:
        return default_v2_database_path(self.control_root)


@dataclass(frozen=True, slots=True)
class V2RunResult:
    run_id: str
    loop: V2LoopResult
    database_path: Path


class V2Harness:
    """Compose v2 database, memory, policy dispatcher, and the main loop.

    ``staging_port`` (default: a fresh in-memory port) receives loop
    dispatches and holds staged candidate content.  ``disk_port`` (default:
    a real local-disk port over ``config.workspace``) is the only writer of
    real files, and only via the approval-gated writeback service.
    """

    def __init__(
        self,
        config: V2HarnessConfig,
        *,
        staging_port: InMemoryWorkspacePort | None = None,
        disk_port: _DiskPort | None = None,
    ) -> None:
        self._config = config
        initialize_v2_database(config.database_path)
        self._database: V2Database = open_v2_database(config.database_path)
        self._memory = V2Memory()
        self._staging = (
            staging_port if staging_port is not None else InMemoryWorkspacePort()
        )
        self._disk_port = (
            disk_port
            if disk_port is not None
            else LocalDiskWorkspacePort(config.workspace)
        )
        self._writeback = V2WritebackService(
            self._database, self._disk_port, workspace=config.workspace
        )
        self._recovery = V2RecoveryService(self._database, self._disk_port)

    @property
    def database(self) -> V2Database:
        return self._database

    @property
    def workspace_port(self) -> InMemoryWorkspacePort:
        """The in-memory staging port used by the agent loop."""

        return self._staging

    @property
    def disk_port(self) -> object:
        """The real-workspace port used by writeback and recovery."""

        return self._disk_port

    @property
    def writeback_service(self) -> V2WritebackService:
        return self._writeback

    @property
    def recovery_service(self) -> V2RecoveryService:
        return self._recovery

    def run(self, task: str, llm: V2LLM) -> V2RunResult:
        run_id = self._database.create_run(str(self._config.workspace))
        if not self._database.transition_run_latest(
            run_id, status="RUNNING", phase="AGENT_LOOP"
        ):
            raise RuntimeError("v2 run could not enter AGENT_LOOP")
        loop = V2AgentLoop(
            workspace=self._config.workspace,
            llm=llm,
            dispatcher=V2ToolDispatcher(self._staging),
            memory=self._memory,
            max_turns=self._config.max_turns,
        )
        try:
            result = loop.run(task, run_id=run_id)
        except Exception:
            self._database.transition_run_latest(run_id, status="STOPPED", phase=None)
            raise
        final_status = "SUCCEEDED" if result.status == "SUCCEEDED" else "STOPPED"
        if not self._database.transition_run_latest(
            run_id, status=final_status, phase=None
        ):
            raise RuntimeError("v2 run could not enter its terminal state")
        return V2RunResult(run_id, result, self._config.database_path)

    def stage_candidate(self, run_id: str) -> CandidateIdentityV2:
        """Record the staged content as a candidate under one snapshot."""

        snapshot_id = self._database.create_snapshot(run_id)
        candidate_id = self._database.create_candidate(run_id, snapshot_id, revision=0)
        return CandidateIdentityV2(
            candidate_id=candidate_id, snapshot_id=snapshot_id, revision=0
        )

    def staged_operations(self) -> tuple[WriteOperationV2, ...]:
        """Build explicit CREATE/REPLACE operations from staged content.

        The declared action reflects the real workspace state at call time:
        REPLACE for files that already exist, CREATE for new files.
        """

        return tuple(
            WriteOperationV2(
                "REPLACE" if self._disk_port.exists(path) else "CREATE",
                path,
                content,
            )
            for path, content in sorted(self._staging.files.items())
        )

    def close(self) -> None:
        self._database.close()


__all__ = ["V2Harness", "V2HarnessConfig", "V2RunResult"]
