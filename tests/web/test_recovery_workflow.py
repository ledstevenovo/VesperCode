"""T38.2 legacy step 38.D: read-only-first recovery WebUI tests.

The exact RED pins the smallest read-only contract: the preview path
must render with zero apply/write calls and no force/ignore bypass
control (SPEC §4.6/§5.3/AC-29).  The ``local_web_client`` fixture is a
test-local mirror (the T28.1 M3-precedent class documented in T29.1)
whose middleware mirrors the Task 28.A fixed order verbatim and whose
deterministic session lets the card's header-only GET pass the exact
security order and reach the real ``RecoveryRouteInstallerV1`` over the
spy ports.

The domain pins cover the full path/status/consequence preview, the
distinct explicit confirmation step, zero preview write, stable
unresolved blocking, the frozen apply binding, security, and
accessibility.
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

from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.persistence.recovery_apply import RecoveryResultV1
from src.vespercode.persistence.recovery_preview import (
    RecoveryDispositionV1,
    RecoveryPathClassificationEntryV1,
    RecoveryPathClassificationV1,
    RecoveryPreviewErrorV1,
    RecoveryPreviewV1,
)
from src.vespercode.web.routes_recovery import (
    ApplyRecoveryForRunV1,
    RecoveryRouteInstallerV1,
    RecoveryWorkflowIdentityPortV1,
    RecoveryWorkflowPortsV1,
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


def preview_payload(
    disposition: RecoveryDispositionV1 = "ROLLED_BACK",
    paths: tuple[tuple[str, RecoveryPathClassificationV1], ...] = (
        ("src/a.py", "POSTIMAGE"),
        ("src/b.py", "PREIMAGE"),
    ),
) -> RecoveryPreviewV1:
    """One immutable read-only recovery preview (SPEC 4.6)."""
    return RecoveryPreviewV1(
        schema_version=1,
        transaction_id="tx-1",
        disposition=disposition,
        path_classifications=tuple(
            RecoveryPathClassificationEntryV1(
                schema_version=1, path=path, classification=classification
            )
            for path, classification in paths
        ),
        observations=(),
        preview_digest="preview-digest-1",
        workspace_write_count=0,
    )


def rolled_back_result() -> RecoveryResultV1:
    """One closed service-proven ROLLED_BACK apply outcome."""
    return RecoveryResultV1(
        schema_version=1,
        transaction_id="tx-1",
        disposition="ROLLED_BACK",
        error_code=None,
        changed_paths=("src/a.py", "src/b.py"),
        evidence_digest="evidence-digest-1",
        workspace_write_count=2,
        message="recovery rolled back",
    )


class SpyLocalOperationsPorts:
    """One spy recovery workflow-port implementation.

    The spy exposes exactly the card RED's two counters
    (``recovery_apply_call_count``, ``workspace_write_count``) plus the
    preview/apply seams; it never touches a database or a workspace.
    """

    def __init__(self) -> None:
        self.recovery_apply_call_count = 0
        self.workspace_write_count = 0
        self.preview_call_count = 0
        self.preview_result = preview_payload()
        self.preview_error: RecoveryPreviewErrorV1 | None = None
        self.apply_result = rolled_back_result()
        self._apply_commands: list[ApplyRecoveryForRunV1] = []

    def seed_preview(self, preview: RecoveryPreviewV1) -> None:
        self.preview_result = preview

    def seed_preview_error(self, error: RecoveryPreviewErrorV1) -> None:
        self.preview_error = error

    def seed_apply_result(self, result: RecoveryResultV1) -> None:
        self.apply_result = result

    @property
    def apply_commands(self) -> list[ApplyRecoveryForRunV1]:
        return list(self._apply_commands)

    def preview(self, run_id: str) -> RecoveryPreviewV1:
        self.preview_call_count += 1
        if self.preview_error is not None:
            raise self.preview_error
        return self.preview_result

    def apply(self, command: ApplyRecoveryForRunV1) -> RecoveryResultV1:
        self.recovery_apply_call_count += 1
        self._apply_commands.append(command)
        self.workspace_write_count = self.apply_result.workspace_write_count
        return self.apply_result


class FixedRecoveryIdentityPortV1:
    """One deterministic server-controlled identity seam (SPEC §5.4)."""

    def __init__(self) -> None:
        self._counter = 0

    def new_event_id(self) -> str:
        self._counter += 1
        return f"rec-event-{self._counter}"

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
def operations_ports() -> SpyLocalOperationsPorts:
    return SpyLocalOperationsPorts()


@pytest.fixture
def recovery_identity() -> FixedRecoveryIdentityPortV1:
    return FixedRecoveryIdentityPortV1()


@pytest.fixture
def local_web_client(
    security_config: LocalWebSecurityConfigV1,
    operations_ports: SpyLocalOperationsPorts,
    recovery_identity: FixedRecoveryIdentityPortV1,
) -> TestClient:
    ports: RecoveryWorkflowPortsV1 = operations_ports
    identity: RecoveryWorkflowIdentityPortV1 = recovery_identity
    app, manager = _build_local_app(
        security_config, (RecoveryRouteInstallerV1(ports, identity),)
    )
    client = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")
    session = manager.create()
    client.cookies.set(security_config.session_cookie_name, session.session_id)
    return client


def test_recovery_preview_is_read_only_and_has_no_force_control(
    local_web_client: TestClient,
    operations_ports: SpyLocalOperationsPorts,
) -> None:
    response = local_web_client.get(
        "/runs/run-recovery/recovery", headers=valid_local_security_headers()
    )
    assert (
        operations_ports.recovery_apply_call_count
        == operations_ports.workspace_write_count
        == 0
    )
    assert 'name="force"' not in response.text and 'name="ignore"' not in response.text


def test_recovery_preview_renders_full_path_status_consequence_evidence(
    local_web_client: TestClient,
    operations_ports: SpyLocalOperationsPorts,
) -> None:
    """The preview page renders the transaction, the closed disposition,
    the per-path status/consequence rows, the zero-write proof, and the
    preview digest — and no bypass control (GREEN-2)."""
    response = local_web_client.get(
        "/runs/run-recovery/recovery", headers=valid_local_security_headers()
    )
    assert response.status_code == 200
    assert operations_ports.preview_call_count == 1
    assert "tx-1" in response.text
    assert "已回滚" in response.text
    assert "本次预览工作区写入次数：0" in response.text
    assert "preview-digest-1" in response.text
    assert "src/a.py" in response.text and "后映像" in response.text
    assert "拟保持后映像并重做写后核对" in response.text
    assert "src/b.py" in response.text and "前映像" in response.text
    assert "拟恢复前映像" in response.text
    for forbidden in ("force", "ignore", "skip", "edit", "abandon"):
        assert f'name="{forbidden}"' not in response.text


def test_recovery_unresolved_preview_blocks_without_apply_control(
    local_web_client: TestClient,
    operations_ports: SpyLocalOperationsPorts,
) -> None:
    """An UNRESOLVED preview renders the stable blocking warning and no
    apply control; only service-proven terminal results unblock
    (GREEN-4/Boundary)."""
    operations_ports.seed_preview(preview_payload(disposition="UNRESOLVED"))
    response = local_web_client.get(
        "/runs/run-recovery/recovery", headers=valid_local_security_headers()
    )
    assert response.status_code == 200
    assert "未解决" in response.text
    assert "只有服务证明的已提交或已回滚终局才能解除恢复阻塞" in response.text
    assert 'name="confirmation"' not in response.text
    assert 'name="force"' not in response.text
    assert 'name="ignore"' not in response.text


def test_recovery_terminal_preview_renders_explicit_confirmation_form(
    local_web_client: TestClient,
    operations_ports: SpyLocalOperationsPorts,
) -> None:
    """A terminal preview renders the distinct explicit confirmation step
    with the frozen binding fields only (GREEN-2)."""
    response = local_web_client.get(
        "/runs/run-recovery/recovery", headers=valid_local_security_headers()
    )
    assert response.status_code == 200
    assert "确认回滚到前映像" in response.text
    assert 'name="transaction_id" value="tx-1"' in response.text
    assert 'name="preview_digest" value="preview-digest-1"' in response.text
    assert 'name="confirmation"' in response.text
    assert "我确认执行该恢复操作" in response.text


def test_recovery_apply_binds_exact_command_and_renders_terminal_result(
    local_web_client: TestClient,
    operations_ports: SpyLocalOperationsPorts,
    recovery_identity: FixedRecoveryIdentityPortV1,
) -> None:
    """A confirmed apply posts the frozen binding fields; the command
    carries the Run id, the rendered transaction/digest, the literal
    confirmation, and the server-controlled event; the service-proven
    terminal result renders with the changed paths and evidence digest
    (GREEN-1/Boundary)."""
    response = local_web_client.post(
        "/runs/run-recovery/recovery",
        headers=valid_local_security_headers(),
        data={
            "transaction_id": "tx-1",
            "preview_digest": "preview-digest-1",
            "confirmation": "yes",
        },
    )
    assert response.status_code == 200
    assert operations_ports.recovery_apply_call_count == 1
    command = operations_ports.apply_commands[0]
    assert command.run_id == "run-recovery"
    assert command.transaction_id == "tx-1"
    assert command.preview_digest == "preview-digest-1"
    assert command.confirmation == "yes"
    assert command.event_id == "rec-event-1"
    assert command.decided_at == _FIXED_NOW
    assert "已回滚" in response.text
    assert "src/a.py、src/b.py" in response.text
    assert "evidence-digest-1" in response.text
    assert "工作区写入次数" in response.text and "2" in response.text


def test_recovery_apply_requires_literal_confirmation_and_closed_form(
    local_web_client: TestClient,
    operations_ports: SpyLocalOperationsPorts,
) -> None:
    """The apply form accepts only the frozen binding fields; a missing
    confirmation or any bypass/override field rejects with zero apply
    calls (GREEN-1)."""
    base = {
        "transaction_id": "tx-1",
        "preview_digest": "preview-digest-1",
        "confirmation": "yes",
    }
    for body in (
        {"transaction_id": "tx-1", "preview_digest": "preview-digest-1"},
        dict(base, confirmation="no"),
        dict(base, force="1"),
        dict(base, ignore="1"),
        dict(base, skip="1"),
        dict(base, edit="1"),
        dict(base, abandon="1"),
        dict(base, disposition="COMMITTED"),
        dict(base, workspace_id="foreign"),
        dict(base, event_id="client-supplied"),
    ):
        response = local_web_client.post(
            "/runs/run-recovery/recovery",
            headers=valid_local_security_headers(),
            data=body,
        )
        assert response.status_code == 422
        assert operations_ports.recovery_apply_call_count == 0


def test_recovery_stale_preview_apply_rejects_with_zero_calls(
    local_web_client: TestClient,
    operations_ports: SpyLocalOperationsPorts,
) -> None:
    """A stale transaction/digest binding rejects before any domain call;
    the stale preview never renders success (GREEN-1/Boundary)."""
    operations_ports.seed_preview(preview_payload(paths=(("src/a.py", "POSTIMAGE"),)))
    response = local_web_client.post(
        "/runs/run-recovery/recovery",
        headers=valid_local_security_headers(),
        data={
            "transaction_id": "tx-1",
            "preview_digest": "stale-digest",
            "confirmation": "yes",
        },
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "RECOVERY_PREVIEW_STALE"
    assert operations_ports.recovery_apply_call_count == 0


def test_recovery_unresolved_apply_never_renders_success(
    local_web_client: TestClient,
    operations_ports: SpyLocalOperationsPorts,
) -> None:
    """An UNRESOLVED apply outcome re-renders the blocked state with the
    bounded message — never a success (Boundary)."""
    operations_ports.seed_apply_result(
        RecoveryResultV1(
            schema_version=1,
            transaction_id="tx-1",
            disposition="UNRESOLVED",
            error_code="RECOVERY_UNRESOLVED",
            changed_paths=(),
            evidence_digest=None,
            workspace_write_count=0,
            message="external change detected; recovery remains unresolved",
        )
    )
    response = local_web_client.post(
        "/runs/run-recovery/recovery",
        headers=valid_local_security_headers(),
        data={
            "transaction_id": "tx-1",
            "preview_digest": "preview-digest-1",
            "confirmation": "yes",
        },
    )
    assert response.status_code == 200
    assert operations_ports.recovery_apply_call_count == 1
    assert "external change detected; recovery remains unresolved" in response.text
    assert "保持恢复阻塞" in response.text
    assert "已回滚" not in response.text
    assert "全部路径恢复到前映像" not in response.text


def test_recovery_preview_error_renders_stable_blocked_page(
    local_web_client: TestClient,
    operations_ports: SpyLocalOperationsPorts,
) -> None:
    """A closed preview rejection renders the stable blocked page with no
    apply control (GREEN-4)."""
    operations_ports.seed_preview_error(
        RecoveryPreviewErrorV1("TRANSACTION_NOT_FOUND", "no transaction")
    )
    response = local_web_client.get(
        "/runs/run-recovery/recovery", headers=valid_local_security_headers()
    )
    assert response.status_code == 200
    assert "该运行没有非终态恢复事务。" in response.text
    assert 'name="confirmation"' not in response.text
    assert 'name="force"' not in response.text


def test_recovery_preview_escapes_hostile_path_text(
    local_web_client: TestClient,
    operations_ports: SpyLocalOperationsPorts,
) -> None:
    """Hostile path text renders as escaped text, never executable markup
    (GREEN-2/SPEC §4.9)."""
    operations_ports.seed_preview(
        preview_payload(paths=(("<em>hostile", "POSTIMAGE"),))
    )
    response = local_web_client.get(
        "/runs/run-recovery/recovery", headers=valid_local_security_headers()
    )
    assert response.status_code == 200
    assert "<em>hostile" not in response.text
    assert "&lt;em&gt;hostile" in response.text


def test_recovery_route_is_loopback_security_bound(
    local_web_client: TestClient,
    operations_ports: SpyLocalOperationsPorts,
    security_config: LocalWebSecurityConfigV1,
) -> None:
    """The Task 28.A fixed-order rejections fire before any domain call."""
    no_session = TestClient(local_web_client.app, base_url="http://127.0.0.1:8765")
    response = no_session.get(
        "/runs/run-recovery/recovery", headers={"Host": "127.0.0.1:8765"}
    )
    assert response.status_code == 401
    assert operations_ports.preview_call_count == 0

    no_csrf = TestClient(local_web_client.app, base_url="http://127.0.0.1:8765")
    no_csrf.cookies.set(security_config.session_cookie_name, "f" * 64)
    response = no_csrf.post(
        "/runs/run-recovery/recovery",
        headers={"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"},
        data={
            "transaction_id": "tx-1",
            "preview_digest": "preview-digest-1",
            "confirmation": "yes",
        },
    )
    assert response.status_code == 403
    assert operations_ports.recovery_apply_call_count == 0
