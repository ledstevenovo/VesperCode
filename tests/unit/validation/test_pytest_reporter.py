"""T19.1 legacy step 19.B: production pytest report plugin emission.

The production ``pytest_reporter`` module is loaded explicitly (``-p
vespercode.validation.pytest_reporter``, never entry-point autoload) and
emits exactly one complete ordered ``PytestEvidenceV1`` document through
the fixed ``GATEEV1:`` stdout channel; the parser then proves the channel
is authoritative over exit code and console text.  These tests run real
pytest 8.4.2 subprocesses on seeded projects (the T02.4 gate pattern) and
recover the report channel from the bounded stdout bytes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# The reporter contracts are pydantic runtime models; the hash-locked
# gate toolchain does not install runtime dependencies, so this module
# skips cleanly there instead of failing at collection (formal env runs it
# fully).
pytest.importorskip("pydantic")

from vespercode.validation.pytest_evidence import (
    PytestEvidenceV1,
    PytestReportExpectationV1,
    parse_pytest_evidence,
)

_PLUGIN_MODULE = "vespercode.validation.pytest_reporter"
_PLUGIN_VERSION = "1"
_NODE_ADD = "tests/test_calculator.py::test_add_returns_sum"
_NODE_MULTIPLY = "tests/test_calculator.py::test_multiply_returns_product"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _seed_project(tmp_path: Path) -> Path:
    """One deterministic mini-project with one stable failing test."""
    project = tmp_path / "project"
    (project / "src" / "vesper_fixture").mkdir(parents=True)
    (project / "tests").mkdir(parents=True)
    (project / "pyproject.toml").write_text(
        "[project]\n"
        'name = "vesper-fixture"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.12,<3.13"\n'
        "\n"
        "[tool.pytest.ini_options]\n"
        'testpaths = ["tests"]\n',
        encoding="utf-8",
    )
    (project / "conftest.py").write_text(
        "import os, sys\n"
        "sys.path.insert(0, os.path.join("
        "os.path.dirname(os.path.abspath(__file__)), 'src'))\n",
        encoding="utf-8",
    )
    (project / "src" / "vesper_fixture" / "calculator.py").write_text(
        "def add(left, right):\n"
        "    return left - right\n"
        "def multiply(left, right):\n"
        "    return left * right\n",
        encoding="utf-8",
    )
    (project / "tests" / "test_calculator.py").write_text(
        "from vesper_fixture.calculator import add, multiply\n"
        "def test_add_returns_sum():\n"
        "    assert add(2, 2) == 4\n"
        "def test_multiply_returns_product():\n"
        "    assert multiply(3, 4) == 12\n",
        encoding="utf-8",
    )
    return project


def _run_pytest(
    root: Path,
    *extra_args: str,
) -> subprocess.CompletedProcess[str]:
    argv = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        _PLUGIN_MODULE,
        "-o",
        "cacheprovider=disabled",
        "--rootdir",
        str(root),
        *extra_args,
    ]
    env = os.environ.copy()
    # The installed-wheel import name is ``vespercode...``; the packaged
    # ``src`` tree maps to it directly.
    env["PYTHONPATH"] = str(_repo_root() / "src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONHASHSEED"] = "0"
    env["TZ"] = "UTC"
    env["LC_ALL"] = "C.UTF-8"
    return subprocess.run(
        argv,
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _full_expectation() -> PytestReportExpectationV1:
    return PytestReportExpectationV1(
        schema_version=1,
        run_kind="FULL_PYTEST",
        planned_node_ids=(_NODE_ADD, _NODE_MULTIPLY),
        report_plugin_version=_PLUGIN_VERSION,
    )


def _extract_raw_document(stdout: str) -> dict[str, object]:
    """Extract the raw channel document JSON from the bounded stdout."""
    import json

    prefix = "GATEEV1:"
    start = stdout.index(prefix) + len(prefix)
    document, _end = json.JSONDecoder().raw_decode(stdout, start)
    assert isinstance(document, dict)
    return document


def _extract_outcome(proc: subprocess.CompletedProcess[str]) -> PytestEvidenceV1:
    """Parse the report channel out of the bounded stdout bytes."""
    outcome = parse_pytest_evidence(proc.stdout.encode("utf-8"), _full_expectation())
    assert outcome.error_code is None, proc.stdout
    assert outcome.evidence is not None
    return outcome.evidence


def test_full_run_emits_one_complete_ordered_document(tmp_path: Path) -> None:
    root = _seed_project(tmp_path)
    proc = _run_pytest(root, str(root), "-q")
    assert proc.returncode == 1  # the stable fixture failure
    evidence = _extract_outcome(proc)
    assert evidence.run_kind == "FULL_PYTEST"
    assert evidence.collected_node_ids == (_NODE_ADD, _NODE_MULTIPLY)
    assert evidence.pytest_exit_code == 1
    assert evidence.normal_end_marker is True
    assert [event.event_type for event in evidence.events] == [
        "SESSION_START",
        "COLLECTION_ITEM",
        "COLLECTION_ITEM",
        "TEST_PHASE",
        "TEST_PHASE",
        "TEST_PHASE",
        "TEST_PHASE",
        "TEST_PHASE",
        "TEST_PHASE",
        "SESSION_END",
    ]
    failure = next(
        event
        for event in evidence.events
        if event.event_type == "TEST_PHASE"
        and event.node_id.kind == "PRESENT"
        and event.node_id.value == _NODE_ADD
        and event.outcome.kind == "PRESENT"
        and event.outcome.value == "FAIL"
    )
    assert failure.phase.kind == "PRESENT"
    assert failure.phase.value == "CALL"
    exception = failure.exception
    assert exception.kind == "PRESENT"
    assert exception.value.exception_type == "AssertionError"
    assert "0 == 4" in exception.value.normalized_message
    assert exception.value.project_frames[0].relative_path.value == (
        "tests/test_calculator.py"
    )


def test_assertion_diff_is_captured_for_assertion_failures(tmp_path: Path) -> None:
    root = _seed_project(tmp_path)
    proc = _run_pytest(root, str(root), "-q")
    evidence = _extract_outcome(proc)
    failure = next(
        event
        for event in evidence.events
        if event.event_type == "TEST_PHASE"
        and event.outcome.kind == "PRESENT"
        and event.outcome.value == "FAIL"
    )
    exception = failure.exception
    assert exception.kind == "PRESENT"
    diff = exception.value.normalized_assertion_diff
    assert diff.kind == "PRESENT"
    assert "0 == 4" in diff.value


def test_collect_only_run_emits_collection_kind(tmp_path: Path) -> None:
    root = _seed_project(tmp_path)
    proc = _run_pytest(root, "--collect-only", str(root), "-q")
    assert proc.returncode == 0
    expectation = PytestReportExpectationV1(
        schema_version=1,
        run_kind="COLLECT_ONLY",
        planned_node_ids=(_NODE_ADD, _NODE_MULTIPLY),
        report_plugin_version=_PLUGIN_VERSION,
    )
    outcome = parse_pytest_evidence(proc.stdout.encode("utf-8"), expectation)
    assert outcome.error_code is None
    assert outcome.evidence is not None
    assert outcome.evidence.run_kind == "COLLECT_ONLY"
    assert outcome.evidence.pytest_exit_code == 0
    assert outcome.evidence.event_count == 4  # start, two items, end
    assert outcome.evidence.events[-1].event_type == "SESSION_END"


def test_target_rerun_emits_target_kind_with_planned_ids(tmp_path: Path) -> None:
    root = _seed_project(tmp_path)
    proc = _run_pytest(root, _NODE_ADD, "-q")
    assert proc.returncode == 1
    expectation = PytestReportExpectationV1(
        schema_version=1,
        run_kind="TARGET_TESTS",
        planned_node_ids=(_NODE_ADD,),
        report_plugin_version=_PLUGIN_VERSION,
    )
    outcome = parse_pytest_evidence(proc.stdout.encode("utf-8"), expectation)
    assert outcome.error_code is None
    assert outcome.evidence is not None
    assert outcome.evidence.run_kind == "TARGET_TESTS"
    assert outcome.evidence.planned_node_ids == (_NODE_ADD,)
    assert outcome.evidence.collected_node_ids == (_NODE_ADD,)
    assert outcome.evidence.pytest_exit_code == 1


def test_reporter_is_only_loaded_explicitly(tmp_path: Path) -> None:
    root = _seed_project(tmp_path)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "cacheprovider=disabled",
            "--rootdir",
            str(root),
            str(root),
            "-q",
        ],
        cwd=str(root),
        env={**os.environ.copy(), "PYTHONPATH": str(_repo_root() / "src")},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 1
    assert "GATEEV1:" not in proc.stdout


def test_collection_error_emits_session_error_event(tmp_path: Path) -> None:
    root = _seed_project(tmp_path)
    (root / "tests" / "test_broken.py").write_text(
        "def broken(:\n    pass\n",
        encoding="utf-8",
    )
    proc = _run_pytest(root, str(root), "-q")
    assert proc.returncode == 2  # collection error exit code
    # The channel carries the SESSION_ERROR event and still ends normally;
    # the report is complete (all planned nodes were still collected and
    # executed), so it parses — rejecting collection errors is the
    # Baseline policy layer's decision, not the report contract's.
    document = _extract_raw_document(proc.stdout)
    raw_events = document["events"]
    assert isinstance(raw_events, list)
    event_types = [event["event_type"] for event in raw_events]
    assert "SESSION_ERROR" in event_types
    assert event_types[-1] == "SESSION_END"
    outcome = parse_pytest_evidence(proc.stdout.encode("utf-8"), _full_expectation())
    assert outcome.error_code is None
    assert outcome.evidence is not None
    assert any(event.event_type == "SESSION_ERROR" for event in outcome.evidence.events)
    assert outcome.evidence.pytest_exit_code == 2


def test_skip_and_xfail_events_are_emitted(tmp_path: Path) -> None:
    root = _seed_project(tmp_path)
    (root / "tests" / "test_skip_xfail.py").write_text(
        "import pytest\n"
        "@pytest.mark.skip(reason='demo skip')\n"
        "def test_skipped():\n"
        "    assert True\n"
        "@pytest.mark.xfail(reason='demo xfail')\n"
        "def test_expected_failure():\n"
        "    assert False\n",
        encoding="utf-8",
    )
    proc = _run_pytest(root, str(root), "-q")
    # The seeded fixture failure still fails; the SKIP/XFAIL outcomes are
    # what this test observes, and the report exit code stays consistent
    # with the recorded FAIL.
    assert proc.returncode == 1
    expectation = PytestReportExpectationV1(
        schema_version=1,
        run_kind="FULL_PYTEST",
        planned_node_ids=(
            _NODE_ADD,
            _NODE_MULTIPLY,
            "tests/test_skip_xfail.py::test_skipped",
            "tests/test_skip_xfail.py::test_expected_failure",
        ),
        report_plugin_version=_PLUGIN_VERSION,
    )
    outcome = parse_pytest_evidence(proc.stdout.encode("utf-8"), expectation)
    assert outcome.error_code is None
    assert outcome.evidence is not None
    outcomes = {
        event.outcome.value
        for event in outcome.evidence.events
        if event.event_type == "TEST_PHASE" and event.outcome.kind == "PRESENT"
    }
    assert "SKIP" in outcomes
    assert "XFAIL" in outcomes
    xfail = next(
        event
        for event in outcome.evidence.events
        if event.event_type == "TEST_PHASE"
        and event.outcome.kind == "PRESENT"
        and event.outcome.value == "XFAIL"
    )
    assert xfail.wasxfail.kind == "PRESENT"
    assert xfail.wasxfail.value is True


def test_two_independent_object_failure_runs_fingerprint_identically(
    tmp_path: Path,
) -> None:
    """Two real runs with volatile object addresses fingerprint identically.

    The failing assertion compares two live objects, so pytest's rewritten
    message carries the per-process runtime addresses; the reporter marks
    the addresses it observed and the fingerprint normalizes the declared
    volatility away, so two independent runs yield byte-identical
    fingerprints (SPEC §4.5 rule 2/4).
    """
    import tempfile

    from vespercode.validation.failure_fingerprint import (
        FingerprintNormalizationContextV1,
        build_failure_fingerprint,
    )

    root = _seed_project(tmp_path)
    (root / "tests" / "test_objects.py").write_text(
        "def test_object_inequality():\n"
        "    left = object()\n"
        "    right = object()\n"
        "    assert left == right\n",
        encoding="utf-8",
    )
    node = "tests/test_objects.py::test_object_inequality"
    expectation = PytestReportExpectationV1(
        schema_version=1,
        run_kind="FULL_PYTEST",
        planned_node_ids=(
            _NODE_ADD,
            _NODE_MULTIPLY,
            node,
        ),
        report_plugin_version=_PLUGIN_VERSION,
    )
    first_proc = _run_pytest(root, str(root), "-q")
    second_proc = _run_pytest(root, str(root), "-q")
    first_outcome = parse_pytest_evidence(
        first_proc.stdout.encode("utf-8"), expectation
    )
    second_outcome = parse_pytest_evidence(
        second_proc.stdout.encode("utf-8"), expectation
    )
    assert first_outcome.error_code is None, first_proc.stdout
    assert second_outcome.error_code is None, second_proc.stdout
    assert first_outcome.evidence is not None
    assert second_outcome.evidence is not None
    context = FingerprintNormalizationContextV1(
        schema_version=1,
        execution_root=str(root),
        tmp_root=tempfile.gettempdir(),
        run_id="run-demo-1",
        container_id="c" * 64,
    )
    first = build_failure_fingerprint(first_outcome.evidence, node, context)
    second = build_failure_fingerprint(second_outcome.evidence, node, context)
    assert first.kind == "STABLE"
    assert second.kind == "STABLE"
    assert first.fingerprint is not None
    assert second.fingerprint is not None
    # The volatile addresses were reporter-marked in both runs, so the
    # normalized text and the fingerprints are byte-identical.
    assert first.normalized_exception_text == second.normalized_exception_text
    assert first.fingerprint.digest == second.fingerprint.digest
    assert "<OBJECT_ADDRESS>" in first.normalized_exception_text


def test_caught_assertion_explanation_never_attaches_to_later_failure(
    tmp_path: Path,
) -> None:
    """The diff binds only the failing assertion, never a caught one.

    The test catches one assertion failure (whose explanation the
    assertion hook captures) and then fails on a different comparison;
    the FAIL event's diff must contain the failing assertion's content
    and none of the caught assertion's.
    """
    root = _seed_project(tmp_path)
    (root / "tests" / "test_caught_assert.py").write_text(
        "def test_caught_then_failing_assert():\n"
        "    try:\n"
        "        assert [1, 2] == [1, 3]\n"
        "    except AssertionError:\n"
        "        pass\n"
        "    assert {'a': 1} == {'a': 2}\n",
        encoding="utf-8",
    )
    node = "tests/test_caught_assert.py::test_caught_then_failing_assert"
    expectation = PytestReportExpectationV1(
        schema_version=1,
        run_kind="FULL_PYTEST",
        planned_node_ids=(_NODE_ADD, _NODE_MULTIPLY, node),
        report_plugin_version=_PLUGIN_VERSION,
    )
    proc = _run_pytest(root, str(root), "-q")
    outcome = parse_pytest_evidence(proc.stdout.encode("utf-8"), expectation)
    assert outcome.error_code is None, proc.stdout
    assert outcome.evidence is not None
    failure = next(
        event
        for event in outcome.evidence.events
        if event.event_type == "TEST_PHASE"
        and event.outcome.kind == "PRESENT"
        and event.outcome.value == "FAIL"
        and event.node_id.kind == "PRESENT"
        and event.node_id.value == node
    )
    exception = failure.exception
    assert exception.kind == "PRESENT"
    diff = exception.value.normalized_assertion_diff
    assert diff.kind == "PRESENT"
    assert "'a'" in diff.value
    assert "[1, 2]" not in diff.value


def test_caught_assertion_never_attaches_to_truthy_failure(
    tmp_path: Path,
) -> None:
    """A truthy failing assert never carries a caught assertion's diff.

    The caught comparison fires the compare hook (its explanation is
    captured), but the failing truthy assert never fires it; the FAIL
    event's diff must be the assertion message itself, with none of the
    caught assertion's content (the pairing fallback only consults the
    buffer when the crash line is unavailable).
    """
    root = _seed_project(tmp_path)
    (root / "tests" / "test_caught_truthy.py").write_text(
        "def test_caught_then_truthy_assert():\n"
        "    try:\n"
        "        assert [1, 2] == [1, 3]\n"
        "    except AssertionError:\n"
        "        pass\n"
        "    result = False\n"
        "    assert result\n",
        encoding="utf-8",
    )
    node = "tests/test_caught_truthy.py::test_caught_then_truthy_assert"
    expectation = PytestReportExpectationV1(
        schema_version=1,
        run_kind="FULL_PYTEST",
        planned_node_ids=(_NODE_ADD, _NODE_MULTIPLY, node),
        report_plugin_version=_PLUGIN_VERSION,
    )
    proc = _run_pytest(root, str(root), "-q")
    outcome = parse_pytest_evidence(proc.stdout.encode("utf-8"), expectation)
    assert outcome.error_code is None, proc.stdout
    assert outcome.evidence is not None
    failure = next(
        event
        for event in outcome.evidence.events
        if event.event_type == "TEST_PHASE"
        and event.outcome.kind == "PRESENT"
        and event.outcome.value == "FAIL"
        and event.node_id.kind == "PRESENT"
        and event.node_id.value == node
    )
    exception = failure.exception
    assert exception.kind == "PRESENT"
    diff = exception.value.normalized_assertion_diff
    assert diff.kind == "PRESENT"
    assert "assert False" in diff.value
    assert "[1, 2]" not in diff.value
