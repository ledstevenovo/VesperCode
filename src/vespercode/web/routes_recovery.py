"""T38.2 legacy step 38.D: read-only-first recovery WebUI routes.

``RecoveryWorkflowPortsV1`` is the closed typed seam exposing exactly
``preview`` (the read-only Task 26.B preview of the Run's non-terminal
transaction) and ``apply`` (the separately confirmed, currently bound
Task 26.C apply command), and ``RecoveryRouteInstallerV1`` installs the
preview page and the apply route: the preview path renders full
path/status/consequence evidence with the literal zero-write proof and
never calls apply or writes (GREEN-1/GREEN-3), the apply accepts only
the frozen binding fields (run id, transaction id, preview digest,
literal confirmation, and the server-controlled event id) with a stale
pre-check before any domain call (GREEN-1), and the page renders a
distinct explicit confirmation step with scanable risk hierarchy,
keyboard focus, labels, live errors/status, escaping, and no
force/ignore/skip/edit/abandon control (GREEN-2).  Preview mutation,
stale-digest apply, partial/exception success, domain predicate
duplication, and any bypass control remain out of scope (GREEN-4):
only service-proven terminal results unblock, and stale
preview/exception/partial results never render success (Boundary).

Recorded interface interpretations (reviewer-flagged, T29.3 precedent
class): ``render_recovery_preview`` renders the packaged template
through a dedicated autoescaping environment and receives the CSRF
token and CSP nonce as keyword arguments (the apply form must carry the
Task 28.A token; the same keyword-argument extension the Task 29.3
writeback renderer uses); the apply form posts to the page's own URL
(GET preview / POST apply on ``/runs/{run_id}/recovery``), so the pure
preview renderer needs no Run id; and the workflow port's ``preview``
raises the closed Task 26.B ``RecoveryPreviewErrorV1``, which the route
projects as stable blocked pages (never a success).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Protocol

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, ConfigDict, StrictStr, ValidationError
from starlette.datastructures import FormData

from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.persistence.recovery_apply import RecoveryResultV1
from src.vespercode.persistence.recovery_preview import (
    RecoveryPathClassificationEntryV1,
    RecoveryPreviewErrorV1,
    RecoveryPreviewV1,
)

_TEMPLATES_DIRECTORY: str = str(Path(__file__).resolve().parent / "templates")
"""The packaged template directory of the local shell."""

_TEMPLATE_ENV = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIRECTORY), autoescape=True
)
"""The dedicated recovery template environment: autoescape is always on,
so service-projected and workspace text can never render as executable
markup."""

DISPOSITION_LABELS_V1: dict[str, str] = {
    "COMMITTED": "已提交",
    "ROLLED_BACK": "已回滚",
    "UNRESOLVED": "未解决",
}
"""One distinct user-facing text per closed recovery disposition."""

CLASSIFICATION_LABELS_V1: dict[str, str] = {
    "PREIMAGE": "前映像",
    "POSTIMAGE": "后映像",
    "ABSENT": "缺失",
    "EXTERNAL_CHANGE": "外部变化",
    "UNPROVABLE": "无法证明",
}
"""One distinct user-facing text per closed path classification."""

CONSEQUENCE_TEXT_V1: dict[str, str] = {
    "PREIMAGE": "拟恢复前映像",
    "POSTIMAGE": "拟保持后映像并重做写后核对",
    "ABSENT": "拟删除本事务新建文件（仅当文件仍精确匹配后映像）",
    "EXTERNAL_CHANGE": "外部变化，无法安全处置（保持未解决）",
    "UNPROVABLE": "证据不足，无法安全处置（保持未解决）",
}
"""One bounded user-facing consequence per closed classification."""

APPLY_BUTTON_TEXT_V1: dict[str, str] = {
    "COMMITTED": "确认按已提交状态恢复",
    "ROLLED_BACK": "确认回滚到前映像",
}
"""The distinct explicit confirmation button text per terminal disposition."""

_PREVIEW_ERROR_TEXT_V1: dict[str, str] = {
    "TRANSACTION_NOT_FOUND": "该运行没有非终态恢复事务。",
    "WORKSPACE_MISMATCH": "恢复事务与运行工作区不匹配。",
    "NO_PATH_RECORDS": "恢复事务没有路径记录。",
}
"""One bounded user-facing text per closed preview rejection."""


def classification_label(classification: str) -> str:
    """One exact user-facing classification label."""
    return CLASSIFICATION_LABELS_V1[classification]


def consequence_text(classification: str) -> str:
    """One bounded user-facing consequence of a path classification."""
    return CONSEQUENCE_TEXT_V1[classification]


def disposition_label(disposition: str) -> str:
    """One exact user-facing disposition label."""
    return DISPOSITION_LABELS_V1[disposition]


class RecoveryWorkflowIdentityPortV1(Protocol):
    """The injected control-plane identity seam of one apply operation.

    The apply event id and time are created server-side through this
    seam — the form can never supply them (SPEC §5.4).
    """

    def new_event_id(self) -> str:
        """One harness-generated apply event identity."""
        ...

    def now(self) -> CanonicalTimestampV1:
        """The sole current-time source of one apply."""
        ...


class ApplyRecoveryForRunV1(BaseModel):
    """One closed apply command bound to a current preview (GREEN-1).

    The command carries only the frozen binding fields: the Run id, the
    rendered transaction id, the rendered preview digest, the literal
    confirmation, and the server-controlled event id and time.  There is
    no force/ignore/skip/edit/abandon field and no disposition override.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: StrictStr
    transaction_id: StrictStr
    preview_digest: StrictStr
    confirmation: Literal["yes"]
    event_id: StrictStr
    decided_at: CanonicalTimestampV1


