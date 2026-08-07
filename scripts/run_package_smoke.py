"""T33.1 Wheel Build and Clean pipx Distribution Smoke driver.

Legacy step 33.A builds exactly one versioned wheel containing every
declared runtime resource (the frozen console entry point included),
publishes adjacent lowercase SHA-256 evidence computed from the exact
wheel bytes, and exposes the archive facts (filename/version/RECORD/
member bytes) to the package smoke tests.  Legacy step 33.B installs
that exact wheel into a fresh project-specific isolated pipx home and
proves the installed CLI (``vespercode --help``), the production WebUI
composition (the frozen governance-then-operations installer tuple over
the packaged app with the identity-verified packaged asset), and the
read-only recovery preview — every proof runs with no ``PYTHONPATH``
and a working directory outside the source checkout, so zero
source-checkout import or preview write is observable.

The driver owns the harness vocabulary only (``PackageSmokeConfigV1``,
``PackageSmokeResultV1``, ``WheelArchive``, ``InstalledPackage``, the
isolated pipx install, the installed probe, redaction); packaging
metadata, dependency tables, the build backend, lockfiles, indexes,
source behavior, and publication remain out of scope (GREEN-4).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, StrictStr

_REPO_ROOT: Final = Path(__file__).resolve().parents[1]
"""The repository root (``scripts/`` is one level below it)."""

WHEEL_GLOB: Final = "vespercode-*.whl"
"""The one declared wheel name pattern (33.A interface)."""

PIPX_ROOT_PREFIX_V1: Final = "vespercode-pipx-"
"""The fresh project-specific pipx home root prefix (33.B GREEN-1)."""

PACKAGE_SMOKE_REPORT_DEFAULT_V1: Final = "tests/.tmp/package-smoke-report.json"
"""The default content-addressed smoke report location."""

_APP_NAME_V1: Final = "vespercode"
"""The installed application name of the wheel (the pipx app name)."""

EXPECTED_HTMX_BYTE_LENGTH_V1: Final = 50917
"""The pinned packaged htmx asset byte length (Task 28.C identity)."""

EXPECTED_HTMX_SHA256_V1: Final = (
    "e209dda5c8235479f3166defc7750e1dbcd5a5c1808b7792fc2e6733768fb447"
)
"""The pinned packaged htmx asset SHA-256 (Task 28.C identity)."""

_EXPECTED_HEALTHZ_BODY_V1: Final = '{"status":"ok","mode":"simulation"}'
"""The exact canonical Demo /healthz body (SPEC §8.3)."""

EXPECTED_RECOVERY_PREVIEW_KIND_V1: Final = "NO_TRANSACTION"
"""The exact read-only preview kind of a fresh workspace (Task 38.F)."""

_EXPECTED_RECOVERY_HINT_V1: Final = "没有非终态恢复事务"
"""The exact bounded recovery preview projection hint (Task 38.E)."""

_OUTPUT_LIMIT_V1: Final = 1024
"""The bounded redacted output length of one command outcome (SPEC
§5.4: logs limit and redact output text)."""

_RUN_TIMEOUT_SECONDS_V1: Final = 600
"""The closed subprocess timeout of every smoke command."""

_SERVER_START_TIMEOUT_SECONDS_V1: Final = 60
"""The closed uvicorn startup timeout of the installed probes."""


class PackageSmokeErrorV1(RuntimeError):
    """One closed package-smoke failure (bounded message only)."""


class RedactedCommandOutcomeV1(BaseModel):
    """One bounded redacted command outcome (SPEC §5.4).

    The output is length-limited and path-redacted, so the report never
    carries unbounded tooling text or temp/control paths.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    label: StrictStr
    exit_code: int
    output: StrictStr


class RecordEntryV1(BaseModel):
    """One parsed wheel RECORD row: member path, recorded digest, size."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    path: StrictStr
    sha256: StrictStr | None
    size: int | None


class WheelArchive(BaseModel):
    """One closed inspection of the built wheel archive.

    ``members`` is the set of every member name plus every ancestor
    directory prefix, so the exact RED's ``PROHIBITED_WHEEL_MEMBERS
    isdisjoint`` check catches any prohibited name or prefix (e.g. a
    ``tests/x.py`` member adds the ``tests`` and ``tests/`` prefixes);
    ``record_entries`` is the parsed RECORD and ``sha256`` the digest of
    the exact wheel bytes.  ``member_bytes`` reads member content from
    the archive itself, never from the source tree (GREEN-2).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    wheel_path: Path
    name: StrictStr
    version: StrictStr
    member_names: tuple[StrictStr, ...]
    members: frozenset[StrictStr]
    record_entries: tuple[RecordEntryV1, ...]
    sha256: StrictStr
    evidence_path: Path | None
    evidence_sha256: StrictStr | None

    def member_bytes(self, member: str) -> bytes:
        """Read the exact bytes of one member from the wheel archive."""
        with zipfile.ZipFile(self.wheel_path) as archive:
            return archive.read(member)


