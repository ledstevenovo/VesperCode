"""T19.1 legacy step 19.B: authoritative pytest event evidence.

``parse_pytest_evidence`` validates one bounded raw report channel into
the single complete ordered ``PytestEvidenceV1`` and fails closed with the
stable ``REPORTER_INVALID`` error for missing, duplicate, reordered,
truncated, over-limit, corrupt, schema-violating, exit-inconsistent, or
expectation-mismatched evidence (SPEC §4.5).  The report's integrity and
normal end are authoritative over any exit code or console text: stdout/
stderr and the process exit code can never supplement or override missing
structured facts ("stdout/stderr 和 pytest 退出码不能补足或覆盖缺失的
结构化事实").

The channel is the fixed ``GATEEV1:`` stdout line (the T02.4-proven
mechanism): the plugin emits exactly one canonical JSON document of the
complete report; the parser extracts it from the bounded stdout bytes
independently of interleaved console text.  ``PytestEvidenceV1`` is
self-authoritative: every closed invariant (ordered sequences, terminal
session events, event/exit consistency, event count, and the §0.1
integrity binding) is model-enforced, so any constructed evidence is
complete by construction.

Owns plugin report-schema validation only.  Fingerprinting, Baseline
orchestration, static-tool parsing, and PASS synthesis from other
channels remain out of scope (GREEN-4).
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)

from vespercode.canonical.digest import domain_digest
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.optional import AbsentV1, PresentV1

# The fixed stdout channel prefix (SPEC §4.5 machine-readable report
# channel; the T02.4-proven GATEEV1 mechanism).  The production plugin
# module carries its own copy so it stays self-contained inside the
# offline execution image.
STDOUT_EVENT_PREFIX = "GATEEV1:"

# The hard report-event cap shared with the plugin: no emitted or parsed
# report may carry more events; the expectation declares the plan-frozen
# bound it compares against.
MAX_REPORT_EVENTS = 65536

ErrorPhase = Literal["COLLECTION", "SETUP", "CALL", "TEARDOWN", "ENVIRONMENT"]
TestStatus = Literal[
    "PASS", "FAIL", "SKIP", "XFAIL", "XPASS", "DESELECTED", "ERROR", "NOT_RUN"
]
RunKindV1 = Literal["COLLECT_ONLY", "FULL_PYTEST", "TARGET_TESTS"]
EventTypeV1 = Literal[
    "SESSION_START",
    "COLLECTION_ITEM",
    "TEST_PHASE",
    "DESELECTED",
    "SESSION_ERROR",
    "SESSION_END",
]
OptionalTextV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[StrictStr], Field(discriminator="kind")
]
OptionalBooleanV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[Annotated[bool, Strict()]], Field(discriminator="kind")
]
OptionalErrorPhaseV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[ErrorPhase], Field(discriminator="kind")
]
OptionalTestStatusV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[TestStatus], Field(discriminator="kind")
]


def _reject_coerced_schema_version(value: object) -> object:
    """Reject bool/float/string spellings of the integer literal 1."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("schema_version must be the decimal integer 1")
    return value


def _require_present_text(optional: OptionalTextV1, field_name: str) -> str:
    """One PRESENT non-empty text value or a closed rejection."""
    if not isinstance(optional, PresentV1) or optional.value == "":
        raise ValueError(f"{field_name} must be an explicit non-empty PRESENT value")
    return optional.value


def _require_absent(optional: AbsentV1 | PresentV1[Any], field_name: str) -> None:
    if not isinstance(optional, AbsentV1):
        raise ValueError(f"{field_name} must be explicitly ABSENT for this event type")


