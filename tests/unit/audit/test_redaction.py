"""T23.1 legacy step 23.A: redacted monotonic audit append RED + matrix tests.

Pins the exact RED (a complete LLM request body plus secret fields are
rejected with ``AUDIT_STORE_FAILED`` and zero persisted rows) and the
PLAN legacy-step matrix row 23.A: the closed event-type allowlist
accepts only bounded redacted facts, forbidden body/secret/request/
response fields are rejected with zero rows, per-Run sequences are
monotonic and unique, exact replay is stable under the T07.3 ledger,
pagination is complete and stable, and an explicit ended-Run clear never
exposes removed content.  Schema DDL, event vocabulary, and repository
behavior stay in their declared files (GREEN-4).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

# The repository consumes pydantic runtime contracts; the hash-locked
# gate toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from vespercode.audit.event import AuditEventTypeV1
from vespercode.audit.repository import (
    AppendAuditEventV1,
    AuditClearResultV1,
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

_BOUNDED_PAYLOAD: dict[str, dict[str, str]] = {
    "LIFECYCLE": {"status": "RUNNING", "phase": "PREFLIGHT"},
    "ACTION": {"action_type": "read_file", "policy_decision": "ALLOW"},
    "POLICY_DECISION": {"decision": "DENY", "reason_code": "PATCH_PATH_NOT_EDITABLE"},
    "FINAL_WRITEBACK_APPROVAL": {"approval_id": "approval-1", "status": "APPROVED"},
    "DISCLOSURE_GRANT": {"grant_id": "grant-1", "status": "ACTIVE"},
    "DISCLOSURE_AUTHORIZATION": {"category": "FILE", "byte_count": "1024"},
    "CHECK_RESULT": {"check_kind": "TARGET_TESTS", "status": "PASS"},
    "RECOVERY": {"transaction_id": "tx-1", "disposition": "COMMITTED"},
    "STOP_EVIDENCE": {"reason_code": "TURN_LIMIT"},
    "LLM_CALL": {"outcome": "COMPLETED"},
}

_FORBIDDEN_KEYS: tuple[str, ...] = (
    "request_body",
    "api_key",
    "response_body",
    "raw_output",
    "output",
    "secret",
    "token",
    "request",
    "response",
    "body",
)


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "audit.db")
    apply_migrations(database, _MIGRATIONS)
    yield database
    database.close()


@pytest.fixture
def audit_repository(control_database: ControlDatabase) -> AuditRepository:
    repository = AuditRepository(control_database)
    _seed_run(control_database, "run-1", "RUNNING", "AGENT_LOOP")
    return repository


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
    event_id: str | None = None,
    created_at: CanonicalTimestampV1 = _CREATED_AT,
    evidence_refs: tuple[str, ...] = (),
) -> AppendAuditEventV1:
    """One deterministic append command (card RED fixture helper).

    The default event id is derived from the payload bytes so two
    identical commands replay instead of colliding; tests that append
    multiple distinct facts pass explicit event ids.
    """
    return AppendAuditEventV1(
        run_id=run_id,
        event_type=cast(AuditEventTypeV1, event_type),
        payload=payload,
        evidence_refs=evidence_refs,
        event_id=(
            event_id
            if event_id is not None
            else f"evt-{run_id}-{event_type}-{json.dumps(payload, sort_keys=True)}"
        ),
        created_at=created_at,
    )


def first_page() -> AuditPageRequestV1:
    """The unbounded first page request (card RED fixture helper)."""
    return AuditPageRequestV1(page_size=100)


def test_audit_rejects_complete_request_body_and_secret_fields(
    audit_repository: AuditRepository,
) -> None:
    result = audit_repository.append(
        append_event(
            "LLM_CALL",
            {"request_body": "source text", "api_key": "inert-sentinel"},
        )
    )
    assert result.error_code == "AUDIT_STORE_FAILED"
    assert audit_repository.event_count == 0


def test_audit_rejects_prefixed_environment_variable_secrets(
    audit_repository: AuditRepository,
) -> None:
    # Prefixed env-var spellings (OPENAI_API_KEY=...) are secret values and
    # must fail closed into the audit trail exactly like bare spellings.
    result = audit_repository.append(
        append_event(
            "LLM_CALL",
            {"outcome": "OPENAI_API_KEY=sk-prefixed-secret"},
        )
    )
    assert result.error_code == "AUDIT_STORE_FAILED"
    assert audit_repository.event_count == 0


def test_audit_schema_replay_pagination_matrix(
    audit_repository: AuditRepository,
) -> None:
    """PLAN legacy-step matrix row 23.A: redacted schema, replay, pagination."""
    # The closed event-type allowlist accepts only bounded redacted facts.
    for index, event_type in enumerate(_BOUNDED_PAYLOAD):
        result = audit_repository.append(
            append_event(
                event_type,
                _BOUNDED_PAYLOAD[event_type],
                event_id=f"allow-{index}",
                evidence_refs=(f"ref-{index}",),
            )
        )
        assert result.kind == "APPENDED"
        assert result.event is not None
        assert result.event.sequence == index + 1
        assert result.event.event_type == event_type
        assert result.event.redacted_payload.kind == event_type
        assert result.event.redacted_payload.evidence_refs == (f"ref-{index}",)

    # Secret/body/request/response fields are rejected with zero rows.
    before = audit_repository.event_count
    for index, key in enumerate(_FORBIDDEN_KEYS):
        rejected = audit_repository.append(
            append_event(
                "LLM_CALL",
                {key: "inert-sentinel"},
                event_id=f"forbid-{index}",
            )
        )
        assert rejected.error_code == "AUDIT_STORE_FAILED"
    unknown_key = audit_repository.append(
        append_event("LLM_CALL", {"random_field": "x"}, event_id="forbid-unknown")
    )
    assert unknown_key.error_code == "AUDIT_STORE_FAILED"
    assert audit_repository.event_count == before

    # The sequence is monotonic and unique per Run; another Run restarts at 1.
    _seed_run(audit_repository.database, "run-seq", "RUNNING", "BASELINE")
    for index in range(3):
        appended = audit_repository.append(
            append_event(
                "LIFECYCLE",
                {"status": "RUNNING", "phase": "PREFLIGHT"},
                run_id="run-seq",
                event_id=f"seq-{index}",
            )
        )
        assert appended.event is not None
        assert appended.event.sequence == index + 1
    _seed_run(audit_repository.database, "run-seq-b", "RUNNING", "PREFLIGHT")
    other = audit_repository.append(
        append_event(
            "LIFECYCLE",
            {"status": "RUNNING", "phase": "PREFLIGHT"},
            run_id="run-seq-b",
            event_id="seq-b-0",
        )
    )
    assert other.event is not None
    assert other.event.sequence == 1

    # Exact replay is stable; event-id reuse for a different request is a
    # conflict and never appends a row.
    count_before_replay = audit_repository.event_count
    original = audit_repository.append(
        append_event(
            "STOP_EVIDENCE",
            {"reason_code": "TURN_LIMIT"},
            event_id="replay-1",
        )
    )
    assert original.kind == "APPENDED"
    replay = audit_repository.append(
        append_event(
            "STOP_EVIDENCE",
            {"reason_code": "TURN_LIMIT"},
            event_id="replay-1",
        )
    )
    assert replay.kind == "REPLAY"
    assert replay.event == original.event
    assert audit_repository.event_count == count_before_replay + 1
    conflict = audit_repository.append(
        append_event(
            "STOP_EVIDENCE",
            {"reason_code": "LLM_CALL_FAILED"},
            event_id="replay-1",
        )
    )
    assert conflict.kind == "EVENT_ID_REUSE_CONFLICT"
    assert audit_repository.event_count == count_before_replay + 1

    # Pagination is complete, ordered, and stable.
    collected: list[int] = []
    cursor: AuditCursorV1 | None = None
    for _ in range(20):
        page = audit_repository.list_run(
            "run-1", AuditPageRequestV1(page_size=3, cursor=cursor)
        )
        collected.extend(item.sequence for item in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert collected == sorted(collected)
    assert len(collected) == len(set(collected))
    full = audit_repository.list_run("run-1", first_page())
    assert collected == [item.sequence for item in full.items]
    # A cursor bound to another Run fails closed with zero partial results.
    with pytest.raises(AuditPaginationErrorV1):
        audit_repository.list_run(
            "run-1",
            AuditPageRequestV1(
                page_size=3,
                cursor=AuditCursorV1(run_id="run-seq", last_sequence=0),
            ),
        )

    # Clear removes only ended-Run audit and never exposes removed content.
    _seed_run(audit_repository.database, "run-clear", "SUCCEEDED", None)
    for index in range(2):
        appended = audit_repository.append(
            append_event(
                "LIFECYCLE",
                {"status": "SUCCEEDED"},
                run_id="run-clear",
                event_id=f"clear-{index}",
            )
        )
        assert appended.kind == "APPENDED"
    cleared = audit_repository.clear_ended_run(
        ClearEndedRunAuditV1(
            run_id="run-clear",
            event_id="clear-cmd-1",
            decided_at=_CLEARED_AT,
        )
    )
    assert cleared.kind == "CLEARED"
    assert cleared.cleared_event_count == 2
    # The closed result shape carries counts only, never payload bodies.
    assert set(AuditClearResultV1.model_fields) == {
        "kind",
        "message",
        "cleared_event_count",
        "error_code",
    }
    assert audit_repository.list_run("run-clear", first_page()).items == ()
    # An exact append replay after the clear replays without resurrecting.
    count_after_clear = audit_repository.event_count
    replay_after_clear = audit_repository.append(
        append_event(
            "LIFECYCLE",
            {"status": "SUCCEEDED"},
            run_id="run-clear",
            event_id="clear-0",
        )
    )
    assert replay_after_clear.kind == "REPLAY"
    assert replay_after_clear.event is None
    assert audit_repository.event_count == count_after_clear
