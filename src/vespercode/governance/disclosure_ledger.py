"""T15.2 legacy step 15.E: transactional disclosure authorization ledger.

``DisclosureLedger.authorize`` revalidates one prepared request against
the current active Grant — Grant/subject identity, frozen profile facts,
source categories/scopes, revocation/expiry, request identity, and the
cumulative byte budget — inside one immediate transaction, then commits
exactly one body-free authorization record and one byte charge for an
exact authorized request.  Budget races, stale/revoked Grants,
scope/category drift, and replay conflicts charge zero; the event-scoped
T07.3 ledger makes exact replay free and event reuse a conflict.  Final
registry edits, Grant decisions/revocation, request serialization/calls,
body storage, and refunds remain out of scope (GREEN-4).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    StrictStr,
    field_validator,
)

from src.vespercode.canonical.digest import domain_digest
from src.vespercode.canonical.json_v1 import CanonicalValueV1, canonical_json_bytes
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.governance.disclosure_decision import (
    parse_categories,
    parse_scope_sequence,
)
from src.vespercode.governance.disclosure_scope import scope_matches
from src.vespercode.governance.request_sources import (
    RequestSourceV1,
    SourceProjectionV1,
)
from src.vespercode.storage.connection import ControlDatabase
from src.vespercode.storage.idempotency import IdempotencyRepository

_AUTHORIZE_EVENT_SCOPE = "disclosure_authorize"
_DIGEST_RE = re.compile(r"[0-9a-f]{64}")

DisclosureAuthorizationKindV1: TypeAlias = Literal[
    "AUTHORIZED",
    "REPLAY",
    "REPLAY_CONFLICT",
    "GRANT_NOT_FOUND",
    "SUBJECT_MISMATCH",
    "EXPIRED",
    "REVOKED",
    "EXHAUSTED",
    "DISCLOSURE_SCOPE_EXCEEDED",
    "DISCLOSURE_BUDGET_EXCEEDED",
]
"""The closed outcomes of one authorization command."""


class AuthorizePreparedRequestV1(BaseModel):
    """One closed prepared-request authorization command.

    Carries only the request's derived facts (digest, body-free source
    projection, charge, frozen profile identities, event, and time); the
    ledger revalidates every fact against the active Grant subject before
    any charge or record.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    authorization_record_id: StrictStr
    grant_id: StrictStr
    request_digest: StrictStr
    actual_sources: Annotated[
        tuple[RequestSourceV1, ...], Field(min_length=1, max_length=1024)
    ]
    charge_bytes: Annotated[int, Strict(), Field(ge=1, le=65536)]
    llm_profile_digest: StrictStr
    provider: StrictStr
    endpoint_id: StrictStr
    model: StrictStr
    request_serializer_version: StrictStr
    redaction_profile_id: StrictStr
    event_id: StrictStr
    authorized_at: CanonicalTimestampV1

    @field_validator("request_digest", "llm_profile_digest")
    @classmethod
    def _digests_have_exact_form(cls, value: str) -> str:
        if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
            raise ValueError("must be exactly 64 lowercase hexadecimal characters")
        return value


class DisclosureAuthorizationRecordV1(BaseModel):
    """SPEC §4.4.4: the durable body-free per-request authorization record.

    The record proves the exact OpenAI request was authorized before the
    call; it stores only verified source indexes/paths/digests/byte counts
    (never segment content) and no refund or body column.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    authorization_record_id: StrictStr
    grant_id: StrictStr
    grant_subject_digest: StrictStr
    llm_profile_digest: StrictStr
    provider: StrictStr
    endpoint_id: StrictStr
    model: StrictStr
    request_serializer_version: StrictStr
    request_digest: StrictStr
    actual_sources: tuple[RequestSourceV1, ...]
    canonical_byte_count: int
    redaction_profile_id: StrictStr
    created_at: CanonicalTimestampV1


class DisclosureAuthorizationOutcomeV1(BaseModel):
    """One closed authorization outcome; ``record`` is present on AUTHORIZED."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: DisclosureAuthorizationKindV1
    message: StrictStr
    record: DisclosureAuthorizationRecordV1 | None = None


