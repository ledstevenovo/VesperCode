# VesperCode v2 Relaxed Identity Implementation Plan

> Historical v1 execution plan: [`PLAN_v1_frozen.md`](PLAN_v1_frozen.md).
> This plan is intentionally smaller and does not require SHA-256 identity
> gates, canonical digest vectors, lock distribution hashes, or image digest
> promotion.

## Goal and stop condition

Deliver a runnable offline v2 alpha with opaque runtime IDs, revision-based
freshness, behavior-oriented governance, an injectable Mock LLM loop, scoped
memory, and an independent SQLite database. Stop when the v2 unit suite,
syntax checks, credential scan, and documentation checks pass. Do not migrate
the v1 schema or delete legacy evidence in this plan.

## Task V2-01 — Identity and database boundary

- **Goal:** introduce opaque IDs, v2 value objects, fresh database path, and
  revision-bound approvals.
- **Files:** `src/vespercode/contracts/v2_identity.py`,
  `src/vespercode/storage/v2_database.py`,
  `tests/unit/v2/test_identity.py`, `tests/unit/v2/test_database.py`.
- **Implementation:** UUID factories; `CandidateIdentityV2`,
  `ActionInstanceV2`, `FinalWritebackSubjectV2`; v2 schema; run CAS;
  candidate-revision approval consumption; refuse v1 schema reuse.
- **Intended RED:** missing v2 modules and missing v2 database behavior.
  THIRD-ROUND RED (before the structural fix):
  ``test_an_uncited_request_rejects_before_the_binding_lookup``
  failed with ``AssertionError: 'SUCCEEDED' != 'FAILED'`` — the
  unguarded production service executed an uncited request
  through the permissive fake (binding consulted, readiness
  checked, executor called); importing the not-yet-existing
  ``V2ExecutionTestService`` failed the whole service suite with
  ``ImportError: cannot import name 'V2ExecutionTestService'``
  (468 tests ran, 1 loader error).
- **Verification:** `python -m unittest discover -s tests\unit\v2 -v`.
- **Dependencies:** none. **Parallelizable:** no; this is the storage base.
- **Status:** complete in the current worktree; implementation commit pending.

## Task V2-02 — Deterministic relaxed governance

- **Goal:** preserve path, sensitive, protected-file, and action controls
  without digest-based identity gates.
- **Files:** `src/vespercode/governance/relaxed_policy.py`,
  `tests/unit/v2/test_relaxed_policy.py`.
- **Implementation:** canonical lexical path rejection, workspace confinement,
  symlink-aware resolution, protected read/write distinction, closed action
  families.
- **Intended RED:** policy module absent, then alias paths accidentally accepted
  by path normalization.
- **Verification:** v2 unit suite; Windows symlink integration test when
  available.
- **Dependencies:** V2-01 vocabulary only. **Parallelizable:** no, shares policy
  semantics with the dispatcher.
- **Status:** complete in the current worktree; implementation commit pending.

## Task V2-03 — Harness core and feedback mechanism

- **Goal:** provide the self-owned v2 loop and deterministic mechanism demo
  surface.
- **Files:** `src/vespercode/llm/v2.py`, `src/vespercode/memory/v2.py`,
  `src/vespercode/tools/v2_dispatcher.py`, `src/vespercode/loop/v2_engine.py`,
  `src/vespercode/runtime_v2.py`, `tests/unit/v2/test_runtime.py`,
  `tests/unit/v2/test_composition.py`.
- **Implementation:** injected scripted LLM; in-memory workspace port; policy
  dispatch; context assembly; one call per turn; feedback memory; DONE and
  MAX_TURNS stopping; run lifecycle composition.
- **Intended RED:** imports fail before implementation; later RED covers invalid
  model action and missing error envelope.
- **Verification:** v2 unit suite; repeat the scripted dangerous-action and
  corrective-action scenario twice and compare statuses/turns/workspace bytes.
- **Dependencies:** V2-01 and V2-02. **Parallelizable:** no; composition is
  the final vertical slice.
- **Status:** complete in the current worktree; implementation commit pending.

## Task V2-04 — Version and process contract

- **Goal:** make v2 the active source contract while retaining v1 as read-only
  history.
- **Files:** `SPEC.md`, `PLAN.md`, `README.md`, `pyproject.toml`,
  `src/vespercode/__init__.py`, selected package smoke expectations,
  `SPEC_PROCESS.md`, `AGENT_LOG.md`.
- **Implementation:** version `0.2.0-alpha`/`0.2.0a0`; explicit v1/v2
  incompatibility; v2 database path; secure-key threat model; one documented
  offline test command; no claims of retained hash-level integrity.
- **Intended RED:** documentation still describes v1 digest gates as the
  current contract and package metadata still reports `0.1.0`.
- **Verification:** v2 unit suite, syntax compilation, credential scan,
  `git diff --check`, README/process contract checks where dependencies exist.
- **Dependencies:** V2-01–V2-03. **Parallelizable:** documentation can be
  reviewed independently after the code slice is stable.
- **Status:** complete in the current worktree; implementation commit pending.

## Task V2-05 — Remaining integrations (future)

- **Goal:** migrate real filesystem candidate/writeback, disclosure ledger,
  validation references, WebUI, CLI, Docker profile, and CI to v2 behavior.
- **Files:** subsequent task-specific slices only; do not global-replace
  `digest`.
- **Verification:** each slice gets a deterministic RED/GREEN test and keeps
  v1 legacy tests untouched.
- **Dependencies:** V2-04 and explicit contract review.
- **Parallelizable:** independent adapters may proceed in separate worktrees
  after interfaces are frozen.
- **Status:** partially started — Route A (real local filesystem writeback
  and recovery) is implemented by tasks RA-01..RA-09 below; Route B1
  (candidate/validation/reference-profile identity contracts and storage)
  is implemented by tasks B1-01..B1-04 below; Route B2 (the
  disclosure/provider/credential control plane — grants, per-request
  authorizations, provider endpoints, the injectable credential port, and
  the one-call provider boundary) is implemented by tasks B2-01..B2-05
  below; the remaining integrations (WebUI/CLI, Docker validation
  execution, the real OS credential adapter and real provider
  transports, and release) are **not started**.

## Task RA-01 — Route A / A0: frozen writeback interfaces

- **Goal:** freeze the v2 writeback vocabulary, value objects, and the
  workspace port protocol before any filesystem behavior lands.
- **Files:** `src/vespercode/contracts/v2_writeback.py`,
  `tests/unit/v2/test_writeback_contracts.py`.
- **Implementation:** `WriteOperationV2` (CREATE/REPLACE with canonical
  relative paths), `JournalEntryV2` (intended write plus observed
  original), `WritebackRequestV2`/`WritebackOutcomeV2`,
  `TransactionStateV2` (PREPARED/WRITING/COMMITTED/UNRESOLVED/ROLLED_BACK),
  `WritebackStatusV2`, recovery preview/outcome records, and the
  `V2WorkspacePort` protocol. No content digest enters any contract.
- **Intended RED:** `ModuleNotFoundError` for the contracts module, then
  rejected invalid shapes.
- **Verification:** `python -m unittest tests.unit.v2.test_writeback_contracts -v`.
- **Dependencies:** V2-01 vocabulary. **Parallelizable:** no; every later
  Route A task consumes these contracts.
- **Status:** complete in the current worktree; implementation commit pending.

## Task RA-02 — Route A / A1: real path/object boundary

- **Goal:** make the real filesystem boundary fail closed against
  traversal, aliasing, link, and reparse hazards.
- **Files:** `src/vespercode/workspace/v2_boundary.py`,
  `tests/unit/v2/test_v2_boundary.py`.
- **Implementation:** canonical lexical rules, component-wise `lstat` walk
  refusing symlinks and Windows reparse points (junctions are reparse
  points that `Path.is_symlink` does not report), resolved confinement,
  file type checks for read/CREATE/REPLACE targets, Windows reserved device
  names and trailing dot/space refusal, and a full recheck immediately
  before mutation to shrink the TOCTOU window.
- **Intended RED:** module missing; then junction and reserved-name
  rejections.
- **Verification:** v2 unit suite; Windows-marked junction tests run on a
  Windows host and skip elsewhere.
- **Dependencies:** RA-01 constants only. **Parallelizable:** no; the port
  and all writeback services depend on it.
- **Status:** complete in the current worktree; implementation commit pending.

## Task RA-03 — Route A / A2: durable transactions and atomic writeback

- **Goal:** land schema v3 (transactions with a legal state machine plus a
  durable journal) and the approval-bound writeback service with zero
  writes on stale/mismatch/deny.
- **Files:** `src/vespercode/storage/v2_database.py`,
  `src/vespercode/persistence/v2_writeback.py`,
  `src/vespercode/tools/v2_dispatcher.py` (in-memory port protocol
  conformance),
  `tests/unit/v2/test_v2_database_transactions.py`,
  `tests/unit/v2/test_v2_writeback.py`.
- **Implementation:** `transaction_journal` table; `begin_writeback_transaction`
  atomically re-verifies freshness and the pending approval, consumes it,
  and journals intended writes with observed originals; `transition_transaction`
  enforces the frozen state map with a state CAS; `V2WritebackService`
  validates candidate revision, approval, duplicates, policy, and strict
  target semantics before any write, then applies per-file operations and
  marks UNRESOLVED on faults.
- **Intended RED:** schema version mismatch and missing methods; then
  zero-write outcomes and fault injection.
- **Verification:** `python -m unittest tests.unit.v2.test_v2_database_transactions tests.unit.v2.test_v2_writeback -v`
  plus the full v2 suite.
- **Dependencies:** RA-01, RA-02. **Parallelizable:** no.
- **Status:** complete in the current worktree; implementation commit pending.

## Task RA-04 — Route A / A3: recovery preview, apply, and rollback

- **Goal:** recover crashed writebacks from durable state alone with
  fail-closed drift blocking.
- **Files:** `src/vespercode/persistence/v2_recovery.py`,
  `tests/unit/v2/test_v2_recovery.py`.
- **Implementation:** pending-transaction listing; byte-comparison preview
  classifying APPLIED/PENDING/DRIFTED/UNREADABLE; apply completes pending
  writes through the boundary-checked port; rollback restores recorded
  originals and removes created files; DRIFTED/UNREADABLE block both paths.
- **Intended RED:** module missing; then drift blocking and restart
  safety.
- **Verification:** `python -m unittest tests.unit.v2.test_v2_recovery -v`.
- **Dependencies:** RA-03. **Parallelizable:** no.
- **Status:** complete in the current worktree; implementation commit pending.

- **Status:** complete in the current worktree; implementation commit pending.

## Task RA-05 — Route A / A4+A5: real disk port, harness injection, and fault/Windows tests

- **Goal:** inject the real workspace port into `V2Harness` while keeping
  deterministic in-memory staging, and cover faults and Windows reparse
  behavior.
- **Files:** `src/vespercode/workspace/v2_disk.py`,
  `src/vespercode/runtime_v2.py`,
  `tests/unit/v2/test_v2_harness_writeback.py`.
- **Implementation:** `LocalDiskWorkspacePort` (atomic temp-file writes with
  fsync, link-based CREATE, replace-based REPLACE, boundary recheck before
  mutation); harness composes staging + disk ports + writeback/recovery
  services; `stage_candidate` and `staged_operations`; fault-injected crash
  and restart tests against the real filesystem.
- **Intended RED:** missing disk port and harness wiring; then end-to-end
  disk writeback and restart recovery.
- **Verification:** full v2 suite (`python -m unittest discover -s tests/unit/v2 -v`),
  demo script, compileall, `git diff --check`.
- **Dependencies:** RA-01..RA-04. **Parallelizable:** no; final vertical
  slice.
- **Status:** complete in the current worktree; implementation commit pending.

## Task RA-06 — Route A hardening: compare-and-publish content guard

- **Goal:** close the REPLACE content TOCTOU found in parent review: the
  port rechecked path/type but not content immediately before publication,
  so an external modification after preflight could be overwritten.
- **Files:** `src/vespercode/contracts/v2_writeback.py` (new
  `PlannedWriteV2`, `WorkspaceContentMismatchError`; `JournalEntryV2`
  `planned`/`planned_restore`; port protocol `apply` takes plans),
  `src/vespercode/tools/v2_dispatcher.py`,
  `src/vespercode/workspace/v2_disk.py`,
  `src/vespercode/persistence/v2_writeback.py`,
  `src/vespercode/persistence/v2_recovery.py`,
  `tests/unit/v2/test_v2_replace_content_guard.py`,
  `tests/unit/v2/test_writeback_contracts.py`, port fixture updates.
- **Implementation:** a planned write binds a REPLACE to the exact expected
  original bytes (CREATE binds absence, enforced by the no-clobber link);
  both ports compare current bytes to the expected original immediately
  before publication and raise instead of overwriting; writeback returns
  FAILED/UNRESOLVED with the approval and journal auditable; recovery
  apply and rollback publish through the same binding, so restores expect
  the applied bytes and refuse externally modified targets.
- **Intended RED:** `test_v2_replace_content_guard` showed the current
  code reporting `COMMITTED` while overwriting an externally modified
  target (`AssertionError: 'COMMITTED' != 'FAILED'`) plus the missing
  `PlannedWriteV2` API; the regression went green after the guard landed.
- **Verification:** full v2 suite (`python -m unittest discover -s tests/unit/v2 -v`,
  121 tests), compileall, `git diff --check`, demo script.
- **Dependencies:** RA-01..RA-05. **Parallelizable:** no; hardens the frozen
  port contract every Route A consumer depends on.
- **Status:** complete in the current worktree; implementation commit pending.

