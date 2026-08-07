"""T38.1 legacy step 38.C: redacted audit WebUI routes.

``AuditWorkflowPortsV1`` is the closed typed seam exposing exactly
``list_run`` (Task 23.B closed keyset page projection) and
``clear_ended_run`` (Task 23.C closed clear command), and
``AuditRouteInstallerV1`` installs the audit page and the explicit
ended-Run clear route: the page consumes only the redacted page
projection, preserves the monotonic cursor ordering with bounded
pagination, and renders the retention state with explicit clear
confirmation (GREEN-1/GREEN-2).  The rendered entry facts are closed
literals only — free-text identifiers and raw bodies can never reach
the page, so the raw-request/backup-body sentinel contract holds on
every rendered page and error branch (GREEN-3).  Internal DB columns,
raw bodies, active/foreign/stale/unsafe deletion, recovery-evidence
loss, and repository-rule bypass remain out of scope (GREEN-4/Boundary):
the clear control renders only for an ended Run without unresolved
recovery evidence, and the domain command remains the sole deletion
path.

Recorded interface interpretation (reviewer-flagged, T29.3 precedent
class): the card's two named port methods are the exact delegation
surface; the route additionally reads the run's clear state through the
``clear_state_for`` extension method because the WebUI cannot access
the database directly (SPEC §6.1) and the card requires the ended-Run /
unresolved-recovery gate to be decided before any clear control is
rendered.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, StrictStr, ValidationError
from starlette.datastructures import FormData

from src.vespercode.audit.event import (
    ActionPayloadV1,
    AuditPayloadV1,
    CheckResultPayloadV1,
    DisclosureAuthorizationPayloadV1,
    DisclosureGrantPayloadV1,
    FinalWritebackApprovalPayloadV1,
    LifecyclePayloadV1,
    PolicyDecisionPayloadV1,
    RecoveryPayloadV1,
    StopEvidencePayloadV1,
)
from src.vespercode.audit.repository import (
    AuditClearResultV1,
    AuditCursorV1,
    AuditPageRequestV1,
    AuditPageV1,
    AuditPaginationErrorV1,
    ClearEndedRunAuditV1,
)
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1

AUDIT_PAGE_SIZE_V1 = 20
"""The fixed bounded page size of the audit WebUI (SPEC §5.1 bounds)."""

AUDIT_EVENT_TYPE_LABELS_V1: dict[str, str] = {
    "LIFECYCLE": "生命周期",
    "ACTION": "动作",
    "POLICY_DECISION": "策略决定",
    "FINAL_WRITEBACK_APPROVAL": "最终写回批准",
    "DISCLOSURE_GRANT": "披露授权",
    "DISCLOSURE_AUTHORIZATION": "逐请求披露授权",
    "CHECK_RESULT": "检查结果",
    "RECOVERY": "恢复",
    "STOP_EVIDENCE": "停止证据",
    "LLM_CALL": "LLM 调用",
}
"""One distinct user-facing text per closed audit event type."""

_LIFECYCLE_STATUS_LABELS_V1: dict[str, str] = {
    "CREATED": "已创建",
    "RUNNING": "运行中",
    "WAITING_USER": "等待用户决定",
    "RECOVERY_REQUIRED": "恢复阻塞",
    "SUCCEEDED": "成功",
    "STOPPED": "已停止",
}

_LIFECYCLE_PHASE_LABELS_V1: dict[str, str] = {
    "PREFLIGHT": "预检",
    "BASELINE": "基线",
    "AGENT_LOOP": "主循环",
    "FORMAL_VALIDATION": "正式验证",
    "PERSISTENCE": "持久化",
}

_POLICY_LABELS_V1: dict[str, str] = {
    "ALLOW": "允许",
    "ASK": "询问",
    "DENY": "拒绝",
}

_APPROVAL_STATUS_LABELS_V1: dict[str, str] = {
    "PENDING": "待定",
    "APPROVED": "已批准",
    "REJECTED": "已拒绝",
    "EXPIRED": "已过期",
}

_DISCLOSURE_STATUS_LABELS_V1: dict[str, str] = {
    "ACTIVE": "有效",
    "EXHAUSTED": "已耗尽",
    "REVOKED": "已撤销",
    "EXPIRED": "已过期",
}

_AUTHORIZATION_CATEGORY_LABELS_V1: dict[str, str] = {
    "ROOT": "整个仓库",
    "FILE": "文件",
    "DIRECTORY": "目录",
}

_CHECK_KIND_LABELS_V1: dict[str, str] = {
    "TARGET_TESTS": "目标测试",
    "FULL_PYTEST": "完整测试",
    "RUFF": "Ruff",
    "MYPY": "Mypy",
}

_CHECK_STATUS_LABELS_V1: dict[str, str] = {
    "PASS": "通过",
    "FAIL": "失败",
    "ERROR": "错误",
    "BLOCKED": "阻断",
}

_RECOVERY_DISPOSITION_LABELS_V1: dict[str, str] = {
    "COMMITTED": "已提交",
    "ROLLED_BACK": "已回滚",
    "UNRESOLVED": "未解决",
}

_LLM_OUTCOME_LABELS_V1: dict[str, str] = {
    "COMPLETED": "已完成",
    "FAILED": "失败",
    "NOT_ATTEMPTED": "未尝试",
}


def event_type_label(event_type: str) -> str:
    """One distinct user-facing text per closed audit event type."""
    return AUDIT_EVENT_TYPE_LABELS_V1[event_type]


def render_payload_facts(payload: AuditPayloadV1) -> tuple[str, ...]:
    """One bounded fact-line of one redacted payload.

    Only closed-literal fields are rendered — a hostile free-text value
    (action type, reason code, transaction id, byte count, evidence
    reference) can never reach the page, so the raw-request/backup-body
    sentinel contract holds by construction (GREEN-3).  An UNRESOLVED
    recovery fact additionally yields the recovery warning marker.
    """
    if isinstance(payload, LifecyclePayloadV1):
        facts = [f"状态：{_LIFECYCLE_STATUS_LABELS_V1[payload.status]}"]
        if payload.phase is not None:
            facts.append(f"阶段：{_LIFECYCLE_PHASE_LABELS_V1[payload.phase]}")
        return tuple(facts)
    if isinstance(payload, ActionPayloadV1):
        return (f"策略决策：{_POLICY_LABELS_V1[payload.policy_decision]}",)
    if isinstance(payload, PolicyDecisionPayloadV1):
        return (f"决定：{_POLICY_LABELS_V1[payload.decision]}",)
    if isinstance(payload, FinalWritebackApprovalPayloadV1):
        return (f"状态：{_APPROVAL_STATUS_LABELS_V1[payload.status]}",)
    if isinstance(payload, DisclosureGrantPayloadV1):
        return (f"状态：{_DISCLOSURE_STATUS_LABELS_V1[payload.status]}",)
    if isinstance(payload, DisclosureAuthorizationPayloadV1):
        return (f"类别：{_AUTHORIZATION_CATEGORY_LABELS_V1[payload.category]}",)
    if isinstance(payload, CheckResultPayloadV1):
        return (
            f"检查：{_CHECK_KIND_LABELS_V1[payload.check_kind]}",
            f"结果：{_CHECK_STATUS_LABELS_V1[payload.status]}",
        )
    if isinstance(payload, RecoveryPayloadV1):
        return (f"处置：{_RECOVERY_DISPOSITION_LABELS_V1[payload.disposition]}",)
    if isinstance(payload, StopEvidencePayloadV1):
        return ("已记录停止证据",)
    return (f"结果：{_LLM_OUTCOME_LABELS_V1[payload.outcome]}",)


def payload_has_unresolved_recovery(payload: AuditPayloadV1) -> bool:
    """Whether one redacted payload is an UNRESOLVED recovery fact."""
    return (
        isinstance(payload, RecoveryPayloadV1) and payload.disposition == "UNRESOLVED"
    )


class AuditClearStateV1(BaseModel):
    """One closed read-only clear-state of one Run's audit.

    ``run_ended`` and ``has_unresolved_recovery`` are the exact gates the
    page uses to decide whether the explicit clear control may render
    (SPEC §4.7/§5.6: only an ended Run without unresolved recovery
    evidence can be cleared).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: StrictStr
    run_ended: bool
    has_unresolved_recovery: bool


