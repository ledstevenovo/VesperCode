"""T17.1 legacy step 17.C: the ordered guarded tool dispatcher.

``ToolDispatcher.dispatch`` converts one bound action instance into one
closed ``ActionResultV1`` after the four gates pass in the exact card
order — current-candidate binding, path/object authorization, Run phase,
and the Task 13 policy (SPEC §4.2.5 behavior 4) — and only then selects
and invokes exactly one registered typed tool port (GREEN-1).  Every gate
failure and unknown capability returns a stable ``REJECTED`` envelope with
zero port calls; a tool exception or an invalid tool result becomes a
typed ``FAILED`` envelope and is never swallowed or reported as success
(GREEN-2).  The three file ports use the exact Task 11.A/11.B pure
signatures over the context's visible tree; file-tool results are
published through the bounded artifact store and the payload reference
enters the envelope.  Parsing, binding, tool implementations, shell,
waits, and high-level agent runners remain out of scope (GREEN-4).

The dispatcher's own ``ActionResultV1``/``DispatchErrorV1`` envelopes are
T17.1-owned: the card's exact RED contract reads ``result.error.code``
directly, which the read-only T05.1 contracts envelope (whose error is the
``ABSENT | PRESENT(ActionErrorV1)`` union with ``error_code``) cannot
satisfy; the closed optional-error shape here keeps the SPEC §0.1
discriminant-union convention while exposing the stable ``code``.  The
T25.C action-pipeline successor consumes this dispatcher envelope (the
card's ``dispatch -> ActionResultV1``), so the loop's result vocabulary is
this module's envelope, not the T05.1 contracts vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Protocol, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    field_validator,
    model_validator,
)

from src.vespercode.candidate.patch_engine import (
    ApplyCandidatePatchAction,
    CandidatePatchErrorCodeV1,
    CandidatePatchOutcomeV1,
)
from src.vespercode.contracts.action import (
    ActionInstanceV1 as ContractsActionInstanceV1,
)
from src.vespercode.contracts.action import (
    ActionStatusV1,
    SharedActionV1,
    _instance_digest_for,
    _require_action_id,
)
from src.vespercode.contracts.evidence import (
    ArtifactRefV1,
    OptionalArtifactRefV1,
    _DIGEST_RE,
)
from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.contracts.run import RunPhase
from src.vespercode.governance.policy import (
    PatchPathFactV1,
    PolicyContextV1,
    PolicyEngine,
    governance_policy_digest,
    policy_context_digest,
)
from src.vespercode.loop.agent_actions import (
    ActionInstanceV1,
    AgentAction,
    ProposeCompletionActionV1,
    RunCheckActionV1,
)
from src.vespercode.tools.file_actions import (
    ListFilesActionV1,
    ReadFileActionV1,
    SearchTextActionV1,
)
from src.vespercode.tools.file_results import (
    FileToolErrorCodeV1,
    FileToolErrorV1,
    FileToolResultV1,
    ListFilesResultV1,
    ListFilesSuccessV1,
    ReadFileResultV1,
    ReadFileSuccessV1,
    SearchTextResultV1,
    SearchTextSuccessV1,
)
from src.vespercode.trees.readable import ReadableTreeV1
from src.vespercode.workspace.path_guard import sensitive_path_rule_id

OwnDispatchErrorCodeV1: TypeAlias = Literal[
    "STALE_CANDIDATE",
    "SENSITIVE_PATH",
    "ACTION_NOT_ALLOWED_IN_PHASE",
    "POLICY_DENY",
    "UNKNOWN_CAPABILITY",
    "TOOL_EXCEPTION",
    "INVALID_RESULT",
    "ARTIFACT_PUBLICATION_FAILED",
    "INTERNAL_ERROR",
]
"""The dispatcher's own closed failure codes.

