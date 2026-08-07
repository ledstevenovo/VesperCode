"""T23.1 legacy step 23.A: transactional redacted audit repository tests.

Pins the append contract (unique increasing per-Run sequences, per-Run
independence, unknown-Run and sequence-overflow rejections with zero
rows and zero ledger residue, exact replay stability, event-id reuse
conflicts, and replay after an explicit clear never resurrecting removed
content), the stable keyset pagination contract (complete ordered pages,
bounded page sizes, cross-Run cursor rejection), and the explicit
ended-Run clear contract (ended Runs only, replay/conflict under the
T07.3 ledger, other Runs untouched).  Final registry edits, user
projection, external actions, and time-based retention remain out of
scope (GREEN-4).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

# The repository consumes pydantic runtime contracts; the hash-locked
# gate toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.audit.event import AuditEventTypeV1
from vespercode.audit.repository import (
    AppendAuditEventV1,
    AUDIT_SEQUENCE_MAX_V1,
    AuditCursorV1,
    AuditPageRequestV1,
    AuditPaginationErrorV1,
    AuditRepository,
    ClearEndedRunAuditV1,
)
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.storage.connection import (
    ControlDatabase,
    open_control_database,
)
from vespercode.storage.migration_engine import apply_migrations
from vespercode.storage.migrations.v0001_run_wait import RUN_WAIT_V1_MIGRATION
from vespercode.storage.migrations.v0002_idempotency import (
    IDEMPOTENCY_V1_MIGRATION,
)
from vespercode.storage.migrations.v0003_disclosure_grants import (
    DISCLOSURE_GRANTS_V1_MIGRATION,
)
from vespercode.storage.migrations.v0004_disclosure_authorizations import (
    DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
)
from vespercode.storage.migrations.v0005_memory import MEMORY_V1_MIGRATION
from vespercode.storage.migrations.v0006_audit import AUDIT_V1_MIGRATION

_CREATED_AT = CanonicalTimestampV1("2026-08-06T09:00:00.000Z")
_CLEARED_AT = CanonicalTimestampV1("2026-08-06T11:00:00.000Z")

_MIGRATIONS = (
    RUN_WAIT_V1_MIGRATION,
    IDEMPOTENCY_V1_MIGRATION,
    DISCLOSURE_GRANTS_V1_MIGRATION,
    DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
    MEMORY_V1_MIGRATION,
    AUDIT_V1_MIGRATION,
)


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "audit_repository.db")
    apply_migrations(database, _MIGRATIONS)
    yield database
    database.close()


@pytest.fixture
def repository(control_database: ControlDatabase) -> AuditRepository:
    audit_repository = AuditRepository(control_database)
    _seed_run(control_database, "run-1", "RUNNING", "AGENT_LOOP")
    return audit_repository


def _seed_run(
    database: ControlDatabase,
    run_id: str,
    status: str,
    phase: str | None,
) -> None:
    """Insert one deterministic run row (config snapshot + run)."""
    with database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots (config_snapshot_id, digest,"
            " llm_profile_id, reference_profile_id, policy_id, target_test_ids,"
            " limits_digest, frozen_at)"
            " VALUES (?, ?, 'llm-1', 'ref-1', 'policy-1', '[]', 'limits-1', ?)",
            (f"cfg-{run_id}", f"{run_id}{'a' * 64}"[:64], _CREATED_AT.value),
        )
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES (?, 'workspace-a', ?, ?, ?, 1, ?, ?)",
            (
                run_id,
                f"cfg-{run_id}",
                status,
                phase,
                _CREATED_AT.value,
                "2026-08-06T10:00:00.000Z",
            ),
        )


def append_event(
    event_type: str,
    payload: dict[str, str],
    *,
    run_id: str = "run-1",
    event_id: str,
    created_at: CanonicalTimestampV1 = _CREATED_AT,
    evidence_refs: tuple[str, ...] = (),
) -> AppendAuditEventV1:
    """One deterministic append command (helper duplication is deliberate)."""
    return AppendAuditEventV1(
        run_id=run_id,
        event_type=cast(AuditEventTypeV1, event_type),
        payload=payload,
        evidence_refs=evidence_refs,
        event_id=event_id,
        created_at=created_at,
    )


def first_page() -> AuditPageRequestV1:
    """The unbounded first page request."""
    return AuditPageRequestV1(page_size=100)


def test_append_assigns_unique_increasing_per_run_sequences(
    repository: AuditRepository,
) -> None:
    first = repository.append(
        append_event(
            "LIFECYCLE", {"status": "RUNNING", "phase": "PREFLIGHT"}, event_id="a-1"
        )
    )
    second = repository.append(
        append_event(
            "LIFECYCLE", {"status": "RUNNING", "phase": "BASELINE"}, event_id="a-2"
        )
    )
    assert first.kind == "APPENDED"
    assert first.event is not None
    assert second.event is not None
    assert [first.event.sequence, second.event.sequence] == [1, 2]
    _seed_run(repository.database, "run-b", "RUNNING", "AGENT_LOOP")
    other = repository.append(
        append_event(
            "LIFECYCLE",
            {"status": "RUNNING", "phase": "AGENT_LOOP"},
            run_id="run-b",
            event_id="b-1",
        )
    )
    assert other.event is not None
    assert other.event.sequence == 1
    assert repository.event_count == 3


def test_append_unknown_run_rejects_with_zero_rows_and_no_ledger(
    repository: AuditRepository,
) -> None:
    result = repository.append(
        append_event(
            "STOP_EVIDENCE",
            {"reason_code": "TURN_LIMIT"},
            run_id="no-such-run",
            event_id="unknown-1",
        )
    )
    assert result.kind == "REJECTED"
    assert result.error_code == "AUDIT_STORE_FAILED"
    assert result.event is None
    assert repository.event_count == 0
    # The NEW ledger record rolled back with the rejection.
    assert (
        len(
            repository.database.read_rows(
                "SELECT 1 FROM idempotency_events WHERE event_id = 'unknown-1'"
            )
        )
        == 0
    )


def test_append_sequence_overflow_rejects_with_zero_rows(
    repository: AuditRepository,
) -> None:
    assert (
        repository.append(
            append_event(
                "STOP_EVIDENCE", {"reason_code": "TURN_LIMIT"}, event_id="ov-1"
            )
        ).kind
        == "APPENDED"
    )
    with repository.database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE audit_events SET sequence = ? WHERE run_id = 'run-1'"
            " AND sequence = 1",
            (AUDIT_SEQUENCE_MAX_V1,),
        )
    result = repository.append(
        append_event("STOP_EVIDENCE", {"reason_code": "TURN_LIMIT"}, event_id="ov-2")
    )
    assert result.kind == "REJECTED"
    assert result.error_code == "AUDIT_STORE_FAILED"
    assert repository.event_count == 1
    assert (
        len(
            repository.database.read_rows(
                "SELECT 1 FROM idempotency_events WHERE event_id = 'ov-2'"
            )
        )
        == 0
    )


def test_append_replay_and_conflict_are_mutation_free(
    repository: AuditRepository,
) -> None:
    original = repository.append(
        append_event(
            "CHECK_RESULT",
            {"check_kind": "RUFF", "status": "PASS"},
            event_id="rp-1",
        )
    )
    assert original.kind == "APPENDED"
    replay = repository.append(
        append_event(
            "CHECK_RESULT",
            {"check_kind": "RUFF", "status": "PASS"},
            event_id="rp-1",
        )
    )
    assert replay.kind == "REPLAY"
    assert replay.event == original.event
    conflict = repository.append(
        append_event(
            "CHECK_RESULT",
            {"check_kind": "RUFF", "status": "FAIL"},
            event_id="rp-1",
        )
    )
    assert conflict.kind == "EVENT_ID_REUSE_CONFLICT"
    assert repository.event_count == 1


def test_append_surrogate_identities_reject_with_zero_rows(
    repository: AuditRepository,
) -> None:
    """Lone surrogates fail closed everywhere (T22.1 lesson, SPEC 5.4)."""
    surrogate_run = repository.append(
        append_event(
            "STOP_EVIDENCE",
            {"reason_code": "TURN_LIMIT"},
            run_id="run-\ud800",
            event_id="sur-1",
        )
    )
    assert surrogate_run.kind == "REJECTED"
    assert surrogate_run.error_code == "AUDIT_STORE_FAILED"
    surrogate_event_id = repository.append(
        append_event(
            "STOP_EVIDENCE",
            {"reason_code": "TURN_LIMIT"},
            event_id="evt-\udfff",
        )
    )
    assert surrogate_event_id.kind == "REJECTED"
    assert surrogate_event_id.error_code == "AUDIT_STORE_FAILED"
    surrogate_value = repository.append(
        append_event(
            "STOP_EVIDENCE",
            {"reason_code": "TURN-\ud800"},
            event_id="sur-2",
        )
    )
    assert surrogate_value.kind == "REJECTED"
    assert surrogate_value.error_code == "AUDIT_STORE_FAILED"
    assert repository.event_count == 0
    assert (
        len(
            repository.database.read_rows(
                "SELECT 1 FROM idempotency_events WHERE scope = 'audit_append'"
            )
        )
        == 0
    )
    surrogate_clear = repository.clear_ended_run(
        ClearEndedRunAuditV1(
            run_id="run-\ud800", event_id="clr-sur", decided_at=_CLEARED_AT
        )
    )
    assert surrogate_clear.kind == "REJECTED"
    assert surrogate_clear.error_code == "AUDIT_STORE_FAILED"


def test_append_evidence_refs_are_part_of_the_request_identity(
    repository: AuditRepository,
) -> None:
    """Different evidence references make the request different (conflict)."""
    original = repository.append(
        append_event(
            "CHECK_RESULT",
            {"check_kind": "RUFF", "status": "PASS"},
            event_id="refs-1",
            evidence_refs=("ref-a",),
        )
    )
    assert original.kind == "APPENDED"
    assert original.event is not None
    assert original.event.redacted_payload.evidence_refs == ("ref-a",)
    # Exact replay keeps the recorded references.
    replay = repository.append(
        append_event(
            "CHECK_RESULT",
            {"check_kind": "RUFF", "status": "PASS"},
            event_id="refs-1",
            evidence_refs=("ref-a",),
        )
    )
    assert replay.kind == "REPLAY"
    assert replay.event == original.event
    # Different references for the same event id are a different request.
    conflict = repository.append(
        append_event(
            "CHECK_RESULT",
            {"check_kind": "RUFF", "status": "PASS"},
            event_id="refs-1",
            evidence_refs=("ref-b",),
        )
    )
    assert conflict.kind == "EVENT_ID_REUSE_CONFLICT"
    assert repository.event_count == 1


def test_append_replay_after_clear_never_resurrects_removed_content(
    repository: AuditRepository,
) -> None:
    _seed_run(repository.database, "run-c", "SUCCEEDED", None)
    appended = repository.append(
        append_event(
            "STOP_EVIDENCE",
            {"reason_code": "TURN_LIMIT"},
            run_id="run-c",
            event_id="rc-1",
        )
    )
    assert appended.kind == "APPENDED"
    cleared = repository.clear_ended_run(
        ClearEndedRunAuditV1(run_id="run-c", event_id="clr-1", decided_at=_CLEARED_AT)
    )
    assert cleared.kind == "CLEARED"
    replay = repository.append(
        append_event(
            "STOP_EVIDENCE",
            {"reason_code": "TURN_LIMIT"},
            run_id="run-c",
            event_id="rc-1",
        )
    )
    assert replay.kind == "REPLAY"
    assert replay.event is None
    assert repository.event_count == 0


def test_list_run_pagination_is_complete_and_stable(
    repository: AuditRepository,
) -> None:
    for index in range(5):
        appended = repository.append(
            append_event(
                "STOP_EVIDENCE",
                {"reason_code": "TURN_LIMIT"},
                event_id=f"pg-{index}",
            )
        )
        assert appended.kind == "APPENDED"
    collected: list[int] = []
    cursor: AuditCursorV1 | None = None
    for _ in range(10):
        page = repository.list_run(
            "run-1", AuditPageRequestV1(page_size=2, cursor=cursor)
        )
        collected.extend(item.sequence for item in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert collected == [1, 2, 3, 4, 5]
    full = repository.list_run("run-1", first_page())
    assert [item.sequence for item in full.items] == [1, 2, 3, 4, 5]
    assert full.next_cursor is None
    empty = repository.list_run("no-such-run", AuditPageRequestV1(page_size=2))
    assert empty.items == ()
    assert empty.next_cursor is None
    # A cursor bound to another Run fails closed with zero partial results.
    with pytest.raises(AuditPaginationErrorV1):
        repository.list_run(
            "run-1",
            AuditPageRequestV1(
                page_size=2,
                cursor=AuditCursorV1(run_id="run-other", last_sequence=0),
            ),
        )


def test_tampered_event_type_column_fails_closed_on_read(
    repository: AuditRepository,
) -> None:
    """A DB row whose event_type disagrees with its payload kind must
    never rehydrate: the read fails closed, so a Recovery payload hidden
    under a forged event type is never silently projected."""
    appended = repository.append(
        append_event("LLM_CALL", {"outcome": "COMPLETED"}, event_id="tamper-1")
    )
    assert appended.kind == "APPENDED"
    assert appended.event is not None
    with repository.database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE audit_events SET event_type = 'ACTION' WHERE event_id = ?",
            ("tamper-1",),
        )
    with pytest.raises(ValidationError):
        repository.list_run("run-1", first_page())


def test_page_request_bounds_are_closed() -> None:
    with pytest.raises(ValidationError):
        AuditPageRequestV1(page_size=0)
    with pytest.raises(ValidationError):
        AuditPageRequestV1(page_size=101)
    with pytest.raises(ValidationError):
        AuditPageRequestV1(page_size="5")  # type: ignore[arg-type]


def test_clear_ended_run_removes_only_ended_run_audit(
    repository: AuditRepository,
) -> None:
    _seed_run(repository.database, "run-ended", "STOPPED", None)
    for index in range(3):
        appended = repository.append(
            append_event(
                "STOP_EVIDENCE",
                {"reason_code": "TURN_LIMIT"},
                run_id="run-ended",
                event_id=f"ce-{index}",
            )
        )
        assert appended.kind == "APPENDED"
    assert (
        repository.append(
            append_event(
                "STOP_EVIDENCE", {"reason_code": "TURN_LIMIT"}, event_id="keep-1"
            )
        ).kind
        == "APPENDED"
    )
    cleared = repository.clear_ended_run(
        ClearEndedRunAuditV1(
            run_id="run-ended", event_id="ce-cmd", decided_at=_CLEARED_AT
        )
    )
    assert cleared.kind == "CLEARED"
    assert cleared.cleared_event_count == 3
    assert repository.list_run("run-ended", first_page()).items == ()
    # The other Run's audit is untouched.
    assert [
        item.sequence for item in repository.list_run("run-1", first_page()).items
    ] == [1]
    assert repository.event_count == 1


def test_clear_rejects_active_missing_and_forged_runs(
    repository: AuditRepository,
) -> None:
    for run_id, status, phase in (
        ("run-active", "RUNNING", "PREFLIGHT"),
        ("run-created", "CREATED", None),
        ("run-waiting", "WAITING_USER", None),
        ("run-recovery", "RECOVERY_REQUIRED", None),
    ):
        _seed_run(repository.database, run_id, status, phase)
        result = repository.clear_ended_run(
            ClearEndedRunAuditV1(
                run_id=run_id, event_id=f"clr-{run_id}", decided_at=_CLEARED_AT
            )
        )
        assert result.error_code == "AUDIT_STORE_FAILED"
        assert result.cleared_event_count == 0
    missing = repository.clear_ended_run(
        ClearEndedRunAuditV1(
            run_id="no-such-run", event_id="clr-missing", decided_at=_CLEARED_AT
        )
    )
    assert missing.error_code == "AUDIT_STORE_FAILED"
    # The rejections leave no ledger residue behind.
    assert (
        len(
            repository.database.read_rows(
                "SELECT 1 FROM idempotency_events WHERE scope = 'audit_clear'"
            )
        )
        == 0
    )


def test_clear_replay_and_conflict_are_mutation_free(
    repository: AuditRepository,
) -> None:
    _seed_run(repository.database, "run-d", "SUCCEEDED", None)
    assert (
        repository.append(
            append_event(
                "STOP_EVIDENCE",
                {"reason_code": "TURN_LIMIT"},
                run_id="run-d",
                event_id="cd-1",
            )
        ).kind
        == "APPENDED"
    )
    assert (
        repository.clear_ended_run(
            ClearEndedRunAuditV1(
                run_id="run-d", event_id="cd-cmd", decided_at=_CLEARED_AT
            )
        ).kind
        == "CLEARED"
    )
    replay = repository.clear_ended_run(
        ClearEndedRunAuditV1(run_id="run-d", event_id="cd-cmd", decided_at=_CLEARED_AT)
    )
    assert replay.kind == "REPLAY"
    assert replay.cleared_event_count == 0
    _seed_run(repository.database, "run-e", "SUCCEEDED", None)
    assert (
        repository.append(
            append_event(
                "STOP_EVIDENCE",
                {"reason_code": "TURN_LIMIT"},
                run_id="run-e",
                event_id="ce-1",
            )
        ).kind
        == "APPENDED"
    )
    conflict = repository.clear_ended_run(
        ClearEndedRunAuditV1(run_id="run-e", event_id="cd-cmd", decided_at=_CLEARED_AT)
    )
    assert conflict.kind == "EVENT_ID_REUSE_CONFLICT"
    assert repository.list_run("run-e", first_page()).items


def test_clear_ended_run_with_no_events_is_clean(
    repository: AuditRepository,
) -> None:
    _seed_run(repository.database, "run-empty", "SUCCEEDED", None)
    cleared = repository.clear_ended_run(
        ClearEndedRunAuditV1(
            run_id="run-empty", event_id="ce-empty", decided_at=_CLEARED_AT
        )
    )
    assert cleared.kind == "CLEARED"
    assert cleared.cleared_event_count == 0
