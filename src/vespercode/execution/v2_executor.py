"""Route B / B4a + B4b-02A: the v2 execution service and the
deterministic fakes.

The service is one deterministic boundary over four injectable
pieces: the bound execution profile record (``execution/v2_profile``),
the injectable read-only control-plane binding lookup
(``V2ExecutionBindingPort`` — the B1 run/candidate/revision identity
and the cited terminal-PASSED validation the request must match), an
injectable readiness port, and an injectable execution port.  The
call order is fixed and fail-closed:

1. the request must be an ``ExecutionActionRequestV2`` — a shell or
   command string rejects before anything is touched;
2. the request's execution profile id/revision and reference profile
   id/revision must match the bound profile exactly (early
   diagnostics; a stale revision is the same revision discipline
   Route A/B1/B2 use), rejecting before the binding lookup is even
   consulted;
3. the production service STRUCTURALLY requires the request to cite a
   validation run: an uncited request rejects with the closed
   ``VALIDATION_BINDING_REQUIRED`` code BEFORE the binding port is
   consulted — the citation requirement is the service's own gate,
   so no binding-port choice (fake or real) can bypass it;
4. the binding port must resolve the whole cited binding — the cited
   (run, candidate) pair at the candidate's CURRENT revision, plus
   the cited validation as the terminal PASSED validation of that
   current revision under the request's own reference profile — and
   the service re-verifies every field of the returned facts,
   rejecting with a closed code BEFORE the readiness port is
   consulted;
5. the readiness port must answer READY, rejecting before the
   executor is touched;
6. execution is exactly one port call — no automatic retry; any
   executor exception or hostile return maps to the closed
   ``EXECUTION_FAILED`` outcome with a static message, so raw
   exception text can never reach an outcome;
7. the executor report maps to a sanitized ``ExecutionOutcomeV2``:
   closed status, closed error code, static message, bounded exit
   code, and an output excerpt capped at 2048 characters and stripped
   of control characters.

``FakeV2BindingLookup``, ``FakeV2Executor``, and ``FakeV2Readiness``
are the deterministic fakes the offline tests use.  ``V2ExecutionTestService``
is the explicitly TEST-ONLY subclass of the production service: it
relaxes exactly the step-3 citation gate so the offline fakes can
exercise the service's ordering and sanitization without a control
plane.  It is non-production by contract — the class name says test,
its docstring forbids production use, and every production execution
must go through ``V2ExecutionService`` (or the production
database-backed binding, B4b-02A,
``execution/v2_database_binding.py``, which additionally answers an
uncited lookup with the closed ``VALIDATION_REQUIRED`` kind — defense
in depth).
"""

from __future__ import annotations

from vespercode.execution.v2_execution import (
    EXECUTION_MESSAGES_V2,
    EXECUTION_OUTCOME_EXCERPT_MAX_CHARS_V2,
    ExecutionActionRequestV2,
    ExecutionBindingFactsV2,
    ExecutionBindingOutcomeV2,
    ExecutionOutcomeV2,
    ExecutionReadinessResultV2,
    ExecutionResultV2,
    ValidationBindingFactsV2,
)
from vespercode.execution.v2_profile import ExecutionProfileRecordV2

FAKE_EXECUTION_OUTPUT_V2 = "fake execution output"
"""The fixed output of the deterministic fake execution port."""


def _sanitize_output(output: object) -> str:
    """Bound and strip an executor output into an outcome excerpt.

    Every control character except newline and tab is removed, and
    the result is capped at the closed excerpt bound, so even a
    misbehaving executor cannot push an oversized or control-bearing
    string through the outcome (the outcome record re-verifies both
    invariants at construction).
    """
    if not isinstance(output, str):
        return ""
    kept: list[str] = []
    for character in output:
        code = ord(character)
        if character in "\n\t" or (code >= 0x20 and not 0x7F <= code <= 0x9F):
            kept.append(character)
        if len(kept) >= EXECUTION_OUTCOME_EXCERPT_MAX_CHARS_V2:
            break
    return "".join(kept)