## Task RA-07 — Route A hardening round 2: content-bound removal and full schema validation

- **Goal:** close the second parent-review REQUIRED CHANGES pair: (1) the
  recovery rollback could delete externally changed content because
  `remove(path)` was unbound, and (2) schema validation did not cover every
  v2 table's columns.
- **Files:** `src/vespercode/contracts/v2_writeback.py` (protocol
  `remove(path)` replaced by `remove_expected(path, expected_content)`),
  `src/vespercode/tools/v2_dispatcher.py`,
  `src/vespercode/workspace/v2_disk.py` (compare-and-delete guard),
  `src/vespercode/persistence/v2_recovery.py`,
  `src/vespercode/storage/v2_database.py` (`actions`, `disclosures`,
  `artifacts` added to `_V2_REQUIRED_COLUMNS`),
  `tests/unit/v2/test_v2_replace_content_guard.py`,
  `tests/unit/v2/test_writeback_contracts.py`,
  `tests/unit/v2/test_v2_database_transactions.py`, port fixture updates.
- **Implementation:** the port protocol exposes only
  `remove_expected(path, expected_content)`; both ports compare the current
  bytes to the expected content immediately before the unlink and raise
  `WorkspaceContentMismatchError` on mismatch, so an external change between
  the recovery observation and the removal is refused (FAILED, non-terminal
  transaction) instead of deleting external bytes; the schema contract now
  validates the columns of every v2 table — the journal columns were already
  validated (pinned by a test that passes against the pre-fix code), while
  `actions`, `disclosures`, and `artifacts` were genuinely unvalidated and
  are now required on open and initialize.
- **Intended RED:** both rollback-race regressions failed with
  `AssertionError: 'ROLLED_BACK' != 'FAILED'` (the old code deleted the
  externally changed file), the removal seam was missing
  (`AttributeError: no attribute 'remove_expected'`), the protocol accepted
  an unbound `remove` implementation, and the malformed-table tests showed
  `open_v2_database accepted a malformed actions/disclosures/artifacts
  table`; the journal malformed-schema test passed against the pre-fix code
  as a pin.
- **Verification:** full v2 suite (`python -m unittest discover -s tests/unit/v2 -v`,
  130 tests), compileall, `git diff --check`, demo script.
- **Dependencies:** RA-06. **Parallelizable:** no; second hardening pass over
  the frozen port contract and the schema gate.
- **Status:** complete in the current worktree; implementation commit pending.

## Task RA-08 — Route A hardening round 3: secret-content gate and corrupted-journal rejection

- **Goal:** close the third parent-review REQUIRED CHANGES pair: (1) the
  journal persisted complete staged content, so ordinary `src/*.py` files
  carrying credentials would enter the control database; (2) recovery
  accepted corrupted journals — an active transaction with an empty
  journal previewed as unblocked and could be committed with zero writes
  verified, and non-contiguous positions were never checked.
- **Files:** `src/vespercode/governance/v2_secret_scanner.py` (new),
  `src/vespercode/persistence/v2_writeback.py` (pre-journal content gate),
  `src/vespercode/persistence/v2_recovery.py` (journal validation),
  `tests/unit/v2/test_v2_secret_scanner.py` (new),
  `tests/unit/v2/test_v2_recovery.py`.
- **Implementation:** a deterministic conservative marker scanner
  (assignment spellings, Bearer headers, PEM private-key headers,
  structured provider-token shapes — GitHub/Slack/OpenAI/Anthropic/
  Stripe/AWS/Google/npm/JWT) checks every staged operation's content and
  every REPLACE target's observed original before the approval is
  consumed; a hit returns DENIED with zero writes, a PENDING approval, no
  transaction, and a message that never contains the matched material.
  Recovery now validates the journal at load: non-empty, every row bound
  to the requested transaction, positions contiguous from zero, and row
  shapes through `JournalEntryV2`; any violation raises a closed failure
  before any state advance.
- **Intended RED:** a pre-fix probe showed the writeback returning
  `COMMITTED` and journaling `API_KEY = "abc123"` into
  `transaction_journal.content`; the scanner module import failed
  (`ModuleNotFoundError`); and both corrupted-journal regressions failed
  with `AssertionError: ValueError not raised` (empty journal previewed
  unblocked; non-contiguous positions accepted). The three
  malformed-row-shape subtests passed as pins (`JournalEntryV2` already
  rejected them).
- **Verification:** full v2 suite (`python -m unittest discover -s tests/unit/v2 -v`,
  141 tests), compileall, `git diff --check`, demo script.
- **Dependencies:** RA-07. **Parallelizable:** no; third hardening pass
  over the writeback boundary and the recovery gate.
- **Status:** complete in the current worktree; implementation commit pending.

## Task RA-09 — Route A hardening round 4: wheel package contract covers the v2 modules

- **Goal:** close the fourth parent-review REQUIRED CHANGES finding: the
  Route A production modules were absent from the wheel package smoke
  contract `REQUIRED_RUNTIME_MEMBERS` in
  `tests/smoke/package/test_wheel_contents.py`, so the v2 source tests
  could pass while the built wheel omitted Route A code.
- **Files:** `tests/smoke/package/test_wheel_contents.py` (six new
  required members plus a contract note),
  `tests/unit/v2/test_v2_wheel_contract.py` (new offline guard),
  `SPEC.md` / `README.md` (packaging-guard notes).
- **Implementation:** the six Route A modules
  (`contracts/v2_writeback.py`, `governance/v2_secret_scanner.py`,
  `persistence/v2_recovery.py`, `persistence/v2_writeback.py`,
  `workspace/v2_boundary.py`, `workspace/v2_disk.py`) join the required
  wheel member set alongside the existing v2 baseline members; the v1
  frozen member set is untouched. The new stdlib-only guard
  `test_v2_wheel_contract.py` pins all 14 v2 production modules and
  enforces, statically and offline: (1) every pinned v2 module appears in
  `REQUIRED_RUNTIME_MEMBERS`; (2) every pinned module exists in the source
  tree; (3) the Hatchling wheel selection keeps
  `packages = ["src/vespercode"]` and the `vespercode/**/*.py` include;
  (4) the pin stays in lockstep with the source tree (discovery via
  `v2*.py` plus `relaxed_policy.py`/`runtime_v2.py`), so a new v2 module
  cannot appear without the contract growing with it. The guard runs in
  the CI `unit-test` job through the same v2 discover command.
- **Intended RED:** the contract additions were staged first (an honest
  order deviation for a config-list change), so RED evidence was captured
  by temporarily reverting only the uncommitted member additions — the
  parent's baseline untouched — and running the guard:
  `test_every_v2_production_module_is_a_required_wheel_member` failed
  listing exactly the six missing modules. The other three guard tests
  passed against the reverted contract (they test the tree and pyproject,
  not the member list). Re-applying the additions turned the guard green
  (4/4).
- **Verification:** full v2 suite 145 tests, 0 failures, 2 controlled
  symlink skips; compileall over `src`, `tests/unit/v2`, and the smoke
  contract file (syntax proof without pytest); `git diff --check`; demo.
  The pytest/pipx-gated real-wheel smoke suite cannot run on this host
  (pytest, build, and pipx are not installed) and is not claimed — the
  static guard plus the contract listing are this round's deliverable.
- **Dependencies:** RA-08. **Parallelizable:** no; packaging contract
  pass over the v2 module surface.
- **Status:** complete in the current worktree; implementation commit pending.

## Task B1-01 — Route B1: candidate/validation/reference identity contracts

- **Goal:** give the v2 control plane the record vocabulary that replaces
  the v1 digest-bound candidate identity, final diff, validation manifest,
  and reference profile manifest — opaque IDs, non-negative revisions, a
  bounded candidate status, five-key validation run/result records with a
  bounded status/error, a reference profile record keyed by id + revision
  with declared metadata as configuration, and a pure fail-closed evidence
  binding check.
- **Files:** `src/vespercode/candidate/v2_candidate.py` (new),
  `src/vespercode/contracts/v2_validation.py` (new),
  `src/vespercode/profiles/v2_reference.py` (new),
  `src/vespercode/contracts/v2_identity.py` (new id generators),
  `tests/unit/v2/test_v2_candidate_control.py` (new),
  `tests/unit/v2/test_v2_validation_contracts.py` (new),
  `tests/unit/v2/test_v2_b1_v1_separation.py` (new).
- **Implementation:** `CandidateControlIdentityV2`
  (candidate_id/snapshot_id/revision/status, statuses bounded to
  ACTIVE/SUPERSEDED) and `CandidateDiffRecordV2`
  (diff_id/candidate_id/candidate_revision/artifact_id);
  `advance_candidate_revision` models the content-mutation transition
  (revision + 1 only — no identity regeneration);
  `ReferenceProfileRecordV2` keyed by reference_profile_id +
  profile_revision with declared Python/pytest/Ruff/Mypy versions as plain
  configuration; `ValidationBindingV2`/`ValidationRunRecordV2`/
  `ValidationResultV2` carrying the five control keys with
  PENDING/PASSED/FAILED statuses, an error required exactly for FAILED,
  and a 512-character error bound; `verify_evidence_binding` rejects a
  result from another run, a re-bound result, or any key mismatch with the
  currently expected binding (including stale revisions). Strict
  exact-field mapping parsers reject unknown and missing fields, so
  v1-shaped digest payloads never parse as v2 authority.
- **Intended RED:** `ModuleNotFoundError` for the three new modules (and
  missing id generators), plus the missing-module failures of the static
  v1-separation guard.
- **Verification:** `python -m unittest tests.unit.v2.test_v2_candidate_control
  tests.unit.v2.test_v2_validation_contracts tests.unit.v2.test_v2_b1_v1_separation -v`
  (23 tests), then the full v2 suite.
- **Dependencies:** V2-01 vocabulary. **Parallelizable:** the three modules
  are independent of the storage slice (B1-02) but the tests were written
  and turned green together with them.
- **Status:** complete in the current worktree; implementation commit pending.

## Task B1-02 — Route B1: durable validation/reference storage (v3 schema)

- **Goal:** persist the B1 records in the existing v3 v2 schema with strict
  schema validation and fail-closed creation rules, without migrating any
  v1 row and without disturbing the Route A transaction/writeback/recovery
  invariants.
- **Files:** `src/vespercode/storage/v2_database.py`,
  `tests/unit/v2/test_v2_validation_storage.py` (new).
- **Implementation:** three new tables in the v3 schema —
  `reference_profiles` (PK (reference_profile_id, profile_revision),
  declared metadata), `candidate_diffs` (one authoritative diff per
  candidate revision, FK to artifacts/runs/candidates), and
  `validation_runs` (five-key binding, bounded status CHECK, bounded
  error length, composite FK to reference_profiles). All three join
  `_V2_TABLES`/`_V2_REQUIRED_COLUMNS`, so open and initialize validate
  their columns fail-closed. New methods: `get_candidate_control`
  (row-to-record projection that revalidates the shape at read time),
  `create_reference_profile`/`get_reference_profile` (immutable
  id+revision key, duplicate re-declaration rejects),
  `create_candidate_diff`/`get_candidate_diff` (same-run candidate and
  artifact checks, current-revision check, unique per revision),
  `create_validation_run` (same-run candidate, current revision, known
  profile revision; inserts PENDING), `get_validation_run` (revalidating
  read), `record_validation_result` (one-shot PENDING->terminal, bounded
  status/error, unknown id returns False). No schema version bump: the
  parent directed the tables into the v3 schema; the strict table-set and
  column validation reject pre-B1 v3 databases fail-closed, no data
  migration happens, and a fresh database path is required.
- **Intended RED:** `AttributeError` for every new method, the fresh
  database missing the three tables, and open accepting malformed B1
  tables (the DROP+recreate probes failed on the then-missing tables).
- **Verification:** `python -m unittest tests.unit.v2.test_v2_validation_storage -v`
  (11 tests), then the full v2 suite (179 tests) proving Route A
  transaction/writeback/recovery tests still pass.
- **Dependencies:** B1-01 contracts. **Parallelizable:** no; one schema
  module.
- **Status:** complete in the current worktree; implementation commit pending.

## Task B1-03 — Route B1: wheel contract and documentation

- **Goal:** keep the packaging guard in lockstep with the three new v2
  production modules and record the B1 boundary in the process documents,
  clearly marking the remaining Route B slices as not started.
- **Files:** `tests/unit/v2/test_v2_wheel_contract.py` (pin),
  `tests/smoke/package/test_wheel_contents.py`
  (`REQUIRED_RUNTIME_MEMBERS`), `SPEC.md`, `PLAN.md`, `README.md`,
  `SPEC_PROCESS.md`, `AGENT_LOG.md`.
- **Implementation:** the pin grows to 17 v2 production modules
  (candidate/v2_candidate.py, contracts/v2_validation.py,
  profiles/v2_reference.py added); the smoke contract gains the three
  matching wheel members. SPEC gains FR-V2-VALIDATION (Route B1), the
  three tables in the data model, Route B1 acceptance criteria, and risk
  notes; README documents the new modules and the control-plane-only
  validation semantics; SPEC_PROCESS and AGENT_LOG record the RED/GREEN
  evidence and the v3-schema decision.
- **Intended RED:** `test_the_pin_covers_every_v2_module_in_the_source_tree`
  failed with `tree-only=['candidate/v2_candidate.py',
  'contracts/v2_validation.py', 'profiles/v2_reference.py']` the moment
  the modules existed — the natural packaging RED; the pin and member
  updates turned it green.
