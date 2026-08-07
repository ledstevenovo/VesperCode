"""T29.2 legacy step 29.B: disclosure decision WebUI tests.

The exact RED pins the smallest override rejection (a scope/endpoint
override field on the disclosure decision form rejects with 422 before
any workflow-port call); the matrix pins the Expected (29.B) line —
exact human labels, no-content-redaction warning, expiry, budget, and
closed decision binding pass — behind the exact Task 28.A security order.
Per the SPEC_PROCESS section-49 precedent the card's "exact section 5.1
matrix" reference is non-operative; the Expected (29.B) line is the
matrix authority.

Fixture interpretation (T28.1 M3-precedent class, same as T29.1): the
``local_web_client`` fixture is a test-local composition mirror whose
middleware logic mirrors the Task 28.B shell verbatim (fixed HOST ->
SESSION -> ORIGIN -> CSRF order and the exact security headers) with a
deterministic-token session manager, and the fixture pre-creates one
session whose cookie the client carries, so the card's RED post (which
passes only ``valid_local_security_headers()``) passes through the exact
security order and reaches the closed-form validation.  The substantive
production composition is pinned by the Task 28.2 app-composition tests
and by this file's real-composition domain test.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Callable, Final, cast

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.credentials.port import CredentialStatusV1
from vespercode.governance.disclosure_decision import (
    DecideDisclosureGrantV1,
    DisclosureDecisionResultV1,
)
from vespercode.governance.disclosure_scope import (
    DirectoryDisclosureScopeV1,
    DisclosureScopeSequenceV1,
)
from vespercode.governance.disclosure_subject import (
    DisclosureGrantSubjectV1,
    DisclosureSubjectRequestV1,
    build_disclosure_subject,
)
from vespercode.governance.request_sources import (
    RequestSourceV1,
    SourceProjectionV1,
)
from vespercode.profiles.endpoints import (
    OpenAIEndpointRegistry,
    OpenAIEndpointV1,
)
from vespercode.profiles.llm import OpenAILLMProfileV1, load_llm_profile
from vespercode.web.app import RunVisibilitySequenceV1, create_local_app
from vespercode.web.disclosure_workflow import (
    AuthorizationSummaryV1,
    DisclosureWaitFactsV1,
    build_authorization_summary,
)
from vespercode.web.routes_disclosure import DisclosureRouteInstallerV1
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

_OPENAI_BUILTIN: Final[Path] = (
    Path(__file__).resolve().parents[2]
    / "src/vespercode/profiles/builtin/openai-single-turn-v1.json"
)
"""The frozen packaged built-in OpenAI profile (digest-verified)."""

_CREATED_AT = CanonicalTimestampV1("2026-08-07T09:00:00.000Z")
_EXPIRES_AT = CanonicalTimestampV1("2026-08-07T09:05:00.000Z")
_DECIDED_AT = CanonicalTimestampV1("2026-08-07T09:01:00.000Z")
"""One fixed deterministic instant for the injectable fake clock."""


def _fixed_token_generator() -> Callable[[], str]:
    """One deterministic session/CSRF token generator (SPEC §5.4)."""

    def generate() -> str:
        return _FIXED_TOKEN

    return generate


def valid_local_security_headers() -> dict[str, str]:
    """One fully valid loopback request-header set (Host + Origin + CSRF)."""
    return {
        "Host": "127.0.0.1:8765",
        "Origin": "http://127.0.0.1:8765",
        "X-CSRF-Token": _FIXED_TOKEN,
    }


def profile() -> OpenAILLMProfileV1:
    """The frozen packaged built-in OpenAI profile (digest-verified)."""
    loaded = load_llm_profile(_OPENAI_BUILTIN.read_bytes())
    assert isinstance(loaded, OpenAILLMProfileV1)
    return loaded


def endpoint() -> OpenAIEndpointV1:
    """The trusted built-in endpoint record (SPEC §4.1/§4.4.3)."""
    return OpenAIEndpointRegistry.resolve("OPENAI_PUBLIC_API_V1")


def sources() -> SourceProjectionV1:
    """One validated source projection with a path-bearing TOOL_RESULT."""
    raw = "tool bytes".encode("utf-8")
    return (
        RequestSourceV1(
            message_index=0,
            segment_index=0,
            source_category="TOOL_RESULT",
            source_path=PresentV1(
                kind="PRESENT", value=CanonicalRelativePathV1("src/a.py")
            ),
            content_digest=hashlib.sha256(raw).hexdigest(),
            byte_count=len(raw),
        ),
    )


def scopes() -> DisclosureScopeSequenceV1:
    """One canonical DIRECTORY disclosure scope (SPEC §4.4.3)."""
    return (
        DirectoryDisclosureScopeV1(
            kind="DIRECTORY", path=CanonicalRelativePathV1("src")
        ),
    )


def disclosure_subject(run_id: str = "run-1") -> DisclosureGrantSubjectV1:
    """One immutable disclosure Grant subject for the declared run."""
    return build_disclosure_subject(
        DisclosureSubjectRequestV1(
            run_id=run_id,
            expires_at=_EXPIRES_AT,
            cumulative_byte_budget=100000,
            url=AbsentV1(kind="ABSENT"),
        ),
        sources(),
        scopes(),
        profile(),
        endpoint(),
    )


def wait_facts(run_id: str = "run-1", decided: bool = False) -> DisclosureWaitFactsV1:
    """One exact current disclosure wait for the declared run."""
    subject = disclosure_subject(run_id)
    return DisclosureWaitFactsV1(
        wait_id="wait-1",
        run_id=run_id,
        subject=subject,
        created_at=_CREATED_AT,
        expires_at=subject.expires_at,
        decided=decided,
    )


def valid_disclosure_decision() -> dict[str, str]:
    """One valid bound disclosure decision form body."""
    return {
        "decision": "approve",
        "wait_id": "wait-1",
        "subject_digest": disclosure_subject().digest,
    }


class FakeWorkflowIdentityV1:
    """One deterministic control-plane identity/clock (SPEC §5.4)."""

    def new_grant_id(self) -> str:
        return "grant-1"

    def new_approval_id(self) -> str:
        return "approval-1"

    def new_event_id(self) -> str:
        return "event-1"

    def now(self) -> CanonicalTimestampV1:
        return _DECIDED_AT


class SpyDisclosurePorts:
    """One spy typed disclosure-decision workflow-port implementation."""

    def __init__(self) -> None:
        self.decide_call_count = 0
        self.decide_result = DisclosureDecisionResultV1(
            kind="APPROVED", message="disclosure grant created"
        )
        self._waits: dict[str, DisclosureWaitFactsV1] = {}
        self._commands: list[DecideDisclosureGrantV1] = []

    def seed_wait(self, facts: DisclosureWaitFactsV1) -> None:
        """Seed one exact disclosure wait the page renders."""
        self._waits[facts.run_id] = facts

    def disclosure_wait_for(self, run_id: str) -> DisclosureWaitFactsV1 | None:
        return self._waits.get(run_id)

    def decide(self, command: DecideDisclosureGrantV1) -> DisclosureDecisionResultV1:
        self.decide_call_count += 1
        self._commands.append(command)
        return self.decide_result

    @property
    def last_command(self) -> DecideDisclosureGrantV1 | None:
        return self._commands[-1] if self._commands else None


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
    installer: DisclosureRouteInstallerV1,
) -> tuple[FastAPI, LocalSessionManager]:
    """One test-local shell mirroring the Task 28.B composition."""
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

    installer.install(app)
    return app, manager


def _attach_headers(response: Any, csp_nonce: str | None) -> None:
    """Attach the exact CSP and response security headers to one response."""
    for name, value in local_response_security_headers(csp_nonce).items():
        response.headers[name] = value


@pytest.fixture
def disclosure_ports() -> SpyDisclosurePorts:
    return SpyDisclosurePorts()


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
    disclosure_ports: SpyDisclosurePorts,
) -> TestClient:
    installer = DisclosureRouteInstallerV1(disclosure_ports, FakeWorkflowIdentityV1())
    app, manager = _build_local_app(security_config, installer)
    client = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")
    session = manager.create()
    client.cookies.set(security_config.session_cookie_name, session.session_id)
    return client


def test_disclosure_form_cannot_supply_scope_or_endpoint_override(
    local_web_client: TestClient,
    disclosure_ports: SpyDisclosurePorts,
) -> None:
    response = local_web_client.post(
        "/runs/run-1/disclosure",
        headers=valid_local_security_headers(),
        data=valid_disclosure_decision() | {"base_url": "https://bad.example"},
    )
    assert response.status_code == 422
    assert disclosure_ports.decide_call_count == 0


def test_disclosure_web_workflow_matrix(
    local_web_client: TestClient,
    security_config: LocalWebSecurityConfigV1,
    disclosure_ports: SpyDisclosurePorts,
) -> None:
    """The exact disclosure WebUI matrix (Expected 29.B authority).

    Exact human labels, the no-content-redaction warning, expiry, budget,
    and closed decision binding pass; the form can never supply scope,
    endpoint, budget, credential, or clock overrides, and the Task 28.A
    boundary rejects before every workflow-port call.
    """
    client = local_web_client
    headers = valid_local_security_headers()
    app = cast(FastAPI, client.app)
    spy = disclosure_ports
    facts = wait_facts()
    spy.seed_wait(facts)
    subject = facts.subject

    # --- the disclosure page renders the exact summary facts ---
    page = client.get("/runs/run-1/disclosure", headers=headers)
    assert page.status_code == 200
    text = page.text
    for label in (
        "供应商",
        "端点标识",
        "目的主机",
        "模型",
        "来源类别",
        "来源路径",
        "累计字节预算",
        "有效期至",
        "脱敏配置",
    ):
        assert label in text
    assert "openai" in text  # the subject provider
    assert "OPENAI_PUBLIC_API_V1" in text  # the exact endpoint id
    assert "api.openai.com" in text  # the trusted builtin host
    assert "gpt-4.1-mini" in text  # the frozen profile model
    assert "工具结果" in text  # the exact category label
    assert "目录及其后代：src" in text  # the exact scope label (no sentinel)
    assert "100000 字节" in text  # the exact byte budget
    assert subject.expires_at.value in text  # the exact expiry
    assert "NO_CONTENT_REDACTION_V1" in text
    assert "被选择的项目正文将在规范裁剪后原样发送" in text  # the warning
    assert "敏感路径拒绝不等于通用秘密扫描" in text
    assert f'value="{facts.wait_id}"' in text  # the hidden binding
    assert f'value="{subject.digest}"' in text
    assert "批准披露" in text
    assert "拒绝披露" in text
    # the page never carries a form-supplied URL or override field
    for forbidden in ("base_url", "bad.example", "endpoint_id", "api_key"):
        assert forbidden not in text
    # the CSRF delivery wiring is present (Task 28.A header form)
    assert 'name="csrf-token"' in text
    assert f'content="{_FIXED_TOKEN}"' in text
    assert 'hx-post="/runs/run-1/disclosure"' in text
    assert "htmx:configRequest" in text

    # --- a valid approve submits exactly one bound decision ---
    approved = client.post(
        "/runs/run-1/disclosure",
        headers=headers,
        data=valid_disclosure_decision(),
        follow_redirects=False,
    )
    assert approved.status_code == 303
    assert approved.headers["location"] == "/runs/run-1"
    assert spy.decide_call_count == 1
    command = spy.last_command
    assert command is not None
    assert command.decision.wait_id == "wait-1"
    assert command.decision.run_id == "run-1"
    assert command.decision.wait_kind == "DISCLOSURE_GRANT"
    assert command.decision.subject_digest.value == subject.digest
    assert command.decision.decision == "APPROVE"
    assert command.decision.event_id == "event-1"
    assert command.decision.decided_at == _DECIDED_AT
    assert command.grant_id == "grant-1"
    assert command.subject == subject  # the exact immutable subject

    # --- a valid reject submits the closed REJECT choice ---
    rejected = client.post(
        "/runs/run-1/disclosure",
        headers=headers,
        data={**valid_disclosure_decision(), "decision": "reject"},
        follow_redirects=False,
    )
    assert rejected.status_code == 303
    assert spy.last_command is not None
    assert spy.last_command.decision.decision == "REJECT"
    assert spy.decide_call_count == 2

    # --- the closed port-outcome mappings are pinned: replay is the
    # idempotent repeat (same 303), conflict and every other closed
    # outcome fail closed with stable payloads ---
    spy.decide_result = DisclosureDecisionResultV1(
        kind="REPLAY", message="wait decision already recorded identically"
    )
    replayed = client.post(
        "/runs/run-1/disclosure",
        headers=headers,
        data=valid_disclosure_decision(),
        follow_redirects=False,
    )
    assert replayed.status_code == 303
    assert replayed.headers["location"] == "/runs/run-1"
    spy.decide_result = DisclosureDecisionResultV1(
        kind="CONFLICT", message="wait decision already recorded differently"
    )
    conflicted = client.post(
        "/runs/run-1/disclosure",
        headers=headers,
        data=valid_disclosure_decision(),
    )
    assert conflicted.status_code == 409
    assert conflicted.json()["error_code"] == "DISCLOSURE_CONFLICT"
    assert conflicted.json()["message"] == "wait decision already recorded differently"
    spy.decide_result = DisclosureDecisionResultV1(
        kind="EXPIRED", message="disclosure wait already expired"
    )
    expired = client.post(
        "/runs/run-1/disclosure",
        headers=headers,
        data=valid_disclosure_decision(),
    )
    assert expired.status_code == 409
    assert expired.json()["error_code"] == "DISCLOSURE_DECISION_REJECTED"
    assert expired.json()["message"] == "disclosure wait already expired"
    assert expired.json()["next_step"] == "刷新页面后重试。"
    spy.decide_result = DisclosureDecisionResultV1(
        kind="APPROVED", message="disclosure grant created"
    )

    # --- scope/endpoint/budget/credential/clock overrides reject before
    # any workflow-port call (GREEN-2) ---
    for override in (
        {"base_url": "https://bad.example"},
        {"endpoint_id": "OPENAI_PUBLIC_API_V1"},
        {"cumulative_byte_budget": "999999999"},
        {"expires_at": "2099-01-01T00:00:00.000Z"},
        {"credential": "sk-test"},
        {"decided_at": "2026-08-07T09:02:00.000Z"},
        {"x-extra": "value"},
    ):
        overridden = client.post(
            "/runs/run-1/disclosure",
            headers=headers,
            data={**valid_disclosure_decision(), **override},
        )
        assert overridden.status_code == 422
        assert overridden.json()["error_code"] == "FORM_INVALID"
    assert spy.decide_call_count == 5  # zero additional domain calls

    # --- stale binding rejects before any domain call (AC-27) ---
    stale = client.post(
        "/runs/run-1/disclosure",
        headers=headers,
        data={
            **valid_disclosure_decision(),
            "subject_digest": "0" * 64,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error_code"] == "DISCLOSURE_STALE"
    wrong_wait = client.post(
        "/runs/run-1/disclosure",
        headers=headers,
        data={**valid_disclosure_decision(), "wait_id": "wait-other"},
    )
    assert wrong_wait.status_code == 409
    assert wrong_wait.json()["error_code"] == "DISCLOSURE_STALE"
    assert spy.decide_call_count == 5  # zero domain calls after staleness

    # --- invalid decision values reject at the closed schema ---
    invalid_decision = client.post(
        "/runs/run-1/disclosure",
        headers=headers,
        data={**valid_disclosure_decision(), "decision": "maybe"},
    )
    assert invalid_decision.status_code == 422
    assert invalid_decision.json()["error_code"] == "FORM_INVALID"
    assert spy.decide_call_count == 5

    # --- unknown run is a closed 404 ---
    unknown = client.get("/runs/run-missing/disclosure", headers=headers)
    assert unknown.status_code == 404
    assert unknown.json()["error_code"] == "DISCLOSURE_WAIT_NOT_FOUND"

    # --- a decided wait renders no decision controls (state-aware) ---
    spy.seed_wait(wait_facts(decided=True))
    decided_page = client.get("/runs/run-1/disclosure", headers=headers)
    assert decided_page.status_code == 200
    assert "该披露等待已处理" in decided_page.text
    assert "批准披露" not in decided_page.text
    assert "拒绝披露" not in decided_page.text

    # --- untrusted run text is escaped everywhere (SPEC §4.9) ---
    untrusted_facts = wait_facts(run_id="<img src=x onerror=alert(1)>")
    spy.seed_wait(untrusted_facts)
    escaped = client.get(
        "/runs/%3Cimg%20src=x%20onerror=alert(1)%3E/disclosure", headers=headers
    )
    assert escaped.status_code == 200
    assert "<img src=x onerror=alert(1)>" not in escaped.text
    assert "&lt;img src=x onerror=alert(1)&gt;" in escaped.text

    # --- the Task 28.A boundary rejects before every port call, and the
    # exact security headers ride on every T29 response ---
    spy.seed_wait(wait_facts())
    fresh = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")
    no_session = fresh.post(
        "/runs/run-1/disclosure",
        headers={"Host": f"127.0.0.1:{security_config.port}"},
        data=valid_disclosure_decision(),
    )
    assert no_session.status_code == 401
    assert no_session.json()["error_code"] == "SESSION_MISSING"
    bad_origin = client.post(
        "/runs/run-1/disclosure",
        headers={
            "Host": "127.0.0.1:8765",
            "Origin": "https://attacker.example",
            "X-CSRF-Token": _FIXED_TOKEN,
        },
        data=valid_disclosure_decision(),
    )
    assert bad_origin.status_code == 403
    assert bad_origin.json()["error_code"] == "ORIGIN_REJECTED"
    assert spy.decide_call_count == 5  # zero domain calls after rejections
    page_headers = page.headers
    assert page_headers["x-content-type-options"] == "nosniff"
    assert page_headers["x-frame-options"] == "DENY"
    assert page_headers["referrer-policy"] == "no-referrer"
    assert page_headers["content-security-policy"].startswith("default-src 'self'")
    assert f"'nonce-{_MIRROR_NONCE}'" in page_headers["content-security-policy"]

    # --- the summary functions are pure and bound to the exact subject
    # and the trusted endpoint record (SPEC §4.4.3) ---
    summary: AuthorizationSummaryV1 = build_authorization_summary(subject, endpoint())
    assert summary.provider == subject.provider
    assert summary.endpoint_id == subject.endpoint_id
    assert summary.endpoint_host == "api.openai.com"
    assert summary.model == subject.model
    assert summary.categories == subject.allowed_source_categories
    assert summary.source_scopes == subject.allowed_source_paths
    assert summary.cumulative_byte_budget == subject.cumulative_byte_budget
    assert summary.expires_at == subject.expires_at
    assert summary.redaction_profile_id == "NO_CONTENT_REDACTION_V1"


def test_real_composition_installs_disclosure_routes(
    security_config: LocalWebSecurityConfigV1,
    disclosure_ports: SpyDisclosurePorts,
) -> None:
    """The real Task 28.B composition installs the T29.2 routes (the
    substantive production composition behind the mirror fixture)."""
    disclosure_ports.seed_wait(wait_facts())
    installer = DisclosureRouteInstallerV1(disclosure_ports, FakeWorkflowIdentityV1())

    class _ShellPorts:
        def list_recent_runs(self) -> RunVisibilitySequenceV1:
            return ()

        def credential_status(self) -> CredentialStatusV1:
            return CredentialStatusV1(
                schema_version=1,
                provider="OPENAI",
                configured=False,
                updated_at=AbsentV1(kind="ABSENT"),
            )

    app = create_local_app(_ShellPorts(), security_config, (installer,))
    client = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")
    home = client.get("/", headers={"Host": f"127.0.0.1:{security_config.port}"})
    assert home.status_code == 200
    page = client.get(
        "/runs/run-1/disclosure",
        headers={"Host": f"127.0.0.1:{security_config.port}"},
    )
    assert page.status_code == 200
    assert "api.openai.com" in page.text
    assert "目录及其后代：src" in page.text
    # the browser-style decision post uses only the rendered page state:
    # the session cookie from the client jar and the rendered CSRF token
    session_id = client.cookies.get(security_config.session_cookie_name)
    assert session_id is not None
    manager = app.state.local_session_manager
    session = manager.get(session_id)
    assert session is not None
    meta_token = re.search(r'name="csrf-token" content="([0-9a-f]{64})"', page.text)
    assert meta_token is not None
    assert meta_token.group(1) == session.csrf_token
    browser_headers = {
        "Host": f"127.0.0.1:{security_config.port}",
        "Origin": f"http://127.0.0.1:{security_config.port}",
        "X-CSRF-Token": meta_token.group(1),
    }
    decided = client.post(
        "/runs/run-1/disclosure",
        headers=browser_headers,
        data=valid_disclosure_decision(),
        follow_redirects=False,
    )
    assert decided.status_code == 303
    assert decided.headers["location"] == "/runs/run-1"
    assert disclosure_ports.decide_call_count == 1
