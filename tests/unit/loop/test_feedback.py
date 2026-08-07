"""T24.1 legacy step 24.A: structured bounded feedback construction tests.

The exact RED test pins the mandatory newest-failure retention; the matrix
pins the exact selection contract (unconsumed filter, severity/recency/id
ordering, the 10-record and 32 KiB bounds, and the newest required failure
surviving both limits), and the domain tests pin the deterministic
normalization of typed check/action/control failures into bounded
source-attributed records with stable occurrence ids, canonical
timestamps, bounded summaries, structured source attribution, canonical
payloads, and evidence references.
"""

from __future__ import annotations

from typing import cast

import pytest

# The builder consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips cleanly
# there (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.canonical.clock import FakeClockV1
from vespercode.canonical.digest import domain_digest
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.action import (
    ActionErrorV1,
    ActionResultV1,
    ActionStatusV1,
    CheckPlanIdV1,
)
from vespercode.contracts.evidence import (
    ArtifactRefV1,
    DigestV1,
    StableControlErrorV1,
)
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.loop.feedback import (
    FEEDBACK_MAX_BYTES_V1,
    FEEDBACK_MAX_RECORDS_V1,
    ActionFeedbackSourceV1,
    CheckFeedbackSourceV1,
    ControlFeedbackSourceV1,
    FeedbackConstructionErrorV1,
    FeedbackRecordSequenceV1,
    FeedbackRecordV1,
    FeedbackSelectionV1,
    FeedbackSeverityV1,
    build_feedback,
    feedback_canonical_bytes,
    select_feedback,
    serialize_feedback_record,
    serialize_feedback_source,
)
from vespercode.validation.check_result import (
    CheckFindingLocationV1,
    CheckFindingV1,
    CheckResultV1,
)

_CLOCK = FakeClockV1.from_epoch_milliseconds(1_781_640_000_000)
"""A fixed deterministic clock; build_feedback reads only ``now()``."""

CHECK_FAIL = CheckResultV1(
    status="FAIL",
    check_kind="TARGET_TESTS",
    structured_findings=(
        CheckFindingV1(
            error_code="CHECK_FAILED",
            message="assert x == 1",
            location=CheckFindingLocationV1(
                path="src/pkg/a.py",
                line=7,
                column=PresentV1(kind="PRESENT", value=3),
            ),
        ),
        CheckFindingV1(
            error_code="CHECK_FAILED",
            message="assert y == 2",
            location=CheckFindingLocationV1(
                path="src/pkg/b.py", line=9, column=AbsentV1(kind="ABSENT")
            ),
        ),
    ),
    raw_digest="a" * 64,
)


def feedback_record(
    *,
    record_id: str,
    severity: FeedbackSeverityV1 = "HIGH",
    created_at: str = "2026-08-06T09:00:00.000Z",
    summary: str = "check failed",
    consumed_by_turn: str | None = None,
    bounded_payload: str = '{"check_kind":"TARGET_TESTS","status":"FAIL"}',
    evidence_refs: tuple[str, ...] = (),
) -> FeedbackRecordV1:
    """One deterministic valid record (helper duplication is deliberate)."""
    return FeedbackRecordV1(
        id=record_id,
        kind="CHECK",
        severity=severity,
        created_at=CanonicalTimestampV1(created_at),
        summary=summary,
        source_ref=CheckFeedbackSourceV1(
            kind="CHECK",
            check_kind="TARGET_TESTS",
            path=AbsentV1(kind="ABSENT"),
        ),
        bounded_payload=bounded_payload,
        evidence_refs=evidence_refs,
        consumed_by_turn=consumed_by_turn,
    )


def bulky_feedback_record(*, record_id: str, created_at: str) -> FeedbackRecordV1:
    """One maximum-size valid record for the exact 32 KiB byte-limit case.

    The summary is at the 512-character bound, the canonical payload at
    the 4096-byte bound, and the eight evidence references each at the
    128-character bound, so every record serializes to roughly 5.7 KiB
    and ten of them always exceed the 32 KiB selection budget.
    """
    return feedback_record(
        record_id=record_id,
        severity="HIGH",
        created_at=created_at,
        summary="S" * 512,
        bounded_payload='{"p":"' + "X" * 4086 + '"}',
        evidence_refs=tuple("r" * 128 for _ in range(8)),
    )


