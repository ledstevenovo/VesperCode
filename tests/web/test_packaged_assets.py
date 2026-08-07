"""T28.2 legacy step 28.C: packaged-asset identity and serving tests.

The pinned packaged ``htmx.min.js`` is loaded only through immutable
package resources, its declared SHA-256 identity and byte length are
verified at every load (failing closed on drift or a missing file), and
the sole local static path serves exactly those bytes — no CDN, no
runtime download, and no other static route (28.C GREEN-1/GREEN-4;
Registry row 28.C Expected line: packaged asset identity/loading,
autoescaping, CSP, accessibility hooks, and zero external asset request
pass).
"""

from __future__ import annotations

import hashlib
import importlib.resources

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from vespercode.audit.projection import RunVisibilityV1
from vespercode.contracts.optional import AbsentV1
from vespercode.credentials.port import CredentialStatusV1
from vespercode.web import app as app_module
from vespercode.web.app import (
    LocalRouteInstallerSequenceV1,
    LocalShellPortsV1,
    PackagedWebAssetErrorV1,
    RunVisibilitySequenceV1,
    create_local_app,
    install_packaged_web_assets,
    load_packaged_web_asset,
)
from vespercode.web.security import LocalWebSecurityConfigV1

_PINNED_SHA256 = "e209dda5c8235479f3166defc7750e1dbcd5a5c1808b7792fc2e6733768fb447"
_PINNED_BYTE_LENGTH = 50917


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

    def list_recent_runs(self) -> RunVisibilitySequenceV1:
        return (
            RunVisibilityV1(
                run_id="run-1",
                state_label="WAITING_USER",
                reason_code="USER_DECISION_PENDING",
                next_action="AWAIT_USER_DECISION",
                evidence_refs=(),
            ),
        )

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


def test_packaged_asset_loads_with_its_exact_declared_identity() -> None:
    """The loader verifies the declared identity of the pinned asset."""
    asset = load_packaged_web_asset("htmx.min.js")
    assert asset.name == "htmx.min.js"
    assert asset.version == "2.0.4"
    assert asset.sha256 == _PINNED_SHA256
    assert asset.byte_length == _PINNED_BYTE_LENGTH
    assert asset.content_type == "application/javascript"
    assert len(asset.content) == _PINNED_BYTE_LENGTH
    assert hashlib.sha256(asset.content).hexdigest() == _PINNED_SHA256
    assert b"var htmx=function()" in asset.content
    assert b'version:"2.0.4' in asset.content
    # immutable: two loads carry identical bytes
    again = load_packaged_web_asset("htmx.min.js")
    assert again.content == asset.content
    assert again.sha256 == asset.sha256


def test_packaged_asset_loads_through_package_resources_only() -> None:
    """The asset bytes come from the package resource itself — the file
    inside the package, never a CDN or a runtime download."""
    resource = importlib.resources.files("vespercode.web").joinpath(
        "static", "htmx.min.js"
    )
    assert resource.is_file()
    asset = load_packaged_web_asset("htmx.min.js")
    assert asset.content == resource.read_bytes()
    assert b"https://" not in asset.content  # fully self-contained file


def test_install_packaged_web_assets_serves_the_sole_local_static_path(
    security_config: LocalWebSecurityConfigV1,
) -> None:
    """The installer registers exactly the one local static route and
    serves exactly the identity-verified packaged bytes (no CDN, no
    network fallback, no other static path)."""
    shell_ports: LocalShellPortsV1 = FakeShellPortsV1()
    installers: LocalRouteInstallerSequenceV1 = ()
    app = create_local_app(shell_ports, security_config, installers)
    install_packaged_web_assets(app)
    routes = {getattr(route, "path", None) for route in app.routes}
    assert routes == {"/", "/static/htmx.min.js"}
    assert app.state.local_packaged_assets is True

    client = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")
    asset = load_packaged_web_asset("htmx.min.js")
    served = client.get("/static/htmx.min.js")
    assert served.status_code == 200
    assert served.headers["content-type"] == "application/javascript"
    assert served.content == asset.content
    assert len(served.content) == _PINNED_BYTE_LENGTH
    assert hashlib.sha256(served.content).hexdigest() == _PINNED_SHA256
    # the security boundary still applies: bad Host is rejected even for
    # the static path, and the security headers attach to the asset
    rejected = client.get("/static/htmx.min.js", headers={"Host": "evil.example"})
    assert rejected.status_code == 403
    assert rejected.json()["error_code"] == "HOST_REJECTED"
    assert served.headers["x-content-type-options"] == "nosniff"
    assert served.headers["content-security-policy"].startswith("default-src 'self'")
    # no other static paths exist
    missing = client.get("/static/other.js")
    assert missing.status_code == 404


def test_packaged_asset_rejects_unknown_names_and_identity_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the pinned asset loads; any identity drift or a missing
    packaged file fails closed (28.C GREEN-1)."""
    with pytest.raises(PackagedWebAssetErrorV1, match="unknown"):
        load_packaged_web_asset("cdn.js")  # type: ignore[arg-type]

    monkeypatch.setattr(app_module, "_PACKAGED_HTMX_SHA256_V1", "00" * 32)
    with pytest.raises(PackagedWebAssetErrorV1, match="identity mismatch"):
        load_packaged_web_asset("htmx.min.js")
    monkeypatch.undo()

    monkeypatch.setattr(app_module, "_PACKAGED_HTMX_BYTE_LENGTH_V1", 1)
    with pytest.raises(PackagedWebAssetErrorV1, match="length mismatch"):
        load_packaged_web_asset("htmx.min.js")
    monkeypatch.undo()


def test_packaged_asset_missing_file_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing packaged resource fails closed instead of serving
    nothing or falling back to a network source."""

    class _MissingResource:
        def joinpath(self, *parts: str) -> _MissingResource:
            del parts
            return self

        def is_file(self) -> bool:
            return False

        def read_bytes(self) -> bytes:
            raise AssertionError("a missing resource must never be read")

    monkeypatch.setattr(
        importlib.resources,
        "files",
        lambda package: _MissingResource(),  # noqa: ARG005
    )
    with pytest.raises(PackagedWebAssetErrorV1, match="missing"):
        load_packaged_web_asset("htmx.min.js")
    monkeypatch.undo()


def test_packaged_asset_home_page_uses_only_the_local_asset(
    security_config: LocalWebSecurityConfigV1,
) -> None:
    """The composed shell page references only the local packaged asset
    and never any external source (28.C Expected line: zero external
    asset request)."""
    shell_ports: LocalShellPortsV1 = FakeShellPortsV1()
    installers: LocalRouteInstallerSequenceV1 = ()
    app = create_local_app(shell_ports, security_config, installers)
    install_packaged_web_assets(app)
    client = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")
    response = client.get("/", headers={"Host": f"127.0.0.1:{security_config.port}"})
    assert response.status_code == 200
    assert response.text.count("htmx.min.js") >= 1
    assert "https://" not in response.text
    assert "http://" not in response.text
