"""T18.2 legacy step 18.C: isolated Docker check execution.

``DockerExecutor.execute`` executes one closed ``ExecutionRequestV1``
against one materialized candidate in one fresh container created from
the frozen built-in image digest with every frozen SPEC §1.4.5 isolation
parameter (network none, non-root user 10001:10001, read-only rootfs,
cap-drop ALL, no Docker socket, one read-only /workspace bind, bounded
tmpfs, 2 CPU / 2 GiB memory / 256 PIDs), re-verifies the daemon-side
configuration of that exact container, and collects only bounded raw
output bytes (stdout + stderr capped together at the profile's 4 MiB)
under a bounded deadline.  Any isolation-config drift, deadline expiry,
or output overflow stops/kills the exact container (never a wildcard)
and returns the closed failure with bounded raw evidence; the container
itself is left for the cleanup contract to remove (GREEN-1..GREEN-4).
PASS/FAIL parsing and materialization-root deletion remain out of scope.

The deadline bounds the container-side phases (attach collection and the
exit-code wait); the daemon API calls around them (create/inspect/
attach/start/stop/kill) are each individually bounded by the SDK's own
request timeout, and a daemon that hangs on those calls fails closed as
``CHECK_EXECUTION_ERROR`` rather than silently exceeding the frozen
per-check bound.
"""

from __future__ import annotations

import os
import struct
import time
import uuid
from typing import Callable, Literal, Protocol, TypeAlias, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.execution.docker_profile import ExecutionRequestV1
from vespercode.execution.materialization import MaterializedCandidateV1

# The frozen per-check deadline (SPEC §4.2.6: the target-check sublimit
# ceiling of 120 s); shorter deadlines can be injected on the executor for
# deterministic tests.  The deadline is a bound, never a target.
_FROZEN_TIMEOUT_SECONDS = 120.0

# The frozen T02.2 /tmp tmpfs options (SPEC §1.4.5).
_FROZEN_TMPFS_OPTIONS = "rw,size=256m"

# The docker attach stream multiplexing frame header: stream byte, three
# reserved bytes, then a big-endian uint32 payload length.
_FRAME_HEADER = struct.Struct(">BxxxL")

ExecutionErrorCodeV1 = Literal[
    "CHECK_TIMEOUT",
    "CHECK_OUTPUT_LIMIT_EXCEEDED",
    "CHECK_ISOLATION_VIOLATION",
    "CHECK_EXECUTION_ERROR",
]
"""Closed execution failures (SPEC §4.5 errors; GREEN-2/GREEN-3)."""


