"""T18.2 legacy step 18.C: isolated Docker execution output/deadline limits.

The card's exact RED test (a real output flood in one fresh frozen
container is stopped/killed by its exact id with bounded raw evidence),
a real deadline kill, and the 18.C isolation/deadline/output matrix: the
exact closed isolation profile within limits yields one bounded result,
and every network/root/capability/socket/writable-root/resource/deadline/
output-limit violation stops/kills the exact container and returns the
declared failure with bounded output (GREEN-1..GREEN-4).
"""

from __future__ import annotations

import shutil
import struct
import tempfile
from pathlib import Path
from collections.abc import Iterator

import pytest

pytest.importorskip("pydantic")

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.execution.docker_executor import (
    DockerExecutor,
    RawExecutionResultV1,
)
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
_MANIFEST_DIGEST = "d0700f00f5ae2501ac9be7fbdd66d20e76c16a6c6f9ab7893c1aea71d57e927e"
_IMAGE_DIGEST = "cf0b6c5ccac588fccd07c3b9f050bff4daf550ac6e518fd06efb6e988ab1d823"
_MAX_OUTPUT_BYTES = 4 * 1024**2

_FIXTURE_FILES = (
    "pyproject.toml",
    "requirements.lock",
    "src/vesper_fixture/calculator.py",
    "tests/test_calculator.py",
)
_CALCULATOR_PATH = "src/vesper_fixture/calculator.py"

# The output flood: 32 MiB of stdout written in flushed 64 KiB chunks with
# a short pause between chunks, so the stream keeps producing for several
# seconds.  The bounded collector necessarily observes more than the 4 MiB
# cap while the container is still running and kills it by its exact id,
# and the slow rate guarantees the collector attaches mid-run even when
# the daemon's attach handshake is slow (a fast flood could finish before
# the collector connects, which would end in a natural exit instead of
# the required mid-run kill).
_FLOOD_SCRIPT = (
    "import sys, time\n"
    "for _ in range(512):\n"
    "    sys.stdout.write('x' * 65536)\n"
    "    sys.stdout.flush()\n"
    "    time.sleep(0.01)\n"
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def packaged_reference_profile_bytes() -> bytes:
    """The packaged production manifest bytes (the frozen GO identity)."""
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
        "max_output_bytes": _MAX_OUTPUT_BYTES,
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
        "request_id": "req-18-c-1",
        "reference_profile_digest": _MANIFEST_DIGEST,
        "docker_image_digest": _IMAGE_DIGEST,
        "docker_execution_profile_version": 1,
        "profile": builtin_profile_dict(),
        "argv": {"arguments": ("python", "-c", _FLOOD_SCRIPT)},
    }


def output_flood_request() -> ExecutionRequestV1:
    """The closed request whose argv floods stdout beyond the 4 MiB cap."""
    return ExecutionRequestV1.model_validate(builtin_request_dict())


def idle_request() -> ExecutionRequestV1:
    """The closed request whose argv sleeps far beyond any deadline."""
    return ExecutionRequestV1.model_validate(
        {
            **builtin_request_dict(),
            "request_id": "req-18-c-idle",
            "argv": {"arguments": ("python", "-c", "import time; time.sleep(60)")},
        }
    )


_MODULE_ROOT_BASE = Path(tempfile.mkdtemp(prefix="vesper-t182-execute-"))


@pytest.fixture(scope="module", autouse=True)
def _remove_module_residue() -> Iterator[None]:
    yield
    # The executor stops/kills but never removes (the cleanup contract
    # owns removal); this module's own containers and roots are removed
    # at teardown so no residue outlives the module.
    _remove_executor_containers()
    shutil.rmtree(_MODULE_ROOT_BASE, ignore_errors=True)


def _remove_executor_containers() -> None:
    """Remove every container created by this module's executor runs."""
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
    """One real materialized fixture candidate in a fresh execution root."""
    return materialize_candidate(
        build_fixture_candidate(), allocate_execution_root(_MODULE_ROOT_BASE)
    )