class InstalledCommandResultV1(BaseModel):
    """One installed-command outcome plus its source-import fact.

    ``source_checkout_import`` records whether the command's import of
    the installed package resolved into the source checkout instead of
    the isolated pipx venv (a closed source-fallback violation).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    command: StrictStr
    exit_code: int
    output: StrictStr
    source_checkout_import: bool


class InstalledPackage:
    """One fresh isolated pipx-installed package harness (33.B GREEN-1).

    ``run`` executes a packaged entry point from the isolated bin
    directory with a clean environment (no ``PYTHONPATH``, no pipx
    variables) and a working directory outside the source checkout, so
    every resolved ``vespercode`` import must come from the installed
    wheel; ``source_checkout_import_count`` stays zero unless a command
    falls back to the source checkout.
    """

    def __init__(
        self,
        *,
        wheel_path: Path,
        root: Path,
        home: Path,
        bin_dir: Path,
        venv_dir: Path,
        python: Path,
        source_src: Path,
        sandbox: Path,
    ) -> None:
        self._wheel_path = wheel_path
        self._root = root
        self._home = home
        self._bin_dir = bin_dir
        self._venv_dir = venv_dir
        self._python = python
        self._source_src = source_src
        self._sandbox = sandbox
        self._runs: list[InstalledCommandResultV1] = []

    @property
    def wheel_digest(self) -> str:
        """The SHA-256 of the exact wheel bytes (33.A binding)."""
        return wheel_sha256(self._wheel_path)

    @property
    def root(self) -> Path:
        """The fresh project-specific pipx root (home + bin + data)."""
        return self._root

    @property
    def home(self) -> Path:
        """The isolated pipx home (``PIPX_HOME``)."""
        return self._home

    @property
    def bin_dir(self) -> Path:
        """The isolated pipx bin directory (``PIPX_BIN_DIR``)."""
        return self._bin_dir

    @property
    def venv_dir(self) -> Path:
        """The isolated pipx application venv of the installed package."""
        return self._venv_dir

    @property
    def python(self) -> Path:
        """The interpreter of the isolated application venv."""
        return self._python

    @property
    def entry_point(self) -> Path:
        """The installed ``vespercode`` console script of the wheel."""
        name = _APP_NAME_V1 + (".exe" if os.name == "nt" else "")
        return self._bin_dir / name

    @property
    def source_checkout_import_count(self) -> int:
        """The number of smoke commands that imported the source
        checkout instead of the installed package."""
        return sum(1 for outcome in self._runs if outcome.source_checkout_import)

    @property
    def runs(self) -> tuple[InstalledCommandResultV1, ...]:
        """Every executed installed-command outcome, in order."""
        return tuple(self._runs)

    def run(self, executable: str, *args: str) -> InstalledCommandResultV1:
        """Execute one packaged entry point in the clean sandbox.

        The working directory is the sandbox outside the repository, the
        environment carries no ``PYTHONPATH``, and the source-import
        fact is probed through the installed venv interpreter after the
        command.  A missing executable (the installed-help smoke not yet
        implemented) fails closed with exit code 1.
        """
        exe = self._bin_dir / (executable + (".exe" if os.name == "nt" else ""))
        label = " ".join((executable, *args))
        env = self._clean_env()
        try:
            proc = subprocess.run(
                [str(exe), *args],
                cwd=str(self._sandbox),
                env=env,
                capture_output=True,
                text=True,
                timeout=_RUN_TIMEOUT_SECONDS_V1,
                check=False,
            )
            exit_code, raw = proc.returncode, proc.stdout + proc.stderr
        except FileNotFoundError:
            # The clean installed-help smoke is not implemented yet: the
            # isolated pipx install has not produced the entry point, so
            # the command fails closed with exit 1 and no import probe
            # (there is no installed venv to probe).
            outcome = InstalledCommandResultV1(
                schema_version=1,
                command=label,
                exit_code=1,
                output=(
                    "installed executable not found: the clean installed-help "
                    "smoke has not been implemented"
                ),
                source_checkout_import=False,
            )
            self._runs.append(outcome)
            return outcome
        outcome = InstalledCommandResultV1(
            schema_version=1,
            command=label,
            exit_code=exit_code,
            output=redact_output(raw, (str(self._root), str(self._sandbox))),
            source_checkout_import=self._probe_source_import(env),
        )
        self._runs.append(outcome)
        return outcome

    def installed_package_path(self) -> Path:
        """The resolved installed ``vespercode`` package location.

        Fails closed if the installed package cannot be imported or the
        resolution falls back into the source checkout.
        """
        probe = "import vespercode; print(vespercode.__file__)"
        proc = subprocess.run(
            [str(self._python), "-c", probe],
            cwd=str(self._sandbox),
            env=self._clean_env(),
            capture_output=True,
            text=True,
            timeout=_RUN_TIMEOUT_SECONDS_V1,
            check=False,
        )
        if proc.returncode != 0:
            raise PackageSmokeErrorV1(
                "installed package import failed: "
                + redact_output(proc.stderr, (str(self._root),))
            )
        resolved = Path(proc.stdout.strip()).resolve()
        if resolved.is_relative_to(self._source_src):
            raise PackageSmokeErrorV1(
                f"installed package resolved into the source checkout: {resolved}"
            )
        return resolved

    def installed_version(self) -> str:
        """The installed package's own frozen version string."""
        probe = "import vespercode; print(vespercode.__version__)"
        proc = subprocess.run(
            [str(self._python), "-c", probe],
            cwd=str(self._sandbox),
            env=self._clean_env(),
            capture_output=True,
            text=True,
            timeout=_RUN_TIMEOUT_SECONDS_V1,
            check=False,
        )
        if proc.returncode != 0:
            raise PackageSmokeErrorV1(
                "installed version probe failed: "
                + redact_output(proc.stderr, (str(self._root),))
            )
        return proc.stdout.strip()

    def _clean_env(self) -> dict[str, str]:
        """One environment without ``PYTHONPATH`` or pipx variables."""
        env = {
            key: value
            for key, value in os.environ.items()
            if key.upper() != "PYTHONPATH"
        }
        env.pop("PIPX_HOME", None)
        env.pop("PIPX_BIN_DIR", None)
        env.pop("PIPX_MAN_DIR", None)
        return env

    def _probe_source_import(self, env: dict[str, str]) -> bool:
        """Whether the installed package import resolves into the source
        checkout (a missing import also fails closed as True)."""
        probe = "import vespercode; print(vespercode.__file__)"
        proc = subprocess.run(
            [str(self._python), "-c", probe],
            cwd=str(self._sandbox),
            env=env,
            capture_output=True,
            text=True,
            timeout=_RUN_TIMEOUT_SECONDS_V1,
            check=False,
        )
        if proc.returncode != 0:
            return True
        resolved = Path(proc.stdout.strip()).resolve()
        return resolved.is_relative_to(self._source_src)


