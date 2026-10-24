"""Route B / B2: v2 disclosure grant/authorization records and pure policy.

The v1 disclosure plane (``governance/disclosure_ledger.py``,
``governance/disclosure_scope.py``, ``governance/disclosure_decision.py``,
``governance/request_sources.py``) closes every authorization over
SHA-256 request and subject digests in the legacy control database.
Those modules remain untouched read-only legacy; nothing here imports
them.

The v2 disclosure control plane keys every record by opaque IDs and
non-negative revisions instead.  A grant is created ``PENDING`` from an
approved disclosure subject (``disclosure_id``) and must be explicitly
activated by the user before it authorizes anything; it carries the
harness ``run_id``, the bound reference profile id/revision, an ISO-8601
expiry, a bounded byte budget, the allowed source categories, and the
allowed path scopes.  A per-request authorization is keyed by its own
``authorization_id`` plus the grant/run/request/endpoint references, its
requested sources, its byte charge, and a one-shot ``AUTHORIZED`` ->
``CONSUMED`` state.  No digest of any payload is computed, stored, or
consulted: identities are opaque references, bindings are control-key
equality checks, and source scopes are matched lexically.

The module is standard-library only and importable without any
filesystem, network, LLM, or v1 dependency.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from typing import Any

DISCLOSURE_GRANT_STATUSES_V2 = frozenset(
    {"PENDING", "ACTIVE", "REVOKED", "EXPIRED", "EXHAUSTED"}
)
"""The closed grant lifecycle: created ``PENDING``, activated by the
user to ``ACTIVE``, and terminally ``REVOKED``/``EXPIRED``/``EXHAUSTED``."""

DISCLOSURE_AUTHORIZATION_STATUSES_V2 = frozenset({"AUTHORIZED", "CONSUMED"})
"""The closed per-request authorization lifecycle: ``AUTHORIZED`` by a
successful charge, then one-shot ``CONSUMED`` by the provider call."""

DISCLOSURE_SOURCE_CATEGORIES_V2 = frozenset(
    {
        "HARNESS_PROTOCOL",
        "TASK",
        "FILE_CONTENT",
        "TOOL_RESULT",
        "MEMORY",
        "FEEDBACK",
    }
)
"""The source categories a request may cite (the v1 control vocabulary,
kept identical so existing review surfaces stay meaningful)."""

PATH_BEARING_SOURCE_CATEGORIES_V2 = frozenset({"FILE_CONTENT"})
"""The only categories whose sources carry a path."""

DISCLOSURE_SCOPE_KINDS_V2 = frozenset({"ROOT", "FILE", "DIRECTORY"})

MIN_DISCLOSURE_CHARGE_BYTES_V2 = 1
MAX_DISCLOSURE_CHARGE_BYTES_V2 = 65536
MIN_DISCLOSURE_BUDGET_BYTES_V2 = 1
MAX_DISCLOSURE_BUDGET_BYTES_V2 = 1_048_576
MAX_DISCLOSURE_SCOPES_V2 = 500
MAX_DISCLOSURE_SOURCES_V2 = 1024

DISCLOSURE_AUTHORIZATION_OUTCOMES_V2 = frozenset(
    {
        "AUTHORIZED",
        "REPLAY",
        "REPLAY_CONFLICT",
        "GRANT_NOT_FOUND",
        "GRANT_PENDING",
        "GRANT_REVOKED",
        "GRANT_EXPIRED",
        "GRANT_EXHAUSTED",
        "RUN_MISMATCH",
        "ENDPOINT_NOT_FOUND",
        "PROFILE_MISMATCH",
        "SCOPE_EXCEEDED",
        "BUDGET_EXCEEDED",
    }
)
"""The closed outcomes of one authorization command."""

DISCLOSURE_CONSUME_OUTCOMES_V2 = frozenset(
    {"CONSUMED", "NOT_AUTHORIZED", "GRANT_NOT_ACTIVE"}
)
"""The closed outcomes of one authorization consume command.