@pytest.fixture(scope="module")
def executor() -> DockerExecutor:
    return DockerExecutor()


def test_output_limit_kills_exact_container(executor: DockerExecutor) -> None:
    result = executor.execute(output_flood_request(), materialized_candidate())
    assert result.error_code == "CHECK_OUTPUT_LIMIT_EXCEEDED"
    assert result.container_stopped is True


def test_deadline_kills_exact_container() -> None:
    executor = DockerExecutor(timeout_seconds=5)
    result = executor.execute(idle_request(), materialized_candidate())
    assert result.error_code == "CHECK_TIMEOUT"
    assert result.timed_out is True
    assert result.container_stopped is True
    assert result.output_bytes <= _MAX_OUTPUT_BYTES


def test_container_isolation_deadline_output_matrix() -> None:
    """18.C matrix (PLAN 18.C): the exact closed isolation profile within
    limits yields one bounded result; network, root, capability, Docker
    socket, writable root/workspace, resource, deadline, or output-limit
    violation kills the exact container and returns the declared failure
    with bounded output.
    """
    # --- Success within limits: one bounded raw result, no stop/kill. ---
    script = "import sys; sys.stdout.write('out-bytes'); sys.stderr.write('err-bytes')"
    request = ExecutionRequestV1.model_validate(
        {
            **builtin_request_dict(),
            "argv": {"arguments": ("python", "-c", script)},
        }
    )
    candidate = materialized_candidate()
    success = _execute_with_fake(
        _FakeClient(
            container=_FakeContainer(
                container_id="fake-success",
                attrs=_frozen_attrs(candidate),
                exit_code=0,
            ),
            socket=_FakeStreamSocket(
                [_frame(1, b"out-bytes"), _frame(2, b"err-bytes")]
            ),
        ),
        request,
        candidate,
    )
    assert success.error_code is None
    assert success.exit_code == 0
    assert success.stdout == b"out-bytes"
    assert success.stderr == b"err-bytes"
    assert success.output_bytes == 18
    assert success.container_stopped is False

    # --- Deadline violation: the exact container is stopped. ---
    deadline_result = _execute_with_fake(
        _FakeClient(
            container=_FakeContainer(
                container_id="fake-idle",
                attrs=_frozen_attrs(candidate),
                exit_code=None,
            ),
            socket=_FakeStreamSocket([], timeout_forever=True),
        ),
        request,
        candidate,
        timeout_seconds=0.05,
    )
    assert deadline_result.error_code == "CHECK_TIMEOUT"
    assert deadline_result.timed_out is True
    assert deadline_result.container_stopped is True
    assert deadline_result.output_bytes == 0

    # --- Output-limit violation: the exact container is stopped with
    # bounded output (a single frame larger than the 4 MiB cap). ---
    overflow_result = _execute_with_fake(
        _FakeClient(
            container=_FakeContainer(
                container_id="fake-flood",
                attrs=_frozen_attrs(candidate),
                exit_code=None,
            ),
            socket=_FakeStreamSocket(
                [_frame(1, b"prefix"), _frame(1, b"x" * (_MAX_OUTPUT_BYTES + 1))]
            ),
        ),
        request,
        candidate,
    )
    assert overflow_result.error_code == "CHECK_OUTPUT_LIMIT_EXCEEDED"
    assert overflow_result.output_limit_exceeded is True
    assert overflow_result.container_stopped is True
    assert overflow_result.output_bytes <= _MAX_OUTPUT_BYTES

    # --- Output-limit violation on the COMBINED total: SPEC §1.4.5/§5.1
    # bounds one check's raw output (stdout + stderr) at 4 MiB. ---
    combined_overflow = _execute_with_fake(
        _FakeClient(
            container=_FakeContainer(
                container_id="fake-combined",
                attrs=_frozen_attrs(candidate),
                exit_code=None,
            ),
            socket=_FakeStreamSocket(
                [
                    _frame(1, b"o" * (_MAX_OUTPUT_BYTES - 100)),
                    _frame(2, b"e" * 200),
                ]
            ),
        ),
        request,
        candidate,
    )
    assert combined_overflow.error_code == "CHECK_OUTPUT_LIMIT_EXCEEDED"
    assert combined_overflow.container_stopped is True
    assert combined_overflow.output_bytes <= _MAX_OUTPUT_BYTES

    # --- Isolation violations: every daemon-side drift of the exact
    # container is detected before start; the container is never started
    # and the closed failure is returned with zero output. ---
    workspace_mount = {
        "Type": "bind",
        "Target": "/workspace",
        "ReadOnly": True,
        "Source": candidate.root_path.replace("\\", "/"),
    }
    drift_cases: list[tuple[str, dict[str, object]]] = [
        ("network", {"HostConfig": {"NetworkMode": "bridge"}}),
        ("non-root user", {"Config": {"User": "root"}}),
        ("read-only rootfs", {"HostConfig": {"ReadonlyRootfs": False}}),
        ("capability drop", {"HostConfig": {"CapDrop": []}}),
        (
            "docker socket mount",
            {
                "HostConfig": {
                    "Mounts": [
                        workspace_mount,
                        {
                            "Type": "bind",
                            "Target": "/var/run/docker.sock",
                            "ReadOnly": True,
                            "Source": "/var/run/docker.sock",
                        },
                    ]
                }
            },
        ),
        (
            "writable workspace",
            {"HostConfig": {"Mounts": [dict(workspace_mount, ReadOnly=False)]}},
        ),
        ("resource limit", {"HostConfig": {"Memory": 1024**3}}),
    ]
    for label, drift in drift_cases:
        drifted = _drift_attrs(candidate, drift)
        violation = _execute_with_fake(
            _FakeClient(
                container=_FakeContainer(container_id="fake-drift", attrs=drifted),
                socket=_FakeStreamSocket([]),
            ),
            request,
            candidate,
        )
        assert violation.error_code == "CHECK_ISOLATION_VIOLATION", label
        assert violation.container_stopped is False, label
        assert violation.output_bytes == 0, label
        assert violation.exit_code is None, label

    # --- Execution error: container creation fails closed with the exact
    # empty container identity and no residue claims. ---
    failed = _execute_with_fake(
        _FakeClient(
            container=_FakeContainer("fake-gone", _frozen_attrs(candidate)),
            socket=_FakeStreamSocket([]),
            create_failure=RuntimeError("daemon down"),
        ),
        request,
        candidate,
    )
    assert failed.error_code == "CHECK_EXECUTION_ERROR"
    assert failed.container_id == ""
    assert failed.exit_code is None


