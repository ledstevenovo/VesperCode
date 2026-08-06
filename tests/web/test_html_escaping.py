"""T28.2 legacy step 28.C: escaped rendering and local-asset tests.

The exact RED pins the smallest local-asset and escaped-render contract
(untrusted run text is escaped, HTMX is served locally, and no script
source is remote); the matrix pins the escaped render, the exact CSP
(with the per-request nonce and no ``unsafe-inline`` script bypass), the
keyboard/live-error hooks, the local-only packaged asset identity, and
zero CDN/network fallback (SPEC §4.9, §5.3, §5.5; Registry row 28.C
Expected line: packaged asset identity/loading, autoescaping, CSP,
accessibility hooks, and zero external asset request pass).
"""

from __future__ import annotations

import re
from typing import cast

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.vespercode.audit.projection import RunVisibilityV1
from src.vespercode.contracts.optional import AbsentV1
from src.vespercode.credentials.port import CredentialStatusV1
from src.vespercode.web.app import (
    LocalRouteInstallerSequenceV1,
    LocalShellPortsV1,
    PackagedWebAssetErrorV1,
    RunVisibilitySequenceV1,
    create_local_app,
    install_packaged_web_assets,
    load_packaged_web_asset,
)
from src.vespercode.web.security import LocalWebSecurityConfigV1

_UNTRUSTED_RUN_TEXT_V1 = "<script>alert(1)</script>"
"""The exact untrusted run text the exact RED renders (SPEC §4.9:
untrusted text is rendered as plain text or safely escaped, never
executed as repository HTML)."""

_ESCAPED_UNTRUSTED_RUN_TEXT_V1 = "&lt;script&gt;alert(1)&lt;/script&gt;"
"""The exact escaped form the rendered page must carry."""

_SCRIPT_SRC_RE = re.compile(r'<script[^>]*\bsrc="([^"]+)"')


def extract_script_sources(html_text: str) -> list[str]:
    """One closed extraction of every script ``src`` in rendered HTML."""
    return _SCRIPT_SRC_RE.findall(html_text)


def valid_local_security_headers() -> dict[str, str]:
    """One valid loopback request-header set for the local shell."""
    return {"Host": "127.0.0.1:8765"}


def untrusted_visibility() -> RunVisibilityV1:
    """One run visibility carrying the exact untrusted run text."""
    return RunVisibilityV1(
        run_id=_UNTRUSTED_RUN_TEXT_V1,
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
    shell_ports: LocalShellPortsV1 = FakeShellPortsV1((untrusted_visibility(),))
    installers: LocalRouteInstallerSequenceV1 = ()
    app = create_local_app(shell_ports, security_config, installers)
    install_packaged_web_assets(app)
    return TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")


def test_untrusted_run_text_is_escaped_and_htmx_is_local(
    local_web_client: TestClient,
) -> None:
    response = local_web_client.get("/", headers=valid_local_security_headers())
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert 'src="/static/htmx.min.js"' in response.text
    assert "https://" not in extract_script_sources(response.text)


def test_web_escape_asset_csp_matrix(
    local_web_client: TestClient,
    security_config: LocalWebSecurityConfigV1,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact escape/asset/CSP matrix (Expected 28.C).

    Untrusted text is autoescaped everywhere it renders, the packaged
    HTMX asset is served from the sole local static path with its exact
    declared identity and zero external sources, the CSP carries the
    per-request nonce without any ``unsafe-inline`` script bypass, and
    the keyboard/focus/live-error hooks remain present.
    """
    client = local_web_client
    app = cast(FastAPI, client.app)

    # --- the untrusted run text renders escaped, never as markup ---
    response = client.get("/", headers=valid_local_security_headers())
    assert response.status_code == 200
    text = response.text
    assert "<script>alert(1)</script>" not in text
    assert _ESCAPED_UNTRUSTED_RUN_TEXT_V1 in text
    assert "&lt;" in text and "&gt;" in text
    assert "onerror=" not in text

    # --- the only script source is the sole local static path ---
    sources = extract_script_sources(text)
    assert sources == ["/static/htmx.min.js"]
    assert "https://" not in text
    assert "http://" not in text

    # --- the packaged asset identity and local serving ---
    asset = load_packaged_web_asset("htmx.min.js")
    assert asset.name == "htmx.min.js"
    assert asset.version == "2.0.4"
    assert asset.sha256 == (
        "e209dda5c8235479f3166defc7750e1dbcd5a5c1808b7792fc2e6733768fb447"
    )
    assert asset.byte_length == 50917
    assert asset.content_type == "application/javascript"
    assert b"var htmx=function()" in asset.content
    assert b'version:"2.0.4' in asset.content
    served = client.get("/static/htmx.min.js")
    assert served.status_code == 200
    assert served.headers["content-type"] == "application/javascript"
    assert served.content == asset.content
    assert served.headers["x-content-type-options"] == "nosniff"

    # --- the exact CSP: per-request nonce, no unsafe-inline script ---
    csp = response.headers["content-security-policy"]
    assert csp.startswith("default-src 'self'; ")
    assert "script-src 'self' 'nonce-" in csp
    assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "object-src 'none'" in csp
    assert "base-uri 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "form-action 'self'" in csp
    header_nonce = re.search(r"'nonce-([A-Za-z0-9_-]{16,128})'", csp)
    assert header_nonce is not None
    assert f'nonce="{header_nonce.group(1)}"' in text
    # the static asset response carries the nonce-less exact CSP
    static_csp = served.headers["content-security-policy"]
    assert static_csp == (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
        "form-action 'self'"
    )

    # --- keyboard/focus and live-error hooks (28.C GREEN-2) ---
    assert 'id="refresh-runs"' in text
    assert ":focus-visible" in text
    assert 'id="live-error"' in text
    assert "aria-live" in text
    assert 'role="alert"' in text
    assert "htmx:responseError" in text  # the live-error hook wiring
    assert "htmx:sendError" in text
    # the refresh swaps only the #content region (hx-select), so the
    # hook script below it is never re-inserted with a stale nonce and
    # the live-error listeners survive refreshes
    assert 'hx-target="#content"' in text
    assert 'hx-select="#content"' in text
    assert text.index("<script nonce=") > text.index("</main>")

    # --- zero CDN/network fallback: the page and the asset never
    # reference a remote host (the packaged file itself is fully
    # self-contained with no URL strings at all) ---
    assert "https://" not in extract_script_sources(text)
    assert b"https://" not in asset.content
    assert app.state.local_packaged_assets is True

    # --- the closed asset name rejects unknown values ---
    with pytest.raises(PackagedWebAssetErrorV1):
        load_packaged_web_asset("cdn.js")  # type: ignore[arg-type]

    # --- identity drift fails closed ---
    import src.vespercode.web.app as app_module

    monkeypatch.setattr(app_module, "_PACKAGED_HTMX_SHA256_V1", "00" * 32)
    with pytest.raises(PackagedWebAssetErrorV1, match="identity mismatch"):
        app_module.load_packaged_web_asset("htmx.min.js")