``CONSUMED``: the one-shot ``AUTHORIZED`` -> ``CONSUMED`` transition
committed.  ``NOT_AUTHORIZED``: no such authorization, a binding
mismatch, or the status is no longer ``AUTHORIZED`` — nothing was
consumed.  ``GRANT_NOT_ACTIVE``: the grant is revoked or expired as of
the consume-time clock — nothing was consumed.
"""

_OUTCOME_MESSAGES: dict[str, str] = {
    "AUTHORIZED": "the request was authorized and charged",
    "REPLAY": (
        "the request was already authorized; the original "
        "authorization is returned with no new charge"
    ),
    "REPLAY_CONFLICT": (
        "the request id was already authorized with a different payload"
    ),
    "GRANT_NOT_FOUND": "no disclosure grant exists for the given id",
    "GRANT_PENDING": "the grant awaits explicit user approval",
    "GRANT_REVOKED": "the grant was revoked",
    "GRANT_EXPIRED": "the grant expired",
    "GRANT_EXHAUSTED": "the grant's byte budget is exhausted",
    "RUN_MISMATCH": "the request run does not match the grant run",
    "ENDPOINT_NOT_FOUND": "the provider endpoint is unknown",
    "PROFILE_MISMATCH": (
        "the endpoint profile binding does not match the grant's "
        "reference profile revision"
    ),
    "SCOPE_EXCEEDED": (
        "a requested source is outside the grant's categories and path scopes"
    ),
    "BUDGET_EXCEEDED": "the charge would exceed the grant's remaining byte budget",
}

_MAX_IDENTIFIER_BYTES = 256
_MAX_PATH_BYTES = 512


def _identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    if len(value.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
        raise ValueError(f"{field_name} is too long")
    return value


def _revision(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _timestamp(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty timestamp")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    return value


def _canonical_path(value: str, field_name: str) -> str:
    """A workspace-relative POSIX path, validated lexically.

    Mirrors the lexical rules of the v2 workspace boundary (no absolute
    paths, no backslashes, no drive/stream separators, no ``.``/``..``
    or empty segments, no control characters); a scope or source path
    is matched against these exact spellings, never touched to disk by
    this module.
    """

    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    if len(value.encode("utf-8")) > _MAX_PATH_BYTES:
        raise ValueError(f"{field_name} is too long")
    if any(ord(char) < 0x20 for char in value):
        raise ValueError(f"{field_name} must not contain control characters")
    if "\\" in value:
        raise ValueError(f"{field_name} must use '/' separators only")
    if ":" in value:
        raise ValueError(f"{field_name} must not contain a drive or stream separator")
    if value.startswith("/"):
        raise ValueError(f"{field_name} must be relative, not absolute")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(
            f"{field_name} must be canonical: no empty, '.', or '..' segments"
        )
    return value


def _strict_mapping(data: object, names: tuple[str, ...]) -> dict[str, Any]:
    """Require exactly the given fields: unknown or missing keys reject.

    A v1-shaped digest payload (``subject_digest``, ``request_digest``,
    ``schema_version``) is rejected here as unknown fields, never
    accepted as v2 authority.
    """

    if not isinstance(data, Mapping):
        raise ValueError("record must be a mapping of exact fields")
    keys = set(data.keys())
    unknown = sorted(str(key) for key in keys - set(names))
    if unknown:
        raise ValueError(f"unknown fields: {unknown}")
    missing = sorted(name for name in names if name not in keys)
    if missing:
        raise ValueError(f"missing fields: {missing}")
    return {name: data[name] for name in names}


class DisclosureScopeErrorV2(ValueError):
    """Fail-closed rejection of an out-of-scope request source."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(f"{error_code}: {message}")
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class DisclosurePathScopeV2:
    """One allowed disclosure path scope.

    ``ROOT`` carries no path and matches any canonical path;
    ``FILE(path)`` matches its exact path; ``DIRECTORY(path)`` matches
    the path itself and true descendants only (``path + "/"`` — never a
    mere string prefix).
    """

    kind: str
    path: str

    def __post_init__(self) -> None:
        if self.kind not in DISCLOSURE_SCOPE_KINDS_V2:
            raise ValueError(
                f"scope kind must be one of {sorted(DISCLOSURE_SCOPE_KINDS_V2)}"
            )
        if self.kind == "ROOT":
            if self.path != "":
                raise ValueError("a ROOT scope carries no path")
        else:
            object.__setattr__(self, "path", _canonical_path(self.path, "scope path"))