class RawExecutionResultV1(BaseModel):
    """One bounded raw execution evidence for one exact container.

    Sealed value fields: the request id and the exact container id, the
    container exit code when it ran to completion, bounded raw stdout/
    stderr bytes (never lossily re-encoded, so the exact captured bytes
    are the evidence) and their exact byte total, the closed failure
    flags, and the closed error code (None exactly on success).  The
    result is raw evidence only: no PASS/FAIL interpretation ever happens
    here (GREEN-4).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    request_id: StrictStr
    container_id: StrictStr
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    output_bytes: int
    timed_out: bool
    output_limit_exceeded: bool
    container_stopped: bool
    error_code: ExecutionErrorCodeV1 | None

    @field_validator("stdout", "stderr", mode="before")
    @classmethod
    def _streams_are_exact_bytes(cls, value: object) -> object:
        if not isinstance(value, bytes):
            raise ValueError("stdout and stderr must be exact raw bytes")
        return value

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("request_id")
    @classmethod
    def _request_id_is_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("request id must not be empty")
        return value

    @field_validator("exit_code", mode="before")
    @classmethod
    def _exit_code_is_exact_int_or_none(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("exit_code must be an exact integer or None")
        return value

    @field_validator(
        "timed_out", "output_limit_exceeded", "container_stopped", mode="before"
    )
    @classmethod
    def _flags_are_exact_bools(cls, value: object) -> object:
        if not isinstance(value, bool):
            raise ValueError("failure flags must be exact booleans")
        return value

    @field_validator("output_bytes", mode="before")
    @classmethod
    def _output_bytes_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("output_bytes must be an exact decimal integer")
        if value < 0:
            raise ValueError("output_bytes must not be negative")
        return value

    @model_validator(mode="after")
    def _require_closed_outcome(self) -> RawExecutionResultV1:
        if self.error_code is None:
            if self.timed_out or self.output_limit_exceeded or self.container_stopped:
                raise ValueError("success results must not carry failure flags")
            if self.exit_code is None:
                raise ValueError("success results require a container exit code")
        elif self.error_code == "CHECK_TIMEOUT":
            if not self.timed_out or not self.container_stopped:
                raise ValueError("CHECK_TIMEOUT results require both failure flags")
            if self.output_limit_exceeded:
                raise ValueError("CHECK_TIMEOUT results cannot be output-limited")
        elif self.error_code == "CHECK_OUTPUT_LIMIT_EXCEEDED":
            if not self.output_limit_exceeded or not self.container_stopped:
                raise ValueError("output-limit results require both failure flags")
            if self.timed_out:
                raise ValueError("output-limit results cannot be timed out")
        elif self.error_code == "CHECK_ISOLATION_VIOLATION":
            if self.timed_out or self.output_limit_exceeded or self.container_stopped:
                raise ValueError("isolation violations are detected before start")
            if self.exit_code is not None:
                raise ValueError("isolation violations have no container exit code")
        elif self.error_code == "CHECK_EXECUTION_ERROR":
            if self.timed_out or self.output_limit_exceeded:
                raise ValueError("execution errors cannot be timeout/output-limited")
            if self.exit_code is not None:
                raise ValueError("execution errors have no container exit code")
        # An empty container id is legal only for a pre-create execution
        # error: no container was ever created, so there is nothing to
        # stop or remove.
        if self.container_id == "" and self.error_code != "CHECK_EXECUTION_ERROR":
            raise ValueError(
                "a container id is required for every non-execution-error result"
            )
        if self.output_bytes != len(self.stdout) + len(self.stderr):
            raise ValueError(
                "output_bytes must equal the exact raw stdout+stderr byte total"
            )
        return self


class _ReadableAttachSocketV1(Protocol):
    """The minimal raw socket surface the bounded collector needs.

    Linux attach streams surface as an ``http.client`` ``SocketIO`` with
    ``readinto`` instead of ``recv_into``; the collector prefers
    ``recv_into`` and falls back to ``readinto`` and then ``read``, so
    the protocol declares all three (each implementation supplies only
    the ones it has).
    """

    def settimeout(self, timeout: float) -> None: ...
    def recv_into(self, buffer: bytearray) -> int: ...
    def readinto(self, buffer: bytearray) -> int: ...
    def read(self, size: int = -1) -> bytes: ...


class _DockerContainerHandleV1(Protocol):
    """The exact-container handle surface used by the executor."""

    id: str
    attrs: dict[str, object]

    def start(self) -> None: ...
    def stop(self, timeout: float | None = None) -> None: ...
    def kill(self) -> None: ...
    def wait(self, timeout: float | None = None) -> dict[str, object]: ...
    def reload(self) -> None: ...
    def logs(
        self,
        *,
        stdout: bool = True,
        stderr: bool = True,
        stream: bool = False,
    ) -> bytes: ...


class _DockerContainersV1(Protocol):
    def create(self, **kwargs: object) -> _DockerContainerHandleV1: ...


class _DockerAPIClientV1(Protocol):
    """The low-level attach surface (the SDK's own attach composition)."""

    def _url(self, path: str, *args: object) -> str: ...
    def _post(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, object] | None = None,
        stream: bool = False,
    ) -> object: ...
    def _get_raw_response_socket(self, response: object) -> object: ...


class _DockerExecutionClientV1(Protocol):
    """The full client surface used by the executor (injectable fake)."""

    @property
    def api(self) -> _DockerAPIClientV1: ...
    @property
    def containers(self) -> _DockerContainersV1: ...


ClientFactoryV1: TypeAlias = Callable[[], _DockerExecutionClientV1]
"""The injectable client factory: the real SDK by default, scripted fakes
in the deterministic matrix tests."""


class _IsolationViolationError(RuntimeError):
    """One closed daemon-side isolation drift of the exact container."""


class _RunNotCompleted(RuntimeError):
    """The run did not complete within the bounded deadline.

    Raised when the exit code cannot be obtained inside the deadline
    (the attach stream closed but the process kept running, or the wait
    itself failed); the caller stops the exact container and reports the
    declared ``CHECK_TIMEOUT`` failure.
    """


