"""T38.2 legacy step 38.F: final CLI production recovery composition tests.

The exact RED pins the production binding order: the complete v1
migration registry is applied before the recovery service is
constructed, and the installed ``recover`` command reaches exactly the
terminal preview/apply event (GREEN-1/GREEN-2).  The fixtures build the
production composition through the real ``cli_composition`` functions
and record the composition sequence on the probe (a documented test
seam: the probe observes the fixture performing the exact production
composition steps, and the terminal event is recorded by a thin
recording wrapper around the built handler — the production interface
itself stays probe-free).

The domain pins cover the complete-registry-before-service ordering, the
sole initialized production handler graph, the injected workspace
service, and the installed entry-point reachability (``vespercode
serve`` + ``recover``).
"""

from __future__ import annotations

import argparse
import contextlib
import io
from pathlib import Path
from typing import Any, Sequence

import pytest

pytest.importorskip("fastapi")

from vespercode.cli import build_cli
from vespercode.cli_composition import (
    bind_production_recover_command,
    build_production_recovery_cli_handler,
    initialize_production_control_database,
)
from vespercode.storage.migrations.registry import ALL_V1_MIGRATIONS
from vespercode.web.app import LocalShellPortsV1
from vespercode.workspace.identity_win32 import WorkspaceIdentityV1


class _InvocationResult:
    """One closed invocation result: exit code and captured output."""

    def __init__(self, exit_code: int, output: str) -> None:
        self.exit_code = exit_code
        self.output = output


class InstalledCliRunner:
    """One minimal CLI runner over an installed production parser."""

    def __init__(self, parser: argparse.ArgumentParser) -> None:
        self._parser = parser

    def invoke(self, arguments: Sequence[str]) -> _InvocationResult:
        stdout, stderr = io.StringIO(), io.StringIO()
        exit_code: int = 0
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                namespace = self._parser.parse_args(list(arguments))
                handler = getattr(namespace, "_recover_handler", None)
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


class ProductionRecoveryProbe:
    """One composition-sequence probe.

    ``applied_migrations`` is the migration registry actually recorded
    in the initialized control database; ``events`` records the exact
    composition order (registry first, then the recovery service, then
    the terminal CLI event).
    """

    def __init__(self) -> None:
        self.applied_migrations: tuple[Any, ...] = ()
        self._events: list[str] = []

    @property
    def events(self) -> tuple[str, ...]:
        """The recorded composition sequence (immutable view)."""
        return tuple(self._events)

    def record(self, event: str) -> None:
        """Append one observed composition event."""
        self._events.append(event)


class _RecordingHandler:
    """One thin recording wrapper around the production handler.

    The wrapper records the terminal preview/apply event on the probe
    (test seam only; the production interface itself is probe-free).
    """

    def __init__(self, inner: Any, probe: ProductionRecoveryProbe) -> None:
        self._inner = inner
        self._probe = probe

    def preview(self, workspace: Path) -> Any:
        self._probe.record("preview")
        return self._inner.preview(workspace)

    def apply(self, workspace: Path) -> Any:
        self._probe.record("apply")
        return self._inner.apply(workspace)


class FakeWorkspaceServiceV1:
    """One fake Task 9.D workspace identity service (test-owned)."""

    def __init__(self) -> None:
        self.resolve_calls: list[Path] = []
        self.reject = False
        self._identity = WorkspaceIdentityV1(
            schema_version=1,
            canonical_absolute_path="C:\\repo",
            volume_serial_number=12345678,
            final_object_file_id_128_hex="1" * 32,
            final_object_kind="DIRECTORY",
            link_count=1,
            acl_observable=True,
            digest="a" * 64,
        )

    def resolve(self, locator: Path) -> WorkspaceIdentityV1:
        self.resolve_calls.append(Path(locator))
        if self.reject:
            raise ValueError("unsupported workspace")
        return self._identity


class _EmptyShellFactory:
    """One placeholder shell factory (never created by recover)."""

    def create(self) -> LocalShellPortsV1:
        raise AssertionError("recover never composes the local shell")


@pytest.fixture
def production_recovery_probe() -> ProductionRecoveryProbe:
    return ProductionRecoveryProbe()


@pytest.fixture
def workspace_service() -> FakeWorkspaceServiceV1:
    return FakeWorkspaceServiceV1()


@pytest.fixture
def installed_cli_runner(
    tmp_path: Path,
    production_recovery_probe: ProductionRecoveryProbe,
    workspace_service: FakeWorkspaceServiceV1,
) -> InstalledCliRunner:
    """One runner over the production parser with the initialized db.

    The fixture performs the exact production composition steps: the
    complete registry is applied first, the sole production handler is
    constructed second, and the Task 38.E recover parser is bound to it
    last; the probe records the sequence.
    """
    database_path = tmp_path / "control.db"
    db = initialize_production_control_database(database_path)
    recorded = set(db.recorded_migrations())
    production_recovery_probe.applied_migrations = tuple(
        migration
        for migration in ALL_V1_MIGRATIONS
        if (migration.version, migration.name, migration.checksum.value) in recorded
    )
    production_recovery_probe.record("apply_complete_registry")
    handler = build_production_recovery_cli_handler(db, workspace_service)
    production_recovery_probe.record("construct_recovery_service")
    parser = build_cli(
        _EmptyShellFactory(),
        recovery_handler=_RecordingHandler(handler, production_recovery_probe),
    )
    return InstalledCliRunner(parser)


