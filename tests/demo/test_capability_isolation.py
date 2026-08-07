"""T30.2 legacy step 30.B: public Demo app capability-isolation tests.

The exact displayed RED test ``test_demo_app_registers_no_formal_capability_adapter``
is copied from the T30.2 card (the final assert line is 92 characters and
ruff-wrapped with unchanged semantics per the T17.1/T24.1 precedent-class
comment).  The already-RED matrix test ``test_demo_app_capability_matrix``
pins the PLAN 30.B row: health validates assets/registry, PORT boundaries
hold, and forbidden capabilities/endpoints remain absent.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vespercode.demo.app import (
    DEMO_CAPABILITY_KINDS_V1,
    DemoAppConfigV1,
    create_demo_app,
)
from vespercode.demo.scenario import FIXED_DEMO_SCENARIO_V1


@pytest.fixture
def demo_app() -> FastAPI:
    return create_demo_app(DemoAppConfigV1(port=8080))


@pytest.fixture
def demo_client(demo_app: FastAPI) -> TestClient:
    return TestClient(demo_app)


def test_demo_app_registers_no_formal_capability_adapter(
    demo_app: FastAPI,
) -> None:
    # The card's displayed final assert is 96 characters; ruff-wrapped with
    # the same semantics per the T17.1/T24.1 precedent-class comment.
    assert demo_app.state.capability_kinds == {
        "DEMO_EXECUTOR",
        "DEMO_SESSION",
        "DEMO_RENDERER",
    }


def _advance_full_scenario(client: TestClient, session_id: str) -> dict[str, object]:
    """Advance the whole fixed scenario through the app routes."""
    step: dict[str, object] = {}
    for index in range(6):
        body: dict[str, object] = {}
        if index == 4:
            body = {"decision": "REJECT"}
        elif index == 5:
            body = {"decision": "APPROVE"}
        response = client.post(f"/demo/sessions/{session_id}/advance", json=body)
        assert response.status_code == 200
        step = response.json()
    return step


def test_demo_app_capability_matrix(demo_app: FastAPI, demo_client: TestClient) -> None:
    """PLAN 30.B row: health validates assets/registry, PORT boundaries
    hold, and forbidden capabilities/endpoints remain absent.
    """
    # The exact fixed-simulation capability registry.
    assert demo_app.state.capability_kinds == DEMO_CAPABILITY_KINDS_V1
    # The closed route set: health, the page, and the two demo routes —
    # no credential, Docker, persistence, recovery, or formal Run route.
    # mypy's starlette typing sees BaseRoute without ``path``; the
    # closed route surface is the app's registered API surface.
    routes = sorted(route.path for route in demo_app.routes)  # type: ignore[attr-defined]
    assert routes == [
        "/",
        "/demo/sessions",
        "/demo/sessions/{session_id}/advance",
        "/healthz",
    ]
    # Health and the closed demo flow work end to end.
    health = demo_client.get("/healthz")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "mode": "simulation"}
    created = demo_client.post("/demo/sessions")
    assert created.status_code == 201
    session = created.json()
    assert session["session"]["scenario_version"] == 1
    advance = demo_client.post(
        f"/demo/sessions/{session['demo_session_id']}/advance", json={}
    )
    assert advance.status_code == 200
    assert advance.json()["status"] in (
        "DEMO_CREATED",
        "DEMO_RUNNING",
        "DEMO_WAITING_USER",
        "DEMO_COMPLETED",
        "DEMO_FAILED",
    )
    # The fixed scenario data is served escaped on the page.
    page = demo_client.get("/")
    assert page.status_code == 200
    assert FIXED_DEMO_SCENARIO_V1.source in page.text
    assert FIXED_DEMO_SCENARIO_V1.expected_patch in page.text
    # An unknown session rejects closed (no partial result).
    missing = demo_client.post("/demo/sessions/does-not-exist/advance", json={})
    assert missing.status_code == 404
    # A full fresh run ends in the Demo-only terminal status (never a
    # formal RunStatus), and a completed session is discarded.
    second = demo_client.post("/demo/sessions").json()
    completed = _advance_full_scenario(demo_client, second["demo_session_id"])
    assert completed["status"] == "DEMO_COMPLETED"
    after_completion = demo_client.post(
        f"/demo/sessions/{second['demo_session_id']}/advance", json={}
    )
    assert after_completion.status_code == 404


def test_demo_app_rejects_wrong_writeback_decisions(
    demo_client: TestClient,
) -> None:
    """The writeback step advances only through the exact fixed visitor
    decision; a wrong decision rejects closed with the stable code and
    never forms a formal approval."""
    created = demo_client.post("/demo/sessions").json()
    session_id = created["demo_session_id"]
    for _ in range(4):
        response = demo_client.post(f"/demo/sessions/{session_id}/advance", json={})
        assert response.status_code == 200
    wrong = demo_client.post(
        f"/demo/sessions/{session_id}/advance", json={"decision": "APPROVE"}
    )
    assert wrong.status_code == 400
    assert wrong.json()["detail"] == "DEMO_DECISION_MISMATCH"
    rejected = demo_client.post(
        f"/demo/sessions/{session_id}/advance", json={"decision": "REJECT"}
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "DEMO_WAITING_USER"


def test_demo_app_config_port_boundaries() -> None:
    """The validated platform PORT: 1..65535 holds, everything else
    rejects closed (SPEC §8.3 platform PORT handling)."""
    from pydantic import ValidationError

    for port in (1, 65535):
        assert DemoAppConfigV1(port=port).port == port
    invalid_ports: tuple[object, ...] = (0, 65536, -1, 70000, "8080", 80.5, True)
    for invalid_port in invalid_ports:
        with pytest.raises(ValidationError):
            DemoAppConfigV1(port=invalid_port)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        DemoAppConfigV1(port=8080, mode="formal")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        DemoAppConfigV1.model_validate({"port": 8080, "forbidden": "extra"})