class ProjectFrameV1(BaseModel):
    """One project stack frame of a structured exception (SPEC §4.5).

    The relative path is a canonical repository-relative path; the line
    number is the exact reported source line.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    relative_path: CanonicalRelativePathV1
    function_name: StrictStr
    line_number: Annotated[int, Strict()]

    @field_validator("relative_path", mode="before")
    @classmethod
    def _relative_path_is_document_string(cls, value: object) -> object:
        """Accept the document JSON form: one plain canonical path string."""
        if isinstance(value, str):
            return CanonicalRelativePathV1(value)
        return value

    @field_validator("function_name")
    @classmethod
    def _function_name_is_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("function names must not be empty")
        return value

    @field_validator("line_number", mode="before")
    @classmethod
    def _line_number_is_positive(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError("line numbers must be positive decimal integers")
        return value


class StructuredExceptionV1(BaseModel):
    """One complete structured exception of a failed event (SPEC §4.5).

    ``normalized_assertion_diff`` is explicitly ABSENT for non-assertion
    exceptions and PRESENT for assertion failures the reporter observed;
    the fingerprint layer enforces that applicability rule.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    exception_type: StrictStr
    normalized_message: StrictStr
    normalized_assertion_diff: OptionalTextV1
    project_frames: tuple[ProjectFrameV1, ...]

    @field_validator("exception_type", "normalized_message")
    @classmethod
    def _exception_fields_are_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("exception type and message must not be empty")
        return value


OptionalStructuredExceptionV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[StructuredExceptionV1], Field(discriminator="kind")
]


