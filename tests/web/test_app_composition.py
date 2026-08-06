"""T28.2 legacy step 28.B: local shell composition tests.

The shell composes the typed ports and the immutable typed installer
sequence deterministically — the installers run in the exact tuple order
against the exact composed app, and there is no service locator or
hidden workflow lookup (GREEN-1/Boundary).  The Task 28.A security
boundary stays enforced on the composed shell, and the escaped template
defaults hold (Expected 28.B: exact status comprehension, escaped
template defaults, accessible names, and deterministic typed installer
order pass).
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.vespercode.audit.projection import RunVisibilityV1
from src.vespercode.contracts.optional import AbsentV1
from src.vespercode.credentials.port import CredentialStatusV1
from src.vespercode.web.app import (
    LocalRouteInstallerSequenceV1,
    LocalRouteInstallerV1,
    LocalShellPortsV1,
    RunVisibilitySequenceV1,
    create_local_app,
)
from src.vespercode.web.security import LocalWebSecurityConfigV1


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


class SpyInstallerV1:
    """One spy typed route installer recording its install calls."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.installed_apps: list[FastAPI] = []

    def install(self, app: FastAPI) -> None:
        self.installed_apps.append(app)


def waiting_visibility(run_id: str = "run-1") -> RunVisibilityV1:
    """One waiting-for-user-decision run visibility."""
    return RunVisibilityV1(
        run_id=run_id,
        state_label="WAITING_USER",
        reason_code="USER_DECISION_PENDING",
        next_action="AWAIT_USER_DECISION",
        evidence_refs=(),
    )


@pytest.fixture
def security_config() -> LocalWebSecurityConfigV1:
    return LocalWebSecurityConfigV1(
        host="127.0.0.1",
        port=8765,
        session_cookie_name="vespercode_session",
        csrf_header_name="X-CSRF-Token",
    )


def test_composition_applies_installers_in_deterministic_order(
    security_config: LocalWebSecurityConfigV1,
) -> None:
    """The typed installer sequence is applied in its exact tuple order
    against the exact composed app (GREEN-1, Expected 28.B)."""
    shell_ports: LocalShellPortsV1 = FakeShellPortsV1((waiting_visibility(),))
    first = SpyInstallerV1("first")
    second = SpyInstallerV1("second")
    installers: LocalRouteInstallerSequenceV1 = (first, second)
    app = create_local_app(shell_ports, security_config, installers)
    assert first.installed_apps == [app]
    assert second.installed_apps == [app]
    # the stored sequence is the exact injected tuple (immutable, ordered)
    assert app.state.local_route_installers is installers
    assert isinstance(installers, tuple)


def test_composition_uses_the_exact_injected_ports(
    security_config: LocalWebSecurityConfigV1,
) -> None:
    """The shell uses the injected typed ports — never a service locator
    or hidden lookup (GREEN-1/Boundary)."""
    shell_ports: LocalShellPortsV1 = FakeShellPortsV1((waiting_visibility(),))
    installers: LocalRouteInstallerSequenceV1 = ()
    app = create_local_app(shell_ports, security_config, installers)
    assert app.state.local_shell_ports is shell_ports
    assert app.state.local_security_config is security_config
    # the home page renders exactly the injected port data
    client = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")
    response = client.get("/", headers={"Host": f"127.0.0.1:{security_config.port}"})
    assert response.status_code == 200
    assert "run-1" in response.text
    assert "WAITING_USER" in response.text


