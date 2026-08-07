"""T38.2 legacy step 38.E: recovery CLI parser/delegation tests.

The exact RED pins the smallest zero-write contract: ``vespercode
recover --workspace PATH`` must invoke the injected handler's preview
exactly once, apply zero times, and return the successful read-only
projection (SPEC §8.2/AC-29: recovery defaults to preview; only the
literal ``--apply`` mutates).  The card's test body references ``app``
as a free variable, so ``app`` is a module-level parser over the
module-level spy handler; the ``recovery_service`` fixture resets the
spy's counts per test (the click-free ``CliRunner`` pattern of the
T28.3 CLI tests).

The domain pins cover the closed argument surface, the literal
``--apply`` gate, the injected typed handler, Windows path handling, the
bounded help/error/result projection, and the zero storage/migration
import boundary.
"""

from __future__ import annotations

import argparse
import contextlib
import io
from pathlib import Path
from typing import Any, Sequence

import pytest

pytest.importorskip("fastapi")

from vespercode.cli import (
    RecoveryCliHandlerV1,
    RecoveryCliResultKindV1,
    RecoveryCliResultV1,
    install_recover_command,
)
from vespercode.web.app import LocalShellPortsV1


class _InvocationResult:
    """One closed invocation result: exit code and captured output."""

    def __init__(self, exit_code: int, output: str) -> None:
        self.exit_code = exit_code
        self.output = output


class CliRunner:
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


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


class SpyRecoveryService:
    """One spy injected ``RecoveryCliHandlerV1`` implementation.

    The spy records the workspaces it receives and returns the seeded
    closed results; it never touches a database, a migration, or a
    repository.
    """

    def __init__(self) -> None:
        self.preview_call_count = 0
        self.apply_call_count = 0
        self._preview_workspaces: list[Path] = []
        self._apply_workspaces: list[Path] = []
        self.preview_result = RecoveryCliResultV1(
            kind="PREVIEW", message="恢复预览：事务 tx-1 判定 已回滚（零写入）"
        )
        self.apply_result = RecoveryCliResultV1(
            kind="APPLIED", message="恢复已执行：已回滚，变更路径 src/a.py"
        )

    def seed_preview_result(self, result: RecoveryCliResultV1) -> None:
        self.preview_result = result

    def seed_apply_result(self, result: RecoveryCliResultV1) -> None:
        self.apply_result = result

    @property
    def preview_workspaces(self) -> list[Path]:
        return list(self._preview_workspaces)

    @property
    def apply_workspaces(self) -> list[Path]:
        return list(self._apply_workspaces)

    def preview(self, workspace: Path) -> RecoveryCliResultV1:
        self.preview_call_count += 1
        self._preview_workspaces.append(Path(workspace))
        return self.preview_result

    def apply(self, workspace: Path) -> RecoveryCliResultV1:
        self.apply_call_count += 1
        self._apply_workspaces.append(Path(workspace))
        return self.apply_result


class _EmptyShellFactory:
    """One placeholder shell factory (never created by recover)."""

    def create(self) -> LocalShellPortsV1:
        raise AssertionError("recover never composes the local shell")


_recovery_service = SpyRecoveryService()
"""The module-level spy the card's free-variable ``app`` invokes."""

app = argparse.ArgumentParser(
    prog="vespercode", description="VesperCode 编码智能体框架本地控制台。"
)
install_recover_command(app, _recovery_service)
"""One closed parser with the recover command installed over the spy."""


@pytest.fixture
def recovery_service() -> SpyRecoveryService:
    """One reset module-level spy (fresh counts and results per test)."""
    _recovery_service.preview_call_count = 0
    _recovery_service.apply_call_count = 0
    _recovery_service._preview_workspaces = []
    _recovery_service._apply_workspaces = []
    _recovery_service.preview_result = RecoveryCliResultV1(
        kind="PREVIEW", message="恢复预览：事务 tx-1 判定 已回滚（零写入）"
    )
    _recovery_service.apply_result = RecoveryCliResultV1(
        kind="APPLIED", message="恢复已执行：已回滚，变更路径 src/a.py"
    )
    return _recovery_service


def test_recover_without_apply_never_writes(
    cli_runner: CliRunner,
    recovery_service: SpyRecoveryService,
) -> None:
    result = cli_runner.invoke(app, ["recover", "--workspace", "C:\\repo"])
    assert result.exit_code == 0
    assert recovery_service.preview_call_count == 1
    assert recovery_service.apply_call_count == 0


def test_recover_apply_requires_the_literal_apply_switch(
    cli_runner: CliRunner,
    recovery_service: SpyRecoveryService,
) -> None:
    """Only the literal ``--apply`` switch reaches the apply path; every
    other spelling is a preview or a closed rejection (GREEN-1)."""
    for index, arguments in enumerate(
        (
            ["recover", "--workspace", "C:\\repo", "--apply"],
            ["recover", "--apply", "--workspace", "C:\\repo"],
        ),
        start=1,
    ):
        result = cli_runner.invoke(app, arguments)
        assert result.exit_code == 0, arguments
        assert recovery_service.apply_call_count == index, arguments
        assert recovery_service.preview_call_count == 0, arguments
        assert "恢复已执行：已回滚" in result.output


