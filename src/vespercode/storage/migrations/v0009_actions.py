"""T25.2 legacy step 25.D: immutable v0009 body-free action-record DDL.

The one action-step storage schema per SPEC 7 ActionRecord row and the
25.D GREEN-1 contract: ``action_records`` (PK ``action_id``, FK
``turn_id`` -> agent_turns, closed six-value ``action_type`` CHECK,
instance/semantic digests as exact 64-hex SHA-256, closed ALLOW/ASK/DENY
``policy_decision`` CHECK, and a body-free ``result_ref`` holding the
published artifact reference only — never an action body or a result
body).  The final registry composition (Task 7.D) is not editable here.
"""

from __future__ import annotations

from vespercode.contracts.evidence import DigestV1
from vespercode.storage.connection import ControlTransactionV1
from vespercode.storage.migration_engine import (
    MigrationV1,
    migration_checksum,
)

ACTIONS_V1_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE action_records (
        action_id TEXT PRIMARY KEY,
        turn_id TEXT NOT NULL REFERENCES agent_turns(turn_id),
        action_type TEXT NOT NULL CHECK (action_type IN (
            'apply_candidate_patch',
            'list_files',
            'propose_completion',
            'read_file',
            'run_check',
            'search_text'
        )),
        semantic_digest TEXT NOT NULL CHECK (length(semantic_digest) = 64),
        instance_digest TEXT NOT NULL CHECK (length(instance_digest) = 64),
        policy_decision TEXT NOT NULL CHECK (policy_decision IN (
            'ALLOW',
            'ASK',
            'DENY'
        )),
        result_ref TEXT
    )""",
)
"""The exact immutable v0009 statements; the checksum binds these bytes."""


def _apply_actions_v1(tx: ControlTransactionV1) -> None:
    for statement in ACTIONS_V1_STATEMENTS:
        tx.execute(statement)


ACTIONS_V1_MIGRATION = MigrationV1(
    version=9,
    name="actions_v1",
    checksum=DigestV1(
        value=migration_checksum(
            9,
            "actions_v1",
            "\n".join(ACTIONS_V1_STATEMENTS),
        )
    ),
    apply=_apply_actions_v1,
)
"""Immutable v0009 action-record migration consumed by Task 7.D."""
