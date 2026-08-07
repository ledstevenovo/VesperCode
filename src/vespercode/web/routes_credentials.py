"""T38.1 legacy step 38.A: credential lifecycle WebUI routes.

``CredentialWorkflowPortsV1`` is the closed typed seam exposing exactly
``set``/``status``/``update``/``clear`` over the literal ``OPENAI``
provider, and ``CredentialRouteInstallerV1`` installs the status page and
the single closed mutation route: the provider lives only in the URL
path, the form accepts only the declared ``action``/``secret`` fields
(any unknown or override field rejects with the stable FORM_INVALID
payload before any domain call), and every mutation event is
server-controlled through the injected identity seam (SPEC §5.4) so the
route can never construct, widen, or echo a secret (GREEN-1).  The
status/form page renders the password field for its form lifetime only,
with explicit labels, keyboard focus, live error/status regions,
contextual recovery guidance, and escaped service-projected text
(GREEN-2).  The response contract of SPEC §4.8/§8.1/AC-08 is enforced by
construction: the submitted secret, its length, its digest, and every
derivative are never rendered, echoed, or logged by any success or
failure branch (GREEN-3).  Credential persistence, domain-rule
duplication, secret logging/redisplay, request-security bypass,
alternate provider, and false-success synthesis remain out of scope
(GREEN-4/Boundary): a failed clear/update renders the service's real
state and never claims false success.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Protocol

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError
from starlette.datastructures import FormData

from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.credentials.port import (
    CredentialMutationResultV1,
    CredentialSecretInvalidError,
    CredentialStatusV1,
    SecretCredentialV1,
)

_SECRET_FORM_MAX_CHARS = 4096
"""The closed upper bound of one password-form secret submission."""


class CredentialWorkflowIdentityPortV1(Protocol):
    """The injected control-plane identity seam of one mutation (SPEC §5.4).

    Mutation events are created server-side through this seam — the form
    can never supply an event id or a time, so replay identity and
    ordering stay under the composition's control (GREEN-1).
    """

    def new_event_id(self) -> str:
        """One harness-generated mutation event identity."""
        ...

    def now(self) -> CanonicalTimestampV1:
        """The sole current-time source of one mutation."""
        ...


class CredentialWorkflowPortsV1(Protocol):
    """The closed typed credential workflow seam (injection point).

    The routes adapt the form only through these exact methods over the
    literal ``OPENAI`` provider; persistence, backend probing, and
    domain rules live behind the port (Task 27), never in the WebUI
    (GREEN-4).
    """

    def set(
        self,
        provider: Literal["OPENAI"],
        secret: SecretCredentialV1,
        event_id: str,
    ) -> CredentialMutationResultV1: ...

    def status(self, provider: Literal["OPENAI"]) -> CredentialStatusV1: ...

    def update(
        self,
        provider: Literal["OPENAI"],
        secret: SecretCredentialV1,
        event_id: str,
    ) -> CredentialMutationResultV1: ...

    def clear(
        self, provider: Literal["OPENAI"], event_id: str
    ) -> CredentialMutationResultV1: ...


class CredentialFormV1(BaseModel):
    """One closed credential mutation form adaptation (GREEN-1).

    Only the declared ``action`` and ``secret`` fields are accepted; the
    default action is the first-time entry ``set`` (SPEC §8.1), the
    action is closed to the three declared mutations, and any unknown or
    override field (provider, workspace, credential, length/digest
    reporting, ...) rejects at the closed schema before any domain call.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    action: Literal["set", "update", "clear"] = "set"
    secret: Annotated[StrictStr, Field(max_length=_SECRET_FORM_MAX_CHARS)] = ""


