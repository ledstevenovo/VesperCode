"""T20.2 legacy step 20.B: stable Baseline and ValidationManifestV1 tests.

``run_baseline`` executes the frozen six-check Baseline sequence with
fresh boundaries and publishes exactly one immutable ``ValidationManifestV1``
only when every predicate holds; every blocked row of the publication
matrix publishes no manifest (PLAN registry row 20.B as the operative
"exact §5.1 matrix" authority, SPEC_PROCESS §49 precedent).  The unit
surface scripts the closed ``DockerExecutor`` client factory with
deterministic raw outputs per check, so every blocked and passing row
runs fully offline with real materialization/cleanup boundaries.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest

# The Baseline contracts are pydantic runtime models; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.contracts.evidence import ArtifactRefV1, DigestV1
from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.execution.cleanup import ExecutionCleanupResultV1
from src.vespercode.execution.docker_executor import DockerExecutor
from src.vespercode.profiles.reference import load_reference_profile
from src.vespercode.trees.content_store import ContentObjectRefV1, ContentObjectStore
from src.vespercode.trees.snapshot import (
    SealedSnapshotInputFileV1,
    SnapshotDirectoryEntryV1,
    SnapshotEntryV1,
    SnapshotFileEntryV1,
    SnapshotTreeV1,
    _root_digest,
)
from src.vespercode.trees.text_classifier import TextMetadataV1, classify_supported_text
from src.vespercode.validation import baseline as baseline_module
from src.vespercode.validation.baseline import (
    BaselineBlockedV1,
    PassingBaselineV1,
    run_baseline,
)
from src.vespercode.validation.manifest import (
    ManifestBindingsV1,
    ValidationManifestV1,
    create_validation_manifest,
)
from src.vespercode.validation.python_adapter import (
    BaselineCheckPlanV1,
    PythonProjectAdapterV1,
    TargetTestIdSequenceV1,
)

_ADD = "tests/test_calculator.py::test_add_returns_sum"
_MULTIPLY = "tests/test_calculator.py::test_multiply_returns_product"
_PLUGIN_VERSION = "1"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _packaged_manifest_bytes() -> bytes:
    return (
        _repo_root()
        / "src"
        / "vespercode"
        / "profiles"
        / "builtin"
        / "reference-profile-v1.json"
    ).read_bytes()


def _policy_digest() -> str:
    manifest = load_reference_profile(_packaged_manifest_bytes())
    return manifest.editable_path_policy.digest


def _supported_pyproject_bytes() -> bytes:
    """The supported-normal-form pyproject (SPEC §1.4.1; T20.1 matrix
    shape plus the pytest-8 ``pythonpath`` ini option that makes the
    ``src/`` layout importable under profile v1's frozen environment —
    the frozen fixture bytes are T02.1 evidence and cannot change)."""
    return (
        b"[project]\n"
        b'name = "vesper-fixture"\n'
        b'version = "0.1.0"\n'
        b'requires-python = ">=3.12,<3.13"\n'
        b"\n"
        b"[tool.pytest.ini_options]\n"
        b'testpaths = ["tests"]\n'
        b'pythonpath = ["src"]\n'
        b"\n"
        b"[tool.ruff]\n"
        b"line-length = 88\n"
        b"\n"
        b"[tool.mypy]\n"
        b'python_version = "3.12"\n'
        b"strict = true\n"
    )


def _workspace_files() -> tuple[tuple[str, bytes], ...]:
    fixture = _repo_root() / "reference" / "fixture"
    return (
        ("pyproject.toml", _supported_pyproject_bytes()),
        ("requirements.lock", (fixture / "requirements.lock").read_bytes()),
        (
            "src/vesper_fixture/calculator.py",
            (fixture / "src/vesper_fixture/calculator.py").read_bytes(),
        ),
        (
            "tests/test_calculator.py",
            (fixture / "tests/test_calculator.py").read_bytes(),
        ),
    )


def _supported_snapshot(
    extra_files: tuple[tuple[str, bytes], ...] = (),
) -> SnapshotTreeV1:
    """One sealed supported-normal-form Snapshot (T10.2 conventions)."""
    store = ContentObjectStore()
    rows: list[SealedSnapshotInputFileV1] = []
    for rel, raw in (*_workspace_files(), *extra_files):
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
    policy_digest = _policy_digest()
    return SnapshotTreeV1(
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


def _baseline_plan(
    snapshot: SnapshotTreeV1,
) -> BaselineCheckPlanV1:
    manifest = load_reference_profile(_packaged_manifest_bytes())
    adapter = PythonProjectAdapterV1(manifest)
    static = adapter.detect_static(snapshot, manifest)
    assert static.kind == "SUPPORTED", static.reasons
    return adapter.build_baseline_plan(
        static, TargetTestIdSequenceV1(target_test_ids=(_ADD,))
    )


@dataclass(frozen=True)
class BaselineFixture:
    """The sealed supported project and its frozen plan.

    ``plan_with_mismatched_target_fingerprints`` is the same frozen plan
    (a plan carries no fingerprints — the mismatch is scripted by the
    ``executor`` fixture, whose full-run and target-rerun target failures
    differ); ``unbound_snapshot`` is a different Snapshot identity for the
    static-binding rejection row.
    """

    plan_with_mismatched_target_fingerprints: BaselineCheckPlanV1
    snapshot: SnapshotTreeV1
    plan: BaselineCheckPlanV1
    unbound_snapshot: SnapshotTreeV1


@pytest.fixture
def baseline_fixture() -> BaselineFixture:
    snapshot = _supported_snapshot()
    plan = _baseline_plan(snapshot)
    unbound = _supported_snapshot(extra_files=(("extra.txt", b"x\n"),))
    return BaselineFixture(
        plan_with_mismatched_target_fingerprints=plan,
        snapshot=snapshot,
        plan=plan,
        unbound_snapshot=unbound,
    )


# ---------------------------------------------------------------------------
# Scripted report documents (the closed evidence the fake executor serves)
# ---------------------------------------------------------------------------


def _absent() -> dict[str, str]:
    return {"kind": "ABSENT"}


def _present_text(value: str) -> dict[str, object]:
    return {"kind": "PRESENT", "value": value}


def _exception_document(
    exception_type: str = "AssertionError",
    normalized_message: str = "assert 0 == 4",
    assertion_diff: str | None = "assert 0 == 4\n  where 0 = add(2, 2)",
    frames: tuple[tuple[str, str, int], ...] = (
        ("tests/test_calculator.py", "test_add_returns_sum", 5),
    ),
) -> dict[str, object]:
    return {
        "exception_type": exception_type,
        "normalized_message": normalized_message,
        "normalized_assertion_diff": (
            _present_text(assertion_diff) if assertion_diff is not None else _absent()
        ),
        "project_frames": [
            {
                "relative_path": relative_path,
                "function_name": function_name,
                "line_number": line_number,
            }
            for relative_path, function_name, line_number in frames
        ],
    }


def _event(sequence: int, event_type: str, **fields: object) -> dict[str, object]:
    event: dict[str, object] = {"sequence": sequence, "event_type": event_type}
    for name in (
        "node_id",
        "phase",
        "outcome",
        "wasxfail",
        "exception",
        "display_summary",
    ):
        event[name] = fields.pop(name, _absent())
    if fields:
        raise AssertionError(f"unknown event field: {sorted(fields)}")
    return event


def _phase_event(
    sequence: int,
    node_id: str,
    phase: str,
    outcome: str,
    exception: dict[str, object] | None = None,
) -> dict[str, object]:
    fields: dict[str, object] = {
        "node_id": _present_text(node_id),
        "phase": {"kind": "PRESENT", "value": phase},
        "outcome": {"kind": "PRESENT", "value": outcome},
    }
    if exception is not None:
        fields["exception"] = {"kind": "PRESENT", "value": exception}
    return _event(sequence, "TEST_PHASE", **fields)


def _evidence_raw(
    *,
    run_kind: str,
    planned: tuple[str, ...],
    collected: tuple[str, ...],
    events: list[dict[str, object]],
    pytest_exit_code: int,
    report_plugin_version: str = _PLUGIN_VERSION,
) -> bytes:
    """One canonical GATEEV1 report document (the exact §0.1 document form
    the parser consumes)."""
    body: dict[str, object] = {
        "schema_version": 1,
        "report_plugin_version": report_plugin_version,
        "run_kind": run_kind,
        "planned_node_ids": list(planned),
        "collected_node_ids": list(collected),
        "events": events,
        "pytest_exit_code": pytest_exit_code,
        "event_count": len(events),
        "normal_end_marker": True,
    }
    digest = hashlib.sha256(
        b"VesperCode\x00PytestEvidenceV1\x001\x00"
        + json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    document = {**body, "integrity_digest": digest}
    return (
        "GATEEV1:"
        + json.dumps(
            document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    ).encode("utf-8")


def _collect_events(
    node_ids: tuple[str, ...],
    session_error: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    events: list[dict[str, object]] = [_event(1, "SESSION_START")]
    for index, node_id in enumerate(node_ids, start=2):
        events.append(_event(index, "COLLECTION_ITEM", node_id=_present_text(node_id)))
    if session_error is not None:
        events.append(_event(len(events) + 1, "SESSION_ERROR", exception=session_error))
    events.append(_event(len(events) + 1, "SESSION_END"))
    return events


def _collect_raw(
    node_ids: tuple[str, ...] = (_ADD, _MULTIPLY),
    session_error: dict[str, object] | None = None,
) -> bytes:
    return _evidence_raw(
        run_kind="COLLECT_ONLY",
        planned=node_ids,
        collected=node_ids,
        events=_collect_events(node_ids, session_error=session_error),
        pytest_exit_code=1 if session_error is not None else 0,
    )


def _node_phase_events(
    node_id: str,
    start: int,
    call_outcome: str,
    call_message: str | None = None,
    frames: tuple[tuple[str, str, int], ...] = (
        ("tests/test_calculator.py", "test_add_returns_sum", 5),
    ),
) -> tuple[list[dict[str, object]], int]:
    """One node's TEST_PHASE events in the production reporter shape:
    the reporter emits one TEST_PHASE event per phase (SETUP/CALL/
    TEARDOWN), so an executed node carries three events; a skipped node
    carries the SETUP SKIP event followed by the TEARDOWN PASS report
    (pytest's runtestprotocol still runs teardown after a setup skip)."""
    if call_outcome == "SKIP":
        return [
            _phase_event(start, node_id, "SETUP", "SKIP"),
            _phase_event(start + 1, node_id, "TEARDOWN", "PASS"),
        ], start + 2
    events = [_phase_event(start, node_id, "SETUP", "PASS")]
    if call_outcome == "FAIL":
        events.append(
            _phase_event(
                start + 1,
                node_id,
                "CALL",
                "FAIL",
                exception=_exception_document(
                    normalized_message=call_message or "assert 0 == 4",
                    frames=frames,
                ),
            )
        )
    else:
        events.append(_phase_event(start + 1, node_id, "CALL", call_outcome))
    events.append(_phase_event(start + 2, node_id, "TEARDOWN", "PASS"))
    return events, start + 3


def _full_events(
    add_outcome: str = "FAIL",
    add_message: str = "assert 0 == 4",
    multiply_outcome: str = "PASS",
    session_error: dict[str, object] | None = None,
    deselected_node: str | None = None,
) -> list[dict[str, object]]:
    events: list[dict[str, object]] = [_event(1, "SESSION_START")]
    events.append(_event(2, "COLLECTION_ITEM", node_id=_present_text(_ADD)))
    events.append(_event(3, "COLLECTION_ITEM", node_id=_present_text(_MULTIPLY)))
    index = 4
    if session_error is not None:
        events.append(_event(index, "SESSION_ERROR", exception=session_error))
        index += 1
    if deselected_node is not None:
        events.append(
            _event(index, "DESELECTED", node_id=_present_text(deselected_node))
        )
        index += 1
    add_events, index = _node_phase_events(
        _ADD, index, add_outcome, call_message=add_message
    )
    events.extend(add_events)
    multiply_events, index = _node_phase_events(
        _MULTIPLY,
        index,
        multiply_outcome,
        call_message="assert 3 * 4 == 12",
        frames=(("tests/test_calculator.py", "test_multiply_returns_product", 9),),
    )
    events.extend(multiply_events)
    events.append(_event(index, "SESSION_END"))
    return events


def _full_raw(
    add_outcome: str = "FAIL",
    add_message: str = "assert 0 == 4",
    multiply_outcome: str = "PASS",
    session_error: dict[str, object] | None = None,
    deselected_node: str | None = None,
) -> bytes:
    failed = (
        add_outcome == "FAIL"
        or multiply_outcome == "FAIL"
        or session_error is not None
        or deselected_node is not None
    )
    return _evidence_raw(
        run_kind="FULL_PYTEST",
        planned=(_ADD, _MULTIPLY),
        collected=(_ADD, _MULTIPLY),
        events=_full_events(
            add_outcome=add_outcome,
            add_message=add_message,
            multiply_outcome=multiply_outcome,
            session_error=session_error,
            deselected_node=deselected_node,
        ),
        pytest_exit_code=1 if failed else 0,
    )


def _target_events(message: str = "assert 0 == 4") -> list[dict[str, object]]:
    events: list[dict[str, object]] = [
        _event(1, "SESSION_START"),
        _event(2, "COLLECTION_ITEM", node_id=_present_text(_ADD)),
    ]
    node_events, index = _node_phase_events(_ADD, 3, "FAIL", call_message=message)
    events.extend(node_events)
    events.append(_event(index, "SESSION_END"))
    return events


def _target_raw(message: str = "assert 0 == 4") -> bytes:
    return _evidence_raw(
        run_kind="TARGET_TESTS",
        planned=(_ADD,),
        collected=(_ADD,),
        events=_target_events(message=message),
        pytest_exit_code=1,
    )


def _ruff_clean_raw() -> bytes:
    return b"All checks passed!\n"


def _ruff_failed_raw() -> bytes:
    return b"F401 unused import\n --> tests/test_calculator.py:1:1\nFound 1 error.\n"


def _mypy_clean_raw() -> bytes:
    return b"Success: no issues found in 2 source files\n"


def _document_digest(raw: bytes) -> str:
    """The integrity digest of one scripted GATEEV1 document."""
    text = raw.decode("utf-8")
    assert text.startswith("GATEEV1:")
    return str(json.loads(text[len("GATEEV1:") :])["integrity_digest"])


# ---------------------------------------------------------------------------
# Scripted docker executor (the T18.2 fake-client pattern)
# ---------------------------------------------------------------------------


def _frame(stream_id: int, payload: bytes) -> bytes:
    """One docker attach stream frame (8-byte header + payload)."""
    return struct.pack(">BxxxL", stream_id, len(payload)) + payload


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
        self, container_id: str, attrs: dict[str, object], exit_code: int
    ) -> None:
        self.id = container_id
        self.attrs = attrs
        self._exit_code = exit_code
        self.stopped_exact: list[str] = []
        self.killed_exact: list[str] = []

    def start(self) -> None:
        return None

    def stop(self, timeout: float | None = None) -> None:
        self.stopped_exact.append(self.id)
        self.attrs = {**self.attrs, "State": {"Running": False}}

    def kill(self) -> None:
        self.killed_exact.append(self.id)
        self.attrs = {**self.attrs, "State": {"Running": False}}

    def reload(self) -> None:
        return None

    def wait(self, timeout: float | None = None) -> dict[str, object]:
        if self.stopped_exact or self.killed_exact:
            return {"StatusCode": 137}
        return {"StatusCode": self._exit_code}