class PytestEventV1(BaseModel):
    """One closed pytest lifecycle event (SPEC §4.5 PytestEventV1).

    Every optional field is an explicit ABSENT/PRESENT union; the
    per-event-type field combinations are closed and model-enforced
    (inapplicable fields must be ABSENT, TEST_PHASE requires node/phase/
    outcome, failures and errors require a structured exception).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    sequence: Annotated[int, Strict()]
    event_type: EventTypeV1
    node_id: OptionalTextV1
    phase: OptionalErrorPhaseV1
    outcome: OptionalTestStatusV1
    wasxfail: OptionalBooleanV1
    exception: OptionalStructuredExceptionV1
    display_summary: OptionalTextV1

    @field_validator("sequence", mode="before")
    @classmethod
    def _sequence_is_positive_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError("event sequences must be positive decimal integers")
        return value

    @model_validator(mode="after")
    def _require_closed_event_combination(self) -> PytestEventV1:
        node = self.node_id
        phase = self.phase
        outcome = self.outcome
        wasxfail = self.wasxfail
        exception = self.exception
        display = self.display_summary
        if self.event_type == "SESSION_START":
            for name, value in (
                ("node_id", node),
                ("phase", phase),
                ("outcome", outcome),
                ("wasxfail", wasxfail),
                ("exception", exception),
                ("display_summary", display),
            ):
                _require_absent(value, name)
        elif self.event_type == "COLLECTION_ITEM":
            _require_present_text(node, "node_id")
            for name, value in (
                ("phase", phase),
                ("outcome", outcome),
                ("wasxfail", wasxfail),
                ("exception", exception),
                ("display_summary", display),
            ):
                _require_absent(value, name)
        elif self.event_type == "TEST_PHASE":
            _require_present_text(node, "node_id")
            if not isinstance(phase, PresentV1):
                raise ValueError("TEST_PHASE events require an explicit phase")
            if not isinstance(outcome, PresentV1):
                raise ValueError("TEST_PHASE events require an explicit outcome")
            if isinstance(outcome.value, str) and outcome.value not in (
                "PASS",
                "FAIL",
                "SKIP",
                "XFAIL",
                "XPASS",
                "ERROR",
                "NOT_RUN",
            ):
                raise ValueError("TEST_PHASE outcomes are a closed vocabulary")
            _require_absent(display, "display_summary")
            if outcome.value in ("XFAIL", "XPASS"):
                if not isinstance(wasxfail, PresentV1) or wasxfail.value is not True:
                    raise ValueError("XFAIL/XPASS events require wasxfail PRESENT true")
            else:
                _require_absent(wasxfail, "wasxfail")
            if outcome.value in ("FAIL", "ERROR"):
                if not isinstance(exception, PresentV1):
                    raise ValueError("FAIL/ERROR events require a structured exception")
                if not exception.value.project_frames:
                    raise ValueError(
                        "FAIL/ERROR events require at least one project frame"
                    )
                if outcome.value == "FAIL" and phase.value != "CALL":
                    raise ValueError("FAIL events must be in the CALL phase")
                if outcome.value == "ERROR" and phase.value == "CALL":
                    raise ValueError("ERROR events cannot be in the CALL phase")
            else:
                _require_absent(exception, "exception")
        elif self.event_type == "DESELECTED":
            _require_present_text(node, "node_id")
            for name, value in (
                ("phase", phase),
                ("outcome", outcome),
                ("wasxfail", wasxfail),
                ("exception", exception),
                ("display_summary", display),
            ):
                _require_absent(value, name)
        elif self.event_type == "SESSION_ERROR":
            if not isinstance(exception, PresentV1):
                raise ValueError("SESSION_ERROR events require a structured exception")
            for name, value in (
                ("node_id", node),
                ("phase", phase),
                ("outcome", outcome),
                ("wasxfail", wasxfail),
                ("display_summary", display),
            ):
                _require_absent(value, name)
        elif self.event_type == "SESSION_END":
            for name, value in (
                ("node_id", node),
                ("phase", phase),
                ("outcome", outcome),
                ("wasxfail", wasxfail),
                ("exception", exception),
                ("display_summary", display),
            ):
                _require_absent(value, name)
        return self


def _structured_exception_document(
    exception: StructuredExceptionV1,
) -> dict[str, object]:
    """One structured exception in the exact document JSON form.

    The relative path is the plain canonical string (the document form),
    never the pydantic dataclass wrapper, so the recomputed digest binds
    the exact emitted report bytes.
    """
    diff = exception.normalized_assertion_diff
    if isinstance(diff, PresentV1):
        diff_document: dict[str, object] = {"kind": "PRESENT", "value": diff.value}
    else:
        diff_document = {"kind": "ABSENT"}
    return {
        "exception_type": exception.exception_type,
        "normalized_message": exception.normalized_message,
        "normalized_assertion_diff": diff_document,
        "project_frames": tuple(
            {
                "relative_path": frame.relative_path.value,
                "function_name": frame.function_name,
                "line_number": frame.line_number,
            }
            for frame in exception.project_frames
        ),
    }


def _event_document(event: PytestEventV1) -> dict[str, object]:
    """One event in the exact document JSON form (SPEC §4.5)."""
    fields: list[tuple[str, AbsentV1 | PresentV1[Any]]] = [
        ("node_id", event.node_id),
        ("phase", event.phase),
        ("outcome", event.outcome),
        ("wasxfail", event.wasxfail),
        ("exception", event.exception),
        ("display_summary", event.display_summary),
    ]
    document: dict[str, object] = {
        "sequence": event.sequence,
        "event_type": event.event_type,
    }
    for name, optional in fields:
        if isinstance(optional, PresentV1):
            if isinstance(optional.value, StructuredExceptionV1):
                document[name] = {
                    "kind": "PRESENT",
                    "value": _structured_exception_document(optional.value),
                }
            else:
                document[name] = {"kind": "PRESENT", "value": optional.value}
        else:
            document[name] = {"kind": "ABSENT"}
    return document


def _evidence_digest_body(evidence: PytestEvidenceV1) -> dict[str, object]:
    """Every field except the integrity digest, in the exact document form."""
    return {
        "schema_version": evidence.schema_version,
        "report_plugin_version": evidence.report_plugin_version,
        "run_kind": evidence.run_kind,
        "planned_node_ids": tuple(evidence.planned_node_ids),
        "collected_node_ids": tuple(evidence.collected_node_ids),
        "events": tuple(_event_document(event) for event in evidence.events),
        "pytest_exit_code": evidence.pytest_exit_code,
        "event_count": evidence.event_count,
        "normal_end_marker": evidence.normal_end_marker,
    }


def pytest_evidence_integrity_digest(evidence: PytestEvidenceV1) -> str:
    """Recompute the §0.1 integrity identity of one evidence (SPEC §4.5)."""
    return domain_digest(
        "PytestEvidenceV1",
        1,
        _evidence_digest_body(evidence),  # type: ignore[arg-type]
    )


class PytestEvidenceV1(BaseModel):
    """The complete ordered authoritative pytest report (SPEC §4.5).

    All fields are required and unknown fields reject; the integrity
    digest binds every other field through the canonical report bytes, so
    a constructed instance is authoritative by construction.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    report_plugin_version: StrictStr
    run_kind: RunKindV1
    planned_node_ids: tuple[StrictStr, ...]
    collected_node_ids: tuple[StrictStr, ...]
    events: tuple[PytestEventV1, ...]
    pytest_exit_code: Annotated[int, Strict()]
    event_count: Annotated[int, Strict()]
    normal_end_marker: Literal[True]
    integrity_digest: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("integrity_digest")
    @classmethod
    def _integrity_digest_is_64_lowercase_hex(cls, value: str) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError(
                "integrity_digest must be exactly 64 lowercase hexadecimal characters"
            )
        return value

    @model_validator(mode="after")
    def _require_complete_ordered_evidence(self) -> PytestEvidenceV1:
        events = self.events
        if len(events) != self.event_count:
            raise ValueError("event_count must equal the exact number of events")
        if any(event.sequence != index + 1 for index, event in enumerate(events)):
            raise ValueError("event sequences must be exactly 1..N with no gaps")
        if not events:
            raise ValueError("the report must carry at least one event")
        if events[0].event_type != "SESSION_START":
            raise ValueError("the first event must be SESSION_START")
        if events[-1].event_type != "SESSION_END":
            raise ValueError("the last event must be SESSION_END")
        if any(
            event.event_type in ("SESSION_START", "SESSION_END")
            for event in events[1:-1]
        ):
            raise ValueError("SESSION_START/SESSION_END may appear once each")
        any_failure = any(
            event.event_type == "SESSION_ERROR"
            or (
                event.event_type == "TEST_PHASE"
                and isinstance(event.outcome, PresentV1)
                and event.outcome.value in ("FAIL", "ERROR")
            )
            for event in events
        )
        if any_failure and self.pytest_exit_code == 0:
            raise ValueError("exit code contradicts the recorded failures")
        if not any_failure and self.pytest_exit_code != 0:
            raise ValueError("exit code is inconsistent with a clean report")
        collected_set = set(self.collected_node_ids)
        for event in events:
            if event.event_type in ("COLLECTION_ITEM", "TEST_PHASE", "DESELECTED"):
                if not isinstance(event.node_id, PresentV1):
                    raise ValueError("node events require an explicit node id")
                if event.node_id.value not in collected_set:
                    raise ValueError(
                        "event node id is not a member of the collected set"
                    )
        if self.integrity_digest != pytest_evidence_integrity_digest(self):
            raise ValueError("integrity_digest does not bind the report fields")
        return self