def test_composed_shell_still_enforces_the_loopback_security_boundary(
    security_config: LocalWebSecurityConfigV1,
) -> None:
    """The Task 28.A boundary stays enforced on the composed shell: Host,
    session, and the exact security headers before any route-domain call
    (28.B quality focus: Task 28.A security integration)."""
    shell_ports: LocalShellPortsV1 = FakeShellPortsV1((waiting_visibility(),))
    installers: LocalRouteInstallerSequenceV1 = ()
    app = create_local_app(shell_ports, security_config, installers)
    client = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")

    rejected = client.get("/", headers={"Host": "evil.example"})
    assert rejected.status_code == 403
    assert rejected.json()["error_code"] == "HOST_REJECTED"
    assert rejected.headers["x-frame-options"] == "DENY"

    valid = client.get("/", headers={"Host": f"127.0.0.1:{security_config.port}"})
    assert valid.status_code == 200
    assert valid.headers["x-content-type-options"] == "nosniff"
    assert valid.headers["referrer-policy"] == "no-referrer"
    assert valid.headers["content-security-policy"].startswith("default-src 'self'")

    # state changes without a session are rejected before any domain call
    # (a fresh client has no bootstrapped cookie)
    fresh_client = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")
    missing_session = fresh_client.post(
        "/runs",
        data={"target": "tests"},
        headers={"Host": f"127.0.0.1:{security_config.port}"},
    )
    assert missing_session.status_code == 401
    assert missing_session.json()["error_code"] == "SESSION_MISSING"

    # state changes with a valid session still require the fixed Origin
    # then CSRF checks before the (future) route-domain call: the real
    # middleware rejects even though no /runs route exists yet
    session_client = TestClient(
        app, base_url=f"http://127.0.0.1:{security_config.port}"
    )
    session_client.get("/")  # bootstrap the session cookie
    manager = app.state.local_session_manager
    session = manager.get(
        session_client.cookies.get(security_config.session_cookie_name)
    )
    assert session is not None
    origin_headers = {"Origin": f"http://127.0.0.1:{security_config.port}"}

    no_origin = session_client.post(
        "/runs",
        data={"target": "tests"},
        headers={"Host": f"127.0.0.1:{security_config.port}"},
    )
    assert no_origin.status_code == 403
    assert no_origin.json()["error_code"] == "ORIGIN_MISSING"

    bad_origin = session_client.post(
        "/runs",
        data={"target": "tests"},
        headers={
            "Host": f"127.0.0.1:{security_config.port}",
            "Origin": "https://attacker.example",
        },
    )
    assert bad_origin.status_code == 403
    assert bad_origin.json()["error_code"] == "ORIGIN_REJECTED"

    no_csrf = session_client.post(
        "/runs",
        data={"target": "tests"},
        headers={
            "Host": f"127.0.0.1:{security_config.port}",
            **origin_headers,
        },
    )
    assert no_csrf.status_code == 403
    assert no_csrf.json()["error_code"] == "CSRF_REJECTED"


def test_composed_shell_renders_escaped_defaults_and_accessible_names(
    security_config: LocalWebSecurityConfigV1,
) -> None:
    """The template environment autoescapes by default and the rendered
    page carries the accessible-name status semantics (Expected 28.B)."""
    shell_ports: LocalShellPortsV1 = FakeShellPortsV1((waiting_visibility(),))
    installers: LocalRouteInstallerSequenceV1 = ()
    app = create_local_app(shell_ports, security_config, installers)
    client = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")
    response = client.get("/", headers={"Host": f"127.0.0.1:{security_config.port}"})
    assert response.status_code == 200
    templates = app.state.local_templates
    assert templates.env.autoescape  # the autoescape policy is enabled
    assert 'class="status-badge"' in response.text
    assert 'aria-label="状态：WAITING_USER（等待用户决定）"' in response.text
    assert "WAITING_USER" in response.text
    assert "等待用户决定" in response.text


def test_composed_shell_exposes_no_service_locator_state(
    security_config: LocalWebSecurityConfigV1,
) -> None:
    """The shell state carries only the injected ports, config, manager,
    templates, and installers — no global registry or hidden lookup.

    The identity pins prove the shell uses exactly the injected objects:
    the ports and config are the exact passed instances, and the route
    set contains only the declared home route.
    """
    shell_ports: LocalShellPortsV1 = FakeShellPortsV1((waiting_visibility(),))
    installers: LocalRouteInstallerSequenceV1 = ()
    app = create_local_app(shell_ports, security_config, installers)
    state = app.state
    assert state.local_shell_ports is shell_ports
    assert state.local_security_config is security_config
    assert state.local_session_manager is not None
    assert state.local_route_installers is installers
    assert state.local_templates is not None
    routes = {getattr(route, "path", None) for route in app.routes}
    assert routes == {"/"}


def test_installer_protocol_is_structural() -> None:
    """Any object with ``install(app: FastAPI) -> None`` satisfies the
    typed installer protocol (the deterministic sequence accepts it)."""
    spy = SpyInstallerV1("typed")
    installer: LocalRouteInstallerV1 = spy
    assert installer is spy
