"""T29.3 legacy step 29.C: final writeback WebUI routes.

``FinalWritebackRouteInstallerV1`` installs the final-writeback review
page and the closed decision route onto one composed app; the page
renders the exact FinalDiff/evidence/subject (GREEN-1) and the decision
route accepts only one bound final approve/reject decision after the
Task 28 request security, rejecting stale or override fields before any
domain call, so a stale write can never reach the Task 26.E persistence
port (GREEN-2/Boundary).
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import ValidationError
from starlette.datastructures import FormData

from src.vespercode.contracts.run import WaitDecisionChoiceV1
from src.vespercode.web.disclosure_workflow import WorkflowIdentityPortV1
from src.vespercode.web.writeback_workflow import (
    FinalWritebackDecisionFormV1,
    FinalWritebackWorkflowPortV1,
    build_final_writeback_decision_command,
    render_writeback_review_page,
)


class FinalWritebackRouteInstallerV1:
    """Install the closed final-writeback routes over the typed port.

    The installer receives the workflow port and the control-plane
    identity seam explicitly; the routes close over exactly the injected
    objects and never look ports up anywhere else (GREEN-1/Boundary).
    """

    def __init__(
        self,
        ports: FinalWritebackWorkflowPortV1,
        identity: WorkflowIdentityPortV1,
    ) -> None:
        self._ports = ports
        self._identity = identity

    def install(self, app: FastAPI) -> None:
        @app.get("/runs/{run_id}/final-writeback", response_class=HTMLResponse)
        def writeback_review(request: Request, run_id: str) -> Any:
            """One escaped final-writeback review page (GREEN-1).

            The review is the exact current FinalDiff/evidence/subject
            from the workflow port — the route never constructs or
            accepts candidate/diff/evidence/workspace/policy fields —
            and the decision form renders only while the wait is
            undecided (state-aware controls).
            """
            review = self._ports.writeback_review_for(run_id)
            if review is None:
                return _review_not_found()
            return HTMLResponse(
                content=str(
                    render_writeback_review_page(
                        review,
                        csrf_token=request.state.local_session.csrf_token,
                        csp_nonce=request.state.csp_nonce,
                    )
                )
            )

        @app.post("/runs/{run_id}/final-writeback")
        async def writeback_decide(request: Request, run_id: str) -> Any:
            """Submit exactly one bound final decision (GREEN-2).

            Unknown and override fields reject at the closed schema with
            the stable FORM_INVALID payload; a stale wait/subject binding
            rejects with 409 before any domain call (so no stale write
            can ever reach the persistence port); a valid decision
            forwards the bound command and maps the closed outcome.
            """
            form_raw = _form_to_dict(await request.form())
            try:
                form = FinalWritebackDecisionFormV1.model_validate(form_raw)
            except ValidationError:
                return _form_invalid("写回决定表单包含未声明或非法的字段。")
            review = self._ports.writeback_review_for(run_id)
            if review is None:
                return _review_not_found()
            if (
                form.wait_id != review.wait_id
                or form.subject_digest != review.subject.digest
            ):
                return _stale("写回等待的绑定已变化，请刷新页面后重新决定。")
            decision: WaitDecisionChoiceV1 = (
                "APPROVE" if form.decision == "approve" else "REJECT"
            )
            command = build_final_writeback_decision_command(
                review, decision, self._identity
            )
            outcome = self._ports.decide(command)
            if outcome.kind in ("APPROVED", "REJECTED", "REPLAY"):
                # a replay is the idempotent repeat of the same decision
                return RedirectResponse(f"/runs/{run_id}", status_code=303)
            if outcome.kind == "CONFLICT":
                return JSONResponse(
                    status_code=409,
                    content={
                        "error_code": "WRITEBACK_CONFLICT",
                        "message": outcome.message,
                        "next_step": "刷新页面后查看当前决定。",
                    },
                )
            return JSONResponse(
                status_code=409,
                content={
                    "error_code": "WRITEBACK_DECISION_REJECTED",
                    "message": outcome.message,
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


def _review_not_found() -> JSONResponse:
    """One stable unknown-review rejection."""
    return JSONResponse(
        status_code=404,
        content={
            "error_code": "WRITEBACK_REVIEW_NOT_FOUND",
            "message": "该运行没有待处理的写回审查。",
            "next_step": "请从运行详情页确认当前状态。",
        },
    )


def _stale(message: str) -> JSONResponse:
    """One stable stale-binding rejection (AC-27, no domain call)."""
    return JSONResponse(
        status_code=409,
        content={
            "error_code": "WRITEBACK_STALE",
            "message": message,
            "next_step": "请刷新页面后重新决定。",
        },
    )