class AuditWorkflowIdentityPortV1(Protocol):
    """The injected control-plane identity seam of one clear operation.

    The clear event id and time are created server-side through this
    seam — the form can never supply them (SPEC §5.4).
    """

    def new_event_id(self) -> str:
        """One harness-generated clear event identity."""
        ...

    def now(self) -> CanonicalTimestampV1:
        """The sole current-time source of one clear."""
        ...


class AuditWorkflowPortsV1(Protocol):
    """The closed typed audit workflow seam (injection point).

    The routes consume only the Task 23.B redacted page projection and
    the Task 23.C closed clear command; sequencing, redaction, retention,
    and deletion rules live behind the port (Task 23), never in the
    WebUI (GREEN-4).
    """

    def list_run(self, run_id: str, page: AuditPageRequestV1) -> AuditPageV1:
        """One bounded ordered redacted page of the Run's events."""
        ...

    def clear_ended_run(self, command: ClearEndedRunAuditV1) -> AuditClearResultV1:
        """Explicitly clear the ended Run's local audit atomically."""
        ...

    def clear_state_for(self, run_id: str) -> AuditClearStateV1:
        """The read-only clear state (endedness, unresolved recovery)."""
        ...


class ConfirmAuditClearFormV1(BaseModel):
    """One closed explicit clear confirmation form adaptation.

    Only the literal ``yes`` confirmation is accepted; any other field
    (targets, run ids, event ids, times, force/ignore/skip controls)
    rejects before the domain command is built.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    confirm: Literal["yes"]


class AuditRouteInstallerV1:
    """Install the closed audit routes over the typed port.

    The installer receives the port and the identity seam explicitly; the
    routes close over exactly the injected objects and never look ports
    up anywhere else (GREEN-1/Boundary).
    """

    def __init__(
        self,
        ports: AuditWorkflowPortsV1,
        identity: AuditWorkflowIdentityPortV1,
    ) -> None:
        self._ports = ports
        self._identity = identity

    def install(self, app: FastAPI) -> None:
        @app.get("/runs/{run_id}/audit", response_class=HTMLResponse)
        def audit_page(request: Request, run_id: str, cursor: str | None = None) -> Any:
            """One escaped redacted audit page (GREEN-1/GREEN-2).

            The page consumes only the redacted keyset projection in the
            monotonic cursor order with the fixed bounded page size; a
            cursor that cannot bind the Run fails closed with zero
            partial results.
            """
            page_request = _page_request(run_id, cursor)
            if page_request is None:
                return _invalid_cursor()
            try:
                page = self._ports.list_run(run_id, page_request)
            except AuditPaginationErrorV1:
                return _invalid_cursor()
            clear_state = self._ports.clear_state_for(run_id)
            return _render_audit_page(
                app,
                request,
                page,
                clear_state,
                error_message=None,
            )

        @app.post("/runs/{run_id}/audit/clear")
        async def audit_clear(request: Request, run_id: str) -> Any:
            """Explicitly clear the ended Run's local audit (GREEN-2).

            Only the literal confirmation is accepted; a rejected,
            foreign, stale, or unsafe clear never reaches the domain
            command with the wrong state, and a failed clear re-renders
            the real page with the bounded error.
            """
            form_raw = _form_to_dict(await request.form())
            try:
                ConfirmAuditClearFormV1.model_validate(form_raw)
            except ValidationError:
                return _form_invalid("清除确认表单包含未声明或非法的字段。")
            command = ClearEndedRunAuditV1(
                run_id=run_id,
                event_id=self._identity.new_event_id(),
                decided_at=self._identity.now(),
            )
            result = self._ports.clear_ended_run(command)
            if result.kind in ("CLEARED", "REPLAY"):
                return RedirectResponse(f"/runs/{run_id}/audit", status_code=303)
            page = self._ports.list_run(
                run_id,
                AuditPageRequestV1(page_size=AUDIT_PAGE_SIZE_V1, cursor=None),
            )
            return _render_audit_page(
                app,
                request,
                page,
                self._ports.clear_state_for(run_id),
                error_message=result.message,
            )


def _page_request(run_id: str, cursor: str | None) -> AuditPageRequestV1 | None:
    """One closed bounded page request, or None for a malformed cursor.

    The cursor form is the plain decimal last-sequence of the exact Run
    (the keyset position); any other spelling fails closed.
    """
    if cursor is None:
        return AuditPageRequestV1(page_size=AUDIT_PAGE_SIZE_V1, cursor=None)
    if not cursor.isdecimal():
        return None
    return AuditPageRequestV1(
        page_size=AUDIT_PAGE_SIZE_V1,
        cursor=AuditCursorV1(run_id=run_id, last_sequence=int(cursor)),
    )


def _form_to_dict(form: FormData) -> dict[str, object]:
    """One raw form mapping with repeated keys grouped into lists."""
    items: dict[str, list[str]] = {}
    for key, value in form.multi_items():
        items.setdefault(key, []).append(str(value))
    return {
        key: (values[0] if len(values) == 1 else values)
        for key, values in items.items()
    }


def _form_invalid(message: str) -> JSONResponse:
    """One stable closed-form rejection (SPEC §5.3 style)."""
    return JSONResponse(
        status_code=422,
        content={
            "error_code": "FORM_INVALID",
            "message": message,
            "next_step": "请仅提交声明字段。",
        },
    )


def _invalid_cursor() -> JSONResponse:
    """One stable closed cursor rejection (zero partial results)."""
    return JSONResponse(
        status_code=422,
        content={
            "error_code": "CURSOR_INVALID",
            "message": "分页游标非法或不属于该运行。",
            "next_step": "请从审计页第一页开始浏览。",
        },
    )


def _render_audit_page(
    app: FastAPI,
    request: Request,
    page: AuditPageV1,
    clear_state: AuditClearStateV1,
    *,
    error_message: str | None,
) -> HTMLResponse:
    """One escaped redacted audit page (GREEN-2).

    The page renders the bounded fact lines, the next-page cursor link,
    the retention state, the unresolved-recovery warning, and the
    explicit clear confirmation only for an ended Run without unresolved
    recovery evidence.
    """
    templates = _templates(app)
    return templates.TemplateResponse(
        request,
        "audit.html",
        {
            "csp_nonce": request.state.csp_nonce,
            "csrf_token": request.state.local_session.csrf_token,
            "run_id": page.run_id,
            "items": page.items,
            "next_cursor": page.next_cursor,
            "clear_state": clear_state,
            "error_message": error_message,
            "event_type_label": event_type_label,
            "render_payload_facts": render_payload_facts,
            "payload_has_unresolved_recovery": payload_has_unresolved_recovery,
        },
    )


def _templates(app: FastAPI) -> Jinja2Templates:
    """The packaged template loader of the composed app."""
    templates = app.state.local_templates
    assert isinstance(templates, Jinja2Templates)
    return templates
