"""T21.1 legacy step 21.B: complete formal check execution tests.

``execute_formal_plan`` invokes every frozen request exactly once in plan
order through a fresh Task 18 execution boundary (fresh identity-bound
materialization root + sealed cleanup per check) and collects the
complete ordered raw/check/teardown/cleanup/timeout/residual evidence, so
missing, duplicate, or partial execution remains explicit and
non-success.  The spy executor scripts every closed execution branch; the
real frozen-container path lives in ``test_reference_formal_validation.py``
(GREEN-1..GREEN-4).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("pydantic")

from vespercode.candidate.final_diff import recompute_final_diff
from vespercode.candidate.identity import bind_revision_identity
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.evidence import ArtifactRefV1, DigestV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.execution.cleanup import ExecutionCleanupResultV1
from vespercode.execution.docker_executor import RawExecutionResultV1
from vespercode.execution.docker_profile import ExecutionRequestV1
from vespercode.execution.materialization import MaterializedCandidateV1
from vespercode.profiles.reference import (
    ReferenceProfileManifestV1,
    load_reference_profile,
)
from vespercode.trees.candidate import root_candidate_revision
from vespercode.trees.content_store import ContentObjectRefV1, ContentObjectStore
from vespercode.trees.snapshot import (
    SealedSnapshotInputFileV1,
    SnapshotDirectoryEntryV1,
    SnapshotEntryV1,
    SnapshotFileEntryV1,
    SnapshotTreeV1,
    _root_digest,
)
from vespercode.trees.text_classifier import TextMetadataV1, classify_supported_text
from vespercode.validation.baseline import (
    BaselineTestRecordV1,
    PassingBaselineV1,
    RuntimeCompatibleV1,
    compute_environment_whitelist_digest,
    compute_protected_artifact_set_digest,
    compute_resource_parameters_digest,
)
from vespercode.validation.formal_execution import (
    FormalRequestEvidenceV1,
    FormalRequestRejectionV1,
    FormalValidationEvidenceV1,
    execute_formal_plan,
    formal_validation_evidence_digest,
)
from vespercode.validation.formal_plan import (
    FormalValidationPlanV1,
    build_formal_validation_plan,
)
from vespercode.validation.manifest import (
    ManifestBindingsV1,
    ValidationManifestV1,
    create_validation_manifest,
)

pytestmark = pytest.mark.docker_integration

_ADD = "tests/test_calculator.py::test_add_returns_sum"
_MULTIPLY = "tests/test_calculator.py::test_multiply_returns_product"
_A = "a" * 64
_B = "b" * 64
_C = "c" * 64
_D = "d" * 64
_E = "e" * 64
_F = "f" * 64
_ZERO = "0" * 64
_PLUGIN_VERSION = "1"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _frozen_manifest() -> ReferenceProfileManifestV1:
    return load_reference_profile(
        (
            _repo_root()
            / "src"
            / "vespercode"
            / "profiles"
            / "builtin"
            / "reference-profile-v1.json"
        ).read_bytes()
    )


def _supported_pyproject_bytes() -> bytes:
    """The supported-normal-form pyproject (SPEC §1.4.1 normal form;
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
    """The supported-normal-form workspace bytes (real fixture files
    byte-identical to the T02.1 evidence plus the seeded report plugin)."""
    fixture = _repo_root() / "reference" / "fixture"
    plugin = _repo_root() / "src" / "vespercode" / "validation" / "pytest_reporter.py"
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
        ("vespercode/__init__.py", b""),
        ("vespercode/validation/__init__.py", b""),
        ("vespercode/validation/pytest_reporter.py", plugin.read_bytes()),
    )


def _sealed_snapshot() -> SnapshotTreeV1:
    """One sealed Snapshot over the supported workspace bytes (T10.2)."""
    store = ContentObjectStore()
    rows: list[SealedSnapshotInputFileV1] = []
    for rel, raw in _workspace_files():
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
        text_profile: PresentV1[TextMetadataV1] | AbsentV1 = (
            classification.text_profile
            if classification.kind == "TEXT_FILE"
            else AbsentV1(kind="ABSENT")
        )
        entries.append(
            SnapshotFileEntryV1(
                kind=classification.kind,
                path=row.path,
                size_bytes=row.byte_count,
                content_ref=ref,
                text_profile=text_profile,
            )
        )
    policy_digest = _frozen_manifest().editable_path_policy.digest
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


