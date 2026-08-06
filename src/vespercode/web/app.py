"""T28.2 legacy steps 28.B/28.C: local WebUI shell and packaged assets.

``create_local_app`` composes the extensible local FastAPI shell from
typed ports and a deterministic typed installer sequence (GREEN-1): the
Task 28.A security boundary runs before every route-domain call, the
escaped templates render distinct text plus accessible-name status
semantics with visible focus, keyboard reachability, live-error hooks,
non-color cues, sufficient contrast, and reduced-motion-safe behavior
(GREEN-2), and ``load_packaged_web_asset``/``install_packaged_web_assets``
serve the pinned packaged ``htmx.min.js`` from the sole local static
path with no network or CDN fallback (28.C GREEN-1/GREEN-2).  The shell
owns composition, templates, and status semantics only — static asset
bytes, package-resource lookup, CLI parsing, server launch, and domain
workflow rules remain out of scope (GREEN-4/Boundary).
"""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import secrets
from pathlib import Path
from typing import Annotated, Any, Final, Literal, Protocol, TypeAlias

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup
from pydantic import BaseModel, ConfigDict, Strict, StrictStr

from src.vespercode.audit.projection import RunVisibilityV1, StateLabelV1
from src.vespercode.credentials.port import CredentialStatusV1
from src.vespercode.web.security import (
    LocalRequestErrorCodeV1,
    LocalSessionManager,
    LocalWebSecurityConfigV1,
    is_loopback_host,
    local_request_rejection_payload,
    local_request_status,
    local_response_security_headers,
    verify_local_request,
)

RunVisibilitySequenceV1: TypeAlias = tuple[RunVisibilityV1, ...]
"""The immutable ordered sequence of one shell's recent-run visibilities."""

LocalRouteInstallerSequenceV1: TypeAlias = tuple["LocalRouteInstallerV1", ...]
"""The immutable ordered tuple of typed route installers of one shell."""

STATUS_TEXT_V1: Final[dict[StateLabelV1, str]] = {
    "CREATED": "已创建",
    "PREFLIGHT": "预检中",
    "BASELINE": "基线中",
    "AGENT_LOOP": "运行中",
    "FORMAL_VALIDATION": "正式验证中",
    "PERSISTENCE": "持久化中",
    "WAITING_USER": "等待用户决定",
    "RECOVERY_REQUIRED": "恢复阻塞",
    "SUCCEEDED": "成功",
    "STOPPED": "已停止",
}
"""One distinct user-facing text per closed state label (SPEC §4.9: the
labels use different, unambiguous tags; §5.3: users must be able to
distinguish preparing, preflight, running, waiting, recovery-blocked,
succeeded, and stopped)."""

_TEMPLATES_DIRECTORY: Final[str] = str(Path(__file__).resolve().parent / "templates")
"""The packaged template directory of the local shell."""


class LocalShellPortsV1(Protocol):
    """The typed shell ports behind one local WebUI (SPEC §4.9 pages).

    The shell receives these ports explicitly — there is no service
    locator or hidden workflow lookup (GREEN-1/Boundary).
    """

    def list_recent_runs(self) -> RunVisibilitySequenceV1:
        """Return the recent run visibilities in display order."""
        ...

    def credential_status(self) -> CredentialStatusV1:
        """Return the non-revealing credential status (SPEC §4.8)."""
        ...


class LocalRouteInstallerV1(Protocol):
    """One typed route installer of the local shell.

    Installers are applied in the exact order of the immutable installer
    tuple; the shell never looks routes up anywhere else (GREEN-1).
    """

    def install(self, app: FastAPI) -> None:
        """Install the installer's routes onto the composed app."""
        ...


