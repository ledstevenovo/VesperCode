"""T34.1 legacy step 34.B: the Demo OCI image smoke driver.

``run_image_smoke`` inspects the built ``vespercode-demo`` image (curated
module members and fresh digest), runs one fresh container against the
exact §8.3 boundary (non-root platform PORT, ``/healthz``, fixed Mock
trace, ephemeral sessions, no persistence, no sockets/secrets/
repositories, zero formal adapter construction or calls), and returns the
closed ``ImageSmokeResultV1``.  The curated allowlist is the reviewed set
of source modules the Demo image ships — the Demo package plus the exact
Task 30 ``DEMO_SHARED_CORE_MODULES_V1`` shared pure core with its
canonical/contract import closure and the wiring modules the real shared
pipeline requires — never the formal wheel, loop engine, Run/turn/SQLite
repositories, WinCred/OpenAI/file-tool/Docker adapters, persistence,
recovery, memory, audit, web control plane, or CLI composition (SPEC
§8.3; T34.1 boundary).  ``PROHIBITED_DEMO_MODULE_PREFIXES_V1`` is the
exact card constant (T34.1 Interface, §75 ruling: the formal-capability
prefixes with ``vespercode.storage`` narrowed to
``vespercode.storage.run_repository``, ``vespercode.workspace`` narrowed
to ``vespercode.workspace.mutex_win32``, and ``vespercode.execution``
removed because all three execution modules are boot-required type
imports; ``vespercode.audit`` narrowed to the repository/projection/
retention modules because ``loop.feedback`` boot-imports
``vespercode.audit.event._contains_secret`` (SPEC_PROCESS 86, same
§75 precedent class) — Docker absence is proven behaviorally: zero formal adapter
construction or calls, ``requirements/demo.lock`` without the docker SDK,
and a boot import closure without ``import docker``).

The driver owns the curated Demo image construction and smoke evidence
only; formal wheel/engine/repositories, local files, Docker control,
credentials, persistence, recovery, provider adapters, and capability
expansion remain out of scope (GREEN-4).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final, Literal

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pydantic import BaseModel, ConfigDict, Strict  # noqa: E402

from vespercode.demo.runner import (  # noqa: E402
    DEMO_SHARED_CORE_MODULES_V1 as DEMO_SHARED_CORE_MODULES_V1,
)

__all__ = (
    "DEMO_IMAGE_TAG_V1",
    "DEMO_SHARED_CORE_MODULES_V1",
    "ImageSmokeConfigV1",
    "ImageSmokeResultV1",
    "OCIImageInspection",
    "PROHIBITED_DEMO_MODULE_PREFIXES_V1",
    "allowlist_from_dockerfile",
    "container_capability_registry_ok",
    "container_filesystem_violations",
    "container_fixed_trace",
    "container_healthz_body",
    "container_host_port",
    "container_non_root_uid",
    "container_post_completion_rejected",
    "container_sessions_are_ephemeral",
    "ensure_demo_image",
    "image_import_docker_hits",
    "inspect_local_image",
    "lock_docker_sdk_present",
    "lock_is_hash_locked",
    "probe_container_healthz",
    "run_image_smoke",
    "start_demo_container",
    "stop_demo_container",
)

DEMO_IMAGE_TAG_V1: Final = "vespercode-demo:local"
"""The exact local tag of the curated Demo image (card Build command)."""

DEMO_DOCKERFILE_RELATIVE_V1: Final = "containers/demo/Dockerfile"
DEMO_LOCK_RELATIVE_V1: Final = "requirements/demo.lock"

_NON_ROOT_UID_V1: Final = 10001
"""The fixed non-root uid of the Demo image (SPEC §8.3 non-root)."""

_EXPECTED_FIXED_TRACE_V1: Final = (
    "DENIED",
    "DENIED",
    "CHECK_FAILED",
    "DENIED",
    "REJECTED(DEMO_WAITING_USER)",
    "COMPLETED(DEMO_COMPLETED)",
)
"""The exact six fixed Mock trace labels (T30.2 fixed trace; a step label
is ``outcome`` for running steps and ``outcome(status)`` otherwise)."""

_HEALTHZ_OK_BODY_V1: Final = '{"mode": "simulation", "status": "ok"}'
"""The exact canonical /healthz body of the Demo app (SPEC §8.3), in the
same sorted-key serialization ``container_healthz_body`` returns."""

PROHIBITED_DEMO_MODULE_PREFIXES_V1: Final[frozenset[str]] = frozenset(
    {
        "vespercode.audit.repository",
        "vespercode.audit.projection",
        "vespercode.audit.retention",
        "vespercode.cli_composition",
        "vespercode.credentials",
        "vespercode.llm.openai_adapter",
        "vespercode.loop.call_orchestrator",
        "vespercode.loop.engine",
        "vespercode.loop.turn_boundary",
        "vespercode.memory",
        "vespercode.persistence",
        "vespercode.storage.run_repository",
        "vespercode.tools.list_files",
        "vespercode.tools.read_file",
        "vespercode.tools.search_text",
        "vespercode.web",
        "vespercode.workspace.mutex_win32",
    }
)
"""The exact closed prohibited module prefixes of the curated Demo image
(T34.1 card Interface, §75 ruling): no formal capability adapter —
loop engine, Run/turn/SQLite repositories, workspace lease, file-tool
implementations, persistence, credentials, OpenAI adapter, audit
repositories/projection/retention, memory, web control plane, or CLI
composition — may enter the image (``audit.event`` is boot-required by
``loop.feedback``, SPEC_PROCESS 86).

