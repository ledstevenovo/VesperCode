"""Route B / B3: the local v2 services shell.

``V2LocalShell`` is the shared domain surface under the v2 CLI and the
v2 local WebUI: it composes a real ``V2Harness`` (fresh v2 control
database, boundary-checked disk port, approval-gated writeback,
durable recovery) plus the B2 injectable credential port, and exposes
small closed operations that project bounded, non-revealing facts only.

Composition decisions that belong to this shell:

- the control database lives at ``<workspace>/.vespercode`` (overridable
  for tests), and writeback through the shell additionally denies the
  control-plane directory, so staged content can never replace the v2
  database or its journal even after an explicit approval;
- the agent loop runs only behind an injected LLM factory: with no
  factory composed, ``start_run`` fails closed with ``NO_LLM_BOUNDARY``
  (no real provider transport exists in this slice);
- staged content is process-local (Route A's staging architecture), so
  the shell binds each run's writeback to the staged operations
  observed when that run was staged; a fresh process finds
  ``NOTHING_STAGED`` and must use durable recovery instead;
- every projection carries opaque IDs, closed statuses, revisions, and
  bounded timestamps — never file content, credentials, tokens, or
  request bodies.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, Sequence

from vespercode.contracts.v2_writeback import (
    ACTIVE_TRANSACTION_STATES,
    RecoveryOutcomeV2,
    RecoveryPreviewV2,
    WritebackOutcomeV2,
    WriteOperationV2,
    WritebackRequestV2,
)
from vespercode.credentials.v2_port import (
    InMemoryV2CredentialProvider,
    V2CredentialError,
    V2CredentialStatus,
)
from vespercode.governance.relaxed_policy import (
    DecisionV2,
    RelaxedPolicyV2,
)
from vespercode.loop.v2_engine import V2LLM
from vespercode.persistence.v2_recovery import V2RecoveryService
from vespercode.persistence.v2_writeback import V2WritebackService
from vespercode.runtime_v2 import V2Harness, V2HarnessConfig
from vespercode.storage.v2_database import (
    V2_DATABASE_FILENAME,
    V2Database,
    V2DatabaseError,
)

V2_SHELL_ERROR_CODES = frozenset(
    {
        "NO_LLM_BOUNDARY",
        "UNKNOWN_RUN",
        "UNKNOWN_CANDIDATE",
        "RUN_CANDIDATE_MISMATCH",
        "STALE_CANDIDATE_REVISION",
        "NOTHING_STAGED",
        "UNKNOWN_TRANSACTION",
        "NOT_RECOVERABLE",
        "INVALID_PROVIDER",
    }
)
"""The closed error-code vocabulary of the local shell surface."""

V2_SHELL_ERROR_MESSAGES = {
    "NO_LLM_BOUNDARY": (
        "no v2 LLM boundary is composed; the loop cannot run in this process"
    ),
    "UNKNOWN_RUN": "the run is unknown to this v2 control database",
    "UNKNOWN_CANDIDATE": "the candidate is unknown to this v2 control database",
    "RUN_CANDIDATE_MISMATCH": "the candidate does not belong to this run",
    "STALE_CANDIDATE_REVISION": "the candidate revision is stale",
    "NOTHING_STAGED": (
        "no staged content is bound to this run in this process; use "
        "durable recovery for cross-restart transactions"
    ),
    "UNKNOWN_TRANSACTION": "the transaction is unknown to this v2 control database",
    "NOT_RECOVERABLE": "the transaction is terminal and cannot be recovered",
    "INVALID_PROVIDER": "the provider name is not a closed identifier",
}
"""The bounded static message of every closed shell error."""


class V2ShellError(RuntimeError):
    """One closed local-shell failure (bounded code and static message)."""

    def __init__(self, code: str, message: str | None = None) -> None:
        if code not in V2_SHELL_ERROR_CODES:
            raise ValueError("unknown v2 shell error code")
        super().__init__(
            message
            if message is not None
            else V2_SHELL_ERROR_MESSAGES[code]
        )
        self.code = code


@dataclass(frozen=True, slots=True)
class V2RunSummaryV2:
    """The bounded projection of one run row."""

    run_id: str
    status: str
    phase: str | None
    revision: int


@dataclass(frozen=True, slots=True)
class V2RunStartOutcomeV2:
    """The bounded projection of one composed local run and its candidate."""

    run_id: str
    candidate_id: str
    candidate_revision: int
    loop_status: str
    stop_reason: str
    turns: int


@dataclass(frozen=True, slots=True)
class V2DisclosureGrantSummaryV2:
    """The bounded, non-revealing projection of one disclosure grant."""

    grant_id: str
    disclosure_id: str
    run_id: str
    status: str
    expires_at: str
    byte_budget: int
    consumed_bytes: int


class V2LocalShellPort(Protocol):
    """The domain surface the local CLI and WebUI compose against."""

    def recent_runs(self, limit: int = 50) -> Sequence[V2RunSummaryV2]: ...

    def run_detail(self, run_id: str) -> V2RunSummaryV2 | None: ...

    def candidate_revision(
        self, run_id: str, candidate_id: str
    ) -> int | None: ...

    def start_run(self, task: str) -> V2RunStartOutcomeV2: ...

    def create_writeback_approval(
        self, *, run_id: str, candidate_id: str, candidate_revision: int
    ) -> str: ...

    def request_writeback(
        self,
        *,
        run_id: str,
        candidate_id: str,
        candidate_revision: int,
        approval_id: str,
    ) -> WritebackOutcomeV2: ...

    def pending_transaction_ids(self) -> tuple[str, ...]: ...

    def recovery_preview(self, transaction_id: str) -> RecoveryPreviewV2: ...

    def recovery_apply(self, transaction_id: str) -> RecoveryOutcomeV2: ...

    def credential_status(self, provider: str) -> V2CredentialStatus: ...

    def disclosure_grant_summaries(
        self, limit: int = 100
    ) -> Sequence[V2DisclosureGrantSummaryV2]: ...


class _LocalControlPolicyV2(RelaxedPolicyV2):
    """The writeback policy of the local composition.

    Everything the base policy denies stays denied; additionally, any
    path inside the control-plane directory is denied for writes, so
    staged content can never replace the v2 control database or its
    journal even after an explicit approval.
    """

    def __init__(self, control_segments: tuple[str, ...]) -> None:
        self._control_segments = tuple(
            segment.casefold() for segment in control_segments
        )

    def evaluate(self, request) -> DecisionV2:  # type: ignore[override]
        if self._control_segments:
            relative = self._canonical_relative_path(request.path)
            if relative is not None:
                parts = [part.casefold() for part in relative.parts]
                prefix = list(self._control_segments)
                if parts[: len(prefix)] == prefix:
                    return DecisionV2.DENY
        return super().evaluate(request)


class V2LocalShell:
    """The local v2 services shell over one workspace and control root.

    ``llm_factory`` produces one fresh injectable LLM boundary per run
    (``None`` composes no LLM: ``start_run`` fails closed).  The
    credential port defaults to the deterministic in-memory provider —
    the B2 fake, process-local and never a real OS store.
    """

    def __init__(
        self,
        *,
        workspace: Path,
        control_root: Path | None = None,
        llm_factory: Callable[[], V2LLM] | None = None,
        credential_port: object | None = None,
        max_turns: int = 20,
    ) -> None:
        if not isinstance(workspace, Path):
            raise TypeError("workspace must be a Path")
        if not workspace.is_dir():
            raise ValueError("workspace must be an existing directory")
        if isinstance(max_turns, bool) or not isinstance(max_turns, int):
            raise ValueError("max_turns must be an integer")
        if max_turns < 1:
            raise ValueError("max_turns must be positive")
        self._workspace = workspace
        resolved_control = control_root if control_root is not None else (
            workspace / ".vespercode"
        )
        if not isinstance(resolved_control, Path):
            raise TypeError("control_root must be a Path")
        self._control_root_path = resolved_control
        self._llm_factory = llm_factory
        self._credential_port = (
            credential_port if credential_port is not None
            else InMemoryV2CredentialProvider()
        )
        self._harness = V2Harness(
            V2HarnessConfig(workspace, resolved_control, max_turns=max_turns)
        )
        control_segments = self._control_segments(workspace, resolved_control)
        self._writeback = V2WritebackService(
            self._harness.database,
            self._harness.disk_port,
            workspace=workspace,
            policy=_LocalControlPolicyV2(control_segments),
        )
        self._recovery = V2RecoveryService(
            self._harness.database, self._harness.disk_port
        )
        self._staged_by_run: dict[str, tuple[WriteOperationV2, ...]] = {}

    @staticmethod
    def _control_segments(
        workspace: Path, control_root: Path
    ) -> tuple[str, ...]:
        """The control root's segments relative to the workspace, if inside."""

        try:
            relative = control_root.resolve(strict=False).relative_to(
                workspace.resolve(strict=False)
            )
        except ValueError:
            return ()
        return tuple(part for part in relative.parts if part not in {".", ".."})

    @property
    def workspace(self) -> Path:
        return self._workspace

    @property
    def database_path(self) -> Path:
        """The v2 control database path of this composition."""

        return self._control_root_path / V2_DATABASE_FILENAME

    @property
    def database(self) -> V2Database:
        """The v2 control database (composition/test seam, read use only)."""

        return self._harness.database

    # ------------------------------------------------------------------
    # run projection
    # ------------------------------------------------------------------

    def recent_runs(self, limit: int = 50) -> tuple[V2RunSummaryV2, ...]:
        return tuple(
            V2RunSummaryV2(
                run_id=str(row["run_id"]),
                status=str(row["status"]),
                phase=None if row["phase"] is None else str(row["phase"]),
                revision=int(row["revision"]),
            )
            for row in self._harness.database.list_runs(limit)
        )

    def run_detail(self, run_id: str) -> V2RunSummaryV2 | None:
        row = self._harness.database.get_run(run_id)
        if row is None:
            return None
        return V2RunSummaryV2(
            run_id=str(row["run_id"]),
            status=str(row["status"]),
            phase=None if row["phase"] is None else str(row["phase"]),
            revision=int(row["revision"]),
        )

    def start_run(self, task: str) -> V2RunStartOutcomeV2:
        """Run the composed loop once and stage the candidate.

        Fails closed with ``NO_LLM_BOUNDARY`` when no LLM factory is
        composed — the v2 local integration never invents a provider
        transport.
        """

        if not isinstance(task, str) or not task:
            raise ValueError("task must be a non-empty string")
        if self._llm_factory is None:
            raise V2ShellError("NO_LLM_BOUNDARY")
        result = self._harness.run(task, self._llm_factory())
        identity = self._harness.stage_candidate(result.run_id)
        self._staged_by_run[result.run_id] = self._harness.staged_operations()
        return V2RunStartOutcomeV2(
            run_id=result.run_id,
            candidate_id=identity.candidate_id,
            candidate_revision=identity.revision,
            loop_status=result.loop.status,
            stop_reason=result.loop.stop_reason,
            turns=result.loop.turns,
        )

    def candidate_revision(
        self, run_id: str, candidate_id: str
    ) -> int | None:
        """The candidate's current revision, or None when not owned."""

        row = self._harness.database.get_candidate(candidate_id)
        if row is None or str(row["run_id"]) != run_id:
            return None
        return int(row["revision"])

    # ------------------------------------------------------------------
    # explicit writeback approval and apply
    # ------------------------------------------------------------------

    def create_writeback_approval(
        self, *, run_id: str, candidate_id: str, candidate_revision: int
    ) -> str:
        """Create one PENDING approval bound to the current candidate.

        Fail-closed order: the run must exist, the candidate must exist
        and belong to that run, and the candidate revision must be
        current — otherwise no approval row is written.  A race inside
        the database still fails closed through its own checks.
        """

        database = self._harness.database
        if database.get_run(run_id) is None:
            raise V2ShellError("UNKNOWN_RUN")
        candidate = database.get_candidate(candidate_id)
        if candidate is None:
            raise V2ShellError("UNKNOWN_CANDIDATE")
        if str(candidate["run_id"]) != run_id:
            raise V2ShellError("RUN_CANDIDATE_MISMATCH")
        if int(candidate["revision"]) != candidate_revision:
            raise V2ShellError("STALE_CANDIDATE_REVISION")
        try:
            return database.create_writeback_approval(
                run_id, candidate_id, candidate_revision
            )
        except V2DatabaseError as exc:
            message = str(exc).lower()
            if "mismatch" in message:
                raise V2ShellError("RUN_CANDIDATE_MISMATCH") from exc
            if "stale" in message:
                raise V2ShellError("STALE_CANDIDATE_REVISION") from exc
            raise

    def staged_operations(self, run_id: str) -> tuple[WriteOperationV2, ...]:
        """The staged operations bound to one run in this process (or none).

        A bounded projection for local previews: paths and action types,
        never file content.
        """

        if not isinstance(run_id, str):
            raise TypeError("run_id must be a string")
        return self._staged_by_run.get(run_id, ())

    def request_writeback(
        self,
        *,
        run_id: str,
        candidate_id: str,
        candidate_revision: int,
        approval_id: str,
    ) -> WritebackOutcomeV2:
        """Apply the run's staged operations behind the explicit approval.

        The operations come from the staging snapshot bound to this run
        in this process; a fresh process must use durable recovery
        instead (Route A keeps staged content process-local).
        """

        operations = self._staged_by_run.get(run_id)
        if not operations:
            raise V2ShellError("NOTHING_STAGED")
        request = WritebackRequestV2(
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_revision=candidate_revision,
            approval_id=approval_id,
            operations=operations,
        )
        return self._writeback.request_writeback(request)

    # ------------------------------------------------------------------
    # durable recovery
    # ------------------------------------------------------------------

    def pending_transaction_ids(self) -> tuple[str, ...]:
        return self._recovery.pending_transaction_ids()

    def recovery_preview(self, transaction_id: str) -> RecoveryPreviewV2:
        self._require_active_transaction(transaction_id)
        return self._recovery.preview(transaction_id)

    def recovery_apply(self, transaction_id: str) -> RecoveryOutcomeV2:
        self._require_active_transaction(transaction_id)
        return self._recovery.apply(transaction_id)

    def _require_active_transaction(self, transaction_id: str) -> None:
        row = self._harness.database.get_transaction(transaction_id)
        if row is None:
            raise V2ShellError("UNKNOWN_TRANSACTION")
        if str(row["state"]) not in ACTIVE_TRANSACTION_STATES:
            raise V2ShellError("NOT_RECOVERABLE")

    # ------------------------------------------------------------------
    # non-revealing credential / disclosure projections
    # ------------------------------------------------------------------

    def credential_status(self, provider: str) -> V2CredentialStatus:
        """The non-revealing credential status of one provider."""

        try:
            return self._credential_port.status(provider)  # type: ignore[attr-defined]
        except V2CredentialError as exc:
            raise V2ShellError("INVALID_PROVIDER") from exc

    def disclosure_grant_summaries(
        self, limit: int = 100
    ) -> tuple[V2DisclosureGrantSummaryV2, ...]:
        """The bounded, non-revealing disclosure grant projections."""

        return tuple(
            V2DisclosureGrantSummaryV2(
                grant_id=record.grant_id,
                disclosure_id=record.disclosure_id,
                run_id=record.run_id,
                status=record.status,
                expires_at=record.expires_at,
                byte_budget=record.byte_budget,
                consumed_bytes=record.consumed_bytes,
            )
            for record in self._harness.database.list_disclosure_grants(limit)
        )

    def close(self) -> None:
        self._harness.close()


__all__ = [
    "V2DisclosureGrantSummaryV2",
    "V2LocalShell",
    "V2LocalShellPort",
    "V2RunStartOutcomeV2",
    "V2RunSummaryV2",
    "V2ShellError",
    "V2_SHELL_ERROR_CODES",
]
