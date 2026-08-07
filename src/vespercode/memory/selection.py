"""T22.1 legacy step 22.B: workspace-bound listing and pure bounded selection.

``MemoryRepository.list`` (owned by 22.A) supplies the non-cleared
entries of one exact workspace in stable creation order;
``select_memory`` is the pure deterministic selection: exact workspace
matching and cleared-entry exclusion, then the frozen kind priority,
recency (newest ``updated_at`` first), the stable entry-id tie-break,
the frozen count cap (20), and the frozen canonical byte budget
(16 KiB), keeping every selected entry's source attribution.
``MemorySelectorV1`` composes the two into one future-selection path so
a committed clear is immediately visible to every later selection.
Creation, confirmation, clearing, current Snapshot/check overrides, and
governance decisions remain out of scope (GREEN-4).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from vespercode.memory.entry import (
    MemoryEntryV1,
    MemoryKindV1,
    canonical_memory_byte_count,
)
from vespercode.memory.repository import (
    MemoryEntrySequenceV1,
    MemoryRepository,
)

MEMORY_SELECTION_COUNT_LIMIT_V1 = 20
"""SPEC 4.7: at most 20 memory entries are ever selected per context."""

MEMORY_SELECTION_BYTE_LIMIT_V1 = 16384
"""SPEC 4.7: at most 16 KiB of memory content is ever selected per context."""

FROZEN_MEMORY_KIND_PRIORITY_V1: tuple[MemoryKindV1, ...] = (
    "KNOWN_FAILURE",
    "PROJECT_CONVENTION",
    "USER_DECISION",
    "RUN_SUMMARY",
)
"""The frozen kind priority (smaller rank first) applied by every selection.

Known failures are the most actionable fix context, then persistent
project conventions, then the user's recorded decisions, and finally
ended-run summaries; the order is frozen so identical memory always
selects identically.
"""


class MemorySelectionQueryV1(BaseModel):
    """One closed selection request with frozen bounded limits.

    The count and byte limits are frozen into the immutable query at
    construction and cannot exceed the SPEC 4.7 hard caps.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    workspace_identity_digest: StrictStr
    count_limit: int = Field(default=20, ge=1, le=20)
    byte_limit: int = Field(default=16384, ge=1, le=16384)


class MemorySelectionV1(BaseModel):
    """One closed deterministic selection outcome.

    ``entries`` keeps full source attribution of every selected entry;
    ``total_canonical_bytes`` is the sum of the canonical content bytes.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    workspace_identity_digest: StrictStr
    entries: MemoryEntrySequenceV1
    total_canonical_bytes: int


def select_memory(
    query: MemorySelectionQueryV1,
    entries: MemoryEntrySequenceV1,
) -> MemorySelectionV1:
    """Select eligible non-cleared entries of the exact workspace purely.

    The pure function defends the same workspace/cleared boundary as the
    repository listing, then orders by frozen kind priority, recency
    (newest update first), and stable entry id, applies the count cap,
    and includes entries greedily in that order while the canonical byte
    budget lasts (the remaining lower-priority/older entries are
    excluded, mirroring SPEC 4.2.4 "先删除最旧记忆").
    """
    priority = {kind: rank for rank, kind in enumerate(FROZEN_MEMORY_KIND_PRIORITY_V1)}
    eligible = [
        entry
        for entry in entries
        if entry.workspace_identity == query.workspace_identity_digest
        and entry.cleared_at is None
    ]
    ordered = sorted(
        eligible,
        key=lambda entry: (
            priority[entry.kind],
            -entry.updated_at.epoch_milliseconds,
            entry.entry_id,
        ),
    )
    bounded = ordered[: query.count_limit]
    selected: list[MemoryEntryV1] = []
    total_bytes = 0
    for entry in bounded:
        byte_count = canonical_memory_byte_count(entry)
        if total_bytes + byte_count > query.byte_limit:
            break
        selected.append(entry)
        total_bytes += byte_count
    return MemorySelectionV1(
        workspace_identity_digest=query.workspace_identity_digest,
        entries=tuple(selected),
        total_canonical_bytes=total_bytes,
    )


class MemorySelectorV1:
    """The composed future-selection path over one memory repository.

    Every selection goes through the repository listing, so a committed
    clear tombstone excludes the targeted entries from every later
    selection immediately (SPEC 4.7 "用户清除后，后续 turn 和运行不得再
    选择该条目").
    """

    def __init__(self, repository: MemoryRepository) -> None:
        self._repository = repository

    def select(self, query: MemorySelectionQueryV1) -> MemorySelectionV1:
        return select_memory(
            query, self._repository.list(query.workspace_identity_digest)
        )
