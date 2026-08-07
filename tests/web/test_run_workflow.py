"""T29.1 legacy step 29.A: run lifecycle WebUI tests.

The exact RED pins the smallest closed-form rejection (an override field
on the run-creation form rejects with 422 before any workflow-port call);
the matrix pins the Expected (29.A) line — create/status/cancel states
render safely, idempotently, and without exposing forbidden override
fields — behind the exact Task 28.A security order and with the exact
status/reason/next-action text, escaped untrusted text, accessible
labels, focus, and non-color cues.  Per the SPEC_PROCESS section-49
precedent the card's "exact section 5.1 matrix" reference is
non-operative; the Expected (29.A) line is the matrix authority.

Fixture interpretation (T28.1 M3-precedent class): the ``local_web_client``
fixture is a test-local composition mirror whose middleware logic mirrors
the Task 28.B shell verbatim (fixed HOST -> SESSION -> ORIGIN -> CSRF
order and the exact security headers).  The mirror's session manager uses
a deterministic token generator, and the fixture pre-creates one session
whose cookie the client carries, so the card's RED post (which passes
only ``valid_local_security_headers()``) passes through the exact
security order and reaches the closed-form validation — the substantive
production composition (``create_local_app``) is pinned by the Task 28.2
app-composition tests and by this file's real-composition domain test.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Final, cast

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from vespercode.audit.projection import RunVisibilityV1
from vespercode.contracts.optional import AbsentV1
from vespercode.credentials.port import CredentialStatusV1
from vespercode.web.app import (
    LocalRouteInstallerSequenceV1,
    LocalShellPortsV1,
    RunVisibilitySequenceV1,
    create_local_app,
)
from vespercode.web.routes_runs import RunLifecycleRouteInstallerV1
from vespercode.web.run_lifecycle_workflow import (
    CreateRunFormV1,
    RunCancellationResultV1,
    RunCreationResultV1,
    RunLifecycleWorkflowPortsV1,
)
from vespercode.web.security import (
    LocalRequestErrorCodeV1,
    LocalSessionManager,
    LocalWebSecurityConfigV1,
    is_loopback_host,
    local_request_rejection_payload,
    local_request_status,
    local_response_security_headers,
    verify_local_request,
)

_FIXED_TOKEN: Final[str] = "f" * 64
"""One deterministic 256-bit hex session/CSRF token (closed token form)."""

_MIRROR_NONCE: Final[str] = "test-nonce-1234567890"
"""One deterministic closed CSP nonce form for the test-local mirror."""

_TEMPLATES_DIRECTORY: Final[str] = str(
    Path(__file__).resolve().parents[2] / "src/vespercode/web/templates"
)
"""The packaged template directory (mirror app needs the same loader)."""


def _fixed_token_generator() -> Callable[[], str]:
    """One deterministic session/CSRF token generator (SPEC §5.4)."""

    def generate() -> str:
        return _FIXED_TOKEN

    return generate


def valid_local_security_headers() -> dict[str, str]:
    """One fully valid loopback request-header set (Host + Origin + CSRF).

    The fixture pre-creates one deterministic session and seeds the
    client's cookie jar, so this exact header set passes the fixed
    HOST -> SESSION -> ORIGIN -> CSRF order and reaches the routes.
    """
    return {
        "Host": "127.0.0.1:8765",
        "Origin": "http://127.0.0.1:8765",
        "X-CSRF-Token": _FIXED_TOKEN,
    }


def valid_run_creation_form() -> dict[str, str | list[str]]:
    """One valid closed run-creation form body (all 13 declared fields)."""
    return {
        "workspace_path": "C:/work/demo",
        "target_test_ids": ["tests/a_test.py::test_a"],
        "llm_profile_id": "mock-deterministic-v1",
        "reference_profile_id": "python-src-py312-v1",
        "max_turns": "10",
        "max_llm_calls": "10",
        "max_run_wall_clock_seconds": "600",
        "user_wait_timeout_seconds": "120",
        "tool_timeout_seconds": "30",
        "target_check_timeout_seconds": "60",
        "full_check_timeout_seconds": "120",
        "baseline_timeout_seconds": "300",
        "formal_validation_timeout_seconds": "300",
    }


def created_visibility(run_id: str = "run-1") -> RunVisibilityV1:
    """One created run visibility (cancellable)."""
    return RunVisibilityV1(
        run_id=run_id,
        state_label="CREATED",
        reason_code="RUN_CREATED",
        next_action="START",
        evidence_refs=(),
    )


def running_visibility(run_id: str = "run-1") -> RunVisibilityV1:
    """One running (AGENT_LOOP) run visibility (cancellable)."""
    return RunVisibilityV1(
        run_id=run_id,
        state_label="AGENT_LOOP",
        reason_code="RUNNING_PHASE",
        next_action="CONTINUE",
        evidence_refs=(),
    )


def waiting_visibility(run_id: str = "run-1") -> RunVisibilityV1:
    """One waiting-for-user-decision run visibility (cancellable)."""
    return RunVisibilityV1(
        run_id=run_id,
        state_label="WAITING_USER",
        reason_code="USER_DECISION_PENDING",
        next_action="AWAIT_USER_DECISION",
        evidence_refs=(),
    )


def succeeded_visibility(run_id: str = "run-1") -> RunVisibilityV1:
    """One succeeded run visibility (not cancellable)."""
    return RunVisibilityV1(
        run_id=run_id,
        state_label="SUCCEEDED",
        reason_code="RUN_SUCCEEDED",
        next_action="RETRIEVE_EVIDENCE",
        evidence_refs=(),
    )


def stopped_visibility(run_id: str = "run-1") -> RunVisibilityV1:
    """One stopped run visibility (not cancellable)."""
    return RunVisibilityV1(
        run_id=run_id,
        state_label="STOPPED",
        reason_code="RUN_STOPPED",
        next_action="REVIEW_STOP_REASON",
        evidence_refs=(),
    )


class SpyRunLifecyclePorts:
    """One spy typed run-lifecycle workflow-port implementation."""

    def __init__(self) -> None:
        self.create_call_count = 0
        self.cancel_call_count = 0
        self.created_result = RunCreationResultV1(kind="CREATED", run_id="run-1")
        self.cancel_result = RunCancellationResultV1(
            kind="CANCELLED", message="运行已取消"
        )
        self._visibilities: dict[str, RunVisibilityV1] = {}
        self._create_forms: list[CreateRunFormV1] = []
        self._cancelled: list[str] = []

    def seed_visibility(self, visibility: RunVisibilityV1) -> None:
        """Seed one exact visibility the detail page renders."""
        self._visibilities[visibility.run_id] = visibility

    def create(self, form: CreateRunFormV1) -> RunCreationResultV1:
        self.create_call_count += 1
        self._create_forms.append(form)
        return self.created_result

    def visibility_for(self, run_id: str) -> RunVisibilityV1 | None:
        return self._visibilities.get(run_id)

    def cancel(self, run_id: str) -> RunCancellationResultV1:
        self.cancel_call_count += 1
        self._cancelled.append(run_id)
        return self.cancel_result

    @property
    def last_create_form(self) -> CreateRunFormV1 | None:
        return self._create_forms[-1] if self._create_forms else None

    @property
    def cancelled_runs(self) -> list[str]:
        return self._cancelled


def _rejection_response(error_code: LocalRequestErrorCodeV1) -> JSONResponse:
    """One closed rejection response carrying the exact security headers."""
    payload = local_request_rejection_payload(error_code)
    response = JSONResponse(
        status_code=local_request_status(error_code), content=payload
    )
    for name, value in local_response_security_headers().items():
        response.headers[name] = value
    return response


def _build_local_app(
    security_config: LocalWebSecurityConfigV1,
    installers: LocalRouteInstallerSequenceV1,
) -> tuple[FastAPI, LocalSessionManager]:
    """One test-local shell mirroring the Task 28.B composition.

    The middleware mirrors the Task 28.A fixed order verbatim (HOST ->
    SESSION -> ORIGIN -> CSRF for state changes, the exact security
    headers) and the manager uses the deterministic token generator, so
    the fixture can pre-create one session whose cookie the client
    carries (T28.1 M3-precedent class: the production composition is
    pinned by the Task 28.2 app-composition tests and the real-
    composition domain test below).
    """
    manager = LocalSessionManager(
        security_config, token_generator=_fixed_token_generator()
    )
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.local_security_config = security_config
    app.state.local_session_manager = manager
    app.state.local_templates = Jinja2Templates(directory=_TEMPLATES_DIRECTORY)

    @app.middleware("http")
    async def _local_security_middleware(request: Request, call_next: Any) -> Any:
        assert isinstance(
            request, Request
        )  # the runtime contract is a starlette Request
        request.state.csp_nonce = _MIRROR_NONCE
        if not is_loopback_host(request.headers.get("host", "")):
            return _rejection_response("HOST_REJECTED")
        if request.url.path.startswith("/static/"):
            response = await call_next(request)
            _attach_headers(response, None)
            return response
        cookie_value = request.cookies.get(security_config.session_cookie_name)
        if cookie_value is None:
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
        _attach_headers(
            response, _MIRROR_NONCE if "text/html" in content_type else None
        )
        return response

    for installer in installers:
        installer.install(app)
    return app, manager


def _attach_headers(response: Any, csp_nonce: str | None) -> None:
    """Attach the exact CSP and response security headers to one response."""
    for name, value in local_response_security_headers(csp_nonce).items():
        response.headers[name] = value


class FakeShellPortsV1:
    """One fake typed shell port implementation (test-owned)."""

    def __init__(self, runs: RunVisibilitySequenceV1) -> None:
        self._runs = runs

    def list_recent_runs(self) -> RunVisibilitySequenceV1:
        return self._runs

    def credential_status(self) -> CredentialStatusV1:
        return CredentialStatusV1(
            schema_version=1,
            provider="OPENAI",
            configured=False,
            updated_at=AbsentV1(kind="ABSENT"),
        )


@pytest.fixture
def workflow_ports() -> SpyRunLifecyclePorts:
    return SpyRunLifecyclePorts()


@pytest.fixture
def security_config() -> LocalWebSecurityConfigV1:
    return LocalWebSecurityConfigV1(
        host="127.0.0.1",
        port=8765,
        session_cookie_name="vespercode_session",
        csrf_header_name="X-CSRF-Token",
    )


@pytest.fixture
def local_web_client(
    security_config: LocalWebSecurityConfigV1,
    workflow_ports: SpyRunLifecyclePorts,
) -> TestClient:
    installers: LocalRouteInstallerSequenceV1 = (
        RunLifecycleRouteInstallerV1(
            RunLifecycleWorkflowPortsV1(
                creation=workflow_ports,
                visibility=workflow_ports,
                cancellation=workflow_ports,
            )
        ),
    )
    app, manager = _build_local_app(security_config, installers)
    client = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")
    session = manager.create()
    client.cookies.set(security_config.session_cookie_name, session.session_id)
    return client


def test_invalid_run_form_creates_no_run(
    local_web_client: TestClient,
    workflow_ports: SpyRunLifecyclePorts,
) -> None:
    response = local_web_client.post(
        "/runs",
        headers=valid_local_security_headers(),
        data={"base_url": "https://bad.example"},
    )
    assert response.status_code == 422
    assert workflow_ports.create_call_count == 0


def test_run_web_workflow_matrix(
    local_web_client: TestClient,
    security_config: LocalWebSecurityConfigV1,
    workflow_ports: SpyRunLifecyclePorts,
) -> None:
    """The exact run-lifecycle WebUI matrix (Expected 29.A authority).

    Create/status/cancel states render safely, idempotently, and without
    exposing forbidden override fields; the Task 28.A boundary rejects
    before every workflow-port call; and the pages carry the exact
    status/reason/next-action text, escaped untrusted text, accessible
    labels, visible focus, keyboard operation, live-error hooks, and
    non-color status cues.
    """
    client = local_web_client
    headers = valid_local_security_headers()
    app = cast(FastAPI, client.app)
    spy = workflow_ports

    # --- the create page renders the closed form only ---
    create_page = client.get("/runs/new", headers=headers)
    assert create_page.status_code == 200
    text = create_page.text
    for field in (
        "workspace_path",
        "target_test_ids",
        "llm_profile_id",
        "reference_profile_id",
        "max_turns",
        "max_llm_calls",
        "max_run_wall_clock_seconds",
        "user_wait_timeout_seconds",
        "tool_timeout_seconds",
        "target_check_timeout_seconds",
        "full_check_timeout_seconds",
        "baseline_timeout_seconds",
        "formal_validation_timeout_seconds",
    ):
        assert f'name="{field}"' in text
    # the create page exposes no override/secret fields
    for forbidden in (
        "base_url",
        "endpoint",
        "secret",
        "credential",
        "api_key",
    ):
        assert forbidden not in text
    assert 'method="post"' in text
    assert 'action="/runs"' in text
    assert ":focus-visible" in text
    assert 'id="live-error"' in text
    assert "aria-live" in text
    # the page delivers the session CSRF token and the htmx wiring that
    # attaches it as the Task 28.A header on every POST (SPEC §5.5; the
    # HttpOnly cookie is never script-readable)
    assert 'name="csrf-token"' in text
    assert f'content="{_FIXED_TOKEN}"' in text
    assert 'hx-post="/runs"' in text
    assert 'hx-target="#content"' in text
    assert 'hx-select="#content"' in text
    assert 'hx-swap="outerHTML"' in text
    assert "htmx:configRequest" in text
    assert "X-CSRF-Token" in text
    assert f'nonce="{_MIRROR_NONCE}"' in text

    # --- a valid closed create form adapts to the typed port exactly once ---
    created = client.post(
        "/runs",
        headers=headers,
        data=valid_run_creation_form(),
        follow_redirects=False,
    )
    assert created.status_code == 303
    assert created.headers["location"] == "/runs/run-1"
    assert spy.create_call_count == 1
    form = spy.last_create_form
    assert form is not None
    assert form.workspace_path == "C:/work/demo"
    assert form.target_test_ids == ["tests/a_test.py::test_a"]
    assert form.llm_profile_id == "mock-deterministic-v1"
    assert form.reference_profile_id == "python-src-py312-v1"
    assert form.limits.max_turns == 10
    assert form.limits.max_llm_calls == 10
    assert form.limits.max_run_wall_clock_seconds == 600
    assert form.limits.user_wait_timeout_seconds == 120
    assert form.limits.tool_timeout_seconds == 30
    assert form.limits.target_check_timeout_seconds == 60
    assert form.limits.full_check_timeout_seconds == 120
    assert form.limits.baseline_timeout_seconds == 300
    assert form.limits.formal_validation_timeout_seconds == 300

    # --- override, unknown, malformed, and out-of-range fields reject
    # before any domain call (GREEN-1) ---
    for override_form in (
        {"base_url": "https://bad.example"},
        {"endpoint": "OPENAI_PUBLIC_API_V1"},
        {"max_run_wall_clock_seconds": "999999"},
        {"x-extra": "value"},
    ):
        rejected = client.post(
            "/runs",
            headers=headers,
            data={**valid_run_creation_form(), **override_form},
        )
        assert rejected.status_code == 422
        assert rejected.json()["error_code"] == "FORM_INVALID"
    malformed = client.post(
        "/runs", headers=headers, data={**valid_run_creation_form(), "max_turns": "abc"}
    )
    assert malformed.status_code == 422
    assert malformed.json()["error_code"] == "FORM_INVALID"
    out_of_range = client.post(
        "/runs", headers=headers, data={**valid_run_creation_form(), "max_turns": "21"}
    )
    assert out_of_range.status_code == 422
    assert out_of_range.json()["error_code"] == "FORM_INVALID"
    assert spy.create_call_count == 1  # zero additional domain calls

    # --- a domain rejection renders the stable rejection payload ---
    spy.created_result = RunCreationResultV1(
        kind="REJECTED",
        error_code="TARGET_SET_INVALID",
        reason="目标集合非法。",
        suggestion="提交 1..20 个唯一 pytest 节点。",
    )
    rejected = client.post("/runs", headers=headers, data=valid_run_creation_form())
    assert rejected.status_code == 422
    assert rejected.json()["error_code"] == "TARGET_SET_INVALID"
    assert rejected.json()["message"] == "目标集合非法。"
    assert rejected.json()["next_step"] == "提交 1..20 个唯一 pytest 节点。"
    assert spy.create_call_count == 2

    # --- a browser-style submission uses only the rendered page state:
    # the session cookie from the client jar and the CSRF token the page
    # itself delivers (the htmx wiring attaches exactly this header) ---
    spy.created_result = RunCreationResultV1(kind="CREATED", run_id="run-1")
    create_page = client.get("/runs/new", headers=headers)
    assert create_page.status_code == 200
    meta_token = re.search(
        r'name="csrf-token" content="([0-9a-f]{64})"', create_page.text
    )
    assert meta_token is not None
    assert meta_token.group(1) == _FIXED_TOKEN
    browser_headers = {
        "Host": "127.0.0.1:8765",
        "Origin": "http://127.0.0.1:8765",
        "X-CSRF-Token": meta_token.group(1),
    }
    browser_create = client.post(
        "/runs",
        headers=browser_headers,
        data=valid_run_creation_form(),
        follow_redirects=False,
    )
    assert browser_create.status_code == 303
    assert browser_create.headers["location"] == "/runs/run-1"
    assert spy.create_call_count == 3

    # --- the detail page renders the exact state facts, state-aware ---
    spy.seed_visibility(running_visibility())
    detail = client.get("/runs/run-1", headers=headers)
    assert detail.status_code == 200
    assert "run-1" in detail.text
    assert "运行中" in detail.text  # the exact STATUS_TEXT for AGENT_LOOP
    assert "正在执行阶段" in detail.text  # the exact reason text
    assert "继续运行" in detail.text  # the exact next-action text
    assert 'aria-label="状态：AGENT_LOOP（运行中）"' in detail.text
    assert 'action="/runs/run-1/cancel"' in detail.text
    assert 'hx-post="/runs/run-1/cancel"' in detail.text
    assert "取消运行" in detail.text
    assert 'name="csrf-token"' in detail.text
    assert "htmx:configRequest" in detail.text

    # --- cancellable states render the cancel control; terminal and
    # persistence/recovery states never do (state-aware controls) ---
    for visibility in (
        created_visibility(),
        running_visibility(),
        waiting_visibility(),
        RunVisibilityV1(
            run_id="run-pf",
            state_label="PREFLIGHT",
            reason_code="RUNNING_PHASE",
            next_action="CONTINUE",
            evidence_refs=(),
        ),
        RunVisibilityV1(
            run_id="run-b",
            state_label="BASELINE",
            reason_code="RUNNING_PHASE",
            next_action="CONTINUE",
            evidence_refs=(),
        ),
        RunVisibilityV1(
            run_id="run-fv",
            state_label="FORMAL_VALIDATION",
            reason_code="RUNNING_PHASE",
            next_action="CONTINUE",
            evidence_refs=(),
        ),
    ):
        spy.seed_visibility(visibility)
        page = client.get(f"/runs/{visibility.run_id}", headers=headers)
        assert page.status_code == 200
        assert "取消运行" in page.text
    # a waiting run shows the distinct reason and next-action texts
    spy.seed_visibility(waiting_visibility())
    waiting_page = client.get("/runs/run-1", headers=headers)
    assert "等待用户决定" in waiting_page.text  # the exact reason text
    assert "请处理等待的决定" in waiting_page.text  # the exact next-action text
    for visibility in (
        succeeded_visibility(),
        stopped_visibility(),
        RunVisibilityV1(
            run_id="run-p",
            state_label="PERSISTENCE",
            reason_code="RUNNING_PHASE",
            next_action="CONTINUE",
            evidence_refs=(),
        ),
        RunVisibilityV1(
            run_id="run-r",
            state_label="RECOVERY_REQUIRED",
            reason_code="RECOVERY_PENDING",
            next_action="REVIEW_RECOVERY",
            evidence_refs=(),
        ),
    ):
        spy.seed_visibility(visibility)
        page = client.get(f"/runs/{visibility.run_id}", headers=headers)
        assert page.status_code == 200
        assert "取消运行" not in page.text

    # --- cancel is idempotent and bound to the URL run id only ---
    spy.seed_visibility(running_visibility())
    first_cancel = client.post(
        "/runs/run-1/cancel", headers=headers, data={}, follow_redirects=False
    )
    assert first_cancel.status_code == 303
    assert first_cancel.headers["location"] == "/runs/run-1"
    second_cancel = client.post(
        "/runs/run-1/cancel", headers=headers, data={}, follow_redirects=False
    )
    assert second_cancel.status_code == 303
    assert second_cancel.headers["location"] == "/runs/run-1"
    assert spy.cancelled_runs == ["run-1", "run-1"]

    # --- the cancel form accepts no fields at all ---
    with_field = client.post(
        "/runs/run-1/cancel",
        headers=headers,
        data={"run_id": "run-other"},
    )
    assert with_field.status_code == 422
    assert with_field.json()["error_code"] == "FORM_INVALID"
    assert spy.cancel_call_count == 2

    # --- closed cancel outcomes: not-cancellable and unknown run ---
    spy.cancel_result = RunCancellationResultV1(
        kind="NOT_CANCELLABLE", message="该运行状态不允许取消。"
    )
    not_cancellable = client.post("/runs/run-1/cancel", headers=headers, data={})
    assert not_cancellable.status_code == 409
    assert not_cancellable.json()["error_code"] == "RUN_NOT_CANCELLABLE"
    spy.cancel_result = RunCancellationResultV1(
        kind="NOT_FOUND", message="运行不存在。"
    )
    not_found_cancel = client.post("/runs/run-missing/cancel", headers=headers, data={})
    assert not_found_cancel.status_code == 404
    assert not_found_cancel.json()["error_code"] == "RUN_NOT_FOUND"

    # --- unknown run detail is a closed 404 ---
    unknown = client.get("/runs/run-missing", headers=headers)
    assert unknown.status_code == 404
    assert unknown.json()["error_code"] == "RUN_NOT_FOUND"

    # --- untrusted run text is escaped everywhere (SPEC §4.9) ---
    untrusted = running_visibility(run_id="<img src=x onerror=alert(1)>")
    spy.seed_visibility(untrusted)
    escaped = client.get("/runs/%3Cimg%20src=x%20onerror=alert(1)%3E", headers=headers)
    assert escaped.status_code == 200
    assert "<img src=x onerror=alert(1)>" not in escaped.text
    assert "&lt;img src=x onerror=alert(1)&gt;" in escaped.text

    # --- the Task 28.A boundary rejects before every workflow-port call,
    # and the exact security headers ride on every T29 response ---
    fresh = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")
    no_session = fresh.post(
        "/runs",
        headers={"Host": f"127.0.0.1:{security_config.port}"},
        data=valid_run_creation_form(),
    )
    assert no_session.status_code == 401
    assert no_session.json()["error_code"] == "SESSION_MISSING"
    bad_host = client.post(
        "/runs",
        headers={
            "Host": "evil.example",
            "Origin": "http://127.0.0.1:8765",
            "X-CSRF-Token": _FIXED_TOKEN,
        },
        data=valid_run_creation_form(),
    )
    assert bad_host.status_code == 403
    assert bad_host.json()["error_code"] == "HOST_REJECTED"
    bad_origin = client.post(
        "/runs",
        headers={
            "Host": "127.0.0.1:8765",
            "Origin": "https://attacker.example",
            "X-CSRF-Token": _FIXED_TOKEN,
        },
        data=valid_run_creation_form(),
    )
    assert bad_origin.status_code == 403
    assert bad_origin.json()["error_code"] == "ORIGIN_REJECTED"
    bad_csrf = client.post(
        "/runs",
        headers={
            "Host": "127.0.0.1:8765",
            "Origin": "http://127.0.0.1:8765",
            "X-CSRF-Token": "0" * 64,
        },
        data=valid_run_creation_form(),
    )
    assert bad_csrf.status_code == 403
    assert bad_csrf.json()["error_code"] == "CSRF_REJECTED"
    assert spy.create_call_count == 3  # zero domain calls after rejections
    page_headers = detail.headers
    assert page_headers["x-content-type-options"] == "nosniff"
    assert page_headers["x-frame-options"] == "DENY"
    assert page_headers["referrer-policy"] == "no-referrer"
    assert page_headers["content-security-policy"].startswith("default-src 'self'")
    assert f"'nonce-{_MIRROR_NONCE}'" in page_headers["content-security-policy"]


def test_real_composition_installs_run_lifecycle_routes(
    security_config: LocalWebSecurityConfigV1,
    workflow_ports: SpyRunLifecyclePorts,
) -> None:
    """The real Task 28.B composition installs the T29.1 routes (the
    substantive production composition behind the mirror fixture)."""
    workflow_ports.seed_visibility(running_visibility())
    shell_ports: LocalShellPortsV1 = FakeShellPortsV1(())
    installer = RunLifecycleRouteInstallerV1(
        RunLifecycleWorkflowPortsV1(
            creation=workflow_ports,
            visibility=workflow_ports,
            cancellation=workflow_ports,
        )
    )
    app = create_local_app(shell_ports, security_config, (installer,))
    client = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")
    # the home route bootstraps one bounded local session (Task 28.B)
    home = client.get("/", headers={"Host": f"127.0.0.1:{security_config.port}"})
    assert home.status_code == 200
    detail = client.get(
        "/runs/run-1", headers={"Host": f"127.0.0.1:{security_config.port}"}
    )
    assert detail.status_code == 200
    assert "run-1" in detail.text
    assert "运行中" in detail.text
    # a state change still requires the fixed Origin then CSRF checks
    session_id = client.cookies.get(security_config.session_cookie_name)
    assert session_id is not None
    manager = app.state.local_session_manager
    session = manager.get(session_id)
    assert session is not None
    origin_headers = {
        "Host": f"127.0.0.1:{security_config.port}",
        "Origin": f"http://127.0.0.1:{security_config.port}",
    }
    no_csrf = client.post("/runs/run-1/cancel", headers=origin_headers, data={})
    assert no_csrf.status_code == 403
    assert no_csrf.json()["error_code"] == "CSRF_REJECTED"

    # --- the full browser-style flow through the real composition: the
    # create page delivers the session CSRF token, and a submission using
    # only the cookie and the rendered token passes the boundary, creates
    # the run, and lands on its detail page (SPEC §5.5 usable forms) ---
    workflow_ports.created_result = RunCreationResultV1(kind="CREATED", run_id="run-1")
    create_page = client.get(
        "/runs/new", headers={"Host": f"127.0.0.1:{security_config.port}"}
    )
    assert create_page.status_code == 200
    meta_token = re.search(
        r'name="csrf-token" content="([0-9a-f]{64})"', create_page.text
    )
    assert meta_token is not None
    assert meta_token.group(1) == session.csrf_token
    browser_headers = {
        **origin_headers,
        "X-CSRF-Token": meta_token.group(1),
    }
    created = client.post(
        "/runs", headers=browser_headers, data=valid_run_creation_form()
    )
    assert created.status_code == 200  # 303 followed to the detail page
    assert "运行中" in created.text
    assert workflow_ports.create_call_count == 1
    # and the same flow cancels the run through its rendered control
    cancelled = client.post("/runs/run-1/cancel", headers=browser_headers, data={})
    assert cancelled.status_code == 200  # 303 followed to the detail page
    assert "运行中" in cancelled.text
    assert workflow_ports.cancelled_runs == ["run-1"]