def test_recover_closed_argument_surface_rejects_every_override(
    cli_runner: CliRunner,
    recovery_service: SpyRecoveryService,
) -> None:
    """Force/ignore/body/secret/disposition/transaction-edit arguments
    and a missing workspace fail closed with zero handler calls
    (GREEN-4/Boundary)."""
    for rejected in (
        ["recover"],
        ["recover", "--workspace"],
        ["recover", "--workspace", "C:\\repo", "--force"],
        ["recover", "--workspace", "C:\\repo", "--ignore"],
        ["recover", "--workspace", "C:\\repo", "--skip"],
        ["recover", "--workspace", "C:\\repo", "--edit"],
        ["recover", "--workspace", "C:\\repo", "--abandon"],
        ["recover", "--workspace", "C:\\repo", "--disposition", "COMMITTED"],
        ["recover", "--workspace", "C:\\repo", "--transaction", "tx-1"],
        ["recover", "--workspace", "C:\\repo", "--body", "x"],
        ["recover", "--workspace", "C:\\repo", "--secret", "x"],
        ["recover", "--workspace", "C:\\repo", "--api-key", "x"],
        ["recover", "--workspace", "C:\\repo", "--apply", "--force"],
        ["recover", "--workspace", "C:\\repo", "--apply", "--ignore"],
    ):
        result = cli_runner.invoke(app, rejected)
        assert result.exit_code != 0, rejected
    assert recovery_service.preview_call_count == 0
    assert recovery_service.apply_call_count == 0


def test_recover_help_is_bounded_and_closed(
    cli_runner: CliRunner,
    recovery_service: SpyRecoveryService,
) -> None:
    """``--help`` projects bounded command text without any handler call
    and without opening production storage (GREEN-2)."""
    result = cli_runner.invoke(app, ["recover", "--help"])
    assert result.exit_code == 0
    assert "recover" in result.output
    assert "--workspace" in result.output
    assert "--apply" in result.output
    assert recovery_service.preview_call_count == 0
    assert recovery_service.apply_call_count == 0


def test_recover_passes_windows_workspace_path_to_handler(
    cli_runner: CliRunner,
    recovery_service: SpyRecoveryService,
) -> None:
    """The ``--workspace`` value is adapted to a ``Path`` exactly
    (Windows paths included) and reaches the injected handler
    (GREEN-2)."""
    result = cli_runner.invoke(app, ["recover", "--workspace", "C:\\repo"])
    assert result.exit_code == 0
    assert recovery_service.preview_workspaces == [Path("C:\\repo")]
    assert recovery_service.apply_workspaces == []


def test_recover_projects_bounded_outcomes_without_storage(
    cli_runner: CliRunner,
    recovery_service: SpyRecoveryService,
) -> None:
    """Every closed outcome kind projects its bounded text with exit 0;
    the parser itself opens no database, migration, or repository
    (GREEN-2/GREEN-4)."""
    outcomes: tuple[tuple[RecoveryCliResultKindV1, str], ...] = (
        ("UNRESOLVED", "恢复处于未解决状态：外部变化或证据不足，保持恢复阻塞。"),
        ("NO_TRANSACTION", "该工作区没有非终态恢复事务。"),
        ("WORKSPACE_REJECTED", "工作区路径无法解析为受支持的工作区。"),
        ("RECOVERY_FAILED", "恢复操作失败，状态未变化。"),
    )
    for kind, message in outcomes:
        recovery_service.seed_preview_result(
            RecoveryCliResultV1(kind=kind, message=message)
        )
        result = cli_runner.invoke(app, ["recover", "--workspace", "C:\\repo"])
        assert result.exit_code == 0, kind
        assert message in result.output, kind
        assert recovery_service.preview_call_count == 1
        recovery_service.preview_call_count = 0


def test_recover_repeated_previews_never_write(
    cli_runner: CliRunner,
    recovery_service: SpyRecoveryService,
) -> None:
    """Repeated preview invocations without ``--apply`` keep the apply
    count at zero (GREEN-3)."""
    for _ in range(3):
        result = cli_runner.invoke(app, ["recover", "--workspace", "C:\\repo"])
        assert result.exit_code == 0
    assert recovery_service.preview_call_count == 3
    assert recovery_service.apply_call_count == 0


def test_recovery_cli_module_has_no_storage_or_migration_imports() -> None:
    """The recover parser/delegation surface never imports storage or
    migration machinery at module level (GREEN-4/Boundary: Task 38.F
    owns the production binding)."""
    import vespercode.cli as cli_module

    source = cli_module.__file__
    assert source is not None
    imports = [
        line
        for line in Path(source).read_text(encoding="utf-8").splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]
    assert not any(
        "storage" in line or "migration" in line or "RecoveryService" in line
        for line in imports
    )
    handler: RecoveryCliHandlerV1 = _recovery_service
    assert handler is not None