class PytestReportExpectationV1(BaseModel):
    """The declared expectation one report must match exactly.

    Binds the plan-frozen run kind, exact planned node ids, the declared
    report plugin version, and the bounded event cap; a report that
    mismatches any of them is ``REPORTER_INVALID``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    run_kind: RunKindV1
    planned_node_ids: tuple[StrictStr, ...]
    report_plugin_version: StrictStr
    max_events: Annotated[int, Strict()] = MAX_REPORT_EVENTS

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("max_events")
    @classmethod
    def _max_events_is_bounded(cls, value: int) -> int:
        if value < 1 or value > MAX_REPORT_EVENTS:
            raise ValueError("max_events must be within 1..65536")
        return value

    @field_validator("planned_node_ids")
    @classmethod
    def _planned_ids_are_non_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or any(node_id == "" for node_id in value):
            raise ValueError("planned node ids must be non-empty")
        return value


class PytestParseOutcomeV1(BaseModel):
    """The closed parse outcome: one evidence or the stable REPORTER_INVALID.

    ``error_code`` is ``REPORTER_INVALID`` exactly when the evidence is
    absent and a stable reason is present; success carries the evidence
    and an empty reason.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    error_code: Literal["REPORTER_INVALID"] | None
    evidence: PytestEvidenceV1 | None
    reason: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @model_validator(mode="after")
    def _require_closed_outcome(self) -> PytestParseOutcomeV1:
        if self.error_code is None:
            if self.evidence is None or self.reason != "":
                raise ValueError("success outcomes carry evidence and no reason")
        else:
            if self.evidence is not None or self.reason == "":
                raise ValueError("failures carry a stable reason and no evidence")
        return self


