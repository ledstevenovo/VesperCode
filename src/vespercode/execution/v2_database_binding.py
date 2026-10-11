"""Route B / B4b-02A: the production database-backed execution binding.

``DatabaseBackedExecutionBinding`` is the production-shaped read-only
``V2ExecutionBindingPort`` over a REAL ``V2Database`` — the module that
replaces B4a's fake/read-only binding seam for production wiring.  It
is standard-library plus v2-only (no v1 authority module, no digest
identity, no subprocess, no socket) and resolves one lookup against
durable committed rows only:

1. the request must cite a validation run (``validation_run_id``):
   an uncited request is malformed for this binding and answers the
   closed ``VALIDATION_REQUIRED`` rejection — the production binding
   resolves only cited validations;
2. the cited run must exist and the cited candidate must exist, and
   the candidate row must revalidate as a B1 control identity and
   belong to that run — an unknown run, an unknown candidate, a
   foreign candidate, or a corrupted candidates row answers
   ``BINDING_NOT_FOUND``;
3. the cited validation run must exist and its row must revalidate as
   a B1 ``ValidationRunRecordV2``, and it must bind the same run, the
   same candidate, at the candidate's CURRENT revision, under the
   cited reference profile id/revision — a missing, foreign, stale,
   or profile-mismatched validation answers ``VALIDATION_NOT_FOUND``;
4. the validation's own reference profile revision must still exist
   and revalidate as a B1 ``ReferenceProfileRecordV2`` (the terminal
   record must not cite configuration that can no longer be read),
   and the validation must be terminal ``PASSED`` — a ``PENDING`` or
   ``FAILED`` validation answers ``VALIDATION_NOT_PASSED``.

Every corrupted or missing row is a closed rejection, never fake
data: record revalidation failures (``ValueError``/``TypeError`` from
the B1 record constructors the storage layer projects rows through)
are caught and answered as the corresponding NOT_FOUND kind, so a
hostile writer cannot make a corrupt record executable.  The lookup is
strictly read-only — no mutation, no approval consumption, no
validation result creation, no candidate advancement — and holds no
cached state: every answer is read from the database, so a
freshly-reopened database in a fresh process resolves the same
binding.  Infrastructure failures (``sqlite3`` errors beyond record
shape) propagate loudly: nothing executes either way, and the
storage layer's own behavior is preserved.

Real Docker execution stays behind the B4b-01 executor and the B4a
readiness gates; this adapter adds no shell, network, or container
behavior at all.
"""

from __future__ import annotations

from vespercode.candidate.v2_candidate import CandidateControlIdentityV2
from vespercode.execution.v2_execution import (
    ExecutionBindingFactsV2,
    ExecutionBindingOutcomeV2,
    ValidationBindingFactsV2,
)
from vespercode.storage.v2_database import V2Database


class DatabaseBackedExecutionBinding:
    """The read-only production binding over one ``V2Database``.

    ``lookup_execution_binding`` answers one closed outcome for the
    request's five binding keys (the run, the candidate, the
    validation citation, and the reference profile id/revision):
    ``RESOLVED`` with the candidate's CURRENT revision and the cited
    validation's own five keys and status — only when the cited
    validation is a terminal ``PASSED`` validation of that current
    revision under the cited reference profile — or the corresponding
    closed rejection kind.  The lookup never writes, never caches,
    and never fabricates a fact.
    """

    def __init__(self, database: V2Database) -> None:
        if not isinstance(database, V2Database):
            raise ValueError(
                "the database-backed execution binding requires a "
                "V2Database"
            )
        self._database = database

    def lookup_execution_binding(
        self,
        run_id: str,
        candidate_id: str,
        validation_run_id: str | None,
        reference_profile_id: str,
        reference_profile_revision: int,
    ) -> ExecutionBindingOutcomeV2:
        # The production binding resolves only cited validations: an
        # uncited request is malformed here, whatever the fake allows
        # for the isolated B4a seam.
        if validation_run_id is None:
            return ExecutionBindingOutcomeV2("VALIDATION_REQUIRED")

        # --- the run/candidate pair -----------------------------------
        if self._database.get_run(run_id) is None:
            return ExecutionBindingOutcomeV2("BINDING_NOT_FOUND")
        candidate_row = self._database.get_candidate(candidate_id)
        if candidate_row is None:
            return ExecutionBindingOutcomeV2("BINDING_NOT_FOUND")
        try:
            # Revalidate the row as a B1 control identity: a corrupted
            # or foreign-written candidates row fails closed here.
            control = CandidateControlIdentityV2(
                candidate_id=str(candidate_row["candidate_id"]),
                snapshot_id=str(candidate_row["snapshot_id"]),
                revision=int(candidate_row["revision"]),
                status=str(candidate_row["status"]),
            )
        except (TypeError, ValueError):
            return ExecutionBindingOutcomeV2("BINDING_NOT_FOUND")
        if str(candidate_row["run_id"]) != run_id:
            return ExecutionBindingOutcomeV2("BINDING_NOT_FOUND")

        # --- the cited validation run ---------------------------------
        try:
            validation = self._database.get_validation_run(
                validation_run_id
            )
        except (TypeError, ValueError):
            # A corrupted validation_runs row does not revalidate as a
            # B1 record: it is not usable evidence, never fake facts.
            return ExecutionBindingOutcomeV2("VALIDATION_NOT_FOUND")
        if validation is None:
            return ExecutionBindingOutcomeV2("VALIDATION_NOT_FOUND")
        if (
            validation.run_id != run_id
            or validation.candidate_id != candidate_id
            or validation.candidate_revision != control.revision
            or validation.reference_profile_id != reference_profile_id
            or validation.reference_profile_revision
            != reference_profile_revision
        ):
            # A validation of another run, another candidate, a stale
            # revision (the candidate advanced after it was recorded),
            # or another reference profile revision is not this
            # request's evidence.
            return ExecutionBindingOutcomeV2("VALIDATION_NOT_FOUND")
        try:
            profile = self._database.get_reference_profile(
                validation.reference_profile_id,
                validation.reference_profile_revision,
            )
        except (TypeError, ValueError):
            return ExecutionBindingOutcomeV2("VALIDATION_NOT_FOUND")
        if profile is None:
            # The terminal record cites configuration that can no
            # longer be read: fail closed, exactly like the B1
            # completion path does.
            return ExecutionBindingOutcomeV2("VALIDATION_NOT_FOUND")
        if validation.status != "PASSED":
            # Only a terminal PASSED validation is executable
            # evidence; PENDING means it never finished and FAILED
            # means it did not pass.
            return ExecutionBindingOutcomeV2("VALIDATION_NOT_PASSED")

        # --- resolved: the current binding plus the passed validation -
        return ExecutionBindingOutcomeV2(
            "RESOLVED",
            ExecutionBindingFactsV2(
                run_id=run_id,
                candidate_id=candidate_id,
                candidate_revision=control.revision,
                validation=ValidationBindingFactsV2(
                    validation_run_id=validation.validation_run_id,
                    run_id=validation.run_id,
                    candidate_id=validation.candidate_id,
                    candidate_revision=validation.candidate_revision,
                    reference_profile_id=validation.reference_profile_id,
                    reference_profile_revision=(
                        validation.reference_profile_revision
                    ),
                    status=validation.status,
                ),
            ),
        )


__all__ = ("DatabaseBackedExecutionBinding",)