class _Script:
    """One scripted Baseline: the raw output of every check plus optional
    execution failures (``timeout`` checks spin the attach stream silent;
    ``create_failure`` checks make container creation raise)."""

    def __init__(
        self,
        *,
        collect1: bytes,
        collect2: bytes,
        full: bytes,
        target: bytes,
        ruff: bytes,
        mypy: bytes,
        timeout_checks: tuple[str, ...] = (),
        create_failure_checks: tuple[str, ...] = (),
    ) -> None:
        self.collect1 = collect1
        self.collect2 = collect2
        self.full = full
        self.target = target
        self.ruff = ruff
        self.mypy = mypy
        self.timeout_checks = set(timeout_checks)
        self.create_failure_checks = set(create_failure_checks)
        self._collect_count = 0

    def for_command(self, command: list[str]) -> tuple[bytes, int, str]:
        """(stdout bytes, exit code, mode) for one frozen argv."""
        if command[0] == "ruff":
            check = "ruff"
            stdout = self.ruff
            exit_code = 0
        elif command[0] == "mypy":
            check = "mypy"
            stdout = self.mypy
            exit_code = 0
        elif "--collect-only" in command:
            self._collect_count += 1
            check = "collect"
            stdout = self.collect1 if self._collect_count == 1 else self.collect2
            exit_code = 0
        elif command[-1] == "/workspace":
            check = "full"
            stdout = self.full
            exit_code = 1
        else:
            check = "target"
            stdout = self.target
            exit_code = 1
        if check in self.timeout_checks:
            return stdout, exit_code, "timeout"
        if check in self.create_failure_checks:
            return stdout, exit_code, "create_failure"
        return stdout, exit_code, "ok"


