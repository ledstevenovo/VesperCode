"""T02.3 legacy step 2.D: reference container isolation probe.

Starts one fresh reference container from the frozen build evidence with the
frozen SPEC §1.4.5 execution profile — no network, non-root, read-only root
filesystem, dropped capabilities, no Docker socket, a read-only workspace
mount, a bounded tmpfs, and 2 CPU / 2 GiB memory / 256 PID limits — and
observes every isolation control from inside that same container plus the
daemon-side configuration.  Returns one immutable
``ContainerIsolationEvidenceV1`` only when every required observation matches
the frozen expectations and cleanup is verified.

Any missing or false isolation observation — a writable workspace, an
unbounded resource, a present Docker socket, a writable root filesystem, or
unverified cleanup — fails closed with ``RuntimeError`` and no evidence is
ever returned.

Owns container configuration, runtime-isolation observations, and cleanup
only.  Pytest interpretation and failure-fingerprint computation remain out
of scope: the layout reproduction below re-runs the builder's own frozen
build machinery (same fixed parameters, same builder-identity assert) solely
to obtain the runnable image bytes that the frozen build evidence binds,
never as a second build contract or new build evidence.
"""

from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from spikes.docker_reference_boundary.image_builder import (
    FIXTURE_RELATIVE,
    RECIPE_RELATIVE,
    REFERENCE_LOCK_RELATIVE,
    REPO_ROOT,
    ReferenceImageBuildEvidenceV1,
    _read_required,
    _run_docker_build,
)

# Frozen SPEC §1.4.5 execution-profile values: 2 CPU, 2 GiB memory, 256 PIDs,
# 256 MiB bounded tmpfs, non-root uid/gid 10001, read-only /workspace mount.
CPU_LIMIT = 2
MEMORY_LIMIT_BYTES = 2 * 1024**3  # 2 GiB
MEMORY_ARGV = f"{MEMORY_LIMIT_BYTES // 1024**3}g"  # the frozen ``--memory`` value
PID_LIMIT = 256
TMPFS_SPEC = "/tmp:rw,size=256m"  # the frozen ``--tmpfs`` argument
TMPFS_OPTIONS = "rw,size=256m"  # the observed Tmpfs value for /tmp
TMPFS_SIZE_KIB = "262144k"  # 256 MiB as observed in /proc/mounts
NON_ROOT_UID = 10001
NON_ROOT_GID = 10001
WORKSPACE_TARGET = "/workspace"

# Frozen observation expectations (from the real probe run on the frozen
# image; any deviation from these raw bytes is a closed failure).
ZERO_CAPABILITY_HEX = "0000000000000000"
ROOT_WRITE_REJECTED_ERRNO = 30  # EROFS
WORKSPACE_WRITE_REJECTED_ERRNO = 30  # EROFS
NO_EXTERNAL_ROUTE_ERRNO = 101  # ENETUNREACH
CPU_MAX_EXPECTED = "200000 100000"  # 2 CPUs over a 100 ms period
MEMORY_MAX_EXPECTED = "2147483648"
PIDS_MAX_EXPECTED = "256"
LOOPBACK_ONLY_INTERFACES = ["lo"]


@dataclass(frozen=True)
class ContainerIsolationEvidenceV1:
    """Immutable evidence of one fresh reference container's isolation."""

    network_disabled: bool
    non_root: bool
    root_read_only: bool
    capabilities_dropped: bool
    docker_socket_absent: bool
    workspace_read_only: bool
    tmpfs_bounded: bool
    cpu_limit: int
    memory_limit_bytes: int
    pid_limit: int
    cleanup_verified: bool