class V2ExecutionService:
    """The one-call execution boundary over the bound profile.

    ``profile`` is the bound ``ExecutionProfileRecordV2`` (the request
    must cite exactly its ids and revisions); ``binding`` implements
    the read-only ``V2ExecutionBindingPort`` (the request's run/
    candidate/revision must resolve to the candidate's CURRENT
    revision); ``readiness`` implements ``V2ReadinessPort``;
    ``executor`` implements ``V2ExecutionPort``.

    The production service STRUCTURALLY requires every request to
    cite a validation run: an uncited request rejects with the closed
    ``VALIDATION_BINDING_REQUIRED`` code before the binding port is
    consulted, so the requirement does not depend on which binding
    port a caller injects — a production service constructed over a
    permissive port still cannot execute an uncited request.  Only
    the explicitly test-only ``V2ExecutionTestService`` subclass
    relaxes this one gate (for the offline fakes, never production).
    """

    _REQUIRES_VALIDATION_CITATION: bool = True

    def __init__(
        self,
        profile: object,
        binding: object,
        readiness: object,
        executor: object,
    ) -> None:
        if not isinstance(profile, ExecutionProfileRecordV2):
            raise ValueError(
                "the execution service requires an ExecutionProfileRecordV2"
            )
        if binding is None or readiness is None or executor is None:
            raise ValueError(
                "the execution service requires a control-plane binding "
                "lookup, a readiness port, and an execution port"
            )
        self._profile = profile
        self._binding = binding
        self._readiness = readiness
        self._executor = executor

    @property
    def profile(self) -> ExecutionProfileRecordV2:
        return self._profile

    def execute(self, request: object) -> ExecutionOutcomeV2:
        """Run exactly one authorized execution request, sanitized."""
        if not isinstance(request, ExecutionActionRequestV2):
            raise ValueError(
                "request must be an ExecutionActionRequestV2; a shell "
                "command string is never accepted"
            )
        if (
            request.execution_profile_id != self._profile.execution_profile_id
            or request.execution_profile_revision
            != self._profile.execution_profile_revision
        ):
            return self._rejected(request, "PROFILE_BINDING_MISMATCH")
        if (
            request.reference_profile_id != self._profile.reference_profile_id
            or request.reference_profile_revision
            != self._profile.reference_profile_revision
        ):
            return self._rejected(request, "PROFILE_BINDING_MISMATCH")
        # The structural citation gate: the production service
        # requires every request to cite a validation run.  This is
        # the service's OWN gate — it runs before the binding port is
        # consulted, so no binding-port choice (fake or real) can
        # bypass the validation requirement; an uncited request can
        # never reach readiness or the executor here.  Only the
        # explicitly test-only subclass relaxes it.
        if (
            self._REQUIRES_VALIDATION_CITATION
            and request.validation_run_id is None
        ):
            return self._rejected(request, "VALIDATION_BINDING_REQUIRED")
        # The B1 control-plane binding: the cited (run, candidate) pair
        # must resolve together at the candidate's CURRENT revision,
        # and a cited validation run must resolve as the terminal
        # PASSED validation of that current revision under the
        # request's own reference profile.  The port is read-only and
        # returns one closed outcome; the service re-verifies every
        # field of the returned facts, so a hostile or drifted port
        # cannot authorize a foreign, stale, or unvalidated binding.
        # Every binding rejection lands BEFORE the readiness port is
        # consulted, with zero executor calls.
        binding = self._binding.lookup_execution_binding(
            request.run_id,
            request.candidate_id,
            request.validation_run_id,
            request.reference_profile_id,
            request.reference_profile_revision,
        )
        if not isinstance(binding, ExecutionBindingOutcomeV2):
            raise ValueError(
                "the binding port must return an ExecutionBindingOutcomeV2"
            )
        if binding.kind == "BINDING_NOT_FOUND":
            return self._rejected(request, "EXECUTION_BINDING_NOT_FOUND")
        if binding.kind == "VALIDATION_REQUIRED":
            return self._rejected(request, "VALIDATION_BINDING_REQUIRED")
        if binding.kind == "VALIDATION_NOT_FOUND":
            return self._rejected(request, "VALIDATION_BINDING_NOT_FOUND")
        if binding.kind == "VALIDATION_NOT_PASSED":
            return self._rejected(request, "VALIDATION_BINDING_NOT_PASSED")
        facts = binding.facts
        if not isinstance(facts, ExecutionBindingFactsV2):
            raise ValueError(
                "a RESOLVED binding outcome must carry "
                "ExecutionBindingFactsV2"
            )
        if (
            facts.run_id != request.run_id
            or facts.candidate_id != request.candidate_id
        ):
            return self._rejected(request, "EXECUTION_BINDING_NOT_FOUND")
        if facts.candidate_revision != request.candidate_revision:
            return self._rejected(request, "EXECUTION_BINDING_STALE")
        if request.validation_run_id is None:
            # Reachable ONLY through the explicitly test-only subclass
            # (the production service rejected the uncited request
            # before the binding lookup): a port that invents
            # validation facts for a request that cites none still
            # cannot bypass the citation requirement.
            if facts.validation is not None:
                return self._rejected(request, "VALIDATION_BINDING_REQUIRED")
        else:
            validation = facts.validation
            if validation is None:
                return self._rejected(
                    request, "VALIDATION_BINDING_NOT_FOUND"
                )
            if (
                validation.validation_run_id != request.validation_run_id
                or validation.run_id != request.run_id
                or validation.candidate_id != request.candidate_id
                or validation.candidate_revision
                != request.candidate_revision
                or validation.reference_profile_id
                != request.reference_profile_id
                or validation.reference_profile_revision
                != request.reference_profile_revision
            ):
                return self._rejected(
                    request, "VALIDATION_BINDING_NOT_FOUND"
                )
            if validation.status != "PASSED":
                return self._rejected(
                    request, "VALIDATION_BINDING_NOT_PASSED"
                )
        readiness = self._readiness.check(self._profile)
        if not isinstance(readiness, ExecutionReadinessResultV2):
            raise ValueError(
                "the readiness port must return an ExecutionReadinessResultV2"
            )
        if readiness.status != "READY":
            return self._rejected(
                request, f"READINESS_{readiness.reason}"
            )
        try:
            result = self._executor.run(request, self._profile)
        except Exception:
            # The raw executor exception is discarded: it may carry raw
            # command output or environment details and must never
            # reach the outcome.  No retry is attempted.
            return self._rejected(request, "EXECUTION_FAILED")
        if not isinstance(result, ExecutionResultV2):
            return self._rejected(request, "EXECUTION_FAILED")
        if result.status == "TIMED_OUT":
            return ExecutionOutcomeV2(
                request_id=request.request_id,
                status="FAILED",
                error_code="TIMED_OUT",
                message=EXECUTION_MESSAGES_V2["TIMED_OUT"],
                exit_code=None,
                output_excerpt=_sanitize_output(result.output),
            )
        if result.status == "FAILED":
            return ExecutionOutcomeV2(
                request_id=request.request_id,
                status="FAILED",
                error_code="EXECUTION_FAILED",
                message=EXECUTION_MESSAGES_V2["EXECUTION_FAILED"],
                exit_code=result.exit_code,
                output_excerpt=_sanitize_output(result.output),
            )
        return ExecutionOutcomeV2(
            request_id=request.request_id,
            status="SUCCEEDED",
            error_code=None,
            message=EXECUTION_MESSAGES_V2["SUCCEEDED"],
            exit_code=result.exit_code,
            output_excerpt=_sanitize_output(result.output),
        )

    def _rejected(
        self, request: ExecutionActionRequestV2, error_code: str
    ) -> ExecutionOutcomeV2:
        return ExecutionOutcomeV2(
            request_id=request.request_id,
            status="FAILED",
            error_code=error_code,
            message=EXECUTION_MESSAGES_V2[error_code],
            exit_code=None,
            output_excerpt="",
        )