class _FakeAPIClient:
    def __init__(self, client: "_FakeClient") -> None:
        self._client = client

    def _url(self, path: str, *args: object) -> str:
        return path

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
        return self._client._current_socket()


class _FakeClient:
    def __init__(self, script: _Script) -> None:
        self._script = script
        self.api = _FakeAPIClient(self)
        self._created = 0
        self._pending: tuple[bytes, int, str] | None = None

    @property
    def containers(self) -> "_FakeClient":
        return self

    def create(self, **kwargs: object) -> _FakeContainer:
        self._created += 1
        command_value = kwargs.get("command")
        assert isinstance(command_value, list)
        command = [str(argument) for argument in command_value]
        self._pending = self._script.for_command(command)
        stdout, exit_code, mode = self._pending
        if mode == "create_failure":
            raise RuntimeError("scripted container creation failure")
        return _FakeContainer(
            f"fake-baseline-{self._created}",
            _attrs_from_kwargs(kwargs),
            exit_code,
        )

    def _current_socket(self) -> _FakeStreamSocket:
        assert self._pending is not None
        stdout, _exit_code, mode = self._pending
        return _FakeStreamSocket([_frame(1, stdout)], timeout_forever=mode == "timeout")


def _attrs_from_kwargs(kwargs: dict[str, object]) -> dict[str, object]:
    mounts_value = kwargs.get("mounts")
    assert isinstance(mounts_value, list) and mounts_value
    first = mounts_value[0]
    # docker.types.Mount is a dict with capitalized keys (Target/Source/...).
    source = (
        first.get("Source") if isinstance(first, dict) else getattr(first, "Source")
    )
    environment = kwargs["environment"]
    assert isinstance(environment, list)
    cap_drop = kwargs["cap_drop"]
    assert isinstance(cap_drop, list)
    tmpfs = kwargs["tmpfs"]
    assert isinstance(tmpfs, dict)
    return {
        "Image": kwargs["image"],
        "Config": {
            "User": kwargs["user"],
            "WorkingDir": kwargs["working_dir"],
            "Env": list(environment),
        },
        "HostConfig": {
            "NetworkMode": kwargs["network_mode"],
            "ReadonlyRootfs": kwargs["read_only"],
            "CapDrop": list(cap_drop),
            "Tmpfs": tmpfs,
            "NanoCpus": kwargs["nano_cpus"],
            "Memory": kwargs["mem_limit"],
            "PidsLimit": kwargs["pids_limit"],
            "Mounts": [
                {
                    "Type": "bind",
                    "Target": "/workspace",
                    "ReadOnly": True,
                    "Source": source,
                }
            ],
        },
        "State": {"Running": False},
    }


