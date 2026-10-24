"""Route B / B4a: the v2 execution service over the injectable ports.

The service is one deterministic boundary over four injectable pieces:
the bound execution profile record, the injectable control-plane
binding lookup (the run/candidate the request targets — the B1
identity plane — plus the terminal-PASSED validation the B4b-02A
production binding requires), an injectable readiness port, and an
injectable execution port.  Binding mismatches (execution profile
id/revision or reference profile id/revision) reject before the binding
lookup; the production ``V2ExecutionService`` STRUCTURALLY requires
the request to cite a validation run — an uncited request rejects with
the closed ``VALIDATION_BINDING_REQUIRED`` code before the binding
port is even consulted, so no binding-port choice (fake or real) can
bypass the validation requirement; an unknown run/candidate pair, a
foreign binding, a stale candidate revision, or an unresolvable,
stale, or non-PASSED cited validation rejects BEFORE the readiness
port is consulted and with zero executor calls; a NOT_READY verdict
rejects before the executor is touched; execution is exactly one port
call with no retry; any executor exception or hostile return maps to
the closed ``EXECUTION_FAILED`` outcome with a static message, so raw
command output, exception text, or secrets can never reach an outcome.

Outcomes are closed, bounded, sanitized shapes.  ``FakeV2Executor``,
``FakeV2Readiness``, and ``FakeV2BindingLookup`` are the deterministic
fakes the offline tests use; the production database-backed binding
(``DatabaseBackedExecutionBinding``) has its own dedicated suite in
``test_v2_database_binding.py``.  ``V2ExecutionTestService`` is the
explicitly TEST-ONLY subclass — non-production, named for grep —
under which the offline fakes may exercise the service's ordering
and sanitization with an uncited request; every other test in this
suite drives the production ``V2ExecutionService``.  No real Docker
execution exists in this suite.
"""

from __future__ import annotations

import unittest

from vespercode.execution.v2_execution import (
    EXECUTION_MESSAGES_V2,
    EXECUTION_OUTCOME_ERROR_CODES_V2,
    EXECUTION_OUTCOME_EXCERPT_MAX_CHARS_V2,
    ExecutionActionRequestV2,
    ExecutionBindingFactsV2,
    ExecutionBindingOutcomeV2,
    ExecutionOutcomeV2,
    ExecutionResultV2,
    ExecutionReadinessResultV2,
    ValidationBindingFactsV2,
)
from vespercode.execution.v2_executor import (
    FAKE_EXECUTION_OUTPUT_V2,
    FakeV2BindingLookup,
    FakeV2Executor,
    FakeV2Readiness,
    V2ExecutionService,
    V2ExecutionTestService,
)
from vespercode.execution.v2_profile import (
    EXECUTION_MAX_OUTPUT_BYTES_V2,
    ExecutionProfileRecordV2,
)

_SECRET = "registry-token-sk-0001"


def _profile() -> ExecutionProfileRecordV2:
    return ExecutionProfileRecordV2(
        execution_profile_id="exec-profile-1",
        execution_profile_revision=4,
        reference_profile_id="reference-1",
        reference_profile_revision=3,
        image_reference="vespercode-validation-image",
        network_disabled=True,
        non_root_user="10001:10001",
        read_only_rootfs=True,
        all_capabilities_dropped=True,
        docker_socket_mounted=False,
        workspace_mount_read_only=True,
        timeout_seconds=120,
        max_output_bytes=EXECUTION_MAX_OUTPUT_BYTES_V2,
    )


class _BadExecutor:
    """A hostile executor that returns garbage instead of a result."""

    def run(self, request: object, profile: object) -> object:
        return "not a result"


class _BrokenBindingPort:
    """A hostile binding port that returns garbage instead of an outcome."""

    def lookup_execution_binding(self, *args: object) -> object:
        return "not an outcome"