class WebUIPageProbeV1(BaseModel):
    """One probed WebUI page fact of the installed composition."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    path: StrictStr
    status: int
    content_type: StrictStr
    byte_length: int
    ok: bool


class InstalledProbeResultV1(BaseModel):
    """One parsed installed WebUI/recovery probe fact set."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    installed_package_path: StrictStr
    source_checkout_imported: bool
    python_version: StrictStr
    pages: tuple[WebUIPageProbeV1, ...]
    demo_healthz_status: int
    demo_healthz_ok: bool
    recovery_kind: StrictStr
    recovery_workspace_zero_writes: bool
    recovery_cli_exit_code: int
    recovery_cli_hint_ok: bool
    all_ok: bool


class PackageSmokeConfigV1(BaseModel):
    """One closed package-smoke configuration (33.B GREEN-1)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    dist_dir: StrictStr
    require_one_wheel: bool
    report_path: StrictStr
    pipx_python: StrictStr | None = None
    source_root: StrictStr = ""


class PackageSmokeResultV1(BaseModel):
    """One closed package-smoke result (33.B interface).

    Carries the wheel/source/Python/pipx identities and the redacted
    command outcomes; ``report_text`` is exactly the bytes written to
    the report path and ``report_digest`` the SHA-256 of those bytes
    (fresh content-addressed evidence).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    wheel_name: StrictStr
    wheel_sha256: StrictStr
    wheel_evidence_match: bool
    source_revision: StrictStr
    source_tree_clean: bool
    pipx_python_identity: StrictStr
    pipx_home: StrictStr
    pipx_bin_dir: StrictStr
    installed_entry_point: StrictStr
    help_exit_code: int
    help_source_checkout_imports: int
    webui_pages: tuple[WebUIPageProbeV1, ...]
    webui_ok: bool
    demo_healthz_ok: bool
    recovery_preview_kind: StrictStr
    recovery_preview_zero_writes: bool
    recovery_cli_exit_code: int
    command_outcomes: tuple[RedactedCommandOutcomeV1, ...]
    all_ok: bool
    error_message: StrictStr | None = None
    report_text: StrictStr = ""
    report_digest: StrictStr = ""


def redact_output(text: str, secrets: tuple[str, ...]) -> str:
    """One length-bounded, path-redacted command output (SPEC §5.4)."""
    redacted = text
    for secret in secrets:
        redacted = redacted.replace(secret, "<redacted-path>")
    if len(redacted) > _OUTPUT_LIMIT_V1:
        redacted = redacted[:_OUTPUT_LIMIT_V1] + "…[truncated]"
    return redacted


def reserve_loopback_port() -> int:
    """Reserve one free loopback port for the installed probes."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wheel_sha256(path: Path) -> str:
    """The lowercase SHA-256 of the exact wheel bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence_path_for(wheel_path: Path) -> Path:
    """The adjacent lowercase SHA-256 evidence path of one wheel."""
    return wheel_path.with_name(wheel_path.name + ".sha256")


def publish_wheel_sha256_evidence(wheel_path: Path) -> Path:
    """Publish the adjacent lowercase SHA-256 evidence of one wheel.

    The evidence is computed from the exact wheel bytes by the harness
    itself (never by the build backend) and written in the standard
    ``sha256sum`` two-column form with the lowercase digest first
    (33.A GREEN-2).
    """
    evidence = evidence_path_for(wheel_path)
    digest = wheel_sha256(wheel_path)
    evidence.write_text(f"{digest}  {wheel_path.name}\n", encoding="utf-8")
    return evidence


def read_wheel_sha256_evidence(wheel_path: Path) -> str:
    """Read the lowercase digest token of one wheel's evidence file."""
    evidence = evidence_path_for(wheel_path)
    text = evidence.read_text(encoding="utf-8")
    tokens = text.split()
    if not tokens:
        raise PackageSmokeErrorV1(f"empty SHA-256 evidence: {evidence}")
    return tokens[0]


def find_single_wheel(dist_dir: Path, *, require_one: bool) -> Path:
    """The exactly one declared wheel of one dist directory."""
    wheels = sorted(dist_dir.glob(WHEEL_GLOB))
    if require_one and len(wheels) != 1:
        raise PackageSmokeErrorV1(
            f"expected exactly one wheel in {dist_dir}, got {len(wheels)}"
        )
    if not wheels:
        raise PackageSmokeErrorV1(f"no wheel found in {dist_dir}")
    return wheels[0]


def build_wheel_into(dist_dir: Path) -> Path:
    """Build the wheel with the exact card Build command.

    ``python -m build --wheel`` runs against the current source identity
    in the repository root and writes into ``dist_dir``; the caller owns
    cleaning stale artifacts before the build (one clean wheel).
    """
    dist_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist_dir)],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=_RUN_TIMEOUT_SECONDS_V1,
        check=False,
    )
    if proc.returncode != 0:
        raise PackageSmokeErrorV1(
            "wheel build failed: " + redact_output(proc.stdout + proc.stderr, ())
        )
    return find_single_wheel(dist_dir, require_one=True)