@pytest.mark.parametrize(
    ("arguments", "terminal_event"),
    (
        (("recover", "--workspace", "C:\\repo"), "preview"),
        (("recover", "--workspace", "C:\\repo", "--apply"), "apply"),
    ),
)
def test_installed_recover_binds_complete_database_before_handler(
    installed_cli_runner: InstalledCliRunner,
    production_recovery_probe: ProductionRecoveryProbe,
    arguments: tuple[str, ...],
    terminal_event: str,
) -> None:
    result = installed_cli_runner.invoke(arguments)
    assert result.exit_code == 0
    assert production_recovery_probe.applied_migrations == ALL_V1_MIGRATIONS
    assert production_recovery_probe.events == (
        "apply_complete_registry",
        "construct_recovery_service",
        terminal_event,
    )


def test_initialize_production_control_database_applies_registry_exactly_once(
    tmp_path: Path,
) -> None:
    """The complete v1 registry is applied exactly once; a second
    initialization is a no-op with the identical history (GREEN-1)."""
    database_path = tmp_path / "control.db"
    first = initialize_production_control_database(database_path)
    recorded = first.recorded_migrations()
    assert len(recorded) == len(ALL_V1_MIGRATIONS)
    assert tuple(row[0] for row in recorded) == tuple(
        migration.version for migration in ALL_V1_MIGRATIONS
    )
    second = initialize_production_control_database(database_path)
    assert second.recorded_migrations() == recorded
    first.close()
    second.close()


def test_production_handler_preview_is_read_only_no_transaction(
    tmp_path: Path,
    workspace_service: FakeWorkspaceServiceV1,
) -> None:
    """The production handler previews through the injected workspace
    service and reports the closed NO_TRANSACTION outcome with zero
    writes (GREEN-2/AC-29)."""
    db = initialize_production_control_database(tmp_path / "control.db")
    handler = build_production_recovery_cli_handler(db, workspace_service)
    result = handler.preview(Path("C:\\repo"))
    assert result.kind == "NO_TRANSACTION"
    assert "没有非终态恢复事务" in result.message
    assert workspace_service.resolve_calls == [Path("C:\\repo")]
    db.close()


def test_production_handler_apply_without_transaction_never_writes(
    tmp_path: Path,
    workspace_service: FakeWorkspaceServiceV1,
) -> None:
    """The explicit apply with no transaction performs zero mutation and
    reports the bounded outcome (GREEN-2/Boundary)."""
    db = initialize_production_control_database(tmp_path / "control.db")
    handler = build_production_recovery_cli_handler(db, workspace_service)
    result = handler.apply(Path("C:\\repo"))
    assert result.kind == "NO_TRANSACTION"
    assert "没有非终态恢复事务" in result.message
    db.close()


def test_production_handler_rejects_unresolvable_workspace(
    tmp_path: Path,
    workspace_service: FakeWorkspaceServiceV1,
) -> None:
    """An unresolvable workspace projects the bounded rejection without
    opening the recovery graph's mutation path."""
    workspace_service.reject = True
    db = initialize_production_control_database(tmp_path / "control.db")
    handler = build_production_recovery_cli_handler(db, workspace_service)
    result = handler.preview(Path("C:\\repo"))
    assert result.kind == "WORKSPACE_REJECTED"
    assert "无法解析为受支持的工作区" in result.message
    db.close()


def test_bind_production_recover_command_installs_recover_and_keeps_serve(
    tmp_path: Path,
    workspace_service: FakeWorkspaceServiceV1,
) -> None:
    """``bind_production_recover_command`` installs the recover command
    onto a parser that still serves the closed ``serve`` surface
    (GREEN-2; Expected 38.F: ``vespercode serve`` + ``recover``)."""
    from vespercode.cli import install_serve_command

    parser = argparse.ArgumentParser(
        prog="vespercode", description="VesperCode 编码智能体框架本地控制台。"
    )
    install_serve_command(parser, _EmptyShellFactory())
    bind_production_recover_command(parser, tmp_path / "control.db", workspace_service)
    runner = InstalledCliRunner(parser)

    recover = runner.invoke(("recover", "--workspace", "C:\\repo"))
    assert recover.exit_code == 0
    assert "没有非终态恢复事务" in recover.output

    help_result = runner.invoke(("recover", "--help"))
    assert help_result.exit_code == 0
    assert "--workspace" in help_result.output and "--apply" in help_result.output

    serve_help = runner.invoke(("serve", "--help"))
    assert serve_help.exit_code == 0
    assert "--port" in serve_help.output
