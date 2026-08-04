"""Raw-byte gate scan core for the T01.1 step 1.Aa bootstrap.

Scans the staged/unstaged/untracked changed-file union relative to HEAD for
fixed credential patterns. Operates on raw bytes only and never emits matched
bytes, values, or surrounding context.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_PRIVATE_KEY_BLOCK_RE = re.compile(
    rb"(?<![A-Za-z0-9_])-----BEGIN [A-Z0-9][A-Z0-9 -]* PRIVATE KEY-----"
    rb"(?![A-Za-z0-9_])"
)
_GENERIC_API_KEY_RE = re.compile(
    rb"(?<![A-Za-z0-9_])(?i:API_KEY|SECRET_KEY|ACCESS_TOKEN|AUTH_TOKEN)"
    rb"(?![A-Za-z0-9_])[ \t]*(?>=>|=|:)(?:([\"'])([^\n]+?)\1|"
    rb"[^ \t\r\n\v\f,;)}\x22']+)"
)
_CREDENTIAL_URL_RE = re.compile(
    rb"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@"
)

_RULES: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    ("PRIVATE_KEY_BLOCK", _PRIVATE_KEY_BLOCK_RE),
    ("GENERIC_API_KEY", _GENERIC_API_KEY_RE),
    ("CREDENTIAL_URL", _CREDENTIAL_URL_RE),
)


@dataclass(frozen=True)
class GateScanHooksV1:
    enumerate_changed_paths: Callable[[Path], tuple[str, ...]]
    resolve_path: Callable[[Path, str], Path]
    is_regular_file: Callable[[Path], bool]
    read_bytes: Callable[[Path], bytes]


@dataclass(frozen=True)
class GateScanRunResultV1:
    exit_code: int
    stdout: str
    stderr: str


def _git_list(root: Path, *args: str) -> tuple[str, ...]:
    proc = subprocess.run(
        ("git", "-c", "core.quotepath=false", *args),
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise OSError(f"git {' '.join(args)} exited {proc.returncode}")
    stdout = proc.stdout
    if stdout is None:
        raise OSError(f"git {' '.join(args)} produced no output")
    return tuple(
        line.decode("utf-8", "surrogateescape") for line in stdout.splitlines()
    )


def _expand_untracked_directory(root: Path, directory: str) -> tuple[str, ...]:
    """Expand a git untracked-directory entry to its files, sorted."""
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root / directory):
        dirnames.sort()
        filenames.sort()
        for filename in filenames:
            full = os.path.join(dirpath, filename)
            files.append(os.path.relpath(full, root).replace("\\", "/"))
    return tuple(files)


def _enumerate_changed_paths(root: Path) -> tuple[str, ...]:
    tracked = _git_list(root, "diff", "--name-only", "HEAD")
    untracked: list[str] = []
    for entry in _git_list(root, "ls-files", "--others", "--exclude-standard"):
        if entry.endswith("/") or (root / entry).is_dir():
            untracked.extend(_expand_untracked_directory(root, entry))
        else:
            untracked.append(entry)
    combined: list[str] = []
    seen: set[str] = set()
    for path in tracked + tuple(untracked):
        if path and path not in seen:
            seen.add(path)
            combined.append(path)
    return tuple(path for path in combined if (root / path).exists())


def _resolve_path(root: Path, path: str) -> Path:
    return (root / path).resolve()


def _read_path_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _scan_bytes(data: bytes) -> tuple[str, ...]:
    return tuple(
        rule_id for rule_id, pattern in _RULES if pattern.search(data) is not None
    )


def _escapes_root(root_text: str, resolved: Path) -> bool:
    try:
        resolved_text = os.path.abspath(os.path.normcase(str(resolved)))
    except Exception:
        return True
    if resolved_text == root_text:
        return False
    if resolved_text.startswith(root_text):
        tail = resolved_text[len(root_text) :]
        return not (tail.startswith("\\") or tail.startswith("/"))
    return True


def _error_result(code: str) -> GateScanRunResultV1:
    return GateScanRunResultV1(2, "", f"ERROR\t{code}\n")


def run_gate_scan(
    root: Path, *, hooks: GateScanHooksV1 | None = None
) -> GateScanRunResultV1:
    root = Path(root)
    if hooks is None:
        hooks = GateScanHooksV1(
            enumerate_changed_paths=_enumerate_changed_paths,
            resolve_path=_resolve_path,
            is_regular_file=os.path.isfile,
            read_bytes=_read_path_bytes,
        )
    try:
        changed_paths = hooks.enumerate_changed_paths(root)
    except Exception:
        return _error_result("GATE_SCAN_GIT_ENUMERATION_FAILED")
    root_text = os.path.abspath(os.path.normcase(str(root))).rstrip("\\/")
    facts: set[tuple[str, str]] = set()
    for path in changed_paths:
        try:
            resolved = hooks.resolve_path(root, path)
        except Exception:
            return _error_result("GATE_SCAN_PATH_ESCAPE")
        if _escapes_root(root_text, resolved):
            return _error_result("GATE_SCAN_PATH_ESCAPE")
        try:
            regular = hooks.is_regular_file(resolved)
        except Exception:
            regular = False
        if not regular:
            return _error_result("GATE_SCAN_NON_REGULAR_FILE")
        try:
            data = hooks.read_bytes(resolved)
        except Exception:
            return _error_result("GATE_SCAN_READ_FAILED")
        normalized = path.replace("\\", "/")
        for rule_id in _scan_bytes(data):
            facts.add((normalized, rule_id))
    if not facts:
        return GateScanRunResultV1(0, "", "")
    lines = sorted(f"MATCH\t{path}\t{rule_id}" for path, rule_id in facts)
    return GateScanRunResultV1(1, "\n".join(lines) + "\n", "")


def main(argv: list[str]) -> int:
    if argv:
        sys.stderr.write("ERROR\tGATE_SCAN_INVALID_ARGUMENT\n")
        return 2
    root = Path(__file__).resolve().parents[1]
    result = run_gate_scan(root)
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
