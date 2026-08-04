"""T02.4 legacy step 2.E: authoritative gate pytest evidence.

Captures one pytest lifecycle as an immutable ordered event sequence by
explicitly loading this module as a reporter plugin (``-p
spikes.docker_reference_boundary.pytest_reporter``), never through
entry-point auto-loading.  The plugin writes one compact JSON event per line
to the fixed report channel named by the ``REPORT_CHANNEL`` environment
variable; ``load_gate_pytest_report`` parses that channel strictly into one
``GatePytestReportV1`` and ``validate_gate_pytest_report`` fails closed on
missing, truncated, duplicate, implicit, or mismatched lifecycle evidence
with one stable rejection reason.

The gate event vocabulary is this task's own closed contract, consistent
with SPEC §4.5 ``PytestEventV1`` semantics: ``SESSION_START`` must be the
first event with sequence 1, ``SESSION_END`` must be the last event,
``TEST_PHASE`` events must declare node, phase, and outcome, and a
``FAIL``/``ERROR`` event must declare a structured exception with its crash
location.  Every digest is the SPEC §0.1 domain-separated SHA-256 of the
canonical JSON of every field except the digest itself.

Owns pytest event capture, loading, and completeness validation only.
Docker isolation, image identity, failure stability, and aggregate GO remain
out of scope (steps 2.D, 2.F, 2.G).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generator, Literal, TextIO

import pytest

GATE_REPORTER_VERSION = "1"

EventTypeV1 = Literal[
    "SESSION_START",
    "COLLECTION_ITEM",
    "TEST_PHASE",
    "DESELECTED",
    "SESSION_ERROR",
    "SESSION_END",
]
PhaseV1 = Literal["COLLECTION", "SETUP", "CALL", "TEARDOWN", "ENVIRONMENT"]
OutcomeV1 = Literal[
    "PASS", "FAIL", "SKIP", "XFAIL", "XPASS", "DESELECTED", "ERROR", "NOT_RUN"
]

TestIdSequenceV1 = tuple[str, ...]
GatePytestEventSequenceV1 = tuple["GatePytestEventV1", ...]

REPORT_CHANNEL_ENV = "REPORT_CHANNEL"
# The fixed structured marker every event line is also mirrored to stdout
# with; inside the frozen reference container the report channel lives on the
# bounded tmpfs, which ``docker cp`` cannot read (it never traverses mount
# points), so the probe extracts the prefixed lines from ``docker logs``.
STDOUT_EVENT_PREFIX = "GATEEV1:"
REPO_ROOT = Path(__file__).resolve().parents[2]

_EVENT_TYPES = frozenset(
    (
        "SESSION_START",
        "COLLECTION_ITEM",
        "TEST_PHASE",
        "DESELECTED",
        "SESSION_ERROR",
        "SESSION_END",
    )
)
_PHASES = frozenset(("COLLECTION", "SETUP", "CALL", "TEARDOWN", "ENVIRONMENT"))
_OUTCOMES = frozenset(
    ("PASS", "FAIL", "SKIP", "XFAIL", "XPASS", "DESELECTED", "ERROR", "NOT_RUN")
)
_OPTIONAL_FIELDS = (
    "node_id",
    "phase",
    "outcome",
    "wasxfail",
    "exception_type",
    "normalized_message",
    "relative_path",
    "function_name",
    "line_number",
)
_EVENT_KEYS = ("sequence", "event_type", *_OPTIONAL_FIELDS)
_EXCEPTION_FIELDS = (
    "exception_type",
    "normalized_message",
    "relative_path",
    "function_name",
    "line_number",
)

# Stable closed rejection reasons (the complete vocabulary of the gate
# pytest-evidence validator).
REASON_COMPLETE = "COMPLETE"
REASON_INTEGRITY = "INTEGRITY_DIGEST_MISMATCH"
REASON_EMPTY_EVENTS = "EMPTY_EVENTS"
REASON_SEQUENCE = "SEQUENCE_BREAK"
REASON_DUPLICATE = "DUPLICATE_EVENT"
REASON_ORDER = "INVALID_EVENT_ORDER"
REASON_START = "MISSING_SESSION_START"
REASON_END = "MISSING_END_MARKER"
REASON_NORMAL_END = "NORMAL_END_FALSE"
REASON_IMPLICIT = "IMPLICIT_EVENT_FIELD"
REASON_FAIL_NO_EXC = "FAIL_WITHOUT_EXCEPTION"
REASON_ERROR_NO_EXC = "ERROR_WITHOUT_EXCEPTION"
REASON_DESELECTED = "DESELECTED_PRESENT"
REASON_COLLECTION_ERROR = "COLLECTION_ERROR_PRESENT"
REASON_EMPTY_COLLECTION = "EMPTY_COLLECTION"
REASON_UNPLANNED = "UNPLANNED_NODE_COLLECTED"
REASON_MISSING_COLLECTED = "PLANNED_NODE_NOT_COLLECTED"
REASON_MISMATCH = "COLLECTED_PLAN_MISMATCH"
REASON_NOT_EXECUTED = "PLANNED_NODE_NOT_EXECUTED"
REASON_UNCOLLECTED = "TEST_PHASE_NODE_UNCOLLECTED"
REASON_DUPLICATE_PHASE = "DUPLICATE_TEST_PHASE"
REASON_EXIT = "EXIT_CODE_INCONSISTENT"


@dataclass(frozen=True)
class GatePytestEventV1:
    """One immutable pytest lifecycle event."""

    sequence: int
    event_type: EventTypeV1
    node_id: str | None = None
    phase: PhaseV1 | None = None
    outcome: OutcomeV1 | None = None
    wasxfail: bool | None = None
    exception_type: str | None = None
    normalized_message: str | None = None
    relative_path: str | None = None
    function_name: str | None = None
    line_number: int | None = None


@dataclass(frozen=True)
class GatePytestReportV1:
    """One immutable explicit pytest lifecycle report."""

    planned_node_ids: TestIdSequenceV1
    collected_node_ids: TestIdSequenceV1
    events: GatePytestEventSequenceV1
    normal_end: bool
    exit_code: int
    integrity_digest: str


@dataclass(frozen=True)
class GatePytestEvidenceResultV1:
    """The closed validation result of one gate pytest report."""

    passed: bool
    reason: str


def _canonical_json_bytes(obj: object) -> bytes:
    """Deterministic compact UTF-8 JSON with sorted keys (SPEC §0.1)."""
    return json.dumps(
        obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _domain_separated_digest(object_type: str, schema_version: int, obj: object) -> str:
    """SPEC §0.1 digest: domain prefix, type, decimal version, canonical JSON."""
    prefix = (
        b"VesperCode\x00"
        + object_type.encode("utf-8")
        + b"\x00"
        + str(schema_version).encode("ascii")
        + b"\x00"
    )
    return hashlib.sha256(prefix + _canonical_json_bytes(obj)).hexdigest()


def _event_to_dict(event: GatePytestEventV1) -> dict[str, object]:
    return {
        "sequence": event.sequence,
        "event_type": event.event_type,
        "node_id": event.node_id,
        "phase": event.phase,
        "outcome": event.outcome,
        "wasxfail": event.wasxfail,
        "exception_type": event.exception_type,
        "normalized_message": event.normalized_message,
        "relative_path": event.relative_path,
        "function_name": event.function_name,
        "line_number": event.line_number,
    }


def _report_digest_body(
    planned_node_ids: TestIdSequenceV1,
    collected_node_ids: TestIdSequenceV1,
    events: GatePytestEventSequenceV1,
    *,
    normal_end: bool,
    exit_code: int,
) -> dict[str, object]:
    """Every field except the integrity digest, as canonical JSON input."""
    return {
        "planned_node_ids": list(planned_node_ids),
        "collected_node_ids": list(collected_node_ids),
        "events": [_event_to_dict(event) for event in events],
        "normal_end": normal_end,
        "exit_code": exit_code,
    }


def build_gate_pytest_report(
    planned_node_ids: TestIdSequenceV1,
    collected_node_ids: TestIdSequenceV1,
    events: GatePytestEventSequenceV1,
    *,
    normal_end: bool,
    exit_code: int,
) -> GatePytestReportV1:
    """Build one immutable report with its SPEC §0.1 integrity identity."""
    body = _report_digest_body(
        planned_node_ids,
        collected_node_ids,
        events,
        normal_end=normal_end,
        exit_code=exit_code,
    )
    digest = _domain_separated_digest("GatePytestReportV1", 1, body)
    return GatePytestReportV1(
        planned_node_ids=tuple(planned_node_ids),
        collected_node_ids=tuple(collected_node_ids),
        events=tuple(events),
        normal_end=normal_end,
        exit_code=exit_code,
        integrity_digest=digest,
    )


def _declared_optional_fields(
    event: GatePytestEventV1, exclude: tuple[str, ...] = ()
) -> tuple[str, ...]:
    return tuple(
        name
        for name in _OPTIONAL_FIELDS
        if name not in exclude and getattr(event, name) is not None
    )


def _reject(reason: str) -> GatePytestEvidenceResultV1:
    return GatePytestEvidenceResultV1(passed=False, reason=reason)


def validate_gate_pytest_report(
    report: GatePytestReportV1,
) -> GatePytestEvidenceResultV1:
    """Fail closed unless the report is complete, ordered, and explicit.

    Missing, truncated, duplicate, implicit, or mismatched lifecycle
    evidence returns one stable rejection reason before it can become gate
    evidence; only a complete explicit report with a self-consistent
    integrity identity passes.
    """
    if (
        _domain_separated_digest(
            "GatePytestReportV1",
            1,
            _report_digest_body(
                report.planned_node_ids,
                report.collected_node_ids,
                report.events,
                normal_end=report.normal_end,
                exit_code=report.exit_code,
            ),
        )
        != report.integrity_digest
    ):
        return _reject(REASON_INTEGRITY)
    if not report.events:
        return _reject(REASON_EMPTY_EVENTS)
    events = report.events
    seen: set[int] = set()
    for index, event in enumerate(events):
        expected_sequence = index + 1
        if event.sequence in seen:
            return _reject(REASON_DUPLICATE)
        seen.add(event.sequence)
        if event.sequence != expected_sequence:
            return _reject(REASON_SEQUENCE)
    if events[0].event_type != "SESSION_START":
        return _reject(REASON_START)
    if _declared_optional_fields(events[0]):
        return _reject(REASON_IMPLICIT)
    if any(event.event_type == "SESSION_START" for event in events[1:]):
        return _reject(REASON_ORDER)
    if events[-1].event_type != "SESSION_END":
        return _reject(REASON_END)
    if not report.normal_end:
        return _reject(REASON_NORMAL_END)
    if _declared_optional_fields(events[-1]):
        return _reject(REASON_IMPLICIT)
    for event in events[1:-1]:
        if event.event_type == "COLLECTION_ITEM":
            if event.node_id is None or _declared_optional_fields(
                event, exclude=("node_id",)
            ):
                return _reject(REASON_IMPLICIT)
        elif event.event_type == "TEST_PHASE":
            if event.node_id is None or event.phase is None or event.outcome is None:
                return _reject(REASON_IMPLICIT)
            if event.outcome == "FAIL":
                if event.phase != "CALL":
                    return _reject(REASON_IMPLICIT)
                if any(getattr(event, field) is None for field in _EXCEPTION_FIELDS):
                    return _reject(REASON_FAIL_NO_EXC)
            elif event.outcome == "ERROR":
                if event.phase == "CALL":
                    return _reject(REASON_IMPLICIT)
                if any(getattr(event, field) is None for field in _EXCEPTION_FIELDS):
                    return _reject(REASON_ERROR_NO_EXC)
            elif event.outcome in ("XFAIL", "XPASS"):
                if event.wasxfail is not True:
                    return _reject(REASON_IMPLICIT)
                if _declared_optional_fields(
                    event, exclude=("node_id", "phase", "outcome", "wasxfail")
                ):
                    return _reject(REASON_IMPLICIT)
            else:
                if event.wasxfail is not None or _declared_optional_fields(
                    event, exclude=("node_id", "phase", "outcome")
                ):
                    return _reject(REASON_IMPLICIT)
        elif event.event_type == "DESELECTED":
            return _reject(REASON_DESELECTED)
        elif event.event_type == "SESSION_ERROR":
            return _reject(REASON_COLLECTION_ERROR)
        else:
            return _reject(REASON_ORDER)
    if not report.collected_node_ids:
        return _reject(REASON_EMPTY_COLLECTION)
    collected_set = set(report.collected_node_ids)
    if report.planned_node_ids:
        if report.collected_node_ids != report.planned_node_ids:
            planned_set = set(report.planned_node_ids)
            missing = tuple(
                node_id
                for node_id in report.planned_node_ids
                if node_id not in collected_set
            )
            extra = tuple(
                node_id
                for node_id in report.collected_node_ids
                if node_id not in planned_set
            )
            if missing:
                return _reject(REASON_MISSING_COLLECTED)
            if extra:
                return _reject(REASON_UNPLANNED)
            return _reject(REASON_MISMATCH)
    executed_nodes: set[str] = set()
    seen_phases: set[tuple[str, str]] = set()
    for event in events:
        if event.event_type != "TEST_PHASE":
            continue
        assert event.node_id is not None and event.phase is not None
        if event.node_id not in collected_set:
            return _reject(REASON_UNCOLLECTED)
        key = (event.node_id, event.phase)
        if key in seen_phases:
            return _reject(REASON_DUPLICATE_PHASE)
        seen_phases.add(key)
        if event.phase == "CALL":
            executed_nodes.add(event.node_id)
    for node_id in report.planned_node_ids:
        if node_id not in executed_nodes:
            return _reject(REASON_NOT_EXECUTED)
    any_failure = any(
        event.event_type == "TEST_PHASE" and event.outcome in ("FAIL", "ERROR")
        for event in events
    )
    if any_failure:
        expected_exit_code = 1
    else:
        expected_exit_code = 0
    if report.exit_code != expected_exit_code:
        return _reject(REASON_EXIT)
    return GatePytestEvidenceResultV1(passed=True, reason=REASON_COMPLETE)


def _optional_str(value: object, field: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise ValueError(f"gate reporter event {field} must be a string or null")


def _optional_bool(value: object, field: str) -> bool | None:
    if value is None or (isinstance(value, bool) and not isinstance(value, int)):
        return value
    raise ValueError(f"gate reporter event {field} must be a boolean or null")


def _optional_int(value: object, field: str) -> int | None:
    if value is None or (isinstance(value, int) and not isinstance(value, bool)):
        return value
    raise ValueError(f"gate reporter event {field} must be an integer or null")


def _parse_event_line(line: str) -> GatePytestEventV1:
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError("gate reporter channel contains invalid JSON") from exc
    if not isinstance(obj, dict):
        raise ValueError("gate reporter event must be a JSON object")
    if set(obj) != set(_EVENT_KEYS):
        raise ValueError("gate reporter event has an invalid field set")
    sequence = obj["sequence"]
    if not isinstance(sequence, int) or isinstance(sequence, bool):
        raise ValueError("gate reporter event sequence must be an integer")
    event_type = obj["event_type"]
    if not isinstance(event_type, str) or event_type not in _EVENT_TYPES:
        raise ValueError("gate reporter event_type is not a closed value")
    phase = _optional_str(obj["phase"], "phase")
    if phase is not None and phase not in _PHASES:
        raise ValueError("gate reporter event phase is not a closed value")
    outcome = _optional_str(obj["outcome"], "outcome")
    if outcome is not None and outcome not in _OUTCOMES:
        raise ValueError("gate reporter event outcome is not a closed value")
    return GatePytestEventV1(
        sequence=sequence,
        event_type=event_type,  # type: ignore[arg-type]
        node_id=_optional_str(obj["node_id"], "node_id"),
        phase=phase,  # type: ignore[arg-type]
        outcome=outcome,  # type: ignore[arg-type]
        wasxfail=_optional_bool(obj["wasxfail"], "wasxfail"),
        exception_type=_optional_str(obj["exception_type"], "exception_type"),
        normalized_message=_optional_str(
            obj["normalized_message"], "normalized_message"
        ),
        relative_path=_optional_str(obj["relative_path"], "relative_path"),
        function_name=_optional_str(obj["function_name"], "function_name"),
        line_number=_optional_int(obj["line_number"], "line_number"),
    )


def load_gate_pytest_report(
    channel: Path,
    planned_node_ids: TestIdSequenceV1,
    exit_code: int,
) -> GatePytestReportV1:
    """Parse one strict report-channel file into an immutable report.

    The collected node ids are derived from the channel's own
    ``COLLECTION_ITEM`` events in order, so the report summary can never
    disagree with the events it claims to carry; any malformed channel bytes
    fail closed with ``ValueError``.
    """
    try:
        raw = channel.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("gate reporter channel is not valid UTF-8") from exc
    if not raw.strip():
        raise ValueError("gate reporter channel is empty")
    lines = raw.splitlines()
    events = tuple(_parse_event_line(line) for line in lines)
    collected = tuple(
        event.node_id
        for event in events
        if event.event_type == "COLLECTION_ITEM" and event.node_id is not None
    )
    normal_end = events[-1].event_type == "SESSION_END"
    return build_gate_pytest_report(
        planned_node_ids=planned_node_ids,
        collected_node_ids=collected,
        events=events,
        normal_end=normal_end,
        exit_code=exit_code,
    )


def run_gate_pytest(
    root: Path,
    planned_node_ids: TestIdSequenceV1,
    *,
    collect_only: bool = False,
    target_node_ids: TestIdSequenceV1 | None = None,
) -> GatePytestReportV1:
    """Capture one explicitly loaded pytest lifecycle for the project at *root*.

    Runs the frozen gate interpreter with this module loaded explicitly via
    ``-p`` (never auto-loaded from entry points), writes the fixed report
    channel, and returns one immutable report bound to the observed exit
    code.  ``target_node_ids`` selects a target rerun; ``collect_only``
    collects without executing.
    """
    root = Path(root)
    with tempfile.TemporaryDirectory(prefix="vesper-gate-pytest-") as tmp:
        channel = Path(tmp) / "events.jsonl"
        argv = [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "spikes.docker_reference_boundary.pytest_reporter",
            "-o",
            "cacheprovider=disabled",
            "--rootdir",
            str(root),
        ]
        if collect_only:
            argv.append("--collect-only")
        if target_node_ids is not None:
            argv.extend(target_node_ids)
        else:
            argv.append(str(root))
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT)
        env[REPORT_CHANNEL_ENV] = str(channel)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONHASHSEED"] = "0"
        env.setdefault("TZ", "UTC")
        env.setdefault("LC_ALL", "C.UTF-8")
        proc = subprocess.run(
            argv,
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if not channel.is_file():
            raise RuntimeError(
                "gate reporter channel was not created; the reporter was not "
                "explicitly loaded"
            )
        return load_gate_pytest_report(channel, planned_node_ids, proc.returncode)


class _ReporterState:
    """Per-process plugin state; one fresh state per captured run."""

    def __init__(self) -> None:
        self.sequence = 0
        self.channel: TextIO | None = None


_REPORTER = _ReporterState()


def _emit(event_type: EventTypeV1, **fields: object) -> None:
    if _REPORTER.channel is None:
        raise RuntimeError("gate reporter channel is not open")
    _REPORTER.sequence += 1
    event: dict[str, object] = {
        "sequence": _REPORTER.sequence,
        "event_type": event_type,
    }
    for name in _OPTIONAL_FIELDS:
        event[name] = fields.get(name)
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    _REPORTER.channel.write(line + "\n")
    _REPORTER.channel.flush()
    print(STDOUT_EVENT_PREFIX + line, flush=True)


def pytest_sessionstart(session: object) -> None:
    channel_path = os.environ.get(REPORT_CHANNEL_ENV)
    if not channel_path:
        raise RuntimeError(
            "the gate reporter requires the REPORT_CHANNEL environment variable"
        )
    _REPORTER.sequence = 0
    _REPORTER.channel = open(channel_path, "w", encoding="utf-8")
    _emit("SESSION_START")


def pytest_collection_finish(session: object) -> None:
    for item in getattr(session, "items", []):
        node_id = getattr(item, "nodeid", None)
        if isinstance(node_id, str):
            _emit("COLLECTION_ITEM", node_id=node_id)


def pytest_collectreport(report: object) -> None:
    if getattr(report, "failed", False):
        longrepr = getattr(report, "longrepr", None)
        message = str(longrepr) if longrepr is not None else "collection error"
        _emit(
            "SESSION_ERROR",
            exception_type="CollectionError",
            normalized_message=message,
        )


def _crash_location(excinfo: object) -> tuple[str, str, int] | None:
    """The innermost project frame of the exception traceback, if any.

    Returns ``(relative_path, function_name, line_number)`` in
    forward-slash repository-relative form; frames outside the project root
    (pytest itself, site-packages) never count.
    """
    traceback = getattr(excinfo, "traceback", None)
    if traceback is None:
        return None
    cwd = Path(os.getcwd()).resolve()
    for entry in reversed(list(traceback)):
        path = getattr(entry, "path", None)
        if path is None:
            continue
        try:
            relative = Path(str(path)).resolve().relative_to(cwd)
        except ValueError:
            continue
        if not relative.parts or relative.parts[0] in (
            "site-packages",
            ".venv-gate",
        ):
            continue
        name = getattr(entry, "name", None)
        lineno = getattr(entry, "lineno", None)
        if isinstance(name, str) and isinstance(lineno, int):
            return relative.as_posix(), name, lineno
    return None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: object, call: object
) -> Generator[None, None, None]:
    outcome: Any = yield
    report = outcome.get_result()
    when = getattr(report, "when", None)
    if when == "setup":
        phase: PhaseV1 = "SETUP"
    elif when == "call":
        phase = "CALL"
    elif when == "teardown":
        phase = "TEARDOWN"
    else:
        return
    outcome_raw = getattr(report, "outcome", None)
    wasxfail = bool(getattr(report, "wasxfail", None))
    if outcome_raw == "passed":
        outcome_value = "XPASS" if wasxfail else "PASS"
    elif outcome_raw == "failed":
        outcome_value = "FAIL" if when == "call" else "ERROR"
    elif outcome_raw == "skipped":
        outcome_value = "XFAIL" if wasxfail else "SKIP"
    else:
        outcome_value = "NOT_RUN"
    fields: dict[str, object] = {
        "node_id": getattr(report, "nodeid", None),
        "phase": phase,
        "outcome": outcome_value,
        "wasxfail": wasxfail if outcome_value in ("XFAIL", "XPASS") else None,
    }
    if outcome_value in ("FAIL", "ERROR"):
        excinfo = getattr(call, "excinfo", None)
        exc_type = getattr(excinfo, "type", None)
        if isinstance(exc_type, type):
            exception_type = exc_type.__name__
        else:
            exception_type = "UnknownError"
        value = getattr(excinfo, "value", None)
        normalized_message = str(value) if value is not None else "unknown failure"
        crash = _crash_location(excinfo)
        if crash is not None:
            fields.update(
                exception_type=exception_type,
                normalized_message=normalized_message,
                relative_path=crash[0],
                function_name=crash[1],
                line_number=crash[2],
            )
        else:
            fields.update(
                exception_type=exception_type,
                normalized_message=normalized_message,
            )
    _emit("TEST_PHASE", **fields)


def pytest_sessionfinish(session: object, exitstatus: object) -> None:
    if _REPORTER.channel is None:
        return
    try:
        _emit("SESSION_END")
    finally:
        _REPORTER.channel.close()
        _REPORTER.channel = None
