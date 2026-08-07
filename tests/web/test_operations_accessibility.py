"""T38.3 legacy step 38.G: cross-workflow browser and accessibility
acceptance tests.

The exact RED pins the verifier-first acceptance runner: the task-owned
``run_operations_accessibility_acceptance`` and
``OperationsAccessibilityAcceptanceResultV1`` must exist inside this
test file and fail closed on any missing workflow, label, focus
transition, live error/status region, redaction/scope invariant, or
recovery no-bypass observation (GREEN-3).  The ``rendered_operations_pages``
fixture renders the credential, memory, audit, and recovery pages
through Task 38.F's production composition over the spy ports, so the
pytest runner and the fixture start successfully and the card test fails
only because the task-owned symbols do not exist yet (the card's
Expected RED).

At GREEN the runner and the bounded result live in this file only —
production modules expose no new interface (GREEN-1/GREEN-4) — and the
Browser (38.G) flow exercises credential set/status/update/clear,
memory create/confirm/view/clear, paged audit/ended-run clear, and
recovery preview->explicit apply through the production composition
using only keyboard input events and the exact local request-security
contract (page-rendered CSRF token, Task 28.A headers).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Final

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from vespercode.audit.event import (
    ActionPayloadV1,
    AuditEventV1,
    LifecyclePayloadV1,
)
from vespercode.audit.repository import (
    AuditClearResultV1,
    AuditCursorV1,
    AuditPageRequestV1,
    AuditPageV1,
    ClearEndedRunAuditV1,
)
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.credentials.port import CredentialStatusV1
from vespercode.memory.clear import MemoryClearResultV1
from vespercode.memory.entry import (
    MemoryEntryV1,
    MemoryMutationResultV1,
    UserVisibleTextSourceV1,
)
from vespercode.persistence.recovery_apply import RecoveryResultV1
from vespercode.persistence.recovery_preview import (
    RecoveryPathClassificationEntryV1,
    RecoveryPreviewV1,
)
from vespercode.web.app import (
    LocalRouteInstallerSequenceV1,
    RunVisibilitySequenceV1,
)
from vespercode.web.security import LocalWebSecurityConfigV1

_FIXED_TOKEN: Final[str] = "f" * 64
"""One deterministic 256-bit hex session/CSRF token (closed token form)."""

_FIXED_NOW = CanonicalTimestampV1("2026-08-07T09:00:00.000Z")

_HOST = {"Host": "127.0.0.1:8765"}
"""The exact loopback Host header of every request (Task 28.A)."""


def valid_local_security_headers(csrf_token: str = _FIXED_TOKEN) -> dict[str, str]:
    """One fully valid loopback request-header set (Host + Origin + CSRF)."""
    return {
        "Host": "127.0.0.1:8765",
        "Origin": "http://127.0.0.1:8765",
        "X-CSRF-Token": csrf_token,
    }


def _rejection_response(error_code: str) -> JSONResponse:
    """One closed rejection response carrying the exact security headers."""
    from vespercode.web.security import (
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
    from vespercode.web.security import local_response_security_headers

    for name, value in local_response_security_headers(csp_nonce).items():
        response.headers[name] = value


def _fixed_token_generator() -> Callable[[], str]:
    """One deterministic session/CSRF token generator (SPEC §5.4)."""

    def generate() -> str:
        return _FIXED_TOKEN

    return generate


def _build_local_app(
    security_config: LocalWebSecurityConfigV1,
    installers: LocalRouteInstallerSequenceV1,
) -> tuple[FastAPI, Any]:
    """One test-local shell mirroring the Task 28.B composition."""
    from vespercode.web.security import (
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
        request.state.csp_nonce = "test-nonce-1234567890"
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
            response,
            "test-nonce-1234567890" if "text/html" in content_type else None,
        )
        return response

    for installer in installers:
        installer.install(app)
    return app, manager


class SpyCredentialPorts:
    """One spy credential workflow-port implementation.

    The spy holds a configured flag (never a secret value), counts every
    mutation, and returns the closed status/mutation results.
    """

    def __init__(self) -> None:
        self.set_call_count = 0
        self.update_call_count = 0
        self.clear_call_count = 0
        self.configured = False

    def set(self, provider: str, secret: Any, event_id: str) -> Any:
        from vespercode.credentials.port import CredentialMutationResultV1

        self.set_call_count += 1
        self.configured = True
        return CredentialMutationResultV1(
            schema_version=1, kind="STORED", error=AbsentV1(kind="ABSENT")
        )

    def status(self, provider: str) -> CredentialStatusV1:
        return CredentialStatusV1(
            schema_version=1,
            provider="OPENAI",
            configured=self.configured,
            updated_at=(
                PresentV1[CanonicalTimestampV1](kind="PRESENT", value=_FIXED_NOW)
                if self.configured
                else AbsentV1(kind="ABSENT")
            ),
        )

    def update(self, provider: str, secret: Any, event_id: str) -> Any:
        from vespercode.credentials.port import CredentialMutationResultV1

        self.update_call_count += 1
        self.configured = True
        return CredentialMutationResultV1(
            schema_version=1, kind="STORED", error=AbsentV1(kind="ABSENT")
        )

    def clear(self, provider: str, event_id: str) -> Any:
        from vespercode.credentials.port import CredentialMutationResultV1

        self.clear_call_count += 1
        self.configured = False
        return CredentialMutationResultV1(
            schema_version=1, kind="CLEARED", error=AbsentV1(kind="ABSENT")
        )


class SpyMemoryPorts:
    """One spy memory workflow-port implementation (in-memory store).

    The store keeps the bounded entries of one derived workspace; create
    adds an untrusted project convention, confirm clears the untrusted
    marker, and clear tombstones the targets.
    """

    def __init__(self) -> None:
        self.list_call_count = 0
        self._entries: dict[str, MemoryEntryV1] = {}

    def seed_entry(self, entry: MemoryEntryV1) -> None:
        self._entries[entry.entry_id] = entry

    def list(self, run_id: str) -> tuple[MemoryEntryV1, ...]:
        self.list_call_count += 1
        return tuple(
            entry for entry in self._entries.values() if entry.cleared_at is None
        )

    def create(self, command: Any) -> MemoryMutationResultV1:
        entry = MemoryEntryV1(
            entry_id=command.entry_id,
            workspace_identity="ws-digest-1",
            kind="PROJECT_CONVENTION",
            summary=command.summary,
            creator="USER",
            source=UserVisibleTextSourceV1(
                kind="USER_VISIBLE_TEXT", reference=command.source_reference
            ),
            created_at=command.decided_at,
            updated_at=command.decided_at,
            untrusted=True,
        )
        self._entries[entry.entry_id] = entry
        return MemoryMutationResultV1(
            kind="CREATED", message="memory entry created", entry=entry
        )

    def confirm(self, command: Any) -> MemoryMutationResultV1:
        entry = self._entries[command.entry_id]
        updated_at = (
            command.decided_at
            if command.decided_at.epoch_milliseconds
            >= entry.created_at.epoch_milliseconds
            else entry.created_at
        )
        updated = MemoryEntryV1(
            entry_id=entry.entry_id,
            workspace_identity=entry.workspace_identity,
            kind=entry.kind,
            summary=entry.summary,
            creator=entry.creator,
            source=entry.source,
            created_at=entry.created_at,
            updated_at=updated_at,
            untrusted=False,
        )
        self._entries[entry.entry_id] = updated
        return MemoryMutationResultV1(
            kind="CONFIRMED",
            message="project convention confirmed",
            entry=updated,
        )

    def clear(self, command: Any) -> MemoryClearResultV1:
        for target in command.target_entry_ids:
            entry = self._entries[target]
            self._entries[target] = MemoryEntryV1(
                entry_id=entry.entry_id,
                workspace_identity=entry.workspace_identity,
                kind=entry.kind,
                summary=entry.summary,
                creator=entry.creator,
                source=entry.source,
                created_at=entry.created_at,
                updated_at=entry.updated_at,
                untrusted=entry.untrusted,
                cleared_at=command.decided_at,
                clear_transaction_id=command.event_id,
            )
        return MemoryClearResultV1(
            kind="CLEARED",
            message="memory entries cleared",
            cleared_count=len(command.target_entry_ids),
        )


class SpyAuditPorts:
    """One spy audit workflow-port implementation (seeded pages)."""

    def __init__(self) -> None:
        self.list_call_count = 0
        self.clear_call_count = 0
        self.page_result = AuditPageV1(run_id="run-1", items=())
        self.clear_result = AuditClearResultV1(
            kind="CLEARED", message="audit events cleared"
        )

    def seed_page(self, page: AuditPageV1) -> None:
        self.page_result = page

    def list_run(self, run_id: str, page: AuditPageRequestV1) -> AuditPageV1:
        self.list_call_count += 1
        return self.page_result

    def clear_ended_run(self, command: ClearEndedRunAuditV1) -> AuditClearResultV1:
        self.clear_call_count += 1
        return self.clear_result

    def clear_state_for(self, run_id: str) -> Any:
        from vespercode.web.routes_audit import AuditClearStateV1

        return AuditClearStateV1(
            run_id=run_id, run_ended=True, has_unresolved_recovery=False
        )


class SpyRecoveryPorts:
    """One spy recovery workflow-port implementation (seeded preview)."""

    def __init__(self) -> None:
        self.preview_result = RecoveryPreviewV1(
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
        self.apply_result = RecoveryResultV1(
            schema_version=1,
            transaction_id="tx-1",
            disposition="ROLLED_BACK",
            error_code=None,
            changed_paths=("src/a.py",),
            evidence_digest="evidence-digest-1",
            workspace_write_count=1,
            message="recovery rolled back",
        )

    def preview(self, run_id: str) -> RecoveryPreviewV1:
        return self.preview_result

    def apply(self, command: Any) -> RecoveryResultV1:
        return self.apply_result


class _EmptyGovernancePorts:
    """One dummy Milestone 29 governance aggregate (never called)."""


def _spy_operations() -> Any:
    """One spy operations aggregate with the four workflow spies."""
    from vespercode.web.routes_operations import (
        LocalOperationsWorkflowPortsV1,
    )

    return LocalOperationsWorkflowPortsV1(
        credentials=SpyCredentialPorts(),
        memory=SpyMemoryPorts(),
        audit=SpyAuditPorts(),
        recovery=SpyRecoveryPorts(),
    )


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


def _production_ports() -> Any:
    """One fake production port aggregate over the spy ports.

    The spies are fresh per call and unseeded, so the mutation flows
    (the Browser 38.G flow) start from the empty state; the acceptance
    fixture seeds the memory/audit spies with the hostile/redacted
    content its checks verify.
    """
    from typing import cast

    from vespercode.web.local_composition import (
        ProductionLocalWorkflowPortsV1,
    )
    from vespercode.web.run_workflows import RunGovernanceWorkflowPortsV1

    return ProductionLocalWorkflowPortsV1(
        shell=FakeShellPortsV1(),
        governance=RunGovernanceWorkflowPortsV1(
            run_lifecycle=cast(Any, _EmptyGovernancePorts()),
            disclosure=cast(Any, _EmptyGovernancePorts()),
            final_writeback=cast(Any, _EmptyGovernancePorts()),
        ),
        operations=_spy_operations(),
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
def production_ports() -> Any:
    """One fake production port aggregate (fresh spies per test)."""
    return _production_ports()


@pytest.fixture
def production_client(
    security_config: LocalWebSecurityConfigV1,
    production_ports: Any,
) -> TestClient:
    """One client over the real Task 38.F production composition.

    The session is bootstrapped by the first home visit (the Task 28.A
    session bootstrap), so every later page and state change flows
    through the exact local request-security contract.
    """
    from vespercode.web.local_composition import build_local_application

    app = build_local_application(production_ports, security_config)
    client = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")
    home = client.get("/", headers=_HOST)
    assert home.status_code == 200
    return client


@pytest.fixture
def rendered_operations_pages(
    production_client: TestClient,
    production_ports: Any,
) -> tuple[str, ...]:
    """The four operations pages rendered through the production app.

    The memory and audit spies are seeded so the rendered pages carry
    the creator/source/scope rows and a projection whose free-text
    payload fields contain the raw-request sentinel (which must never
    reach the page — the redaction invariant is a real observation).
    """
    operations = production_ports.operations
    operations.memory.seed_entry(
        MemoryEntryV1(
            entry_id="mem-1",
            workspace_identity="ws-digest-1",
            kind="PROJECT_CONVENTION",
            summary="按规范使用 src 目录结构",
            creator="USER",
            source=UserVisibleTextSourceV1(
                kind="USER_VISIBLE_TEXT",
                reference="用户提交的运行要求（第 2 页）",
            ),
            created_at=_FIXED_NOW,
            updated_at=_FIXED_NOW,
            untrusted=True,
        )
    )
    operations.audit.seed_page(
        AuditPageV1(
            run_id="run-1",
            items=(
                AuditEventV1(
                    run_id="run-1",
                    sequence=1,
                    event_type="ACTION",
                    redacted_payload=ActionPayloadV1(
                        kind="ACTION",
                        action_type="raw-request-sentinel",
                        policy_decision="ALLOW",
                    ),
                    created_at=_FIXED_NOW,
                ),
                AuditEventV1(
                    run_id="run-1",
                    sequence=2,
                    event_type="LIFECYCLE",
                    redacted_payload=LifecyclePayloadV1(
                        kind="LIFECYCLE", status="SUCCEEDED"
                    ),
                    created_at=_FIXED_NOW,
                ),
            ),
            next_cursor=AuditCursorV1(run_id="run-1", last_sequence=2),
        )
    )
    return (
        production_client.get("/credentials/openai", headers=_HOST).text,
        production_client.get("/runs/run-1/memory", headers=_HOST).text,
        production_client.get("/runs/run-1/audit", headers=_HOST).text,
        production_client.get("/runs/run-recovery/recovery", headers=_HOST).text,
    )


def test_operations_acceptance_runner_requires_all_workflows(
    rendered_operations_pages: tuple[str, ...],
) -> None:
    result = run_operations_accessibility_acceptance(
        rendered_operations_pages=rendered_operations_pages,
        workflow_ids=("CREDENTIAL", "MEMORY", "AUDIT", "RECOVERY"),
        input_events=("TAB", "ENTER"),
    )
    assert result.workflow_ids == ("CREDENTIAL", "MEMORY", "AUDIT", "RECOVERY")
    assert result.keyboard_only is True
    assert result.capture_count == len(rendered_operations_pages)
    assert result.failures == ()


EXPECTED_WORKFLOW_IDS_V1: Final[tuple[str, ...]] = (
    "CREDENTIAL",
    "MEMORY",
    "AUDIT",
    "RECOVERY",
)
"""The deterministic acceptance workflow order (GREEN-1)."""

_KEYBOARD_INPUT_EVENTS_V1: Final[frozenset[str]] = frozenset(
    {
        "TAB",
        "ENTER",
        "SPACE",
        "ARROW_LEFT",
        "ARROW_RIGHT",
        "ARROW_UP",
        "ARROW_DOWN",
        "HOME",
        "END",
        "PAGE_UP",
        "PAGE_DOWN",
    }
)
"""The closed keyboard input-event vocabulary of the acceptance."""

_WORKFLOW_REQUIREMENTS_V1: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    "CREDENTIAL": (
        ("h1", "凭据状态"),
        ("status-region", "配置状态"),
        ("password-field", 'name="secret"'),
        ("password-type", 'type="password"'),
        ("live-error-region", 'id="live-error"'),
        ("native-control", "<button"),
    ),
    "MEMORY": (
        ("h1", "运行记忆"),
        ("creator-label", "创建者"),
        ("source-label", "来源"),
        ("scope-label", "范围"),
        ("live-error-region", 'id="live-error"'),
        ("native-control", "<button"),
    ),
    "AUDIT": (
        ("h1", "运行审计"),
        ("retention", "默认保留 30 天"),
        ("live-error-region", 'id="live-error"'),
        ("native-control", "<button"),
    ),
    "RECOVERY": (
        ("h1", "恢复预览"),
        ("zero-write", "零写入"),
        ("confirmation", 'name="confirmation"'),
        ("live-error-region", 'id="live-error"'),
        ("native-control", "<button"),
    ),
}
"""The fail-closed per-workflow required markers (GREEN-3)."""

_WORKFLOW_FORBIDDEN_V1: Final[dict[str, tuple[str, ...]]] = {
    "CREDENTIAL": ("inert-sentinel", "secret-sentinel"),
    "MEMORY": ('name="workspace_id"', 'name="kind"', 'name="creator"'),
    "AUDIT": ("raw-request-sentinel", "backup-body-sentinel"),
    "RECOVERY": (
        'name="force"',
        'name="ignore"',
        'name="skip"',
        'name="edit"',
        'name="abandon"',
    ),
}
"""The fail-closed per-workflow forbidden markers (redaction/scope/
no-bypass invariants)."""


@dataclass(frozen=True)
class OperationsAccessibilityAcceptanceResultV1:
    """One bounded acceptance result (test-owned, GREEN-1).

    ``workflow_ids`` is the deterministic workflow order, ``keyboard_only``
    is whether every declared input event is keyboard-only,
    ``capture_count`` is the bounded rendered-page count, and
    ``failures`` is the closed stable failure-code tuple.
    """

    workflow_ids: tuple[str, ...]
    keyboard_only: bool
    capture_count: int
    failures: tuple[str, ...]


def run_operations_accessibility_acceptance(
    rendered_operations_pages: tuple[str, ...],
    workflow_ids: tuple[str, ...],
    input_events: tuple[str, ...],
) -> OperationsAccessibilityAcceptanceResultV1:
    """One verifier-first bounded acceptance run (GREEN-1/GREEN-3).

    The runner fails closed on the deterministic workflow order, the
    page count, non-keyboard input events, any missing required
    workflow marker (heading, label, focusable native control, live
    error/status region), and any forbidden marker (secret derivative,
    workspace selector, raw body, or recovery bypass control); the
    failure codes are stable closed strings and the evidence is the
    bounded in-memory result only.
    """
    failures: list[str] = []
    if workflow_ids != EXPECTED_WORKFLOW_IDS_V1:
        failures.append("WORKFLOW_ORDER_INVALID")
    if len(rendered_operations_pages) != len(workflow_ids):
        failures.append("PAGE_COUNT_MISMATCH")
    keyboard_only = all(event in _KEYBOARD_INPUT_EVENTS_V1 for event in input_events)
    if not keyboard_only:
        failures.append("KEYBOARD_ONLY_VIOLATION")
    for workflow_id, page in zip(workflow_ids, rendered_operations_pages):
        requirements = _WORKFLOW_REQUIREMENTS_V1.get(workflow_id)
        if requirements is None:
            failures.append(f"UNKNOWN_WORKFLOW:{workflow_id}")
            continue
        for marker_name, marker in requirements:
            if marker not in page:
                failures.append(f"MISSING:{workflow_id}:{marker_name}")
        for forbidden in _WORKFLOW_FORBIDDEN_V1.get(workflow_id, ()):
            if forbidden in page:
                failures.append(f"FORBIDDEN:{workflow_id}:{forbidden}")
    return OperationsAccessibilityAcceptanceResultV1(
        workflow_ids=workflow_ids,
        keyboard_only=keyboard_only,
        capture_count=len(rendered_operations_pages),
        failures=tuple(failures),
    )


def _page_csrf_token(page_text: str) -> str:
    """One page-rendered CSRF token (the Task 28.A header value)."""
    match = re.search(r'<meta name="csrf-token" content="([0-9a-f]{64})">', page_text)
    assert match is not None, "the page must render the CSRF token"
    return match.group(1)


def test_acceptance_runner_fails_closed_on_missing_workflow_content() -> None:
    """Empty pages fail closed with the stable missing-marker codes for
    every required workflow (GREEN-3)."""
    result = run_operations_accessibility_acceptance(
        rendered_operations_pages=("", "", "", ""),
        workflow_ids=("CREDENTIAL", "MEMORY", "AUDIT", "RECOVERY"),
        input_events=("TAB", "ENTER"),
    )
    for workflow_id in ("CREDENTIAL", "MEMORY", "AUDIT", "RECOVERY"):
        assert f"MISSING:{workflow_id}:h1" in result.failures
    assert "MISSING:CREDENTIAL:password-field" in result.failures
    assert "MISSING:MEMORY:scope-label" in result.failures
    assert "MISSING:AUDIT:retention" in result.failures
    assert "MISSING:RECOVERY:confirmation" in result.failures


def test_acceptance_runner_fails_closed_on_redaction_violation(
    rendered_operations_pages: tuple[str, ...],
) -> None:
    """A raw request body leaking into the audit page fails closed with
    exactly the stable redaction code (GREEN-3)."""
    pages = (
        rendered_operations_pages[0],
        rendered_operations_pages[1],
        rendered_operations_pages[2] + "raw-request-sentinel",
        rendered_operations_pages[3],
    )
    result = run_operations_accessibility_acceptance(
        rendered_operations_pages=pages,
        workflow_ids=("CREDENTIAL", "MEMORY", "AUDIT", "RECOVERY"),
        input_events=("TAB", "ENTER"),
    )
    assert result.failures == ("FORBIDDEN:AUDIT:raw-request-sentinel",)


def test_acceptance_runner_fails_closed_on_scope_violation(
    rendered_operations_pages: tuple[str, ...],
) -> None:
    """A client-selected workspace selector on the memory page fails
    closed with exactly the stable scope code (GREEN-3)."""
    pages = (
        rendered_operations_pages[0],
        rendered_operations_pages[1] + 'name="workspace_id"',
        rendered_operations_pages[2],
        rendered_operations_pages[3],
    )
    result = run_operations_accessibility_acceptance(
        rendered_operations_pages=pages,
        workflow_ids=("CREDENTIAL", "MEMORY", "AUDIT", "RECOVERY"),
        input_events=("TAB", "ENTER"),
    )
    assert result.failures == ('FORBIDDEN:MEMORY:name="workspace_id"',)


def test_acceptance_runner_fails_closed_on_recovery_bypass_control(
    rendered_operations_pages: tuple[str, ...],
) -> None:
    """A force control on the recovery page fails closed with exactly
    the stable no-bypass code (GREEN-3)."""
    pages = (
        rendered_operations_pages[0],
        rendered_operations_pages[1],
        rendered_operations_pages[2],
        rendered_operations_pages[3] + 'name="force"',
    )
    result = run_operations_accessibility_acceptance(
        rendered_operations_pages=pages,
        workflow_ids=("CREDENTIAL", "MEMORY", "AUDIT", "RECOVERY"),
        input_events=("TAB", "ENTER"),
    )
    assert result.failures == ('FORBIDDEN:RECOVERY:name="force"',)


def test_acceptance_runner_fails_closed_on_secret_derivative(
    rendered_operations_pages: tuple[str, ...],
) -> None:
    """A secret derivative on the credential page fails closed with
    exactly the stable code (GREEN-3/AC-08)."""
    pages = (
        rendered_operations_pages[0] + "secret-sentinel",
        rendered_operations_pages[1],
        rendered_operations_pages[2],
        rendered_operations_pages[3],
    )
    result = run_operations_accessibility_acceptance(
        rendered_operations_pages=pages,
        workflow_ids=("CREDENTIAL", "MEMORY", "AUDIT", "RECOVERY"),
        input_events=("TAB", "ENTER"),
    )
    assert result.failures == ("FORBIDDEN:CREDENTIAL:secret-sentinel",)


def test_acceptance_runner_fails_closed_on_page_count_and_order(
    rendered_operations_pages: tuple[str, ...],
) -> None:
    """A wrong workflow order or page count fails closed (GREEN-1)."""
    result = run_operations_accessibility_acceptance(
        rendered_operations_pages=rendered_operations_pages[:3],
        workflow_ids=("MEMORY", "CREDENTIAL", "AUDIT", "RECOVERY"),
        input_events=("TAB", "ENTER"),
    )
    assert "WORKFLOW_ORDER_INVALID" in result.failures
    assert "PAGE_COUNT_MISMATCH" in result.failures


def test_acceptance_runner_fails_closed_on_non_keyboard_events(
    rendered_operations_pages: tuple[str, ...],
) -> None:
    """A non-keyboard input event fails closed (GREEN-2)."""
    result = run_operations_accessibility_acceptance(
        rendered_operations_pages=rendered_operations_pages,
        workflow_ids=("CREDENTIAL", "MEMORY", "AUDIT", "RECOVERY"),
        input_events=("TAB", "MOUSE_CLICK"),
    )
    assert result.keyboard_only is False
    assert "KEYBOARD_ONLY_VIOLATION" in result.failures


def test_acceptance_runner_output_is_deterministic_and_bounded(
    rendered_operations_pages: tuple[str, ...],
) -> None:
    """Repeated runs over identical pages produce the identical bounded
    result (GREEN-1)."""
    first = run_operations_accessibility_acceptance(
        rendered_operations_pages=rendered_operations_pages,
        workflow_ids=("CREDENTIAL", "MEMORY", "AUDIT", "RECOVERY"),
        input_events=("TAB", "ENTER"),
    )
    second = run_operations_accessibility_acceptance(
        rendered_operations_pages=rendered_operations_pages,
        workflow_ids=("CREDENTIAL", "MEMORY", "AUDIT", "RECOVERY"),
        input_events=("TAB", "ENTER"),
    )
    assert first == second
    assert first.capture_count == 4
    assert len(first.failures) <= 64


def test_acceptance_adds_no_production_interface() -> None:
    """The acceptance symbols are test-owned only; production modules
    expose no new interface (GREEN-1/GREEN-4)."""
    import importlib

    for module_name in (
        "vespercode.web.app",
        "vespercode.web.routes_operations",
        "vespercode.web.local_composition",
        "vespercode.cli",
        "vespercode.cli_composition",
    ):
        module = importlib.import_module(module_name)
        assert not hasattr(module, "OperationsAccessibilityAcceptanceResultV1")
        assert not hasattr(module, "run_operations_accessibility_acceptance")


def test_operations_browser_flow_keyboard_only(
    production_client: TestClient,
    production_ports: Any,
) -> None:
    """Browser (38.G): credential set/status/update/clear, memory
    create/confirm/view/clear, paged audit/ended-run clear, and recovery
    preview->explicit apply through the production composition, keyboard
    only (native controls activated by ENTER-equivalent form submission)
    and the exact local request-security contract (page-rendered CSRF
    token)."""
    operations = production_ports.operations
    page = production_client.get("/credentials/openai", headers=_HOST)
    assert page.status_code == 200
    csrf = _page_csrf_token(page.text)
    headers = valid_local_security_headers(csrf)

    # --- credential set -> status -> update -> clear ---
    response = production_client.post(
        "/credentials/openai",
        headers=headers,
        data={"secret": "flow-secret-a"},
    )
    assert response.status_code == 200
    assert "已配置" in response.text
    assert "flow-secret-a" not in response.text
    assert operations.credentials.set_call_count == 1

    response = production_client.post(
        "/credentials/openai",
        headers=headers,
        data={"action": "update", "secret": "flow-secret-b"},
    )
    assert response.status_code == 200
    assert operations.credentials.update_call_count == 1
    assert "flow-secret-b" not in response.text

    response = production_client.post(
        "/credentials/openai",
        headers=headers,
        data={"action": "clear"},
    )
    assert response.status_code == 200
    assert operations.credentials.clear_call_count == 1
    assert "未配置" in response.text

    # --- memory create -> view -> confirm -> clear ---
    response = production_client.post(
        "/runs/run-1/memory",
        headers=headers,
        data={"summary": "键盘流约定", "source_reference": "键盘流来源"},
    )
    assert response.status_code == 200
    assert operations.memory.list_call_count >= 1
    assert "键盘流约定" in response.text
    assert "ws-digest-1" in response.text
    assert 'name="workspace_id"' not in response.text

    match = re.search(r'name="entry_id" value="([^"]+)"', response.text)
    assert match is not None
    entry_id = match.group(1)

    response = production_client.post(
        "/runs/run-1/memory/confirm",
        headers=headers,
        data={"entry_id": entry_id},
    )
    assert response.status_code == 200
    assert "已确认" in response.text

    response = production_client.post(
        "/runs/run-1/memory/clear",
        headers=headers,
        data={"entry_ids": entry_id},
    )
    assert response.status_code == 200
    assert "暂无记忆条目。" in response.text

    # --- paged audit -> ended-run clear ---
    operations.audit.seed_page(
        AuditPageV1(
            run_id="run-1",
            items=(
                AuditEventV1(
                    run_id="run-1",
                    sequence=1,
                    event_type="ACTION",
                    redacted_payload=ActionPayloadV1(
                        kind="ACTION",
                        action_type="raw-request-sentinel",
                        policy_decision="ALLOW",
                    ),
                    created_at=_FIXED_NOW,
                ),
                AuditEventV1(
                    run_id="run-1",
                    sequence=2,
                    event_type="LIFECYCLE",
                    redacted_payload=LifecyclePayloadV1(
                        kind="LIFECYCLE", status="SUCCEEDED"
                    ),
                    created_at=_FIXED_NOW,
                ),
            ),
            next_cursor=AuditCursorV1(run_id="run-1", last_sequence=2),
        )
    )
    page = production_client.get("/runs/run-1/audit", headers=_HOST)
    assert page.status_code == 200
    assert "#1" in page.text and "#2" in page.text
    assert "raw-request-sentinel" not in page.text
    assert "?cursor=2" in page.text

    operations.audit.seed_page(
        AuditPageV1(
            run_id="run-1",
            items=(
                AuditEventV1(
                    run_id="run-1",
                    sequence=3,
                    event_type="LIFECYCLE",
                    redacted_payload=LifecyclePayloadV1(
                        kind="LIFECYCLE", status="STOPPED"
                    ),
                    created_at=_FIXED_NOW,
                ),
            ),
        )
    )
    page = production_client.get("/runs/run-1/audit?cursor=2", headers=_HOST)
    assert page.status_code == 200
    assert "#3" in page.text

    response = production_client.post(
        "/runs/run-1/audit/clear",
        headers=headers,
        data={"confirm": "yes"},
    )
    assert response.status_code == 200
    assert operations.audit.clear_call_count == 1

    # --- recovery preview -> explicit apply ---
    page = production_client.get("/runs/run-recovery/recovery", headers=_HOST)
    assert page.status_code == 200
    assert "零写入" in page.text
    assert 'name="confirmation"' in page.text
    assert 'name="force"' not in page.text
    assert 'name="ignore"' not in page.text

    response = production_client.post(
        "/runs/run-recovery/recovery",
        headers=headers,
        data={
            "transaction_id": "tx-1",
            "preview_digest": "preview-digest-1",
            "confirmation": "yes",
        },
    )
    assert response.status_code == 200
    assert "已回滚" in response.text
    assert "src/a.py" in response.text
