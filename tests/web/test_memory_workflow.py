"""T38.1 legacy step 38.B: workspace memory WebUI tests.

The exact RED pins the smallest cross-workspace rejection: a
client-selected ``workspace_id`` must be rejected before command
construction with zero create-port calls (SPEC §4.7/AC-14).  The
``memory_client`` fixture is a test-local mirror (the T28.1 M3-precedent
class documented in T29.1) whose middleware mirrors the Task 28.A fixed
order verbatim and whose deterministic session lets the card's
header-only POST pass the exact security order and reach the real
``MemoryRouteInstallerV1`` over the spy ports.

The domain pins cover the server-derived workspace scope, the
creator/source/scope display, the create->confirm->clear state
transitions, stale/foreign/duplicate no-mutation, the closed form
surface with zero control/policy fields, escaping, and accessibility.
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
from vespercode.memory.clear import MemoryClearResultV1
from vespercode.memory.entry import (
    MemoryCreatorV1,
    MemoryEntryV1,
    MemoryKindV1,
    MemoryMutationResultV1,
    RunSummarySourceV1,
    UserDecisionSourceV1,
    UserVisibleTextSourceV1,
)
from vespercode.web.routes_memory import (
    ClearMemoryForRunV1,
    ConfirmMemoryForRunV1,
    CreateMemoryForRunV1,
    MemoryRouteInstallerV1,
    MemoryWorkflowIdentityPortV1,
    MemoryWorkflowPortsV1,
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


def valid_memory_form() -> dict[str, str]:
    """One valid closed memory create-form body (declared fields only)."""
    return {
        "summary": "按规范使用 src 目录结构",
        "source_reference": "用户提交的运行要求（第 2 页）",
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


def memory_entry(
    entry_id: str = "mem-1",
    *,
    kind: MemoryKindV1 = "PROJECT_CONVENTION",
    summary: str = "按规范使用 src 目录结构",
    creator: MemoryCreatorV1 = "USER",
    source: Any = None,
    untrusted: bool = True,
) -> MemoryEntryV1:
    """One bounded immutable memory entry value (SPEC 7 MemoryEntry)."""
    return MemoryEntryV1(
        entry_id=entry_id,
        workspace_identity="ws-digest-1",
        kind=kind,
        summary=summary,
        creator=creator,
        source=(
            source
            if source is not None
            else UserVisibleTextSourceV1(
                kind="USER_VISIBLE_TEXT", reference="用户提交的运行要求（第 2 页）"
            )
        ),
        created_at=_FIXED_NOW,
        updated_at=_FIXED_NOW,
        untrusted=untrusted,
    )


class SpyMemoryPorts:
    """One spy typed memory workflow-port implementation.

    The spy records every command for exact pinning and never touches a
    database; the routes own no domain rule, so the spy only counts and
    returns the seeded closed results.
    """

    def __init__(self) -> None:
        self.create_call_count = 0
        self.confirm_call_count = 0
        self.clear_call_count = 0
        self.list_call_count = 0
        self.entries: tuple[MemoryEntryV1, ...] = ()
        self.create_result = MemoryMutationResultV1(
            kind="CREATED", message="memory entry created"
        )
        self.confirm_result = MemoryMutationResultV1(
            kind="CONFIRMED", message="project convention confirmed"
        )
        self.clear_result = MemoryClearResultV1(
            kind="CLEARED", message="memory entries cleared"
        )
        self._create_commands: list[CreateMemoryForRunV1] = []
        self._confirm_commands: list[ConfirmMemoryForRunV1] = []
        self._clear_commands: list[ClearMemoryForRunV1] = []
        self._listed_run_ids: list[str] = []

    def seed_entries(self, entries: tuple[MemoryEntryV1, ...]) -> None:
        self.entries = entries

    def seed_create_result(self, result: MemoryMutationResultV1) -> None:
        self.create_result = result

    def seed_confirm_result(self, result: MemoryMutationResultV1) -> None:
        self.confirm_result = result

    def seed_clear_result(self, result: MemoryClearResultV1) -> None:
        self.clear_result = result

    @property
    def create_commands(self) -> list[CreateMemoryForRunV1]:
        return list(self._create_commands)

    @property
    def confirm_commands(self) -> list[ConfirmMemoryForRunV1]:
        return list(self._confirm_commands)

    @property
    def clear_commands(self) -> list[ClearMemoryForRunV1]:
        return list(self._clear_commands)

    @property
    def listed_run_ids(self) -> list[str]:
        return list(self._listed_run_ids)

    def list(self, run_id: str) -> tuple[MemoryEntryV1, ...]:
        self.list_call_count += 1
        self._listed_run_ids.append(run_id)
        return self.entries

    def create(self, command: CreateMemoryForRunV1) -> MemoryMutationResultV1:
        self.create_call_count += 1
        self._create_commands.append(command)
        return self.create_result

    def confirm(self, command: ConfirmMemoryForRunV1) -> MemoryMutationResultV1:
        self.confirm_call_count += 1
        self._confirm_commands.append(command)
        return self.confirm_result

    def clear(self, command: ClearMemoryForRunV1) -> MemoryClearResultV1:
        self.clear_call_count += 1
        self._clear_commands.append(command)
        return self.clear_result


class FixedMemoryIdentityPortV1:
    """One deterministic server-controlled identity seam (SPEC §5.4)."""

    def __init__(self) -> None:
        self._event_counter = 0
        self._entry_counter = 0

    def new_event_id(self) -> str:
        self._event_counter += 1
        return f"mem-event-{self._event_counter}"

    def new_entry_id(self) -> str:
        self._entry_counter += 1
        return f"mem-entry-{self._entry_counter}"

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
def memory_ports() -> SpyMemoryPorts:
    return SpyMemoryPorts()


@pytest.fixture
def memory_identity() -> FixedMemoryIdentityPortV1:
    return FixedMemoryIdentityPortV1()


@pytest.fixture
def memory_client(
    security_config: LocalWebSecurityConfigV1,
    memory_ports: SpyMemoryPorts,
    memory_identity: FixedMemoryIdentityPortV1,
) -> TestClient:
    ports: MemoryWorkflowPortsV1 = memory_ports
    identity: MemoryWorkflowIdentityPortV1 = memory_identity
    app, manager = _build_local_app(
        security_config, (MemoryRouteInstallerV1(ports, identity),)
    )
    client = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")
    session = manager.create()
    client.cookies.set(security_config.session_cookie_name, session.session_id)
    return client


def test_memory_form_cannot_select_foreign_workspace(
    memory_client: TestClient,
    memory_ports: SpyMemoryPorts,
) -> None:
    response = memory_client.post(
        "/runs/run-1/memory",
        headers=valid_local_security_headers(),
        data=valid_memory_form() | {"workspace_id": "foreign"},
    )
    assert response.status_code == 422
    assert memory_ports.create_call_count == 0


def test_memory_create_derives_scope_from_run_and_binds_command(
    memory_client: TestClient,
    memory_ports: SpyMemoryPorts,
    memory_identity: FixedMemoryIdentityPortV1,
) -> None:
    """A valid create posts only the declared fields; the command carries
    the Run id, the server-fixed kind/creator, and the server-controlled
    identities — never a client-selected workspace (GREEN-1)."""
    memory_ports.seed_entries((memory_entry(entry_id="mem-entry-1", untrusted=True),))
    response = memory_client.post(
        "/runs/run-1/memory",
        headers=valid_local_security_headers(),
        data=valid_memory_form(),
    )
    assert response.status_code == 200
    assert memory_ports.create_call_count == 1
    command = memory_ports.create_commands[0]
    assert command.run_id == "run-1"
    assert command.kind == "PROJECT_CONVENTION"
    assert command.creator == "USER"
    assert command.summary == "按规范使用 src 目录结构"
    assert command.source_reference == "用户提交的运行要求（第 2 页）"
    assert command.entry_id == "mem-entry-1"
    assert command.event_id == "mem-event-1"
    assert command.decided_at == _FIXED_NOW
    redirect = memory_client.post(
        "/runs/run-1/memory",
        headers=valid_local_security_headers(),
        data=valid_memory_form(),
        follow_redirects=False,
    )
    assert redirect.status_code == 303
    assert redirect.headers["location"] == "/runs/run-1/memory"


def test_memory_form_rejects_all_override_fields_before_construction(
    memory_client: TestClient,
    memory_ports: SpyMemoryPorts,
) -> None:
    """Control/policy/scope/identity override fields reject with 422 and
    zero create calls (GREEN-1/GREEN-4: no generic write, no policy/
    Manifest/approval/disclosure/config mutation)."""
    for override_field in (
        "workspace_id",
        "workspace_identity",
        "kind",
        "creator",
        "entry_id",
        "event_id",
        "policy_id",
        "manifest_digest",
        "approval_id",
        "disclosure_grant_id",
        "config_id",
        "success",
    ):
        response = memory_client.post(
            "/runs/run-1/memory",
            headers=valid_local_security_headers(),
            data=valid_memory_form() | {override_field: "x"},
        )
        assert response.status_code == 422
        assert memory_ports.create_call_count == 0


def test_memory_page_renders_creator_source_scope_and_state(
    memory_client: TestClient,
    memory_ports: SpyMemoryPorts,
) -> None:
    """The page renders creator/source/scope and the create->confirm->
    clear state with explicit labels and no control/policy fields
    (GREEN-2)."""
    memory_ports.seed_entries(
        (
            memory_entry(entry_id="mem-a", untrusted=True),
            memory_entry(
                entry_id="mem-b",
                kind="USER_DECISION",
                summary="拒绝扩大披露范围",
                creator="CONTROL_PLANE",
                source=UserDecisionSourceV1(
                    kind="USER_DECISION",
                    decision="REJECT",
                    reference="决定记录 d-1",
                ),
                untrusted=False,
            ),
            memory_entry(
                entry_id="mem-c",
                kind="RUN_SUMMARY",
                summary="运行总结",
                creator="CONTROL_PLANE",
                source=RunSummarySourceV1(
                    kind="RUN_SUMMARY", run_id="run-9", result="STOPPED"
                ),
                untrusted=False,
            ),
        )
    )
    response = memory_client.get(
        "/runs/run-1/memory", headers={"Host": "127.0.0.1:8765"}
    )
    assert response.status_code == 200
    assert memory_ports.list_call_count >= 1
    assert "按规范使用 src 目录结构" in response.text
    assert "创建者" in response.text and "来源" in response.text
    assert "范围" in response.text and "状态" in response.text
    assert "用户" in response.text and "控制面" in response.text
    assert "用户可见文本" in response.text
    assert "拒绝：决定记录 d-1" in response.text
    assert "run-9（已停止）" in response.text
    assert "ws-digest-1" in response.text
    assert "未确认（待用户确认）" in response.text
    assert "已确认" in response.text
    assert 'name="workspace_id"' not in response.text
    assert 'name="workspace_identity"' not in response.text
    assert 'name="kind"' not in response.text
    assert 'name="creator"' not in response.text
    assert 'name="policy"' not in response.text
    assert 'name="approval"' not in response.text
    assert 'name="disclosure"' not in response.text
    assert 'name="config"' not in response.text


def test_memory_confirm_binds_entry_and_clears_untrusted_marker(
    memory_client: TestClient,
    memory_ports: SpyMemoryPorts,
) -> None:
    """The confirm form posts only the entry id; the command binds the
    Run, the user creator, and the server-controlled event (GREEN-1)."""
    memory_ports.seed_entries((memory_entry(entry_id="mem-a", untrusted=False),))
    response = memory_client.post(
        "/runs/run-1/memory/confirm",
        headers=valid_local_security_headers(),
        data={"entry_id": "mem-a"},
    )
    assert response.status_code == 200
    assert memory_ports.confirm_call_count == 1
    command = memory_ports.confirm_commands[0]
    assert command.run_id == "run-1"
    assert command.entry_id == "mem-a"
    assert command.creator == "USER"
    assert command.event_id == "mem-event-1"
    assert command.decided_at == _FIXED_NOW


def test_memory_clear_binds_target_entries(
    memory_client: TestClient,
    memory_ports: SpyMemoryPorts,
) -> None:
    """The clear form posts only the entry targets; the command carries
    the Run-bound targets and the user creator (GREEN-1/Boundary)."""
    memory_ports.seed_entries((memory_entry(entry_id="mem-a"),))
    response = memory_client.post(
        "/runs/run-1/memory/clear",
        headers=valid_local_security_headers(),
        data={"entry_ids": "mem-a"},
    )
    assert response.status_code == 200
    assert memory_ports.clear_call_count == 1
    command = memory_ports.clear_commands[0]
    assert command.run_id == "run-1"
    assert command.target_entry_ids == ("mem-a",)
    assert command.creator == "USER"
    assert command.event_id == "mem-event-1"


def test_memory_rejected_mutation_renders_real_state_with_error(
    memory_client: TestClient,
    memory_ports: SpyMemoryPorts,
) -> None:
    """A stale/foreign/duplicate rejection re-renders the real memory
    state with the bounded error and never claims success (Boundary)."""
    memory_ports.seed_entries((memory_entry(entry_id="mem-a"),))
    memory_ports.seed_create_result(
        MemoryMutationResultV1(
            kind="REJECTED",
            message="memory entry id already exists",
            error_code="MEMORY_STORE_FAILED",
        )
    )
    response = memory_client.post(
        "/runs/run-1/memory",
        headers=valid_local_security_headers(),
        data=valid_memory_form(),
    )
    assert response.status_code == 200
    assert memory_ports.create_call_count == 1
    assert "memory entry id already exists" in response.text
    assert "按规范使用 src 目录结构" in response.text


def test_memory_page_escapes_untrusted_summary(
    memory_client: TestClient,
    memory_ports: SpyMemoryPorts,
) -> None:
    """Untrusted memory content renders as escaped text, never executable
    markup (GREEN-2/SPEC §4.9)."""
    memory_ports.seed_entries(
        (memory_entry(entry_id="mem-a", summary='<script>alert("x")</script>'),)
    )
    response = memory_client.get(
        "/runs/run-1/memory", headers={"Host": "127.0.0.1:8765"}
    )
    assert response.status_code == 200
    assert "<script>alert" not in response.text
    assert "&lt;script&gt;" in response.text


def test_memory_empty_list_renders_empty_state(
    memory_client: TestClient,
    memory_ports: SpyMemoryPorts,
) -> None:
    """An empty workspace memory list renders the empty state."""
    response = memory_client.get(
        "/runs/run-1/memory", headers={"Host": "127.0.0.1:8765"}
    )
    assert response.status_code == 200
    assert "暂无记忆条目。" in response.text


def test_memory_route_is_loopback_security_bound(
    memory_client: TestClient,
    memory_ports: SpyMemoryPorts,
    security_config: LocalWebSecurityConfigV1,
) -> None:
    """The Task 28.A fixed-order rejections fire before any domain call."""
    no_session = TestClient(memory_client.app, base_url="http://127.0.0.1:8765")
    response = no_session.get("/runs/run-1/memory", headers={"Host": "127.0.0.1:8765"})
    assert response.status_code == 401
    assert memory_ports.list_call_count == 0

    no_csrf = TestClient(memory_client.app, base_url="http://127.0.0.1:8765")
    no_csrf.cookies.set(security_config.session_cookie_name, "f" * 64)
    response = no_csrf.post(
        "/runs/run-1/memory",
        headers={"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"},
        data=valid_memory_form(),
    )
    assert response.status_code == 403
    assert memory_ports.create_call_count == 0
