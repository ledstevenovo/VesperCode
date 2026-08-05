"""T08.1 legacy step 8.A: strict run-request admission and frozen config.

``validate_request`` parses the closed SPEC §4.1 request schema (every
field required, unknown fields rejected, no silent defaults), validates
the target set, resolves the built-in LLM/reference profile identities
and the sole built-in editable policy, and produces one
``ValidatedRunRequestV1`` with the canonical sorted target set and the
bound profile digests; ``freeze_run_config`` freezes the no-secret
``RunConfigSnapshotV1`` whose §0.1 digest binds the frozen
profile/policy/target/limit identities; ``create_run`` creates exactly
one ``CREATED`` Run in one atomic transaction with its immutable frozen
config, ending this task's ownership.  Workspace lease, Snapshot,
readiness, and PREFLIGHT execution remain out of scope (GREEN-4).
"""

from __future__ import annotations

import json
import uuid
from typing import Callable, Literal, Mapping, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)

from src.vespercode.canonical.clock import SystemClockV1
from src.vespercode.canonical.digest import domain_digest
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.optional import AbsentV1
from src.vespercode.contracts.run import (
    RunLimitsV1,
    _require_non_empty_identifier,
)
from src.vespercode.profiles.editable import _reject_coerced_schema_version
from src.vespercode.profiles.endpoints import UnknownEndpointError
from src.vespercode.profiles.llm import OpenAILLMProfileV1
from src.vespercode.profiles.registry import (
    ProfileRegistry,
    UnknownProfileError,
)
from src.vespercode.storage.run_repository import (
    RunRecordV1,
    RunRepository,
)


def _system_now() -> CanonicalTimestampV1:
    """Production current time: the system clock (UTC epoch milliseconds)."""
    return SystemClockV1().now()


def _unique_run_id() -> str:
    """Production run ids: one unique identifier per created Run."""
    return f"run-{uuid.uuid4().hex}"


# SPEC §5.4 test-mode injection points: tests replace these module
# functions with a FakeClockV1 and a deterministic id factory so the
# frozen_at, run_id, and deadline of one run are stable across runs.
_now: Callable[[], CanonicalTimestampV1] = _system_now
_new_run_id: Callable[[], str] = _unique_run_id


class ValidateRunRequestV1(BaseModel):
    """SPEC §4.1 closed request schema.

    Every field is required and the parser never fills defaults; unknown
    fields, type-confused values, malformed limits, and target-set
    violations reject before any profile resolution or Run exists.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    workspace_path: StrictStr
    target_test_ids: list[StrictStr]
    llm_profile_id: StrictStr
    reference_profile_id: StrictStr
    limits: RunLimitsV1

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("workspace_path", "llm_profile_id", "reference_profile_id")
    @classmethod
    def _ids_are_non_empty(cls, value: str) -> str:
        return _require_non_empty_identifier(value)


class ValidatedRunRequestV1(BaseModel):
    """One closed validated request with the bound profile identities.

    The canonical target set is sorted (SPEC §4.1 behavior 1 binds the
    canonical request after §0.1 sorting) and the resolved manifest
    digests are bound here so the frozen config can never re-resolve a
    different profile identity.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    workspace_path: StrictStr
    target_test_ids: tuple[StrictStr, ...]
    llm_profile_id: StrictStr
    llm_profile_digest: StrictStr
    reference_profile_id: StrictStr
    reference_profile_digest: StrictStr
    policy_id: StrictStr
    limits: RunLimitsV1

    @model_validator(mode="after")
    def _targets_are_canonical(self) -> ValidatedRunRequestV1:
        if tuple(sorted(self.target_test_ids)) != self.target_test_ids:
            raise ValueError("target_test_ids must be in canonical sorted order")
        return self


ConfigInvalidReasonV1: TypeAlias = Literal[
    "UNKNOWN_FIELD",
    "REQUEST_SCHEMA_INVALID",
    "DUPLICATE_TARGET_ID",
    "TARGET_SET_INVALID",
    "UNKNOWN_LLM_PROFILE",
    "UNKNOWN_REFERENCE_PROFILE",
    "PROFILE_ENDPOINT_UNRESOLVED",
    "POLICY_ID_UNRESOLVED",
    "POLICY_DIGEST_MISMATCH",
    "LIMITS_INVALID",
]
"""The closed stable rejection-reason vocabulary of the v1 request schema."""