# The in-container observation script: reads only /proc and /sys facts plus
# bounded write/connect probes, and prints one JSON object to stdout.  The
# script is fixed source of this module and is delivered to the container
# inline through ``python -c`` so no host path ever enters the container.
_OBSERVATION_SCRIPT = r"""
import json
import os
import socket


def _status_hex(name):
    with open("/proc/self/status", encoding="utf-8") as stream:
        for line in stream:
            if line.startswith(name + ":"):
                return line.split()[1]
    return "MISSING"


def _write_errno(path):
    try:
        with open(path, "w", encoding="utf-8") as stream:
            stream.write("x")
        return 0
    except OSError as exc:
        return exc.errno


def _connect_errno(host, port):
    try:
        with socket.create_connection((host, port), timeout=2):
            return 0
    except OSError as exc:
        return exc.errno


def _cgroup_value(name):
    try:
        with open("/sys/fs/cgroup/" + name, encoding="utf-8") as stream:
            return stream.read().strip()
    except OSError as exc:
        return "ERR:" + str(exc.errno)


def _tmp_mounts():
    result = []
    with open("/proc/mounts", encoding="utf-8") as stream:
        for line in stream:
            parts = line.split()
            if len(parts) >= 4 and parts[1] == "/tmp":
                result.append({"fs": parts[2], "opts": parts[3]})
    return result


def _interfaces():
    result = []
    with open("/proc/net/dev", encoding="utf-8") as stream:
        for line in stream.readlines()[2:]:
            name = line.split(":")[0].strip()
            if name:
                result.append(name)
    return result


def _route_entries():
    count = 0
    with open("/proc/net/route", encoding="utf-8") as stream:
        for line in stream.readlines()[1:]:
            if line.strip():
                count += 1
    return count


print(json.dumps({
    "uid": os.getuid(),
    "gid": os.getgid(),
    "cap_eff": _status_hex("CapEff"),
    "cap_prm": _status_hex("CapPrm"),
    "cap_bnd": _status_hex("CapBnd"),
    "interfaces": _interfaces(),
    "route_entries": _route_entries(),
    "connect_external_errno": _connect_errno("10.255.255.1", 80),
    "tmp_mounts": _tmp_mounts(),
    "cpu_max": _cgroup_value("cpu.max"),
    "memory_max": _cgroup_value("memory.max"),
    "pids_max": _cgroup_value("pids.max"),
    "root_write_errno": _write_errno("/probe-root-write"),
    "workspace_write_errno": _write_errno("/workspace/probe-write"),
    "workspace_listing": sorted(os.listdir("/workspace")),
    "docker_sock_var_run": os.path.exists("/var/run/docker.sock"),
    "docker_sock_run": os.path.exists("/run/docker.sock"),
}, sort_keys=True))
"""


def probe_reference_container(
    build: ReferenceImageBuildEvidenceV1, fixture: Path
) -> ContainerIsolationEvidenceV1:
    """Prove one fresh reference container enforces the frozen boundary.

    Reproduces the frozen runnable image bytes, loads them under the frozen
    build-evidence identity, launches one fresh container with the frozen
    SPEC §1.4.5 execution parameters, observes every isolation control from
    inside that container and from the daemon-side configuration, verifies
    container and loaded-image cleanup on every exit path, and returns one
    immutable evidence.  Any missing or false observation fails closed with
    ``RuntimeError`` and no partial evidence is ever returned.
    """
    fixture = Path(fixture)
    if not fixture.is_dir():
        raise ValueError(f"workspace fixture missing: {fixture}")
    container_id = ""
    image_ref = ""
    loaded_by_probe = False
    failure: BaseException | None = None
    evidence: ContainerIsolationEvidenceV1 | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="vesper-execution-probe-") as tmp:
            output_tar = _reproduce_frozen_layout(Path(tmp))
            image_ref, loaded_by_probe = _ensure_frozen_image(build, output_tar)
            container_id = _run_reference_container(image_ref, fixture)
            runtime = _observe_container(container_id)
            config = _inspect_container(container_id)
            evidence = _build_evidence(runtime, config)
    except BaseException as exc:
        failure = exc
    try:
        cleanup_verified = _verify_cleanup(
            container_id, image_ref if loaded_by_probe else ""
        )
    except BaseException:
        cleanup_verified = False
    if not cleanup_verified:
        raise RuntimeError("reference container cleanup not verified") from failure
    if failure is not None:
        raise failure.with_traceback(failure.__traceback__)
    assert evidence is not None
    return evidence


