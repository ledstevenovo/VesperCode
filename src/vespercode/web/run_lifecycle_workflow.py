"""T29.1 legacy step 29.A: run lifecycle workflow vocabulary and ports.

The module owns the closed run-lifecycle WebUI contract only: the closed
run-creation form adaptation (``CreateRunFormV1``), the closed result
unions of creation and cancellation, the three typed workflow ports
(``RunCreationWorkflowPortV1``, ``RunVisibilityWorkflowPortV1``,
``RunCancellationWorkflowPortV1``) over which the routes adapt forms
after the Task 28 request security boundary, the exact user-facing
reason/next-action text maps and the state-aware cancellable set (SPEC
§4.9 distinct labels, §5.3 comprehensible states).  Run creation rules,
lifecycle transitions, status projection, loop behavior, repositories,
and security middleware remain out of scope (GREEN-4): the ports are the
composition's injection seam and never reimplement a domain predicate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    field_validator,
    model_validator,
)

from src.vespercode.audit.projection import (
    NextActionV1,
    ReasonCodeV1,
    RunVisibilityV1,
    StateLabelV1,
)
from src.vespercode.contracts.run import RunLimitsV1

REASON_TEXT_V1: Final[dict[ReasonCodeV1, str]] = {
    "RUN_CREATED": "运行已创建",
    "RUNNING_PHASE": "正在执行阶段",
    "USER_DECISION_PENDING": "等待用户决定",
    "WAIT_CONTEXT_MISSING": "等待上下文缺失",
    "RECOVERY_PENDING": "恢复待处理",
    "RUN_SUCCEEDED": "运行成功",
    "RUN_STOPPED": "运行已停止",
}
"""One distinct user-facing text per closed reason code (SPEC §5.3)."""

NEXT_ACTION_TEXT_V1: Final[dict[NextActionV1, str]] = {
    "START": "开始运行",
    "CONTINUE": "继续运行",
    "AWAIT_USER_DECISION": "请处理等待的决定",
    "REVIEW_RECOVERY": "查看恢复",
    "RETRIEVE_EVIDENCE": "查看证据",
    "REVIEW_STOP_REASON": "查看停止原因",
}
"""One distinct user-facing text per closed next-action code (SPEC §5.3)."""

CANCELLABLE_STATE_LABELS_V1: Final[frozenset[StateLabelV1]] = frozenset(
    {
        "CREATED",
        "PREFLIGHT",
        "BASELINE",
        "AGENT_LOOP",
        "FORMAL_VALIDATION",
        "WAITING_USER",
    }
)
"""The state-aware cancellable set: the non-persisted, non-terminal
states whose cancellation is a declared action (SPEC §4.2.6/§4.2.7:
persistence, recovery, and terminal states hold and never render a
cancel control)."""

RUN_CREATE_LIMIT_FIELDS_V1: Final[tuple[tuple[str, str], ...]] = (
    ("max_turns", "最大轮数"),
    ("max_llm_calls", "最大调用次数"),
    ("max_run_wall_clock_seconds", "总墙钟上限（秒）"),
    ("user_wait_timeout_seconds", "用户等待上限（秒）"),
    ("tool_timeout_seconds", "普通工具上限（秒）"),
    ("target_check_timeout_seconds", "目标检查上限（秒）"),
    ("full_check_timeout_seconds", "完整单项检查上限（秒）"),
    ("baseline_timeout_seconds", "基线整体上限（秒）"),
    ("formal_validation_timeout_seconds", "正式验证整体上限（秒）"),
)
"""The declared create-form limit fields in display order (SPEC §4.1)."""


def cancellable(state_label: StateLabelV1) -> bool:
    """Whether one visible state may render the cancel control.

    Only the declared cancellable states render the control; persistence,
    recovery, and terminal states never do, so the page can never bypass
    the domain cancellation safe points (GREEN-2).
    """
    return state_label in CANCELLABLE_STATE_LABELS_V1


_LIMIT_FORM_RE = re.compile(r"^[0-9]+$")
"""The closed plain-decimal limit form (no sign, whitespace, separators,
or non-ASCII digits — the form carries strings, so the strict integer
contract is enforced at the closed form boundary)."""

_LIMIT_FIELD_NAMES: Final[tuple[str, ...]] = (
    "max_turns",
    "max_llm_calls",
    "max_run_wall_clock_seconds",
    "user_wait_timeout_seconds",
    "tool_timeout_seconds",
    "target_check_timeout_seconds",
    "full_check_timeout_seconds",
    "baseline_timeout_seconds",
    "formal_validation_timeout_seconds",
)


class CreateRunFormV1(BaseModel):
    """One closed run-creation form adaptation (GREEN-1).

    Only the declared create vocabulary is accepted: the workspace path,
    the target test node ids (repeated), the LLM/reference profile ids,
    and the nine frozen limits as plain-decimal string forms.  Any
    unknown or override field rejects at the closed schema before the
    workflow port is called; the limits are validated inside the
    built-in hard bounds through the T08.1 ``RunLimitsV1`` contract
    (SPEC §4.1).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    workspace_path: StrictStr
    target_test_ids: list[StrictStr]
    llm_profile_id: StrictStr
    reference_profile_id: StrictStr
    max_turns: StrictStr
    max_llm_calls: StrictStr
    max_run_wall_clock_seconds: StrictStr
    user_wait_timeout_seconds: StrictStr
    tool_timeout_seconds: StrictStr
    target_check_timeout_seconds: StrictStr
    full_check_timeout_seconds: StrictStr
    baseline_timeout_seconds: StrictStr
    formal_validation_timeout_seconds: StrictStr

    @field_validator(*_LIMIT_FIELD_NAMES)
    @classmethod
    def _limits_are_plain_decimal_forms(cls, value: str) -> str:
        if _LIMIT_FORM_RE.fullmatch(value) is None:
            raise ValueError("limit fields must be plain decimal integers")
        return value

    @model_validator(mode="after")
    def _limits_are_in_bounds(self) -> CreateRunFormV1:
        # the T08.1 RunLimitsV1 contract is the sole range authority
        self.limits
        return self

    @property
    def limits(self) -> RunLimitsV1:
        """The closed T08.1 limits the form carries (range-validated)."""
        return RunLimitsV1(
            max_turns=int(self.max_turns),
            max_llm_calls=int(self.max_llm_calls),
            max_run_wall_clock_seconds=int(self.max_run_wall_clock_seconds),
            user_wait_timeout_seconds=int(self.user_wait_timeout_seconds),
            tool_timeout_seconds=int(self.tool_timeout_seconds),
            target_check_timeout_seconds=int(self.target_check_timeout_seconds),
            full_check_timeout_seconds=int(self.full_check_timeout_seconds),
            baseline_timeout_seconds=int(self.baseline_timeout_seconds),
            formal_validation_timeout_seconds=int(
                self.formal_validation_timeout_seconds
            ),
        )