class ConfigInvalidV1(BaseModel):
    """Closed ``CONFIG_INVALID`` rejection with a stable reason and
    user-understandable guidance (SPEC §5.3)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["CONFIG_INVALID"]
    reason: ConfigInvalidReasonV1
    message: StrictStr
    suggestion: StrictStr


def _invalid(
    reason: ConfigInvalidReasonV1, message: str, suggestion: str
) -> ConfigInvalidV1:
    """One closed rejection with the stable reason and next-step guidance."""
    return ConfigInvalidV1(
        kind="CONFIG_INVALID",
        reason=reason,
        message=message,
        suggestion=suggestion,
    )


def _limits_digest(limits: RunLimitsV1) -> str:
    """The §0.1 identity of the closed limits (SPEC §4.1 behavior 4)."""
    return domain_digest(
        "RunLimitsV1",
        1,
        {
            "max_turns": limits.max_turns,
            "max_llm_calls": limits.max_llm_calls,
            "max_run_wall_clock_seconds": limits.max_run_wall_clock_seconds,
            "user_wait_timeout_seconds": limits.user_wait_timeout_seconds,
            "tool_timeout_seconds": limits.tool_timeout_seconds,
            "target_check_timeout_seconds": limits.target_check_timeout_seconds,
            "full_check_timeout_seconds": limits.full_check_timeout_seconds,
            "baseline_timeout_seconds": limits.baseline_timeout_seconds,
            "formal_validation_timeout_seconds": limits.formal_validation_timeout_seconds,
        },
    )


def _snapshot_digest(
    *,
    llm_profile_id: str,
    llm_profile_digest: str,
    reference_profile_id: str,
    reference_profile_digest: str,
    policy_id: str,
    target_test_ids: tuple[str, ...],
    limits_digest: str,
) -> str:
    """The §0.1 identity of the frozen profile/policy/target/limit set.

    The freeze time is deliberately excluded: identical inputs must form
    the identical frozen config (SPEC §5.2) while ``frozen_at`` remains
    per-freeze run metadata.
    """
    return domain_digest(
        "RunConfigSnapshotV1",
        1,
        {
            "llm_profile_id": llm_profile_id,
            "llm_profile_digest": llm_profile_digest,
            "reference_profile_id": reference_profile_id,
            "reference_profile_digest": reference_profile_digest,
            "policy_id": policy_id,
            "target_test_ids": target_test_ids,
            "limits_digest": limits_digest,
        },
    )


class RunConfigSnapshotV1(BaseModel):
    """The immutable no-secret frozen config (SPEC §4.1 behavior 4).

    Binds the canonical target set, the limits, the LLM profile digest,
    and the unique reference manifest digest; the snapshot id is derived
    from the §0.1 digest, so identical inputs always bind the identical
    frozen config.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    config_snapshot_id: StrictStr
    digest: StrictStr
    llm_profile_id: StrictStr
    llm_profile_digest: StrictStr
    reference_profile_id: StrictStr
    reference_profile_digest: StrictStr
    policy_id: StrictStr
    target_test_ids: tuple[StrictStr, ...]
    limits: RunLimitsV1
    limits_digest: StrictStr
    frozen_at: CanonicalTimestampV1

    @model_validator(mode="after")
    def _digests_bind_the_frozen_identities(self) -> RunConfigSnapshotV1:
        if self.limits_digest != _limits_digest(self.limits):
            raise ValueError("limits_digest must equal the §0.1 identity of the limits")
        if self.digest != _snapshot_digest(
            llm_profile_id=self.llm_profile_id,
            llm_profile_digest=self.llm_profile_digest,
            reference_profile_id=self.reference_profile_id,
            reference_profile_digest=self.reference_profile_digest,
            policy_id=self.policy_id,
            target_test_ids=self.target_test_ids,
            limits_digest=self.limits_digest,
        ):
            raise ValueError(
                "digest must equal the §0.1 identity of the frozen identities"
            )
        if self.config_snapshot_id != f"snap-{self.digest}":
            raise ValueError(
                "config_snapshot_id must derive from the frozen config digest"
            )
        return self