- **Verification:** full v2 suite (179 tests, 0 failures, 2 controlled
  symlink skips), `python -m compileall -q` over `src/vespercode`,
  `tests/unit/v2`, and the smoke contract file, `git diff --check`, and
  the repeatable demo.
- **Dependencies:** B1-01, B1-02. **Parallelizable:** documentation can be
  reviewed independently.
- **Status:** complete in the current worktree; implementation commit pending.
- **Boundary:** Route B2 (disclosure/provider), WebUI/CLI, Docker
  validation, and any release work are **not started** in this slice.

## Task B1-04 — Route B1 hardening: currency-checked result terminalization

- **Goal:** close the parent-review IMPORTANT finding:
  ``record_validation_result`` only CASed ``validation_runs.status =
  'PENDING'``; it never verified that the candidate's current revision
  still equaled the run's recorded ``candidate_revision``, that the
  candidate still belonged to the run, or that the referenced reference
  profile revision still existed — so an old validation run could be
  terminalized after candidate advancement or profile state drift,
  leaving misleading terminal evidence in the database.
- **Files:** `src/vespercode/storage/v2_database.py`,
  `tests/unit/v2/test_v2_validation_storage.py`.
- **Implementation:** inside one SQLite transaction,
  ``record_validation_result`` now loads the validation row's binding,
  verifies the candidate still belongs to the validation run's run at
  the recorded revision, and verifies the referenced profile revision
  still exists and revalidates as a ``ReferenceProfileRecordV2``; only
  then does the one-shot ``PENDING`` -> terminal update run. Any drift
  (stale revision, lost run ownership, missing or corrupted profile row)
  rejects with a closed ``V2DatabaseError`` and leaves the run
  ``PENDING`` — no terminal evidence is written for a non-current
  binding. Unknown runs and already-terminal runs still return False
  without mutation, and the bounded status/error validation still runs
  first.
- **Intended RED:** four regressions failed with
  ``AssertionError: V2DatabaseError not raised`` against the pre-fix
  code (stale candidate revision, run ownership drift, missing reference
  profile row, corrupted reference profile row), each also asserting the
  run stays PENDING afterwards; the stale case additionally asserts that
  malformed outcomes still reject first and that a fresh run at the
  current revision still terminalizes.
- **Verification:** full v2 suite (`python -m unittest discover -s
  tests/unit/v2 -v`, 183 tests, 0 failures, 2 controlled symlink skips;
  was 179), compileall over `src/vespercode` and `tests/unit/v2`,
  `git diff --check`.
- **Dependencies:** B1-02. **Parallelizable:** no; hardening pass over
  the B1 storage boundary.
- **Status:** complete in the current worktree; implementation commit pending.

## Task B2-01 — Route B2: disclosure/credential/endpoint contracts and pure policy

- **Goal:** give the v2 control plane the record vocabulary and pure
  policy that replace the v1 digest-bound disclosure plane — a grant
  keyed by `grant_id`/`disclosure_id` with run, reference profile
  id/revision, ISO-8601 expiry, bounded byte budget, granted
  categories/path scopes, and a `PENDING`/`ACTIVE`/`REVOKED`/
  `EXPIRED`/`EXHAUSTED` lifecycle; a per-request authorization keyed
  by `authorization_id` plus grant/run/request/endpoint references,
  sources, bounded charge, and a one-shot `AUTHORIZED`/`CONSUMED`
  state; an injectable provider-agnostic credential port with a
  redacted, non-comparable, non-serializable secret wrapper; and an
  immutable provider endpoint record keyed by `endpoint_id`.
- **Files:** `src/vespercode/governance/v2_disclosure.py` (new),
  `src/vespercode/credentials/v2_port.py` (new),
  `src/vespercode/profiles/v2_endpoints.py` (new),
  `src/vespercode/contracts/v2_identity.py` (four new id
  generators), `tests/unit/v2/test_v2_disclosure_contracts.py` (new),
  `tests/unit/v2/test_v2_credentials_port.py` (new).
- **Implementation:** frozen slots dataclasses validating every field
  at construction (bounded identifiers, non-negative revisions,
  bounded charge/budget, ISO-8601 timestamps, closed status
  vocabularies); `ROOT`/`FILE`/`DIRECTORY` path scopes with exact,
  segment-boundary, and root matching over canonical relative paths;
  canonical category/scope/source sequences (non-empty, deduplicated,
  `ROOT` alone, deterministic order); `FILE_CONTENT` requires a path,
  every other category forbids one; the pure grant expiry check
  (naive timestamps read as UTC), the pure source-scope check raising
  a closed `DisclosureScopeErrorV2`, and the replay payload key;
  closed outcome kinds with static messages; strict exact-field
  parsers rejecting v1 digest payloads.  The credential port wraps
  hidden input in a `V2CredentialSecret` (redacted repr, comparison
  and copy/pickle disabled, single `reveal` accessor), validates
  provider names as short identifiers, projects status as
  provider/configured/updated-at only, and ships the deterministic
  `InMemoryV2CredentialProvider` as the B2 port implementation (real
  OS credential integration is out of scope).
- **Intended RED:** `ModuleNotFoundError: No module named
  'vespercode.governance.v2_disclosure'` / `'vespercode.credentials.v2_port'`
  on the first test run, plus the missing-module failures of the B2
  separation guard; then shape rejections (mixed `ROOT` scopes,
  duplicate categories, out-of-vocabulary statuses, non-canonical
  paths, unparseable expiry, v1-shaped mapping payloads, comparable
  or serializable secrets) — all captured before any implementation
  landed.
- **Verification:** `python -m unittest tests.unit.v2.test_v2_disclosure_contracts
  tests.unit.v2.test_v2_credentials_port -v` (34 tests), then the full
  v2 suite.
- **Dependencies:** V2-01 vocabulary; B1-01 record conventions.
  **Parallelizable:** the contract modules are independent of the
  storage slice (B2-03) but were test-driven together with it.
- **Status:** complete in the current worktree; implementation commit pending.

## Task B2-02 — Route B2: provider endpoint and disclosure grant storage (v3 schema)

- **Goal:** persist the B2 records in the existing v3 v2 schema with
  strict schema validation and fail-closed creation/activation rules,
  without migrating any v1 row and without disturbing the Route A/B1
  invariants.
- **Files:** `src/vespercode/storage/v2_database.py`,
  `tests/unit/v2/test_v2_disclosure_ledger.py` (new).
- **Implementation:** six new tables in the v3 schema —
  `provider_endpoints` (immutable per `endpoint_id`),
  `disclosure_grants` (PK `grant_id`, `UNIQUE(disclosure_id)`, FK to
  disclosures/runs, bounded budget/consumed/status CHECKs),
  `disclosure_grant_categories`/`disclosure_grant_scopes` (ordered,
  position-keyed children), `disclosure_authorizations` (PK
  `authorization_id`, `UNIQUE(grant_id, request_id)`, FK to
  grants/runs/endpoints, bounded charge/status CHECKs),
  `disclosure_authorization_sources` (ordered source children).  All
  six join `_V2_TABLES`/`_V2_REQUIRED_COLUMNS`, so open and initialize
  validate their columns fail-closed; the schema version stays 3, so
  a database created before B2 is rejected (no in-place migration).
  New methods: `create_provider_endpoint`/`get_provider_endpoint`
  (duplicate declaration rejects), `create_disclosure_grant`
  (validates the record shape first, then the disclosure/run binding,
  the reference profile revision, and the one-grant-per-disclosure
  rule; inserts `PENDING` with consumed 0),
  `get_disclosure_grant`/`get_disclosure_grant_by_disclosure`
  (revalidating read projections),
  `activate_disclosure_grant` (one-shot `PENDING`→`ACTIVE` user
  approval), `revoke_disclosure_grant` (terminal from
  `PENDING`/`ACTIVE`).
- **Intended RED:** `AttributeError` for every new method, the fresh
  database missing the six tables, and open accepting malformed B2
  tables (the DROP+recreate probes failed on the then-missing
  tables); the corrupted-grant read probe initially failed because
  the status CHECK constraint blocked the corruption UPDATE —
  evidence the DDL itself is fail-closed — so the probe corrupts the
  unchecked `expires_at` column instead and the revalidating read
  rejects it.
- **Verification:** `python -m unittest tests.unit.v2.test_v2_disclosure_ledger -v`
  (schema, lifecycle, and authorization cases), then the full v2 suite
  proving Route A/B1 tests still pass.
- **Dependencies:** B2-01 contracts, B1-02 schema conventions.
  **Parallelizable:** no; one schema module.
- **Status:** complete in the current worktree; implementation commit pending.

## Task B2-03 — Route B2: atomic disclosure authorization ledger and provider call boundary

- **Goal:** charge requests against grants atomically or not at all,
  and make the provider call a one-call, no-retry, sanitized
  boundary that never carries a credential value outside the call
  frame.
- **Files:** `src/vespercode/storage/v2_database.py`
  (`authorize_disclosure_request`, `get_disclosure_authorization`,
  `consume_disclosure_authorization`),
  `src/vespercode/providers/v2_call.py` (new),
  `tests/unit/v2/test_v2_disclosure_ledger.py`,
  `tests/unit/v2/test_v2_provider_call.py` (new).
- **Implementation:** `authorize_disclosure_request` runs every check
  inside one `BEGIN IMMEDIATE` transaction and returns a closed
  outcome record: unknown grant / run mismatch / `PENDING` (no user
  approval) / `REVOKED` / `EXHAUSTED` / `EXPIRED` reject with zero
  charge; a stale-but-`ACTIVE` grant is flipped to `EXPIRED` and
  rejected in the same commit; an unknown endpoint or a
  profile/revision binding mismatch (endpoint vs grant, by control
  IDs and revisions) rejects; an existing `(grant_id, request_id)`
  authorization is an exact-payload `REPLAY` return (no second
  charge) or a `REPLAY_CONFLICT` rejection; the requested sources
  are checked against the granted categories and path scopes; the
  cumulative budget check commits the authorization row, its source
  rows, and the new consumed total together, flipping `EXHAUSTED`
  when the budget is fully consumed.  `consume_disclosure_authorization`
  is a one-shot CAS over all four control references.
  `V2ProviderCallService` (over the injected database, credential
  port, transport, and clock) re-checks the endpoint's
  provider/profile declaration, the authorization's
  grant/run/request/endpoint binding and `AUTHORIZED` state, and
  the grant's `ACTIVE`/unexpired status, fetches the credential
  inside the boundary, consumes the authorization one-shot *before*
  the transport call (a duplicate call can never double-call the
  provider; a failed call burns its authorization — no refund), then
  performs exactly one transport call; any exception or non-success
  response maps to the closed `PROVIDER_CALL_FAILED` code with a
  static message (raw exception text discarded), and no retry is
  attempted.  The request/response records carry control references
  only.
- **Intended RED:** `ModuleNotFoundError` for the provider module
  plus `AttributeError` for the ledger methods; then the behavioral
  regressions — budget-race double-charge, replay double-charge,
  consume-twice, revoked-grant call, missing-credential consumption,
  and the secret-in-outcome probe — all failed against the
  not-yet-implemented boundary and went green with it.
- **Verification:** `python -m unittest tests.unit.v2.test_v2_disclosure_ledger
  tests.unit.v2.test_v2_provider_call -v`, then the full v2 suite
  (252 tests, 0 failures, 2 controlled symlink skips; was 183).
- **Dependencies:** B2-01, B2-02. **Parallelizable:** no; the ledger
  and the call boundary share the authorization state machine.
- **Status:** complete in the current worktree; implementation commit pending.

## Task B2-04 — Route B2: wheel contract, separation guard, and documentation

- **Goal:** keep the packaging guard in lockstep with the four new v2
  production modules, pin the v1 separation and no-digest constraints
  statically, and record the B2 boundary in the process documents,
  clearly marking the remaining Route B slices as not started.
- **Files:** `tests/unit/v2/test_v2_wheel_contract.py` (pin),
  `tests/smoke/package/test_wheel_contents.py`
  (`REQUIRED_RUNTIME_MEMBERS`),
  `tests/unit/v2/test_v2_b2_v1_separation.py` (new),
  `SPEC.md`, `PLAN.md`, `README.md`, `SPEC_PROCESS.md`,
  `AGENT_LOG.md`.
- **Implementation:** the pin grows to 21 v2 production modules and
  the smoke contract gains the four matching wheel members
  (`credentials/v2_port.py`, `governance/v2_disclosure.py`,
  `profiles/v2_endpoints.py`, `providers/v2_call.py`); the new
  separation guard statically pins that the B2 modules import no v1
  authority module and no `hashlib` (digest identity stays out of
  the v2 authorization plane).  SPEC gains FR-V2-DISCLOSURE, the six
  tables in the data model, Route B2 acceptance criteria and risks,
  the updated credential threat model, and the Route B2 mechanism
  paragraph; README documents the new modules and semantics;
  SPEC_PROCESS and AGENT_LOG record the RED/GREEN evidence and the
  in-place v3 decision.
- **Intended RED:** the natural packaging RED —
  `test_the_pin_covers_every_v2_module_in_the_source_tree` failed
  with `tree-only=['credentials/v2_port.py',
  'governance/v2_disclosure.py', 'profiles/v2_endpoints.py',
  'providers/v2_call.py']` the moment the modules existed; the pin and
  member updates turned it green.
- **Verification:** full v2 suite (`python -m unittest discover -s
  tests/unit/v2 -v`, 252 tests, 0 failures, 2 controlled symlink
  skips), `python -m compileall -q` over `src/vespercode`,
  `tests/unit/v2`, and the smoke contract file, `git diff --check`,
  and the repeatable demo.