def _record(
    node_id: str,
    status: str,
    *,
    fingerprint: str | None = None,
) -> BaselineTestRecordV1:
    return BaselineTestRecordV1(
        schema_version=1,
        node_id=node_id,
        status=status,  # type: ignore[arg-type]
        error_phase=AbsentV1(kind="ABSENT"),
        failure_fingerprint_digest=(
            PresentV1(kind="PRESENT", value=DigestV1(value=fingerprint))
            if fingerprint is not None
            else AbsentV1(kind="ABSENT")
        ),
    )


def _passing_baseline(snapshot: SnapshotTreeV1) -> PassingBaselineV1:
    frozen = _frozen_manifest()
    return PassingBaselineV1(
        schema_version=1,
        kind="PASSING",
        plan_digest=_A,
        check_plan_version=frozen.check_plan_version,
        adapter_version="1",
        python_version=frozen.python_version,
        pytest_version=frozen.pytest_version,
        report_plugin_version=frozen.report_plugin_version,
        ruff_version=frozen.ruff_version,
        mypy_version=frozen.mypy_version,
        docker_image_digest=frozen.docker_image_digest,
        docker_execution_profile_version=1,
        reference_profile_digest=frozen.digest,
        snapshot_root_digest=snapshot.root_digest,
        repository_policy_digest=snapshot.repository_policy_digest,
        target_test_ids=(_ADD,),
        collected_node_ids=(_ADD, _MULTIPLY),
        collect_only_evidence_digests=(_A, _A),
        full_pytest_evidence_digest=_B,
        target_rerun_evidence_digest=_C,
        ruff_result_digest=_D,
        mypy_result_digest=_E,
        baseline_test_records=(
            _record(_ADD, "FAIL", fingerprint=_F),
            _record(_MULTIPLY, "PASS"),
        ),
        protected_artifact_set_digest=compute_protected_artifact_set_digest(snapshot),
        runtime_compatibility=RuntimeCompatibleV1(
            schema_version=1,
            status="COMPATIBLE",
            reference_profile_digest=frozen.digest,
            evidence_digest=_E,
        ),
    )


def _manifest(snapshot: SnapshotTreeV1) -> ValidationManifestV1:
    """One exact-current Manifest bound to the sealed Snapshot and the
    frozen reference profile."""
    return create_validation_manifest(
        _passing_baseline(snapshot),
        ManifestBindingsV1(
            schema_version=1,
            resource_parameters_digest=compute_resource_parameters_digest(),
            environment_whitelist_digest=compute_environment_whitelist_digest(),
        ),
    )


def _frozen_plan() -> FormalValidationPlanV1:
    """One complete frozen formal plan over the supported workspace."""
    snapshot = _sealed_snapshot()
    manifest = _manifest(snapshot)
    store = ContentObjectStore()
    for _path, raw in snapshot.file_bytes:
        store.put(raw)
    revision = root_candidate_revision(snapshot, store)
    diff = recompute_final_diff(
        snapshot, revision.tree, _frozen_manifest().editable_path_policy
    )
    bound = bind_revision_identity(revision, diff.digest)
    result = build_formal_validation_plan(manifest, bound, diff)
    assert isinstance(result, FormalValidationPlanV1)
    return result


# ---------------------------------------------------------------------------
# Scripted report documents (the closed evidence the spy serves)
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
    """One canonical GATEEV1 report document (the exact §0.1 document
    form the parser consumes)."""
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


def _collect_raw() -> bytes:
    events: list[dict[str, object]] = [_event(1, "SESSION_START")]
    for index, node_id in enumerate((_ADD, _MULTIPLY), start=2):
        events.append(_event(index, "COLLECTION_ITEM", node_id=_present_text(node_id)))
    events.append(_event(len(events) + 1, "SESSION_END"))
    return _evidence_raw(
        run_kind="COLLECT_ONLY",
        planned=(_ADD, _MULTIPLY),
        collected=(_ADD, _MULTIPLY),
        events=events,
        pytest_exit_code=0,
    )