class V2ExecutionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = _profile()
        self.binding = FakeV2BindingLookup()
        self.readiness = FakeV2Readiness()
        self.executor = FakeV2Executor()
        self.service = V2ExecutionService(
            self.profile, self.binding, self.readiness, self.executor
        )

    def _request(self, **overrides: object) -> ExecutionActionRequestV2:
        values: dict[str, object] = {
            "request_id": "exec-request-1",
            "execution_profile_id": "exec-profile-1",
            "execution_profile_revision": 4,
            "reference_profile_id": "reference-1",
            "reference_profile_revision": 3,
            "run_id": "run-1",
            "candidate_id": "cand-0001",
            "candidate_revision": 3,
            "action_kind": "VALIDATE_CANDIDATE",
            "argv": ("vespercode-validate", "cand-0001", "3"),
            "validation_run_id": "valid-0001",
        }
        values.update(overrides)
        return ExecutionActionRequestV2(**values)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_a_ready_request_executes_once_and_succeeds(self) -> None:
        outcome = self.service.execute(self._request())
        self.assertEqual(outcome.request_id, "exec-request-1")
        self.assertEqual(outcome.status, "SUCCEEDED")
        self.assertIsNone(outcome.error_code)
        self.assertEqual(outcome.message, EXECUTION_MESSAGES_V2["SUCCEEDED"])
        self.assertEqual(outcome.exit_code, 0)
        self.assertEqual(outcome.output_excerpt, FAKE_EXECUTION_OUTPUT_V2)
        self.assertEqual(len(self.executor.calls), 1)
        self.assertEqual(len(self.readiness.checks), 1)
        self.assertEqual(
            self.binding.lookups,
            [("run-1", "cand-0001", "valid-0001", "reference-1", 3)],
        )

    def test_the_fake_executor_receives_the_exact_request_and_profile(
        self,
    ) -> None:
        request = self._request()
        self.service.execute(request)
        seen_request, seen_profile = self.executor.calls[0]
        self.assertIs(seen_request, request)
        self.assertIs(seen_profile, self.profile)
        self.assertEqual(self.readiness.checks[0], self.profile)
        # The binding lookup received the request's own five binding
        # keys plus the validation citation.
        self.assertEqual(
            self.binding.lookups,
            [("run-1", "cand-0001", "valid-0001", "reference-1", 3)],
        )

    # ------------------------------------------------------------------
    # Binding checks before readiness and execution
    # ------------------------------------------------------------------

    def test_a_stale_execution_profile_revision_rejects_before_the_binding_lookup(
        self,
    ) -> None:
        outcome = self.service.execute(self._request(execution_profile_revision=5))
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "PROFILE_BINDING_MISMATCH")
        self.assertEqual(
            outcome.message,
            EXECUTION_MESSAGES_V2["PROFILE_BINDING_MISMATCH"],
        )
        self.assertIsNone(outcome.exit_code)
        self.assertEqual(outcome.output_excerpt, "")
        self.assertEqual(self.binding.lookups, [])
        self.assertEqual(self.readiness.checks, [])
        self.assertEqual(self.executor.calls, [])

    def test_a_wrong_execution_profile_id_rejects_before_the_binding_lookup(
        self,
    ) -> None:
        outcome = self.service.execute(
            self._request(execution_profile_id="exec-profile-9")
        )
        self.assertEqual(outcome.error_code, "PROFILE_BINDING_MISMATCH")
        self.assertEqual(self.binding.lookups, [])
        self.assertEqual(self.readiness.checks, [])
        self.assertEqual(self.executor.calls, [])

    def test_a_reference_profile_binding_mismatch_rejects_before_execution(
        self,
    ) -> None:
        stale = self.service.execute(self._request(reference_profile_revision=2))
        self.assertEqual(stale.error_code, "PROFILE_BINDING_MISMATCH")
        foreign = self.service.execute(
            self._request(reference_profile_id="reference-9")
        )
        self.assertEqual(foreign.error_code, "PROFILE_BINDING_MISMATCH")
        self.assertEqual(self.executor.calls, [])

    # ------------------------------------------------------------------
    # Control-plane binding: the B1 run/candidate/revision gate
    # ------------------------------------------------------------------

    def test_an_unknown_run_candidate_binding_rejects_before_readiness(
        self,
    ) -> None:
        binding = FakeV2BindingLookup(unresolved=True)
        readiness = FakeV2Readiness()
        executor = FakeV2Executor()
        service = V2ExecutionService(self.profile, binding, readiness, executor)
        outcome = service.execute(self._request())
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "EXECUTION_BINDING_NOT_FOUND")
        self.assertEqual(
            outcome.message,
            EXECUTION_MESSAGES_V2["EXECUTION_BINDING_NOT_FOUND"],
        )
        self.assertIsNone(outcome.exit_code)
        self.assertEqual(outcome.output_excerpt, "")
        self.assertEqual(
            binding.lookups,
            [("run-1", "cand-0001", "valid-0001", "reference-1", 3)],
        )
        self.assertEqual(readiness.checks, [])
        self.assertEqual(executor.calls, [])

    def test_a_foreign_binding_rejects_before_readiness(self) -> None:
        binding = FakeV2BindingLookup(
            facts=ExecutionBindingFactsV2("run-9", "cand-0009", 3)
        )
        readiness = FakeV2Readiness()
        executor = FakeV2Executor()
        service = V2ExecutionService(self.profile, binding, readiness, executor)
        outcome = service.execute(self._request())
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "EXECUTION_BINDING_NOT_FOUND")
        self.assertEqual(
            binding.lookups,
            [("run-1", "cand-0001", "valid-0001", "reference-1", 3)],
        )
        self.assertEqual(readiness.checks, [])
        self.assertEqual(executor.calls, [])

    def test_a_stale_candidate_revision_rejects_before_readiness(self) -> None:
        binding = FakeV2BindingLookup(current_revision=4)
        readiness = FakeV2Readiness()
        executor = FakeV2Executor()
        service = V2ExecutionService(self.profile, binding, readiness, executor)
        outcome = service.execute(self._request())
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "EXECUTION_BINDING_STALE")
        self.assertEqual(
            outcome.message,
            EXECUTION_MESSAGES_V2["EXECUTION_BINDING_STALE"],
        )
        self.assertIsNone(outcome.exit_code)
        self.assertEqual(outcome.output_excerpt, "")
        self.assertEqual(
            binding.lookups,
            [("run-1", "cand-0001", "valid-0001", "reference-1", 3)],
        )
        self.assertEqual(readiness.checks, [])
        self.assertEqual(executor.calls, [])
        # A request citing the current revision is accepted.
        current = service.execute(
            self._request(
                candidate_revision=4,
                argv=("vespercode-validate", "cand-0001", "4"),
            )
        )
        self.assertEqual(current.status, "SUCCEEDED")
        self.assertEqual(len(executor.calls), 1)

    def test_a_broken_binding_port_rejects_loudly(self) -> None:
        service = V2ExecutionService(
            self.profile, _BrokenBindingPort(), self.readiness, self.executor
        )
        with self.assertRaises(ValueError):
            service.execute(self._request())
        self.assertEqual(self.readiness.checks, [])
        self.assertEqual(self.executor.calls, [])

    # ------------------------------------------------------------------
    # The validation gate (B4b-02A contract over the same port)
    # ------------------------------------------------------------------

    def test_an_uncited_request_rejects_before_the_binding_lookup(
        self,
    ) -> None:
        # The production service structurally requires the citation:
        # an uncited request cannot reach readiness or the executor —
        # and the binding port is never even consulted, so no
        # binding-port choice (fake or real) can bypass the
        # validation requirement.
        binding = FakeV2BindingLookup()
        readiness = FakeV2Readiness()
        executor = FakeV2Executor()
        service = V2ExecutionService(self.profile, binding, readiness, executor)
        outcome = service.execute(self._request(validation_run_id=None))
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "VALIDATION_BINDING_REQUIRED")
        self.assertEqual(
            outcome.message,
            EXECUTION_MESSAGES_V2["VALIDATION_BINDING_REQUIRED"],
        )
        self.assertIsNone(outcome.exit_code)
        self.assertEqual(outcome.output_excerpt, "")
        self.assertEqual(binding.lookups, [])
        self.assertEqual(readiness.checks, [])
        self.assertEqual(executor.calls, [])
        # A matching cited PASSED binding executes exactly once.
        accepted = service.execute(self._request())
        self.assertEqual(accepted.status, "SUCCEEDED")
        self.assertIsNone(accepted.error_code)
        self.assertEqual(len(readiness.checks), 1)
        self.assertEqual(len(executor.calls), 1)
        self.assertEqual(
            binding.lookups,
            [("run-1", "cand-0001", "valid-0001", "reference-1", 3)],
        )

    def test_an_uncited_request_executes_only_through_the_test_service(
        self,
    ) -> None:
        # The ISOLATED B4a seam, explicitly test-only: only
        # V2ExecutionTestService — the test-only subclass documented as
        # non-production — executes an uncited request, and only
        # through the deterministic offline fake.  The production
        # V2ExecutionService rejects the same request before the
        # binding port is even consulted.
        binding = FakeV2BindingLookup()
        readiness = FakeV2Readiness()
        executor = FakeV2Executor()
        service = V2ExecutionTestService(self.profile, binding, readiness, executor)
        outcome = service.execute(self._request(validation_run_id=None))
        self.assertEqual(outcome.status, "SUCCEEDED")
        self.assertEqual(len(executor.calls), 1)
        self.assertEqual(
            binding.lookups,
            [("run-1", "cand-0001", None, "reference-1", 3)],
        )

    def test_the_test_service_is_an_explicitly_named_subclass(self) -> None:
        # The relaxation of the citation requirement lives ONLY on
        # the class whose name says test; the production service and
        # the test subclass are the only two spellings of the seam.
        self.assertTrue(issubclass(V2ExecutionTestService, V2ExecutionService))
        production = V2ExecutionService(
            self.profile, self.binding, self.readiness, self.executor
        )
        self.assertIsInstance(production, V2ExecutionService)
        self.assertNotIsInstance(production, V2ExecutionTestService)

    def test_a_citation_requiring_binding_rejects_through_the_test_service(
        self,
    ) -> None:
        # Through the test-only subclass, the PORT-level citation
        # requirement is still exercised: a binding that answers
        # VALIDATION_REQUIRED for an uncited lookup rejects with the
        # same closed code, before readiness and the executor.
        binding = FakeV2BindingLookup(validation_required=True)
        readiness = FakeV2Readiness()
        executor = FakeV2Executor()
        service = V2ExecutionTestService(self.profile, binding, readiness, executor)
        outcome = service.execute(self._request(validation_run_id=None))
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "VALIDATION_BINDING_REQUIRED")
        self.assertEqual(
            outcome.message,
            EXECUTION_MESSAGES_V2["VALIDATION_BINDING_REQUIRED"],
        )
        self.assertEqual(
            binding.lookups,
            [("run-1", "cand-0001", None, "reference-1", 3)],
        )
        self.assertEqual(readiness.checks, [])
        self.assertEqual(executor.calls, [])

    def test_an_unresolvable_cited_validation_rejects_before_readiness(
        self,
    ) -> None:
        binding = FakeV2BindingLookup(validation_unresolved=True)
        readiness = FakeV2Readiness()
        executor = FakeV2Executor()
        service = V2ExecutionService(self.profile, binding, readiness, executor)
        outcome = self.execute_rejecting(service)
        self.assertEqual(outcome.error_code, "VALIDATION_BINDING_NOT_FOUND")
        self.assertEqual(
            outcome.message,
            EXECUTION_MESSAGES_V2["VALIDATION_BINDING_NOT_FOUND"],
        )
        self.assertEqual(readiness.checks, [])
        self.assertEqual(executor.calls, [])

    def test_a_non_passed_cited_validation_rejects_before_readiness(
        self,
    ) -> None:
        for status in ("PENDING", "FAILED"):
            with self.subTest(status=status):
                binding = FakeV2BindingLookup(validation_status=status)
                readiness = FakeV2Readiness()
                executor = FakeV2Executor()
                service = V2ExecutionService(self.profile, binding, readiness, executor)
                outcome = self.execute_rejecting(service)
                self.assertEqual(outcome.error_code, "VALIDATION_BINDING_NOT_PASSED")
                self.assertEqual(
                    outcome.message,
                    EXECUTION_MESSAGES_V2["VALIDATION_BINDING_NOT_PASSED"],
                )
                self.assertEqual(readiness.checks, [])
                self.assertEqual(executor.calls, [])

    def test_a_drifted_validation_binding_rejects_before_readiness(
        self,
    ) -> None:
        # A hostile port returns RESOLVED facts whose validation is
        # re-bound to another run: the service re-verifies every field
        # and rejects closed.
        drifts = (
            ValidationBindingFactsV2(
                "valid-0001",
                "run-9",
                "cand-0001",
                3,
                "reference-1",
                3,
                "PASSED",
            ),
            ValidationBindingFactsV2(
                "valid-0001",
                "run-1",
                "cand-0009",
                3,
                "reference-1",
                3,
                "PASSED",
            ),
            ValidationBindingFactsV2(
                "valid-0001",
                "run-1",
                "cand-0001",
                2,
                "reference-1",
                3,
                "PASSED",
            ),
            ValidationBindingFactsV2(
                "valid-0001",
                "run-1",
                "cand-0001",
                3,
                "reference-9",
                3,
                "PASSED",
            ),
            ValidationBindingFactsV2(
                "valid-0001",
                "run-1",
                "cand-0001",
                3,
                "reference-1",
                2,
                "PASSED",
            ),
            ValidationBindingFactsV2(
                "valid-0009",
                "run-1",
                "cand-0001",
                3,
                "reference-1",
                3,
                "PASSED",
            ),
        )
        for validation in drifts:
            with self.subTest(validation=validation):
                binding = FakeV2BindingLookup(
                    facts=ExecutionBindingFactsV2("run-1", "cand-0001", 3, validation)
                )
                readiness = FakeV2Readiness()
                executor = FakeV2Executor()
                service = V2ExecutionService(self.profile, binding, readiness, executor)
                outcome = self.execute_rejecting(service)
                self.assertEqual(outcome.error_code, "VALIDATION_BINDING_NOT_FOUND")
                self.assertEqual(readiness.checks, [])
                self.assertEqual(executor.calls, [])

    def test_a_port_inventing_validation_facts_cannot_bypass_the_citation_requirement(
        self,
    ) -> None:
        # Through the test-only subclass, a port that returns RESOLVED
        # facts WITH validation facts for a request that cites none
        # still cannot bypass the citation requirement.
        binding = FakeV2BindingLookup(
            facts=ExecutionBindingFactsV2(
                "run-1",
                "cand-0001",
                3,
                ValidationBindingFactsV2(
                    "valid-0001",
                    "run-1",
                    "cand-0001",
                    3,
                    "reference-1",
                    3,
                    "PASSED",
                ),
            )
        )
        readiness = FakeV2Readiness()
        executor = FakeV2Executor()
        service = V2ExecutionTestService(self.profile, binding, readiness, executor)
        outcome = service.execute(self._request(validation_run_id=None))
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "VALIDATION_BINDING_REQUIRED")
        self.assertEqual(readiness.checks, [])
        self.assertEqual(executor.calls, [])

    def execute_rejecting(self, service: V2ExecutionService) -> ExecutionOutcomeV2:
        outcome = service.execute(self._request())
        self.assertEqual(outcome.status, "FAILED")
        return outcome

    # ------------------------------------------------------------------
    # Readiness gate
    # ------------------------------------------------------------------

    def test_a_not_ready_profile_rejects_before_execution(self) -> None:
        for reason in (
            "IMAGE_NOT_AVAILABLE",
            "DAEMON_UNAVAILABLE",
            "PROFILE_REVISION_UNKNOWN",
        ):
            with self.subTest(reason=reason):
                binding = FakeV2BindingLookup()
                readiness = FakeV2Readiness(
                    ExecutionReadinessResultV2("NOT_READY", reason)
                )
                executor = FakeV2Executor()
                service = V2ExecutionService(self.profile, binding, readiness, executor)
                outcome = service.execute(self._request())
                self.assertEqual(outcome.status, "FAILED")
                self.assertEqual(outcome.error_code, f"READINESS_{reason}")
                self.assertEqual(
                    outcome.message,
                    EXECUTION_MESSAGES_V2[f"READINESS_{reason}"],
                )
                self.assertIsNone(outcome.exit_code)
                self.assertEqual(outcome.output_excerpt, "")
                self.assertEqual(executor.calls, [])
                self.assertEqual(readiness.checks, [self.profile])
                # The binding was consulted exactly once, before readiness.
                self.assertEqual(
                    binding.lookups,
                    [("run-1", "cand-0001", "valid-0001", "reference-1", 3)],
                )

    # ------------------------------------------------------------------
    # Executor failures: one call, no retry, sanitized outcomes
    # ------------------------------------------------------------------

    def test_an_executor_exception_is_sanitized(self) -> None:
        executor = FakeV2Executor(
            error=RuntimeError(f"docker: unauthorized, {_SECRET}")
        )
        service = V2ExecutionService(
            self.profile, self.binding, self.readiness, executor
        )
        outcome = service.execute(self._request())
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "EXECUTION_FAILED")
        self.assertEqual(outcome.message, EXECUTION_MESSAGES_V2["EXECUTION_FAILED"])
        self.assertNotIn(_SECRET, outcome.message)
        self.assertNotIn(_SECRET, outcome.output_excerpt)
        self.assertNotIn(_SECRET, repr(outcome))
        self.assertNotIn(_SECRET, str(outcome))
        self.assertEqual(outcome.output_excerpt, "")
        # Exactly one call: no automatic retry on executor error.
        self.assertEqual(len(executor.calls), 1)

    def test_an_executor_failure_status_maps_to_execution_failed(self) -> None:
        executor = FakeV2Executor(
            ExecutionResultV2("FAILED", 2, "2 checks failed: test_a, test_b")
        )
        service = V2ExecutionService(
            self.profile, self.binding, self.readiness, executor
        )
        outcome = service.execute(self._request())
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "EXECUTION_FAILED")
        self.assertEqual(outcome.exit_code, 2)
        self.assertEqual(outcome.output_excerpt, "2 checks failed: test_a, test_b")

    def test_a_timed_out_execution_maps_to_the_closed_code(self) -> None:
        executor = FakeV2Executor(
            ExecutionResultV2("TIMED_OUT", None, "partial output")
        )
        service = V2ExecutionService(
            self.profile, self.binding, self.readiness, executor
        )
        outcome = service.execute(self._request())
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "TIMED_OUT")
        self.assertIsNone(outcome.exit_code)
        self.assertEqual(outcome.output_excerpt, "partial output")

    def test_a_hostile_executor_return_is_a_closed_failure(self) -> None:
        service = V2ExecutionService(
            self.profile, self.binding, self.readiness, _BadExecutor()
        )
        outcome = service.execute(self._request())
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "EXECUTION_FAILED")
        self.assertEqual(outcome.message, EXECUTION_MESSAGES_V2["EXECUTION_FAILED"])

    def test_output_is_bounded_and_sanitized(self) -> None:
        hostile = "line\n" + "x" * 5_000 + "\x00\x1b[31m\rhidden"
        executor = FakeV2Executor(ExecutionResultV2("SUCCEEDED", 0, hostile))
        service = V2ExecutionService(
            self.profile, self.binding, self.readiness, executor
        )
        outcome = service.execute(self._request())
        self.assertLessEqual(
            len(outcome.output_excerpt),
            EXECUTION_OUTCOME_EXCERPT_MAX_CHARS_V2,
        )
        for control in ("\x00", "\x1b", "\r", "\x7f"):
            self.assertNotIn(control, outcome.output_excerpt)
        self.assertTrue(outcome.output_excerpt.startswith("line\n"))

    # ------------------------------------------------------------------
    # Request discipline and closed outcome shapes
    # ------------------------------------------------------------------

    def test_a_non_record_request_rejects(self) -> None:
        for bad in ("rm -rf /workspace", "vespercode-validate cand-0001 3", 3, None):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.service.execute(bad)
        self.assertEqual(self.binding.lookups, [])
        self.assertEqual(self.readiness.checks, [])
        self.assertEqual(self.executor.calls, [])

    def test_outcomes_carry_only_closed_static_messages(self) -> None:
        scenarios: list[tuple[str, V2ExecutionService, object]] = [
            (
                "PROFILE_BINDING_MISMATCH",
                self.service,
                self._request(execution_profile_revision=5),
            ),
            (
                "EXECUTION_BINDING_NOT_FOUND",
                V2ExecutionService(
                    self.profile,
                    FakeV2BindingLookup(unresolved=True),
                    FakeV2Readiness(),
                    FakeV2Executor(),
                ),
                None,
            ),
            (
                "EXECUTION_BINDING_STALE",
                V2ExecutionService(
                    self.profile,
                    FakeV2BindingLookup(current_revision=4),
                    FakeV2Readiness(),
                    FakeV2Executor(),
                ),
                None,
            ),
            (
                "VALIDATION_BINDING_REQUIRED",
                V2ExecutionService(
                    self.profile,
                    FakeV2BindingLookup(validation_required=True),
                    FakeV2Readiness(),
                    FakeV2Executor(),
                ),
                self._request(validation_run_id=None),
            ),
            (
                "VALIDATION_BINDING_NOT_FOUND",
                V2ExecutionService(
                    self.profile,
                    FakeV2BindingLookup(validation_unresolved=True),
                    FakeV2Readiness(),
                    FakeV2Executor(),
                ),
                None,
            ),
            (
                "VALIDATION_BINDING_NOT_PASSED",
                V2ExecutionService(
                    self.profile,
                    FakeV2BindingLookup(validation_status="PENDING"),
                    FakeV2Readiness(),
                    FakeV2Executor(),
                ),
                None,
            ),
            (
                "READINESS_DAEMON_UNAVAILABLE",
                V2ExecutionService(
                    self.profile,
                    self.binding,
                    FakeV2Readiness(
                        ExecutionReadinessResultV2("NOT_READY", "DAEMON_UNAVAILABLE")
                    ),
                    FakeV2Executor(),
                ),
                None,
            ),
            (
                "TIMED_OUT",
                V2ExecutionService(
                    self.profile,
                    self.binding,
                    FakeV2Readiness(),
                    FakeV2Executor(ExecutionResultV2("TIMED_OUT", None, "")),
                ),
                None,
            ),
            (
                "EXECUTION_FAILED",
                V2ExecutionService(
                    self.profile,
                    self.binding,
                    FakeV2Readiness(),
                    FakeV2Executor(error=RuntimeError("boom")),
                ),
                None,
            ),
        ]
        for expected_code, service, request in scenarios:
            with self.subTest(expected_code=expected_code):
                outcome = service.execute(
                    request if request is not None else self._request()
                )
                self.assertEqual(outcome.status, "FAILED")
                self.assertIn(outcome.error_code, EXECUTION_OUTCOME_ERROR_CODES_V2)
                self.assertEqual(outcome.error_code, expected_code)
                self.assertEqual(outcome.message, EXECUTION_MESSAGES_V2[expected_code])

    def test_the_fake_executor_is_deterministic(self) -> None:
        executor = FakeV2Executor()
        request = self._request()
        first = executor.run(request, self.profile)
        second = executor.run(request, self.profile)
        self.assertEqual(first, second)
        self.assertEqual(first.status, "SUCCEEDED")
        self.assertEqual(first.exit_code, 0)
        self.assertEqual(first.output, FAKE_EXECUTION_OUTPUT_V2)
        self.assertEqual(len(executor.calls), 2)
        self.assertEqual(executor.calls[0][0], request)

    def test_the_fake_binding_lookup_is_deterministic(self) -> None:
        binding = FakeV2BindingLookup()
        self.assertEqual(
            binding.lookup_execution_binding(
                "run-1", "cand-0001", "valid-0001", "reference-1", 3
            ),
            ExecutionBindingOutcomeV2(
                "RESOLVED",
                ExecutionBindingFactsV2(
                    "run-1",
                    "cand-0001",
                    3,
                    ValidationBindingFactsV2(
                        "valid-0001",
                        "run-1",
                        "cand-0001",
                        3,
                        "reference-1",
                        3,
                        "PASSED",
                    ),
                ),
            ),
        )
        self.assertEqual(
            binding.lookups,
            [("run-1", "cand-0001", "valid-0001", "reference-1", 3)],
        )
        unresolved = FakeV2BindingLookup(unresolved=True)
        self.assertEqual(
            unresolved.lookup_execution_binding(
                "run-1", "cand-0001", "valid-0001", "reference-1", 3
            ),
            ExecutionBindingOutcomeV2("BINDING_NOT_FOUND"),
        )
        uncited = FakeV2BindingLookup().lookup_execution_binding(
            "run-1", "cand-0001", None, "reference-1", 3
        )
        assert uncited.facts is not None
        self.assertIsNone(uncited.facts.validation)

    def test_the_service_requires_valid_collaborators(self) -> None:
        for profile, binding, readiness, executor in (
            (None, self.binding, self.readiness, self.executor),
            ("profile", self.binding, self.readiness, self.executor),
            (self.profile, None, self.readiness, self.executor),
            (self.profile, self.binding, None, self.executor),
            (self.profile, self.binding, self.readiness, None),
        ):
            with self.subTest(profile=type(profile).__name__):
                with self.assertRaises(ValueError):
                    V2ExecutionService(profile, binding, readiness, executor)

    def test_the_outcome_echoes_the_request_id(self) -> None:
        outcome = self.service.execute(self._request(request_id="exec-request-42"))
        self.assertEqual(outcome.request_id, "exec-request-42")

    def test_an_outcome_record_enforces_its_own_closed_shape(self) -> None:
        # A hostile outcome spelling cannot even be constructed.
        for kwargs in (
            {
                "request_id": "r-1",
                "status": "SUCCEEDED",
                "error_code": "EXECUTION_FAILED",
                "message": EXECUTION_MESSAGES_V2["EXECUTION_FAILED"],
                "exit_code": 0,
                "output_excerpt": "",
            },
            {
                "request_id": "r-1",
                "status": "FAILED",
                "error_code": "NOT_A_CODE",
                "message": "custom text",
                "exit_code": None,
                "output_excerpt": "",
            },
            {
                "request_id": "r-1",
                "status": "SUCCEEDED",
                "error_code": None,
                "message": "custom text",
                "exit_code": 0,
                "output_excerpt": "",
            },
            {
                "request_id": "r-1",
                "status": "SUCCEEDED",
                "error_code": None,
                "message": EXECUTION_MESSAGES_V2["SUCCEEDED"],
                "exit_code": 0,
                "output_excerpt": "x" * (EXECUTION_OUTCOME_EXCERPT_MAX_CHARS_V2 + 1),
            },
            {
                "request_id": "r-1",
                "status": "SUCCEEDED",
                "error_code": None,
                "message": EXECUTION_MESSAGES_V2["SUCCEEDED"],
                "exit_code": 0,
                "output_excerpt": "bad\x00control",
            },
            {
                "request_id": "r-1",
                "status": "SUCCEEDED",
                "error_code": None,
                "message": EXECUTION_MESSAGES_V2["SUCCEEDED"],
                "exit_code": 256,
                "output_excerpt": "",
            },
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    ExecutionOutcomeV2(**kwargs)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
