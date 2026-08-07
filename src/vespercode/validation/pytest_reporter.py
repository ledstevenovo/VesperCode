"""T19.1 legacy step 19.B: production pytest report plugin (GATEEV1 channel).

Loaded explicitly as ``-p vespercode.validation.pytest_reporter`` (never
through entry-point auto-loading; SPEC §1.4.1 allows only the built-in
plugins and the fixed machine-readable report plugin inside the execution
image), this module captures one complete pytest lifecycle and emits
exactly one canonical JSON ``PytestEvidenceV1`` document through the
fixed ``GATEEV1:`` stdout channel at session finish.  The bounded stdout
bytes are the machine-readable report; console text and the process exit
code can never supplement or override the structured facts (SPEC §4.5).

The module is deliberately self-contained (standard library + pytest
only): it is copied into the offline read-only workspace by the
integration test, and the frozen execution image carries it, so it can
never import other harness modules.

Owns plugin emission only.  Report validation lives in
``pytest_evidence.py``; fingerprinting, Baseline orchestration, and PASS
synthesis remain out of scope (GREEN-4).
"""

from __future__ import annotations

import hashlib
import json
import os
from itertools import islice
from pathlib import Path
from typing import Any, Generator, Literal

import pytest
from _pytest.config import Config

REPORT_PLUGIN_VERSION = "1"
STDOUT_EVENT_PREFIX = "GATEEV1:"
MAX_REPORT_EVENTS = 65536

# The shared fixed placeholders: the reporter marks the runtime object
# addresses it observed (SPEC §4.5 rule 2) so the fingerprint never sees
# raw addresses.
ADDRESS_PLACEHOLDER = "<OBJECT_ADDRESS>"

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

_OPTIONAL_FIELDS = (
    "node_id",
    "phase",
    "outcome",
    "wasxfail",
    "exception",
    "display_summary",
)


