"""T38.1 legacy step 38.B: workspace memory WebUI routes.

``MemoryWorkflowPortsV1`` is the closed typed seam exposing exactly
``list``/``create``/``confirm``/``clear`` over the Run-bound commands,
and ``MemoryRouteInstallerV1`` installs the memory page and the three
closed mutation routes: the workspace scope is always derived from the
Run by the port (the form can never select a workspace — any
client-selected ``workspace_id`` or control/policy field rejects at the
closed schema before command construction with zero port calls,
GREEN-1), the page renders creator/source/scope and the create->
confirm->clear state with scanable hierarchy, explicit labels, keyboard
focus, live error/status regions, escaped content, and no control/policy
fields (GREEN-2), and only user-authored ``PROJECT_CONVENTION`` follows
create->confirm — no generic model write or field affecting
policy/Manifest/approval/disclosure/config/success is accepted
(GREEN-4/Boundary).

Recorded interface interpretation (reviewer-flagged): the card's
displayed ``MemoryWorkflowPortsV1.clear(command) -> MemoryMutationResultV1``
return type is read as the closed memory mutation result family; the
clear operation returns the Task 22.1 closed ``MemoryClearResultV1``,
because the frozen ``MemoryMutationKindV1`` vocabulary
(CREATED/CONFIRMED/REPLAY/EVENT_ID_REUSE_CONFLICT/REJECTED/FAILED)
cannot represent a fresh clear success — SPEC §4.7 requires a closed
"清除结果" (the domain clear vocabulary with ``CLEARED``).  The
create/confirm methods return ``MemoryMutationResultV1`` exactly as
displayed.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Protocol

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError
from starlette.datastructures import FormData

from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.memory.clear import MemoryClearResultV1
from vespercode.memory.entry import (
    MemoryCreatorV1,
    MemoryEntryV1,
    MemoryKindV1,
    MemoryMutationResultV1,
    MemorySourceV1,
)

_MEMORY_SUMMARY_MAX_CHARS = 2048
_MEMORY_SOURCE_REF_MAX_CHARS = 256

CREATOR_LABELS_V1: dict[MemoryCreatorV1, str] = {
    "USER": "用户",
    "CONTROL_PLANE": "控制面",
    "MODEL": "模型",
}
"""One distinct user-facing text per closed memory creator."""

KIND_LABELS_V1: dict[MemoryKindV1, str] = {
    "PROJECT_CONVENTION": "项目约定",
    "USER_DECISION": "用户决定",
    "RUN_SUMMARY": "运行总结",
    "KNOWN_FAILURE": "已知失败",
}
"""One distinct user-facing text per closed memory kind."""

SOURCE_LABELS_V1: dict[str, str] = {
    "USER_VISIBLE_TEXT": "用户可见文本",
    "USER_DECISION": "用户决定",
    "RUN_SUMMARY": "运行总结",
    "KNOWN_FAILURE": "已知失败",
}
"""One distinct user-facing text per closed memory content-source kind."""


def source_label(source: MemorySourceV1) -> str:
    """One exact user-facing source label (SPEC §4.7 attribution)."""
    return SOURCE_LABELS_V1[source.kind]


def creator_label(creator: MemoryCreatorV1) -> str:
    """One exact user-facing creator label (SPEC §4.7 attribution)."""
    return CREATOR_LABELS_V1[creator]


def kind_label(kind: MemoryKindV1) -> str:
    """One exact user-facing memory kind label."""
    return KIND_LABELS_V1[kind]


class MemoryWorkflowIdentityPortV1(Protocol):
    """The injected control-plane identity seam of one memory operation.

    Entry ids, event ids, and times are created server-side through this
    seam — the form can never supply them, so replay identity and
    ordering stay under the composition's control (SPEC §5.4).
    """

    def new_event_id(self) -> str:
        """One harness-generated mutation event identity."""
        ...

    def new_entry_id(self) -> str:
        """One harness-generated memory entry identity."""
        ...

    def now(self) -> CanonicalTimestampV1:
        """The sole current-time source of one operation."""
        ...


class CreateMemoryForRunV1(BaseModel):
    """One closed create command bound to its Run (GREEN-1).

    The command carries the Run id and the operation-visible fields
    (kind, summary, source reference, user creator) plus the
    server-controlled identities; it never carries a client-selected
    workspace identity — the port derives the workspace scope from the
    Run.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: StrictStr
    kind: Literal["PROJECT_CONVENTION"]
    summary: Annotated[
        StrictStr, Field(min_length=1, max_length=_MEMORY_SUMMARY_MAX_CHARS)
    ]
    source_reference: Annotated[
        StrictStr, Field(min_length=1, max_length=_MEMORY_SOURCE_REF_MAX_CHARS)
    ]
    creator: Literal["USER"]
    entry_id: StrictStr
    event_id: StrictStr
    decided_at: CanonicalTimestampV1