The prefix rule is exact module-boundary matching: a module path is
prohibited when it equals a prefix or starts with ``prefix + "."``.
``vespercode.execution`` is absent from the set by the §75 ruling (all
three execution modules are boot-required type imports of the shared
check-result contract); Docker absence is proven behaviorally instead.
"""


def _module_hits_prefixes(
    members: frozenset[str], prefixes: frozenset[str]
) -> list[str]:
    """The members that equal a prefix or start with ``prefix + "."``."""
    return sorted(
        member
        for member in members
        if any(
            member == prefix or member.startswith(prefix + ".") for prefix in prefixes
        )
    )


@dataclass(frozen=True)
class OCIImageInspection:
    """One closed inspection of a local Demo image.

    ``python_members`` is the set of module names of the image's curated
    code tree at ``/app`` (the ``src.`` prefix normalized away), so the
    exact RED test compares it against the shared-core/prohibited sets;
    an absent image yields an empty inspection (the pre-implementation
    allowlist/prohibited-prefix contract state).  ``image_id`` is the
    local image config digest and ``repo_digest`` the registry digest
    when one exists (fresh image digest evidence).
    """

    python_members: frozenset[str]
    image_id: str | None
    repo_digest: str | None


def _empty_inspection() -> OCIImageInspection:
    """The closed empty inspection of a missing image."""
    return OCIImageInspection(
        python_members=frozenset(), image_id=None, repo_digest=None
    )


_MEMBER_SCAN_SCRIPT = """\
import pathlib
for path in sorted(pathlib.Path('/app').rglob('*.py')):
    name = '.'.join(path.relative_to('/app').with_suffix('').parts)
    if name.startswith('src.'):
        name = name[len('src.'):]
    print(name)
