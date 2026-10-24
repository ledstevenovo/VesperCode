"""Route B / B2 (+ B4b-02C1): the injectable v2 credential provider port.

The v1 credential plane (``credentials/port.py``,
``credentials/service.py``, ``credentials/wincred_store.py``) is
pydantic-bound, closed to the single ``OPENAI`` provider, and backed by
the verified Windows Credential Manager; it remains untouched
read-only legacy and nothing here imports it.

The v2 port is standard-library only and provider-agnostic.  Hidden
input is wrapped in a non-comparable, non-serializable, redacted secret
object whose two accessors are capability-gated: ``reveal`` requires
the exact reveal capability minted once by this module — handed only
to the provider call boundary (``providers/v2_call.py``) through a
module-private friend seam — and ``reveal_for_storage`` requires the
separately minted storage capability — handed only to the OS
credential adapter (``credentials/v2_os_store.py``) — so the raw
value exists in exactly two sanctioned frames: the one provider
transport call frame, and the OS-store write frame between the
storage extraction and the backend write.  Neither capability appears
on any public API of the package, and the two are never
interchangeable.  ``set``/``clear``/``status`` never project the
secret, its length, or any derivative (status is provider, configured
flag, and update time only), and ``get_for_call`` is the only
call-boundary projection.  ``InMemoryV2CredentialProvider`` is the
deterministic fake used by the offline tests and the local
composition; ``credentials/v2_os_store.py`` (B4b-02C1) is the
production OS-backed implementation behind the same port.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

_PROVIDER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class V2CredentialError(ValueError):
    """Fail-closed rejection at the v2 credential port boundary."""

    def __init__(self, message: str, *, error_code: str = "CREDENTIAL_INVALID") -> None:
        super().__init__(message)
        self.error_code = error_code


def _provider_name(value: str) -> str:
    if not isinstance(value, str) or not _PROVIDER_NAME_PATTERN.match(value):
        raise V2CredentialError(
            "provider name must be a short identifier",
            error_code="CREDENTIAL_PROVIDER_INVALID",
        )
    return value


class _RevealCapability:
    """The private reveal capability, minted once by this module.

    Only the provider call boundary (``providers/v2_call.py``) obtains
    the single instance, through the module-private friend seam
    ``_provider_reveal_capability``.  ``V2CredentialSecret.reveal``
    accepts this exact object and nothing else — a missing argument, a
    look-alike value, or even a fresh instance of this private class is
    rejected, because the check is by object identity.  No public API
    of this module exposes the capability, so ordinary direct use of a
    secret wrapper cannot obtain the raw value.
    """

    __slots__ = ()


_REVEAL_CAPABILITY = _RevealCapability()


def _provider_reveal_capability() -> _RevealCapability:
    """Friend seam for ``providers.v2_call`` only (private by spelling).

    Importing this private function is the single documented way for
    the provider call boundary to obtain the reveal capability; no
    public name of this module yields it.
    """

    return _REVEAL_CAPABILITY


class _StorageCapability:
    """The private storage-write capability, minted once by this module.

    Only the OS credential adapter (``credentials/v2_os_store.py``)
    obtains the single instance, through the module-private friend seam
    ``_storage_reveal_capability``.  ``V2CredentialSecret.reveal_for_storage``
    accepts this exact object and nothing else — the same
    object-identity check as the provider-call reveal, and the two
    capabilities are never interchangeable: a real OS store must
    receive the raw value to persist it, and that storage write frame
    is the one other sanctioned place the raw value exists.
    """

    __slots__ = ()


_STORAGE_CAPABILITY = _StorageCapability()


def _storage_reveal_capability() -> _StorageCapability:
    """Friend seam for ``credentials.v2_os_store`` only (private by spelling).

    Importing this private function is the single documented way for
    the OS credential adapter to obtain the storage-write capability;
    no public name of this module yields it, and it never unlocks
    ``reveal``.
    """

    return _STORAGE_CAPABILITY


class V2CredentialSecret:
    """Hidden-input secret wrapper: non-comparable, non-serializable, redacted.

    ``from_hidden_input`` is the sole public construction path; the
    hidden value lives in a private slot so repr, status, logs,
    exceptions, and public results can never expose it or a derivative.
    Two accessors exist and both are capability-gated: ``reveal``
    (the provider-call reveal, granted only to the provider call
    boundary) and ``reveal_for_storage`` (the OS-store write reveal,
    granted only to the OS credential adapter) — so arbitrary code
    holding a wrapper cannot call either in any ordinary way.  The
    raw value exists only inside the provider transport call frame and
    the OS-store write frame, and never enters a record, an outcome,
    an exception, a log line, or a database row.
    """

    __slots__ = ("_hidden",)

    def __init__(self, hidden: str) -> None:
        if not isinstance(hidden, str) or not hidden:
            raise V2CredentialError("credential secret is not available")
        object.__setattr__(self, "_hidden", hidden)

    @classmethod
    def from_hidden_input(cls, value: object) -> "V2CredentialSecret":
        """Wrap *value* after rejecting non-string or empty hidden input."""

        if not isinstance(value, str):
            raise V2CredentialError("credential secret must be a string")
        if value == "":
            raise V2CredentialError("credential secret must not be empty")
        return cls(value)

    def reveal(self, capability: object) -> str:
        """The hidden value, only for the provider call boundary.

        ``capability`` must be the exact capability object minted by
        this module and obtained through the private friend seam; any
        other value — including a missing argument or a look-alike
        instance — rejects with a closed error, so direct ordinary use
        of a ``V2CredentialSecret`` cannot obtain the raw secret.
        """

        if capability is not _REVEAL_CAPABILITY:
            raise V2CredentialError(
                "reveal requires the provider call boundary capability",
                error_code="CREDENTIAL_REVEAL_FORBIDDEN",
            )
        return self._require_hidden()

    def reveal_for_storage(self, capability: object) -> str:
        """The hidden value, only for the OS credential adapter's write path.

        ``capability`` must be the exact storage capability object
        minted by this module and obtained through the private friend
        seam used only by ``credentials/v2_os_store`` — the provider
        call capability is a different object and never unlocks this
        accessor.  The returned value exists only inside the storage
        write frame, between this extraction and the backend write,
        and never enters the control database, a log line, an outcome,
        or any other projection.
        """

        if capability is not _STORAGE_CAPABILITY:
            raise V2CredentialError(
                "reveal_for_storage requires the OS store capability",
                error_code="CREDENTIAL_REVEAL_FORBIDDEN",
            )
        return self._require_hidden()

    def _require_hidden(self) -> str:
        hidden = getattr(self, "_hidden", None)
        if not isinstance(hidden, str) or not hidden:
            raise V2CredentialError("credential secret is not available")
        return hidden

    def __repr__(self) -> str:
        return "V2CredentialSecret([redacted])"

    __str__ = __repr__

    def __eq__(self, other: object) -> bool:
        raise TypeError("V2CredentialSecret is not comparable")

    def __ne__(self, other: object) -> bool:
        raise TypeError("V2CredentialSecret is not comparable")

    def __reduce__(self) -> "str | tuple[Any, ...]":
        raise TypeError("V2CredentialSecret is not serializable")

    def __reduce_ex__(self, protocol: object) -> "str | tuple[Any, ...]":
        raise TypeError("V2CredentialSecret is not serializable")

    def __copy__(self) -> "V2CredentialSecret":
        raise TypeError("V2CredentialSecret is not copyable")

    def __deepcopy__(
        self, memo: dict[int, object] | None = None
    ) -> "V2CredentialSecret":
        raise TypeError("V2CredentialSecret is not copyable")


@dataclass(frozen=True, slots=True)
class V2CredentialStatus:
    """The non-revealing credential status of one provider.

    Carries the provider name, a configured flag, and the last update
    time only — no secret, no secret length, and no secret derivative.
    """

    provider: str
    configured: bool
    updated_at: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _provider_name(self.provider))
        if not isinstance(self.configured, bool):
            raise V2CredentialError("configured must be a boolean")
        if self.updated_at is not None and (
            not isinstance(self.updated_at, str) or not self.updated_at
        ):
            raise V2CredentialError("updated_at must be a non-empty timestamp or None")


@dataclass(frozen=True, slots=True)
class V2CredentialMutation:
    """The redacted result of one credential store mutation."""

    kind: str
    provider: str

    def __post_init__(self) -> None:
        if self.kind not in ("STORED", "CLEARED"):
            raise V2CredentialError("kind must be 'STORED' or 'CLEARED'")
        object.__setattr__(self, "provider", _provider_name(self.provider))


@runtime_checkable
class V2CredentialProviderPort(Protocol):
    """The injectable credential provider port.

    ``set``/``clear``/``status`` never project the secret;
    ``get_for_call`` is the only call-boundary projection and returns
    the wrapper (or ``None`` when nothing is configured).  The raw
    value leaves the wrapper only through ``reveal``, which only the
    provider call boundary consumes.
    """

    def set(
        self, provider: str, secret: V2CredentialSecret
    ) -> V2CredentialMutation: ...

    def get_for_call(self, provider: str) -> V2CredentialSecret | None: ...

    def status(self, provider: str) -> V2CredentialStatus: ...

    def clear(self, provider: str) -> V2CredentialMutation: ...


def _now_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class InMemoryV2CredentialProvider:
    """Deterministic in-memory v2 credential provider (B2 fake).

    Holds wrapped secrets per provider name and implements the port
    with safe set/get/clear/status semantics: the secret never leaves
    except through ``get_for_call``'s wrapper, and the status
    projection reports only the provider, the configured flag, and the
    update time.  No real OS credential store is touched; the real
    integration is out of scope for B2.
    """

    def __init__(self) -> None:
        self._secrets: dict[str, V2CredentialSecret] = {}
        self._updated_at: dict[str, str] = {}

    def set(self, provider: str, secret: V2CredentialSecret) -> V2CredentialMutation:
        name = _provider_name(provider)
        if not isinstance(secret, V2CredentialSecret):
            raise V2CredentialError("secret must be a V2CredentialSecret")
        self._secrets[name] = secret
        self._updated_at[name] = _now_timestamp()
        return V2CredentialMutation("STORED", name)

    def get_for_call(self, provider: str) -> V2CredentialSecret | None:
        name = _provider_name(provider)
        return self._secrets.get(name)

    def status(self, provider: str) -> V2CredentialStatus:
        name = _provider_name(provider)
        return V2CredentialStatus(
            provider=name,
            configured=name in self._secrets,
            updated_at=self._updated_at.get(name),
        )

    def clear(self, provider: str) -> V2CredentialMutation:
        name = _provider_name(provider)
        self._secrets.pop(name, None)
        self._updated_at[name] = _now_timestamp()
        return V2CredentialMutation("CLEARED", name)


__all__ = (
    "InMemoryV2CredentialProvider",
    "V2CredentialError",
    "V2CredentialMutation",
    "V2CredentialProviderPort",
    "V2CredentialSecret",
    "V2CredentialStatus",
)
