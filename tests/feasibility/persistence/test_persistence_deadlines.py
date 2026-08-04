"""T03.1 legacy step 3.C: persistence deadline stop semantics tests.

Covers the closed deadline dispositions (STOPPED_ZERO_WRITE before any
write, RECOVERY_REQUIRED after a write) and the further-write
authorization boundary at, before, and after the deadline, as a pure
function of immutable transaction facts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from spikes.persistence_recovery.deadline import (
    DeadlineEvaluationV1,
    DeadlineDispositionV1,
    evaluate_persistence_deadline,
)
from spikes.persistence_recovery.protocol import GateTransactionV1

_DEADLINE_MS = 1_000


def expired_transaction() -> GateTransactionV1:
    """A PREPARED transaction whose deadline has already passed at now_ms=2_000."""
    return GateTransactionV1(
        transaction_id="txn-deadline-test",
        workspace=Path("C:/nonexistent-workspace"),
        state="PREPARED",
        deadline_ms=_DEADLINE_MS,
        prepared_at_ms=0,
        updated_at_ms=0,
        workspace_write_count=0,
        records=(),
    )


def _transaction(deadline_ms: int) -> GateTransactionV1:
    """One closed PREPARED transaction fact with the given absolute deadline."""
    return GateTransactionV1(
        transaction_id="txn-boundary",
        workspace=Path("C:/nonexistent-workspace"),
        state="PREPARED",
        deadline_ms=deadline_ms,
        prepared_at_ms=0,
        updated_at_ms=0,
        workspace_write_count=0,
        records=(),
    )


def test_deadline_after_first_replace_forbids_next_write() -> None:
    result = evaluate_persistence_deadline(
        expired_transaction(), observed_write_count=1, now_ms=2_000
    )
    assert result.further_workspace_writes_allowed is False


def test_deadline_after_first_write_requires_recovery() -> None:
    result = evaluate_persistence_deadline(
        expired_transaction(), observed_write_count=1, now_ms=2_000
    )
    assert result.disposition == "RECOVERY_REQUIRED"
    assert result.further_workspace_writes_allowed is False


def test_deadline_before_first_write_stops_with_zero_write() -> None:
    result = evaluate_persistence_deadline(
        expired_transaction(), observed_write_count=0, now_ms=2_000
    )
    assert result.disposition == "STOPPED_ZERO_WRITE"
    assert result.further_workspace_writes_allowed is False


def test_deadline_not_expired_allows_further_writes() -> None:
    transaction = _transaction(_DEADLINE_MS)
    before_write = evaluate_persistence_deadline(
        transaction, observed_write_count=0, now_ms=999
    )
    assert before_write.disposition == "STOPPED_ZERO_WRITE"
    assert before_write.further_workspace_writes_allowed is True
    after_write = evaluate_persistence_deadline(
        transaction, observed_write_count=3, now_ms=999
    )
    assert after_write.disposition == "RECOVERY_REQUIRED"
    assert after_write.further_workspace_writes_allowed is True


def test_deadline_exactly_at_boundary_is_expired() -> None:
    result = evaluate_persistence_deadline(
        _transaction(_DEADLINE_MS), observed_write_count=1, now_ms=_DEADLINE_MS
    )
    assert result.further_workspace_writes_allowed is False


def test_deadline_evaluation_is_pure_and_deterministic() -> None:
    first = evaluate_persistence_deadline(
        expired_transaction(), observed_write_count=2, now_ms=2_000
    )
    second = evaluate_persistence_deadline(
        expired_transaction(), observed_write_count=2, now_ms=2_000
    )
    assert first == second
    assert isinstance(first, DeadlineEvaluationV1)
    with pytest.raises(AttributeError):
        first.further_workspace_writes_allowed = True  # type: ignore[misc]


def test_deadline_rejects_negative_write_count() -> None:
    with pytest.raises(ValueError):
        evaluate_persistence_deadline(
            expired_transaction(), observed_write_count=-1, now_ms=2_000
        )


def test_persistence_deadline_boundary_matrix() -> None:
    """Every deadline boundary deterministically allows zero or no further
    writes exactly as declared: before expiry writes are allowed with the
    count-based disposition; at/after expiry no further write is allowed
    and the disposition is STOPPED_ZERO_WRITE only with zero writes."""
    rows: list[tuple[int, int, DeadlineDispositionV1, bool]] = [
        (999, 0, "STOPPED_ZERO_WRITE", True),
        (999, 1, "RECOVERY_REQUIRED", True),
        (999, 3, "RECOVERY_REQUIRED", True),
        (1_000, 0, "STOPPED_ZERO_WRITE", False),
        (1_000, 1, "RECOVERY_REQUIRED", False),
        (1_000, 3, "RECOVERY_REQUIRED", False),
        (2_000, 0, "STOPPED_ZERO_WRITE", False),
        (2_000, 1, "RECOVERY_REQUIRED", False),
        (2_000, 3, "RECOVERY_REQUIRED", False),
    ]
    for now_ms, write_count, disposition, allowed in rows:
        result = evaluate_persistence_deadline(
            _transaction(_DEADLINE_MS), observed_write_count=write_count, now_ms=now_ms
        )
        assert result.disposition == disposition, (now_ms, write_count)
        assert result.further_workspace_writes_allowed is allowed, (now_ms, write_count)
