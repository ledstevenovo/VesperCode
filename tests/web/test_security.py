"""T28.1 legacy step 28.A: loopback request-security boundary tests.

The exact RED pins the smallest pre-domain Origin rejection; the matrix
pins the exact fixed-order boundary (HOST -> SESSION -> ORIGIN -> CSRF
for state changes) with stable rejections, the exact CSP/response
security headers, and zero spy route-domain calls after every rejection
(SPEC §4.9 local mode and tests, §5.3, §5.5 WebUI threat; Registry row
28.A Expected line: binding, session, Host/Origin/CSRF and headers fail
before all spy domain calls).
"""

from __future__ import annotations

from typing import Any, cast

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.vespercode.canonical.clock import FakeClockV1
from src.vespercode.web.security import (
    LocalRequestErrorCodeV1,
    LocalSessionErrorV1,
    LocalSessionManager,
    LocalSessionV1,
    LocalWebSecurityConfigV1,
    is_loopback_host,
    local_request_rejection_payload,
    local_request_status,
    local_response_security_headers,
    verify_local_request,
)

_EPOCH_MS = 1_783_500_000_000
"""One fixed deterministic instant for the injectable fake clock."""

_EXPECTED_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
    "form-action 'self'"
)
"""The exact CSP the matrix pins on every response."""


def valid_run_form_data() -> dict[str, str]:
    """One valid run-creation form body (route-domain data; the security
    boundary must not care about its content)."""
    return {"target": "tests/web"}