class PackagedWebAssetV1(BaseModel):
    """One immutable packaged web asset (28.C interface).

    The asset carries its declared identity (version, SHA-256, byte
    length) and the exact immutable bytes loaded through package
    resources; it is served from the sole local static path and never
    from a CDN or runtime download (28.C GREEN-1).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    name: Literal["htmx.min.js"]
    version: Literal["2.0.4"]
    sha256: StrictStr
    byte_length: Annotated[int, Strict()]
    content_type: Literal["application/javascript"]
    content: bytes


class PackagedWebAssetErrorV1(RuntimeError):
    """One closed packaged-asset failure (missing, drifted, or unknown)."""


_PACKAGED_HTMX_SHA256_V1: Final[str] = (
    "e209dda5c8235479f3166defc7750e1dbcd5a5c1808b7792fc2e6733768fb447"
)
"""The declared SHA-256 identity of the pinned packaged htmx.min.js."""

_PACKAGED_HTMX_BYTE_LENGTH_V1: Final[int] = 50917
"""The declared byte length of the pinned packaged htmx.min.js."""


def load_packaged_web_asset(
    name: Literal["htmx.min.js"],
) -> PackagedWebAssetV1:
    """Load the pinned packaged asset through immutable package resources.

    Only the pinned ``htmx.min.js`` can be loaded; the bytes come from
    the package resource itself (never a CDN, never a runtime download),
    and the loader verifies the declared SHA-256 identity and byte
    length at every load, failing closed on any drift (28.C GREEN-1).
    """
    if name != "htmx.min.js":
        raise PackagedWebAssetErrorV1("unknown packaged web asset")
    resource = importlib.resources.files("src.vespercode.web").joinpath(
        "static", "htmx.min.js"
    )
    if not resource.is_file():
        raise PackagedWebAssetErrorV1("packaged asset file is missing")
    content = resource.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if digest != _PACKAGED_HTMX_SHA256_V1:
        raise PackagedWebAssetErrorV1("packaged asset identity mismatch")
    if len(content) != _PACKAGED_HTMX_BYTE_LENGTH_V1:
        raise PackagedWebAssetErrorV1("packaged asset length mismatch")
    return PackagedWebAssetV1(
        name=name,
        version="2.0.4",
        sha256=digest,
        byte_length=len(content),
        content_type="application/javascript",
        content=content,
    )


def install_packaged_web_assets(app: FastAPI) -> None:
    """Serve the pinned packaged asset from the sole local static path.

    Registers exactly the one local ``/static/htmx.min.js`` route that
    serves the identity-verified packaged bytes — there is no CDN, no
    runtime download, and no other static path (28.C GREEN-1/GREEN-4).
    """
    app.state.local_packaged_assets = True

    @app.get("/static/htmx.min.js")
    def packaged_htmx() -> Response:
        """One identity-verified local asset response."""
        asset = load_packaged_web_asset("htmx.min.js")
        return Response(content=asset.content, media_type=asset.content_type)


_BADGE_TEMPLATE_ENV = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIRECTORY), autoescape=True
)
"""The dedicated badge environment: autoescape is always on, so the
status badge can never render untrusted text as executable markup."""


def render_status_badge(visibility: RunVisibilityV1) -> Markup:
    """One escaped semantic status badge (28.B interface).

    The badge renders the exact unambiguous state label as text with its
    distinct user-facing text and an accessible name (``aria-label``
    with the 状态： prefix), plus a non-color cue element — status is
    never conveyed by color alone (SPEC §4.9/§5.3).
    """
    state_label = visibility.state_label
    template = _BADGE_TEMPLATE_ENV.get_template("components/status_badge.html")
    return Markup(
        template.render(
            visibility=visibility,
            status_text=STATUS_TEXT_V1[state_label],
        )
    )


def create_local_app(
    shell_ports: LocalShellPortsV1,
    security: LocalWebSecurityConfigV1,
    route_installers: LocalRouteInstallerSequenceV1,
) -> FastAPI:
    """Compose the extensible local FastAPI shell (28.B GREEN-1).

    The shell receives its typed ports and the immutable installer
    sequence explicitly — no service locator, no hidden workflow lookup.
    The Task 28.A security boundary (Host, bounded session, Origin, CSRF,
    exact CSP and response security headers) runs before every
    route-domain call; the home route renders the escaped templates with
    the status badges, credential status, keyboard focus, live-error
    hooks, non-color cues, contrast, and reduced-motion safety.
    """
    manager = LocalSessionManager(security)
    templates = Jinja2Templates(directory=_TEMPLATES_DIRECTORY)
    app = FastAPI(
        title="VesperCode 本地 WebUI",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.local_shell_ports = shell_ports
    app.state.local_security_config = security
    app.state.local_session_manager = manager
    app.state.local_route_installers = route_installers
    app.state.local_templates = templates

    @app.middleware("http")
    async def _local_security_middleware(request: Request, call_next: Any) -> Any:
        assert isinstance(
            request, Request
        )  # the runtime contract is a starlette Request
        csp_nonce = secrets.token_urlsafe(24)
        request.state.csp_nonce = csp_nonce
        if not is_loopback_host(request.headers.get("host", "")):
            return _rejection_response("HOST_REJECTED")
        if request.url.path.startswith("/static/"):
            response = await call_next(request)
            _attach_headers(response, None)
            return response
        cookie_value = request.cookies.get(security.session_cookie_name)
        if cookie_value is None:
            if request.method in ("GET", "HEAD") and request.url.path == "/":
                # Bootstrap one bounded local session on the first home
                # visit and set its cookie on the response.
                bootstrap_session = manager.create()
                request.state.local_session = bootstrap_session
                response = await call_next(request)
                response.set_cookie(
                    security.session_cookie_name,
                    bootstrap_session.session_id,
                    httponly=True,
                    samesite="strict",
                    max_age=manager.session_ttl_seconds,
                    path="/",
                )
                _attach_headers(response, csp_nonce)
                return response
            return _rejection_response("SESSION_MISSING")
        session = manager.get(cookie_value)
        if session is None:
            return _rejection_response("SESSION_INVALID")
        if not manager.is_active(session):
            return _rejection_response("SESSION_EXPIRED")
        authorization = verify_local_request(request, session)
        if not authorization.authorized:
            assert authorization.error_code is not None
            return _rejection_response(authorization.error_code)
        request.state.local_session = session
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        _attach_headers(response, csp_nonce if "text/html" in content_type else None)
        return response

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        """One escaped home page over the typed shell ports.

        The page renders the recent-run visibilities with the semantic
        status badges and the non-revealing credential status; every
        value flows through the autoescaping templates, and the per-
        request CSP nonce authorizes the hook script.
        """
        recent_runs = shell_ports.list_recent_runs()
        credential_status = shell_ports.credential_status()
        return templates.TemplateResponse(
            request,
            "home.html",
            {
                "recent_runs": recent_runs,
                "credential_status": credential_status,
                "csp_nonce": request.state.csp_nonce,
                "render_status_badge": render_status_badge,
            },
        )

    for installer in route_installers:
        installer.install(app)

    return app


def _attach_headers(response: Response, csp_nonce: str | None) -> None:
    """Attach the exact CSP and response security headers to one
    response without touching its status or body (GREEN-2)."""
    for name, value in local_response_security_headers(csp_nonce).items():
        response.headers[name] = value


def _rejection_response(error_code: LocalRequestErrorCodeV1) -> Response:
    """One closed rejection response carrying the exact security headers."""
    payload = local_request_rejection_payload(error_code)
    response = Response(
        status_code=local_request_status(error_code),
        content=json.dumps(payload),
        media_type="application/json",
    )
    for name, value in local_response_security_headers().items():
        response.headers[name] = value
    return response