def _remove_leftover_baseline_bases() -> None:
    """Dispose of every per-run baseline base the residue rows preserve."""
    for entry in Path(tempfile.gettempdir()).iterdir():
        if entry.is_dir() and entry.name.startswith("vesper-baseline-"):
            shutil.rmtree(entry, ignore_errors=True)


def _executor_for(script: _Script, timeout_seconds: float = 60.0) -> DockerExecutor:
    return DockerExecutor(
        timeout_seconds=timeout_seconds, client_factory=lambda: _FakeClient(script)
    )


def _stable_script() -> _Script:
    return _Script(
        collect1=_collect_raw(),
        collect2=_collect_raw(),
        full=_full_raw(),
        target=_target_raw(),
        ruff=_ruff_clean_raw(),
        mypy=_mypy_clean_raw(),
    )


@pytest.fixture
def executor() -> DockerExecutor:
    """The exact-RED executor: the full-run target failure and the
    target-rerun failure normalize to different fingerprints."""
    script = _Script(
        collect1=_collect_raw(),
        collect2=_collect_raw(),
        full=_full_raw(add_message="assert 0 == 4"),
        target=_target_raw(message="assert 0 == 3"),
        ruff=_ruff_clean_raw(),
        mypy=_mypy_clean_raw(),
    )
    return _executor_for(script)


