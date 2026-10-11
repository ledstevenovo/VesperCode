"""Route B / B4a: an optional, clearly separated, read-only Docker
readiness probe.

This module is the single real-Docker boundary of the B4a slice, and
it is deliberately read-only: ``SubprocessDockerProbeV2`` implements
``V2ReadinessPort`` by asking the local daemon whether the profile's
opaque image token is present (``docker image inspect``) and, only
when that fails, whether the daemon is reachable at all
(``docker info``).  It never creates, runs, or execs a container,
never pulls or pushes, never opens the docker socket itself (the CLI
uses its own operator-provided channel), never passes a host string,
and never parses digests out of the inspect output — there is no v2
digest authorization, so the probe decision is the exit status alone
and no inspect stdout enters the closed readiness record, which
carries only a status and a closed reason.

The argv is a closed literal list plus the profile's charset-validated
opaque image token, executed with ``shell=False`` — there is no shell
string anywhere on this path, and the token charset excludes option,
path, and URL spellings by construction.  The command runner is
injectable, so every probe decision is covered by deterministic
offline tests; the default ``subprocess`` runner exists only for an
opt-in, operator-driven probe and is never exercised by the v2 unit
job.  A real container execution adapter remains B4b work behind the
same ports.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from vespercode.execution.v2_execution import ExecutionReadinessResultV2
from vespercode.execution.v2_profile import ExecutionProfileRecordV2

DOCKER_PROBE_TIMEOUT_SECONDS_V2 = 15
"""The bounded timeout of one probe command (never unbounded wait)."""

_INSPECT_COMMAND = ("docker", "image", "inspect")
_DAEMON_COMMAND = ("docker", "info")


@dataclass(frozen=True, slots=True)
class ProbeCommandResultV2:
    """One closed probe command outcome: an exit status and captured stdout.

    ``stdout`` exists for the runner contract only — the probe
    deliberately discards it, so no image detail or digest ever enters
    the control plane through readiness.
    """

    returncode: int
    stdout: str

    def __post_init__(self) -> None:
        if isinstance(self.returncode, bool) or not isinstance(self.returncode, int):
            raise ValueError("returncode must be an integer")
        if not -255 <= self.returncode <= 255:
            raise ValueError("returncode is out of the bounded range")
        if not isinstance(self.stdout, str):
            raise ValueError("stdout must be a string")


def _default_command_runner(argv: Sequence[str]) -> ProbeCommandResultV2:
    """The real subprocess edge: closed argv, no shell, bounded wait.

    Discards all command output — the probe decision is the exit
    status alone.
    """
    completed = subprocess.run(  # noqa: S603 - closed literal argv, shell=False
        list(argv),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=DOCKER_PROBE_TIMEOUT_SECONDS_V2,
        check=False,
        shell=False,
    )
    return ProbeCommandResultV2(returncode=completed.returncode, stdout="")


class SubprocessDockerProbeV2:
    """A read-only readiness probe over the operator's docker CLI.

    ``runner`` is injectable (the deterministic offline tests inject a
    fake); the default is the real bounded ``subprocess`` edge.
    """

    def __init__(
        self,
        runner: Callable[[Sequence[str]], ProbeCommandResultV2] | None = None,
    ) -> None:
        self._runner = runner if runner is not None else _default_command_runner

    def check(self, profile: object) -> ExecutionReadinessResultV2:
        """Answer whether the profile's execution image is locally ready."""
        if not isinstance(profile, ExecutionProfileRecordV2):
            raise ValueError("profile must be an ExecutionProfileRecordV2")
        inspect_argv = [*_INSPECT_COMMAND, profile.image_reference]
        try:
            outcome = self._runner(inspect_argv)
        except Exception:
            # No docker executable, daemon transport failure, timeout,
            # or any other error is fail-closed: not ready, and no raw
            # error text ever enters the closed result.
            return ExecutionReadinessResultV2("NOT_READY", "DAEMON_UNAVAILABLE")
        if not isinstance(outcome, ProbeCommandResultV2):
            raise ValueError(
                "the command runner must return a ProbeCommandResultV2"
            )
        if outcome.returncode == 0:
            return ExecutionReadinessResultV2("READY")
        # The image probe failed: distinguish a missing image from an
        # unreachable daemon with one more read-only command.
        try:
            daemon_outcome = self._runner(list(_DAEMON_COMMAND))
        except Exception:
            return ExecutionReadinessResultV2(
                "NOT_READY", "DAEMON_UNAVAILABLE"
            )
        if not isinstance(daemon_outcome, ProbeCommandResultV2):
            raise ValueError(
                "the command runner must return a ProbeCommandResultV2"
            )
        if daemon_outcome.returncode == 0:
            return ExecutionReadinessResultV2(
                "NOT_READY", "IMAGE_NOT_AVAILABLE"
            )
        return ExecutionReadinessResultV2("NOT_READY", "DAEMON_UNAVAILABLE")


__all__ = (
    "DOCKER_PROBE_TIMEOUT_SECONDS_V2",
    "ProbeCommandResultV2",
    "SubprocessDockerProbeV2",
)
