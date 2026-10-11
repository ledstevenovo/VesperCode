"""Route B / B4b-01: the optional real container execution adapter.

``SubprocessDockerExecutorV2`` is the clearly separated, opt-in real
Docker boundary of the B4b-01 slice: it implements ``V2ExecutionPort``
by driving the operator's docker CLI — one fresh container per run
(``docker create`` with the closed isolation flag set), a daemon-side
drift verification of that exact container BEFORE it starts
(``docker inspect``), one bounded attached run (``docker start
--attach``) whose stdout+stderr are collected under the profile's
byte cap and whose wall clock is bounded by the profile's timeout, an
exact-container stop on timeout (``docker stop --time 0``), and a
deterministic exact-container removal (``docker rm --force``) after
every create that succeeded.  It never pulls, pushes, or builds, never
passes a host string, never mounts the docker socket, never injects
environment or an entrypoint, and never accepts anything but the
closed structured request and profile records — the image reference is
the profile's opaque local token and the argv is the request's frozen
grammar projection.

The command runner is injectable, so every decision — the closed
argv of each command, the drift verification, the timeout and output
bounds, the nonzero/exception/overflow mappings, and the cleanup
discipline — is covered by deterministic offline tests.  The default
``subprocess`` edge exists only for opt-in, operator-driven execution
and is never exercised by the v2 unit job (the optional real-Docker
integration module and the B4a binding/readiness gates stay the only
paths through which a real execution can ever be reached).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vespercode.execution.v2_docker_executor import (
    EXECUTOR_CLEANUP_TIMEOUT_SECONDS_V2,
    EXECUTOR_CPU_LIMIT_V2,
    EXECUTOR_MEMORY_LIMIT_BYTES_V2,
    EXECUTOR_PIDS_LIMIT_V2,
    EXECUTOR_TMPFS_MOUNT_V2,
    ExecutorCommandOutcomeV2,
    SubprocessDockerExecutorV2,
)
from vespercode.execution.v2_execution import (
    ExecutionActionRequestV2,
    ExecutionReadinessResultV2,
    V2ExecutionPort,
)
from vespercode.execution.v2_executor import (
    FakeV2BindingLookup,
    FakeV2Readiness,
    V2ExecutionService,
)
from vespercode.execution.v2_profile import (
    EXECUTION_MAX_OUTPUT_BYTES_V2,
    ExecutionProfileRecordV2,
)


def _ok(
    returncode: int = 0,
    stdout: bytes = b"",
    stderr: bytes = b"",
    output_truncated: bool = False,
) -> ExecutorCommandOutcomeV2:
    return ExecutorCommandOutcomeV2(
        returncode, stdout, stderr, False, output_truncated
    )


def _timed_out(stdout: bytes = b"") -> ExecutorCommandOutcomeV2:
    return ExecutorCommandOutcomeV2(None, stdout, b"", True, False)


class _ScriptedRunner:
    """Deterministic injectable command runner for the offline tests.

    Records every ``(argv, timeout_seconds, max_output_bytes)`` triple
    it receives and answers with the scripted outcome, raising the
    scripted exception instead when the next entry is one.
    """

    def __init__(self, outcomes: list[object]) -> None:
        self.calls: list[tuple[list[str], float, int]] = []
        self._outcomes = list(outcomes)

    def __call__(
        self,
        argv: object,
        *,
        timeout_seconds: object,
        max_output_bytes: object,
    ) -> ExecutorCommandOutcomeV2:
        assert isinstance(argv, list)
        assert isinstance(timeout_seconds, (int, float))
        assert isinstance(max_output_bytes, int)
        self.calls.append(
            (list(argv), float(timeout_seconds), int(max_output_bytes))
        )
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, ExecutorCommandOutcomeV2)
        return outcome

    def argvs(self) -> list[list[str]]:
        return [call[0] for call in self.calls]


def _profile(**overrides: object) -> ExecutionProfileRecordV2:
    values: dict[str, object] = {
        "execution_profile_id": "exec-profile-1",
        "execution_profile_revision": 4,
        "reference_profile_id": "reference-1",
        "reference_profile_revision": 3,
        "image_reference": "vespercode-validation-image",
        "network_disabled": True,
        "non_root_user": "10001:10001",
        "read_only_rootfs": True,
        "all_capabilities_dropped": True,
        "docker_socket_mounted": False,
        "workspace_mount_read_only": True,
        "timeout_seconds": 120,
        "max_output_bytes": EXECUTION_MAX_OUTPUT_BYTES_V2,
    }
    values.update(overrides)
    return ExecutionProfileRecordV2(**values)  # type: ignore[arg-type]


def _request(**overrides: object) -> ExecutionActionRequestV2:
    values: dict[str, object] = {
        "request_id": "exec-request-1",
        "execution_profile_id": "exec-profile-1",
        "execution_profile_revision": 4,
        "reference_profile_id": "reference-1",
        "reference_profile_revision": 3,
        "run_id": "run-1",
        "candidate_id": "cand-0001",
        "candidate_revision": 3,
        "action_kind": "VALIDATE_CANDIDATE",
        "argv": ("vespercode-validate", "cand-0001", "3"),
        "validation_run_id": "valid-0001",
    }
    values.update(overrides)
    return ExecutionActionRequestV2(**values)  # type: ignore[arg-type]


def _tmpfs_inspect_spec() -> dict[str, str]:
    """The daemon-side Tmpfs spelling of the frozen tmpfs flag."""
    path, _, options = EXECUTOR_TMPFS_MOUNT_V2.partition(":")
    return {path: options}


def _inspect_payload(
    profile: ExecutionProfileRecordV2,
    request: ExecutionActionRequestV2,
    source: str,
    *,
    host: dict[str, object] | None = None,
    config: dict[str, object] | None = None,
    mounts: list[dict[str, object]] | None = None,
) -> bytes:
    """The exact daemon inspect report of a correctly created container.

    Mirrors what ``docker inspect`` reports on the real daemon for a
    container created with the adapter's closed flag set (calibrated
    against Docker 29.1.3); ``host``/``config``/``mounts`` patch the
    defaults to script one daemon-side drift at a time.
    """
    host_report: dict[str, object] = {
        "NetworkMode": "none",
        "ReadonlyRootfs": True,
        "CapDrop": ["ALL"],
        "Privileged": False,
        "Memory": EXECUTOR_MEMORY_LIMIT_BYTES_V2,
        "MemorySwap": EXECUTOR_MEMORY_LIMIT_BYTES_V2,
        "NanoCpus": EXECUTOR_CPU_LIMIT_V2 * 1_000_000_000,
        "PidsLimit": EXECUTOR_PIDS_LIMIT_V2,
        "Tmpfs": _tmpfs_inspect_spec(),
        "Mounts": [
            {
                "Type": "bind",
                "Source": source,
                "Target": "/workspace",
                "ReadOnly": True,
            }
        ],
    }
    if host is not None:
        host_report.update(host)
    if mounts is not None:
        host_report["Mounts"] = mounts
    config_report: dict[str, object] = {
        "User": profile.non_root_user,
        "Image": profile.image_reference,
        "Cmd": list(request.argv),
    }
    if config is not None:
        config_report.update(config)
    report = [{"HostConfig": host_report, "Config": config_report}]
    return json.dumps(report).encode("utf-8")


def _happy_outcomes(
    profile: ExecutionProfileRecordV2,
    request: ExecutionActionRequestV2,
    source: str,
) -> list[object]:
    """create, inspect, start, and remove — every phase succeeds."""
    return [
        _ok(0, b"0123456789abcdef" * 4 + b"\n"),
        _ok(0, _inspect_payload(profile, request, source)),
        _ok(0, b"validate ok\n"),
        _ok(0, b"removed\n"),
    ]


class SubprocessDockerExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self._directory.name) / "workspace"
        self.workspace.mkdir()
        self.source = self.workspace.as_posix()
        self.profile = _profile()
        self.request = _request()

    def tearDown(self) -> None:
        self._directory.cleanup()

    def _run(self, runner: _ScriptedRunner) -> object:
        executor = SubprocessDockerExecutorV2(self.workspace, runner)
        return executor.run(self.request, self.profile)

    @staticmethod
    def _container_name(argv: list[str]) -> str:
        return argv[argv.index("--name") + 1]

    def _name_of_run(self, runner: _ScriptedRunner) -> str:
        create = runner.argvs()[0]
        assert create[1] == "create"
        return self._container_name(create)

    # ------------------------------------------------------------------
    # Construction and port contract
    # ------------------------------------------------------------------

    def test_the_adapter_requires_an_absolute_existing_workspace(self) -> None:
        file_target = self.workspace / "file.txt"
        file_target.touch()
        for bad, reason in (
            ("workspace", "a relative path"),
            (self.workspace / "missing", "a missing directory"),
            (file_target, "a plain file"),
            (Path("C:/tmp/work,space"), "a comma in the mount source"),
        ):
            with self.subTest(reason=reason):
                with self.assertRaises(ValueError):
                    SubprocessDockerExecutorV2(bad)

    def test_the_adapter_implements_the_execution_port(self) -> None:
        executor = SubprocessDockerExecutorV2(self.workspace)
        self.assertIsInstance(executor, V2ExecutionPort)

    def test_run_requires_the_closed_request_and_profile_records(
        self,
    ) -> None:
        runner = _ScriptedRunner([])
        executor = SubprocessDockerExecutorV2(self.workspace, runner)
        for bad_request in (
            "rm -rf /workspace",
            "vespercode-validate cand-0001 3",
            None,
            3,
        ):
            with self.subTest(bad_request=bad_request):
                with self.assertRaises(ValueError):
                    executor.run(bad_request, self.profile)
        with self.assertRaises(ValueError):
            executor.run(self.request, "profile")
        self.assertEqual(runner.calls, [])

    # ------------------------------------------------------------------
    # The closed command contract
    # ------------------------------------------------------------------

    def test_a_successful_run_issues_exactly_the_closed_sequence(self) -> None:
        runner = _ScriptedRunner(
            _happy_outcomes(self.profile, self.request, self.source)
        )
        result = self._run(runner)
        self.assertEqual(result.status, "SUCCEEDED")
        verbs = [tuple(argv[0:2]) for argv in runner.argvs()]
        self.assertEqual(
            verbs,
            [
                ("docker", "create"),
                ("docker", "inspect"),
                ("docker", "start"),
                ("docker", "rm"),
            ],
        )
        name = self._name_of_run(runner)
        self.assertEqual(
            self._container_name(runner.argvs()[0]),
            name,
        )
        for argv in runner.argvs()[1:]:
            self.assertEqual(argv[-1], name)

    def test_the_create_command_is_the_closed_isolation_flag_set(self) -> None:
        runner = _ScriptedRunner(
            _happy_outcomes(self.profile, self.request, self.source)
        )
        self._run(runner)
        create = runner.argvs()[0]
        name = self._container_name(create)
        self.assertEqual(
            create,
            [
                "docker",
                "create",
                "--pull",
                "never",
                "--name",
                name,
                "--network",
                "none",
                "--user",
                "10001:10001",
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
                f"type=bind,source={self.source},target=/workspace,readonly",
                "vespercode-validation-image",
                "vespercode-validate",
                "cand-0001",
                "3",
            ],
        )

    def test_the_isolation_parameters_come_from_the_bound_profile(self) -> None:
        profile = _profile(non_root_user="20002:20002")
        runner = _ScriptedRunner(
            _happy_outcomes(profile, self.request, self.source)
        )
        executor = SubprocessDockerExecutorV2(self.workspace, runner)
        executor.run(self.request, profile)
        create = runner.argvs()[0]
        self.assertEqual(
            create[create.index("--user") + 1], profile.non_root_user
        )
        self.assertEqual(
            create[create.index("--network") + 1], "none"
        )
        self.assertIn("--read-only", create)
        self.assertEqual(create[create.index("--cap-drop") + 1], "ALL")
        self.assertEqual(
            create[create.index("--pull") + 1], "never"
        )
        mount = create[create.index("--mount") + 1]
        self.assertEqual(
            mount,
            f"type=bind,source={self.source},target=/workspace,readonly",
        )
        self.assertEqual(
            create[create.index("--tmpfs") + 1], EXECUTOR_TMPFS_MOUNT_V2
        )
        self.assertEqual(
            create[create.index("--memory") + 1],
            str(EXECUTOR_MEMORY_LIMIT_BYTES_V2),
        )
        self.assertEqual(
            create[create.index("--memory-swap") + 1],
            str(EXECUTOR_MEMORY_LIMIT_BYTES_V2),
        )
        self.assertEqual(
            create[create.index("--pids-limit") + 1],
            str(EXECUTOR_PIDS_LIMIT_V2),
        )
        self.assertEqual(
            create[create.index("--cpus") + 1], str(EXECUTOR_CPU_LIMIT_V2)
        )

    def test_every_command_is_a_plain_token_list_never_a_shell_string(
        self,
    ) -> None:
        scenarios: list[list[object]] = [
            _happy_outcomes(self.profile, self.request, self.source),
            [
                _ok(0, b"id"),
                _ok(0, _inspect_payload(self.profile, self.request, self.source)),
                _timed_out(b"partial\n"),
                _ok(0, b"stopped\n"),
                _ok(0, b"removed\n"),
            ],
            [_ok(1, b"", b"no such image")],
            [
                _ok(0, b"id"),
                _ok(1, b"", b"daemon error"),
                _ok(0, b"removed\n"),
            ],
        ]
        for outcomes in scenarios:
            with self.subTest(outcomes=outcomes):
                runner = _ScriptedRunner(outcomes)
                self._run(runner)
                for argv, _, _ in runner.calls:
                    self.assertIsInstance(argv, list)
                    for token in argv:
                        self.assertIsInstance(token, str)
                        self.assertNotIn(";", token)
                        self.assertNotIn("|", token)
                        self.assertNotIn("&&", token)

    def test_no_command_carries_a_host_registry_or_secret_surface(
        self,
    ) -> None:
        forbidden = {
            "-H",
            "--host",
            "--privileged",
            "--entrypoint",
            "--env",
            "-e",
            "--volume",
            "-v",
            "--link",
            "--dns",
            "--add-host",
            "--socket",
            "docker.sock",
            "login",
            "logout",
            "push",
            "build",
            "exec",
            "kill",
            "restart",
            "commit",
            "save",
            "load",
            "tag",
            "prune",
            "https://",
            "http://",
        }
        scenarios: list[list[object]] = [
            _happy_outcomes(self.profile, self.request, self.source),
            [
                _ok(0, b"id"),
                _ok(0, _inspect_payload(self.profile, self.request, self.source)),
                _timed_out(b"partial\n"),
                _ok(0, b"stopped\n"),
                _ok(0, b"removed\n"),
            ],
        ]
        for outcomes in scenarios:
            with self.subTest(outcomes=outcomes):
                runner = _ScriptedRunner(outcomes)
                self._run(runner)
                for argv in runner.argvs():
                    self.assertEqual(argv[0], "docker")
                    for token in argv:
                        self.assertNotIn(token, forbidden)

    def test_the_inspect_start_and_remove_commands_reference_the_container(
        self,
    ) -> None:
        runner = _ScriptedRunner(
            _happy_outcomes(self.profile, self.request, self.source)
        )
        self._run(runner)
        name = self._name_of_run(runner)
        argvs = runner.argvs()
        self.assertEqual(argvs[1], ["docker", "inspect", name])
        self.assertEqual(argvs[2], ["docker", "start", "--attach", name])
        self.assertEqual(argvs[3], ["docker", "rm", "--force", name])

    def test_the_runner_bounds_every_command_by_the_profile(self) -> None:
        profile = _profile(timeout_seconds=5, max_output_bytes=4096)
        runner = _ScriptedRunner(
            _happy_outcomes(profile, self.request, self.source)
        )
        executor = SubprocessDockerExecutorV2(self.workspace, runner)
        executor.run(self.request, profile)
        self.assertEqual(len(runner.calls), 4)
        for index, (argv, timeout, cap) in enumerate(runner.calls):
            self.assertEqual(cap, 4096)
            if index < 3:
                # create/inspect/start run inside the profile's own
                # bounded timeout budget (the remaining deadline).
                self.assertGreater(timeout, 0)
                self.assertLessEqual(timeout, 5)
            else:
                # the removal is bounded hygiene after the execution.
                self.assertEqual(
                    timeout, EXECUTOR_CLEANUP_TIMEOUT_SECONDS_V2
                )

    def test_the_container_name_is_unique_per_run_and_never_leaks(self) -> None:
        names = []
        for _ in range(2):
            runner = _ScriptedRunner(
                _happy_outcomes(self.profile, self.request, self.source)
            )
            result = self._run(runner)
            name = self._name_of_run(runner)
            self.assertTrue(name.startswith("vespercode-exec-"))
            self.assertNotIn(name, result.output)
            self.assertNotIn("vespercode-exec-", result.output)
            names.append(name)
        self.assertNotEqual(names[0], names[1])

    # ------------------------------------------------------------------
    # Result mapping: success, nonzero, timeout, overflow
    # ------------------------------------------------------------------

    def test_a_successful_execution_reports_the_bounded_container_output(
        self,
    ) -> None:
        runner = _ScriptedRunner(
            [
                _ok(0, b"id\n"),
                _ok(0, _inspect_payload(self.profile, self.request, self.source)),
                _ok(0, b"validate ok\n", b"warn: deprecation\n"),
                _ok(0, b"removed\n"),
            ]
        )
        result = self._run(runner)
        self.assertEqual(result.status, "SUCCEEDED")
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.output, "validate ok\nwarn: deprecation\n")

    def test_a_nonzero_container_exit_code_is_a_closed_failure(self) -> None:
        runner = _ScriptedRunner(
            [
                _ok(0, b"id\n"),
                _ok(0, _inspect_payload(self.profile, self.request, self.source)),
                _ok(2, b"2 checks failed\n", b""),
                _ok(0, b"removed\n"),
            ]
        )
        result = self._run(runner)
        self.assertEqual(result.status, "FAILED")
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(result.output, "2 checks failed\n")

    def test_a_timeout_stops_the_exact_container_and_reports_timed_out(
        self,
    ) -> None:
        runner = _ScriptedRunner(
            [
                _ok(0, b"id\n"),
                _ok(0, _inspect_payload(self.profile, self.request, self.source)),
                _timed_out(b"partial output\n"),
                _ok(0, b"stopped\n"),
                _ok(0, b"removed\n"),
            ]
        )
        result = self._run(runner)
        self.assertEqual(result.status, "TIMED_OUT")
        self.assertIsNone(result.exit_code)
        self.assertEqual(result.output, "partial output\n")
        argvs = runner.argvs()
        name = self._name_of_run(runner)
        self.assertEqual(argvs[3], ["docker", "stop", "--time", "0", name])
        self.assertEqual(argvs[4], ["docker", "rm", "--force", name])
        # No retry: the start was issued exactly once.
        self.assertEqual(
            [argv[1] for argv in argvs],
            ["create", "inspect", "start", "stop", "rm"],
        )

    def test_a_runner_reported_output_overflow_fails_closed(self) -> None:
        runner = _ScriptedRunner(
            [
                _ok(0, b"id\n"),
                _ok(0, _inspect_payload(self.profile, self.request, self.source)),
                _ok(0, b"validate", b"", output_truncated=True),
                _ok(0, b"removed\n"),
            ]
        )
        result = self._run(runner)
        self.assertEqual(result.status, "FAILED")
        self.assertIsNone(result.exit_code)
        self.assertEqual(result.output, "validate")

    def test_an_over_cap_runner_return_fails_closed_and_clamps(self) -> None:
        profile = _profile(max_output_bytes=64)
        runner = _ScriptedRunner(
            [
                _ok(0, b"id\n"),
                _ok(0, _inspect_payload(profile, self.request, self.source)),
                _ok(0, b"x" * 200, b"y" * 200),
                _ok(0, b"removed\n"),
            ]
        )
        executor = SubprocessDockerExecutorV2(self.workspace, runner)
        result = executor.run(self.request, profile)
        self.assertEqual(result.status, "FAILED")
        self.assertIsNone(result.exit_code)
        self.assertLessEqual(len(result.output), 64)

    # ------------------------------------------------------------------
    # Fail-closed infra failures and daemon drift
    # ------------------------------------------------------------------

    def test_create_infra_failures_are_closed_failures(self) -> None:
        scenarios: list[list[object]] = [
            [_ok(1, b"", b"docker: no such image")],
            [_timed_out()],
            [FileNotFoundError("docker")],
            [OSError("cannot connect to the daemon")],
            ["not an outcome"],
        ]
        for outcomes in scenarios:
            with self.subTest(outcomes=outcomes):
                runner = _ScriptedRunner(outcomes)
                result = self._run(runner)
                self.assertEqual(result.status, "FAILED")
                self.assertIsNone(result.exit_code)
                self.assertEqual(result.output, "")
                # Nothing was created: no inspect, no start, and no
                # removal of a container that does not exist.
                self.assertEqual(len(runner.calls), 1)

    def test_inspect_infra_failures_are_closed_failures_with_cleanup(
        self,
    ) -> None:
        scenarios: list[list[object]] = [
            [_ok(0, b"id\n"), _ok(1, b"", b"daemon error"), _ok(0, b"removed")],
            [_ok(0, b"id\n"), _timed_out(), _ok(0, b"removed")],
            [
                _ok(0, b"id\n"),
                _ok(0, b"not json at all"),
                _ok(0, b"removed"),
            ],
            [_ok(0, b"id\n"), _ok(0, b"[]"), _ok(0, b"removed")],
            [
                _ok(0, b"id\n"),
                _ok(0, b'{"HostConfig": {}}'),
                _ok(0, b"removed"),
            ],
            [
                _ok(0, b"id\n"),
                RuntimeError("inspect exploded"),
                _ok(0, b"removed"),
            ],
        ]
        for outcomes in scenarios:
            with self.subTest(outcomes=outcomes):
                runner = _ScriptedRunner(outcomes)
                result = self._run(runner)
                self.assertEqual(result.status, "FAILED")
                self.assertIsNone(result.exit_code)
                self.assertEqual(result.output, "")
                argvs = runner.argvs()
                self.assertNotIn("start", [argv[1] for argv in argvs])
                self.assertEqual(argvs[-1][0:2], ["docker", "rm"])

    def test_daemon_configuration_drift_fails_closed_before_the_run(
        self,
    ) -> None:
        base = _inspect_payload(self.profile, self.request, self.source)
        drifts: list[tuple[str, bytes]] = [
            (
                "network mode drift",
                _inspect_payload(
                    self.profile,
                    self.request,
                    self.source,
                    host={"NetworkMode": "bridge"},
                ),
            ),
            (
                "read-only rootfs drift",
                _inspect_payload(
                    self.profile,
                    self.request,
                    self.source,
                    host={"ReadonlyRootfs": False},
                ),
            ),
            (
                "capability drop drift",
                _inspect_payload(
                    self.profile,
                    self.request,
                    self.source,
                    host={"CapDrop": []},
                ),
            ),
            (
                "partial capability drop drift",
                _inspect_payload(
                    self.profile,
                    self.request,
                    self.source,
                    host={"CapDrop": ["NET_ADMIN"]},
                ),
            ),
            (
                "privileged drift",
                _inspect_payload(
                    self.profile,
                    self.request,
                    self.source,
                    host={"Privileged": True},
                ),
            ),
            (
                "memory limit drift",
                _inspect_payload(
                    self.profile,
                    self.request,
                    self.source,
                    host={"Memory": 1},
                ),
            ),
            (
                "unbounded swap drift",
                _inspect_payload(
                    self.profile,
                    self.request,
                    self.source,
                    host={"MemorySwap": 0},
                ),
            ),
            (
                "cpu limit drift",
                _inspect_payload(
                    self.profile,
                    self.request,
                    self.source,
                    host={"NanoCpus": 0},
                ),
            ),
            (
                "pids limit drift",
                _inspect_payload(
                    self.profile,
                    self.request,
                    self.source,
                    host={"PidsLimit": 0},
                ),
            ),
            (
                "tmpfs drift",
                _inspect_payload(
                    self.profile,
                    self.request,
                    self.source,
                    host={"Tmpfs": {}},
                ),
            ),
            (
                "non-root user drift",
                _inspect_payload(
                    self.profile,
                    self.request,
                    self.source,
                    config={"User": "0:0"},
                ),
            ),
            (
                "image reference drift",
                _inspect_payload(
                    self.profile,
                    self.request,
                    self.source,
                    config={"Image": "other-validation-image"},
                ),
            ),
            (
                "command drift",
                _inspect_payload(
                    self.profile,
                    self.request,
                    self.source,
                    config={"Cmd": ["sh", "-c", "rm -rf /"]},
                ),
            ),
            (
                "stale candidate drift",
                _inspect_payload(
                    self.profile,
                    self.request,
                    self.source,
                    config={"Cmd": ["vespercode-validate", "cand-0002", "3"]},
                ),
            ),
            (
                "missing workspace bind",
                _inspect_payload(
                    self.profile,
                    self.request,
                    self.source,
                    mounts=[],
                ),
            ),
            (
                "extra mount drift",
                _inspect_payload(
                    self.profile,
                    self.request,
                    self.source,
                    mounts=[
                        {
                            "Type": "bind",
                            "Source": self.source,
                            "Target": "/workspace",
                            "ReadOnly": True,
                        },
                        {
                            "Type": "bind",
                            "Source": "/host",
                            "Target": "/host",
                            "ReadOnly": True,
                        },
                    ],
                ),
            ),
            (
                "docker socket mount",
                _inspect_payload(
                    self.profile,
                    self.request,
                    self.source,
                    mounts=[
                        {
                            "Type": "bind",
                            "Source": "/var/run/docker.sock",
                            "Target": "/var/run/docker.sock",
                            "ReadOnly": True,
                        }
                    ],
                ),
            ),
            (
                "workspace mount target drift",
                _inspect_payload(
                    self.profile,
                    self.request,
                    self.source,
                    mounts=[
                        {
                            "Type": "bind",
                            "Source": self.source,
                            "Target": "/etc",
                            "ReadOnly": True,
                        }
                    ],
                ),
            ),
            (
                "writable workspace mount",
                _inspect_payload(
                    self.profile,
                    self.request,
                    self.source,
                    mounts=[
                        {
                            "Type": "bind",
                            "Source": self.source,
                            "Target": "/workspace",
                            "ReadOnly": False,
                        }
                    ],
                ),
            ),
            (
                "workspace mount source drift",
                _inspect_payload(
                    self.profile,
                    self.request,
                    self.source + "-other",
                ),
            ),
        ]
        for reason, payload in drifts:
            with self.subTest(reason=reason):
                runner = _ScriptedRunner(
                    [_ok(0, b"id\n"), _ok(0, payload), _ok(0, b"removed\n")]
                )
                result = self._run(runner)
                self.assertEqual(result.status, "FAILED")
                self.assertIsNone(result.exit_code)
                self.assertEqual(result.output, "")
                argvs = runner.argvs()
                # The container never started, and it was removed.
                self.assertNotIn("start", [argv[1] for argv in argvs])
                self.assertEqual(argvs[-1][0:2], ["docker", "rm"])
                self.assertEqual(len(argvs), 3)
        # The undrifted payload is accepted (the control).
        runner = _ScriptedRunner(
            [
                _ok(0, b"id\n"),
                _ok(0, base),
                _ok(0, b"validate ok\n"),
                _ok(0, b"removed\n"),
            ]
        )
        result = self._run(runner)
        self.assertEqual(result.status, "SUCCEEDED")

    # ------------------------------------------------------------------
    # Cleanup discipline
    # ------------------------------------------------------------------

    def test_cleanup_removes_the_container_on_every_post_create_path(
        self,
    ) -> None:
        scenarios: list[list[object]] = [
            ("SUCCEEDED", _happy_outcomes(self.profile, self.request, self.source)),
            (
                "FAILED",
                [
                    _ok(0, b"id\n"),
                    _ok(0, _inspect_payload(self.profile, self.request, self.source)),
                    _ok(2, b"", b"failed\n"),
                    _ok(0, b"removed\n"),
                ],
            ),
            (
                "TIMED_OUT",
                [
                    _ok(0, b"id\n"),
                    _ok(0, _inspect_payload(self.profile, self.request, self.source)),
                    _timed_out(b"partial\n"),
                    _ok(0, b"stopped\n"),
                    _ok(0, b"removed\n"),
                ],
            ),
            (
                "DRIFT",
                [
                    _ok(0, b"id\n"),
                    _ok(
                        0,
                        _inspect_payload(
                            self.profile,
                            self.request,
                            self.source,
                            host={"NetworkMode": "bridge"},
                        ),
                    ),
                    _ok(0, b"removed\n"),
                ],
            ),
            (
                "START_ERROR",
                [
                    _ok(0, b"id\n"),
                    _ok(0, _inspect_payload(self.profile, self.request, self.source)),
                    RuntimeError("start exploded"),
                    _ok(0, b"removed\n"),
                ],
            ),
        ]
        for expected, outcomes in scenarios:
            with self.subTest(outcomes=outcomes):
                runner = _ScriptedRunner(outcomes)
                self._run(runner)
                argvs = runner.argvs()
                self.assertEqual(argvs[-1][0:2], ["docker", "rm"])
                self.assertEqual(argvs[-1][-1], self._name_of_run(runner))
                # Exactly one removal, always the final command.
                removals = [argv for argv in argvs if argv[1] == "rm"]
                self.assertEqual(len(removals), 1)

    def test_a_cleanup_failure_never_changes_the_execution_result(
        self,
    ) -> None:
        for cleanup in (RuntimeError("rm exploded"), _ok(1, b"", b"gone")):
            with self.subTest(cleanup=type(cleanup).__name__):
                runner = _ScriptedRunner(
                    [
                        _ok(0, b"id\n"),
                        _ok(
                            0,
                            _inspect_payload(
                                self.profile, self.request, self.source
                            ),
                        ),
                        _ok(0, b"validate ok\n"),
                        cleanup,
                    ]
                )
                result = self._run(runner)
                self.assertEqual(result.status, "SUCCEEDED")
                self.assertEqual(result.exit_code, 0)
                self.assertEqual(result.output, "validate ok\n")

    # ------------------------------------------------------------------
    # Composition behind the B4a binding/readiness gates
    # ------------------------------------------------------------------

    def _service(
        self,
        *,
        binding: object | None = None,
        readiness: object | None = None,
        runner: _ScriptedRunner,
    ) -> V2ExecutionService:
        executor = SubprocessDockerExecutorV2(self.workspace, runner)
        return V2ExecutionService(
            self.profile,
            binding if binding is not None else FakeV2BindingLookup(),
            readiness if readiness is not None else FakeV2Readiness(),
            executor,
        )

    def test_a_not_ready_verdict_makes_no_executor_call(self) -> None:
        for reason in ("IMAGE_NOT_AVAILABLE", "DAEMON_UNAVAILABLE"):
            with self.subTest(reason=reason):
                runner = _ScriptedRunner([])
                service = self._service(
                    readiness=FakeV2Readiness(
                        ExecutionReadinessResultV2("NOT_READY", reason)
                    ),
                    runner=runner,
                )
                outcome = service.execute(self.request)
                self.assertEqual(outcome.status, "FAILED")
                self.assertEqual(outcome.error_code, f"READINESS_{reason}")
                self.assertEqual(runner.calls, [])

    def test_an_unresolved_binding_makes_no_executor_call(self) -> None:
        runner = _ScriptedRunner([])
        service = self._service(
            binding=FakeV2BindingLookup(unresolved=True), runner=runner
        )
        outcome = service.execute(self.request)
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "EXECUTION_BINDING_NOT_FOUND")
        self.assertEqual(runner.calls, [])

    def test_a_stale_binding_makes_no_executor_call(self) -> None:
        runner = _ScriptedRunner([])
        service = self._service(
            binding=FakeV2BindingLookup(current_revision=4), runner=runner
        )
        outcome = service.execute(self.request)
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "EXECUTION_BINDING_STALE")
        self.assertEqual(runner.calls, [])

    def test_the_adapter_composes_behind_the_binding_and_readiness_gates(
        self,
    ) -> None:
        runner = _ScriptedRunner(
            _happy_outcomes(self.profile, self.request, self.source)
        )
        service = self._service(runner=runner)
        outcome = service.execute(self.request)
        self.assertEqual(outcome.status, "SUCCEEDED")
        self.assertIsNone(outcome.error_code)
        self.assertEqual(outcome.exit_code, 0)
        self.assertEqual(outcome.output_excerpt, "validate ok\n")
        self.assertEqual(len(runner.calls), 4)


if __name__ == "__main__":
    unittest.main()
