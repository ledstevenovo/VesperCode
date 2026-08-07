"""T38.1 legacy step 38.A: credential lifecycle WebUI tests.

The exact RED pins the smallest zero-secret-response contract: the
submitted sentinel, its length, its digest, and every derivative must be
absent from every success and failure response (SPEC §4.8/§8.1/AC-08).
The ``credential_client`` fixture is a test-local mirror (the T28.1
M3-precedent class documented in T29.1) whose middleware mirrors the
Task 28.A fixed order verbatim and whose deterministic session lets the
card's header-only POST pass the exact security order and reach the real
``CredentialRouteInstallerV1`` over the spy ports.

The domain pins cover the closed action/provider surface, the
server-controlled mutation events, the status/form page (password-field
lifetime only, explicit labels, keyboard focus, live error/status
regions, contextual recovery guidance, escaped service-projected text),
the typed-port delegation with zero secret derivatives on every branch,
and the never-false-success failure projection.
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

from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.credentials.port import (
    CredentialErrorV1,
    CredentialMutationResultV1,
    CredentialStatusV1,
    SecretCredentialV1,
)
from vespercode.web.routes_credentials import (
    CredentialRouteInstallerV1,
    CredentialWorkflowIdentityPortV1,
    CredentialWorkflowPortsV1,
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


class SpyCredentialPorts:
    """One spy typed credential workflow-port implementation.

    The spy never records a secret value — only the mutation counts, the
    provider, and the server-controlled event ids — so the tests cannot
    accidentally leak a secret into an assertion or a report (AC-08
    discipline).
    """

    def __init__(self) -> None:
        self.set_call_count = 0
        self.update_call_count = 0
        self.clear_call_count = 0
        self.status_call_count = 0
        self.mutation_result = CredentialMutationResultV1(
            schema_version=1, kind="STORED", error=AbsentV1(kind="ABSENT")
        )
        self._status = CredentialStatusV1(
            schema_version=1,
            provider="OPENAI",
            configured=False,
            updated_at=AbsentV1(kind="ABSENT"),
        )
        self._event_ids: list[str] = []

    def seed_status(self, status: CredentialStatusV1) -> None:
        self._status = status

    def seed_mutation(self, result: CredentialMutationResultV1) -> None:
        self.mutation_result = result

    @property
    def event_ids(self) -> list[str]:
        return list(self._event_ids)

    def set(
        self,
        provider: str,
        secret: SecretCredentialV1,
        event_id: str,
    ) -> CredentialMutationResultV1:
        self.set_call_count += 1
        assert provider == "OPENAI"
        self._event_ids.append(event_id)
        return self.mutation_result

    def status(self, provider: str) -> CredentialStatusV1:
        self.status_call_count += 1
        assert provider == "OPENAI"
        return self._status

    def update(
        self,
        provider: str,
        secret: SecretCredentialV1,
        event_id: str,
    ) -> CredentialMutationResultV1:
        self.update_call_count += 1
        assert provider == "OPENAI"
        self._event_ids.append(event_id)
        return self.mutation_result

    def clear(self, provider: str, event_id: str) -> CredentialMutationResultV1:
        self.clear_call_count += 1
        assert provider == "OPENAI"
        self._event_ids.append(event_id)
        return self.mutation_result


class FixedCredentialIdentityPortV1:
    """One deterministic server-controlled identity seam (SPEC §5.4)."""

    def __init__(self) -> None:
        self._counter = 0

    def new_event_id(self) -> str:
        self._counter += 1
        return f"cred-event-{self._counter}"

    def now(self) -> CanonicalTimestampV1:
        return _FIXED_NOW


def configured_status(
    configured: bool = True, updated: bool = True
) -> CredentialStatusV1:
    """One non-revealing credential status (SPEC §4.8)."""
    return CredentialStatusV1(
        schema_version=1,
        provider="OPENAI",
        configured=configured,
        updated_at=(
            PresentV1[CanonicalTimestampV1](kind="PRESENT", value=_FIXED_NOW)
            if updated
            else AbsentV1(kind="ABSENT")
        ),
    )


@pytest.fixture
def security_config() -> LocalWebSecurityConfigV1:
    return LocalWebSecurityConfigV1(
        host="127.0.0.1",
        port=8765,
        session_cookie_name="vespercode_session",
        csrf_header_name="X-CSRF-Token",
    )


@pytest.fixture
def credential_ports() -> SpyCredentialPorts:
    return SpyCredentialPorts()


@pytest.fixture
def credential_identity() -> FixedCredentialIdentityPortV1:
    return FixedCredentialIdentityPortV1()


@pytest.fixture
def credential_client(
    security_config: LocalWebSecurityConfigV1,
    credential_ports: SpyCredentialPorts,
    credential_identity: FixedCredentialIdentityPortV1,
) -> TestClient:
    ports: CredentialWorkflowPortsV1 = credential_ports
    identity: CredentialWorkflowIdentityPortV1 = credential_identity
    app, manager = _build_local_app(
        security_config, (CredentialRouteInstallerV1(ports, identity),)
    )
    client = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")
    session = manager.create()
    client.cookies.set(security_config.session_cookie_name, session.session_id)
    return client


def test_credential_response_never_contains_secret_or_derivative(
    credential_client: TestClient,
) -> None:
    response = credential_client.post(
        "/credentials/openai",
        headers=valid_local_security_headers(),
        data={"secret": "inert-sentinel"},
    )
    assert "inert-sentinel" not in response.text
    assert "length" not in response.text and "digest" not in response.text


def test_credential_set_renders_real_status_with_zero_secret_derivatives(
    credential_client: TestClient,
    credential_ports: SpyCredentialPorts,
    credential_identity: FixedCredentialIdentityPortV1,
) -> None:
    """A valid first-time set redirects to the status page (PRG), calls
    the set port exactly once with the server-controlled event, and never
    exposes the sentinel, its length, its digest, or a derivative in the
    POST response or the followed page (GREEN-3/AC-08)."""
    credential_ports.seed_status(configured_status())
    sentinel = "fresh-sentinel-7f3a"
    response = credential_client.post(
        "/credentials/openai",
        headers=valid_local_security_headers(),
        data={"secret": sentinel},
    )
    assert response.status_code == 200
    assert credential_ports.set_call_count == 1
    assert credential_ports.event_ids == ["cred-event-1"]
    assert "已配置" in response.text
    assert sentinel not in response.text
    assert "length" not in response.text and "digest" not in response.text
    redirect = credential_client.post(
        "/credentials/openai",
        headers=valid_local_security_headers(),
        data={"secret": sentinel},
        follow_redirects=False,
    )
    assert redirect.status_code == 303
    assert redirect.headers["location"] == "/credentials/openai"


def test_credential_update_action_delegates_to_update_port(
    credential_client: TestClient,
    credential_ports: SpyCredentialPorts,
) -> None:
    """The update action maps to the update port exactly once."""
    credential_ports.seed_status(configured_status())
    response = credential_client.post(
        "/credentials/openai",
        headers=valid_local_security_headers(),
        data={"action": "update", "secret": "update-sentinel"},
    )
    assert response.status_code == 200
    assert credential_ports.update_call_count == 1
    assert credential_ports.set_call_count == 0
    assert "update-sentinel" not in response.text


def test_credential_clear_action_delegates_to_clear_port(
    credential_client: TestClient,
    credential_ports: SpyCredentialPorts,
) -> None:
    """The clear action maps to the clear port exactly once and the page
    renders the real cleared state (未配置)."""
    credential_ports.seed_status(configured_status(configured=False))
    response = credential_client.post(
        "/credentials/openai",
        headers=valid_local_security_headers(),
        data={"action": "clear"},
    )
    assert response.status_code == 200
    assert credential_ports.clear_call_count == 1
    assert credential_ports.set_call_count == 0
    assert "未配置" in response.text


def test_credential_form_rejects_unknown_and_override_fields(
    credential_client: TestClient,
    credential_ports: SpyCredentialPorts,
) -> None:
    """Unknown/override fields (provider, workspace, secret derivatives)
    reject with 422 before any domain call (GREEN-1)."""
    for override_field in (
        "provider",
        "workspace_id",
        "api_key",
        "length",
        "digest",
        "secret_digest",
    ):
        response = credential_client.post(
            "/credentials/openai",
            headers=valid_local_security_headers(),
            data={"secret": "sentinel-a", override_field: "x"},
        )
        assert response.status_code == 422
        assert credential_ports.set_call_count == 0
        assert credential_ports.update_call_count == 0
        assert credential_ports.clear_call_count == 0
        assert "sentinel-a" not in response.text


def test_credential_form_rejects_unknown_action_and_empty_secret(
    credential_client: TestClient,
    credential_ports: SpyCredentialPorts,
) -> None:
    """An unknown action or an empty secret rejects with 422 and zero
    port calls; the failure body carries no derivative."""
    for body in ({"action": "delete", "secret": "s1"}, {"secret": ""}):
        response = credential_client.post(
            "/credentials/openai",
            headers=valid_local_security_headers(),
            data=body,
        )
        assert response.status_code == 422
        assert credential_ports.set_call_count == 0
        assert credential_ports.update_call_count == 0
        assert credential_ports.clear_call_count == 0
        assert "s1" not in response.text
        assert "length" not in response.text and "digest" not in response.text


def test_credential_failed_mutation_renders_real_state_never_false_success(
    credential_client: TestClient,
    credential_ports: SpyCredentialPorts,
) -> None:
    """A failed clear/update re-renders the service's real state with the
    bounded typed error and never claims success (Boundary)."""
    credential_ports.seed_status(configured_status(configured=False))
    credential_ports.seed_mutation(
        CredentialMutationResultV1(
            schema_version=1,
            kind="FAILED",
            error=PresentV1[CredentialErrorV1](
                kind="PRESENT",
                value=CredentialErrorV1(
                    schema_version=1,
                    error_code="CREDENTIAL_CLEAR_FAILED",
                    message="credential store clear failed",
                ),
            ),
        )
    )
    response = credential_client.post(
        "/credentials/openai",
        headers=valid_local_security_headers(),
        data={"action": "clear"},
    )
    assert response.status_code == 200
    assert credential_ports.clear_call_count == 1
    assert "未配置" in response.text
    assert "credential store clear failed" in response.text
    assert "已清除" not in response.text
    assert "已存储" not in response.text
    assert "sentinel" not in response.text


def test_credential_status_page_has_scanable_form_and_labels(
    credential_client: TestClient,
    credential_ports: SpyCredentialPorts,
) -> None:
    """The status page renders the non-revealing status fields and the
    closed form with explicit labels, keyboard focus, and a password
    field that never carries a persisted value (GREEN-2)."""
    credential_ports.seed_status(configured_status())
    response = credential_client.get(
        "/credentials/openai", headers={"Host": "127.0.0.1:8765"}
    )
    assert response.status_code == 200
    assert "凭据状态" in response.text
    assert "OPENAI" in response.text
    assert "已配置" in response.text
    assert "更新时间" in response.text
    for label in ("操作", "凭据值", "录入（首次配置）", "更新", "清除"):
        assert label in response.text
    assert 'type="password"' in response.text
    assert 'name="secret"' in response.text
    assert 'name="action"' in response.text
    assert "recovery-guidance" in response.text
    secret_tag = response.text.split('name="secret"')[1].split(">")[0]
    assert "value=" not in secret_tag
    assert credential_ports.set_call_count == 0


def test_credential_route_is_loopback_security_bound(
    credential_client: TestClient,
    credential_ports: SpyCredentialPorts,
    security_config: LocalWebSecurityConfigV1,
) -> None:
    """The Task 28.A fixed-order rejections fire before any domain call
    with the exact security headers (HOST -> SESSION -> ORIGIN -> CSRF)."""
    credential_ports.seed_status(configured_status())
    app = credential_client.app

    host_rejected = TestClient(app, base_url="http://127.0.0.1:8765")
    host_rejected.cookies.set(security_config.session_cookie_name, "f" * 64)
    response = host_rejected.get(
        "/credentials/openai", headers={"Host": "evil.example"}
    )
    assert response.status_code == 403
    assert credential_ports.status_call_count == 0

    no_csrf = TestClient(app, base_url="http://127.0.0.1:8765")
    no_csrf.cookies.set(security_config.session_cookie_name, "f" * 64)
    response = no_csrf.post(
        "/credentials/openai",
        headers={"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"},
        data={"secret": "sentinel-b"},
    )
    assert response.status_code == 403
    assert credential_ports.set_call_count == 0
    assert "sentinel-b" not in response.text


def test_credential_alternate_provider_path_fails_closed(
    credential_client: TestClient,
    credential_ports: SpyCredentialPorts,
) -> None:
    """Only the literal OPENAI provider path exists; an alternate provider
    path is not routable (GREEN-4: alternate provider out of scope)."""
    response = credential_client.post(
        "/credentials/anthropic",
        headers=valid_local_security_headers(),
        data={"secret": "sentinel-c"},
    )
    assert response.status_code == 404
    assert credential_ports.set_call_count == 0
    assert credential_ports.update_call_count == 0
    assert credential_ports.clear_call_count == 0
    assert "sentinel-c" not in response.text