class _SpyDomainPorts:
    """Records every route-domain call (the matrix pins zero calls after
    every rejection)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def record(self, method: str, origin: str) -> None:
        self.calls.append((method, origin))


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
    config: LocalWebSecurityConfigV1,
    manager: LocalSessionManager,
    spy: _SpyDomainPorts,
) -> FastAPI:
    """One minimal loopback app mirroring the production composition.

    The security envelope mirrors the middleware wiring of Task 28.B's
    ``create_local_app``: Host first, session resolution through the
    bounded manager, then ``verify_local_request`` (HOST -> SESSION ->
    ORIGIN -> CSRF) before the route-domain call, and the exact security
    headers on every response.
    """
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.security_config = config
    app.state.session_manager = manager
    app.state.spy = spy
    app.state.test_clock = manager.clock

    @app.middleware("http")
    async def _local_security_middleware(request: Request, call_next: Any) -> Any:
        assert isinstance(
            request, Request
        )  # the runtime contract is a starlette Request
        if not is_loopback_host(request.headers.get("host", "")):
            return _rejection_response("HOST_REJECTED")
        if request.url.path.startswith("/static/"):
            return await call_next(request)
        cookie_value = request.cookies.get(config.session_cookie_name)
        if cookie_value is None:
            if request.method in ("GET", "HEAD") and request.url.path == "/":
                # Bootstrap one bounded local session on the first home
                # visit and set its cookie on the response.
                bootstrap_session = manager.create()
                request.state.local_session = bootstrap_session
                response = await call_next(request)
                response.set_cookie(
                    config.session_cookie_name,
                    bootstrap_session.session_id,
                    httponly=True,
                    samesite="strict",
                    max_age=manager.session_ttl_seconds,
                    path="/",
                )
                for name, value in local_response_security_headers().items():
                    response.headers[name] = value
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
        for name, value in local_response_security_headers().items():
            response.headers[name] = value
        return response

    @app.get("/")
    def home(request: Request) -> JSONResponse:
        """Render the home response for the middleware-resolved session."""
        session: LocalSessionV1 = request.state.local_session
        return JSONResponse({"status": "ready", "session_id": session.session_id})

    @app.post("/runs")
    def create_run(request: Request) -> dict[str, str]:
        """One spy route-domain call (must never run after a rejection)."""
        spy.record("POST", request.headers.get("origin", ""))
        return {"status": "created"}

    @app.post("/deny")
    def deny_run() -> JSONResponse:
        """One downstream DENY-style rejection: the security headers must
        attach without weakening its status or body (GREEN-2)."""
        return JSONResponse(status_code=403, content={"error_code": "POLICY_DENY"})

    return app


@pytest.fixture
def security_config() -> LocalWebSecurityConfigV1:
    return LocalWebSecurityConfigV1(
        host="127.0.0.1",
        port=8765,
        session_cookie_name="vespercode_session",
        csrf_header_name="X-CSRF-Token",
    )


@pytest.fixture
def local_web_client(security_config: LocalWebSecurityConfigV1) -> TestClient:
    manager = LocalSessionManager(
        security_config, clock=FakeClockV1.from_epoch_milliseconds(_EPOCH_MS)
    )
    spy = _SpyDomainPorts()
    app = _build_local_app(security_config, manager, spy)
    return TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")


@pytest.fixture
def valid_csrf_headers(
    local_web_client: TestClient, security_config: LocalWebSecurityConfigV1
) -> dict[str, str]:
    """One valid CSRF header for the session the client carries."""
    local_web_client.get("/")
    session_id = local_web_client.cookies.get(security_config.session_cookie_name)
    assert session_id is not None
    manager: LocalSessionManager = cast(
        FastAPI, local_web_client.app
    ).state.session_manager
    session = manager.get(session_id)
    assert session is not None
    return {security_config.csrf_header_name: session.csrf_token}


def test_state_change_rejects_non_loopback_origin(
    local_web_client: TestClient,
    valid_csrf_headers: dict[str, str],
) -> None:
    response = local_web_client.post(
        "/runs",
        headers={**valid_csrf_headers, "Origin": "https://attacker.example"},
        data=valid_run_form_data(),
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "ORIGIN_REJECTED"


def test_web_request_security_matrix(
    local_web_client: TestClient,
    security_config: LocalWebSecurityConfigV1,
) -> None:
    """The exact fixed-order loopback security matrix (Expected 28.A).

    Binding, session, Host/Origin/CSRF, and the security headers all fail
    before any spy domain call; the one fully valid state change runs the
    route-domain call exactly once; the first failing check in the fixed
    order always wins; and the headers never weaken a downstream DENY.
    """
    client = local_web_client
    app = cast(FastAPI, client.app)
    manager: LocalSessionManager = app.state.session_manager
    spy: _SpyDomainPorts = app.state.spy
    fake_clock: FakeClockV1 = app.state.test_clock
    base_origin = f"http://127.0.0.1:{security_config.port}"

    # --- one valid session: bootstrap through the home route ---
    home = client.get("/")
    assert home.status_code == 200
    assert "vespercode_session" in client.cookies
    # the session cookie carries the defense-in-depth security attributes
    set_cookie = home.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie
    assert "SameSite=strict" in set_cookie
    assert "Max-Age=28800" in set_cookie
    session_id = client.cookies.get(security_config.session_cookie_name)
    assert session_id is not None
    session = manager.get(session_id)
    assert session is not None and manager.is_active(session)
    csrf_headers = {security_config.csrf_header_name: session.csrf_token}
    valid_origin = {"Origin": base_origin}
    # bounded session shape: 256-bit tokens and the exact 8-hour TTL
    assert len(session.session_id) == 64
    assert len(session.csrf_token) == 64
    assert (
        session.expires_at.epoch_milliseconds - session.created_at.epoch_milliseconds
        == 8 * 60 * 60 * 1000
    )
    assert session.session_cookie_name == security_config.session_cookie_name
    assert session.csrf_header_name == security_config.csrf_header_name

    # --- the one fully valid state change runs the domain call exactly once ---
    response = client.post(
        "/runs",
        headers={**valid_origin, **csrf_headers},
        data=valid_run_form_data(),
    )
    assert response.status_code == 200
    assert response.json() == {"status": "created"}
    assert spy.calls == [("POST", base_origin)]

    # --- Host checks (first in the fixed order) ---
    _assert_rejected(client, "HOST_REJECTED", 403, headers={"Host": "evil.example"})
    _assert_rejected(client, "HOST_REJECTED", 403, headers={"Host": "[::1]:8765"})
    _assert_rejected(client, "HOST_REJECTED", 403, headers={"Host": ""})
    assert not is_loopback_host("0.0.0.0:8765")
    assert not is_loopback_host("127.0.0.1.evil.example")
    assert not is_loopback_host("127.0.0.1:99999")  # out-of-range port syntax
    assert not is_loopback_host("127.0.0.1:0")
    assert is_loopback_host("127.0.0.1:8765")
    assert is_loopback_host("localhost")
    assert is_loopback_host("127.0.0.1")
    assert spy.calls == [("POST", base_origin)]

    # --- session checks (second in the fixed order) ---
    no_cookie_client = TestClient(
        app, base_url=f"http://127.0.0.1:{security_config.port}"
    )
    _assert_rejected(no_cookie_client, "SESSION_MISSING", 401, headers=csrf_headers)
    invalid_cookie_client = TestClient(
        app, base_url=f"http://127.0.0.1:{security_config.port}"
    )
    invalid_cookie_client.cookies.set(
        security_config.session_cookie_name, "deadbeef" * 8
    )
    _assert_rejected(
        invalid_cookie_client,
        "SESSION_INVALID",
        401,
        headers={**valid_origin, **csrf_headers},
    )

    # --- Origin checks (third; state changes only) ---
    _assert_rejected(client, "ORIGIN_MISSING", 403, headers=csrf_headers)
    _assert_rejected(
        client,
        "ORIGIN_REJECTED",
        403,
        headers={**csrf_headers, "Origin": "https://127.0.0.1:8765"},
    )
    _assert_rejected(
        client,
        "ORIGIN_REJECTED",
        403,
        headers={**csrf_headers, "Origin": "http://127.0.0.1:9999"},
    )
    _assert_rejected(
        client,
        "ORIGIN_REJECTED",
        403,
        headers={**csrf_headers, "Origin": "http://localhost:8765"},
    )
    _assert_rejected(
        client,
        "ORIGIN_REJECTED",
        403,
        headers={**csrf_headers, "Origin": "http://127.0.0.1:8765.evil.example"},
    )
    _assert_rejected(
        client,
        "ORIGIN_REJECTED",
        403,
        headers={**csrf_headers, "Origin": "ftp://127.0.0.1:8765"},
    )

    # --- CSRF checks (fourth; state changes only) ---
    _assert_rejected(
        client,
        "CSRF_REJECTED",
        403,
        headers={**valid_origin, security_config.csrf_header_name: "wrong"},
    )
    _assert_rejected(client, "CSRF_REJECTED", 403, headers=valid_origin)

    # --- the localhost loopback path is a fully valid flow: Host
    # ``localhost:8765`` with the matching Origin is accepted ---
    localhost_ok = client.post(
        "/runs",
        headers={
            "Host": "localhost:8765",
            "Origin": "http://localhost:8765",
            **csrf_headers,
        },
        data=valid_run_form_data(),
    )
    assert localhost_ok.status_code == 200
    assert spy.calls == [("POST", base_origin), ("POST", "http://localhost:8765")]

    # --- safe reads never require Origin/CSRF and still verify ---
    safe = client.get("/")
    assert safe.status_code == 200
    assert spy.calls == [("POST", base_origin), ("POST", "http://localhost:8765")]

    # --- fixed-order pins: the first failing check always wins ---
    _assert_rejected(
        client,
        "HOST_REJECTED",
        403,
        headers={**valid_origin, **csrf_headers, "Host": "evil.example"},
    )
    _assert_rejected(
        client,
        "ORIGIN_REJECTED",
        403,
        headers={
            **valid_origin,
            **csrf_headers,
            "Origin": "http://127.0.0.1:9999",
            security_config.csrf_header_name: "wrong",
        },
    )
    order_invalid_cookie_client = TestClient(
        app, base_url=f"http://127.0.0.1:{security_config.port}"
    )
    order_invalid_cookie_client.cookies.set(
        security_config.session_cookie_name, "deadbeef" * 8
    )
    _assert_rejected(
        order_invalid_cookie_client,
        "SESSION_INVALID",
        401,
        headers={
            **valid_origin,
            **csrf_headers,
            "Origin": "http://127.0.0.1:9999",
            security_config.csrf_header_name: "wrong",
        },
    )

    # --- the exact CSP and security headers on every response ---
    assert response.headers["content-security-policy"] == _EXPECTED_CSP
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    for code in ("HOST_REJECTED", "ORIGIN_MISSING", "CSRF_REJECTED"):
        payload = local_request_rejection_payload(code)
        assert set(payload) == {"error_code", "message", "next_step"}
        assert payload["error_code"] == code
        assert local_request_status(code) in (401, 403)
    assert local_request_status("SESSION_MISSING") == 401
    assert local_request_status("ORIGIN_REJECTED") == 403

    # --- the headers never weaken a downstream DENY ---
    denied = client.post(
        "/deny",
        headers={**valid_origin, **csrf_headers},
        data=valid_run_form_data(),
    )
    assert denied.status_code == 403
    assert denied.json() == {"error_code": "POLICY_DENY"}
    assert denied.headers["x-frame-options"] == "DENY"
    assert spy.calls == [("POST", base_origin), ("POST", "http://localhost:8765")]

    # --- binding is closed to the literal loopback host ---
    non_loopback_host: Any = "0.0.0.0"
    with pytest.raises(ValidationError):
        LocalWebSecurityConfigV1(
            host=non_loopback_host,
            port=8765,
            session_cookie_name="s",
            csrf_header_name="h",
        )
    with pytest.raises(ValidationError):
        LocalWebSecurityConfigV1(
            host="127.0.0.1",
            port=0,
            session_cookie_name="s",
            csrf_header_name="h",
        )
    with pytest.raises(ValidationError):
        LocalWebSecurityConfigV1(
            host="127.0.0.1",
            port=65536,
            session_cookie_name="s",
            csrf_header_name="h",
        )

    # --- bounded local sessions: entropy, TTL, concurrency, pruning ---
    bounded_clock = FakeClockV1.from_epoch_milliseconds(_EPOCH_MS)
    bounded = LocalSessionManager(
        security_config,
        session_ttl_milliseconds=60_000,
        max_sessions=2,
        clock=bounded_clock,
    )
    first = bounded.create()
    second = bounded.create()
    assert len(first.session_id) == 64
    assert first.session_id != second.session_id
    assert first.csrf_token != first.session_id
    with pytest.raises(LocalSessionErrorV1, match="limit"):
        bounded.create()
    bounded_clock.advance(60_000 + 1)
    assert not bounded.is_active(first)
    assert not bounded.is_active(second)
    third = bounded.create()  # expired sessions are pruned before the bound
    assert bounded.is_active(third)
    assert len(bounded) == 1

    # --- expired session is rejected before any domain call ---
    expired_client = TestClient(
        app, base_url=f"http://127.0.0.1:{security_config.port}"
    )
    expired_client.cookies.set(security_config.session_cookie_name, session.session_id)
    fake_clock.advance(8 * 60 * 60 * 1000 + 1)
    assert not manager.is_active(session)
    _assert_rejected(
        expired_client,
        "SESSION_EXPIRED",
        401,
        headers={**valid_origin, **csrf_headers},
    )
    assert spy.calls == [("POST", base_origin), ("POST", "http://localhost:8765")]


def _assert_rejected(
    client: TestClient,
    error_code: str,
    status_code: int,
    *,
    headers: dict[str, str],
) -> None:
    """One rejection pin: exact status and closed code, zero domain calls."""
    spy: _SpyDomainPorts = cast(FastAPI, client.app).state.spy
    before = len(spy.calls)
    response = client.post("/runs", headers=headers, data=valid_run_form_data())
    assert response.status_code == status_code
    assert response.json()["error_code"] == error_code
    assert len(spy.calls) == before
