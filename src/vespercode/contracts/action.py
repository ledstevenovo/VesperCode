"""T05.1 legacy step 5.C: closed action/result/policy-decision envelopes.

``SharedActionV1`` is the shared closed action identity every model action
carries; ``ActionErrorV1`` is the stable error envelope with an optional
evidence reference; ``ActionResultV1`` enforces status/payload consistency
so success cannot carry error data and failure always carries a stable
error, and its instance digest must be the exact §0.1
``ActionInstanceDigestV1`` binding of its own action identity;
``ActionInstanceV1`` binds the Harness-generated action id and the
semantic digest to the action value under the same instance identity
rule.  Model JSON parsing, policy evaluation, dispatch, and check
execution remain out of scope (GREEN-4).
"""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.canonical.digest import domain_digest
from vespercode.contracts.evidence import OptionalArtifactRefV1, _DIGEST_RE
from vespercode.contracts.optional import AbsentV1, PresentV1

CheckPlanIdV1: TypeAlias = Literal["TARGET_TESTS", "FULL_PYTEST", "RUFF", "MYPY"]
"""SPEC §4.2.2 ``RunCheckAction`` check plans."""

ActionStatusV1: TypeAlias = Literal["SUCCEEDED", "REJECTED", "FAILED"]
"""SPEC §4.2.2 ``ActionResult`` statuses."""

PolicyDecisionV1: TypeAlias = Literal["ALLOW", "ASK", "DENY"]
"""SPEC §4.4.1 policy decisions."""


def _require_action_id(value: str) -> str:
    """SPEC §4.2.2: Harness-generated non-empty UTF-8 string, <=128 bytes."""
    if value == "":
        raise ValueError("action_id must be non-empty")
    if len(value.encode("utf-8")) > 128:
        raise ValueError("action_id must be at most 128 UTF-8 bytes")
    return value


def _instance_digest_for(action_id: str, semantic_digest: str) -> str:
    """The exact §0.1 ``ActionInstanceDigestV1`` binding of one identity."""
    return domain_digest(
        "ActionInstanceDigestV1",
        1,
        {
            "schema_version": 1,
            "action_id": action_id,
            "semantic_digest": semantic_digest,
        },
    )


class SharedActionV1(BaseModel):
    """The shared closed action identity every action carries (§4.2.2)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    action_type: StrictStr

    @field_validator("action_type")
    @classmethod
    def _action_type_must_be_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("action_type must be non-empty")
        return value


class ActionErrorV1(BaseModel):
    """SPEC §4.2.2 stable action error with an optional evidence reference."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    error_code: StrictStr
    bounded_message: StrictStr
    evidence_ref: OptionalArtifactRefV1

    @field_validator("error_code", "bounded_message")
    @classmethod
    def _no_empty_values(cls, value: str) -> str:
        if value == "":
            raise ValueError("action error fields must be non-empty")
        return value


OptionalActionErrorV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[ActionErrorV1], Field(discriminator="kind")
]
"""SPEC §4.2.2: ``ABSENT`` or ``PRESENT(ActionErrorV1)``."""


class ActionResultV1(BaseModel):
    """SPEC §4.2.2 closed action result envelope.

    Success never carries error data, failure always carries a stable
    error, and the instance digest is the exact §0.1
    ``ActionInstanceDigestV1`` binding of ``{schema_version, action_id,
    semantic_digest}``; contradictory envelopes reject before publishing.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    action_id: StrictStr
    semantic_digest: StrictStr
    instance_digest: StrictStr
    status: ActionStatusV1
    result_type: StrictStr
    payload_ref: OptionalArtifactRefV1
    error: OptionalActionErrorV1

    @field_validator("action_id")
    @classmethod
    def _validate_action_id(cls, value: str) -> str:
        return _require_action_id(value)

    @field_validator("semantic_digest", "instance_digest")
    @classmethod
    def _digests_must_be_sha256_hex(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError(
                "digests must be exactly 64 lowercase hexadecimal characters"
            )
        return value

    @field_validator("result_type")
    @classmethod
    def _result_type_must_be_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("result_type must be non-empty")
        return value

    @model_validator(mode="after")
    def _enforce_status_payload_consistency(self) -> ActionResultV1:
        error_present = self.error.kind == "PRESENT"
        if self.status == "SUCCEEDED" and error_present:
            raise ValueError("SUCCEEDED results cannot carry error data")
        if self.status in ("FAILED", "REJECTED") and not error_present:
            raise ValueError("FAILED and REJECTED results must carry error data")
        if self.instance_digest != _instance_digest_for(
            self.action_id, self.semantic_digest
        ):
            raise ValueError("instance_digest must bind action_id and semantic_digest")
        return self


class ActionInstanceV1(BaseModel):
    """SPEC §4.2.2 Harness-bound action instance envelope.

    The instance digest is the exact §0.1 ``ActionInstanceDigestV1``
    binding of ``{schema_version, action_id, semantic_digest}``, so the
    instance identity can never be detached from the action value.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    action_id: StrictStr
    semantic_digest: StrictStr
    instance_digest: StrictStr
    action: SharedActionV1

    @field_validator("action_id")
    @classmethod
    def _validate_action_id(cls, value: str) -> str:
        return _require_action_id(value)

    @field_validator("semantic_digest", "instance_digest")
    @classmethod
    def _digests_must_be_sha256_hex(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError(
                "digests must be exactly 64 lowercase hexadecimal characters"
            )
        return value

    @model_validator(mode="after")
    def _bind_instance_identity(self) -> ActionInstanceV1:
        if self.instance_digest != _instance_digest_for(
            self.action_id, self.semantic_digest
        ):
            raise ValueError("instance_digest must bind action_id and semantic_digest")
        return self
