"""T30.1 legacy step 30.A: Demo-only immutable scenario/session/decision/step/
status/trace values.

Every Demo value is a closed frozen pydantic model (``extra="forbid"``) that
serializes to the exact §0.1 canonical bytes through ``to_canonical_bytes``.
The vocabulary is deliberately Demo-only: ``DemoRunStatus`` is the §4.2.1
public-Demo status set (never a formal ``RunStatus``), ``DemoDecision`` is the
closed simulated visitor choice that can never become a formal approval or
disclosure grant, and ``RunIdV1``/``TurnIdV1``/``RepositoryIdentityV1`` are
defined here only as the formal identity shapes that every Demo value must
reject — the Demo package imports no formal Run/turn/repository identity,
executor, adapter, session store, Web, disk, credential, Docker, recovery, or
persistence capability (GREEN-4 boundary).  Executor, shared-core sequencing,
session storage, Web behavior, local files, credentials, Docker, recovery,
persistence, and real providers remain out of scope (GREEN-4).
"""

from __future__ import annotations

from typing import Annotated, Any, Final, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.canonical.json_v1 import canonical_json_bytes
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import DigestV1
from vespercode.contracts.optional import AbsentV1, PresentV1

DemoRunStatus: TypeAlias = Literal[
    "DEMO_CREATED",
    "DEMO_RUNNING",
    "DEMO_WAITING_USER",
    "DEMO_COMPLETED",
    "DEMO_FAILED",
]
"""SPEC §4.2.1 public-Demo statuses; never a formal ``RunStatus``."""

DemoDecision: TypeAlias = Literal["APPROVE", "REJECT"]
"""The closed simulated visitor choice that only advances the fixed Demo
scenario and can never become a formal approval (SPEC §2.9/§4.9)."""

DemoInputKindV1: TypeAlias = Literal["FIXED_SOURCE", "FIXED_FAILURE", "FIXED_PATCH"]
"""The exact closed input kinds of the sole Mock scenario (card GREEN-2)."""

DemoOutcomeV1: TypeAlias = Literal["DENIED", "CHECK_FAILED", "REJECTED", "COMPLETED"]
"""The closed fixed-trace step outcomes of the sole Mock scenario."""


class DemoTypeIsolationError(Exception):
    """Closed rejection when a Demo value receives a direct formal
    Run/turn/repository identity; such identities must never enter Demo data
    (GREEN-1/AC-09).  Identities nested inside containers are rejected by the
    strict closed field types (ValidationError) before any field accepts them."""


class RunIdV1:
    """Formal run identity shape that Demo value types must never accept.

    Defined here (not imported) so the Demo package never imports formal
    Run identity modules; it exists only to be rejected (T30.1 boundary).
    """

    def __init__(self, value: str) -> None:
        if not isinstance(value, str) or value == "":
            raise ValueError("formal run identity must be a non-empty string")
        self.value = value


class TurnIdV1:
    """Formal turn identity shape that Demo value types must never accept."""

    def __init__(self, value: str) -> None:
        if not isinstance(value, str) or value == "":
            raise ValueError("formal turn identity must be a non-empty string")
        self.value = value


class RepositoryIdentityV1:
    """Formal repository identity shape that Demo value types must never accept."""

    def __init__(self, value: str) -> None:
        if not isinstance(value, str) or value == "":
            raise ValueError("formal repository identity must be a non-empty string")
        self.value = value


_FORMAL_IDENTITY_TYPES: Final = (RunIdV1, TurnIdV1, RepositoryIdentityV1)


def _require_non_empty(value: str) -> str:
    if value == "":
        raise ValueError("Demo value strings must be non-empty")
    return value