@dataclass(frozen=True, slots=True)
class DisclosureSourceV2:
    """One requested authorization source: a category and maybe a path.

    ``FILE_CONTENT`` sources require a canonical path; every other
    category carries none.
    """

    category: str
    path: str | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.category, str)
            or self.category not in DISCLOSURE_SOURCE_CATEGORIES_V2
        ):
            raise ValueError(
                "source category must be one of "
                f"{sorted(DISCLOSURE_SOURCE_CATEGORIES_V2)}"
            )
        if self.category in PATH_BEARING_SOURCE_CATEGORIES_V2:
            if self.path is None:
                raise ValueError(f"{self.category} sources require a path")
            object.__setattr__(self, "path", _canonical_path(self.path, "source path"))
        elif self.path is not None:
            raise ValueError(f"{self.category} sources carry no path")


def canonicalize_disclosure_scopes(
    scopes: Any,
) -> tuple[DisclosurePathScopeV2, ...]:
    """Validate and order a grant's path scopes deterministically.

    At least one scope is required; duplicates reject; a ``ROOT`` scope
    must be the only scope; the result is ordered ``ROOT`` < ``FILE`` <
    ``DIRECTORY`` and then by path.
    """

    validated: list[DisclosurePathScopeV2] = []
    for scope in scopes:
        if not isinstance(scope, DisclosurePathScopeV2):
            raise ValueError("each scope must be a DisclosurePathScopeV2")
        validated.append(scope)
    if not validated:
        raise ValueError("at least one disclosure scope is required")
    if len(validated) > MAX_DISCLOSURE_SCOPES_V2:
        raise ValueError("too many disclosure scopes")
    if any(scope.kind == "ROOT" for scope in validated) and len(validated) != 1:
        raise ValueError("a ROOT scope must be the only scope")
    if len(set(validated)) != len(validated):
        raise ValueError("duplicate disclosure scopes are not allowed")
    order = {"ROOT": 0, "FILE": 1, "DIRECTORY": 2}
    return tuple(sorted(validated, key=lambda scope: (order[scope.kind], scope.path)))


def canonicalize_disclosure_categories(categories: Any) -> tuple[str, ...]:
    """Validate and order a grant's allowed source categories."""

    validated: list[str] = []
    for category in categories:
        if (
            not isinstance(category, str)
            or category not in DISCLOSURE_SOURCE_CATEGORIES_V2
        ):
            raise ValueError(
                "allowed categories must come from "
                f"{sorted(DISCLOSURE_SOURCE_CATEGORIES_V2)}"
            )
        validated.append(category)
    if not validated:
        raise ValueError("at least one allowed source category is required")
    if len(set(validated)) != len(validated):
        raise ValueError("duplicate source categories are not allowed")
    return tuple(sorted(validated))


def canonicalize_disclosure_sources(
    sources: Any,
) -> tuple[DisclosureSourceV2, ...]:
    """Validate the requested sources of one authorization command."""

    validated: list[DisclosureSourceV2] = []
    for source in sources:
        if not isinstance(source, DisclosureSourceV2):
            raise ValueError("each source must be a DisclosureSourceV2")
        validated.append(source)
    if not validated:
        raise ValueError("at least one request source is required")
    if len(validated) > MAX_DISCLOSURE_SOURCES_V2:
        raise ValueError("too many request sources")
    return tuple(validated)


def disclosure_scope_matches(
    path: str, allowed_scopes: tuple[DisclosurePathScopeV2, ...]
) -> bool:
    """True when the canonical path falls inside one allowed scope."""

    canonical = _canonical_path(path, "path")
    for scope in allowed_scopes:
        if scope.kind == "ROOT":
            return True
        if scope.kind == "FILE" and canonical == scope.path:
            return True
        if scope.kind == "DIRECTORY" and (
            canonical == scope.path or canonical.startswith(scope.path + "/")
        ):
            return True
    return False


def check_disclosure_request_sources(
    allowed_categories: tuple[str, ...],
    allowed_scopes: tuple[DisclosurePathScopeV2, ...],
    sources: tuple[DisclosureSourceV2, ...],
) -> None:
    """Fail closed when a requested source is outside the grant.

    Every source's category must be one of the granted categories, and
    every path-bearing source must fall inside a granted path scope.
    """

    granted = set(allowed_categories)
    for source in sources:
        if source.category not in granted:
            raise DisclosureScopeErrorV2(
                "SOURCE_CATEGORY",
                "the source category is not granted",
            )
        if source.path is not None and not disclosure_scope_matches(
            source.path, allowed_scopes
        ):
            raise DisclosureScopeErrorV2(
                "SOURCE_PATH",
                "the source path is outside the granted scopes",
            )


