"""T17.1 legacy step 17.A: the closed model-action vocabulary.

Owns the SPEC §4.2.2 closed action grammar: the two model-action schemas
no earlier task produced (``RunCheckActionV1`` and
``ProposeCompletionActionV1``), the closed ``AgentAction`` union of all six
registered model actions, the Harness-bound ``ActionInstanceV1`` whose
instance digest is the exact §0.1 ``ActionInstanceDigestV1`` binding of
``{schema_version, action_id, semantic_digest}``, and the stable
``ParseErrorV1`` outcome.  Every schema rejects unknown fields and every
field is required — no parser default may fill an omission — and no schema
carries a model-supplied Harness action identity (GREEN-2).  Response
framing, identity generation, policy/phase evaluation, and dispatch remain
out of scope (GREEN-4).
"""

from __future__ import annotations

from typing import Annotated, Final, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    TypeAdapter,
    field_validator,
    model_validator,
)

from vespercode.candidate.patch_engine import ApplyCandidatePatchAction
from vespercode.contracts.action import (
    CheckPlanIdV1,
    _instance_digest_for,
    _require_action_id,
)
from vespercode.contracts.evidence import _DIGEST_RE
from vespercode.tools.file_actions import (
    ListFilesActionV1,
    ReadFileActionV1,
    SearchTextActionV1,
)


def _reject_coerced_schema_version(value: object) -> object:
    """Reject bool/float/string spelling of the integer schema version."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("schema_version must be the decimal integer 1")
    return value


def _require_sha256_hex(value: str) -> str:
    """The closed 64-lowercase-hex digest form shared by every digest field."""
    if _DIGEST_RE.fullmatch(value) is None:
        raise ValueError("digests must be exactly 64 lowercase hexadecimal characters")
    return value


class RunCheckActionV1(BaseModel):
    """SPEC §4.2.2 ``RunCheckAction``: one frozen check-plan selection.

    The plan id is the closed ``CheckPlanIdV1`` literal; the action carries
    no executable, argv, workdir, environment, or command text — those are
    adapter-built from the frozen profile (SPEC §4.2.2).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    action_type: Literal["run_check"]
    check_plan_id: CheckPlanIdV1

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)


class ProposeCompletionActionV1(BaseModel):
    """SPEC §4.2.2 ``ProposeCompletionAction``: request formal validation.

    The action binds the current candidate digest and a bounded rationale;
    it can only request ``FORMAL_VALIDATION`` — never declare success
    (SPEC §4.2.5 behavior 6 / AC-06).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    action_type: Literal["propose_completion"]
    candidate_digest: StrictStr
    rationale_summary: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("candidate_digest")
    @classmethod
    def _candidate_digest_is_sha256_hex(cls, value: str) -> str:
        return _require_sha256_hex(value)

    @field_validator("rationale_summary")
    @classmethod
    def _rationale_is_bounded_utf8(cls, value: str) -> str:
        try:
            byte_length = len(value.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise ValueError("rationale_summary must be strict UTF-8 text") from error
        if byte_length > 2048:
            raise ValueError("rationale_summary must be at most 2048 UTF-8 bytes")
        return value


AgentAction: TypeAlias = Annotated[
    ListFilesActionV1
    | ReadFileActionV1
    | SearchTextActionV1
    | ApplyCandidatePatchAction
    | RunCheckActionV1
    | ProposeCompletionActionV1,
    Field(discriminator="action_type"),
]
"""SPEC §4.2.2: the closed union of the six registered model actions.

Every variant is a required-field, unknown-field-rejecting schema, so a
model response can only ever produce one exact closed action or one
``ParseErrorV1`` (GREEN-1).
"""

_agent_action_adapter: Final[TypeAdapter[AgentAction]] = TypeAdapter(AgentAction)


def _validate_agent_action(value: object) -> AgentAction:
    """Validate one raw value into the closed action union.

    The union is an ``Annotated`` alias, so validation goes through the
    one shared pydantic ``TypeAdapter``; the strict parser and the
    vocabulary tests consume this single path so the discriminant
    selection can never drift.
    """
    return _agent_action_adapter.validate_python(value)


ParseErrorCodeV1: TypeAlias = Literal[
    "NOT_JSON_OBJECT",
    "UNKNOWN_ACTION_TYPE",
    "UNKNOWN_FIELD",
    "MISSING_FIELD",
    "FIELD_INVALID",
]
"""The closed stable parse-error codes of the strict parser.

``NOT_JSON_OBJECT`` covers every framing violation (malformed JSON,
non-object values, multiple objects, and trailing non-whitespace bytes);
``UNKNOWN_ACTION_TYPE`` covers an unknown or missing discriminator value;
``UNKNOWN_FIELD`` covers extra keys including any model-supplied Harness
action identity; ``MISSING_FIELD`` covers omissions that no parser default
may fill; ``FIELD_INVALID`` covers every other wrong-type or out-of-range
violation.
"""


class ParseErrorV1(BaseModel):
    """One stable parse error with the closed code and a bounded message."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    error_code: ParseErrorCodeV1
    bounded_message: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("bounded_message")
    @classmethod
    def _bounded_message_is_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("bounded_message must be non-empty")
        return value


class ActionInstanceV1(BaseModel):
    """SPEC §4.2.2 Harness-bound action instance envelope.

    The instance digest is the exact §0.1 ``ActionInstanceDigestV1``
    binding of ``{schema_version, action_id, semantic_digest}``, computed
    by the T05.1 contracts vocabulary so the identity can never detach
    from the action value or from the T05.1 result envelope that consumes
    the same rule (GREEN-1).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    action_id: StrictStr
    semantic_digest: StrictStr
    instance_digest: StrictStr
    action: AgentAction

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("action_id")
    @classmethod
    def _validate_action_id(cls, value: str) -> str:
        return _require_action_id(value)

    @field_validator("semantic_digest", "instance_digest")
    @classmethod
    def _digests_must_be_sha256_hex(cls, value: str) -> str:
        return _require_sha256_hex(value)

    @model_validator(mode="after")
    def _bind_instance_identity(self) -> ActionInstanceV1:
        if self.instance_digest != _instance_digest_for(
            self.action_id, self.semantic_digest
        ):
            raise ValueError("instance_digest must bind action_id and semantic_digest")
        return self
