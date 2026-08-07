"""T07.2 legacy step 7.B: immutable v0001 Run/config/wait DDL migration.

The one coupled Run/config/wait storage schema per the PLAN storage
registry rows 424/429/431: ``runs`` (PK run_id, immutable config FK,
lifecycle revision compare-and-update fields, deadline/status/phase, no
body/secret columns), ``run_config_snapshots`` (PK config_snapshot_id,
unique canonical digest, frozen profile/policy/target/limit identities,
no credential value), and ``wait_contexts`` (PK wait_id, FK run_id ->
runs, unique active wait per Run, exact kind/subject/expiry/decision
binding, no subject body).  The final registry composition (Task 7.D) is
not editable here.
"""

from __future__ import annotations

from vespercode.contracts.evidence import DigestV1
from vespercode.storage.connection import ControlTransactionV1
from vespercode.storage.migration_engine import (
    MigrationV1,
    migration_checksum,
)

RUN_WAIT_V1_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE run_config_snapshots (
        config_snapshot_id TEXT PRIMARY KEY,
        digest TEXT NOT NULL UNIQUE,
        llm_profile_id TEXT NOT NULL,
        reference_profile_id TEXT NOT NULL,
        policy_id TEXT NOT NULL,
        target_test_ids TEXT NOT NULL,
        limits_digest TEXT NOT NULL,
        frozen_at TEXT NOT NULL
    )""",
    """CREATE TABLE runs (
        run_id TEXT PRIMARY KEY,
        workspace_identity TEXT NOT NULL,
        config_snapshot_id TEXT NOT NULL
            REFERENCES run_config_snapshots(config_snapshot_id),
        status TEXT NOT NULL CHECK (status IN (
            'CREATED',
            'RUNNING',
            'WAITING_USER',
            'RECOVERY_REQUIRED',
            'SUCCEEDED',
            'STOPPED'
        )),
        phase TEXT CHECK (phase IN (
            'PREFLIGHT',
            'BASELINE',
            'AGENT_LOOP',
            'FORMAL_VALIDATION',
            'PERSISTENCE'
        )),
        revision INTEGER NOT NULL DEFAULT 1,
        started_at TEXT NOT NULL,
        run_deadline TEXT NOT NULL,
        CHECK (
            (status = 'RUNNING' AND phase IS NOT NULL)
            OR (status <> 'RUNNING' AND phase IS NULL)
        )
    )""",
    """CREATE TABLE wait_contexts (
        wait_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        wait_kind TEXT NOT NULL CHECK (wait_kind IN (
            'DISCLOSURE_GRANT',
            'FINAL_WRITEBACK'
        )),
        source_phase TEXT NOT NULL CHECK (source_phase IN (
            'AGENT_LOOP',
            'FORMAL_VALIDATION'
        )),
        subject_digest TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN (
            'PENDING',
            'DECIDING',
            'DECIDED',
            'EXPIRED'
        )),
        decision TEXT CHECK (decision IN ('APPROVE', 'REJECT')),
        decided_at TEXT
    )""",
    """CREATE UNIQUE INDEX ux_wait_contexts_one_active_wait_per_run
        ON wait_contexts(run_id)
        WHERE status IN ('PENDING', 'DECIDING')""",
)
"""The exact immutable v0001 statements; the checksum binds these bytes."""


def _apply_run_wait_v1(tx: ControlTransactionV1) -> None:
    for statement in RUN_WAIT_V1_STATEMENTS:
        tx.execute(statement)


RUN_WAIT_V1_MIGRATION = MigrationV1(
    version=1,
    name="run_wait_v1",
    checksum=DigestV1(
        value=migration_checksum(
            1,
            "run_wait_v1",
            "\n".join(RUN_WAIT_V1_STATEMENTS),
        )
    ),
    apply=_apply_run_wait_v1,
)
"""Immutable v0001 Run/config/wait migration consumed by Task 7.D."""