- **Dependencies:** B2-01..B2-03. **Parallelizable:** documentation can
  be reviewed independently.
- **Status:** complete in the current worktree; implementation commit pending.
- **Boundary:** B3 (WebUI/CLI integration), Docker validation
  execution, the real OS credential adapter, real provider
  transports, release automation, and the validation executor are
  **not started** in this slice.

## Task B2-05 — Route B2 hardening: capability-gated reveal and atomic consume revalidation

- **Goal:** close the two IMPORTANT findings from the main-thread B2
  review: (1) ``V2CredentialSecret.reveal`` was a public no-argument
  method, so any code holding a wrapper could obtain the raw secret —
  the "only the provider call boundary consumes reveal" rule was
  documentation, not API; (2) the provider call service read the grant
  and then consumed the authorization with a plain status CAS, so a
  revocation or an expiry crossing between the read and the consume
  still allowed the provider call.
- **Files:** `src/vespercode/credentials/v2_port.py`,
  `src/vespercode/governance/v2_disclosure.py`,
  `src/vespercode/providers/v2_call.py`,
  `src/vespercode/storage/v2_database.py`,
  `tests/unit/v2/test_v2_credentials_port.py`,
  `tests/unit/v2/test_v2_disclosure_ledger.py`,
  `tests/unit/v2/test_v2_provider_call.py`.
- **Implementation:** the port now mints a private, single-instance
  reveal capability (``_RevealCapability`` / ``_provider_reveal_capability``,
  private by spelling, identity-checked) and ``reveal`` requires it —
  a missing argument rejects with ``TypeError`` and any other value
  (including a fresh look-alike instance of the private class) rejects
  with the closed ``CREDENTIAL_REVEAL_FORBIDDEN`` error; no public API
  of the module exposes the capability, and the provider call service
  obtains it only through the documented module-private friend seam.
  ``consume_disclosure_authorization`` is now one transaction that
  revalidates the full binding (authorization id, grant id, run id,
  request id), the ``AUTHORIZED`` status, the grant's ``ACTIVE``
  state and its expiry as of an explicit deterministic ``now``
  parameter (the service passes its injectable clock, so the
  consume-time recheck is deterministic), and the endpoint/profile
  binding (tamper evidence); it returns a closed
  ``DisclosureConsumeOutcomeV2`` (``CONSUMED``/``NOT_AUTHORIZED``/
  ``GRANT_NOT_ACTIVE``) so the service maps a lost race to the right
  failure code with zero transport calls.  Corrupted or missing
  control rows reject fail-closed with ``V2DatabaseError`` and the
  transaction rolls back; consumed authorizations are never refunded
  after provider failure and the no-retry semantics are unchanged.
- **Intended RED:** the capability tests failed with ``ImportError``
  (no seam existed) and ``assertRaises`` misses (``reveal()`` with no
  argument succeeded); the consume tests failed with
  ``AttributeError`` (``bool`` has no ``kind``) and
  ``AssertionError: V2DatabaseError not raised`` (tamper probes); both
  race regressions failed with ``AssertionError: 'SUCCEEDED' !=
  'FAILED'`` against the pre-fix code — the hostile-credential-store
  revocation between read and consume, and the clock crossing the
  expiry between the grant check and the consume, both let the
  provider call proceed.
- **Verification:** full v2 suite (`python -m unittest discover -s
  tests/unit/v2 -v`, 260 tests, 0 failures, 2 controlled symlink
  skips; was 252; +8 hardening tests), compileall over
  `src/vespercode`, `tests/unit/v2`, and the smoke contract file,
  `git diff --check`, the repeatable demo, and a runtime probe that
  the capability is absent from the public surface and that importing
  the B2 modules loads no v1/digest module.
- **Dependencies:** B2-01..B2-04. **Parallelizable:** no; hardening
  pass over the frozen credential and provider call boundaries.
- **Status:** complete in the current worktree; implementation commit pending.

## Task B3-01 — Route B3: the local v2 services shell

- **Goal:** compose one closed local domain surface over the Route A
  harness and the B2 credential port that the v2 CLI and WebUI share,
  without adding any new authority or table.
- **Files:** `src/vespercode/shell_v2.py` (new),
  `src/vespercode/storage/v2_database.py` (two bounded read
  projections only), `tests/unit/v2/test_v2_shell.py` (new).
- **Implementation:** `V2LocalShell` composes a real `V2Harness`
  (control database under `<workspace>/.vespercode`), a writeback
  service whose policy additionally denies the control-plane
  directory, durable recovery, and the B2 in-memory credential port;
  run start runs only behind an injected LLM factory (`None` composes
  no LLM: `NO_LLM_BOUNDARY` fail-closed, zero run rows); each run's
  writeback is bound to the staged operations observed when that run
  was staged (process-local staging; a fresh process gets
  `NOTHING_STAGED`); writeback approval re-checks run/candidate/revision
  bindings before creation; every projection is bounded and
  non-revealing (the credential status carries provider, configured
  flag, update time only; disclosure summaries carry opaque IDs,
  status, expiry, and budget counters only).  `V2Database` gains only
  `list_runs`/`list_disclosure_grants` (fail-closed 1..500 limits, no
  schema change, no new table).
- **Intended RED:** `test_v2_shell` failed to import
  (`ModuleNotFoundError: No module named 'vespercode.shell_v2'`) and
  the wheel-contract pin drifted (`pin-only=['cli_v2.py',
  'shell_v2.py', 'web/v2_app.py', 'web/v2_forms.py',
  'web/v2_security.py', 'web/v2_server.py']`) the moment the pin was
  extended before the modules existed.
- **Verification:** the shell's own unit tests over a real temporary
  workspace (real disk writes, real recovery, control-directory
  denial, non-revealing projections) inside the full suite.
- **Dependencies:** Route A, B1, B2. **Parallelizable:** the shell and
  the web security/forms modules were developed together; the shell
  contract is testable independently of the CLI/WebUI.
- **Status:** complete in the current worktree; implementation commit pending.

## Task B3-02 — Route B3: the loopback WebUI security boundary

- **Goal:** give the v2 local WebUI an independent, standard-library
  request-security boundary: loopback-only binding, bounded sessions,
  and the fixed HOST -> SESSION -> ORIGIN -> CSRF authorization order.
- **Files:** `src/vespercode/web/v2_security.py` (new),
  `tests/unit/v2/test_v2_web_security.py` (new).
- **Implementation:** the closed `V2LocalSecurityConfig` binds
  `127.0.0.1` only with a validated port and exact cookie/CSRF field
  names; `V2LocalSessionManager` creates bounded sessions (independent
  256-bit tokens, bounded TTL, bounded concurrency, injectable
  epoch-milliseconds clock and token generator, pruning at create);
  `verify_v2_local_request` validates one request in the fixed order —
  HOST, SESSION cookie equality, then (state-changing methods only)
  a loopback Origin matching the request's own Host and the CSRF
  synchronizer token — first failure wins with a stable closed code,
  status, and bounded payload; `v2_security_headers` carries the exact
  CSP (the nonce path never widens scripts to `unsafe-inline`) plus
  nosniff, frame-deny, and no-referrer.
- **Intended RED:** the security tests failed to import
  (`ModuleNotFoundError: No module named 'vespercode.web.v2_security'`);
  two expectation bugs surfaced during the RED→GREEN loop and were
  corrected as test-side decisions: incidental whitespace around a
  Host header is stripped (matching ordinary HTTP token handling, as
  the v1 boundary also does), and the CSP's deliberately inline
  `style-src` exception is asserted against `script-src` specifically.
- **Verification:** the security unit tests (config bounds, token
  forms, expiry, session limits, check order, origin binding, header
  exactness) inside the full suite.
- **Dependencies:** none (pure boundary). **Parallelizable:** yes;
  independent of the shell and CLI tasks.
- **Status:** complete in the current worktree; implementation commit pending.

## Task B3-03 — Route B3: typed allowlisted form contracts

- **Goal:** make every WebUI endpoint's input shape a closed contract
  so malformed, polluted, or unconfirmed forms reject with zero domain
  calls.
- **Files:** `src/vespercode/web/v2_forms.py` (new),
  `tests/unit/v2/test_v2_web_forms.py` (new).
- **Implementation:** each endpoint names one `V2FormContract` — an
  exact field set with per-field closed parsers (bounded opaque
  identifiers, non-negative decimal revisions, bounded task text, the
  literal `CONFIRM`, the 64-hex CSRF token form); `parse` requires
  the exact key set (unknown/missing fields reject with closed
  codes); `parse_v2_urlencoded` rejects duplicate fields (HTTP
  parameter pollution) and bounded-excessive field counts.  No form
  carries a path, a policy/profile override, a provider URL, a
  secret, or file content.
- **Intended RED:** the forms tests failed to import
  (`ModuleNotFoundError: No module named 'vespercode.web.v2_forms'`);
  the disclosure-grant fixtures additionally revealed the closed
  category/scope vocabulary (`FILE_CONTENT`, `ROOT` scope) during the
  fixture repair.
- **Verification:** the forms unit tests (per-contract happy paths,
  unknown/missing/duplicate/malformed rejections, closed literals)
  inside the full suite.
- **Dependencies:** none (pure contracts). **Parallelizable:** yes.
- **Status:** complete in the current worktree; implementation commit pending.

## Task B3-04 — Route B3: the framework-agnostic WebUI application

- **Goal:** compose the closed route surface over the injected shell:
  fixed security order before any parsing or domain call, binding
  pre-checks before any mutation, escaped bounded projections, and
  the explicit `CONFIRM` gate on every mutation.
- **Files:** `src/vespercode/web/v2_app.py` (new),
  `tests/unit/v2/test_v2_web_app.py` (new).
- **Implementation:** a closed route table (one GET/POST pair per
  control; static 404/405 with security headers otherwise); `handle`
  runs route resolution, then the host check, then session resolution
  (safe GET reads without a session establish one and respond with
  Set-Cookie; state changes require a live session and reject
  missing/invalid/expired), then `verify_v2_local_request` for
  cookie-resolved requests; each mutation parses its contract, then
  re-checks the run/candidate/revision binding, then calls the shell;
  `V2ShellError` maps to bounded status pages by closed code
  (`NO_LLM_BOUNDARY` → 503, unknown bindings → 404, stale/not-staged
  → 409); every dynamic value renders through `html.escape`; pages
  carry only bounded control-plane facts (never a secret, file
  content, or request body).
- **Intended RED:** the app tests failed to import
  (`ModuleNotFoundError: No module named 'vespercode.web.v2_app'`);
  during the GREEN loop the first `handle` draft wrongly passed a
  freshly created session through the cookie-equality verify (401 on
  the home page) and the test helper omitted the CSRF token — both
  surfaced as 401/403 cascades and were fixed to the documented
  flow: a fresh session serves the safe read directly after the host
  check; cookie-resolved requests go through the fixed-order verify.
- **Verification:** the app unit tests with a recording shell (zero
  shell calls on malformed/unauthenticated forms, zero mutation calls
  on unknown/stale/mismatched bindings, CSRF/origin/session
  ordering, escaping, non-revealing credential/disclosure pages)
  inside the full suite.
- **Dependencies:** B3-01..B3-03. **Parallelizable:** no; composes all
  three.
- **Status:** complete in the current worktree; implementation commit pending.

## Task B3-05 — Route B3: the standard-library loopback server adapter

- **Goal:** serve the WebUI contract on the literal loopback host only
  through `http.server`, with bounded bodies, closed methods, and
  silent logs — no FastAPI, no third-party package.
- **Files:** `src/vespercode/web/v2_server.py` (new),
  `tests/unit/v2/test_v2_web_server.py` (new).
- **Implementation:** `v2_make_handler` bridges `BaseHTTPRequestHandler`
  to the app: headers lower-cased, cookies through the standard jar,
  query strings and URL-encoded bodies through the closed v2 form
  rules (duplicate fields reject); request bodies are bounded
  (64 KiB) and must carry the URL-encoded content type — 415/413
  reject before parsing with the rejected body drained bounded (16
  MiB cap) so the client can read the rejection; GET/POST dispatch
  and other methods reject 405; nothing about a request is logged;
  responses always close the connection (no desync on rejected
  bodies).  `v2_serve_forever` validates the literal loopback host and
  the closed port range before any socket opens and serves
  single-threaded on the caller's thread (the composition shares one
  SQLite connection with its shell: serve from the creating thread —
  the CLI `serve` command does exactly that).
- **Intended RED:** the server tests failed to import
  (`ModuleNotFoundError: No module named 'vespercode.web.v2_server'`);
  the GREEN loop fixed the oversized-body case to drain the rejected
  body before responding (the client otherwise hit a reset while
  still sending) and the end-to-end smoke exposed the SQLite
  single-thread constraint for background-thread serving, which is
  documented rather than silently crossed.
- **Verification:** real-loopback-socket unit tests on an ephemeral
  port with a fake shell (home page with security headers and
  Set-Cookie, 404/405/413/415/400 transport rejections, launcher
  host/port validation) inside the full suite.
- **Dependencies:** B3-04. **Parallelizable:** no; the transport seam
  of the app contract.
- **Status:** complete in the current worktree; implementation commit pending.

## Task B3-06 — Route B3: the closed v2 CLI, wheel contract, and documentation

- **Goal:** give v2 its own closed console surface, keep the packaging
  guard in lockstep with the six new modules, and record the B3
  boundary in the process documents — clearly marking B4
  (Docker/release/public deployment) as not started.
