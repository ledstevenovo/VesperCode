"""Route B / B4b-01: the optional real container execution adapter.

``SubprocessDockerExecutorV2`` implements ``V2ExecutionPort`` — the
clearly separated, opt-in real-Docker boundary of the B4b-01 slice.
It drives the operator's docker CLI through ONE closed command
sequence per run and through nothing else:

1. ``docker create --pull never ...`` — one fresh container from the
   profile's opaque local image token with the closed isolation flag
   set: network ``none``, the profile's non-root uid:gid, a read-only
   root filesystem, ``--cap-drop ALL``, frozen memory/memory-swap/
   pids/cpu bounds (the v2 profile record represents only timeout and
   output bounds, so the adapter freezes the rest), a bounded ``/tmp``
   tmpfs, and exactly one READ-ONLY bind of the operator-configured
   workspace directory at ``/workspace``.  No host string, no
   environment, no entrypoint override, no volume/``-v`` flag, no
   docker socket, no registry credential flag exists anywhere in the
   argv, and ``--pull never`` makes the no-pull rule structural: an
   absent image is a fail-closed create error, never a fetch.
2. ``docker inspect <container>`` — the daemon-side configuration of
   that exact created container is re-verified BEFORE it starts
   (network mode, read-only rootfs, cap drop, privileged, memory/
   swap/cpu/pids limits, tmpfs, non-root user, image reference, the
   exact command, and the exact read-only workspace bind); ANY drift
   fails closed and nothing runs.  The inspect report is read for the
   drift decision only — no digest is parsed and no image detail ever
   enters a v2 record.
3. ``docker start --attach <container>`` — the single attached run,
   bounded by the profile's ``timeout_seconds`` (one monotonic
   deadline covers create, inspect, and start; a pre-start phase
   that consumes the budget fails closed as an infrastructure
   failure, only an attached run that exceeds it reports ``TIMED_OUT``)
   and collecting stdout+stderr under the profile's byte cap; an
   output overflow fails closed (the run is stopped, never silently
   truncated to a success).
4. On timeout: ``docker stop --time 0 <container>`` stops the exact
   container (the CLI attach process is killed by the runner first).
5. Always, after every create that succeeded: ``docker rm --force
   <container>`` — the deterministic cleanup that leaves no container
   behind, best-effort bounded and never able to change the already
   determined execution result.

The container name is a per-run ``vespercode-exec-<uuid>`` token —
an internal transport handle that never enters a result.  The command
runner is injectable: the offline unit suite proves every decision
(create argv, drift rejection, timeout/overflow mapping, nonzero and
exception mapping, cleanup discipline, and that the B4a binding/
readiness gates make no call at all) with a scripted fake, and the
default ``subprocess`` edge (``shell=False``, closed argv, bounded
wait, bounded collection) exists only for opt-in operator-driven
execution behind the B4a service.  Every phase failure — runner
exception, hostile runner return, timed-out create/inspect, budget
exhaustion — maps to the closed ``FAILED`` result with empty output:
no CLI/daemon error text, no raw command, and no secret can enter
``ExecutionResultV2`` (the service then sanitizes even that into the
caller-facing outcome).  No retry exists anywhere in the adapter.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from vespercode.execution.v2_execution import (
    ExecutionActionRequestV2,
    ExecutionResultV2,
)
from vespercode.execution.v2_profile import ExecutionProfileRecordV2

EXECUTOR_CLEANUP_TIMEOUT_SECONDS_V2 = 30
"""The frozen bound of one cleanup/stop command (bounded hygiene after
the execution deadline has already been decided)."""

EXECUTOR_CPU_LIMIT_V2 = 2
"""The frozen CPU ceiling of one v2 execution container (the profile
record does not represent a cpu bound; the adapter freezes it)."""

EXECUTOR_MEMORY_LIMIT_BYTES_V2 = 2 * 1024 * 1024 * 1024
"""The frozen memory ceiling of one v2 execution container, with swap
bounded to the same value (no swap)."""

EXECUTOR_PIDS_LIMIT_V2 = 256
"""The frozen process-id ceiling of one v2 execution container."""

EXECUTOR_TMPFS_MOUNT_V2 = "/tmp:rw,size=256m"
"""The frozen bounded writable /tmp of one v2 execution container (a
read-only root filesystem still needs a small scratch area)."""

_CONTAINER_NAME_PREFIX = "vespercode-exec-"

_CREATE_COMMAND = ("docker", "create", "--pull", "never")
_INSPECT_COMMAND = ("docker", "inspect")
_START_COMMAND = ("docker", "start", "--attach")
_STOP_COMMAND = ("docker", "stop", "--time", "0")
_REMOVE_COMMAND = ("docker", "rm", "--force")


def _tmpfs_inspect_spec() -> dict[str, str]:
    """The daemon-side Tmpfs spelling of the frozen tmpfs flag."""
    path, _, options = EXECUTOR_TMPFS_MOUNT_V2.partition(":")
    return {path: options}


@dataclass(frozen=True, slots=True)
class ExecutorCommandOutcomeV2:
    """One closed outcome of a single docker CLI command.

    ``returncode`` is ``None`` exactly when the command timed out;
    ``stdout``/``stderr`` are the exact bounded raw bytes the runner
    collected (the runner enforces the caller's byte cap; the adapter
    re-verifies); ``output_truncated`` reports that the cap stopped
    collection.  The probe/executor runners discard or bound command
    output — the drift decision, the exit decision, and the bounded
    container output are the only consumers.
    """

    returncode: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    output_truncated: bool

    def __post_init__(self) -> None:
        if self.timed_out:
            if self.returncode is not None:
                raise ValueError("a timed-out command carries no returncode")
        elif isinstance(self.returncode, bool) or not isinstance(
            self.returncode, int
        ):
            raise ValueError("returncode must be None or an integer")
        if not self.timed_out and not -255 <= self.returncode <= 255:
            raise ValueError("returncode is out of the bounded range")
        if not isinstance(self.stdout, bytes):
            raise ValueError("stdout must be exact raw bytes")
        if not isinstance(self.stderr, bytes):
            raise ValueError("stderr must be exact raw bytes")
        if not isinstance(self.timed_out, bool):
            raise ValueError("timed_out must be a boolean")
        if not isinstance(self.output_truncated, bool):
            raise ValueError("output_truncated must be a boolean")


def _kill(process: subprocess.Popen[bytes]) -> None:
    """Kill the exact CLI process; a concurrently dead one is fine."""
    try:
        process.kill()
    except Exception:
        pass


def _default_command_runner(
    argv: Sequence[str],
    *,
    timeout_seconds: float,
    max_output_bytes: int,
) -> ExecutorCommandOutcomeV2:
    """The real subprocess edge: closed argv, no shell, bounded wait.

    Two reader threads drain stdout and stderr under ONE shared byte
    budget (the combined raw output of the command); a reader that
    observes the budget exhausted stops collecting, flags the
    truncation, and kills the process so an overflowing writer cannot
    stall past its own deadline.  The wall clock is bounded by
    ``timeout_seconds``: on expiry the CLI process is killed, the
    outcome reports ``timed_out``, and whatever was collected so far
    is returned bounded.  No output beyond the cap is ever buffered,
    and no error text is ever fabricated.
    """
    process = subprocess.Popen(  # noqa: S603 - closed literal argv, shell=False
        list(argv),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    )
    lock = threading.Lock()
    budget = [max_output_bytes]
    truncated = [False]

    def _collect(stream: IO[bytes] | None) -> bytes:
        assert stream is not None
        chunks: list[bytes] = []
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            with lock:
                if budget[0] <= 0:
                    # The cap is exhausted: stop collecting and stop
                    # the writer (fail-closed overflow, v1 heritage).
                    truncated[0] = True
                    break
                if len(chunk) > budget[0]:
                    chunks.append(chunk[: budget[0]])
                    budget[0] = 0
                    truncated[0] = True
                    break
                budget[0] -= len(chunk)
                chunks.append(chunk)
        if truncated[0]:
            _kill(process)
        return b"".join(chunks)

    stdout_box: list[bytes] = []
    stderr_box: list[bytes] = []
    readers = [
        threading.Thread(
            target=lambda box, stream: box.append(_collect(stream)),
            args=(stdout_box, process.stdout),
            daemon=True,
        ),
        threading.Thread(
            target=lambda box, stream: box.append(_collect(stream)),
            args=(stderr_box, process.stderr),
            daemon=True,
        ),
    ]
    for reader in readers:
        reader.start()
    timed_out = False
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill(process)
        try:
            process.wait(timeout=EXECUTOR_CLEANUP_TIMEOUT_SECONDS_V2)
        except subprocess.TimeoutExpired:
            pass
    for reader in readers:
        reader.join(timeout=EXECUTOR_CLEANUP_TIMEOUT_SECONDS_V2)
    for stream in (process.stdout, process.stderr):
        try:
            stream.close()  # type: ignore[union-attr]
        except Exception:
            pass
    return ExecutorCommandOutcomeV2(
        returncode=None if timed_out else process.returncode,
        stdout=stdout_box[0] if stdout_box else b"",
        stderr=stderr_box[0] if stderr_box else b"",
        timed_out=timed_out,
        output_truncated=truncated[0],
    )


def _failed(output: str) -> ExecutionResultV2:
    """One closed fail-fast result; no retry is ever attempted."""
    return ExecutionResultV2(status="FAILED", exit_code=None, output=output)


CommandRunnerV2 = Callable[..., ExecutorCommandOutcomeV2]
"""The injectable command runner: called with the closed argv and the
bounded ``timeout_seconds``/``max_output_bytes`` of one docker command;
the deterministic offline tests inject a scripted fake."""


class SubprocessDockerExecutorV2:
    """The optional real container execution adapter (V2ExecutionPort).

    ``workspace_source`` is the operator-provided absolute directory
    that is bind-mounted READ-ONLY at ``/workspace`` of every run — it
    is adapter configuration, never a request or profile field, so no
    caller can steer the mount.  ``runner`` is the injectable command
    runner; the default is the real bounded subprocess edge, which
    exists only for opt-in operator-driven execution behind the B4a
    binding/readiness gates and is never exercised by the v2 unit job.
    """

    def __init__(
        self,
        workspace_source: object,
        runner: CommandRunnerV2 | None = None,
    ) -> None:
        if not isinstance(workspace_source, (str, os.PathLike)):
            raise ValueError("workspace_source must be a path")
        path = Path(workspace_source)
        if not path.is_absolute():
            raise ValueError("workspace_source must be an absolute directory")
        if not path.is_dir():
            raise ValueError("workspace_source must be an existing directory")
        normalized = path.as_posix()
        if "," in normalized:
            raise ValueError(
                "workspace_source must not contain a comma (the docker "
                "--mount value is comma-delimited)"
            )
        self._workspace_source = normalized
        self._runner = runner if runner is not None else _default_command_runner

    def run(
        self, request: object, profile: object
    ) -> ExecutionResultV2:
        """Run exactly one closed execution request; fail closed always."""
        if not isinstance(request, ExecutionActionRequestV2):
            raise ValueError(
                "request must be an ExecutionActionRequestV2; a shell "
                "command string is never accepted"
            )
        if not isinstance(profile, ExecutionProfileRecordV2):
            raise ValueError("profile must be an ExecutionProfileRecordV2")
        deadline = time.monotonic() + profile.timeout_seconds
        cap = profile.max_output_bytes
        container = f"{_CONTAINER_NAME_PREFIX}{uuid.uuid4().hex}"
        created = False
        try:
            created_outcome = self._invoke(
                self._create_argv(container, request, profile), deadline, cap
            )
            if (
                created_outcome is None
                or created_outcome.timed_out
                or created_outcome.returncode != 0
            ):
                # The container was not created (or cannot be proven to
                # be): a closed failure with no CLI/daemon error text.
                return _failed("")
            created = True
            inspected_outcome = self._invoke(
                [*_INSPECT_COMMAND, container], deadline, cap
            )
            if (
                inspected_outcome is None
                or inspected_outcome.timed_out
                or inspected_outcome.returncode != 0
            ):
                return _failed("")
            if self._daemon_drift(inspected_outcome.stdout, request, profile):
                # The daemon-side configuration of the exact container
                # drifted from the closed flag set: nothing runs.
                return _failed("")
            started_outcome = self._invoke(
                [*_START_COMMAND, container], deadline, cap
            )
            if started_outcome is None:
                return _failed("")
            output = self._bounded_output(started_outcome, cap)
            overflowed = (
                started_outcome.output_truncated
                or len(started_outcome.stdout) + len(started_outcome.stderr)
                > cap
            )
            if started_outcome.timed_out:
                self._stop_container(container, cap)
                return ExecutionResultV2(
                    status="TIMED_OUT", exit_code=None, output=output
                )
            if overflowed:
                # The output limit is a fail-closed bound, never a
                # silent truncation of an otherwise accepted run.
                return _failed(output)
            code = started_outcome.returncode
            if code == 0:
                return ExecutionResultV2(
                    status="SUCCEEDED", exit_code=0, output=output
                )
            if code is None or not 0 <= code <= 255:
                return _failed(output)
            return ExecutionResultV2(
                status="FAILED", exit_code=code, output=output
            )
        except Exception:
            # Any runner/transport/contract failure is a closed failure;
            # the raw exception text never enters the result.
            return _failed("")
        finally:
            if created:
                self._remove_container(container, cap)

    def _create_argv(
        self,
        container: str,
        request: ExecutionActionRequestV2,
        profile: ExecutionProfileRecordV2,
    ) -> list[str]:
        """The closed create argv: isolation flags + frozen bounds."""
        return [
            *_CREATE_COMMAND,
            "--name",
            container,
            "--network",
            "none",
            "--user",
            profile.non_root_user,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--memory",
            str(EXECUTOR_MEMORY_LIMIT_BYTES_V2),
            "--memory-swap",
            str(EXECUTOR_MEMORY_LIMIT_BYTES_V2),
            "--pids-limit",
            str(EXECUTOR_PIDS_LIMIT_V2),
            "--cpus",
            str(EXECUTOR_CPU_LIMIT_V2),
            "--tmpfs",
            EXECUTOR_TMPFS_MOUNT_V2,
            "--mount",
            f"type=bind,source={self._workspace_source}"
            ",target=/workspace,readonly",
            profile.image_reference,
            *request.argv,
        ]

    def _invoke(
        self,
        argv: Sequence[str],
        deadline: float,
        max_output_bytes: int,
    ) -> ExecutorCommandOutcomeV2 | None:
        """One bounded runner call inside the remaining time budget."""
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        outcome = self._runner(
            list(argv),
            timeout_seconds=remaining,
            max_output_bytes=max_output_bytes,
        )
        if not isinstance(outcome, ExecutorCommandOutcomeV2):
            raise ValueError(
                "the command runner must return an ExecutorCommandOutcomeV2"
            )
        return outcome

    def _invoke_cleanup(
        self, argv: Sequence[str], max_output_bytes: int
    ) -> None:
        """One bounded hygiene command outside the execution deadline."""
        outcome = self._runner(
            list(argv),
            timeout_seconds=EXECUTOR_CLEANUP_TIMEOUT_SECONDS_V2,
            max_output_bytes=max_output_bytes,
        )
        if not isinstance(outcome, ExecutorCommandOutcomeV2):
            raise ValueError(
                "the command runner must return an ExecutorCommandOutcomeV2"
            )

    @staticmethod
    def _bounded_output(
        outcome: ExecutorCommandOutcomeV2, cap: int
    ) -> str:
        """The bounded decoded stdout+stderr of the attached run."""
        combined = outcome.stdout + outcome.stderr
        if len(combined) > cap:
            combined = combined[:cap]
        return combined.decode("utf-8", errors="replace")

    def _daemon_drift(
        self,
        inspect_stdout: bytes,
        request: ExecutionActionRequestV2,
        profile: ExecutionProfileRecordV2,
    ) -> str | None:
        """Re-verify the daemon-side configuration of the exact
        container before it starts.

        Returns the closed drift reason, or ``None`` when the daemon
        reports exactly the configuration this adapter requested.  The
        report is consumed for this decision only — no digest is read
        and no image detail is retained anywhere.
        """
        try:
            report = json.loads(inspect_stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return "the daemon inspect report is not readable"
        if (
            not isinstance(report, list)
            or len(report) != 1
            or not isinstance(report[0], dict)
        ):
            return "the daemon inspect report is malformed"
        entry = report[0]
        host = entry.get("HostConfig")
        config = entry.get("Config")
        if not isinstance(host, dict) or not isinstance(config, dict):
            return "the daemon inspect report is malformed"
        if host.get("NetworkMode") != "none":
            return "network mode drift"
        if host.get("ReadonlyRootfs") is not True:
            return "read-only root filesystem drift"
        if host.get("CapDrop") != ["ALL"]:
            return "capability drop drift"
        if host.get("Privileged") is not False:
            return "privileged mode drift"
        if host.get("Memory") != EXECUTOR_MEMORY_LIMIT_BYTES_V2:
            return "memory limit drift"
        if host.get("MemorySwap") != EXECUTOR_MEMORY_LIMIT_BYTES_V2:
            return "swap limit drift"
        if host.get("NanoCpus") != EXECUTOR_CPU_LIMIT_V2 * 1_000_000_000:
            return "cpu limit drift"
        if host.get("PidsLimit") != EXECUTOR_PIDS_LIMIT_V2:
            return "pids limit drift"
        if host.get("Tmpfs") != _tmpfs_inspect_spec():
            return "tmpfs drift"
        if config.get("User") != profile.non_root_user:
            return "non-root user drift"
        if config.get("Image") != profile.image_reference:
            return "image reference drift"
        if config.get("Cmd") != list(request.argv):
            return "command drift"
        mounts = host.get("Mounts")
        if not isinstance(mounts, list) or len(mounts) != 1:
            return "mount set drift"
        mount = mounts[0]
        if not isinstance(mount, dict):
            return "mount set drift"
        for spelling in (
            str(mount.get("Source") or ""),
            str(mount.get("Target") or ""),
        ):
            if "docker.sock" in spelling.lower():
                return "docker socket mount"
        if mount.get("Type") != "bind" or mount.get("Target") != "/workspace":
            return "workspace mount drift"
        if mount.get("ReadOnly") is not True:
            return "workspace mount drift"
        observed = str(mount.get("Source") or "").replace("\\", "/").lower()
        expected = self._workspace_source.lower()
        if observed != expected:
            return "workspace mount source drift"
        return None

    def _stop_container(self, container: str, cap: int) -> None:
        """Stop the exact container after a timeout; best effort."""
        try:
            self._invoke_cleanup([*_STOP_COMMAND, container], cap)
        except Exception:
            pass

    def _remove_container(self, container: str, cap: int) -> None:
        """Remove the exact container; bounded, best-effort hygiene.

        A failed removal never changes the already determined result
        (the closed result cannot carry cleanup status); the offline
        tests prove the removal is always issued after every create
        that succeeded.
        """
        try:
            self._invoke_cleanup([*_REMOVE_COMMAND, container], cap)
        except Exception:
            pass


__all__ = (
    "EXECUTOR_CLEANUP_TIMEOUT_SECONDS_V2",
    "EXECUTOR_CPU_LIMIT_V2",
    "EXECUTOR_MEMORY_LIMIT_BYTES_V2",
    "EXECUTOR_PIDS_LIMIT_V2",
    "EXECUTOR_TMPFS_MOUNT_V2",
    "ExecutorCommandOutcomeV2",
    "SubprocessDockerExecutorV2",
)
