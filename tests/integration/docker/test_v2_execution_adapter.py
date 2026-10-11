"""Route B / B4b-01: the optional real-Docker integration test.

NOT part of the v2 offline unit job: ``tests/unit/v2`` never imports
this module, and the recorded test command never runs it.  It exists
so an operator can prove the REAL ``SubprocessDockerExecutorV2``
against the local Docker daemon:

    python -m unittest discover -s tests/integration/docker ^
        -p "test_v2_execution_adapter.py" -v

The module skips HONESTLY (``SkipTest`` with the exact reason) when
the docker CLI is not on PATH, the daemon is unreachable, or no
token-conformant local validation image exists (the v2 token charset
excludes every registry/tag spelling, so an operator must tag one,
e.g. ``docker tag <image> vespercode-validation-image``).  The run
mounts a THROWAWAY temporary workspace READ-ONLY, never the operator's
working tree, and removes the container it creates.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from vespercode.execution.v2_docker_executor import (  # noqa: E402
    ExecutorCommandOutcomeV2,
    SubprocessDockerExecutorV2,
    _default_command_runner,
)
from vespercode.execution.v2_execution import (  # noqa: E402
    ExecutionActionRequestV2,
)
from vespercode.execution.v2_profile import (  # noqa: E402
    EXECUTION_MAX_OUTPUT_BYTES_V2,
    ExecutionProfileRecordV2,
)

_IMAGE_TOKEN = "vespercode-validation-image"
_CONTAINER_PREFIX = "vespercode-exec-"


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        completed = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
            shell=False,
        )
    except Exception:
        return False
    return completed.returncode == 0


def _image_available(token: str) -> bool:
    try:
        completed = subprocess.run(
            ["docker", "image", "inspect", token],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
            shell=False,
        )
    except Exception:
        return False
    return completed.returncode == 0


class _RecordingRunner:
    """The module's real default subprocess runner, with recorded argv."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(
        self,
        argv: object,
        *,
        timeout_seconds: object,
        max_output_bytes: object,
    ) -> ExecutorCommandOutcomeV2:
        assert isinstance(argv, list)
        self.calls.append(list(argv))
        return _default_command_runner(
            argv,
            timeout_seconds=timeout_seconds,  # type: ignore[arg-type]
            max_output_bytes=max_output_bytes,  # type: ignore[arg-type]
        )


@unittest.skipUnless(
    _docker_available(),
    "the docker CLI/daemon is unavailable on this host",
)
@unittest.skipUnless(
    _image_available(_IMAGE_TOKEN),
    "no token-conformant local validation image exists (tag one with: "
    f"docker tag <image> {_IMAGE_TOKEN})",
)
class RealDockerExecutorTests(unittest.TestCase):
    """The real adapter against the real daemon: a real isolated run.

    The image under the opaque token is operator-supplied; when it has
    no ``vespercode-validate`` entrypoint the run fails fast inside the
    container (a real, bounded, cleaned-up FAILED result), and when it
    has one the run reports the container's own exit code and output.
    """

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self._directory.name) / "workspace"
        self.workspace.mkdir()
        self.runner = _RecordingRunner()
        self.executor = SubprocessDockerExecutorV2(self.workspace, self.runner)
        self.profile = ExecutionProfileRecordV2(
            execution_profile_id="exec-profile-integration",
            execution_profile_revision=1,
            reference_profile_id="reference-integration",
            reference_profile_revision=1,
            image_reference=_IMAGE_TOKEN,
            network_disabled=True,
            non_root_user="10001:10001",
            read_only_rootfs=True,
            all_capabilities_dropped=True,
            docker_socket_mounted=False,
            workspace_mount_read_only=True,
            timeout_seconds=120,
            max_output_bytes=EXECUTION_MAX_OUTPUT_BYTES_V2,
        )
        self.request = ExecutionActionRequestV2(
            request_id="exec-request-integration",
            execution_profile_id="exec-profile-integration",
            execution_profile_revision=1,
            reference_profile_id="reference-integration",
            reference_profile_revision=1,
            run_id="run-integration",
            candidate_id="cand-integration",
            candidate_revision=0,
            action_kind="VALIDATE_CANDIDATE",
            argv=("vespercode-validate", "cand-integration", "0"),
        )

    def tearDown(self) -> None:
        self._directory.cleanup()

    def _leftover_containers(self) -> list[str]:
        completed = subprocess.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"name={_CONTAINER_PREFIX}",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            timeout=30,
            check=False,
            shell=False,
        )
        return sorted(completed.stdout.decode("utf-8").split())

    def test_the_real_adapter_runs_isolated_and_cleans_up(self) -> None:
        result = self.executor.run(self.request, self.profile)
        self.assertIn(result.status, {"SUCCEEDED", "FAILED", "TIMED_OUT"})
        self.assertIsInstance(result.output, str)
        if result.status == "SUCCEEDED":
            self.assertEqual(result.exit_code, 0)
        # The daemon-side drift verification passed against the REAL
        # daemon: create, inspect, start (and the removal) were issued
        # through the module's own default subprocess runner.
        verbs = [argv[1] for argv in self.runner.calls]
        self.assertIn("create", verbs)
        self.assertIn("inspect", verbs)
        self.assertIn("start", verbs)
        self.assertEqual(verbs[-1], "rm")
        create = self.runner.calls[0]
        self.assertEqual(create[create.index("--network") + 1], "none")
        self.assertEqual(create[create.index("--cap-drop") + 1], "ALL")
        self.assertIn("--read-only", create)
        self.assertEqual(create[create.index("--pull") + 1], "never")
        # No leftover container of this adapter remains.
        self.assertEqual(self._leftover_containers(), [])

    def test_a_real_timeout_stops_and_removes_the_container(self) -> None:
        profile = ExecutionProfileRecordV2(
            execution_profile_id="exec-profile-integration",
            execution_profile_revision=1,
            reference_profile_id="reference-integration",
            reference_profile_revision=1,
            image_reference=_IMAGE_TOKEN,
            network_disabled=True,
            non_root_user="10001:10001",
            read_only_rootfs=True,
            all_capabilities_dropped=True,
            docker_socket_mounted=False,
            workspace_mount_read_only=True,
            timeout_seconds=1,
            max_output_bytes=EXECUTION_MAX_OUTPUT_BYTES_V2,
        )
        result = self.executor.run(self.request, profile)
        # The 1-second bound can only bite when the image provides a
        # long-running entrypoint; with a fast one the run completes
        # (or fails fast) inside the bound.  Either way the exact
        # container is stopped and removed.
        self.assertIn(result.status, {"SUCCEEDED", "FAILED", "TIMED_OUT"})
        if result.status == "TIMED_OUT":
            verbs = [argv[1] for argv in self.runner.calls]
            self.assertEqual(verbs[-2], "stop")
            self.assertEqual(verbs[-1], "rm")
            self.assertIsNone(result.exit_code)
        self.assertEqual(self._leftover_containers(), [])


if __name__ == "__main__":
    unittest.main()