"""
"""The in-container module-name scan of the curated /app code tree."""

_IMPORT_DOCKER_SCAN_SCRIPT = """\
import ast, pathlib
hits = []
for path in sorted(pathlib.Path('/app').rglob('*.py')):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == 'docker' or alias.name.startswith('docker.'):
                    hits.append(f"{path}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module == 'docker' or node.module.startswith('docker.'):
                hits.append(f"{path}: from {node.module} import ...")
for hit in sorted(hits):
    print(hit)
"""
"""The in-container scan for any module-level ``docker`` import in the
/app code tree.

Only top-level imports execute at boot; function-local lazy imports
(such as the Docker executor's ``import docker`` inside its connect
path) never run in the Demo and do not make the docker SDK a boot
dependency (§75 ruling: the boot import closure carries no docker).
"""

_FILESYSTEM_SCAN_SCRIPT = """\
import os, pathlib, stat
violations = []
base_infra = (
    '/etc/ssl/certs/',
    '/usr/local/lib/python3.12/',
    '/usr/local/share/ca-certificates/',
    '/usr/lib/ssl/',
    '/usr/share/ca-certificates/',
)
for root in ('/app', '/tmp', '/home', '/root', '/opt', '/srv', '/var', '/usr', '/etc'):
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda exc: None):
        if '.git' in dirnames:
            violations.append(os.path.join(dirpath, '.git'))
        for name in filenames:
            full = os.path.join(dirpath, name)
            if full.startswith(base_infra):
                continue
            try:
                if stat.S_ISSOCK(os.lstat(full).st_mode):
                    violations.append(full + ' (socket)')
            except OSError:
                pass
            lower = name.lower()
            if (
                lower == '.env'
                or lower.startswith('.env.')
                or lower in ('id_rsa', 'id_ed25519', 'credentials.json')
                or lower.startswith('secrets.')
                or lower.endswith(('.pem', '.key', '.p12', '.pfx'))
            ):
                violations.append(full)
for violation in sorted(set(violations)):
    print(violation)
"""
"""The in-container scan for sockets, secrets, and repositories.