def action_result(
    action_id: str,
    status: ActionStatusV1,
    error: ActionErrorV1 | None,
    result_type: str = "ApplyCandidatePatchResult",
) -> ActionResultV1:
    """One deterministic action result with the exact instance digest."""
    semantic_digest = "e" * 64
    instance_digest = domain_digest(
        "ActionInstanceDigestV1",
        1,
        {
            "schema_version": 1,
            "action_id": action_id,
            "semantic_digest": semantic_digest,
        },
    )
    error_field = (
        AbsentV1(kind="ABSENT")
        if error is None
        else PresentV1(kind="PRESENT", value=error)
    )
    return ActionResultV1(
        schema_version=1,
        action_id=action_id,
        semantic_digest=semantic_digest,
        instance_digest=instance_digest,
        status=status,
        result_type=result_type,
        payload_ref=AbsentV1(kind="ABSENT"),
        error=error_field,
    )


def over_limit_records_with_newest_failure() -> FeedbackRecordSequenceV1:
    """Twelve unconsumed records; the newest failure ranks below the limit.

    Eleven HIGH records are all more relevant than the newest MEDIUM
    failure by severity, so a plain top-10 selection would drop it; the
    mandatory retention must keep the newest required failure as the last
    selected record.
    """
    records = [
        feedback_record(
            record_id=f"high-{index}",
            severity="HIGH",
            created_at=f"2026-08-06T09:{index:02d}:00.000Z",
        )
        for index in range(11)
    ]
    records.append(
        feedback_record(
            record_id="newest-failure",
            severity="MEDIUM",
            created_at="2026-08-06T10:00:00.000Z",
        )
    )
    return tuple(records)


def test_newest_failure_survives_feedback_limit() -> None:
    selection = select_feedback(over_limit_records_with_newest_failure())
    assert selection.records[-1].id == "newest-failure"


