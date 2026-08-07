"""T25.2 legacy step 25.C: one authorized Mock/OpenAI call orchestration tests.

The exact RED test pins the missing-credential short circuit (a cleared
credential stops before every Grant charge, authorization, turn/call
count, and transport); the matrix pins the exact ordering of every real
call (credential probe -> fresh get_for_call -> Grant charge + durable
authorization record -> begin -> record_call_started -> exactly one
adapter call), the zero-side-effect aborts at every stage, the Mock
isolation, the exactly-once conversions into ``LLMCallResultV1``, and
the no-retry/no-cache properties (SPEC §4.4.4, card Expected line).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Mapping

import pytest

# The orchestrator consumes pydantic runtime contracts; the hash-locked
# gate toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from vespercode.canonical.clock import FakeClockV1
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import DigestV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.contracts.run import (
    RunStateV1,
    WaitContextV1,
    WaitDecisionV1,
)
from vespercode.credentials.port import (
    CredentialBackendProbeV1,
    CredentialBackendUnsafeError,
    CredentialMissingV1,
    CredentialStoreMutationV1,
    CredentialStatusV1,
    SecretCredentialV1,
)
from vespercode.governance.disclosure_decision import (
    DecideDisclosureGrantV1,
    DisclosureDecisionServiceV1,
)
from vespercode.governance.disclosure_ledger import (
    AuthorizePreparedRequestV1,
    DisclosureAuthorizationOutcomeV1,
    DisclosureAuthorizationRecordV1,
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
    RequestContentSegmentV1,
    RequestMessageV1,
    RequestSourceCategoryV1,
    validate_segment_sources,
)
from vespercode.llm.base import ModelResponse
from vespercode.llm.call_result import PresentAuthorizationRecordRefV1
from vespercode.llm.mock_adapter import MockLLMAdapter
from vespercode.llm.openai_adapter import (
    BoundOpenAILLMAdapterV1,
    LLMTransportResultV1,
    OpenAILLMAdapter,
)
from vespercode.llm.prepared_request import (
    MockPreparedModelRequestV1,
    OpenAIPreparedModelRequestV1,
    prepare_mock_request,
    prepare_openai_request,
)
from vespercode.loop.call_orchestrator import (
    AdapterOutcomeV1,
    CallOnceV1,
    CallOrchestrator,
    build_call_result,
)
from vespercode.loop.turn_boundary import (
    AbortBeforeCallResultV1,
    BeginTurnResultV1,
    CloseTurnResultV1,
    RecordCallStartedResultV1,
    TurnBoundary,
    TurnOutcomeV1,
)
from vespercode.profiles.endpoints import OpenAIEndpointV1
from vespercode.profiles.llm import (
    MockLLMProfileV1,
    OpenAILLMProfileV1,
    load_llm_profile,
)
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
from vespercode.storage.migrations.v0007_agent_turns import (
    AGENT_TURNS_V1_MIGRATION,
)
from vespercode.storage.run_repository import RunRepository

_CREATED_AT = CanonicalTimestampV1("2026-08-06T09:00:00.000Z")
_EXPIRES_AT = CanonicalTimestampV1("2026-08-06T09:05:00.000Z")
_DECIDED_AT = CanonicalTimestampV1("2026-08-06T09:01:00.000Z")
_AUTHORIZED_AT = CanonicalTimestampV1("2026-08-06T09:02:00.000Z")
_CLOCK_EPOCH = _AUTHORIZED_AT.epoch_milliseconds
_RUN_DEADLINE = CanonicalTimestampV1("2026-08-06T09:15:00.000Z")

_OPENAI_BUILTIN = (
    Path(__file__).resolve().parents[3]
    / "src/vespercode/profiles/builtin/openai-single-turn-v1.json"
)
_MOCK_BUILTIN = (
    Path(__file__).resolve().parents[3]
    / "src/vespercode/profiles/builtin/mock-deterministic-v1.json"
)

_MIGRATIONS = (
    RUN_WAIT_V1_MIGRATION,
    IDEMPOTENCY_V1_MIGRATION,
    DISCLOSURE_GRANTS_V1_MIGRATION,
    DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
    MEMORY_V1_MIGRATION,
    AUDIT_V1_MIGRATION,
    AGENT_TURNS_V1_MIGRATION,
)

# A valid OpenAI response body the transport spy returns: the adapter
# parses choices[0].message.content into the closed ModelResponse.
_MOCK_ACTION_TEXT = (
    '{"schema_version":1,"action_type":"list_files","root":{"kind":"ROOT"},'
    '"recursive":false,"max_entries":1,"cursor":{"kind":"ABSENT"}}'
)
_OK_RESPONSE_BODY = json.dumps(
    {"choices": [{"message": {"content": _MOCK_ACTION_TEXT}}]},
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")


def openai_profile() -> OpenAILLMProfileV1:
    loaded = load_llm_profile(_OPENAI_BUILTIN.read_bytes())
    assert isinstance(loaded, OpenAILLMProfileV1)
    return loaded


def mock_profile() -> MockLLMProfileV1:
    loaded = load_llm_profile(_MOCK_BUILTIN.read_bytes())
    assert isinstance(loaded, MockLLMProfileV1)
    return loaded


def endpoint() -> OpenAIEndpointV1:
    return OpenAIEndpointV1(
        endpoint_id="OPENAI_PUBLIC_API_V1",
        scheme="https",
        host="api.openai.com",
        effective_port=443,
        base_path="/v1",
    )


def _segment(
    category: RequestSourceCategoryV1,
    content: str,
    path: str | None = None,
) -> RequestContentSegmentV1:
    raw = content.encode("utf-8")
    return RequestContentSegmentV1(
        source_category=category,
        source_path=(
            AbsentV1(kind="ABSENT")
            if path is None
            else PresentV1(kind="PRESENT", value=CanonicalRelativePathV1(path))
        ),
        content=content,
        content_digest=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
    )


def messages(path: str = "src/a.py") -> tuple[RequestMessageV1, ...]:
    """The fixed two-message request: protocol + task + one source file."""
    return (
        RequestMessageV1(
            role="SYSTEM",
            segments=(_segment("HARNESS_PROTOCOL", "VesperCode protocol"),),
        ),
        RequestMessageV1(
            role="USER",
            segments=(
                _segment("TASK", "fix the failing test"),
                _segment("FILE_CONTENT", "source bytes", path),
            ),
        ),
    )


def openai_request(path: str = "src/a.py") -> OpenAIPreparedModelRequestV1:
    return prepare_openai_request(openai_profile(), messages(path))


def mock_request() -> MockPreparedModelRequestV1:
    return prepare_mock_request(mock_profile(), messages())


def subject_for(
    run_id: str,
    *,
    expires_at: CanonicalTimestampV1 = _EXPIRES_AT,
    budget: int = 1000,
) -> DisclosureGrantSubjectV1:
    sources = validate_segment_sources(messages())
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
        openai_profile(),
        endpoint(),
    )


_SUBJECT = subject_for("run-1")


def _insert_run(
    database: ControlDatabase,
    run_id: str,
    status: str,
    phase: str | None,
) -> None:
    with database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots (config_snapshot_id, digest,"
            " llm_profile_id, reference_profile_id, policy_id, target_test_ids,"
            " limits_digest, frozen_at)"
            " VALUES (?, ?, 'openai-single-turn-v1', 'python-src-py312-v1',"
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
            " VALUES (?, 'ws-1', ?, ?, ?, 1, ?, ?)",
            (
                run_id,
                f"snap-{run_id}",
                status,
                phase,
                _CREATED_AT.value,
                _RUN_DEADLINE.value,
            ),
        )


def _create_wait(
    database: ControlDatabase,
    wait_id: str,
    run_id: str,
    subject_digest: str,
) -> None:
    RunRepository(database).create_wait(
        WaitContextV1(
            wait_id=wait_id,
            run_id=run_id,
            wait_kind="DISCLOSURE_GRANT",
            source_phase="AGENT_LOOP",
            subject_digest=DigestV1(value=subject_digest),
            created_at=_CREATED_AT,
            expires_at=_EXPIRES_AT,
        )
    )


def _decide(
    *,
    run_id: str = "run-1",
    wait_id: str = "wait-1",
    event_id: str = "evt-1",
    grant_id: str = "grant-1",
    subject: DisclosureGrantSubjectV1 = _SUBJECT,
) -> DecideDisclosureGrantV1:
    return DecideDisclosureGrantV1(
        decision=WaitDecisionV1(
            wait_id=wait_id,
            run_id=run_id,
            wait_kind="DISCLOSURE_GRANT",
            subject_digest=DigestV1(value=subject.digest),
            decision="APPROVE",
            event_id=event_id,
            decided_at=_DECIDED_AT,
        ),
        subject=subject,
        grant_id=grant_id,
    )


def seed_granted_run(
    database: ControlDatabase,
    run_id: str,
    *,
    budget: int = 1000,
) -> None:
    """Insert one run, wait, and APPROVED Grant (the Task 15.2 lifecycle)."""
    _insert_run(database, run_id, "WAITING_USER", None)
    subject = subject_for(run_id, budget=budget)
    _create_wait(database, f"wait-{run_id}", run_id, subject.digest)
    outcome = DisclosureDecisionServiceV1(database).decide(
        _decide(
            run_id=run_id,
            wait_id=f"wait-{run_id}",
            event_id=f"evt-{run_id}",
            grant_id=f"grant-{run_id}",
            subject=subject,
        )
    )
    assert outcome.kind == "APPROVED"


def valid_openai_call(
    *,
    run_id: str = "run-1",
    request: OpenAIPreparedModelRequestV1 | None = None,
    llm_profile_digest: str | None = None,
    adapter_version: str | None = None,
    endpoint_id: str | None = None,
    model: str | None = None,
    request_serializer_version: str | None = None,
    redaction_profile_id: str | None = None,
    grant_id: str = "grant-run-1",
    authorization_record_id: str = "rec-1",
    event_id: str = "evt-1",
) -> CallOnceV1:
    """One deterministic valid OpenAI call command (the RED fixture)."""
    profile = openai_profile()
    req = request if request is not None else openai_request()
    return CallOnceV1(
        schema_version=1,
        run_id=run_id,
        request=req,
        llm_profile_digest=llm_profile_digest or profile.digest,
        adapter_version=adapter_version or profile.adapter_version,
        endpoint_id=endpoint_id or profile.endpoint_id,
        model=model or profile.model,
        request_serializer_version=(
            request_serializer_version or profile.request_serializer_version
        ),
        redaction_profile_id=redaction_profile_id or profile.redaction_profile_id,
        grant_id=grant_id,
        authorization_record_id=authorization_record_id,
        event_id=event_id,
    )


def valid_mock_call(*, run_id: str = "run-1") -> CallOnceV1:
    """One deterministic valid Mock call command (no real ports)."""
    profile = mock_profile()
    return CallOnceV1(
        schema_version=1,
        run_id=run_id,
        request=mock_request(),
        llm_profile_digest=profile.digest,
        adapter_version=profile.adapter_version,
        script_id=profile.script_id,
        script_digest=profile.script_digest,
    )


class RealCallSpies:
    """The five real call-gate side-effect counters plus the event log.

    ``counts()`` counts persisted effects only: the grant byte-charge and
    the durable authorization record (both inside the one Task 15.E
    authorize transaction), the APPLIED turn/call counts, and the
    transport attempts.  ``events()`` records every invocation in order,
    so the matrix can pin the exact credential -> Grant -> authorization
    -> count -> transport sequence.
    """

    def __init__(self) -> None:
        self._counts = {
            "grant": 0,
            "authorization": 0,
            "turn": 0,
            "call": 0,
            "transport": 0,
        }
        self._events: list[str] = []

    def record(self, event: str) -> None:
        self._events.append(event)

    def increment(self, key: str) -> None:
        self._counts[key] += 1

    def counts(self) -> dict[str, int]:
        return dict(self._counts)

    def events(self) -> list[str]:
        return list(self._events)

    def reset(self) -> None:
        """Clear the event log and every counter (matrix row isolation)."""
        self._events.clear()
        self._counts.update(
            {"grant": 0, "authorization": 0, "turn": 0, "call": 0, "transport": 0}
        )


class _CredentialStoreSpy:
    """One credential store port spy: configurable probe/read outcomes.

    The default is a cleared credential (``credential_missing=True``) so
    the card's exact RED fixture — a cleared credential that must stop
    before every charge or count — holds with no extra configuration; the
    matrix enables the credential per real-call row.
    """

    def __init__(self, spies: RealCallSpies) -> None:
        self._spies = spies
        self.backend_unsafe = False
        self.credential_missing = True

    def probe_backend(self) -> CredentialBackendProbeV1:
        self._spies.record("credential_probe")
        if self.backend_unsafe:
            raise CredentialBackendUnsafeError(
                "backend is not the verified Windows Credential Manager"
            )
        return CredentialBackendProbeV1(
            schema_version=1,
            backend_id="WINDOWS_CREDENTIAL_MANAGER",
            capability="READ_WRITE_DELETE",
        )

    def get_for_call(self, provider: str) -> SecretCredentialV1 | CredentialMissingV1:
        self._spies.record("credential_read")
        if self.credential_missing:
            return CredentialMissingV1(schema_version=1, kind="MISSING")
        return SecretCredentialV1.from_hidden_input("test-secret")

    def set(
        self, provider: str, secret: SecretCredentialV1
    ) -> CredentialStoreMutationV1:
        raise NotImplementedError("the orchestrator never mutates credentials")

    def status(self, provider: str) -> CredentialStatusV1:
        raise NotImplementedError("the orchestrator never reads credential status")

    def clear(self, provider: str) -> CredentialStoreMutationV1:
        raise NotImplementedError("the orchestrator never clears credentials")


class _BoundarySpy(TurnBoundary):
    """One Task 25.B counting-port spy around the real TurnBoundary."""

    def __init__(self, spies: RealCallSpies, inner: TurnBoundary) -> None:
        super().__init__(inner.database)
        self._spies = spies
        self._inner = inner
        self.fail_call_start = False

    def begin(self, run_id: str, expected_state: RunStateV1) -> BeginTurnResultV1:
        self._spies.record("turn")
        result = self._inner.begin(run_id, expected_state)
        if result.kind == "APPLIED":
            self._spies.increment("turn")
        return result

    def record_call_started(
        self, run_id: str, turn_id: str, expected_revision: int
    ) -> RecordCallStartedResultV1:
        self._spies.record("call")
        if self.fail_call_start:
            # Close the ACTIVE turn first so the real CAS boundary returns
            # CLOSED — the post-authorization count-failure stop path.
            with self._inner.database.immediate_transaction() as tx:
                tx.execute(
                    "UPDATE agent_turns SET status = 'CLOSED', outcome = 'ABORTED',"
                    " closed_at = ? WHERE turn_id = ? AND status = 'ACTIVE'",
                    ("2026-08-06T09:02:01.000Z", turn_id),
                )
        result = self._inner.record_call_started(run_id, turn_id, expected_revision)
        if result.kind == "APPLIED":
            self._spies.increment("call")
        return result

    def abort_before_call(self, run_id: str, reason: str) -> AbortBeforeCallResultV1:
        self._spies.record(f"abort:{reason}")
        return self._inner.abort_before_call(run_id, reason)

    def close_turn(
        self,
        run_id: str,
        turn_id: str,
        outcome: TurnOutcomeV1,
        expected_revision: int,
    ) -> CloseTurnResultV1:
        self._spies.record("close")
        return self._inner.close_turn(run_id, turn_id, outcome, expected_revision)


class _LedgerSpy(DisclosureLedger):
    """One Task 15.E ledger spy: counts only persisted AUTHORIZED effects."""

    def __init__(self, spies: RealCallSpies, inner: DisclosureLedger) -> None:
        super().__init__(inner.database, inner.database_path)
        self._spies = spies
        self._inner = inner

    def authorize(
        self, command: AuthorizePreparedRequestV1
    ) -> DisclosureAuthorizationOutcomeV1:
        outcome = self._inner.authorize(command)
        self._spies.record("grant")
        self._spies.record("authorization")
        if outcome.kind == "AUTHORIZED":
            self._spies.increment("grant")
            self._spies.increment("authorization")
        return outcome


class _TransportSpy:
    """One bounded HTTP transport spy with a configurable failure status."""

    def __init__(self, spies: RealCallSpies) -> None:
        self._spies = spies
        self.fail_status: int | None = None

    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> LLMTransportResultV1:
        self._spies.record("transport")
        self._spies.increment("transport")
        if self.fail_status is not None:
            return LLMTransportResultV1(
                status_code=self.fail_status, headers=(), body=b""
            )
        return LLMTransportResultV1(status_code=200, headers=(), body=_OK_RESPONSE_BODY)


class _MockAdapterSpy(MockLLMAdapter):
    """One Mock adapter spy: counts the exact generate invocations."""

    def __init__(self, spies: RealCallSpies) -> None:
        self._spies = spies

    def generate(self, request: MockPreparedModelRequestV1) -> ModelResponse:
        self._spies.record("transport")
        self._spies.increment("transport")
        return super().generate(request)


class _BrokenBindAdapter(OpenAILLMAdapter):
    """One injected broken adapter whose bind always raises (M1 pin)."""

    def bind(
        self,
        authorization: DisclosureAuthorizationRecordV1,
        credential: SecretCredentialV1,
    ) -> BoundOpenAILLMAdapterV1:
        raise RuntimeError("injected bind failure")


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "call_orchestrator.db")
    apply_migrations(database, _MIGRATIONS)
    seed_granted_run(database, "run-1")
    yield database
    database.close()


@pytest.fixture
def spies() -> RealCallSpies:
    return RealCallSpies()


@pytest.fixture
def credential_spy(spies: RealCallSpies) -> _CredentialStoreSpy:
    return _CredentialStoreSpy(spies)


@pytest.fixture
def transport_spy(spies: RealCallSpies) -> _TransportSpy:
    return _TransportSpy(spies)


@pytest.fixture
def mock_spy(spies: RealCallSpies) -> _MockAdapterSpy:
    return _MockAdapterSpy(spies)


@pytest.fixture
def boundary_spy(
    spies: RealCallSpies,
    control_database: ControlDatabase,
) -> _BoundarySpy:
    return _BoundarySpy(
        spies, TurnBoundary(control_database, clock=FakeClockV1(_CLOCK_EPOCH))
    )


@pytest.fixture
def ledger_spy(
    spies: RealCallSpies,
    control_database: ControlDatabase,
    tmp_path: Path,
) -> _LedgerSpy:
    return _LedgerSpy(
        spies,
        DisclosureLedger(control_database, tmp_path / "call_orchestrator.db"),
    )


@pytest.fixture
def orchestrator(
    boundary_spy: _BoundarySpy,
    ledger_spy: _LedgerSpy,
    credential_spy: _CredentialStoreSpy,
    transport_spy: _TransportSpy,
    mock_spy: _MockAdapterSpy,
) -> CallOrchestrator:
    return CallOrchestrator(
        boundary=boundary_spy,
        ledger=ledger_spy,
        credential_store=credential_spy,
        mock_adapter=mock_spy,
        openai_adapter=OpenAILLMAdapter(transport=transport_spy),
        clock=FakeClockV1(_CLOCK_EPOCH),
    )


def _counter_row(
    database: ControlDatabase,
    run_id: str,
) -> tuple[int, int] | None:
    rows = database.read_rows(
        "SELECT turn_count, call_count FROM run_turn_call_counters WHERE run_id = ?",
        (run_id,),
    )
    if not rows:
        return None
    return (int(rows[0][0]), int(rows[0][1]))


def _active_turn_id(database: ControlDatabase, run_id: str) -> str | None:
    rows = database.read_rows(
        "SELECT turn_id FROM agent_turns WHERE run_id = ? AND status = 'ACTIVE'",
        (run_id,),
    )
    if not rows:
        return None
    return str(rows[0][0])


def _grant_state(database: ControlDatabase, grant_id: str) -> tuple[int, str]:
    rows = database.read_rows(
        "SELECT consumed_bytes, status FROM disclosure_grants WHERE grant_id = ?",
        (grant_id,),
    )
    assert rows
    return (int(rows[0][0]), str(rows[0][1]))


def _record_count(database: ControlDatabase) -> int:
    return len(database.read_rows("SELECT 1 FROM disclosure_authorizations"))


def test_cleared_credential_stops_before_every_charge_or_count(
    orchestrator: CallOrchestrator,
    spies: RealCallSpies,
) -> None:
    # The exact RED body of the card (PLAN.md 25.C): the final assert is
    # ruff-wrapped (the card displays it on one 97-char line) — a
    # documented tooling deviation of the T17.1/T24.1 precedent class;
    # the assertions themselves are unchanged.
    result = orchestrator.call_once(valid_openai_call())
    assert result.error_code == "CREDENTIAL_MISSING"
    assert spies.counts() == {
        "grant": 0,
        "authorization": 0,
        "turn": 0,
        "call": 0,
        "transport": 0,
    }


def test_call_orchestration_matrix(
    control_database: ControlDatabase,
    orchestrator: CallOrchestrator,
    spies: RealCallSpies,
    credential_spy: _CredentialStoreSpy,
    transport_spy: _TransportSpy,
    boundary_spy: _BoundarySpy,
) -> None:
    """PLAN Registry row 25.C: the exact one-authorized-call matrix.

    Per the SPEC_PROCESS 49 precedent the card Expected line is the
    operative matrix authority: Mock calls never touch real ports; OpenAI
    calls follow the exact credential -> Grant -> authorization -> count
    -> transport order exactly once, with zero-side-effect aborts at
    every pre-count stage.
    """

    # --- Mock success: no real ports, exactly one adapter call. ---
    seed_granted_run(control_database, "run-mock")
    mock_result = orchestrator.call_once(valid_mock_call(run_id="run-mock"))
    assert mock_result.status == "SUCCEEDED"
    assert mock_result.error_code is None
    assert mock_result.mode == "MOCK"
    assert mock_result.authorization_record_ref.kind == "ABSENT"
    assert mock_result.response_digest.kind == "PRESENT"
    assert spies.events() == ["turn", "call", "transport"]
    assert spies.counts() == {
        "grant": 0,
        "authorization": 0,
        "turn": 1,
        "call": 1,
        "transport": 1,
    }
    assert _counter_row(control_database, "run-mock") == (1, 1)
    assert _record_count(control_database) == 0

    # --- OpenAI success: the exact five-stage order, exactly once. ---
    seed_granted_run(control_database, "run-openai")
    credential_spy.credential_missing = False
    spies.reset()
    request = openai_request()
    charge = request.canonical_byte_count
    result = orchestrator.call_once(
        valid_openai_call(
            run_id="run-openai",
            grant_id="grant-run-openai",
            authorization_record_id="rec-openai",
            event_id="evt-openai",
            request=request,
        )
    )
    assert result.status == "SUCCEEDED"
    assert result.error_code is None
    assert result.mode == "OPENAI"
    assert result.request_digest == request.digest
    assert result.authorization_record_ref.kind == "PRESENT"
    assert result.authorization_record_ref.authorization_record_id == "rec-openai"
    assert result.response_digest.kind == "PRESENT"
    assert spies.events() == [
        "credential_probe",
        "credential_read",
        "grant",
        "authorization",
        "turn",
        "call",
        "transport",
    ]
    assert spies.counts() == {
        "grant": 1,
        "authorization": 1,
        "turn": 1,
        "call": 1,
        "transport": 1,
    }
    assert _counter_row(control_database, "run-openai") == (1, 1)
    assert _grant_state(control_database, "grant-run-openai") == (charge, "ACTIVE")
    assert _record_count(control_database) == 1

    # --- Re-send of the same body re-charges with fresh credential reads
    #     and a fresh turn (no cached credential, no reuse of the record). ---
    turn_one = _active_turn_id(control_database, "run-openai")
    assert turn_one is not None
    boundary_spy.close_turn("run-openai", turn_one, "SUCCEEDED", 2)
    spies.reset()
    second = orchestrator.call_once(
        valid_openai_call(
            run_id="run-openai",
            grant_id="grant-run-openai",
            authorization_record_id="rec-openai-2",
            event_id="evt-openai-2",
            request=request,
        )
    )
    assert second.status == "SUCCEEDED"
    assert spies.events() == [
        "credential_probe",
        "credential_read",
        "grant",
        "authorization",
        "turn",
        "call",
        "transport",
    ]
    assert _grant_state(control_database, "grant-run-openai") == (2 * charge, "ACTIVE")
    assert _record_count(control_database) == 2
    assert _counter_row(control_database, "run-openai") == (2, 2)

    # --- Cleared credential: zero charge, record, count, or transport. ---
    seed_granted_run(control_database, "run-cred")
    credential_spy.credential_missing = True
    spies.reset()
    cleared = orchestrator.call_once(
        valid_openai_call(
            run_id="run-cred",
            grant_id="grant-run-cred",
            authorization_record_id="rec-cred",
            event_id="evt-cred",
        )
    )
    assert cleared.status == "NOT_ATTEMPTED"
    assert cleared.error_code == "CREDENTIAL_MISSING"
    assert cleared.authorization_record_ref.kind == "ABSENT"
    assert spies.events() == [
        "credential_probe",
        "credential_read",
        "abort:CREDENTIAL_MISSING",
    ]
    assert spies.counts() == {
        "grant": 0,
        "authorization": 0,
        "turn": 0,
        "call": 0,
        "transport": 0,
    }
    assert _counter_row(control_database, "run-cred") is None
    assert _grant_state(control_database, "grant-run-cred") == (0, "ACTIVE")
    assert _record_count(control_database) == 2

    # --- Unsafe backend: the probe failure stops before the read. ---
    seed_granted_run(control_database, "run-unsafe")
    credential_spy.credential_missing = False
    credential_spy.backend_unsafe = True
    spies.reset()
    unsafe = orchestrator.call_once(
        valid_openai_call(
            run_id="run-unsafe",
            grant_id="grant-run-unsafe",
            authorization_record_id="rec-unsafe",
            event_id="evt-unsafe",
        )
    )
    assert unsafe.status == "NOT_ATTEMPTED"
    assert unsafe.error_code == "CREDENTIAL_BACKEND_UNSAFE"
    assert spies.events() == ["credential_probe", "abort:CREDENTIAL_BACKEND_UNSAFE"]
    assert spies.counts() == {
        "grant": 0,
        "authorization": 0,
        "turn": 0,
        "call": 0,
        "transport": 0,
    }
    assert _grant_state(control_database, "grant-run-unsafe") == (0, "ACTIVE")
    credential_spy.backend_unsafe = False

    # --- Out-of-scope source: the ledger charges zero and aborts. ---
    seed_granted_run(control_database, "run-scope")
    spies.reset()
    outside = orchestrator.call_once(
        valid_openai_call(
            run_id="run-scope",
            grant_id="grant-run-scope",
            authorization_record_id="rec-scope",
            event_id="evt-scope",
            request=openai_request(path="README.md"),
        )
    )
    assert outside.status == "NOT_ATTEMPTED"
    assert outside.error_code == "DISCLOSURE_SCOPE_EXCEEDED"
    assert outside.authorization_record_ref.kind == "ABSENT"
    assert spies.events() == [
        "credential_probe",
        "credential_read",
        "grant",
        "authorization",
        "abort:DISCLOSURE_SCOPE_EXCEEDED",
    ]
    assert spies.counts() == {
        "grant": 0,
        "authorization": 0,
        "turn": 0,
        "call": 0,
        "transport": 0,
    }
    assert _grant_state(control_database, "grant-run-scope") == (0, "ACTIVE")
    assert _record_count(control_database) == 2

    # --- Budget insufficient: the ledger charges zero and aborts. ---
    seed_granted_run(control_database, "run-budget", budget=10)
    spies.reset()
    budgeted = orchestrator.call_once(
        valid_openai_call(
            run_id="run-budget",
            grant_id="grant-run-budget",
            authorization_record_id="rec-budget",
            event_id="evt-budget",
        )
    )
    assert budgeted.status == "NOT_ATTEMPTED"
    assert budgeted.error_code == "DISCLOSURE_BUDGET_EXCEEDED"
    assert spies.counts() == {
        "grant": 0,
        "authorization": 0,
        "turn": 0,
        "call": 0,
        "transport": 0,
    }
    assert _grant_state(control_database, "grant-run-budget") == (0, "ACTIVE")
    assert _record_count(control_database) == 2

    # --- Endpoint drift: LLM_ENDPOINT_MISMATCH before any side effect. ---
    seed_granted_run(control_database, "run-endpoint")
    spies.reset()
    drifted = orchestrator.call_once(
        valid_openai_call(
            run_id="run-endpoint",
            grant_id="grant-run-endpoint",
            authorization_record_id="rec-endpoint",
            event_id="evt-endpoint",
            endpoint_id="OPENAI_PUBLIC_API_V2",
        )
    )
    assert drifted.status == "NOT_ATTEMPTED"
    assert drifted.error_code == "LLM_ENDPOINT_MISMATCH"
    assert spies.events() == ["abort:LLM_ENDPOINT_MISMATCH"]
    assert spies.counts() == {
        "grant": 0,
        "authorization": 0,
        "turn": 0,
        "call": 0,
        "transport": 0,
    }
    assert _record_count(control_database) == 2

    # --- Frozen profile digest drift: INTERNAL_ERROR before any side effect. ---
    seed_granted_run(control_database, "run-profile")
    spies.reset()
    drifted_profile = orchestrator.call_once(
        valid_openai_call(
            run_id="run-profile",
            grant_id="grant-run-profile",
            authorization_record_id="rec-profile",
            event_id="evt-profile",
            llm_profile_digest="0" * 64,
        )
    )
    assert drifted_profile.status == "NOT_ATTEMPTED"
    assert drifted_profile.error_code == "INTERNAL_ERROR"
    assert spies.events() == ["abort:INTERNAL_ERROR"]
    assert spies.counts() == {
        "grant": 0,
        "authorization": 0,
        "turn": 0,
        "call": 0,
        "transport": 0,
    }
    assert _record_count(control_database) == 2

    # --- Mock script drift: INTERNAL_ERROR before any side effect. ---
    seed_granted_run(control_database, "run-script")
    spies.reset()
    profile = mock_profile()
    drifted_mock = CallOnceV1(
        schema_version=1,
        run_id="run-script",
        request=mock_request(),
        llm_profile_digest=profile.digest,
        adapter_version=profile.adapter_version,
        script_id=profile.script_id,
        script_digest="0" * 64,
    )
    script_drift = orchestrator.call_once(drifted_mock)
    assert script_drift.status == "NOT_ATTEMPTED"
    assert script_drift.error_code == "INTERNAL_ERROR"
    assert spies.events() == ["abort:INTERNAL_ERROR"]
    assert spies.counts() == {
        "grant": 0,
        "authorization": 0,
        "turn": 0,
        "call": 0,
        "transport": 0,
    }
    assert _counter_row(control_database, "run-script") is None

    # --- Bounded adapter failure: FAILED with the stable code, consumed
    #     counts kept, charge and record not refunded. ---
    seed_granted_run(control_database, "run-fail")
    transport_spy.fail_status = 500
    spies.reset()
    failed = orchestrator.call_once(
        valid_openai_call(
            run_id="run-fail",
            grant_id="grant-run-fail",
            authorization_record_id="rec-fail",
            event_id="evt-fail",
        )
    )
    assert failed.status == "FAILED"
    assert failed.error_code == "LLM_CALL_FAILED"
    assert failed.authorization_record_ref.kind == "PRESENT"
    assert failed.response_digest.kind == "ABSENT"
    assert spies.counts() == {
        "grant": 1,
        "authorization": 1,
        "turn": 1,
        "call": 1,
        "transport": 1,
    }
    assert _counter_row(control_database, "run-fail") == (1, 1)
    assert _grant_state(control_database, "grant-run-fail")[0] > 0
    assert _record_count(control_database) == 3
    transport_spy.fail_status = None

    # --- Post-authorization count failure: NOT_ATTEMPTED with the record
    #     reference PRESENT; the charge stands and the counts stay (1, 0). ---
    seed_granted_run(control_database, "run-countfail")
    boundary_spy.fail_call_start = True
    spies.reset()
    count_failed = orchestrator.call_once(
        valid_openai_call(
            run_id="run-countfail",
            grant_id="grant-run-countfail",
            authorization_record_id="rec-countfail",
            event_id="evt-countfail",
        )
    )
    assert count_failed.status == "NOT_ATTEMPTED"
    assert count_failed.error_code == "INTERNAL_ERROR"
    assert count_failed.authorization_record_ref.kind == "PRESENT"
    assert (
        count_failed.authorization_record_ref.authorization_record_id == "rec-countfail"
    )
    assert spies.events() == [
        "credential_probe",
        "credential_read",
        "grant",
        "authorization",
        "turn",
        "call",
        "abort:INTERNAL_ERROR",
    ]
    assert spies.counts() == {
        "grant": 1,
        "authorization": 1,
        "turn": 1,
        "call": 0,
        "transport": 0,
    }
    assert _counter_row(control_database, "run-countfail") == (1, 0)
    assert _record_count(control_database) == 4
    boundary_spy.fail_call_start = False

    # --- Begin failure (run not in AGENT_LOOP): INTERNAL_ERROR with zero
    #     counts and zero persisted effects. ---
    _insert_run(control_database, "run-preflight", "RUNNING", "PREFLIGHT")
    spies.reset()
    preflight = orchestrator.call_once(
        valid_openai_call(
            run_id="run-preflight",
            grant_id="grant-run-1",
            authorization_record_id="rec-preflight",
            event_id="evt-preflight",
        )
    )
    assert preflight.status == "NOT_ATTEMPTED"
    assert preflight.error_code == "INTERNAL_ERROR"
    assert spies.events() == [
        "credential_probe",
        "credential_read",
        "grant",
        "authorization",
        "turn",
        "abort:INTERNAL_ERROR",
    ]
    assert spies.counts() == {
        "grant": 1,
        "authorization": 1,
        "turn": 0,
        "call": 0,
        "transport": 0,
    }
    assert _counter_row(control_database, "run-preflight") is None


def test_broken_adapter_bind_stops_before_transport(
    control_database: ControlDatabase,
    spies: RealCallSpies,
    credential_spy: _CredentialStoreSpy,
    boundary_spy: _BoundarySpy,
    ledger_spy: _LedgerSpy,
) -> None:
    """A bind failure is the post-charge pre-transport stop family (M1).

    A deliberately broken adapter whose bind raises stops with
    NOT_ATTEMPTED/INTERNAL_ERROR, the PRESENT record reference, consumed
    counts (1,1), and zero transport attempts — the charge never refunded.
    """
    credential_spy.credential_missing = False
    broken = CallOrchestrator(
        boundary=boundary_spy,
        ledger=ledger_spy,
        credential_store=credential_spy,
        mock_adapter=_MockAdapterSpy(spies),
        openai_adapter=_BrokenBindAdapter(),
        clock=FakeClockV1(_CLOCK_EPOCH),
    )
    spies.reset()
    result = broken.call_once(valid_openai_call())
    assert result.status == "NOT_ATTEMPTED"
    assert result.error_code == "INTERNAL_ERROR"
    assert result.authorization_record_ref.kind == "PRESENT"
    assert result.authorization_record_ref.authorization_record_id == "rec-1"
    assert spies.events() == [
        "credential_probe",
        "credential_read",
        "grant",
        "authorization",
        "turn",
        "call",
        "abort:INTERNAL_ERROR",
    ]
    assert spies.counts() == {
        "grant": 1,
        "authorization": 1,
        "turn": 1,
        "call": 1,
        "transport": 0,
    }
    assert _counter_row(control_database, "run-1") == (1, 1)


def test_build_call_result_converts_each_adapter_outcome_exactly(
    spies: RealCallSpies,
) -> None:
    """The builder converts only response/failure/NOT_ATTEMPTED outcomes."""
    request = openai_request()
    response = _response(_MOCK_ACTION_TEXT)
    succeeded = build_call_result(
        request,
        PresentAuthorizationRecordRefV1(
            kind="PRESENT", authorization_record_id="rec-1"
        ),
        AdapterOutcomeV1(schema_version=1, kind="RESPONSE", response=response),
    )
    assert succeeded.status == "SUCCEEDED"
    assert succeeded.error_code is None
    assert succeeded.response_digest.kind == "PRESENT"
    assert succeeded.response_digest.value == response.text_digest
    assert succeeded.authorization_record_ref.kind == "PRESENT"

    failed = build_call_result(
        request,
        PresentAuthorizationRecordRefV1(
            kind="PRESENT", authorization_record_id="rec-1"
        ),
        AdapterOutcomeV1(
            schema_version=1, kind="FAILURE", stable_error_code="LLM_CALL_FAILED"
        ),
    )
    assert failed.status == "FAILED"
    assert failed.error_code == "LLM_CALL_FAILED"
    assert failed.response_digest.kind == "ABSENT"

    not_attempted = build_call_result(
        request,
        AbsentV1(kind="ABSENT"),
        AdapterOutcomeV1(
            schema_version=1,
            kind="NOT_ATTEMPTED",
            stable_error_code="CREDENTIAL_MISSING",
        ),
    )
    assert not_attempted.status == "NOT_ATTEMPTED"
    assert not_attempted.error_code == "CREDENTIAL_MISSING"
    assert not_attempted.authorization_record_ref.kind == "ABSENT"


def _response(text: str) -> ModelResponse:
    raw = text.encode("utf-8")
    return ModelResponse(
        schema_version=1,
        text=text,
        text_digest=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
    )
