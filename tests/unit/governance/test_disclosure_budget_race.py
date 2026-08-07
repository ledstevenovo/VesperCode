"""T15.2 legacy step 15.E: disclosure budget race tests.

Pins the exact RED (two concurrent requests each requiring the remaining
budget yield exactly one AUTHORIZED) and the budget state matrix over the
PLAN Registry row 15.E: exact in-scope charges decrement once, every
out-of-scope/expired/revoked/exhausted failure charges zero, and
concurrent charges can never exceed the item/byte limits.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import cast

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
    DisclosureAuthorizationOutcomeV1,
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


def subject(budget: int = 1000) -> DisclosureGrantSubjectV1:
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
            run_id="run-1",
            expires_at=_EXPIRES_AT,
            cumulative_byte_budget=budget,
            url=AbsentV1(kind="ABSENT"),
        ),
        sources,
        scopes,
        profile(),
        endpoint(),
    )


_SUBJECT = subject()


def _setup(database: ControlDatabase) -> None:
    """One run, one pending wait, one approved ACTIVE Grant."""
    with database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots"
            " (config_snapshot_id, digest, llm_profile_id, reference_profile_id,"
            " policy_id, target_test_ids, limits_digest, frozen_at)"
            " VALUES ('snap-1', ?, 'mock-deterministic-v1', 'python-src-py312-v1',"
            " 'PYTHON_SRC_ONLY_V1', '[]', ?, ?)",
            ("a" * 64, "b" * 64, _CREATED_AT.value),
        )
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES ('run-1', 'ws-1', 'snap-1', 'WAITING_USER', NULL, 1,"
            " ?, ?)",
            (_CREATED_AT.value, _RUN_DEADLINE.value),
        )
    RunRepository(database).create_wait(
        WaitContextV1(
            wait_id="wait-1",
            run_id="run-1",
            wait_kind="DISCLOSURE_GRANT",
            source_phase="AGENT_LOOP",
            subject_digest=DigestV1(value=_SUBJECT.digest),
            created_at=_CREATED_AT,
            expires_at=_EXPIRES_AT,
        )
    )
    decision_service = DisclosureDecisionServiceV1(database)
    approved = decision_service.decide(
        DecideDisclosureGrantV1(
            decision=WaitDecisionV1(
                wait_id="wait-1",
                run_id="run-1",
                wait_kind="DISCLOSURE_GRANT",
                subject_digest=DigestV1(value=_SUBJECT.digest),
                decision="APPROVE",
                event_id="evt-1",
                decided_at=_DECIDED_AT,
            ),
            subject=_SUBJECT,
            grant_id="grant-1",
        )
    )
    assert approved.kind == "APPROVED"


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "race.db")
    apply_migrations(
        database,
        (
            RUN_WAIT_V1_MIGRATION,
            IDEMPOTENCY_V1_MIGRATION,
            DISCLOSURE_GRANTS_V1_MIGRATION,
            DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
        ),
    )
    _setup(database)
    yield database
    database.close()


@pytest.fixture
def ledger(tmp_path: Path, control_database: ControlDatabase) -> DisclosureLedger:
    return DisclosureLedger(control_database, tmp_path / "race.db")


def authorize_request(
    *,
    charge_bytes: int,
    event_id: str,
    authorization_record_id: str,
) -> AuthorizePreparedRequestV1:
    raw = b"tool bytes"
    actual_sources: SourceProjectionV1 = (
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
    return AuthorizePreparedRequestV1(
        authorization_record_id=authorization_record_id,
        grant_id="grant-1",
        request_digest=hashlib.sha256(event_id.encode("utf-8")).hexdigest(),
        actual_sources=actual_sources,
        charge_bytes=charge_bytes,
        llm_profile_digest=_SUBJECT.llm_profile_digest,
        provider=_SUBJECT.provider,
        endpoint_id=_SUBJECT.endpoint_id,
        model=_SUBJECT.model,
        request_serializer_version=_SUBJECT.request_serializer_version,
        redaction_profile_id=_SUBJECT.redaction_profile_id,
        event_id=event_id,
        authorized_at=_AUTHORIZED_AT,
    )


def two_requests_each_requiring_remaining_budget() -> tuple[
    AuthorizePreparedRequestV1, ...
]:
    """Two requests that each alone consume the full remaining budget."""
    return (
        authorize_request(
            charge_bytes=1000, event_id="race-a", authorization_record_id="rec-a"
        ),
        authorize_request(
            charge_bytes=1000, event_id="race-b", authorization_record_id="rec-b"
        ),
    )


def authorize_concurrently(
    ledger: DisclosureLedger,
    commands: tuple[AuthorizePreparedRequestV1, ...],
) -> tuple[DisclosureAuthorizationOutcomeV1, ...]:
    """Run every command on its own connection; BEGIN IMMEDIATE serializes.

    sqlite3 connections are thread-bound, so each worker opens its own
    connection to the same on-disk file (T07.2 precedent); the writers
    serialize and the budget compare-and-update lets exactly one win.
    """
    outcomes: list[DisclosureAuthorizationOutcomeV1 | None] = [None] * len(commands)
    errors: list[BaseException] = []
    barrier = threading.Barrier(len(commands), timeout=60)

    def worker(index: int) -> None:
        database = open_control_database(ledger.database_path)
        try:
            worker_ledger = DisclosureLedger(database, ledger.database_path)
            barrier.wait()
            outcomes[index] = worker_ledger.authorize(commands[index])
        except BaseException as exc:  # pragma: no cover - worker failure probe
            errors.append(exc)
        finally:
            database.close()

    threads = [
        threading.Thread(target=worker, args=(index,)) for index in range(len(commands))
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not errors, f"worker errors: {errors}"
    assert all(outcome is not None for outcome in outcomes)
    return cast(tuple[DisclosureAuthorizationOutcomeV1, ...], tuple(outcomes))


def test_two_requests_cannot_overdraw_one_grant(ledger: DisclosureLedger) -> None:
    results = authorize_concurrently(
        ledger, two_requests_each_requiring_remaining_budget()
    )
    assert sum(result.kind == "AUTHORIZED" for result in results) == 1


def test_disclosure_budget_state_matrix(
    control_database: ControlDatabase,
    ledger: DisclosureLedger,
) -> None:
    """PLAN Registry row 15.E.

    Exact in-scope charge decrements once; out-of-scope, expired, revoked,
    or exhausted Grant yields zero disclosure; concurrent charges cannot
    exceed item/byte limits.
    """
    # Exact in-scope charge decrements once.
    single = ledger.authorize(
        authorize_request(
            charge_bytes=400, event_id="m1", authorization_record_id="m1-rec"
        )
    )
    assert single.kind == "AUTHORIZED"
    rows = control_database.read_rows(
        "SELECT consumed_bytes FROM disclosure_grants WHERE grant_id = 'grant-1'"
    )
    assert int(rows[0][0]) == 400

    # A second in-scope charge still fits (800 <= 1000).
    second = ledger.authorize(
        authorize_request(
            charge_bytes=400, event_id="m2", authorization_record_id="m2-rec"
        )
    )
    assert second.kind == "AUTHORIZED"

    # Expired Grant yields zero disclosure (grant still ACTIVE).
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE disclosure_grant_subjects SET expires_at ="
            " '2026-08-05T09:00:30.000Z' WHERE subject_digest = ?",
            (_SUBJECT.digest,),
        )
    expired = ledger.authorize(
        authorize_request(
            charge_bytes=1, event_id="m5", authorization_record_id="m5-rec"
        )
    )
    assert expired.kind == "EXPIRED"
    rows = control_database.read_rows(
        "SELECT consumed_bytes, status FROM disclosure_grants"
        " WHERE grant_id = 'grant-1'"
    )
    assert int(rows[0][0]) == 800
    assert rows[0][1] == "EXPIRED"

    # The race needs an ACTIVE grant with the expiry restored: two
    # concurrent 200-byte charges cannot both fit the remaining 200
    # bytes — exactly one wins and the total never exceeds the budget.
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE disclosure_grants SET status = 'ACTIVE' WHERE grant_id = 'grant-1'"
        )
        tx.execute(
            "UPDATE disclosure_grant_subjects SET expires_at ="
            " '2026-08-05T09:05:00.000Z' WHERE subject_digest = ?",
            (_SUBJECT.digest,),
        )
    assert (
        sum(
            result.kind == "AUTHORIZED"
            for result in authorize_concurrently(
                ledger,
                (
                    authorize_request(
                        charge_bytes=200,
                        event_id="m3",
                        authorization_record_id="m3-rec",
                    ),
                    authorize_request(
                        charge_bytes=200,
                        event_id="m4",
                        authorization_record_id="m4-rec",
                    ),
                ),
            )
        )
        == 1
    )
    rows = control_database.read_rows(
        "SELECT consumed_bytes, status FROM disclosure_grants"
        " WHERE grant_id = 'grant-1'"
    )
    assert int(rows[0][0]) == 1000
    assert rows[0][1] == "EXHAUSTED"

    # Revoked Grant yields zero disclosure.
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE disclosure_grants SET status = 'REVOKED' WHERE grant_id = 'grant-1'"
        )
    revoked = ledger.authorize(
        authorize_request(
            charge_bytes=1, event_id="m6", authorization_record_id="m6-rec"
        )
    )
    assert revoked.kind == "REVOKED"

    # A charge that lands exactly on the budget exhausts the Grant.
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "UPDATE disclosure_grants SET status = 'ACTIVE',"
            " consumed_bytes = 999 WHERE grant_id = 'grant-1'"
        )
        tx.execute(
            "UPDATE disclosure_grant_subjects SET expires_at ="
            " '2026-08-05T09:05:00.000Z' WHERE subject_digest = ?",
            (_SUBJECT.digest,),
        )
    exhausted = ledger.authorize(
        authorize_request(
            charge_bytes=1, event_id="m7", authorization_record_id="m7-rec"
        )
    )
    assert exhausted.kind == "AUTHORIZED"
    rows = control_database.read_rows(
        "SELECT consumed_bytes, status FROM disclosure_grants"
        " WHERE grant_id = 'grant-1'"
    )
    assert int(rows[0][0]) == 1000
    assert rows[0][1] == "EXHAUSTED"
    # An already-exhausted Grant yields zero disclosure.
    already = ledger.authorize(
        authorize_request(
            charge_bytes=1, event_id="m8", authorization_record_id="m8-rec"
        )
    )
    assert already.kind == "EXHAUSTED"
