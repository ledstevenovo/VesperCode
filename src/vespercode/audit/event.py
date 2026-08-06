"""T23.1 legacy step 23.A: closed bounded redacted audit event vocabulary.

Defines the allowlisted event-type union, the closed discriminated
redacted-payload variants (each carrying only bounded facts and bounded
evidence references — never credentials, request/response bodies, raw
outputs, or file bodies per SPEC 4.7), the immutable ``AuditEventV1``
value (run id, per-Run unique increasing sequence, event type, redacted
payload, canonical timestamp), the one SPEC audit error code, the
allowlist/forbidden-key tables and bounds, the redact-and-minimize
function consumed by the append transaction, and the canonical payload
storage round-trip.  Storage, sequencing, pagination, projection, and
retention stay out of scope (GREEN-4).
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Literal, Self, TypeAlias, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    ValidationError,
    model_validator,
)

from src.vespercode.canonical.json_v1 import canonical_json_bytes
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1

AuditEventTypeV1: TypeAlias = Literal[
    "LIFECYCLE",
    "ACTION",
    "POLICY_DECISION",
    "FINAL_WRITEBACK_APPROVAL",
    "DISCLOSURE_GRANT",
    "DISCLOSURE_AUTHORIZATION",
    "CHECK_RESULT",
    "RECOVERY",
    "STOP_EVIDENCE",
    "LLM_CALL",
]
"""SPEC 4.7 audit record kinds: the closed event-type allowlist."""

AuditErrorCodeV1: TypeAlias = Literal["AUDIT_STORE_FAILED"]
"""SPEC 4.7: the single closed audit error code."""

AuditPayloadInputV1: TypeAlias = dict[str, str]
"""One raw bounded append payload; the repository redacts before storing."""

_PAYLOAD_KEY_MAX = 8
_PAYLOAD_VALUE_MAX_CHARS = 512
_EVIDENCE_REFS_MAX = 8
_EVIDENCE_REF_MAX_CHARS = 128

# The per-event-type allowlist of payload keys; every other key is either
# globally forbidden (body/secret/request/response/raw-output classes) or
# not allowlisted and therefore rejected with zero rows.
_ALLOWED_PAYLOAD_KEYS: dict[str, tuple[str, ...]] = {
    "LIFECYCLE": ("status", "phase"),
    "ACTION": ("action_type", "policy_decision"),
    "POLICY_DECISION": ("decision", "reason_code"),
    "FINAL_WRITEBACK_APPROVAL": ("approval_id", "status"),
    "DISCLOSURE_GRANT": ("grant_id", "status"),
    "DISCLOSURE_AUTHORIZATION": ("category", "byte_count"),
    "CHECK_RESULT": ("check_kind", "status"),
    "RECOVERY": ("transaction_id", "disposition"),
    "STOP_EVIDENCE": ("reason_code",),
    "LLM_CALL": ("outcome",),
}

_FORBIDDEN_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "request",
        "request_body",
        "response",
        "response_body",
        "api_key",
        "secret",
        "secret_key",
        "token",
        "raw_output",
        "output",
        "stdout",
        "stderr",
        "body",
        "content",
        "prompt",
        "completion",
        "messages",
        "authorization",
        "credentials",
        "password",
    }
)
"""SPEC 4.7 data minimization: body/secret/request/response fields are
never representable in a redacted payload."""

_PRIVATE_KEY_BLOCK_RE = re.compile(
    rb"(?<![A-Za-z0-9_])-----BEGIN [A-Z0-9][A-Z0-9 -]* PRIVATE KEY-----"
    rb"(?![A-Za-z0-9_])"
)
_GENERIC_API_KEY_RE = re.compile(
    rb"(?<![A-Za-z0-9_])(?i:API_KEY|SECRET_KEY|ACCESS_TOKEN|AUTH_TOKEN)"
    rb"(?![A-Za-z0-9_])[ \t]*(?>=>|=|:)(?:([\"'])([^\n]+?)\1|"
    rb"[^ \t\r\n\v\f,;)}\x22']+)"
)
_CREDENTIAL_URL_RE = re.compile(
    rb"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@"
)
"""The audit secret vocabulary mirrors the Task 1 frozen credential rule
table (scripts/gate_scan.py) and the T22.1 memory mirror.  It stays local
because ``scripts/`` is not part of the packaged runtime (T33.1 wheel);
any later change to the gate rules must be mirrored here."""


def _contains_secret(text: str) -> bool:
    data = text.encode("utf-8")
    return (
        _PRIVATE_KEY_BLOCK_RE.search(data) is not None
        or _GENERIC_API_KEY_RE.search(data) is not None
        or _CREDENTIAL_URL_RE.search(data) is not None
    )


class _PayloadBaseV1(BaseModel):
    """Shared bounded evidence-reference contract of every payload variant."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    evidence_refs: tuple[StrictStr, ...] = Field(
        default=(), max_length=_EVIDENCE_REFS_MAX
    )

    @model_validator(mode="after")
    def _validate_evidence_refs(self) -> Self:
        for ref in self.evidence_refs:
            if len(ref) < 1 or len(ref) > _EVIDENCE_REF_MAX_CHARS:
                raise ValueError("evidence references must be 1..128 characters")
            if _contains_secret(ref):
                raise ValueError("evidence references must not contain secret values")
        return self