def test_feedback_selection_matrix() -> None:
    """PLAN Registry row 24.A: the exact bounded selection matrix.

    Per the SPEC_PROCESS 49 precedent the card Expected line is the
    operative matrix authority: stable inputs produce stable records and
    order, and the newest required failure survives the exact count and
    byte limits.  The selection is the ordered non-mandatory records
    (severity, then newest time, then stable id) followed by the newest
    required failure — the unconsumed record with the latest canonical
    timestamp (id tie-break) — anchored last.
    """
    # --- Stable inputs produce stable records and order. ---
    critical = feedback_record(
        record_id="critical-1",
        severity="CRITICAL",
        created_at="2026-08-06T09:00:00.000Z",
    )
    high_newer = feedback_record(
        record_id="high-new",
        severity="HIGH",
        created_at="2026-08-06T09:01:00.000Z",
    )
    high_older = feedback_record(
        record_id="high-old",
        severity="HIGH",
        created_at="2026-08-06T08:59:00.000Z",
    )
    medium = feedback_record(
        record_id="medium-1",
        severity="MEDIUM",
        created_at="2026-08-06T08:58:00.000Z",
    )
    low = feedback_record(
        record_id="low-1",
        severity="LOW",
        created_at="2026-08-06T08:57:00.000Z",
    )
    first = select_feedback((medium, high_newer, critical, low, high_older))
    second = select_feedback((medium, high_newer, critical, low, high_older))
    assert first == second
    # Severity order among the non-mandatory records; the newest required
    # failure (high-new, 09:01) is anchored as the last selected record.
    assert [record.id for record in first.records] == [
        "critical-1",
        "high-old",
        "medium-1",
        "low-1",
        "high-new",
    ]
    assert first.refs == (
        "critical-1",
        "high-old",
        "medium-1",
        "low-1",
        "high-new",
    )

    # --- Recency within a severity, newest required failure anchored. ---
    recency = select_feedback(
        (
            high_older,
            feedback_record(
                record_id="high-mid",
                severity="HIGH",
                created_at="2026-08-06T09:00:00.000Z",
            ),
            low,
            high_newer,
        )
    )
    assert [record.id for record in recency.records] == [
        "high-mid",
        "high-old",
        "low-1",
        "high-new",
    ]

    # --- Stable id tie-break among equally recent records. ---
    tied = select_feedback(
        (
            feedback_record(
                record_id="tie-c",
                severity="HIGH",
                created_at="2026-08-06T09:00:00.000Z",
            ),
            feedback_record(
                record_id="tie-a",
                severity="HIGH",
                created_at="2026-08-06T09:00:00.000Z",
            ),
            feedback_record(
                record_id="tie-b",
                severity="HIGH",
                created_at="2026-08-06T09:00:00.000Z",
            ),
            feedback_record(
                record_id="anchor-1",
                severity="MEDIUM",
                created_at="2026-08-06T09:01:00.000Z",
            ),
        )
    )
    assert [record.id for record in tied.records] == [
        "tie-a",
        "tie-b",
        "tie-c",
        "anchor-1",
    ]

    # --- Consumed records are never selected. ---
    consumed = feedback_record(
        record_id="consumed-1",
        severity="CRITICAL",
        created_at="2026-08-06T10:00:00.000Z",
        consumed_by_turn="turn-1",
    )
    assert select_feedback((consumed, high_older)).records[0].id == "high-old"
    assert select_feedback((consumed,)).records == ()
    assert select_feedback((consumed,)).refs == ()

    # --- The exact count limit: at most 10, newest failure last. ---
    over_count = select_feedback(over_limit_records_with_newest_failure())
    assert len(over_count.records) == FEEDBACK_MAX_RECORDS_V1
    assert over_count.records[-1].id == "newest-failure"
    assert "high-2" in {record.id for record in over_count.records}
    # The two oldest HIGH records (09:00 and 09:01) are the dropped ones.
    assert "high-0" not in {record.id for record in over_count.records}
    assert "high-1" not in {record.id for record in over_count.records}

    # --- The exact byte limit: 32 KiB, newest failure never dropped. ---
    bulky = [
        bulky_feedback_record(
            record_id=f"bulky-{index}",
            created_at=f"2026-08-06T09:{index:02d}:00.000Z",
        )
        for index in range(11)
    ]
    bulky.append(
        bulky_feedback_record(
            record_id="newest-failure",
            created_at="2026-08-06T10:00:00.000Z",
        )
    )
    byte_selection = select_feedback(tuple(bulky))
    assert byte_selection.records[-1].id == "newest-failure"
    total = sum(feedback_canonical_bytes(record) for record in byte_selection.records)
    assert total <= FEEDBACK_MAX_BYTES_V1
    # Dropping stops from the least relevant end (the oldest records
    # first) with the exact resulting order; the newest failure stays.
    assert [record.id for record in byte_selection.records] == [
        "bulky-10",
        "bulky-9",
        "bulky-8",
        "bulky-7",
        "newest-failure",
    ]
    # The newest required failure alone always fits the budget.
    assert feedback_canonical_bytes(byte_selection.records[-1]) <= FEEDBACK_MAX_BYTES_V1


def test_build_feedback_check_fail_creates_one_record_per_finding() -> None:
    records = build_feedback(CHECK_FAIL, _CLOCK)
    assert len(records) == 2
    first, second = records
    assert first.kind == "CHECK"
    assert first.severity == "MEDIUM"
    assert first.created_at == _CLOCK.now()
    assert first.summary == "assert x == 1"
    assert first.source_ref.kind == "CHECK"
    assert isinstance(first.source_ref, CheckFeedbackSourceV1)
    assert first.source_ref.check_kind == "TARGET_TESTS"
    assert first.source_ref.path.kind == "PRESENT"
    assert isinstance(first.source_ref.path, PresentV1)
    assert first.source_ref.path.value.value == "src/pkg/a.py"
    assert isinstance(second.source_ref, CheckFeedbackSourceV1)
    assert isinstance(second.source_ref.path, PresentV1)
    assert second.source_ref.path.value.value == "src/pkg/b.py"
    assert first.evidence_refs == ()
    assert first.id == f"check:TARGET_TESTS:0:{_CLOCK.now().value}"
    assert second.id == f"check:TARGET_TESTS:1:{_CLOCK.now().value}"
    assert "check_kind" in first.bounded_payload
    assert "raw_digest" in first.bounded_payload
    # The canonical serialization is the single semantic authority.
    payload_text = serialize_feedback_record(first)
    assert '"summary":"assert x == 1"' in payload_text
    assert first.id in payload_text