def _frame(stream_id: int, payload: bytes) -> bytes:
    """One docker attach stream frame (8-byte header + payload)."""
    return struct.pack(">BxxxL", stream_id, len(payload)) + payload


def _frozen_attrs(candidate: MaterializedCandidateV1) -> dict[str, object]:
    """The daemon-side inspect shape the frozen profile must produce."""
    environment = [
        "PATH=/usr/local/bin:/usr/bin:/bin",
        "LANG=C.UTF-8",
        "LC_ALL=C.UTF-8",
        "PYTHONDONTWRITEBYTECODE=1",
        "PYTHONHASHSEED=0",
        "TZ=UTC",
    ]
    return {
        "Image": _IMAGE_DIGEST,
        "Config": {
            "User": "10001:10001",
            "WorkingDir": "/workspace",
            "Env": environment,
        },
        "HostConfig": {
            "NetworkMode": "none",
            "ReadonlyRootfs": True,
            "CapDrop": ["ALL"],
            "Tmpfs": {"/tmp": "rw,size=256m"},
            "NanoCpus": 2_000_000_000,
            "Memory": 2 * 1024**3,
            "PidsLimit": 256,
            "Mounts": [
                {
                    "Type": "bind",
                    "Target": "/workspace",
                    "ReadOnly": True,
                    "Source": candidate.root_path.replace("\\", "/"),
                }
            ],
        },
        "State": {"Running": False},
    }


