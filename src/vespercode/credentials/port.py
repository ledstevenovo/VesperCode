"""T27.1 legacy step 27.A: the closed credential port vocabulary.

SPEC §4.8 closes the credential lifecycle to the single ``OPENAI``
provider, wraps hidden input in a non-serializable, non-comparable,
redacted secret object, and defines the verified store port whose
``probe_backend`` result is the only basis for any lifecycle operation.
Every value here is a closed frozen schema (SPEC §0.1): unknown fields
reject, optional values use the T05.1 ``ABSENT``/``PRESENT`` unions, and
scalar literals reject bool/float/string coercion at the parse boundary.
The service policy, the WinCred adapter, CLI/env/file input, Web forms,
network calls, Grant, and call counting remain out of scope (GREEN-4).
"""

from __future__ import annotations

from typing import Annotated, Any, Final, Literal, Protocol, SupportsIndex, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    StrictBool,
    field_validator,
    model_validator,
)

from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.optional import AbsentV1, PresentV1

OPENAI_PROVIDER: Final = "OPENAI"

CredentialErrorCodeV1: TypeAlias = Literal[
    "CREDENTIAL_INVALID",
    "CREDENTIAL_BACKEND_UNSAFE",
    "CREDENTIAL_STORE_FAILED",
    "CREDENTIAL_CLEAR_FAILED",
    "CREDENTIAL_MISSING",
]


def _reject_coerced_schema_version(value: object) -> object:
    """Reject bool/float/string spelling of the integer schema version 1.

    Pydantic lax mode coerces ``True`` and ``1.0`` into ``Literal[1]``;
    the closed parse boundary rejects every non-exact-int spelling
    (T06.3 port precedent, memory lesson: coercion at parse boundaries
    defeats type-contract defenses).
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("schema_version must be the decimal integer 1")
    return value


class CredentialContractError(ValueError):
    """Base class for every closed credential failure (SPEC §4.8 errors).

    Subclasses carry the exact closed ``error_code``; messages are
    bounded and static so no value or derivative can ever enter them.
    """

    error_code: CredentialErrorCodeV1


class CredentialProviderClosedError(CredentialContractError):
    """The provider is not the exact literal ``OPENAI``."""

    error_code: CredentialErrorCodeV1 = "CREDENTIAL_INVALID"


class CredentialSecretInvalidError(CredentialContractError):
    """Hidden input is not a non-empty string."""

    error_code: CredentialErrorCodeV1 = "CREDENTIAL_INVALID"


class CredentialBackendUnsafeError(CredentialContractError):
    """The resolved backend is not the verified Windows Credential Manager."""

    error_code: CredentialErrorCodeV1 = "CREDENTIAL_BACKEND_UNSAFE"


class CredentialStoreFailedError(CredentialContractError):
    """A store write/read failed; nothing authoritative was produced."""

    error_code: CredentialErrorCodeV1 = "CREDENTIAL_STORE_FAILED"


class CredentialClearFailedError(CredentialContractError):
    """A store clear failed; the entry may still exist."""

    error_code: CredentialErrorCodeV1 = "CREDENTIAL_CLEAR_FAILED"


class SecretCredentialV1(BaseModel):
    """Hidden-input secret wrapper: non-serializable, non-comparable, redacted.

    ``from_hidden_input`` is the sole public construction path; the hidden
    value lives in a private attribute so repr, status, logs, exceptions,
    and public results can never expose it or a derivative.  JSON, pickle,
    copy, and deepcopy serialization are disabled by contract (GREEN-1);
    ``reveal`` is the single accessor and is consumed only by the store
    port.  A wrapper with no hidden value (e.g. an empty ``model_validate``
    payload) is rejected at validation and fails closed in ``reveal``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    __hash__ = None  # type: ignore[assignment]

    _hidden_value: str | None = PrivateAttr(default=None)

    @classmethod
    def from_hidden_input(cls, value: object) -> SecretCredentialV1:
        """Wrap *value* after rejecting non-string or empty hidden input."""
        if not isinstance(value, str):
            raise CredentialSecretInvalidError("credential secret must be a string")
        if value == "":
            raise CredentialSecretInvalidError("credential secret must not be empty")
        return cls.model_construct(_hidden_value=value)

    @model_validator(mode="after")
    def _hidden_value_must_be_set(self) -> SecretCredentialV1:
        if self._hidden_value is None:
            raise ValueError("SecretCredentialV1 has no hidden value")
        return self

    def reveal(self) -> str:
        """The hidden value for the sole store port; never log or display it."""
        hidden = self._hidden_value
        if hidden is None:
            raise CredentialSecretInvalidError("credential secret is not available")
        return hidden

    def model_dump(self, *args: object, **kwargs: object) -> dict[str, object]:
        raise TypeError("SecretCredentialV1 is not serializable")

    def model_dump_json(self, *args: object, **kwargs: object) -> str:
        raise TypeError("SecretCredentialV1 is not serializable")

    def __reduce_ex__(self, protocol: SupportsIndex) -> str | tuple[Any, ...]:
        raise TypeError("SecretCredentialV1 is not serializable")

    def __copy__(self) -> SecretCredentialV1:
        raise TypeError("SecretCredentialV1 is not copyable")

    def __deepcopy__(self, memo: dict[int, Any] | None = None) -> SecretCredentialV1:
        raise TypeError("SecretCredentialV1 is not copyable")

    def __repr__(self) -> str:
        return "SecretCredentialV1([redacted])"

    __str__ = __repr__

    def __eq__(self, other: object) -> bool:
        raise TypeError("SecretCredentialV1 is not comparable")

    def __ne__(self, other: object) -> bool:
        raise TypeError("SecretCredentialV1 is not comparable")