class _DemoValueV1(BaseModel):
    """Closed immutable Demo value: frozen, unknown fields forbidden, and one
    deterministic §0.1 canonical byte form for every closed variant.

    The before-validator is the smallest formal-identity rejection: any
    direct formal Run/turn/repository identity passed to a Demo value raises
    ``DemoTypeIsolationError`` before any field can accept it (GREEN-1/3);
    identities nested inside containers are still rejected by the strict
    closed field types.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="before")
    @classmethod
    def _reject_formal_identities(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for value in data.values():
                if isinstance(value, _FORMAL_IDENTITY_TYPES):
                    raise DemoTypeIsolationError(
                        "Demo value types cannot accept formal "
                        "Run/turn/repository identities"
                    )
        return data

    def to_canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump())


class DemoDecisionV1(_DemoValueV1):
    """One closed simulated visitor decision (SPEC §4.9/§7 ``DemoDecision``).

    It only advances the fixed Demo scenario and can never be converted into
    ``FinalWritebackApproval``, ``DisclosureGrant``, or a formal audit event.
    """

    demo_session_id: StrictStr
    subject_digest: DigestV1
    decision: DemoDecision
    created_at: CanonicalTimestampV1

    @field_validator("demo_session_id")
    @classmethod
    def _demo_session_id_must_be_non_empty(cls, value: str) -> str:
        return _require_non_empty(value)


OptionalDemoDecisionV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[DemoDecisionV1], Field(discriminator="kind")
]
"""SPEC §0.1 closed optional: ``ABSENT`` or ``PRESENT(DemoDecisionV1)``."""


class DemoSessionV1(_DemoValueV1):
    """One closed in-memory Demo session (SPEC §7 ``DemoSession`` row).

    A session is fully isolated from any formal ``Run``: it carries its own
    ``demo_session_id``, the fixed scenario version, a public-Demo status, a
    §0.1 state digest, and a canonical expiry; it never accepts a formal
    Run/turn/repository identity and never touches local files, credentials,
    Docker, persistence, or recovery.
    """

    demo_session_id: StrictStr
    scenario_version: Literal[1]
    status: DemoRunStatus
    state_digest: DigestV1
    expires_at: CanonicalTimestampV1

    @field_validator("demo_session_id")
    @classmethod
    def _demo_session_id_must_be_non_empty(cls, value: str) -> str:
        return _require_non_empty(value)


class DemoStepResultV1(_DemoValueV1):
    """One closed deterministic step result of the fixed Demo trace."""

    step_index: Annotated[int, Strict(), Field(ge=0)]
    action_label: StrictStr
    outcome: DemoOutcomeV1
    status: DemoRunStatus
    decision: OptionalDemoDecisionV1

    @field_validator("action_label")
    @classmethod
    def _action_label_must_be_non_empty(cls, value: str) -> str:
        return _require_non_empty(value)


class DemoTraceV1(_DemoValueV1):
    """The canonical fixed trace: ordered closed step results for one scenario."""

    scenario_id: StrictStr
    steps: tuple[DemoStepResultV1, ...]

    @field_validator("scenario_id")
    @classmethod
    def _scenario_id_must_be_non_empty(cls, value: str) -> str:
        return _require_non_empty(value)


class DemoScenarioV1(_DemoValueV1):
    """The closed fixed Mock scenario (SPEC §4.9/§6.4/§10.4).

    Only the exact fixed source, injected failure, expected patch, decisions,
    statuses, and canonical trace data are representable; prompts, URLs,
    uploads, provider, secret, filesystem, Docker, persistence, and recovery
    inputs are rejected because no such field exists (GREEN-2).
    """

    scenario_id: StrictStr
    scenario_version: Literal[1]
    input_kinds: tuple[DemoInputKindV1, ...]
    source: StrictStr
    injected_failure: StrictStr
    expected_patch: StrictStr
    decisions: tuple[DemoDecisionV1, ...]
    statuses: tuple[DemoRunStatus, ...]
    trace: DemoTraceV1

    @field_validator("scenario_id", "source", "injected_failure", "expected_patch")
    @classmethod
    def _fields_must_be_non_empty(cls, value: str) -> str:
        return _require_non_empty(value)
