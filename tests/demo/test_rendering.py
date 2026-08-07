"""T30.2 legacy step 30.B: public Demo page rendering tests.

The fixed-scenario page is rendered escaped with persistent simulation
labeling, keyboard/focus and live-error support, non-color status,
sufficient contrast, and reduced motion (card 30.B GREEN-2), and carries
no prompt, URL, repository, upload, provider, or secret input (SPEC
§4.9/§8.3).  All scenario text is fixed data rendered through Jinja
autoescape; the page has no text inputs at all.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vespercode.demo.app import (
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


def test_page_renders_the_escaped_fixed_scenario(
    demo_app: FastAPI, demo_client: TestClient
) -> None:
    """The page renders the fixed scenario data through the template
    autoescape (the template environment escapes by default) — the
    scenario texts appear as text, never as executable markup."""
    response = demo_client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    # The fixed scenario values are present as text.
    assert FIXED_DEMO_SCENARIO_V1.source in response.text
    assert FIXED_DEMO_SCENARIO_V1.injected_failure in response.text
    assert FIXED_DEMO_SCENARIO_V1.expected_patch in response.text
    for step in FIXED_DEMO_SCENARIO_V1.trace.steps:
        assert step.action_label in response.text
    # Escaping is on: the template environment autoescapes, and the page
    # never builds HTML from data (only text nodes).
    assert demo_app.state.demo.templates.env.autoescape


def test_page_is_persistently_simulation_labeled(
    demo_client: TestClient,
) -> None:
    """The page carries persistent simulation labeling in text — the Demo
    is never presented as a formal verification (SPEC §2.9/§4.9)."""
    response = demo_client.get("/")
    text = response.text
    assert "SIMULATION" in text
    assert "模拟" in text
    assert "非正式验证" in text


def test_page_supports_keyboard_focus_and_live_errors(
    demo_client: TestClient,
) -> None:
    """Keyboard/focus support: every control is a native button and a
    visible focus ring is declared; live-error support: an assertive
    aria-live alert region exists for live errors."""
    response = demo_client.get("/")
    text = response.text
    assert "button" in text
    assert ":focus-visible" in text
    assert "aria-live" in text
    assert 'role="alert"' in text
    assert 'id="live-error"' in text


def test_page_status_is_not_color_only_and_contrast_holds(
    demo_client: TestClient,
) -> None:
    """Status is conveyed as text, never color-only, and the declared
    colors have sufficient contrast (dark text on light backgrounds)."""
    response = demo_client.get("/")
    text = response.text
    assert "status-text" in text
    assert "状态" in text
    # The declared text/background pair is dark-on-light (sufficient
    # contrast) and the banner is light-on-dark.
    assert "--text: #1a1a1a" in text
    assert "--background: #f7f5f0" in text
    assert "--banner-bg: #101418" in text
    assert "--banner-text: #ffffff" in text


def test_page_respects_reduced_motion(demo_client: TestClient) -> None:
    """Reduced motion: a prefers-reduced-motion media query disables all
    animation and transition."""
    response = demo_client.get("/")
    assert "prefers-reduced-motion" in response.text
    assert "animation: none" in response.text


def test_page_buttons_map_to_the_fixed_visitor_decisions(
    demo_client: TestClient,
) -> None:
    """The page's keyboard-operable buttons drive exactly the fixed
    visitor decisions: the advance step sends no decision, and the
    writeback buttons send REJECT/APPROVE (the simulated choice only
    advances the fixed scenario, never a formal approval)."""
    response = demo_client.get("/")
    assert "advance(null)" in response.text
    assert 'advance("REJECT")' in response.text
    assert 'advance("APPROVE")' in response.text
    assert 'id="advance-step"' in response.text
    assert 'id="reject-writeback"' in response.text
    assert 'id="approve-writeback"' in response.text


def test_page_has_no_untrusted_input_surface(demo_client: TestClient) -> None:
    """No prompt, URL, repository, upload, provider, or secret input
    exists anywhere on the page (SPEC §4.9/§8.3)."""
    response = demo_client.get("/")
    assert "<input" not in response.text
    assert "<textarea" not in response.text
    assert "<form" not in response.text
    assert 'type="text"' not in response.text
    assert 'type="password"' not in response.text
    assert 'type="file"' not in response.text
    assert 'type="url"' not in response.text
