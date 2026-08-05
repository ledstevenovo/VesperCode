"""T27.1 legacy step 27.A: the pure non-revealing credential lifecycle.

``CredentialService`` closes providers to ``OPENAI``, probes the verified
store port before every lifecycle operation, and maps backend/store
failures into the closed typed-result vocabulary of SPEC §4.8 with
bounded redacted messages.  It never prints, logs, serializes, or caches
any secret; ``get_for_call`` re-probes and re-reads on every call and
never reuses an earlier "configured" observation.  The WinCred adapter,
CLI/env/file input, Web forms, network calls, Grant, and call counting
remain out of scope (GREEN-4).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.credentials.port import (
    OPENAI_PROVIDER,
    CredentialContractError,
    CredentialErrorCodeV1,
    CredentialErrorV1,
    CredentialMutationResultV1,
    CredentialProviderClosedError,
    CredentialStatusV1,
    CredentialStorePortV1,
    SecretCredentialV1,
)

_ERROR_MESSAGES: dict[CredentialErrorCodeV1, str] = {
    "CREDENTIAL_INVALID": "credential input is invalid",
    "CREDENTIAL_BACKEND_UNSAFE": (
        "credential backend is not the verified Windows Credential Manager"
    ),
    "CREDENTIAL_STORE_FAILED": "credential store operation failed",
    "CREDENTIAL_CLEAR_FAILED": "credential store clear failed",
    "CREDENTIAL_MISSING": "no credential is configured",
}


class CredentialService:
    """Pure credential lifecycle policy over an injectable verified store."""

    def __init__(self, store: CredentialStorePortV1) -> None:
        self._store = store

    @staticmethod
    def _guard_provider(provider: str) -> None:
        if provider != OPENAI_PROVIDER:
            raise CredentialProviderClosedError(
                "credential provider is closed to OPENAI"
            )

    @staticmethod
    def _to_error(exc: CredentialContractError) -> CredentialErrorV1:
        return CredentialErrorV1(
            schema_version=1,
            error_code=exc.error_code,
            message=_ERROR_MESSAGES[exc.error_code],
        )

    def _mutate(
        self,
        provider: Literal["OPENAI"],
        success_kind: Literal["STORED", "CLEARED"],
        operation: Callable[[], object],
    ) -> CredentialMutationResultV1:
        """Probe, run one store mutation, and map failures to a typed result."""
        self._guard_provider(provider)
        try:
            self._store.probe_backend()
            operation()
        except CredentialContractError as exc:
            return CredentialMutationResultV1(
                schema_version=1,
                kind="FAILED",
                error=PresentV1[CredentialErrorV1](
                    kind="PRESENT", value=self._to_error(exc)
                ),
            )
        return CredentialMutationResultV1(
            schema_version=1,
            kind=success_kind,
            error=AbsentV1(kind="ABSENT"),
        )

    def set(
        self, provider: Literal["OPENAI"], secret: SecretCredentialV1
    ) -> CredentialMutationResultV1:
        """Probe the verified store, then store *secret* (SPEC §4.8 behaviors 2-3)."""
        return self._mutate(
            provider, "STORED", lambda: self._store.set(provider, secret)
        )

    def update(
        self, provider: Literal["OPENAI"], secret: SecretCredentialV1
    ) -> CredentialMutationResultV1:
        """Overwrite the existing entry with *secret* (SPEC §4.8 behavior 5)."""
        return self.set(provider, secret)

    def clear(self, provider: Literal["OPENAI"]) -> CredentialMutationResultV1:
        """Probe the verified store, then delete the entry (SPEC §4.8 behavior 5)."""
        return self._mutate(provider, "CLEARED", lambda: self._store.clear(provider))

    def status(self, provider: Literal["OPENAI"]) -> CredentialStatusV1:
        """Report configured/provider/update time only; unsafe backend raises."""
        self._guard_provider(provider)
        self._store.probe_backend()
        return self._store.status(provider)

    def get_for_call(
        self, provider: Literal["OPENAI"]
    ) -> SecretCredentialV1 | CredentialErrorV1:
        """Re-probe and re-read fresh on every call (SPEC §4.8 behavior 6).

        Missing, unsafe, and store failures become closed typed errors;
        a returned secret is never cached or reused.
        """
        self._guard_provider(provider)
        try:
            self._store.probe_backend()
            result = self._store.get_for_call(provider)
        except CredentialContractError as exc:
            return self._to_error(exc)
        if isinstance(result, SecretCredentialV1):
            return result
        return CredentialErrorV1(
            schema_version=1,
            error_code="CREDENTIAL_MISSING",
            message=_ERROR_MESSAGES["CREDENTIAL_MISSING"],
        )
