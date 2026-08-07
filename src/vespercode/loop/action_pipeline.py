"""T25.2 legacy step 25.D: parse, policy, dispatch, feedback, action step.

``ActionPipeline.execute`` sequences one model response through the exact
Tasks 17.A-17.C parser/binder/dispatcher, the Task 13 policy engine, and
the Task 24.A/24.C feedback builder/repository in the exact order of the
25.D GREEN-2 contract: parse -> bind -> policy -> ALLOW-only dispatch ->
structured feedback append/consume -> body-free action-record storage.
A policy DENY never reaches the dispatcher (the card's exact RED), ASK is
unreachable for the six model actions (the control-plane writeback is the
only ASK subject, Task 13), every failure is recorded and exposed — never
hidden — and the v0009 ``action_records`` row binds the turn identity,
the unique action identity, both digests, the policy decision, and the
result reference (GREEN-1).  Registry edits, context assembly, LLM
invocation, counters, waits, restart, stopping, and outer-loop
composition remain out of scope (GREEN-4).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.canonical.clock import ClockV1
from vespercode.contracts.action import (
    ActionErrorV1,
    ActionResultV1 as ContractsActionResultV1,
    ActionInstanceV1 as ContractsActionInstanceV1,
    OptionalActionErrorV1,
    PolicyDecisionV1,
    SharedActionV1,
)
from vespercode.contracts.evidence import (
    StableControlErrorV1,
    _DIGEST_RE,
)
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.contracts.run import RunPhase
from vespercode.governance.policy import (
    PatchPathFactV1,
    PolicyContextV1,
    PolicyEngine,
    governance_policy_digest,
    policy_context_digest,
)
from vespercode.llm.base import ModelResponse
from vespercode.loop.action_binding import (
    ActionIdGeneratorV1,
    bind_action,
)
from vespercode.loop.action_parser import ActionParser
from vespercode.loop.agent_actions import ActionInstanceV1, ParseErrorV1
from vespercode.loop.feedback import (
    FeedbackRecordSequenceV1,
    build_feedback,
)
from vespercode.loop.feedback_consumption import (
    FeedbackAppendResultV1,
    FeedbackConsumptionResultV1,
    FeedbackReferenceSequenceV1,
    FeedbackRepositoryV1,
    consume_feedback,
)
from vespercode.storage.connection import ControlDatabase
from vespercode.tools.dispatcher import (
    ActionResultV1,
    ArtifactStorePortV1,
    DispatchContextV1,
    ToolDispatcher,
    ToolPortsV1,
)
from vespercode.trees.readable import ReadableTreeV1

_ACTION_TYPES_V1: frozenset[str] = frozenset(
    {
        "apply_candidate_patch",
        "list_files",
        "propose_completion",
        "read_file",
        "run_check",
        "search_text",
    }
)
"""The closed six model action types (SPEC §4.2.2)."""


def _require_sha256_hex(value: str) -> str:
    """The closed 64-lowercase-hex digest form of every digest field."""
    if _DIGEST_RE.fullmatch(value) is None:
        raise ValueError("digests must be exactly 64 lowercase hexadecimal characters")
    return value


def _require_bounded_identifier(value: str, bound: int) -> str:
    """One non-empty UTF-8 identifier at most *bound* bytes."""
    if value == "":
        raise ValueError("identifiers must be non-empty")
    if len(value.encode("utf-8")) > bound:
        raise ValueError(f"identifiers must be at most {bound} UTF-8 bytes")
    return value


class ActionStepFeedbackV1(BaseModel):
    """One closed step-feedback summary (the card's RED contract).

    ``APPENDED`` carries the stable error code of the produced record and
    its record id; ``REJECTED`` carries the code when the Task 24.C append
    rejected the record (never hidden); ``NONE`` carries nothing.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    kind: Literal["NONE", "APPENDED", "REJECTED"]
    error_code: StrictStr | None = None
    record_id: StrictStr | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @model_validator(mode="after")
    def _require_exact_outcome(self) -> ActionStepFeedbackV1:
        if self.kind == "NONE":
            if self.error_code is not None or self.record_id is not None:
                raise ValueError("NONE feedback carries no code or record id")
        elif self.kind == "APPENDED":
            if self.error_code is None or self.record_id is None:
                raise ValueError(
                    "APPENDED feedback requires the stable code and record id"
                )
        elif self.error_code is None or self.record_id is not None:
            raise ValueError(
                "REJECTED feedback requires the stable code and no record id"
            )
        return self


class ActionRecordDraftV1(BaseModel):
    """One body-free v0009 action-record row to persist (GREEN-1).

    Binds the turn identity, the unique Harness action identity, the
    instance/semantic digests, the policy decision, and the body-free
    result reference (the published artifact id, or none).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    turn_id: StrictStr
    action_id: StrictStr
    action_type: StrictStr
    semantic_digest: StrictStr
    instance_digest: StrictStr
    policy_decision: PolicyDecisionV1
    result_ref: StrictStr | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("action_type")
    @classmethod
    def _action_type_is_closed(cls, value: str) -> str:
        if value not in _ACTION_TYPES_V1:
            raise ValueError(f"unknown action type {value!r}")
        return value

    @field_validator("semantic_digest", "instance_digest")
    @classmethod
    def _digests_have_exact_form(cls, value: str) -> str:
        return _require_sha256_hex(value)

    @field_validator("turn_id", "action_id", "result_ref")
    @classmethod
    def _identifiers_are_bounded(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _require_bounded_identifier(value, 128)


class ActionRecordStoredV1(BaseModel):
    """One closed action-record storage outcome (explicit, never hidden)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    kind: Literal["STORED", "REJECTED", "FAILED"]
    message: StrictStr
    action_id: StrictStr | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @model_validator(mode="after")
    def _require_exact_outcome(self) -> ActionRecordStoredV1:
        if self.kind == "STORED":
            if self.action_id is None or self.message == "":
                raise ValueError("STORED outcomes require the action id")
        elif self.action_id is not None:
            raise ValueError("REJECTED and FAILED outcomes carry no action id")
        return self


class ActionRecordRepositoryV1:
    """Transactional v0009 action-record storage (one immediate insert).

    The record insert is the step's own atomic transaction; a duplicate
    action identity rejects with a closed outcome and a storage exception
    fails closed with a fixed message (SPEC 5.4) — never a raw sqlite
    error.
    """

    def __init__(self, database: ControlDatabase) -> None:
        self._database = database

    def store(self, draft: ActionRecordDraftV1) -> ActionRecordStoredV1:
        """Persist exactly one body-free action record.

        A duplicate action identity (or any other sqlite constraint
        violation such as a missing turn row) rejects with the closed
        REJECTED outcome — the rejection is detected by the exception
        TYPE, never by matching a sqlite message string (SPEC 5.4); any
        other storage failure fails closed with a fixed message.
        """
        try:
            with self._database.immediate_transaction() as tx:
                tx.execute(
                    "INSERT INTO action_records (action_id, turn_id, action_type,"
                    " semantic_digest, instance_digest, policy_decision, result_ref)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        draft.action_id,
                        draft.turn_id,
                        draft.action_type,
                        draft.semantic_digest,
                        draft.instance_digest,
                        draft.policy_decision,
                        draft.result_ref,
                    ),
                )
        except sqlite3.IntegrityError:
            return ActionRecordStoredV1(
                schema_version=1,
                kind="REJECTED",
                message=f"action id {draft.action_id!r} violates the stored "
                "action-record constraints",
            )
        except Exception:  # noqa: BLE001 - closed rejection, no raw error
            return ActionRecordStoredV1(
                schema_version=1,
                kind="FAILED",
                message="action-record storage failed",
            )
        return ActionRecordStoredV1(
            schema_version=1,
            kind="STORED",
            message="action record stored",
            action_id=draft.action_id,
        )