def _record_entries(text: str) -> tuple[RecordEntryV1, ...]:
    """Parse one wheel RECORD into closed (path, digest, size) rows."""
    entries: list[RecordEntryV1] = []
    for line in text.splitlines():
        parts = line.split(",")
        if len(parts) != 3:
            raise PackageSmokeErrorV1(f"malformed RECORD row: {line}")
        digest: str | None = None
        size: int | None = None
        if parts[1].startswith("sha256="):
            digest = parts[1][len("sha256=") :]
        if parts[2]:
            size = int(parts[2])
        entries.append(
            RecordEntryV1(schema_version=1, path=parts[0], sha256=digest, size=size)
        )
    return tuple(entries)


def _members_with_prefixes(names: tuple[str, ...]) -> frozenset[str]:
    """Every member name plus every ancestor directory prefix.

    A member ``tests/x.py`` therefore contributes ``tests``, ``tests/``
    and ``tests/x.py``, so exact-set containment catches any prohibited
    name or prefix (the exact RED's disjoint check).
    """
    expanded: set[str] = set()
    for name in names:
        parts = name.split("/")
        for index in range(1, len(parts) + 1):
            expanded.add("/".join(parts[:index]))
    return frozenset(expanded)


def open_wheel_archive(wheel_path: Path) -> WheelArchive:
    """Open one wheel into a closed archive inspection.

    Publishes the adjacent lowercase SHA-256 evidence (computed from the
    exact wheel bytes) and parses the RECORD and every member
    independently of the source tree (33.A GREEN-2).
    """
    evidence = publish_wheel_sha256_evidence(wheel_path)
    digest = wheel_sha256(wheel_path)
    with zipfile.ZipFile(wheel_path) as archive:
        names = tuple(sorted(archive.namelist()))
        record_name = next(
            (name for name in names if name.endswith(".dist-info/RECORD")), None
        )
        if record_name is None:
            raise PackageSmokeErrorV1(f"wheel has no RECORD: {wheel_path.name}")
        record_text = archive.read(record_name).decode("utf-8")
    version = _wheel_version(names)
    return WheelArchive(
        schema_version=1,
        wheel_path=wheel_path,
        name=wheel_path.name,
        version=version,
        member_names=names,
        members=_members_with_prefixes(names),
        record_entries=_record_entries(record_text),
        sha256=digest,
        evidence_path=evidence,
        evidence_sha256=digest,
    )


def _wheel_version(names: tuple[str, ...]) -> str:
    """The project version of one wheel from its dist-info name."""
    for name in names:
        if name.endswith(".dist-info/METADATA"):
            prefix = name[: -len(".dist-info/METADATA")]
            return prefix.split("-", 1)[1]
    raise PackageSmokeErrorV1("wheel has no dist-info METADATA")


def _venv_python_of(home: Path) -> Path:
    """The interpreter of the isolated application venv."""
    venv = home / "venvs" / _APP_NAME_V1
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def pipx_install_wheel(
    wheel_path: Path,
    *,
    pipx_home: Path,
    pipx_bin_dir: Path,
    pipx_man_dir: Path,
    python: str,
) -> RedactedCommandOutcomeV1:
    """Install one wheel into a fresh isolated pipx home.

    ``PIPX_HOME``/``PIPX_BIN_DIR``/``PIPX_MAN_DIR`` confine every venv,
    entry point, and man page to the caller-owned fresh root, so no
    shared pipx state is touched (33.B GREEN-1/Boundary).
    """
    env = os.environ.copy()
    env["PIPX_HOME"] = str(pipx_home)
    env["PIPX_BIN_DIR"] = str(pipx_bin_dir)
    env["PIPX_MAN_DIR"] = str(pipx_man_dir)
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pipx",
            "install",
            "--python",
            python,
            str(wheel_path),
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=_RUN_TIMEOUT_SECONDS_V1,
        check=False,
    )
    return RedactedCommandOutcomeV1(
        schema_version=1,
        label="pipx-install",
        exit_code=proc.returncode,
        output=redact_output(
            proc.stdout + proc.stderr, (str(pipx_home), str(pipx_bin_dir))
        ),
    )


def _python_identity(python: Path) -> str:
    """One bounded interpreter identity of the isolated venv."""
    proc = subprocess.run(
        [str(python), "--version"],
        capture_output=True,
        text=True,
        timeout=_RUN_TIMEOUT_SECONDS_V1,
        check=False,
    )
    return redact_output((proc.stdout + proc.stderr).strip(), ())


def _source_identity(source_root: Path) -> tuple[str, bool]:
    """The clean source revision and tree-cleanliness of one checkout."""
    revision = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=_RUN_TIMEOUT_SECONDS_V1,
        check=False,
    )
    if revision.returncode != 0:
        raise PackageSmokeErrorV1("cannot resolve the source revision (git HEAD)")
    status = subprocess.run(
        ["git", "-C", str(source_root), "status", "--porcelain"],
        capture_output=True,
        text=True,
        timeout=_RUN_TIMEOUT_SECONDS_V1,
        check=False,
    )
    return revision.stdout.strip(), status.stdout.strip() == ""