# ---------------------------------------------------------------------------
# Exact RED test (copied verbatim from the task card)
# ---------------------------------------------------------------------------


def test_unstable_target_fingerprint_creates_no_manifest(
    baseline_fixture: BaselineFixture,
    executor: DockerExecutor,
) -> None:
    result = run_baseline(
        baseline_fixture.plan_with_mismatched_target_fingerprints,
        baseline_fixture.snapshot,
        executor,
    )
    assert isinstance(result, BaselineBlockedV1)
    assert result.reason == "BASELINE_UNSTABLE"


# ---------------------------------------------------------------------------
# Publication matrix (PLAN registry row 20.B as the operative authority)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _MatrixRow:
    expected: str | None
    build: Callable[
        [BaselineFixture], tuple[BaselineCheckPlanV1, SnapshotTreeV1, DockerExecutor]
    ]


def _row_collection_drift(
    fixture: BaselineFixture,
) -> tuple[BaselineCheckPlanV1, SnapshotTreeV1, DockerExecutor]:
    script = _Script(
        collect1=_collect_raw(),
        collect2=_collect_raw(node_ids=(_ADD,)),
        full=_full_raw(),
        target=_target_raw(),
        ruff=_ruff_clean_raw(),
        mypy=_mypy_clean_raw(),
    )
    return fixture.plan, fixture.snapshot, _executor_for(script)


def _row_empty_collection(
    fixture: BaselineFixture,
) -> tuple[BaselineCheckPlanV1, SnapshotTreeV1, DockerExecutor]:
    script = _Script(
        collect1=_collect_raw(node_ids=()),
        collect2=_collect_raw(node_ids=()),
        full=_full_raw(),
        target=_target_raw(),
        ruff=_ruff_clean_raw(),
        mypy=_mypy_clean_raw(),
    )
    return fixture.plan, fixture.snapshot, _executor_for(script)


def _row_forbidden_skip(
    fixture: BaselineFixture,
) -> tuple[BaselineCheckPlanV1, SnapshotTreeV1, DockerExecutor]:
    script = _Script(
        collect1=_collect_raw(),
        collect2=_collect_raw(),
        full=_full_raw(multiply_outcome="SKIP"),
        target=_target_raw(),
        ruff=_ruff_clean_raw(),
        mypy=_mypy_clean_raw(),
    )
    return fixture.plan, fixture.snapshot, _executor_for(script)


def _row_non_target_failure(
    fixture: BaselineFixture,
) -> tuple[BaselineCheckPlanV1, SnapshotTreeV1, DockerExecutor]:
    script = _Script(
        collect1=_collect_raw(),
        collect2=_collect_raw(),
        full=_full_raw(multiply_outcome="FAIL"),
        target=_target_raw(),
        ruff=_ruff_clean_raw(),
        mypy=_mypy_clean_raw(),
    )
    return fixture.plan, fixture.snapshot, _executor_for(script)


def _row_target_pass(
    fixture: BaselineFixture,
) -> tuple[BaselineCheckPlanV1, SnapshotTreeV1, DockerExecutor]:
    script = _Script(
        collect1=_collect_raw(),
        collect2=_collect_raw(),
        full=_full_raw(add_outcome="PASS"),
        target=_target_raw(),
        ruff=_ruff_clean_raw(),
        mypy=_mypy_clean_raw(),
    )
    return fixture.plan, fixture.snapshot, _executor_for(script)


def _row_fingerprint_drift(
    fixture: BaselineFixture,
) -> tuple[BaselineCheckPlanV1, SnapshotTreeV1, DockerExecutor]:
    script = _Script(
        collect1=_collect_raw(),
        collect2=_collect_raw(),
        full=_full_raw(add_message="assert 0 == 4"),
        target=_target_raw(message="assert 0 == 3"),
        ruff=_ruff_clean_raw(),
        mypy=_mypy_clean_raw(),
    )
    return fixture.plan, fixture.snapshot, _executor_for(script)


def _row_deselected_node(
    fixture: BaselineFixture,
) -> tuple[BaselineCheckPlanV1, SnapshotTreeV1, DockerExecutor]:
    script = _Script(
        collect1=_collect_raw(),
        collect2=_collect_raw(),
        full=_full_raw(deselected_node=_ADD),
        target=_target_raw(),
        ruff=_ruff_clean_raw(),
        mypy=_mypy_clean_raw(),
    )
    return fixture.plan, fixture.snapshot, _executor_for(script)


