"""T25.2 legacy step 25.C: one authorized Mock/OpenAI call orchestration.

``CallOrchestrator.call_once`` prepares and performs exactly one Mock or
OpenAI call, enforcing fresh credential and authorization ordering before
Task 25.B records call start (SPEC §4.4.4): Mock requests route without
real ports; every real call re-probes and re-reads the sole Windows
credential store before Grant consumption, authorization, turn/call
counting, or transport.  The exact real-call sequence is credential
probe -> fresh ``get_for_call`` -> Grant byte-charge + durable
authorization record (one Task 15.E transaction) -> Task 25.B ``begin``
(turn count) -> ``record_call_started`` (call count) -> exactly one
adapter call; every pre-count failure aborts through the Task 25.B
zero-count abort port with the exact unchanged counts, and only the
resulting response or bounded adapter failure converts into the
task-owned ``LLMCallResultV1`` envelope (T17.1 precedent: the card's
exact RED reads ``result.error_code`` directly, which the read-only Task
16.A envelope cannot satisfy).  The orchestrator never closes the turn
(the caller owns close-on-stop per the Task 25.B interface split), never
retries, never falls back, never caches credentials, never reinterprets
policy (a DENY can never be expanded into a call here), and never
reconstructs an uncertain response (GREEN-2/GREEN-4).
"""

from __future__ import annotations

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.canonical.clock import ClockV1, SystemClockV1
from vespercode.contracts.evidence import _DIGEST_RE
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.contracts.run import RunStateV1
from vespercode.credentials.port import (
    CredentialBackendUnsafeError,
    CredentialMissingV1,
    CredentialStorePortV1,
    SecretCredentialV1,
)
from vespercode.governance.disclosure_ledger import (
    AuthorizePreparedRequestV1,
    DisclosureAuthorizationRecordV1,
    DisclosureLedger,
)
from vespercode.governance.request_sources import (
    SourceValidationError,
    validate_segment_sources,
)
from vespercode.llm.base import ModelResponse
from vespercode.llm.call_result import (
    OptionalAuthorizationRecordRefV1,
    OptionalLLMCallErrorV1,
    OptionalResponseDigestV1,
    PresentAuthorizationRecordRefV1,
    PresentLLMCallErrorV1,
    PresentResponseDigestV1,
)
from vespercode.llm.mock_adapter import MockLLMAdapter, MockScriptMismatchError
from vespercode.llm.openai_adapter import (
    OpenAILLMAdapter,
    OpenAITransportFailure,
)
from vespercode.llm.prepared_request import (
    MockPreparedModelRequestV1,
    OpenAIPreparedModelRequestV1,
    PreparedModelRequestV1,
)
from vespercode.loop.turn_boundary import TurnBoundary
from vespercode.profiles.endpoints import OpenAIEndpointRegistry

# The T16.1 adapter versions the orchestrator holds (the frozen
# profile/adapter identity gate of SPEC §4.2.1/§4.4.4: a command whose
# claimed adapter version drifts is rejected before any counting).
MOCK_ADAPTER_VERSION_V1 = "1"
OPENAI_ADAPTER_VERSION_V1 = "1"

_MAX_IDENTIFIER_CHARS = 128

# The only state in which a turn can be established (SPEC §4.2.3/§4.2.5);
# the orchestrator invokes the Task 25.B counting port with this exact
# expectation at its post-authorization counting point.
_RUNNING_AGENT_LOOP = RunStateV1(
    status="RUNNING", phase=PresentV1(kind="PRESENT", value="AGENT_LOOP")
)

# The closed mapping of Task 15.E authorization outcomes onto the SPEC
# §4.4.4 stable error codes of the orchestrator's abort path.  Grant
# absence, subject drift, and ledger replay conflicts are control-plane
# consistency failures and fail closed as INTERNAL_ERROR.
_AUTHORIZATION_FAILURE_CODES: dict[str, str] = {
    "DISCLOSURE_SCOPE_EXCEEDED": "DISCLOSURE_SCOPE_EXCEEDED",
    "DISCLOSURE_BUDGET_EXCEEDED": "DISCLOSURE_BUDGET_EXCEEDED",
    "EXPIRED": "DISCLOSURE_GRANT_EXPIRED",
    "REVOKED": "DISCLOSURE_GRANT_REVOKED",
    "EXHAUSTED": "DISCLOSURE_BUDGET_EXCEEDED",
}


