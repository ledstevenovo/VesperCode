"""T29.2 legacy step 29.B: disclosure decision WebUI routes.

``DisclosureRouteInstallerV1`` installs the disclosure wait page and the
closed decision route onto one composed app; the page renders the exact
provider/endpoint/category/path/budget disclosure facts from the bound
subject and the trusted endpoint map (GREEN-1) and the decision route
accepts only one bound approve/reject decision after the Task 28
request security, rejecting scope/endpoint/budget/credential/clock
overrides and stale bindings before the workflow port (GREEN-2), and
never constructs, widens, or mutates a Grant (GREEN-4/Boundary).
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from starlette.datastructures import FormData

from vespercode.contracts.run import WaitDecisionChoiceV1
from vespercode.profiles.endpoints import OpenAIEndpointRegistry
from vespercode.web.disclosure_workflow import (
    DisclosureDecisionFormV1,
    DisclosureDecisionWorkflowPortV1,
    WorkflowIdentityPortV1,
    build_authorization_summary,
    build_disclosure_decision_command,
    render_authorization_summary,
)


class DisclosureRouteInstallerV1:
    """Install the closed disclosure routes over the typed port.

    The installer receives the workflow port and the control-plane
    identity seam explicitly; the routes close over exactly the injected
    objects and never look ports up anywhere else (GREEN-1/Boundary).
    """

    def __init__(
        self,
        ports: DisclosureDecisionWorkflowPortV1,
        identity: WorkflowIdentityPortV1,
    ) -> None:
        self._ports = ports
        self._identity = identity

    def install(self, app: FastAPI) -> None:
        @app.get("/runs/{run_id}/disclosure", response_class=HTMLResponse)
        def disclosure_wait(request: Request, run_id: str) -> Any:
            """One escaped disclosure wait page (GREEN-1).

            The summary is built only from the exact bound subject and
            the trusted built-in endpoint record; the decision form is
            rendered only while the wait is undecided (state-aware
            controls), and the page carries the CSRF token delivery.
            """
            wait = self._ports.disclosure_wait_for(run_id)
            if wait is None:
                return _disclosure_not_found()
            summary = build_authorization_summary(
                wait.subject,
                OpenAIEndpointRegistry.resolve(wait.subject.endpoint_id),
            )
            templates = cast(Jinja2Templates, app.state.local_templates)
            return templates.TemplateResponse(
                request,
                "disclosure_wait.html",
                {
                    "csp_nonce": request.state.csp_nonce,
                    "csrf_token": request.state.local_session.csrf_token,
                    "wait": wait,
                    "summary_markup": render_authorization_summary(summary),
                },
            )

        @app.post("/runs/{run_id}/disclosure")
        async def disclosure_decide(request: Request, run_id: str) -> Any:
            """Submit exactly one bound decision (GREEN-2).

            Unknown and override fields reject at the closed schema with
            the stable FORM_INVALID payload; a stale wait/subject binding
            rejects with 409 before the workflow port; a valid decision
            forwards the bound command and maps the closed outcome.
            """
            form_raw = _form_to_dict(await request.form())
            try:
                form = DisclosureDecisionFormV1.model_validate(form_raw)
            except ValidationError:
                return _form_invalid("披露决定表单包含未声明或非法的字段。")
            wait = self._ports.disclosure_wait_for(run_id)
            if wait is None:
                return _disclosure_not_found()
            if (
                form.wait_id != wait.wait_id
                or form.subject_digest != wait.subject.digest
            ):
                return _stale("披露等待的绑定已变化，请刷新页面后重新决定。")
            decision: WaitDecisionChoiceV1 = (
                "APPROVE" if form.decision == "approve" else "REJECT"
            )
            command = build_disclosure_decision_command(wait, decision, self._identity)
            result = self._ports.decide(command)
            if result.kind in ("APPROVED", "REJECTED", "REPLAY"):
                # a replay is the idempotent repeat of the same decision
                return RedirectResponse(f"/runs/{run_id}", status_code=303)
            if result.kind == "CONFLICT":
                return JSONResponse(
                    status_code=409,
                    content={
                        "error_code": "DISCLOSURE_CONFLICT",
                        "message": result.message,
                        "next_step": "刷新页面后查看当前决定。",
                    },
                )
            return JSONResponse(
                status_code=409,
                content={
                    "error_code": "DISCLOSURE_DECISION_REJECTED",
                    "message": result.message,
                    "next_step": "刷新页面后重试。",
                },
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


def _disclosure_not_found() -> JSONResponse:
    """One stable unknown-wait rejection."""
    return JSONResponse(
        status_code=404,
        content={
            "error_code": "DISCLOSURE_WAIT_NOT_FOUND",
            "message": "该运行没有待处理的披露等待。",
            "next_step": "请从运行详情页确认当前状态。",
        },
    )


def _stale(message: str) -> JSONResponse:
    """One stable stale-binding rejection (AC-27, no domain call)."""
    return JSONResponse(
        status_code=409,
        content={
            "error_code": "DISCLOSURE_STALE",
            "message": message,
            "next_step": "请刷新页面后重新决定。",
        },
    )