def test_build_feedback_check_error_and_timeout_are_high_severity() -> None:
    error = build_feedback(
        CheckResultV1(
            status="ERROR",
            check_kind="RUFF",
            structured_findings=(
                CheckFindingV1(
                    error_code="CHECK_ERROR",
                    message="output is empty: completeness cannot be proven",
                    location=None,
                ),
            ),
            raw_digest="b" * 64,
        ),
        _CLOCK,
    )
    assert len(error) == 1
    assert error[0].severity == "HIGH"
    assert error[0].id.startswith("check:RUFF:0:")
    timeout = build_feedback(
        CheckResultV1(
            status="TIMEOUT",
            check_kind="MYPY",
            structured_findings=(
                CheckFindingV1(
                    error_code="CHECK_TIMEOUT",
                    message="check timed out",
                    location=None,
                ),
            ),
            raw_digest="c" * 64,
        ),
        _CLOCK,
    )
    assert len(timeout) == 1
    assert timeout[0].severity == "HIGH"


def test_build_feedback_ignores_check_pass_and_not_run() -> None:
    for status in ("PASS", "NOT_RUN"):
        result = CheckResultV1(
            status=status,
            check_kind="RUFF",
            structured_findings=(),
            raw_digest="d" * 64,
        )
        assert build_feedback(result, _CLOCK) == ()


def test_build_feedback_action_rejections_and_failures() -> None:
    rejected = action_result(
        "action-1",
        "REJECTED",
        ActionErrorV1(
            error_code="PATCH_PATH_NOT_EDITABLE",
            bounded_message="path is not editable",
            evidence_ref=AbsentV1(kind="ABSENT"),
        ),
    )
    records = build_feedback(rejected, _CLOCK)
    assert len(records) == 1
    record = records[0]
    assert record.kind == "ACTION"
    assert record.severity == "HIGH"
    assert record.source_ref.kind == "ACTION"
    assert record.source_ref.action_id == "action-1"
    assert record.summary == "path is not editable"
    assert record.id.startswith("action:")
    assert record.evidence_refs == ()
    # A failed action with an evidence reference carries the artifact ref.
    failed = action_result(
        "action-2",
        "FAILED",
        ActionErrorV1(
            error_code="FILE_NOT_TEXT",
            bounded_message="not a text file",
            evidence_ref=PresentV1(
                kind="PRESENT",
                value=ArtifactRefV1(
                    artifact_id="artifact-9",
                    digest=DigestV1(value="a" * 64),
                ),
            ),
        ),
        result_type="ReadFileResult",
    )
    failed_records = build_feedback(failed, _CLOCK)
    assert len(failed_records) == 1
    assert failed_records[0].evidence_refs == ("artifact-9",)
    assert failed_records[0].id.startswith("action:")


def test_build_feedback_ignores_succeeded_actions() -> None:
    succeeded = action_result(
        "action-3", "SUCCEEDED", None, result_type="ListFilesResult"
    )
    assert build_feedback(succeeded, _CLOCK) == ()


def test_build_feedback_control_failure_is_critical() -> None:
    records = build_feedback(
        StableControlErrorV1(
            error_code="CREDENTIAL_MISSING",
            bounded_message="credential missing",
        ),
        _CLOCK,
    )
    assert len(records) == 1
    record = records[0]
    assert record.kind == "CONTROL"
    assert record.severity == "CRITICAL"
    assert record.source_ref.kind == "CONTROL"
    assert record.source_ref.error_code == "CREDENTIAL_MISSING"
    assert record.id == f"control:CREDENTIAL_MISSING:{_CLOCK.now().value}"
    assert record.summary == "credential missing"


def test_build_feedback_is_deterministic() -> None:
    first = build_feedback(CHECK_FAIL, _CLOCK)
    second = build_feedback(CHECK_FAIL, _CLOCK)
    assert first == second
    assert serialize_feedback_record(first[0]) == serialize_feedback_record(second[0])