def _canonical_json_bytes(obj: object) -> bytes:
    """The SPEC §0.1 canonical UTF-8 JSON bytes (compact, sorted keys)."""
    return json.dumps(
        obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _domain_separated_digest(object_type: str, schema_version: int, obj: object) -> str:
    """The SPEC §0.1 domain-separated SHA-256 binding identity."""
    prefix = (
        b"VesperCode\x00"
        + object_type.encode("utf-8")
        + b"\x00"
        + str(schema_version).encode("ascii")
        + b"\x00"
    )
    return hashlib.sha256(prefix + _canonical_json_bytes(obj)).hexdigest()


def _absent() -> dict[str, object]:
    return {"kind": "ABSENT"}


def _present_text(value: str) -> dict[str, object]:
    return {"kind": "PRESENT", "value": value}


def _present_bool(value: bool) -> dict[str, object]:
    return {"kind": "PRESENT", "value": value}


class _ReporterState:
    """Per-process plugin state; one fresh state per captured run."""

    def __init__(self) -> None:
        self.sequence = 0
        self.events: list[dict[str, object]] = []
        # (assertion source line, explanation) pairs captured by
        # pytest_assertrepr_compare; consumed only for the assertion whose
        # source line matches the failing exception's crash line.
        self.explanations: list[tuple[int | None, str]] = []
        self.observed_addresses: set[str] = set()


_STATE = _ReporterState()


def _record_event(event_type: EventTypeV1, **fields: object) -> None:
    """Record one event dict with explicit ABSENT/PRESENT optional fields."""
    _STATE.sequence += 1
    event: dict[str, object] = {"sequence": _STATE.sequence, "event_type": event_type}
    for name in _OPTIONAL_FIELDS:
        event[name] = fields.get(name, _absent())
    _STATE.events.append(event)


def _observe_address(address: int) -> None:
    """Record every exact spelling one observed address can take in text.

    CPython ``repr`` renders object addresses through ``%p``: lowercase
    unpadded on POSIX (``0x7f9a…``) but uppercase zero-padded on Windows
    (``0x000001CF…``).  The reporter records only the exact observed
    spellings, so user hexadecimal text is never touched (SPEC §4.5
    rule 4).
    """
    _STATE.observed_addresses.add(f"0x{address:x}")
    _STATE.observed_addresses.add(f"0x{address:X}")
    _STATE.observed_addresses.add(f"0x{address:016x}")
    _STATE.observed_addresses.add(f"0x{address:016X}")


def _observe_value(value: object, depth: int = 0) -> None:
    """Observe one value and a bounded walk of its container elements.

    A repr can render addresses of objects nested inside a container
    (e.g. ``[<object object at 0x…>]``) even though only the container is
    a local; the walk is depth/width/total capped so a large or deep
    object graph stays bounded and deterministic.  Only built-in
    containers are traversed.
    """
    if depth > 2 or len(_STATE.observed_addresses) > 4096:
        return
    try:
        _observe_address(id(value))
    except Exception:
        return
    if depth >= 2:
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        for element in islice(value, 64):
            _observe_value(element, depth + 1)
    elif isinstance(value, dict):
        for key in islice(value, 64):
            _observe_value(key, depth + 1)
        for element in islice(value.values(), 64):
            _observe_value(element, depth + 1)


def _observed_address_tokens() -> tuple[str, ...]:
    """The exact observed ``0x…`` tokens, deterministically ordered."""
    return tuple(sorted(_STATE.observed_addresses))


def _normalize_reporter_text(text: str) -> str:
    """LF-unify and replace only the observed runtime object addresses."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    for token in _observed_address_tokens():
        normalized = normalized.replace(token, ADDRESS_PLACEHOLDER)
    return normalized


def _collect_observed_addresses(excinfo: object) -> None:
    """Record the addresses of every live local and exception argument.

    Best-effort observation: any failure to walk a frame leaves the
    observed set smaller, never larger; the reporter must never crash a
    run because of a hostile or unusual object graph.
    """
    traceback = getattr(excinfo, "traceback", None)
    if traceback is None:
        traceback = ()
    for entry in list(traceback):
        frame = getattr(entry, "frame", None)
        if frame is None:
            continue
        try:
            locals_map = getattr(frame, "f_locals", None)
        except Exception:
            locals_map = None
        if isinstance(locals_map, dict):
            for value in locals_map.values():
                try:
                    _observe_value(value)
                except Exception:
                    continue
    value = getattr(excinfo, "value", None)
    if value is not None:
        try:
            args = getattr(value, "args", ())
        except Exception:
            args = ()
        if isinstance(args, tuple):
            for argument in args:
                try:
                    _observe_value(argument)
                except Exception:
                    continue


def _project_frames(excinfo: object) -> list[dict[str, object]]:
    """The project stack frames in call order, bounded (SPEC §4.5 rule 3).

    Only frames under the project root (the run's rootdir) are kept;
    pytest, standard library, and site-packages frames never count.  The
    ordered list is capped so a deep traceback stays bounded.

    Closure contract with the parser: every FAIL/ERROR event requires at
    least one project frame.  A test failure's traceback always contains
    the test function's own frame (a CALL-phase failure) or the fixture
    frame (a setup/teardown error), both under the project root, so the
    emitted FAIL/ERROR events always satisfy the parser invariant; an
    exception raised entirely outside the project (no frame under the
    root) is emitted fail-closed and the parse rejects it as
    REPORTER_INVALID rather than fabricating a frame.
    """
    traceback = getattr(excinfo, "traceback", None)
    if traceback is None:
        return []
    root = Path(os.getcwd()).resolve()
    frames: list[dict[str, object]] = []
    for entry in list(traceback):
        path = getattr(entry, "path", None)
        if path is None:
            continue
        try:
            relative = Path(str(path)).resolve().relative_to(root)
        except ValueError:
            continue
        if not relative.parts or relative.parts[0] in (
            "site-packages",
            ".venv",
            ".venv-gate",
            ".venv-formal",
        ):
            continue
        name = getattr(entry, "name", None)
        lineno = getattr(entry, "lineno", None)
        if not isinstance(name, str) or not isinstance(lineno, int):
            continue
        frames.append(
            {
                "relative_path": relative.as_posix(),
                "function_name": name,
                "line_number": lineno,
            }
        )
        if len(frames) >= 32:
            break
    return frames


def _failing_assertion_line(excinfo: object) -> int | None:
    """The crash line of the failing assertion, if the traceback has one.

    The innermost traceback entry is the frame where the assertion
    raised; its line is the assertion's source line.
    """
    traceback = getattr(excinfo, "traceback", None)
    if traceback is None:
        return None
    entries = list(traceback)
    if not entries:
        return None
    lineno = getattr(entries[-1], "lineno", None)
    return lineno if isinstance(lineno, int) else None


def _structured_exception(
    excinfo: object, assertion_diff: str | None
) -> dict[str, object]:
    """One complete structured exception with reporter-marked text."""
    exc_type = getattr(excinfo, "type", None)
    exception_type = exc_type.__name__ if isinstance(exc_type, type) else "UnknownError"
    value = getattr(excinfo, "value", None)
    normalized_message = _normalize_reporter_text(
        str(value) if value is not None else "unknown failure"
    )
    diff_field: dict[str, object]
    if assertion_diff is None:
        diff_field = _absent()
    else:
        diff_field = _present_text(_normalize_reporter_text(assertion_diff))
    return {
        "exception_type": exception_type,
        "normalized_message": normalized_message,
        "normalized_assertion_diff": diff_field,
        "project_frames": _project_frames(excinfo),
    }


def pytest_sessionstart(session: object) -> None:
    """Open the lifecycle: SESSION_START is always the first event."""
    _STATE.sequence = 0
    _STATE.events = []
    _STATE.explanations = []
    _STATE.observed_addresses = set()
    _record_event("SESSION_START")


def pytest_collectreport(report: object) -> None:
    """Record one collection failure as a SESSION_ERROR event."""
    if not getattr(report, "failed", False):
        return
    longrepr = getattr(report, "longrepr", None)
    message = str(longrepr) if longrepr is not None else "collection error"
    _record_event(
        "SESSION_ERROR",
        exception={
            "kind": "PRESENT",
            "value": {
                "exception_type": "CollectionError",
                "normalized_message": _normalize_reporter_text(message),
                "normalized_assertion_diff": _absent(),
                "project_frames": [],
            },
        },
    )


def pytest_collection_finish(session: object) -> None:
    """Record every collected item in exact collection order."""
    for item in getattr(session, "items", []):
        node_id = getattr(item, "nodeid", None)
        if isinstance(node_id, str):
            _record_event("COLLECTION_ITEM", node_id=_present_text(node_id))


def _assertion_source_line() -> int | None:
    """The user-frame source line of the assertion being evaluated.

    The hook fires while the rewritten assertion executes inside the test
    frame; walking up past the pytest machinery yields that frame, whose
    current line is the assertion's source line.  This pairs every
    captured explanation with its own assertion, so a caught assertion's
    explanation can never attach to a different failing assertion.
    """
    import inspect

    frame = inspect.currentframe()
    try:
        while frame is not None:
            module_name = frame.f_globals.get("__name__")
            if isinstance(module_name, str) and not module_name.startswith(
                (
                    "pytest",
                    "_pytest",
                    "pluggy",
                    # The harness package: the installed plugin and the
                    # repo tree (src on the path) both load as
                    # ``vespercode...``.
                    "vespercode",
                )
            ):
                return frame.f_lineno
            frame = frame.f_back
        return None
    finally:
        del frame


@pytest.hookimpl
def pytest_assertrepr_compare(
    config: Config,
    op: str,
    left: object,
    right: object,
) -> list[str] | None:
    """Capture the assertion explanation for the current failure.

    Computes the same explanation the default hook renders (the shared
    ``_pytest.assertion.util.assertrepr_compare``) but returns None so
    pytest's own display is never altered; each captured explanation is
    paired with its assertion source line, and the FAIL event consumes
    only the entry belonging to the failing assertion.
    """
    from _pytest.assertion.util import assertrepr_compare

    try:
        explanation = assertrepr_compare(config, op, left, right)
    except Exception:
        return None
    if explanation:
        _STATE.explanations.append((_assertion_source_line(), "\n".join(explanation)))
    return None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: object, call: object
) -> Generator[None, None, None]:
    """Record one TEST_PHASE event per setup/call/teardown phase."""
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
        outcome_value: OutcomeV1 = "XPASS" if wasxfail else "PASS"
    elif outcome_raw == "failed":
        outcome_value = "FAIL" if when == "call" else "ERROR"
    elif outcome_raw == "skipped":
        outcome_value = "XFAIL" if wasxfail else "SKIP"
    else:
        outcome_value = "NOT_RUN"
    fields: dict[str, object] = {
        "node_id": _present_text(str(getattr(report, "nodeid", ""))),
        "phase": _present_text(phase),
        "outcome": _present_text(outcome_value),
    }
    if outcome_value in ("XFAIL", "XPASS"):
        fields["wasxfail"] = _present_bool(True)
    else:
        fields["wasxfail"] = _absent()
    if outcome_value in ("FAIL", "ERROR"):
        excinfo = getattr(call, "excinfo", None)
        if excinfo is not None:
            _collect_observed_addresses(excinfo)
            exc_type = getattr(excinfo, "type", None)
            exception_type = (
                exc_type.__name__ if isinstance(exc_type, type) else "UnknownError"
            )
            assertion_diff: str | None
            if exception_type == "AssertionError":
                failing_line = _failing_assertion_line(excinfo)
                matched = next(
                    (
                        explanation
                        for line, explanation in reversed(_STATE.explanations)
                        if line is not None and line == failing_line
                    ),
                    None,
                )
                if matched is not None:
                    # The specialized comparison diff captured by
                    # pytest_assertrepr_compare for the exact failing
                    # assertion; a caught assertion's explanation never
                    # attaches to a different failing assertion.
                    assertion_diff = matched
                elif failing_line is None and _STATE.explanations:
                    # The crash line is unavailable and only the last
                    # captured explanation can plausibly belong to the
                    # failing assertion (the last assertion evaluated).
                    assertion_diff = _STATE.explanations[-1][1]
                else:
                    # No explanation belongs to the failing assertion
                    # (e.g. a truthy assert that never fired the compare
                    # hook, or a mismatch after a caught assertion): the
                    # rewritten assertion message already carries the full
                    # explanation, so the stale buffer is never attached.
                    value = getattr(excinfo, "value", None)
                    assertion_diff = str(value) if value is not None else None
            else:
                assertion_diff = None
            fields["exception"] = {
                "kind": "PRESENT",
                "value": _structured_exception(excinfo, assertion_diff),
            }
        else:
            fields["exception"] = _absent()
    else:
        fields["exception"] = _absent()
    _record_event("TEST_PHASE", **fields)
    _STATE.explanations = []


def _positional_args(config: object) -> tuple[str, ...]:
    """The frozen argv positionals: -p/-o/--rootdir pairs and flags removed."""
    args = getattr(getattr(config, "invocation_params", None), "args", ())
    positional: list[str] = []
    skip_next = False
    for argument in args:
        if skip_next:
            skip_next = False
            continue
        if argument in ("-p", "-o", "--rootdir"):
            skip_next = True
            continue
        if isinstance(argument, str) and not argument.startswith("-"):
            positional.append(argument)
    return tuple(positional)


def _derive_run_identity(session: object) -> tuple[str, tuple[str, ...]]:
    """The deterministic run kind and planned node ids of this invocation.

    COLLECT_ONLY comes from the collect-only option; a run whose frozen
    positional arguments are exact target identities (anything other than
    the workspace root path — node ids with or without ``::``, per the
    frozen plan vocabulary) is TARGET_TESTS with those exact ids as the
    plan; anything else is FULL_PYTEST whose plan is the full collected
    set.
    """
    config = getattr(session, "config", None)
    if config is not None and getattr(config, "getoption", None) is not None:
        collect_only = bool(config.getoption("collectonly", False))
    else:
        collect_only = False
    positional = _positional_args(config)
    if collect_only:
        return "COLLECT_ONLY", ()
    rootdir = ""
    if config is not None:
        root = getattr(config, "rootdir", None)
        if root is not None:
            rootdir = str(root)
    if positional and any(argument != rootdir for argument in positional):
        return "TARGET_TESTS", positional
    return "FULL_PYTEST", ()


def pytest_sessionfinish(session: object, exitstatus: object) -> None:
    """Emit exactly one canonical PytestEvidenceV1 document on stdout."""
    if not _STATE.events or _STATE.events[0].get("event_type") != "SESSION_START":
        return
    if _STATE.sequence > MAX_REPORT_EVENTS:
        raise RuntimeError("the report event count exceeds the bounded v1 report cap")
    if not isinstance(exitstatus, int) or isinstance(exitstatus, bool):
        raise RuntimeError("pytest session exit status must be an integer")
    collected: list[str] = []
    for event in _STATE.events:
        if event.get("event_type") != "COLLECTION_ITEM":
            continue
        node_field = event.get("node_id")
        if not isinstance(node_field, dict):
            continue
        node_value = node_field.get("value")
        if isinstance(node_value, str):
            collected.append(node_value)
    run_kind, planned_args = _derive_run_identity(session)
    if run_kind == "TARGET_TESTS":
        planned: tuple[str, ...] = planned_args
    else:
        planned = tuple(collected)
    _record_event("SESSION_END")
    body: dict[str, object] = {
        "schema_version": 1,
        "report_plugin_version": REPORT_PLUGIN_VERSION,
        "run_kind": run_kind,
        "planned_node_ids": list(planned),
        "collected_node_ids": list(collected),
        "events": _STATE.events,
        "pytest_exit_code": exitstatus,
        "event_count": len(_STATE.events),
        "normal_end_marker": True,
    }
    document: dict[str, object] = {
        **body,
        "integrity_digest": _domain_separated_digest("PytestEvidenceV1", 1, body),
    }
    line = STDOUT_EVENT_PREFIX + _canonical_json_bytes(document).decode("utf-8")
    print(line, flush=True)
    _STATE.events = []
    _STATE.sequence = 0
