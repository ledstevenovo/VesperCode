"""T22.1 legacy step 22.A: bounded structured memory entry vocabulary.

Defines the closed memory kind/creator unions, the closed bounded source
union (user-visible text reference for project conventions; structured
approve/reject/config decision, ended-run, and check-result/fingerprint
facts for the control-plane kinds), the bounded immutable
``MemoryEntryV1`` value with exact workspace identity, creator, source,
timestamps, untrusted marker, and clear tombstone fields only (SPEC 7
MemoryEntry row), the canonical source storage round-trip, the
deterministic canonical byte accounting, and the closed mutation
result/error vocabulary.  No secret, permission, full-source-body,
audit, or governance field exists; storage, selection, and clearing
stay out of scope (GREEN-4).
"""

from __future__ import annotations

import json
from typing import Annotated, Literal, TypeAlias, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    model_validator,
)

from vespercode.canonical.json_v1 import CanonicalValueV1, canonical_json_bytes
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1

MemoryKindV1: TypeAlias = Literal[
    "PROJECT_CONVENTION",
    "USER_DECISION",
    "RUN_SUMMARY",
    "KNOWN_FAILURE",
]
"""SPEC 4.7 table: the closed memory kind vocabulary."""

MemoryCreatorV1: TypeAlias = Literal["USER", "CONTROL_PLANE", "MODEL"]
"""SPEC 4.7: the closed creator vocabulary.

``MODEL`` is a legal closed value so a model-originated write is
representable and rejectable; no write path ever persists it.
"""


class UserVisibleTextSourceV1(BaseModel):
    """PROJECT_CONVENTION content source: user-visible text reference.

    Carries only a bounded reference to the user-visible text, never the
    full text body (SPEC 4.7 "用户可见文本与来源"; data minimization).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["USER_VISIBLE_TEXT"]
    reference: StrictStr


class UserDecisionSourceV1(BaseModel):
    """USER_DECISION content source: approve/reject/config summary.

    The bounded structured summary of the real user decision (SPEC 4.7
    "批准、拒绝或配置决定的结构化摘要").
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["USER_DECISION"]
    decision: Literal["APPROVE", "REJECT", "CONFIG"]
    reference: StrictStr


class RunSummarySourceV1(BaseModel):
    """RUN_SUMMARY content source: ended-run structured status.

    Binds the ended run id and its terminal result; never a model
    free-form summary (SPEC 4.7 "不调用模型自由总结").
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["RUN_SUMMARY"]
    run_id: StrictStr
    result: Literal["SUCCEEDED", "STOPPED"]


class KnownFailureSourceV1(BaseModel):
    """KNOWN_FAILURE content source: check-result and fingerprint refs.

    Binds the structured check-result and stable failure fingerprint
    identities; the evidence bodies stay out of the memory store.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["KNOWN_FAILURE"]
    check_result_digest: StrictStr
    failure_fingerprint_digest: StrictStr


MemorySourceV1 = Annotated[
    UserVisibleTextSourceV1
    | UserDecisionSourceV1
    | RunSummarySourceV1
    | KnownFailureSourceV1,
    Field(discriminator="kind"),
]
"""The closed bounded memory content-source union (discriminated by kind)."""


class MemoryEntryV1(BaseModel):
    """One bounded immutable memory entry value (SPEC 7 MemoryEntry row).

    Fields are limited to the exact workspace identity, kind, summary,
    creator, source, timestamps, untrusted marker, and clear tombstone
    pair; secrets, permissions, full source bodies, and governance
    content have no representable field.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    entry_id: StrictStr
    workspace_identity: StrictStr
    kind: MemoryKindV1
    summary: Annotated[StrictStr, Field(min_length=1, max_length=2048)]
    creator: MemoryCreatorV1
    source: MemorySourceV1
    created_at: CanonicalTimestampV1
    updated_at: CanonicalTimestampV1
    untrusted: StrictBool
    cleared_at: CanonicalTimestampV1 | None = None
    clear_transaction_id: StrictStr | None = None

    @model_validator(mode="after")
    def _bind_timestamps(self) -> MemoryEntryV1:
        if self.updated_at.epoch_milliseconds < self.created_at.epoch_milliseconds:
            raise ValueError("updated_at must not precede created_at")
        if (self.cleared_at is None) != (self.clear_transaction_id is None):
            raise ValueError("clear tombstone fields must be set together")
        return self


MemoryErrorCodeV1: TypeAlias = Literal[
    "MEMORY_CREATOR_FORBIDDEN",
    "MEMORY_SCOPE_VIOLATION",
    "MEMORY_WRITE_NOT_AUTHORIZED",
    "MEMORY_CONTENT_REJECTED",
    "MEMORY_STORE_FAILED",
]
"""SPEC 4.7 errors plus the card's RED-mandated creator rejection code."""