class _AuthorizationRollback(Exception):
    """Internal sentinel: roll back the transaction and return the outcome.

    The immediate-transaction context manager commits on clean exit and
    rolls back only on an exception; every zero-charge failure must not
    persist the reserved idempotency event or any partial charge, so the
    sentinel rolls the whole transaction back before the outcome returns.
    """

    def __init__(self, outcome: DisclosureAuthorizationOutcomeV1) -> None:
        super().__init__(outcome.message)
        self.outcome = outcome


def _authorize_result_digest(command: AuthorizePreparedRequestV1) -> str:
    """The §0.1 identity of the recorded AUTHORIZED outcome."""
    return domain_digest(
        "DisclosureAuthorizationResultV1",
        1,
        {
            "kind": "AUTHORIZED",
            "authorization_record_id": command.authorization_record_id,
            "grant_id": command.grant_id,
            "request_digest": command.request_digest,
        },
    )


def _source_to_canonical(source: RequestSourceV1) -> dict[str, CanonicalValueV1]:
    """One body-free source index in canonical storage shape (SPEC §4.4.4)."""
    path: CanonicalValueV1
    if source.source_path.kind == "ABSENT":
        path = {"kind": "ABSENT"}
    else:
        path = {"kind": "PRESENT", "value": source.source_path.value.value}
    return {
        "message_index": source.message_index,
        "segment_index": source.segment_index,
        "source_category": source.source_category,
        "source_path": path,
        "content_digest": source.content_digest,
        "byte_count": source.byte_count,
    }


def serialize_actual_sources(sources: SourceProjectionV1) -> str:
    """The canonical JSON storage form of the body-free source projection."""
    return canonical_json_bytes(
        tuple(_source_to_canonical(source) for source in sources)
    ).decode("utf-8")