def _reporter_invalid(reason: str) -> PytestParseOutcomeV1:
    return PytestParseOutcomeV1(
        schema_version=1,
        error_code="REPORTER_INVALID",
        evidence=None,
        reason=reason,
    )


def _extract_channel_document(text: str) -> tuple[str | None, bool]:
    """Extract the single channel document from the bounded stdout text.

    Scans every ``GATEEV1:`` occurrence (the T02.4 stdout mirror may be
    interleaved with console text on the same physical line) and keeps the
    occurrence whose JSON decodes to a report-shaped object.  Returns
    ``(document, duplicate)``: the exact document text when exactly one
    report-shaped document exists, a duplicate flag when more than one
    exists (any channel duplication fails closed), and nothing when the
    channel is absent (the caller falls back to the whole text).
    """
    decoder = json.JSONDecoder()
    matches: list[str] = []
    start = 0
    while True:
        index = text.find(STDOUT_EVENT_PREFIX, start)
        if index < 0:
            break
        candidate = index + len(STDOUT_EVENT_PREFIX)
        try:
            obj, end = decoder.raw_decode(text, candidate)
        except json.JSONDecodeError:
            start = candidate
            continue
        if isinstance(obj, dict) and "schema_version" in obj and "events" in obj:
            matches.append(text[candidate:end])
        start = end
    if len(matches) == 1:
        return matches[0], False
    if len(matches) > 1:
        return None, True
    return None, False


def parse_pytest_evidence(
    raw: bytes,
    expectation: PytestReportExpectationV1,
) -> PytestParseOutcomeV1:
    """Parse one bounded raw report channel into the sole closed outcome.

    The report's integrity and normal end are authoritative over exit code
    and console text: a complete ordered document parses successfully even
    when the process exit code or the surrounding console text disagree,
    and a missing, duplicate, truncated, corrupt, or mismatched document
    always returns ``REPORTER_INVALID`` with a stable reason.
    """
    if raw == b"":
        return _reporter_invalid("report channel is empty")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return _reporter_invalid("report channel is not valid UTF-8")
    document_text, duplicate = _extract_channel_document(text)
    if duplicate:
        return _reporter_invalid("duplicate report channel documents")
    if document_text is None:
        document_text = text
    try:
        document = json.loads(document_text)
    except json.JSONDecodeError:
        return _reporter_invalid("report document is corrupt JSON")
    if not isinstance(document, dict):
        return _reporter_invalid("report document is not a JSON object")
    try:
        evidence = PytestEvidenceV1.model_validate(document)
    except ValidationError:
        return _reporter_invalid("report document violates the closed contract")
    if evidence.run_kind != expectation.run_kind:
        return _reporter_invalid("run kind does not match the expectation")
    if evidence.report_plugin_version != expectation.report_plugin_version:
        return _reporter_invalid("report plugin version does not match the expectation")
    if evidence.planned_node_ids != expectation.planned_node_ids:
        return _reporter_invalid("planned node ids do not match the expectation")
    if evidence.collected_node_ids != expectation.planned_node_ids:
        return _reporter_invalid("collected node ids do not match the plan")
    if len(evidence.events) > expectation.max_events:
        return _reporter_invalid("report event count exceeds the bounded expectation")
    return PytestParseOutcomeV1(
        schema_version=1,
        error_code=None,
        evidence=evidence,
        reason="",
    )
