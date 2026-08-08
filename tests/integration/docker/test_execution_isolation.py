"""T18.2 legacy step 18.C: real frozen-container isolation observations.

The executor creates one fresh container from the frozen built-in image
digest with every SPEC §1.4.5 isolation parameter; these tests observe
that boundary from inside the real container (the T02.3 pattern: uid/
gid, capability sets, loopback-only interfaces, no routes, ENETUNREACH
external connect, EROFS root and workspace writes, absent Docker socket,
bounded /tmp tmpfs, exact cgroup CPU/memory/PID ceilings) and prove the
container reads the exact materialized candidate bytes, while the
executor's own daemon-side configuration verification runs on the same
real container.  Each execution returns one bounded raw result
(GREEN-1..GREEN-4).
"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from collections.abc import Iterator

import pytest

pytest.importorskip("pydantic")

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.execution.docker_executor import DockerExecutor
from vespercode.execution.docker_profile import ExecutionRequestV1
from vespercode.execution.materialization import (
    MaterializedCandidateV1,
    allocate_execution_root,
    materialize_candidate,
)
from vespercode.profiles.reference import load_reference_profile
from vespercode.trees.candidate import (
    CandidatePostimageV1,
    CandidateTreeV1,
    derive_candidate_revision,
    root_candidate_revision,
)
from vespercode.trees.content_store import ContentObjectRefV1, ContentObjectStore
from vespercode.trees.snapshot import (
    SealedSnapshotInputFileV1,
    SnapshotDirectoryEntryV1,
    SnapshotEntryV1,
    SnapshotFileEntryV1,
    SnapshotTreeV1,
    _root_digest,
)
from vespercode.trees.text_classifier import (
    TextMetadataV1,
    classify_supported_text,
)

pytestmark = pytest.mark.docker_integration

# The frozen T18.1 request identity (SPEC §1.4.1/§1.4.5).
_MANIFEST_DIGEST = "841e9d55359c4007cd53b4b50a2ff10572b955650847bfb545ea2f4aa661443b"
_IMAGE_DIGEST = "71e931b58316637d1cbe647a57fc4c3588837f9451f7fbad391c34b3b1b43905"

_FIXTURE_FILES = (
    "pyproject.toml",
    "requirements.lock",
    "src/vesper_fixture/calculator.py",
    "tests/test_calculator.py",
)
_CALCULATOR_PATH = "src/vesper_fixture/calculator.py"

# The in-container observation script: reads only /proc, /sys, and the
# read-only /workspace facts plus bounded write/connect probes, and prints
# one JSON object to stdout.  The initial pause lets the bounded collector
# attach before any output is written (the daemon's attach handshake can
# lag a fast container start).  The script is fixed source delivered
# inline through ``python -c`` so no host path ever enters the container
# (the T02.3 pattern).
_OBSERVATION_SCRIPT = r"""
import hashlib
import json
import os
import socket
import time

time.sleep(0.5)


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


def _file_hash(relpath):
    try:
        with open(relpath, "rb") as stream:
            return hashlib.sha256(stream.read()).hexdigest()
    except OSError as exc:
        return "ERR:" + str(exc.errno)