class LifecyclePayloadV1(_PayloadBaseV1):
    """Bounded lifecycle fact: recorded status plus optional phase."""

    kind: Literal["LIFECYCLE"]
    status: Literal[
        "CREATED",
        "RUNNING",
        "WAITING_USER",
        "RECOVERY_REQUIRED",
        "SUCCEEDED",
        "STOPPED",
    ]
    phase: (
        Literal[
            "PREFLIGHT",
            "BASELINE",
            "AGENT_LOOP",
            "FORMAL_VALIDATION",
            "PERSISTENCE",
        ]
        | None
    ) = None


class ActionPayloadV1(_PayloadBaseV1):
    """Bounded action summary: action type and policy outcome only."""

    kind: Literal["ACTION"]
    action_type: Annotated[StrictStr, Field(min_length=1, max_length=64)]
    policy_decision: Literal["ALLOW", "ASK", "DENY"]


class PolicyDecisionPayloadV1(_PayloadBaseV1):
    """Bounded policy decision fact with the stable reason code."""

    kind: Literal["POLICY_DECISION"]
    decision: Literal["ALLOW", "ASK", "DENY"]
    reason_code: Annotated[StrictStr, Field(min_length=1, max_length=64)]


class FinalWritebackApprovalPayloadV1(_PayloadBaseV1):
    """Bounded FinalWritebackApproval fact: id and recorded status only."""

    kind: Literal["FINAL_WRITEBACK_APPROVAL"]
    approval_id: Annotated[StrictStr, Field(min_length=1, max_length=128)]
    status: Literal["PENDING", "APPROVED", "REJECTED", "EXPIRED"]


class DisclosureGrantPayloadV1(_PayloadBaseV1):
    """Bounded DisclosureGrant fact: id and recorded status only."""

    kind: Literal["DISCLOSURE_GRANT"]
    grant_id: Annotated[StrictStr, Field(min_length=1, max_length=128)]
    status: Literal["ACTIVE", "EXHAUSTED", "REVOKED", "EXPIRED"]


class DisclosureAuthorizationPayloadV1(_PayloadBaseV1):
    """Bounded per-request disclosure authorization metadata."""

    kind: Literal["DISCLOSURE_AUTHORIZATION"]
    category: Literal["ROOT", "FILE", "DIRECTORY"]
    byte_count: Annotated[StrictStr, Field(min_length=1, max_length=16)]


class CheckResultPayloadV1(_PayloadBaseV1):
    """Bounded check-result fact: check kind and status, never raw output."""

    kind: Literal["CHECK_RESULT"]
    check_kind: Literal["TARGET_TESTS", "FULL_PYTEST", "RUFF", "MYPY"]
    status: Literal["PASS", "FAIL", "ERROR", "BLOCKED"]


class RecoveryPayloadV1(_PayloadBaseV1):
    """Bounded recovery fact: transaction id and closed disposition."""

    kind: Literal["RECOVERY"]
    transaction_id: Annotated[StrictStr, Field(min_length=1, max_length=128)]
    disposition: Literal["COMMITTED", "ROLLED_BACK", "UNRESOLVED"]


class StopEvidencePayloadV1(_PayloadBaseV1):
    """Bounded stop evidence: the stable stop reason code only."""

    kind: Literal["STOP_EVIDENCE"]
    reason_code: Annotated[StrictStr, Field(min_length=1, max_length=64)]


class LLMCallPayloadV1(_PayloadBaseV1):
    """Bounded LLM-call fact: outcome only, never request/response bytes."""

    kind: Literal["LLM_CALL"]
    outcome: Literal["COMPLETED", "FAILED", "NOT_ATTEMPTED"]


AuditPayloadV1 = Annotated[
    LifecyclePayloadV1
    | ActionPayloadV1
    | PolicyDecisionPayloadV1
    | FinalWritebackApprovalPayloadV1
    | DisclosureGrantPayloadV1
    | DisclosureAuthorizationPayloadV1
    | CheckResultPayloadV1
    | RecoveryPayloadV1
    | StopEvidencePayloadV1
    | LLMCallPayloadV1,
    Field(discriminator="kind"),
]
"""The closed bounded redacted payload union (discriminated by kind)."""


