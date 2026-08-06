"""T26.2 legacy step 26.C: the explicit recovery service facade.

``RecoveryService.preview`` selects the workspace-bound non-terminal
transaction (the v0011 one-active-workspace index admits at most one)
and delegates to the read-only Task 26.B preview; ``apply`` delegates to
the Task 26.C apply service; ``has_unresolved_transaction`` is the
read-only recovery gate (AC-21: an UNRESOLVED transaction blocks new
runs).  This module owns no DDL, repository rules, or recovery
classification (GREEN-4).
"""

from __future__ import annotations


from src.vespercode.persistence.recovery_apply import (
    ApplyRecoveryV1,
    RecoveryApplyService,
    RecoveryResultV1,
)
from src.vespercode.persistence.recovery_preview import (
    RecoveryPreviewErrorV1,
    RecoveryPreviewService,
    RecoveryPreviewV1,
)
from src.vespercode.persistence.transaction import (
    PersistenceTransactionRepositoryV1,
)
from src.vespercode.workspace.identity_win32 import WorkspaceIdentityV1


class RecoveryService:
    """The explicit recovery entry point (CLI/WebUI composition)."""

    def __init__(
        self,
        *,
        transaction_repository: PersistenceTransactionRepositoryV1,
        preview_service: RecoveryPreviewService,
        apply_service: RecoveryApplyService,
    ) -> None:
        self._transactions = transaction_repository
        self._preview_service = preview_service
        self._apply_service = apply_service

    @property
    def transaction_repository(self) -> PersistenceTransactionRepositoryV1:
        """The owned persistence-transaction repository (evidence seam)."""
        return self._transactions

    def preview(self, workspace: WorkspaceIdentityV1) -> RecoveryPreviewV1:
        """Preview the unique workspace-bound non-terminal transaction.

        Selects the transaction bound to the sealed workspace identity
        (at most one active per workspace) and delegates only to the
        read-only Task 26.B preview; nothing is ever written.
        """
        transaction = self._transactions.find_active_by_workspace(workspace.digest)
        if transaction is None:
            raise RecoveryPreviewErrorV1(
                "TRANSACTION_NOT_FOUND",
                "no non-terminal transaction for this workspace",
            )
        return self._preview_service.preview_transaction(transaction.transaction_id)

    def apply(self, command: ApplyRecoveryV1) -> RecoveryResultV1:
        """Apply the bound recovery command (Task 26.C)."""
        return self._apply_service.apply(command)

    def has_unresolved_transaction(self, workspace_identity_digest: str) -> bool:
        """Read-only recovery gate: an UNRESOLVED transaction exists.

        While True, new runs for this workspace must be rejected
        (SPEC 4.6 / AC-21); only a service-proven COMMITTED or
        ROLLED_BACK terminal releases the gate.
        """
        return self._transactions.has_unresolved(workspace_identity_digest)
