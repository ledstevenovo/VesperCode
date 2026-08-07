"""T28.3 legacy step 28.D: thin loopback serve CLI composition tests.

The exact RED pins the smallest closed-parser rejection; the matrix pins
the closed serve parsing (literal loopback host, validated port,
secret/provider/repository/alternate-bind rejection) and the exactly-
once composition of Tasks 28.A–28.C through the injected shell factory
and the injected application/server boundary (SPEC §8.2 ``vespercode
serve``, §4.9; Registry row 28.D Expected line: ``127.0.0.1``).
"""

from __future__ import annotations

import contextlib
import io
from typing import Any, Sequence

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vespercode.audit.projection import RunVisibilityV1
from vespercode.contracts.optional import AbsentV1
from vespercode.credentials.port import CredentialStatusV1
from vespercode.web.app import LocalShellPortsV1, RunVisibilitySequenceV1
from vespercode.web.security import LocalWebSecurityConfigV1
from vespercode.cli import (
    CSRF_HEADER_NAME_V1,
    DEFAULT_PORT_V1,
    LOOPBACK_HOST_V1,
    SESSION_COOKIE_NAME_V1,
    build_cli,
    cli,
)


class _InvocationResult:
    """One closed invocation result: exit code and captured output."""

    def __init__(self, exit_code: int, output: str) -> None:
        self.exit_code = exit_code
        self.output = output


class _CliRunner:
    """One minimal CLI runner over the argparse-based CLI surface (the
    repository has no click runtime dependency, so the card's
    ``CliRunner``-shaped fixture is provided here: ``invoke`` runs the
    ``main`` entry against captured stdio and normalizes ``SystemExit``
    into an exit code)."""

    def invoke(self, target: Any, args: Sequence[str]) -> _InvocationResult:
        stdout, stderr = io.StringIO(), io.StringIO()
        exit_code: int = 0
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                if hasattr(target, "main"):
                    result = target.main(list(args))
                    if result is not None:
                        exit_code = int(result)
                else:
                    # an argparse parser: errors exit via SystemExit;
                    # a successful parse runs the installed handler
                    namespace = target.parse_args(list(args))
                    handler = getattr(namespace, "_serve_handler", None)
                    if handler is not None:
                        result = handler(namespace)
                        if result is not None:
                            exit_code = int(result)
            except SystemExit as exit_error:
                code = exit_error.code
                exit_code = (
                    code if isinstance(code, int) else (1 if code is not None else 0)
                )
        return _InvocationResult(
            exit_code=exit_code, output=stdout.getvalue() + stderr.getvalue()
        )


@pytest.fixture
def cli_runner() -> _CliRunner:
    return _CliRunner()


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


class FakeShellFactoryV1:
    """One counting fake shell factory (the matrix pins exactly one
    ``create`` per serve invocation)."""

    def __init__(self) -> None:
        self.create_count = 0

    def create(self) -> LocalShellPortsV1:
        self.create_count += 1
        return FakeShellPortsV1()


class SpyServerLauncherV1:
    """One spy server boundary recording its launch arguments."""

    def __init__(self) -> None:
        self.calls: list[tuple[object, str, int]] = []

    def __call__(self, app: object, host: str, port: int) -> object:
        self.calls.append((app, host, port))
        return None


@pytest.fixture
def fake_factory() -> FakeShellFactoryV1:
    return FakeShellFactoryV1()


@pytest.fixture
def spy_launcher() -> SpyServerLauncherV1:
    return SpyServerLauncherV1()


def test_serve_rejects_non_loopback_host_and_secret_arguments(
    cli_runner: _CliRunner,
) -> None:
    assert cli_runner.invoke(cli, ["serve", "--host", "0.0.0.0"]).exit_code != 0
    assert cli_runner.invoke(cli, ["serve", "--api-key", "secret"]).exit_code != 0