``POLICY_DENY`` is the card's exact RED code for a Task 13 hard ``DENY``
(SPEC's governance vocabulary spells the equivalent ``ACTION_DENIED``);
tool-level rejections keep their own stable codes (``FileToolErrorCodeV1``
/ ``CandidatePatchErrorCodeV1``) so feedback stays typed.
"""

DispatchFailureCodeV1: TypeAlias = (
    OwnDispatchErrorCodeV1 | FileToolErrorCodeV1 | CandidatePatchErrorCodeV1
)
"""Every stable failure code one dispatch envelope can carry."""

DispatchResultTypeV1: TypeAlias = Literal[
    "ListFilesResult",
    "ReadFileResult",
    "SearchTextResult",
    "ApplyCandidatePatchResult",
    "RunCheckResult",
    "ProposeCompletionResult",
]
"""SPEC §4.2.2 result families of the six model actions."""


class DispatchErrorV1(BaseModel):
    """One closed optional dispatch error.

    ``ABSENT`` carries no code or message; ``PRESENT`` requires the stable
    ``code`` and a bounded message, so ``result.error.code`` is directly
    readable on the present branch (the card's exact RED contract).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["ABSENT"] | Literal["PRESENT"]
    code: DispatchFailureCodeV1 | None = None
    bounded_message: StrictStr | None = None

    @model_validator(mode="after")
    def _require_exact_shape(self) -> DispatchErrorV1:
        if self.kind == "PRESENT":
            if (
                self.code is None
                or self.bounded_message is None
                or self.bounded_message == ""
            ):
                raise ValueError(
                    "PRESENT dispatch errors require the stable code and "
                    "a bounded message"
                )
        elif self.code is not None or self.bounded_message is not None:
            raise ValueError("ABSENT dispatch errors must not carry code or message")
        return self


class ActionResultV1(BaseModel):
    """SPEC §4.2.2 ``ActionResult`` envelope of the ordered dispatcher.

    Success never carries error data, failure always carries the stable
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
    result_type: DispatchResultTypeV1
    payload_ref: OptionalArtifactRefV1
    error: DispatchErrorV1

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


class RunCheckOutcomeV1(BaseModel):
    """One closed run-check port outcome.

    ``COMPLETED`` means the frozen check plan ran (whether the check
    itself PASSed or FAILed is the ``CheckResult``'s own status, which the
    successor loop publishes — the action still SUCCEEDED, SPEC §4.2.2);
    ``REJECTED`` carries the stable error code and bounded message.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["COMPLETED", "REJECTED"]
    error_code: DispatchFailureCodeV1 | None = None
    bounded_message: StrictStr | None = None

    @model_validator(mode="after")
    def _require_exact_outcome(self) -> RunCheckOutcomeV1:
        if self.kind == "REJECTED" and (
            self.error_code is None or self.bounded_message is None
        ):
            raise ValueError("REJECTED run-check outcomes require the code and message")
        if self.kind == "COMPLETED" and (
            self.error_code is not None or self.bounded_message is not None
        ):
            raise ValueError("COMPLETED run-check outcomes carry no error")
        return self


class CompletionOutcomeV1(BaseModel):
    """One closed propose-completion port outcome (SPEC §4.2.2:
    ``VALIDATION_REQUESTED`` or a structured rejection)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["VALIDATION_REQUESTED", "REJECTED"]
    error_code: DispatchFailureCodeV1 | None = None
    bounded_message: StrictStr | None = None

    @model_validator(mode="after")
    def _require_exact_outcome(self) -> CompletionOutcomeV1:
        if self.kind == "REJECTED" and (
            self.error_code is None or self.bounded_message is None
        ):
            raise ValueError(
                "REJECTED completion outcomes require the code and message"
            )
        if self.kind == "VALIDATION_REQUESTED" and (
            self.error_code is not None or self.bounded_message is not None
        ):
            raise ValueError("VALIDATION_REQUESTED outcomes carry no error")
        return self


ToolResultV1: TypeAlias = (
    FileToolResultV1 | CandidatePatchOutcomeV1 | RunCheckOutcomeV1 | CompletionOutcomeV1
)
"""Every closed result one registered tool port may return."""


class ToolPortsV1(Protocol):
    """The six named typed tool ports (card 17.C).

    The three file ports carry the exact Task 11.A/11.B pure signatures
    over the visible tree; the patch port consumes the Task 12.C closed
    action and outcome; the check and completion ports consume the closed
    T17.1 action schemas.  A port may be unregistered (``None``) — the
    dispatcher fails closed with ``UNKNOWN_CAPABILITY`` and zero calls.
    """

    list_files: Callable[[ReadableTreeV1, ListFilesActionV1], ListFilesResultV1] | None
    read_file: Callable[[ReadableTreeV1, ReadFileActionV1], ReadFileResultV1] | None
    search_text: (
        Callable[[ReadableTreeV1, SearchTextActionV1], SearchTextResultV1] | None
    )
    apply_candidate_patch: (
        Callable[[ApplyCandidatePatchAction], CandidatePatchOutcomeV1] | None
    )
    run_check: Callable[[RunCheckActionV1], RunCheckOutcomeV1] | None
    propose_completion: (
        Callable[[ProposeCompletionActionV1], CompletionOutcomeV1] | None
    )


class ArtifactStorePortV1(Protocol):
    """One bounded artifact store: ``put`` persists a file-tool result
    payload and returns its closed reference."""

    def put(self, payload: FileToolResultV1) -> ArtifactRefV1: ...


class FileToolOutcomeV1(BaseModel):
    """One closed file-tool publication outcome bound to its instance.

    ``PUBLISHED`` carries the artifact reference; ``REJECTED`` carries the
    stable error code and a bounded message (e.g. a store failure).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["PUBLISHED", "REJECTED"]
    action_id: StrictStr
    instance_digest: StrictStr
    artifact_ref: ArtifactRefV1 | None = None
    error_code: DispatchFailureCodeV1 | None = None
    bounded_message: StrictStr | None = None

    @field_validator("action_id")
    @classmethod
    def _validate_action_id(cls, value: str) -> str:
        return _require_action_id(value)

    @field_validator("instance_digest")
    @classmethod
    def _digest_must_be_sha256_hex(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError(
                "instance_digest must be exactly 64 lowercase hexadecimal characters"
            )
        return value

    @model_validator(mode="after")
    def _require_exact_outcome(self) -> FileToolOutcomeV1:
        if self.kind == "PUBLISHED" and (
            self.artifact_ref is None
            or self.error_code is not None
            or self.bounded_message is not None
        ):
            raise ValueError("PUBLISHED outcomes require the reference and no error")
        if self.kind == "REJECTED" and (
            self.artifact_ref is not None
            or self.error_code is None
            or self.bounded_message is None
        ):
            raise ValueError("REJECTED outcomes require the error and no reference")
        return self


def publish_file_tool_outcome(
    instance: ActionInstanceV1,
    result: FileToolResultV1,
    artifact_store: ArtifactStorePortV1,
) -> FileToolOutcomeV1:
    """Publish one file-tool result payload into the bounded artifact store.

    A store failure becomes a ``REJECTED`` outcome with the stable
    ``ARTIFACT_PUBLICATION_FAILED`` code — never a partial publication and
    never a success.
    """
    try:
        artifact_ref = artifact_store.put(result)
    except Exception as error:
        return FileToolOutcomeV1(
            kind="REJECTED",
            action_id=instance.action_id,
            instance_digest=instance.instance_digest,
            error_code="ARTIFACT_PUBLICATION_FAILED",
            bounded_message=_bounded(str(error)),
        )
    return FileToolOutcomeV1(
        kind="PUBLISHED",
        action_id=instance.action_id,
        instance_digest=instance.instance_digest,
        artifact_ref=artifact_ref,
    )


def _bounded(message: str) -> str:
    """One bounded non-empty message for a failure envelope."""
    return message[:512] or "unknown failure"


@dataclass(frozen=True)
class DispatchContextV1:
    """The frozen facts of one dispatch: gates, ports, tree, and store.

    Only immutable facts enter the context — the run phase, the current
    candidate/final-diff identities, the frozen policy identities and the
    deterministic pre-policy patch-path fact (Task 12 pipeline), the
    visible tree, the registered ports, the artifact store, and the per-run
    Task 13 policy engine.  No prompt text, repository content, mutable
    config, Grant, or approval state can enter (GREEN-1).
    """

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


class ToolDispatcher:
    """One deterministic, stateless ordered guarded dispatcher.

    ``dispatch`` runs the four gates in the exact card order before any
    port call; gate failures and unknown capabilities return ``REJECTED``
    with zero port calls, and only an exact allowed current action invokes
    exactly one registered port once.
    """

    def dispatch(
        self, instance: ActionInstanceV1, context: DispatchContextV1
    ) -> ActionResultV1:
        action = instance.action
        # Gate 1: current-candidate binding (SPEC §4.3 STALE_CANDIDATE).
        if isinstance(action, ApplyCandidatePatchAction):
            if context.current_candidate_digest != action.base_candidate_digest:
                return self._reject(instance, "STALE_CANDIDATE", action)
        elif isinstance(action, ProposeCompletionActionV1):
            if context.current_candidate_digest != action.candidate_digest:
                return self._reject(instance, "STALE_CANDIDATE", action)
        # Gate 2: path/object authorization (SPEC §1.4.3 sensitive rules).
        sensitive = _first_sensitive_path(action)
        if sensitive is not None:
            return self._reject(
                instance,
                "SENSITIVE_PATH",
                action,
                detail=f"the action path {sensitive!r} hits a sensitive-path rule",
            )
        # Gate 3: Run phase (SPEC §4.2.3 matrix).
        if context.run_phase != "AGENT_LOOP":
            return self._reject(instance, "ACTION_NOT_ALLOWED_IN_PHASE", action)
        # Gate 4: Task 13 policy; an approval can never widen a DENY.
        evaluation = context.policy_engine.evaluate(
            _policy_projection(instance), _policy_context(context)
        )
        if evaluation.decision == "DENY":
            reason = evaluation.reason_code or "UNKNOWN_CAPABILITY"
            return self._reject(
                instance,
                "POLICY_DENY",
                action,
                detail=f"policy denied the action: {reason}",
            )
        if evaluation.decision != "ALLOW":
            return self._reject(instance, "INTERNAL_ERROR", action)
        # Select exactly one registered typed port.
        port = _select_port(context.ports, action.action_type)
        if port is None:
            return self._reject(instance, "UNKNOWN_CAPABILITY", action)
        try:
            result = _call_port(context, action, port)
        except Exception as error:
            return self._fail(
                instance,
                "TOOL_EXCEPTION",
                action,
                detail=f"tool port raised {type(error).__name__}: {_bounded(str(error))}",
            )
        return _convert_result(instance, action, result, context.artifact_store)

    @staticmethod
    def _reject(
        instance: ActionInstanceV1,
        code: OwnDispatchErrorCodeV1,
        action: AgentAction,
        *,
        detail: str | None = None,
    ) -> ActionResultV1:
        message = detail or "the action was rejected before any tool call"
        return _envelope(instance, action, "REJECTED", code, message)

    @staticmethod
    def _fail(
        instance: ActionInstanceV1,
        code: DispatchFailureCodeV1,
        action: AgentAction,
        *,
        detail: str,
    ) -> ActionResultV1:
        return _envelope(instance, action, "FAILED", code, detail)


def _envelope(
    instance: ActionInstanceV1,
    action: AgentAction,
    status: ActionStatusV1,
    code: DispatchFailureCodeV1,
    message: str,
) -> ActionResultV1:
    return ActionResultV1(
        schema_version=1,
        action_id=instance.action_id,
        semantic_digest=instance.semantic_digest,
        instance_digest=instance.instance_digest,
        status=status,
        result_type=_result_type_for(action.action_type),
        payload_ref=AbsentV1(kind="ABSENT"),
        error=DispatchErrorV1(
            kind="PRESENT", code=code, bounded_message=_bounded(message)
        ),
    )


def _success(
    instance: ActionInstanceV1,
    action: AgentAction,
    result_type: DispatchResultTypeV1,
    artifact_ref: ArtifactRefV1 | None,
) -> ActionResultV1:
    return ActionResultV1(
        schema_version=1,
        action_id=instance.action_id,
        semantic_digest=instance.semantic_digest,
        instance_digest=instance.instance_digest,
        status="SUCCEEDED",
        result_type=result_type,
        payload_ref=(
            PresentV1(kind="PRESENT", value=artifact_ref)
            if artifact_ref is not None
            else AbsentV1(kind="ABSENT")
        ),
        error=DispatchErrorV1(kind="ABSENT"),
    )


def _convert_result(
    instance: ActionInstanceV1,
    action: AgentAction,
    result: ToolResultV1,
    artifact_store: ArtifactStorePortV1,
) -> ActionResultV1:
    result_type = _result_type_for(action.action_type)
    if isinstance(
        result,
        (
            FileToolErrorV1,
            ListFilesSuccessV1,
            ReadFileSuccessV1,
            SearchTextSuccessV1,
        ),
    ):
        return _convert_file_result(
            instance, action, result, result_type, artifact_store
        )
    if isinstance(result, CandidatePatchOutcomeV1):
        if result.kind == "REJECTED":
            assert result.error_code is not None
            assert result.reason is not None
            return _envelope(
                instance, action, "FAILED", result.error_code, result.reason
            )
        return _success(instance, action, result_type, None)
    if isinstance(result, RunCheckOutcomeV1):
        if result.kind == "REJECTED":
            assert result.error_code is not None
            assert result.bounded_message is not None
            return _envelope(
                instance,
                action,
                "FAILED",
                result.error_code,
                result.bounded_message,
            )
        return _success(instance, action, result_type, None)
    if isinstance(result, CompletionOutcomeV1):
        if result.kind == "REJECTED":
            assert result.error_code is not None
            assert result.bounded_message is not None
            return _envelope(
                instance,
                action,
                "FAILED",
                result.error_code,
                result.bounded_message,
            )
        return _success(instance, action, result_type, None)
    return _envelope(
        instance,
        action,
        "FAILED",
        "INVALID_RESULT",
        f"the port returned an unknown result of type {type(result).__name__}",
    )


def _convert_file_result(
    instance: ActionInstanceV1,
    action: AgentAction,
    result: FileToolErrorV1
    | ListFilesSuccessV1
    | ReadFileSuccessV1
    | SearchTextSuccessV1,
    result_type: DispatchResultTypeV1,
    artifact_store: ArtifactStorePortV1,
) -> ActionResultV1:
    """Convert one closed file-tool result into the dispatch envelope.

    A typed tool error becomes ``FAILED`` with the tool's own stable code;
    a success payload is published to the bounded artifact store and its
    reference enters ``payload_ref=PRESENT`` (SPEC §4.2.2).  The success
    payload must belong to the selected action's result family — a
    conforming typed port cannot return a mismatched family, so any such
    result is an invalid result, not a success.
    """
    if isinstance(result, FileToolErrorV1):
        return _envelope(
            instance, action, "FAILED", result.error_code, result.bounded_message
        )
    expected = _file_success_type(action.action_type)
    if expected is None or not isinstance(result, expected):
        return _envelope(
            instance,
            action,
            "FAILED",
            "INVALID_RESULT",
            f"the {action.action_type} port returned a mismatched result of "
            f"type {type(result).__name__}",
        )
    outcome = publish_file_tool_outcome(instance, result, artifact_store)
    if outcome.kind == "REJECTED":
        assert outcome.error_code is not None
        assert outcome.bounded_message is not None
        return _envelope(
            instance,
            action,
            "FAILED",
            outcome.error_code,
            outcome.bounded_message,
        )
    return _success(instance, action, result_type, outcome.artifact_ref)


def _result_type_for(action_type: str) -> DispatchResultTypeV1:
    """SPEC §4.2.2 result family of one model action type."""
    mapping: dict[str, DispatchResultTypeV1] = {
        "list_files": "ListFilesResult",
        "read_file": "ReadFileResult",
        "search_text": "SearchTextResult",
        "apply_candidate_patch": "ApplyCandidatePatchResult",
        "run_check": "RunCheckResult",
        "propose_completion": "ProposeCompletionResult",
    }
    return mapping[action_type]


def _first_sensitive_path(action: AgentAction) -> str | None:
    """The first SPEC §1.4.3 sensitive-path rule hit by a file action.

    Path/object authorization (gate 2): list/search roots and the read
    path must not hit the shared sensitive-path rules — defense in depth
    on top of the Snapshot admission that already excludes sensitive
    tracked paths.  Patch actions carry no path fields (their paths are
    validated by the Task 12 pipeline and flow into policy as the
    pre-policy fact).
    """
    if isinstance(action, ReadFileActionV1):
        return sensitive_path_rule_id(action.path.value)
    if isinstance(action, ListFilesActionV1) and action.root.kind == "PATH":
        return sensitive_path_rule_id(action.root.path.value)
    if isinstance(action, SearchTextActionV1):
        for root in action.roots:
            if root.kind == "PATH":
                hit = sensitive_path_rule_id(root.path.value)
                if hit is not None:
                    return hit
    return None


def _policy_projection(instance: ActionInstanceV1) -> ContractsActionInstanceV1:
    """The Task 13 policy projection of one bound instance.

    The T13.1 engine evaluates the T05.1 contracts envelope, whose
    ``action`` is the shared two-field identity; the projection carries
    the same action type, id, and digests, so the memo key
    (policy digest, action type, semantic digest, context digest) is
    unchanged.
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


def _policy_context(context: DispatchContextV1) -> PolicyContextV1:
    """One immutable Task 13 policy context from the dispatch facts."""
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


def _select_port(
    ports: ToolPortsV1, action_type: str
) -> Callable[..., ToolResultV1] | None:
    """The one registered typed port for *action_type*, or None."""
    by_type: dict[str, Callable[..., ToolResultV1] | None] = {
        "list_files": ports.list_files,
        "read_file": ports.read_file,
        "search_text": ports.search_text,
        "apply_candidate_patch": ports.apply_candidate_patch,
        "run_check": ports.run_check,
        "propose_completion": ports.propose_completion,
    }
    return by_type.get(action_type)


def _call_port(
    context: DispatchContextV1, action: AgentAction, port: Callable[..., ToolResultV1]
) -> ToolResultV1:
    """Invoke the selected port with the exact pure signatures.

    The three file ports receive the context's visible tree plus the
    action (the exact Task 11.A/11.B signatures); the patch, check, and
    completion ports receive the action only — their machinery is bound by
    the successor loop.
    """
    if isinstance(action, ListFilesActionV1):
        return port(context.visible_tree, action)
    if isinstance(action, ReadFileActionV1):
        return port(context.visible_tree, action)
    if isinstance(action, SearchTextActionV1):
        return port(context.visible_tree, action)
    return port(action)


def _file_success_type(action_type: str) -> type[object] | None:
    """The one closed success class of a file action's result family, or
    ``None`` for non-file actions.

    A non-file port (patch/check/completion) must never return a file
    success payload; the caller converts ``None`` or a mismatched class
    into ``FAILED/INVALID_RESULT`` with zero publication, so this lookup
    never raises.
    """
    return {
        "list_files": ListFilesSuccessV1,
        "read_file": ReadFileSuccessV1,
        "search_text": SearchTextSuccessV1,
    }.get(action_type)