class V2ExecutionTestService(V2ExecutionService):
    """The explicitly TEST-ONLY service subclass (the isolated seam).

    This subclass relaxes exactly ONE gate of the production service:
    it does not require the request to cite a validation run, so the
    deterministic offline fakes (``FakeV2BindingLookup`` resolving an
    uncited request) can exercise the service's fixed call order,
    facts re-verification, and outcome sanitization without a control
    plane.  It exists ONLY for the offline test suite: it is
    non-production by contract, its name says test, and no harness,
    CLI, WebUI, or other production code may construct it — every
    production execution goes through ``V2ExecutionService`` and its
    structural citation gate.  Even here, a binding port that answers
    ``VALIDATION_REQUIRED``, or one that invents validation facts for
    an uncited request, still rejects closed; only a port that
    resolves the uncited request proceeds.
    """

    _REQUIRES_VALIDATION_CITATION: bool = False


class FakeV2BindingLookup:
    """The deterministic injectable binding lookup (the offline fake).

    Records every ``(run_id, candidate_id, validation_run_id,
    reference_profile_id, reference_profile_revision)`` tuple it is
    asked about and answers with a closed outcome: by default the
    lookup keys echo back at ``current_revision`` (default 3) with a
    ``PASSED`` validation for a cited request and no validation facts
    for an uncited one, so a request citing the current revision is
    accepted and a stale or foreign one rejects through the service's
    own comparisons.  The uncited resolution exists ONLY for
    ``V2ExecutionTestService`` (the test-only service subclass): the
    production ``V2ExecutionService`` rejects an uncited request
    before this port is ever consulted.  ``unresolved=True`` answers
    ``BINDING_NOT_FOUND`` for every lookup; ``facts=...`` replaces
    the echoed facts with one fixed record, so a hostile or drifted
    port can be scripted; ``current_revision`` scripts the candidate's
    current revision for stale-binding tests;
    ``validation_required=True`` answers ``VALIDATION_REQUIRED`` for
    an uncited lookup (the production adapter's shape);
    ``validation_unresolved=True`` answers ``VALIDATION_NOT_FOUND``
    for a cited request; and ``validation_status`` scripts the echoed
    validation's status.  No real control plane is touched.
    """

    def __init__(
        self,
        *,
        current_revision: int = 3,
        unresolved: bool = False,
        facts: ExecutionBindingFactsV2 | None = None,
        validation_required: bool = False,
        validation_unresolved: bool = False,
        validation_status: str = "PASSED",
    ) -> None:
        self._current_revision = current_revision
        self._unresolved = unresolved
        self._facts = facts
        self._validation_required = validation_required
        self._validation_unresolved = validation_unresolved
        self._validation_status = validation_status
        self.lookups: list[
            tuple[str, str, str | None, str, int]
        ] = []

    def lookup_execution_binding(
        self,
        run_id: str,
        candidate_id: str,
        validation_run_id: str | None,
        reference_profile_id: str,
        reference_profile_revision: int,
    ) -> ExecutionBindingOutcomeV2:
        keys = (
            run_id,
            candidate_id,
            validation_run_id,
            reference_profile_id,
            reference_profile_revision,
        )
        self.lookups.append(keys)
        if self._unresolved:
            return ExecutionBindingOutcomeV2("BINDING_NOT_FOUND")
        facts = (
            self._facts
            if self._facts is not None
            else ExecutionBindingFactsV2(
                run_id=run_id,
                candidate_id=candidate_id,
                candidate_revision=self._current_revision,
            )
        )
        if validation_run_id is None:
            if self._validation_required:
                return ExecutionBindingOutcomeV2("VALIDATION_REQUIRED")
            return ExecutionBindingOutcomeV2("RESOLVED", facts)
        if self._validation_unresolved:
            return ExecutionBindingOutcomeV2("VALIDATION_NOT_FOUND")
        if self._facts is None:
            facts = ExecutionBindingFactsV2(
                run_id=run_id,
                candidate_id=candidate_id,
                candidate_revision=self._current_revision,
                validation=ValidationBindingFactsV2(
                    validation_run_id=validation_run_id,
                    run_id=run_id,
                    candidate_id=candidate_id,
                    candidate_revision=self._current_revision,
                    reference_profile_id=reference_profile_id,
                    reference_profile_revision=reference_profile_revision,
                    status=self._validation_status,
                ),
            )
        return ExecutionBindingOutcomeV2("RESOLVED", facts)