MemoryMutationKindV1: TypeAlias = Literal[
    "CREATED",
    "CONFIRMED",
    "REPLAY",
    "EVENT_ID_REUSE_CONFLICT",
    "REJECTED",
    "FAILED",
]
"""The closed outcomes of one create/confirm command."""


class MemoryMutationResultV1(BaseModel):
    """One closed memory mutation outcome.

    ``error_code`` is present exactly on rejected/failed outcomes;
    ``entry`` is present on created/confirmed outcomes.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: MemoryMutationKindV1
    message: StrictStr
    error_code: MemoryErrorCodeV1 | None = None
    entry: MemoryEntryV1 | None = None


def _source_storage_value(source: MemorySourceV1) -> dict[str, CanonicalValueV1]:
    """One source variant's canonical storage shape (SPEC 0.1)."""
    if source.kind == "USER_VISIBLE_TEXT":
        return {"kind": "USER_VISIBLE_TEXT", "reference": source.reference}
    if source.kind == "USER_DECISION":
        return {
            "kind": "USER_DECISION",
            "decision": source.decision,
            "reference": source.reference,
        }
    if source.kind == "RUN_SUMMARY":
        return {
            "kind": "RUN_SUMMARY",
            "run_id": source.run_id,
            "result": source.result,
        }
    return {
        "kind": "KNOWN_FAILURE",
        "check_result_digest": source.check_result_digest,
        "failure_fingerprint_digest": source.failure_fingerprint_digest,
    }


def serialize_source(source: MemorySourceV1) -> str:
    """The canonical JSON storage text of one bounded source variant."""
    return canonical_json_bytes(_source_storage_value(source)).decode("utf-8")


def parse_source(text: str) -> MemorySourceV1:
    """Rebuild one source variant from its canonical storage text."""
    raw = json.loads(text)
    if not isinstance(raw, dict):
        raise ValueError("stored memory source must be a JSON object")
    kind = raw.get("kind")
    if kind == "USER_VISIBLE_TEXT":
        return UserVisibleTextSourceV1(
            kind="USER_VISIBLE_TEXT", reference=_require_field(raw, "reference")
        )
    if kind == "USER_DECISION":
        return UserDecisionSourceV1(
            kind="USER_DECISION",
            decision=cast(
                Literal["APPROVE", "REJECT", "CONFIG"],
                _require_field(raw, "decision"),
            ),
            reference=_require_field(raw, "reference"),
        )
    if kind == "RUN_SUMMARY":
        return RunSummarySourceV1(
            kind="RUN_SUMMARY",
            run_id=_require_field(raw, "run_id"),
            result=cast(Literal["SUCCEEDED", "STOPPED"], _require_field(raw, "result")),
        )
    if kind == "KNOWN_FAILURE":
        return KnownFailureSourceV1(
            kind="KNOWN_FAILURE",
            check_result_digest=_require_field(raw, "check_result_digest"),
            failure_fingerprint_digest=_require_field(
                raw, "failure_fingerprint_digest"
            ),
        )
    raise ValueError(f"unknown stored memory source kind {kind!r}")


def _require_field(raw: dict[str, object], field: str) -> str:
    """One required storage field; missing fields fail closed as ValueError."""
    value = raw.get(field)
    if value is None:
        raise ValueError(f"stored memory source is missing field {field!r}")
    return str(value)


def canonical_memory_byte_count(entry: MemoryEntryV1) -> int:
    """The canonical UTF-8 content bytes of one memory entry.

    Counts the bounded content that flows into a context projection
    (summary plus the stored source attribution text) in strict UTF-8,
    so the same entry always contributes the same byte count.
    """
    return len(entry.summary.encode("utf-8")) + len(
        serialize_source(entry.source).encode("utf-8")
    )