class CredentialRouteInstallerV1:
    """Install the closed credential routes over the typed port.

    The installer receives the port and the identity seam explicitly; the
    routes close over exactly the injected objects and never look ports
    up anywhere else (GREEN-1/Boundary).
    """

    def __init__(
        self,
        ports: CredentialWorkflowPortsV1,
        identity: CredentialWorkflowIdentityPortV1,
    ) -> None:
        self._ports = ports
        self._identity = identity

    def install(self, app: FastAPI) -> None:
        @app.get("/credentials/openai", response_class=HTMLResponse)
        def credential_status_page(request: Request) -> HTMLResponse:
            """One escaped credential status/form page (GREEN-2).

            The page renders the non-revealing status fields (provider,
            configured flag, update time — never the secret or any
            derivative) and the closed mutation form; every value flows
            through the autoescaping template, so service-projected text
            can never execute as markup.
            """
            return _render_status_page(
                app, request, self._ports.status("OPENAI"), error_message=None
            )

        @app.post("/credentials/openai")
        async def credential_mutate(request: Request) -> Any:
            """Adapt one closed mutation form to the typed port (GREEN-1).

            Unknown and override fields reject at the closed schema with
            the stable FORM_INVALID payload before any domain call; the
            secret exists only inside the password-form service-call
            lifetime (wrapped through the non-serializable hidden-input
            contract, never echoed or stored by the route); every
            mutation event is server-controlled.  A successful mutation
            redirects to the status page (PRG); a failed clear/update
            re-renders the service's real state with the bounded error —
            never a false success (Boundary).
            """
            form_raw = _form_to_dict(await request.form())
            try:
                form = CredentialFormV1.model_validate(form_raw)
            except ValidationError:
                return _form_invalid("凭据表单包含未声明或非法的字段。")
            event_id = self._identity.new_event_id()
            if form.action == "clear":
                result = self._ports.clear("OPENAI", event_id)
            else:
                try:
                    secret = SecretCredentialV1.from_hidden_input(form.secret)
                except CredentialSecretInvalidError:
                    return _form_invalid("凭据值不能为空。")
                if form.action == "update":
                    result = self._ports.update("OPENAI", secret, event_id)
                else:
                    result = self._ports.set("OPENAI", secret, event_id)
            if result.kind in ("STORED", "CLEARED"):
                return RedirectResponse("/credentials/openai", status_code=303)
            return _render_status_page(
                app,
                request,
                self._ports.status("OPENAI"),
                error_message=_mutation_failure_text(result),
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
    """One stable closed-form rejection (SPEC §5.3 style).

    The payload is a bounded static text pair; it carries no submitted
    value, no secret, and no derivative, so the sentinel/``length``/
    ``digest`` absence contract holds on the failure branch too
    (GREEN-3).
    """
    return JSONResponse(
        status_code=422,
        content={
            "error_code": "FORM_INVALID",
            "message": message,
            "next_step": "请仅提交声明字段。",
        },
    )


def _mutation_failure_text(result: CredentialMutationResultV1) -> str:
    """One bounded service-projected failure text (never a false success).

    The text is the closed typed error's bounded static message; the
    route never synthesizes a success or echoes the submitted secret
    (Boundary).
    """
    if result.kind == "FAILED" and result.error.kind == "PRESENT":
        return result.error.value.message
    return "凭据操作失败，状态未变化。"


def _render_status_page(
    app: FastAPI,
    request: Request,
    status: CredentialStatusV1,
    *,
    error_message: str | None,
) -> HTMLResponse:
    """One escaped credential status/form page (GREEN-2).

    The password field renders with a closed lifetime (never a persisted
    value attribute), explicit labels, keyboard focus, live error/status
    regions, and contextual recovery guidance; the status facts are the
    non-revealing closed fields only.
    """
    templates = _templates(app)
    return templates.TemplateResponse(
        request,
        "credential_status.html",
        {
            "csp_nonce": request.state.csp_nonce,
            "csrf_token": request.state.local_session.csrf_token,
            "status": status,
            "updated_at_text": _updated_at_text(status),
            "error_message": error_message,
        },
    )


def _updated_at_text(status: CredentialStatusV1) -> str:
    """One closed user-facing update-time text (never a secret value)."""
    if status.updated_at.kind == "PRESENT":
        return status.updated_at.value.value
    return "从未更新"


def _templates(app: FastAPI) -> Jinja2Templates:
    """The packaged template loader of the composed app."""
    templates = app.state.local_templates
    assert isinstance(templates, Jinja2Templates)
    return templates