def _require_sha256_hex(value: str) -> str:
    """The closed 64-lowercase-hex digest form of every digest field."""
    if _DIGEST_RE.fullmatch(value) is None:
        raise ValueError("digests must be exactly 64 lowercase hexadecimal characters")
    return value


def _require_identifier(value: str) -> str:
    """One bounded non-empty identifier (SPEC §4.4.4 id bounds)."""
    if value == "":
        raise ValueError("identifiers must be non-empty")
    if len(value.encode("utf-8")) > _MAX_IDENTIFIER_CHARS:
        raise ValueError("identifiers must be at most 128 UTF-8 bytes")
    return value


class LLMCallResultV1(BaseModel):
    """SPEC §4.4.4: one closed, body-free call result (orchestrator-owned).

    The task-owned envelope (T17.1 precedent) keeps the exact SPEC fields
    and closed status combinations, exposes the card's RED contract
    ``error_code`` as a derived property, and admits one honest
    NOT_ATTEMPTED extension: an OpenAI NOT_ATTEMPTED result binds
    ``authorization_record_ref=ABSENT`` exactly when no authorization
    record was created (a pre-charge abort) and ``PRESENT`` when the
    charge/record happened but the count or transport did not (a
    post-charge stop) — the ABSENT/PRESENT pair is pinned in the 25.C
    matrix.  Every other OpenAI status requires the PRESENT ref; Mock
    results always bind ABSENT and never use DELIVERY_UNKNOWN.

    The same class name as the Task 16.A contract envelope is the
    established T17.1 pattern (the dispatcher's same-named
    ``ActionResultV1``): this module's envelope is what the loop
    (successor 25.G) consumes, the Task 16.A envelope has no external
    importers, and the NOT_ATTEMPTED/ABSENT relaxation is forced by the
    card's exact RED contract.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    mode: Literal["MOCK", "OPENAI"]
    llm_profile_digest: StrictStr
    request_digest: StrictStr
    authorization_record_ref: OptionalAuthorizationRecordRefV1
    status: Literal["NOT_ATTEMPTED", "SUCCEEDED", "FAILED", "DELIVERY_UNKNOWN"]
    response_digest: OptionalResponseDigestV1
    error: OptionalLLMCallErrorV1

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("llm_profile_digest", "request_digest")
    @classmethod
    def _digests_have_exact_form(cls, value: str) -> str:
        return _require_sha256_hex(value)

    @property
    def error_code(self) -> str | None:
        """The stable failure code of the result, or ``None`` on SUCCEEDED.

        The card's exact RED contract reads ``result.error_code`` directly
        (T17.1 precedent for the task-owned envelope); the value always
        equals the ``error`` union's stable code when present.
        """
        if self.error.kind == "PRESENT":
            return self.error.stable_error_code
        return None

    @model_validator(mode="after")
    def _closed_status_combinations(self) -> LLMCallResultV1:
        if self.mode == "MOCK":
            if self.authorization_record_ref.kind != "ABSENT":
                raise ValueError(
                    "Mock call results must bind authorization_record_ref=ABSENT"
                )
            if self.status == "DELIVERY_UNKNOWN":
                raise ValueError("Mock call results must never use DELIVERY_UNKNOWN")
        elif self.status != "NOT_ATTEMPTED" and (
            self.authorization_record_ref.kind != "PRESENT"
        ):
            raise ValueError(
                "OpenAI results other than NOT_ATTEMPTED must bind a PRESENT "
                "authorization record"
            )
        if self.status == "SUCCEEDED":
            if self.response_digest.kind != "PRESENT" or self.error.kind != "ABSENT":
                raise ValueError(
                    "SUCCEEDED requires response_digest=PRESENT and error=ABSENT"
                )
        elif self.response_digest.kind != "ABSENT" or self.error.kind != "PRESENT":
            raise ValueError(
                "non-SUCCEEDED results require response_digest=ABSENT and error=PRESENT"
            )
        return self


class AdapterOutcomeV1(BaseModel):
    """One closed adapter outcome: the response, or a bounded failure.

    ``RESPONSE`` carries the exact ``ModelResponse``; ``FAILURE`` and
    ``NOT_ATTEMPTED`` carry the stable error code and no response.
    ``DELIVERY_UNKNOWN`` is never constructed here (card GREEN-4:
    uncertain-response reconstruction remains out of scope).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    kind: Literal["RESPONSE", "FAILURE", "NOT_ATTEMPTED"]
    response: ModelResponse | None = None
    stable_error_code: StrictStr | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @model_validator(mode="after")
    def _require_exact_outcome(self) -> AdapterOutcomeV1:
        if self.kind == "RESPONSE":
            if self.response is None or self.stable_error_code is not None:
                raise ValueError(
                    "RESPONSE outcomes carry the response and no error code"
                )
        elif self.response is not None or self.stable_error_code is None:
            raise ValueError(
                "FAILURE and NOT_ATTEMPTED outcomes carry the stable error "
                "code and no response"
            )
        return self


