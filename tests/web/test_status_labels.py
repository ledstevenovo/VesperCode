"""T28.2 legacy step 28.B: local shell status-label and accessibility
tests.

The exact RED pins the smallest semantic status component (text plus
accessible name); the matrix pins the distinct unambiguous text and
accessible-name semantics of every closed state label plus the
keyboard/focus, live-error, non-color, contrast, and reduced-motion
properties of the rendered home page (SPEC §4.9 local mode, §5.3;
Registry row 28.B Expected line: exact status comprehension, escaped
template defaults, accessible names, and deterministic typed installer
order pass).
"""

from __future__ import annotations

from typing import cast

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from markupsafe import Markup

from src.vespercode.audit.projection import RunVisibilityV1, StateLabelV1
from src.vespercode.contracts.optional import AbsentV1
from src.vespercode.credentials.port import CredentialStatusV1
from src.vespercode.web.app import (
    LocalRouteInstallerSequenceV1,
    LocalShellPortsV1,
    RunVisibilitySequenceV1,
    STATUS_TEXT_V1,
    create_local_app,
    render_status_badge,
)
from src.vespercode.web.security import LocalWebSecurityConfigV1

_EPOCH_MS = 1_783_500_000_000

_STATUS_EXPECTATIONS_V1: dict[str, str] = {
    # The card's exact RED names the waiting-for-user-decision semantic
    # "WAITING_APPROVAL"; the closed SPEC §4.9 label for that state is
    # WAITING_USER (Task 23.1 closed StateLabelV1).  The alias maps the
    # plan author's informal name to the closed label so the byte-identical
    # RED body pins the rendered badge for the waiting state.
    "WAITING_APPROVAL": "WAITING_USER",
}

_ALL_STATE_LABELS_V1: tuple[StateLabelV1, ...] = (
    "CREATED",
    "PREFLIGHT",
    "BASELINE",
    "AGENT_LOOP",
    "FORMAL_VALIDATION",
    "PERSISTENCE",
    "WAITING_USER",
    "RECOVERY_REQUIRED",
    "SUCCEEDED",
    "STOPPED",
)
"""The exact closed §4.9 label set (mirrors Task 23.1's StateLabelV1)."""


def valid_local_security_headers() -> dict[str, str]:
    """One valid loopback request-header set for the local shell."""
    return {"Host": "127.0.0.1:8765"}


def assert_status_badge_contract(html_text: str, expected_status: str) -> None:
    """Assert the rendered status badge for one expected status.

    The badge must carry the exact unambiguous state-label text, an
    accessible name (``aria-label`` with the 状态： prefix), and a
    non-color cue element alongside the text (SPEC §4.9/§5.3: status is
    never conveyed by color alone).
    """
    state_label = _STATUS_EXPECTATIONS_V1.get(expected_status, expected_status)
    assert 'class="status-badge"' in html_text
    assert state_label in html_text
    assert "aria-label" in html_text
    assert "状态：" in html_text
    assert 'class="status-dot"' in html_text


def waiting_visibility(run_id: str = "run-1") -> RunVisibilityV1:
    """One waiting-for-user-decision run visibility (the card's
    WAITING_APPROVAL semantic under the closed §4.9 label)."""
    return RunVisibilityV1(
        run_id=run_id,
        state_label="WAITING_USER",
        reason_code="USER_DECISION_PENDING",
        next_action="AWAIT_USER_DECISION",
        evidence_refs=(),
    )


def credential_status() -> CredentialStatusV1:
    """One non-revealing credential status (SPEC §4.8)."""
    return CredentialStatusV1(
        schema_version=1,
        provider="OPENAI",
        configured=False,
        updated_at=AbsentV1(kind="ABSENT"),
    )


