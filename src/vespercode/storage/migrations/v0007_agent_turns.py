"""T25.1 legacy step 25.B: immutable v0007 active-turn DDL migration.

The one active-turn storage schema per SPEC 7 AgentTurn row and 4.2.5:
``agent_turns`` (PK ``turn_id``, FK ``run_id`` -> runs, lifecycle
revision compare-and-update field, closed ACTIVE/CLOSED status with the
closed four-value outcome CHECK and the closed ACTIVE/CLOSED coupling,
and body-free request/result references) with the partial unique index
admitting exactly one ACTIVE turn per Run, plus ``run_turn_call_counters``
(PK ``run_id``, monotonic turn/call counters with their own revision and
non-negative CHECKs).  The final registry composition (Task 7.D) is not
editable here.
"""

from __future__ import annotations

from src.vespercode.contracts.evidence import DigestV1
from src.vespercode.storage.connection import ControlTransactionV1
from src.vespercode.storage.migration_engine import (
    MigrationV1,
    migration_checksum,
)

AGENT_TURNS_V1_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE agent_turns (
        turn_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
        status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'CLOSED')),
        outcome TEXT CHECK (outcome IN (
            'SUCCEEDED',
            'FAILED',
            'NOT_ATTEMPTED',
            'ABORTED'
        )),
        closed_at TEXT,
        request_ref TEXT,
        result_ref TEXT,
        CHECK (
            (status = 'ACTIVE' AND outcome IS NULL AND closed_at IS NULL)
            OR (status = 'CLOSED' AND outcome IS NOT NULL AND closed_at IS NOT NULL)
        )
    )""",
    """CREATE UNIQUE INDEX ux_agent_turns_one_active_turn_per_run
        ON agent_turns(run_id)
        WHERE status = 'ACTIVE'""",
    """CREATE TABLE run_turn_call_counters (
        run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
        turn_count INTEGER NOT NULL CHECK (turn_count >= 0),
        call_count INTEGER NOT NULL CHECK (call_count >= 0),
        revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1)
    )""",
)
"""The exact immutable v0007 statements; the checksum binds these bytes."""


def _apply_agent_turns_v1(tx: ControlTransactionV1) -> None:
    for statement in AGENT_TURNS_V1_STATEMENTS:
        tx.execute(statement)


AGENT_TURNS_V1_MIGRATION = MigrationV1(
    version=7,
    name="agent_turns_v1",
    checksum=DigestV1(
        value=migration_checksum(
            7,
            "agent_turns_v1",
            "\n".join(AGENT_TURNS_V1_STATEMENTS),
        )
    ),
    apply=_apply_agent_turns_v1,
)
"""Immutable v0007 active-turn migration consumed by Task 7.D."""
