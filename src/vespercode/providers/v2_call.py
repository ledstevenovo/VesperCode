"""Route B / B2: the v2 provider call request/response boundary.

The v1 provider path (``profiles/endpoints.py``, the v1 CLI credential
flow, and the v1 release workflow) is digest-bound and remains
untouched read-only legacy; nothing here imports it, and no v1 CLI or
release path is turned into a v2 provider path.

The v2 provider call boundary is one deterministic service over three
injectable pieces: the control database (provider endpoint,
authorization, grant), the injectable credential port
(``credentials/v2_port.py``), and an injectable transport.  The
request and outcome records carry control IDs and revisions only.  The
credential never flows to the transport as a raw value: after the
atomic consume the service mints the provider-only call credential
(``V2ProviderCallCredential`` — redacted, non-comparable,
non-serializable, single-use, minted only behind the provider-call
reveal capability) and passes that handshake object to the one
transport call; the raw value materializes only inside the real
transport adapter's single call frame, through the separately minted
transport-reveal seam granted to exactly that module, exactly once,
and never enters a record, an outcome, an exception, a log line, or
a database row.

Call semantics (frozen for B2):

- every binding is checked before the credential or the transport is
  touched: the endpoint must exist, the request's provider/profile
  binding must match the endpoint's declaration, the authorization
  must exist and match the request's grant/run/request/endpoint, it
  must still be ``AUTHORIZED``, and the grant must still be ``ACTIVE``
  and unexpired (these are early diagnostics);
- the authoritative gate is the atomic consume
  (``consume_disclosure_authorization``): inside one SQLite
  transaction it revalidates the binding, the ``AUTHORIZED`` status,
  the grant's ``ACTIVE``/unexpired state as of the consume-time clock
  (so a revocation or an expiry crossing since the reads above
  rejects the call), and the endpoint/profile binding; the consume
  commits one-shot *before* the transport call, so a duplicate call
  can never double-call the provider (a failed call burns its
  authorization — there is no refund); a credential-port
  infrastructure failure (an unavailable or unsafe OS credential
  backend raising its closed store error, B4b-02C1) happens strictly
  before the consume and propagates loudly — it is never silently
  mapped to a business outcome and never burns the authorization;
- exactly one transport call happens; a provider error is never
  retried automatically;
- any transport exception or non-success response maps to the closed
  ``PROVIDER_CALL_FAILED`` error with a static message — the raw
  exception text is discarded and can never reach the outcome.

Credential handling (B4b-02C1 review fix): the service never hands a
raw value to the transport.  After the atomic consume it mints the
provider-only call credential (``V2ProviderCallCredential``) from the
configured wrapper behind the module-private reveal capability
(``credentials.v2_port._provider_reveal_capability``), which no public
API of the package exposes; ordinary direct calls to ``reveal`` are
rejected, minting requires the exact provider-call capability and a
real secret wrapper (a raw string can mint nothing), and a forged or
replayed handshake never opens.  The raw value materializes only
inside the real transport adapter's single call frame, through the
separately minted transport-reveal seam granted to exactly that
module, exactly once (the handshake is single-use).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol, runtime_checkable

from vespercode.credentials.v2_port import (
    V2CredentialError,
    V2CredentialSecret,
    _provider_reveal_capability,
)
from vespercode.governance.v2_disclosure import grant_is_expired

_MAX_IDENTIFIER_BYTES = 256
_PROVIDER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

PROVIDER_CALL_STATUSES_V2 = frozenset({"SUCCEEDED", "FAILED"})
"""The closed outcome statuses of one provider call."""

PROVIDER_CALL_ERROR_CODES_V2 = frozenset(
    {
        "CREDENTIAL_NOT_CONFIGURED",
        "ENDPOINT_NOT_FOUND",
        "PROFILE_MISMATCH",
        "AUTHORIZATION_NOT_FOUND",
        "AUTHORIZATION_BINDING_MISMATCH",
        "AUTHORIZATION_NOT_AUTHORIZED",
        "GRANT_NOT_ACTIVE",
        "PROVIDER_CALL_FAILED",
    }
)
"""The closed failure codes of one provider call."""

PROVIDER_CALL_FAILED_MESSAGE = "the provider call failed; no retry is attempted"

_CALL_MESSAGES: dict[str, str] = {
    "SUCCEEDED": "the provider call completed",
    "CREDENTIAL_NOT_CONFIGURED": "no credential is configured for the provider",
    "ENDPOINT_NOT_FOUND": "the provider endpoint is unknown",
    "PROFILE_MISMATCH": (
        "the request does not match the endpoint's provider or profile binding"
    ),
    "AUTHORIZATION_NOT_FOUND": "no disclosure authorization exists for the request",
    "AUTHORIZATION_BINDING_MISMATCH": (
        "the authorization does not match the request's grant, run, "
        "request, or endpoint"
    ),
    "AUTHORIZATION_NOT_AUTHORIZED": (
        "the authorization is not in the AUTHORIZED state"
    ),
    "GRANT_NOT_ACTIVE": "the grant is not active",
    "PROVIDER_CALL_FAILED": PROVIDER_CALL_FAILED_MESSAGE,
}


def _identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    if len(value.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
        raise ValueError(f"{field_name} is too long")
    return value


def _provider_name(value: str) -> str:
    if not isinstance(value, str) or not _PROVIDER_NAME_PATTERN.match(value):
        raise ValueError("provider must be a short identifier")
    return value


def _revision(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


@dataclass(frozen=True, slots=True)
class ProviderCallRequestV2:
    """One provider call request: control-plane references only.

    The request names the authorization it consumes and the endpoint it
    targets, and repeats the grant/run/request bindings plus the
    provider and reference profile id/revision the caller believes it
    is using — the service re-checks all of them.  It never carries a
    credential value, a payload body, or a digest.
    """

    request_id: str
    authorization_id: str
    grant_id: str
    run_id: str
    endpoint_id: str
    provider: str
    reference_profile_id: str
    reference_profile_revision: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "request_id", _identifier(self.request_id, "request_id")
        )
        object.__setattr__(
            self,
            "authorization_id",
            _identifier(self.authorization_id, "authorization_id"),
        )
        object.__setattr__(self, "grant_id", _identifier(self.grant_id, "grant_id"))
        object.__setattr__(self, "run_id", _identifier(self.run_id, "run_id"))
        object.__setattr__(
            self, "endpoint_id", _identifier(self.endpoint_id, "endpoint_id")
        )
        object.__setattr__(self, "provider", _provider_name(self.provider))
        object.__setattr__(
            self,
            "reference_profile_id",
            _identifier(self.reference_profile_id, "reference_profile_id"),
        )
        object.__setattr__(
            self,
            "reference_profile_revision",
            _revision(
                self.reference_profile_revision, "reference_profile_revision"
            ),
        )


@dataclass(frozen=True, slots=True)
class ProviderCallResponseV2:
    """The transport-facing response: a status and nothing else.

    A real transport adapter normalizes its provider response into this
    closed shape; a ``FAILED`` response never carries provider payload
    text into the harness (the service discards everything but the
    status and maps it to the closed failure).
    """

    status: str

    def __post_init__(self) -> None:
        if self.status not in PROVIDER_CALL_STATUSES_V2:
            raise ValueError(
                f"response status must be one of {sorted(PROVIDER_CALL_STATUSES_V2)}"
            )


@dataclass(frozen=True, slots=True)
class ProviderCallOutcomeV2:
    """The sanitized outcome of one provider call.

    ``error_code`` is ``None`` exactly for ``SUCCEEDED``; ``message`` is
    always the closed static message of the code, so no provider
    exception text, secret, or payload can ever enter the outcome.
    """

    request_id: str
    status: str
    error_code: str | None
    message: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "request_id", _identifier(self.request_id, "request_id")
        )
        if self.status not in PROVIDER_CALL_STATUSES_V2:
            raise ValueError(
                f"status must be one of {sorted(PROVIDER_CALL_STATUSES_V2)}"
            )
        if self.status == "SUCCEEDED":
            if self.error_code is not None:
                raise ValueError("SUCCEEDED outcomes carry no error code")
        else:
            if self.error_code not in PROVIDER_CALL_ERROR_CODES_V2:
                raise ValueError(
                    "error_code must be one of "
                    f"{sorted(PROVIDER_CALL_ERROR_CODES_V2)}"
                )
        expected = _CALL_MESSAGES["SUCCEEDED" if self.status == "SUCCEEDED" else self.error_code]
        if self.message != expected:
            raise ValueError(
                "outcome message must be the closed static message of its code"
            )


class _TransportRevealCapability:
    """The private transport-reveal capability, minted once by this module.

    Only the real transport adapter (``providers/v2_transport.py``)
    obtains the single instance, through the module-private friend seam
    ``_transport_reveal_capability``.  ``V2ProviderCallCredential.
    reveal_for_transport`` accepts this exact object and nothing else —
    the check is by object identity, so a missing argument, a
    look-alike value, or even a fresh instance of this private class
    rejects, and the provider-call mint capability never unlocks it.
    No public API of the package exposes the capability.
    """

    __slots__ = ()


_TRANSPORT_REVEAL_CAPABILITY = _TransportRevealCapability()


def _transport_reveal_capability() -> _TransportRevealCapability:
    """Friend seam for ``providers.v2_transport`` only (private by spelling).

    Importing this private function is the single documented way for the
    real transport adapter to obtain the transport-reveal capability; no
    public name of this module yields it, and it never unlocks the
    wrapper's own ``reveal`` or ``reveal_for_storage``.
    """

    return _TRANSPORT_REVEAL_CAPABILITY


class _MintedState:
    """The private minted-state sentinel (checked by object identity)."""

    __slots__ = ()


_MINTED_STATE = _MintedState()


class V2ProviderCallCredential:
    """The provider-only call credential handshake object (review fix).

    The B4b-02C1 main-thread review rejected the first cut's
    raw-string transport API: any caller holding a raw secret could
    drive the real transport adapter directly, bypassing the service's
    authorization/consume boundary.  This handshake object closes that
    shape.  It is minted only by the provider call service, only
    behind the provider-call reveal capability, only from a real
    secret wrapper — so a caller holding a raw string can neither mint
    one nor pass the real adapter's credential check.  Opening it
    requires the separately minted transport-reveal capability handed
    only to the real transport adapter, happens exactly once (single
    use), and the object is redacted, non-comparable, non-serializable,
    and non-copyable; a forged ``__new__`` instance never opens.
    """

    __slots__ = ("_secret", "_minted_state")

    def __init__(self, secret: V2CredentialSecret, capability: object) -> None:
        if capability is not _provider_reveal_capability():
            raise V2CredentialError(
                "minting requires the provider call boundary capability",
                error_code="CREDENTIAL_REVEAL_FORBIDDEN",
            )
        if not isinstance(secret, V2CredentialSecret):
            raise V2CredentialError(
                "the call credential requires a real secret wrapper",
                error_code="CREDENTIAL_REVEAL_FORBIDDEN",
            )
        object.__setattr__(self, "_secret", secret)
        object.__setattr__(self, "_minted_state", _MINTED_STATE)

    def reveal_for_transport(self, capability: object) -> str:
        """Open the credential exactly once, only for the transport adapter.

        ``capability`` must be the exact transport-reveal capability
        minted by this module and obtained through the private friend
        seam used only by ``providers/v2_transport`` — any other value
        (including the provider-call mint capability and the storage
        capability), a fresh look-alike instance, or a second call on
        an already-opened credential rejects with the closed error.
        The returned value exists only inside the real transport
        adapter's single call frame and never enters a record, an
        outcome, an exception, a log line, or a database row.
        """

        if capability is not _TRANSPORT_REVEAL_CAPABILITY:
            raise V2CredentialError(
                "the transport reveal requires the transport adapter "
                "capability",
                error_code="CREDENTIAL_REVEAL_FORBIDDEN",
            )
        if getattr(self, "_minted_state", None) is not _MINTED_STATE:
            raise V2CredentialError(
                "the call credential was not minted by the provider call "
                "boundary",
                error_code="CREDENTIAL_REVEAL_FORBIDDEN",
            )
        secret = getattr(self, "_secret", None)
        if not isinstance(secret, V2CredentialSecret):
            raise V2CredentialError(
                "the call credential was not minted by the provider call "
                "boundary",
                error_code="CREDENTIAL_REVEAL_FORBIDDEN",
            )
        # Single use: burn the minted state before the one reveal, so a
        # retained or replayed credential never yields a second value.
        object.__setattr__(self, "_minted_state", None)
        object.__setattr__(self, "_secret", None)
        return secret.reveal(_provider_reveal_capability())

    def __repr__(self) -> str:
        return "V2ProviderCallCredential([redacted])"

    __str__ = __repr__

    def __eq__(self, other: object) -> bool:
        raise TypeError("V2ProviderCallCredential is not comparable")

    def __ne__(self, other: object) -> bool:
        raise TypeError("V2ProviderCallCredential is not comparable")

    def __reduce__(self) -> object:
        raise TypeError("V2ProviderCallCredential is not serializable")

    def __reduce_ex__(self, protocol: object) -> object:
        raise TypeError("V2ProviderCallCredential is not serializable")

    def __copy__(self) -> "V2ProviderCallCredential":
        raise TypeError("V2ProviderCallCredential is not copyable")

    def __deepcopy__(
        self, memo: dict[int, object] | None = None
    ) -> "V2ProviderCallCredential":
        raise TypeError("V2ProviderCallCredential is not copyable")


@runtime_checkable
class V2ProviderTransport(Protocol):
    """The injectable provider transport edge.

    ``call`` receives the control-plane request and the provider-only
    call credential (``V2ProviderCallCredential``) — never a raw
    credential value; the handshake object opens only inside the real
    transport adapter's single call frame, through the transport-reveal
    seam, exactly once — and returns a closed response.  Tests inject
    deterministic fakes; the real adapter
    (``providers/v2_transport.py``) is the production implementation
    behind this protocol.
    """

    def call(
        self,
        request: ProviderCallRequestV2,
        credential: V2ProviderCallCredential,
    ) -> ProviderCallResponseV2:
        ...


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


class V2ProviderCallService:
    """One-call, no-retry provider boundary over the control database.

    ``database`` is a ``V2Database``; ``credential_port`` implements
    ``V2CredentialProviderPort``; ``transport`` implements
    ``V2ProviderTransport``; ``clock`` (injectable for deterministic
    tests) yields the current time for the grant expiry check.
    """

    def __init__(
        self,
        database: object,
        credential_port: object,
        transport: V2ProviderTransport,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if database is None or credential_port is None or transport is None:
            raise ValueError(
                "the provider call service requires a database, a "
                "credential port, and a transport"
            )
        self._database = database
        self._credentials = credential_port
        self._transport = transport
        self._clock = clock if clock is not None else _default_clock

    def call(self, request: ProviderCallRequestV2) -> ProviderCallOutcomeV2:
        """Perform exactly one provider call for an authorized request."""

        if not isinstance(request, ProviderCallRequestV2):
            raise ValueError("request must be a ProviderCallRequestV2")

        endpoint = self._database.get_provider_endpoint(request.endpoint_id)
        if endpoint is None:
            return self._failed(request, "ENDPOINT_NOT_FOUND")
        if (
            endpoint.provider != request.provider
            or endpoint.reference_profile_id != request.reference_profile_id
            or endpoint.reference_profile_revision != request.reference_profile_revision
        ):
            return self._failed(request, "PROFILE_MISMATCH")

        authorization = self._database.get_disclosure_authorization(
            request.authorization_id
        )
        if authorization is None:
            return self._failed(request, "AUTHORIZATION_NOT_FOUND")
        if (
            authorization.grant_id != request.grant_id
            or authorization.run_id != request.run_id
            or authorization.request_id != request.request_id
            or authorization.endpoint_id != request.endpoint_id
        ):
            return self._failed(request, "AUTHORIZATION_BINDING_MISMATCH")
        if authorization.status != "AUTHORIZED":
            return self._failed(request, "AUTHORIZATION_NOT_AUTHORIZED")

        grant = self._database.get_disclosure_grant(request.grant_id)
        if grant is None:
            return self._failed(request, "AUTHORIZATION_BINDING_MISMATCH")
        if grant.status != "ACTIVE" or grant_is_expired(grant, self._clock()):
            return self._failed(request, "GRANT_NOT_ACTIVE")
        if (
            grant.reference_profile_id != endpoint.reference_profile_id
            or grant.reference_profile_revision != endpoint.reference_profile_revision
        ):
            return self._failed(request, "PROFILE_MISMATCH")

        secret = self._credentials.get_for_call(request.provider)
        if secret is None:
            return self._failed(request, "CREDENTIAL_NOT_CONFIGURED")

        # The authoritative gate: the consume revalidates the binding,
        # the AUTHORIZED status, the grant's ACTIVE/unexpired state
        # (as of the consume-time clock, so a revocation or an expiry
        # crossing since the reads above rejects here), and the
        # endpoint/profile binding, atomically.  A duplicate call can
        # never double-call the provider because the one-shot consume
        # commits before the transport call; a failed provider call
        # burns its authorization — there is no refund and no retry.
        consume_outcome = self._database.consume_disclosure_authorization(
            authorization_id=request.authorization_id,
            grant_id=request.grant_id,
            run_id=request.run_id,
            request_id=request.request_id,
            now=self._clock(),
        )
        if consume_outcome.kind == "GRANT_NOT_ACTIVE":
            return self._failed(request, "GRANT_NOT_ACTIVE")
        if consume_outcome.kind != "CONSUMED":
            return self._failed(request, "AUTHORIZATION_NOT_AUTHORIZED")

        try:
            # The single sanctioned mint: the raw value still does not
            # exist anywhere — the handshake object carries only the
            # wrapper, and only the transport adapter's own frame opens
            # it, exactly once, through the transport-reveal seam.
            credential = V2ProviderCallCredential(
                secret, _provider_reveal_capability()
            )
            response = self._transport.call(request, credential)
        except Exception:
            # The raw provider exception is discarded: it may carry the
            # credential or provider details and must never reach the
            # outcome.  No retry is attempted.
            return self._failed(request, "PROVIDER_CALL_FAILED")
        if not isinstance(response, ProviderCallResponseV2):
            return self._failed(request, "PROVIDER_CALL_FAILED")
        if response.status != "SUCCEEDED":
            return self._failed(request, "PROVIDER_CALL_FAILED")
        return ProviderCallOutcomeV2(
            request_id=request.request_id,
            status="SUCCEEDED",
            error_code=None,
            message=_CALL_MESSAGES["SUCCEEDED"],
        )

    def _failed(
        self, request: ProviderCallRequestV2, error_code: str
    ) -> ProviderCallOutcomeV2:
        return ProviderCallOutcomeV2(
            request_id=request.request_id,
            status="FAILED",
            error_code=error_code,
            message=_CALL_MESSAGES[error_code],
        )


__all__ = (
    "PROVIDER_CALL_ERROR_CODES_V2",
    "PROVIDER_CALL_FAILED_MESSAGE",
    "PROVIDER_CALL_STATUSES_V2",
    "ProviderCallOutcomeV2",
    "ProviderCallRequestV2",
    "ProviderCallResponseV2",
    "V2ProviderCallCredential",
    "V2ProviderCallService",
    "V2ProviderTransport",
)
