"""Route B / B4a: the optional read-only Docker readiness probe.

``SubprocessDockerProbeV2`` is the clearly separated, optional real
Docker boundary of the B4a slice: it is a READ-ONLY readiness probe
that asks the local daemon whether the profile's opaque image token is
present (``docker image inspect``) and, when that fails, whether the
daemon is reachable at all (``docker info``).  It never creates, runs,
or execs a container, never pulls or pushes, never opens the docker
socket itself, never parses digests out of the inspect output (there is
no v2 digest authorization), and never places any inspect output in
its closed result — the readiness record carries a status and a closed
reason only.

The command runner is injectable, so every probe decision is covered
by deterministic offline tests; the real ``subprocess`` edge is never
exercised by the v2 unit job (the default runner exists for an
opt-in, operator-driven probe only).
"""

from __future__ import annotations

import unittest

from vespercode.execution.v2_docker_probe import (
    DOCKER_PROBE_TIMEOUT_SECONDS_V2,
    ProbeCommandResultV2,
    SubprocessDockerProbeV2,
)
from vespercode.execution.v2_execution import (
    ExecutionReadinessResultV2,
)
from vespercode.execution.v2_profile import (
    EXECUTION_MAX_OUTPUT_BYTES_V2,
    ExecutionProfileRecordV2,
)


class _ScriptedRunner:
    """Deterministic injectable command runner for the offline tests."""

    def __init__(self, outcomes: list[object]) -> None:
        self.calls: list[list[str]] = []
        self._outcomes = list(outcomes)

    def __call__(self, argv: object) -> ProbeCommandResultV2:
        assert isinstance(argv, list)
        self.calls.append(list(argv))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, ProbeCommandResultV2)
        return outcome


def _profile() -> ExecutionProfileRecordV2:
    return ExecutionProfileRecordV2(
        execution_profile_id="exec-profile-1",
        execution_profile_revision=4,
        reference_profile_id="reference-1",
        reference_profile_revision=3,
        image_reference="vespercode-validation-image",
        network_disabled=True,
        non_root_user="10001:10001",
        read_only_rootfs=True,
        all_capabilities_dropped=True,
        docker_socket_mounted=False,
        workspace_mount_read_only=True,
        timeout_seconds=120,
        max_output_bytes=EXECUTION_MAX_OUTPUT_BYTES_V2,
    )


class SubprocessDockerProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = _profile()
        self.probe = SubprocessDockerProbeV2()

    def test_a_present_local_image_reports_ready(self) -> None:
        runner = _ScriptedRunner(
            [ProbeCommandResultV2(0, "sha256:cf0b6c5c... inspect output")]
        )
        probe = SubprocessDockerProbeV2(runner)
        result = probe.check(self.profile)
        self.assertIsInstance(result, ExecutionReadinessResultV2)
        self.assertEqual(result.status, "READY")
        self.assertIsNone(result.reason)
        self.assertEqual(len(runner.calls), 1)

    def test_the_probe_argv_is_exactly_the_closed_inspect_command(self) -> None:
        runner = _ScriptedRunner([ProbeCommandResultV2(0, "")])
        probe = SubprocessDockerProbeV2(runner)
        probe.check(self.profile)
        self.assertEqual(
            runner.calls,
            [["docker", "image", "inspect", "vespercode-validation-image"]],
        )
        # The runner receives a closed list of plain tokens — never a
        # shell command string.
        for call in runner.calls:
            self.assertIsInstance(call, list)
            for token in call:
                self.assertIsInstance(token, str)

    def test_a_missing_image_reports_image_not_available(self) -> None:
        runner = _ScriptedRunner(
            [ProbeCommandResultV2(1, ""), ProbeCommandResultV2(0, "...")]
        )
        probe = SubprocessDockerProbeV2(runner)
        result = probe.check(self.profile)
        self.assertEqual(result.status, "NOT_READY")
        self.assertEqual(result.reason, "IMAGE_NOT_AVAILABLE")
        self.assertEqual(len(runner.calls), 2)
        self.assertEqual(runner.calls[1], ["docker", "info"])

    def test_an_unreachable_daemon_reports_daemon_unavailable(self) -> None:
        # inspect fails and the daemon probe also fails.
        runner = _ScriptedRunner(
            [ProbeCommandResultV2(1, ""), ProbeCommandResultV2(1, "")]
        )
        probe = SubprocessDockerProbeV2(runner)
        result = probe.check(self.profile)
        self.assertEqual(result.status, "NOT_READY")
        self.assertEqual(result.reason, "DAEMON_UNAVAILABLE")
        # The command runner itself fails (no docker executable,
        # timeout, or any other transport error).
        for error in (
            FileNotFoundError("docker"),
            OSError("cannot connect to the daemon"),
            TimeoutError("probe timed out"),
        ):
            with self.subTest(error=type(error).__name__):
                failing = _ScriptedRunner([error])
                probe = SubprocessDockerProbeV2(failing)
                result = probe.check(self.profile)
                self.assertEqual(result.status, "NOT_READY")
                self.assertEqual(result.reason, "DAEMON_UNAVAILABLE")

    def test_the_probe_result_carries_no_inspect_output_or_digest(self) -> None:
        hostile = (
            "Id: sha256:cf0b6c5ccac588fccd07c3b9f050bff4daf550ac6e518fd"
            "06efb6e988ab1d823\nRepoDigests: [docker.io/x@sha256:d0700f]"
        )
        runner = _ScriptedRunner([ProbeCommandResultV2(0, hostile)])
        probe = SubprocessDockerProbeV2(runner)
        result = probe.check(self.profile)
        self.assertEqual(result.status, "READY")
        # The readiness record has exactly two fields — status and
        # reason — so no inspect output, digest, or image detail can
        # ever enter the control plane through readiness.
        self.assertEqual((result.status, result.reason), ("READY", None))
        self.assertNotIn("sha256", repr(result))

    def test_the_probe_never_issues_container_or_registry_commands(self) -> None:
        closed_verbs = {"image", "info"}
        scenarios = [
            [ProbeCommandResultV2(0, "")],
            [ProbeCommandResultV2(1, ""), ProbeCommandResultV2(0, "")],
            [ProbeCommandResultV2(1, ""), ProbeCommandResultV2(1, "")],
        ]
        for outcomes in scenarios:
            with self.subTest(outcomes=outcomes):
                runner = _ScriptedRunner(outcomes)
                probe = SubprocessDockerProbeV2(runner)
                probe.check(self.profile)
                for call in runner.calls:
                    self.assertEqual(call[0], "docker")
                    self.assertIn(call[1], closed_verbs)
                    for forbidden in (
                        "run",
                        "create",
                        "exec",
                        "pull",
                        "push",
                        "build",
                        "login",
                        "-H",
                        "--host",
                    ):
                        self.assertNotIn(forbidden, call)

    def test_the_probe_requires_a_validated_profile_record(self) -> None:
        for bad in ("nope", None, 3, {"image_reference": "img"}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.probe.check(bad)

    def test_the_probe_timeout_is_bounded(self) -> None:
        self.assertIsInstance(DOCKER_PROBE_TIMEOUT_SECONDS_V2, int)
        self.assertGreaterEqual(DOCKER_PROBE_TIMEOUT_SECONDS_V2, 1)
        self.assertLessEqual(DOCKER_PROBE_TIMEOUT_SECONDS_V2, 60)


if __name__ == "__main__":
    unittest.main()