# The installed-package probe script (runs inside the isolated pipx venv
# with the wheel's own site-packages; the driver writes it to a temp
# file and executes it with a clean environment and a working directory
# outside the repository).
_INSTALLED_PROBE_SCRIPT_V1: Final = '''\
"""One installed-package WebUI/recovery probe (runs in the pipx venv).

Composes the production local app over the frozen governance-then-
operations installer tuple with fake typed ports (never mutating any
domain state), serves it on the reserved loopback port, fetches the
formal pages and the identity-verified packaged asset, boots the fixed
Demo app, and projects the read-only recovery preview through the
production recovery CLI handler — every fact reported as JSON with the
resolved installed package path so the driver can verify zero
source-checkout fallback.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, cast

import uvicorn


class _SpyShell:
    """One fake typed shell port implementation (never mutates state)."""

    def list_recent_runs(self) -> tuple[Any, ...]:
        return ()

    def credential_status(self) -> Any:
        from vespercode.contracts.optional import AbsentV1
        from vespercode.credentials.port import CredentialStatusV1

        return CredentialStatusV1(
            schema_version=1,
            provider="OPENAI",
            configured=False,
            updated_at=AbsentV1(kind="ABSENT"),
        )


class _SpyCredentialPorts:
    """One minimal credential workflow-port spy (status page only)."""

    def status(self, provider: str) -> Any:
        from vespercode.contracts.optional import AbsentV1
        from vespercode.credentials.port import CredentialStatusV1

        return CredentialStatusV1(
            schema_version=1,
            provider="OPENAI",
            configured=False,
            updated_at=AbsentV1(kind="ABSENT"),
        )

    def set(self, provider: str, secret: Any, event_id: str) -> Any:
        raise AssertionError("the installed smoke never mutates credentials")

    def update(self, provider: str, secret: Any, event_id: str) -> Any:
        raise AssertionError("the installed smoke never mutates credentials")

    def clear(self, provider: str, event_id: str) -> Any:
        raise AssertionError("the installed smoke never mutates credentials")


class _SpyMemoryPorts:
    """One minimal memory workflow-port spy (list only)."""

    def list(self, run_id: str) -> tuple[Any, ...]:
        return ()

    def create(self, command: Any) -> Any:
        raise AssertionError("the installed smoke never mutates memory")

    def confirm(self, command: Any) -> Any:
        raise AssertionError("the installed smoke never mutates memory")

    def clear(self, command: Any) -> Any:
        raise AssertionError("the installed smoke never mutates memory")


class _SpyAuditPorts:
    """One minimal audit workflow-port spy (page + clear state only)."""

    def __init__(self) -> None:
        from vespercode.audit.repository import AuditPageV1

        self._page = AuditPageV1(run_id="run-1", items=())

    def list_run(self, run_id: str, page: Any) -> Any:
        return self._page

    def clear_ended_run(self, command: Any) -> Any:
        raise AssertionError("the installed smoke never clears audit")

    def clear_state_for(self, run_id: str) -> Any:
        from vespercode.web.routes_audit import AuditClearStateV1

        return AuditClearStateV1(
            run_id=run_id, run_ended=True, has_unresolved_recovery=False
        )


class _SpyRecoveryPorts:
    """One minimal recovery workflow-port spy (preview only)."""

    def preview(self, run_id: str) -> Any:
        from vespercode.persistence.recovery_preview import (
            RecoveryPathClassificationEntryV1,
            RecoveryPreviewV1,
        )

        return RecoveryPreviewV1(
            schema_version=1,
            transaction_id="tx-1",
            disposition="ROLLED_BACK",
            path_classifications=(
                RecoveryPathClassificationEntryV1(
                    schema_version=1,
                    path="src/a.py",
                    classification="POSTIMAGE",
                ),
            ),
            observations=(),
            preview_digest="preview-digest-1",
            workspace_write_count=0,
        )

    def apply(self, command: Any) -> Any:
        raise AssertionError("the installed smoke never applies recovery")


class _EmptyGovernancePorts:
    """One dummy Milestone 29 governance aggregate (never called)."""


def _start_server(app: Any, port: int) -> Any:
    """Serve one app on the reserved loopback port until exit."""
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 60
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("uvicorn did not start on 127.0.0.1")
        time.sleep(0.05)
    return server


def _probe_webui(webui_port: int) -> dict[str, Any]:
    """Compose the production local app and fetch the formal pages."""
    import httpx

    from vespercode.cli import CSRF_HEADER_NAME_V1, SESSION_COOKIE_NAME_V1
    from vespercode.web.app import install_packaged_web_assets
    from vespercode.web.local_composition import (
        ProductionLocalWorkflowPortsV1,
        build_local_application,
    )
    from vespercode.web.routes_operations import LocalOperationsWorkflowPortsV1
    from vespercode.web.run_workflows import RunGovernanceWorkflowPortsV1
    from vespercode.web.security import LocalWebSecurityConfigV1

    ports = ProductionLocalWorkflowPortsV1(
        shell=_SpyShell(),
        governance=RunGovernanceWorkflowPortsV1(
            run_lifecycle=cast(Any, _EmptyGovernancePorts()),
            disclosure=cast(Any, _EmptyGovernancePorts()),
            final_writeback=cast(Any, _EmptyGovernancePorts()),
        ),
        operations=LocalOperationsWorkflowPortsV1(
            credentials=_SpyCredentialPorts(),
            memory=_SpyMemoryPorts(),
            audit=_SpyAuditPorts(),
            recovery=_SpyRecoveryPorts(),
        ),
    )
    security = LocalWebSecurityConfigV1(
        host="127.0.0.1",
        port=webui_port,
        session_cookie_name=SESSION_COOKIE_NAME_V1,
        csrf_header_name=CSRF_HEADER_NAME_V1,
    )
    app = build_local_application(ports, security)
    install_packaged_web_assets(app)
    server = _start_server(app, webui_port)
    pages: list[dict[str, Any]] = []
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{webui_port}", timeout=30, follow_redirects=False
        ) as client:
            for path in (
                "/",
                "/credentials/openai",
                "/runs/new",
                "/runs/run-1/memory",
                "/runs/run-1/audit",
                "/runs/run-1/recovery",
            ):
                response = client.get(path)
                pages.append(
                    {
                        "path": path,
                        "status": response.status_code,
                        "content_type": response.headers.get("content-type", ""),
                        "byte_length": len(response.content),
                        "body_hint": "VesperCode 本地" in response.text,
                        "sha256": "",
                    }
                )
            asset = client.get("/static/htmx.min.js")
            pages.append(
                {
                    "path": "/static/htmx.min.js",
                    "status": asset.status_code,
                    "content_type": asset.headers.get("content-type", ""),
                    "byte_length": len(asset.content),
                    "body_hint": True,
                    "sha256": hashlib.sha256(asset.content).hexdigest(),
                }
            )
    finally:
        server.should_exit = True
    return {"pages": pages}


def _probe_demo(demo_port: int) -> dict[str, Any]:
    """Boot the fixed Demo app and probe its canonical healthz."""
    import httpx

    from vespercode.demo.app import DemoAppConfigV1, create_demo_app

    app = create_demo_app(DemoAppConfigV1(port=demo_port))
    server = _start_server(app, demo_port)
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{demo_port}", timeout=30
        ) as client:
            response = client.get("/healthz")
            return {
                "status": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "body": response.text,
            }
    finally:
        server.should_exit = True


def _probe_recovery(workspace: str, control_db_dir: str) -> dict[str, Any]:
    """Project the read-only recovery preview with zero workspace writes."""
    from vespercode.cli_composition import (
        ProductionWorkspaceServiceV1,
        build_production_recovery_cli_handler,
        initialize_production_control_database,
    )

    workspace_path = Path(workspace)
    workspace_path.mkdir(parents=True, exist_ok=True)
    before = sorted(path.name for path in workspace_path.iterdir())
    database = initialize_production_control_database(
        Path(control_db_dir) / "control.db"
    )
    try:
        handler = build_production_recovery_cli_handler(
            database, ProductionWorkspaceServiceV1()
        )
        result = handler.preview(workspace_path)
    finally:
        database.close()
    after = sorted(path.name for path in workspace_path.iterdir())
    return {
        "kind": result.kind,
        "workspace_zero_writes": before == after,
        "message": result.message,
    }


def _probe_recovery_cli(workspace: str, control_db_dir: str) -> dict[str, Any]:
    """Project the installed ``recover --workspace`` parser surface."""
    import argparse

    from vespercode.cli_composition import (
        ProductionWorkspaceServiceV1,
        bind_production_recover_command,
    )

    parser = argparse.ArgumentParser(
        prog="vespercode", description="installed package smoke"
    )
    bind_production_recover_command(
        parser,
        Path(control_db_dir) / "cli-control.db",
        ProductionWorkspaceServiceV1(),
    )
    args = parser.parse_args(["recover", "--workspace", workspace])
    handler = getattr(args, "_recover_handler", None)
    if handler is None:
        return {"exit_code": 2, "message": "", "hint_ok": False}
    stream = io.StringIO()
    exit_code: int = 2
    with contextlib.redirect_stdout(stream):
        try:
            result = handler(args)
            if result is not None:
                exit_code = int(result)
        except SystemExit as exc:
            code = exc.code
            exit_code = code if isinstance(code, int) else (1 if code is not None else 0)
    return {
        "exit_code": exit_code,
        "message": stream.getvalue(),
        "hint_ok": "没有非终态恢复事务" in stream.getvalue(),
    }


def _probe_main() -> int:
    """One probe run: report every installed fact as JSON on stdout."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--webui-port", type=int, required=True)
    parser.add_argument("--demo-port", type=int, required=True)
    parser.add_argument("--source-src", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--control-db-dir", required=True)
    args = parser.parse_args()

    import vespercode

    installed = Path(vespercode.__file__).resolve()
    source_src = Path(args.source_src).resolve()
    report = {
        "installed_package_path": str(installed),
        "source_checkout_imported": installed.is_relative_to(source_src),
        "python_version": sys.version.split()[0],
        "webui": _probe_webui(args.webui_port),
        "demo": _probe_demo(args.demo_port),
        "recovery": _probe_recovery(args.workspace, args.control_db_dir),
        "recovery_cli": _probe_recovery_cli(args.workspace, args.control_db_dir),
    }
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(_probe_main())
'''