def _workspace_listing():
    result = []
    for dirpath, dirnames, filenames in os.walk("/workspace"):
        for name in sorted(dirnames):
            full = os.path.join(dirpath, name)
            result.append({"type": "dir", "path": full.replace("/workspace/", "")})
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            result.append({
                "type": "file",
                "path": full.replace("/workspace/", ""),
                "sha256": _file_hash(full),
            })
    return result


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
    "workspace_listing": _workspace_listing(),
    "docker_sock_var_run": os.path.exists("/var/run/docker.sock"),
    "docker_sock_run": os.path.exists("/run/docker.sock"),
}, sort_keys=True))
"""

# The frozen T02.3 observation expectations (real probe evidence on the
# frozen image; any deviation is a closed failure).
_ZERO_CAPABILITY_HEX = "0000000000000000"
_EROFS_ERRNO = 30
_ENETUNREACH_ERRNO = 101
_TMPFS_SIZE_KIB = "262144k"
_CPU_MAX_EXPECTED = "200000 100000"
_MEMORY_MAX_EXPECTED = "2147483648"
_PIDS_MAX_EXPECTED = "256"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def packaged_reference_profile_bytes() -> bytes:
    return (
        _repo_root()
        / "src"
        / "vespercode"
        / "profiles"
        / "builtin"
        / "reference-profile-v1.json"
    ).read_bytes()


def frozen_policy_digest() -> str:
    manifest = load_reference_profile(packaged_reference_profile_bytes())
    return manifest.editable_path_policy.digest


def corrected_calculator_bytes() -> bytes:
    original = (_repo_root() / "reference" / "fixture" / _CALCULATOR_PATH).read_bytes()
    fixed = original.replace(b"    return left - right\n", b"    return left + right\n")
    assert fixed != original, "the fixture defect line must exist"
    return fixed


def build_fixture_candidate() -> CandidateTreeV1:
    """One real candidate tree over the frozen reference fixture bytes."""
    fixture = _repo_root() / "reference" / "fixture"
    store = ContentObjectStore()
    rows: list[SealedSnapshotInputFileV1] = []
    for rel in _FIXTURE_FILES:
        raw = (fixture / rel).read_bytes()
        ref = store.put(raw)
        rows.append(
            SealedSnapshotInputFileV1(
                schema_version=1,
                path=CanonicalRelativePathV1(rel),
                content_sha256=ref.sha256,
                byte_count=ref.byte_count,
            )
        )
    rows.sort(key=lambda row: row.path.value)
    directory_values = {
        "/".join(row.path.value.split("/")[:index])
        for row in rows
        for index in range(1, len(row.path.value.split("/")))
    }
    entries: list[SnapshotEntryV1] = [
        SnapshotDirectoryEntryV1(kind="DIRECTORY", path=CanonicalRelativePathV1(value))
        for value in sorted(directory_values)
    ]
    for row in rows:
        ref = ContentObjectRefV1(sha256=row.content_sha256, byte_count=row.byte_count)
        classification = classify_supported_text(store.get(ref))
        if classification.kind == "TEXT_FILE":
            text_profile: PresentV1[TextMetadataV1] | AbsentV1 = (
                classification.text_profile
            )
        else:
            text_profile = AbsentV1(kind="ABSENT")
        entries.append(
            SnapshotFileEntryV1(
                kind=classification.kind,
                path=row.path,
                size_bytes=row.byte_count,
                content_ref=ref,
                text_profile=text_profile,
            )
        )
    policy_digest = frozen_policy_digest()
    snapshot = SnapshotTreeV1(
        root_digest=_root_digest(policy_digest, tuple(entries)),
        repository_policy_digest=policy_digest,
        entries=tuple(entries),
        file_bytes=tuple(
            (
                row.path.value,
                store.get(
                    ContentObjectRefV1(
                        sha256=row.content_sha256, byte_count=row.byte_count
                    )
                ),
            )
            for row in rows
        ),
    )
    revision = derive_candidate_revision(
        root_candidate_revision(snapshot, store),
        (
            CandidatePostimageV1(
                schema_version=1,
                operation="REPLACE",
                path=CanonicalRelativePathV1(_CALCULATOR_PATH),
                raw_bytes=corrected_calculator_bytes(),
            ),
        ),
    )
    return revision.tree


def builtin_environment_dict() -> dict[str, object]:
    return {
        "variables": [
            {"name": "LANG", "value": "C.UTF-8"},
            {"name": "LC_ALL", "value": "C.UTF-8"},
            {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
            {"name": "PYTHONHASHSEED", "value": "0"},
            {"name": "TZ", "value": "UTC"},
        ]
    }


def builtin_resources_dict() -> dict[str, object]:
    return {
        "cpus": 2,
        "memory_bytes": 2 * 1024**3,
        "pids_limit": 256,
        "tmpfs_size_bytes": 256 * 1024**2,
        "max_output_bytes": 4 * 1024**2,
    }


def builtin_profile_dict() -> dict[str, object]:
    return {
        "schema_version": 1,
        "profile_version": 1,
        "network_mode": "none",
        "user": "10001:10001",
        "read_only_rootfs": True,
        "capabilities_dropped": "ALL",
        "docker_socket_mounted": False,
        "workdir": "/workspace",
        "workspace_mount": {"target": "/workspace", "read_only": True},
        "tmpfs_mount": {"path": "/tmp"},
        "resources": builtin_resources_dict(),
        "environment": builtin_environment_dict(),
        "fresh_container_per_check": True,
        "pytest_plugin_autoload_disabled": True,
    }


def builtin_request_dict() -> dict[str, object]:
    return {
        "schema_version": 1,
        "request_id": "req-18-c-isolation",
        "reference_profile_digest": _MANIFEST_DIGEST,
        "docker_image_digest": _IMAGE_DIGEST,
        "docker_execution_profile_version": 1,
        "profile": builtin_profile_dict(),
        "argv": {"arguments": ("python", "-c", "print('probe')")},
    }


def observation_request() -> ExecutionRequestV1:
    payload = base64.b64encode(_OBSERVATION_SCRIPT.encode("utf-8")).decode("ascii")
    return ExecutionRequestV1.model_validate(
        {
            **builtin_request_dict(),
            "argv": {
                "arguments": (
                    "python",
                    "-c",
                    f"import base64;exec(base64.b64decode('{payload}'))",
                )
            },
        }
    )


_MODULE_ROOT_BASE = Path(tempfile.mkdtemp(prefix="vesper-t182-isolation-"))


@pytest.fixture(scope="module", autouse=True)
def _remove_module_residue() -> Iterator[None]:
    yield
    _remove_executor_containers()
    shutil.rmtree(_MODULE_ROOT_BASE, ignore_errors=True)


def _remove_executor_containers() -> None:
    try:
        import docker  # type: ignore[import-untyped]

        client = docker.from_env()
        for container in client.containers.list(
            all=True, filters={"name": "vespercode-check"}
        ):
            container.remove(force=True)
    except Exception:
        pass


def materialized_candidate() -> MaterializedCandidateV1:
    return materialize_candidate(
        build_fixture_candidate(), allocate_execution_root(_MODULE_ROOT_BASE)
    )


@pytest.fixture(scope="module")
def executor() -> DockerExecutor:
    return DockerExecutor()


def test_real_container_observes_frozen_isolation_boundary(
    executor: DockerExecutor,
) -> None:
    result = executor.execute(observation_request(), materialized_candidate())
    assert result.error_code is None
    assert result.exit_code == 0
    assert result.container_stopped is False
    observations = json.loads(result.stdout.decode("utf-8"))
    assert observations["uid"] == 10001
    assert observations["gid"] == 10001
    for capability in ("cap_eff", "cap_prm", "cap_bnd"):
        assert observations[capability] == _ZERO_CAPABILITY_HEX, capability
    assert observations["interfaces"] == ["lo"]
    assert observations["route_entries"] == 0
    assert observations["connect_external_errno"] == _ENETUNREACH_ERRNO
    assert observations["root_write_errno"] == _EROFS_ERRNO
    assert observations["workspace_write_errno"] == _EROFS_ERRNO
    assert observations["docker_sock_var_run"] is False
    assert observations["docker_sock_run"] is False
    tmp_mounts = observations["tmp_mounts"]
    assert len(tmp_mounts) == 1
    assert tmp_mounts[0]["fs"] == "tmpfs"
    assert _TMPFS_SIZE_KIB in tmp_mounts[0]["opts"]
    assert observations["cpu_max"] == _CPU_MAX_EXPECTED
    assert observations["memory_max"] == _MEMORY_MAX_EXPECTED
    assert observations["pids_max"] == _PIDS_MAX_EXPECTED


def test_real_container_reads_exact_candidate_bytes(
    executor: DockerExecutor,
) -> None:
    candidate = build_fixture_candidate()
    materialized = materialize_candidate(
        candidate, allocate_execution_root(_MODULE_ROOT_BASE)
    )
    result = executor.execute(observation_request(), materialized)
    assert result.error_code is None
    observations = json.loads(result.stdout.decode("utf-8"))
    listing = observations["workspace_listing"]
    calculator_row = next(row for row in listing if row["path"] == _CALCULATOR_PATH)
    # The container saw the CANDIDATE bytes (the corrected calculator),
    # byte-identical to the sealed materialization and the candidate tree.
    expected = candidate.read_bytes(CanonicalRelativePathV1(_CALCULATOR_PATH))
    assert hashlib.sha256(expected).hexdigest() == calculator_row["sha256"]
    assert corrected_calculator_bytes() == expected
    # Every materialized file is present with its exact sealed bytes.
    materialized_paths = {row.path for row in materialized.files}
    listed_paths = {row["path"] for row in listing if row["type"] == "file"}
    assert materialized_paths.issubset(listed_paths)
    for row in materialized.files:
        listed = next(entry for entry in listing if entry["path"] == row.path)
        assert listed["sha256"] == row.sha256, row.path


def test_real_execution_success_returns_bounded_raw_evidence(
    executor: DockerExecutor,
) -> None:
    request = ExecutionRequestV1.model_validate(
        {
            **builtin_request_dict(),
            "request_id": "req-18-c-probe",
            "argv": {
                "arguments": (
                    "python",
                    "-c",
                    "import sys; sys.stdout.write('exact-out'); sys.stderr.write('exact-err')",
                )
            },
        }
    )
    result = executor.execute(request, materialized_candidate())
    assert result.error_code is None
    assert result.exit_code == 0
    assert result.stdout == b"exact-out"
    assert result.stderr == b"exact-err"
    assert result.output_bytes == 18
    assert result.container_stopped is False
    assert result.timed_out is False
    assert result.output_limit_exceeded is False
    assert result.container_id != ""