def test_cli_serve_boundary_matrix(
    cli_runner: _CliRunner,
    fake_factory: FakeShellFactoryV1,
    spy_launcher: SpyServerLauncherV1,
) -> None:
    """The exact thin serve-boundary matrix (Expected 28.D: 127.0.0.1).

    The parser accepts only the closed ``serve`` command with the
    literal loopback host and the validated port; secret, provider,
    repository, and alternate-bind inputs are rejected; a valid serve
    composes Tasks 28.A–28.C exactly once (one factory create, one
    launch, real local app, packaged-asset reachable) with no duplicated
    security, UI, or workflow rule.
    """
    parser = build_cli(fake_factory, server_launcher=spy_launcher)

    # --- the literal loopback host is the only accepted binding ---
    for bad_host in ("0.0.0.0", "::1", "localhost", "127.0.0.2", "example.com"):
        result = cli_runner.invoke(parser, ["serve", "--host", bad_host])
        assert result.exit_code != 0, bad_host
    assert fake_factory.create_count == 0
    assert spy_launcher.calls == []

    # --- secret, provider, repository, and alternate-bind inputs are
    # rejected by the closed parser (unknown options fail closed) ---
    for rejected in (
        ["serve", "--api-key", "secret"],
        ["serve", "--provider", "openai"],
        ["serve", "--repo", "C:\\repo"],
        ["serve", "--workspace", "C:\\repo"],
        ["serve", "--host", "127.0.0.1", "--api-key", "secret"],
        ["serve", "--bind", "0.0.0.0"],
        ["serve", "--port", "0"],
        ["serve", "--port", "65536"],
        ["serve", "--port", "abc"],
        ["serve", "--port", "-1"],
        ["serve", "--port", " 8765"],
        ["serve", "--port", "+8765"],
        ["serve", "--port", "1_000"],
        ["serve", "--port", "８７６５"],
        ["other-command"],
    ):
        result = cli_runner.invoke(parser, rejected)
        assert result.exit_code != 0, rejected
    assert fake_factory.create_count == 0
    assert spy_launcher.calls == []

    # --- one valid serve: one factory create, one launch, exact host ---
    result = cli_runner.invoke(
        parser, ["serve", "--host", "127.0.0.1", "--port", "8765"]
    )
    assert result.exit_code == 0
    assert fake_factory.create_count == 1
    assert len(spy_launcher.calls) == 1
    launched_app, launched_host, launched_port = spy_launcher.calls[0]
    assert launched_host == "127.0.0.1"
    assert launched_port == 8765
    assert isinstance(launched_app, FastAPI)
    app = launched_app
    # Task 28.A: the composed security config is the exact loopback one
    security: LocalWebSecurityConfigV1 = app.state.local_security_config
    assert security.host == "127.0.0.1"
    assert security.port == 8765
    assert security.session_cookie_name == SESSION_COOKIE_NAME_V1
    assert security.csrf_header_name == CSRF_HEADER_NAME_V1
    # Task 28.B: the composed shell uses the injected ports
    assert isinstance(app.state.local_shell_ports, FakeShellPortsV1)
    # Task 28.C: the packaged asset is reachable on the composed app
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    asset = client.get("/static/htmx.min.js")
    assert asset.status_code == 200
    assert asset.headers["content-type"] == "application/javascript"
    assert len(asset.content) == 50917
    # the loopback security still applies to the composed app
    rejected_host = client.get("/", headers={"Host": "evil.example"})
    assert rejected_host.status_code == 403
    assert rejected_host.json()["error_code"] == "HOST_REJECTED"

    # --- defaults: host 127.0.0.1, port 8765 ---
    result = cli_runner.invoke(parser, ["serve"])
    assert result.exit_code == 0
    assert fake_factory.create_count == 2
    assert len(spy_launcher.calls) == 2
    assert spy_launcher.calls[1][1] == LOOPBACK_HOST_V1
    assert spy_launcher.calls[1][2] == DEFAULT_PORT_V1

    # --- the standalone entry's placeholder factory fails closed ---
    with pytest.raises(NotImplementedError):
        cli.main(["serve"])
    with pytest.raises(NotImplementedError):
        cli.main(["serve", "--host", "127.0.0.1"])