class _BoundedStreamCollector:
    """Deadline-bounded collector over the docker attach stream.

    Reads the raw multiplexed attach stream (8-byte frame headers, then
    payloads) through ``recv_into`` with a per-read timeout so the
    deadline is always honored even when the stream is silent; splits
    stdout (stream 1) and stderr (stream 2) under ONE combined byte cap,
    so a single frame declared larger than the cap (or a frame whose
    addition would push the combined total beyond the cap) is an overflow
    that stops collection immediately without ever buffering beyond the
    bound (SPEC §1.4.5/§5.1: 单次检查输出最多 4 MiB — the aggregate raw
    output of one check, stdout + stderr).
    """

    def __init__(
        self,
        socket: _ReadableAttachSocketV1,
        max_output_bytes: int,
        deadline_monotonic: float,
    ) -> None:
        self._socket = socket
        self._max_output_bytes = max_output_bytes
        self._deadline = deadline_monotonic

    def collect(
        self,
    ) -> tuple[bytes, bytes, Literal["ok", "timeout", "overflow", "error"]]:
        pending = bytearray()
        stdout = bytearray()
        stderr = bytearray()
        while True:
            remaining = self._deadline - time.monotonic()
            if remaining <= 0:
                return bytes(stdout), bytes(stderr), "timeout"
            try:
                self._socket.settimeout(min(0.25, remaining))
            except AttributeError:
                # The docker SDK wraps the Linux attach stream in a
                # ``SocketIO`` that has no ``settimeout``; the stream
                # still ends at the container's EOF, so the bounded
                # deadline below remains the outer guard.
                pass
            buffer = bytearray(65536)
            try:
                if hasattr(self._socket, "recv_into"):
                    count = self._socket.recv_into(buffer)
                elif hasattr(self._socket, "readinto"):
                    # The Linux attach stream is an ``http.client``
                    # ``SocketIO`` (HTTPResponse) with ``readinto`` but no
                    # ``recv_into``; the caller handles the pending
                    # buffer the same way as ``recv_into``.
                    count = self._socket.readinto(buffer)
                else:
                    # A plain file-like stream (``read`` only): fold the
                    # bytes into the same pending buffer and fall through
                    # to the shared frame parsing below.
                    data = self._socket.read(65536)
                    count = len(data)
                    if count:
                        pending.extend(data)
            except TimeoutError:
                # The read timeout fired; the deadline check above decides.
                continue
            except Exception:
                # Any non-timeout read failure is a broken or truncated
                # stream, never a clean EOF: the collected evidence is
                # incomplete and must fail closed.
                return bytes(stdout), bytes(stderr), "error"
            if count == 0:
                break
            pending.extend(buffer[:count])
            while len(pending) >= _FRAME_HEADER.size:
                stream_id, size = _FRAME_HEADER.unpack_from(bytes(pending))
                if stream_id not in (1, 2):
                    # The multiplexed stream ids are stdout=1 and stderr=2;
                    # any other id is a corrupt stream.
                    return bytes(stdout), bytes(stderr), "error"
                if size > self._max_output_bytes:
                    return bytes(stdout), bytes(stderr), "overflow"
                if len(pending) < _FRAME_HEADER.size + size:
                    break
                payload = bytes(pending[_FRAME_HEADER.size : _FRAME_HEADER.size + size])
                del pending[: _FRAME_HEADER.size + size]
                target = stdout if stream_id == 1 else stderr
                if len(stdout) + len(stderr) + size > self._max_output_bytes:
                    return bytes(stdout), bytes(stderr), "overflow"
                target.extend(payload)
        if pending:
            # A trailing half frame is a truncated stream: the evidence is
            # incomplete and must never be treated as a clean end.
            return bytes(stdout), bytes(stderr), "error"
        return bytes(stdout), bytes(stderr), "ok"