- **Files:** `src/vespercode/cli_v2.py` (new),
  `tests/unit/v2/test_cli_v2.py` (new),
  `tests/unit/v2/test_v2_b3_v1_separation.py` (new),
  `tests/unit/v2/test_v2_wheel_contract.py` (pin),
  `tests/smoke/package/test_wheel_contents.py`
  (`REQUIRED_RUNTIME_MEMBERS`), `pyproject.toml`
  (`vespercode-v2` entry point only; the legacy `vespercode` entry
  point untouched), `SPEC.md`, `PLAN.md`, `README.md`,
  `SPEC_PROCESS.md`, `AGENT_LOG.md`.
- **Implementation:** a closed argparse grammar — `run`, `status`,
  `writeback`, `recovery`, `credential-status`, `disclosure-status`,
  `serve` — with every argument bounded and typed (existing workspace
  directory, bounded task text, bounded opaque identifiers, closed
  decimal counts/ports, literal loopback host) and no shell, argv
  passthrough, provider-URL, secret, policy, or profile option;
  writeback and recovery preview by default and require `--apply`
  (`recovery --apply` additionally requires `--transaction-id`);
  bounded non-revealing projections with closed `error: <code>` lines
  and nonzero exits; the injectable `V2CliComposition` (LLM factory,
  shell factory, server launcher, output streams) keeps every behavior
  offline-testable.  The wheel pin grows to 27 v2 production modules
  and the smoke contract gains the matching members
  (`cli_v2.py`, `shell_v2.py`, `web/v2_app.py`, `web/v2_forms.py`,
  `web/v2_security.py`, `web/v2_server.py`); a static B3 separation
  guard pins that the B3 modules import no v1 authority module, no
  `hashlib`, and no third-party package.  SPEC gains FR-V2-LOCALUI,
  the Route B3 architecture/data-model notes (no new tables), Route
  B3 acceptance criteria, risks, and the mechanism paragraph;
  README documents the CLI/WebUI usage, the entry points, the
  limitations, and the not-started B4 boundary; SPEC_PROCESS and
  AGENT_LOG record the RED/GREEN evidence.
- **Intended RED:** the natural packaging RED — the pin drift test
  failed with `pin-only=['cli_v2.py', 'shell_v2.py', ...]` and the
  required-member test failed until the smoke contract grew the
  matching members; the grammar test first over-forbade the bounded
  `--provider` lookup argument of `credential-status` and was
  corrected to forbid the provider-connection surface
  (`--provider-url`, `--api-key`, ...) instead.
- **Verification:** full v2 suite (`python -m unittest discover -s
  tests/unit/v2 -v`, 358 tests, 0 failures, 2 controlled symlink
  skips; was 260; +98 B3 tests), compileall over `src/vespercode`,
  `tests/unit/v2`, and the smoke contract file, `git diff --check`,
  the repeatable demo, a runtime import probe (importing the whole
  B3 surface loads no v1 authority module), and an end-to-end CLI
  smoke (run → status → writeback preview → writeback --apply →
  credential-status → disclosure-status → real loopback `serve` with
  a fetched home page).
- **Dependencies:** B3-01..B3-05. **Parallelizable:** documentation can
  be reviewed independently.
- **Status:** complete in the current worktree; implementation commit pending.
- **Boundary:** B4 — Docker validation execution, release automation,
  the real OS credential adapter, real provider transports, and any
  public deployment — is **not started** in this slice; Route B is not
  fully complete.

## Task B3-07 — Route B3 hardening: manager-bound request authorization

- **Goal:** close the parent-review security finding — the original
  ``verify_v2_local_request`` took a caller-provided ``session``
  object and checked cookie/CSRF equality against it, but never proved
  that the session was registered in the WebUI's session manager or
  still live; a caller passing a forged or expired session object
  with matching cookie/CSRF values would be authorized, because
  registration and liveness lived only in the caller-side resolution
  docstring.
- **Files:** ``src/vespercode/web/v2_security.py`` (the boundary),
  ``src/vespercode/web/v2_app.py`` (the only route handler),
  ``tests/unit/v2/test_v2_web_security.py``,
  ``tests/unit/v2/test_v2_web_app.py``, ``SPEC.md``, ``README.md``,
  ``SPEC_PROCESS.md``, ``AGENT_LOG.md``.
- **Implementation:** the session-taking verifier is **removed** and
  replaced by the manager-bound ``authorize_v2_local_request(*,
  method, headers, cookies, form, session_manager, config)``: one
  function performs the whole fixed order HOST → SESSION → ORIGIN →
  CSRF, where the SESSION check is self-contained — the cookie value
  must resolve to a session registered in the given
  ``V2LocalSessionManager`` (type-checked; the app hands its own) and
  must still be live at the manager's clock; a forged valid-looking
  session value or an expired one rejects with
  ``SESSION_INVALID``/``SESSION_EXPIRED`` **before** the Origin and
  CSRF checks, and an authorized result now carries the resolved live
  session (``V2RequestAuthorizationV2`` gained an optional,
  consistency-checked ``session`` field; rejected results never carry
  one).  Cookie equality with the resolved session holds by
  construction because the manager resolves the session from the
  exact cookie value.  ``V2LocalWebApp.handle`` now delegates to the
  authorizer for every request (no session object ever passes through
  the app into an authorization call — no such parameter exists), and
  a GET that fails only the session check auto-establishes a fresh
  session from the same manager (the host check has already passed
  inside the authorizer).  The server adapter is unchanged: it only
  bridges HTTP to ``app.handle``.
- **Intended RED:** (1) a throwaway probe against the pre-fix seam
  demonstrated the vulnerability exactly:
  ``forged unregistered session -> authorized: True`` and
  ``expired session -> authorized: True``; (2) the security tests
  were rewritten first to the manager-bound API and failed with
  ``ImportError: cannot import name 'authorize_v2_local_request'``
  (the seam did not exist), while the two new app-level pins
  (forged cookie and expired session → 401 with zero shell calls)
  passed against the app's existing manager-resolution behavior,
  pinning it through the refactor.
- **GREEN:** the manager-bound authorizer landed as above; all
  pre-existing order/code assertions moved to the new seam unchanged
  (host first, session before origin/csrf, origin before csrf, csrf
  correctness, origin binding, safe reads, PUT behavior) plus four new
  boundary tests (forged unregistered session, expired registered
  session, valid session resolves from the manager with identity,
  non-manager store rejects) and the record-consistency tests for the
  new ``session`` field.
- **Verification:** full v2 suite
  (``python -m unittest discover -s tests/unit/v2 -v``, 365 tests, 0
  failures, 2 controlled symlink skips; was 358; +7 tests),
  compileall over ``src/vespercode``, ``tests/unit/v2``, and the smoke
  contract file, ``git diff --check``, the repeatable demo, the
  post-fix probe (the old seam is gone: importing
  ``verify_v2_local_request`` now fails with ``ImportError``; the
  forged/expired scenarios reject with ``SESSION_INVALID``/
  ``SESSION_EXPIRED``), a real-loopback security smoke (forged cookie
  over the socket → 401 with zero shell calls), the end-to-end CLI
  smoke, and the runtime v1-import probe.
- **Dependencies:** B3-01..B3-06. **Parallelizable:** no; a hardening
  pass over the frozen security boundary.
- **Status:** complete in the current worktree; implementation commit pending.
- **Boundary:** B4 — Docker validation execution, release automation,
  the real OS credential adapter, real provider transports, and any
  public deployment — is **not started** in this slice; Route B is not
  fully complete.

## Task B4a-01 — Route B4a: the v2 Docker execution profile record

- **Goal:** give the v2 execution plane its configuration identity —
  an opaque execution-profile id + revision bound to an opaque
  reference profile id/revision, an opaque local image token, and the
  fail-closed isolation parameters — with no digest identity and no
  import of any v1 Docker/profile/validation authority.
- **Files:** ``src/vespercode/execution/v2_profile.py`` (new),
  ``tests/unit/v2/test_v2_execution_profile.py`` (new).
- **Implementation:** a frozen slots ``ExecutionProfileRecordV2`` with
  strict validators: opaque identifiers (64-hex digest-shaped values
  reject), non-negative revisions, a charset-closed ``image_reference``
  token (URLs, registry/repository/tag spellings, and digest shapes
  reject), a non-root ``uid:gid`` pair (both ids >= 1, decimal, no
  leading zeros), strict booleans, and bounded
  ``timeout_seconds``/``max_output_bytes`` ceilings (1..600 s,
  1..4 MiB).  The isolation policy is pinned fail-closed:
  ``network_disabled=True``, ``read_only_rootfs=True``,
  ``all_capabilities_dropped=True``, ``docker_socket_mounted=False``,
  ``workspace_mount_read_only=True`` — a widening profile is not
  constructible.  ``execution_profile_from_mapping`` is a strict
  exact-field parse: unknown or missing fields reject, so v1-shaped
  payloads (``schema_version``, gate digests, nested
  ``resources``/``environment`` blocks) never parse as a v2 profile.
- **Intended RED:** the new profile tests failed first with
  ``ModuleNotFoundError: No module named
  'vespercode.execution.v2_profile'`` (captured in the RED run).
- **Verification:** 19 deterministic profile-record tests (field-set
  closure, immutability, v1 payload rejection, digest-shape and
  URL/registry rejection, every isolation violation, user spellings,
  timeout/output bounds, revision/identifier/boolean strictness)
  inside the full suite.
- **Dependencies:** none within B4a (consumes the B1 reference-profile
  binding semantics only). **Parallelizable:** with B4a-02.
- **Status:** complete in the current worktree; implementation commit pending.

## Task B4a-02 — Route B4a: the closed execution request/result/outcome contracts and ports

- **Goal:** define the structured execution request the port accepts
  (never a shell or command string), the closed action vocabulary and
  per-kind argv grammar, the executor/readiness port protocols, and the
  sanitized caller-facing outcome shapes.
- **Files:** ``src/vespercode/execution/v2_execution.py`` (new),
  ``tests/unit/v2/test_v2_execution_request.py`` (new).
- **Implementation:** ``EXECUTION_ACTION_KINDS_V2`` (B4a:
  ``VALIDATE_CANDIDATE`` only) plus a read-only
  ``EXECUTION_ACTION_GRAMMARS_V2`` view pinning the frozen argv
  executable token and the exact argument count per kind.
  ``ExecutionActionRequestV2`` validates its control bindings
  (request, execution profile, reference profile — opaque ids with
  digest-shape rejection plus non-negative revisions) and its argv: a
  bare string rejects as a shell command string, argv[0] must equal the
  kind's frozen executable, the argument count is exactly the kind's
  grammar, and every argument is a bounded opaque token (no paths,
  URLs, options, whitespace, control characters, or digest shapes).
  The request field set carries no image, URL, registry, credential,
  environment, command, or shell field.
  ``ExecutionResultV2``/``ExecutionReadinessResultV2``/
  ``ExecutionOutcomeV2`` are closed-shape records — the outcome
  re-verifies at construction that its error code is from the closed
  set, its message is the static message of its own code, its exit
  code is bounded, and its excerpt is capped (2048 chars) and
  control-character-free.  ``V2ExecutionPort`` and ``V2ReadinessPort``
  are runtime-checkable injectable protocols.
- **Intended RED:** the request tests failed first with
  ``ModuleNotFoundError: No module named
  'vespercode.execution.v2_execution'`` (captured in the RED run).