class ConfirmMemoryForRunV1(BaseModel):
    """One closed confirm command bound to its Run (GREEN-1)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: StrictStr
    entry_id: StrictStr
    creator: Literal["USER"]
    event_id: StrictStr
    decided_at: CanonicalTimestampV1


class ClearMemoryForRunV1(BaseModel):
    """One closed clear command bound to its Run (GREEN-1).

    The targets are the Run-visible entry ids only; the workspace scope
    is derived by the port, never selected by the client.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: StrictStr
    target_entry_ids: tuple[StrictStr, ...] = Field(min_length=1, max_length=100)
    creator: Literal["USER"]
    event_id: StrictStr
    decided_at: CanonicalTimestampV1


class MemoryWorkflowPortsV1(Protocol):
    """The closed typed memory workflow seam (injection point).

    The routes adapt the closed forms only through these exact methods;
    workspace scope resolution, creation/confirmation/clearing rules,
    and repositories live behind the port (Task 22), never in the WebUI
    (GREEN-4).
    """

    def list(self, run_id: str) -> tuple[MemoryEntryV1, ...]:
        """The non-cleared entries of the Run's derived workspace."""
        ...

    def create(self, command: CreateMemoryForRunV1) -> MemoryMutationResultV1:
        """Create one user-authored project convention for the Run."""
        ...

    def confirm(self, command: ConfirmMemoryForRunV1) -> MemoryMutationResultV1:
        """Confirm one existing project convention for the Run."""
        ...

    def clear(self, command: ClearMemoryForRunV1) -> MemoryClearResultV1:
        """Clear the targeted Run-visible entries (closed clear result)."""
        ...


class CreateMemoryFormV1(BaseModel):
    """One closed memory create form adaptation (GREEN-1).

    Only the summary and the source reference are accepted; the kind and
    the creator are server-fixed to ``PROJECT_CONVENTION``/``USER``, and
    any unknown or override field (workspace id, kind, creator, policy,
    Manifest, approval, disclosure, config, ...) rejects at the closed
    schema before command construction.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    summary: Annotated[
        StrictStr, Field(min_length=1, max_length=_MEMORY_SUMMARY_MAX_CHARS)
    ]
    source_reference: Annotated[
        StrictStr, Field(min_length=1, max_length=_MEMORY_SOURCE_REF_MAX_CHARS)
    ]


class ConfirmMemoryFormV1(BaseModel):
    """One closed memory confirm form adaptation (entry target only)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    entry_id: StrictStr


