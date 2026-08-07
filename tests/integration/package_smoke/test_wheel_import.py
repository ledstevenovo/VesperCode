"""Wheel package smoke: the installed wheel must import as ``vespercode``.

The repository uses the standard src layout, so the built wheel installs
the top-level ``vespercode`` package; every internal import uses
``from vespercode...`` (never ``src.vespercode``), which resolves in the
checkout only because pytest adds ``src`` to the path.  This test builds a
real wheel, installs it into a clean virtualenv, and imports the core
modules from site-packages — a ``src.vespercode``-style import would fail
there, so a packaged import break is caught in the package_smoke
environment instead of silently passing on a checkout root.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.package_smoke

# tests/integration/package_smoke/test_wheel_import.py -> parents[3] is
# the repository root (parents[2] would be the tests directory).
_ROOT = Path(__file__).resolve().parents[3]


def _run(*args: str, cwd: Path) -> None:
    subprocess.run(
        args,
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


def test_wheel_install_imports_core_modules(tmp_path: Path) -> None:
    build_dir = tmp_path / "wheelhouse"
    build_dir.mkdir()
    _run(
        sys.executable,
        "-m",
        "build",
        "--wheel",
        "--outdir",
        str(build_dir),
        cwd=_ROOT,
    )
    wheels = list(build_dir.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, got {wheels}"

    venv = tmp_path / "venv"
    _run(sys.executable, "-m", "venv", str(venv), cwd=tmp_path)
    if sys.platform == "win32":
        pip = venv / "Scripts" / "pip.exe"
        python = venv / "Scripts" / "python.exe"
    else:
        pip = venv / "bin" / "pip"
        python = venv / "bin" / "python"
    _run(str(pip), "install", str(wheels[0]), cwd=tmp_path)

    # Import every public module of the installed package: a single
    # ``from src.vespercode...`` import anywhere would fail to resolve in
    # the clean venv (site-packages has no ``src`` namespace), so a
    # packaged import regression in ANY module is caught here — not just
    # in the handful of core modules.
    probe = (
        "import vespercode, pkgutil\n"
        "failed = []\n"
        "for info in pkgutil.walk_packages("
        "vespercode.__path__, 'vespercode.'):\n"
        "    try:\n"
        "        __import__(info.name)\n"
        "    except Exception as exc:\n"
        "        failed.append((info.name, str(exc)))\n"
        "print('ALL_IMPORTED' if not failed else 'IMPORT_FAILURES')\n"
        "print(failed)\n"
    )
    result = subprocess.run(
        [str(python), "-c", probe],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "ALL_IMPORTED" in result.stdout, result.stdout