def _row_incomplete_report(
    fixture: BaselineFixture,
) -> tuple[BaselineCheckPlanV1, SnapshotTreeV1, DockerExecutor]:
    script = _Script(
        collect1=b"not a report channel",
        collect2=_collect_raw(),
        full=_full_raw(),
        target=_target_raw(),
        ruff=_ruff_clean_raw(),
        mypy=_mypy_clean_raw(),
    )
    return fixture.plan, fixture.snapshot, _executor_for(script)


def _row_static_binding(
    fixture: BaselineFixture,
) -> tuple[BaselineCheckPlanV1, SnapshotTreeV1, DockerExecutor]:
    script = _stable_script()
    return fixture.plan, fixture.unbound_snapshot, _executor_for(script)


def _row_timeout(
    fixture: BaselineFixture,
) -> tuple[BaselineCheckPlanV1, SnapshotTreeV1, DockerExecutor]:
    script = _Script(
        collect1=_collect_raw(),
        collect2=_collect_raw(),
        full=_full_raw(),
        target=_target_raw(),
        ruff=_ruff_clean_raw(),
        mypy=_mypy_clean_raw(),
        timeout_checks=("collect",),
    )
    return fixture.plan, fixture.snapshot, _executor_for(script, timeout_seconds=0.2)


def _row_ruff_failure(
    fixture: BaselineFixture,
) -> tuple[BaselineCheckPlanV1, SnapshotTreeV1, DockerExecutor]:
    script = _Script(
        collect1=_collect_raw(),
        collect2=_collect_raw(),
        full=_full_raw(),
        target=_target_raw(),
        ruff=_ruff_failed_raw(),
        mypy=_mypy_clean_raw(),
    )
    return fixture.plan, fixture.snapshot, _executor_for(script)


def _row_session_error(
    fixture: BaselineFixture,
) -> tuple[BaselineCheckPlanV1, SnapshotTreeV1, DockerExecutor]:
    session_error: dict[str, object] = {
        "kind": "PRESENT",
        "value": _exception_document(
            exception_type="ModuleNotFoundError",
            normalized_message="import error",
            assertion_diff=None,
        ),
    }
    script = _Script(
        collect1=_collect_raw(session_error=session_error),
        collect2=_collect_raw(session_error=session_error),
        full=_full_raw(session_error=session_error),
        target=_target_raw(),
        ruff=_ruff_clean_raw(),
        mypy=_mypy_clean_raw(),
    )
    return fixture.plan, fixture.snapshot, _executor_for(script)


def _row_cleanup_residue(
    fixture: BaselineFixture,
) -> tuple[BaselineCheckPlanV1, SnapshotTreeV1, DockerExecutor]:
    script = _stable_script()
    return fixture.plan, fixture.snapshot, _executor_for(script)


def _cleanup_residue_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_finalize(*args: object, **kwargs: object) -> ExecutionCleanupResultV1:
        return ExecutionCleanupResultV1(
            schema_version=1,
            container_removed=False,
            materialization_removed=True,
            workspace_unchanged=True,
            residual_artifact=ArtifactRefV1(
                artifact_id="container:fake-baseline-1",
                digest=DigestV1(value="a" * 64),
            ),
        )

    monkeypatch.setattr(baseline_module, "finalize_execution", fake_finalize)


def _row_stable(
    fixture: BaselineFixture,
) -> tuple[BaselineCheckPlanV1, SnapshotTreeV1, DockerExecutor]:
    return fixture.plan, fixture.snapshot, _executor_for(_stable_script())


_MATRIX_ROWS: tuple[
    tuple[str, _MatrixRow, Callable[[pytest.MonkeyPatch], None] | None], ...
] = (
    (
        "collection-drift",
        _MatrixRow(expected="RUNTIME_PROFILE_VIOLATION", build=_row_collection_drift),
        None,
    ),
    (
        "empty-collection",
        _MatrixRow(expected="RUNTIME_PROFILE_VIOLATION", build=_row_empty_collection),
        None,
    ),
    (
        "forbidden-skip-state",
        _MatrixRow(expected="BASELINE_UNSTABLE", build=_row_forbidden_skip),
        None,
    ),
    (
        "non-target-failure",
        _MatrixRow(expected="BASELINE_UNSTABLE", build=_row_non_target_failure),
        None,
    ),
    (
        "target-pass",
        _MatrixRow(expected="TARGET_NOT_REPRODUCED", build=_row_target_pass),
        None,
    ),
    (
        "full-target-fingerprint-drift",
        _MatrixRow(expected="BASELINE_UNSTABLE", build=_row_fingerprint_drift),
        None,
    ),
    (
        "deselected-node",
        _MatrixRow(expected="BASELINE_UNSTABLE", build=_row_deselected_node),
        None,
    ),
    (
        "incomplete-report",
        _MatrixRow(expected="REPORTER_INVALID", build=_row_incomplete_report),
        None,
    ),
    (
        "static-plan-binding-failure",
        _MatrixRow(expected="TREE_INTEGRITY_FAILED", build=_row_static_binding),
        None,
    ),
    (
        "execution-timeout",
        _MatrixRow(expected="CHECK_TIMEOUT", build=_row_timeout),
        None,
    ),
    (
        "ruff-failure",
        _MatrixRow(expected="CHECK_ERROR", build=_row_ruff_failure),
        None,
    ),
    (
        "check-environment-error",
        _MatrixRow(expected="RUNTIME_PROFILE_VIOLATION", build=_row_session_error),
        None,
    ),
    (
        "cleanup-residue",
        _MatrixRow(expected="EXECUTION_WORKSPACE_MUTATED", build=_row_cleanup_residue),
        _cleanup_residue_setup,
    ),
    (
        "exact-stable-target",
        _MatrixRow(expected=None, build=_row_stable),
        None,
    ),
)


