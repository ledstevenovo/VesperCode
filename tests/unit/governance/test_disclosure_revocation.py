"""T15.2 legacy step 15.F: exact active disclosure Grant revocation tests.

Pins the exact RED (a subject-mismatched revocation is rejected and the
active Grant survives), the one-time ACTIVE → REVOKED transition bound to
the exact Grant/Run/subject/idempotency event, the stable exact replay,
the deterministic stale/mismatched/already-revoked rejections with zero
mutation of unrelated Grants, and the event-reuse conflict.  Wait
decisions, Grant creation, request authorization, byte charging, body
storage, and committed-charge refunds remain out of scope (GREEN-4).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

# The service consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips cleanly
# there (formal env runs it fully).
pytest.importorskip("pydantic")

from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.evidence import DigestV1
from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.contracts.run import WaitContextV1, WaitDecisionV1
from src.vespercode.governance.disclosure_decision import (
    DecideDisclosureGrantV1,
    DisclosureDecisionServiceV1,
)
from src.vespercode.governance.disclosure_revocation import (
    DisclosureRevocationServiceV1,
    RevokeDisclosureGrantV1,
)
from src.vespercode.governance.disclosure_scope import (
    DirectoryDisclosureScopeV1,
    DisclosureScopeSequenceV1,
)
from src.vespercode.governance.disclosure_subject import (
    DisclosureGrantSubjectV1,
    DisclosureSubjectRequestV1,
    build_disclosure_subject,
)
from src.vespercode.governance.request_sources import (
    RequestSourceV1,
    SourceProjectionV1,
)
from src.vespercode.profiles.endpoints import OpenAIEndpointV1
from src.vespercode.profiles.llm import OpenAILLMProfileV1, load_llm_profile
from src.vespercode.storage.connection import (
    ControlDatabase,
    open_control_database,
)
from src.vespercode.storage.migration_engine import apply_migrations
from src.vespercode.storage.migrations.v0001_run_wait import RUN_WAIT_V1_MIGRATION
from src.vespercode.storage.migrations.v0002_idempotency import (
    IDEMPOTENCY_V1_MIGRATION,
)
from src.vespercode.storage.migrations.v0003_disclosure_grants import (
    DISCLOSURE_GRANTS_V1_MIGRATION,
)
from src.vespercode.storage.run_repository import RunRepository

_CREATED_AT = CanonicalTimestampV1("2026-08-05T09:00:00.000Z")
_EXPIRES_AT = CanonicalTimestampV1("2026-08-05T09:05:00.000Z")
_DECIDED_AT = CanonicalTimestampV1("2026-08-05T09:01:00.000Z")
_RUN_DEADLINE = CanonicalTimestampV1("2026-08-05T09:15:00.000Z")
_REVOKED_AT = CanonicalTimestampV1("2026-08-05T09:02:00.000Z")
_OPENAI_BUILTIN = (
    Path(__file__).resolve().parents[3]
    / "src/vespercode/profiles/builtin/openai-single-turn-v1.json"
)


def profile() -> OpenAILLMProfileV1:
    loaded = load_llm_profile(_OPENAI_BUILTIN.read_bytes())
    assert isinstance(loaded, OpenAILLMProfileV1)
    return loaded


def endpoint() -> OpenAIEndpointV1:
    return OpenAIEndpointV1(
        endpoint_id="OPENAI_PUBLIC_API_V1",
        scheme="https",
        host="api.openai.com",
        effective_port=443,
        base_path="/v1",
    )


def subject(
    run_id: str = "run-1",
    expires_at: CanonicalTimestampV1 = _EXPIRES_AT,
    budget: int = 1000,
) -> DisclosureGrantSubjectV1:
    raw = b"tool result bytes"
    sources: SourceProjectionV1 = (
        RequestSourceV1(
            message_index=0,
            segment_index=0,
            source_category="TOOL_RESULT",
            source_path=PresentV1(
                kind="PRESENT", value=CanonicalRelativePathV1("src/a.py")
            ),
            content_digest=hashlib.sha256(raw).hexdigest(),
            byte_count=len(raw),
        ),
    )
    scopes: DisclosureScopeSequenceV1 = (
        DirectoryDisclosureScopeV1(
            kind="DIRECTORY", path=CanonicalRelativePathV1("src")
        ),
    )
    return build_disclosure_subject(
        DisclosureSubjectRequestV1(
            run_id=run_id,
            expires_at=expires_at,
            cumulative_byte_budget=budget,
            url=AbsentV1(kind="ABSENT"),
        ),
        sources,
        scopes,
        profile(),
        endpoint(),
    )


_SUBJECT = subject()


def _insert_run(database: ControlDatabase, run_id: str, status: str) -> None:
    """Insert one v0001 runs row directly at the given state."""
    with database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots"
            " (config_snapshot_id, digest, llm_profile_id, reference_profile_id,"
            " policy_id, target_test_ids, limits_digest, frozen_at)"
            " VALUES (?, ?, 'mock-deterministic-v1', 'python-src-py312-v1',"
            " 'PYTHON_SRC_ONLY_V1', '[]', ?, ?)",
            (
                f"snap-{run_id}",
                hashlib.sha256(f"snap-{run_id}".encode("utf-8")).hexdigest(),
                "c" * 64,
                _CREATED_AT.value,
            ),
        )
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES (?, 'ws-1', ?, ?, NULL, 1, ?, ?)",
            (
                run_id,
                f"snap-{run_id}",
                status,
                _CREATED_AT.value,
                _RUN_DEADLINE.value,
            ),
        )


def _create_wait(
    database: ControlDatabase,
    wait_id: str,
    run_id: str,
    subject_digest: DigestV1 = DigestV1(value=_SUBJECT.digest),
) -> None:
    RunRepository(database).create_wait(
        WaitContextV1(
            wait_id=wait_id,
            run_id=run_id,
            wait_kind="DISCLOSURE_GRANT",
            source_phase="AGENT_LOOP",
            subject_digest=subject_digest,
            created_at=_CREATED_AT,
            expires_at=_EXPIRES_AT,
        )
    )


def decide(
    *,
    wait_id: str = "wait-1",
    run_id: str = "run-1",
    subject_digest: DigestV1 = DigestV1(value=_SUBJECT.digest),
    decision: str = "APPROVE",
    event_id: str = "evt-1",
    decided_at: CanonicalTimestampV1 = _DECIDED_AT,
    subject: DisclosureGrantSubjectV1 = _SUBJECT,
    grant_id: str = "grant-1",
) -> DecideDisclosureGrantV1:
    return DecideDisclosureGrantV1(
        decision=WaitDecisionV1(
            wait_id=wait_id,
            run_id=run_id,
            wait_kind="DISCLOSURE_GRANT",
            subject_digest=subject_digest,
            decision=decision,  # type: ignore[arg-type]
            event_id=event_id,
            decided_at=decided_at,
        ),
        subject=subject,
        grant_id=grant_id,
    )


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "revocation.db")
    apply_migrations(
        database,
        (
            RUN_WAIT_V1_MIGRATION,
            IDEMPOTENCY_V1_MIGRATION,
            DISCLOSURE_GRANTS_V1_MIGRATION,
        ),
    )
    _insert_run(database, "run-1", "WAITING_USER")
    _create_wait(database, "wait-1", "run-1")
    # One ACTIVE Grant via the decision service (the only sanctioned owner).
    decision_service = DisclosureDecisionServiceV1(database)
    assert decision_service.decide(decide()).kind == "APPROVED"
    yield database
    database.close()


@pytest.fixture
def service(control_database: ControlDatabase) -> DisclosureRevocationServiceV1:
    return DisclosureRevocationServiceV1(control_database)


def revoke(
    grant_id: str = "grant-1",
    run_id: str = "run-1",
    subject_digest: DigestV1 = DigestV1(value=_SUBJECT.digest),
    event_id: str = "revoke-1",
    revoked_at: CanonicalTimestampV1 = _REVOKED_AT,
) -> RevokeDisclosureGrantV1:
    return RevokeDisclosureGrantV1(
        grant_id=grant_id,
        run_id=run_id,
        subject_digest=subject_digest,
        event_id=event_id,
        revoked_at=revoked_at,
    )


def revoke_command_for_other_subject() -> RevokeDisclosureGrantV1:
    return revoke(subject_digest=DigestV1(value="f" * 64))


def test_revoke_rejects_mismatched_subject(
    service: DisclosureRevocationServiceV1,
) -> None:
    result = service.revoke(revoke_command_for_other_subject())
    assert result.kind == "SUBJECT_MISMATCH"
    assert service.active_grant_count() == 1


def _grant_status(database: ControlDatabase, grant_id: str) -> str:
    rows = database.read_rows(
        "SELECT status FROM disclosure_grants WHERE grant_id = ?", (grant_id,)
    )
    assert len(rows) == 1
    return str(rows[0][0])


def test_exact_revoke_transitions_active_to_revoked_once(
    control_database: ControlDatabase,
    service: DisclosureRevocationServiceV1,
) -> None:
    result = service.revoke(revoke())
    assert result.kind == "REVOKED"
    assert service.active_grant_count() == 0
    assert _grant_status(control_database, "grant-1") == "REVOKED"


def test_exact_revoke_replay_is_stable(
    control_database: ControlDatabase,
    service: DisclosureRevocationServiceV1,
) -> None:
    assert service.revoke(revoke()).kind == "REVOKED"
    replay = service.revoke(revoke())
    assert replay.kind == "REPLAY"
    assert service.active_grant_count() == 0
    assert _grant_status(control_database, "grant-1") == "REVOKED"


def test_new_event_on_revoked_grant_is_already_revoked(
    control_database: ControlDatabase,
    service: DisclosureRevocationServiceV1,
) -> None:
    assert service.revoke(revoke()).kind == "REVOKED"
    other = service.revoke(revoke(event_id="revoke-other"))
    assert other.kind == "ALREADY_REVOKED"
    assert service.active_grant_count() == 0


def test_event_reuse_with_different_request_is_conflict(
    control_database: ControlDatabase,
    service: DisclosureRevocationServiceV1,
) -> None:
    assert service.revoke(revoke()).kind == "REVOKED"
    # The same event id bound to a different grant is a replay conflict.
    _insert_run(control_database, "run-2", "WAITING_USER")
    second_subject = subject(run_id="run-2")
    _create_wait(
        database=control_database,
        wait_id="wait-2",
        run_id="run-2",
        subject_digest=DigestV1(value=second_subject.digest),
    )
    second_command = decide(
        wait_id="wait-2",
        run_id="run-2",
        subject=second_subject,
        subject_digest=DigestV1(value=second_subject.digest),
        event_id="evt-2",
        grant_id="grant-2",
    )
    decision_service = DisclosureDecisionServiceV1(control_database)
    assert decision_service.decide(second_command).kind == "APPROVED"
    conflict = service.revoke(
        revoke(grant_id="grant-2", run_id="run-2", event_id="revoke-1")
    )
    assert conflict.kind == "REPLAY_CONFLICT"
    assert _grant_status(control_database, "grant-2") == "ACTIVE"


def test_wrong_run_rejected(
    control_database: ControlDatabase,
    service: DisclosureRevocationServiceV1,
) -> None:
    result = service.revoke(revoke(run_id="run-other"))
    assert result.kind == "RUN_MISMATCH"
    assert _grant_status(control_database, "grant-1") == "ACTIVE"


def test_missing_grant_rejected(
    control_database: ControlDatabase,
    service: DisclosureRevocationServiceV1,
) -> None:
    result = service.revoke(revoke(grant_id="grant-missing"))
    assert result.kind == "NOT_FOUND"
    assert service.active_grant_count() == 1


def test_exhausted_grant_rejected_without_mutation(
    control_database: ControlDatabase,
    service: DisclosureRevocationServiceV1,
) -> None:
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE disclosure_grants SET status = 'EXHAUSTED'"
            " WHERE grant_id = 'grant-1'"
        )
    result = service.revoke(revoke())
    assert result.kind == "EXHAUSTED"
    assert _grant_status(control_database, "grant-1") == "EXHAUSTED"


def test_expired_grant_rejected_without_mutation(
    control_database: ControlDatabase,
    service: DisclosureRevocationServiceV1,
) -> None:
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE disclosure_grants SET status = 'EXPIRED' WHERE grant_id = 'grant-1'"
        )
    result = service.revoke(revoke())
    assert result.kind == "EXPIRED"
    assert _grant_status(control_database, "grant-1") == "EXPIRED"


def test_unrelated_grant_is_never_mutated(
    control_database: ControlDatabase,
    service: DisclosureRevocationServiceV1,
) -> None:
    # A second unrelated grant for a different run/subject.
    _insert_run(control_database, "run-2", "WAITING_USER")
    second_subject = subject(run_id="run-2")
    _create_wait(
        database=control_database,
        wait_id="wait-2",
        run_id="run-2",
        subject_digest=DigestV1(value=second_subject.digest),
    )
    second_command = decide(
        wait_id="wait-2",
        run_id="run-2",
        subject=second_subject,
        subject_digest=DigestV1(value=second_subject.digest),
        event_id="evt-2",
        grant_id="grant-2",
    )
    decision_service = DisclosureDecisionServiceV1(control_database)
    assert decision_service.decide(second_command).kind == "APPROVED"
    # A mismatched revoke attempt on grant-2 changes nothing.
    result = service.revoke(
        revoke(
            grant_id="grant-2",
            run_id="run-2",
            subject_digest=DigestV1(value="f" * 64),
            event_id="revoke-mismatch",
        )
    )
    assert result.kind == "SUBJECT_MISMATCH"
    assert _grant_status(control_database, "grant-1") == "ACTIVE"
    assert _grant_status(control_database, "grant-2") == "ACTIVE"
    # The exact revoke of grant-1 leaves grant-2 untouched.
    assert service.revoke(revoke()).kind == "REVOKED"
    assert _grant_status(control_database, "grant-1") == "REVOKED"
    assert _grant_status(control_database, "grant-2") == "ACTIVE"


def test_revocation_binds_idempotency_event(
    control_database: ControlDatabase,
    service: DisclosureRevocationServiceV1,
) -> None:
    """The successful revocation records exactly one ledger event row."""
    assert service.revoke(revoke()).kind == "REVOKED"
    rows = control_database.read_rows(
        "SELECT scope, event_id, request_digest, result_digest"
        " FROM idempotency_events WHERE scope = 'disclosure_revoke'"
    )
    assert len(rows) == 1
    assert rows[0][0] == "disclosure_revoke"
    assert rows[0][1] == "revoke-1"
    assert len(str(rows[0][2])) == 64
    assert len(str(rows[0][3])) == 64
    # A failed attempt records nothing (rollback removes the event row).
    before = len(
        control_database.read_rows(
            "SELECT 1 FROM idempotency_events WHERE scope = 'disclosure_revoke'"
        )
    )
    assert (
        service.revoke(
            revoke(event_id="revoke-2", subject_digest=DigestV1(value="f" * 64))
        ).kind
        == "SUBJECT_MISMATCH"
    )
    after = len(
        control_database.read_rows(
            "SELECT 1 FROM idempotency_events WHERE scope = 'disclosure_revoke'"
        )
    )
    assert after == before


def test_disclosure_revocation_matrix(
    control_database: ControlDatabase,
    service: DisclosureRevocationServiceV1,
) -> None:
    """PLAN Registry row 15.F.

    Exact active subject revokes once; exact replay is stable; mismatched
    subject or already-exhausted/expired Grant is rejected without
    changing another Grant.
    """
    assert service.active_grant_count() == 1

    # Exact active subject revokes once.
    assert service.revoke(revoke()).kind == "REVOKED"
    assert service.active_grant_count() == 0

    # Exact replay is stable (the ledger returns the recorded event).
    replay = service.revoke(revoke())
    assert replay.kind == "REPLAY"
    assert service.active_grant_count() == 0

    # A new event on the revoked grant is already-revoked, no mutation.
    assert service.revoke(revoke(event_id="revoke-new")).kind == "ALREADY_REVOKED"

    # Mismatched subject never mutates the grant.
    _insert_run(control_database, "run-2", "WAITING_USER")
    second_subject = subject(run_id="run-2")
    _create_wait(
        database=control_database,
        wait_id="wait-2",
        run_id="run-2",
        subject_digest=DigestV1(value=second_subject.digest),
    )
    second_command = decide(
        wait_id="wait-2",
        run_id="run-2",
        subject=second_subject,
        subject_digest=DigestV1(value=second_subject.digest),
        event_id="evt-2",
        grant_id="grant-2",
    )
    decision_service = DisclosureDecisionServiceV1(control_database)
    assert decision_service.decide(second_command).kind == "APPROVED"
    mismatch = service.revoke(
        revoke(
            grant_id="grant-2",
            run_id="run-2",
            subject_digest=DigestV1(value="f" * 64),
            event_id="revoke-mismatch",
        )
    )
    assert mismatch.kind == "SUBJECT_MISMATCH"
    assert _grant_status(control_database, "grant-2") == "ACTIVE"

    # Already-exhausted Grant is rejected without changing another Grant.
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE disclosure_grants SET status = 'EXHAUSTED'"
            " WHERE grant_id = 'grant-2'"
        )
    exhausted = service.revoke(
        revoke(
            grant_id="grant-2",
            run_id="run-2",
            subject_digest=DigestV1(value=second_subject.digest),
            event_id="revoke-exhausted",
        )
    )
    assert exhausted.kind == "EXHAUSTED"
    assert _grant_status(control_database, "grant-2") == "EXHAUSTED"

    # Already-expired Grant is rejected without changing another Grant.
    _insert_run(control_database, "run-3", "WAITING_USER")
    third_subject = subject(run_id="run-3")
    _create_wait(
        database=control_database,
        wait_id="wait-3",
        run_id="run-3",
        subject_digest=DigestV1(value=third_subject.digest),
    )
    third_command = decide(
        wait_id="wait-3",
        run_id="run-3",
        subject=third_subject,
        subject_digest=DigestV1(value=third_subject.digest),
        event_id="evt-3",
        grant_id="grant-3",
    )
    assert decision_service.decide(third_command).kind == "APPROVED"
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE disclosure_grants SET status = 'EXPIRED' WHERE grant_id = 'grant-3'"
        )
    expired = service.revoke(
        revoke(
            grant_id="grant-3",
            run_id="run-3",
            subject_digest=DigestV1(value=third_subject.digest),
            event_id="revoke-expired",
        )
    )
    assert expired.kind == "EXPIRED"
    assert _grant_status(control_database, "grant-3") == "EXPIRED"
