"""Bootstrap the closed hash-locked gate toolchain (T01.1 step 1.Ab/1.Ac).

This script owns the two bootstrap subcommands defined by the pre-RED gate
contract:

* ``resolve-lock`` resolves ``requirements/gate.in`` against the single fixed
  PyPI Simple index for the Windows / CPython 3.12 profile, and atomically
  publishes the reviewed ``requirements/gate.lock``.
* ``materialize`` creates the isolated ``.venv-gate`` at the repository root
  from the reviewed lock (``--require-hashes --no-deps``, fixed index only)
  and writes the exact ``GateToolchainEvidenceV1`` record only after lock
  review, hash-locked materialization, and positive integrity checks succeed.

The script uses only the standard library.  Every child process (venv, pip,
identity probes) is isolated from user and environment configuration and never
writes bytecode.  ``--require-existing-evidence`` is a read-only offline
validation path: it performs no pip, no index access, no lock rewrite, and no
evidence rewrite.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import NamedTuple

INDEX_URL = "https://pypi.org/simple"

REPO_ROOT = Path(__file__).resolve().parent.parent

GATE_ARGUMENT_INVALID = "GATE_ARGUMENT_INVALID"
GATE_PYTHON_VERSION_MISMATCH = "GATE_PYTHON_VERSION_MISMATCH"
GATE_LOCK_INVALID = "GATE_LOCK_INVALID"
GATE_RESOLUTION_FAILED = "GATE_RESOLUTION_FAILED"
GATE_MATERIALIZE_FAILED = "GATE_MATERIALIZE_FAILED"
GATE_EVIDENCE_INVALID = "GATE_EVIDENCE_INVALID"

_EXIT_CODES = {
    GATE_ARGUMENT_INVALID: 2,
    GATE_PYTHON_VERSION_MISMATCH: 3,
    GATE_LOCK_INVALID: 4,
    GATE_RESOLUTION_FAILED: 5,
    GATE_MATERIALIZE_FAILED: 6,
    GATE_EVIDENCE_INVALID: 7,
}

_REQUIRED_EVIDENCE_FIELDS = frozenset(
    {
        "schema_version",
        "evidence_type",
        "python_version",
        "pytest_version",
        "ruff_version",
        "mypy_version",
        "gate_input_sha256",
        "gate_lock_sha256",
        "pytest_config_sha256",
        "ruff_config_sha256",
        "mypy_config_sha256",
        "runner_sha256",
        "gate_scan_sha256",
        "gate_scan_core_sha256",
        "evidence_digest",
    }
)

# Evidence field -> repository-relative path of the file whose raw bytes are
# hashed.  ``gate_lock_sha256`` is special-cased: it binds the lock file
# supplied to the current invocation rather than a fixed repository path.
_EVIDENCE_DIGEST_PATHS = {
    "gate_input_sha256": ("requirements", "gate.in"),
    "gate_lock_sha256": None,
    "pytest_config_sha256": ("gates", "pytest.ini"),
    "ruff_config_sha256": ("gates", "ruff.toml"),
    "mypy_config_sha256": ("gates", "mypy.ini"),
    "runner_sha256": ("scripts", "run_gate_checks.py"),
    "gate_scan_sha256": ("scripts", "scan_gate_changed_files.ps1"),
    "gate_scan_core_sha256": ("scripts", "gate_scan.py"),
}


class BootstrapError(Exception):
    """Base class for the stable gate failure codes."""

    code: str


class ArgumentInvalid(BootstrapError):
    code = GATE_ARGUMENT_INVALID


class PythonVersionMismatch(BootstrapError):
    code = GATE_PYTHON_VERSION_MISMATCH


class LockInvalid(BootstrapError):
    code = GATE_LOCK_INVALID


class ResolutionFailed(BootstrapError):
    code = GATE_RESOLUTION_FAILED


class MaterializeFailed(BootstrapError):
    code = GATE_MATERIALIZE_FAILED


class EvidenceInvalid(BootstrapError):
    code = GATE_EVIDENCE_INVALID


class LockEntry(NamedTuple):
    """One accepted lock entry: normalized name, pinned version, sha256s."""

    name: str
    version: str
    hashes: tuple[str, ...]


def normalize_dist_name(name: str) -> str:
    """PEP 503 normalized distribution name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def sha256_file(path: Path) -> str:
    """Lowercase SHA-256 of the raw bytes of ``path`` (raises OSError)."""
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: dict[str, object]) -> str:
    """Canonical JSON serialization: sorted keys, no insignificant whitespace."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def compute_evidence_digest(evidence: dict[str, object]) -> str:
    """SHA-256 of the canonical JSON of ``evidence`` with its digest omitted."""
    without_digest = {
        key: value for key, value in evidence.items() if key != "evidence_digest"
    }
    return hashlib.sha256(canonical_json(without_digest).encode("utf-8")).hexdigest()


def build_evidence_object(
    lock_path: Path,
    repo_root: Path,
    python_version: str,
    tool_versions: dict[str, str],
) -> dict[str, object]:
    """Build the exact GateToolchainEvidenceV1 object (digest included)."""
    evidence = {
        "schema_version": 1,
        "evidence_type": "GATE_TOOLCHAIN_EVIDENCE_V1",
        "python_version": python_version,
        "pytest_version": tool_versions["pytest"],
        "ruff_version": tool_versions["ruff"],
        "mypy_version": tool_versions["mypy"],
    }
    for field, rel_path in _EVIDENCE_DIGEST_PATHS.items():
        if rel_path is None:
            evidence[field] = sha256_file(lock_path)
        else:
            evidence[field] = sha256_file(repo_root.joinpath(*rel_path))
    evidence["evidence_digest"] = compute_evidence_digest(evidence)
    return evidence


def verify_evidence(evidence: object, lock_path: Path, repo_root: Path) -> None:
    """Verify an evidence record against its files without mutating anything.

    Checks the exact field set, schema/type literals, every digest against the
    current raw file bytes, and the evidence_digest round-trip.
    """
    if not isinstance(evidence, dict):
        raise EvidenceInvalid("evidence record is not a JSON object")
    if set(evidence) != _REQUIRED_EVIDENCE_FIELDS:
        raise EvidenceInvalid("evidence record has unexpected or missing fields")
    if evidence["schema_version"] != 1:
        raise EvidenceInvalid("evidence record has an unexpected schema version")
    if evidence["evidence_type"] != "GATE_TOOLCHAIN_EVIDENCE_V1":
        raise EvidenceInvalid("evidence record has an unexpected evidence type")
    if re.fullmatch(r"3\.12\.[0-9]+", evidence["python_version"]) is None:
        raise EvidenceInvalid("evidence python version is not an exact 3.12.x")
    for tool in ("pytest", "ruff", "mypy"):
        version = evidence[f"{tool}_version"]
        if not isinstance(version, str) or not version or " " in version:
            raise EvidenceInvalid(f"evidence {tool} version is malformed")
    for field, rel_path in _EVIDENCE_DIGEST_PATHS.items():
        if rel_path is None:
            path = lock_path
        else:
            path = repo_root.joinpath(*rel_path)
        try:
            actual = sha256_file(path)
        except OSError as exc:
            raise EvidenceInvalid(
                f"cannot hash {path} while verifying evidence"
            ) from exc
        if evidence[field] != actual:
            raise EvidenceInvalid(f"{field} no longer matches {path}")
    if evidence["evidence_digest"] != compute_evidence_digest(evidence):
        raise EvidenceInvalid("evidence digest does not round-trip")


_LINE_PATTERN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*?)==([^=\s;]+)(.*)$")
_HASH_PATTERN = re.compile(r"--hash=sha256:[0-9a-f]{64}")
_MARKER_CHARS = re.compile(r"[A-Za-z0-9 ._\-()<>=~!\"']+")


def _is_plausible_marker(text: str) -> bool:
    if not text or text.startswith((";", "==", "--")) or ";" in text:
        return False
    if _MARKER_CHARS.fullmatch(text) is None:
        return False
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _parse_lock_line(line: str) -> tuple[str, str, tuple[str, ...]]:
    match = _LINE_PATTERN.match(line)
    if match is None:
        raise LockInvalid(f"malformed lock line: {line!r}")
    name, version, rest = match.groups()
    rest = rest.strip()
    if not rest:
        raise LockInvalid(f"missing hashes on {name}=={version}")
    if "@" in line or "/" in line or "\\" in line or ":" in version or "*" in version:
        raise LockInvalid(
            f"unsupported source or unpinned version in lock line: {line!r}"
        )
    tokens = rest.split()
    marker = None
    index = 0
    if not tokens[0].startswith("--hash="):
        if tokens[0] != ";":
            raise LockInvalid(f"unexpected token {tokens[0]!r} in lock line")
        marker_parts: list[str] = []
        index = 1
        while index < len(tokens) and not tokens[index].startswith("--hash="):
            marker_parts.append(tokens[index])
            index += 1
        marker = " ".join(marker_parts).strip()
        if not marker or not _is_plausible_marker(marker):
            raise LockInvalid(f"malformed marker in lock line: {line!r}")
    hashes: list[str] = []
    for token in tokens[index:]:
        if _HASH_PATTERN.fullmatch(token) is None:
            raise LockInvalid(
                f"unsupported hash or unexpected token {token!r} on {name}"
            )
        hashes.append(token.removeprefix("--hash=sha256:"))
    if not hashes:
        raise LockInvalid(f"no hashes on {name}=={version}")
    return name, version, tuple(sorted(set(hashes)))


def validate_lock_bytes(lock_bytes: bytes) -> list[LockEntry]:
    """Validate the exact lock format and return its normalized entries.

    The first line must be exactly ``--index-url https://pypi.org/simple``;
    every remaining non-empty line is one ``name==version [; marker]
    --hash=sha256:...`` entry, each name appears exactly once, entries are
    sorted by normalized name, and every hash is a lowercase SHA-256.
    """
    if not lock_bytes.endswith(b"\n"):
        raise LockInvalid("lock file does not end with a newline")
    try:
        text = lock_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LockInvalid("lock file is not valid UTF-8") from exc
    lines = text.split("\n")
    if not lines or lines[0] != f"--index-url {INDEX_URL}":
        raise LockInvalid("lock file must start with the fixed index line")
    entries: list[LockEntry] = []
    seen: set[str] = set()
    previous: str | None = None
    for raw_line in lines[1:]:
        line = raw_line.strip()
        if not line:
            continue
        name, version, hashes = _parse_lock_line(line)
        normalized = normalize_dist_name(name)
        if normalized in seen:
            raise LockInvalid(f"duplicate distribution {normalized} in lock")
        if previous is not None and normalized < previous:
            raise LockInvalid("lock entries are not sorted by normalized name")
        seen.add(normalized)
        previous = normalized
        entries.append(LockEntry(normalized, version, hashes))
    if not entries:
        raise LockInvalid("lock file contains no distribution entries")
    return entries


def validate_lock_path(lock_path: Path) -> list[LockEntry]:
    """Read and validate the lock file at ``lock_path``."""
    try:
        data = lock_path.read_bytes()
    except OSError as exc:
        raise LockInvalid(f"cannot read lock file {lock_path}") from exc
    return validate_lock_bytes(data)


def _write_atomic(destination: Path, data: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / f".{destination.name}.{os.getpid()}.tmp"
    try:
        temporary.write_bytes(data)
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass


def _run(argv: list[str], *, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    return subprocess.run(
        argv,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _read_direct_requirements(input_path: Path) -> list[str]:
    try:
        data = input_path.read_bytes()
    except OSError as exc:
        raise LockInvalid(f"cannot read requirements input {input_path}") from exc
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LockInvalid(f"requirements input {input_path} is not UTF-8") from exc
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lowered = line.lower()
        if (
            line.startswith(("-", ".", "/", "\\"))
            or "@" in line
            or "/" in line
            or "\\" in line
            or ":" in line
            or "[" in line
            or "]" in line
            or lowered.startswith(("git+", "file:", "http://", "https://"))
        ):
            raise LockInvalid(f"unsupported requirement line {line!r} in {input_path}")
        if re.match(r"^[A-Za-z0-9][A-Za-z0-9._\-]*(\s*[<>=!~].*)?$", line) is None:
            raise LockInvalid(f"unsupported requirement line {line!r} in {input_path}")
        lines.append(line)
    if not lines:
        raise LockInvalid(f"requirements input {input_path} has no requirements")
    return lines


def _fetch_simple_index(url: str) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.pypi.simple.v1+json",
            "User-Agent": "vesper-gate-bootstrap/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        raise ResolutionFailed(f"index HTTP error {exc.code} for {url}") from exc
    except OSError as exc:
        raise ResolutionFailed(f"index fetch failed for {url}") from exc
    try:
        document = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LockInvalid(f"index response for {url} is not PEP 691 JSON") from exc
    if not isinstance(document, dict):
        raise LockInvalid(f"index response for {url} is not a JSON object")
    return document


def _wheel_compatible(python_tag: str, abi_tag: str, platform_tag: str) -> bool:
    if platform_tag not in ("win_amd64", "any"):
        return False
    if python_tag in ("py3", "py312", "py2.py3"):
        return abi_tag == "none"
    if python_tag == "cp312":
        return abi_tag in ("cp312", "abi3")
    match = re.fullmatch(r"cp3([0-9]+)", python_tag)
    if match is not None and int(match.group(1)) < 12:
        return abi_tag == "abi3"
    return False


def _discover_hashes(name: str, version: str, index_url: str) -> tuple[str, ...]:
    """Collect SHA-256 hashes of every compatible file of the exact release.

    Requests only the fixed PyPI Simple endpoint (PEP 691 JSON Accept header)
    for the normalized package name, filters files by normalized distribution
    name and the exact selected release version parsed from the wheel
    filename, keeps only Windows x64 / CPython 3.12 compatible files, and
    takes the values from the PEP 691 ``hashes`` mapping.  Malformed fields
    take the stable lock-invalid path.
    """
    url = index_url.rstrip("/") + "/" + name + "/"
    data = _fetch_simple_index(url)
    files = data.get("files")
    if not isinstance(files, list):
        raise LockInvalid(f"index file for {name} has no file list")
    expected_version = version.replace("-", "_")
    digests: set[str] = set()
    for file_info in files:
        if not isinstance(file_info, dict):
            raise LockInvalid(f"index file for {name} has a malformed entry")
        filename = file_info.get("filename")
        if not isinstance(filename, str) or not filename.endswith(".whl"):
            continue
        parts = filename[:-4].split("-")
        if len(parts) < 5:
            continue
        if normalize_dist_name(parts[0]) != name:
            continue
        if parts[1] != expected_version:
            continue
        py_tag, abi_tag, plat_tag = parts[-3], parts[-2], parts[-1]
        if not _wheel_compatible(py_tag, abi_tag, plat_tag):
            continue
        hashes = file_info.get("hashes")
        if not isinstance(hashes, dict) or not isinstance(hashes.get("sha256"), str):
            raise LockInvalid(f"missing sha256 for {filename}")
        digest = hashes["sha256"].lower()
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise LockInvalid(f"invalid sha256 for {filename}")
        digests.add(digest)
    if not digests:
        raise LockInvalid(f"no compatible files with hashes for {name}=={version}")
    return tuple(sorted(digests))


def _pip_resolution_report(input_path: Path, index_url: str) -> dict[str, object]:
    """Resolve the direct requirements with pip for the Windows/3.12 profile.

    The pip invocation is fully isolated (``--isolated``, explicit fixed
    index, no inherited config), targets the fixed cross platform flags, and
    writes a dry-run JSON report without installing anything.
    """
    handle, report_name = tempfile.mkstemp(prefix="gate-resolve-", suffix=".json")
    os.close(handle)
    report_path = Path(report_name)
    try:
        argv = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--dry-run",
            "--ignore-installed",
            "--isolated",
            "--disable-pip-version-check",
            "--no-input",
            "--index-url",
            index_url,
            "--only-binary",
            ":all:",
            "--platform",
            "win_amd64",
            "--python-version",
            "3.12",
            "--implementation",
            "cp",
            "--abi",
            "cp312",
            "--report",
            str(report_path),
            "-r",
            str(input_path),
        ]
        completed = _run(argv, timeout=1200)
        if completed.returncode != 0:
            raise ResolutionFailed("pip could not resolve the gate requirements")
        try:
            with report_path.open("r", encoding="utf-8") as report_file:
                report = json.load(report_file)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResolutionFailed("pip resolution report could not be parsed") from exc
    finally:
        try:
            report_path.unlink()
        except OSError:
            pass
    if not isinstance(report, dict):
        raise ResolutionFailed("pip resolution report is not a JSON object")
    return report


def _resolve_entries(input_path: Path, index_url: str) -> list[LockEntry]:
    report = _pip_resolution_report(input_path, index_url)
    installs = report.get("install")
    if not isinstance(installs, list) or not installs:
        raise ResolutionFailed("pip resolution produced no install set")
    by_name: dict[str, tuple[str, tuple[str, ...]]] = {}
    for item in installs:
        if not isinstance(item, dict):
            raise ResolutionFailed("pip resolution report is malformed")
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            raise ResolutionFailed("pip resolution report is malformed")
        name = metadata.get("name")
        version = metadata.get("version")
        if (
            not isinstance(name, str)
            or not isinstance(version, str)
            or not name
            or not version
        ):
            raise ResolutionFailed("pip resolution report is missing name or version")
        normalized = normalize_dist_name(name)
        if normalized in by_name:
            raise ResolutionFailed(f"conflicting resolutions for {normalized}")
        by_name[normalized] = (
            version,
            _discover_hashes(normalized, version, index_url),
        )
    return [
        LockEntry(name, version, hashes)
        for name, (version, hashes) in sorted(by_name.items())
    ]


def _run_resolve_lock(opts: dict[str, object]) -> None:
    input_path = Path(str(opts["input"])).resolve()
    lock_path = Path(str(opts["lock"])).resolve()
    _read_direct_requirements(input_path)
    entries = _resolve_entries(input_path, INDEX_URL)
    lines = [f"--index-url {INDEX_URL}"]
    for entry in entries:
        line = f"{entry.name}=={entry.version}"
        for digest in entry.hashes:
            line += f" --hash=sha256:{digest}"
        lines.append(line)
    content = ("\n".join(lines) + "\n").encode("utf-8")
    try:
        validate_lock_bytes(content)
    except LockInvalid as exc:
        raise ResolutionFailed("resolved lock failed its own validation") from exc
    _write_atomic(lock_path, content)


def _require_toolchain_inputs(repo_root: Path) -> None:
    for rel_path in _EVIDENCE_DIGEST_PATHS.values():
        if rel_path is not None and not repo_root.joinpath(*rel_path).is_file():
            raise MaterializeFailed(f"missing toolchain input {'/'.join(rel_path)}")


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _create_venv(venv_dir: Path) -> None:
    completed = _run([sys.executable, "-m", "venv", str(venv_dir)])
    if completed.returncode != 0:
        raise MaterializeFailed("venv creation failed")


def _install_locked(venv_python: Path, lock_path: Path) -> None:
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
    completed = _run(argv, timeout=1200)
    if completed.returncode != 0:
        raise MaterializeFailed(
            "hash-locked installation into the gate environment failed"
        )


def _identity_probe(names: list[str]) -> str:
    return (
        "import importlib.metadata as metadata\n"
        "import json\n"
        "import sys\n"
        "version = sys.version_info\n"
        "print(version.major, version.minor, version.micro)\n"
        "names = " + repr(sorted(names)) + "\n"
        "installed = {}\n"
        "for name in names:\n"
        "    try:\n"
        "        installed[name] = metadata.version(name)\n"
        "    except metadata.PackageNotFoundError:\n"
        "        installed[name] = None\n"
        "print(json.dumps(installed, sort_keys=True))\n"
    )


def _installed_identities(
    venv_python: Path, names: list[str]
) -> tuple[str, dict[str, str | None]]:
    probe = _identity_probe(names)
    completed = _run([str(venv_python), "-c", probe])
    if completed.returncode != 0:
        raise MaterializeFailed("gate environment interpreter probe failed")
    stdout_lines = completed.stdout.splitlines()
    if len(stdout_lines) < 2:
        raise MaterializeFailed(
            "gate environment interpreter probe returned no identity"
        )
    try:
        major, minor, micro = (int(part) for part in stdout_lines[0].split())
    except ValueError as exc:
        raise MaterializeFailed(
            "gate environment interpreter probe is malformed"
        ) from exc
    if (major, minor) != (3, 12):
        raise MaterializeFailed(
            f"gate environment interpreter is {major}.{minor}, expected 3.12"
        )
    try:
        installed = json.loads(stdout_lines[1])
    except json.JSONDecodeError as exc:
        raise MaterializeFailed(
            "gate environment tool identity probe is malformed"
        ) from exc
    if not isinstance(installed, dict):
        raise MaterializeFailed("gate environment tool identity probe is malformed")
    return f"{major}.{minor}.{micro}", dict(installed)


def _check_installed_versions(
    entries: list[LockEntry],
    python_version: str,
    tool_versions: dict[str, str | None],
) -> dict[str, str]:
    """Verify installed identities against the lock; return the narrowed map."""
    if not python_version.startswith("3.12."):
        raise MaterializeFailed(
            f"gate python version {python_version} drifted from 3.12"
        )
    verified: dict[str, str] = {}
    for entry in entries:
        installed = tool_versions.get(entry.name)
        if installed is None or installed != entry.version:
            raise MaterializeFailed(
                f"installed {entry.name} is {installed!r}, lock requires "
                f"{entry.version}"
            )
        verified[entry.name] = installed
    return verified


def _require_existing(lock_path: Path, evidence_path: Path, repo_root: Path) -> None:
    """Read-only offline validation of an already materialized gate."""
    if not lock_path.is_file():
        raise LockInvalid(f"lock file {lock_path} does not exist")
    if not evidence_path.is_file():
        raise EvidenceInvalid(f"evidence file {evidence_path} does not exist")
    entries = validate_lock_path(lock_path)
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceInvalid("evidence file is not readable UTF-8 JSON") from exc
    verify_evidence(evidence, lock_path, repo_root)
    venv_python = _venv_python(repo_root / ".venv-gate")
    if not venv_python.is_file():
        raise MaterializeFailed("gate environment is not materialized")
    python_version, tool_versions = _installed_identities(
        venv_python, [entry.name for entry in entries]
    )
    verified_versions = _check_installed_versions(
        entries, python_version, tool_versions
    )
    if python_version != evidence["python_version"]:
        raise MaterializeFailed(
            "installed python version drifted from the evidence record"
        )
    for tool in ("pytest", "ruff", "mypy"):
        if verified_versions.get(tool) != evidence[f"{tool}_version"]:
            raise MaterializeFailed(
                f"installed {tool} version drifted from the evidence record"
            )


def _run_materialize(opts: dict[str, object]) -> None:
    lock_path = Path(str(opts["lock"])).resolve()
    evidence_path = Path(str(opts["evidence"])).resolve()
    require_existing = bool(opts["require_existing"])
    repo_root = REPO_ROOT
    if require_existing:
        _require_existing(lock_path, evidence_path, repo_root)
        return
    validate_lock_path(lock_path)
    _require_toolchain_inputs(repo_root)
    venv_dir = repo_root / ".venv-gate"
    venv_python = _venv_python(venv_dir)
    venv_created = not venv_dir.exists()
    try:
        if venv_created:
            _create_venv(venv_dir)
        _install_locked(venv_python, lock_path)
        entries = validate_lock_path(lock_path)
        python_version, tool_versions = _installed_identities(
            venv_python, [entry.name for entry in entries]
        )
        verified_versions = _check_installed_versions(
            entries, python_version, tool_versions
        )
        evidence = build_evidence_object(
            lock_path, repo_root, python_version, verified_versions
        )
        _write_atomic(evidence_path, canonical_json(evidence).encode("utf-8"))
    except BaseException:
        if venv_created and venv_dir.exists():
            shutil.rmtree(venv_dir, ignore_errors=True)
        raise


def _parse_argv(argv: list[str]) -> tuple[str, dict[str, object]]:
    if not argv:
        raise ArgumentInvalid("missing subcommand")
    subcommand = argv[0]
    if subcommand == "resolve-lock":
        if (
            len(argv) != 7
            or argv[1] != "--input"
            or argv[3] != "--lock"
            or argv[5] != "--index-url"
        ):
            raise ArgumentInvalid("malformed resolve-lock invocation")
        if argv[6] != INDEX_URL:
            raise ArgumentInvalid("unexpected --index-url value")
        return subcommand, {
            "input": argv[2],
            "lock": argv[4],
            "index_url": argv[6],
        }
    if subcommand == "materialize":
        if len(argv) not in (5, 6) or argv[1] != "--lock" or argv[3] != "--evidence":
            raise ArgumentInvalid("malformed materialize invocation")
        require_existing = False
        if len(argv) == 6:
            if argv[5] != "--require-existing-evidence":
                raise ArgumentInvalid("unexpected trailing argument")
            require_existing = True
        return subcommand, {
            "lock": argv[2],
            "evidence": argv[4],
            "require_existing": require_existing,
        }
    raise ArgumentInvalid(f"unknown subcommand {subcommand!r}")


def _emit_failure(code: str) -> int:
    sys.stderr.write(f"ERROR\t{code}\n")
    sys.stderr.flush()
    return _EXIT_CODES[code]


def main(
    argv: list[str],
    *,
    python_version_info: tuple[int, int, int] | None = None,
) -> int:
    """Run the bootstrap CLI and return the process exit code.

    ``python_version_info`` is a test seam: ``None`` reads the running
    interpreter's ``sys.version_info[:3]``; otherwise the given triple is
    used for the Python 3.12 gate check.
    """
    fallback_code = GATE_RESOLUTION_FAILED
    try:
        subcommand, opts = _parse_argv(argv)
        fallback_code = (
            GATE_MATERIALIZE_FAILED
            if subcommand == "materialize"
            else GATE_RESOLUTION_FAILED
        )
        python_info = (
            python_version_info
            if python_version_info is not None
            else sys.version_info[:3]
        )
        if tuple(python_info)[:2] != (3, 12):
            raise PythonVersionMismatch("gate requires CPython 3.12")
        if subcommand == "resolve-lock":
            _run_resolve_lock(opts)
        else:
            _run_materialize(opts)
    except BootstrapError as exc:
        return _emit_failure(exc.code)
    except Exception:
        return _emit_failure(fallback_code)
    sys.stdout.write(f"OK\t{subcommand}\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
