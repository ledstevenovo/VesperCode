"""T04.1 legacy step 4.A GREEN-3: fail-closed formal environment bootstrap.

Validates the fixed terminal GO evidence, compares the PATH-resolved exact
Python patch with the recorded patch, and only on equality validates
``requirements/dev.lock`` and performs hash-locked ``--no-deps``
materialization into ``.venv-formal`` through the declared interpreter.  A
Python patch mismatch wins over any lock problem and never creates or uses
``.venv-formal``.

Every child process is isolated from user and environment configuration and
never writes bytecode.  This script consumes the unchanged Task 1 loader
for all report/toolchain identity validation.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.bootstrap_gate_env import (  # noqa: E402
    INDEX_URL,
    LockInvalid,
    validate_lock_bytes,
)
from spikes.win32_workspace_boundary.report import (  # noqa: E402
    WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH,
    load_workspace_boundary_gate_report,
)

FORMAL_ARGUMENT_INVALID = "FORMAL_ARGUMENT_INVALID"
FORMAL_PYTHON_VERSION_MISMATCH = "FORMAL_PYTHON_VERSION_MISMATCH"
FORMAL_LOCK_INVALID = "FORMAL_LOCK_INVALID"
FORMAL_MATERIALIZE_FAILED = "FORMAL_MATERIALIZE_FAILED"
FORMAL_EVIDENCE_INVALID = "FORMAL_EVIDENCE_INVALID"

_EXIT_CODES = {
    FORMAL_ARGUMENT_INVALID: 2,
    FORMAL_PYTHON_VERSION_MISMATCH: 3,
    FORMAL_LOCK_INVALID: 4,
    FORMAL_MATERIALIZE_FAILED: 6,
    FORMAL_EVIDENCE_INVALID: 7,
}

_DEV_LOCK_REL_PATH = Path("requirements/dev.lock")
_VENV_DIR_NAME = ".venv-formal"


class BootstrapError(Exception):
    """Base class for the stable formal bootstrap failure codes."""

    code: str


class ArgumentInvalid(BootstrapError):
    code = FORMAL_ARGUMENT_INVALID


class PythonVersionMismatch(BootstrapError):
    code = FORMAL_PYTHON_VERSION_MISMATCH

    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(f"{expected}:{actual}")
        self.expected = expected
        self.actual = actual


class LockInvalidError(BootstrapError):
    code = FORMAL_LOCK_INVALID


class EvidenceInvalid(BootstrapError):
    code = FORMAL_EVIDENCE_INVALID


class MaterializeFailed(BootstrapError):
    code = FORMAL_MATERIALIZE_FAILED


class _Options(NamedTuple):
    root: Path
    gate_evidence: Path


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _parse_argv(argv: list[str]) -> _Options:
    if len(argv) not in (0, 4) or (len(argv) == 4 and argv[0] != "--root"):
        raise ArgumentInvalid("expected --root ROOT [--gate-evidence PATH]")
    root = Path(argv[1]).resolve() if argv else Path.cwd().resolve()
    if len(argv) == 4:
        if argv[2] != "--gate-evidence":
            raise ArgumentInvalid("expected --root ROOT [--gate-evidence PATH]")
        evidence = Path(argv[3]).resolve()
    else:
        evidence = root / WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH
    if evidence != root / WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH:
        raise ArgumentInvalid("gate evidence must be the fixed terminal GO path")
    return _Options(root=root, gate_evidence=evidence)


def _run(argv: list[str], *, timeout: int = 1200) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    return subprocess.run(
        argv,
        cwd=str(Path.cwd()),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _python_patch() -> str:
    info = sys.version_info
    return f"{info.major}.{info.minor}.{info.micro}"


def _read_lock(root: Path) -> None:
    """Require the exact hash-complete project lock before materialization."""
    lock_path = root / _DEV_LOCK_REL_PATH
    if not lock_path.is_file():
        raise LockInvalidError(f"project lock file {lock_path} does not exist")
    try:
        validate_lock_bytes(lock_path.read_bytes())
    except LockInvalid as exc:
        raise LockInvalidError(f"project lock {lock_path} is invalid: {exc}") from exc


def _create_venv(venv_dir: Path) -> None:
    completed = _run([sys.executable, "-m", "venv", str(venv_dir)], timeout=600)
    if completed.returncode != 0:
        raise MaterializeFailed("formal environment venv creation failed")


def _install_locked(venv_python: Path, root: Path) -> None:
    lock_path = root / _DEV_LOCK_REL_PATH
    argv = [
        str(venv_python),
        "-m",
        "pip",
        "install",
        "--isolated",
        "--disable-pip-version-check",
        "--no-input",
        "--require-hashes",
        "--no-deps",
        "--only-binary",
        ":all:",
        "--index-url",
        INDEX_URL,
        "-r",
        str(lock_path),
    ]
    completed = _run(argv)
    if completed.returncode != 0:
        raise MaterializeFailed(
            "hash-locked installation into the formal environment failed"
        )


def _verify_identities(venv_python: Path, root: Path, expected_python: str) -> None:
    """Probe the materialized interpreter and require exact lock agreement."""
    probe = (
        "import importlib.metadata as metadata\n"
        "import json\n"
        "import sys\n"
        "version = sys.version_info\n"
        "print(version.major, version.minor, version.micro)\n"
        "installed = {}\n"
        "for name in ('pytest', 'ruff', 'mypy'):\n"
        "    try:\n"
        "        installed[name] = metadata.version(name)\n"
        "    except metadata.PackageNotFoundError:\n"
        "        installed[name] = None\n"
        "print(json.dumps(installed, sort_keys=True))\n"
    )
    completed = _run([str(venv_python), "-c", probe], timeout=300)
    if completed.returncode != 0:
        raise MaterializeFailed("formal environment interpreter probe failed")
    lines = completed.stdout.splitlines()
    if len(lines) < 2:
        raise MaterializeFailed(
            "formal environment interpreter probe returned no identity"
        )
    try:
        major, minor, micro = (int(part) for part in lines[0].split())
    except ValueError as exc:
        raise MaterializeFailed(
            "formal environment interpreter probe is malformed"
        ) from exc
    actual_patch = f"{major}.{minor}.{micro}"
    if actual_patch != expected_python:
        raise MaterializeFailed(
            f"formal environment python is {actual_patch}, expected {expected_python}"
        )
    lock_entries = validate_lock_bytes((root / _DEV_LOCK_REL_PATH).read_bytes())
    locked: dict[str, str] = {}
    for entry in lock_entries:
        locked[entry.name] = entry.version
    try:
        installed = json.loads(lines[1])
    except json.JSONDecodeError as exc:
        raise MaterializeFailed(
            "formal environment tool identity probe is malformed"
        ) from exc
    if not isinstance(installed, dict):
        raise MaterializeFailed("formal environment tool identity probe is malformed")
    for tool in ("pytest", "ruff", "mypy"):
        installed_version = installed.get(tool)
        if installed_version != locked.get(tool):
            raise MaterializeFailed(
                f"formal {tool} is {installed_version!r}, lock requires "
                f"{locked.get(tool)!r}"
            )


def _run_bootstrap(opts: _Options) -> None:
    try:
        report = load_workspace_boundary_gate_report(opts.root)
    except (OSError, ValueError) as exc:
        raise EvidenceInvalid(str(exc)) from exc
    expected_python = report.gate_toolchain.python_version
    actual_python = _python_patch()
    if actual_python != expected_python:
        raise PythonVersionMismatch(expected_python, actual_python)
    _read_lock(opts.root)
    venv_dir = opts.root / _VENV_DIR_NAME
    venv_python = _venv_python(venv_dir)
    venv_created = not venv_python.is_file()
    try:
        if venv_created:
            _create_venv(venv_dir)
        _install_locked(venv_python, opts.root)
        _verify_identities(venv_python, opts.root, expected_python)
    except BaseException:
        if venv_created and venv_dir.exists():
            shutil.rmtree(venv_dir, ignore_errors=True)
        raise


def _emit_failure(error: BootstrapError) -> int:
    if isinstance(error, PythonVersionMismatch):
        sys.stderr.write(f"ERROR\t{error.code}:{error.expected}:{error.actual}\n")
    else:
        sys.stderr.write(f"ERROR\t{error.code}\n")
    sys.stderr.flush()
    return _EXIT_CODES[error.code]


def main(argv: list[str]) -> int:
    try:
        opts = _parse_argv(argv)
        _run_bootstrap(opts)
    except BootstrapError as exc:
        return _emit_failure(exc)
    except Exception:
        return _emit_failure(MaterializeFailed("unexpected bootstrap failure"))
    sys.stdout.write("OK\tbootstrap\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