def _reference_run_argv(image_ref: str, fixture: Path, command: list[str]) -> list[str]:
    """The frozen no-network, non-root, read-only, bounded ``docker run``."""
    return [
        "docker",
        "run",
        "-d",
        "--network",
        "none",
        "--user",
        f"{NON_ROOT_UID}:{NON_ROOT_GID}",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--tmpfs",
        TMPFS_SPEC,
        "--cpus",
        str(CPU_LIMIT),
        "--memory",
        MEMORY_ARGV,
        "--pids-limit",
        str(PID_LIMIT),
        "--mount",
        f"type=bind,src={_mount_src(fixture)},dst={WORKSPACE_TARGET},ro",
        image_ref,
        *command,
    ]


def _mount_src(fixture: Path) -> str:
    """Windows daemon paths are normalized to forward slashes for ``--mount``."""
    return str(fixture).replace("\\", "/")


def _observation_command() -> list[str]:
    """Deliver the fixed observation script to the container inline."""
    payload = base64.b64encode(_OBSERVATION_SCRIPT.encode("utf-8")).decode("ascii")
    return ["python", "-c", f"import base64;exec(base64.b64decode('{payload}'))"]


def _reproduce_frozen_layout(tmp: Path) -> Path:
    """Reproduce the frozen OCI layout tar via the builder's own machinery."""
    context = tmp / "context"
    output_tar = tmp / "output.tar"
    context.mkdir()
    (context / "Dockerfile").write_bytes(_read_required(REPO_ROOT / RECIPE_RELATIVE))
    shutil.copytree(REPO_ROOT / FIXTURE_RELATIVE, context / "fixture")
    (context / "requirements.lock").write_bytes(
        _read_required(REPO_ROOT / REFERENCE_LOCK_RELATIVE)
    )
    _run_docker_build(context, output_tar)
    return output_tar


def _ensure_frozen_image(
    build: ReferenceImageBuildEvidenceV1, output_tar: Path
) -> tuple[str, bool]:
    """Return ``(image_ref, loaded_by_probe)`` for the frozen build evidence.

    When the daemon already holds the frozen identity the image is reused;
    otherwise the reproduced layout is loaded and the loaded image id is
    re-verified against the frozen build evidence.  A load that reports a
    drifted identity removes the drifted image and fails closed, so no
    residue is ever left on the drift path.
    """
    image_ref = f"sha256:{build.local_oci_manifest_digest}"
    if _image_id(image_ref) == image_ref:
        return image_ref, False
    loaded_id = _load_image(output_tar)
    if loaded_id != image_ref:
        _fail_load_with_cleanup(loaded_id, image_ref)
    return image_ref, True