class ActionStepResultV1(BaseModel):
    """One closed action-step outcome (the pipeline's result envelope).

    Carries the parse outcome, the policy decision, the bound action
    identity, the dispatch envelope (ALLOW path only), the step-feedback
    summary, and the explicit append/consume/storage outcomes so no
    failure is ever hidden.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    parse_outcome: Literal["PARSED", "INVALID"]
    policy_decision: Literal["ALLOW", "ASK", "DENY"] | None = None
    action_id: StrictStr | None = None
    dispatch_result: ActionResultV1 | None = None
    feedback: ActionStepFeedbackV1
    append_outcome: FeedbackAppendResultV1 | None = None
    consume_outcome: FeedbackConsumptionResultV1 | None = None
    action_record: ActionRecordStoredV1 | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @model_validator(mode="after")
    def _require_exact_outcome(self) -> ActionStepResultV1:
        if self.parse_outcome == "INVALID":
            if (
                self.policy_decision is not None
                or self.action_id is not None
                or self.dispatch_result is not None
                or self.action_record is not None
            ):
                raise ValueError(
                    "invalid outputs carry no policy decision, action, or record"
                )
        elif self.policy_decision is None or self.action_id is None:
            raise ValueError("parsed outputs require the policy decision and action")
        return self


@dataclass(frozen=True)
class ActionPipelineContextV1:
    """The frozen facts and ports of one action step (GREEN-1..GREEN-4).

    Only immutable facts and injected ports enter the context: the turn
    identity and the feedback refs selected for this turn (Task 24.B), the
    policy/dispatch facts (Task 13/17.C), the visible tree, the registered
    ports, the artifact store, the Task 13 policy engine, the exact Task
    17.C dispatcher, the Task 24.C feedback repository, the v0009 action
    record repository, the clock, and the Harness action-id generator.
    """

    turn_id: str
    consumed_feedback_refs: FeedbackReferenceSequenceV1
    run_phase: RunPhase
    editable_policy_digest: str
    reference_profile_digest: str
    current_candidate_digest: str | None
    final_diff_digest: str | None
    patch_path_fact: PatchPathFactV1 | None
    visible_tree: ReadableTreeV1
    ports: ToolPortsV1
    artifact_store: ArtifactStorePortV1
    policy_engine: PolicyEngine
    dispatcher: ToolDispatcher
    feedback_repository: FeedbackRepositoryV1
    action_record_repository: ActionRecordRepositoryV1
    clock: ClockV1
    action_id_generator: ActionIdGeneratorV1


class ActionPipeline:
    """One deterministic parse/policy/dispatch/feedback/action pipeline.

    ``execute`` owns the exact 25.D sequence; the pipeline never widens a
    DENY and never hides a failure (every stage outcome is exposed on
    ``ActionStepResultV1``).
    """

    def execute(
        self,
        response: ModelResponse,
        context: ActionPipelineContextV1,
    ) -> ActionStepResultV1:
        """Convert one model response into at most one bound action step.

        The exact sequence is parse -> bind -> policy -> ALLOW-only
        dispatch -> structured feedback append/consume -> action-record
        transaction (GREEN-2); an invalid output or a DENY never reaches
        the dispatcher.
        """
        parsed = ActionParser().parse(response)
        if isinstance(parsed, ParseErrorV1):
            return self._invalid_step(parsed, context)
        instance = bind_action(parsed, context.action_id_generator)
        evaluation = context.policy_engine.evaluate(
            _policy_projection(instance), _policy_context(context)
        )
        if evaluation.decision == "DENY":
            reason = evaluation.reason_code or "INTERNAL_ERROR"
            return self._control_step(
                instance,
                "DENY",
                reason,
                StableControlErrorV1(
                    error_code=reason,
                    bounded_message=f"policy denied the action: {reason}",
                ),
                context,
            )
        if evaluation.decision != "ALLOW":
            # ASK is unreachable for the six model actions (the Task 13
            # engine returns ASK only for the control-plane writeback);
            # fail closed with a control error and zero dispatch.
            return self._control_step(
                instance,
                "ASK",
                "INTERNAL_ERROR",
                StableControlErrorV1(
                    error_code="INTERNAL_ERROR",
                    bounded_message="an ASK evaluation is impossible for a "
                    "model action",
                ),
                context,
            )
        dispatch_result = context.dispatcher.dispatch(
            instance, _dispatch_context(context)
        )
        return self._dispatch_step(instance, dispatch_result, context)

    def _invalid_step(
        self,
        parse_error: ParseErrorV1,
        context: ActionPipelineContextV1,
    ) -> ActionStepResultV1:
        """One invalid-output step: control feedback, zero dispatch.

        The parse error's stable code is the precise feedback code (SPEC
        §4.2.8's loop-level MODEL_OUTPUT_INVALID vocabulary belongs to the
        stopping evaluator); no action identity exists, so no action
        record is written.
        """
        records = build_feedback(
            StableControlErrorV1(
                error_code=parse_error.error_code,
                bounded_message=parse_error.bounded_message,
            ),
            context.clock,
        )
        feedback, append_outcome = self._append_feedback(
            records, parse_error.error_code, context
        )
        consume_outcome = self._consume(context)
        return ActionStepResultV1(
            schema_version=1,
            parse_outcome="INVALID",
            policy_decision=None,
            action_id=None,
            dispatch_result=None,
            feedback=feedback,
            append_outcome=append_outcome,
            consume_outcome=consume_outcome,
            action_record=None,
        )

    def _control_step(
        self,
        instance: ActionInstanceV1,
        decision: Literal["ALLOW", "ASK", "DENY"],
        error_code: str,
        control_error: StableControlErrorV1,
        context: ActionPipelineContextV1,
    ) -> ActionStepResultV1:
        """One DENY/ASK step: control feedback, zero dispatch, record."""
        records = build_feedback(control_error, context.clock)
        feedback, append_outcome = self._append_feedback(records, error_code, context)
        consume_outcome = self._consume(context)
        action_record = self._store_record(instance, decision, None, context)
        return ActionStepResultV1(
            schema_version=1,
            parse_outcome="PARSED",
            policy_decision=decision,
            action_id=instance.action_id,
            dispatch_result=None,
            feedback=feedback,
            append_outcome=append_outcome,
            consume_outcome=consume_outcome,
            action_record=action_record,
        )

    def _dispatch_step(
        self,
        instance: ActionInstanceV1,
        dispatch_result: ActionResultV1,
        context: ActionPipelineContextV1,
    ) -> ActionStepResultV1:
        """One ALLOW step: exact Task 17.C dispatch then feedback/record."""
        if dispatch_result.status == "SUCCEEDED":
            records: FeedbackRecordSequenceV1 = ()
            error_code: str | None = None
        else:
            # The Task 17.C envelope invariant — FAILED/REJECTED results
            # always carry the PRESENT closed error — is enforced at this
            # pipeline boundary before the feedback builder consumes it
            # (never hidden, never a silent None code).
            assert dispatch_result.error.kind == "PRESENT"
            assert dispatch_result.error.code is not None
            assert dispatch_result.error.bounded_message is not None
            # The Task 24.A feedback builder consumes the exact Task 05
            # contracts envelope; the dispatcher's task-owned envelope is
            # projected onto it (the stable code and bounded message are
            # preserved, the evidence ref stays ABSENT).
            error_code = dispatch_result.error.code
            records = build_feedback(
                _contracts_envelope(dispatch_result), context.clock
            )
        feedback, append_outcome = self._append_feedback(records, error_code, context)
        consume_outcome = self._consume(context)
        result_ref = None
        if dispatch_result.payload_ref.kind == "PRESENT":
            result_ref = dispatch_result.payload_ref.value.artifact_id
        action_record = self._store_record(instance, "ALLOW", result_ref, context)
        return ActionStepResultV1(
            schema_version=1,
            parse_outcome="PARSED",
            policy_decision="ALLOW",
            action_id=instance.action_id,
            dispatch_result=dispatch_result,
            feedback=feedback,
            append_outcome=append_outcome,
            consume_outcome=consume_outcome,
            action_record=action_record,
        )

    def _append_feedback(
        self,
        records: FeedbackRecordSequenceV1,
        error_code: str | None,
        context: ActionPipelineContextV1,
    ) -> tuple[ActionStepFeedbackV1, FeedbackAppendResultV1 | None]:
        """Append the step's feedback records exactly once (Task 24.C).

        An empty sequence produces ``NONE`` and no append; an append
        rejection is never hidden (``REJECTED`` carries the stable code
        and the append outcome is exposed on the result).
        """
        if not records:
            return (
                ActionStepFeedbackV1(schema_version=1, kind="NONE"),
                None,
            )
        append_outcome = context.feedback_repository.append(records)
        assert error_code is not None
        if append_outcome.kind == "APPENDED":
            return (
                ActionStepFeedbackV1(
                    schema_version=1,
                    kind="APPENDED",
                    error_code=error_code,
                    record_id=records[0].id,
                ),
                append_outcome,
            )
        return (
            ActionStepFeedbackV1(
                schema_version=1, kind="REJECTED", error_code=error_code
            ),
            append_outcome,
        )

    def _consume(
        self, context: ActionPipelineContextV1
    ) -> FeedbackConsumptionResultV1 | None:
        """Consume the turn's selected feedback refs exactly once.

        The refs were selected by the Task 24.B projection for this turn;
        the Task 24.C one-winner consume binds them to the turn, and any
        conflict outcome is exposed, never hidden.
        """
        if not context.consumed_feedback_refs:
            return None
        return consume_feedback(
            context.turn_id, context.consumed_feedback_refs, context.feedback_repository
        )

    def _store_record(
        self,
        instance: ActionInstanceV1,
        decision: PolicyDecisionV1,
        result_ref: str | None,
        context: ActionPipelineContextV1,
    ) -> ActionRecordStoredV1:
        """Persist one body-free action record (GREEN-1)."""
        return context.action_record_repository.store(
            ActionRecordDraftV1(
                schema_version=1,
                turn_id=context.turn_id,
                action_id=instance.action_id,
                action_type=instance.action.action_type,
                semantic_digest=instance.semantic_digest,
                instance_digest=instance.instance_digest,
                policy_decision=decision,
                result_ref=result_ref,
            )
        )


def _policy_projection(instance: ActionInstanceV1) -> ContractsActionInstanceV1:
    """The Task 13 policy projection of one bound instance.

    The Task 13 engine evaluates the Task 05 contracts envelope, whose
    ``action`` is the shared two-field identity; the projection carries
    the same action type, id, and digests, so the memo key (policy
    digest, action type, semantic digest, context digest) is unchanged.
    """
    return ContractsActionInstanceV1(
        action_id=instance.action_id,
        semantic_digest=instance.semantic_digest,
        instance_digest=instance.instance_digest,
        action=SharedActionV1(
            schema_version=instance.action.schema_version,
            action_type=instance.action.action_type,
        ),
    )


def _contracts_envelope(result: ActionResultV1) -> ContractsActionResultV1:
    """Project one dispatcher envelope onto the exact Task 05 contracts
    envelope the Task 24.A feedback builder consumes.

    The stable code and bounded message are preserved exactly; the
    dispatcher's error carries no evidence reference, so the projected
    envelope binds ``evidence_ref=ABSENT``.
    """
    if result.error.kind == "PRESENT":
        assert result.error.code is not None
        assert result.error.bounded_message is not None
        error: OptionalActionErrorV1 = PresentV1(
            kind="PRESENT",
            value=ActionErrorV1(
                error_code=result.error.code,
                bounded_message=result.error.bounded_message,
                evidence_ref=AbsentV1(kind="ABSENT"),
            ),
        )
    else:
        error = AbsentV1(kind="ABSENT")
    return ContractsActionResultV1(
        schema_version=1,
        action_id=result.action_id,
        semantic_digest=result.semantic_digest,
        instance_digest=result.instance_digest,
        status=result.status,
        result_type=result.result_type,
        payload_ref=result.payload_ref,
        error=error,
    )


def _policy_context(context: ActionPipelineContextV1) -> PolicyContextV1:
    """One immutable Task 13 policy context from the step facts."""
    policy_digest = governance_policy_digest(context.editable_policy_digest)
    return PolicyContextV1(
        schema_version=1,
        run_phase=context.run_phase,
        policy_digest=policy_digest,
        editable_policy_digest=context.editable_policy_digest,
        reference_profile_digest=context.reference_profile_digest,
        candidate_digest=context.current_candidate_digest,
        final_diff_digest=context.final_diff_digest,
        patch_path_fact=context.patch_path_fact,
        writeback=None,
        digest=policy_context_digest(
            run_phase=context.run_phase,
            editable_policy_digest=context.editable_policy_digest,
            reference_profile_digest=context.reference_profile_digest,
            candidate_digest=context.current_candidate_digest,
            final_diff_digest=context.final_diff_digest,
            patch_path_fact=context.patch_path_fact,
            writeback=None,
        ),
    )


def _dispatch_context(context: ActionPipelineContextV1) -> DispatchContextV1:
    """One exact Task 17.C dispatch context from the step facts."""
    return DispatchContextV1(
        run_phase=context.run_phase,
        editable_policy_digest=context.editable_policy_digest,
        reference_profile_digest=context.reference_profile_digest,
        current_candidate_digest=context.current_candidate_digest,
        final_diff_digest=context.final_diff_digest,
        patch_path_fact=context.patch_path_fact,
        visible_tree=context.visible_tree,
        ports=context.ports,
        artifact_store=context.artifact_store,
        policy_engine=context.policy_engine,
    )