The trusted base-image infrastructure — the system CA stores and the
Python standard library/pip installation (whose stdlib ``secrets``
module and vendored CA bundle match name patterns but hold no
credential) — is excluded; every other file name that matches a
private-key/credential pattern, any socket, and any ``.git`` repository
is a violation.
"""

_REGISTRY_CHECK_SCRIPT = """\
from vespercode.demo.app import DEMO_CAPABILITY_KINDS_V1, DemoAppConfigV1, create_demo_app
app = create_demo_app(DemoAppConfigV1(port=8080))
assert app.state.capability_kinds == DEMO_CAPABILITY_KINDS_V1, app.state.capability_kinds
"""
"""The in-container proof that the capability registry is exactly the
fixed simulation set (T30.2 30.B registry; SPEC §4.9)."""


def _run_docker(
    args: list[str], *, timeout: int, input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run one docker CLI command, failing closed on any error."""
    return subprocess.run(
        ["docker", *args],
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _require_docker_ok(proc: subprocess.CompletedProcess[str], context: str) -> None:
    if proc.returncode != 0:
        raise RuntimeError(
            f"{context} failed: " + (proc.stderr or proc.stdout or "").strip()
        )


def _image_python_members(tag: str) -> frozenset[str]:
    """The module names of the image's curated /app code tree."""
    proc = _run_docker(
        ["run", "--rm", "-i", tag, "python", "-"],
        timeout=300,
        input_text=_MEMBER_SCAN_SCRIPT,
    )
    _require_docker_ok(proc, "the demo image member scan")
    return frozenset(line.strip() for line in proc.stdout.splitlines() if line.strip())


def ensure_demo_image(tag: str, dockerfile: Path) -> OCIImageInspection:
    """Build the image from the reviewed recipe whenever the recipe
    exists (docker layer caching keeps the rebuild cheap and guarantees
    the inspected image reflects the current recipe), then inspect it.

    Before the allowlist/prohibited-prefix image contract exists there
    is no recipe, so no build happens and the inspection is empty (the
    exact RED's first task-owned assertion then fails on the missing
    contract).
    """
    if dockerfile.exists():
        _sweep_stale_demo_containers()
        proc = _run_docker(
            [
                "build",
                "--pull=false",
                "-f",
                str(dockerfile),
                "-t",
                tag,
                str(dockerfile.parents[2]),
            ],
            timeout=600,
        )
        _require_docker_ok(proc, "the demo image build")
    return inspect_local_image(tag)


def inspect_local_image(tag: str) -> OCIImageInspection:
    """Inspect one local Demo image; empty inspection when it is absent."""
    try:
        proc = _run_docker(["image", "inspect", tag], timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return _empty_inspection()
    if proc.returncode != 0:
        return _empty_inspection()
    try:
        info = json.loads(proc.stdout)[0]
    except (json.JSONDecodeError, IndexError, KeyError):
        return _empty_inspection()
    repo_digests = info.get("RepoDigests") or []
    return OCIImageInspection(
        python_members=_image_python_members(tag),
        image_id=info.get("Id"),
        repo_digest=repo_digests[0] if repo_digests else None,
    )


def allowlist_from_dockerfile(dockerfile: Path) -> frozenset[str]:
    """The curated module allowlist declared by the recipe COPY lines.

    The allowlist identity contract: the built image's ``python_members``
    must equal exactly the modules the recipe copies (per-file and
    per-directory), so the Dockerfile remains the single reviewed
    allowlist source.
    """
    repo_root = dockerfile.parents[2]
    members: set[str] = set()
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[0] != "COPY":
            continue
        src = parts[1]
        if not src.startswith("src/vespercode/"):
            continue
        src_path = repo_root / src
        if src_path.is_dir():
            for module_path in src_path.rglob("*.py"):
                members.add(_module_name(module_path.relative_to(repo_root)))
        else:
            members.add(_module_name(src_path.relative_to(repo_root)))
    return frozenset(members)


def _module_name(relative: Path) -> str:
    """The dotted module name of one repository-relative Python file."""
    name = ".".join(relative.with_suffix("").parts)
    if name.startswith("src."):
        name = name[len("src.") :]
    return name


def lock_is_hash_locked(lock_path: Path) -> bool:
    """True when every non-header demo.lock line carries a sha256 hash."""
    lines = [
        line
        for line in lock_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("--")
    ]
    return bool(lines) and all(" --hash=sha256:" in line for line in lines)


def lock_docker_sdk_present(lock_path: Path) -> bool:
    """True when the demo lock pins the docker SDK package."""
    return any(
        line.startswith("docker==")
        for line in lock_path.read_text(encoding="utf-8").splitlines()
    )


def image_import_docker_hits(tag: str) -> list[str]:
    """Every ``import docker`` hit in the image's /app code tree."""
    proc = _run_docker(
        ["run", "--rm", "-i", tag, "python", "-"],
        timeout=300,
        input_text=_IMPORT_DOCKER_SCAN_SCRIPT,
    )
    _require_docker_ok(proc, "the demo image import scan")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _free_host_port() -> int:
    """One free loopback host port for the container port mapping."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def container_host_port(container_id: str) -> int:
    """The mapped loopback host port of one Demo container."""
    proc = _run_docker(["port", container_id], timeout=60)
    _require_docker_ok(proc, "the demo container port query")
    first = (proc.stdout.splitlines() or [""])[0]
    # docker port output: "8000/tcp -> 127.0.0.1:PORT"
    return int(first.rsplit(":", 1)[1].strip())


def _sweep_stale_demo_containers() -> None:
    """Remove every leftover ``vespercode-demo-*`` container.

    Self-healing of historical residue: any orphan left by an earlier
    interrupted run is removed before a new run starts, so the zero
    residue contract holds even across process crashes (quality review
    F1).
    """
    proc = _run_docker(
        [
            "ps",
            "-a",
            "--filter",
            "name=vespercode-demo-",
            "--format",
            "{{.ID}}",
        ],
        timeout=60,
    )
    _require_docker_ok(proc, "the stale demo container sweep")
    for container_id in proc.stdout.splitlines():
        cleaned = container_id.strip()
        if cleaned:
            _run_docker(["rm", "-f", cleaned], timeout=120)


def start_demo_container(tag: str, port: int | None = None) -> str:
    """Start one fresh Demo container on a loopback port (zero residue
    contract: the caller removes it with ``stop_demo_container``).

    Any startup failure after a successful ``docker run`` removes the
    container before re-raising, so a bounded healthz timeout can never
    leave an orphan behind (quality review F1).
    """
    port = port or _free_host_port()
    name = f"vespercode-demo-{uuid.uuid4().hex[:12]}"
    proc = _run_docker(
        [
            "run",
            "-d",
            "--name",
            name,
            "-e",
            f"PORT={port}",
            "-p",
            f"127.0.0.1:{port}:{port}",
            tag,
        ],
        timeout=120,
    )
    _require_docker_ok(proc, "the demo container start")
    container_id = proc.stdout.strip()
    try:
        _wait_healthz(port)
    except Exception:
        _run_docker(["rm", "-f", container_id], timeout=120)
        raise
    return container_id


def stop_demo_container(container_id: str) -> None:
    """Remove one Demo container and its port mapping (zero residue).

    A failed removal is a residue and fails closed (the zero-residue
    contract never silently drops a leftover container).
    """
    proc = _run_docker(["rm", "-f", container_id], timeout=120)
    _require_docker_ok(proc, "the demo container removal")


def _http_status(base: str, path: str) -> int:
    """The HTTP status of one GET on the local Demo container.

    A transient connection failure (the uvicorn startup window closes
    connections before the app is ready) returns 0 so the bounded
    ``_wait_healthz`` poll loop keeps retrying; a closed HTTP error
    keeps its real status.
    """
    try:
        with urllib.request.urlopen(f"{base}{path}", timeout=15) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except (urllib.error.URLError, OSError):
        return 0


def container_healthz_body(base: str) -> str:
    """The exact raw body of GET /healthz (compact JSON)."""
    with urllib.request.urlopen(f"{base}/healthz", timeout=15) as resp:
        return json.dumps(json.loads(resp.read().decode("utf-8")), sort_keys=True)


def _wait_healthz(port: int, timeout_seconds: int = 90) -> None:
    """Poll the local /healthz until 200 or the bounded deadline."""
    deadline = time.monotonic() + timeout_seconds
    base = f"http://127.0.0.1:{port}"
    while time.monotonic() < deadline:
        if _http_status(base, "/healthz") == 200:
            return
        time.sleep(1.0)
    raise RuntimeError("the demo container /healthz did not become ready")


def probe_container_healthz(container_id: str) -> int:
    """The /healthz status of one running Demo container."""
    port = container_host_port(container_id)
    return _http_status(f"http://127.0.0.1:{port}", "/healthz")


def _post_json(base: str, path: str, body: dict[str, object]) -> dict[str, object]:
    """One POST with a JSON body, failing closed on a non-2xx status."""
    request = urllib.request.Request(
        f"{base}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            return dict(json.loads(resp.read().decode("utf-8")))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"POST {path} failed with HTTP {exc.code}") from exc


def _trace_label(step: dict[str, object]) -> str:
    """The closed trace label of one step result (outcome or
    ``outcome(status)`` for non-running steps)."""
    outcome = str(step["outcome"])
    status = str(step["status"])
    if status == "DEMO_RUNNING":
        return outcome
    return f"{outcome}({status})"


def container_fixed_trace(container_id: str) -> tuple[str, ...]:
    """The six fixed Mock trace labels served by one Demo container."""
    port = container_host_port(container_id)
    base = f"http://127.0.0.1:{port}"
    created = _post_json(base, "/demo/sessions", {})
    session_id = str(created["demo_session_id"])
    labels: list[str] = []
    for index in range(6):
        body: dict[str, object] = {}
        if index == 4:
            body = {"decision": "REJECT"}
        elif index == 5:
            body = {"decision": "APPROVE"}
        step = _post_json(base, f"/demo/sessions/{session_id}/advance", body)
        labels.append(_trace_label(step))
    return tuple(labels)


def container_post_completion_rejected(container_id: str) -> bool:
    """True when the advance after the completed scenario rejects 404.

    The completed session is discarded (SPEC §4.9), so the next advance
    rejects with SESSION_NOT_FOUND mapped to HTTP 404.
    """
    port = container_host_port(container_id)
    base = f"http://127.0.0.1:{port}"
    created = _post_json(base, "/demo/sessions", {})
    session_id = str(created["demo_session_id"])
    for index in range(6):
        body: dict[str, object] = {}
        if index == 4:
            body = {"decision": "REJECT"}
        elif index == 5:
            body = {"decision": "APPROVE"}
        _post_json(base, f"/demo/sessions/{session_id}/advance", body)
    request = urllib.request.Request(
        f"{base}/demo/sessions/{session_id}/advance",
        data=json.dumps({}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15):
            return False
    except urllib.error.HTTPError as exc:
        return exc.code == 404


def container_sessions_are_ephemeral(container_id: str) -> bool:
    """True when a container restart drops every in-memory session."""
    port = container_host_port(container_id)
    base = f"http://127.0.0.1:{port}"
    created = _post_json(base, "/demo/sessions", {})
    session_id = str(created["demo_session_id"])
    proc = _run_docker(["restart", container_id], timeout=180)
    _require_docker_ok(proc, "the demo container restart")
    _wait_healthz(port)
    request = urllib.request.Request(
        f"{base}/demo/sessions/{session_id}/advance",
        data=json.dumps({}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15):
            return False
    except urllib.error.HTTPError as exc:
        return exc.code == 404


def container_non_root_uid(container_id: str) -> int:
    """The uid of the container process (SPEC §8.3 non-root)."""
    proc = _run_docker(["exec", container_id, "id", "-u"], timeout=60)
    _require_docker_ok(proc, "the demo container uid query")
    return int(proc.stdout.strip())


def container_filesystem_violations(container_id: str) -> list[str]:
    """Every socket/secret/repository hit inside the running container."""
    proc = _run_docker(
        ["exec", "-i", container_id, "python", "-"],
        timeout=180,
        input_text=_FILESYSTEM_SCAN_SCRIPT,
    )
    _require_docker_ok(proc, "the demo container filesystem scan")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def container_capability_registry_ok(container_id: str) -> bool:
    """True when the capability registry is exactly the fixed simulation
    set (zero formal capability construction)."""
    proc = _run_docker(
        ["exec", container_id, "python", "-c", _REGISTRY_CHECK_SCRIPT],
        timeout=120,
    )
    return proc.returncode == 0


class ImageSmokeConfigV1(BaseModel):
    """The closed configuration of one demo-image smoke run."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    demo_image_tag: Annotated[str, Strict()] = DEMO_IMAGE_TAG_V1
    report_path: Annotated[str, Strict()] = "tests/.tmp/demo-image-smoke-report.json"


class ImageSmokeResultV1(BaseModel):
    """The closed outcome of one demo-image smoke run."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    demo_image_tag: str
    image_id: str | None
    repo_digest: str | None
    python_members: tuple[str, ...]
    shared_core_modules: tuple[str, ...]
    prohibited_prefixes: tuple[str, ...]
    prohibited_hits: tuple[str, ...]
    shared_core_present: bool
    lock_hash_locked: bool
    docker_sdk_in_lock: bool
    import_docker_hits: tuple[str, ...]
    non_root_uid: int | None
    non_root_ok: bool
    port_ok: bool
    healthz_status: int | None
    healthz_body: str
    fixed_trace_ok: bool
    fixed_trace_steps: tuple[str, ...]
    ephemeral_sessions_ok: bool
    no_persistence_ok: bool
    filesystem_violations: tuple[str, ...]
    capability_registry_ok: bool
    all_ok: bool
    report_text: str
    report_digest: str


def _finalize_report(result: ImageSmokeResultV1) -> ImageSmokeResultV1:
    """Bind the exact report bytes the driver writes.

    The report text is the canonical JSON of every field except the
    report text/digest themselves; ``report_digest`` is its SHA-256, so
    the written file is exactly the bounded bytes the result binds (the
    T32.1 report-identity convention).
    """
    payload = {
        key: value
        for key, value in result.model_dump(mode="json").items()
        if key not in {"report_text", "report_digest"}
    }
    text = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return ImageSmokeResultV1(
        **{
            **result.model_dump(mode="json"),
            "report_text": text,
            "report_digest": digest,
        }
    )


def run_image_smoke(config: ImageSmokeConfigV1) -> ImageSmokeResultV1:
    """Run the exact demo-image smoke and return the closed result."""
    inspection = inspect_local_image(config.demo_image_tag)
    lock_path = _REPO_ROOT / DEMO_LOCK_RELATIVE_V1
    lock_hash_locked = lock_is_hash_locked(lock_path)
    docker_sdk_in_lock = lock_docker_sdk_present(lock_path)
    import_docker_hits = (
        tuple(image_import_docker_hits(config.demo_image_tag))
        if inspection.image_id is not None
        else ()
    )
    members = inspection.python_members
    prohibited_hits = tuple(
        _module_hits_prefixes(members, PROHIBITED_DEMO_MODULE_PREFIXES_V1)
    )
    shared_core_present = set(DEMO_SHARED_CORE_MODULES_V1) <= members

    non_root_uid: int | None = None
    healthz_status: int | None = None
    healthz_body = ""
    trace_steps: tuple[str, ...] = ()
    ephemeral_sessions_ok = False
    filesystem_violations: tuple[str, ...] = ()
    capability_registry_ok = False
    container_id: str | None = None
    if inspection.image_id is not None:
        _sweep_stale_demo_containers()
        container_id = start_demo_container(config.demo_image_tag)
        try:
            non_root_uid = container_non_root_uid(container_id)
            port = container_host_port(container_id)
            base = f"http://127.0.0.1:{port}"
            healthz_status = _http_status(base, "/healthz")
            healthz_body = container_healthz_body(base)
            trace_steps = container_fixed_trace(container_id)
            ephemeral_sessions_ok = container_sessions_are_ephemeral(container_id)
            filesystem_violations = tuple(container_filesystem_violations(container_id))
            capability_registry_ok = container_capability_registry_ok(container_id)
        finally:
            stop_demo_container(container_id)

    non_root_ok = non_root_uid == _NON_ROOT_UID_V1
    port_ok = healthz_status == 200
    healthz_body_ok = healthz_body == _HEALTHZ_OK_BODY_V1
    fixed_trace_ok = trace_steps == _EXPECTED_FIXED_TRACE_V1
    no_persistence_ok = ephemeral_sessions_ok
    all_ok = (
        shared_core_present
        and not prohibited_hits
        and lock_hash_locked
        and not docker_sdk_in_lock
        and not import_docker_hits
        and non_root_ok
        and port_ok
        and healthz_body_ok
        and fixed_trace_ok
        and ephemeral_sessions_ok
        and not filesystem_violations
        and capability_registry_ok
    )
    return _finalize_report(
        ImageSmokeResultV1(
            schema_version=1,
            demo_image_tag=config.demo_image_tag,
            image_id=inspection.image_id,
            repo_digest=inspection.repo_digest,
            python_members=tuple(sorted(members)),
            shared_core_modules=tuple(sorted(DEMO_SHARED_CORE_MODULES_V1)),
            prohibited_prefixes=tuple(sorted(PROHIBITED_DEMO_MODULE_PREFIXES_V1)),
            prohibited_hits=prohibited_hits,
            shared_core_present=shared_core_present,
            lock_hash_locked=lock_hash_locked,
            docker_sdk_in_lock=docker_sdk_in_lock,
            import_docker_hits=import_docker_hits,
            non_root_uid=non_root_uid,
            non_root_ok=non_root_ok,
            port_ok=port_ok,
            healthz_status=healthz_status,
            healthz_body=healthz_body,
            fixed_trace_ok=fixed_trace_ok,
            fixed_trace_steps=trace_steps,
            ephemeral_sessions_ok=ephemeral_sessions_ok,
            no_persistence_ok=no_persistence_ok,
            filesystem_violations=filesystem_violations,
            capability_registry_ok=capability_registry_ok,
            all_ok=all_ok,
            report_text="",
            report_digest="",
        )
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry: run the smoke and write the bounded report; 0 on pass."""
    parser = argparse.ArgumentParser(description="Run the demo-image smoke.")
    parser.add_argument("--demo", default=DEMO_IMAGE_TAG_V1, help="demo image tag")
    parser.add_argument("--report", default="tests/.tmp/demo-image-smoke-report.json")
    args = parser.parse_args(argv)
    config = ImageSmokeConfigV1(demo_image_tag=args.demo, report_path=args.report)
    result = run_image_smoke(config)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    # The written file is exactly the bounded report bytes the result
    # binds (report_digest matches the file).
    report_path.write_bytes(result.report_text.encode("utf-8"))
    print(
        f"demo image smoke: {len(result.python_members)} members,"
        f" health {result.healthz_status},"
        f" trace {'OK' if result.fixed_trace_ok else 'FAILED'},"
        f" all_ok {result.all_ok},"
        f" report digest {result.report_digest}"
    )
    return 0 if result.all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