def test_build_feedback_truncates_oversized_summaries() -> None:
    long_message = "X" * 900
    result = CheckResultV1(
        status="FAIL",
        check_kind="TARGET_TESTS",
        structured_findings=(
            CheckFindingV1(
                error_code="CHECK_FAILED",
                message=long_message,
                location=None,
            ),
        ),
        raw_digest="a" * 64,
    )
    records = build_feedback(result, _CLOCK)
    assert len(records) == 1
    assert len(records[0].summary) == 512
    assert records[0].summary == long_message[:512]
    # Truncation never emits a dangling surrogate code unit at the cut:
    # a directly constructed message ending in a surrogate pair bounds
    # to the scalar-safe prefix instead of failing the whole source.
    pair_message = "X" * 511 + "😀"
    pair_result = CheckResultV1(
        status="FAIL",
        check_kind="TARGET_TESTS",
        structured_findings=(
            CheckFindingV1(
                error_code="CHECK_FAILED",
                message=pair_message,
                location=None,
            ),
        ),
        raw_digest="a" * 64,
    )
    pair_records = build_feedback(pair_result, _CLOCK)
    assert len(pair_records) == 1
    assert pair_records[0].summary == "X" * 511 + "😀"
    # A directly constructed message whose 513th code unit is a dangling
    # surrogate half bounds to the scalar-safe prefix: the cut never
    # emits a lone surrogate into the summary.
    split_message = "X" * 511 + chr(0xD83D) + chr(0xDE00)
    split_result = CheckResultV1(
        status="FAIL",
        check_kind="TARGET_TESTS",
        structured_findings=(
            CheckFindingV1(
                error_code="CHECK_FAILED",
                message=split_message,
                location=None,
            ),
        ),
        raw_digest="a" * 64,
    )
    split_records = build_feedback(split_result, _CLOCK)
    assert len(split_records) == 1
    assert split_records[0].summary == "X" * 511
    # A mid-string lone surrogate still fails closed.
    with pytest.raises(FeedbackConstructionErrorV1, match="normalize"):
        build_feedback(
            CheckResultV1(
                status="FAIL",
                check_kind="TARGET_TESTS",
                structured_findings=(
                    CheckFindingV1(
                        error_code="CHECK_FAILED",
                        message="X" * 100 + "\ud800" + "Y" * 500,
                        location=None,
                    ),
                ),
                raw_digest="a" * 64,
            ),
            _CLOCK,
        )


def test_build_feedback_rejects_non_canonical_inputs() -> None:
    with pytest.raises(FeedbackConstructionErrorV1, match="normalize"):
        build_feedback(
            StableControlErrorV1(
                error_code="BAD-\ud800",
                bounded_message="surrogate",
            ),
            _CLOCK,
        )
    with pytest.raises(FeedbackConstructionErrorV1, match="supported"):
        build_feedback("not-a-typed-source", _CLOCK)  # type: ignore[arg-type]
    with pytest.raises(FeedbackConstructionErrorV1, match="normalize"):
        build_feedback(
            StableControlErrorV1(
                error_code="X" * 65,
                bounded_message="too long",
            ),
            _CLOCK,
        )


def test_feedback_record_contract_is_closed() -> None:
    with pytest.raises(ValidationError):
        feedback_record(record_id="")
    with pytest.raises(ValidationError):
        feedback_record(record_id="x" * 129)
    with pytest.raises(ValidationError):
        feedback_record(record_id="ok", summary="")
    with pytest.raises(ValidationError):
        feedback_record(record_id="ok", summary="x" * 513)
    with pytest.raises(ValidationError):
        FeedbackRecordV1(
            id="ok",
            kind="CHECK",
            severity="URGENT",  # type: ignore[arg-type]
            created_at=CanonicalTimestampV1("2026-08-06T09:00:00.000Z"),
            summary="s",
            source_ref=CheckFeedbackSourceV1(
                kind="CHECK",
                check_kind="RUFF",
                path=AbsentV1(kind="ABSENT"),
            ),
            bounded_payload='{"x":1}',
        )
    with pytest.raises(ValidationError):
        # The record kind must match the source attribution kind.
        FeedbackRecordV1(
            id="ok",
            kind="CHECK",
            severity="HIGH",
            created_at=CanonicalTimestampV1("2026-08-06T09:00:00.000Z"),
            summary="s",
            source_ref=ActionFeedbackSourceV1(
                kind="ACTION",
                action_id="action-9",
                semantic_digest="a" * 64,
            ),
            bounded_payload='{"x":1}',
        )
    with pytest.raises(ValidationError):
        feedback_record(record_id="ok", consumed_by_turn="x" * 129)
    # The evidence-reference bounds are exact: cardinality, length, and
    # the canonical JSON text against the v0008 stored-row bound.
    with pytest.raises(ValidationError):
        feedback_record(
            record_id="ok",
            evidence_refs=tuple(f"ref-{index}" for index in range(9)),
        )
    with pytest.raises(ValidationError):
        feedback_record(record_id="ok", evidence_refs=("r" * 129,))
    with pytest.raises(ValidationError):
        feedback_record(
            record_id="ok",
            evidence_refs=tuple('"' * 128 for _ in range(8)),
        )
    # The bounded payload bound is exact (4096 UTF-8 bytes).
    with pytest.raises(ValidationError):
        feedback_record(record_id="ok", bounded_payload='{"p":"' + "X" * 4089 + '"}')
    selection = FeedbackSelectionV1(records=())
    assert selection.records == ()
    assert selection.refs == ()