class FakeShellPortsV1:
    """One fake typed shell port implementation (test-owned)."""

    def __init__(self, runs: RunVisibilitySequenceV1) -> None:
        self._runs = runs

    def list_recent_runs(self) -> RunVisibilitySequenceV1:
        return self._runs

    def credential_status(self) -> CredentialStatusV1:
        return credential_status()


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
    shell_ports: LocalShellPortsV1 = FakeShellPortsV1((waiting_visibility(),))
    installers: LocalRouteInstallerSequenceV1 = ()
    app = create_local_app(shell_ports, security_config, installers)
    return TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")


def test_status_badge_has_text_and_accessible_name(
    local_web_client: TestClient,
) -> None:
    response = local_web_client.get("/", headers=valid_local_security_headers())
    assert_status_badge_contract(response.text, expected_status="WAITING_APPROVAL")


def test_status_component_accessibility_matrix(
    local_web_client: TestClient,
    security_config: LocalWebSecurityConfigV1,
) -> None:
    """The exact status/accessibility matrix (Expected 28.B).

    Every closed state label renders a distinct text plus accessible-name
    badge; the home page renders the waiting run's badge with keyboard
    reachability, live-error hooks, non-color cues, sufficient contrast,
    and reduced-motion-safe behavior; the template environment
    autoescapes by default.
    """
    client = local_web_client
    app = cast(FastAPI, client.app)

    # --- every closed label has a distinct text plus accessible name ---
    rendered_texts: list[str] = []
    for state_label in _ALL_STATE_LABELS_V1:  # the closed 10-label set
        visibility = waiting_visibility().model_copy(
            update={"run_id": f"run-{state_label}", "state_label": state_label}
        )
        badge = render_status_badge(visibility)
        assert isinstance(badge, Markup)
        html = str(badge)
        assert 'class="status-badge"' in html
        assert state_label in html
        assert "aria-label" in html
        assert "状态：" in html
        assert 'class="status-dot"' in html
        assert f"run-{state_label}" not in html  # the badge never leaks the run id
        rendered_texts.append(html)
    assert len(set(rendered_texts)) == len(_ALL_STATE_LABELS_V1)
    assert set(STATUS_TEXT_V1) == set(_ALL_STATE_LABELS_V1)
    assert len({STATUS_TEXT_V1[label] for label in _ALL_STATE_LABELS_V1}) == len(
        _ALL_STATE_LABELS_V1
    )

    # --- the home page renders the waiting badge with the exact labels ---
    response = client.get("/", headers=valid_local_security_headers())
    assert response.status_code == 200
    text = response.text
    assert_status_badge_contract(text, expected_status="WAITING_APPROVAL")
    assert "WAITING_USER" in text
    assert "等待用户决定" in text
    assert "run-1" in text

    # --- keyboard reachability and visible focus ---
    assert "button" in text
    assert ":focus-visible" in text
    assert "outline" in text

    # --- live-error hooks: assertive live region ---
    assert 'id="live-error"' in text
    assert "aria-live" in text
    assert 'role="alert"' in text

    # --- non-color status and sufficient contrast declarations ---
    assert "status-dot" in text  # the color cue
    assert "等待用户决定" in text  # the text cue (never color-only)
    assert "--text: #1a1a1a" in text
    assert "--background: #f7f5f0" in text
    assert "--banner-bg: #101418" in text
    assert "--banner-text: #ffffff" in text

    # --- reduced-motion-safe behavior ---
    assert "prefers-reduced-motion" in text
    assert "animation: none" in text

    # --- credential status renders non-revealing text ---
    assert "凭据状态" in text
    assert "未配置" in text
    assert "OPENAI" in text
    assert "secret" not in text

    # --- escaped template defaults: the Jinja environment autoescapes ---
    templates = app.state.local_templates
    assert templates.env.autoescape

    # --- the security integration: the shell still enforces 28.A ---
    rejected = client.get("/", headers={"Host": "evil.example"})
    assert rejected.status_code == 403
    assert rejected.json()["error_code"] == "HOST_REJECTED"

    # --- the security headers attach to shell responses ---
    assert response.headers["content-security-policy"].startswith("default-src 'self'")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
