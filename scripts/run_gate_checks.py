"""Closed gate-tool runner for the T01.1 step 1.Aa bootstrap.

Usage: python scripts/run_gate_checks.py <command> -- <forwarded args...>
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

_REPO_ROOT = Path(__file__).resolve().parents[1]

_COMMANDS = ("pytest", "ruff-format", "ruff-check", "mypy")

_BASE_ARGV: dict[str, tuple[str, ...]] = {
    "pytest": (sys.executable, "-m", "pytest", "-c", "gates/pytest.ini"),
    "ruff-format": (
        sys.executable,
        "-m",
        "ruff",
        "format",
        "--check",
        "--config",
        "gates/ruff.toml",
    ),
    "ruff-check": (
        sys.executable,
        "-m",
        "ruff",
        "check",
        "--config",
        "gates/ruff.toml",
    ),
    "mypy": (
        sys.executable,
        "-m",
        "mypy",
        "--config-file",
        "gates/mypy.ini",
        "--explicit-package-bases",
    ),
}

_MAXFAIL_RE = re.compile(r"--maxfail=[1-9][0-9]*")
_ENV_ASSIGN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")

_MYPY_ROOTS = (
    "spikes",
    "tests/feasibility",
    "src",
    "tests",
    "scripts/bootstrap_gate_env.py",
)
_MYPY_DIR_ROOTS = ("spikes", "tests/feasibility", "src", "tests")


def _is_env_assignment(arg: str) -> bool:
    return _ENV_ASSIGN_RE.match(arg) is not None


def _is_repo_relative_path(arg: str) -> bool:
    if not arg or arg == ".":
        return False
    if arg.startswith(("/", "\\")):
        return False
    if len(arg) >= 2 and arg[0].isalpha() and arg[1] == ":":
        return False
    if any(char in arg for char in "*?[]{}~"):
        return False
    if arg.startswith("-") or _is_env_assignment(arg):
        return False
    return ".." not in arg.replace("\\", "/").split("/")


def _is_valid_forwarded(command: str, arg: str) -> bool:
    if command == "pytest":
        if arg in ("-q", "-v", "-x"):
            return True
        if _MAXFAIL_RE.fullmatch(arg) is not None:
            return True
        return _is_repo_relative_path(arg)
    if command in ("ruff-format", "ruff-check"):
        return arg == "." or _is_repo_relative_path(arg)
    if not _is_repo_relative_path(arg):
        return False
    normalized = arg.replace("\\", "/")
    if normalized in _MYPY_ROOTS:
        return True
    return any(normalized.startswith(root + "/") for root in _MYPY_DIR_ROOTS)


def build_closed_argv(command: str, forwarded_args: tuple[str, ...]) -> tuple[str, ...]:
    if command not in _BASE_ARGV:
        raise ValueError(f"unknown gate command: {command!r}")
    for arg in forwarded_args:
        if not _is_valid_forwarded(command, arg):
            raise ValueError(f"widening gate argument: {arg!r}")
    return _BASE_ARGV[command] + tuple(forwarded_args)


def run_closed_command(
    command: str,
    forwarded_args: tuple[str, ...],
    *,
    execute: Callable[[tuple[str, ...]], int] | None = None,
) -> int:
    if command not in _BASE_ARGV:
        sys.stderr.write("ERROR\tGATE_COMMAND_UNKNOWN\n")
        return 2
    try:
        argv = build_closed_argv(command, forwarded_args)
    except ValueError:
        sys.stderr.write("ERROR\tGATE_ARGUMENT_WIDENING\n")
        return 2
    if execute is not None:
        return execute(argv)
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(argv, cwd=str(_REPO_ROOT), env=env)
    return proc.returncode


def main(argv: list[str]) -> int:
    try:
        separator = argv.index("--")
    except ValueError:
        sys.stderr.write("ERROR\tGATE_ARGUMENT_SEPARATOR_MISSING\n")
        return 2
    command = argv[0] if separator > 0 else ""
    forwarded = tuple(argv[separator + 1 :])
    return run_closed_command(command, forwarded)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
