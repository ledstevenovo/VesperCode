"""T02.4 legacy step 2.G: real reference gate probe.

Runs the complete real evidence chain for the frozen repository state —
build input freeze, reproducible OCI build, credential-free loopback
registry round-trip, reference container isolation, collection/full/target
pytest lifecycles inside fresh reference containers, and two independent
target-failure fingerprint inputs — then freezes ``reference-profile-v1.json``
and emits the GO report only when every producer identity is complete and
mutually consistent.

The pytest runs inside fresh reference containers reuse the frozen SPEC
§1.4.5 execution parameters of step 2.D and add one minimal mechanism the
driver approved: the gate reporter tree is bound read-only at ``/gate`` and
``PYTHONPATH`` is set so the reporter loads explicitly (``-p``), with the
fixed report channel on the bounded tmpfs.  The T02.1 Dockerfile and all
frozen evidence bytes are never modified.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from spikes.docker_reference_boundary.execution_probe import (
    CPU_LIMIT,
    MEMORY_ARGV,
    NON_ROOT_GID,
    NON_ROOT_UID,
    PID_LIMIT,
    TMPFS_SPEC,
    WORKSPACE_TARGET,
    _ensure_frozen_image,
    _mount_src,
    _reproduce_frozen_layout,
    _verify_cleanup,
    probe_reference_container,
)
from spikes.docker_reference_boundary.failure_fingerprint_probe import (
    compare_failure_inputs,
    normalize_call_fail_input,
)
from spikes.docker_reference_boundary.image_builder import (
    ReferenceImageBuildEvidenceV1,
    build_reference_image,
)
from spikes.docker_reference_boundary.input_contract import (
    GATE_TOOLCHAIN_EVIDENCE_RELATIVE,
    freeze_reference_build_input,
)
from spikes.docker_reference_boundary.pytest_reporter import (
    STDOUT_EVENT_PREFIX,
    GatePytestReportV1,
    TestIdSequenceV1,
    load_gate_pytest_report,
    validate_gate_pytest_report,
)
from spikes.docker_reference_boundary.registry_probe import (
    probe_loopback_registry,
)
from spikes.docker_reference_boundary.report import (
    AssembleReferenceGateReportV1,
    DockerBoundaryGateReportV1,
    assemble_reference_gate_report,
    freeze_reference_profile_manifest,
    load_gate_toolchain_evidence,
)

MANIFEST_RELATIVE = Path("reference") / "manifest" / "reference-profile-v1.json"
SPIKES_RELATIVE = Path("spikes")
GATE_MOUNT_TARGET = "/gate"
PYTHONPATH_VALUE = f"{GATE_MOUNT_TARGET}:/workspace/src"
# The frozen fixture's one stable failing target (SPEC §4.5 baseline step 3).
TARGET_TEST_NODE_ID = "tests/test_calculator.py::test_add_returns_sum"


def _pytest_run_argv(
    image_ref: str,
    fixture: Path,
    spikes_root: Path,
    *,
    collect_only: bool,
    target_node_ids: TestIdSequenceV1 | None,
) -> list[str]:
    """The frozen SPEC §1.4.5 run parameters plus the explicit reporter
    channel: the fixture bind at /workspace stays the only project mount."""
    argv = [
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
        "--mount",
        f"type=bind,src={_mount_src(spikes_root)},dst={GATE_MOUNT_TARGET}/spikes,ro",
        "--env",
        f"PYTHONPATH={PYTHONPATH_VALUE}",
        "--env",
        "REPORT_CHANNEL=/tmp/gate-events.jsonl",
        "--env",
        "PYTHONHASHSEED=0",
        "--env",
        "TZ=UTC",
        "--env",
        "LANG=C.UTF-8",
        "--env",
        "LC_ALL=C.UTF-8",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        "--workdir",
        "/workspace",
        image_ref,
        "python",
        "-m",
        "pytest",
        "-p",
        "spikes.docker_reference_boundary.pytest_reporter",
        "-o",
        "cacheprovider=disabled",
        # The frozen fixture's pyproject.toml carries Python-style booleans
        # (``strict = True`` under [tool.mypy]) that TOML parsers reject, so
        # any pytest config search through /workspace fails before tests run.
        # The frozen fixture bytes are T02.1 evidence and cannot change; the
        # minimal mechanism is to pin an empty config file, which bypasses
        # the search entirely without touching any frozen byte.
        "-c",
        "/dev/null",
        "--rootdir",
        "/workspace",
    ]
    if collect_only:
        argv.append("--collect-only")
    if target_node_ids is not None:
        argv.extend(f"/workspace/{node_id}" for node_id in target_node_ids)
    else:
        argv.append("/workspace")
    return argv


def capture_reference_pytest(
    build: ReferenceImageBuildEvidenceV1,
    fixture: Path,
    root: Path,
    planned_node_ids: TestIdSequenceV1,
    *,
    collect_only: bool = False,
    target_node_ids: TestIdSequenceV1 | None = None,
) -> GatePytestReportV1:
    """Capture one explicitly loaded pytest lifecycle inside a fresh
    reference container and return one immutable report.

    The container runs with the frozen SPEC §1.4.5 parameters and the fixed
    report channel on the bounded tmpfs; the channel is reconstructed from
    the container's stdout, the container and any image loaded by this probe
    are removed on every exit path, and the report is bound to the observed
    container exit code.
    """
    with tempfile.TemporaryDirectory(prefix="vesper-gate-pytest-") as tmp:
        tmp_path = Path(tmp)
        output_tar = _reproduce_frozen_layout(tmp_path)
        image_ref, loaded_by_probe = _ensure_frozen_image(build, output_tar)
        container_id = ""
        failure: BaseException | None = None
        report: GatePytestReportV1 | None = None
        channel = tmp_path / "events.jsonl"
        try:
            container_id = _run_pytest_container(
                image_ref,
                fixture,
                root,
                collect_only=collect_only,
                target_node_ids=target_node_ids,
            )
            exit_code = _container_exit_code(container_id)
            _extract_channel_from_logs(container_id, channel)
            report = load_gate_pytest_report(channel, planned_node_ids, exit_code)
        except BaseException as exc:
            failure = exc
        try:
            cleanup_verified = _verify_cleanup(
                container_id, image_ref if loaded_by_probe else ""
            )
        except BaseException:
            cleanup_verified = False
        if not cleanup_verified:
            raise RuntimeError(
                "reference pytest container cleanup not verified"
            ) from failure
        if failure is not None:
            raise failure.with_traceback(failure.__traceback__)
        assert report is not None
        return report


def _run_pytest_container(
    image_ref: str,
    fixture: Path,
    root: Path,
    *,
    collect_only: bool,
    target_node_ids: TestIdSequenceV1 | None,
) -> str:
    proc = subprocess.run(
        _pytest_run_argv(
            image_ref,
            fixture,
            root / SPIKES_RELATIVE,
            collect_only=collect_only,
            target_node_ids=target_node_ids,
        ),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        tail = proc.stderr[-2000:] if proc.stderr else ""
        raise RuntimeError(
            f"docker run reference pytest failed (exit {proc.returncode}): {tail}"
        )
    container_id = proc.stdout.strip().splitlines()[-1].strip()
    if not container_id:
        raise RuntimeError("docker run returned no reference pytest container id")
    return container_id


def _container_exit_code(container_id: str) -> int:
    proc = subprocess.run(
        ["docker", "wait", container_id],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError("docker wait failed for the reference pytest container")
    try:
        return int(proc.stdout.strip())
    except ValueError as exc:
        raise RuntimeError("docker wait returned a non-integer exit code") from exc


def _extract_channel_from_logs(container_id: str, channel: Path) -> None:
    """Reconstruct the report channel from the container's stdout.

    Every event line is mirrored to stdout with the fixed structured prefix;
    the tmpfs channel itself is not readable through ``docker cp`` because
    tmpfs is a mount point, so the probe filters the prefixed lines from
    ``docker logs`` and fails closed when the reporter emitted none.
    """
    proc = subprocess.run(
        ["docker", "logs", container_id],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError("docker logs failed for the reference pytest container")
    lines = [
        line.partition(STDOUT_EVENT_PREFIX)[2]
        for line in proc.stdout.splitlines()
        if STDOUT_EVENT_PREFIX in line
    ]
    if not lines:
        raise RuntimeError("reference pytest reporter emitted no events")
    channel.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_reference_gate(root: Path) -> DockerBoundaryGateReportV1:
    """Run the complete real evidence chain and emit the GO/NO_GO report.

    Fails closed on any missing, drifted, or inconsistent real evidence:
    nothing is frozen and no report is emitted until build, registry,
    isolation, pytest, and fingerprint evidence are complete and
    identity-consistent.  The frozen manifest file is written exactly once
    from that consistent evidence.
    """
    root = Path(root)
    build_input = freeze_reference_build_input(root)
    build = build_reference_image(build_input)
    fixture = root / "reference" / "fixture"
    registry = probe_loopback_registry(build)
    isolation = probe_reference_container(build, fixture)
    gate_toolchain = load_gate_toolchain_evidence(
        root / GATE_TOOLCHAIN_EVIDENCE_RELATIVE
    )

    collect_one = capture_reference_pytest(build, fixture, root, (), collect_only=True)
    collect_two = capture_reference_pytest(build, fixture, root, (), collect_only=True)
    if collect_one.collected_node_ids != collect_two.collected_node_ids:
        raise RuntimeError("reference pytest collection is not stable")
    planned = collect_one.collected_node_ids
    full_report = capture_reference_pytest(build, fixture, root, planned)
    target_one = capture_reference_pytest(
        build,
        fixture,
        root,
        (TARGET_TEST_NODE_ID,),
        target_node_ids=(TARGET_TEST_NODE_ID,),
    )
    target_two = capture_reference_pytest(
        build,
        fixture,
        root,
        (TARGET_TEST_NODE_ID,),
        target_node_ids=(TARGET_TEST_NODE_ID,),
    )
    validated = [
        validate_gate_pytest_report(report)
        for report in (collect_one, collect_two, full_report, target_one, target_two)
    ]
    for result in validated:
        if result.passed is not True:
            raise RuntimeError(f"pytest evidence incomplete: {result.reason}")

    fingerprint = compare_failure_inputs(
        normalize_call_fail_input(target_one, TARGET_TEST_NODE_ID),
        normalize_call_fail_input(target_two, TARGET_TEST_NODE_ID),
    )
    if fingerprint.equal is not True:
        raise RuntimeError("independent target failures are not byte-identical")

    manifest = freeze_reference_profile_manifest(
        build_input, build, gate_toolchain, root / MANIFEST_RELATIVE
    )
    command = AssembleReferenceGateReportV1(
        manifest=manifest,
        build_input=build_input,
        build=build,
        registry=registry,
        isolation=isolation,
        pytest_evidence=validated[2],
        fingerprint=fingerprint,
        gate_toolchain=gate_toolchain,
    )
    report = assemble_reference_gate_report(command)
    if report.outcome != "GO":
        raise RuntimeError(f"reference gate report is not GO: {report.outcome}")
    return report