def _image_id(image_ref: str) -> str | None:
    """The daemon image id for *image_ref*, or None when absent."""
    proc = subprocess.run(
        ["docker", "image", "inspect", image_ref, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        return None
    observed = proc.stdout.strip()
    return observed if observed else None


_LOADED_IMAGE_ID_RE = re.compile(r"Loaded image ID: (sha256:[0-9a-f]{64})")


def _load_image(output_tar: Path) -> str:
    """Load the layout tar and return the image id docker reports.

    Fails closed when the load fails or reports no image id.
    """
    proc = subprocess.run(
        ["docker", "load", "-i", str(output_tar)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        tail = proc.stderr[-2000:] if proc.stderr else ""
        raise RuntimeError(f"docker load failed (exit {proc.returncode}): {tail}")
    match = _LOADED_IMAGE_ID_RE.search(f"{proc.stdout}\n{proc.stderr}")
    if match is None:
        raise RuntimeError("docker load did not report a loaded image id")
    return match.group(1)


def _fail_load_with_cleanup(loaded_id: str, expected_ref: str) -> NoReturn:
    """Remove the drifted loaded image, then raise the identity failure.

    Fails closed when the drifted image removal itself cannot be verified.
    """
    if not _cleanup_loaded_image(loaded_id):
        raise RuntimeError("loaded reference image cleanup not verified")
    raise RuntimeError(
        f"loaded reference image identity {loaded_id} does not match "
        f"frozen build evidence {expected_ref}"
    )


def _run_reference_container(image_ref: str, fixture: Path) -> str:
    proc = subprocess.run(
        _reference_run_argv(image_ref, fixture, _observation_command()),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        tail = proc.stderr[-2000:] if proc.stderr else ""
        raise RuntimeError(
            f"docker run reference container failed (exit {proc.returncode}): {tail}"
        )
    container_id = proc.stdout.strip().splitlines()[-1].strip()
    if not container_id:
        raise RuntimeError("docker run returned no reference container id")
    return container_id


def _observe_container(container_id: str) -> dict[str, object]:
    """Wait for the observation script, then parse its JSON output."""
    wait = subprocess.run(
        ["docker", "wait", container_id], capture_output=True, text=True, timeout=60
    )
    if wait.returncode != 0:
        raise RuntimeError("docker wait failed for the reference container")
    if wait.stdout.strip() != "0":
        raise RuntimeError(
            f"reference container observation exited with code {wait.stdout.strip()}"
        )
    logs = subprocess.run(
        ["docker", "logs", container_id], capture_output=True, text=True, timeout=60
    )
    if logs.returncode != 0:
        raise RuntimeError("docker logs failed for the reference container")
    try:
        observations = json.loads(logs.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "reference container observation output is not valid JSON"
        ) from exc
    if not isinstance(observations, dict):
        raise RuntimeError("reference container observation output must be an object")
    return observations


def _inspect_container(container_id: str) -> dict[str, object]:
    """Extract the daemon-side configuration facts for the container."""
    proc = subprocess.run(
        ["docker", "inspect", container_id],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError("docker inspect failed for the reference container")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("docker inspect output is not valid JSON") from exc
    if (
        not isinstance(payload, list)
        or len(payload) != 1
        or not isinstance(payload[0], dict)
    ):
        raise RuntimeError("docker inspect must return exactly one container object")
    container = payload[0]
    host_config = container.get("HostConfig")
    image_config = container.get("Config")
    if not isinstance(host_config, dict) or not isinstance(image_config, dict):
        raise RuntimeError("docker inspect container object is malformed")
    user = image_config.get("User")
    mounts = host_config.get("Mounts")
    return {
        "config_user": user if isinstance(user, str) else "",
        "network_mode": host_config.get("NetworkMode"),
        "readonly_rootfs": host_config.get("ReadonlyRootfs"),
        "cap_drop": host_config.get("CapDrop"),
        "tmpfs": host_config.get("Tmpfs"),
        "nano_cpus": host_config.get("NanoCpus"),
        "memory": host_config.get("Memory"),
        "pids_limit": host_config.get("PidsLimit"),
        "mounts": mounts if isinstance(mounts, list) else [],
    }


def _build_evidence(
    runtime: dict[str, object], config: dict[str, object]
) -> ContainerIsolationEvidenceV1:
    """Validate every observed control against the frozen expectations.

    Any missing or false observation raises ``RuntimeError`` naming the exact
    observed field; no partial evidence is ever constructed.
    """
    # The smallest real read-only workspace probe (GREEN-3 core).
    _require_exact(runtime, "workspace_write_errno", WORKSPACE_WRITE_REJECTED_ERRNO)
    _require_nonempty_string_list(runtime, "workspace_listing")
    # The remaining runtime isolation controls, each observed from inside the
    # same fresh container.
    _require_exact(runtime, "uid", NON_ROOT_UID)
    _require_exact(runtime, "gid", NON_ROOT_GID)
    for capability in ("cap_eff", "cap_prm", "cap_bnd"):
        _require_exact(runtime, capability, ZERO_CAPABILITY_HEX)
    _require_exact(runtime, "interfaces", LOOPBACK_ONLY_INTERFACES)
    _require_exact(runtime, "route_entries", 0)
    _require_exact(runtime, "connect_external_errno", NO_EXTERNAL_ROUTE_ERRNO)
    _require_exact(runtime, "root_write_errno", ROOT_WRITE_REJECTED_ERRNO)
    _require_exact(runtime, "docker_sock_var_run", False)
    _require_exact(runtime, "docker_sock_run", False)
    _require_tmpfs_bounded(runtime)
    _require_exact(runtime, "cpu_max", CPU_MAX_EXPECTED)
    _require_exact(runtime, "memory_max", MEMORY_MAX_EXPECTED)
    _require_exact(runtime, "pids_max", PIDS_MAX_EXPECTED)
    _require_frozen_config(config)
    return ContainerIsolationEvidenceV1(
        network_disabled=True,
        non_root=True,
        root_read_only=True,
        capabilities_dropped=True,
        docker_socket_absent=True,
        workspace_read_only=True,
        tmpfs_bounded=True,
        cpu_limit=CPU_LIMIT,
        memory_limit_bytes=MEMORY_LIMIT_BYTES,
        pid_limit=PID_LIMIT,
        cleanup_verified=True,
    )


def _require_exact(observations: dict[str, object], key: str, expected: object) -> None:
    if key not in observations:
        raise RuntimeError(f"isolation observation missing: {key}")
    if observations[key] != expected:
        raise RuntimeError(f"isolation observation not satisfied: {key}")


def _require_nonempty_string_list(observations: dict[str, object], key: str) -> None:
    value = observations.get(key)
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(entry, str) for entry in value)
    ):
        raise RuntimeError(f"isolation observation not satisfied: {key}")


def _require_tmpfs_bounded(observations: dict[str, object]) -> None:
    """/tmp must be exactly one tmpfs mount bounded to 256 MiB."""
    value = observations.get("tmp_mounts")
    if (
        not isinstance(value, list)
        or len(value) != 1
        or not isinstance(value[0], dict)
        or value[0].get("fs") != "tmpfs"
    ):
        raise RuntimeError("isolation observation not satisfied: tmp_mounts")
    opts = value[0].get("opts")
    if not isinstance(opts, str) or TMPFS_SIZE_KIB not in opts:
        raise RuntimeError("isolation observation not satisfied: tmp_mounts")


def _require_frozen_config(config: dict[str, object]) -> None:
    """The fresh container's daemon-side configuration must be the frozen one."""
    _require_exact(config, "network_mode", "none")
    _require_exact(config, "readonly_rootfs", True)
    _require_exact(config, "cap_drop", ["ALL"])
    _require_exact(config, "tmpfs", {"/tmp": TMPFS_OPTIONS})
    _require_exact(config, "nano_cpus", CPU_LIMIT * 1_000_000_000)
    _require_exact(config, "memory", MEMORY_LIMIT_BYTES)
    _require_exact(config, "pids_limit", PID_LIMIT)
    user = config.get("config_user")
    if not isinstance(user, str) or user in ("", "root", "0"):
        raise RuntimeError("isolation observation not satisfied: config_user")
    _require_frozen_mounts(config.get("mounts"))


def _require_frozen_mounts(value: object) -> None:
    """Exactly the one read-only /workspace bind and no other mount.

    The workspace bind must be the container's only mount, so no
    authoritative workspace, control-plane database, credential, or backup
    path can be mounted, and no Docker socket can be present.
    """
    if not isinstance(value, list) or len(value) != 1:
        raise RuntimeError("isolation observation not satisfied: mounts")
    mount = value[0]
    if (
        not isinstance(mount, dict)
        or mount.get("Type") != "bind"
        or mount.get("Target") != WORKSPACE_TARGET
        or mount.get("ReadOnly") is not True
    ):
        raise RuntimeError("isolation observation not satisfied: mounts")
    if "docker.sock" in str(mount):
        raise RuntimeError("isolation observation not satisfied: mounts")


def _verify_cleanup(container_id: str, image_ref: str) -> bool:
    """Remove the container and any image loaded by this probe, then verify."""
    if container_id and not _cleanup_container(container_id):
        return False
    if image_ref and not _cleanup_loaded_image(image_ref):
        return False
    return True


def _cleanup_container(container_id: str) -> bool:
    """Remove the container and verify it is gone."""
    proc = subprocess.run(
        ["docker", "rm", "-f", container_id],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        return False
    verify = subprocess.run(
        ["docker", "inspect", container_id],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return verify.returncode != 0


def _cleanup_loaded_image(image_ref: str) -> bool:
    """Remove an image loaded by this probe and verify it is gone."""
    proc = subprocess.run(
        ["docker", "image", "rm", image_ref],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        return False
    verify = subprocess.run(
        ["docker", "image", "inspect", image_ref],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return verify.returncode != 0