def _full_raw(add_outcome: str = "FAIL") -> bytes:
    """The production-reporter-shape full run: one TEST_PHASE event per
    phase (SETUP/CALL/TEARDOWN)."""
    events: list[dict[str, object]] = [_event(1, "SESSION_START")]
    events.append(_event(2, "COLLECTION_ITEM", node_id=_present_text(_ADD)))
    events.append(_event(3, "COLLECTION_ITEM", node_id=_present_text(_MULTIPLY)))
    index = 4
    add_events, index = _node_phase_events(_ADD, index, add_outcome)
    events.extend(add_events)
    multiply_events, index = _node_phase_events(
        _MULTIPLY,
        index,
        "PASS",
        frames=(("tests/test_calculator.py", "test_multiply_returns_product", 9),),
    )
    events.extend(multiply_events)
    events.append(_event(index, "SESSION_END"))
    return _evidence_raw(
        run_kind="FULL_PYTEST",
        planned=(_ADD, _MULTIPLY),
        collected=(_ADD, _MULTIPLY),
        events=events,
        pytest_exit_code=1 if add_outcome == "FAIL" else 0,
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
    """One node's TEST_PHASE events in the production reporter shape."""
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


def _ruff_clean_raw() -> bytes:
    return b"All checks passed!\n"


def _mypy_clean_raw() -> bytes:
    return b"Success: no issues found in 2 source files\n"


# ---------------------------------------------------------------------------
# Scripted execution port (records every frozen call exactly)
# ---------------------------------------------------------------------------


class _FormalScript:
    """One scripted formal run: the raw output of every request plus
    optional closed execution failures per request id."""

    def __init__(
        self,
        *,
        timeout_requests: tuple[str, ...] = (),
        execution_error_requests: tuple[str, ...] = (),
        empty_requests: tuple[str, ...] = (),
    ) -> None:
        self.timeout_requests = set(timeout_requests)
        self.execution_error_requests = set(execution_error_requests)
        self.empty_requests = set(empty_requests)
        self.raise_requests: set[str] = set()

    def for_request(self, request: ExecutionRequestV1) -> RawExecutionResultV1:
        kind = request.request_id.split("-")[1]
        stdout: bytes
        exit_code: int
        if kind == "COLLECT_ONLY":
            stdout, exit_code = _collect_raw(), 0
        elif kind == "FULL_PYTEST":
            stdout, exit_code = _full_raw(), 1
        elif kind == "RUFF":
            stdout, exit_code = _ruff_clean_raw(), 0
        else:
            stdout, exit_code = _mypy_clean_raw(), 0
        if request.request_id in self.empty_requests:
            stdout, exit_code = b"", 0
        if request.request_id in self.timeout_requests:
            return RawExecutionResultV1(
                schema_version=1,
                request_id=request.request_id,
                container_id=f"fake-formal-{kind.lower()}",
                exit_code=None,
                stdout=stdout,
                stderr=b"",
                output_bytes=len(stdout),
                timed_out=True,
                output_limit_exceeded=False,
                container_stopped=True,
                error_code="CHECK_TIMEOUT",
            )
        if request.request_id in self.execution_error_requests:
            return RawExecutionResultV1(
                schema_version=1,
                request_id=request.request_id,
                container_id="",
                exit_code=None,
                stdout=b"",
                stderr=b"",
                output_bytes=0,
                timed_out=False,
                output_limit_exceeded=False,
                container_stopped=False,
                error_code="CHECK_EXECUTION_ERROR",
            )
        return RawExecutionResultV1(
            schema_version=1,
            request_id=request.request_id,
            container_id=f"fake-formal-{kind.lower()}",
            exit_code=exit_code,
            stdout=stdout,
            stderr=b"",
            output_bytes=len(stdout),
            timed_out=False,
            output_limit_exceeded=False,
            container_stopped=False,
            error_code=None,
        )


class SpyDockerExecutionPortV1:
    """The scripted ``DockerExecutionPortV1``: records every
    (request id, materialized candidate) call in order."""

    def __init__(self, script: _FormalScript) -> None:
        self._script = script
        self.executed: list[tuple[str, MaterializedCandidateV1]] = []

    def execute(
        self,
        request: ExecutionRequestV1,
        candidate: MaterializedCandidateV1,
    ) -> RawExecutionResultV1:
        self.executed.append((request.request_id, candidate))
        if request.request_id in self._script.raise_requests:
            raise RuntimeError("scripted unexpected executor raise")
        return self._script.for_request(request)


@pytest.fixture(scope="module", autouse=True)
def _remove_module_residue() -> Iterator[None]:
    yield
    _remove_executor_containers()


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


@pytest.fixture
def executor() -> SpyDockerExecutionPortV1:
    """The scripted complete formal run (all four checks succeed)."""
    return SpyDockerExecutionPortV1(_FormalScript())


def four_check_plan() -> FormalValidationPlanV1:
    """The complete frozen four-check formal plan."""
    return _frozen_plan()


def test_executor_must_run_every_frozen_request_once(
    executor: SpyDockerExecutionPortV1,
) -> None:
    evidence = execute_formal_plan(four_check_plan(), executor)
    assert evidence.executed_request_ids == four_check_plan().request_ids


def test_every_frozen_request_runs_once_in_order_with_fresh_boundaries(
    executor: SpyDockerExecutionPortV1,
) -> None:
    plan = four_check_plan()
    evidence = execute_formal_plan(plan, executor)
    assert tuple(request_id for request_id, _candidate in executor.executed) == (
        plan.request_ids
    )
    # One fresh identity-bound materialization per request: the roots are
    # all distinct and every call carries the exact frozen candidate
    # tree (the materialization binds the tree digest and the Snapshot).
    roots = [candidate.root_id for _request_id, candidate in executor.executed]
    assert len(set(roots)) == 4
    assert all(
        candidate.candidate_digest == plan.candidate_tree_digest
        and candidate.snapshot_tree_digest == plan.snapshot_tree_digest
        for _request_id, candidate in executor.executed
    )
    # Complete ordered evidence: every request executed, nothing missing
    # or duplicated, and the evidence self-binds its digest.
    assert evidence.complete is True
    assert evidence.missing_request_ids == ()
    assert evidence.duplicate_request_ids == ()
    assert evidence.evidence_digest == formal_validation_evidence_digest(evidence)
    assert tuple(row.request_id for row in evidence.evidence) == plan.request_ids
    # The pytest checks parsed authoritative evidence; the tool checks
    # parsed PASS results.
    assert isinstance(evidence.evidence[0].pytest_evidence, PresentV1)
    assert isinstance(evidence.evidence[1].pytest_evidence, PresentV1)
    assert isinstance(evidence.evidence[2].tool_result, PresentV1)
    assert evidence.evidence[2].tool_result.value.status == "PASS"
    assert isinstance(evidence.evidence[3].tool_result, PresentV1)
    assert evidence.evidence[3].tool_result.value.status == "PASS"


def _evidence(
    plan: FormalValidationPlanV1,
    *,
    executed_request_ids: tuple[str, ...],
    rows: tuple[FormalRequestEvidenceV1, ...],
    missing_request_ids: tuple[str, ...] = (),
    duplicate_request_ids: tuple[str, ...] = (),
) -> FormalValidationEvidenceV1:
    """One closed evidence via the digest two-pass (the model re-validates)."""
    complete = (
        missing_request_ids == ()
        and duplicate_request_ids == ()
        and all(
            isinstance(row.rejection, AbsentV1)
            and row.raw is not None
            and row.raw.error_code is None
            and row.cleanup is not None
            and row.cleanup.container_removed
            and row.cleanup.materialization_removed
            and row.cleanup.workspace_unchanged
            and isinstance(row.parse_error, AbsentV1)
            for row in rows
        )
    )
    document = {
        "schema_version": 1,
        "plan_digest": plan.digest,
        "executed_request_ids": executed_request_ids,
        "evidence": rows,
        "missing_request_ids": missing_request_ids,
        "duplicate_request_ids": duplicate_request_ids,
        "complete": complete,
    }
    probe = FormalValidationEvidenceV1.model_construct(**document)  # type: ignore[arg-type]
    return FormalValidationEvidenceV1.model_validate(
        {**document, "evidence_digest": formal_validation_evidence_digest(probe)}
    )


def test_formal_execution_completeness_matrix() -> None:
    plan = four_check_plan()
    ids = plan.request_ids

    # Row: raw timeout stays explicit and non-success.
    timed_out = execute_formal_plan(
        plan, SpyDockerExecutionPortV1(_FormalScript(timeout_requests=(ids[1],)))
    )
    assert timed_out.executed_request_ids == ids
    assert timed_out.complete is False
    assert isinstance(timed_out.evidence[1].parse_error, PresentV1)
    assert timed_out.evidence[1].parse_error.value == "CHECK_TIMEOUT"

    # Row: raw execution error stays explicit and non-success.
    execution_error = execute_formal_plan(
        plan,
        SpyDockerExecutionPortV1(_FormalScript(execution_error_requests=(ids[2],))),
    )
    assert execution_error.executed_request_ids == ids
    assert execution_error.complete is False
    assert isinstance(execution_error.evidence[2].tool_result, PresentV1)
    assert execution_error.evidence[2].tool_result.value.status == "ERROR"

    # Row: an unparseable report stays explicit and non-success.
    reporter_invalid = execute_formal_plan(
        plan, SpyDockerExecutionPortV1(_FormalScript(empty_requests=(ids[0],)))
    )
    assert reporter_invalid.executed_request_ids == ids
    assert reporter_invalid.complete is False
    assert isinstance(reporter_invalid.evidence[0].parse_error, PresentV1)
    assert reporter_invalid.evidence[0].parse_error.value == "REPORTER_INVALID"

    # Row: an unexpected executor raise is recorded as one closed
    # execution failure (deterministic partial-execution records — the
    # earlier rows are never lost).
    raising_script = _FormalScript()
    raising_script.raise_requests = {ids[2]}
    raising = execute_formal_plan(plan, SpyDockerExecutionPortV1(raising_script))
    assert raising.executed_request_ids == ids
    assert raising.complete is False
    assert raising.evidence[2].raw is not None
    assert raising.evidence[2].raw.error_code == "CHECK_EXECUTION_ERROR"
    assert isinstance(raising.evidence[2].tool_result, PresentV1)
    assert raising.evidence[2].tool_result.value.status == "ERROR"
    assert raising.evidence[0].pytest_evidence is not None

    # Row: a drifted frozen request is rejected before execution and the
    # missing execution stays explicit (zero implicit skips).
    drifted_plan = plan.model_copy(update={"docker_image_digest": _ZERO})
    rejected = execute_formal_plan(
        drifted_plan, SpyDockerExecutionPortV1(_FormalScript())
    )
    assert rejected.executed_request_ids == ()
    assert rejected.missing_request_ids == ids
    assert rejected.complete is False
    assert all(
        isinstance(row.rejection, PresentV1)
        and row.rejection.value.code == "VALIDATION_ENVIRONMENT_CHANGED"
        for row in rejected.evidence
    )

    # The clean rows of one complete run are the base of the
    # model-constructed explicitness rows below.
    spy = SpyDockerExecutionPortV1(_FormalScript())
    complete_evidence = execute_formal_plan(plan, spy)
    assert complete_evidence.complete is True
    rows = complete_evidence.evidence

    # Row: a duplicate execution record stays explicit and non-success.
    duplicated = _evidence(
        plan,
        executed_request_ids=(ids[0], ids[1], ids[1], ids[2], ids[3]),
        rows=(rows[0], rows[1], rows[1], rows[2], rows[3]),
        duplicate_request_ids=(ids[1],),
    )
    assert duplicated.complete is False
    assert duplicated.duplicate_request_ids == (ids[1],)
    assert duplicated.evidence_digest == formal_validation_evidence_digest(duplicated)

    # Row: a missing execution record stays explicit and non-success.
    rejected_row = rows[1].model_copy(
        update={
            "rejection": PresentV1(
                kind="PRESENT",
                value=FormalRequestRejectionV1(
                    schema_version=1,
                    code="TREE_INTEGRITY_FAILED",
                    message="the fresh candidate materialization boundary failed",
                ),
            ),
            "raw": None,
            "cleanup": None,
            "pytest_evidence": AbsentV1(kind="ABSENT"),
            "tool_result": AbsentV1(kind="ABSENT"),
            "parse_error": AbsentV1(kind="ABSENT"),
        }
    )
    missing = _evidence(
        plan,
        executed_request_ids=(ids[0], ids[2], ids[3]),
        rows=(rows[0], rejected_row, rows[2], rows[3]),
        missing_request_ids=(ids[1],),
    )
    assert missing.complete is False
    assert missing.missing_request_ids == (ids[1],)

    # Row: a cleanup-failed (teardown) verdict stays explicit and non-success.
    failed_cleanup = rows[1].model_copy(
        update={
            "cleanup": ExecutionCleanupResultV1(
                schema_version=1,
                container_removed=False,
                materialization_removed=True,
                workspace_unchanged=True,
                residual_artifact=ArtifactRefV1(
                    artifact_id="container",
                    digest=DigestV1(value=_ZERO),
                ),
            )
        }
    )
    residue = _evidence(
        plan,
        executed_request_ids=ids,
        rows=(rows[0], failed_cleanup, rows[2], rows[3]),
    )
    assert residue.complete is False

    # Row: a workspace-drift verdict stays explicit and non-success.
    drifted = rows[1].model_copy(
        update={
            "cleanup": ExecutionCleanupResultV1(
                schema_version=1,
                container_removed=True,
                materialization_removed=True,
                workspace_unchanged=False,
                residual_artifact=ArtifactRefV1(
                    artifact_id="workspace",
                    digest=DigestV1(value=_ZERO),
                ),
            )
        }
    )
    workspace_drift = _evidence(
        plan,
        executed_request_ids=ids,
        rows=(rows[0], drifted, rows[2], rows[3]),
    )
    assert workspace_drift.complete is False

    # Every request executed exactly once in plan order with fresh roots.
    assert [request_id for request_id, _candidate in spy.executed] == list(ids)
    assert len({candidate.root_id for _request_id, candidate in spy.executed}) == 4