_EXPECTED_WEBUI_PAGES_V1: Final[tuple[tuple[str, int, int | None], ...]] = (
    ("/", 200, None),
    ("/credentials/openai", 200, None),
    ("/runs/new", 200, None),
    ("/runs/run-1/memory", 200, None),
    ("/runs/run-1/audit", 200, None),
    ("/runs/run-1/recovery", 200, None),
    ("/static/htmx.min.js", 200, EXPECTED_HTMX_BYTE_LENGTH_V1),
)
"""The exact expected WebUI page matrix of the installed composition."""


def _page_ok(page: dict[str, Any], expected: tuple[str, int, int | None]) -> bool:
    """Whether one probed page satisfies its pinned expectation."""
    path, status, byte_length = expected
    if page.get("path") != path or page.get("status") != status:
        return False
    if path == "/static/htmx.min.js":
        return (
            page.get("byte_length") == EXPECTED_HTMX_BYTE_LENGTH_V1
            and page.get("sha256") == EXPECTED_HTMX_SHA256_V1
            and str(page.get("content_type", "")).startswith("application/javascript")
        )
    return bool(page.get("body_hint")) and str(page.get("content_type", "")).startswith(
        "text/html"
    )


def run_installed_webui_probe(
    *,
    venv_python: Path,
    webui_port: int,
    demo_port: int,
    source_src: Path,
    workspace: Path,
    control_db_dir: Path,
    probe_dir: Path,
) -> InstalledProbeResultV1:
    """Run the installed WebUI/recovery probe inside the pipx venv.

    The probe executes only packaged entrypoints/resources with a clean
    environment and a working directory outside the repository; the
    parsed facts are validated against the pinned page matrix and the
    closed recovery/demo expectations.
    """
    probe_path = probe_dir / "installed_probe.py"
    probe_path.write_text(_INSTALLED_PROBE_SCRIPT_V1, encoding="utf-8")
    env = {
        key: value for key, value in os.environ.items() if key.upper() != "PYTHONPATH"
    }
    proc = subprocess.run(
        [
            str(venv_python),
            str(probe_path),
            "--webui-port",
            str(webui_port),
            "--demo-port",
            str(demo_port),
            "--source-src",
            str(source_src),
            "--workspace",
            str(workspace),
            "--control-db-dir",
            str(control_db_dir),
        ],
        cwd=str(workspace.parent),
        env=env,
        capture_output=True,
        text=True,
        timeout=_RUN_TIMEOUT_SECONDS_V1,
        check=False,
    )
    if proc.returncode != 0:
        raise PackageSmokeErrorV1(
            "installed probe failed: "
            + redact_output(proc.stderr, (str(probe_dir), str(workspace.parent)))
        )
    try:
        raw = json.loads(proc.stdout)
        demo = raw["demo"]
        recovery = raw["recovery"]
        recovery_cli = raw["recovery_cli"]
        pages = tuple(
            WebUIPageProbeV1(
                schema_version=1,
                path=str(page.get("path", "")),
                status=int(page.get("status", -1)),
                content_type=str(page.get("content_type", "")),
                byte_length=int(page.get("byte_length", -1)),
                ok=_page_ok(page, expected),
            )
            for page, expected in zip(
                raw["webui"]["pages"], _EXPECTED_WEBUI_PAGES_V1, strict=True
            )
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PackageSmokeErrorV1(
            "installed probe reported malformed facts: "
            + redact_output(str(exc), (str(probe_dir),))
        ) from exc
    all_ok = (
        not bool(raw["source_checkout_imported"])
        and all(page.ok for page in pages)
        and int(demo.get("status", -1)) == 200
        and _EXPECTED_HEALTHZ_BODY_V1 in str(demo.get("body", ""))
        and str(recovery.get("kind", "")) == EXPECTED_RECOVERY_PREVIEW_KIND_V1
        and bool(recovery.get("workspace_zero_writes"))
        and int(recovery_cli.get("exit_code", -1)) == 0
        and bool(recovery_cli.get("hint_ok"))
    )
    return InstalledProbeResultV1(
        schema_version=1,
        installed_package_path=str(raw["installed_package_path"]),
        source_checkout_imported=bool(raw["source_checkout_imported"]),
        python_version=str(raw["python_version"]),
        pages=pages,
        demo_healthz_status=int(demo.get("status", -1)),
        demo_healthz_ok=(
            int(demo.get("status", -1)) == 200
            and _EXPECTED_HEALTHZ_BODY_V1 in str(demo.get("body", ""))
        ),
        recovery_kind=str(recovery.get("kind", "")),
        recovery_workspace_zero_writes=bool(recovery.get("workspace_zero_writes")),
        recovery_cli_exit_code=int(recovery_cli.get("exit_code", -1)),
        recovery_cli_hint_ok=bool(recovery_cli.get("hint_ok")),
        all_ok=all_ok,
    )


def run_package_smoke(config: PackageSmokeConfigV1) -> PackageSmokeResultV1:
    """Run the clean wheel + isolated pipx distribution smoke.

    Binds the exact 33.A wheel digest, the clean source revision, the
    isolated venv Python identity, and the fresh project-specific pipx
    home; proves help, the production WebUI composition, and the
    read-only recovery preview; cleans every temp artifact in
    ``finally``; and returns the closed result whose ``report_text`` is
    exactly the bytes written to the report path (GREEN-1/GREEN-2).
    """
    outcomes: list[RedactedCommandOutcomeV1] = []
    pipx_root = Path(tempfile.mkdtemp(prefix=PIPX_ROOT_PREFIX_V1))
    probe_dir = Path(tempfile.mkdtemp(prefix="vespercode-probe-"))
    try:
        source_root = Path(config.source_root or _REPO_ROOT)
        wheel_path = find_single_wheel(
            Path(config.dist_dir), require_one=config.require_one_wheel
        )
        digest = wheel_sha256(wheel_path)
        evidence_path = publish_wheel_sha256_evidence(wheel_path)
        evidence_sha256 = read_wheel_sha256_evidence(wheel_path)
        evidence_match = digest == evidence_sha256 and evidence_path.is_file()
        source_revision, source_clean = _source_identity(source_root)

        home = pipx_root / "home"
        bin_dir = pipx_root / "bin"
        man_dir = pipx_root / "man"
        install_outcome = pipx_install_wheel(
            wheel_path,
            pipx_home=home,
            pipx_bin_dir=bin_dir,
            pipx_man_dir=man_dir,
            python=config.pipx_python or sys.executable,
        )
        outcomes.append(install_outcome)
        if install_outcome.exit_code != 0:
            raise PackageSmokeErrorV1(
                "pipx install failed with exit " + str(install_outcome.exit_code)
            )

        sandbox = pipx_root / "sandbox"
        sandbox.mkdir()
        package = InstalledPackage(
            wheel_path=wheel_path,
            root=pipx_root,
            home=home,
            bin_dir=bin_dir,
            venv_dir=home / "venvs" / _APP_NAME_V1,
            python=_venv_python_of(home),
            source_src=source_root / "src",
            sandbox=sandbox,
        )
        python_identity = _python_identity(package.python)
        help_result = package.run("vespercode", "--help")
        outcomes.append(
            RedactedCommandOutcomeV1(
                schema_version=1,
                label="installed-cli-help",
                exit_code=help_result.exit_code,
                output=help_result.output,
            )
        )

        workspace = pipx_root / "workspace"
        workspace.mkdir()
        control_db_dir = pipx_root / "control"
        control_db_dir.mkdir()
        probe = run_installed_webui_probe(
            venv_python=package.python,
            webui_port=reserve_loopback_port(),
            demo_port=reserve_loopback_port(),
            source_src=source_root / "src",
            workspace=workspace,
            control_db_dir=control_db_dir,
            probe_dir=probe_dir,
        )
        outcomes.append(
            RedactedCommandOutcomeV1(
                schema_version=1,
                label="installed-webui-probe",
                exit_code=0 if probe.all_ok else 1,
                output=(
                    f"pages {len(probe.pages)}, recovery "
                    f"{probe.recovery_kind}, demo healthz {probe.demo_healthz_status}"
                ),
            )
        )
    except PackageSmokeErrorV1 as exc:
        result = _failed_result(exc, tuple(outcomes))
        return seal_result(result, config)
    except (OSError, subprocess.TimeoutExpired) as exc:
        # A subprocess launch/launch-timeout failure must fail closed
        # with a bounded redacted message (SPEC §5.4), never an
        # uncaught traceback carrying the temp root path.
        result = _failed_result(
            PackageSmokeErrorV1(f"smoke subprocess failed: {type(exc).__name__}"),
            tuple(outcomes),
        )
        return seal_result(result, config)
    finally:
        shutil.rmtree(pipx_root, ignore_errors=True)
        shutil.rmtree(probe_dir, ignore_errors=True)

    all_ok = (
        evidence_match
        and install_outcome.exit_code == 0
        and help_result.exit_code == 0
        and help_result.source_checkout_import is False
        and probe.all_ok
    )
    result = PackageSmokeResultV1(
        schema_version=1,
        wheel_name=wheel_path.name,
        wheel_sha256=digest,
        wheel_evidence_match=evidence_match,
        source_revision=source_revision,
        source_tree_clean=source_clean,
        pipx_python_identity=python_identity,
        pipx_home=str(home),
        pipx_bin_dir=str(bin_dir),
        installed_entry_point=str(package.entry_point),
        help_exit_code=help_result.exit_code,
        help_source_checkout_imports=package.source_checkout_import_count,
        webui_pages=probe.pages,
        webui_ok=probe.all_ok,
        demo_healthz_ok=probe.demo_healthz_ok,
        recovery_preview_kind=probe.recovery_kind,
        recovery_preview_zero_writes=probe.recovery_workspace_zero_writes,
        recovery_cli_exit_code=probe.recovery_cli_exit_code,
        command_outcomes=tuple(outcomes),
        all_ok=all_ok,
        error_message=None,
    )
    return seal_result(result, config)


def _failed_result(
    exc: PackageSmokeErrorV1,
    outcomes: tuple[RedactedCommandOutcomeV1, ...],
) -> PackageSmokeResultV1:
    """One closed failed result with the bounded error message."""
    return PackageSmokeResultV1(
        schema_version=1,
        wheel_name="",
        wheel_sha256="",
        wheel_evidence_match=False,
        source_revision="",
        source_tree_clean=False,
        pipx_python_identity="",
        pipx_home="",
        pipx_bin_dir="",
        installed_entry_point="",
        help_exit_code=1,
        help_source_checkout_imports=0,
        webui_pages=(),
        webui_ok=False,
        demo_healthz_ok=False,
        recovery_preview_kind="",
        recovery_preview_zero_writes=False,
        recovery_cli_exit_code=1,
        command_outcomes=outcomes,
        all_ok=False,
        error_message=str(exc),
    )


def seal_result(
    result: PackageSmokeResultV1, config: PackageSmokeConfigV1
) -> PackageSmokeResultV1:
    """Seal one result with the exact report bytes and their digest.

    ``report_text`` is exactly the bytes written to the report path and
    ``report_digest`` the SHA-256 of those bytes (fresh content-addressed
    evidence); the report body is the result's own closed serialization.
    """
    body = result.model_dump(exclude={"report_text", "report_digest"})
    report_text = json.dumps(body, indent=2, sort_keys=True)
    report_digest = hashlib.sha256(report_text.encode("utf-8")).hexdigest()
    report_path = Path(config.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(report_text.encode("utf-8"))
    return PackageSmokeResultV1(
        **body,
        report_text=report_text,
        report_digest=report_digest,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry: run the package smoke and write the sealed report."""
    parser = argparse.ArgumentParser(description="Run the wheel + pipx smoke.")
    parser.add_argument("--dist", default="dist", type=Path)
    parser.add_argument("--require-one-wheel", action="store_true")
    parser.add_argument("--report", default=PACKAGE_SMOKE_REPORT_DEFAULT_V1, type=Path)
    parser.add_argument("--source-root", default=str(_REPO_ROOT), type=Path)
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="the interpreter of the isolated pipx venv (default: this interpreter)",
    )
    args = parser.parse_args(argv)
    config = PackageSmokeConfigV1(
        schema_version=1,
        dist_dir=str(args.dist),
        require_one_wheel=args.require_one_wheel,
        report_path=str(args.report),
        pipx_python=args.python,
        source_root=str(args.source_root),
    )
    result = run_package_smoke(config)
    print(
        f"package smoke: wheel {result.wheel_name} "
        f"sha256 {result.wheel_sha256}, "
        f"help exit {result.help_exit_code}, "
        f"webui_ok {result.webui_ok}, "
        f"recovery {result.recovery_preview_kind}, "
        f"all_ok {result.all_ok}, "
        f"report digest {result.report_digest}"
    )
    if result.error_message is not None:
        print(f"package smoke error: {result.error_message}")
    return 0 if result.all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