- **Verification:** 15 deterministic request-contract tests plus the
  outcome closed-shape tests (under B4a-03's file) inside the full
  suite.
- **Dependencies:** B4a-01 (imports the profile record for the port
  signature). **Parallelizable:** with B4a-04's test authoring.
- **Status:** complete in the current worktree; implementation commit pending.

## Task B4a-03 — Route B4a: the execution service and the deterministic fakes

- **Goal:** run exactly one authorized execution over the injectable
  ports with a fixed fail-closed order and sanitized bounded outcomes,
  fully testable offline with deterministic fakes.
- **Files:** ``src/vespercode/execution/v2_executor.py`` (new),
  ``tests/unit/v2/test_v2_execution_service.py`` (new).
- **Implementation:** ``V2ExecutionService(profile, readiness,
  executor)`` type-checks the bound profile record and requires both
  ports; ``execute`` rejects a non-record request (a shell string)
  outright, then rejects execution-profile and reference-profile
  id/revision binding mismatches *before* the readiness port is
  consulted, then rejects a NOT_READY verdict *before* the executor is
  touched, then performs exactly one executor call with no automatic
  retry.  Any executor exception or hostile return maps to the closed
  ``EXECUTION_FAILED`` code with the static message — raw exception
  text is discarded.  Executor reports map to sanitized outcomes with
  a bounded, control-free excerpt (the sanitizer caps at 2048
  characters; the outcome record re-verifies).  ``FakeV2Executor`` and
  ``FakeV2Readiness`` are the shipped deterministic fakes that record
  every call for the offline tests.
- **Intended RED:** the service tests failed first with
  ``ModuleNotFoundError: No module named
  'vespercode.execution.v2_execution'`` (the service file imports the
  contracts first; captured in the RED run).  One GREEN-loop fix: the
  readiness record needed ``reason: str | None = None`` so the READY
  spelling (``ExecutionReadinessResultV2("READY")``) constructs —
  the default-fake construction caught it immediately.
- **Verification:** 17 deterministic service tests (happy path, binding
  order, all three NOT_READY reasons, exception sanitization with a
  planted fake secret, failure/timeout mapping, hostile returns,
  bounded sanitized excerpts, non-record rejection, closed static
  messages, fake determinism, collaborator validation, request-id
  echo, and the outcome closed-shape pins) inside the full suite.
- **Dependencies:** B4a-01, B4a-02. **Parallelizable:** no; composes
  the two contract modules.
- **Status:** complete in the current worktree; implementation commit pending.

## Task B4a-04 — Route B4a: the optional read-only Docker readiness probe

- **Goal:** provide the clearly separated, optional real-Docker
  boundary — a read-only readiness probe over the operator's docker
  CLI — with every decision covered offline through an injectable
  command runner.
- **Files:** ``src/vespercode/execution/v2_docker_probe.py`` (new),
  ``tests/unit/v2/test_v2_docker_probe.py`` (new),
  ``scripts/run_v2_execution_probe_demo.py`` (new, opt-in manual
  evidence).
- **Implementation:** ``SubprocessDockerProbeV2`` implements
  ``V2ReadinessPort`` with a closed literal argv —
  ``["docker", "image", "inspect", <opaque token>]`` and, only on
  failure, ``["docker", "info"]`` to distinguish a missing image from
  an unreachable daemon — executed with ``shell=False`` and a bounded
  15-second timeout; all command output is discarded (no digest is
  ever parsed; the readiness record carries only a status and a
  closed reason).  The default subprocess runner exists only for
  opt-in operator use; the unit tests inject a scripted fake runner
  and never spawn a process.  The demo script exercises the real edge
  read-only for manual evidence.
- **Intended RED:** the probe tests failed first with
  ``ModuleNotFoundError: No module named
  'vespercode.execution.v2_docker_probe'`` (captured in the RED run).
- **Verification:** 8 deterministic offline probe tests (READY on
  inspect rc 0, the exact closed argv, IMAGE_NOT_AVAILABLE vs
  DAEMON_UNAVAILABLE discrimination including runner exceptions, no
  inspect output or digest in the result, no container/registry verbs
  in any issued command, profile-record validation, bounded timeout).
  Manual opt-in real-edge evidence (read-only): the local daemon
  answered IMAGE_NOT_AVAILABLE for absent tokens while remaining
  reachable (``docker info`` rc 0), and a scoped unreachable
  ``DOCKER_HOST`` produced DAEMON_UNAVAILABLE; no READY-over-real-
  daemon run was possible on this host because every local image
  carries a registry/tag spelling the closed token charset excludes
  (the READY decision is covered offline by the fake-runner tests).
- **Dependencies:** B4a-01, B4a-02. **Parallelizable:** yes, with
  B4a-03.
- **Status:** complete in the current worktree; implementation commit pending.

## Task B4a-05 — Route B4a: separation guard, wheel contract, and documentation

- **Goal:** pin the v1/v2 execution separation statically and at
  runtime, grow the packaging guard with the four new modules, and
  record the B4a boundary truthfully in the process documents.
- **Files:** ``tests/unit/v2/test_v2_b4_v1_separation.py`` (new),
  ``tests/unit/v2/test_v2_wheel_contract.py`` (pin),
  ``tests/smoke/package/test_wheel_contents.py``
  (``REQUIRED_RUNTIME_MEMBERS``), ``SPEC.md``, ``PLAN.md``,
  ``README.md``, ``SPEC_PROCESS.md``, ``AGENT_LOG.md``.
- **Implementation:** the B4 separation guard pins that the four B4a
  modules import no v1 Docker/profile/validation (or any other v1
  authority) module, no ``hashlib``, and no third-party package, that
  the only subprocess edge is the probe module, that no B4a module
  opens sockets, and that importing the whole B4a surface loads no
  v1 module at runtime.  The wheel pin grows to 31 v2 production
  modules and the smoke contract gains the matching members
  (``execution/v2_docker_probe.py``, ``execution/v2_execution.py``,
  ``execution/v2_executor.py``, ``execution/v2_profile.py``).  SPEC
  gains FR-V2-EXEC, the Route B4a architecture/data-model notes (no
  new tables), Route B4a acceptance criteria, risks, and the mechanism
  paragraph; README documents the new modules and the updated B4b
  boundary; SPEC_PROCESS and AGENT_LOG record the RED/GREEN evidence.
- **Intended RED:** the natural packaging RED — the pin drift test
  failed with ``tree-only=['execution/v2_docker_probe.py',
  'execution/v2_execution.py', 'execution/v2_executor.py',
  'execution/v2_profile.py']`` and the separation guard failed with
  ``missing B4a module: execution/v2_profile.py`` before the sources
  existed (both captured in the RED run).
- **Verification:** full v2 suite (``python -m unittest discover -s
  tests/unit/v2``, 431 tests, 0 failures, 2 controlled symlink skips;
  was 365; +66 B4a tests), compileall over ``src/vespercode``,
  ``tests/unit/v2``, the demo scripts, and the smoke contract file,
  ``git diff --check``, the repeatable demo, and the opt-in probe
  demo.  pytest and pydantic remain unavailable on this host, so the
  pytest/pipx-gated package smoke suite and the pydantic-gated v1
  suites were NOT run and are not claimed; the Docker CLI and daemon
  (29.1.3) are available and were exercised read-only only.
- **Dependencies:** B4a-01..B4a-04. **Parallelizable:** documentation
  can be reviewed independently.
- **Status:** complete in the current worktree; implementation commit pending.
- **Boundary:** B4b — release automation, public deployment, the real
  OS credential adapter, real provider transports, and the real
  container execution adapter — is **not started** in this slice
  (the real container execution adapter later landed in B4b-01);
  Route B is not fully complete.

## Task B4a-06 — Route B4a hardening: the B1 control-plane binding gate

- **Goal:** close the parent-review security finding — the B4a request
  carried no run/candidate/revision binding and the service checked
  only the profile bindings before readiness/execution, so any
  syntactically valid ``VALIDATE_CANDIDATE`` request could be executed
  against an unrelated or stale candidate unless an unimplemented
  caller added an external guarantee.  The execution plane must be
  bound to the same B1 candidate/run/revision identity the rest of v2
  authorizes against.
- **Files:** ``src/vespercode/execution/v2_execution.py`` (the request
  record, the binding facts record + port, two new closed error
  codes), ``src/vespercode/execution/v2_executor.py`` (the service
  binding step + ``FakeV2BindingLookup``),
  ``tests/unit/v2/test_v2_execution_request.py``,
  ``tests/unit/v2/test_v2_execution_service.py``, ``SPEC.md``,
  ``README.md``, ``SPEC_PROCESS.md``, ``AGENT_LOG.md``.
- **Implementation:** ``ExecutionActionRequestV2`` gains
  ``run_id``, ``candidate_id`` (an argv-token-conformant opaque id,
  because the closed grammar projects it into the adapter-facing
  argv), and ``candidate_revision``; for ``VALIDATE_CANDIDATE`` the two
  argv argument slots must equal the request's own ``candidate_id``
  and the decimal spelling of its ``candidate_revision``, so the
  adapter-facing argv is a closed projection of the request's control
  fields — a request that names one candidate in its binding and
  another in its argv is not representable.  The new read-only
  ``V2ExecutionBindingPort``/``ExecutionBindingFactsV2`` resolves the
  cited (run, candidate) pair to the candidate's CURRENT revision (or
  ``None`` when the pair does not resolve together);
  ``V2ExecutionService`` now requires the port and enforces the fixed
  profile-binding -> control-plane-binding -> readiness -> execution
  order, re-verifying every field of the returned facts (unknown pair
  -> ``EXECUTION_BINDING_NOT_FOUND``; stale revision ->
  ``EXECUTION_BINDING_STALE``; both with zero readiness checks and
  zero executor calls).  ``FakeV2BindingLookup`` is the deterministic
  fake, and the offline suite drives the same seam over a REAL v2
  control database through a test-local read-only adapter (run/
  snapshot/candidate rows; ``advance_candidate`` crossing the
  revision proves the stale gate) — production database wiring stays
  B4b.
- **Intended RED:** the binding tests failed first with
  ``TypeError: ExecutionActionRequestV2.__init__() got an unexpected
  keyword argument 'run_id'`` and ``ImportError: cannot import name
  'ExecutionBindingFactsV2' from 'vespercode.execution.v2_execution'``
  (the seam did not exist); one GREEN-loop fix — the not-ready
  scenario tests shared one binding fake across subTests and asserted
  a single lookup, so each subTest now builds its own fake.
- **Verification:** full v2 suite (``python -m unittest discover -s
  tests/unit/v2``, 443 tests, 0 failures, 2 controlled symlink skips;
  was 431; +12 binding tests across the request, service, and
  real-database suites), compileall over ``src/vespercode``,
  ``tests/unit/v2``, the demo scripts, and the smoke contract file,
  ``git diff --check``, and the repeatable demo.  The wheel pin is
  unchanged (no new modules — the seam lives in the existing contract
  and executor modules).  pytest and pydantic remain unavailable on
  this host, so the pytest/pipx-gated package smoke suite and the
  pydantic-gated v1 suites were NOT run and are not claimed.
- **Dependencies:** B4a-01..B4a-05. **Parallelizable:** no; a hardening
  pass over the frozen execution boundary.
- **Status:** complete in the current worktree; implementation commit pending.
- **Boundary:** B4b — release automation, public deployment, the real
  OS credential adapter, real provider transports, the production
  database-backed binding implementation, and the real container
  execution adapter (later landed in B4b-01) — is **not started** in
  this slice; Route B is not fully complete.

## Task B4b-01 — Route B4b: the real container execution adapter

- **Goal:** implement the real container execution adapter behind the
  frozen B4a execution contracts (``V2ExecutionPort``,
  ``ExecutionActionRequestV2``, ``ExecutionProfileRecordV2``) as an
  optional, opt-in, bounded subprocess-Docker adapter: it accepts only
  the closed structured request + profile records (never a shell
  string or arbitrary argv), treats ``image_reference`` as an opaque
  local image token (never pulled, pushed, built, or content-verified;
  no registry credential field exists anywhere), enforces the profile
  isolation set structurally (network ``none``, the profile's non-root
  uid:gid, read-only rootfs, ``--cap-drop ALL``, no privileged mode,
  no docker socket, exactly one READ-ONLY workspace bind), bounds
  time and output, re-verifies the daemon-side configuration of the
  exact container before it starts, fails closed on every drift,
  overflow, and phase failure, and always removes the container it
  created — while the offline unit job stays deterministic (the
  command runner is injectable) and the real subprocess edge stays
  opt-in integration-only.
- **Files:** ``src/vespercode/execution/v2_docker_executor.py`` (new;
  the only production module of the task — the second and last
  subprocess edge of the v2 execution plane),
  ``tests/unit/v2/test_v2_docker_executor.py`` (new; 25 offline
  fake-runner tests),
  ``tests/integration/docker/test_v2_execution_adapter.py`` (new;
  opt-in real-daemon integration tests that skip honestly when the
  docker CLI/daemon or the token-named local image is unavailable),
  ``tests/unit/v2/test_v2_b4_v1_separation.py`` (guard update: the
  executor joins the probe as the two permitted subprocess edges and
  is pinned as a runtime import of the execution seam),
  ``tests/unit/v2/test_v2_wheel_contract.py`` (wheel pin update),
  ``tests/smoke/package/test_wheel_contents.py``
  (``REQUIRED_RUNTIME_MEMBERS`` update; pytest-gated, not run on this
  host), and the truthfulness docs (``SPEC.md``, ``README.md``,
  ``SPEC_PROCESS.md``, ``AGENT_LOG.md``).
- **Implementation:** ``SubprocessDockerExecutorV2`` takes the
  operator's workspace directory as ADAPTER configuration (absolute,
  existing, comma-free — the ``--mount`` value is comma-delimited —
  and never a request or profile field, so no caller can steer the
  mount) plus an injectable command runner
  (``runner(argv, *, timeout_seconds, max_output_bytes) ->
  ExecutorCommandOutcomeV2``; the frozen/slots outcome carries
  ``returncode=None`` exactly when the command timed out, and the
  default is the real ``subprocess.Popen(shell=False,
  stdin=DEVNULL)`` edge with two reader threads draining stdout and
  stderr under ONE shared byte budget and a wall-clock bound).
  Every run follows ONE closed command sequence: ``docker create
  --pull never`` with the frozen isolation flags (network none, the
  profile's ``--user``, ``--read-only``, ``--cap-drop ALL``, frozen
  memory/memory-swap/pids/cpu bounds — the v2 profile record
  represents only timeout and output, so the adapter freezes the
  rest — a bounded ``/tmp`` tmpfs, and exactly one read-only bind of
  the workspace at ``/workspace``; no host string, no environment, no
  entrypoint override, no ``-v`` flag exists anywhere in the argv) →
  ``docker inspect`` (daemon-side drift verification of that exact
  container BEFORE start: network mode, read-only rootfs, cap drop,
  privileged, memory/swap/cpu/pids, tmpfs, user, image, cmd, the
  single workspace bind, and rejection of any ``docker.sock`` spelling
  in any mount source/target; any drift fails closed and nothing
  runs) → one ``docker start --attach`` under the remaining budget →
  on timeout ``docker stop --time 0`` → ALWAYS ``docker rm --force``
  after any successful create (bounded, best-effort, never able to
  change the determined result).  One monotonic deadline spans
  create+inspect+start (``profile.timeout_seconds``): only a timed-out
  attached start reports ``TIMED_OUT`` — a pre-start phase that
  exhausts the budget fails closed as ``FAILED`` with empty output.
  Output overflow (runner-reported truncation or a re-verified
  over-cap combined stdout+stderr) is a fail-closed ``FAILED``,
  never a silently truncated success.  Every phase failure — runner
  exception, hostile runner return, failed create/inspect — maps to
  the closed ``FAILED`` result with no CLI/daemon error text; no
  retry exists anywhere in the adapter.  The container name is a
  per-run ``vespercode-exec-<uuid4().hex>`` transport handle that
  never enters a result.  The offline fake-runner suite pins the
  exact create argv (closed flags, ``--pull never``, the profile's
  user, the image token, the request argv, the comma-free workspace
  source), the phase sequences, the full drift matrix (one test per
  daemon field, using the exact daemon-side spellings calibrated
  against a real Docker 29.1.3 create+inspect cycle), timeout and
  overflow mapping, nonzero/exception/hostile outcomes, cleanup on
  every exit path (including hostile ones), and that the B4a
  binding/readiness gates issue NO runner call at all when they fail
  upstream.