class RunCreatedV1(BaseModel):
    """SPEC §4.1 output: one CREATED run with its frozen config identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: StrictStr
    config_snapshot_id: StrictStr
    status: Literal["CREATED"]


def _classify_invalid(exc: ValidationError) -> ConfigInvalidV1:
    """Map the closed-schema parse failure to the stable rejection reason."""
    errors = exc.errors()
    for error in errors:
        if error.get("type") == "extra_forbidden":
            loc = error.get("loc") or ()
            field = loc[0] if loc else "?"
            return _invalid(
                "UNKNOWN_FIELD",
                f"unknown request field {field!r}: the v1 request schema is closed",
                "remove the field and resubmit the request",
            )
    if any((error.get("loc") or ())[:1] == ("limits",) for error in errors):
        return _invalid(
            "LIMITS_INVALID",
            "the limits field does not satisfy the closed RunLimitsV1 contract",
            "submit every limit field inside the built-in hard caps",
        )
    if any((error.get("loc") or ())[:1] == ("target_test_ids",) for error in errors):
        return _invalid(
            "TARGET_SET_INVALID",
            "the target set does not satisfy the closed request schema",
            "submit 1..20 unique non-empty pytest node ids of at most 1024 UTF-8 bytes",
        )
    return _invalid(
        "REQUEST_SCHEMA_INVALID",
        "the request does not satisfy the closed v1 request schema",
        "submit exactly the declared fields with their exact types",
    )


def validate_request(
    request: Mapping[str, object], profiles: ProfileRegistry
) -> ValidatedRunRequestV1 | ConfigInvalidV1:
    """Validate one closed raw request before any run id can exist.

    Syntax, type, enum, and basic domain validation run first; then the
    built-in profile identities and the sole built-in editable policy are
    bound; every rejection returns ``CONFIG_INVALID`` with a stable reason
    and never touches the repository.
    """
    try:
        parsed = ValidateRunRequestV1.model_validate(request)
    except ValidationError as exc:
        return _classify_invalid(exc)
    targets = parsed.target_test_ids
    if not 1 <= len(targets) <= 20:
        return _invalid(
            "TARGET_SET_INVALID",
            "the request must carry 1..20 target node ids",
            "submit between 1 and 20 unique pytest node ids",
        )
    for target in targets:
        if target == "":
            return _invalid(
                "TARGET_SET_INVALID",
                "target node ids must be non-empty",
                "submit non-empty pytest node ids",
            )
        if len(target.encode("utf-8")) > 1024:
            return _invalid(
                "TARGET_SET_INVALID",
                "target node ids must not exceed 1024 UTF-8 bytes",
                "submit pytest node ids of at most 1024 UTF-8 bytes",
            )
    if len(set(targets)) != len(targets):
        return _invalid(
            "DUPLICATE_TARGET_ID",
            "target node ids must be unique",
            "remove the repeated target node id and resubmit",
        )
    try:
        llm = profiles.resolve_llm(parsed.llm_profile_id)
    except UnknownProfileError as exc:
        return _invalid(
            "UNKNOWN_LLM_PROFILE",
            str(exc),
            "choose one of the built-in LLM profile ids: "
            "mock-deterministic-v1, openai-single-turn-v1",
        )
    if isinstance(llm, OpenAILLMProfileV1):
        try:
            profiles.resolve_endpoint(llm.endpoint_id)
        except UnknownEndpointError as exc:
            return _invalid(
                "PROFILE_ENDPOINT_UNRESOLVED",
                str(exc),
                "choose an LLM profile whose endpoint_id resolves in the "
                "built-in endpoint map",
            )
    try:
        reference = profiles.resolve_reference(parsed.reference_profile_id)
    except UnknownProfileError as exc:
        return _invalid(
            "UNKNOWN_REFERENCE_PROFILE",
            str(exc),
            "choose the built-in reference profile id python-src-py312-v1",
        )
    try:
        policy = profiles.resolve_editable(reference.editable_path_policy.policy_id)
    except UnknownProfileError as exc:
        return _invalid(
            "POLICY_ID_UNRESOLVED",
            str(exc),
            "the reference manifest must bind the sole built-in editable policy",
        )
    if policy.digest != reference.editable_path_policy.digest:
        return _invalid(
            "POLICY_DIGEST_MISMATCH",
            "the reference manifest's editable policy digest does not bind "
            "the sole built-in policy",
            "use an unmodified built-in reference manifest",
        )
    return ValidatedRunRequestV1(
        schema_version=1,
        workspace_path=parsed.workspace_path,
        target_test_ids=tuple(sorted(targets)),
        llm_profile_id=llm.profile_id,
        llm_profile_digest=llm.digest,
        reference_profile_id=reference.profile_id,
        reference_profile_digest=reference.digest,
        policy_id=policy.policy_id,
        limits=parsed.limits,
    )


def freeze_run_config(request: ValidatedRunRequestV1) -> RunConfigSnapshotV1:
    """Freeze the no-secret config for one validated request."""
    limits_digest = _limits_digest(request.limits)
    digest = _snapshot_digest(
        llm_profile_id=request.llm_profile_id,
        llm_profile_digest=request.llm_profile_digest,
        reference_profile_id=request.reference_profile_id,
        reference_profile_digest=request.reference_profile_digest,
        policy_id=request.policy_id,
        target_test_ids=request.target_test_ids,
        limits_digest=limits_digest,
    )
    return RunConfigSnapshotV1(
        config_snapshot_id=f"snap-{digest}",
        digest=digest,
        llm_profile_id=request.llm_profile_id,
        llm_profile_digest=request.llm_profile_digest,
        reference_profile_id=request.reference_profile_id,
        reference_profile_digest=request.reference_profile_digest,
        policy_id=request.policy_id,
        target_test_ids=request.target_test_ids,
        limits=request.limits,
        limits_digest=limits_digest,
        frozen_at=_now(),
    )


def create_run(
    request: ValidatedRunRequestV1, repository: RunRepository
) -> RunCreatedV1:
    """Create exactly one ``CREATED`` Run with its immutable frozen config.

    The frozen snapshot row and the run row are written in one explicit
    immediate transaction; an identical already-frozen config shares its
    row (the UNIQUE digest identity) while every valid request creates
    exactly one new Run.
    """
    snapshot = freeze_run_config(request)
    run_id = _new_run_id()
    now = _now()
    run_deadline = CanonicalTimestampV1.from_epoch_milliseconds(
        now.epoch_milliseconds + request.limits.max_run_wall_clock_seconds * 1000
    )
    run = RunRecordV1(
        run_id=run_id,
        workspace_identity=request.workspace_path,
        status="CREATED",
        phase=AbsentV1(kind="ABSENT"),
        config_snapshot_id=snapshot.config_snapshot_id,
        started_at=now,
        run_deadline=run_deadline,
    )
    with repository.database.immediate_transaction() as tx:
        tx.execute(
            "INSERT OR IGNORE INTO run_config_snapshots (config_snapshot_id,"
            " digest, llm_profile_id, reference_profile_id, policy_id,"
            " target_test_ids, limits_digest, frozen_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot.config_snapshot_id,
                snapshot.digest,
                snapshot.llm_profile_id,
                snapshot.reference_profile_id,
                snapshot.policy_id,
                json.dumps(list(snapshot.target_test_ids)),
                snapshot.limits_digest,
                snapshot.frozen_at.value,
            ),
        )
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES (?, ?, ?, ?, NULL, 1, ?, ?)",
            (
                run.run_id,
                run.workspace_identity,
                run.config_snapshot_id,
                run.status,
                run.started_at.value,
                run.run_deadline.value,
            ),
        )
    return RunCreatedV1(
        run_id=run.run_id,
        config_snapshot_id=run.config_snapshot_id,
        status="CREATED",
    )


class RunRequestService:
    """One closed validate-and-create entry (SPEC §4.1 behaviors 1-4)."""

    def __init__(self, profiles: ProfileRegistry, repository: RunRepository) -> None:
        self._profiles = profiles
        self._repository = repository

    def validate_and_create(
        self, raw_request: Mapping[str, object]
    ) -> RunCreatedV1 | ConfigInvalidV1:
        """Reject every invalid request before a run id exists, otherwise
        create one ``CREATED`` Run with its immutable frozen config."""
        validated = validate_request(raw_request, self._profiles)
        if isinstance(validated, ConfigInvalidV1):
            return validated
        return create_run(validated, self._repository)
