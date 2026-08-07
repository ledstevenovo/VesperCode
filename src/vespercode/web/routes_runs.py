"""T29.1 legacy step 29.A: run lifecycle WebUI routes.

``RunLifecycleRouteInstallerV1`` installs the closed create, detail, and
cancel routes onto one composed app; every route adapts its form to the
typed workflow ports only after the Task 28.A request security boundary
(GREEN-1), rejects unknown/override fields at the closed schema before
any domain call, and renders the state-aware escaped pages with exact
status/reason/next-action text, idempotent controls, accessible labels,
visible focus, keyboard operation, live errors, and non-color cues
(GREEN-2).  Run creation rules, lifecycle transitions, status projection,
loop behavior, repositories, and security middleware remain out of scope
(GREEN-4).
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from starlette.datastructures import FormData

from vespercode.audit.projection import RunVisibilityV1
from vespercode.web.app import render_status_badge
from vespercode.web.run_lifecycle_workflow import (
    NEXT_ACTION_TEXT_V1,
    REASON_TEXT_V1,
    RUN_CREATE_LIMIT_FIELDS_V1,
    CreateRunFormV1,
    RunLifecycleWorkflowPortsV1,
    cancellable,
)


class RunLifecycleRouteInstallerV1:
    """Install the closed run-lifecycle routes over the typed ports.

    The installer receives the immutable port aggregate explicitly; the
    routes are declared inside ``install`` so they close over exactly the
    injected ports and never look routes or ports up anywhere else
    (GREEN-1/Boundary).
    """

    def __init__(self, ports: RunLifecycleWorkflowPortsV1) -> None:
        self._ports = ports

    def install(self, app: FastAPI) -> None:
        @app.get("/runs/new", response_class=HTMLResponse)
        def run_create_page(request: Request) -> HTMLResponse:
            """One escaped closed run-creation form page."""
            return _render_create_page(app, request)

        @app.post("/runs")
        async def create_run(request: Request) -> Any:
            """Adapt one closed create form to the typed port (GREEN-1).

            Unknown and override fields reject at the closed schema with
            the stable FORM_INVALID payload before any domain call; a
            domain rejection re-renders its stable reason and next step;
            a created run redirects to its detail page.
            """
            form_raw = _form_to_dict(await request.form())
            if "target_test_ids" in form_raw and not isinstance(
                form_raw["target_test_ids"], list
            ):
                # one target is still a list of one after adaptation
                form_raw["target_test_ids"] = [form_raw["target_test_ids"]]
            try:
                form = CreateRunFormV1.model_validate(form_raw)
            except ValidationError:
                return _form_invalid("创建表单包含未声明或非法的字段。")
            result = self._ports.creation.create(form)
            if result.kind == "CREATED":
                if result.run_id is None:
                    return _form_invalid("创建结果缺少运行标识。")
                return RedirectResponse(f"/runs/{result.run_id}", status_code=303)
            return JSONResponse(
                status_code=422,
                content={
                    "error_code": result.error_code or "RUN_CREATE_REJECTED",
                    "message": result.reason or "运行创建被拒绝。",
                    "next_step": result.suggestion or "请检查输入后重试。",
                },
            )

        @app.get("/runs/{run_id}", response_class=HTMLResponse)
        def run_detail(request: Request, run_id: str) -> Any:
            """One state-aware escaped run detail page (GREEN-2)."""
            visibility = self._ports.visibility.visibility_for(run_id)
            if visibility is None:
                return _run_not_found()
            return _render_detail_page(app, request, visibility)

        @app.post("/runs/{run_id}/cancel")
        async def cancel_run(request: Request, run_id: str) -> Any:
            """Cancel one run through the typed port (idempotent control).

            The cancel form declares no fields: any submitted field is an
            unknown/override attempt and rejects before the domain call.
            The page only renders the control for cancellable states, and
            the closed NOT_CANCELLABLE/NOT_FOUND outcomes map to stable
            statuses (GREEN-2).
            """
            form_raw = _form_to_dict(await request.form())
            if form_raw:
                return _form_invalid("取消表单不接受任何字段。")
            result = self._ports.cancellation.cancel(run_id)
            if result.kind == "CANCELLED":
                return RedirectResponse(f"/runs/{run_id}", status_code=303)
            if result.kind == "NOT_CANCELLABLE":
                return JSONResponse(
                    status_code=409,
                    content={
                        "error_code": "RUN_NOT_CANCELLABLE",
                        "message": result.message,
                        "next_step": "该运行状态不允许取消，请查看运行详情。",
                    },
                )
            return _run_not_found()


def _form_to_dict(form: FormData) -> dict[str, object]:
    """One raw form mapping with repeated keys grouped into lists.

    The closed form schemas parse this mapping; repeated keys (the target
    node ids) become lists and every other key stays a single string.
    """
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


def _run_not_found() -> JSONResponse:
    """One stable unknown-run rejection."""
    return JSONResponse(
        status_code=404,
        content={
            "error_code": "RUN_NOT_FOUND",
            "message": "运行不存在。",
            "next_step": "请从主页选择现有运行。",
        },
    )


def _render_create_page(app: FastAPI, request: Request) -> HTMLResponse:
    """One escaped run-creation page over the closed form fields.

    The page carries the session's CSRF token in a meta element and the
    htmx wiring that attaches it as the Task 28.A header on every POST
    (the HttpOnly cookie is never script-readable); errors surface
    through the base page's assertive live-error region, never as
    repository HTML.
    """
    templates = cast(Jinja2Templates, app.state.local_templates)
    return templates.TemplateResponse(
        request,
        "run_create.html",
        {
            "csp_nonce": request.state.csp_nonce,
            "csrf_token": request.state.local_session.csrf_token,
            "limit_fields": RUN_CREATE_LIMIT_FIELDS_V1,
        },
    )


def _render_detail_page(
    app: FastAPI,
    request: Request,
    visibility: RunVisibilityV1,
) -> HTMLResponse:
    """One state-aware escaped run detail page (GREEN-2).

    The page renders the exact state label (through the semantic status
    badge with its non-color cue), the exact reason and next-action text,
    and the cancel control only when the state is cancellable — never the
    internal projection rows or forbidden override fields.
    """
    templates = cast(Jinja2Templates, app.state.local_templates)
    return templates.TemplateResponse(
        request,
        "run_detail.html",
        {
            "csp_nonce": request.state.csp_nonce,
            "csrf_token": request.state.local_session.csrf_token,
            "visibility": visibility,
            "reason_text": REASON_TEXT_V1[visibility.reason_code],
            "next_action_text": NEXT_ACTION_TEXT_V1[visibility.next_action],
            "cancellable": cancellable(visibility.state_label),
            "render_status_badge": render_status_badge,
        },
    )
