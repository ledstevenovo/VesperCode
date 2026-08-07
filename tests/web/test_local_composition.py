"""T38.2 legacy step 38.F: final local operations and production route
composition tests.

The exact RED pins the frozen production installer tuple: exactly
``RunGovernanceRouteInstallerV1`` followed by
``LocalOperationsRouteInstallerV1`` (GREEN-3).  At RED time the fixture
holds a local ``build_local_route_installers`` that returns the empty
tuple, so the card test reaches its first task-owned assertion and
fails; at GREEN the same fixture imports the real composition over the
spy ports (the T29.1 holder-shell precedent).

The domain pins cover the typed installer tuple order, the exact
governance-then-operations composition, the four operations route
surfaces through the real ``build_local_application``, the preserved
Task 28.A security boundary, and the absence of alternate composition
paths.
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

from src.vespercode.audit.repository import (
    AuditClearResultV1,
    AuditPageRequestV1,
    AuditPageV1,
    ClearEndedRunAuditV1,
)
from src.vespercode.contracts.optional import AbsentV1
from src.vespercode.credentials.port import CredentialStatusV1
from src.vespercode.memory.clear import MemoryClearResultV1
from src.vespercode.memory.entry import MemoryEntryV1, MemoryMutationResultV1
from src.vespercode.persistence.recovery_apply import RecoveryResultV1
from src.vespercode.persistence.recovery_preview import (
    RecoveryPathClassificationEntryV1,
    RecoveryPreviewV1,
)
from src.vespercode.web.app import (
    LocalRouteInstallerSequenceV1,
    RunVisibilitySequenceV1,
)
from src.vespercode.web.local_composition import (
    ProductionLocalWorkflowPortsV1,
    build_local_route_installers,
)
from src.vespercode.web.security import LocalWebSecurityConfigV1

_FIXED_TOKEN: Final[str] = "f" * 64
"""One deterministic 256-bit hex session/CSRF token (closed token form)."""

_MIRROR_NONCE: Final[str] = "test-nonce-1234567890"
"""One deterministic closed CSP nonce form for the test-local mirror."""

_FIXED_NOW = "2026-08-07T09:00:00.000Z"


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


def _rejection_response(error_code: str) -> JSONResponse:
    """One closed rejection response carrying the exact security headers."""
    from src.vespercode.web.security import (
        local_request_rejection_payload,
        local_request_status,
        local_response_security_headers,
    )

    payload = local_request_rejection_payload(error_code)  # type: ignore[arg-type]
    response = JSONResponse(
        status_code=local_request_status(error_code),  # type: ignore[arg-type]
        content=payload,
    )
    for name, value in local_response_security_headers().items():
        response.headers[name] = value
    return response


def _attach_headers(response: Any, csp_nonce: str | None) -> None:
    """Attach the exact CSP and response security headers to one response."""
    from src.vespercode.web.security import local_response_security_headers

    for name, value in local_response_security_headers(csp_nonce).items():
        response.headers[name] = value


class FakeShellPortsV1:
    """One fake typed shell port implementation (test-owned)."""

    def list_recent_runs(self) -> RunVisibilitySequenceV1:
        return ()

    def credential_status(self) -> CredentialStatusV1:
        return CredentialStatusV1(
            schema_version=1,
            provider="OPENAI",
            configured=False,
            updated_at=AbsentV1(kind="ABSENT"),
        )


class SpyCredentialPorts:
    """One minimal credential workflow-port spy (status page only)."""

    def __init__(self) -> None:
        self.status_call_count = 0

    def set(self, provider: str, secret: Any, event_id: str) -> Any:
        raise AssertionError("composition tests never mutate credentials")

    def status(self, provider: str) -> CredentialStatusV1:
        self.status_call_count += 1
        return CredentialStatusV1(
            schema_version=1,
            provider="OPENAI",
            configured=False,
            updated_at=AbsentV1(kind="ABSENT"),
        )

    def update(self, provider: str, secret: Any, event_id: str) -> Any:
        raise AssertionError("composition tests never mutate credentials")

    def clear(self, provider: str, event_id: str) -> Any:
        raise AssertionError("composition tests never mutate credentials")


class SpyMemoryPorts:
    """One minimal memory workflow-port spy (list only)."""

    def __init__(self) -> None:
        self.list_call_count = 0

    def list(self, run_id: str) -> tuple[MemoryEntryV1, ...]:
        self.list_call_count += 1
        return ()

    def create(self, command: Any) -> MemoryMutationResultV1:
        raise AssertionError("composition tests never mutate memory")

    def confirm(self, command: Any) -> MemoryMutationResultV1:
        raise AssertionError("composition tests never mutate memory")

    def clear(self, command: Any) -> MemoryClearResultV1:
        raise AssertionError("composition tests never mutate memory")


class SpyAuditPorts:
    """One minimal audit workflow-port spy (page + clear state only)."""

    def __init__(self) -> None:
        self.list_call_count = 0

    def list_run(self, run_id: str, page: AuditPageRequestV1) -> AuditPageV1:
        self.list_call_count += 1
        return AuditPageV1(run_id=run_id, items=())

    def clear_ended_run(self, command: ClearEndedRunAuditV1) -> AuditClearResultV1:
        raise AssertionError("composition tests never clear audit")

    def clear_state_for(self, run_id: str) -> Any:
        from src.vespercode.web.routes_audit import AuditClearStateV1

        return AuditClearStateV1(
            run_id=run_id, run_ended=True, has_unresolved_recovery=False
        )


class SpyRecoveryPorts:
    """One minimal recovery workflow-port spy (preview only)."""

    def __init__(self) -> None:
        self.preview_call_count = 0

    def preview(self, run_id: str) -> RecoveryPreviewV1:
        self.preview_call_count += 1
        return RecoveryPreviewV1(
            schema_version=1,
            transaction_id="tx-1",
            disposition="ROLLED_BACK",
            path_classifications=(
                RecoveryPathClassificationEntryV1(
                    schema_version=1, path="src/a.py", classification="POSTIMAGE"
                ),
            ),
            observations=(),
            preview_digest="preview-digest-1",
            workspace_write_count=0,
        )

    def apply(self, command: Any) -> RecoveryResultV1:
        raise AssertionError("composition tests never apply recovery")


class _EmptyGovernancePorts:
    """One dummy Milestone 29 governance aggregate (never called)."""


def _production_ports() -> ProductionLocalWorkflowPortsV1:
    """One fake production port aggregate over the spy ports."""
    from src.vespercode.web.routes_operations import (
        LocalOperationsWorkflowPortsV1,
    )
    from src.vespercode.web.run_workflows import RunGovernanceWorkflowPortsV1
    from typing import cast

    return ProductionLocalWorkflowPortsV1(
        shell=FakeShellPortsV1(),
        governance=RunGovernanceWorkflowPortsV1(
            run_lifecycle=cast(Any, _EmptyGovernancePorts()),
            disclosure=cast(Any, _EmptyGovernancePorts()),
            final_writeback=cast(Any, _EmptyGovernancePorts()),
        ),
        operations=LocalOperationsWorkflowPortsV1(
            credentials=SpyCredentialPorts(),
            memory=SpyMemoryPorts(),
            audit=SpyAuditPorts(),
            recovery=SpyRecoveryPorts(),
        ),
    )


def _build_local_app(
    security_config: LocalWebSecurityConfigV1,
    installers: LocalRouteInstallerSequenceV1,
) -> tuple[FastAPI, Any]:
    """One test-local shell mirroring the Task 28.B composition."""
    from src.vespercode.web.security import (
        LocalSessionManager,
        is_loopback_host,
        verify_local_request,
    )

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


@pytest.fixture
def security_config() -> LocalWebSecurityConfigV1:
    return LocalWebSecurityConfigV1(
        host="127.0.0.1",
        port=8765,
        session_cookie_name="vespercode_session",
        csrf_header_name="X-CSRF-Token",
    )


@pytest.fixture
def production_ports() -> ProductionLocalWorkflowPortsV1:
    """One fake production port aggregate over the spy ports."""
    return _production_ports()


def test_production_installer_tuple_has_exact_order(
    production_ports: ProductionLocalWorkflowPortsV1,
) -> None:
    installers = build_local_route_installers(production_ports)
    assert tuple(type(item).__name__ for item in installers) == (
        "RunGovernanceRouteInstallerV1",
        "LocalOperationsRouteInstallerV1",
    )


def test_build_local_application_composes_governance_then_operations(
    security_config: LocalWebSecurityConfigV1,
    production_ports: Any,
) -> None:
    """The production app carries the exact frozen installer tuple and
    serves the governance pages through the real Task 28.B composition
    (GREEN-2/GREEN-3)."""
    from src.vespercode.web.local_composition import build_local_application

    app = build_local_application(production_ports, security_config)
    installers = app.state.local_route_installers
    assert tuple(type(item).__name__ for item in installers) == (
        "RunGovernanceRouteInstallerV1",
        "LocalOperationsRouteInstallerV1",
    )
    client = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")
    home = client.get("/", headers={"Host": f"127.0.0.1:{security_config.port}"})
    assert home.status_code == 200
    create = client.get(
        "/runs/new", headers={"Host": f"127.0.0.1:{security_config.port}"}
    )
    assert create.status_code == 200
    assert "创建运行" in create.text


def test_build_local_application_installs_all_operations_routes(
    security_config: LocalWebSecurityConfigV1,
    production_ports: Any,
) -> None:
    """All four operations route families are installed and reachable
    through the production app (GREEN-2)."""
    from src.vespercode.web.local_composition import build_local_application

    app = build_local_application(production_ports, security_config)
    client = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")
    host = {"Host": f"127.0.0.1:{security_config.port}"}
    assert client.get("/", headers=host).status_code == 200
    pages = (
        "/credentials/openai",
        "/runs/run-1/memory",
        "/runs/run-1/audit",
        "/runs/run-recovery/recovery",
    )
    for page in pages:
        response = client.get(page, headers=host)
        assert response.status_code == 200, page
    operations = production_ports.operations
    assert operations.credentials.status_call_count == 1
    assert operations.memory.list_call_count == 1
    assert operations.audit.list_call_count == 1
    assert operations.recovery.preview_call_count == 1


def test_build_local_application_keeps_loopback_security_boundary(
    security_config: LocalWebSecurityConfigV1,
    production_ports: Any,
) -> None:
    """The Task 28.A boundary still rejects non-loopback requests on the
    composed production app (GREEN-1)."""
    from src.vespercode.web.local_composition import build_local_application

    app = build_local_application(production_ports, security_config)
    client = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")
    response = client.get("/", headers={"Host": "evil.example"})
    assert response.status_code == 403
    assert response.json()["error_code"] == "HOST_REJECTED"


def test_local_operations_installer_installs_all_four_families(
    security_config: LocalWebSecurityConfigV1,
    production_ports: Any,
) -> None:
    """``LocalOperationsRouteInstallerV1`` installs exactly the
    credential, memory, audit, and recovery route families onto one app
    (GREEN-2)."""
    from src.vespercode.web.routes_operations import (
        LocalOperationsRouteInstallerV1,
    )

    app, _ = _build_local_app(
        security_config,
        (LocalOperationsRouteInstallerV1(production_ports.operations),),
    )
    client = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")
    session = app.state.local_session_manager.create()
    client.cookies.set(security_config.session_cookie_name, session.session_id)
    host = {"Host": f"127.0.0.1:{security_config.port}"}
    for page in (
        "/credentials/openai",
        "/runs/run-1/memory",
        "/runs/run-1/audit",
        "/runs/run-recovery/recovery",
    ):
        response = client.get(page, headers=host)
        assert response.status_code == 200, page