class CallResultConstructionErrorV1(ValueError):
    """Closed rejection of an invalid ``LLMCallResultV1`` construction.

    A Mock result with a PRESENT authorization ref, an OpenAI result with
    an ABSENT ref outside NOT_ATTEMPTED, or any inconsistent mode/status
    combination fails closed here (SPEC §4.2.8 INTERNAL_ERROR protection)
    before the result can be published.
    """


class CallOnceV1(BaseModel):
    """One closed single-call command (SPEC §4.4.4 call facts only).

    Carries the run identity, the prepared request, the frozen profile
    facts (digest, adapter version, and the exact mode-specific identity
    fields), and — for real calls only — the grant/record/event ids.  The
    mode-specific facts are closed: Mock commands require the Mock script
    facts and forbid OpenAI facts and grant ids; OpenAI commands require
    the OpenAI facts and the grant ids and forbid Mock facts.  The
    ``turn_id``/``expected_revision`` of the Task 25.B counting port are
    intentionally absent: the orchestrator establishes the turn and counts
    the call at its own post-authorization boundaries.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    run_id: StrictStr
    request: PreparedModelRequestV1
    llm_profile_digest: StrictStr
    adapter_version: StrictStr
    script_id: StrictStr | None = None
    script_digest: StrictStr | None = None
    endpoint_id: StrictStr | None = None
    model: StrictStr | None = None
    request_serializer_version: StrictStr | None = None
    redaction_profile_id: StrictStr | None = None
    grant_id: StrictStr | None = None
    authorization_record_id: StrictStr | None = None
    event_id: StrictStr | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("llm_profile_digest", "script_digest")
    @classmethod
    def _digests_have_exact_form(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _require_sha256_hex(value)

    @field_validator("run_id", "script_id")
    @classmethod
    def _identifiers_are_bounded(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _require_identifier(value)

    @model_validator(mode="after")
    def _mode_facts_are_exact(self) -> CallOnceV1:
        if self.request.mode == "MOCK":
            if (
                self.script_id is None
                or self.script_digest is None
                or self.endpoint_id is not None
                or self.model is not None
                or self.request_serializer_version is not None
                or self.redaction_profile_id is not None
                or self.grant_id is not None
                or self.authorization_record_id is not None
                or self.event_id is not None
            ):
                raise ValueError(
                    "MOCK commands require the Mock script facts and forbid "
                    "every OpenAI fact and grant id"
                )
        elif (
            self.endpoint_id is None
            or self.model is None
            or self.request_serializer_version is None
            or self.redaction_profile_id is None
            or self.grant_id is None
            or self.authorization_record_id is None
            or self.event_id is None
            or self.script_id is not None
            or self.script_digest is not None
        ):
            raise ValueError(
                "OPENAI commands require the OpenAI facts and grant ids and "
                "forbid every Mock fact"
            )
        return self


def build_call_result(
    request: PreparedModelRequestV1,
    authorization_ref: OptionalAuthorizationRecordRefV1,
    outcome: AdapterOutcomeV1,
) -> LLMCallResultV1:
    """Convert exactly one response or bounded adapter failure into a
    closed ``LLMCallResultV1`` (card Interface, GREEN-2).

    The mode, profile digest, and request digest always bind the called
    prepared request; a Mock result with a PRESENT ref, an OpenAI result
    with an ABSENT ref outside NOT_ATTEMPTED, or any status/ref/response
    combination the envelope forbids fails closed with
    ``CallResultConstructionErrorV1``.
    """
    if request.mode == "MOCK" and authorization_ref.kind == "PRESENT":
        raise CallResultConstructionErrorV1(
            "Mock call results must bind authorization_record_ref=ABSENT"
        )
    if (
        request.mode == "OPENAI"
        and authorization_ref.kind == "ABSENT"
        and outcome.kind != "NOT_ATTEMPTED"
    ):
        raise CallResultConstructionErrorV1(
            "OpenAI call results other than NOT_ATTEMPTED require a PRESENT "
            "authorization record"
        )
    if outcome.kind == "RESPONSE":
        assert outcome.response is not None
        response_digest: OptionalResponseDigestV1 = PresentResponseDigestV1(
            kind="PRESENT", value=outcome.response.text_digest
        )
        error: OptionalLLMCallErrorV1 = AbsentV1(kind="ABSENT")
        status: Literal["NOT_ATTEMPTED", "SUCCEEDED", "FAILED", "DELIVERY_UNKNOWN"] = (
            "SUCCEEDED"
        )
    else:
        assert outcome.stable_error_code is not None
        response_digest = AbsentV1(kind="ABSENT")
        error = PresentLLMCallErrorV1(
            kind="PRESENT", stable_error_code=outcome.stable_error_code
        )
        status = "NOT_ATTEMPTED" if outcome.kind == "NOT_ATTEMPTED" else "FAILED"
    try:
        return LLMCallResultV1(
            schema_version=1,
            mode=request.mode,
            llm_profile_digest=request.llm_profile_digest,
            request_digest=request.digest,
            authorization_record_ref=authorization_ref,
            status=status,
            response_digest=response_digest,
            error=error,
        )
    except Exception as exc:
        raise CallResultConstructionErrorV1(
            "the call result combination is not closed"
        ) from exc


class CallOrchestrator:
    """One deterministic orchestrator of exactly one authorized call.

    The boundary (Task 25.B counting port), the Task 15.E disclosure
    ledger, the Task 27.B credential store, and the exact Task 16.B
    adapters are injected; ``call_once`` enforces the exact
    credential -> Grant -> authorization -> count -> transport sequence
    once (GREEN-2) and converts only the resulting response or bounded
    adapter failure into ``LLMCallResultV1`` (GREEN-2/GREEN-4).
    """

    def __init__(
        self,
        *,
        boundary: TurnBoundary,
        ledger: DisclosureLedger,
        credential_store: CredentialStorePortV1,
        mock_adapter: MockLLMAdapter | None = None,
        openai_adapter: OpenAILLMAdapter | None = None,
        clock: ClockV1 | None = None,
    ) -> None:
        self._boundary = boundary
        self._ledger = ledger
        self._credential_store = credential_store
        self._mock_adapter = (
            mock_adapter if mock_adapter is not None else MockLLMAdapter()
        )
        self._openai_adapter = (
            openai_adapter if openai_adapter is not None else OpenAILLMAdapter()
        )
        self._clock = clock if clock is not None else SystemClockV1()

    def call_once(self, command: CallOnceV1) -> LLMCallResultV1:
        """Prepare and perform exactly one authorized call (GREEN-2)."""
        if command.request.mode == "MOCK":
            return self._call_mock(command)
        return self._call_openai(command)

    # ------------------------------------------------------------------
    # Mock path: no credential, Grant, authorization, or network behavior.
    # ------------------------------------------------------------------

    def _call_mock(self, command: CallOnceV1) -> LLMCallResultV1:
        request = command.request
        assert isinstance(request, MockPreparedModelRequestV1)
        gate = _mock_consistency_gate(request, command)
        if gate is not None:
            return self._abort(command, gate)
        begun = self._boundary.begin(command.run_id, _RUNNING_AGENT_LOOP)
        if begun.kind != "APPLIED" or begun.turn_id is None:
            return self._abort(command, "INTERNAL_ERROR")
        recorded = self._boundary.record_call_started(command.run_id, begun.turn_id, 1)
        if recorded.kind != "APPLIED":
            return self._abort(command, "INTERNAL_ERROR")
        try:
            response = self._mock_adapter.generate(request)
        except MockScriptMismatchError:
            return build_call_result(
                request,
                AbsentV1(kind="ABSENT"),
                AdapterOutcomeV1(
                    schema_version=1,
                    kind="FAILURE",
                    stable_error_code="LLM_CALL_FAILED",
                ),
            )
        except Exception:  # noqa: BLE001 - fail closed, no raw exception escapes
            return build_call_result(
                request,
                AbsentV1(kind="ABSENT"),
                AdapterOutcomeV1(
                    schema_version=1,
                    kind="FAILURE",
                    stable_error_code="INTERNAL_ERROR",
                ),
            )
        return build_call_result(
            request,
            AbsentV1(kind="ABSENT"),
            AdapterOutcomeV1(schema_version=1, kind="RESPONSE", response=response),
        )

    # ------------------------------------------------------------------
    # OpenAI path: the exact five-stage real-call sequence (SPEC §4.4.4).
    # ------------------------------------------------------------------

    def _call_openai(self, command: CallOnceV1) -> LLMCallResultV1:
        request = command.request
        assert isinstance(request, OpenAIPreparedModelRequestV1)
        gate = _openai_consistency_gate(request, command)
        if gate is not None:
            return self._abort(command, gate)
        # The CallOnceV1 validator guarantees the OpenAI facts for an
        # OPENAI command (mode-specific closure); the asserts narrow the
        # optional fields for the ledger command below.
        assert command.model is not None
        assert command.request_serializer_version is not None
        assert command.redaction_profile_id is not None
        assert command.grant_id is not None
        assert command.authorization_record_id is not None
        assert command.event_id is not None
        # Static endpoint/effective-target consistency (SPEC §4.4.4): the
        # request endpoint must equal the frozen profile endpoint and
        # resolve through the trusted built-in map only.
        if request.endpoint_id != command.endpoint_id:
            return self._abort(command, "LLM_ENDPOINT_MISMATCH")
        try:
            OpenAIEndpointRegistry.resolve(request.endpoint_id)
        except Exception:  # noqa: BLE001 - unknown endpoint fails closed
            return self._abort(command, "LLM_ENDPOINT_MISMATCH")
        # The exact one-to-one source projection (SPEC §4.4.4): one
        # RequestSourceV1 per segment; any projection violation is a
        # control-plane construction error before Grant consumption.
        try:
            actual_sources = validate_segment_sources(request.messages)
        except SourceValidationError:
            return self._abort(command, "INTERNAL_ERROR")
        # Fresh credential for every real call (SPEC §4.4.4 step 4): the
        # backend probe and the per-call read precede Grant consumption.
        try:
            self._credential_store.probe_backend()
        except CredentialBackendUnsafeError:
            return self._abort(command, "CREDENTIAL_BACKEND_UNSAFE")
        except Exception:  # noqa: BLE001 - unverifiable backend is unsafe
            return self._abort(command, "CREDENTIAL_BACKEND_UNSAFE")
        try:
            credential = self._credential_store.get_for_call("OPENAI")
        except Exception:  # noqa: BLE001 - an unreadable credential is unsafe
            return self._abort(command, "CREDENTIAL_BACKEND_UNSAFE")
        if isinstance(credential, CredentialMissingV1):
            return self._abort(command, "CREDENTIAL_MISSING")
        assert isinstance(credential, SecretCredentialV1)
        # Grant byte-charge + durable authorization record: one Task 15.E
        # transaction that revalidates the subject, scopes, and budget and
        # charges zero on every rejection (SPEC §4.4.4 step 5).
        outcome = self._ledger.authorize(
            AuthorizePreparedRequestV1(
                authorization_record_id=command.authorization_record_id,
                grant_id=command.grant_id,
                request_digest=request.digest,
                actual_sources=actual_sources,
                charge_bytes=request.canonical_byte_count,
                llm_profile_digest=command.llm_profile_digest,
                provider="openai",
                endpoint_id=command.endpoint_id,
                model=command.model,
                request_serializer_version=command.request_serializer_version,
                redaction_profile_id=command.redaction_profile_id,
                event_id=command.event_id,
                authorized_at=self._clock.now(),
            )
        )
        if outcome.kind != "AUTHORIZED" or outcome.record is None:
            return self._abort(
                command,
                _AUTHORIZATION_FAILURE_CODES.get(outcome.kind, "INTERNAL_ERROR"),
            )
        record = outcome.record
        # The Task 25.B counting point: begin (turn) then record_call_started
        # (call) as adjacent post-authorization boundaries (SPEC §4.2.5).
        begun = self._boundary.begin(command.run_id, _RUNNING_AGENT_LOOP)
        if begun.kind != "APPLIED" or begun.turn_id is None:
            return self._abort_after_charge(command, record)
        recorded = self._boundary.record_call_started(command.run_id, begun.turn_id, 1)
        if recorded.kind != "APPLIED":
            return self._abort_after_charge(command, record)
        ref = PresentAuthorizationRecordRefV1(
            kind="PRESENT", authorization_record_id=record.authorization_record_id
        )
        try:
            # Exactly one adapter call with the fresh credential (never
            # re-read); the bind failure is guarded too — a broken adapter
            # stops as the same post-charge pre-transport family as the
            # count failure (NOT_ATTEMPTED, PRESENT record ref, counts
            # consumed, charge never refunded).
            bound = self._openai_adapter.bind(record, credential)
        except Exception:  # noqa: BLE001 - a bind failure stops before transport
            return self._abort_after_charge(command, record)
        try:
            response = bound.generate(request)
        except OpenAITransportFailure as failure:
            return build_call_result(
                request,
                ref,
                AdapterOutcomeV1(
                    schema_version=1,
                    kind="FAILURE",
                    stable_error_code=failure.error_code,
                ),
            )
        except Exception:  # noqa: BLE001 - fail closed, no raw exception escapes
            return build_call_result(
                request,
                ref,
                AdapterOutcomeV1(
                    schema_version=1,
                    kind="FAILURE",
                    stable_error_code="INTERNAL_ERROR",
                ),
            )
        return build_call_result(
            request,
            ref,
            AdapterOutcomeV1(schema_version=1, kind="RESPONSE", response=response),
        )

    # ------------------------------------------------------------------
    # The zero-count abort paths (Task 25.B).
    # ------------------------------------------------------------------

    def _abort(self, command: CallOnceV1, error_code: str) -> LLMCallResultV1:
        """One pre-count abort: the exact unchanged counts are reported
        through the Task 25.B zero-side-effect abort port and the result
        binds ``authorization_record_ref=ABSENT`` (no record was created)."""
        self._boundary.abort_before_call(command.run_id, error_code)
        return build_call_result(
            command.request,
            AbsentV1(kind="ABSENT"),
            AdapterOutcomeV1(
                schema_version=1,
                kind="NOT_ATTEMPTED",
                stable_error_code=error_code,
            ),
        )

    def _abort_after_charge(
        self,
        command: CallOnceV1,
        record: DisclosureAuthorizationRecordV1,
    ) -> LLMCallResultV1:
        """One post-charge stop: the charge and the durable record stand
        (never refunded, SPEC §4.4.4) and the NOT_ATTEMPTED result binds
        the PRESENT record reference."""
        self._boundary.abort_before_call(command.run_id, "INTERNAL_ERROR")
        return build_call_result(
            command.request,
            PresentAuthorizationRecordRefV1(
                kind="PRESENT",
                authorization_record_id=record.authorization_record_id,
            ),
            AdapterOutcomeV1(
                schema_version=1,
                kind="NOT_ATTEMPTED",
                stable_error_code="INTERNAL_ERROR",
            ),
        )


def _mock_consistency_gate(
    request: MockPreparedModelRequestV1,
    command: CallOnceV1,
) -> str | None:
    """The frozen profile/adapter/request consistency gate for Mock calls.

    A digest, script, or adapter-version drift fails closed with
    INTERNAL_ERROR before any counting or adapter call (SPEC §4.2.1/
    §4.4.4).
    """
    if (
        request.llm_profile_digest != command.llm_profile_digest
        or command.adapter_version != MOCK_ADAPTER_VERSION_V1
        or request.script_id != command.script_id
        or request.script_digest != command.script_digest
    ):
        return "INTERNAL_ERROR"
    return None


def _openai_consistency_gate(
    request: OpenAIPreparedModelRequestV1,
    command: CallOnceV1,
) -> str | None:
    """The frozen profile/adapter/request consistency gate for real calls.

    A digest, model, serializer, or redaction drift fails closed with
    INTERNAL_ERROR; an endpoint drift is the exact
    ``LLM_ENDPOINT_MISMATCH`` (SPEC §4.4.4).  Both precede Grant
    consumption, counting, and transport.
    """
    if request.llm_profile_digest != command.llm_profile_digest:
        return "INTERNAL_ERROR"
    if command.adapter_version != OPENAI_ADAPTER_VERSION_V1:
        return "INTERNAL_ERROR"
    if (
        request.model != command.model
        or request.request_serializer_version != command.request_serializer_version
        or request.redaction_profile_id != command.redaction_profile_id
    ):
        return "INTERNAL_ERROR"
    if request.endpoint_id != command.endpoint_id:
        return "LLM_ENDPOINT_MISMATCH"
    return None
