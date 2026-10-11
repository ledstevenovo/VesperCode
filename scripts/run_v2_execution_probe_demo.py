"""Opt-in, read-only manual evidence probe for Route B / B4a.

NOT part of the v2 unit job: this script exercises the optional real
subprocess edge of SubprocessDockerProbeV2 against the operator's
local Docker daemon, read-only (docker image inspect / docker info —
no container is created, run, or pulled).  Run it explicitly with:

    PYTHONPATH=src python scripts/run_v2_execution_probe_demo.py [token]
"""

from __future__ import annotations

import sys

from vespercode.execution.v2_docker_probe import SubprocessDockerProbeV2
from vespercode.execution.v2_profile import (
    EXECUTION_MAX_OUTPUT_BYTES_V2,
    ExecutionProfileRecordV2,
)


def _profile(image_reference: str) -> ExecutionProfileRecordV2:
    return ExecutionProfileRecordV2(
        execution_profile_id="exec-profile-demo",
        execution_profile_revision=1,
        reference_profile_id="reference-demo",
        reference_profile_revision=1,
        image_reference=image_reference,
        network_disabled=True,
        non_root_user="10001:10001",
        read_only_rootfs=True,
        all_capabilities_dropped=True,
        docker_socket_mounted=False,
        workspace_mount_read_only=True,
        timeout_seconds=30,
        max_output_bytes=EXECUTION_MAX_OUTPUT_BYTES_V2,
    )


def main() -> int:
    tokens = (
        [sys.argv[1]] if len(sys.argv) > 1 else ["dbgpt-erp", "vespercode-validation-image"]
    )
    probe = SubprocessDockerProbeV2()
    for token in tokens:
        result = probe.check(_profile(token))
        print(f"image_reference={token!r} -> status={result.status} reason={result.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