- **Intended RED:** the new test module failed first with
  ``ModuleNotFoundError: No module named
  'vespercode.execution.v2_docker_executor'``; the separation guard
  failed with ``missing Route B execution-plane module:
  execution/v2_docker_executor.py``; the wheel pin failed with
  ``declared v2 module does not exist: execution/
  v2_docker_executor.py`` — 444 tests, 3 failures, 7 errors before
  any implementation existed.
- **Verification:** full v2 suite (``python -m unittest discover -s
  tests/unit/v2`` — 468 tests, 0 failures, 2 controlled symlink
  skips, exit 0; was 443; +25 adapter tests), the opt-in integration
  suite against the real local Docker 29.1.3 daemon (both tests pass;
  the explicit real-run evidence: status=FAILED, exit_code=1,
  output_len=268 — the daemon's "executable file not found" for the
  operator-tagged demo image, which has no ``vespercode-validate``
  entrypoint; no leftover containers via ``docker ps -a``; operator
  setup ``docker tag vespercode-demo:local
  vespercode-validation-image``), compileall, ``git diff --check``,
  and a manual 88-char line scan (ruff is unavailable on this host).
  pytest and pydantic remain unavailable on this host, so the
  pytest/pipx-gated package smoke suite and the pydantic-gated v1
  suites were NOT run and are not claimed; no SUCCEEDED run over the
  real daemon is claimed (no validation-entrypoint image exists yet).
- **Dependencies:** B4a-01..B4a-06. **Parallelizable:** no; the only
  new execution-plane subprocess edge is this adapter.
- **Status:** complete in the current worktree; implementation commit pending.
- **Boundary:** B4b-02 — the production database-backed binding
  implementation and any database wiring of the execution plane,
  release automation, public deployment (any non-loopback binding,
  TLS, or remote operator surface), the real OS credential adapter,
  and real provider transports — is **NOT STARTED**; Route B is not
  fully complete.

## Task B4b-02A — Route B4b: the production database-backed
## execution binding

- **Goal:** replace B4a's fake/read-only binding seam with the
  production-shaped read-only binding adapter over the real v2
  control database, and extend the binding gate to the B1 validation
  run — without touching the Docker, release, or deployment
  workflows.  ``DatabaseBackedExecutionBinding``
  (``execution/v2_database_binding.py``) implements
  ``V2ExecutionBindingPort`` over ``V2Database``: it resolves the
  cited (run, candidate) pair to the candidate's CURRENT revision
  (rejecting unknown/foreign/corrupted run and candidate rows) and
  requires the request to cite a validation run — an uncited request
  answers the closed ``VALIDATION_REQUIRED`` rejection — whose row
  revalidates as a B1 ``ValidationRunRecordV2`` and binds the same
  run, the same candidate, at the CURRENT candidate revision, under
  the request's own reference profile id/revision, whose
  ``reference_profiles`` row must still exist and revalidate, and
  whose status must be terminal ``PASSED`` (``PENDING``/``FAILED``
  answer ``VALIDATION_NOT_PASSED``; missing/foreign/stale/
  profile-mismatched/corrupted validations answer
  ``VALIDATION_NOT_FOUND``).  The lookup is strictly read-only (no
  mutation, no approval consumption, no validation result creation,
  no candidate advancement), holds no cached state, and never
  fabricates facts — corrupted rows are closed rejections, never
  fake data.  The port contract itself becomes a closed typed
  outcome: ``lookup_execution_binding(run_id, candidate_id,
  validation_run_id, reference_profile_id,
  reference_profile_revision) -> ExecutionBindingOutcomeV2`` with
  ``EXECUTION_BINDING_OUTCOME_KINDS_V2``
  (``RESOLVED``/``BINDING_NOT_FOUND``/``VALIDATION_REQUIRED``/
  ``VALIDATION_NOT_FOUND``/``VALIDATION_NOT_PASSED``), the returned
  ``ExecutionBindingFactsV2`` gains the resolved
  ``ValidationBindingFactsV2`` (the validation's own five keys plus
  status), and the service re-verifies every field against the
  request, so a hostile or drifted port cannot authorize a foreign,
  stale, or unvalidated binding.  The request gains an OPTIONAL
  ``validation_run_id`` (validated as an opaque identifier when
  cited; ``None`` stays the B4a isolated-fake spelling), preserving
  B4a request compatibility — safe because the production adapter
  fails closed on an uncited request with the new closed
  ``VALIDATION_BINDING_REQUIRED`` outcome code while the fake keeps
  resolving uncited requests for the isolated B4a service tests.
  Three new closed outcome codes and static messages
  (``VALIDATION_BINDING_REQUIRED``,
  ``VALIDATION_BINDING_NOT_FOUND``,
  ``VALIDATION_BINDING_NOT_PASSED``) join the closed vocabulary.
  No shell, network, Docker, or subprocess behavior is added; real
  Docker remains behind the B4b-01 executor and the B4a gates.
- **Files:** ``src/vespercode/execution/v2_database_binding.py``
  (new; the only new production module),
  ``src/vespercode/execution/v2_execution.py`` (contract extension:
  the request field, the binding outcome kinds, the validation
  facts record, the port signature, the three new outcome codes and
  messages), ``src/vespercode/execution/v2_executor.py`` (the
  service's binding/validation gate with full facts re-verification
  and the updated deterministic fake),
  ``tests/unit/v2/test_v2_database_binding.py`` (new; 21 tests over a
  real v2 control database), ``tests/unit/v2/
  test_v2_execution_service.py`` (port-contract update, the new
  validation-gate service tests, and removal of the superseded
  test-local ``_DatabaseBindingLookup`` adapter), ``tests/unit/v2/
  test_v2_execution_request.py`` (the request field-set pin plus the
  citation contract), ``tests/unit/v2/test_v2_b4_v1_separation.py``
  (the binding module joins the guarded execution-plane module
  list), ``tests/unit/v2/test_v2_wheel_contract.py`` and
  ``tests/smoke/package/test_wheel_contents.py`` (the wheel pin /
  ``REQUIRED_RUNTIME_MEMBERS`` update), and the truthfulness docs
  (``SPEC.md``, ``README.md``, ``SPEC_PROCESS.md``,
  ``AGENT_LOG.md``).
