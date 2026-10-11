"""Route B / B1: v2 candidate control identity and diff records.

The v1 candidate plane (``candidate/identity.py``, ``candidate/final_diff.py``,
``trees/candidate.py``) binds a candidate's semantic identity to content
digests: the identity is recomputed from tree roots, and every diff entry
carries preimage/postimage digests.  Those modules remain untouched
read-only legacy; nothing here imports them.

The v2 candidate control plane is deliberately shallower.  A candidate is
an ordinary control record — an opaque ``candidate_id``, the snapshot it
derives from, a non-negative ``revision`` that advances when staged
content changes, and a bounded lifecycle ``status``.  A diff record
associates one stored diff artifact with one candidate revision through
plain ``diff_id``/``artifact_id`` references.  Because no identity value
is derived from content, mutating staged content never regenerates an
identity: only the revision advances, and consumers reject stale
revisions instead of recomputing digests.

The module is standard-library only and importable without any
filesystem, network, LLM, or v1 dependency.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any

CANDIDATE_CONTROL_STATUSES_V2 = frozenset({"ACTIVE", "SUPERSEDED"})
"""The closed candidate lifecycle vocabulary of the v2 control plane.

``ACTIVE`` is the only status the current control plane writes; a
``SUPERSEDED`` candidate is retained for audit but is no longer the
current control state.  Any other spelling rejects at construction.
"""

_MAX_IDENTIFIER_BYTES = 256


def _identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    if len(value.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
        raise ValueError(f"{field_name} is too long")
    return value


def _revision(value: int, field_name: str = "revision") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _strict_mapping(data: object, names: tuple[str, ...]) -> dict[str, Any]:
    """Require exactly the given fields: unknown or missing keys reject.

    This is the fail-closed parse boundary for records that arrive as
    mappings (API payloads, log envelopes, exported rows).  A v1-shaped
    digest payload is rejected here as unknown fields, never accepted as
    authority.
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


@dataclass(frozen=True, slots=True)
class CandidateControlIdentityV2:
    """The v2 control identity of one candidate: opaque IDs and a revision.

    ``candidate_id`` and ``snapshot_id`` are opaque lookup keys.  The
    ``revision`` is the control-plane freshness counter: it advances when
    staged content mutates and consumers reject stale references by
    comparing revisions.  The bounded ``status`` is lifecycle state.
    No content digest is carried, so a content mutation never requires
    regenerating this identity.
    """

    candidate_id: str
    snapshot_id: str
    revision: int
    status: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "candidate_id", _identifier(self.candidate_id, "candidate_id")
        )
        object.__setattr__(
            self, "snapshot_id", _identifier(self.snapshot_id, "snapshot_id")
        )
        object.__setattr__(self, "revision", _revision(self.revision))
        if self.status not in CANDIDATE_CONTROL_STATUSES_V2:
            raise ValueError(
                "status must be one of 'ACTIVE' or 'SUPERSEDED'"
            )


@dataclass(frozen=True, slots=True)
class CandidateDiffRecordV2:
    """One stored diff artifact associated with one candidate revision.

    The record binds a diff to its candidate through the opaque
    ``candidate_id`` plus the ``candidate_revision`` it was derived from,
    and points at the stored artifact through a plain ``artifact_id``.
    There is no preimage/postimage digest: the association is a
    control-plane fact, not a content proof.
    """

    diff_id: str
    candidate_id: str
    candidate_revision: int
    artifact_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "diff_id", _identifier(self.diff_id, "diff_id"))
        object.__setattr__(
            self, "candidate_id", _identifier(self.candidate_id, "candidate_id")
        )
        object.__setattr__(
            self,
            "candidate_revision",
            _revision(self.candidate_revision, "candidate_revision"),
        )
        object.__setattr__(
            self, "artifact_id", _identifier(self.artifact_id, "artifact_id")
        )


def advance_candidate_revision(
    identity: CandidateControlIdentityV2,
) -> CandidateControlIdentityV2:
    """The control state after a content mutation: revision + 1 only.

    The candidate ID and snapshot reference never change for a content
    mutation — there is no identity digest to regenerate — so advancing
    the revision is the whole transition.  Consumers that recorded a
    reference to the previous revision must reject it as stale; the
    durable equivalent in the v2 database is the CAS in
    ``V2Database.advance_candidate``.
    """

    if not isinstance(identity, CandidateControlIdentityV2):
        raise ValueError("identity must be a CandidateControlIdentityV2")
    return CandidateControlIdentityV2(
        identity.candidate_id,
        identity.snapshot_id,
        identity.revision + 1,
        identity.status,
    )


def candidate_control_from_mapping(
    data: Mapping[str, Any],
) -> CandidateControlIdentityV2:
    """Parse a control identity from an exact-field mapping, fail closed."""

    names = tuple(field.name for field in fields(CandidateControlIdentityV2))
    values = _strict_mapping(data, names)
    return CandidateControlIdentityV2(
        candidate_id=values["candidate_id"],
        snapshot_id=values["snapshot_id"],
        revision=values["revision"],
        status=values["status"],
    )


def candidate_diff_from_mapping(data: Mapping[str, Any]) -> CandidateDiffRecordV2:
    """Parse a diff record from an exact-field mapping, fail closed."""

    names = tuple(field.name for field in fields(CandidateDiffRecordV2))
    values = _strict_mapping(data, names)
    return CandidateDiffRecordV2(
        diff_id=values["diff_id"],
        candidate_id=values["candidate_id"],
        candidate_revision=values["candidate_revision"],
        artifact_id=values["artifact_id"],
    )


__all__ = (
    "CANDIDATE_CONTROL_STATUSES_V2",
    "CandidateControlIdentityV2",
    "CandidateDiffRecordV2",
    "advance_candidate_revision",
    "candidate_control_from_mapping",
    "candidate_diff_from_mapping",
)
