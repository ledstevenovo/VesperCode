"""T15.2 legacy step 15.E: transactional disclosure authorization ledger tests.

Pins the exact one-transaction revalidation (active Grant, subject facts,
source categories/scopes, revocation/expiry, request identity, cumulative
budget), the exactly-once body-free authorization record and byte charge,
the zero-charge failures (scope/category drift, expired/revoked/exhausted
Grants, budget races, replay conflicts), and the body-free record shape.
Final registry edits, Grant decisions/revocation, request
serialization/calls, body storage, and refunds remain out of scope
(GREEN-4).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

# The ledger consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips cleanly
# there (formal env runs it fully).
pytest.importorskip("pydantic")

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import DigestV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.contracts.run import WaitContextV1, WaitDecisionV1
from vespercode.governance.disclosure_decision import (
    DecideDisclosureGrantV1,
    DisclosureDecisionServiceV1,
)
from vespercode.governance.disclosure_ledger import (
    AuthorizePreparedRequestV1,
    DisclosureLedger,
)
from vespercode.governance.disclosure_scope import (
    DirectoryDisclosureScopeV1,
    DisclosureScopeSequenceV1,
)
from vespercode.governance.disclosure_subject import (
    DisclosureGrantSubjectV1,
    DisclosureSubjectRequestV1,
    build_disclosure_subject,
)
from vespercode.governance.request_sources import (
    RequestSourceCategoryV1,
    RequestSourceV1,
    SourceProjectionV1,
)
from vespercode.profiles.endpoints import OpenAIEndpointV1
from vespercode.profiles.llm import OpenAILLMProfileV1, load_llm_profile
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
from vespercode.storage.run_repository import RunRepository

_CREATED_AT = CanonicalTimestampV1("2026-08-05T09:00:00.000Z")
_EXPIRES_AT = CanonicalTimestampV1("2026-08-05T09:05:00.000Z")
_DECIDED_AT = CanonicalTimestampV1("2026-08-05T09:01:00.000Z")
_AUTHORIZED_AT = CanonicalTimestampV1("2026-08-05T09:02:00.000Z")
_RUN_DEADLINE = CanonicalTimestampV1("2026-08-05T09:15:00.000Z")
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
) -> None:
    RunRepository(database).create_wait(
        WaitContextV1(
            wait_id=wait_id,
            run_id=run_id,
            wait_kind="DISCLOSURE_GRANT",
            source_phase="AGENT_LOOP",
            subject_digest=DigestV1(value=_SUBJECT.digest),
            created_at=_CREATED_AT,
            expires_at=_EXPIRES_AT,
        )
    )


def decide(
    *,
    wait_id: str = "wait-1",
    run_id: str = "run-1",
    event_id: str = "evt-1",
    grant_id: str = "grant-1",
) -> DecideDisclosureGrantV1:
    return DecideDisclosureGrantV1(
        decision=WaitDecisionV1(
            wait_id=wait_id,
            run_id=run_id,
            wait_kind="DISCLOSURE_GRANT",
            subject_digest=DigestV1(value=_SUBJECT.digest),
            decision="APPROVE",
            event_id=event_id,
            decided_at=_DECIDED_AT,
        ),
        subject=_SUBJECT,
        grant_id=grant_id,
    )


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "ledger.db")
    apply_migrations(
        database,
        (
            RUN_WAIT_V1_MIGRATION,
            IDEMPOTENCY_V1_MIGRATION,
            DISCLOSURE_GRANTS_V1_MIGRATION,
            DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
        ),
    )
    _insert_run(database, "run-1", "WAITING_USER")
    _create_wait(database, "wait-1", "run-1")
    decision_service = DisclosureDecisionServiceV1(database)
    assert decision_service.decide(decide()).kind == "APPROVED"
    yield database
    database.close()


@pytest.fixture
def ledger(tmp_path: Path, control_database: ControlDatabase) -> DisclosureLedger:
    return DisclosureLedger(control_database, tmp_path / "ledger.db")


def source(
    category: RequestSourceCategoryV1 = "TOOL_RESULT",
    source_path: str | None = "src/a.py",
    content: str = "tool bytes",
) -> RequestSourceV1:
    raw = content.encode("utf-8")
    return RequestSourceV1(
        message_index=0,
        segment_index=0,
        source_category=category,
        source_path=(
            AbsentV1(kind="ABSENT")
            if source_path is None
            else PresentV1(kind="PRESENT", value=CanonicalRelativePathV1(source_path))
        ),
        content_digest=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
    )


def authorize_request(
    *,
    grant_id: str = "grant-1",
    request_digest: str | None = None,
    actual_sources: tuple[RequestSourceV1, ...] = (source(),),
    charge_bytes: int = 100,
    event_id: str = "authz-1",
    authorization_record_id: str = "rec-1",
    authorized_at: CanonicalTimestampV1 = _AUTHORIZED_AT,
    llm_profile_digest: str | None = None,
    provider: str | None = None,
    endpoint_id: str | None = None,
    model: str | None = None,
    request_serializer_version: str | None = None,
    redaction_profile_id: str | None = None,
) -> AuthorizePreparedRequestV1:
    return AuthorizePreparedRequestV1(
        authorization_record_id=authorization_record_id,
        grant_id=grant_id,
        request_digest=(
            request_digest
            if request_digest is not None
            else hashlib.sha256(b"prepared request").hexdigest()
        ),
        actual_sources=actual_sources,
        charge_bytes=charge_bytes,
        llm_profile_digest=llm_profile_digest or _SUBJECT.llm_profile_digest,
        provider=provider or _SUBJECT.provider,
        endpoint_id=endpoint_id or _SUBJECT.endpoint_id,
        model=model or _SUBJECT.model,
        request_serializer_version=(
            request_serializer_version or _SUBJECT.request_serializer_version
        ),
        redaction_profile_id=redaction_profile_id or _SUBJECT.redaction_profile_id,
        event_id=event_id,
        authorized_at=authorized_at,
    )


def _record_count(database: ControlDatabase) -> int:
    return len(database.read_rows("SELECT 1 FROM disclosure_authorizations"))


def _grant_state(database: ControlDatabase) -> tuple[int, str]:
    rows = database.read_rows(
        "SELECT consumed_bytes, status FROM disclosure_grants"
        " WHERE grant_id = 'grant-1'"
    )
    assert len(rows) == 1
    return int(rows[0][0]), str(rows[0][1])


def test_exact_authorization_commits_one_charge_and_record(
    control_database: ControlDatabase,
    ledger: DisclosureLedger,
) -> None:
    outcome = ledger.authorize(authorize_request())
    assert outcome.kind == "AUTHORIZED"
    assert outcome.record is not None
    assert _grant_state(control_database) == (100, "ACTIVE")
    assert _record_count(control_database) == 1
    record = outcome.record
    assert record.schema_version == 1
    assert record.authorization_record_id == "rec-1"
    assert record.grant_id == "grant-1"
    assert record.grant_subject_digest == _SUBJECT.digest
    assert record.llm_profile_digest == _SUBJECT.llm_profile_digest
    assert record.provider == "openai"
    assert record.endpoint_id == "OPENAI_PUBLIC_API_V1"
    assert record.model == "gpt-4.1-mini"
    assert record.request_serializer_version == "1"
    assert record.request_digest == authorize_request().request_digest
    assert record.canonical_byte_count == 100
    assert record.redaction_profile_id == "NO_CONTENT_REDACTION_V1"
    assert record.created_at == _AUTHORIZED_AT
    assert len(record.actual_sources) == 1
    # The record is body-free: the source projection carries no content.
    assert record.actual_sources[0].content_digest == source().content_digest


def test_two_sequential_charges_within_budget_succeed(
    control_database: ControlDatabase,
    ledger: DisclosureLedger,
) -> None:
    first = ledger.authorize(authorize_request(charge_bytes=400, event_id="a1"))
    second = ledger.authorize(
        authorize_request(
            charge_bytes=400,
            event_id="a2",
            authorization_record_id="rec-2",
        )
    )
    assert first.kind == "AUTHORIZED"
    assert second.kind == "AUTHORIZED"
    assert _grant_state(control_database) == (800, "ACTIVE")
    assert _record_count(control_database) == 2


def test_charge_exceeding_budget_is_zero_charge(
    control_database: ControlDatabase,
    ledger: DisclosureLedger,
) -> None:
    outcome = ledger.authorize(authorize_request(charge_bytes=1001))
    assert outcome.kind == "DISCLOSURE_BUDGET_EXCEEDED"
    assert outcome.record is None
    assert _grant_state(control_database) == (0, "ACTIVE")
    assert _record_count(control_database) == 0


def test_exact_budget_exhausts_grant(
    control_database: ControlDatabase,
    ledger: DisclosureLedger,
) -> None:
    outcome = ledger.authorize(authorize_request(charge_bytes=1000))
    assert outcome.kind == "AUTHORIZED"
    assert _grant_state(control_database) == (1000, "EXHAUSTED")
    next_outcome = ledger.authorize(
        authorize_request(
            charge_bytes=1, event_id="a2", authorization_record_id="rec-2"
        )
    )
    assert next_outcome.kind == "EXHAUSTED"
    assert _record_count(control_database) == 1


def test_out_of_scope_category_charges_zero(
    control_database: ControlDatabase,
    ledger: DisclosureLedger,
) -> None:
    outcome = ledger.authorize(
        authorize_request(actual_sources=(source(category="MEMORY", source_path=None),))
    )
    assert outcome.kind == "DISCLOSURE_SCOPE_EXCEEDED"
    assert _grant_state(control_database) == (0, "ACTIVE")
    assert _record_count(control_database) == 0


def test_out_of_scope_path_charges_zero(
    control_database: ControlDatabase,
    ledger: DisclosureLedger,
) -> None:
    outcome = ledger.authorize(
        authorize_request(actual_sources=(source(source_path="src_backup/a.py"),))
    )
    assert outcome.kind == "DISCLOSURE_SCOPE_EXCEEDED"
    assert _grant_state(control_database) == (0, "ACTIVE")
    assert _record_count(control_database) == 0


def test_revoked_grant_charges_zero(
    control_database: ControlDatabase,
    ledger: DisclosureLedger,
) -> None:
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE disclosure_grants SET status = 'REVOKED' WHERE grant_id = 'grant-1'"
        )
    outcome = ledger.authorize(authorize_request())
    assert outcome.kind == "REVOKED"
    assert _grant_state(control_database) == (0, "REVOKED")
    assert _record_count(control_database) == 0


def test_expired_grant_charges_zero_and_settles(
    control_database: ControlDatabase,
    ledger: DisclosureLedger,
) -> None:
    late = CanonicalTimestampV1("2026-08-05T09:06:00.000Z")
    outcome = ledger.authorize(authorize_request(authorized_at=late))
    assert outcome.kind == "EXPIRED"
    assert _grant_state(control_database) == (0, "EXPIRED")
    assert _record_count(control_database) == 0


def test_subject_drift_charges_zero(
    control_database: ControlDatabase,
    ledger: DisclosureLedger,
) -> None:
    drifted = authorize_request(model="gpt-4.1")
    outcome = ledger.authorize(drifted)
    assert outcome.kind == "SUBJECT_MISMATCH"
    assert _grant_state(control_database) == (0, "ACTIVE")
    assert _record_count(control_database) == 0


def test_missing_grant_charges_zero(
    control_database: ControlDatabase,
    ledger: DisclosureLedger,
) -> None:
    outcome = ledger.authorize(authorize_request(grant_id="grant-missing"))
    assert outcome.kind == "GRANT_NOT_FOUND"
    assert _record_count(control_database) == 0


def test_exact_event_replay_charges_once(
    control_database: ControlDatabase,
    ledger: DisclosureLedger,
) -> None:
    first = ledger.authorize(authorize_request())
    second = ledger.authorize(authorize_request())
    assert first.kind == "AUTHORIZED"
    assert second.kind == "REPLAY"
    assert _grant_state(control_database) == (100, "ACTIVE")
    assert _record_count(control_database) == 1


def test_event_reuse_with_different_request_charges_zero(
    control_database: ControlDatabase,
    ledger: DisclosureLedger,
) -> None:
    assert ledger.authorize(authorize_request()).kind == "AUTHORIZED"
    conflict = ledger.authorize(
        authorize_request(
            request_digest=hashlib.sha256(b"other request").hexdigest(),
            event_id="authz-1",
            authorization_record_id="rec-2",
        )
    )
    assert conflict.kind == "REPLAY_CONFLICT"
    assert _grant_state(control_database) == (100, "ACTIVE")
    assert _record_count(control_database) == 1


def test_failed_authorization_records_no_event(
    control_database: ControlDatabase,
    ledger: DisclosureLedger,
) -> None:
    before = len(
        control_database.read_rows(
            "SELECT 1 FROM idempotency_events WHERE scope = 'disclosure_authorize'"
        )
    )
    assert ledger.authorize(authorize_request(charge_bytes=1001)).kind == (
        "DISCLOSURE_BUDGET_EXCEEDED"
    )
    after = len(
        control_database.read_rows(
            "SELECT 1 FROM idempotency_events WHERE scope = 'disclosure_authorize'"
        )
    )
    assert after == before
    assert _record_count(control_database) == 0


def test_authorization_record_is_body_free(
    control_database: ControlDatabase,
    ledger: DisclosureLedger,
) -> None:
    ledger.authorize(authorize_request())
    rows = control_database.read_rows(
        "SELECT actual_sources, canonical_byte_count, created_at"
        " FROM disclosure_authorizations WHERE authorization_id = 'rec-1'"
    )
    assert len(rows) == 1
    assert "tool bytes" not in str(rows[0][0])
    assert rows[0][1] == 100
    assert rows[0][2] == _AUTHORIZED_AT.value


def test_disclosure_budget_state_matrix(
    control_database: ControlDatabase,
    ledger: DisclosureLedger,
) -> None:
    """PLAN Registry row 15.E (ledger-side coverage).

    Exact in-scope charge decrements once; out-of-scope, expired, revoked,
    or exhausted Grant yields zero disclosure.  The registry-pinned matrix
    lives in test_disclosure_budget_race.py; this file's copy covers the
    same row from the single-connection fixture perspective (the race
    file's copy adds the concurrent-charge rows).
    """
    # Exact in-scope charge decrements once.
    assert ledger.authorize(
        authorize_request(charge_bytes=300, event_id="m1")
    ).kind == ("AUTHORIZED")
    assert _grant_state(control_database) == (300, "ACTIVE")
    assert _record_count(control_database) == 1

    # Out-of-scope category and path yield zero disclosure.
    assert (
        ledger.authorize(
            authorize_request(
                actual_sources=(source(category="MEMORY", source_path=None),),
                event_id="m2",
                authorization_record_id="rec-2",
            )
        ).kind
        == "DISCLOSURE_SCOPE_EXCEEDED"
    )
    assert (
        ledger.authorize(
            authorize_request(
                actual_sources=(source(source_path="src_backup/a.py"),),
                event_id="m3",
                authorization_record_id="rec-3",
            )
        ).kind
        == "DISCLOSURE_SCOPE_EXCEEDED"
    )
    assert _grant_state(control_database) == (300, "ACTIVE")
    assert _record_count(control_database) == 1

    # Revoked Grant yields zero disclosure.
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE disclosure_grants SET status = 'REVOKED' WHERE grant_id = 'grant-1'"
        )
    assert (
        ledger.authorize(
            authorize_request(event_id="m4", authorization_record_id="rec-4")
        ).kind
        == "REVOKED"
    )

    # Expired Grant yields zero disclosure (a fresh grant for the check).
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE disclosure_grants SET status = 'ACTIVE' WHERE grant_id = 'grant-1'"
        )
        tx.execute(
            "UPDATE disclosure_grant_subjects SET expires_at ="
            " '2026-08-05T09:00:30.000Z' WHERE subject_digest = ?",
            (_SUBJECT.digest,),
        )
    assert (
        ledger.authorize(
            authorize_request(event_id="m5", authorization_record_id="rec-5")
        ).kind
        == "EXPIRED"
    )
    # The settlement only flips the status; the consumed bytes stay.
    assert _grant_state(control_database) == (300, "EXPIRED")

    # Exhausted Grant yields zero disclosure (a fresh grant for the check).
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE disclosure_grants SET status = 'ACTIVE',"
            " consumed_bytes = 0 WHERE grant_id = 'grant-1'"
        )
        tx.execute(
            "UPDATE disclosure_grant_subjects SET expires_at ="
            " '2026-08-05T09:05:00.000Z' WHERE subject_digest = ?",
            (_SUBJECT.digest,),
        )
    assert (
        ledger.authorize(
            authorize_request(
                charge_bytes=1000,
                event_id="m6",
                authorization_record_id="rec-6",
            )
        ).kind
        == "AUTHORIZED"
    )
    assert _grant_state(control_database) == (1000, "EXHAUSTED")
    assert (
        ledger.authorize(
            authorize_request(event_id="m7", authorization_record_id="rec-7")
        ).kind
        == "EXHAUSTED"
    )
    assert _record_count(control_database) == 2