def authorization_payload_key(
    run_id: str,
    endpoint_id: str,
    charge_bytes: int,
    sources: tuple[DisclosureSourceV2, ...],
) -> tuple[Any, ...]:
    """The replay identity of one authorization command.

    Two commands with the same ``(run_id, endpoint_id, charge_bytes,
    sources)`` facts are the same request; a different fact under the
    same request id is a replay conflict.
    """

    return (run_id, endpoint_id, charge_bytes, tuple(sources))


@dataclass(frozen=True, slots=True)
class DisclosureGrantRecordV2:
    """One disclosure grant keyed by opaque control references.

    The grant binds the approved disclosure subject
    (``disclosure_id``), the harness ``run_id``, and the reference
    profile id/revision whose toolchain configuration the provider
    endpoint must match.  ``expires_at`` is a plain ISO-8601 timestamp,
    ``byte_budget``/``consumed_bytes`` are bounded integers, and the
    allowed categories/path scopes are canonicalized.  No digest of
    the granted subject or of any request exists here.
    """

    grant_id: str
    disclosure_id: str
    run_id: str
    reference_profile_id: str
    reference_profile_revision: int
    expires_at: str
    byte_budget: int
    consumed_bytes: int
    allowed_source_categories: tuple[str, ...]
    allowed_source_paths: tuple[DisclosurePathScopeV2, ...]
    status: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "grant_id", _identifier(self.grant_id, "grant_id"))
        object.__setattr__(
            self, "disclosure_id", _identifier(self.disclosure_id, "disclosure_id")
        )
        object.__setattr__(self, "run_id", _identifier(self.run_id, "run_id"))
        object.__setattr__(
            self,
            "reference_profile_id",
            _identifier(self.reference_profile_id, "reference_profile_id"),
        )
        object.__setattr__(
            self,
            "reference_profile_revision",
            _revision(self.reference_profile_revision, "reference_profile_revision"),
        )
        object.__setattr__(
            self, "expires_at", _timestamp(self.expires_at, "expires_at")
        )
        if isinstance(self.byte_budget, bool) or not isinstance(self.byte_budget, int):
            raise ValueError("byte_budget must be an integer")
        if not (
            MIN_DISCLOSURE_BUDGET_BYTES_V2
            <= self.byte_budget
            <= MAX_DISCLOSURE_BUDGET_BYTES_V2
        ):
            raise ValueError("byte_budget is outside the bounded range")
        if (
            isinstance(self.consumed_bytes, bool)
            or not isinstance(self.consumed_bytes, int)
            or self.consumed_bytes < 0
        ):
            raise ValueError("consumed_bytes must be a non-negative integer")
        if self.consumed_bytes > self.byte_budget:
            raise ValueError("consumed_bytes exceeds the grant's byte budget")
        object.__setattr__(
            self,
            "allowed_source_categories",
            canonicalize_disclosure_categories(self.allowed_source_categories),
        )
        object.__setattr__(
            self,
            "allowed_source_paths",
            canonicalize_disclosure_scopes(self.allowed_source_paths),
        )
        if self.status not in DISCLOSURE_GRANT_STATUSES_V2:
            raise ValueError(
                f"status must be one of {sorted(DISCLOSURE_GRANT_STATUSES_V2)}"
            )