def test_feedback_source_attribution_is_bounded() -> None:
    """Task 24.A bounded records are always appendable by Task 24.C.

    The v0008 ``source_ref`` column backstops the canonical attribution
    at 256 characters, so the record rejects any attribution whose
    canonical text exceeds that exact bound (a closed rejection before
    any append exists); a long but fitting attributed path stays valid.
    """
    fitted = FeedbackRecordV1(
        id="long-path",
        kind="CHECK",
        severity="HIGH",
        created_at=CanonicalTimestampV1("2026-08-06T09:00:00.000Z"),
        summary="long attributed path",
        source_ref=CheckFeedbackSourceV1(
            kind="CHECK",
            check_kind="TARGET_TESTS",
            path=PresentV1(
                kind="PRESENT",
                value=CanonicalRelativePathV1("src/" + "a" * 100 + ".py"),
            ),
        ),
        bounded_payload='{"check_kind":"TARGET_TESTS"}',
    )
    assert len(serialize_feedback_source(fitted.source_ref)) <= 256
    with pytest.raises(ValidationError, match="source attribution"):
        FeedbackRecordV1(
            id="too-long-path",
            kind="CHECK",
            severity="HIGH",
            created_at=CanonicalTimestampV1("2026-08-06T09:00:00.000Z"),
            summary="oversized attributed path",
            source_ref=CheckFeedbackSourceV1(
                kind="CHECK",
                check_kind="TARGET_TESTS",
                path=PresentV1(
                    kind="PRESENT",
                    value=CanonicalRelativePathV1("src/" + "a" * 300 + ".py"),
                ),
            ),
            bounded_payload='{"check_kind":"TARGET_TESTS"}',
        )
    # The builder converts the oversized attribution into the closed
    # construction rejection, never a raw exception.
    with pytest.raises(FeedbackConstructionErrorV1, match="normalize"):
        build_feedback(
            CheckResultV1(
                status="FAIL",
                check_kind="TARGET_TESTS",
                structured_findings=(
                    CheckFindingV1(
                        error_code="CHECK_FAILED",
                        message="assert x == 1",
                        location=CheckFindingLocationV1(
                            path="src/" + "a" * 300 + ".py",
                            line=1,
                            column=AbsentV1(kind="ABSENT"),
                        ),
                    ),
                ),
                raw_digest="a" * 64,
            ),
            _CLOCK,
        )


def test_feedback_source_attribution_is_closed() -> None:
    with pytest.raises(ValidationError):
        CheckFeedbackSourceV1(
            kind="CHECK",
            check_kind=cast("CheckPlanIdV1", "OTHER"),
            path=AbsentV1(kind="ABSENT"),
        )
    with pytest.raises(ValidationError):
        ActionFeedbackSourceV1(kind="ACTION", action_id="", semantic_digest="a" * 64)
    with pytest.raises(ValidationError):
        ActionFeedbackSourceV1(kind="ACTION", action_id="a", semantic_digest="x")
    with pytest.raises(ValidationError):
        ControlFeedbackSourceV1(kind="CONTROL", error_code="X" * 65)
    assert (
        ControlFeedbackSourceV1(
            kind="CONTROL", error_code="CREDENTIAL_MISSING"
        ).error_code
        == "CREDENTIAL_MISSING"
    )
