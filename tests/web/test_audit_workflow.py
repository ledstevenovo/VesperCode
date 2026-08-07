"""T38.1 legacy step 38.C: redacted audit WebUI tests.

The exact RED pins the smallest redacted-projection contract: raw
request and backup-body sentinels must be absent from every rendered
page and error branch (SPEC §4.7/§5.3/§5.6).  The ``audit_client``
fixture is a test-local mirror (the T28.1 M3-precedent class documented
in T29.1) whose middleware mirrors the Task 28.A fixed order verbatim
and whose deterministic session lets the card's header-only GET pass the
exact security order and reach the real ``AuditRouteInstallerV1`` over
the spy ports.

The domain pins cover the monotonic cursor ordering, bounded pagination,
the redacted page projection (hostile free-text payload values never
render), the explicit ended-Run clear confirmation, recovery
preservation, security, and accessibility.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Final

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from src.vespercode.audit.event import (
    ActionPayloadV1,
    AuditEventV1,
    DisclosureAuthorizationPayloadV1,
    LifecyclePayloadV1,
    RecoveryPayloadV1,
    StopEvidencePayloadV1,
)
from src.vespercode.audit.repository import (
    AuditClearResultV1,
    AuditCursorV1,
    AuditPageRequestV1,
    AuditPageV1,
    ClearEndedRunAuditV1,
)
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.web.routes_audit import (
    AuditClearStateV1,
    AuditRouteInstallerV1,
    AuditWorkflowIdentityPortV1,
    AuditWorkflowPortsV1,
)
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

_FIXED_TOKEN: Final[str] = "f" * 64
"""One deterministic 256-bit hex session/CSRF token (closed token form)."""

_MIRROR_NONCE: Final[str] = "test-nonce-1234567890"
"""One deterministic closed CSP nonce form for the test-local mirror."""

_FIXED_NOW = CanonicalTimestampV1("2026-08-07T09:00:00.000Z")


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


def _rejection_response(error_code: LocalRequestErrorCodeV1) -> JSONResponse:
    """One closed rejection response carrying the exact security headers."""
    payload = local_request_rejection_payload(error_code)
    response = JSONResponse(
        status_code=local_request_status(error_code), content=payload
    )
    for name, value in local_response_security_headers().items():
        response.headers[name] = value
    return response


def _attach_headers(response: Any, csp_nonce: str | None) -> None:
    """Attach the exact CSP and response security headers to one response."""
    for name, value in local_response_security_headers(csp_nonce).items():
        response.headers[name] = value


def _build_local_app(
    security_config: LocalWebSecurityConfigV1,
    installers: tuple[Any, ...],
) -> tuple[FastAPI, LocalSessionManager]:
    """One test-local shell mirroring the Task 28.B composition."""
    manager = LocalSessionManager(
        security_config, token_generator=_fixed_token_generator()
    )
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.local_security_config = security_config
    app.state.local_session_manager = manager
    app.state.local_templates = Jinja2Templates(
        directory=str(
            Path(__file__).resolve().parents[2] / "src/vespercode/web/templates"
        )
    )

    @app.middleware("http")
    async def _local_security_middleware(request: Request, call_next: Any) -> Any:
        assert isinstance(
            request, Request
        )  # the runtime contract is a starlette Request
        request.state.csp_nonce = _MIRROR_NONCE
        if not is_loopback_host(request.headers.get("host", "")):
            return _rejection_response("HOST_REJECTED")
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


def audit_event(
    sequence: int,
    payload: Any,
    *,
    run_id: str = "run-1",
) -> AuditEventV1:
    """One immutable redacted audit event (SPEC 7 AuditEvent row)."""
    return AuditEventV1(
        run_id=run_id,
        sequence=sequence,
        event_type=payload.kind,
        redacted_payload=payload,
        created_at=_FIXED_NOW,
    )


class SpyAuditPorts:
    """One spy typed audit workflow-port implementation.

    The spy records every page request and clear command for exact
    pinning; the routes own no sequencing, redaction, retention, or
    deletion rule.
    """

    def __init__(self) -> None:
        self.list_call_count = 0
        self.clear_call_count = 0
        self.page_result = AuditPageV1(run_id="run-1", items=())
        self.clear_result = AuditClearResultV1(
            kind="CLEARED", message="audit events cleared"
        )
        self.clear_state = AuditClearStateV1(
            run_id="run-1", run_ended=True, has_unresolved_recovery=False
        )
        self._page_requests: list[AuditPageRequestV1] = []
        self._clear_commands: list[ClearEndedRunAuditV1] = []

    def seed_page(self, page: AuditPageV1) -> None:
        self.page_result = page

    def seed_clear_result(self, result: AuditClearResultV1) -> None:
        self.clear_result = result

    def seed_clear_state(self, state: AuditClearStateV1) -> None:
        self.clear_state = state

    @property
    def page_requests(self) -> list[AuditPageRequestV1]:
        return list(self._page_requests)

    @property
    def clear_commands(self) -> list[ClearEndedRunAuditV1]:
        return list(self._clear_commands)

    def list_run(self, run_id: str, page: AuditPageRequestV1) -> AuditPageV1:
        self.list_call_count += 1
        self._page_requests.append(page)
        return self.page_result

    def clear_ended_run(self, command: ClearEndedRunAuditV1) -> AuditClearResultV1:
        self.clear_call_count += 1
        self._clear_commands.append(command)
        return self.clear_result

    def clear_state_for(self, run_id: str) -> AuditClearStateV1:
        return self.clear_state


class FixedAuditIdentityPortV1:
    """One deterministic server-controlled identity seam (SPEC §5.4)."""

    def __init__(self) -> None:
        self._counter = 0

    def new_event_id(self) -> str:
        self._counter += 1
        return f"audit-event-{self._counter}"

    def now(self) -> CanonicalTimestampV1:
        return _FIXED_NOW


@pytest.fixture
def security_config() -> LocalWebSecurityConfigV1:
    return LocalWebSecurityConfigV1(
        host="127.0.0.1",
        port=8765,
        session_cookie_name="vespercode_session",
        csrf_header_name="X-CSRF-Token",
    )


@pytest.fixture
def audit_ports() -> SpyAuditPorts:
    return SpyAuditPorts()


@pytest.fixture
def audit_identity() -> FixedAuditIdentityPortV1:
    return FixedAuditIdentityPortV1()


@pytest.fixture
def audit_client(
    security_config: LocalWebSecurityConfigV1,
    audit_ports: SpyAuditPorts,
    audit_identity: FixedAuditIdentityPortV1,
) -> TestClient:
    ports: AuditWorkflowPortsV1 = audit_ports
    identity: AuditWorkflowIdentityPortV1 = audit_identity
    app, manager = _build_local_app(
        security_config, (AuditRouteInstallerV1(ports, identity),)
    )
    client = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")
    session = manager.create()
    client.cookies.set(security_config.session_cookie_name, session.session_id)
    return client


def test_audit_page_contains_only_redacted_projection(
    audit_client: TestClient,
) -> None:
    response = audit_client.get(
        "/runs/run-1/audit", headers=valid_local_security_headers()
    )
    assert "raw-request-sentinel" not in response.text
    assert "backup-body-sentinel" not in response.text


def test_audit_page_renders_only_closed_facts_from_redacted_payloads(
    audit_client: TestClient,
    audit_ports: SpyAuditPorts,
) -> None:
    """Hostile free-text payload values (raw request and backup-body
    sentinels in action type, stop reason, and byte-count fields) never
    reach the rendered page; only the closed-literal fact lines render
    (GREEN-3)."""
    audit_ports.seed_page(
        AuditPageV1(
            run_id="run-1",
            items=(
                audit_event(
                    1,
                    ActionPayloadV1(
                        kind="ACTION",
                        action_type="raw-request-sentinel",
                        policy_decision="ALLOW",
                    ),
                ),
                audit_event(
                    2,
                    StopEvidencePayloadV1(
                        kind="STOP_EVIDENCE",
                        reason_code="backup-body-sentinel",
                    ),
                ),
                audit_event(
                    3,
                    DisclosureAuthorizationPayloadV1(
                        kind="DISCLOSURE_AUTHORIZATION",
                        category="FILE",
                        byte_count="raw-req-sentinel",
                    ),
                ),
                audit_event(
                    4,
                    LifecyclePayloadV1(
                        kind="LIFECYCLE", status="SUCCEEDED", phase=None
                    ),
                ),
            ),
        )
    )
    response = audit_client.get(
        "/runs/run-1/audit", headers=valid_local_security_headers()
    )
    assert response.status_code == 200
    assert "raw-request-sentinel" not in response.text
    assert "raw-req-sentinel" not in response.text
    assert "backup-body-sentinel" not in response.text
    assert "策略决策：允许" in response.text
    assert "已记录停止证据" in response.text
    assert "类别：文件" in response.text
    assert "状态：成功" in response.text
    assert "#1" in response.text and "#2" in response.text and "#3" in response.text


def test_audit_page_preserves_monotonic_cursor_order(
    audit_client: TestClient,
    audit_ports: SpyAuditPorts,
) -> None:
    """The page renders the projection in the monotonic sequence order
    with the exact per-Run sequence labels (GREEN-1)."""
    audit_ports.seed_page(
        AuditPageV1(
            run_id="run-1",
            items=(
                audit_event(1, LifecyclePayloadV1(kind="LIFECYCLE", status="CREATED")),
                audit_event(
                    2,
                    LifecyclePayloadV1(
                        kind="LIFECYCLE", status="RUNNING", phase="AGENT_LOOP"
                    ),
                ),
                audit_event(
                    3, LifecyclePayloadV1(kind="LIFECYCLE", status="SUCCEEDED")
                ),
            ),
        )
    )
    response = audit_client.get(
        "/runs/run-1/audit", headers=valid_local_security_headers()
    )
    text = response.text
    assert text.index("#1") < text.index("#2") < text.index("#3")
    assert "阶段：主循环" in text


def test_audit_pagination_uses_bounded_keyset_cursor(
    audit_client: TestClient,
    audit_ports: SpyAuditPorts,
) -> None:
    """The next-page link carries the keyset cursor of the exact Run; a
    follow-up request adapts it into the closed bounded page request
    (GREEN-1)."""
    audit_ports.seed_page(
        AuditPageV1(
            run_id="run-1",
            items=(
                audit_event(1, LifecyclePayloadV1(kind="LIFECYCLE", status="CREATED")),
                audit_event(
                    2,
                    LifecyclePayloadV1(
                        kind="LIFECYCLE", status="RUNNING", phase="AGENT_LOOP"
                    ),
                ),
            ),
            next_cursor=AuditCursorV1(run_id="run-1", last_sequence=2),
        )
    )
    response = audit_client.get(
        "/runs/run-1/audit", headers=valid_local_security_headers()
    )
    assert "?cursor=2" in response.text
    audit_ports.seed_page(
        AuditPageV1(
            run_id="run-1",
            items=(
                audit_event(
                    3, LifecyclePayloadV1(kind="LIFECYCLE", status="SUCCEEDED")
                ),
            ),
        )
    )
    response = audit_client.get(
        "/runs/run-1/audit?cursor=2", headers=valid_local_security_headers()
    )
    assert response.status_code == 200
    assert audit_ports.list_call_count == 2
    request = audit_ports.page_requests[1]
    assert request.page_size == 20
    assert request.cursor == AuditCursorV1(run_id="run-1", last_sequence=2)
    assert "#3" in response.text


def test_audit_malformed_cursor_fails_closed(
    audit_client: TestClient,
    audit_ports: SpyAuditPorts,
) -> None:
    """A malformed cursor rejects with zero partial results."""
    for malformed in ("abc", "-1", "2.5", "run-1:2"):
        response = audit_client.get(
            f"/runs/run-1/audit?cursor={malformed}",
            headers=valid_local_security_headers(),
        )
        assert response.status_code == 422
    assert audit_ports.list_call_count == 0


def test_audit_clear_control_renders_only_for_ended_run_without_recovery(
    audit_client: TestClient,
    audit_ports: SpyAuditPorts,
) -> None:
    """The explicit clear control renders only for an ended Run without
    unresolved recovery evidence; recovery warnings render instead
    otherwise (GREEN-2)."""
    audit_ports.seed_clear_state(
        AuditClearStateV1(run_id="run-1", run_ended=True, has_unresolved_recovery=False)
    )
    response = audit_client.get(
        "/runs/run-1/audit", headers=valid_local_security_headers()
    )
    assert "我确认清除该已结束运行的本地审计" in response.text
    assert 'name="confirm"' in response.text

    audit_ports.seed_clear_state(
        AuditClearStateV1(
            run_id="run-1", run_ended=False, has_unresolved_recovery=False
        )
    )
    response = audit_client.get(
        "/runs/run-1/audit", headers=valid_local_security_headers()
    )
    assert "该运行尚未结束，不能清除审计。" in response.text
    assert 'name="confirm"' not in response.text

    audit_ports.seed_clear_state(
        AuditClearStateV1(run_id="run-1", run_ended=True, has_unresolved_recovery=True)
    )
    response = audit_client.get(
        "/runs/run-1/audit", headers=valid_local_security_headers()
    )
    assert "该运行存在未解决的恢复证据，审计保留" in response.text
    assert 'name="confirm"' not in response.text


def test_audit_unresolved_recovery_fact_renders_warning(
    audit_client: TestClient,
    audit_ports: SpyAuditPorts,
) -> None:
    """An UNRESOLVED recovery fact renders the warning disposition and
    the recovery-warning marker (GREEN-2)."""
    audit_ports.seed_page(
        AuditPageV1(
            run_id="run-1",
            items=(
                audit_event(
                    1,
                    RecoveryPayloadV1(
                        kind="RECOVERY",
                        transaction_id="raw-request-sentinel",
                        disposition="UNRESOLVED",
                    ),
                ),
            ),
        )
    )
    response = audit_client.get(
        "/runs/run-1/audit", headers=valid_local_security_headers()
    )
    assert "处置：未解决" in response.text
    assert "recovery-warning" in response.text
    assert "raw-request-sentinel" not in response.text


def test_audit_clear_requires_explicit_confirmation(
    audit_client: TestClient,
    audit_ports: SpyAuditPorts,
    audit_identity: FixedAuditIdentityPortV1,
) -> None:
    """The clear route accepts only the literal confirmation and binds
    the server-controlled event into the closed Task 23.C command; any
    other field rejects before the clear call (GREEN-1/GREEN-2)."""
    response = audit_client.post(
        "/runs/run-1/audit/clear",
        headers=valid_local_security_headers(),
        data={},
    )
    assert response.status_code == 422
    assert audit_ports.clear_call_count == 0

    response = audit_client.post(
        "/runs/run-1/audit/clear",
        headers=valid_local_security_headers(),
        data={"confirm": "yes", "force": "1"},
    )
    assert response.status_code == 422
    assert audit_ports.clear_call_count == 0

    response = audit_client.post(
        "/runs/run-1/audit/clear",
        headers=valid_local_security_headers(),
        data={"confirm": "yes"},
    )
    assert response.status_code == 200
    assert audit_ports.clear_call_count == 1
    command = audit_ports.clear_commands[0]
    assert command.run_id == "run-1"
    assert command.event_id == "audit-event-1"
    assert command.decided_at == _FIXED_NOW


def test_audit_rejected_clear_renders_real_page_with_error(
    audit_client: TestClient,
    audit_ports: SpyAuditPorts,
) -> None:
    """A rejected/unsafe clear never claims success; the real page
    re-renders with the bounded error (Boundary)."""
    audit_ports.seed_page(
        AuditPageV1(
            run_id="run-1",
            items=(
                audit_event(
                    1, LifecyclePayloadV1(kind="LIFECYCLE", status="SUCCEEDED")
                ),
            ),
        )
    )
    audit_ports.seed_clear_result(
        AuditClearResultV1(
            kind="REJECTED",
            message="only ended runs can be cleared",
            error_code="AUDIT_STORE_FAILED",
        )
    )
    response = audit_client.post(
        "/runs/run-1/audit/clear",
        headers=valid_local_security_headers(),
        data={"confirm": "yes"},
    )
    assert response.status_code == 200
    assert audit_ports.clear_call_count == 1
    assert "only ended runs can be cleared" in response.text
    assert "状态：成功" in response.text
    assert "raw-request-sentinel" not in response.text
    assert "backup-body-sentinel" not in response.text


def test_audit_page_renders_retention_state(
    audit_client: TestClient,
    audit_ports: SpyAuditPorts,
) -> None:
    """The page renders the retention state (SPEC §4.7/§5.6)."""
    response = audit_client.get(
        "/runs/run-1/audit", headers=valid_local_security_headers()
    )
    assert "审计默认保留 30 天" in response.text


def test_audit_page_escapes_hostile_run_id(
    audit_client: TestClient,
    audit_ports: SpyAuditPorts,
) -> None:
    """A hostile Run id renders as escaped text, never executable markup
    (GREEN-2/SPEC §4.9; escape-test run ids must be slash-free per the
    T29.1 lesson, so the hostile id carries no ``/``)."""
    audit_ports.seed_page(
        AuditPageV1(
            run_id="<em>hostile",
            items=(),
        )
    )
    response = audit_client.get(
        "/runs/%3Cem%3Ehostile/audit",
        headers=valid_local_security_headers(),
    )
    assert response.status_code == 200
    assert "<em>hostile" not in response.text
    assert "&lt;em&gt;hostile" in response.text


def test_audit_route_is_loopback_security_bound(
    audit_client: TestClient,
    audit_ports: SpyAuditPorts,
    security_config: LocalWebSecurityConfigV1,
) -> None:
    """The Task 28.A fixed-order rejections fire before any domain call."""
    no_session = TestClient(audit_client.app, base_url="http://127.0.0.1:8765")
    response = no_session.get("/runs/run-1/audit", headers={"Host": "127.0.0.1:8765"})
    assert response.status_code == 401
    assert audit_ports.list_call_count == 0

    no_csrf = TestClient(audit_client.app, base_url="http://127.0.0.1:8765")
    no_csrf.cookies.set(security_config.session_cookie_name, "f" * 64)
    response = no_csrf.post(
        "/runs/run-1/audit/clear",
        headers={"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"},
        data={"confirm": "yes"},
    )
    assert response.status_code == 403
    assert audit_ports.clear_call_count == 0