@dataclass(frozen=True, slots=True)
class DisclosureAuthorizationRecordV2:
    """One per-request disclosure authorization.

    The record carries the authorization's own opaque id, the
    grant/run/request/endpoint control references it is bound to, the
    bounded byte charge committed by the ledger, its requested sources,
    and its one-shot ``AUTHORIZED``/``CONSUMED`` state.
    """

    authorization_id: str
    grant_id: str
    run_id: str
    request_id: str
    endpoint_id: str
    charge_bytes: int
    status: str
    sources: tuple[DisclosureSourceV2, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "authorization_id",
            _identifier(self.authorization_id, "authorization_id"),
        )
        object.__setattr__(self, "grant_id", _identifier(self.grant_id, "grant_id"))
        object.__setattr__(self, "run_id", _identifier(self.run_id, "run_id"))
        object.__setattr__(
            self, "request_id", _identifier(self.request_id, "request_id")
        )
        object.__setattr__(
            self, "endpoint_id", _identifier(self.endpoint_id, "endpoint_id")
        )
        if isinstance(self.charge_bytes, bool) or not isinstance(
            self.charge_bytes, int
        ):
            raise ValueError("charge_bytes must be an integer")
        if not (
            MIN_DISCLOSURE_CHARGE_BYTES_V2
            <= self.charge_bytes
            <= MAX_DISCLOSURE_CHARGE_BYTES_V2
        ):
            raise ValueError("charge_bytes is outside the bounded range")
        if self.status not in DISCLOSURE_AUTHORIZATION_STATUSES_V2:
            raise ValueError(
                f"status must be one of {sorted(DISCLOSURE_AUTHORIZATION_STATUSES_V2)}"
            )
        object.__setattr__(
            self,
            "sources",
            canonicalize_disclosure_sources(self.sources),
        )


def disclosure_outcome_message(kind: str) -> str:
    """The closed static message for one authorization outcome kind.

    Messages are fixed spellings from this module, so no request
    content, secret, or provider detail can ever enter an outcome.
    """

    try:
        return _OUTCOME_MESSAGES[kind]
    except KeyError as exc:
        raise ValueError(
            "outcome kind must be one of "
            f"{sorted(DISCLOSURE_AUTHORIZATION_OUTCOMES_V2)}"
        ) from exc


_CONSUME_MESSAGES: dict[str, str] = {
    "CONSUMED": "the authorization was consumed one-shot",
    "NOT_AUTHORIZED": (
        "the authorization is missing, misbound, or not in the AUTHORIZED state"
    ),
    "GRANT_NOT_ACTIVE": "the grant is not active or is expired",
}


def disclosure_consume_outcome_message(kind: str) -> str:
    """The closed static message for one consume outcome kind."""

    try:
        return _CONSUME_MESSAGES[kind]
    except KeyError as exc:
        raise ValueError(
            "consume outcome kind must be one of "
            f"{sorted(DISCLOSURE_CONSUME_OUTCOMES_V2)}"
        ) from exc


@dataclass(frozen=True, slots=True)
class DisclosureConsumeOutcomeV2:
    """The closed outcome of one authorization consume command.

    ``CONSUMED`` commits the one-shot ``AUTHORIZED`` -> ``CONSUMED``
    transition; ``NOT_AUTHORIZED`` and ``GRANT_NOT_ACTIVE`` consume
    nothing.  ``message`` is always the closed static message of
    ``kind``.
    """

    kind: str
    message: str

    def __post_init__(self) -> None:
        if self.kind not in DISCLOSURE_CONSUME_OUTCOMES_V2:
            raise ValueError(
                "consume outcome kind must be one of "
                f"{sorted(DISCLOSURE_CONSUME_OUTCOMES_V2)}"
            )
        if self.message != _CONSUME_MESSAGES[self.kind]:
            raise ValueError(
                "consume outcome message must be the closed static message of its kind"
            )


@dataclass(frozen=True, slots=True)
class DisclosureAuthorizationOutcomeV2:
    """The outcome of one authorization command.

    ``kind`` is the closed outcome vocabulary; ``authorization`` is the
    committed record exactly for ``AUTHORIZED``/``REPLAY`` and ``None``
    otherwise; ``consumed_bytes`` reports the grant's charge state
    after the command (unchanged for every zero-charge rejection);
    ``message`` is always the closed static message of ``kind``.
    """

    kind: str
    authorization: DisclosureAuthorizationRecordV2 | None
    consumed_bytes: int
    message: str

    def __post_init__(self) -> None:
        if self.kind not in DISCLOSURE_AUTHORIZATION_OUTCOMES_V2:
            raise ValueError(
                "outcome kind must be one of "
                f"{sorted(DISCLOSURE_AUTHORIZATION_OUTCOMES_V2)}"
            )
        if self.kind in ("AUTHORIZED", "REPLAY"):
            if not isinstance(self.authorization, DisclosureAuthorizationRecordV2):
                raise ValueError(f"{self.kind} outcomes carry the authorization record")
        elif self.authorization is not None:
            raise ValueError(f"{self.kind} outcomes carry no authorization record")
        if (
            isinstance(self.consumed_bytes, bool)
            or not isinstance(self.consumed_bytes, int)
            or self.consumed_bytes < 0
        ):
            raise ValueError("consumed_bytes must be a non-negative integer")
        if self.message != _OUTCOME_MESSAGES[self.kind]:
            raise ValueError(
                "outcome message must be the closed static message of its kind"
            )