class AuditEventV1(BaseModel):
    """One immutable audit event (SPEC 7 AuditEvent row, flat value).

    Fields are limited to the run id, the per-Run unique increasing
    sequence, the allowlisted event type, the redacted payload, and the
    canonical created-at timestamp; secrets, request/response bodies,
    raw outputs, and file bodies have no representable field.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: StrictStr
    sequence: Annotated[int, Field(strict=True, ge=1)]
    event_type: AuditEventTypeV1
    redacted_payload: AuditPayloadV1
    created_at: CanonicalTimestampV1

    @model_validator(mode="after")
    def _bind_identity(self) -> AuditEventV1:
        if not self.run_id:
            raise ValueError("run_id must be non-empty")
        return self


class AuditPayloadErrorV1(ValueError):
    """Closed rejection for a non-allowlisted, unbounded, or secret payload."""


def _require_field(payload: dict[str, str], key: str) -> str:
    """One required payload field; missing fields fail closed."""
    value = payload.get(key)
    if value is None:
        raise AuditPayloadErrorV1("audit payload is missing a required field")
    return value


def _reject_if_secret(text: str) -> None:
    """Raise the closed rejection when *text* contains a secret value.

    A lone surrogate (accepted by pydantic ``StrictStr``) cannot be
    encoded to UTF-8 for scanning; it fails closed with the
    canonical-encoding rejection instead of leaking a raw
    ``UnicodeEncodeError`` (T22.1 lesson: a closed rejection vocabulary
    must cover every input byte sequence).
    """
    try:
        contains_secret = _contains_secret(text)
    except UnicodeEncodeError:
        raise AuditPayloadErrorV1(
            "audit payload cannot be encoded canonically"
        ) from None
    if contains_secret:
        raise AuditPayloadErrorV1("audit payload contains a secret value")


def redact_payload(
    event_type: AuditEventTypeV1,
    payload: AuditPayloadInputV1,
    evidence_refs: tuple[str, ...] = (),
) -> AuditPayloadV1:
    """Redact and minimize one raw payload into the closed bounded variant.

    Raises ``AuditPayloadErrorV1`` with a stable reason on any violation:
    non-mapping payload, too many keys, a forbidden or non-allowlisted
    key, a missing required field, an empty or over-limit value, a secret
    value, or an evidence-reference violation.  No raw fact ever reaches
    storage.
    """
    if not isinstance(payload, dict):
        raise AuditPayloadErrorV1("audit payload must be a mapping")
    if len(payload) > _PAYLOAD_KEY_MAX:
        raise AuditPayloadErrorV1("audit payload exceeds the key bound")
    allowed = _ALLOWED_PAYLOAD_KEYS[event_type]
    for key, value in payload.items():
        if not isinstance(key, str) or key in _FORBIDDEN_PAYLOAD_KEYS:
            raise AuditPayloadErrorV1("audit payload contains a forbidden field")
        if key not in allowed:
            raise AuditPayloadErrorV1(
                "audit payload field is not allowlisted for this event type"
            )
        if not isinstance(value, str) or value == "":
            raise AuditPayloadErrorV1("audit payload value must be a non-empty string")
        if len(value) > _PAYLOAD_VALUE_MAX_CHARS:
            raise AuditPayloadErrorV1("audit payload value exceeds the bound")
        _reject_if_secret(value)
    if len(evidence_refs) > _EVIDENCE_REFS_MAX:
        raise AuditPayloadErrorV1("audit evidence references exceed the bound")
    for ref in evidence_refs:
        if (
            not isinstance(ref, str)
            or len(ref) < 1
            or len(ref) > _EVIDENCE_REF_MAX_CHARS
        ):
            raise AuditPayloadErrorV1(
                "audit evidence references must be 1..128 characters"
            )
        _reject_if_secret(ref)
    try:
        return _build_payload_variant(event_type, payload, evidence_refs)
    except ValidationError as exc:
        raise AuditPayloadErrorV1(
            "audit payload value is not a valid closed fact"
        ) from exc


def _build_payload_variant(
    event_type: AuditEventTypeV1,
    payload: AuditPayloadInputV1,
    evidence_refs: tuple[str, ...],
) -> AuditPayloadV1:
    """Construct the exact variant of one redacted payload."""
    if event_type == "LIFECYCLE":
        return LifecyclePayloadV1(
            kind="LIFECYCLE",
            status=cast(Literal["CREATED"], _require_field(payload, "status")),
            phase=cast(
                Literal[
                    "PREFLIGHT",
                    "BASELINE",
                    "AGENT_LOOP",
                    "FORMAL_VALIDATION",
                    "PERSISTENCE",
                ]
                | None,
                payload.get("phase"),
            ),
            evidence_refs=evidence_refs,
        )
    if event_type == "ACTION":
        return ActionPayloadV1(
            kind="ACTION",
            action_type=_require_field(payload, "action_type"),
            policy_decision=cast(
                Literal["ALLOW"], _require_field(payload, "policy_decision")
            ),
            evidence_refs=evidence_refs,
        )
    if event_type == "POLICY_DECISION":
        return PolicyDecisionPayloadV1(
            kind="POLICY_DECISION",
            decision=cast(Literal["ALLOW"], _require_field(payload, "decision")),
            reason_code=_require_field(payload, "reason_code"),
            evidence_refs=evidence_refs,
        )
    if event_type == "FINAL_WRITEBACK_APPROVAL":
        return FinalWritebackApprovalPayloadV1(
            kind="FINAL_WRITEBACK_APPROVAL",
            approval_id=_require_field(payload, "approval_id"),
            status=cast(Literal["PENDING"], _require_field(payload, "status")),
            evidence_refs=evidence_refs,
        )
    if event_type == "DISCLOSURE_GRANT":
        return DisclosureGrantPayloadV1(
            kind="DISCLOSURE_GRANT",
            grant_id=_require_field(payload, "grant_id"),
            status=cast(Literal["ACTIVE"], _require_field(payload, "status")),
            evidence_refs=evidence_refs,
        )
    if event_type == "DISCLOSURE_AUTHORIZATION":
        return DisclosureAuthorizationPayloadV1(
            kind="DISCLOSURE_AUTHORIZATION",
            category=cast(Literal["ROOT"], _require_field(payload, "category")),
            byte_count=_require_field(payload, "byte_count"),
            evidence_refs=evidence_refs,
        )
    if event_type == "CHECK_RESULT":
        return CheckResultPayloadV1(
            kind="CHECK_RESULT",
            check_kind=cast(
                Literal["TARGET_TESTS"], _require_field(payload, "check_kind")
            ),
            status=cast(Literal["PASS"], _require_field(payload, "status")),
            evidence_refs=evidence_refs,
        )
    if event_type == "RECOVERY":
        return RecoveryPayloadV1(
            kind="RECOVERY",
            transaction_id=_require_field(payload, "transaction_id"),
            disposition=cast(
                Literal["COMMITTED"], _require_field(payload, "disposition")
            ),
            evidence_refs=evidence_refs,
        )
    if event_type == "STOP_EVIDENCE":
        return StopEvidencePayloadV1(
            kind="STOP_EVIDENCE",
            reason_code=_require_field(payload, "reason_code"),
            evidence_refs=evidence_refs,
        )
    return LLMCallPayloadV1(
        kind="LLM_CALL",
        outcome=cast(Literal["COMPLETED"], _require_field(payload, "outcome")),
        evidence_refs=evidence_refs,
    )


def serialize_payload(payload: AuditPayloadV1) -> str:
    """The canonical JSON storage text of one redacted payload variant.

    Optional absent fields (e.g. the lifecycle phase) are omitted so the
    storage text stays inside the canonical JSON value domain (SPEC 0.1
    has no null value); parsing restores the same closed variant.
    """
    storage = {
        key: value for key, value in payload.model_dump().items() if value is not None
    }
    return canonical_json_bytes(storage).decode("utf-8")


def parse_payload(text: str) -> AuditPayloadV1:
    """Rebuild one payload variant from its canonical storage text."""
    raw = json.loads(text)
    if not isinstance(raw, dict):
        raise ValueError("stored audit payload must be a JSON object")
    kind = raw.get("kind")
    if not isinstance(kind, str):
        raise ValueError("stored audit payload is missing its kind")
    if kind == "LIFECYCLE":
        return LifecyclePayloadV1.model_validate(raw)
    if kind == "ACTION":
        return ActionPayloadV1.model_validate(raw)
    if kind == "POLICY_DECISION":
        return PolicyDecisionPayloadV1.model_validate(raw)
    if kind == "FINAL_WRITEBACK_APPROVAL":
        return FinalWritebackApprovalPayloadV1.model_validate(raw)
    if kind == "DISCLOSURE_GRANT":
        return DisclosureGrantPayloadV1.model_validate(raw)
    if kind == "DISCLOSURE_AUTHORIZATION":
        return DisclosureAuthorizationPayloadV1.model_validate(raw)
    if kind == "CHECK_RESULT":
        return CheckResultPayloadV1.model_validate(raw)
    if kind == "RECOVERY":
        return RecoveryPayloadV1.model_validate(raw)
    if kind == "STOP_EVIDENCE":
        return StopEvidencePayloadV1.model_validate(raw)
    if kind == "LLM_CALL":
        return LLMCallPayloadV1.model_validate(raw)
    raise ValueError(f"unknown stored audit payload kind {kind!r}")