def _drift_attrs(
    candidate: MaterializedCandidateV1, drift: dict[str, object]
) -> dict[str, object]:
    """One drifted inspect shape: the frozen shape with one field replaced."""
    attrs = _frozen_attrs(candidate)
    for section, values in drift.items():
        if not isinstance(values, dict):
            raise AssertionError("drift rows are per-section dicts")
        current = attrs.get(section)
        if not isinstance(current, dict):
            current = {}
        merged = dict(current)
        merged.update(values)
        attrs[section] = merged
    return attrs


class _FakeStreamSocket:
    """Scripted attach socket: chunks then EOF, or TimeoutError forever."""

    def __init__(self, chunks: list[bytes], timeout_forever: bool = False) -> None:
        self._chunks = list(chunks)
        self._timeout_forever = timeout_forever

    def settimeout(self, timeout: float) -> None:
        return None

    def recv_into(self, buffer: bytearray) -> int:
        if self._timeout_forever:
            raise TimeoutError("scripted silent stream")
        if not self._chunks:
            return 0
        chunk = self._chunks.pop(0)
        buffer[: len(chunk)] = chunk
        return len(chunk)


class _FakeContainer:
    def __init__(
        self,
        container_id: str,
        attrs: dict[str, object],
        exit_code: int | None = None,
    ) -> None:
        self.id = container_id
        self.attrs = attrs
        self._exit_code = exit_code
        self.started = False
        self.stopped_exact: list[str] = []
        self.killed_exact: list[str] = []
        self.wait_called = False

    def start(self) -> None:
        self.started = True

    def stop(self, timeout: float | None = None) -> None:
        self.stopped_exact.append(self.id)
        self.attrs = {**self.attrs, "State": {"Running": False}}

    def kill(self) -> None:
        self.killed_exact.append(self.id)
        self.attrs = {**self.attrs, "State": {"Running": False}}

    def reload(self) -> None:
        return None

    def wait(self, timeout: float | None = None) -> dict[str, object]:
        self.wait_called = True
        if self.stopped_exact or self.killed_exact:
            return {"StatusCode": 137}
        if self._exit_code is None:
            raise RuntimeError("fake container never exits")
        return {"StatusCode": self._exit_code}


class _FakeAPIClient:
    def __init__(self, socket: _FakeStreamSocket) -> None:
        self._socket = socket

    def _url(self, path: str, *args: object) -> str:
        return path.format(*args)

    def _post(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, object] | None = None,
        stream: bool = False,
    ) -> object:
        return object()

    def _get_raw_response_socket(self, response: object) -> object:
        return self._socket


class _FakeClient:
    def __init__(
        self,
        container: _FakeContainer,
        socket: _FakeStreamSocket,
        create_failure: Exception | None = None,
    ) -> None:
        self._container = container
        self._socket = socket
        self._create_failure = create_failure
        self.api = _FakeAPIClient(socket)
        self.created_kwargs: dict[str, object] = {}

    @property
    def containers(self) -> _FakeClient:
        return self

    def create(self, **kwargs: object) -> _FakeContainer:
        self.created_kwargs = kwargs
        if self._create_failure is not None:
            raise self._create_failure
        return self._container


def _execute_with_fake(
    client: _FakeClient,
    request: ExecutionRequestV1,
    candidate: MaterializedCandidateV1,
    timeout_seconds: float = 60.0,
) -> RawExecutionResultV1:
    return DockerExecutor(
        timeout_seconds=timeout_seconds, client_factory=lambda: client
    ).execute(request, candidate)