- **Implementation:** the adapter composes ONLY existing
  ``V2Database`` read methods (``get_run``, ``get_candidate``,
  ``get_validation_run``, ``get_reference_profile``) — no new tables,
  no schema change, no migration, no write path.  Fail-closed order:
  citation required → run exists → candidate exists and revalidates
  as a B1 ``CandidateControlIdentityV2`` and belongs to the cited
  run → the cited validation row revalidates and binds (same run,
  same candidate, CURRENT revision, the request's reference profile
  id/revision) → the validation's profile row still exists and
  revalidates → status is terminal ``PASSED`` → ``RESOLVED`` facts
  (current revision + the validation's own five keys and status).
  Record-revalidation failures (``ValueError``/``TypeError`` from
  the B1 record constructors the storage layer projects rows
  through) are caught and answered as the corresponding closed
  NOT_FOUND kind — corrupted rows are never executable and never
  answered with fake facts; infrastructure failures beyond record
  shape (``sqlite3`` errors) propagate loudly and still execute
  nothing.  The service consults the binding port with all five
  request keys, maps each closed kind to its closed outcome code
  (all BEFORE readiness, with zero readiness/executor calls), and
  re-verifies every field of the returned facts (identity →
  ``EXECUTION_BINDING_NOT_FOUND``/``STALE``; validation identity or
  profile binding drift → ``VALIDATION_BINDING_NOT_FOUND``; a
  non-PASSED echoed status → ``VALIDATION_BINDING_NOT_PASSED``; a
  port that invents validation facts for an uncited request cannot
  ``FakeV2BindingLookup`` keeps
  the isolated offline seam and gains the
  ``validation_required``/``validation_unresolved``/
  ``validation_status`` scriptables so every service code path is
  offline-testable.  THIRD-ROUND REVIEW FIX (the main-thread
  review rejected the first cut's semantic gap): the citation
  requirement is now the production service's OWN STRUCTURAL
  gate — ``V2ExecutionService`` rejects an uncited request with
  ``VALIDATION_BINDING_REQUIRED`` BEFORE the binding port is
  consulted, so the requirement no longer depends on the caller
  injecting the production binding port (a production service
  constructed over a permissive fake still cannot execute an
  uncited request); ``V2ExecutionTestService`` is the explicitly
  TEST-ONLY subclass — non-production by contract, named for
  grep, documented in the module and SPEC — that relaxes exactly
  this one gate so the offline fakes can exercise the service's
  ordering and sanitization; the production DB adapter's own
  uncited rejection stays as defense in depth and is pinned by a
  direct port test.
- **Intended RED:** the new suite failed first with
  ``ModuleNotFoundError: No module named
  'vespercode.execution.v2_database_binding'``; the service suite
  failed to load with ``ImportError: cannot import name
  'ExecutionBindingOutcomeV2'``/``'ValidationBindingFactsV2'``; the
  request suite failed the closed field-set pin
  (``_REQUEST_FIELDS`` without ``validation_run_id``) and the
  citation contract with ``TypeError: __init__() got an unexpected
  keyword argument 'validation_run_id'``; the B4 separation guard
  failed with ``missing Route B execution-plane module:
  execution/v2_database_binding.py``; the wheel pin failed with
  ``declared v2 module does not exist`` and a pin/tree drift — 447
  tests, 4 failures, 17 errors before any implementation existed.
- **Verification:** full v2 suite (``python -m unittest discover -s
  tests/unit/v2`` — 497 tests, 0 failures, 2 controlled symlink
  skips, exit 0; was 468; +21 production-binding tests over a real
  v2 control database, +5 service/request contract tests, +3
  third-round structural-citation tests (the production uncited
  gate, the test-only subclass pin, the adapter's own uncited
  port rejection), −4 superseded test-local adapter tests),
  including the fresh-process
  reopen test (a new interpreter + connection + adapter resolves the
  same committed binding) and the read-only proof (every v2 table
  byte-identical across accepted and rejected lookups),
  ``python -m compileall`` (clean), ``git diff --check`` (clean),
  and a manual 88-char line scan (ruff is unavailable on this host;
  the only >88 lines in the touched files are pre-existing lines
  preserved verbatim).  pytest and pydantic remain unavailable on
  this host, so the pytest/pipx-gated package smoke suite and the
  pydantic-gated v1 suites were NOT run and are not claimed.  The
  CI/release workflow files and the public deployment surface are
  untouched by this task.
- **Dependencies:** B4a-01..B4a-06 + B4b-01. **Parallelizable:** no;
  the only new execution-plane binding module is this adapter.
- **Status:** complete in the current worktree; implementation commit pending.
- **Boundary:** B4b-02B — release/wheel automation (any tag-triggered
  or artifact-publishing workflow beyond the existing unchanged
  CI/release files) — and B4b-02C — public deployment (any
  non-loopback binding, TLS, or remote operator surface) — are both
  **NOT STARTED**; Route B is not fully complete, and the CI/release
  workflows remain unchanged by this task.

## Task B4b-02B — Route B4b: the independent v2 alpha wheel/release path

- **Goal:** give the v2 alpha (`0.2.0a0`) a coherent wheel/release
  path that never mixes with the frozen v1 release: pin the package
  identity (pyproject version/name/requires-python coherent with the
  package `__init__` pins and every package smoke suite), pin the
  two-entry console boundary (the legacy `vespercode` entry stays
  the frozen v1 CLI and is never silently presented as v2;
  `vespercode-v2` targets `vespercode.cli_v2:main` and presents
  itself as `vespercode-v2`), extend the offline wheel contract
  (required members disjoint from the prohibited set, no
  tests/evidence/credentials/checkout leakage, the version-bound
  dist-info entry-point member, both entry points pinned in the real
  wheel smoke matrix and the installed-wheel smoke), and add the
  release path itself: a NEW, independent, manually dispatched
  `.github/workflows/release-v2-alpha.yml` that verifies the alpha
  identity first, runs the documented offline v2 unit suite, builds
  exactly one `vespercode-0.2.0a0-py3-none-any.whl` with the locked
  build toolchain, smoke-installs it with `--no-deps` through
  `vespercode-v2 --help`, and uploads the wheel plus its adjacent
  `<wheel>.whl.sha256` evidence (the package smoke driver's
  evidence-file convention) as one `v2-alpha-wheel` CI artifact.
  The path is read-only (`contents: read`), secretless, uses only
  checkout/setup-python/artifact-upload actions, publishes nothing
  (no GitHub Release object, no registry image, no public
  deployment), and carries no v1 identity token (the frozen v1
  version, source commit, or image digest); the frozen v1 release
  workflow (`.github/workflows/release.yml`) stays byte-unchanged
  and carries no v2 identity token.
- **Files:** `.github/workflows/release-v2-alpha.yml` (new; the only
  new CI/release file), `tests/unit/v2/process/` (new stdlib test
  package: `__init__.py` + `test_v2_alpha_release_path.py`),
  `tests/unit/v2/test_v2_wheel_contract.py` (the offline
  package-identity/entry-point/member-hygiene extension),
  `tests/smoke/package/test_wheel_contents.py` (the real-wheel
  matrix now pins BOTH console entry points),
  `tests/smoke/package/test_installed_cli.py` (the installed-wheel
  smoke now also proves `vespercode-v2 --help` from the isolated
  pipx home), and the truthfulness docs (`SPEC.md`, `README.md`,
  `SPEC_PROCESS.md`, `AGENT_LOG.md`, this file).
- **Implementation:** the release strategy is deliberately the
  artifact-workflow option: manual `workflow_dispatch` only — no
  push or tag trigger, because the frozen v1 release workflow
  triggers on every pushed `v*` tag and fails closed on its own
  v1 admission pins (tag name, source commit, pyproject `0.1.0`),
  so a v2 alpha tag would start it to no effect and the v2 path
  instead binds to the checked-out source commit.  The preflight job
  verifies `version == "0.2.0a0"`, both console script targets, and
  the `V2_VERSION` pin before anything else runs; the unit-test job
  runs the documented offline command; the wheel job mirrors the
  proven v1 release steps on the locked toolchain
  (`requirements/dev.lock` installs cleanly on Windows — it pins
  `pywin32` — so the wheel job is `windows-latest` like the v1
  release's) with the v2 alpha wheel name check, the lowercase
  SHA-256 evidence file, a fresh-venv `--no-deps` install, and the
  `vespercode-v2.exe --help` smoke (the v2 CLI is standard-library
  only, so the no-deps install is the honest proof that the v2
  surface carries no third-party requirement).
- **Intended RED:** the new suite failed first with 8 errors
  (`FileNotFoundError: ...\.github\workflows\release-v2-alpha.yml`
  for every workflow-content test) and 2 failures — the
  workflow-exists pin and the wheel-smoke-matrix entry-point pin
  (`assert "vespercode-v2 = vespercode.cli_v2:main" in
  entry_points` missing from the smoke file); the remaining new
  tests (version/metadata coherence, frozen v1 pins, member hygiene,
  CI pins, the parser prog pin) passed immediately as pins of
  already-coherent state — 24 tests, 2 failures, 8 errors before any
  implementation existed.
- **Verification:** full v2 suite (`python -m unittest discover -s
  tests/unit/v2` — 517 tests, 0 failures, 2 controlled symlink
  skips, exit 0; was 497; +20: 13 release-path process tests, +7
  wheel-contract identity/hygiene tests), the new suites re-verified
  individually (24 tests, OK), `python -m compileall` (clean),
  `git diff --check` (clean), and a manual 88-char line scan (ruff
  is unavailable on this host).  `build`, pytest, and pipx are NOT
  installed on this host and were NOT installed ad hoc, so the real
  wheel build, the pytest/pipx-gated package smoke suite, and an
  actual `release-v2-alpha.yml` run were NOT executed and are NOT
  claimed — the real-build path is defined by the committed workflow
  and pinned by the offline static contract.  The frozen v1 release
  workflow is byte-unchanged (`git diff .github/workflows/release.yml`
  is empty; the v1 tag/evidence files are untouched).
- **Dependencies:** B4b-01 + B4b-02A. **Parallelizable:** yes; the
  release path touches no production module and no v1 file.
- **Status:** complete in the current worktree; implementation commit pending.
- **Boundary:** B4b-02C — public deployment (any non-loopback
  binding, TLS, or remote operator surface), the real OS credential
  adapter, and real provider transports — is **NOT STARTED**; the
  v2 alpha artifact is a transient CI artifact, not a published
  distribution; Route B is not fully complete.

## Task B4b-02C1 — Route B4b: the production OS credential adapter and
## the real provider transport boundary

- **Goal:** give the B2 credential and provider ports their
  production real-plane implementations — with strict security and
  injectable, offline tests — without touching the v1 release
  workflow or starting any public deployment.  On the credential
  side, `OSV2CredentialProvider` (`credentials/v2_os_store.py`)
  implements `V2CredentialProviderPort` over an injectable OS backend
  port (`V2OSCredentialBackendPort`) whose real implementation is the
  Windows Credential Manager backend: the platform libraries
  (`win32cred`/`pywintypes`) are imported lazily inside functions
  only (the module and the wheel stay standard-library only, and a
  host without them fails closed with the closed
  `CREDENTIAL_BACKEND_UNAVAILABLE` error); every operation first
  proves the backend (identity in the closed
  `WINDOWS_CREDENTIAL_MANAGER` set plus a real write/read/delete
  probe cycle of the backend's own `vespercode/v2/probe` target);
  `set` extracts the raw value only through the new storage-reveal
  capability minted by the port module for exactly this adapter,
  writes under `vespercode/v2/credential/<provider>` (a namespace
  disjoint from the probe target and from all v1 `vespercode/v1/`
  targets by construction), re-verifies the backend after the write,
  and retains nothing; `get_for_call` re-probes and reads fresh with
  no cache; `status` reads metadata only (the stored value is never
  decoded on the status path) and stays provider/configured/
  update-time only; `clear` deletes idempotently; and every
  unavailable, unsafe, malformed, or identity-mismatched condition is
  the closed static `V2OSCredentialStoreError` — never a fallback
  backend, never the secret, a length, or a derivative.  On the
  transport side, `V2ProviderTransportAdapter`
  (`providers/v2_transport.py`) implements `V2ProviderTransport` for
  the declared provider endpoint/profile only: construction is closed
  (exactly one v2 endpoint record, the reference profile record it
  must bind, and an optional injectable HTTP edge — never a URL,
  `base_url`, header set, argv, or shell input), the sole trusted
  destination derives from the closed built-in provider address map
  (`OPENAI` → `https://api.openai.com:443/v1/chat/completions`; an
  undeclared provider cannot construct the adapter), the request body
  is the bounded deterministic control-plane projection of the call
  request (control IDs and revisions only — an oversized projection
  fails before the edge is touched), exactly one HTTP edge call
  happens per `call` with the closed 60-second read timeout, no
  redirect is ever followed and no request is ever re-sent, and every
  edge exception, non-success status, non-conforming result, or
  over-bound body maps to the closed `FAILED` response with the
  response body and the credential never appearing in any response,
  outcome, or retained state.  The provider call service keeps its
  frozen order and semantics: a credential-port infrastructure
  failure happens strictly BEFORE the atomic consume (nothing burned,
  no transport touched, the closed error propagates loudly — never
  silently mapped to a business outcome) and a transport failure
  happens strictly AFTER it (the authorization stays consumed — no
  refund).  The v1 credential service is never the v2 authority and
  no v1 module is imported; the shipped shell/CLI default stays the
  in-memory fake (the new adapters are injectable production
  implementations, not wired callers); no real network call and no
  real OS store access exists in the offline unit job.
- **Files:** `src/vespercode/credentials/v2_os_store.py` (new; the OS
  credential adapter, the backend port, the real Windows Credential
  Manager backend with lazy imports, the unavailable placeholder, the
  closed error type and vocabulary, and the platform default
  resolver), `src/vespercode/providers/v2_transport.py` (new; the real
  provider transport adapter, the closed address map and resolver, the
  injectable HTTP edge protocol, the closed result record, the bounded
  control-projection serializer, and the real lazy-httpx edge),
  `src/vespercode/credentials/v2_port.py` (the storage-reveal
  capability: `_StorageCapability`, the module-private friend seam,
  and `V2CredentialSecret.reveal_for_storage` — the existing
  provider-call `reveal` is unchanged and the two capabilities are
  never interchangeable), `src/vespercode/providers/v2_call.py`
  (docstring only: the credential-port failure order note),
  `tests/unit/v2/test_v2_os_credential_store.py` (new; 23 tests),
  `tests/unit/v2/test_v2_provider_transport.py` (new; 27 tests),
  `tests/unit/v2/test_v2_provider_boundary.py` (new; 13 composed
  end-to-end tests over a real v2 control database),
  `tests/unit/v2/test_v2_credentials_port.py` (+4 storage-reveal
  capability tests), `tests/unit/v2/test_v2_b2_v1_separation.py` (the
  two new modules join the guarded B2 plane),
  `tests/unit/v2/test_v2_wheel_contract.py` and
  `tests/smoke/package/test_wheel_contents.py` (the wheel pin /
  `REQUIRED_RUNTIME_MEMBERS` update),
  `tests/integration/windows/test_v2_os_credential_store.py` (new;
  the opt-in real-WinCred integration suite with honest skips), and
  the truthfulness docs (`SPEC.md` §5/B2 criteria/§7/§8, `README.md`,
  `SPEC_PROCESS.md`, `AGENT_LOG.md`, this file).
- **Implementation:** the OS adapter keeps no secret state (slots
  hold only the backend), probes before every operation, re-probes
  after `set`'s write, and converts the backend's last-written epoch
  milliseconds into the status projection's ISO timestamp; the
  Windows backend mirrors the proven v1 Win32 mechanics (generic
  credentials, `CRED_PERSIST_LOCAL_MACHINE`, UTF-16-LE blob decode,
  `ERROR_NOT_FOUND` as absence, mandatory row-key and username
  identity checks) but deliberately drops the v1 keyring identity
  check — the v2 backend talks to the Win32 Credential API directly,
  proving identity by platform + import + capability cycle, so the
  standard-library-only v2 line gains no keyring dependency (a
  documented deviation).  The transport adapter rechecks its own
  endpoint/provider/profile binding after the service's checks
  (defense in depth: a drifted request can pass the service gate and
  still never reach the edge), enforces the closed request-body
  (1600), response-body (1 MiB), and timeout (60 s) bounds, and
  reduces every failure to the indistinguishable closed `FAILED`
  response (redaction by construction).  The real httpx edge streams
  with `follow_redirects=False` and aborts at the body bound inside
  the call (the adapter still re-checks the returned body).  The
  offline unit job exercises both adapters through deterministic
  fakes only; the real WinCred backend is proven by the opt-in
  integration suite (Windows + pywin32 + the explicit
  `VESPERCODE_V2_WINCRED_INTEGRATION=1` opt-in, honest skips
  otherwise, unknown pre-existing entries refused, entries deleted
  in `finally`, zero `vespercode/v2/` residue proven); the real httpx
  edge is never exercised by any recorded run.  No shell, Docker,
  public listener, arbitrary URL, or environment/file credential
  import exists on either path.
- **Intended RED:** before any implementation existed, the new suites
  failed first with `ModuleNotFoundError: No module named
  'vespercode.credentials.v2_os_store'` (the OS store and boundary
  suites) and `No module named 'vespercode.providers.v2_transport'`
  (the transport suite), the port suite failed to load with
  `ImportError: cannot import name '_storage_reveal_capability'`,
  the B2 separation guard failed with the missing-module
  `FileNotFoundError`/existence failure, and the wheel contract
  failed the source-tree existence and pin-drift checks — 507 tests,
  3 failures, 6 errors (the 4 failing modules' own tests not even
  loading); two RED-side test-double bugs were fixed before any
  implementation existed (the fake backend must fail closed on
  non-string stored values like the real backend, and `None` is the
  constructor's default-backend sentinel, not a non-conforming
  backend).
- **Verification:** full v2 suite (`python -m unittest discover -s
  tests/unit/v2` — 584 tests, 0 failures, 2 controlled symlink
  skips, exit 0; was 517; +67: 23 OS-store tests, 27
  transport-adapter tests, 13 composed boundary tests, 4
  storage-reveal capability tests), the new suites re-verified
  individually (23/27/13/18 tests, OK), `python -m compileall`
  (clean), `git diff --check` (clean), and a manual 88-char line scan
  (ruff is unavailable on this host; the only >88 lines in the
  touched files are pre-existing lines preserved verbatim).  pytest,
  pydantic, pywin32, and httpx are NOT installed on this host and
  were NOT installed ad hoc, so the pytest-gated suites were NOT run
  and are not claimed; the real WinCred integration suite was loaded
  and skips honestly on this host (4 skips with the exact reason —
  pywin32 unavailable, no opt-in given), which is the recorded
  honest state; no real OS store access, no real network call, and no
  real provider contact is claimed by any recorded run.  The CI and
  release workflow files are untouched by this task; the frozen v1
  release workflow is byte-unchanged.
- **Dependencies:** B4b-01 + B4b-02A + B4b-02B (the package identity
  whose wheel contract the new modules join). **Parallelizable:** no;
  the two new production modules are the only credential/transport
  edges of the v2 provider plane.
- **Status:** complete in the current worktree; implementation commit pending.
- **Boundary:** B4b-02C2 — public deployment (any non-loopback
  binding, TLS, or remote operator surface) — is **NOT STARTED**;
  neither new adapter is wired into the harness loop, CLI, or WebUI
  (the shipped default port implementation stays the in-memory
  fake); the real httpx edge has never been executed against any
  real provider; Route B is not fully complete.

## B4b-02C2 public deployment decision (2026-10-11)

Public deployment of the real v2 Harness is intentionally not implemented in this alpha. B3 is a single-user loopback service bound to `127.0.0.1`; its session state, workspace, OS credentials, and Docker/operator boundary are local-machine assumptions. Exposing it publicly would require a separate multi-user security design, including authentication, tenant/workspace isolation, cloud credential storage, TLS/reverse-proxy policy, quotas, audit retention, and remote sandboxing.

The existing v2 loopback WebUI remains the supported deployment boundary. No public v2 URL, remote operator surface, or public deployment claim is made. B4b-02B alpha wheel/release workflow remains separate and does not publish a public service.

**Status:** `INTENTIONALLY_NOT_IMPLEMENTED_IN_V2_ALPHA`.
