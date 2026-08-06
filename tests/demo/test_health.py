"""T30.2 legacy step 30.B: public Demo health tests.

``GET /healthz`` returns exactly ``{"status":"ok","mode":"simulation"}``
and ``healthcheck.main()`` verifies the platform PORT, the closed
capability registry, and the packaged template asset — the explicit
capability-absence verification of the headless Demo boundary (card
30.B Goal / SPEC §8.3).
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from src.vespercode.demo.app import (
    DEMO_CAPABILITY_KINDS_V1,
    DemoAppConfigV1,
    create_demo_app,
)
from src.vespercode.demo.healthcheck import main


@pytest.fixture
def demo_client() -> TestClient:
    return TestClient(create_demo_app(DemoAppConfigV1(port=8080)))


def test_healthz_returns_exact_simulation_payload(demo_client: TestClient) -> None:
    """GET /healthz -> 200 {"status":"ok","mode":"simulation"} (the exact
    card contract; the Demo is persistently labeled as simulation)."""
    response = demo_client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mode": "simulation"}


def test_healthcheck_main_verifies_port_registry_and_assets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """healthcheck.main() returns 0 only when the platform PORT is valid,
    the capability registry is the exact fixed set, and the packaged
    template asset renders (health validates assets/registry, PORT
    boundaries hold)."""
    monkeypatch.setenv("PORT", "8080")
    assert main() == 0


def test_healthcheck_main_rejects_invalid_platform_ports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PORT boundaries hold: missing, non-numeric, zero, and oversized
    platform ports fail the health boundary closed."""
    monkeypatch.delenv("PORT", raising=False)
    assert main() == 1
    for invalid in ("0", "-1", "70000", "8080.5", "abc", ""):
        monkeypatch.setenv("PORT", invalid)
        assert main() == 1


def test_healthcheck_main_fails_closed_on_missing_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The asset verification fails closed when the packaged template
    cannot render (health validates assets)."""
    monkeypatch.setenv("PORT", "8080")
    monkeypatch.setattr(
        "src.vespercode.demo.app._TEMPLATES_DIRECTORY",
        "does-not-exist",
    )
    assert main() == 1


def test_healthcheck_main_fails_closed_on_registry_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The registry verification fails closed when the app registers any
    capability outside the exact fixed simulation set."""
    monkeypatch.setenv("PORT", "8080")

    from src.vespercode.demo import healthcheck as healthcheck_module
    from src.vespercode.demo import app as demo_app_module

    original = demo_app_module.create_demo_app

    def drifted(config: DemoAppConfigV1) -> object:
        app = original(config)
        app.state.capability_kinds = frozenset(
            {"DEMO_EXECUTOR", "DEMO_SESSION", "DEMO_RENDERER", "FORMAL_CREDENTIALS"}
        )
        return app

    monkeypatch.setattr(healthcheck_module, "create_demo_app", drifted)
    assert main() == 1


def test_demo_responses_carry_the_closed_security_headers(
    demo_client: TestClient,
) -> None:
    """Every demo response carries the closed security headers (SPEC
    §4.9 security-header verification: nosniff, never framed, no
    referrer)."""
    for path in ("/", "/healthz"):
        response = demo_client.get(path)
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"


def test_healthz_payload_matches_the_config_mode(
    demo_client: TestClient,
) -> None:
    """The health payload's mode is the closed simulation mode of the
    frozen config (the app can never present as formal verification)."""
    response = demo_client.get("/healthz")
    assert response.json()["mode"] == "simulation"
    assert DEMO_CAPABILITY_KINDS_V1 == frozenset(
        {"DEMO_EXECUTOR", "DEMO_SESSION", "DEMO_RENDERER"}
    )