@pytest.mark.parametrize(
    "row_id,row,setup",
    [(row_id, row, setup) for row_id, row, setup in _MATRIX_ROWS],
    ids=[row_id for row_id, _row, _setup in _MATRIX_ROWS],
)
def test_baseline_publication_matrix(
    baseline_fixture: BaselineFixture,
    row_id: str,
    row: _MatrixRow,
    setup: Callable[[pytest.MonkeyPatch], None] | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every blocked row publishes no manifest; only the exact stable
    target publishes one immutable manifest."""
    if setup is not None:
        setup(monkeypatch)
    plan, snapshot, executor = row.build(baseline_fixture)
    result = run_baseline(plan, snapshot, executor)
    if row.expected is not None:
        assert isinstance(result, BaselineBlockedV1)
        assert result.reason == row.expected
        assert result.evidence_refs
        assert all(len(ref) == 64 for ref in result.evidence_refs)
        if row.expected == "RUNTIME_PROFILE_VIOLATION":
            assert isinstance(result.violation_kind, PresentV1)
        else:
            assert isinstance(result.violation_kind, AbsentV1)
        # A residue-blocked run preserves the surviving root as mutation
        # evidence (the caller's cleanup layer disposes of it); this test
        # disposes of it so the suite leaves zero residue.
        _remove_leftover_baseline_bases()
        return
    # The stable row: exactly one immutable manifest publishes.
    assert isinstance(result, PassingBaselineV1)
    assert result.collected_node_ids == (_ADD, _MULTIPLY)
    assert result.target_test_ids == (_ADD,)
    assert result.full_pytest_evidence_digest == _document_digest(_full_raw())
    assert result.target_rerun_evidence_digest == _document_digest(_target_raw())
    assert result.collect_only_evidence_digests == (
        _document_digest(_collect_raw()),
        _document_digest(_collect_raw()),
    )
    records = {record.node_id: record for record in result.baseline_test_records}
    assert set(records) == {_ADD, _MULTIPLY}
    assert records[_ADD].status == "FAIL"
    assert isinstance(records[_ADD].failure_fingerprint_digest, PresentV1)
    assert records[_MULTIPLY].status == "PASS"
    assert isinstance(records[_MULTIPLY].failure_fingerprint_digest, AbsentV1)
    manifest = create_validation_manifest(
        result,
        ManifestBindingsV1(
            schema_version=1,
            resource_parameters_digest=baseline_module.compute_resource_parameters_digest(),
            environment_whitelist_digest=baseline_module.compute_environment_whitelist_digest(),
        ),
    )
    assert isinstance(manifest, ValidationManifestV1)
    assert len(manifest.digest) == 64
    assert manifest.target_test_ids == (_ADD,)
    assert manifest.collected_node_ids == (_ADD, _MULTIPLY)
    assert tuple(record.node_id for record in manifest.baseline_test_records) == (
        _ADD,
        _MULTIPLY,
    )
    assert manifest.snapshot_tree_digest == snapshot.root_digest
    # Determinism: the same closed inputs publish the same manifest.
    again = create_validation_manifest(
        result,
        ManifestBindingsV1(
            schema_version=1,
            resource_parameters_digest=baseline_module.compute_resource_parameters_digest(),
            environment_whitelist_digest=baseline_module.compute_environment_whitelist_digest(),
        ),
    )
    assert again.digest == manifest.digest


# ---------------------------------------------------------------------------
# Closed-schema domain tests
# ---------------------------------------------------------------------------


def test_blocked_baseline_requires_exact_violation_presence() -> None:
    from src.vespercode.validation.baseline import (
        BaselineBlockedV1,
        BaselineBlockedReasonV1,
        RuntimeProfileViolationKindV1,
    )
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        BaselineBlockedV1(
            schema_version=1,
            kind="BLOCKED",
            reason="RUNTIME_PROFILE_VIOLATION",
            evidence_refs=("a" * 64,),
            violation_kind=AbsentV1(kind="ABSENT"),
        )
    with pytest.raises(ValidationError):
        BaselineBlockedV1(
            schema_version=1,
            kind="BLOCKED",
            reason="BASELINE_UNSTABLE",
            evidence_refs=("a" * 64,),
            violation_kind=PresentV1(kind="PRESENT", value="COLLECTION_UNSTABLE"),
        )
    with pytest.raises(ValidationError):
        BaselineBlockedV1(
            schema_version=1,
            kind="BLOCKED",
            reason="BASELINE_UNSTABLE",
            evidence_refs=("not-a-digest",),
            violation_kind=AbsentV1(kind="ABSENT"),
        )
    ok = BaselineBlockedV1(
        schema_version=1,
        kind="BLOCKED",
        reason="RUNTIME_PROFILE_VIOLATION",
        evidence_refs=("a" * 64,),
        violation_kind=PresentV1(kind="PRESENT", value="COLLECTION_UNSTABLE"),
    )
    assert ok.reason == "RUNTIME_PROFILE_VIOLATION"
    del BaselineBlockedReasonV1, RuntimeProfileViolationKindV1


def test_baseline_record_state_table_is_closed() -> None:
    from src.vespercode.validation.baseline import BaselineTestRecordV1
    from pydantic import ValidationError

    target = "tests/test_calculator.py::test_add_returns_sum"
    with pytest.raises(ValidationError):
        # ERROR records require a PRESENT non-CALL error phase.
        BaselineTestRecordV1(
            schema_version=1,
            node_id=target,
            status="ERROR",
            error_phase=AbsentV1(kind="ABSENT"),
            failure_fingerprint_digest=AbsentV1(kind="ABSENT"),
        )
    with pytest.raises(ValidationError):
        # ERROR records cannot be in the CALL phase.
        BaselineTestRecordV1(
            schema_version=1,
            node_id=target,
            status="ERROR",
            error_phase=PresentV1(kind="PRESENT", value="CALL"),
            failure_fingerprint_digest=AbsentV1(kind="ABSENT"),
        )
    with pytest.raises(ValidationError):
        # PASS records cannot carry a fingerprint.
        BaselineTestRecordV1(
            schema_version=1,
            node_id=target,
            status="PASS",
            error_phase=AbsentV1(kind="ABSENT"),
            failure_fingerprint_digest=PresentV1(
                kind="PRESENT", value=DigestV1(value="a" * 64)
            ),
        )
    with pytest.raises(ValidationError):
        # Non-ERROR records cannot carry an error phase.
        BaselineTestRecordV1(
            schema_version=1,
            node_id=target,
            status="FAIL",
            error_phase=PresentV1(kind="PRESENT", value="SETUP"),
            failure_fingerprint_digest=AbsentV1(kind="ABSENT"),
        )
    ok = BaselineTestRecordV1(
        schema_version=1,
        node_id=target,
        status="FAIL",
        error_phase=AbsentV1(kind="ABSENT"),
        failure_fingerprint_digest=PresentV1(
            kind="PRESENT", value=DigestV1(value="a" * 64)
        ),
    )
    assert ok.status == "FAIL"


def test_runtime_compatible_result_is_closed() -> None:
    from src.vespercode.validation.baseline import (
        RuntimeBaselineBlockedV1,
        RuntimeCompatibleV1,
    )
    from pydantic import ValidationError

    compatible = RuntimeCompatibleV1(
        schema_version=1,
        status="COMPATIBLE",
        reference_profile_digest="a" * 64,
        evidence_digest="b" * 64,
    )
    assert compatible.status == "COMPATIBLE"
    with pytest.raises(ValidationError):
        RuntimeCompatibleV1(
            schema_version=1,
            status="COMPATIBLE",
            reference_profile_digest="short",
            evidence_digest="b" * 64,
        )
    blocked = RuntimeBaselineBlockedV1(
        schema_version=1,
        status="BASELINE_BLOCKED",
        reason="RUNTIME_PROFILE_VIOLATION",
        violation_kind="COLLECTION_UNSTABLE",
        evidence_refs=("a" * 64,),
    )
    assert blocked.violation_kind == "COLLECTION_UNSTABLE"
    with pytest.raises(ValidationError):
        RuntimeBaselineBlockedV1(
            schema_version=1,
            status="BASELINE_BLOCKED",
            reason="RUNTIME_PROFILE_VIOLATION",
            violation_kind="UNKNOWN_KIND",  # type: ignore[arg-type]
            evidence_refs=("a" * 64,),
        )


def test_passing_baseline_rejects_coerced_profile_version(
    baseline_fixture: BaselineFixture,
) -> None:
    """The published identity fields reject bool/float coercion (the
    T06.1/T05.1 strict-scalar convention, pinned on the closed schema)."""
    from src.vespercode.validation.baseline import PassingBaselineV1
    from pydantic import ValidationError

    result = run_baseline(
        baseline_fixture.plan,
        baseline_fixture.snapshot,
        _executor_for(_stable_script()),
    )
    assert isinstance(result, PassingBaselineV1)
    fields = result.model_dump(mode="python")
    for coerced in (True, 1.0):
        with pytest.raises(ValidationError):
            PassingBaselineV1.model_validate(
                {
                    **fields,
                    "docker_execution_profile_version": coerced,
                }
            )
    with pytest.raises(ValidationError):
        PassingBaselineV1.model_validate(
            {**fields, "docker_execution_profile_version": "1"}
        )
