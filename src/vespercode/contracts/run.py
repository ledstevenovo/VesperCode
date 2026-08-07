"""T05.1 legacy step 5.B: closed Run state/phase/wait/limit vocabulary.

``RunStateV1`` composes the §4.2.1 status with a closed optional phase so
``RUNNING`` requires its exact phase and every other status carries an
explicit ``ABSENT``; ``WaitContextV1`` binds each wait kind to its exact
source phase; ``WaitDecisionV1`` binds wait/run/kind/subject/event/time
with a closed APPROVE/REJECT choice (SPEC AC-27); ``RunLimitsV1`` pins
every §4.1 limit inside the built-in hard bounds.  Lifecycle transitions,
repositories, decision services, and clock behavior remain out of scope
(GREEN-4).
"""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import DigestV1
from vespercode.contracts.optional import AbsentV1, PresentV1

RunStatus: TypeAlias = Literal[
    "CREATED",
    "RUNNING",
    "WAITING_USER",
    "RECOVERY_REQUIRED",
    "SUCCEEDED",
    "STOPPED",
]
"""SPEC §4.2.1 formal run statuses (Demo statuses are not formal)."""

RunPhase: TypeAlias = Literal[
    "PREFLIGHT",
    "BASELINE",
    "AGENT_LOOP",
    "FORMAL_VALIDATION",
    "PERSISTENCE",
]
"""SPEC §4.2.1 formal run phases."""

WaitKind: TypeAlias = Literal["DISCLOSURE_GRANT", "FINAL_WRITEBACK"]
"""SPEC §4.2.7 wait kinds."""

WaitDecisionChoiceV1: TypeAlias = Literal["APPROVE", "REJECT"]
"""The closed user decision for one wait (SPEC §4.2.7/AC-27)."""

OptionalRunPhaseV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[RunPhase], Field(discriminator="kind")
]
"""Closed optional phase: ``ABSENT`` unless the state is RUNNING."""


def _require_non_empty_identifier(value: str) -> str:
    """Identity fields must never be empty; empty ids cannot bind."""
    if value == "":
        raise ValueError("identifiers must be non-empty")
    return value


class RunStateV1(BaseModel):
    """One closed formal run state: status plus exact phase presence."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    status: RunStatus
    phase: OptionalRunPhaseV1

    @model_validator(mode="after")
    def _require_exact_phase(self) -> RunStateV1:
        if self.status == "RUNNING" and self.phase.kind != "PRESENT":
            raise ValueError("RUNNING requires its exact phase")
        if self.status != "RUNNING" and self.phase.kind != "ABSENT":
            raise ValueError("non-RUNNING states must carry an ABSENT phase")
        return self


class RunLimitsV1(BaseModel):
    """SPEC §4.1 limits: every value may only tighten the built-in caps."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    max_turns: Annotated[int, Strict(), Field(ge=1, le=20)]
    max_llm_calls: Annotated[int, Strict(), Field(ge=1, le=20)]
    max_run_wall_clock_seconds: Annotated[int, Strict(), Field(ge=1, le=900)]
    user_wait_timeout_seconds: Annotated[int, Strict(), Field(ge=1, le=300)]
    tool_timeout_seconds: Annotated[int, Strict(), Field(ge=1, le=60)]
    target_check_timeout_seconds: Annotated[int, Strict(), Field(ge=1, le=120)]
    full_check_timeout_seconds: Annotated[int, Strict(), Field(ge=1, le=300)]
    baseline_timeout_seconds: Annotated[int, Strict(), Field(ge=1, le=600)]
    formal_validation_timeout_seconds: Annotated[int, Strict(), Field(ge=1, le=600)]


class WaitContextV1(BaseModel):
    """SPEC §4.2.7 wait context bound to its exact kind/phase and order."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    wait_id: StrictStr
    run_id: StrictStr
    wait_kind: WaitKind
    source_phase: Literal["AGENT_LOOP", "FORMAL_VALIDATION"]
    subject_digest: DigestV1
    created_at: CanonicalTimestampV1
    expires_at: CanonicalTimestampV1

    @field_validator("wait_id", "run_id")
    @classmethod
    def _ids_must_be_non_empty(cls, value: str) -> str:
        return _require_non_empty_identifier(value)

    @model_validator(mode="after")
    def _require_exact_wait_kind_phase(self) -> WaitContextV1:
        if self.wait_kind == "DISCLOSURE_GRANT" and self.source_phase != "AGENT_LOOP":
            raise ValueError("DISCLOSURE_GRANT waits bind only AGENT_LOOP")
        if (
            self.wait_kind == "FINAL_WRITEBACK"
            and self.source_phase != "FORMAL_VALIDATION"
        ):
            raise ValueError("FINAL_WRITEBACK waits bind only FORMAL_VALIDATION")
        if self.expires_at.value < self.created_at.value:
            raise ValueError("expires_at must not precede created_at")
        return self


class WaitDecisionV1(BaseModel):
    """One user decision exactly bound to its wait (SPEC §4.2.7/AC-27).

    The decision binds wait_id, run_id, wait_kind, subject_digest,
    event_id, and decided_at with a closed APPROVE/REJECT choice.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    wait_id: StrictStr
    run_id: StrictStr
    wait_kind: WaitKind
    subject_digest: DigestV1
    decision: WaitDecisionChoiceV1
    event_id: StrictStr
    decided_at: CanonicalTimestampV1

    @field_validator("wait_id", "run_id", "event_id")
    @classmethod
    def _ids_must_be_non_empty(cls, value: str) -> str:
        return _require_non_empty_identifier(value)