OptionalTimestampV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[CanonicalTimestampV1], Field(discriminator="kind")
]


class CredentialStatusV1(BaseModel):
    """SPEC §4.8 status: configured flag, provider, and update time only.

    The status carries no secret, no secret length, and no secret
    derivative; ``updated_at`` uses the T05.1 closed optional union.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    provider: Literal["OPENAI"]
    configured: StrictBool
    updated_at: OptionalTimestampV1

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)


class CredentialErrorV1(BaseModel):
    """One closed typed credential failure (SPEC §4.8 error list)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    error_code: CredentialErrorCodeV1
    message: str = Field(max_length=200)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)


OptionalCredentialErrorV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[CredentialErrorV1], Field(discriminator="kind")
]


class CredentialMutationResultV1(BaseModel):
    """Service-level mutation result: STORED/CLEARED or a typed FAILED error.

    ``FAILED`` always carries a present typed error; successful mutations
    always carry the absent union (closed correlation, no nullable
    ambiguity).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    kind: Literal["STORED", "CLEARED", "FAILED"]
    error: OptionalCredentialErrorV1

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @model_validator(mode="after")
    def _kind_and_error_are_consistent(self) -> CredentialMutationResultV1:
        if self.kind == "FAILED" and self.error.kind == "ABSENT":
            raise ValueError("FAILED mutations must carry a typed error")
        if self.kind != "FAILED" and self.error.kind == "PRESENT":
            raise ValueError("successful mutations carry no error")
        return self


class CredentialStoreMutationV1(BaseModel):
    """Store-port mutation result: the write or delete landed."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    kind: Literal["STORED", "CLEARED"]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)


class CredentialMissingV1(BaseModel):
    """Store-port get-for-call result when nothing is configured."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    kind: Literal["MISSING"]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)


class CredentialBackendProbeV1(BaseModel):
    """The verified backend identity and capability probe result (27.B).

    A probe result exists only after the backend identity resolved to
    Windows Credential Manager and a real write/read/delete cycle
    succeeded; anything else raises ``CredentialBackendUnsafeError``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    backend_id: Literal["WINDOWS_CREDENTIAL_MANAGER"]
    capability: Literal["READ_WRITE_DELETE"]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)


class CredentialStorePortV1(Protocol):
    """The verified credential store port (SPEC §4.8, Task 27.A/27.B).

    ``probe_backend`` precedes every lifecycle operation: the service
    probes before delegating, and the WinCred store probes internally
    before each mutation or fresh get-for-call read.  The provider
    parameter is closed to the exact literal ``OPENAI``.
    """

    def probe_backend(self) -> CredentialBackendProbeV1: ...

    def set(
        self, provider: Literal["OPENAI"], secret: SecretCredentialV1
    ) -> CredentialStoreMutationV1: ...

    def get_for_call(
        self, provider: Literal["OPENAI"]
    ) -> SecretCredentialV1 | CredentialMissingV1: ...

    def status(self, provider: Literal["OPENAI"]) -> CredentialStatusV1: ...

    def clear(self, provider: Literal["OPENAI"]) -> CredentialStoreMutationV1: ...