class RecoveryWorkflowPortsV1(Protocol):
    """The closed typed recovery workflow seam (injection point).

    The routes delegate preview and apply only through these methods;
    transaction selection, workspace resolution, digest recomputation,
    lease handling, and the recovery predicates live behind the port
    (Task 26), never in the WebUI (GREEN-4).
    """

    def preview(self, run_id: str) -> RecoveryPreviewV1:
        """The read-only preview of the Run's non-terminal transaction.

        Raises the closed ``RecoveryPreviewErrorV1`` when no preview can
        be produced; nothing is ever written.
        """
        ...

    def apply(self, command: ApplyRecoveryForRunV1) -> RecoveryResultV1:
        """Apply the currently bound recovery command."""
        ...


class ApplyRecoveryFormV1(BaseModel):
    """One closed apply form adaptation (GREEN-1).

    Only the frozen binding fields the page rendered are accepted; any
    unknown or override field (workspace, disposition, force, ignore,
    skip, edit, abandon, event ids, times) rejects at the closed schema
    before any domain call.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    transaction_id: StrictStr
    preview_digest: StrictStr
    confirmation: Literal["yes"]


class RecoveryRouteInstallerV1:
    """Install the closed recovery routes over the typed port.

    The installer receives the port and the identity seam explicitly; the
    routes close over exactly the injected objects and never look ports
    up anywhere else (GREEN-1/Boundary).
    """

    def __init__(
        self,
        ports: RecoveryWorkflowPortsV1,
        identity: RecoveryWorkflowIdentityPortV1,
    ) -> None:
        self._ports = ports
        self._identity = identity

    def install(self, app: FastAPI) -> None:
        @app.get("/runs/{run_id}/recovery", response_class=HTMLResponse)
        def recovery_preview(request: Request, run_id: str) -> HTMLResponse:
            """One escaped read-only recovery preview page (GREEN-1).

            The preview path only reads the typed preview and renders the
            full path/status/consequence evidence; it never calls apply
            and never writes.  A closed preview rejection renders a
            stable blocked page — never a success.
            """
            try:
                preview = self._ports.preview(run_id)
            except RecoveryPreviewErrorV1 as exc:
                return _render_blocked_page(
                    request, error_message=_preview_error_text(exc.error_code)
                )
            return render_recovery_preview(
                preview,
                csrf_token=request.state.local_session.csrf_token,
                csp_nonce=request.state.csp_nonce,
            )

        @app.post("/runs/{run_id}/recovery")
        async def recovery_apply(request: Request, run_id: str) -> Any:
            """Apply the separately confirmed, currently bound command.

            The form accepts only the frozen binding fields; the current
            preview is re-read and the form's transaction/digest binding
            is re-verified before any domain call (a stale preview
            rejects with zero apply calls), and only a service-proven
            terminal result renders success — partial, exception, and
            unresolved results re-render the blocked state (Boundary).
            """
            form_raw = _form_to_dict(await request.form())
            try:
                form = ApplyRecoveryFormV1.model_validate(form_raw)
            except ValidationError:
                return _form_invalid("恢复表单包含未声明或非法的字段。")
            try:
                current = self._ports.preview(run_id)
            except RecoveryPreviewErrorV1:
                return _form_invalid("该运行没有非终态恢复事务。")
            if (
                current.transaction_id != form.transaction_id
                or current.preview_digest != form.preview_digest
            ):
                return _stale()
            command = ApplyRecoveryForRunV1(
                run_id=run_id,
                transaction_id=form.transaction_id,
                preview_digest=form.preview_digest,
                confirmation=form.confirmation,
                event_id=self._identity.new_event_id(),
                decided_at=self._identity.now(),
            )
            result = self._ports.apply(command)
            return _render_result_page(request, result)


def render_recovery_preview(
    preview: RecoveryPreviewV1,
    *,
    csrf_token: str,
    csp_nonce: str,
) -> HTMLResponse:
    """One escaped read-only recovery preview page (GREEN-2).

    The page renders the transaction, the closed disposition, the
    per-path status/consequence rows with scanable risk hierarchy, the
    literal zero-write proof, and — only for a terminal disposition —
    the distinct explicit confirmation form; there is no
    force/ignore/skip/edit/abandon control anywhere.
    """
    return _render_template(
        "recovery_preview.html",
        mode="preview",
        csrf_token=csrf_token,
        csp_nonce=csp_nonce,
        preview=preview,
        result=None,
        error_message=None,
        show_apply_form=preview.disposition in ("COMMITTED", "ROLLED_BACK"),
        apply_button_text=APPLY_BUTTON_TEXT_V1.get(preview.disposition, ""),
        classification_rows=tuple(
            (entry, classification_label(entry.classification))
            for entry in preview.path_classifications
        ),
        disposition_label=disposition_label(preview.disposition),
        consequence_text=consequence_text,
    )


def _render_result_page(request: Request, result: RecoveryResultV1) -> HTMLResponse:
    """One escaped terminal/unresolved recovery result page.

    A service-proven COMMITTED/ROLLED_BACK result renders the terminal
    disposition with the changed paths and evidence digest; an
    UNRESOLVED result renders the bounded message in the blocked state —
    never a success (Boundary).
    """
    return _render_template(
        "recovery_preview.html",
        mode="result",
        csrf_token=request.state.local_session.csrf_token,
        csp_nonce=request.state.csp_nonce,
        preview=None,
        result=result,
        error_message=result.message if result.disposition == "UNRESOLVED" else None,
        show_apply_form=False,
        apply_button_text="",
        classification_rows=(),
        disposition_label=disposition_label(result.disposition),
        consequence_text=consequence_text,
    )


def _render_blocked_page(request: Request, *, error_message: str) -> HTMLResponse:
    """One stable blocked recovery page (never a success)."""
    return _render_template(
        "recovery_preview.html",
        mode="blocked",
        csrf_token=request.state.local_session.csrf_token,
        csp_nonce=request.state.csp_nonce,
        preview=None,
        result=None,
        error_message=error_message,
        show_apply_form=False,
        apply_button_text="",
        classification_rows=(),
        disposition_label="",
        consequence_text=consequence_text,
    )


def _render_template(
    name: str,
    *,
    mode: str,
    csrf_token: str,
    csp_nonce: str,
    preview: RecoveryPreviewV1 | None,
    result: RecoveryResultV1 | None,
    error_message: str | None,
    show_apply_form: bool,
    apply_button_text: str,
    classification_rows: tuple[tuple[RecoveryPathClassificationEntryV1, str], ...],
    disposition_label: str,
    consequence_text: object,
) -> HTMLResponse:
    """One escaped recovery page over the packaged template.

    ``consequence_text`` resolves each closed classification's bounded
    consequence inside the template; every value flows through the
    autoescaping environment.
    """
    template = _TEMPLATE_ENV.get_template(name)
    return HTMLResponse(
        content=template.render(
            csp_nonce=csp_nonce,
            csrf_token=csrf_token,
            mode=mode,
            preview=preview,
            result=result,
            error_message=error_message,
            show_apply_form=show_apply_form,
            apply_button_text=apply_button_text,
            classification_rows=classification_rows,
            consequence_text=consequence_text,
            disposition_label=disposition_label,
        )
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


def _stale() -> JSONResponse:
    """One stable stale-binding rejection (zero apply calls)."""
    return JSONResponse(
        status_code=409,
        content={
            "error_code": "RECOVERY_PREVIEW_STALE",
            "message": "恢复预览已过期，请刷新页面后重新确认。",
            "next_step": "请刷新页面后重新确认。",
        },
    )


def _preview_error_text(error_code: str) -> str:
    """One bounded user-facing preview rejection text."""
    return _PREVIEW_ERROR_TEXT_V1.get(error_code, "恢复预览不可用。")