def grant_is_expired(grant: DisclosureGrantRecordV2, now: datetime) -> bool:
    """True when the grant's expiry timestamp is not in the future.

    Naive timestamps and a naive ``now`` are read as UTC, so the pure
    check stays deterministic regardless of the host timezone.
    """

    if not isinstance(grant, DisclosureGrantRecordV2):
        raise ValueError("grant must be a DisclosureGrantRecordV2")
    if not isinstance(now, datetime):
        raise ValueError("now must be a datetime")
    expires = datetime.fromisoformat(grant.expires_at.replace("Z", "+00:00"))
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return expires <= now


def disclosure_grant_from_mapping(
    data: Mapping[str, Any],
) -> DisclosureGrantRecordV2:
    """Parse a grant from an exact-field mapping, fail closed."""

    names = tuple(field.name for field in fields(DisclosureGrantRecordV2))
    values = _strict_mapping(data, names)
    return DisclosureGrantRecordV2(
        grant_id=values["grant_id"],
        disclosure_id=values["disclosure_id"],
        run_id=values["run_id"],
        reference_profile_id=values["reference_profile_id"],
        reference_profile_revision=values["reference_profile_revision"],
        expires_at=values["expires_at"],
        byte_budget=values["byte_budget"],
        consumed_bytes=values["consumed_bytes"],
        allowed_source_categories=values["allowed_source_categories"],
        allowed_source_paths=values["allowed_source_paths"],
        status=values["status"],
    )


def disclosure_authorization_from_mapping(
    data: Mapping[str, Any],
) -> DisclosureAuthorizationRecordV2:
    """Parse an authorization from an exact-field mapping, fail closed."""

    names = tuple(field.name for field in fields(DisclosureAuthorizationRecordV2))
    values = _strict_mapping(data, names)
    return DisclosureAuthorizationRecordV2(
        authorization_id=values["authorization_id"],
        grant_id=values["grant_id"],
        run_id=values["run_id"],
        request_id=values["request_id"],
        endpoint_id=values["endpoint_id"],
        charge_bytes=values["charge_bytes"],
        status=values["status"],
        sources=values["sources"],
    )


__all__ = (
    "DISCLOSURE_AUTHORIZATION_OUTCOMES_V2",
    "DISCLOSURE_AUTHORIZATION_STATUSES_V2",
    "DISCLOSURE_CONSUME_OUTCOMES_V2",
    "DISCLOSURE_GRANT_STATUSES_V2",
    "DISCLOSURE_SCOPE_KINDS_V2",
    "DISCLOSURE_SOURCE_CATEGORIES_V2",
    "MAX_DISCLOSURE_BUDGET_BYTES_V2",
    "MAX_DISCLOSURE_CHARGE_BYTES_V2",
    "MAX_DISCLOSURE_SCOPES_V2",
    "MAX_DISCLOSURE_SOURCES_V2",
    "MIN_DISCLOSURE_BUDGET_BYTES_V2",
    "MIN_DISCLOSURE_CHARGE_BYTES_V2",
    "PATH_BEARING_SOURCE_CATEGORIES_V2",
    "DisclosureAuthorizationOutcomeV2",
    "DisclosureAuthorizationRecordV2",
    "DisclosureConsumeOutcomeV2",
    "DisclosureGrantRecordV2",
    "DisclosurePathScopeV2",
    "DisclosureScopeErrorV2",
    "DisclosureSourceV2",
    "authorization_payload_key",
    "canonicalize_disclosure_categories",
    "canonicalize_disclosure_scopes",
    "canonicalize_disclosure_sources",
    "check_disclosure_request_sources",
    "disclosure_authorization_from_mapping",
    "disclosure_consume_outcome_message",
    "disclosure_grant_from_mapping",
    "disclosure_outcome_message",
    "disclosure_scope_matches",
    "grant_is_expired",
)