class FakeV2Executor:
    """The deterministic injectable execution port (the B4a offline fake).

    Records every ``(request, profile)`` pair it receives and returns
    the scripted result, raises the scripted error, or — by default —
    reports a fixed successful execution.  No real container is ever
    touched.
    """

    def __init__(
        self,
        result: ExecutionResultV2 | None = None,
        error: Exception | None = None,
    ) -> None:
        self._result = result
        self._error = error
        self.calls: list[
            tuple[ExecutionActionRequestV2, ExecutionProfileRecordV2]
        ] = []

    def run(
        self, request: ExecutionActionRequestV2, profile: ExecutionProfileRecordV2
    ) -> ExecutionResultV2:
        self.calls.append((request, profile))
        if self._error is not None:
            raise self._error
        if self._result is not None:
            return self._result
        return ExecutionResultV2(
            status="SUCCEEDED", exit_code=0, output=FAKE_EXECUTION_OUTPUT_V2
        )


class FakeV2Readiness:
    """The deterministic injectable readiness port (the B4a offline fake).

    Records every profile it is asked about and returns the scripted
    verdict, defaulting to READY.
    """

    def __init__(self, result: ExecutionReadinessResultV2 | None = None) -> None:
        self._result = (
            result if result is not None else ExecutionReadinessResultV2("READY")
        )
        self.checks: list[ExecutionProfileRecordV2] = []

    def check(
        self, profile: ExecutionProfileRecordV2
    ) -> ExecutionReadinessResultV2:
        self.checks.append(profile)
        return self._result


__all__ = (
    "FAKE_EXECUTION_OUTPUT_V2",
    "FakeV2BindingLookup",
    "FakeV2Executor",
    "FakeV2Readiness",
    "V2ExecutionService",
    "V2ExecutionTestService",
)