class RunCreationResultV1(BaseModel):
    """One closed run-creation outcome.

    A CREATED result carries the new run identity; a REJECTED result
    always carries the stable domain error code, a user-understandable
    reason, and a next-step suggestion (SPEC §5.3).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["CREATED", "REJECTED"]
    run_id: StrictStr | None = None
    error_code: StrictStr | None = None
    reason: StrictStr | None = None
    suggestion: StrictStr | None = None


class RunCancellationResultV1(BaseModel):
    """One closed run-cancellation outcome (idempotent per state).

    CANCELLED repeats the same result for the same state; NOT_CANCELLABLE
    and NOT_FOUND are the closed fail-closed outcomes the page can never
    provoke through its state-aware control (GREEN-2).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["CANCELLED", "NOT_CANCELLABLE", "NOT_FOUND"]
    message: StrictStr


class RunCreationWorkflowPortV1(Protocol):
    """The typed run-creation port (the composition's injection seam).

    The port owns run creation rules and repositories (Tasks 8/23/25);
    the route only adapts the closed form and forwards the outcome.
    """

    def create(self, form: CreateRunFormV1) -> RunCreationResultV1:
        """Create one run from the closed form, or reject it."""
        ...


class RunVisibilityWorkflowPortV1(Protocol):
    """The typed run-visibility port (Task 23 projection seam)."""

    def visibility_for(self, run_id: str) -> RunVisibilityV1 | None:
        """Return the bounded user-visible state of one run, or None."""
        ...


class RunCancellationWorkflowPortV1(Protocol):
    """The typed run-cancellation port (Task 25.F safe-point seam)."""

    def cancel(self, run_id: str) -> RunCancellationResultV1:
        """Cancel one run at its deterministic safe point, or close."""
        ...


@dataclass(frozen=True)
class RunLifecycleWorkflowPortsV1:
    """The immutable typed port aggregate of one run-lifecycle WebUI.

    The routes receive the three ports explicitly — there is no service
    locator or hidden workflow lookup (GREEN-1/Boundary).
    """

    creation: RunCreationWorkflowPortV1
    visibility: RunVisibilityWorkflowPortV1
    cancellation: RunCancellationWorkflowPortV1