class DisclosureLedger:
    """Transaction-bound authorization and cumulative-byte accounting."""

    def __init__(self, database: ControlDatabase, database_path: Path) -> None:
        self._database = database
        self._database_path = database_path
        self._ledger = IdempotencyRepository(database)

    @property
    def database(self) -> ControlDatabase:
        """The owned control database (transaction access for callers)."""
        return self._database

    @property
    def database_path(self) -> Path:
        """The on-disk control database path (per-thread connection seam).

        sqlite3 connections are thread-bound, so concurrency tests open
        one connection per worker on the same file (T07.2 precedent).
        """
        return self._database_path

    def authorize(
        self,
        command: AuthorizePreparedRequestV1,
    ) -> DisclosureAuthorizationOutcomeV1:
        """Revalidate and atomically charge exactly one prepared request.

        One immediate transaction serializes competing writers; the
        cumulative-budget compare-and-update lets exactly one concurrent
        charge win, and the event-scoped idempotency ledger makes exact
        replay free and event reuse a conflict with zero charge.
        """
        try:
            with self._database.immediate_transaction() as tx:
                recorded = self._ledger.record_or_replay(
                    tx,
                    _AUTHORIZE_EVENT_SCOPE,
                    command.event_id,
                    command.request_digest,
                    _authorize_result_digest(command),
                )
                if recorded.kind == "REPLAY":
                    return DisclosureAuthorizationOutcomeV1(
                        kind="REPLAY",
                        message="authorization event already recorded",
                    )
                if recorded.kind == "EVENT_ID_REUSE_CONFLICT":
                    return DisclosureAuthorizationOutcomeV1(
                        kind="REPLAY_CONFLICT",
                        message="authorization event reused for a different request",
                    )
                grant = tx.execute(
                    "SELECT grant_id, subject_digest, run_id, wait_id,"
                    " created_at, consumed_bytes, status FROM disclosure_grants"
                    " WHERE grant_id = ?",
                    (command.grant_id,),
                ).fetchone()
                if grant is None:
                    raise _AuthorizationRollback(
                        DisclosureAuthorizationOutcomeV1(
                            kind="GRANT_NOT_FOUND", message="grant does not exist"
                        )
                    )
                grant_subject_digest = str(grant[1])
                grant_status = str(grant[6])
                subject_row = tx.execute(
                    "SELECT subject_digest, run_id, llm_profile_digest,"
                    " provider, endpoint_id, model, request_serializer_version,"
                    " allowed_source_paths, allowed_source_categories,"
                    " redaction_profile_id, cumulative_byte_budget, expires_at"
                    " FROM disclosure_grant_subjects"
                    " WHERE subject_digest = ?",
                    (grant_subject_digest,),
                ).fetchone()
                if subject_row is None:
                    raise _AuthorizationRollback(
                        DisclosureAuthorizationOutcomeV1(
                            kind="SUBJECT_MISMATCH",
                            message="grant subject row does not exist",
                        )
                    )
                expires_at = CanonicalTimestampV1.parse(str(subject_row[11]))
                if grant_status == "REVOKED":
                    raise _AuthorizationRollback(
                        DisclosureAuthorizationOutcomeV1(
                            kind="REVOKED", message="grant already revoked"
                        )
                    )
                if grant_status == "EXHAUSTED":
                    raise _AuthorizationRollback(
                        DisclosureAuthorizationOutcomeV1(
                            kind="EXHAUSTED", message="grant already exhausted"
                        )
                    )
                if (
                    command.authorized_at.epoch_milliseconds
                    > expires_at.epoch_milliseconds
                ):
                    raise _AuthorizationRollback(
                        DisclosureAuthorizationOutcomeV1(
                            kind="EXPIRED", message="grant already expired"
                        )
                    )
                if grant_status == "EXPIRED":
                    raise _AuthorizationRollback(
                        DisclosureAuthorizationOutcomeV1(
                            kind="EXPIRED", message="grant already expired"
                        )
                    )
                if self._record_facts_drift(command, subject_row):
                    raise _AuthorizationRollback(
                        DisclosureAuthorizationOutcomeV1(
                            kind="SUBJECT_MISMATCH",
                            message="prepared request facts drift from the subject",
                        )
                    )
                self._revalidate_sources(command, subject_row)
                budget = int(subject_row[10])
                consumed = int(grant[5])
                if consumed + command.charge_bytes > budget:
                    raise _AuthorizationRollback(
                        DisclosureAuthorizationOutcomeV1(
                            kind="DISCLOSURE_BUDGET_EXCEEDED",
                            message="cumulative budget would be exceeded",
                        )
                    )
                updated = tx.execute(
                    "UPDATE disclosure_grants SET"
                    " consumed_bytes = consumed_bytes + ?,"
                    " status = CASE WHEN consumed_bytes + ? >= ?"
                    " THEN 'EXHAUSTED' ELSE 'ACTIVE' END"
                    " WHERE grant_id = ? AND status = 'ACTIVE'"
                    " AND consumed_bytes + ? <= ?",
                    (
                        command.charge_bytes,
                        command.charge_bytes,
                        budget,
                        command.grant_id,
                        command.charge_bytes,
                        budget,
                    ),
                ).rowcount
                if updated != 1:
                    raise _AuthorizationRollback(
                        DisclosureAuthorizationOutcomeV1(
                            kind="DISCLOSURE_BUDGET_EXCEEDED",
                            message="budget race lost: another charge won",
                        )
                    )
                record = DisclosureAuthorizationRecordV1(
                    schema_version=1,
                    authorization_record_id=command.authorization_record_id,
                    grant_id=command.grant_id,
                    grant_subject_digest=grant_subject_digest,
                    llm_profile_digest=command.llm_profile_digest,
                    provider=command.provider,
                    endpoint_id=command.endpoint_id,
                    model=command.model,
                    request_serializer_version=command.request_serializer_version,
                    request_digest=command.request_digest,
                    actual_sources=command.actual_sources,
                    canonical_byte_count=command.charge_bytes,
                    redaction_profile_id=command.redaction_profile_id,
                    created_at=command.authorized_at,
                )
                tx.execute(
                    "INSERT INTO disclosure_authorizations"
                    " (authorization_id, grant_id, grant_subject_digest,"
                    " llm_profile_digest, provider, endpoint_id, model,"
                    " request_serializer_version, request_digest,"
                    " actual_sources, canonical_byte_count,"
                    " redaction_profile_id, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record.authorization_record_id,
                        record.grant_id,
                        record.grant_subject_digest,
                        record.llm_profile_digest,
                        record.provider,
                        record.endpoint_id,
                        record.model,
                        record.request_serializer_version,
                        record.request_digest,
                        serialize_actual_sources(record.actual_sources),
                        record.canonical_byte_count,
                        record.redaction_profile_id,
                        record.created_at.value,
                    ),
                )
                return DisclosureAuthorizationOutcomeV1(
                    kind="AUTHORIZED",
                    message="prepared request authorized",
                    record=record,
                )
        except _AuthorizationRollback as failure:
            if failure.outcome.kind == "EXPIRED":
                # Status hygiene: the expired Grant transitions
                # ACTIVE -> EXPIRED in its own idempotent transaction so
                # the zero-charge authorization failure never persists the
                # event, charge, or record while the status stays truthful.
                self._settle_expired(command.grant_id)
            return failure.outcome

    def _settle_expired(self, grant_id: str) -> None:
        """Idempotently transition one ACTIVE Grant to EXPIRED.

        Runs in its own immediate transaction after the authorization
        transaction rolled back, so the status settlement is durable while
        the failed authorization persists nothing else.
        """
        with self._database.immediate_transaction() as tx:
            tx.execute(
                "UPDATE disclosure_grants SET status = 'EXPIRED'"
                " WHERE grant_id = ? AND status = 'ACTIVE'",
                (grant_id,),
            )

    def _record_facts_drift(
        self,
        command: AuthorizePreparedRequestV1,
        subject_row: sqlite3.Row,
    ) -> bool:
        """Whether the command's profile facts drift from the subject row."""
        return (
            command.llm_profile_digest != str(subject_row[2])
            or command.provider != str(subject_row[3])
            or command.endpoint_id != str(subject_row[4])
            or command.model != str(subject_row[5])
            or command.request_serializer_version != str(subject_row[6])
            or command.redaction_profile_id != str(subject_row[9])
        )

    def _revalidate_sources(
        self,
        command: AuthorizePreparedRequestV1,
        subject_row: sqlite3.Row,
    ) -> None:
        """Revalidate every source against the frozen categories/scopes.

        Each segment must hit the subject's allowed categories; every
        path-bearing segment must additionally hit at least one allowed
        scope by the exact §4.4.3 matching algorithm.
        """
        categories = parse_categories(str(subject_row[8]))
        scopes = parse_scope_sequence(str(subject_row[7]))
        for source in command.actual_sources:
            if source.source_category not in categories:
                raise _AuthorizationRollback(
                    DisclosureAuthorizationOutcomeV1(
                        kind="DISCLOSURE_SCOPE_EXCEEDED",
                        message=(
                            f"source category {source.source_category} lies "
                            "outside the grant"
                        ),
                    )
                )
            if source.source_path.kind == "PRESENT" and not any(
                scope_matches(scope, source.source_path.value) for scope in scopes
            ):
                raise _AuthorizationRollback(
                    DisclosureAuthorizationOutcomeV1(
                        kind="DISCLOSURE_SCOPE_EXCEEDED",
                        message=(
                            f"source path {source.source_path.value.value!r} lies "
                            "outside the grant scopes"
                        ),
                    )
                )
