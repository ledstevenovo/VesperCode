"""Route B / B4a + B4b-02A: the v2 execution request/result/outcome
contracts and the injectable execution/readiness ports.

The execution port accepts one closed structured request — never a
shell or command string.  ``ExecutionActionRequestV2`` names its
control-plane bindings: the request itself, the execution profile,
and the reference profile (each an opaque id plus a non-negative
revision), the run and candidate it targets (the B1 identity plane —
``run_id``, an argv-token-conformant ``candidate_id``, and the
``candidate_revision`` it cites), the B1 ``validation_run_id`` the
production service structurally requires (``None`` is the explicitly
test-only spelling: the production ``V2ExecutionService`` rejects an
uncited request with the closed ``VALIDATION_BINDING_REQUIRED`` code
before the binding port is even consulted, and only
``V2ExecutionTestService`` — the test-only subclass — executes an
uncited request, through the offline fakes), and an ``action_kind``
from the closed v2 execution
vocabulary.  The per-kind grammar pins the frozen argv executable
token and the exact argument count; for ``VALIDATE_CANDIDATE`` the
argument slots are bound to the request's own candidate id and
revision spelling, so the adapter-facing argv is a closed projection
of the request's control fields — the validation citation is a
control-plane key and is never projected into the argv.  The request
schema has no image, URL, registry, credential, secret, environment,
command, or shell field at all — a user-supplied image or credential
cannot enter the execution plane through the request.

``V2ExecutionBindingPort`` is the read-only lookup the service uses
to revalidate the whole binding against the control plane before
anything is executed.  ``lookup_execution_binding`` receives the
request's five binding keys — the cited (run, candidate) pair, the
validation citation, and the reference profile id/revision — and
returns one closed ``ExecutionBindingOutcomeV2``: ``RESOLVED`` with
``ExecutionBindingFactsV2`` (the candidate's CURRENT revision plus,
for a cited validation, ``ValidationBindingFactsV2`` — the validation
run's own five keys and status) when the whole binding resolves, or
one of the closed rejection kinds — ``BINDING_NOT_FOUND`` (the
run/candidate pair does not resolve together), ``VALIDATION_REQUIRED``
(the production binding requires a citation the request lacks),
``VALIDATION_NOT_FOUND`` (the cited validation does not resolve as
the passed validation of the current candidate under the request's
reference profile), or ``VALIDATION_NOT_PASSED`` (it resolves but is
not terminal ``PASSED``).  The lookup is read-only and the service
re-verifies every field of the returned facts against the request,
so a hostile or drifted port cannot authorize a foreign or stale
binding.

``ExecutionResultV2`` is the executor-facing report (a closed status,
a bounded exit code, and the collected output); the service maps it
to ``ExecutionOutcomeV2``, the caller-facing sanitized shape: a
status from the closed set, an error code from the closed set, the
static message of that code, a bounded exit code, and an output
excerpt that is capped and stripped of control characters — the
outcome record re-verifies those invariants at construction, so raw
command output, executor exception text, or secret material can never
be represented in an outcome.  ``ExecutionReadinessResultV2`` carries
only a status and a closed reason.

``V2ExecutionPort`` and ``V2ReadinessPort`` are the injectable
execution edges: B4a ships the deterministic fakes and the read-only
Docker probe, B4b-01 the opt-in real container execution adapter, and
B4b-02A the production database-backed binding — no other real edge
exists in this plane.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from vespercode.contracts.v2_validation import VALIDATION_RUN_STATUSES_V2
from vespercode.execution.v2_profile import ExecutionProfileRecordV2

EXECUTION_ACTION_KINDS_V2: frozenset[str] = frozenset({"VALIDATE_CANDIDATE"})
"""The closed v2 execution action vocabulary (B4a: one kind)."""

EXECUTION_ACTION_GRAMMARS_V2: MappingProxyType = MappingProxyType(
    {"VALIDATE_CANDIDATE": ("vespercode-validate", 2)}
)
"""Per action kind: the frozen argv executable token and the exact
number of arguments that follow it.  The vocabulary cannot be widened
at runtime (read-only view); adding a kind is a source change."""

EXECUTION_RESULT_STATUSES_V2: frozenset[str] = frozenset(
    {"SUCCEEDED", "FAILED", "TIMED_OUT"}
)
"""The closed statuses of one executor report."""

EXECUTION_READINESS_STATUSES_V2: frozenset[str] = frozenset(
    {"READY", "NOT_READY"}
)
"""The closed statuses of one readiness verdict."""

V2_READINESS_REASONS_V2: frozenset[str] = frozenset(
    {
        "IMAGE_NOT_AVAILABLE",
        "DAEMON_UNAVAILABLE",
        "PROFILE_REVISION_UNKNOWN",
    }
)
"""The closed NOT_READY reasons."""

EXECUTION_OUTCOME_STATUSES_V2: frozenset[str] = frozenset(
    {"SUCCEEDED", "FAILED"}
)
"""The closed statuses of one sanitized outcome."""

EXECUTION_OUTCOME_ERROR_CODES_V2: frozenset[str] = frozenset(
    {
        "PROFILE_BINDING_MISMATCH",
        "EXECUTION_BINDING_NOT_FOUND",
        "EXECUTION_BINDING_STALE",
        "VALIDATION_BINDING_REQUIRED",
        "VALIDATION_BINDING_NOT_FOUND",
        "VALIDATION_BINDING_NOT_PASSED",
        "READINESS_IMAGE_NOT_AVAILABLE",
        "READINESS_DAEMON_UNAVAILABLE",
        "READINESS_PROFILE_REVISION_UNKNOWN",
        "EXECUTION_FAILED",
        "TIMED_OUT",
    }
)
"""The closed failure codes of one sanitized outcome."""

EXECUTION_BINDING_OUTCOME_KINDS_V2: frozenset[str] = frozenset(
    {
        "RESOLVED",
        "BINDING_NOT_FOUND",
        "VALIDATION_REQUIRED",
        "VALIDATION_NOT_FOUND",
        "VALIDATION_NOT_PASSED",
    }
)
"""The closed kinds of one binding-port outcome: ``RESOLVED`` carries
the control-plane facts; every other kind is a closed rejection with
no facts.  The vocabulary cannot be widened at runtime."""

EXECUTION_OUTCOME_EXCERPT_MAX_CHARS_V2 = 2048
"""The closed cap of the sanitized outcome excerpt."""

EXECUTION_RESULT_MAX_OUTPUT_CHARS_V2 = 16 * 1024 * 1024
"""The closed sanity bound of an executor-reported output string."""

EXECUTION_MESSAGES_V2: MappingProxyType = MappingProxyType(
    {
        "SUCCEEDED": "the execution completed",
        "PROFILE_BINDING_MISMATCH": (
            "the request does not match the bound execution profile"
        ),
        "EXECUTION_BINDING_NOT_FOUND": (
            "the run/candidate binding does not resolve in the control "
            "plane"
        ),
        "EXECUTION_BINDING_STALE": (
            "the request cites a stale candidate revision"
        ),
        "VALIDATION_BINDING_REQUIRED": (
            "the request cites no validation run; the production "
            "binding resolves only cited validations"
        ),
        "VALIDATION_BINDING_NOT_FOUND": (
            "the cited validation run does not resolve as the passed "
            "validation of the current candidate under the request's "
            "reference profile"
        ),
        "VALIDATION_BINDING_NOT_PASSED": (
            "the cited validation run is not a terminal PASSED "
            "validation"
        ),
        "READINESS_IMAGE_NOT_AVAILABLE": (
            "the execution image is not available locally"
        ),
        "READINESS_DAEMON_UNAVAILABLE": (
            "the execution daemon is not available"
        ),
        "READINESS_PROFILE_REVISION_UNKNOWN": (
            "the execution profile revision is unknown to the readiness "
            "boundary"
        ),
        "EXECUTION_FAILED": "the execution failed; no retry is attempted",
        "TIMED_OUT": "the execution exceeded its bounded timeout",
    }
)
"""The closed static messages: an outcome message is always exactly
the message of its own status or error code, never dynamic text."""

_MAX_IDENTIFIER_BYTES = 256
_ARGV_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def _is_digest_shaped(value: str) -> bool:
    return len(value) == 64 and all(character in _HEX_DIGITS for character in value)


def _opaque_identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    if len(value.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
        raise ValueError(f"{field_name} is too long")
    if _is_digest_shaped(value):
        raise ValueError(
            f"{field_name} must not be a digest-shaped value; v2 "
            "references are opaque, not content digests"
        )
    return value


def _revision(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _action_kind(value: object) -> str:
    if not isinstance(value, str) or value not in EXECUTION_ACTION_KINDS_V2:
        raise ValueError(
            "action_kind must be one of "
            f"{sorted(EXECUTION_ACTION_KINDS_V2)}; the v2 execution "
            "action vocabulary is closed"
        )
    return value


def _candidate_identifier(value: object) -> str:
    """The request's candidate id: opaque AND argv-token-conformant.

    The closed per-kind grammar projects the candidate id into the
    adapter-facing argv, so the id itself must be token-shaped — a
    path, URL, option, or whitespace spelling cannot be executed
    against even at the binding level.
    """
    identifier = _opaque_identifier(value, "candidate_id")
    if not _ARGV_TOKEN_PATTERN.fullmatch(identifier):
        raise ValueError(
            "candidate_id must be an argv-token-conformant opaque "
            "identifier: the closed grammar projects it into the "
            "adapter-facing argv"
        )
    return identifier


def _argv_token(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("argv arguments must be strings")
    if _is_digest_shaped(value):
        raise ValueError(
            "argv arguments must not be digest-shaped values; v2 "
            "references are opaque, not content digests"
        )
    if not _ARGV_TOKEN_PATTERN.fullmatch(value):
        raise ValueError(
            "argv arguments must be bounded opaque tokens: paths, URLs, "
            "options, whitespace, and control characters are not accepted"
        )
    return value


def _exit_code(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("exit_code must be None or an integer")
    if not 0 <= value <= 255:
        raise ValueError("exit_code must be None or an integer between 0 and 255")
    return value


def _excerpt_is_clean(excerpt: str) -> bool:
    """True when no control character other than newline and tab is present."""
    for character in excerpt:
        code = ord(character)
        if character not in "\n\t" and (code < 0x20 or 0x7F <= code <= 0x9F):
            return False
    return True


@dataclass(frozen=True, slots=True)
class ExecutionActionRequestV2:
    """One closed execution request: control bindings plus a closed argv.

    The request names the run and the candidate it targets — the B1
    control-plane binding the service revalidates against an injected
    read-only binding port before anything is executed — and the B1
    validation run it cites: ``validation_run_id`` names the terminal
    PASSED validation the production service STRUCTURALLY requires
    (an uncited request rejects with the closed
    ``VALIDATION_BINDING_REQUIRED`` code before the binding port is
    even consulted, so the requirement does not depend on which
    binding port a caller injects; ``None`` is the explicitly
    test-only spelling — only ``V2ExecutionTestService``, the
    test-only subclass, executes an uncited request, through the
    offline fakes).  The argv is the
    adapter-built argument sequence: argv[0] is the frozen
    executable token of the request's action kind and, for
    ``VALIDATE_CANDIDATE``, the two argument slots are exactly the
    request's own ``candidate_id`` and the decimal spelling of its
    ``candidate_revision`` — the argv is a closed projection of the
    request's control fields and cannot drift from them.  No shell
    string, model-supplied executable, option token, path, URL, or
    digest-shaped value can be represented in the request at all.
    """

    request_id: str
    execution_profile_id: str
    execution_profile_revision: int
    reference_profile_id: str
    reference_profile_revision: int
    run_id: str
    candidate_id: str
    candidate_revision: int
    action_kind: str
    argv: tuple[str, ...]
    validation_run_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "request_id", _opaque_identifier(self.request_id, "request_id")
        )
        object.__setattr__(
            self,
            "execution_profile_id",
            _opaque_identifier(
                self.execution_profile_id, "execution_profile_id"
            ),
        )
        object.__setattr__(
            self,
            "execution_profile_revision",
            _revision(
                self.execution_profile_revision, "execution_profile_revision"
            ),
        )
        object.__setattr__(
            self,
            "reference_profile_id",
            _opaque_identifier(self.reference_profile_id, "reference_profile_id"),
        )
        object.__setattr__(
            self,
            "reference_profile_revision",
            _revision(
                self.reference_profile_revision, "reference_profile_revision"
            ),
        )
        object.__setattr__(
            self, "run_id", _opaque_identifier(self.run_id, "run_id")
        )
        object.__setattr__(
            self, "candidate_id", _candidate_identifier(self.candidate_id)
        )
        object.__setattr__(
            self,
            "candidate_revision",
            _revision(self.candidate_revision, "candidate_revision"),
        )
        object.__setattr__(self, "action_kind", _action_kind(self.action_kind))
        object.__setattr__(self, "argv", self._validated_argv())
        object.__setattr__(
            self,
            "validation_run_id",
            (
                None
                if self.validation_run_id is None
                else _opaque_identifier(
                    self.validation_run_id, "validation_run_id"
                )
            ),
        )

    def _validated_argv(self) -> tuple[str, ...]:
        """Validate argv against the closed grammar of the action kind.

        A bare string rejects as a shell command string; the sequence
        must start with the kind's frozen executable token, carry
        exactly the kind's argument count, and every argument must be
        a bounded opaque token.  The kind's argument slots are then
        bound to the request's own control fields: for
        ``VALIDATE_CANDIDATE`` the two slots must equal the bound
        ``candidate_id`` and the decimal spelling of the bound
        ``candidate_revision`` (a future kind defines its own
        argument semantics alongside its grammar entry).
        """
        value = self.argv
        if isinstance(value, str):
            raise ValueError(
                "argv must be a sequence of argument tokens, never a "
                "shell command string"
            )
        if not isinstance(value, (list, tuple)):
            raise ValueError("argv must be a sequence of argument tokens")
        tokens = tuple(value)
        for token in tokens:
            if not isinstance(token, str):
                raise ValueError("argv entries must be strings")
        if not tokens:
            raise ValueError("argv must contain the frozen executable token")
        executable, argument_count = EXECUTION_ACTION_GRAMMARS_V2[self.action_kind]
        if tokens[0] != executable:
            raise ValueError(
                "argv[0] must be the frozen executable token of the "
                f"action kind: {executable}"
            )
        arguments = tokens[1:]
        if len(arguments) != argument_count:
            raise ValueError(
                f"action kind {self.action_kind} takes exactly "
                f"{argument_count} argument(s) after the executable"
            )
        for argument in arguments:
            _argv_token(argument)
        if self.action_kind == "VALIDATE_CANDIDATE":
            if arguments[0] != self.candidate_id:
                raise ValueError(
                    "argv[1] must be exactly the request's bound "
                    "candidate_id"
                )
            if arguments[1] != str(self.candidate_revision):
                raise ValueError(
                    "argv[2] must be exactly the decimal spelling of "
                    "the request's bound candidate_revision"
                )
        return tokens


@dataclass(frozen=True, slots=True)
class ExecutionResultV2:
    """The executor-facing report of one execution.

    ``status`` is from the closed set; a SUCCEEDED report must carry
    exit code 0, a FAILED report a non-zero code (or None when the
    adapter signals failure without a code), and a TIMED_OUT report
    no code at all.  ``output`` is the adapter-collected output,
    bounded by the profile's ``max_output_bytes`` in a real adapter
    and sanity-bounded here; the service — never the caller —
    sanitizes it into the outcome excerpt.
    """

    status: str
    exit_code: int | None
    output: str

    def __post_init__(self) -> None:
        if self.status not in EXECUTION_RESULT_STATUSES_V2:
            raise ValueError(
                "status must be one of "
                f"{sorted(EXECUTION_RESULT_STATUSES_V2)}"
            )
        if not isinstance(self.output, str):
            raise ValueError("output must be a string")
        if len(self.output) > EXECUTION_RESULT_MAX_OUTPUT_CHARS_V2:
            raise ValueError("output exceeds the bounded result size")
        if self.status == "SUCCEEDED" and self.exit_code != 0:
            raise ValueError("SUCCEEDED results must report exit code 0")
        if self.status == "FAILED" and self.exit_code == 0:
            raise ValueError("FAILED results must report a non-zero exit code or None")
        if self.status == "TIMED_OUT" and self.exit_code is not None:
            raise ValueError("TIMED_OUT results carry no exit code")
        _exit_code(self.exit_code)


@dataclass(frozen=True, slots=True)
class ExecutionReadinessResultV2:
    """One readiness verdict: a status and, when NOT_READY, a closed reason.

    ``reason`` defaults to ``None`` (the READY spelling); a NOT_READY
    verdict must carry one of the closed reasons.
    """

    status: str
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in EXECUTION_READINESS_STATUSES_V2:
            raise ValueError(
                "status must be one of "
                f"{sorted(EXECUTION_READINESS_STATUSES_V2)}"
            )
        if self.status == "READY":
            if self.reason is not None:
                raise ValueError("READY results carry no reason")
        else:
            if self.reason not in V2_READINESS_REASONS_V2:
                raise ValueError(
                    "reason must be one of "
                    f"{sorted(V2_READINESS_REASONS_V2)}"
                )


@dataclass(frozen=True, slots=True)
class ExecutionOutcomeV2:
    """The sanitized caller-facing outcome of one execution request.

    ``error_code`` is ``None`` exactly for ``SUCCEEDED``; ``message``
    is always the closed static message of the status or code, so no
    executor exception text, raw command output, or secret can ever
    enter an outcome.  ``output_excerpt`` is capped and carries no
    control characters other than newline and tab — the record
    re-verifies both, so even a hostile producer cannot construct an
    outcome that violates them.
    """

    request_id: str
    status: str
    error_code: str | None
    message: str
    exit_code: int | None
    output_excerpt: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "request_id", _opaque_identifier(self.request_id, "request_id")
        )
        if self.status not in EXECUTION_OUTCOME_STATUSES_V2:
            raise ValueError(
                "status must be one of "
                f"{sorted(EXECUTION_OUTCOME_STATUSES_V2)}"
            )
        if self.status == "SUCCEEDED":
            if self.error_code is not None:
                raise ValueError("SUCCEEDED outcomes carry no error code")
        else:
            if self.error_code not in EXECUTION_OUTCOME_ERROR_CODES_V2:
                raise ValueError(
                    "error_code must be one of "
                    f"{sorted(EXECUTION_OUTCOME_ERROR_CODES_V2)}"
                )
        key = "SUCCEEDED" if self.status == "SUCCEEDED" else self.error_code
        if self.message != EXECUTION_MESSAGES_V2[key]:
            raise ValueError(
                "outcome message must be the closed static message of "
                "its status or error code"
            )
        _exit_code(self.exit_code)
        if not isinstance(self.output_excerpt, str):
            raise ValueError("output_excerpt must be a string")
        if len(self.output_excerpt) > EXECUTION_OUTCOME_EXCERPT_MAX_CHARS_V2:
            raise ValueError(
                "output_excerpt exceeds "
                f"{EXECUTION_OUTCOME_EXCERPT_MAX_CHARS_V2} characters"
            )
        if not _excerpt_is_clean(self.output_excerpt):
            raise ValueError(
                "output_excerpt must not contain control characters "
                "other than newline and tab"
            )


@dataclass(frozen=True, slots=True)
class ValidationBindingFactsV2:
    """The control-plane facts of one cited validation run.

    The binding port resolves the cited validation run into these
    facts — its own opaque id, the five B1 keys it was recorded
    against, and its bounded status — and the service re-verifies
    every field against the request, so a hostile or drifted port
    cannot present another run's validation as this request's
    evidence.
    """

    validation_run_id: str
    run_id: str
    candidate_id: str
    candidate_revision: int
    reference_profile_id: str
    reference_profile_revision: int
    status: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "validation_run_id",
            _opaque_identifier(
                self.validation_run_id, "validation_run_id"
            ),
        )
        object.__setattr__(
            self, "run_id", _opaque_identifier(self.run_id, "run_id")
        )
        object.__setattr__(
            self,
            "candidate_id",
            _candidate_identifier(self.candidate_id),
        )
        object.__setattr__(
            self,
            "candidate_revision",
            _revision(self.candidate_revision, "candidate_revision"),
        )
        object.__setattr__(
            self,
            "reference_profile_id",
            _opaque_identifier(
                self.reference_profile_id, "reference_profile_id"
            ),
        )
        object.__setattr__(
            self,
            "reference_profile_revision",
            _revision(
                self.reference_profile_revision, "reference_profile_revision"
            ),
        )
        if self.status not in VALIDATION_RUN_STATUSES_V2:
            raise ValueError(
                "status must be one of "
                f"{sorted(VALIDATION_RUN_STATUSES_V2)}; the v2 "
                "validation run lifecycle is closed"
            )


@dataclass(frozen=True, slots=True)
class ExecutionBindingFactsV2:
    """The control-plane facts one execution request must match.

    The binding port resolves the (run, candidate) pair to the
    candidate's CURRENT revision; the service re-verifies all three
    values against the request, so a hostile or drifted port cannot
    authorize a foreign or stale binding.  For a request that cites a
    validation run, ``validation`` carries the resolved validation
    facts — the service re-verifies those against the request too.
    """

    run_id: str
    candidate_id: str
    candidate_revision: int
    validation: ValidationBindingFactsV2 | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "run_id", _opaque_identifier(self.run_id, "run_id")
        )
        object.__setattr__(
            self,
            "candidate_id",
            _candidate_identifier(self.candidate_id),
        )
        object.__setattr__(
            self,
            "candidate_revision",
            _revision(self.candidate_revision, "candidate_revision"),
        )
        if self.validation is not None and not isinstance(
            self.validation, ValidationBindingFactsV2
        ):
            raise ValueError(
                "validation facts must be a ValidationBindingFactsV2 or None"
            )


@dataclass(frozen=True, slots=True)
class ExecutionBindingOutcomeV2:
    """One closed verdict of the read-only binding lookup.

    ``kind`` is from ``EXECUTION_BINDING_OUTCOME_KINDS_V2``: only
    ``RESOLVED`` carries facts (the candidate's current revision plus,
    for a cited validation, the validation facts); every other kind is
    a closed rejection with no facts at all, so a binding port cannot
    smuggle a half-resolved binding past its own verdict.
    """

    kind: str
    facts: ExecutionBindingFactsV2 | None = None

    def __post_init__(self) -> None:
        if self.kind not in EXECUTION_BINDING_OUTCOME_KINDS_V2:
            raise ValueError(
                "kind must be one of "
                f"{sorted(EXECUTION_BINDING_OUTCOME_KINDS_V2)}; the "
                "binding outcome vocabulary is closed"
            )
        if self.kind == "RESOLVED":
            if not isinstance(self.facts, ExecutionBindingFactsV2):
                raise ValueError(
                    "a RESOLVED binding outcome must carry "
                    "ExecutionBindingFactsV2"
                )
        elif self.facts is not None:
            raise ValueError(
                "only a RESOLVED binding outcome carries facts"
            )


@runtime_checkable
class V2ExecutionBindingPort(Protocol):
    """The injectable read-only control-plane binding lookup.

    ``lookup_execution_binding`` receives the request's five binding
    keys — the cited (run, candidate) pair, the validation citation
    (``None`` when the request cites none), and the reference profile
    id/revision — and resolves them to one closed
    ``ExecutionBindingOutcomeV2``: ``RESOLVED`` facts when the pair
    resolves together at the candidate's CURRENT revision and, for a
    cited validation, the validation belongs to the same run, the
    same candidate, at the current candidate revision, under the cited
    reference profile id/revision, and is terminal ``PASSED``; one of
    the closed rejection kinds otherwise (an unknown run, an unknown
    candidate, a candidate belonging to a different run, a missing,
    foreign, stale, or corrupt validation, or an uncited request the
    binding requires a citation for).  The lookup is read-only: it
    never mutates the control plane, and the service re-verifies
    every field of the returned facts against the request before
    readiness or execution is touched.
    """

    def lookup_execution_binding(
        self,
        run_id: str,
        candidate_id: str,
        validation_run_id: str | None,
        reference_profile_id: str,
        reference_profile_revision: int,
    ) -> ExecutionBindingOutcomeV2: ...


@runtime_checkable
class V2ExecutionPort(Protocol):
    """The injectable execution edge.

    ``run`` receives the closed structured request and the bound
    execution profile — never a shell or command string — and returns
    one ``ExecutionResultV2``.  B4a ships the deterministic fake and
    the read-only Docker probe only; a real container execution
    adapter is a later slice behind this same protocol.
    """

    def run(
        self, request: ExecutionActionRequestV2, profile: ExecutionProfileRecordV2
    ) -> ExecutionResultV2: ...


@runtime_checkable
class V2ReadinessPort(Protocol):
    """The injectable readiness edge.

    ``check`` probes whether the profile's execution environment is
    ready and returns one ``ExecutionReadinessResultV2``; probing is
    read-only and never creates containers or modifies the daemon.
    """

    def check(self, profile: ExecutionProfileRecordV2) -> ExecutionReadinessResultV2: ...


# ``ExecutionActionRequestV2`` validates its argv inside ``__post_init__``
# against the closed grammar of its already-validated action kind, so a
# request is either fully grammar-bound or not constructible at all.


__all__ = (
    "EXECUTION_ACTION_GRAMMARS_V2",
    "EXECUTION_ACTION_KINDS_V2",
    "EXECUTION_BINDING_OUTCOME_KINDS_V2",
    "EXECUTION_MESSAGES_V2",
    "EXECUTION_OUTCOME_ERROR_CODES_V2",
    "EXECUTION_OUTCOME_EXCERPT_MAX_CHARS_V2",
    "EXECUTION_OUTCOME_STATUSES_V2",
    "EXECUTION_READINESS_STATUSES_V2",
    "EXECUTION_RESULT_MAX_OUTPUT_CHARS_V2",
    "EXECUTION_RESULT_STATUSES_V2",
    "ExecutionActionRequestV2",
    "ExecutionBindingFactsV2",
    "ExecutionBindingOutcomeV2",
    "ExecutionOutcomeV2",
    "ExecutionReadinessResultV2",
    "ExecutionResultV2",
    "ValidationBindingFactsV2",
    "V2ExecutionBindingPort",
    "V2ExecutionPort",
    "V2ReadinessPort",
    "V2_READINESS_REASONS_V2",
)