class DockerExecutor:
    """One bounded real Docker executor over the frozen execution profile.

    ``execute`` creates one fresh container from the request's frozen
    built-in image digest and profile, re-verifies the daemon-side
    isolation configuration of that exact container, runs it with a
    bounded deadline and bounded stdout/stderr collectors, stops/kills the
    exact container on any deadline or output-limit violation, and
    returns only bounded ``RawExecutionResultV1`` raw evidence.  The
    client factory is injectable so every closed failure branch runs
    deterministically offline (GREEN-3 matrix); the default factory is
    the real docker SDK.
    """

    def __init__(
        self,
        timeout_seconds: float = _FROZEN_TIMEOUT_SECONDS,
        client_factory: ClientFactoryV1 | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._client_factory = client_factory

    def execute(
        self,
        request: ExecutionRequestV1,
        candidate: MaterializedCandidateV1,
    ) -> RawExecutionResultV1:
        deadline = time.monotonic() + self._timeout_seconds
        client = (
            self._default_client()
            if self._client_factory is None
            else self._client_factory()
        )
        container: _DockerContainerHandleV1 | None = None
        response: object | None = None
        try:
            container = self._create_container(client, request, candidate)
            self._verify_isolation_config(container, request, candidate)
            # The attach stream is opened BEFORE the container starts, so
            # every byte the container ever produces flows into the
            # collector (the daemon's backlog replay on later attach is
            # not deterministic on the npipe transport).
            response = self._open_attach_stream(client.api, container.id)
            socket = cast(
                _ReadableAttachSocketV1, client.api._get_raw_response_socket(response)
            )
            container.start()
            stdout, stderr, outcome = _BoundedStreamCollector(
                socket,
                request.profile.resources.max_output_bytes,
                deadline,
            ).collect()
            timed_out = outcome == "timeout"
            output_limit_exceeded = outcome == "overflow"
            stream_error = outcome == "error"
            if stream_error:
                # Windows npipe: an exited container closes the attach
                # socket with an OSError (WinError 109) even after every
                # byte was delivered, so a closed stream is not proof of
                # truncation.  When the container has already exited,
                # recover the authoritative output from the daemon logs
                # (no npipe) and keep the evidence complete; a still
                # running container or a logs failure stays fail-closed.
                recovered = self._recover_exited_output(
                    container, request.profile.resources.max_output_bytes
                )
                if recovered is not None:
                    recovered_stdout, recovered_stderr, exceeded = recovered
                    stdout = bytes(recovered_stdout)
                    stderr = bytes(recovered_stderr)
                    stream_error = False
                    output_limit_exceeded = exceeded
            container_stopped = False
            if timed_out or output_limit_exceeded or stream_error:
                self._stop_exact_container(container)
                container_stopped = True
            exit_code: int | None = None
            if not timed_out and not output_limit_exceeded and not stream_error:
                try:
                    exit_code = self._wait_exit_code(container, deadline)
                except _RunNotCompleted:
                    # The stream closed but the process never completed
                    # within the bound: stop the exact container and
                    # report the declared deadline failure.
                    self._stop_exact_container(container)
                    container_stopped = True
                    timed_out = True
            error_code: ExecutionErrorCodeV1 | None = (
                "CHECK_TIMEOUT"
                if timed_out
                else "CHECK_OUTPUT_LIMIT_EXCEEDED"
                if output_limit_exceeded
                else "CHECK_EXECUTION_ERROR"
                if stream_error
                else None
            )
            return RawExecutionResultV1(
                schema_version=1,
                request_id=request.request_id,
                container_id=container.id,
                exit_code=exit_code,
                stdout=bytes(stdout),
                stderr=bytes(stderr),
                output_bytes=len(stdout) + len(stderr),
                timed_out=timed_out,
                output_limit_exceeded=output_limit_exceeded,
                container_stopped=container_stopped,
                error_code=error_code,
            )
        except _IsolationViolationError:
            return RawExecutionResultV1(
                schema_version=1,
                request_id=request.request_id,
                container_id=container.id if container is not None else "",
                exit_code=None,
                stdout=b"",
                stderr=b"",
                output_bytes=0,
                timed_out=False,
                output_limit_exceeded=False,
                container_stopped=False,
                error_code="CHECK_ISOLATION_VIOLATION",
            )
        except Exception:
            if os.environ.get("VESPER_EXECUTOR_DIAG"):
                import traceback

                traceback.print_exc()
            stopped = False
            if container is not None:
                try:
                    self._stop_exact_container(container)
                    stopped = True
                except Exception:
                    stopped = False
            return RawExecutionResultV1(
                schema_version=1,
                request_id=request.request_id,
                container_id=container.id if container is not None else "",
                exit_code=None,
                stdout=b"",
                stderr=b"",
                output_bytes=0,
                timed_out=False,
                output_limit_exceeded=False,
                container_stopped=stopped,
                error_code="CHECK_EXECUTION_ERROR",
            )
        finally:
            if response is not None:
                try:
                    response.close()  # type: ignore[attr-defined]
                except Exception:
                    pass

    def _default_client(self) -> _DockerExecutionClientV1:
        try:
            import docker  # type: ignore[import-untyped]
        except Exception as exc:
            raise RuntimeError("the Docker SDK is not available") from exc
        return cast(_DockerExecutionClientV1, docker.from_env())

    def _create_container(
        self,
        client: _DockerExecutionClientV1,
        request: ExecutionRequestV1,
        candidate: MaterializedCandidateV1,
    ) -> _DockerContainerHandleV1:
        """One fresh container from the frozen image digest and profile."""
        profile = request.profile
        try:
            from docker.types import Mount  # type: ignore[import-untyped]
        except Exception as exc:
            raise RuntimeError("the Docker SDK is not available") from exc
        mount = Mount(
            target="/workspace",
            source=candidate.root_path.replace("\\", "/"),
            type="bind",
            read_only=True,
        )
        return client.containers.create(
            image=request.docker_image_digest,
            command=list(request.argv.arguments),
            user=profile.user,
            network_mode=profile.network_mode,
            read_only=profile.read_only_rootfs,
            cap_drop=[profile.capabilities_dropped],
            tmpfs={profile.tmpfs_mount.path: _FROZEN_TMPFS_OPTIONS},
            nano_cpus=profile.resources.cpus * 1_000_000_000,
            mem_limit=profile.resources.memory_bytes,
            pids_limit=profile.resources.pids_limit,
            working_dir=profile.workdir,
            environment=[
                f"{variable.name}={variable.value}"
                for variable in profile.environment.variables
            ],
            mounts=[mount],
            detach=True,
            name=f"vespercode-check-{uuid.uuid4().hex}",
        )

    def _verify_isolation_config(
        self,
        container: _DockerContainerHandleV1,
        request: ExecutionRequestV1,
        candidate: MaterializedCandidateV1,
    ) -> None:
        """Re-verify the daemon-side isolation configuration of the exact
        container against the frozen profile before it starts.

        Any missing or drifted control — network mode, non-root user,
        read-only rootfs, capability drop, tmpfs, CPU/memory/PID limits,
        the exact read-only /workspace bind, an absent Docker socket, the
        workdir, the frozen environment, or the frozen image identity —
        fails closed with ``CHECK_ISOLATION_VIOLATION`` before the
        container can start; the in-container enforcement of the same
        controls is proven by the isolation integration test (T02.3
        pattern).
        """
        profile = request.profile
        container.reload()
        attrs = container.attrs
        host_config = attrs.get("HostConfig") or {}
        config = attrs.get("Config") or {}
        if not isinstance(host_config, dict) or not isinstance(config, dict):
            raise _IsolationViolationError("container inspect is malformed")
        if host_config.get("NetworkMode") != profile.network_mode:
            raise _IsolationViolationError("network_mode drift")
        if host_config.get("ReadonlyRootfs") is not profile.read_only_rootfs:
            raise _IsolationViolationError("read-only rootfs drift")
        if host_config.get("CapDrop") != [profile.capabilities_dropped]:
            raise _IsolationViolationError("capability drop drift")
        if host_config.get("Tmpfs") != {
            profile.tmpfs_mount.path: _FROZEN_TMPFS_OPTIONS
        }:
            raise _IsolationViolationError("tmpfs drift")
        if host_config.get("NanoCpus") != profile.resources.cpus * 1_000_000_000:
            raise _IsolationViolationError("cpu limit drift")
        if host_config.get("Memory") != profile.resources.memory_bytes:
            raise _IsolationViolationError("memory limit drift")
        if host_config.get("PidsLimit") != profile.resources.pids_limit:
            raise _IsolationViolationError("pid limit drift")
        if config.get("User") != profile.user:
            raise _IsolationViolationError("user drift")
        if config.get("WorkingDir") != profile.workdir:
            raise _IsolationViolationError("workdir drift")
        observed_image = str(attrs.get("Image") or "").removeprefix("sha256:")
        if observed_image != request.docker_image_digest:
            raise _IsolationViolationError("image identity drift")
        environment = config.get("Env")
        if not isinstance(environment, list):
            raise _IsolationViolationError("environment drift")
        frozen_pairs = {
            (variable.name, variable.value)
            for variable in profile.environment.variables
        }
        observed_pairs = {tuple(str(entry).split("=", 1)) for entry in environment}
        if not frozen_pairs.issubset(observed_pairs):
            raise _IsolationViolationError("environment whitelist drift")
        mounts = host_config.get("Mounts")
        if not isinstance(mounts, list):
            raise _IsolationViolationError("mount set drift")
        for other in mounts:
            if "docker.sock" in str(other).lower():
                raise _IsolationViolationError("docker socket mount")
        # The check runs on the created-but-not-started container; on the
        # frozen daemon the inspect at this state reports exactly the one
        # read-only /workspace bind (the network /etc/hosts binds are
        # injected only at start).  A daemon that merged extra binds at
        # create time would fail closed here — the safe direction.
        if len(mounts) != 1:
            raise _IsolationViolationError("mount set drift")
        mount = mounts[0]
        if not isinstance(mount, dict):
            raise _IsolationViolationError("mount set drift")
        if mount.get("Type") != "bind" or mount.get("Target") != "/workspace":
            raise _IsolationViolationError("workspace mount drift")
        if mount.get("ReadOnly") is not True:
            raise _IsolationViolationError("writable workspace mount")
        observed_source = str(mount.get("Source") or "").replace("\\", "/").lower()
        expected_source = candidate.root_path.replace("\\", "/").lower()
        if observed_source != expected_source:
            raise _IsolationViolationError("workspace mount source drift")

    def _recover_exited_output(
        self,
        container: _DockerContainerHandleV1,
        max_output_bytes: int,
    ) -> tuple[bytearray, bytearray, bool] | None:
        """Authoritative daemon logs for an already-exited container.

        Returns ``(stdout, stderr, exceeded)`` when the container has a
        concrete exit code and the daemon logs are readable, else None.
        The logs are the demuxed raw bytes (no frame headers) split per
        stream; ``exceeded`` reports the aggregate byte cap so the
        overflow fail-closed code is preserved for over-limit output.
        """
        try:
            container.reload()
            raw_state = container.attrs.get("State")
            state = raw_state if isinstance(raw_state, dict) else {}
            if state.get("Running") is not False or state.get("ExitCode") is None:
                return None
            out = bytearray(container.logs(stdout=True, stderr=False, stream=False))
            err = bytearray(container.logs(stdout=False, stderr=True, stream=False))
        except Exception:
            return None
        return out, err, len(out) + len(err) > max_output_bytes

    def _open_attach_stream(self, api: _DockerAPIClientV1, container_id: str) -> object:
        """Open the live multiplexed attach stream of the exact container.

        The composition mirrors the SDK's own ``attach`` implementation
        (the npipe transport cannot honor deadlines through the blocking
        iterator, so the raw response socket is read directly with
        per-read timeouts).  The executor calls this BEFORE the container
        starts, so no backlog replay is ever relied upon.
        """
        url = api._url("/containers/{0}/attach", container_id)
        return api._post(
            url,
            headers={"Connection": "Upgrade", "Upgrade": "tcp"},
            params={"logs": 1, "stdout": 1, "stderr": 1, "stream": 1},
            stream=True,
        )

    def _stop_exact_container(self, container: _DockerContainerHandleV1) -> None:
        """Stop the exact container and verify it is not running.

        ``stop(timeout=0)`` sends SIGTERM with immediate SIGKILL
        escalation; if the container is still observed running, it is
        killed by its exact id.  A state that cannot be proven stopped
        raises, so an unproven stop is never reported as success.
        """
        try:
            container.stop(timeout=0)
        except Exception:
            # Already stopped or absent; the state verification decides.
            pass
        container.reload()
        state = container.attrs.get("State") or {}
        if not isinstance(state, dict) or state.get("Running") is not False:
            container.kill()
            container.reload()
            state = container.attrs.get("State") or {}
        if not isinstance(state, dict) or state.get("Running") is not False:
            raise RuntimeError(
                f"container {container.id} still running after stop/kill"
            )

    def _wait_exit_code(
        self, container: _DockerContainerHandleV1, deadline: float
    ) -> int:
        """The exact container exit code, bounded by the remaining deadline.

        The wait is capped at the smaller of the 30 s safety window and
        the remaining deadline, so the total wall time of one execution
        can never exceed the frozen per-check bound; a wait that cannot
        complete inside the deadline raises ``_RunNotCompleted``.
        """
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _RunNotCompleted()
        try:
            result = container.wait(timeout=min(30, remaining))
        except Exception as exc:
            raise _RunNotCompleted() from exc
        code = result.get("StatusCode")
        if not isinstance(code, int) or isinstance(code, bool):
            raise _RunNotCompleted()
        return code