class ClearMemoryFormV1(BaseModel):
    """One closed memory clear form adaptation (entry targets only)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    entry_ids: list[StrictStr] = Field(min_length=1, max_length=100)


class MemoryRouteInstallerV1:
    """Install the closed memory routes over the typed port.

    The installer receives the port and the identity seam explicitly; the
    routes close over exactly the injected objects and never look ports
    up anywhere else (GREEN-1/Boundary).
    """

    def __init__(
        self,
        ports: MemoryWorkflowPortsV1,
        identity: MemoryWorkflowIdentityPortV1,
    ) -> None:
        self._ports = ports
        self._identity = identity

    def install(self, app: FastAPI) -> None:
        @app.get("/runs/{run_id}/memory", response_class=HTMLResponse)
        def memory_page(request: Request, run_id: str) -> HTMLResponse:
            """One escaped Run memory page (GREEN-2)."""
            return _render_memory_page(
                app, request, run_id, self._ports.list(run_id), error_message=None
            )

        @app.post("/runs/{run_id}/memory")
        async def memory_create(request: Request, run_id: str) -> Any:
            """Adapt one closed create form to the typed port (GREEN-1).

            Unknown and override fields (including any client-selected
            workspace identity) reject with the stable FORM_INVALID
            payload before command construction, so the create port call
            count stays at zero; a rejected/failed mutation re-renders
            the real memory state with the bounded error.
            """
            form_raw = _form_to_dict(await request.form())
            try:
                form = CreateMemoryFormV1.model_validate(form_raw)
            except ValidationError:
                return _form_invalid("记忆表单包含未声明或非法的字段。")
            command = CreateMemoryForRunV1(
                run_id=run_id,
                kind="PROJECT_CONVENTION",
                summary=form.summary,
                source_reference=form.source_reference,
                creator="USER",
                entry_id=self._identity.new_entry_id(),
                event_id=self._identity.new_event_id(),
                decided_at=self._identity.now(),
            )
            result = self._ports.create(command)
            if result.kind in ("CREATED", "REPLAY"):
                return RedirectResponse(f"/runs/{run_id}/memory", status_code=303)
            return _render_memory_page(
                app,
                request,
                run_id,
                self._ports.list(run_id),
                error_message=result.message,
            )

        @app.post("/runs/{run_id}/memory/confirm")
        async def memory_confirm(request: Request, run_id: str) -> Any:
            """Confirm exactly one targeted project convention (GREEN-1)."""
            form_raw = _form_to_dict(await request.form())
            try:
                form = ConfirmMemoryFormV1.model_validate(form_raw)
            except ValidationError:
                return _form_invalid("确认表单包含未声明或非法的字段。")
            command = ConfirmMemoryForRunV1(
                run_id=run_id,
                entry_id=form.entry_id,
                creator="USER",
                event_id=self._identity.new_event_id(),
                decided_at=self._identity.now(),
            )
            result = self._ports.confirm(command)
            if result.kind in ("CONFIRMED", "REPLAY"):
                return RedirectResponse(f"/runs/{run_id}/memory", status_code=303)
            return _render_memory_page(
                app,
                request,
                run_id,
                self._ports.list(run_id),
                error_message=result.message,
            )

        @app.post("/runs/{run_id}/memory/clear")
        async def memory_clear(request: Request, run_id: str) -> Any:
            """Clear the targeted Run-visible entries (GREEN-1)."""
            form_raw = _form_to_dict(await request.form())
            if "entry_ids" in form_raw and not isinstance(form_raw["entry_ids"], list):
                form_raw["entry_ids"] = [form_raw["entry_ids"]]
            try:
                form = ClearMemoryFormV1.model_validate(form_raw)
            except ValidationError:
                return _form_invalid("清除表单包含未声明或非法的字段。")
            command = ClearMemoryForRunV1(
                run_id=run_id,
                target_entry_ids=tuple(form.entry_ids),
                creator="USER",
                event_id=self._identity.new_event_id(),
                decided_at=self._identity.now(),
            )
            result = self._ports.clear(command)
            if result.kind in ("CLEARED", "REPLAY"):
                return RedirectResponse(f"/runs/{run_id}/memory", status_code=303)
            return _render_memory_page(
                app,
                request,
                run_id,
                self._ports.list(run_id),
                error_message=result.message,
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


def _render_memory_page(
    app: FastAPI,
    request: Request,
    run_id: str,
    entries: tuple[MemoryEntryV1, ...],
    *,
    error_message: str | None,
) -> HTMLResponse:
    """One escaped Run memory page (GREEN-2).

    The page renders creator/source/scope and the create->confirm->clear
    state with scanable hierarchy, explicit labels, keyboard focus, live
    error/status regions, and escaped content; it never renders
    control/policy fields or a workspace selector.
    """
    templates = _templates(app)
    return templates.TemplateResponse(
        request,
        "memory.html",
        {
            "csp_nonce": request.state.csp_nonce,
            "csrf_token": request.state.local_session.csrf_token,
            "run_id": run_id,
            "entries": entries,
            "error_message": error_message,
            "creator_label": creator_label,
            "kind_label": kind_label,
            "source_label": source_label,
        },
    )


def _templates(app: FastAPI) -> Jinja2Templates:
    """The packaged template loader of the composed app."""
    templates = app.state.local_templates
    assert isinstance(templates, Jinja2Templates)
    return templates
