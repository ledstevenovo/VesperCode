# VesperCode v1 Implementation Plan V2

## 1. Document Status and Admission Gates

**Document status:** Draft — design rewrite complete only after mechanical verification; admission reviews and cold-start remain pending.

This PLAN is an execution navigation map for the exact current SPEC. It does not change product scope, behavior, security boundaries, non-goals, or acceptance criteria. The 141 legacy child IDs remain immutable atomic TDD and migration-trace identifiers; only the 55 `TNN.X` session tasks are executable review/commit units, and only the 46 `WP...` work packages are branch/worktree/PR units.

Implementation is forbidden until all gates below pass in order for the exact unchanged input identities:

1. `SPEC_M0`: independent readiness review of exact SPEC bytes and product/design completeness.
2. `PLAN_AUDIT_V2_A` and `PLAN_AUDIT_V2_B`: independently implemented mechanical audits agree on all normative metrics, identities, issues, and semantic digest.
3. `PLAN_SPEC_COMPLIANCE`: independent design-document review confirms no requirement, behavior, security invariant, non-goal, or acceptance condition was weakened.
4. `PLAN_EXECUTABILITY`: independent execution-document review confirms each session task is self-contained and feasible in one fresh-agent session.
5. Human identity approval of exact SPEC SHA-256, PLAN complete-file SHA-256, `PlanSemanticDigestV1`, course inputs, `AGENTS.md`, and Git HEAD.
6. Heterogeneous no-history cold-start retrieval and representative execution trial.
7. `APPROVED_DOCUMENT_BASELINE_V2`: commit the exact approved bytes and prove the implementation base is its clean direct descendant.

All prior M0, PLAN audit, review, approval, cold-start, and baseline results are invalid after this non-tracking SPEC/PLAN rewrite. No embedded statement in this document is admission evidence.

## 2. Global Execution Contract

### 2.1 Units and authority

- A legacy step such as `25.C` is one atomic RED→GREEN contract and historical trace ID. It never owns a branch, PR, review, commit, or independent execution status.
- A session task such as `T25.2` is the smallest executable unit. Exactly one fresh subagent implements all listed legacy steps in order, then receives one task-level SPEC review and one later task-level quality review.
- A work package such as `WP25-CALL` is the integration unit. Exactly one branch, isolated worktree, draft PR, finishing pass, and merge belong to it.
- Task-card `Depends`, `Files`, `SPEC contracts`, and `Legacy steps` are the sole dependency, ownership, design-reference, and atomic-mapping facts. All waves and summaries are derived.

### 2.2 Work-package workflow

1. Start only after every predecessor package has merged and every non-task gate named by the root task has passed.
2. Create the package branch/worktree from the common merged baseline and open one draft PR.
3. Give each session task to a fresh subagent with exact SPEC, PLAN, package diff, and predecessor evidence.
4. Execute each listed legacy step sequentially as an independent RED → minimum GREEN microcycle. A collection, import, environment, unrelated, or already-failing test is not valid RED.
5. After all microcycles, run task Target, Domain, applicable real-environment checks, and the declared global profile.
6. Run task-level SPEC review first. Close every Critical/Important finding, rerun affected checks, and obtain same-stage re-review PASS.
7. Only then run task-level quality review. Close every Critical/Important finding, rerun checks, and obtain same-stage re-review PASS.
8. Create one implementation commit containing only task-owned implementation/tests.
9. Create one narrow evidence commit updating only the task `Status`, its one-line `Completion evidence`, and chronological `AGENT_LOG.md` evidence.
10. A later task in the same package uses a new fresh subagent and the same branch/PR.
11. After the final task, run branch finishing once and merge the package PR in wave/dependency order.

Each task evidence records responsible subagent, human edits, exact commands/results, RED reason, both review/re-review results, implementation SHA, evidence SHA, PR URL, and applicable external URLs/digests. Actual command output and findings belong in `AGENT_LOG.md`, PR, or external evidence—not in PLAN.

### 2.3 Ownership and concurrency

- Every repository path in a task card has that task as primary owner for the package. Generated artifacts inherit the owner of their generator/template.
- `PLAN.md` tracking fields and append-only `AGENT_LOG.md` are evidence modifiers governed by §2.2, not implementation-owned files.
- Shared repository-level configuration may be modified only by its named task; later tasks consume it read-only unless their own Files field explicitly says Modify.
- Same-wave packages run in parallel only when package predecessors are merged and expanded file ownership is disjoint. Merge and append-only evidence updates serialize in displayed package order.
- Any undeclared file need, cross-package ownership collision, or dependency discovered during execution stops the task and requires a semantic PLAN revision and renewed admission.

The following is the complete shared-modifier exception table. `Read` never grants write ownership; every unlisted writable path must have exactly one task:

| Shared path | Primary owner | Authorized later modifier(s) | Constraint |
|---|---|---|---|
| `reference/manifest/reference-profile-v1.json` | T02.2 | T06.1 | T06.1 may promote only the frozen GO identity into the built-in profile; it may not change Task 2 evidence. |
| `pyproject.toml` | T04.1 | T33.1 | T33.1 may add only reviewed wheel/package metadata and resource inclusion. |
| `src/vespercode/cli.py` | T28.1 | T33.1, T38.2 | T33.1 verifies installed entry points; T38.2 adds only the typed recovery composition binding. |
| `tests/unit/loop/test_main_loop_failures.py` | T25.2 | T25.3 | T25.3 may add outer-loop stop/wait integration cases without rewriting call/dispatch assertions. |
| `tests/unit/process/test_delivery_evidence.py` | T37.1 | T37.2 | T37.2 adds final fail-closed delivery-gate cases after process evidence is frozen. |

## 3. Verification and Environment Profiles

| Profile | Required once per session task | Additional scope |
|---|---|---|
| `GATE_OFFLINE_V1` | task Target/Domain through the frozen gate runner; gate Ruff format/check and Mypy choices; changed-file redacted credential scan; `git diff --check` | Tasks 1–3 use only the hash-locked feasibility environment and declared real probe. |
| `FORMAL_OFFLINE_V1` | task Target/Domain; `python -m pytest -q`; `python -m ruff format --check .`; `python -m ruff check .`; `python -m mypy src tests`; `python scripts/scan_credentials.py --changed --redact --fail-on-match`; `git diff --check` | No network, credential, external publication, or undeclared environment use. |
| `WINDOWS_REAL_V1` | exact task-specific Windows/NTFS/WinCred/pipx/browser command and redacted evidence | Required when the task Verification names Windows, Win32, NTFS, WinCred, installed package, or local browser evidence. |
| `DOCKER_REAL_V1` | exact task-specific Docker/OCI/loopback-registry command, digest, cleanup, and no-credential evidence | Required when Verification names Docker, OCI, registry, image, or container evidence. |
| `CI_RELEASE_LIVE_V1` | verifier-first local contract plus exact remote run/URL/digest bound to source commit | Required only for CI, release, GHCR, Render, or public live evidence tasks. |

Profiles define repeated workflow commands once. Task cards retain only task-specific Target, Domain, schema, smoke, browser, or real-environment commands. A profile or real check may not be skipped when required; unavailable infrastructure leaves the task incomplete.

## 4. Work Package Registry

| Work package | Session tasks | Legacy steps | Branch / worktree | Closure |
|---|---|---|---|---|
| WP01 | T01.1, T01.2 | 1.A, 1.B, 1.C, 1.D, 1.E | `codex/wp01` / `.worktrees/wp01` | 最后一个 session task 通过后 finishing 并合并。 |
| WP02 | T02.1, T02.2 | 2.A, 2.B, 2.C, 2.D, 2.E, 2.F, 2.G | `codex/wp02` / `.worktrees/wp02` | 最后一个 session task 通过后 finishing 并合并。 |
| WP03 | T03.1, T03.2 | 3.A, 3.B, 3.C, 3.D, 3.E, 3.F, 3.G | `codex/wp03` / `.worktrees/wp03` | 最后一个 session task 通过后 finishing 并合并。 |
| WP04 | T04.1, T04.2 | 4.A, 4.F, 4.B, 4.C, 4.D, 4.E | `codex/wp04` / `.worktrees/wp04` | 最后一个 session task 通过后 finishing 并合并。 |
| WP05 | T05.1 | 5.A, 5.B, 5.C, 5.E, 5.D | `codex/wp05` / `.worktrees/wp05` | 最后一个 session task 通过后 finishing 并合并。 |
| WP06 | T06.1 | 6.A, 6.B, 6.C, 6.D, 6.E | `codex/wp06` / `.worktrees/wp06` | 最后一个 session task 通过后 finishing 并合并。 |
| WP07-CORE | T07.1 | 7.A, 7.B, 7.C | `codex/wp07-core` / `.worktrees/wp07-core` | 最后一个 session task 通过后 finishing 并合并。 |
| WP07-REGISTRY | T07.2 | 7.D | `codex/wp07-registry` / `.worktrees/wp07-registry` | 最后一个 session task 通过后 finishing 并合并。 |
| WP08 | T08.1 | 8.A, 8.B | `codex/wp08` / `.worktrees/wp08` | 最后一个 session task 通过后 finishing 并合并。 |
| WP09 | T09.1 | 9.A, 9.B, 9.C, 9.D | `codex/wp09` / `.worktrees/wp09` | 最后一个 session task 通过后 finishing 并合并。 |
| WP10-SNAPSHOT | T10.2 | 10.A, 10.C | `codex/wp10-snapshot` / `.worktrees/wp10-snapshot` | 最后一个 session task 通过后 finishing 并合并。 |
| WP10-TEXT | T10.1 | 10.B | `codex/wp10-text` / `.worktrees/wp10-text` | 最后一个 session task 通过后 finishing 并合并。 |
| WP11 | T11.1 | 11.A, 11.B | `codex/wp11` / `.worktrees/wp11` | 最后一个 session task 通过后 finishing 并合并。 |
| WP12 | T12.1 | 12.A, 12.B, 12.C, 12.D | `codex/wp12` / `.worktrees/wp12` | 最后一个 session task 通过后 finishing 并合并。 |
| WP13 | T13.1 | 13 | `codex/wp13` / `.worktrees/wp13` | 最后一个 session task 通过后 finishing 并合并。 |
| WP14 | T14.1 | 14.A, 14.B, 14.C | `codex/wp14` / `.worktrees/wp14` | 最后一个 session task 通过后 finishing 并合并。 |
| WP15 | T15.1, T15.2 | 15.A, 15.B, 15.C, 15.D, 15.F, 15.E | `codex/wp15` / `.worktrees/wp15` | 最后一个 session task 通过后 finishing 并合并。 |
| WP16 | T16.1 | 16.A, 16.B | `codex/wp16` / `.worktrees/wp16` | 最后一个 session task 通过后 finishing 并合并。 |
| WP17 | T17.1 | 17.A, 17.B, 17.C | `codex/wp17` / `.worktrees/wp17` | 最后一个 session task 通过后 finishing 并合并。 |
| WP18-CONTRACT | T18.1 | 18.A | `codex/wp18-contract` / `.worktrees/wp18-contract` | 最后一个 session task 通过后 finishing 并合并。 |
| WP18-EXECUTION | T18.2 | 18.B, 18.C, 18.D | `codex/wp18-execution` / `.worktrees/wp18-execution` | 最后一个 session task 通过后 finishing 并合并。 |
| WP19 | T19.1 | 19.A, 19.B, 19.C | `codex/wp19` / `.worktrees/wp19` | 最后一个 session task 通过后 finishing 并合并。 |
| WP20-BASELINE | T20.2 | 20.B | `codex/wp20-baseline` / `.worktrees/wp20-baseline` | 最后一个 session task 通过后 finishing 并合并。 |
| WP20-DETECTION | T20.1 | 20.A | `codex/wp20-detection` / `.worktrees/wp20-detection` | 最后一个 session task 通过后 finishing 并合并。 |
| WP21 | T21.1 | 21.A, 21.B, 21.C | `codex/wp21` / `.worktrees/wp21` | 最后一个 session task 通过后 finishing 并合并。 |
| WP22 | T22.1 | 22.A, 22.B, 22.C | `codex/wp22` / `.worktrees/wp22` | 最后一个 session task 通过后 finishing 并合并。 |
| WP23 | T23.1 | 23.A, 23.B, 23.C | `codex/wp23` / `.worktrees/wp23` | 最后一个 session task 通过后 finishing 并合并。 |
| WP24 | T24.1 | 24.A, 24.B, 24.C | `codex/wp24` / `.worktrees/wp24` | 最后一个 session task 通过后 finishing 并合并。 |
| WP25-CALL | T25.2 | 25.C, 25.D, 25.F | `codex/wp25-call` / `.worktrees/wp25-call` | 最后一个 session task 通过后 finishing 并合并。 |
| WP25-LOOP | T25.3 | 25.A, 25.E, 25.G | `codex/wp25-loop` / `.worktrees/wp25-loop` | 最后一个 session task 通过后 finishing 并合并。 |
| WP25-TURN | T25.1 | 25.B | `codex/wp25-turn` / `.worktrees/wp25-turn` | 最后一个 session task 通过后 finishing 并合并。 |
| WP26 | T26.1, T26.2 | 26.A, 26.D, 26.E, 26.B, 26.C | `codex/wp26` / `.worktrees/wp26` | 最后一个 session task 通过后 finishing 并合并。 |
| WP27 | T27.1 | 27.A, 27.B | `codex/wp27` / `.worktrees/wp27` | 最后一个 session task 通过后 finishing 并合并。 |
| WP28 | T28.1 | 28.A, 28.B, 28.C, 28.D | `codex/wp28` / `.worktrees/wp28` | 最后一个 session task 通过后 finishing 并合并。 |
| WP29 | T29.1 | 29.A, 29.B, 29.C | `codex/wp29` / `.worktrees/wp29` | 最后一个 session task 通过后 finishing 并合并。 |
| WP30-DEMO | T30.2 | 30.C, 30.D, 30.B | `codex/wp30-demo` / `.worktrees/wp30-demo` | 最后一个 session task 通过后 finishing 并合并。 |
| WP30-SCENARIO | T30.1 | 30.A | `codex/wp30-scenario` / `.worktrees/wp30-scenario` | 最后一个 session task 通过后 finishing 并合并。 |
| WP31 | T31.1 | 31.A, 31.B, 31.C | `codex/wp31` / `.worktrees/wp31` | 最后一个 session task 通过后 finishing 并合并。 |
| WP32 | T32.1 | 32.A, 32.B, 32.C | `codex/wp32` / `.worktrees/wp32` | 最后一个 session task 通过后 finishing 并合并。 |
| WP33 | T33.1 | 33.A, 33.B | `codex/wp33` / `.worktrees/wp33` | 最后一个 session task 通过后 finishing 并合并。 |
| WP34-DEMO | T34.1 | 34.B | `codex/wp34-demo` / `.worktrees/wp34-demo` | 最后一个 session task 通过后 finishing 并合并。 |
| WP34-REFERENCE | T34.2 | 34.A | `codex/wp34-reference` / `.worktrees/wp34-reference` | 最后一个 session task 通过后 finishing 并合并。 |
| WP35 | T35.1 | 35.A, 35.B, 35.C | `codex/wp35` / `.worktrees/wp35` | 最后一个 session task 通过后 finishing 并合并。 |
| WP36 | T36.1 | 36.A, 36.B, 36.C | `codex/wp36` / `.worktrees/wp36` | 最后一个 session task 通过后 finishing 并合并。 |
| WP37 | T37.1, T37.2 | 37.A, 37.B, 37.C | `codex/wp37` / `.worktrees/wp37` | 最后一个 session task 通过后 finishing 并合并。 |
| WP38 | T38.1, T38.2, T38.3 | 38.A, 38.B, 38.C, 38.D, 38.E, 38.F, 38.G | `codex/wp38` / `.worktrees/wp38` | 最后一个 session task 通过后 finishing 并合并。 |

## 5. Session Task Cards

### T01.1: Workspace Gate Bootstrap and Pure Boundary Evaluation

**Status:** Not started
**Work package:** WP01
**Legacy steps:** 1.A, 1.B
**Goal:** Create the sole Python 3.12 feasibility environment, frozen configs, and closed command runner used by every Task 1–3 proof.；Evaluate closed lexical/final-object/ACL observations without touching the filesystem and return stable pass/fail codes.
**SPEC contracts:** SPEC §0.1 `CanonicalRelativePathV1`; §1.4.3; §4.1 behavior 6–10; §4.3 behavior 4–5; §5.2; §5.5; §10.1 AC-01, AC-15, AC-21, AC-26, AC-31; §10.3 Windows integration; §11.2 item 1.
**Files:** `Create: requirements/gate.lock`; `Create: gates/pytest.ini`; `Create: gates/ruff.toml`; `Create: gates/mypy.ini`; `Create: scripts/run_gate_checks.py`; `Test: tests/feasibility/gate/test_gate_bootstrap.py`; `Create: spikes/win32_workspace_boundary/evaluator.py`; `Test: tests/feasibility/windows/test_workspace_boundary_evaluator.py`
**Depends:** ADMISSION_BASELINE_V2

**TDD contracts:**
1. `tests/feasibility/gate/test_gate_bootstrap.py::test_required_bootstrap_artifacts_are_declared` — 前置：所有 task predecessor 已合并且 1.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Create the sole Python 3.12 feasibility environment, frozen configs, and closed command runner used by every Task 1–3 proof.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/feasibility/windows/test_workspace_boundary_evaluator.py::test_unprovable_final_identity_fails_closed` — 前置：所有 task predecessor 已合并且 1.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Evaluate closed lexical/final-object/ACL observations without touching the filesystem and return stable pass/fail codes.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `GATE_OFFLINE_V1`
- Target (1.A): `py -3.12 -m unittest -v tests.feasibility.gate.test_gate_bootstrap.GateBootstrapContractTest.test_required_bootstrap_artifacts_are_declared`
- Domain (1.A): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/gate/test_gate_bootstrap.py -q`
- Expected (1.A): `0`
- Target (1.B): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/windows/test_workspace_boundary_evaluator.py::test_unprovable_final_identity_fails_closed -q`
- Domain (1.B): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/windows/test_workspace_boundary_evaluator.py -q`
- Expected (1.B): `0`

**Review focus:**
- SPEC (1.A): Spec compliance review checks Task 1.A's Goal, Milestone 1's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent bootstrap contract.
- Quality (1.A): Code quality review checks closed command exhaustiveness, immutable argument handling, identity/digest binding, deterministic exit propagation, and rejection before execution.
- SPEC (1.B): Spec compliance review checks Task 1.B's Goal, Milestone 1's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent observation-evaluation contract.
- Quality (1.B): Code quality review checks pure evaluation, exhaustive stable reason mapping, ordered immutable inputs, deterministic precedence, and fail-closed handling of missing facts.

**Done:** legacy steps 1.A, 1.B 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T01.2: Win32 Boundary Probes and GO Decision

**Status:** Not started
**Work package:** WP01
**Legacy steps:** 1.C, 1.D, 1.E
**Goal:** Produce real handle-derived identity, collision, reparse/hard-link, and ACL observations from a disposable NTFS workspace.；Prove two independent Windows processes cannot concurrently hold the same workspace-identity mutex.；Assemble the exact Task 1 GO/NO-GO report only when bootstrap, object/ACL, and mutex evidence are complete and identity-consistent.
**SPEC contracts:** SPEC §0.1 `CanonicalRelativePathV1`; §1.4.3; §4.1 behavior 6–10; §4.3 behavior 4–5; §5.2; §5.5; §10.1 AC-01, AC-15, AC-21, AC-26, AC-31; §10.3 Windows integration; §11.2 item 1.
**Files:** `Create: spikes/win32_workspace_boundary/object_probe.py`; `Test: tests/feasibility/windows/test_workspace_object_probe.py`; `Create: spikes/win32_workspace_boundary/mutex_probe.py`; `Test: tests/feasibility/windows/test_workspace_mutex_probe.py`; `Create: spikes/win32_workspace_boundary/report.py`; `Create: spikes/win32_workspace_boundary/probe.py`; `Test: tests/feasibility/windows/test_workspace_boundary_gate.py`
**Depends:** T01.1

**TDD contracts:**
1. `tests/feasibility/windows/test_workspace_object_probe.py::test_junction_target_identity_is_observed_from_handle` — 前置：所有 task predecessor 已合并且 1.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Produce real handle-derived identity, collision, reparse/hard-link, and ACL observations from a disposable NTFS workspace.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/feasibility/windows/test_workspace_mutex_probe.py::test_two_processes_never_hold_one_workspace_mutex_together` — 前置：所有 task predecessor 已合并且 1.D 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Prove two independent Windows processes cannot concurrently hold the same workspace-identity mutex.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/feasibility/windows/test_workspace_boundary_gate.py::test_gate_refuses_go_when_mutex_evidence_is_missing` — 前置：所有 task predecessor 已合并且 1.E 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Assemble the exact Task 1 GO/NO-GO report only when bootstrap, object/ACL, and mutex evidence are complete and identity-consistent.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `GATE_OFFLINE_V1`
- Target (1.C): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/windows/test_workspace_object_probe.py::test_junction_target_identity_is_observed_from_handle -q`
- Domain (1.C): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/windows/test_workspace_object_probe.py -q`
- Expected (1.C): all collision, device/UNC/ADS, reparse, hard-link, file/directory, and ACL fixtures produce closed observations and verified cleanup.
- Target (1.D): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/windows/test_workspace_mutex_probe.py::test_two_processes_never_hold_one_workspace_mutex_together -q`
- Domain (1.D): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/windows/test_workspace_mutex_probe.py -q`
- Expected (1.D): contention, timeout, abandoned-owner, distinct-workspace, and cleanup cases pass on Windows.
- Target (1.E): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/windows/test_workspace_boundary_gate.py::test_gate_refuses_go_when_mutex_evidence_is_missing -q`
- Domain (1.E): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/windows/test_workspace_boundary_gate.py -q`
- Expected (1.E): only complete identity-matching evidence yields GO; all missing/drifted/unprovable evidence yields NO_GO.

**Review focus:**
- SPEC (1.C): Spec compliance review checks Task 1.C's Goal, Milestone 1's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent Win32 object-probe contract.
- Quality (1.C): Code quality review checks handle lifetime and cleanup, lexical-versus-final identity separation, stable closed observation types, Win32 error propagation, and no aggregate decision leakage.
- SPEC (1.D): Spec compliance review checks Task 1.D's Goal, Milestone 1's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent workspace-mutex contract.
- Quality (1.D): Code quality review checks cross-process exclusivity, deterministic mutex naming, timeout/abandoned-owner handling, handle cleanup on every path, and bounded timing behavior.
- SPEC (1.E): Spec compliance review checks Task 1.E's Goal, Milestone 1's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent boundary-gate report contract.
- Quality (1.E): Code quality review checks complete evidence accounting, identity continuity, deterministic report digesting, GO/NO_GO exhaustiveness, and immutability of consumed evidence.

**Done:** legacy steps 1.C, 1.D, 1.E 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T02.1: Reference OCI Inputs, Build, Registry, and Isolation

**Status:** Not started
**Work package:** WP02
**Legacy steps:** 2.A, 2.B, 2.C, 2.D
**Goal:** Freeze one reference fixture, dependency lock, tool versions, and non-self-referential build-input manifest.；Build the frozen reference image and prove its manifest is reproducible and contains no final manifest/digest self-reference.；Push the exact local OCI manifest to a credential-free loopback registry, pull by digest, and verify cleanup plus three-way digest equality.；Prove one fresh reference container enforces the frozen no-network, non-root, read-only, bounded execution boundary.
**SPEC contracts:** SPEC §1.4.1 `ReferenceProfileManifestV1`; §1.4.5; §4.1 behavior 11–13; §4.5; §5.5; §8.2; §8.4; §10.1 AC-04, AC-19, AC-20, AC-24, AC-25, AC-30; §10.3 Docker integration; §11.2 item 2.
**Files:** `Create: requirements/reference.lock`; `Create: reference/fixture/pyproject.toml`; `Create: reference/fixture/requirements.lock`; `Create: reference/fixture/src/vesper_fixture/calculator.py`; `Create: reference/fixture/tests/test_calculator.py`; `Create: spikes/docker_reference_boundary/input_contract.py`; `Test: tests/feasibility/docker/test_reference_input_contract.py`; `Create: containers/reference/Dockerfile`; `Create: spikes/docker_reference_boundary/image_builder.py`; `Test: tests/feasibility/docker/test_reference_image_reproducibility.py`; `Create: spikes/docker_reference_boundary/registry_probe.py`; `Test: tests/feasibility/docker/test_loopback_registry_probe.py`; `Create: spikes/docker_reference_boundary/execution_probe.py`; `Test: tests/feasibility/docker/test_reference_container_isolation.py`
**Depends:** T01.1, T01.2

**TDD contracts:**
1. `tests/feasibility/docker/test_reference_input_contract.py::test_reference_lock_and_fixture_lock_must_be_byte_identical` — 前置：所有 task predecessor 已合并且 2.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Freeze one reference fixture, dependency lock, tool versions, and non-self-referential build-input manifest.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/feasibility/docker/test_reference_image_reproducibility.py::test_final_manifest_is_absent_from_image_members` — 前置：所有 task predecessor 已合并且 2.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Build the frozen reference image and prove its manifest is reproducible and contains no final manifest/digest self-reference.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/feasibility/docker/test_loopback_registry_probe.py::test_registry_digest_transformation_fails` — 前置：所有 task predecessor 已合并且 2.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Push the exact local OCI manifest to a credential-free loopback registry, pull by digest, and verify cleanup plus three-way digest equality.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. `tests/feasibility/docker/test_reference_container_isolation.py::test_workspace_write_attempt_is_rejected` — 前置：所有 task predecessor 已合并且 2.D 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Prove one fresh reference container enforces the frozen no-network, non-root, read-only, bounded execution boundary.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
5. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `GATE_OFFLINE_V1`
- Target (2.A): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_reference_input_contract.py::test_reference_lock_and_fixture_lock_must_be_byte_identical -q`
- Domain (2.A): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_reference_input_contract.py -q`
- Expected (2.A): exact lock/fixture/tool/build parameters freeze deterministically and reject drift.
- Target (2.B): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_reference_image_reproducibility.py::test_final_manifest_is_absent_from_image_members -q`
- Domain (2.B): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_reference_image_reproducibility.py -q`
- Expected (2.B): repeated frozen builds yield the same single-platform OCI digest and no final manifest member.
- Target (2.C): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_loopback_registry_probe.py::test_registry_digest_transformation_fails -q`
- Domain (2.C): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_loopback_registry_probe.py -q`
- Expected (2.C): local/registry/pull digests match; credential, external bind/push, cleanup, and injected-failure cases close deterministically.
- Target (2.D): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_reference_container_isolation.py::test_workspace_write_attempt_is_rejected -q`
- Domain (2.D): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_reference_container_isolation.py -q`
- Expected (2.D): every required runtime control is observed from a real container and cleanup is verified.

**Review focus:**
- SPEC (2.A): Spec compliance review checks Task 2.A's Goal, Milestone 2's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent frozen reference-input contract.
- Quality (2.A): Code quality review checks deterministic file/input ordering, exact digest binding, byte-level dual-lock comparison, immutable schema construction, and fail-closed drift handling.
- SPEC (2.B): Spec compliance review checks Task 2.B's Goal, Milestone 2's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent reproducible OCI build contract.
- Quality (2.B): Code quality review checks hermetic input use, reproducible OCI identity, complete layer/config/annotation scanning, single-platform evidence, and fail-closed scan results.
- SPEC (2.C): Spec compliance review checks Task 2.C's Goal, Milestone 2's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent loopback registry lifecycle contract.
- Quality (2.C): Code quality review checks loopback-only binding, credential absence, three-way digest identity, cleanup on every exit path, and deterministic failure evidence.
- SPEC (2.D): Spec compliance review checks Task 2.D's Goal, Milestone 2's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent reference-container isolation contract.
- Quality (2.D): Code quality review checks fresh-container construction, complete observed-control accounting, bounded resources, cleanup on all paths, and fail-closed missing evidence.

**Done:** legacy steps 2.A, 2.B, 2.C, 2.D 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T02.2: Reference Evidence, Stability, and GO Decision

**Status:** Not started
**Work package:** WP02
**Legacy steps:** 2.E, 2.F, 2.G
**Goal:** Emit complete explicitly loaded pytest lifecycle evidence for collection, full run, and target rerun inside the reference boundary.；Prove two independent target-failure runs produce byte-identical normalized gate fingerprint inputs without defining the production fingerprint.；Freeze `ReferenceProfileManifestV1` and emit GO only when build, registry, isolation, pytest, and fingerprint evidence are complete and identity-consistent.
**SPEC contracts:** SPEC §1.4.1 `ReferenceProfileManifestV1`; §1.4.5; §4.1 behavior 11–13; §4.5; §5.5; §8.2; §8.4; §10.1 AC-04, AC-19, AC-20, AC-24, AC-25, AC-30; §10.3 Docker integration; §11.2 item 2.
**Files:** `Create: spikes/docker_reference_boundary/pytest_reporter.py`; `Test: tests/feasibility/docker/test_gate_pytest_evidence.py`; `Create: spikes/docker_reference_boundary/failure_fingerprint_probe.py`; `Test: tests/feasibility/docker/test_gate_failure_input_stability.py`; `Create: reference/manifest/reference-profile-v1.json`; `Create: spikes/docker_reference_boundary/probe.py`; `Create: spikes/docker_reference_boundary/report.py`; `Test: tests/feasibility/docker/test_reference_boundary_gate.py`
**Depends:** T01.1, T01.2, T02.1

**TDD contracts:**
1. `tests/feasibility/docker/test_gate_pytest_evidence.py::test_missing_teardown_event_invalidates_gate_report` — 前置：所有 task predecessor 已合并且 2.E 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Emit complete explicitly loaded pytest lifecycle evidence for collection, full run, and target rerun inside the reference boundary.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/feasibility/docker/test_gate_failure_input_stability.py::test_independent_target_failures_have_identical_inputs` — 前置：所有 task predecessor 已合并且 2.F 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Prove two independent target-failure runs produce byte-identical normalized gate fingerprint inputs without defining the production fingerprint.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/feasibility/docker/test_reference_boundary_gate.py::test_gate_rejects_loopback_registry_digest_mismatch` — 前置：所有 task predecessor 已合并且 2.G 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Freeze `ReferenceProfileManifestV1` and emit GO only when build, registry, isolation, pytest, and fingerprint evidence are complete and identity-consistent.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `GATE_OFFLINE_V1`
- Target (2.E): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_gate_pytest_evidence.py::test_missing_teardown_event_invalidates_gate_report -q`
- Domain (2.E): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_gate_pytest_evidence.py -q`
- Expected (2.E): missing/truncated/duplicate/implicit/mismatched evidence fails and complete explicit reports pass.
- Target (2.F): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_gate_failure_input_stability.py::test_independent_target_failures_have_identical_inputs -q`
- Domain (2.F): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_gate_failure_input_stability.py -q`
- Expected (2.F): stable independent inputs compare equal and every semantic input difference compares unequal.
- Target (2.G): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_reference_boundary_gate.py::test_gate_rejects_loopback_registry_digest_mismatch -q`
- Domain (2.G): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_reference_boundary_gate.py -q`
- Expected (2.G): complete matching evidence yields GO; every missing/drifted/transformed input yields NO_GO.

**Review focus:**
- SPEC (2.E): Spec compliance review checks Task 2.E's Goal, Milestone 2's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent gate pytest evidence contract.
- Quality (2.E): Code quality review checks explicit reporter loading, immutable event ordering, lifecycle completeness, integrity binding, stable rejection reasons, and truncated-report handling.
- SPEC (2.F): Spec compliance review checks Task 2.F's Goal, Milestone 2's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent gate fingerprint-input stability contract.
- Quality (2.F): Code quality review checks deterministic normalization, canonical location handling, complete semantic-field binding, symmetric comparison, and separation from production fingerprints.
- SPEC (2.G): Spec compliance review checks Task 2.G's Goal, Milestone 2's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent Docker boundary GO report contract.
- Quality (2.G): Code quality review checks exhaustive producer accounting, cross-evidence identity continuity, deterministic manifest/report bytes, GO/NO_GO closure, and upstream immutability.

**Done:** legacy steps 2.E, 2.F, 2.G 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T03.1: Persistence Protocol, Faults, Deadlines, and Identity

**Status:** Not started
**Work package:** WP03
**Legacy steps:** 3.A, 3.B, 3.C, 3.D
**Goal:** Define and durably record the sorted one-to-three-path PREPARED/WRITING/terminal transaction protocol without applying recovery.；Apply sorted CREATE/REPLACE operations with deterministic interruption around every replace and durable-state write.；Stop before any write on pre-write expiry and stop all subsequent workspace writes after post-write expiry.；Classify current bytes/object identity against preimage/postimage evidence and fail closed on any external or unprovable change.
**SPEC contracts:** SPEC §1.4.4; §4.2.6 deadline rules; §4.6; §5.2; §5.5; §5.6; §10.1 AC-07, AC-21, AC-22, AC-29, AC-31; §10.3 recovery fault injection; §11.2 item 3.
**Files:** `Create: spikes/persistence_recovery/protocol.py`; `Test: tests/feasibility/persistence/test_transaction_protocol.py`; `Create: spikes/persistence_recovery/faults.py`; `Test: tests/feasibility/persistence/test_write_fault_matrix.py`; `Create: spikes/persistence_recovery/deadline.py`; `Test: tests/feasibility/persistence/test_persistence_deadlines.py`; `Create: spikes/persistence_recovery/observation.py`; `Test: tests/feasibility/persistence/test_external_change_classifier.py`
**Depends:** T01.1, T02.2

**TDD contracts:**
1. `tests/feasibility/persistence/test_transaction_protocol.py::test_prepare_rejects_two_create_operations` — 前置：所有 task predecessor 已合并且 3.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Define and durably record the sorted one-to-three-path PREPARED/WRITING/terminal transaction protocol without applying recovery.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/feasibility/persistence/test_write_fault_matrix.py::test_interruption_after_each_replace_has_durable_observation` — 前置：所有 task predecessor 已合并且 3.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Apply sorted CREATE/REPLACE operations with deterministic interruption around every replace and durable-state write.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/feasibility/persistence/test_persistence_deadlines.py::test_deadline_after_first_replace_forbids_next_write` — 前置：所有 task predecessor 已合并且 3.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Stop before any write on pre-write expiry and stop all subsequent workspace writes after post-write expiry.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. `tests/feasibility/persistence/test_external_change_classifier.py::test_same_bytes_with_replaced_object_is_external_change` — 前置：所有 task predecessor 已合并且 3.D 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Classify current bytes/object identity against preimage/postimage evidence and fail closed on any external or unprovable change.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
5. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `GATE_OFFLINE_V1`
- Target (3.A): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_transaction_protocol.py::test_prepare_rejects_two_create_operations -q`
- Domain (3.A): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_transaction_protocol.py -q`
- Expected (3.A): invalid cardinality/order/preimage/state transitions fail before workspace mutation and valid PREPARED records persist.
- Target (3.B): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_write_fault_matrix.py::test_interruption_after_each_replace_has_durable_observation -q`
- Domain (3.B): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_write_fault_matrix.py -q`
- Expected (3.B): every before/after PREPARED/WRITING/replace/progress/terminal fault point is observed deterministically.
- Target (3.C): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_persistence_deadlines.py::test_deadline_after_first_replace_forbids_next_write -q`
- Domain (3.C): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_persistence_deadlines.py -q`
- Expected (3.C): all deadline boundaries deterministically allow zero or no further writes as specified.
- Target (3.D): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_external_change_classifier.py::test_same_bytes_with_replaced_object_is_external_change -q`
- Domain (3.D): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_external_change_classifier.py -q`
- Expected (3.D): byte/object mismatches and unprovable identities always classify unsafe.

**Review focus:**
- SPEC (3.A): Spec compliance review checks Task 3.A's Goal, Milestone 3's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent durable transaction protocol contract.
- Quality (3.A): Code quality review checks sorted-entry validation, atomic durable record creation, closed state transitions, pre-mutation rejection, and deterministic persistence errors.
- SPEC (3.B): Spec compliance review checks Task 3.B's Goal, Milestone 3's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent deterministic write fault matrix contract.
- Quality (3.B): Code quality review checks fault-point exhaustiveness, sorted operation order, flush/replace durability, deterministic interruption evidence, and no hidden recovery policy.
- SPEC (3.C): Spec compliance review checks Task 3.C's Goal, Milestone 3's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent persistence deadline disposition contract.
- Quality (3.C): Code quality review checks boundary-time determinism, write-count invariants, closed disposition exhaustiveness, side-effect freedom, and irreversible no-further-write authorization.
- SPEC (3.D): Spec compliance review checks Task 3.D's Goal, Milestone 3's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent path identity classifier contract.
- Quality (3.D): Code quality review checks byte/object comparison precedence, exhaustive five-value results, stable unsafe classification, immutable inputs, and side-effect-free evaluation.

**Done:** legacy steps 3.A, 3.B, 3.C, 3.D 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T03.2: Recovery Classification, Application, and GO Decision

**Status:** Not started
**Work package:** WP03
**Legacy steps:** 3.E, 3.F, 3.G
**Goal:** Produce a byte-for-byte read-only recovery preview with only COMMITTED, ROLLED_BACK, or UNRESOLVED.；Apply only a previously previewed safe recovery while holding the workspace mutex and preserve unknown/external objects.；Run the complete fault/deadline/external-change/preview/apply matrix on disposable NTFS objects and emit the Task 3 GO/NO-GO report.
**SPEC contracts:** SPEC §1.4.4; §4.2.6 deadline rules; §4.6; §5.2; §5.5; §5.6; §10.1 AC-07, AC-21, AC-22, AC-29, AC-31; §10.3 recovery fault injection; §11.2 item 3.
**Files:** `Create: spikes/persistence_recovery/recovery_preview.py`; `Test: tests/feasibility/persistence/test_recovery_preview.py`; `Create: spikes/persistence_recovery/recovery_apply.py`; `Test: tests/feasibility/persistence/test_recovery_apply.py`; `Create: spikes/persistence_recovery/report.py`; `Test: tests/feasibility/persistence/test_recovery_gate.py`
**Depends:** T01.2, T02.2, T03.1

**TDD contracts:**
1. `tests/feasibility/persistence/test_recovery_preview.py::test_preview_is_byte_for_byte_read_only` — 前置：所有 task predecessor 已合并且 3.E 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Produce a byte-for-byte read-only recovery preview with only COMMITTED, ROLLED_BACK, or UNRESOLVED.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/feasibility/persistence/test_recovery_apply.py::test_apply_never_deletes_externally_replaced_create` — 前置：所有 task predecessor 已合并且 3.F 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Apply only a previously previewed safe recovery while holding the workspace mutex and preserve unknown/external objects.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/feasibility/persistence/test_recovery_gate.py::test_missing_external_identity_case_forces_no_go` — 前置：所有 task predecessor 已合并且 3.G 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Run the complete fault/deadline/external-change/preview/apply matrix on disposable NTFS objects and emit the Task 3 GO/NO-GO report.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `GATE_OFFLINE_V1`
- Target (3.E): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_recovery_preview.py::test_preview_is_byte_for_byte_read_only -q`
- Domain (3.E): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_recovery_preview.py -q`
- Expected (3.E): every mixed-path state maps to one disposition with zero writes.
- Target (3.F): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_recovery_apply.py::test_apply_never_deletes_externally_replaced_create -q`
- Domain (3.F): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_recovery_apply.py -q`
- Expected (3.F): only exact safe pre/postimage cases change and external/unprovable cases remain untouched.
- Target (3.G): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_recovery_gate.py::test_missing_external_identity_case_forces_no_go -q`
- Domain (3.G): `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_recovery_gate.py -q`
- Expected (3.G): every named fault/deadline/external-change/preview/apply case runs on NTFS, cleanup is verified, and only a complete matrix yields GO.

**Review focus:**
- SPEC (3.E): Spec compliance review checks Task 3.E's Goal, Milestone 3's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent read-only recovery preview contract.
- Quality (3.E): Code quality review checks byte-for-byte read-only behavior, complete path accounting, three-value disposition exhaustiveness, immutable preview binding, and unsafe mixed-state handling.
- SPEC (3.F): Spec compliance review checks Task 3.F's Goal, Milestone 3's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent explicit recovery application contract.
- Quality (3.F): Code quality review checks preview-digest binding, mutex ownership, exact safe-case writes, external-object preservation, terminal record durability, and fail-closed explicit intent.
- SPEC (3.G): Spec compliance review checks Task 3.G's Goal, Milestone 3's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent NTFS persistence-recovery GO matrix contract.
- Quality (3.G): Code quality review checks exact matrix enumeration, real-object identity continuity, deterministic case ordering, cleanup on all paths, GO/NO_GO exhaustiveness, and no silent case reduction.

**Done:** legacy steps 3.E, 3.F, 3.G 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T04.1: Dependency Closure and Formal Toolchain

**Status:** Not started
**Work package:** WP04
**Legacy steps:** 4.A, 4.F
**Goal:** Create the minimal Python 3.12 project identity and freeze the sole complete, reviewed, hash-locked v1 runtime/build/development dependency closure without package, classification, marker, source, or lock ambiguity.；Promote the exact Task 1 pytest/Ruff/Mypy identities, marker set, and static rules into the sole formal offline toolchain and configure the locked build backend without changing the completed dependency closure.
**SPEC contracts:** SPEC §0; §0.1 and CTV-01–CTV-07; §5.2; §9; §10.1 AC-10 and AC-26; course requirements §3.6, §4.8, §5; `AGENTS.md` build/test, TDD, and credential-scan rules.
**Files:** `Create: pyproject.toml`; `Create: requirements/dev.lock`; `Create: src/vespercode/__init__.py`; `Create: src/vespercode/project/dependency_closure.py`; `Create: config/dependency-closure-v1.json`; `Create: scripts/bootstrap_formal_env.py`; `Test: tests/unit/process/test_dependency_closure.py`; `Modify: pyproject.toml`; `Create: src/vespercode/project/toolchain_promotion.py`; `Create: config/formal-toolchain-promotion-v1.json`; `Test: tests/unit/process/test_toolchain_promotion.py`
**Depends:** T01.2, T02.2, T03.2

**TDD contracts:**
1. `tests/unit/process/test_dependency_closure.py::test_declared_v1_dependency_closure_is_complete` — 前置：所有 task predecessor 已合并且 4.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Create the minimal Python 3.12 project identity and freeze the sole complete, reviewed, hash-locked v1 runtime/build/development dependency closure without package, classification, marker, source, or lock ambiguity.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/process/test_toolchain_promotion.py::test_formal_toolchain_matches_frozen_gate_identity` — 前置：所有 task predecessor 已合并且 4.F 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Promote the exact Task 1 pytest/Ruff/Mypy identities, marker set, and static rules into the sole formal offline toolchain and configure the locked build backend without changing the completed dependency closure.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Bootstrap (4.A): `py -3.12 scripts/bootstrap_formal_env.py`
- Target (4.A): `.venv-formal\Scripts\python.exe -m pytest -q tests/unit/process/test_dependency_closure.py::test_declared_v1_dependency_closure_is_complete`
- Domain (4.A): `.venv-formal\Scripts\python.exe -m pytest -q tests/unit/process/test_dependency_closure.py`
- Expected (4.A, 1): `0`
- Expected (4.A, 2): `record.python_version == gate_evidence.python_version`
- Bootstrap (4.F): `py -3.12 scripts/bootstrap_formal_env.py`
- Target (4.F): `.venv-formal\Scripts\python.exe -m pytest -q tests/unit/process/test_toolchain_promotion.py::test_formal_toolchain_matches_frozen_gate_identity`
- Domain (4.F): `.venv-formal\Scripts\python.exe -m pytest -q tests/unit/process/test_dependency_closure.py tests/unit/process/test_toolchain_promotion.py`
- Closure (4.F, 1): `.venv-formal\Scripts\python.exe -m ruff format --check .`
- Closure (4.F, 2): `.venv-formal\Scripts\python.exe -m ruff check .`
- Closure (4.F, 3): `.venv-formal\Scripts\python.exe -m mypy src tests`
- Expected (4.F, 1): `0`
- Expected (4.F, 2): `record.python_version == gate_evidence.python_version`

**Review focus:**
- SPEC (4.A): Spec compliance review checks Task 4.A's Goal, Milestone 4's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent dependency-closure/bootstrap contract.
- Quality (4.A): Code quality review checks dependency-family completeness, classification/source/marker consistency, total hash closure, exact gate identity equality, bootstrap fail-closed behavior, and unique record/lock agreement.
- SPEC (4.F): Spec compliance review checks Task 4.F's Goal, Milestone 4's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent formal toolchain promotion contract.
- Quality (4.F): Code quality review checks exact gate-to-formal identity comparison, marker/addopts closure, canonical command construction, tooling-section-only edits, immutable promotion records, and dependency-byte preservation.

**Done:** legacy steps 4.A, 4.F 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T04.2: Canonical Bytes, Time, Paths, and Credential Scan

**Status:** Not started
**Work package:** WP04
**Legacy steps:** 4.B, 4.C, 4.D, 4.E
**Goal:** Encode every v1 canonical value into exact bytes and compute the sole domain-separated SHA-256 identity.；Accept only the v1 UTC millisecond timestamp form and make every current-time observation injectable and deterministic.；Reject every unsupported lexical path form before any filesystem access and return the sole canonical relative-path representation.；Fail a changed-file credential scan on a match while reporting only bounded paths and rule ids and never the matched value.
**SPEC contracts:** SPEC §0; §0.1 and CTV-01–CTV-07; §5.2; §9; §10.1 AC-10 and AC-26; course requirements §3.6, §4.8, §5; `AGENTS.md` build/test, TDD, and credential-scan rules.
**Files:** `Create: src/vespercode/canonical/json_v1.py`; `Create: src/vespercode/canonical/digest.py`; `Test: tests/unit/canonical/test_json_v1.py`; `Test: tests/unit/canonical/test_digest_vectors.py`; `Create: src/vespercode/canonical/timestamp_v1.py`; `Create: src/vespercode/canonical/clock.py`; `Test: tests/unit/canonical/test_timestamp_v1.py`; `Test: tests/unit/canonical/test_clock.py`; `Create: src/vespercode/canonical/path_v1.py`; `Test: tests/unit/canonical/test_path_v1.py`; `Create: scripts/scan_credentials.py`; `Test: tests/unit/process/test_scan_credentials.py`
**Depends:** T04.1

**TDD contracts:**
1. `tests/unit/canonical/test_digest_vectors.py::test_ctv_01_exact_bytes_and_digest` — 前置：所有 task predecessor 已合并且 4.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Encode every v1 canonical value into exact bytes and compute the sole domain-separated SHA-256 identity.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/canonical/test_clock.py::test_fake_clock_advances_exact_milliseconds` — 前置：所有 task predecessor 已合并且 4.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Accept only the v1 UTC millisecond timestamp form and make every current-time observation injectable and deterministic.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/unit/canonical/test_path_v1.py::test_device_and_parent_paths_are_rejected` — 前置：所有 task predecessor 已合并且 4.D 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Reject every unsupported lexical path form before any filesystem access and return the sole canonical relative-path representation.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. `tests/unit/process/test_scan_credentials.py::test_scanner_reports_rule_without_matched_value` — 前置：所有 task predecessor 已合并且 4.E 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Fail a changed-file credential scan on a match while reporting only bounded paths and rule ids and never the matched value.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
5. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (4.B): `python -m pytest -q tests/unit/canonical/test_digest_vectors.py::test_ctv_01_exact_bytes_and_digest`
- Domain (4.B): `python -m pytest -q tests/unit/canonical/test_json_v1.py tests/unit/canonical/test_digest_vectors.py`
- Expected (4.B): `0`
- Target (4.C): `python -m pytest -q tests/unit/canonical/test_clock.py::test_fake_clock_advances_exact_milliseconds`
- Domain (4.C): `python -m pytest -q tests/unit/canonical/test_timestamp_v1.py tests/unit/canonical/test_clock.py`
- Expected (4.C): `0`
- Target (4.D): `python -m pytest -q tests/unit/canonical/test_path_v1.py::test_device_and_parent_paths_are_rejected`
- Domain (4.D): `python -m pytest -q tests/unit/canonical/test_path_v1.py`
- Expected (4.D): `0`
- Target (4.E): `python -m pytest -q tests/unit/process/test_scan_credentials.py::test_scanner_reports_rule_without_matched_value`
- Domain (4.E): `python -m pytest -q tests/unit/process/test_scan_credentials.py`
- Expected (4.E): `0`

**Review focus:**
- SPEC (4.B): Spec compliance review checks Task 4.B's Goal, Milestone 4's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent canonical JSON/digest contract.
- Quality (4.B): Code quality review checks recursive closed-value validation, deterministic byte identity, domain/version separation, Unicode rejection, immutable arrays, and vector stability.
- SPEC (4.C): Spec compliance review checks Task 4.C's Goal, Milestone 4's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent canonical timestamp/clock contract.
- Quality (4.C): Code quality review checks UTC/millisecond exactness, Gregorian edge rejection, leap-second handling, deterministic fake-clock state, protocol substitutability, and absence of hidden wall-clock reads.
- SPEC (4.D): Spec compliance review checks Task 4.D's Goal, Milestone 4's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent canonical relative path contract.
- Quality (4.D): Code quality review checks normalization-free lexical decisions, complete sentinel rejection, segment handling, stable errors, side-effect freedom, and no leakage of filesystem authorization.
- SPEC (4.E): Spec compliance review checks Task 4.E's Goal, Milestone 4's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent redacted credential scanner contract.
- Quality (4.E): Code quality review checks explicit path scoping, deterministic finding order, binary handling, stable path errors, redaction completeness, non-disclosure in exceptions/logs, and zero network use.

**Done:** legacy steps 4.B, 4.C, 4.D, 4.E 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T05.1: Closed Shared Value, Location, Evidence, and Error Contracts

**Status:** Not started
**Work package:** WP05
**Legacy steps:** 5.A, 5.B, 5.C, 5.E, 5.D
**Goal:** Define closed generic optional-value objects so every absent/present field is explicit and cannot collapse into nullable ambiguity.；Define the closed Run state/phase/wait/limit vocabulary and exact specialized wait-decision envelope.；Define the shared closed action identity, policy decision, stable action error, and action-result envelopes.；Define canonical repository-location and disclosure-path-scope value objects with no ambiguous root/path representation.；Define the shared closed evidence/artifact/digest/location vocabulary consumed across tools, validation, audit, and delivery.
**SPEC contracts:** SPEC §0.1 closed-schema rules; §4.2.1–§4.2.2 shared status/action contracts; §4.4.3–§4.4.4 location/source unions; §7 data model; §10.1 AC-17, AC-26, AC-27, AC-28.
**Files:** `Create: src/vespercode/contracts/optional.py`; `Test: tests/unit/contracts/test_optional.py`; `Create: src/vespercode/contracts/run.py`; `Test: tests/unit/contracts/test_run.py`; `Create: src/vespercode/contracts/action.py`; `Test: tests/unit/contracts/test_action.py`; `Create: src/vespercode/contracts/location.py`; `Test: tests/unit/contracts/test_location.py`; `Create: src/vespercode/contracts/evidence.py`; `Test: tests/unit/contracts/test_evidence.py`
**Depends:** T04.1, T04.2

**TDD contracts:**
1. `tests/unit/contracts/test_optional.py::test_present_optional_requires_value` — 前置：所有 task predecessor 已合并且 5.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Define closed generic optional-value objects so every absent/present field is explicit and cannot collapse into nullable ambiguity.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/contracts/test_run.py::test_running_state_requires_exact_phase` — 前置：所有 task predecessor 已合并且 5.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Define the closed Run state/phase/wait/limit vocabulary and exact specialized wait-decision envelope.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/unit/contracts/test_action.py::test_success_result_rejects_error_payload` — 前置：所有 task predecessor 已合并且 5.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Define the shared closed action identity, policy decision, stable action error, and action-result envelopes.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. `tests/unit/contracts/test_location.py::test_repository_root_rejects_path_field` — 前置：所有 task predecessor 已合并且 5.E 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Define canonical repository-location and disclosure-path-scope value objects with no ambiguous root/path representation.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
5. `tests/unit/contracts/test_evidence.py::test_artifact_reference_rejects_unbound_digest` — 前置：所有 task predecessor 已合并且 5.D 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Define the shared closed evidence/artifact/digest/location vocabulary consumed across tools, validation, audit, and delivery.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
6. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (5.A): `python -m pytest -q tests/unit/contracts/test_optional.py::test_present_optional_requires_value`
- Domain (5.A): `python -m pytest -q tests/unit/contracts/test_optional.py`
- Expected (5.A): `0`
- Target (5.B): `python -m pytest -q tests/unit/contracts/test_run.py::test_running_state_requires_exact_phase`
- Domain (5.B): `python -m pytest -q tests/unit/contracts/test_run.py`
- Expected (5.B): every legal state/phase/wait/limit combination round-trips and every illegal combination rejects.
- Target (5.C): `python -m pytest -q tests/unit/contracts/test_action.py::test_success_result_rejects_error_payload`
- Domain (5.C): `python -m pytest -q tests/unit/contracts/test_action.py`
- Expected (5.C): legal actions/results validate and unknown/mixed/contradictory envelopes reject.
- Target (5.E): `python -m pytest -q tests/unit/contracts/test_location.py::test_repository_root_rejects_path_field`
- Domain (5.E): `python -m pytest -q tests/unit/contracts/test_location.py`
- Expected (5.E): `0`
- Target (5.D): `python -m pytest -q tests/unit/contracts/test_evidence.py::test_artifact_reference_rejects_unbound_digest`
- Domain (5.D): `python -m pytest -q tests/unit/contracts/test_evidence.py`
- Expected (5.D): every evidence variant is closed/digest-bound and invalid/unknown combinations reject.

**Review focus:**
- SPEC (5.A): Spec compliance review checks Task 5.A's Goal, Milestone 5's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent closed optional values contract.
- Quality (5.A): Code quality review checks discriminant closure, generic value preservation, absent/present exclusivity, deterministic serialization/validation, and no nullable fallback.
- SPEC (5.B): Spec compliance review checks Task 5.B's Goal, Milestone 5's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent Run/wait state contracts contract.
- Quality (5.B): Code quality review checks enum/union exhaustiveness, state-phase invariants, wait subject identity binding, timestamp typing, deterministic rejection, and absence of lifecycle side effects.
- SPEC (5.C): Spec compliance review checks Task 5.C's Goal, Milestone 5's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent closed action/result contracts contract.
- Quality (5.C): Code quality review checks discriminant exhaustiveness, semantic/instance identity typing, status/payload invariants, stable error closure, deterministic rejection, and schema-only purity.
- SPEC (5.E): Spec compliance review checks Task 5.E's Goal, Milestone 5's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent repository/disclosure location contracts contract.
- Quality (5.E): Code quality review checks discriminant closure, root/path exclusivity, file/directory scope separation, canonical field typing, deterministic rejection, and absence of domain behavior.
- SPEC (5.D): Spec compliance review checks Task 5.D's Goal, Milestone 5's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent shared evidence contracts contract.
- Quality (5.D): Code quality review checks digest/location binding, closed variant exhaustiveness, immutable stable-code ordering, deterministic stable errors, and separation from artifact/audit side effects.

**Done:** legacy steps 5.A, 5.B, 5.C, 5.E, 5.D 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T06.1: Built-in Profiles, Trusted Endpoints, and Registry

**Status:** Not started
**Work package:** WP06
**Legacy steps:** 6.A, 6.B, 6.C, 6.D, 6.E
**Goal:** Implement the sole built-in editable path/operation policy and deterministic segment-boundary matching.；Load and integrity-check the built-in reference manifest against Task 2.G image, lock, tool, execution, and check-plan evidence.；Define immutable mutually exclusive Mock and OpenAI LLM profile contracts and packaged built-ins.；Resolve only the built-in public OpenAI endpoint ID to an immutable trusted endpoint record.；Resolve exact built-in editable/reference/LLM/endpoint profiles and reject missing, duplicate, extra, or cross-profile data before Run creation.
**SPEC contracts:** SPEC §1.4.1; §4.1 input and behavior 1–4; §4.4.3 endpoint/profile fields; §5.2; §7 profile/config rows; §8.2; §9; §10.1 AC-13, AC-15, AC-26, AC-30, AC-31.
**Files:** `Create: src/vespercode/profiles/editable.py`; `Test: tests/unit/profiles/test_editable.py`; `Create: src/vespercode/profiles/reference.py`; `Create: src/vespercode/profiles/builtin/reference-profile-v1.json`; `Test: tests/unit/profiles/test_reference.py`; `Modify: reference/manifest/reference-profile-v1.json`; `Create: src/vespercode/profiles/llm.py`; `Create: src/vespercode/profiles/builtin/mock-deterministic-v1.json`; `Create: src/vespercode/profiles/builtin/openai-single-turn-v1.json`; `Test: tests/unit/profiles/test_llm.py`; `Create: src/vespercode/profiles/endpoints.py`; `Test: tests/unit/profiles/test_endpoints.py`; `Create: src/vespercode/profiles/registry.py`; `Test: tests/unit/profiles/test_registry.py`
**Depends:** T02.2, T04.2, T05.1

**TDD contracts:**
1. `tests/unit/profiles/test_editable.py::test_src_prefix_without_segment_boundary_is_not_editable` — 前置：所有 task predecessor 已合并且 6.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Implement the sole built-in editable path/operation policy and deterministic segment-boundary matching.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/profiles/test_reference.py::test_reference_profile_rejects_image_digest_drift` — 前置：所有 task predecessor 已合并且 6.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Load and integrity-check the built-in reference manifest against Task 2.G image, lock, tool, execution, and check-plan evidence.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/unit/profiles/test_llm.py::test_mock_profile_rejects_openai_fields` — 前置：所有 task predecessor 已合并且 6.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Define immutable mutually exclusive Mock and OpenAI LLM profile contracts and packaged built-ins.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. `tests/unit/profiles/test_endpoints.py::test_endpoint_registry_rejects_user_url` — 前置：所有 task predecessor 已合并且 6.D 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Resolve only the built-in public OpenAI endpoint ID to an immutable trusted endpoint record.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
5. `tests/unit/profiles/test_registry.py::test_registry_rejects_duplicate_profile_id` — 前置：所有 task predecessor 已合并且 6.E 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Resolve exact built-in editable/reference/LLM/endpoint profiles and reject missing, duplicate, extra, or cross-profile data before Run creation.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
6. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (6.A): `python -m pytest -q tests/unit/profiles/test_editable.py::test_src_prefix_without_segment_boundary_is_not_editable`
- Domain (6.A): `python -m pytest -q tests/unit/profiles/test_editable.py`
- Expected (6.A): `src`
- Target (6.B): `python -m pytest -q tests/unit/profiles/test_reference.py::test_reference_profile_rejects_image_digest_drift`
- Domain (6.B): `python -m pytest -q tests/unit/profiles/test_reference.py`
- Expected (6.B): exact Task 2.G identities load and every missing/extra/drifted field rejects.
- Target (6.C): `python -m pytest -q tests/unit/profiles/test_llm.py::test_mock_profile_rejects_openai_fields`
- Domain (6.C): `python -m pytest -q tests/unit/profiles/test_llm.py`
- Expected (6.C): exact built-ins load and cross-mode/unknown/mutable fields reject.
- Target (6.D): `python -m pytest -q tests/unit/profiles/test_endpoints.py::test_endpoint_registry_rejects_user_url`
- Domain (6.D): `python -m pytest -q tests/unit/profiles/test_endpoints.py`
- Expected (6.D): the sole built-in ID resolves and every other ID/URL rejects without network access.
- Target (6.E): `python -m pytest -q tests/unit/profiles/test_registry.py::test_registry_rejects_duplicate_profile_id`
- Domain (6.E): `python -m pytest -q tests/unit/profiles/test_registry.py`
- Expected (6.E): exact built-ins resolve deterministically and every ambiguity/drift/unknown ID rejects before a Run exists.

**Review focus:**
- SPEC (6.A): Spec compliance review checks Task 6.A's Goal, Milestone 6's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent immutable editable-path policy contract.
- Quality (6.A): Code quality review checks segment-boundary correctness, canonical-path inputs, operation closure, immutable root ordering, deterministic digesting, and override rejection.
- SPEC (6.B): Spec compliance review checks Task 6.B's Goal, Milestone 6's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent reference-profile manifest integrity contract.
- Quality (6.B): Code quality review checks exact gate/production field correspondence, digest identity, packaged-resource immutability, missing/extra rejection, and side-effect-free integrity validation.
- SPEC (6.C): Spec compliance review checks Task 6.C's Goal, Milestone 6's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent closed LLM profiles contract.
- Quality (6.C): Code quality review checks mode-discriminant closure, cross-field exclusivity, immutable resource identity, unknown-field rejection, deterministic loading, and zero credential/network behavior.
- SPEC (6.D): Spec compliance review checks Task 6.D's Goal, Milestone 6's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent trusted OpenAI endpoint registry contract.
- Quality (6.D): Code quality review checks exact literal identity, closed lookup behavior, raw-URL rejection, immutable returned records, deterministic errors, and network-free resolution.
- SPEC (6.E): Spec compliance review checks Task 6.E's Goal, Milestone 6's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent built-in profile registry contract.
- Quality (6.E): Code quality review checks deterministic enumeration, per-kind id uniqueness, integrity delegation, exact typed returns, ambiguity/drift rejection, and absence of mutable/external discovery.

**Done:** legacy steps 6.A, 6.B, 6.C, 6.D, 6.E 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T07.1: SQLite Migration, Run Lifecycle, and Idempotency Core

**Status:** Not started
**Work package:** WP07-CORE
**Legacy steps:** 7.A, 7.B, 7.C
**Goal:** Open the local control database with explicit transaction semantics and apply an injected tuple of closed migrations in order, atomically, idempotently, and fail-closed on checksum drift without knowing any application-domain schema.；Apply the closed Run/wait transition matrix atomically so exactly one correctly bound wait decision can win.；Return the first result for an identical event request and reject reuse of the same event id for different request bytes without performing domain mutation.
**SPEC contracts:** SPEC §4.2.1; §4.2.7; §4.7 audit ordering; §5.2; §5.4; §5.6; §7 complete data model and storage split; §10.1 AC-16, AC-21, AC-27, AC-28.
**Files:** `Create: src/vespercode/storage/connection.py`; `Create: src/vespercode/storage/migration_engine.py`; `Create: src/vespercode/storage/migrations/__init__.py`; `Test: tests/unit/storage/test_connection.py`; `Test: tests/unit/storage/test_migration_engine.py`; `Create: src/vespercode/storage/migrations/v0001_run_wait.py`; `Create: src/vespercode/storage/run_repository.py`; `Create: src/vespercode/runs/lifecycle.py`; `Test: tests/unit/storage/test_run_wait_migration.py`; `Test: tests/unit/storage/test_run_repository.py`; `Test: tests/unit/runs/test_lifecycle.py`; `Create: src/vespercode/storage/migrations/v0002_idempotency.py`; `Create: src/vespercode/storage/idempotency.py`; `Test: tests/unit/storage/test_idempotency_migration.py`; `Test: tests/unit/storage/test_idempotency.py`
**Depends:** T05.1

**TDD contracts:**
1. `tests/unit/storage/test_migration_engine.py::test_changed_applied_migration_checksum_fails_closed` — 前置：所有 task predecessor 已合并且 7.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Open the local control database with explicit transaction semantics and apply an injected tuple of closed migrations in order, atomically, idempotently, and fail-closed on checksum drift without knowing any application-domain schema.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/storage/test_run_repository.py::test_same_wait_decision_can_win_only_once` — 前置：所有 task predecessor 已合并且 7.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Apply the closed Run/wait transition matrix atomically so exactly one correctly bound wait decision can win.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/unit/storage/test_idempotency.py::test_event_id_reuse_with_different_request_is_conflict` — 前置：所有 task predecessor 已合并且 7.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Return the first result for an identical event request and reject reuse of the same event id for different request bytes without performing domain mutation.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (7.A): `python -m pytest -q tests/unit/storage/test_migration_engine.py::test_changed_applied_migration_checksum_fails_closed`
- Domain (7.A): `python -m pytest -q tests/unit/storage/test_connection.py tests/unit/storage/test_migration_engine.py`
- Expected (7.A): `0`
- Target (7.B): `python -m pytest -q tests/unit/storage/test_run_repository.py::test_same_wait_decision_can_win_only_once`
- Schema (7.B): `python -m pytest -q tests/unit/storage/test_run_wait_migration.py::test_run_wait_migration_has_exact_schema`
- Domain (7.B): `python -m pytest -q tests/unit/storage/test_run_wait_migration.py tests/unit/storage/test_run_repository.py tests/unit/runs/test_lifecycle.py`
- Expected (7.B): `0`
- Target (7.C): `python -m pytest -q tests/unit/storage/test_idempotency.py::test_event_id_reuse_with_different_request_is_conflict`
- Schema (7.C): `python -m pytest -q tests/unit/storage/test_idempotency_migration.py::test_idempotency_migration_has_exact_schema`
- Domain (7.C): `python -m pytest -q tests/unit/storage/test_idempotency_migration.py tests/unit/storage/test_idempotency.py`
- Expected (7.C): `0`

**Review focus:**
- SPEC (7.A): Spec compliance review checks Task 7.A's Goal, Milestone 7's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent domain-independent migration engine contract.
- Quality (7.A): Code quality review checks transaction identity, foreign-key/connection flags, strict ordering, batch rollback, replay idempotency, checksum history, descriptor closure, and zero domain-schema knowledge.
- SPEC (7.B): Spec compliance review checks Task 7.B's Goal, Milestone 7's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent Run/wait transactional lifecycle contract.
- Quality (7.B): Code quality review checks exact v0001 schema, transaction-bound locking, one-winner concurrency, transition-table exhaustiveness, expiry/time binding, rollback, and prohibited-column absence.
- SPEC (7.C): Spec compliance review checks Task 7.C's Goal, Milestone 7's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent transaction-bound idempotency ledger contract.
- Quality (7.C): Code quality review checks exact v0002 schema, transaction participation, request/result digest binding, replay purity, conflict non-mutation, rollback, and concurrency determinism.

**Done:** legacy steps 7.A, 7.B, 7.C 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T07.2: Complete V1 Migration Registry

**Status:** Not started
**Work package:** WP07-REGISTRY
**Legacy steps:** 7.D
**Goal:** Compose the exact immutable domain migration constants into the sole complete v1 registry and, through a test-only expected owner map, fail closed when any required migration or per-version/final SQLite table ownership is missing, duplicated, introduced by the wrong version, early, late, reordered, unexpected, or checksum-drifted.
**SPEC contracts:** SPEC §4.2.1; §4.2.7; §4.7 audit ordering; §5.2; §5.4; §5.6; §7 complete data model and storage split; §10.1 AC-16, AC-21, AC-27, AC-28.
**Files:** `Create: src/vespercode/storage/migrations/registry.py`; `Test: tests/unit/storage/test_migration_registry.py`
**Depends:** T07.1, T14.1, T15.2, T22.1, T23.1, T24.1, T25.1, T25.2, T26.1, T26.2

**TDD contracts:**
1. `tests/unit/storage/test_migration_registry.py::test_registry_rejects_missing_required_domain_migration` — 前置：所有 task predecessor 已合并且 7.D 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Compose the exact immutable domain migration constants into the sole complete v1 registry and, through a test-only expected owner map, fail closed when any required migration or per-version/final SQLite table ownership is missing, duplicated, introduced by the wrong version, early, late, reordered, unexpected, or checksum-drifted.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/storage/test_migration_registry.py::test_registry_rejects_missing_required_domain_migration` 的 Domain 边界矩阵 — 在首个 GREEN 后逐项加入稳定错误、并发/重放或真实适配边界；每项先 RED 再最小 GREEN。
3. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (7.D): `python -m pytest -q tests/unit/storage/test_migration_registry.py::test_registry_rejects_missing_required_domain_migration`
- Schema owner (7.D): `python -m pytest -q tests/unit/storage/test_migration_registry.py::test_registry_prefixes_match_exact_schema_owner_map`
- Domain (7.D): `python -m pytest -q tests/unit/storage/test_migration_registry.py tests/unit/storage/test_migration_engine.py`
- Expected (7.D, 1): `0`
- Expected (7.D, 2): `schema_migrations`

**Review focus:**
- SPEC (7.D): Spec compliance review checks Task 7.D's Goal, Milestone 7's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent complete v1 migration registry contract.
- Quality (7.D): Code quality review checks exact producer set, versions/names/order/checksums, composition immutability, test-only owner-map isolation, prefix introspection purity, and final 18-table agreement.

**Done:** legacy steps 7.D 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T08.1: Strict Run Request and Ordered Admission Coordinator

**Status:** Not started
**Work package:** WP08
**Legacy steps:** 8.A, 8.B
**Goal:** Reject every invalid or ambiguous run request before a run id exists, and create one `CREATED` Run with an immutable `RunConfigSnapshotV1` for valid input.；Move one existing `CREATED` Run through the exact PREFLIGHT port order while every failure prevents all later calls and forbidden side effects.
**SPEC contracts:** SPEC §4.1 FR-ADM in full; §4.2.7 lifecycle entry; §5.1; §5.3; §10.1 AC-15, AC-16, AC-21, AC-26, AC-28, AC-30, AC-31.
**Files:** `Create: src/vespercode/runs/request.py`; `Test: tests/unit/runs/test_request.py`; `Create: src/vespercode/runs/admission.py`; `Test: tests/unit/runs/test_admission.py`; `Test: tests/unit/runs/test_admission_order.py`
**Depends:** T06.1, T07.1

**TDD contracts:**
1. `tests/unit/runs/test_request.py::test_custom_base_url_is_rejected_without_creating_a_run` — 前置：所有 task predecessor 已合并且 8.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Reject every invalid or ambiguous run request before a run id exists, and create one `CREATED` Run with an immutable `RunConfigSnapshotV1` for valid input.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/runs/test_admission_order.py::test_snapshot_precheck_failure_calls_no_later_admission_port` — 前置：所有 task predecessor 已合并且 8.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Move one existing `CREATED` Run through the exact PREFLIGHT port order while every failure prevents all later calls and forbidden side effects.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (8.A): `python -m pytest -q tests/unit/runs/test_request.py::test_custom_base_url_is_rejected_without_creating_a_run`
- Domain (8.A): `python -m pytest -q tests/unit/runs/test_request.py`
- Expected (8.A): invalid requests produce stable reasons and zero inserts; valid permutations bind one identical frozen config and create exactly one Run.
- Target (8.B): `python -m pytest -q tests/unit/runs/test_admission_order.py::test_snapshot_precheck_failure_calls_no_later_admission_port`
- Domain (8.B): `python -m pytest -q tests/unit/runs/test_admission.py tests/unit/runs/test_admission_order.py`
- Expected (8.B): every failure-point trace is an exact prefix of the required order; rejected PREFLIGHT performs no Agent action, LLM call, execution, install, image build, or workspace write.

**Review focus:**
- SPEC (8.A): Spec compliance review checks Task 8.A's Goal, Milestone 8's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent run-request admission/config freeze contract.
- Quality (8.A): Code quality review checks closed-field validation, profile identity binding, immutable config freezing, zero-side-effect rejection, one-insert atomicity, and stable invalid reasons.
- SPEC (8.B): Spec compliance review checks Task 8.B's Goal, Milestone 8's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent ordered PREFLIGHT coordinator contract.
- Quality (8.B): Code quality review checks exact port ordering, short-circuit traces, lifecycle atomicity, dependency injection, forbidden-effect absence, and no concrete adapter imports.

**Done:** legacy steps 8.A, 8.B 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T09.1: Production Win32 Workspace Identity and Git Preflight

**Status:** Not started
**Work package:** WP09
**Legacy steps:** 9.A, 9.B, 9.C, 9.D
**Goal:** Resolve one handle-derived workspace identity and reject every unprovable, aliased, reparse, ADS, hard-link, kind, or ACL final object.；Give one process exclusive ownership of a workspace-identity-derived named mutex until explicit lease release.；Freeze and validate the exact Git config/index/HEAD/worktree/ignore/attribute state before Snapshot creation.；Authorize an existing object or create parent only when lexical, final-object, root-ancestry, alias, sensitive-path, and editable-policy facts all match.
**SPEC contracts:** SPEC §0.1 path identity; §1.4.1 Git rules; §1.4.2–§1.4.4; §4.1 behavior 6–10; §4.3 behavior 4–5; §4.6 ACL/lease requirements; §5.5; §10.1 AC-01, AC-15, AC-21, AC-26, AC-29, AC-31.
**Files:** `Create: src/vespercode/workspace/identity_win32.py`; `Create: src/vespercode/workspace/object_win32.py`; `Test: tests/integration/windows/test_workspace_identity.py`; `Test: tests/integration/windows/test_workspace_objects.py`; `Create: src/vespercode/workspace/mutex_win32.py`; `Test: tests/integration/windows/test_named_mutex.py`; `Create: src/vespercode/workspace/git_preflight.py`; `Test: tests/unit/workspace/test_git_preflight.py`; `Test: tests/integration/windows/test_git_preflight.py`; `Create: src/vespercode/workspace/path_guard.py`; `Test: tests/unit/workspace/test_path_guard.py`
**Depends:** T01.2, T05.1, T07.1, T08.1

**TDD contracts:**
1. `tests/integration/windows/test_workspace_objects.py::test_reparse_final_object_is_rejected` — 前置：所有 task predecessor 已合并且 9.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Resolve one handle-derived workspace identity and reject every unprovable, aliased, reparse, ADS, hard-link, kind, or ACL final object.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/integration/windows/test_named_mutex.py::test_second_process_cannot_acquire_same_workspace_mutex` — 前置：所有 task predecessor 已合并且 9.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Give one process exclusive ownership of a workspace-identity-derived named mutex until explicit lease release.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/unit/workspace/test_git_preflight.py::test_tracked_file_with_skip_worktree_is_rejected_before_snapshot` — 前置：所有 task predecessor 已合并且 9.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Freeze and validate the exact Git config/index/HEAD/worktree/ignore/attribute state before Snapshot creation.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. `tests/unit/workspace/test_path_guard.py::test_create_rejects_case_alias_of_existing_path` — 前置：所有 task predecessor 已合并且 9.D 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Authorize an existing object or create parent only when lexical, final-object, root-ancestry, alias, sensitive-path, and editable-policy facts all match.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
5. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (9.A): `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_workspace_objects.py::test_reparse_final_object_is_rejected`
- Domain (9.A): `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_workspace_identity.py tests/integration/windows/test_workspace_objects.py`
- Expected (9.A): `0`
- Target (9.B): `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_named_mutex.py::test_second_process_cannot_acquire_same_workspace_mutex`
- Domain (9.B): `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_named_mutex.py`
- Expected (9.B): `0`
- Target (9.C): `python -m pytest -q tests/unit/workspace/test_git_preflight.py::test_tracked_file_with_skip_worktree_is_rejected_before_snapshot`
- Domain (9.C): `python -m pytest -q tests/unit/workspace/test_git_preflight.py`
- Windows (9.C): `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_git_preflight.py`
- Expected (9.C): `0`
- Target (9.D): `python -m pytest -q tests/unit/workspace/test_path_guard.py::test_create_rejects_case_alias_of_existing_path`
- Domain (9.D): `python -m pytest -q tests/unit/workspace/test_path_guard.py`
- Expected (9.D): `0`

**Review focus:**
- SPEC (9.A): Spec compliance review checks Task 9.A's Goal, Milestone 9's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent Win32 workspace object identity contract.
- Quality (9.A): Code quality review checks handle lifetime, final-versus-lexical identity, ancestry proof, object-kind/reparse/ADS/link/ACL coverage, stable Win32 error handling, and cleanup.
- SPEC (9.B): Spec compliance review checks Task 9.B's Goal, Milestone 9's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent Win32 workspace mutex lease contract.
- Quality (9.B): Code quality review checks deterministic mutex naming, cross-process exclusivity, timeout boundaries, lease identity, idempotent cleanup/release, abandoned-handle behavior, and error propagation.
- SPEC (9.C): Spec compliance review checks Task 9.C's Goal, Milestone 9's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent sealed Git preflight contract.
- Quality (9.C): Code quality review checks shell-free argv, closed environment/config, complete Git state sealing, non-secret evidence, skip-worktree/conversion handling, stable errors, and zero writes.
- SPEC (9.D): Spec compliance review checks Task 9.D's Goal, Milestone 9's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent handle-bound path authorization contract.
- Quality (9.D): Code quality review checks handle/root binding, ancestry and kind proof, case/alias collisions, sensitive/editable precedence, create-parent safety, stable failures, and no string fallback.

**Done:** legacy steps 9.A, 9.B, 9.C, 9.D 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T10.1: Shared Supported-text Classification

**Status:** Not started
**Work package:** WP10-TEXT
**Legacy steps:** 10.B
**Goal:** Classify raw bytes once for all file tools and candidate operations under the exact UTF-8/newline rules.
**SPEC contracts:** SPEC §1.4.1 `StaticProjectProfileCheckV1`; §1.4.4; §4.1 behavior 8–10; §4.2.2 `SupportedTextFileV1`; §4.3 behavior 1–3; §7 Snapshot/List entry rows; §10.1 AC-04, AC-15, AC-17, AC-18, AC-26, AC-31.
**Files:** `Create: src/vespercode/trees/text_classifier.py`; `Test: tests/unit/trees/test_text_classifier.py`
**Depends:** T05.1

**TDD contracts:**
1. `tests/unit/trees/test_text_classifier.py::test_mixed_newlines_are_non_text` — 前置：所有 task predecessor 已合并且 10.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Classify raw bytes once for all file tools and candidate operations under the exact UTF-8/newline rules.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/trees/test_text_classifier.py::test_mixed_newlines_are_non_text` 的 Domain 边界矩阵 — 在首个 GREEN 后逐项加入稳定错误、并发/重放或真实适配边界；每项先 RED 再最小 GREEN。
3. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (10.B): `python -m pytest -q tests/unit/trees/test_text_classifier.py::test_mixed_newlines_are_non_text`
- Domain (10.B): `python -m pytest -q tests/unit/trees/test_text_classifier.py`
- Expected (10.B): UTF-8/BOM/LF/CRLF/final-newline cases classify exactly and invalid/binary/mixed cases remain valid non-text entries.

**Review focus:**
- SPEC (10.B): Spec compliance review checks Task 10.B's Goal, Milestone 10's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent supported-text classifier contract.
- Quality (10.B): Code quality review checks byte-level purity, BOM/encoding closure, newline exclusivity, final-newline enforcement, deterministic non-text outcomes, and zero normalization/I/O.

**Done:** legacy steps 10.B 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T10.2: Content Objects and Snapshot Construction

**Status:** Not started
**Work package:** WP10-SNAPSHOT
**Legacy steps:** 10.A, 10.C
**Goal:** Store and retrieve exact immutable file bytes by verified raw SHA-256 content reference.；Construct the Run's sole immutable SnapshotTree from sealed Git-preflight bytes and verify all content, ordering, identity, and policy bindings.
**SPEC contracts:** SPEC §1.4.1 `StaticProjectProfileCheckV1`; §1.4.4; §4.1 behavior 8–10; §4.2.2 `SupportedTextFileV1`; §4.3 behavior 1–3; §7 Snapshot/List entry rows; §10.1 AC-04, AC-15, AC-17, AC-18, AC-26, AC-31.
**Files:** `Create: src/vespercode/trees/content_store.py`; `Test: tests/unit/trees/test_content_store.py`; `Create: src/vespercode/trees/snapshot.py`; `Test: tests/unit/trees/test_snapshot.py`; `Test: tests/integration/windows/test_snapshot_from_preflight.py`
**Depends:** T05.1, T09.1, T10.1

**TDD contracts:**
1. `tests/unit/trees/test_content_store.py::test_get_rejects_bytes_whose_digest_drifted` — 前置：所有 task predecessor 已合并且 10.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Store and retrieve exact immutable file bytes by verified raw SHA-256 content reference.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/integration/windows/test_snapshot_from_preflight.py::test_snapshot_rejects_preflight_object_identity_drift` — 前置：所有 task predecessor 已合并且 10.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Construct the Run's sole immutable SnapshotTree from sealed Git-preflight bytes and verify all content, ordering, identity, and policy bindings.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (10.A): `python -m pytest -q tests/unit/trees/test_content_store.py::test_get_rejects_bytes_whose_digest_drifted`
- Domain (10.A): `python -m pytest -q tests/unit/trees/test_content_store.py`
- Expected (10.A): put/get/dedup/integrity cases pass and corruption fails closed.
- Target (10.C): `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_snapshot_from_preflight.py::test_snapshot_rejects_preflight_object_identity_drift`
- Domain (10.C): `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_snapshot_from_preflight.py`
- Expected (10.C): exact sealed preflight builds one verified deterministic Snapshot and every size/order/content/object/policy drift rejects.

**Review focus:**
- SPEC (10.A): Spec compliance review checks Task 10.A's Goal, Milestone 10's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent immutable content-object store contract.
- Quality (10.A): Code quality review checks raw-byte preservation, digest/size verification, dedup identity, atomic object writes, corruption/missing-object errors, immutability, and no workspace-path reads.
- SPEC (10.C): Spec compliance review checks Task 10.C's Goal, Milestone 10's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent sealed immutable Snapshot contract.
- Quality (10.C): Code quality review checks sealed-input provenance, deterministic entry ordering/root digest, object/content/policy identity binding, integrity fail-closed behavior, and zero mutable-workspace rereads.

**Done:** legacy steps 10.A, 10.C 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T11.1: Read-only List, Read, and Literal Search Tools

**Status:** Not started
**Work package:** WP11
**Legacy steps:** 11.A, 11.B
**Goal:** Freeze the common file action/result contracts and implement bounded text reads that can observe only the bound immutable tree.；Implement stable List/Search discovery whose distinct canonical cursors reproduce unpaged results exactly and fail closed on tampering or tree drift.
**SPEC contracts:** SPEC §4.2.2 file actions/results and `SupportedTextFileV1`; §4.2.8; §4.3 input/behavior 2–5; §5.1; §7 `RepositoryLocationV1`/`ListFilesEntryV1`; §10.1 AC-01, AC-17, AC-26, AC-31; §10.3 offline core tests.
**Files:** `Create: src/vespercode/tools/file_actions.py`; `Create: src/vespercode/tools/file_results.py`; `Create: src/vespercode/tools/read_file.py`; `Test: tests/unit/tools/test_file_actions.py`; `Test: tests/unit/tools/test_read_file.py`; `Create: src/vespercode/tools/list_files.py`; `Create: src/vespercode/tools/search_text.py`; `Test: tests/unit/tools/test_list_files.py`; `Test: tests/unit/tools/test_search_text.py`
**Depends:** T05.1, T10.2

**TDD contracts:**
1. `tests/unit/tools/test_read_file.py::test_read_uses_only_bound_snapshot_bytes` — 前置：所有 task predecessor 已合并且 11.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Freeze the common file action/result contracts and implement bounded text reads that can observe only the bound immutable tree.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/tools/test_list_files.py::test_paged_discovery_equals_unpaged_without_duplicates` — 前置：所有 task predecessor 已合并且 11.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Implement stable List/Search discovery whose distinct canonical cursors reproduce unpaged results exactly and fail closed on tampering or tree drift.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (11.A): `python -m pytest -q tests/unit/tools/test_read_file.py::test_read_uses_only_bound_snapshot_bytes`
- Domain (11.A): `python -m pytest -q tests/unit/tools/test_file_actions.py tests/unit/tools/test_read_file.py`
- Expected (11.A): closed schemas reject unknown fields and Read never observes mutable workspace state.
- Target (11.B): `python -m pytest -q tests/unit/tools/test_list_files.py::test_paged_discovery_equals_unpaged_without_duplicates`
- Domain (11.B): `python -m pytest -q tests/unit/tools/test_list_files.py tests/unit/tools/test_search_text.py`
- Expected (11.B): paged/unpaged equality, stable ordering, non-text accounting, and tampered/stale zero-payload failures all pass.

**Review focus:**
- SPEC (11.A): Spec compliance review checks Task 11.A's Goal, Milestone 11's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent bounded immutable-tree read contract.
- Quality (11.A): Code quality review checks closed action/result schemas, tree binding, text metadata preservation, line/byte bounds, deterministic truncation, zero filesystem reads, and stable errors.
- SPEC (11.B): Spec compliance review checks Task 11.B's Goal, Milestone 11's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent stable paged List/Search contract.
- Quality (11.B): Code quality review checks stable ordering, paged/unpaged equivalence, distinct cursor schemas, tree/query/position/self binding, zero-payload failures, non-text accounting, and purity.

**Done:** legacy steps 11.A, 11.B 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T12.1: CandidateTree, Strict Patch Engine, and FinalDiffV1

**Status:** Not started
**Work package:** WP12
**Legacy steps:** 12.A, 12.B, 12.C, 12.D
**Goal:** Parse the complete no-BOM UTF-8/LF `UNIFIED_DIFF_V1` grammar or return one closed parse failure without deriving candidate state.；Derive an immutable content-addressed child tree from complete staged postimages while leaving its parent tree unchanged.；Apply one parsed patch exactly against the named base candidate and publish one validated revision or no revision.；Recompute the complete Snapshot-to-candidate structured diff and bind its exact digest with Snapshot and CandidateTree digests.
**SPEC contracts:** SPEC §1.4.2–§1.4.4; §4.2.2 `ApplyCandidatePatchAction`; §4.3 in full; §4.4.1 path-policy binding; §4.5 pre-check policy revalidation; §7 Candidate/FinalDiff rows; §10.1 AC-01, AC-04, AC-07, AC-18, AC-26, AC-31.
**Files:** `Create: src/vespercode/candidate/unified_diff.py`; `Test: tests/unit/candidate/test_unified_diff.py`; `Create: src/vespercode/trees/candidate.py`; `Test: tests/unit/trees/test_candidate.py`; `Create: src/vespercode/candidate/patch_engine.py`; `Test: tests/unit/candidate/test_patch_engine.py`; `Create: src/vespercode/candidate/final_diff.py`; `Create: src/vespercode/candidate/identity.py`; `Test: tests/unit/candidate/test_final_diff.py`; `Test: tests/unit/candidate/test_identity.py`
**Depends:** T06.1, T09.1, T10.2

**TDD contracts:**
1. `tests/unit/candidate/test_unified_diff.py::test_trailing_unparsed_patch_bytes_are_rejected` — 前置：所有 task predecessor 已合并且 12.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Parse the complete no-BOM UTF-8/LF `UNIFIED_DIFF_V1` grammar or return one closed parse failure without deriving candidate state.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/trees/test_candidate.py::test_child_revision_does_not_mutate_parent` — 前置：所有 task predecessor 已合并且 12.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Derive an immutable content-addressed child tree from complete staged postimages while leaving its parent tree unchanged.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/unit/candidate/test_patch_engine.py::test_mixed_legal_and_noneditable_patch_has_no_candidate_side_effect` — 前置：所有 task predecessor 已合并且 12.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Apply one parsed patch exactly against the named base candidate and publish one validated revision or no revision.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. `tests/unit/candidate/test_identity.py::test_candidate_identity_ignores_revision_metadata` — 前置：所有 task predecessor 已合并且 12.D 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Recompute the complete Snapshot-to-candidate structured diff and bind its exact digest with Snapshot and CandidateTree digests.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
5. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (12.A): `python -m pytest -q tests/unit/candidate/test_unified_diff.py::test_trailing_unparsed_patch_bytes_are_rejected`
- Domain (12.A): `python -m pytest -q tests/unit/candidate/test_unified_diff.py`
- Expected (12.A): `0`
- Target (12.B): `python -m pytest -q tests/unit/trees/test_candidate.py::test_child_revision_does_not_mutate_parent`
- Domain (12.B): `python -m pytest -q tests/unit/trees/test_candidate.py`
- Expected (12.B): `0`
- Target (12.C): `python -m pytest -q tests/unit/candidate/test_patch_engine.py::test_mixed_legal_and_noneditable_patch_has_no_candidate_side_effect`
- Domain (12.C): `python -m pytest -q tests/unit/candidate/test_patch_engine.py`
- Expected (12.C): `0`
- Target (12.D): `python -m pytest -q tests/unit/candidate/test_identity.py::test_candidate_identity_ignores_revision_metadata`
- Domain (12.D): `python -m pytest -q tests/unit/candidate/test_final_diff.py tests/unit/candidate/test_identity.py`
- Expected (12.D): `0`

**Review focus:**
- SPEC (12.A): Spec compliance review checks Task 12.A's Goal, Milestone 12's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent strict unified-diff parser contract.
- Quality (12.A): Code quality review checks total-input consumption, grammar/range exhaustiveness, deterministic parse errors, prohibited-form closure, entry uniqueness, UTF-8/LF rules, and side-effect freedom.
- SPEC (12.B): Spec compliance review checks Task 12.B's Goal, Milestone 12's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent immutable Candidate overlay contract.
- Quality (12.B): Code quality review checks structural immutability, parent independence, overlay lookup precedence, deterministic ordering/digest, content-ref integrity, and absence of publication side effects.
- SPEC (12.C): Spec compliance review checks Task 12.C's Goal, Milestone 12's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent atomic exact patch application contract.
- Quality (12.C): Code quality review checks all-or-nothing staging, exact-hunk/base binding, authorization precedence, text/limit/collision validation, zero-publication failures, and deterministic errors.
- SPEC (12.D): Spec compliance review checks Task 12.D's Goal, Milestone 12's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent FinalDiff and Candidate identity contract.
- Quality (12.D): Code quality review checks complete diff recomputation, preimage/postimage accuracy, byte accounting, stable ordering, policy/tree consistency, three-root digest binding, and metadata independence.

**Done:** legacy steps 12.A, 12.B, 12.C, 12.D 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T13.1: Versioned PolicyEngine and Non-overridable DENY

**Status:** Not started
**Work package:** WP13
**Legacy steps:** 13
**Goal:** Centralize deterministic `ALLOW/ASK/DENY` evaluation so unsafe capabilities and non-editable candidate changes cannot be approved, prompted around, or dispatched.
**SPEC contracts:** SPEC §1.4.2–§1.4.3; §4.2.3; §4.3 error priority; §4.4.1; §5.2; §5.5; §10.1 AC-01, AC-02, AC-04, AC-06, AC-26, AC-31; §10.4 mechanism demo items 1–4.
**Files:** `Create: src/vespercode/governance/policy.py`; `Test: tests/unit/governance/test_policy.py`; `Test: tests/unit/governance/test_policy_precedence.py`
**Depends:** T05.1, T06.1, T12.1

**TDD contracts:**
1. `tests/unit/governance/test_policy.py::test_user_approval_cannot_override_noneditable_path_deny` — 前置：所有 task predecessor 已合并且 13 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Centralize deterministic `ALLOW/ASK/DENY` evaluation so unsafe capabilities and non-editable candidate changes cannot be approved, prompted around, or dispatched.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/governance/test_policy.py::test_user_approval_cannot_override_noneditable_path_deny` 的 Domain 边界矩阵 — 在首个 GREEN 后逐项加入稳定错误、并发/重放或真实适配边界；每项先 RED 再最小 GREEN。
3. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (13): `python -m pytest -q tests/unit/governance/test_policy.py::test_user_approval_cannot_override_noneditable_path_deny`
- Domain (13): `python -m pytest -q tests/unit/governance/test_policy.py tests/unit/governance/test_policy_precedence.py`
- Full (13): `python -m pytest -q`
- Expected (13): all action/phase decisions, hard-deny sources, reason priorities, cache keys, and policy-digest propagation pass offline.

**Review focus:**
- SPEC (13): Spec compliance review compares the complete rule table with §4.4.1 and proves approval, Grant, config, prompt, and repository content cannot widen it.
- Quality (13): Code quality review checks rule exhaustiveness, pure evaluation, stable precedence, digest/cache keys, and unknown-action fail-closed behavior.

**Done:** legacy steps 13 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T14.1: FinalWritebackSubject and One-time Approval

**Status:** Not started
**Work package:** WP14
**Legacy steps:** 14.A, 14.B, 14.C
**Goal:** Build the immutable final-writeback subject/binding from exact current candidate, policy, validation, Run, and expiry facts.；Apply APPROVE/REJECT/expiry/stale decisions atomically to the exact final-writeback wait with idempotent event replay.；Consume one exact current PENDING final-writeback approval at most once under concurrent/replayed attempts.
**SPEC contracts:** SPEC §4.2.7 final-writeback wait; §4.4.1–§4.4.2; §4.6 writeback preconditions; §5.2; §7 subject/approval rows; §10.1 AC-02, AC-03, AC-06, AC-07, AC-27, AC-31.
**Files:** `Create: src/vespercode/governance/writeback_subject.py`; `Test: tests/unit/governance/test_writeback_subject.py`; `Create: src/vespercode/storage/migrations/v0010_writeback_approvals.py`; `Create: src/vespercode/governance/writeback_decision.py`; `Test: tests/unit/storage/test_writeback_approvals_migration.py`; `Test: tests/unit/governance/test_writeback_decision.py`; `Create: src/vespercode/governance/writeback_approval.py`; `Test: tests/unit/governance/test_writeback_approval.py`; `Test: tests/unit/governance/test_writeback_approval_race.py`
**Depends:** T04.2, T05.1, T07.1, T12.1, T13.1, T20.2, T21.1, T25.2

**TDD contracts:**
1. `tests/unit/governance/test_writeback_subject.py::test_subject_digest_changes_when_final_diff_changes` — 前置：所有 task predecessor 已合并且 14.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Build the immutable final-writeback subject/binding from exact current candidate, policy, validation, Run, and expiry facts.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/governance/test_writeback_decision.py::test_expired_wait_cannot_create_pending_approval` — 前置：所有 task predecessor 已合并且 14.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Apply APPROVE/REJECT/expiry/stale decisions atomically to the exact final-writeback wait with idempotent event replay.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/unit/governance/test_writeback_approval_race.py::test_concurrent_consumers_get_exactly_one_success` — 前置：所有 task predecessor 已合并且 14.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Consume one exact current PENDING final-writeback approval at most once under concurrent/replayed attempts.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (14.A): `python -m pytest -q tests/unit/governance/test_writeback_subject.py::test_subject_digest_changes_when_final_diff_changes`
- Domain (14.A): `python -m pytest -q tests/unit/governance/test_writeback_subject.py`
- Expected (14.A): every bound fact affects the digest and mutable/user-supplied decision facts cannot enter the subject.
- Target (14.B): `python -m pytest -q tests/unit/governance/test_writeback_decision.py::test_expired_wait_cannot_create_pending_approval`
- Schema (14.B): `python -m pytest -q tests/unit/storage/test_writeback_approvals_migration.py::test_writeback_approval_migration_has_exact_schema`
- Domain (14.B): `python -m pytest -q tests/unit/storage/test_writeback_approvals_migration.py tests/unit/governance/test_writeback_decision.py`
- Expected (14.B): exact v0010 schema plus approve/reject/expire/stale/replay/conflict cases are atomic and only exact current APPROVE creates one PENDING approval.
- Target (14.C): `python -m pytest -q tests/unit/governance/test_writeback_approval_race.py::test_concurrent_consumers_get_exactly_one_success`
- Domain (14.C): `python -m pytest -q tests/unit/governance/test_writeback_approval.py tests/unit/governance/test_writeback_approval_race.py`
- Expected (14.C): exactly one matching consumer succeeds and stale/expired/mismatched/replayed attempts create no second consumption.

**Review focus:**
- SPEC (14.A): Spec compliance review checks Task 14.A's Goal, Milestone 14's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent exact final-writeback subject contract.
- Quality (14.A): Code quality review checks complete immutable fact binding, canonical digest determinism, FinalDiff/policy/validation identity sensitivity, expiry typing, mutable-decision exclusion, and side-effect freedom.
- SPEC (14.B): Spec compliance review checks Task 14.B's Goal, Milestone 14's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent atomic writeback decision lifecycle contract.
- Quality (14.B): Code quality review checks exact v0010 schema, wait locking, current-subject reload, clock ownership, approval uniqueness, replay/conflict atomicity, stale identity rejection, and no DENY override.
- SPEC (14.C): Spec compliance review checks Task 14.C's Goal, Milestone 14's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent consume-once writeback approval contract.
- Quality (14.C): Code quality review checks transaction isolation, compare-and-consume atomicity, exact subject/candidate binding, expiry/replay handling, one-winner concurrency, and zero workspace side effects.

**Done:** legacy steps 14.A, 14.B, 14.C 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T15.1: Disclosure Sources, Scope, and Grant Subjects

**Status:** Not started
**Work package:** WP15
**Legacy steps:** 15.A, 15.B, 15.C
**Goal:** Validate exact request message/segment source categories, paths, content digests, indexes, and byte counts before subject construction.；Canonicalize disclosure scopes and match ROOT/FILE/DIRECTORY only at exact path-segment boundaries.；Build the immutable disclosure Grant subject from validated sources, canonical scopes/categories, frozen profile, endpoint, serializer, and expiry.
**SPEC contracts:** SPEC §4.2.7 disclosure wait; §4.4.3–§4.4.4 source/scope/budget contracts; §5.1–§5.2; §5.5–§5.6; §7 disclosure rows; §10.1 AC-13, AC-26, AC-27, AC-28.
**Files:** `Create: src/vespercode/governance/request_sources.py`; `Test: tests/unit/governance/test_request_sources.py`; `Create: src/vespercode/governance/disclosure_scope.py`; `Test: tests/unit/governance/test_disclosure_scope.py`; `Create: src/vespercode/governance/disclosure_subject.py`; `Test: tests/unit/governance/test_disclosure_subject.py`
**Depends:** T04.2, T05.1, T06.1

**TDD contracts:**
1. `tests/unit/governance/test_request_sources.py::test_file_segment_requires_canonical_path` — 前置：所有 task predecessor 已合并且 15.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Validate exact request message/segment source categories, paths, content digests, indexes, and byte counts before subject construction.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/governance/test_disclosure_scope.py::test_directory_scope_does_not_match_string_prefix_sibling` — 前置：所有 task predecessor 已合并且 15.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Canonicalize disclosure scopes and match ROOT/FILE/DIRECTORY only at exact path-segment boundaries.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/unit/governance/test_disclosure_subject.py::test_subject_uses_frozen_endpoint_not_request_url` — 前置：所有 task predecessor 已合并且 15.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Build the immutable disclosure Grant subject from validated sources, canonical scopes/categories, frozen profile, endpoint, serializer, and expiry.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (15.A): `python -m pytest -q tests/unit/governance/test_request_sources.py::test_file_segment_requires_canonical_path`
- Domain (15.A): `python -m pytest -q tests/unit/governance/test_request_sources.py`
- Expected (15.A): exact source/path rules and content identities pass; missing/duplicate/mismatched segments reject before mutation.
- Target (15.B): `python -m pytest -q tests/unit/governance/test_disclosure_scope.py::test_directory_scope_does_not_match_string_prefix_sibling`
- Domain (15.B): `python -m pytest -q tests/unit/governance/test_disclosure_scope.py`
- Expected (15.B): ROOT/FILE/DIRECTORY semantics, alias rejection, ordering, duplicate, and empty-scope cases pass exactly.
- Target (15.C): `python -m pytest -q tests/unit/governance/test_disclosure_subject.py::test_subject_uses_frozen_endpoint_not_request_url`
- Domain (15.C): `python -m pytest -q tests/unit/governance/test_disclosure_subject.py`
- Expected (15.C): every immutable authorization fact is bound and all endpoint/model/source/scope/expiry overrides reject.

**Review focus:**
- SPEC (15.A): Spec compliance review checks Task 15.A's Goal, Milestone 15's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent request source/segment validation contract.
- Quality (15.A): Code quality review checks category closure, canonical path requirements, segment indexing/order, digest/byte-count binding, duplicate detection, deterministic projection, and mutation-free rejection.
- SPEC (15.B): Spec compliance review checks Task 15.B's Goal, Milestone 15's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent canonical disclosure scope matching contract.
- Quality (15.B): Code quality review checks deterministic scope order, segment-boundary correctness, ROOT/FILE/DIRECTORY closure, alias/duplicate handling, empty-scope semantics, and pure evaluation.
- SPEC (15.C): Spec compliance review checks Task 15.C's Goal, Milestone 15's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent immutable disclosure Grant subject contract.
- Quality (15.C): Code quality review checks complete source/scope/profile/endpoint/serializer/expiry binding, trusted endpoint use, canonical digest determinism, override rejection, and side-effect freedom.

**Done:** legacy steps 15.A, 15.B, 15.C 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T15.2: Disclosure Decisions, Revocation, and Authorization Ledger

**Status:** Not started
**Work package:** WP15
**Legacy steps:** 15.D, 15.F, 15.E
**Goal:** Atomically approve/reject/expire/stale/replay the exact disclosure wait and create at most one matching active Grant.；Atomically revoke only the exact matching active disclosure Grant, with idempotent replay and no mutation for stale or mismatched subjects.；Revalidate one prepared request against the current active Grant and atomically charge cumulative bytes exactly once under races.
**SPEC contracts:** SPEC §4.2.7 disclosure wait; §4.4.3–§4.4.4 source/scope/budget contracts; §5.1–§5.2; §5.5–§5.6; §7 disclosure rows; §10.1 AC-13, AC-26, AC-27, AC-28.
**Files:** `Create: src/vespercode/storage/migrations/v0003_disclosure_grants.py`; `Create: src/vespercode/governance/disclosure_decision.py`; `Test: tests/unit/storage/test_disclosure_grants_migration.py`; `Test: tests/unit/governance/test_disclosure_decision.py`; `Create: src/vespercode/governance/disclosure_revocation.py`; `Test: tests/unit/governance/test_disclosure_revocation.py`
**Depends:** T04.2, T05.1, T07.1, T15.1

**TDD contracts:**
1. `tests/unit/governance/test_disclosure_decision.py::test_expired_disclosure_wait_creates_no_grant` — 前置：所有 task predecessor 已合并且 15.D 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Atomically approve/reject/expire/stale/replay the exact disclosure wait and create at most one matching active Grant.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/governance/test_disclosure_revocation.py::test_revoke_rejects_mismatched_subject` — 前置：所有 task predecessor 已合并且 15.F 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Atomically revoke only the exact matching active disclosure Grant, with idempotent replay and no mutation for stale or mismatched subjects.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/unit/governance/test_disclosure_budget_race.py::test_two_requests_cannot_overdraw_one_grant` — 前置：所有 task predecessor 已合并且 15.E 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Revalidate one prepared request against the current active Grant and atomically charge cumulative bytes exactly once under races.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (15.D): `python -m pytest -q tests/unit/governance/test_disclosure_decision.py::test_expired_disclosure_wait_creates_no_grant`
- Schema (15.D): `python -m pytest -q tests/unit/storage/test_disclosure_grants_migration.py::test_disclosure_grant_migration_has_exact_schema`
- Domain (15.D): `python -m pytest -q tests/unit/storage/test_disclosure_grants_migration.py tests/unit/governance/test_disclosure_decision.py`
- Expected (15.D): exact v0003 schema plus approve/reject/expire/stale/replay cases are atomic and never create duplicate/invalid Grants.
- Target (15.F): `python -m pytest -q tests/unit/governance/test_disclosure_revocation.py::test_revoke_rejects_mismatched_subject`
- Domain (15.F): `python -m pytest -q tests/unit/governance/test_disclosure_revocation.py`
- Expected (15.F): `0`
- Target (15.E): `python -m pytest -q tests/unit/governance/test_disclosure_budget_race.py::test_two_requests_cannot_overdraw_one_grant`
- Schema (15.E): `python -m pytest -q tests/unit/storage/test_disclosure_authorizations_migration.py::test_disclosure_authorization_migration_has_exact_schema`
- Domain (15.E): `python -m pytest -q tests/unit/storage/test_disclosure_authorizations_migration.py tests/unit/governance/test_disclosure_ledger.py tests/unit/governance/test_disclosure_budget_race.py`
- Expected (15.E): exact v0004 schema; only exact authorized requests commit one charge; scope/expiry/revocation/budget/race failures charge zero.

**Review focus:**
- SPEC (15.D): Spec compliance review checks Task 15.D's Goal, Milestone 15's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent atomic disclosure Grant decision contract.
- Quality (15.D): Code quality review checks exact v0003 schema, wait/subject locking, active-Grant uniqueness, clock/expiry handling, idempotent replay/conflict, return transition, and zero invalid creation.
- SPEC (15.F): Spec compliance review checks Task 15.F's Goal, Milestone 15's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent exact disclosure Grant revocation contract.
- Quality (15.F): Code quality review checks transaction-bound subject/Run identity, active-state compare-and-set, idempotent replay, unrelated-Grant isolation, stable results, and no budget refund.
- SPEC (15.E): Spec compliance review checks Task 15.E's Goal, Milestone 15's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent transactional disclosure authorization ledger contract.
- Quality (15.E): Code quality review checks exact v0004 schema, immediate-transaction isolation, cumulative-byte arithmetic, one-winner budget races, fresh Grant/subject revalidation, body-free records, and zero-charge failures.

**Done:** legacy steps 15.D, 15.F, 15.E 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T16.1: Closed Prepared Requests and Mock/OpenAI Adapters

**Status:** Not started
**Work package:** WP16
**Legacy steps:** 16.A, 16.B
**Goal:** Build closed Mock/OpenAI prepared-request contracts and a deterministic Mock adapter with no provider, credential, Grant, authorization, or network behavior.；Serialize one authorized `OpenAIPreparedModelRequestV1` to the sole trusted endpoint and perform at most one non-retried transport call through a freshly bound adapter.
**SPEC contracts:** SPEC §4.2.1; §4.2.5; §4.2.8 LLM errors; §4.4.3–§4.4.4 prepared request/call sequence; §5.1–§5.2; §5.5; §7 LLM rows; §9 LLM choice; §10.1 AC-05, AC-13, AC-26, AC-28.
**Files:** `Create: src/vespercode/llm/base.py`; `Create: src/vespercode/llm/prepared_request.py`; `Create: src/vespercode/llm/mock_adapter.py`; `Create: src/vespercode/llm/call_result.py`; `Test: tests/unit/llm/test_prepared_request.py`; `Test: tests/unit/llm/test_mock_adapter.py`; `Test: tests/unit/llm/test_call_result.py`
**Depends:** T06.1, T15.2, T27.1

**TDD contracts:**
1. `tests/unit/llm/test_prepared_request.py::test_mock_request_rejects_openai_transport_fields` — 前置：所有 task predecessor 已合并且 16.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Build closed Mock/OpenAI prepared-request contracts and a deterministic Mock adapter with no provider, credential, Grant, authorization, or network behavior.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/llm/test_openai_adapter.py::test_openai_adapter_never_retries_transport` — 前置：所有 task predecessor 已合并且 16.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Serialize one authorized `OpenAIPreparedModelRequestV1` to the sole trusted endpoint and perform at most one non-retried transport call through a freshly bound adapter.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (16.A): `python -m pytest -q tests/unit/llm/test_prepared_request.py::test_mock_request_rejects_openai_transport_fields`
- Domain (16.A): `python -m pytest -q tests/unit/llm/test_prepared_request.py tests/unit/llm/test_mock_adapter.py tests/unit/llm/test_call_result.py`
- Expected (16.A): closed mode/status combinations and byte-identical Mock responses pass offline with zero real-capability calls.
- Target (16.B): `python -m pytest -q tests/unit/llm/test_openai_adapter.py::test_openai_adapter_never_retries_transport`
- Domain (16.B): `python -m pytest -q tests/unit/llm/test_openai_serializer.py tests/unit/llm/test_openai_adapter.py`
- Expected (16.B): exact body vectors, one transport call, trusted endpoint enforcement, bounded responses, and redacted failures pass.

**Review focus:**
- SPEC (16.A): Spec compliance review checks Task 16.A's Goal, Milestone 16's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent closed prepared requests and Mock adapter contract.
- Quality (16.A): Code quality review checks mode-discriminant closure, prepared-request identity, status/result exhaustiveness, deterministic Mock selection, byte-stable responses, and zero real-capability imports/calls.
- SPEC (16.B): Spec compliance review checks Task 16.B's Goal, Milestone 16's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent single-call trusted OpenAI adapter contract.
- Quality (16.B): Code quality review checks exact serialization, authorization/secret binding, unbound-adapter refusal, trusted endpoint/redirect handling, single-attempt transport, bounded output, redacted errors, and no secret retention.

**Done:** legacy steps 16.A, 16.B 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T17.1: Agent Action Parser, Identity Binding, and Dispatcher

**Status:** Not started
**Work package:** WP17
**Legacy steps:** 17.A, 17.B, 17.C
**Goal:** Parse exactly one closed model action object with no surrounding text, defaults, unknown fields, or model-supplied Harness identity.；Bind one parsed action to a Harness-generated non-empty ID plus canonical semantic and instance digests.；Dispatch a bound action only after current-candidate, path/object, phase, and policy gates pass in the required order.
**SPEC contracts:** SPEC §4.2.1–§4.2.3; §4.2.5 behavior 3–5; §4.2.8; §4.3 candidate binding; §4.4.1; §5.1–§5.2; §7 ActionRecord; §10.1 AC-02, AC-06, AC-17, AC-18, AC-26, AC-28, AC-31.
**Files:** `Create: src/vespercode/loop/agent_actions.py`; `Create: src/vespercode/loop/action_parser.py`; `Test: tests/unit/loop/test_agent_actions.py`; `Test: tests/unit/loop/test_action_parser.py`; `Create: src/vespercode/loop/action_binding.py`; `Test: tests/unit/loop/test_action_binding.py`; `Create: src/vespercode/tools/dispatcher.py`; `Test: tests/unit/tools/test_dispatcher.py`; `Test: tests/unit/tools/test_dispatch_order.py`
**Depends:** T04.2, T05.1, T09.1, T11.1, T12.1, T13.1, T16.1

**TDD contracts:**
1. `tests/unit/loop/test_action_parser.py::test_model_supplied_action_id_is_rejected` — 前置：所有 task predecessor 已合并且 17.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Parse exactly one closed model action object with no surrounding text, defaults, unknown fields, or model-supplied Harness identity.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/loop/test_action_binding.py::test_same_semantics_different_harness_ids_change_instance_digest` — 前置：所有 task predecessor 已合并且 17.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Bind one parsed action to a Harness-generated non-empty ID plus canonical semantic and instance digests.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/unit/tools/test_dispatch_order.py::test_hard_deny_never_invokes_tool_port` — 前置：所有 task predecessor 已合并且 17.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Dispatch a bound action only after current-candidate, path/object, phase, and policy gates pass in the required order.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (17.A): `python -m pytest -q tests/unit/loop/test_action_parser.py::test_model_supplied_action_id_is_rejected`
- Domain (17.A): `python -m pytest -q tests/unit/loop/test_agent_actions.py tests/unit/loop/test_action_parser.py`
- Expected (17.A): exactly one valid action parses and every framing/field/type/omission/default/identity violation returns a stable parse error.
- Target (17.B): `python -m pytest -q tests/unit/loop/test_action_binding.py::test_same_semantics_different_harness_ids_change_instance_digest`
- Domain (17.B): `python -m pytest -q tests/unit/loop/test_action_binding.py`
- Expected (17.B): semantic and instance identities bind exact action bytes/ID and reject empty, duplicate, or malformed Harness IDs.
- Target (17.C): `python -m pytest -q tests/unit/tools/test_dispatch_order.py::test_hard_deny_never_invokes_tool_port`
- Domain (17.C): `python -m pytest -q tests/unit/tools/test_dispatcher.py tests/unit/tools/test_dispatch_order.py`
- Expected (17.C): stale/path/phase/policy failures call zero ports; only an exact allowed current action invokes one registered port.

**Review focus:**
- SPEC (17.A): Spec compliance review checks Task 17.A's Goal, Milestone 17's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent strict closed action parser contract.
- Quality (17.A): Code quality review checks total-input JSON framing, closed action discriminants, unknown-key/default rejection, stable parse errors, model-identity exclusion, and parser side-effect freedom.
- SPEC (17.B): Spec compliance review checks Task 17.B's Goal, Milestone 17's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent Harness-owned action identity contract.
- Quality (17.B): Code quality review checks canonical action bytes, semantic-versus-instance separation, id-generator uniqueness, empty/duplicate/malformed rejection, deterministic digesting, and immutable binding.
- SPEC (17.C): Spec compliance review checks Task 17.C's Goal, Milestone 17's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent ordered guarded dispatcher contract.
- Quality (17.C): Code quality review checks gate precedence, zero-call failures, exact typed port registry, pure file-result conversion, artifact bounds, exception normalization, unknown-action closure, and no shell/runner delegation.

**Done:** legacy steps 17.A, 17.B, 17.C 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T18.1: Docker Execution Contract and Readiness

**Status:** Not started
**Work package:** WP18-CONTRACT
**Legacy steps:** 18.A
**Goal:** Build and validate the sole executable/profile/environment/resource request and verify the frozen reference image is locally ready.
**SPEC contracts:** SPEC §1.4.1 runtime compatibility; §1.4.5; §4.1 readiness; §4.3 cleanup; §4.5 adapter/check execution; §5.1; §5.5; §8.2; §10.1 AC-04, AC-19, AC-20, AC-24, AC-25, AC-30; §10.3 Docker integration.
**Files:** `Create: src/vespercode/execution/docker_profile.py`; `Test: tests/unit/execution/test_docker_profile.py`; `Test: tests/unit/execution/test_docker_request.py`
**Depends:** T02.2, T05.1, T06.1

**TDD contracts:**
1. `tests/unit/execution/test_docker_request.py::test_execution_request_rejects_model_executable_field` — 前置：所有 task predecessor 已合并且 18.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Build and validate the sole executable/profile/environment/resource request and verify the frozen reference image is locally ready.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/execution/test_docker_request.py::test_execution_request_rejects_model_executable_field` 的 Domain 边界矩阵 — 在首个 GREEN 后逐项加入稳定错误、并发/重放或真实适配边界；每项先 RED 再最小 GREEN。
3. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (18.A): `python -m pytest -q tests/unit/execution/test_docker_request.py::test_execution_request_rejects_model_executable_field`
- Domain (18.A): `python -m pytest -q tests/unit/execution/test_docker_profile.py tests/unit/execution/test_docker_request.py`
- Expected (18.A): only adapter-built frozen argv/environment/resources validate and image/profile/daemon drift fails before container creation.

**Review focus:**
- SPEC (18.A): Spec compliance review checks Task 18.A's Goal, Milestone 18's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent closed Docker execution request/readiness contract.
- Quality (18.A): Code quality review checks closed argv/environment/resource schemas, adapter-only construction, profile/image digest binding, daemon readiness fail-closed behavior, and zero build/install side effects.

**Done:** legacy steps 18.A 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T18.2: Candidate Materialization, Execution, and Cleanup

**Status:** Not started
**Work package:** WP18-EXECUTION
**Legacy steps:** 18.B, 18.C, 18.D
**Goal:** Materialize one verified CandidateTree into a fresh identity-bound execution root and verify exact bytes before container creation.；Execute one closed request in one fresh locked container with no network/root/write/socket and bounded time/resources/output.；Reverify Candidate/materialization bytes after execution and remove the exact container/root without following links or hiding residue.
**SPEC contracts:** SPEC §1.4.1 runtime compatibility; §1.4.5; §4.1 readiness; §4.3 cleanup; §4.5 adapter/check execution; §5.1; §5.5; §8.2; §10.1 AC-04, AC-19, AC-20, AC-24, AC-25, AC-30; §10.3 Docker integration.
**Files:** `Create: src/vespercode/execution/docker_executor.py`; `Test: tests/unit/execution/test_docker_executor.py`; `Test: tests/integration/docker/test_execution_isolation.py`; `Test: tests/integration/docker/test_execution_output_limits.py`; `Create: src/vespercode/execution/cleanup.py`; `Test: tests/integration/docker/test_execution_cleanup.py`; `Test: tests/integration/docker/test_execution_workspace_integrity.py`
**Depends:** T02.2, T04.2, T09.1, T10.2, T12.1, T18.1

**TDD contracts:**
1. `tests/integration/docker/test_fresh_candidate_materialization.py::test_materialization_rejects_content_object_digest_drift` — 前置：所有 task predecessor 已合并且 18.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Materialize one verified CandidateTree into a fresh identity-bound execution root and verify exact bytes before container creation.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/integration/docker/test_execution_output_limits.py::test_output_limit_kills_exact_container` — 前置：所有 task predecessor 已合并且 18.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Execute one closed request in one fresh locked container with no network/root/write/socket and bounded time/resources/output.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/integration/docker/test_execution_workspace_integrity.py::test_post_execution_candidate_mutation_fails_closed` — 前置：所有 task predecessor 已合并且 18.D 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Reverify Candidate/materialization bytes after execution and remove the exact container/root without following links or hiding residue.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (18.B): `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_fresh_candidate_materialization.py::test_materialization_rejects_content_object_digest_drift`
- Domain (18.B): `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_fresh_candidate_materialization.py`
- Expected (18.B): each invocation creates a unique verified root and every content/path/object drift fails before Docker.
- Target (18.C): `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_execution_output_limits.py::test_output_limit_kills_exact_container`
- Domain (18.C): `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_execution_isolation.py tests/integration/docker/test_execution_output_limits.py`
- Expected (18.C): exact isolation/resource/deadline/output controls hold and each execution returns bounded raw evidence.
- Target (18.D): `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_execution_workspace_integrity.py::test_post_execution_candidate_mutation_fails_closed`
- Domain (18.D): `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_execution_cleanup.py tests/integration/docker/test_execution_workspace_integrity.py`
- Expected (18.D): clean runs remove exact resources; mutation/link/cleanup failures return explicit non-success residue evidence.

**Review focus:**
- SPEC (18.B): Spec compliance review checks Task 18.B's Goal, Milestone 18's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent fresh Candidate materialization contract.
- Quality (18.B): Code quality review checks fresh-root uniqueness, handle/path authorization, exact-byte writes, digest/tree identity, cleanup-on-preflight-failure, link defense, and real-workspace isolation.
- SPEC (18.C): Spec compliance review checks Task 18.C's Goal, Milestone 18's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent fresh isolated Docker execution contract.
- Quality (18.C): Code quality review checks fresh-container identity, all isolation flags, resource/deadline bounds, collector truncation, exact-container kill, cleanup on failures, and raw-evidence-only separation.
- SPEC (18.D): Spec compliance review checks Task 18.D's Goal, Milestone 18's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent post-execution integrity and cleanup contract.
- Quality (18.D): Code quality review checks post-byte/object verification, exact resource identity, link-safe deletion, cleanup idempotency, residue visibility, workspace immutability, and fail-closed partial cleanup.

**Done:** legacy steps 18.B, 18.C, 18.D 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T19.1: Pytest Evidence, Check Results, and Failure Fingerprints

**Status:** Not started
**Work package:** WP19
**Legacy steps:** 19.A, 19.B, 19.C
**Goal:** Convert bounded Ruff and Mypy executions into the sole closed `CheckResultV1` combinations and fail malformed, truncated, or version-inconsistent output closed.；Emit and validate one complete ordered pytest event report whose integrity and normal end are authoritative over exit code or console text.；Produce a stable fingerprint only for one complete exact target `CALL/FAIL`, with allowlisted volatility removed and user failure content preserved.
**SPEC contracts:** SPEC §1.4.1 runtime compatibility; §4.5 `PytestEvidenceV1`, fingerprint, check execution, errors, and deterministic tests; §5.2; §5.5 trust assumption; §7 evidence rows; §10.1 AC-19, AC-20, AC-24, AC-25, AC-26.
**Files:** `Create: src/vespercode/validation/check_result.py`; `Test: tests/unit/validation/test_check_result.py`; `Test: tests/unit/validation/test_ruff_mypy_parsing.py`; `Create: src/vespercode/validation/pytest_evidence.py`; `Create: src/vespercode/validation/pytest_reporter.py`; `Test: tests/unit/validation/test_pytest_evidence.py`; `Test: tests/unit/validation/test_pytest_reporter.py`; `Test: tests/integration/docker/test_pytest_report_channel.py`; `Create: src/vespercode/validation/failure_fingerprint.py`; `Test: tests/unit/validation/test_failure_fingerprint.py`
**Depends:** T04.2, T05.1, T06.1, T18.2

**TDD contracts:**
1. `tests/unit/validation/test_ruff_mypy_parsing.py::test_truncated_ruff_output_is_check_error` — 前置：所有 task predecessor 已合并且 19.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Convert bounded Ruff and Mypy executions into the sole closed `CheckResultV1` combinations and fail malformed, truncated, or version-inconsistent output closed.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/validation/test_pytest_evidence.py::test_missing_session_end_is_reporter_invalid` — 前置：所有 task predecessor 已合并且 19.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Emit and validate one complete ordered pytest event report whose integrity and normal end are authoritative over exit code or console text.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/unit/validation/test_failure_fingerprint.py::test_user_hexadecimal_value_is_not_normalized_away` — 前置：所有 task predecessor 已合并且 19.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Produce a stable fingerprint only for one complete exact target `CALL/FAIL`, with allowlisted volatility removed and user failure content preserved.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (19.A): `python -m pytest -q tests/unit/validation/test_ruff_mypy_parsing.py::test_truncated_ruff_output_is_check_error`
- Domain (19.A): `python -m pytest -q tests/unit/validation/test_check_result.py tests/unit/validation/test_ruff_mypy_parsing.py`
- Expected (19.A): `0`
- Target (19.B): `python -m pytest -q tests/unit/validation/test_pytest_evidence.py::test_missing_session_end_is_reporter_invalid`
- Domain (19.B): `python -m pytest -q tests/unit/validation/test_pytest_evidence.py tests/unit/validation/test_pytest_reporter.py`
- Docker (19.B): `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_pytest_report_channel.py`
- Expected (19.B): `0`
- Target (19.C): `python -m pytest -q tests/unit/validation/test_failure_fingerprint.py::test_user_hexadecimal_value_is_not_normalized_away`
- Domain (19.C): `python -m pytest -q tests/unit/validation/test_failure_fingerprint.py`
- Expected (19.C): `0`

**Review focus:**
- SPEC (19.A): Spec compliance review checks Task 19.A's Goal, Milestone 19's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent closed static-check evidence contract.
- Quality (19.A): Code quality review checks complete-output detection, version binding, status/finding exhaustiveness, deterministic ordering/digests, bounded parsing, and fail-closed malformed or truncated evidence.
- SPEC (19.B): Spec compliance review checks Task 19.B's Goal, Milestone 19's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent authoritative pytest-report contract.
- Quality (19.B): Code quality review checks event sequencing, canonical integrity, expectation/version/collection binding, report bounds, terminal completeness, stable error taxonomy, and independence from exit code or truncated text.
- SPEC (19.C): Spec compliance review checks Task 19.C's Goal, Milestone 19's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent stable target-fingerprint contract.
- Quality (19.C): Code quality review checks exact node/phase/status gating, project-frame inclusion, canonical normalization, allowlist narrowness, user-content preservation, missing assertion evidence, and deterministic unstable outcomes.

**Done:** legacy steps 19.A, 19.B, 19.C 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T20.1: Static Python Support Detection

**Status:** Not started
**Work package:** WP20-DETECTION
**Legacy steps:** 20.A
**Goal:** Determine support from one sealed Snapshot without execution and generate the complete closed Python check plan.
**SPEC contracts:** SPEC §1.4.1 `PythonProjectProfileV1`, static detection, runtime compatibility; §4.1 behavior 9–13; §4.5 adapter boundary, baseline, Manifest, errors/tests; §5.1–§5.2; §7 static/runtime/Manifest rows; §10.1 AC-04, AC-15, AC-19, AC-20, AC-25, AC-26, AC-30–AC-31.
**Files:** `Create: src/vespercode/validation/python_adapter.py`; `Test: tests/unit/validation/test_python_adapter_static.py`; `Test: tests/unit/validation/test_check_plan.py`
**Depends:** T05.1, T06.1, T08.1, T10.2

**TDD contracts:**
1. `tests/unit/validation/test_python_adapter_static.py::test_static_unsupported_result_performs_no_execution` — 前置：所有 task predecessor 已合并且 20.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Determine support from one sealed Snapshot without execution and generate the complete closed Python check plan.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/validation/test_python_adapter_static.py::test_static_unsupported_result_performs_no_execution` 的 Domain 边界矩阵 — 在首个 GREEN 后逐项加入稳定错误、并发/重放或真实适配边界；每项先 RED 再最小 GREEN。
3. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (20.A): `python -m pytest -q tests/unit/validation/test_python_adapter_static.py::test_static_unsupported_result_performs_no_execution`
- Domain (20.A): `python -m pytest -q tests/unit/validation/test_python_adapter_static.py tests/unit/validation/test_check_plan.py`
- Expected (20.A): supported/unsupported classifications and exact closed argv/order vectors pass with zero static execution.

**Review focus:**
- SPEC (20.A): Spec compliance review checks Task 20.A's Goal, Milestone 20's four-field aggregate and SPEC scope, this Implementation boundary, exact RED probe, and Verification as one consistent Snapshot-only detection and frozen-plan contract.
- Quality (20.A): Code quality review checks sealed-Snapshot access, zero-execution detection, support exhaustiveness, collect/full/target identity, exact argv/order, immutable target bindings, and deterministic unsupported reasons.

**Done:** legacy steps 20.A 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T20.2: Stable Baseline and Validation Manifest

**Status:** Not started
**Work package:** WP20-BASELINE
**Legacy steps:** 20.B
**Goal:** Execute the frozen baseline sequence, require stable target failure evidence, and publish `ValidationManifestV1` only after every baseline predicate succeeds.
**SPEC contracts:** SPEC §1.4.1 `PythonProjectProfileV1`, static detection, runtime compatibility; §4.1 behavior 9–13; §4.5 adapter boundary, baseline, Manifest, errors/tests; §5.1–§5.2; §7 static/runtime/Manifest rows; §10.1 AC-04, AC-15, AC-19, AC-20, AC-25, AC-26, AC-30–AC-31.
**Files:** `Create: src/vespercode/validation/baseline.py`; `Create: src/vespercode/validation/manifest.py`; `Test: tests/unit/validation/test_baseline.py`; `Test: tests/unit/validation/test_runtime_compatibility.py`; `Test: tests/unit/validation/test_manifest.py`; `Test: tests/integration/docker/test_reference_baseline.py`
**Depends:** T18.2, T19.1, T20.1

**TDD contracts:**
1. `tests/unit/validation/test_baseline.py::test_unstable_target_fingerprint_creates_no_manifest` — 前置：所有 task predecessor 已合并且 20.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Execute the frozen baseline sequence, require stable target failure evidence, and publish `ValidationManifestV1` only after every baseline predicate succeeds.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/validation/test_baseline.py::test_unstable_target_fingerprint_creates_no_manifest` 的 Domain 边界矩阵 — 在首个 GREEN 后逐项加入稳定错误、并发/重放或真实适配边界；每项先 RED 再最小 GREEN。
3. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (20.B): `python -m pytest -q tests/unit/validation/test_baseline.py::test_unstable_target_fingerprint_creates_no_manifest`
- Domain (20.B): `python -m pytest -q tests/unit/validation/test_baseline.py tests/unit/validation/test_runtime_compatibility.py tests/unit/validation/test_manifest.py`
- Docker (20.B): `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_reference_baseline.py`
- Expected (20.B): only the exact stable reference failure publishes one immutable Manifest.

**Review focus:**
- SPEC (20.B): Spec compliance review checks Task 20.B's Goal, Milestone 20's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent stable-Baseline and Manifest contract.
- Quality (20.B): Code quality review checks frozen-plan execution, fresh boundaries, runtime compatibility, complete report gating, non-target/collection drift, repeated fingerprint equality, exact bindings, and zero Manifest on any incomplete predicate.

**Done:** legacy steps 20.B 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T21.1: Formal Validation and VerifiedCandidate

**Status:** Not started
**Work package:** WP21
**Legacy steps:** 21.A, 21.B, 21.C
**Goal:** Recompute current candidate/policy/environment bindings and freeze the complete collect/full pytest/Ruff/Mypy formal plan before any container call.；Execute every request in the frozen formal plan with a fresh Task 18 boundary and collect complete ordered check evidence.；Evaluate the complete formal predicate and create `VerifiedCandidateV1` only for exact current complete passing evidence.
**SPEC contracts:** SPEC §4.2.3 formal-validation phase; §4.2.5 completion; §4.3 candidate identity; §4.4.2 final subject inputs; §4.5 check execution and formal success predicate; §4.6 writeback inputs; §7 VerifiedCandidate; §10.1 AC-03–AC-07, AC-18, AC-20, AC-26–AC-28, AC-31.
**Files:** `Create: src/vespercode/validation/formal_plan.py`; `Test: tests/unit/validation/test_formal_plan.py`; `Test: tests/unit/validation/test_formal_preflight.py`; `Create: src/vespercode/validation/formal_execution.py`; `Test: tests/integration/docker/test_reference_formal_validation.py`; `Test: tests/integration/docker/test_formal_execution_completeness.py`; `Create: src/vespercode/validation/formal.py`; `Test: tests/unit/validation/test_formal_predicate.py`; `Test: tests/unit/validation/test_verified_candidate.py`
**Depends:** T12.1, T18.2, T19.1, T20.2

**TDD contracts:**
1. `tests/unit/validation/test_formal_preflight.py::test_stale_candidate_produces_zero_execution_requests` — 前置：所有 task predecessor 已合并且 21.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Recompute current candidate/policy/environment bindings and freeze the complete collect/full pytest/Ruff/Mypy formal plan before any container call.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/integration/docker/test_formal_execution_completeness.py::test_executor_must_run_every_frozen_request_once` — 前置：所有 task predecessor 已合并且 21.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Execute every request in the frozen formal plan with a fresh Task 18 boundary and collect complete ordered check evidence.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/unit/validation/test_formal_predicate.py::test_missing_teardown_evidence_cannot_verify_candidate` — 前置：所有 task predecessor 已合并且 21.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Evaluate the complete formal predicate and create `VerifiedCandidateV1` only for exact current complete passing evidence.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (21.A): `python -m pytest -q tests/unit/validation/test_formal_preflight.py::test_stale_candidate_produces_zero_execution_requests`
- Domain (21.A): `python -m pytest -q tests/unit/validation/test_formal_plan.py tests/unit/validation/test_formal_preflight.py`
- Expected (21.A): exact current inputs create the complete frozen plan and every stale/drifted/protected input yields zero execution requests.
- Target (21.B): `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_formal_execution_completeness.py::test_executor_must_run_every_frozen_request_once`
- Domain (21.B): `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_reference_formal_validation.py tests/integration/docker/test_formal_execution_completeness.py`
- Expected (21.B): every frozen request runs once with fresh boundaries and missing/duplicate/cleanup-failed evidence remains explicit.
- Target (21.C): `python -m pytest -q tests/unit/validation/test_formal_predicate.py::test_missing_teardown_evidence_cannot_verify_candidate`
- Domain (21.C): `python -m pytest -q tests/unit/validation/test_formal_predicate.py tests/unit/validation/test_verified_candidate.py`
- Expected (21.C): only complete passing current evidence verifies; every skip/error/timeout/missing/drift/fingerprint mismatch returns a typed failure.

**Review focus:**
- SPEC (21.A): Spec compliance review checks Task 21.A's Goal, Milestone 21's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent formal preflight and frozen-plan contract.
- Quality (21.A): Code quality review checks candidate/policy/environment/Manifest binding completeness, protected-path revalidation, zero-request failure atomicity, exact check identities/order, immutable plan data, and deterministic drift errors.
- SPEC (21.B): Spec compliance review checks Task 21.B's Goal, Milestone 21's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent complete formal-execution contract.
- Quality (21.B): Code quality review checks exact request identity/order/cardinality, fresh-boundary isolation, evidence completeness, cleanup/teardown visibility, timeout handling, no implicit retries, and deterministic partial-execution records.
- SPEC (21.C): Spec compliance review checks Task 21.C's Goal, Milestone 21's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent complete formal-success predicate.
- Quality (21.C): Code quality review checks exact candidate/policy/environment binding, plan/evidence cardinality, authoritative PASS gating, teardown/cleanup completeness, drift/fingerprint comparison, deterministic digesting, and typed fail-closed outcomes.

**Done:** legacy steps 21.A, 21.B, 21.C 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T22.1: Workspace-isolated Repository Memory

**Status:** Not started
**Work package:** WP22
**Legacy steps:** 22.A, 22.B, 22.C
**Goal:** Create/confirm only authorized structured memory with exact workspace identity, creator/source, bounded content, and no authorization power.；List and select only eligible non-cleared entries from the exact workspace under frozen priority, recency, count, and byte limits.；Make an explicit authorized memory clear transaction immediately exclude the targeted workspace entries from every future selection.
**SPEC contracts:** SPEC §4.2.4 context memory; §4.7 memory write/selection/clear; §5.2; §5.4; §5.6; §7 MemoryEntry; §10.1 AC-14, AC-23, AC-26; §10.3 offline tests.
**Files:** `Create: src/vespercode/storage/migrations/v0005_memory.py`; `Create: src/vespercode/memory/entry.py`; `Create: src/vespercode/memory/repository.py`; `Test: tests/unit/storage/test_memory_migration.py`; `Test: tests/unit/memory/test_entry.py`; `Test: tests/unit/memory/test_repository.py`; `Create: src/vespercode/memory/selection.py`; `Test: tests/unit/memory/test_selection.py`; `Test: tests/unit/memory/test_workspace_isolation.py`; `Create: src/vespercode/memory/clear.py`; `Test: tests/unit/memory/test_clear.py`
**Depends:** T07.1, T10.2, T15.2, T19.1

**TDD contracts:**
1. `tests/unit/memory/test_authorization.py::test_model_originated_project_convention_is_rejected` — 前置：所有 task predecessor 已合并且 22.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Create/confirm only authorized structured memory with exact workspace identity, creator/source, bounded content, and no authorization power.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/memory/test_workspace_isolation.py::test_selection_never_crosses_workspace_identity` — 前置：所有 task predecessor 已合并且 22.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“List and select only eligible non-cleared entries from the exact workspace under frozen priority, recency, count, and byte limits.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/unit/memory/test_clear.py::test_successful_clear_is_immediately_ineligible_for_selection` — 前置：所有 task predecessor 已合并且 22.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Make an explicit authorized memory clear transaction immediately exclude the targeted workspace entries from every future selection.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (22.A): `python -m pytest -q tests/unit/memory/test_authorization.py::test_model_originated_project_convention_is_rejected`
- Schema (22.A): `python -m pytest -q tests/unit/storage/test_memory_migration.py::test_memory_migration_has_exact_schema`
- Domain (22.A): `python -m pytest -q tests/unit/storage/test_memory_migration.py tests/unit/memory/test_entry.py tests/unit/memory/test_repository.py tests/unit/memory/test_authorization.py`
- Expected (22.A): exact v0005 schema; only allowed creator/source/kind combinations persist in the exact workspace and forbidden/full/secret/over-limit content rejects.
- Target (22.B): `python -m pytest -q tests/unit/memory/test_workspace_isolation.py::test_selection_never_crosses_workspace_identity`
- Domain (22.B): `python -m pytest -q tests/unit/memory/test_selection.py tests/unit/memory/test_workspace_isolation.py`
- Expected (22.B): exact workspace/count/byte/priority/recency ordering is deterministic and no other workspace or cleared entry appears.
- Target (22.C): `python -m pytest -q tests/unit/memory/test_clear.py::test_successful_clear_is_immediately_ineligible_for_selection`
- Domain (22.C): `python -m pytest -q tests/unit/memory/test_clear.py`
- Expected (22.C): exact authorized clears take effect atomically; replay is idempotent and cross-workspace/forged/partial failures change nothing.

**Review focus:**
- SPEC (22.A): Spec compliance review checks Task 22.A's Goal, Milestone 22's four-field aggregate and SPEC scope, this Implementation boundary, exact RED and Schema RED, and Verification as one consistent authorized workspace-memory repository contract.
- Quality (22.A): Code quality review checks v0005 schema exactness, workspace keys/indexes, closed kind/creator/source unions, transactional zero-row rejection, bounds, data minimization, tombstone compatibility, and absence of authorization power.
- SPEC (22.B): Spec compliance review checks Task 22.B's Goal, Milestone 22's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent isolated deterministic memory-selection contract.
- Quality (22.B): Code quality review checks exact workspace matching, cleared-entry exclusion, frozen priority/recency/tie-break order, canonical byte accounting, count bounds, source retention, deterministic empty results, and no current-evidence override.
- SPEC (22.C): Spec compliance review checks Task 22.C's Goal, Milestone 22's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent transactional memory-clear contract.
- Quality (22.C): Code quality review checks explicit authority, exact workspace/target identity, transaction atomicity, immediate post-commit exclusion, replay idempotency, rollback on partial failure, and preservation of immutable audit/source facts.

**Done:** legacy steps 22.A, 22.B, 22.C 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T23.1: Redacted Audit and User-facing Visibility Projection

**Status:** Not started
**Work package:** WP23
**Legacy steps:** 23.A, 23.B, 23.C
**Goal:** Append one allowlisted, data-minimized audit event under a unique increasing per-Run sequence or reject it with zero rows.；Project each formal Run/phase/wait/recovery/terminal fact into one distinct bounded user-visible state and reason without inferring success from missing evidence.；Remove only eligible audit records older than 30 days while preserving every unresolved-recovery reference and active/non-ended Run.
**SPEC contracts:** SPEC §4.7 audit; §5.3–§5.6; §7 AuditEvent; §8.4 evidence separation; §10.1 AC-08, AC-13, AC-16, AC-21–AC-24, AC-27–AC-29; §10.3 evidence matrix.
**Files:** `Create: src/vespercode/storage/migrations/v0006_audit.py`; `Create: src/vespercode/audit/event.py`; `Create: src/vespercode/audit/repository.py`; `Test: tests/unit/storage/test_audit_migration.py`; `Test: tests/unit/audit/test_event.py`; `Test: tests/unit/audit/test_repository.py`; `Test: tests/unit/audit/test_redaction.py`; `Create: src/vespercode/audit/projection.py`; `Test: tests/unit/audit/test_projection.py`; `Create: src/vespercode/audit/retention.py`; `Test: tests/unit/audit/test_retention.py`
**Depends:** T07.1, T22.1

**TDD contracts:**
1. `tests/unit/audit/test_redaction.py::test_audit_rejects_complete_request_body_and_secret_fields` — 前置：所有 task predecessor 已合并且 23.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Append one allowlisted, data-minimized audit event under a unique increasing per-Run sequence or reject it with zero rows.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/audit/test_projection.py::test_recovery_required_is_never_projected_as_stopped` — 前置：所有 task predecessor 已合并且 23.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Project each formal Run/phase/wait/recovery/terminal fact into one distinct bounded user-visible state and reason without inferring success from missing evidence.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/unit/audit/test_retention.py::test_retention_preserves_unresolved_recovery_evidence` — 前置：所有 task predecessor 已合并且 23.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Remove only eligible audit records older than 30 days while preserving every unresolved-recovery reference and active/non-ended Run.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (23.A): `python -m pytest -q tests/unit/audit/test_redaction.py::test_audit_rejects_complete_request_body_and_secret_fields`
- Schema (23.A): `python -m pytest -q tests/unit/storage/test_audit_migration.py::test_audit_migration_has_exact_schema`
- Domain (23.A): `python -m pytest -q tests/unit/storage/test_audit_migration.py tests/unit/audit/test_event.py tests/unit/audit/test_repository.py tests/unit/audit/test_redaction.py`
- Expected (23.A): `0`
- Target (23.B): `python -m pytest -q tests/unit/audit/test_projection.py::test_recovery_required_is_never_projected_as_stopped`
- Domain (23.B): `python -m pytest -q tests/unit/audit/test_projection.py`
- Expected (23.B): `0`
- Target (23.C): `python -m pytest -q tests/unit/audit/test_retention.py::test_retention_preserves_unresolved_recovery_evidence`
- Domain (23.C): `python -m pytest -q tests/unit/audit/test_retention.py`
- Expected (23.C): `0`

**Review focus:**
- SPEC (23.A): Spec compliance review checks Task 23.A's Goal, Milestone 23's four-field aggregate and SPEC scope, this Implementation boundary, exact RED and Schema RED, and Verification as one consistent redacted monotonic audit-repository contract.
- Quality (23.A): Code quality review checks v0006 schema exactness, per-Run sequence atomicity, redaction before persistence, payload bounds, zero-row forbidden data, replay/conflict handling, stable pagination, ended-Run authority, and no fabricated external outcome.
- SPEC (23.B): Spec compliance review checks Task 23.B's Goal, Milestone 23's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent user-facing Run visibility contract.
- Quality (23.B): Code quality review checks closed precedence, Run/event identity, monotonic input handling, distinct phase/wait/recovery/terminal mappings, bounded redacted output, missing-evidence fail-closed behavior, and absence of fabricated success or external outcomes.
- SPEC (23.C): Spec compliance review checks Task 23.C's Goal, Milestone 23's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent recovery-preserving audit-retention contract.
- Quality (23.C): Code quality review checks canonical cutoff edges, explicit ended-Run classification, unresolved-recovery reachability, fail-closed missing terminal evidence, deterministic deletion order/counts, idempotency, and preservation of active or ambiguous records.

**Done:** legacy steps 23.A, 23.B, 23.C 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T24.1: ContextProjection and Structured Feedback

**Status:** Not started
**Work package:** WP24
**Legacy steps:** 24.A, 24.B, 24.C
**Goal:** Convert stable check/action/control failures into deterministic bounded feedback records and select the most relevant unconsumed records.；Assemble the exact source-attributed message projection and trim only allowed categories under the frozen context budget.；Bind selected feedback references to one new turn and consume them atomically so no record can be attached to multiple turns.
**SPEC contracts:** SPEC §4.2.4–§4.2.6; §4.4.4 source segments; §4.5 structured feedback; §5.1–§5.2; §5.5 disclosure isolation; §7 FeedbackRecord; §10.1 AC-05, AC-13–AC-14, AC-17, AC-26, AC-28.
**Files:** `Create: src/vespercode/loop/feedback.py`; `Test: tests/unit/loop/test_feedback.py`; `Create: src/vespercode/loop/context_projection.py`; `Test: tests/unit/loop/test_context_projection.py`; `Test: tests/unit/loop/test_context_trimming.py`; `Test: tests/unit/loop/test_context_sources.py`; `Create: src/vespercode/storage/migrations/v0008_feedback.py`; `Create: src/vespercode/loop/feedback_consumption.py`; `Test: tests/unit/storage/test_feedback_migration.py`; `Test: tests/unit/loop/test_feedback_consumption.py`
**Depends:** T04.2, T05.1, T07.1, T10.2, T11.1, T15.2, T16.1, T19.1, T22.1, T25.1

**TDD contracts:**
1. `tests/unit/loop/test_feedback.py::test_newest_failure_survives_feedback_limit` — 前置：所有 task predecessor 已合并且 24.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Convert stable check/action/control failures into deterministic bounded feedback records and select the most relevant unconsumed records.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/loop/test_context_trimming.py::test_trimming_never_removes_most_recent_failure_feedback` — 前置：所有 task predecessor 已合并且 24.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Assemble the exact source-attributed message projection and trim only allowed categories under the frozen context budget.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/unit/loop/test_feedback_consumption.py::test_two_turns_cannot_consume_one_feedback_record` — 前置：所有 task predecessor 已合并且 24.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Bind selected feedback references to one new turn and consume them atomically so no record can be attached to multiple turns.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (24.A): `python -m pytest -q tests/unit/loop/test_feedback.py::test_newest_failure_survives_feedback_limit`
- Domain (24.A): `python -m pytest -q tests/unit/loop/test_feedback.py`
- Expected (24.A): stable inputs produce stable records/order and newest required failure survives exact count/byte limits.
- Target (24.B): `python -m pytest -q tests/unit/loop/test_context_trimming.py::test_trimming_never_removes_most_recent_failure_feedback`
- Domain (24.B): `python -m pytest -q tests/unit/loop/test_context_projection.py tests/unit/loop/test_context_trimming.py tests/unit/loop/test_context_sources.py`
- Expected (24.B): mandatory facts remain, trim order/budgets/source paths are exact, and impossible mandatory content returns zero-side-effect budget failure.
- Target (24.C): `python -m pytest -q tests/unit/loop/test_feedback_consumption.py::test_two_turns_cannot_consume_one_feedback_record`
- Schema (24.C): `python -m pytest -q tests/unit/storage/test_feedback_migration.py::test_feedback_migration_has_exact_schema`
- Domain (24.C): `python -m pytest -q tests/unit/storage/test_feedback_migration.py tests/unit/loop/test_feedback_consumption.py`
- Expected (24.C): exact v0008 schema; exactly one turn consumes each record; replay is stable and conflicts/missing refs change nothing.

**Review focus:**
- SPEC (24.A): Spec compliance review checks Task 24.A's Goal, Milestone 24's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent structured bounded feedback contract.
- Quality (24.A): Code quality review checks typed source coverage, source attribution, stable ids/timestamps, severity and tie-break order, canonical byte/count bounds, newest-failure retention, deterministic output, and exclusion of raw bodies or secrets.
- SPEC (24.B): Spec compliance review checks Task 24.B's Goal, Milestone 24's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent deterministic bounded context-projection contract.
- Quality (24.B): Code quality review checks mandatory fact retention, source attribution, frozen category order, optional-only trimming, canonical byte accounting, stable digesting, impossible-budget failure, deterministic inputs, and exclusion of restricted content.
- SPEC (24.C): Spec compliance review checks Task 24.C's Goal, Milestone 24's four-field aggregate and SPEC scope, this Implementation boundary, exact RED and Schema RED, and Verification as one consistent atomic feedback-to-turn consumption contract.
- Quality (24.C): Code quality review checks v0008 schema exactness, bounded append validation, turn/reference identity, compare-and-consume atomicity, one-winner concurrency, replay stability, rollback on mixed refs, and exclusion of raw bodies or credentials.

**Done:** legacy steps 24.A, 24.B, 24.C 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T25.1: Active Turn and Call Counting Boundary

**Status:** Not started
**Work package:** WP25-TURN
**Legacy steps:** 25.B
**Goal:** Atomically establish one active turn and define exactly which successful pre-call boundary increments turn/call counters.
**SPEC contracts:** SPEC §3.2 dimensions; §4.2 in full; §4.4.4 call ordering; §4.5 feedback/formal transition; §5.1–§5.4; §7 AgentTurn/Action/Feedback; §9 LLM boundary; §10.1 AC-02, AC-05–AC-06, AC-13, AC-15–AC-18, AC-20, AC-27–AC-28, AC-31; Harness requirement prohibiting high-level agent executors.
**Files:** `Create: src/vespercode/storage/migrations/v0007_agent_turns.py`; `Create: src/vespercode/loop/turn_boundary.py`; `Test: tests/unit/storage/test_agent_turns_migration.py`; `Test: tests/unit/loop/test_turn_counting.py`
**Depends:** T07.1, T08.1, T23.1

**TDD contracts:**
1. `tests/unit/loop/test_turn_counting.py::test_pre_call_failure_does_not_increment_turn_or_call` — 前置：所有 task predecessor 已合并且 25.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Atomically establish one active turn and define exactly which successful pre-call boundary increments turn/call counters.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/loop/test_turn_counting.py::test_pre_call_failure_does_not_increment_turn_or_call` 的 Domain 边界矩阵 — 在首个 GREEN 后逐项加入稳定错误、并发/重放或真实适配边界；每项先 RED 再最小 GREEN。
3. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (25.B): `python -m pytest -q tests/unit/loop/test_turn_counting.py::test_pre_call_failure_does_not_increment_turn_or_call`
- Schema (25.B): `python -m pytest -q tests/unit/storage/test_agent_turns_migration.py::test_agent_turn_migration_has_exact_schema`
- Domain (25.B): `python -m pytest -q tests/unit/storage/test_agent_turns_migration.py tests/unit/loop/test_turn_counting.py`
- Expected (25.B): exact v0007 schema; every credential/Grant/readiness/transport boundary has an explicit exact count outcome and concurrent starts admit one active turn.

**Review focus:**
- SPEC (25.B): Spec compliance review checks Task 25.B's Goal, Milestone 25's four-field aggregate and SPEC scope, this Implementation boundary, exact RED and Schema RED, and Verification as one consistent active-turn/counting contract.
- Quality (25.B): Code quality review checks v0007 schema exactness, partial uniqueness, compare-and-update revisions, one-winner concurrency, pre-call zero counts, precise turn/call increment points, close/replay conflicts, and body-free evidence.

**Done:** legacy steps 25.B 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T25.2: Call, Dispatch, and Restart Boundary

**Status:** Not started
**Work package:** WP25-CALL
**Legacy steps:** 25.C, 25.D, 25.F
**Goal:** Prepare and perform exactly one Mock or OpenAI call, enforcing fresh credential and authorization ordering before Task 25.B records call start.；Convert one model response into at most one bound action, evaluate policy, dispatch only ALLOW, and produce/consume structured feedback exactly once.；Detect an interrupted non-persistent Agent turn after process restart and stop without reconstructing, retrying, or resending it.
**SPEC contracts:** SPEC §3.2 dimensions; §4.2 in full; §4.4.4 call ordering; §4.5 feedback/formal transition; §5.1–§5.4; §7 AgentTurn/Action/Feedback; §9 LLM boundary; §10.1 AC-02, AC-05–AC-06, AC-13, AC-15–AC-18, AC-20, AC-27–AC-28, AC-31; Harness requirement prohibiting high-level agent executors.
**Files:** `Create: src/vespercode/loop/call_orchestrator.py`; `Test: tests/unit/loop/test_call_orchestrator.py`; `Create: src/vespercode/storage/migrations/v0009_actions.py`; `Create: src/vespercode/loop/action_pipeline.py`; `Test: tests/unit/storage/test_actions_migration.py`; `Test: tests/unit/loop/test_action_pipeline.py`; `Test: tests/unit/loop/test_main_loop_failures.py`; `Create: src/vespercode/loop/restart.py`; `Test: tests/unit/loop/test_restart_behavior.py`
**Depends:** T07.1, T11.1, T12.1, T13.1, T15.2, T16.1, T17.1, T19.1, T23.1, T24.1, T25.1, T27.1

**TDD contracts:**
1. `tests/unit/loop/test_call_orchestrator.py::test_cleared_credential_stops_before_every_charge_or_count` — 前置：所有 task predecessor 已合并且 25.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Prepare and perform exactly one Mock or OpenAI call, enforcing fresh credential and authorization ordering before Task 25.B records call start.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/loop/test_action_pipeline.py::test_policy_deny_skips_dispatch_and_returns_feedback` — 前置：所有 task predecessor 已合并且 25.D 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Convert one model response into at most one bound action, evaluate policy, dispatch only ALLOW, and produce/consume structured feedback exactly once.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/unit/loop/test_restart_behavior.py::test_restart_during_active_turn_stops_without_resend` — 前置：所有 task predecessor 已合并且 25.F 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Detect an interrupted non-persistent Agent turn after process restart and stop without reconstructing, retrying, or resending it.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (25.C): `python -m pytest -q tests/unit/loop/test_call_orchestrator.py::test_cleared_credential_stops_before_every_charge_or_count`
- Domain (25.C): `python -m pytest -q tests/unit/loop/test_call_orchestrator.py tests/unit/loop/test_turn_counting.py`
- Expected (25.C): Mock calls never touch real ports; OpenAI calls follow the exact credential→Grant→authorization→count→transport order once.
- Target (25.D): `python -m pytest -q tests/unit/loop/test_action_pipeline.py::test_policy_deny_skips_dispatch_and_returns_feedback`
- Schema (25.D): `python -m pytest -q tests/unit/storage/test_actions_migration.py::test_action_migration_has_exact_schema`
- Domain (25.D): `python -m pytest -q tests/unit/storage/test_actions_migration.py tests/unit/loop/test_action_pipeline.py tests/unit/loop/test_main_loop_failures.py`
- Expected (25.D): exact v0009 schema; invalid, DENY, tool failure, check feedback, completion proposal, and consume-once traces pass without hidden dispatch.
- Target (25.F): `python -m pytest -q tests/unit/loop/test_restart_behavior.py::test_restart_during_active_turn_stops_without_resend`
- Domain (25.F): `python -m pytest -q tests/unit/loop/test_restart_behavior.py`
- Expected (25.F): every interrupted non-persistent phase fails closed with zero resend.

**Review focus:**
- SPEC (25.C): Spec compliance review checks Task 25.C's Goal, Milestone 25's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent one-authorized-call contract.
- Quality (25.C): Code quality review checks Mock isolation, per-real-call backend re-probe/read, credential/Grant/authorization/count/transport ordering, DENY preservation, single invocation, bounded failure mapping, and no retry/cache/fallback.
- SPEC (25.D): Spec compliance review checks Task 25.D's Goal, Milestone 25's four-field aggregate and SPEC scope, this Implementation boundary, exact RED and Schema RED, and Verification as one consistent parse/policy/dispatch/feedback contract.
- Quality (25.D): Code quality review checks v0009 schema exactness, parse/bind identity, policy-before-dispatch order, ALLOW-only invocation, DENY preservation, feedback append/consume atomicity, body minimization, and explicit failure records.
- SPEC (25.F): Spec compliance review checks Task 25.F's Goal, Milestone 25's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent restart fail-close contract.
- Quality (25.F): Code quality review checks persisted-phase interpretation, active-turn/terminal precedence, ambiguous-evidence failure, zero reconstruction/resend, typed stop/audit minimization, deterministic replay, and no ordinary-turn recovery.

**Done:** legacy steps 25.C, 25.D, 25.F 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T25.3: Stop, Wait, and Sequential Loop Composition

**Status:** Not started
**Work package:** WP25-LOOP
**Legacy steps:** 25.A, 25.E, 25.G
**Goal:** Decide repeated-action, no-progress, budget, invalid-output, cancel, and deadline stops from immutable inputs without performing loop side effects.；Pause only at declared waits, expire against the smaller applicable deadline, and honor cancellation only at deterministic safe points.；Compose Tasks 25.A–25.F into the formal sequential loop without reimplementing any child rule.
**SPEC contracts:** SPEC §3.2 dimensions; §4.2 in full; §4.4.4 call ordering; §4.5 feedback/formal transition; §5.1–§5.4; §7 AgentTurn/Action/Feedback; §9 LLM boundary; §10.1 AC-02, AC-05–AC-06, AC-13, AC-15–AC-18, AC-20, AC-27–AC-28, AC-31; Harness requirement prohibiting high-level agent executors.
**Files:** `Create: src/vespercode/loop/stopping.py`; `Create: src/vespercode/loop/progress.py`; `Test: tests/unit/loop/test_stopping.py`; `Test: tests/unit/loop/test_progress.py`; `Create: src/vespercode/loop/wait_control.py`; `Create: src/vespercode/loop/cancellation.py`; `Test: tests/unit/loop/test_wait_lifecycle.py`; `Create: src/vespercode/loop/engine.py`; `Test: tests/unit/loop/test_main_loop.py`; `Test: tests/unit/loop/test_main_loop_failures.py`
**Depends:** T05.1, T07.1, T08.1, T14.1, T17.1, T21.1, T24.1, T25.1, T25.2

**TDD contracts:**
1. `tests/unit/loop/test_stopping.py::test_repeated_semantic_action_stops_at_exact_limit` — 前置：所有 task predecessor 已合并且 25.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Decide repeated-action, no-progress, budget, invalid-output, cancel, and deadline stops from immutable inputs without performing loop side effects.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/loop/test_wait_lifecycle.py::test_expired_wait_never_resumes_agent_action` — 前置：所有 task predecessor 已合并且 25.E 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Pause only at declared waits, expire against the smaller applicable deadline, and honor cancellation only at deterministic safe points.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/unit/loop/test_main_loop.py::test_one_engine_step_calls_each_stage_once_in_order` — 前置：所有 task predecessor 已合并且 25.G 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Compose Tasks 25.A–25.F into the formal sequential loop without reimplementing any child rule.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (25.A): `python -m pytest -q tests/unit/loop/test_stopping.py::test_repeated_semantic_action_stops_at_exact_limit`
- Domain (25.A): `python -m pytest -q tests/unit/loop/test_stopping.py tests/unit/loop/test_progress.py`
- Expected (25.A): exact boundary tables are deterministic and side-effect free.
- Target (25.E): `python -m pytest -q tests/unit/loop/test_wait_lifecycle.py::test_expired_wait_never_resumes_agent_action`
- Domain (25.E): `python -m pytest -q tests/unit/loop/test_wait_lifecycle.py`
- Expected (25.E): reject/expiry/wrong binding/duplicate decision/cancel safe-point tables all pass.
- Target (25.G): `python -m pytest -q tests/unit/loop/test_main_loop.py::test_one_engine_step_calls_each_stage_once_in_order`
- Domain (25.G): `python -m pytest -q tests/unit/loop/test_main_loop.py tests/unit/loop/test_main_loop_failures.py`
- Expected (25.G): Mock/OpenAI, correction, wait, cancel, stop, and completion compositions use the child implementations and preserve exactly one active turn/call.

**Review focus:**
- SPEC (25.A): Spec compliance review checks Task 25.A's Goal, Milestone 25's four-field aggregate and SPEC scope, this Implementation boundary, exact RED probe, and Verification as one consistent pure stop/progress contract.
- Quality (25.A): Code quality review checks semantic progress identity, exact window edges, closed stop precedence, turn/call limits, smaller-deadline selection, cancellation/invalid-output handling, deterministic time, and zero side effects.
- SPEC (25.E): Spec compliance review checks Task 25.E's Goal, Milestone 25's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent wait/deadline/cancellation contract.
- Quality (25.E): Code quality review checks exact wait binding, one-winner decisions, smaller-deadline precedence, injected-time edges, expiry before resume, duplicate/reject handling, cancellation safe points, and zero forbidden effects.
- SPEC (25.G): Spec compliance review checks Task 25.G's Goal, Milestone 25's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent thin sequential main-loop contract.
- Quality (25.G): Code quality review checks exact stage order/cardinality, injected-child provenance, wait/restart/cancel boundaries, one active turn/call, first-boundary stopping, evidence ordering, no copied predicates, and no high-level agent runner.

**Done:** legacy steps 25.A, 25.E, 25.G 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T26.1: Persistence Records, Protected Storage, and Writeback

**Status:** Not started
**Work package:** WP26
**Legacy steps:** 26.A, 26.D, 26.E
**Goal:** Define the immutable v0011 persistence schema and typed repositories for transaction and ordered per-path records without performing artifact I/O or workspace writeback.；Store exact preimage, postimage, backup, and raw recovery evidence bytes as current-user ACL-restricted content-addressed artifacts with verified immutable refs.；Thinly compose Task 26.A records and Task 26.D artifacts into the exact approval-bound 1–3-path atomic writeback protocol ending only in verified `COMMITTED` or a durable non-terminal transaction.
**SPEC contracts:** SPEC §4.2.6–§4.2.7 persistence cancellation/lifecycle; §4.4.2 approval; §4.6 in full; §5.2; §5.5–§5.6; §7 persistence rows; §8.2 recovery CLI; §10.1 AC-03, AC-07, AC-21–AC-22, AC-26–AC-29, AC-31; §10.3 recovery fault injection.
**Files:** `Create: src/vespercode/storage/migrations/v0011_persistence.py`; `Create: src/vespercode/persistence/path_record.py`; `Create: src/vespercode/persistence/transaction.py`; `Test: tests/unit/storage/test_persistence_migration.py`; `Test: tests/unit/persistence/test_path_record.py`; `Test: tests/unit/persistence/test_transaction.py`; `Create: src/vespercode/persistence/artifacts.py`; `Test: tests/unit/persistence/test_artifacts.py`; `Create: src/vespercode/persistence/writeback.py`; `Test: tests/unit/persistence/test_writeback_preconditions.py`; `Test: tests/fault_injection/persistence/test_writeback_fault_matrix.py`
**Depends:** T03.2, T07.1, T09.1, T12.1, T14.1, T21.1, T23.1

**TDD contracts:**
1. `tests/unit/persistence/test_path_record.py::test_path_records_are_unique_and_ordered_with_body_free_evidence` — 前置：所有 task predecessor 已合并且 26.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Define the immutable v0011 persistence schema and typed repositories for transaction and ordered per-path records without performing artifact I/O or workspace writeback.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/persistence/test_artifacts.py::test_artifact_store_rejects_digest_mismatch_and_non_private_acl` — 前置：所有 task predecessor 已合并且 26.D 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Store exact preimage, postimage, backup, and raw recovery evidence bytes as current-user ACL-restricted content-addressed artifacts with verified immutable refs.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/unit/persistence/test_writeback_preconditions.py::test_missing_exact_approval_writes_no_workspace_bytes` — 前置：所有 task predecessor 已合并且 26.E 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Thinly compose Task 26.A records and Task 26.D artifacts into the exact approval-bound 1–3-path atomic writeback protocol ending only in verified `COMMITTED` or a durable non-terminal transaction.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (26.A): `python -m pytest -q tests/unit/persistence/test_path_record.py::test_path_records_are_unique_and_ordered_with_body_free_evidence`
- Schema (26.A): `python -m pytest -q tests/unit/storage/test_persistence_migration.py::test_persistence_migration_has_exact_schema`
- Domain (26.A): `python -m pytest -q tests/unit/storage/test_persistence_migration.py tests/unit/persistence/test_path_record.py tests/unit/persistence/test_transaction.py`
- Expected (26.A): exact v0011 schema, keys, uniqueness, state vocabulary, ordered repository access, and body-free evidence refs pass without artifact or workspace I/O.
- Target (26.D): `python -m pytest -q tests/unit/persistence/test_artifacts.py::test_artifact_store_rejects_digest_mismatch_and_non_private_acl`
- Domain (26.D): `python -m pytest -q tests/unit/persistence/test_artifacts.py`
- Expected (26.D): deterministic refs, byte-for-byte verification, ACL rejection, atomic artifact publication, and absence of SQLite/workspace mutations pass.
- Target (26.E): `python -m pytest -q tests/unit/persistence/test_writeback_preconditions.py::test_missing_exact_approval_writes_no_workspace_bytes`
- Domain (26.E): `python -m pytest -q tests/unit/persistence/test_writeback_preconditions.py tests/fault_injection/persistence/test_writeback_fault_matrix.py`
- Expected (26.E): exact approval, byte/identity, 1–3-path ordering, backup-before-replace, verification, cancellation, and injected interruption cases pass; any interruption leaves a durable non-terminal transaction rather than false success.

**Review focus:**
- SPEC (26.A): Spec compliance review checks Task 26.A's Goal, Milestone 26's four-field aggregate and SPEC scope, this Implementation boundary, exact RED and Schema RED, and Verification as one consistent persistence-record contract.
- Quality (26.A): Code quality review checks v0011 schema exactness, foreign/ordered/unique keys, one active workspace transaction, closed states, immutable transitions, replay/concurrency handling, body-free refs, and zero artifact/workspace I/O.
- SPEC (26.D): Spec compliance review checks Task 26.D's Goal, Milestone 26's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent ACL-restricted artifact-store contract.
- Quality (26.D): Code quality review checks content-address identity, atomic publication, kind/length/digest verification, current-user ACL creation and re-probe, unsafe-access rejection, immutable refs, cleanup residue, and zero SQLite/workspace mutation.
- SPEC (26.E): Spec compliance review checks Task 26.E's Goal, Milestone 26's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent thin approval-bound writeback contract.
- Quality (26.E): Code quality review checks current identity binding, exact approval without DENY expansion, 1–3-path order, backup-before-replace, consume-once timing, atomic replace, progress durability, postimage verification, cancellation/interruption, and no false terminal state.

**Done:** legacy steps 26.A, 26.D, 26.E 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T26.2: Recovery Preview and Apply

**Status:** Not started
**Work package:** WP26
**Legacy steps:** 26.B, 26.C
**Goal:** Inspect a non-terminal transaction and current object/byte identities without writing, returning only proven `COMMITTED`, `ROLLED_BACK`, or `UNRESOLVED`.；Apply only a current bound recovery preview under the workspace lease and prove the production protocol across deadline, external-change, ACL, and Windows identity faults.
**SPEC contracts:** SPEC §4.2.6–§4.2.7 persistence cancellation/lifecycle; §4.4.2 approval; §4.6 in full; §5.2; §5.5–§5.6; §7 persistence rows; §8.2 recovery CLI; §10.1 AC-03, AC-07, AC-21–AC-22, AC-26–AC-29, AC-31; §10.3 recovery fault injection.
**Files:** `Create: src/vespercode/persistence/recovery_preview.py`; `Test: tests/unit/persistence/test_recovery_decision.py`; `Create: src/vespercode/storage/migrations/v0012_recovery.py`; `Create: src/vespercode/persistence/recovery_apply.py`; `Create: src/vespercode/persistence/recovery.py`; `Test: tests/unit/storage/test_recovery_migration.py`; `Test: tests/fault_injection/persistence/test_deadline_faults.py`; `Test: tests/fault_injection/persistence/test_external_change_faults.py`; `Test: tests/integration/windows/test_persistence_acl_and_identity.py`
**Depends:** T07.1, T09.1, T23.1, T26.1

**TDD contracts:**
1. `tests/unit/persistence/test_recovery_decision.py::test_recovery_preview_is_read_only` — 前置：所有 task predecessor 已合并且 26.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Inspect a non-terminal transaction and current object/byte identities without writing, returning only proven `COMMITTED`, `ROLLED_BACK`, or `UNRESOLVED`.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/fault_injection/persistence/test_external_change_faults.py::test_stale_preview_cannot_apply_recovery` — 前置：所有 task predecessor 已合并且 26.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Apply only a current bound recovery preview under the workspace lease and prove the production protocol across deadline, external-change, ACL, and Windows identity faults.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (26.B): `python -m pytest -q tests/unit/persistence/test_recovery_decision.py::test_recovery_preview_is_read_only`
- Domain (26.B): `python -m pytest -q tests/unit/persistence/test_recovery_decision.py`
- Expected (26.B): `UNRESOLVED`
- Target (26.C): `python -m pytest -q tests/fault_injection/persistence/test_external_change_faults.py::test_stale_preview_cannot_apply_recovery`
- Schema (26.C): `python -m pytest -q tests/unit/storage/test_recovery_migration.py::test_recovery_migration_has_exact_schema`
- Domain (26.C): `python -m pytest -q tests/unit/storage/test_recovery_migration.py tests/fault_injection/persistence`
- Windows (26.C): `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_persistence_acl_and_identity.py`
- Expected (26.C): exact v0012 schema and the complete production matrix produce only the three declared dispositions and never overwrite an unproven external change.

**Review focus:**
- SPEC (26.B): Spec compliance review checks Task 26.B's Goal, Milestone 26's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent read-only three-value recovery-preview contract.
- Quality (26.B): Code quality review checks transaction/path identity, ordered observations, safe artifact verification, object/byte identity, complete proof for terminal classifications, `UNRESOLVED` default, source attribution, and zero writes to every port.
- SPEC (26.C): Spec compliance review checks Task 26.C's Goal, Milestone 26's four-field aggregate and SPEC scope, this Implementation boundary, exact RED and Schema RED, and Verification as one consistent explicit recovery-apply contract.
- Quality (26.C): Code quality review checks v0012 schema exactness, workspace/lease/preview binding, pre-change identity rechecks, service-proven terminal recording, stale/external/ACL/deadline faults, unresolved admission, no overwrite, and absence of force or declared-success paths.

**Done:** legacy steps 26.B, 26.C 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T27.1: Windows Credential Manager Lifecycle

**Status:** Not started
**Work package:** WP27
**Legacy steps:** 27.A, 27.B
**Goal:** Enforce the OPENAI-only set/status/update/clear/get-for-call contract through a redacted non-serializable secret wrapper and a verified store port.；Implement the sole WinCred store port and prove real set/status/get-for-call/clear lifecycle with final cleanup and no fallback backend.
**SPEC contracts:** SPEC §4.1 OpenAI readiness; §4.8 in full; §5.5 credential threat; §5.6; §8.1; §8.2; §10.1 AC-08, AC-13, AC-15, AC-24, AC-28; §10.3 Windows integration.
**Files:** `Create: src/vespercode/credentials/port.py`; `Create: src/vespercode/credentials/service.py`; `Test: tests/unit/credentials/test_service.py`; `Test: tests/unit/credentials/test_status.py`; `Test: tests/unit/credentials/test_backend_rejection.py`; `Test: tests/unit/credentials/test_call_lookup.py`; `Test: tests/unit/credentials/test_log_redaction.py`; `Create: src/vespercode/credentials/wincred_store.py`; `Test: tests/integration/windows/test_wincred_smoke.py`
**Depends:** T04.2, T05.1, T06.1

**TDD contracts:**
1. `tests/unit/credentials/test_status.py::test_credential_status_never_contains_secret_or_derivative` — 前置：所有 task predecessor 已合并且 27.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Enforce the OPENAI-only set/status/update/clear/get-for-call contract through a redacted non-serializable secret wrapper and a verified store port.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/integration/windows/test_wincred_smoke.py::test_wincred_smoke_clears_generated_test_entry` — 前置：所有 task predecessor 已合并且 27.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Implement the sole WinCred store port and prove real set/status/get-for-call/clear lifecycle with final cleanup and no fallback backend.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (27.A): `python -m pytest -q tests/unit/credentials/test_status.py::test_credential_status_never_contains_secret_or_derivative`
- Domain (27.A): `python -m pytest -q tests/unit/credentials`
- Expected (27.A): `0`
- Target (27.B): `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_wincred_smoke.py::test_wincred_smoke_clears_generated_test_entry`
- Domain (27.B): `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_wincred_smoke.py`
- Expected (27.B): `0`

**Review focus:**
- SPEC (27.A): Spec compliance review checks Task 27.A's Goal, Milestone 27's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent pure non-revealing credential-lifecycle contract.
- Quality (27.A): Code quality review checks OPENAI closure, hidden-input wrapper properties, status/exception/repr/log redaction, derivative absence, probe ordering, update/clear atomicity, fresh call lookup, unsafe-backend failure, and no fallback/print/transport.
- SPEC (27.B): Spec compliance review checks Task 27.B's Goal, Milestone 27's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent mandatory WinCred adapter contract.
- Quality (27.B): Code quality review checks versioned target identity, backend probe-before-operation order, current-user WinCred semantics, overwrite/delete/fresh-read behavior, redacted failures, `finally` cleanup, no fallback/cache/import/print, and no transport call.

**Done:** legacy steps 27.A, 27.B 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T28.1: Loopback WebUI Security and Application Shell

**Status:** Not started
**Work package:** WP28
**Legacy steps:** 28.A, 28.B, 28.C, 28.D
**Goal:** Enforce loopback-only binding, local session, Host, Origin, CSRF, and response security headers before every route-domain call.；Define the extensible local FastAPI shell, typed route installers, escaped templates, and unambiguous accessible status semantics without owning packaged assets or CLI startup.；Serve the pinned packaged HTMX asset locally and prove escaped rendering, CSP compatibility, keyboard/live-error hooks, and zero CDN/network fallback.；Thinly bind the completed local shell/security/assets to the closed loopback-only `vespercode serve` CLI entry point.
**SPEC contracts:** SPEC §4.9 local mode and tests; §5.3; §5.5 WebUI threat; §8.2 `vespercode serve`; §9 UI choice; §10.1 AC-08, AC-11, AC-13, AC-16, AC-24; course WebUI deliverable.
**Files:** `Create: src/vespercode/web/security.py`; `Test: tests/web/test_security.py`; `Create: src/vespercode/web/app.py`; `Create: src/vespercode/web/templates/base.html`; `Create: src/vespercode/web/templates/home.html`; `Create: src/vespercode/web/templates/components/status_badge.html`; `Test: tests/web/test_status_labels.py`; `Test: tests/web/test_app_composition.py`; `Create: src/vespercode/web/static/htmx.min.js`; `Test: tests/web/test_html_escaping.py`; `Test: tests/web/test_packaged_assets.py`; `Create: src/vespercode/cli.py`; `Test: tests/unit/test_cli.py`
**Depends:** T07.1, T08.1, T23.1, T27.1

**TDD contracts:**
1. `tests/web/test_security.py::test_state_change_rejects_non_loopback_origin` — 前置：所有 task predecessor 已合并且 28.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Enforce loopback-only binding, local session, Host, Origin, CSRF, and response security headers before every route-domain call.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/web/test_status_labels.py::test_status_badge_has_text_and_accessible_name` — 前置：所有 task predecessor 已合并且 28.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Define the extensible local FastAPI shell, typed route installers, escaped templates, and unambiguous accessible status semantics without owning packaged assets or CLI startup.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/web/test_html_escaping.py::test_untrusted_run_text_is_escaped_and_htmx_is_local` — 前置：所有 task predecessor 已合并且 28.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Serve the pinned packaged HTMX asset locally and prove escaped rendering, CSP compatibility, keyboard/live-error hooks, and zero CDN/network fallback.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. `tests/unit/test_cli.py::test_serve_rejects_non_loopback_host_and_secret_arguments` — 前置：所有 task predecessor 已合并且 28.D 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Thinly bind the completed local shell/security/assets to the closed loopback-only `vespercode serve` CLI entry point.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
5. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (28.A): `python -m pytest -q tests/web/test_security.py::test_state_change_rejects_non_loopback_origin`
- Domain (28.A): `python -m pytest -q tests/web/test_security.py`
- Expected (28.A): binding, session, Host/Origin/CSRF and headers fail before all spy domain calls.
- Target (28.B): `python -m pytest -q tests/web/test_status_labels.py::test_status_badge_has_text_and_accessible_name`
- Domain (28.B): `python -m pytest -q tests/web/test_status_labels.py tests/web/test_app_composition.py`
- Expected (28.B): exact status comprehension, escaped template defaults, accessible names, and deterministic typed installer order pass.
- Target (28.C): `python -m pytest -q tests/web/test_html_escaping.py::test_untrusted_run_text_is_escaped_and_htmx_is_local`
- Domain (28.C): `python -m pytest -q tests/web/test_html_escaping.py tests/web/test_packaged_assets.py`
- Browser (28.C): open the loopback shell and verify escaped text, keyboard focus, live errors, CSP, local HTMX loading, and no CDN request.
- Expected (28.C): packaged asset identity/loading, autoescaping, CSP, accessibility hooks, and zero external asset request pass.
- Target (28.D): `python -m pytest -q tests/unit/test_cli.py::test_serve_rejects_non_loopback_host_and_secret_arguments`
- Domain (28.D): `python -m pytest -q tests/unit/test_cli.py`
- Expected (28.D): `127.0.0.1`

**Review focus:**
- SPEC (28.A): Spec compliance review checks Task 28.A's Goal, Milestone 28's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent loopback request-security contract.
- Quality (28.A): Code quality and Open Design/`ui-ux-pro-max` review check loopback/Host/session/Origin/CSRF ordering, cookie/session bounds, CSP and security headers, stable non-leaking errors, keyboard-perceivable failure status where rendered, and zero domain calls after rejection.
- SPEC (28.B): Spec compliance review checks Task 28.B's Goal, Milestone 28's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent local shell/template/status contract.
- Quality (28.B): Code quality and Open Design/`ui-ux-pro-max` review check typed installer order, autoescaping, scanable hierarchy, text/non-color status, contrast, accessible names, keyboard/focus, live errors, reduced motion, stable layout, and Task 28.A security integration without asset or CLI leakage.
- SPEC (28.C): Spec compliance review checks Task 28.C's Goal, Milestone 28's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent packaged safe-render asset contract.
- Quality (28.C): Code quality and Open Design/`ui-ux-pro-max` review check pinned identity, local-only loading, no fallback, autoescaping, CSP compatibility, keyboard/focus/live errors, contrast and non-color cues, reduced motion, stable interaction layout, and zero external asset request.
- SPEC (28.D): Spec compliance review checks Task 28.D's Goal, Milestone 28's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent thin loopback-serve CLI contract.
- Quality (28.D): Code quality review checks closed parsing, literal loopback host, port bounds, clear keyboard-readable errors, secret/provider/repository rejection, one shell factory, one launch, packaged-asset reachability, and no duplicated security, UI, or workflow rule.

**Done:** legacy steps 28.A, 28.B, 28.C, 28.D 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T29.1: Local Run and Governance WebUI Workflows

**Status:** Not started
**Work package:** WP29
**Legacy steps:** 29.A, 29.B, 29.C
**Goal:** Expose strict Run creation, state/status detail, and cancellation through closed secure forms and typed workflow ports.；Render exact provider/endpoint/category/path/budget disclosure facts and submit only a bound approve/reject decision to the Task 15 workflow.；Render the exact FinalDiff/evidence/subject, delegate one bound final decision, call persistence only after exact approval, and install all Milestone 29 routes.
**SPEC contracts:** SPEC §2 US-01, US-03–US-06, US-08; §4.2.7 waits; §4.4.2–§4.4.3 UI disclosures; §4.6 writeback review; §4.9 local run capabilities; §5.3–§5.5; §8.2; §10.1 AC-03, AC-06–AC-07, AC-13, AC-15–AC-16, AC-21, AC-27–AC-28, AC-31.
**Files:** `Create: src/vespercode/web/run_lifecycle_workflow.py`; `Create: src/vespercode/web/routes_runs.py`; `Create: src/vespercode/web/templates/run_create.html`; `Create: src/vespercode/web/templates/run_detail.html`; `Test: tests/web/test_run_workflow.py`; `Create: src/vespercode/web/disclosure_workflow.py`; `Create: src/vespercode/web/routes_disclosure.py`; `Create: src/vespercode/web/templates/disclosure_wait.html`; `Test: tests/web/test_disclosure_workflow.py`; `Create: src/vespercode/web/writeback_workflow.py`; `Create: src/vespercode/web/routes_writeback.py`; `Create: src/vespercode/web/run_workflows.py`; `Test: tests/web/test_writeback_workflow.py`; `Test: tests/web/test_accessibility.py`
**Depends:** T08.1, T14.1, T15.2, T16.1, T21.1, T23.1, T25.3, T26.1, T28.1

**TDD contracts:**
1. `tests/web/test_run_workflow.py::test_invalid_run_form_creates_no_run` — 前置：所有 task predecessor 已合并且 29.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Expose strict Run creation, state/status detail, and cancellation through closed secure forms and typed workflow ports.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/web/test_disclosure_workflow.py::test_disclosure_form_cannot_supply_scope_or_endpoint_override` — 前置：所有 task predecessor 已合并且 29.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Render exact provider/endpoint/category/path/budget disclosure facts and submit only a bound approve/reject decision to the Task 15 workflow.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/web/test_writeback_workflow.py::test_stale_writeback_subject_never_calls_persistence` — 前置：所有 task predecessor 已合并且 29.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Render the exact FinalDiff/evidence/subject, delegate one bound final decision, call persistence only after exact approval, and install all Milestone 29 routes.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (29.A): `python -m pytest -q tests/web/test_run_workflow.py::test_invalid_run_form_creates_no_run`
- Domain (29.A): `python -m pytest -q tests/web/test_run_workflow.py`
- Expected (29.A): create/status/cancel states render safely, idempotently, and without exposing forbidden override fields.
- Target (29.B): `python -m pytest -q tests/web/test_disclosure_workflow.py::test_disclosure_form_cannot_supply_scope_or_endpoint_override`
- Domain (29.B): `python -m pytest -q tests/web/test_disclosure_workflow.py`
- Expected (29.B): exact human labels, no-content-redaction warning, expiry, budget, and closed decision binding pass.
- Target (29.C): `python -m pytest -q tests/web/test_writeback_workflow.py::test_stale_writeback_subject_never_calls_persistence`
- Domain (29.C): `python -m pytest -q tests/web/test_writeback_workflow.py tests/web/test_accessibility.py tests/web/test_run_workflow.py tests/web/test_disclosure_workflow.py`
- Browser (29.C): exercise create → running → disclosure → formal review → stale approval by keyboard.
- Expected (29.C): exact installer order, secure posts, no stale write, escaped evidence, focus/errors, and non-color status cues pass.

**Review focus:**
- SPEC (29.A): Spec compliance review checks Task 29.A's Goal, Milestone 29's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent typed Run-lifecycle WebUI contract.
- Quality (29.A): Code quality and Open Design/`ui-ux-pro-max` review check typed-port isolation, state-aware hierarchy, escaped untrusted text, accessible labels, keyboard/focus/live errors, non-color status, idempotent controls, reduced motion, and relevant CSRF/Host/Origin/CSP integration before domain calls.
- SPEC (29.B): Spec compliance review checks Task 29.B's Goal, Milestone 29's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent bound disclosure-decision WebUI contract.
- Quality (29.B): Code quality and Open Design/`ui-ux-pro-max` review check exact subject labels, escaped paths/text, scanable warning/budget/expiry, approve/reject clarity, keyboard/focus/live errors, non-color state, relevant CSRF/Host/Origin/CSP checks, and zero Grant/endpoint/scope override.
- SPEC (29.C): Spec compliance review checks Task 29.C's Goal, Milestone 29's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent final-writeback governance-route contract.
- Quality (29.C): Code quality and Open Design/`ui-ux-pro-max` review check exact subject/evidence hierarchy, escaped paths/text, state-aware approve/reject controls, keyboard/focus/live errors, non-color status, stale conflict clarity, and relevant CSRF/Host/Origin/CSP checks before typed domain calls.

**Done:** legacy steps 29.A, 29.B, 29.C 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T30.1: Closed Demo Scenario

**Status:** Not started
**Work package:** WP30-SCENARIO
**Legacy steps:** 30.A
**Goal:** Define Demo-only immutable types and the exact fixed scenario data without executor, shared-core orchestration, session storage, or Web behavior.
**SPEC contracts:** SPEC §1.5 public demo goal; §2.9 US-09; §4.2.1 Demo states; §4.9 public Demo; §5.1–§5.2; §5.5–§5.6; §6.4; §7 Demo rows; §8.3; §10.1 AC-02, AC-05, AC-09, AC-12, AC-17, AC-24; §10.4 visual scenario.
**Files:** `Create: src/vespercode/demo/types.py`; `Create: src/vespercode/demo/scenario.py`; `Test: tests/demo/test_types.py`; `Test: tests/demo/test_scenario.py`
**Depends:** T04.2, T05.1

**TDD contracts:**
1. `tests/demo/test_types.py::test_fixed_scenario_rejects_formal_identity_types` — 前置：所有 task predecessor 已合并且 30.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Define Demo-only immutable types and the exact fixed scenario data without executor, shared-core orchestration, session storage, or Web behavior.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/demo/test_types.py::test_fixed_scenario_rejects_formal_identity_types` 的 Domain 边界矩阵 — 在首个 GREEN 后逐项加入稳定错误、并发/重放或真实适配边界；每项先 RED 再最小 GREEN。
3. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (30.A): `python -m pytest -q tests/demo/test_types.py::test_fixed_scenario_rejects_formal_identity_types`
- Domain (30.A): `python -m pytest -q tests/demo/test_types.py tests/demo/test_scenario.py`
- Expected (30.A): exact fixed data, closed decisions/statuses, canonical trace values, and formal/Demo type separation pass.

**Review focus:**
- SPEC (30.A): Spec compliance review checks Task 30.A's Goal, Milestone 30's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent fixed Demo-type/scenario contract.
- Quality (30.A): Code quality review checks immutable closed unions, canonical trace data, formal/Demo identity separation, exact Mock fixtures, forbidden input absence, deterministic serialization, and zero executor/session/Web or capability imports.

**Done:** legacy steps 30.A 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T30.2: Capability-isolated Demo Execution and Web App

**Status:** Not started
**Work package:** WP30-DEMO
**Legacy steps:** 30.C, 30.D, 30.B
**Goal:** Implement only the deterministic Demo executor and simulated tool ports while proving that no formal capability adapter can be constructed or called.；Thinly compose the real shared pure-core pipeline with Task 30.C ports and bounded in-memory Demo sessions to produce the deterministic fixed trace.；Present the headless Demo through an escaped simulation-labeled FastAPI app with `/healthz`, platform PORT handling, and explicit capability-absence verification.
**SPEC contracts:** SPEC §1.5 public demo goal; §2.9 US-09; §4.2.1 Demo states; §4.9 public Demo; §5.1–§5.2; §5.5–§5.6; §6.4; §7 Demo rows; §8.3; §10.1 AC-02, AC-05, AC-09, AC-12, AC-17, AC-24; §10.4 visual scenario.
**Files:** `Create: src/vespercode/demo/executor.py`; `Test: tests/demo/test_executor_isolation.py`; `Create: src/vespercode/demo/runner.py`; `Test: tests/demo/test_trace_determinism.py`; `Test: tests/demo/test_shared_core_composition.py`; `Test: tests/demo/test_session_limits.py`; `Create: src/vespercode/demo/app.py`; `Create: src/vespercode/demo/healthcheck.py`; `Create: src/vespercode/demo/templates/demo.html`; `Test: tests/demo/test_capability_isolation.py`; `Test: tests/demo/test_health.py`; `Test: tests/demo/test_rendering.py`
**Depends:** T13.1, T17.1, T24.1, T25.2, T25.3, T30.1

**TDD contracts:**
1. `tests/demo/test_executor_isolation.py::test_demo_executor_exposes_only_simulated_tool_ports` — 前置：所有 task predecessor 已合并且 30.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Implement only the deterministic Demo executor and simulated tool ports while proving that no formal capability adapter can be constructed or called.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/demo/test_shared_core_composition.py::test_demo_step_invokes_shared_core_and_only_demo_tool_ports` — 前置：所有 task predecessor 已合并且 30.D 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Thinly compose the real shared pure-core pipeline with Task 30.C ports and bounded in-memory Demo sessions to produce the deterministic fixed trace.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/demo/test_capability_isolation.py::test_demo_app_registers_no_formal_capability_adapter` — 前置：所有 task predecessor 已合并且 30.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Present the headless Demo through an escaped simulation-labeled FastAPI app with `/healthz`, platform PORT handling, and explicit capability-absence verification.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (30.C): `python -m pytest -q tests/demo/test_executor_isolation.py::test_demo_executor_exposes_only_simulated_tool_ports`
- Domain (30.C): `python -m pytest -q tests/demo/test_executor_isolation.py`
- Expected (30.C): fixed tool results, closed capabilities, prohibited-prefix scans, and zero formal-capability construction/calls pass.
- Target (30.D): `python -m pytest -q tests/demo/test_shared_core_composition.py::test_demo_step_invokes_shared_core_and_only_demo_tool_ports`
- Domain (30.D): `python -m pytest -q tests/demo/test_trace_determinism.py tests/demo/test_shared_core_composition.py tests/demo/test_session_limits.py`
- Expected (30.D): shared-call provenance, fixed repeated trace, limit/expiry/reset, in-memory-only lifecycle, and zero formal-capability calls pass.
- Target (30.B): `python -m pytest -q tests/demo/test_capability_isolation.py::test_demo_app_registers_no_formal_capability_adapter`
- Domain (30.B): `python -m pytest -q tests/demo/test_capability_isolation.py tests/demo/test_health.py tests/demo/test_rendering.py`
- Browser (30.B): execute the fixed scenario with keyboard and verify persistent simulation labeling and non-color status.
- Expected (30.B): health validates assets/registry, PORT boundaries hold, and forbidden capabilities/endpoints remain absent.

**Review focus:**
- SPEC (30.C): Spec compliance review checks Task 30.C's Goal, Milestone 30's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent isolated Demo executor/tool-port contract.
- Quality (30.C): Code quality review checks closed simulated capabilities, deterministic action/result mapping, no ambient input, prohibited-prefix coverage, zero formal construction/calls, and absence of files, repositories, SQLite, Docker, credentials, recovery, persistence, or providers.
- SPEC (30.D): Spec compliance review checks Task 30.D's Goal, Milestone 30's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent shared-core bounded Demo-runner contract.
- Quality (30.D): Code quality review checks exact production provenance/order, injected Demo-only ports, fixed Mock trace determinism, five-minute/20-action/10-concurrent edges, reset/expiry/no-recovery, in-memory isolation, and no copied rule or formal/external capability.
- SPEC (30.B): Spec compliance review checks Task 30.B's Goal, Milestone 30's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent thin public Demo-app contract.
- Quality (30.B): Code quality and Open Design/`ui-ux-pro-max` review check persistent simulation labeling, escaped fixed text, keyboard/focus/live errors, non-color status, contrast, reduced motion, stable layout, health/PORT clarity, and absence of every formal, local, secret, provider, persistence, or Docker capability.

**Done:** legacy steps 30.C, 30.D, 30.B 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T31.1: Reference Fixture End-to-end Workflow

**Status:** Not started
**Work package:** WP31
**Legacy steps:** 31.A, 31.B, 31.C
**Goal:** Build the deterministic disposable reference harness and prove admission through stable baseline, corrective loop, formal validation, and `VerifiedCandidateV1`.；Prove canonical continuation, hard denial, protected-artifact defense, final-wait no-write branches, and per-real-call credential fail-close in the production E2E harness.；Complete exact approved writeback, uncertain recovery blocking, memory/audit evidence, cleanup, and two-run semantic determinism in the reference harness.
**SPEC contracts:** SPEC §1.4 reference profile; §2 US-01 and US-03–US-08; §4.1–§4.8; §5.1–§5.6; §6.2; §7; §10.1 AC-01–AC-08, AC-13–AC-31; §10.3 reference fixture E2E; course repeatable mechanism/demo requirement.
**Files:** `Create: scripts/run_reference_e2e.py`; `Create: tests/e2e/reference/test_reference_success.py`; `Create: tests/e2e/reference/test_reference_denials.py`; `Create: tests/e2e/reference/test_reference_waits.py`; `Create: tests/e2e/reference/test_reference_no_write.py`; `Create: tests/e2e/reference/test_reference_call_gate.py`; `Create: tests/e2e/reference/test_reference_audit.py`; `Create: tests/e2e/reference/test_reference_recovery_block.py`
**Depends:** T09.1, T10.2, T11.1, T12.1, T13.1, T14.1, T15.2, T16.1, T17.1, T18.2, T19.1, T20.2, T21.1, T22.1, T23.1, T24.1, T25.3, T26.1, T26.2, T27.1, T28.1, T29.1, T38.2, T38.3

**TDD contracts:**
1. `tests/e2e/reference/test_reference_success.py::test_reference_happy_path_reaches_verified_candidate` — 前置：所有 task predecessor 已合并且 31.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Build the deterministic disposable reference harness and prove admission through stable baseline, corrective loop, formal validation, and `VerifiedCandidateV1`.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/e2e/reference/test_reference_call_gate.py::test_cleared_credential_has_zero_real_call_side_effects` — 前置：所有 task predecessor 已合并且 31.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Prove canonical continuation, hard denial, protected-artifact defense, final-wait no-write branches, and per-real-call credential fail-close in the production E2E harness.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/e2e/reference/test_reference_recovery_block.py::test_uncertain_transaction_blocks_new_admission_until_proven_recovery` — 前置：所有 task predecessor 已合并且 31.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Complete exact approved writeback, uncertain recovery blocking, memory/audit evidence, cleanup, and two-run semantic determinism in the reference harness.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (31.A): `python -m pytest -q -o addopts='' -m reference_e2e tests/e2e/reference/test_reference_success.py::test_reference_happy_path_reaches_verified_candidate`
- Domain (31.A): `python -m pytest -q -o addopts='' -m reference_e2e tests/e2e/reference/test_reference_success.py::test_reference_happy_path_reaches_verified_candidate`
- Expected (31.A): the real Windows + Docker + Mock happy path reaches a bound VerifiedCandidate and final wait without writing.
- Target (31.B): `python -m pytest -q -o addopts='' -m reference_e2e tests/e2e/reference/test_reference_call_gate.py::test_cleared_credential_has_zero_real_call_side_effects`
- Domain (31.B): `python -m pytest -q -o addopts='' -m reference_e2e tests/e2e/reference/test_reference_denials.py tests/e2e/reference/test_reference_waits.py tests/e2e/reference/test_reference_no_write.py tests/e2e/reference/test_reference_call_gate.py`
- Expected (31.B): every denial/wait/cursor/credential branch produces the exact stable reason and zero forbidden side effects.
- Target (31.C): `python -m pytest -q -o addopts='' -m reference_e2e tests/e2e/reference/test_reference_recovery_block.py::test_uncertain_transaction_blocks_new_admission_until_proven_recovery`
- Domain (31.C): `python -m pytest -q -o addopts='' -m reference_e2e tests/e2e/reference`
- Script (31.C): `python scripts/run_reference_e2e.py --workspace-root tests/.tmp/reference-e2e --report tests/.tmp/reference-e2e-report.json`
- Expected (31.C): exact postimages commit, recovery remains three-valued, audit is redacted/monotonic, two semantic traces match, and cleanup is proven.

**Review focus:**
- SPEC (31.A): Spec compliance review checks Task 31.A's Goal, Milestone 31's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent reference happy-path contract.
- Quality (31.A): Code quality review checks production provenance, driver/config binding, fresh Windows/Docker/Mock identities, ordered content-addressed trace stages, zero-write final wait, deterministic fixtures, cleanup visibility, report access control, and evidence freshness.
- SPEC (31.B): Spec compliance review checks Task 31.B's Goal, Milestone 31's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent production negative-gate contract.
- Quality (31.B): Code quality review checks hook/fixture binding, denial precedence, cursor/wait identity, protected-artifact defense, per-call credential recheck, exhaustive zero-side-effect counters, fresh content-addressed traces, access-controlled evidence, and no substituted core.
- SPEC (31.C): Spec compliance review checks Task 31.C's Goal, Milestone 31's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent terminal reference E2E/report contract.
- Quality (31.C): Code quality review checks approval/transaction/recovery binding, three-value proof, admission blocking, memory/audit minimization, monotonicity, unresolved-evidence preservation, two-run normalization, fresh content-addressed report identity, access control, and cleanup evidence.

**Done:** legacy steps 31.A, 31.B, 31.C 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T32.1: Repeatable Governance and Feedback Mechanism Demo

**Status:** Not started
**Work package:** WP32
**Legacy steps:** 32.A, 32.B, 32.C
**Goal:** Build the headless mechanism driver and prove hard DENY, protected-artifact precedence, final-approval no-write, and bounded canonical reporting.；Prove failing-check feedback changes the next action once and that paged List/Search plus repeated mechanism runs are semantically deterministic.；Prove formal and public Demo compositions execute the same exact pure-core subset while disclosure/credential failures create zero unauthorized real-call side effects.
**SPEC contracts:** SPEC §3.1–§3.3 main contribution; §4.4 policy/disclosure; §4.5 feedback; §4.9 Demo scenario; §10.1 AC-02, AC-04–AC-06, AC-09, AC-13, AC-17, AC-20, AC-26–AC-28, AC-31; §10.4 mechanism demo; Harness course mechanism-demo requirement.
**Files:** `Create: scripts/run_mechanism_demo.py`; `Create: tests/e2e/mechanism/test_hard_deny.py`; `Create: tests/e2e/mechanism/test_protected_artifacts.py`; `Create: tests/e2e/mechanism/test_approval_gate.py`; `Create: tests/e2e/mechanism/test_feedback_recovery.py`; `Create: tests/e2e/mechanism/test_continuation_gate.py`; `Create: tests/e2e/mechanism/test_trace_determinism.py`; `Create: tests/e2e/mechanism/test_disclosure_gate.py`; `Create: tests/e2e/mechanism/test_credential_recheck.py`; `Create: tests/e2e/mechanism/test_shared_core_reuse.py`
**Depends:** T11.1, T12.1, T13.1, T15.2, T16.1, T17.1, T19.1, T24.1, T25.2, T25.3, T27.1, T30.2

**TDD contracts:**
1. `tests/e2e/mechanism/test_hard_deny.py::test_outside_scope_patch_is_denied_before_dispatch_or_publish` — 前置：所有 task predecessor 已合并且 32.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Build the headless mechanism driver and prove hard DENY, protected-artifact precedence, final-approval no-write, and bounded canonical reporting.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/e2e/mechanism/test_feedback_recovery.py::test_failed_check_feedback_changes_next_action_once` — 前置：所有 task predecessor 已合并且 32.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Prove failing-check feedback changes the next action once and that paged List/Search plus repeated mechanism runs are semantically deterministic.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/e2e/mechanism/test_shared_core_reuse.py::test_formal_and_demo_execute_same_core_implementations` — 前置：所有 task predecessor 已合并且 32.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Prove formal and public Demo compositions execute the same exact pure-core subset while disclosure/credential failures create zero unauthorized real-call side effects.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (32.A): `python -m pytest -q tests/e2e/mechanism/test_hard_deny.py::test_outside_scope_patch_is_denied_before_dispatch_or_publish`
- Domain (32.A): `python -m pytest -q tests/e2e/mechanism/test_hard_deny.py tests/e2e/mechanism/test_protected_artifacts.py tests/e2e/mechanism/test_approval_gate.py`
- Expected (32.A): all governance blocks occur before forbidden dispatch/publish/write.
- Target (32.B): `python -m pytest -q tests/e2e/mechanism/test_feedback_recovery.py::test_failed_check_feedback_changes_next_action_once`
- Domain (32.B): `python -m pytest -q tests/e2e/mechanism/test_feedback_recovery.py tests/e2e/mechanism/test_continuation_gate.py tests/e2e/mechanism/test_trace_determinism.py`
- Expected (32.B): feedback is consumed once, cursor pages are exact, tamper/stale returns zero payload, and repeated semantic traces match.
- Target (32.C): `python -m pytest -q tests/e2e/mechanism/test_shared_core_reuse.py::test_formal_and_demo_execute_same_core_implementations`
- Domain (32.C): `python -m pytest -q tests/e2e/mechanism`
- Script (32.C): `python scripts/run_mechanism_demo.py --report tests/.tmp/mechanism-demo-report.json`
- Expected (32.C): implementation provenance matches, Demo uses only simulated ports, and every real-call gate counter remains zero.

**Review focus:**
- SPEC (32.A): Spec compliance review checks Task 32.A's Goal, Milestone 32's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent offline governance-trace contract.
- Quality (32.A): Code quality review checks production-core provenance, fixed Mock/input binding, guardrail precedence, protected artifacts, approval no-write, exhaustive zero-effect counters, deterministic bounded reports, fresh content-addressed trace identity, access minimization, and no substitute mechanism.
- SPEC (32.B): Spec compliance review checks Task 32.B's Goal, Milestone 32's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent feedback-recovery/determinism trace.
- Quality (32.B): Code quality review checks injected-failure identity, production feedback/context provenance, consume-once correction, exact cursor binding, tamper/stale zero payload, semantic normalization, repeated trace equality, content-addressed stage freshness, and bounded access-controlled reports.
- SPEC (32.C): Spec compliance review checks Task 32.C's Goal, Milestone 32's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent shared-core/real-call proof contract.
- Quality (32.C): Code quality review checks callable identity not labels, exact call order, formal-loop separation, disclosure/credential gate precedence, exhaustive zero counters, Demo prohibited-capability absence, fresh content-addressed report identity, access minimization, and no secret/provider outcome.

**Done:** legacy steps 32.A, 32.B, 32.C 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T33.1: Wheel Build and Clean pipx Distribution Smoke

**Status:** Not started
**Work package:** WP33
**Legacy steps:** 33.A, 33.B
**Goal:** Build exactly one versioned wheel containing every required runtime resource, excluding prohibited files, and publish an independently verified SHA-256.；Install Task 33.A's exact wheel into an isolated Windows pipx home and prove installed CLI, production WebUI composition, and read-only recovery preview without source-checkout fallback.
**SPEC contracts:** SPEC §5.4 evidence; §8.2 local distribution; §8.4 `wheel-build-smoke`; §9 package choice; §10.1 AC-08, AC-10–AC-11, AC-24, AC-26, AC-29–AC-30; §10.3 package smoke; course distribution requirement.
**Files:** `Modify: pyproject.toml`; `Create: tests/smoke/package/test_wheel_contents.py`; `Create: tests/smoke/package/test_wheel_digest.py`; `Create: scripts/run_package_smoke.py`; `Create: tests/smoke/package/test_pipx_install.py`; `Create: tests/smoke/package/test_installed_cli.py`; `Create: tests/smoke/package/test_installed_webui.py`; `Modify: src/vespercode/cli.py`
**Depends:** T26.2, T28.1, T29.1, T31.1, T32.1, T38.2, T38.3

**TDD contracts:**
1. `tests/smoke/package/test_wheel_contents.py::test_built_wheel_contains_all_runtime_resources` — 前置：所有 task predecessor 已合并且 33.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Build exactly one versioned wheel containing every required runtime resource, excluding prohibited files, and publish an independently verified SHA-256.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/smoke/package/test_installed_cli.py::test_installed_cli_does_not_import_source_checkout` — 前置：所有 task predecessor 已合并且 33.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Install Task 33.A's exact wheel into an isolated Windows pipx home and prove installed CLI, production WebUI composition, and read-only recovery preview without source-checkout fallback.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (33.A): `python -m pytest -q -o addopts='' -m package_smoke tests/smoke/package/test_wheel_contents.py::test_built_wheel_contains_all_runtime_resources`
- Build (33.A): `python -m build --wheel`
- Domain (33.A): `python -m pytest -q -o addopts='' -m package_smoke tests/smoke/package/test_wheel_contents.py tests/smoke/package/test_wheel_digest.py`
- Expected (33.A): one wheel, correct filename/version/RECORD/resources, independent digest, and zero prohibited member.
- Target (33.B): `python -m pytest -q -o addopts='' -m package_smoke tests/smoke/package/test_installed_cli.py::test_installed_cli_does_not_import_source_checkout`
- Domain (33.B): `python -m pytest -q -o addopts='' -m package_smoke tests/smoke/package`
- Driver (33.B): `python scripts/run_package_smoke.py --dist dist --require-one-wheel --report tests/.tmp/package-smoke-report.json`
- Expected (33.B): clean install, help/serve/formal pages/recovery preview and cleanup pass on Windows with zero source fallback or preview write.

**Review focus:**
- SPEC (33.A): Spec compliance review checks Task 33.A's Goal, Milestone 33's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent versioned wheel/content/digest contract.
- Quality (33.A): Code quality review checks clean source identity, allowed metadata-only changes, one artifact, filename/version/entrypoint, required packaged assets, prohibited exclusions, RECORD integrity, independently recomputed content digest, evidence freshness, and controlled artifact access.
- SPEC (33.B): Spec compliance review checks Task 33.B's Goal, Milestone 33's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent clean installed-package smoke contract.
- Quality (33.B): Code quality review checks wheel/source/Python/pipx identity binding, isolated homes, packaged entrypoint/assets, reserved loopback port, source-import detection, preview zero-write, redacted results, `finally` cleanup, fresh content-addressed report, and controlled evidence access.

**Done:** legacy steps 33.A, 33.B 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T34.1: Demo OCI Smoke

**Status:** Not started
**Work package:** WP34-DEMO
**Legacy steps:** 34.B
**Goal:** Build a Demo-only image from an explicit shared-core allowlist and prove health, fixed trace, non-persistence, and absence of every formal capability adapter.
**SPEC contracts:** SPEC §1.4.1/§1.4.5; §4.5 Docker checks; §4.9 Demo; §5.5–§5.6; §6.4 shared core; §8.2–§8.4; §9; §10.1 AC-04, AC-09, AC-12, AC-19–AC-20, AC-24–AC-25, AC-30; §10.3 OCI smoke.
**Files:** `Create: containers/demo/Dockerfile`; `Create: requirements/demo.lock`; `Create: scripts/run_demo_image_smoke.py`; `Create: tests/smoke/images/test_demo_image_contract.py`; `Create: tests/smoke/images/test_demo_container_health.py`; `Create: tests/smoke/images/test_image_capability_separation.py`
**Depends:** T30.2, T32.1

**TDD contracts:**
1. `tests/smoke/images/test_image_capability_separation.py::test_demo_image_contains_shared_core_but_no_formal_adapters` — 前置：所有 task predecessor 已合并且 34.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Build a Demo-only image from an explicit shared-core allowlist and prove health, fixed trace, non-persistence, and absence of every formal capability adapter.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/smoke/images/test_image_capability_separation.py::test_demo_image_contains_shared_core_but_no_formal_adapters` 的 Domain 边界矩阵 — 在首个 GREEN 后逐项加入稳定错误、并发/重放或真实适配边界；每项先 RED 再最小 GREEN。
3. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (34.B): `python -m pytest -q -o addopts='' -m oci_smoke tests/smoke/images/test_image_capability_separation.py::test_demo_image_contains_shared_core_but_no_formal_adapters`
- Build (34.B): `docker build --pull=false -f containers/demo/Dockerfile -t vespercode-demo:local .`
- Domain (34.B): `python -m pytest -q -o addopts='' -m oci_smoke tests/smoke/images/test_demo_image_contract.py tests/smoke/images/test_demo_container_health.py tests/smoke/images/test_image_capability_separation.py`
- Driver (34.B): `python scripts/run_demo_image_smoke.py --demo vespercode-demo:local --report tests/.tmp/demo-image-smoke-report.json`
- Expected (34.B): curated import closure, non-root PORT/health/fixed trace, no persistence, and capability absence pass.

**Review focus:**
- SPEC (34.B): Spec compliance review checks Task 34.B's Goal, Milestone 34's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent capability-isolated Demo OCI contract.
- Quality (34.B): Code quality review checks allowlist/lock identity, prohibited-prefix exhaustiveness, filesystem/import closure, non-root PORT/health/fixed trace, session ephemerality, no persistence/socket/secret/repository, zero formal adapters, fresh image/report digests, cleanup, and controlled evidence access.

**Done:** legacy steps 34.B 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T34.2: Reference OCI Reproduction

**Status:** Not started
**Work package:** WP34-REFERENCE
**Legacy steps:** 34.A
**Goal:** Reproduce the Task 2-frozen reference OCI manifest exactly and prove its production executor/profile/fixture isolation contract.
**SPEC contracts:** SPEC §1.4.1/§1.4.5; §4.5 Docker checks; §4.9 Demo; §5.5–§5.6; §6.4 shared core; §8.2–§8.4; §9; §10.1 AC-04, AC-09, AC-12, AC-19–AC-20, AC-24–AC-25, AC-30; §10.3 OCI smoke.
**Files:** `Create: scripts/run_reference_image_smoke.py`; `Create: tests/smoke/images/test_reference_image_contract.py`; `Create: tests/smoke/images/test_reference_fixture_smoke.py`
**Depends:** T02.2, T18.2, T20.2, T31.1, T32.1

**TDD contracts:**
1. `tests/smoke/images/test_reference_image_contract.py::test_rebuilt_reference_manifest_matches_frozen_task2_digest` — 前置：所有 task predecessor 已合并且 34.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Reproduce the Task 2-frozen reference OCI manifest exactly and prove its production executor/profile/fixture isolation contract.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/smoke/images/test_reference_image_contract.py::test_rebuilt_reference_manifest_matches_frozen_task2_digest` 的 Domain 边界矩阵 — 在首个 GREEN 后逐项加入稳定错误、并发/重放或真实适配边界；每项先 RED 再最小 GREEN。
3. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (34.A): `python -m pytest -q -o addopts='' -m oci_smoke tests/smoke/images/test_reference_image_contract.py::test_rebuilt_reference_manifest_matches_frozen_task2_digest`
- Build (34.A): `docker build --pull=false -f containers/reference/Dockerfile -t vespercode-reference:local .`
- Domain (34.A): `python -m pytest -q -o addopts='' -m oci_smoke tests/smoke/images/test_reference_image_contract.py tests/smoke/images/test_reference_fixture_smoke.py`
- Driver (34.A): `python scripts/run_reference_image_smoke.py --reference vespercode-reference:local --report tests/.tmp/reference-image-smoke-report.json`
- Expected (34.A): exact digest continuity, no self-reference, non-root/no-network/read-only/resource/report/fixture smoke, and registry cleanup pass.

**Review focus:**
- SPEC (34.A): Spec compliance review checks Task 34.A's Goal, Milestone 34's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent frozen reference-OCI reproduction contract.
- Quality (34.A): Code quality review checks Task 2/source/profile identity, no input mutation, build/pull digest continuity, no self-reference, non-root/network/read-only/resource isolation, fixture/report binding, fresh content-addressed evidence, registry cleanup, and controlled report access.

**Done:** legacy steps 34.A 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T35.1: Dual GitHub Actions and GitLab CI Contracts

**Status:** Not started
**Work package:** WP35
**Legacy steps:** 35.A, 35.B, 35.C
**Goal:** Run exact `unit-test`, `reference-image-build`, and `demo-image-build` verification jobs on every GitHub push and pull request with no publishing secret or action.；Run exact GitLab `unit-test`, Windows `wheel-build-smoke`, `reference-image-build`, and `demo-image-build` jobs in all required push/MR/main/tag contexts without release secrets in ordinary pipelines.；Add fail-closed protected-tag release rules, verify commit/digest/secret ordering, and freeze real passing GitHub/GitLab source-commit evidence without performing the release.
**SPEC contracts:** SPEC §5.4 NFR-OBS; §5.5 release credentials; §8.4 in full; §9 CI choice; §10.1 AC-10–AC-12, AC-24, AC-30; §10.3 GitHub Actions/GitLab/package/image evidence; course common requirements for GitHub Actions on every push and `.gitlab-ci.yml` `unit-test`.
**Files:** `Create: .github/workflows/ci.yml`; `Create: tests/unit/process/test_github_actions_contract.py`; `Create: .gitlab-ci.yml`; `Create: tests/unit/process/test_gitlab_ci_contract.py`; `Modify: .gitlab-ci.yml`; `Create: scripts/verify_ci_contract.py`; `Create: tests/unit/process/test_ci_release_rules.py`; `Create: tests/unit/process/test_ci_secret_boundaries.py`
**Depends:** T33.1, T34.1, T34.2

**TDD contracts:**
1. `tests/unit/process/test_github_actions_contract.py::test_github_runs_three_no_publish_jobs_on_push_and_pr` — 前置：所有 task predecessor 已合并且 35.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Run exact `unit-test`, `reference-image-build`, and `demo-image-build` verification jobs on every GitHub push and pull request with no publishing secret or action.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/process/test_gitlab_ci_contract.py::test_gitlab_runs_all_four_verification_jobs_for_merge_request` — 前置：所有 task predecessor 已合并且 35.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Run exact GitLab `unit-test`, Windows `wheel-build-smoke`, `reference-image-build`, and `demo-image-build` jobs in all required push/MR/main/tag contexts without release secrets in ordinary pipelines.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/unit/process/test_ci_release_rules.py::test_unprotected_tag_cannot_enter_release_stage` — 前置：所有 task predecessor 已合并且 35.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Add fail-closed protected-tag release rules, verify commit/digest/secret ordering, and freeze real passing GitHub/GitLab source-commit evidence without performing the release.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (35.A): `python -m pytest -q tests/unit/process/test_github_actions_contract.py::test_github_runs_three_no_publish_jobs_on_push_and_pr`
- Domain (35.A): `python -m pytest -q tests/unit/process/test_github_actions_contract.py`
- Real (35.A): push the branch and open a GitHub PR; require all applicable jobs to pass and save real URLs/artifacts.
- Expected (35.A): exact jobs/events/permissions/locks/real builds pass with no publish credential/action.
- Target (35.B): `python -m pytest -q tests/unit/process/test_gitlab_ci_contract.py::test_gitlab_runs_all_four_verification_jobs_for_merge_request`
- Domain (35.B): `python -m pytest -q tests/unit/process/test_gitlab_ci_contract.py`
- Real (35.B): push/open a GitLab MR and require the applicable four jobs, then the main-push set, to pass.
- Expected (35.B): exact contexts, runner, commands, artifacts and no-secret ordinary boundary pass.
- Target (35.C): `python -m pytest -q tests/unit/process/test_ci_release_rules.py::test_unprotected_tag_cannot_enter_release_stage`
- Domain (35.C): `python -m pytest -q tests/unit/process/test_github_actions_contract.py tests/unit/process/test_gitlab_ci_contract.py tests/unit/process/test_ci_release_rules.py tests/unit/process/test_ci_secret_boundaries.py`
- Contract (35.C): `python scripts/verify_ci_contract.py .github/workflows/ci.yml .gitlab-ci.yml`
- Real (35.C): require passing GitHub and GitLab main/source-commit job sets and record their URLs/ids.
- Expected (35.C): protected release ordering, three-way commit precheck, secret scoping, event matrix and real evidence pass.

**Review focus:**
- SPEC (35.A): Spec compliance review checks Task 35.A's Goal, Milestone 35's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent GitHub verification-workflow contract.
- Quality (35.A): Code quality review checks exact jobs/events, every-push/PR coverage, read-only permissions, fork secretlessness, locked commands, artifact retention/digests/access, publish-action absence, source-commit/run binding, URL/artifact freshness, and no invented external status.
- SPEC (35.B): Spec compliance review checks Task 35.B's Goal, Milestone 35's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent GitLab verification-pipeline contract.
- Quality (35.B): Code quality review checks four-job/context exclusivity, Windows runner binding, locked commands, ordinary secretlessness, report/artifact retention/digests/access, source-commit pipeline binding, URL/artifact freshness, missing-runner failure, and no invented external status.
- SPEC (35.C): Spec compliance review checks Task 35.C's Goal, Milestone 35's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent protected-release/dual-CI evidence contract.
- Quality (35.C): Code quality review checks protected-rule fail-close, three-way commit equality, prerequisite job completeness, secret-after-precheck ordering, event matrix, platform evidence freshness, content-addressed artifact alignment, URL/id access control, and rejection of invented/non-terminal runs.

**Done:** legacy steps 35.A, 35.B, 35.C 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T36.1: GitHub Release, GHCR, and Render Deployment Evidence

**Status:** Not started
**Work package:** WP36
**Legacy steps:** 36.A, 36.B, 36.C
**Goal:** Define closed non-secret CI/release/deployment evidence schemas and reject any source-commit, wheel, manifest, or platform-state misalignment before external publication.；Execute one protected source-aligned release that publishes the exact wheel/checksum and Task 2 reference manifest, then re-download/re-pull and verify both artifacts.；Deploy the exact capability-isolated Demo image/config to Render and freeze verified public health, scenario, isolation, and source-commit evidence.
**SPEC contracts:** SPEC §5.4–§5.6; §8.2–§8.4; §10.1 AC-10–AC-12, AC-24, AC-30; §10.3 package/public smoke; course CI/CD record and accessible WebUI URL deliverables.
**Files:** `Create: src/vespercode/delivery/evidence.py`; `Create: delivery/evidence/README.md`; `Create: delivery/evidence/ci-v1.json`; `Create: scripts/verify_release_evidence.py`; `Create: tests/smoke/release/test_evidence_schema.py`; `Create: tests/smoke/release/test_commit_alignment.py`; `Create: delivery/evidence/release-v1.json`; `Create: tests/smoke/release/test_manifest_image_alignment.py`; `Create: render.yaml`; `Create: delivery/evidence/deployment-v1.json`; `Create: tests/smoke/release/test_render_contract.py`; `Create: tests/smoke/release/test_public_demo_smoke.py`
**Depends:** T02.2, T33.1, T34.1, T34.2, T35.1

**TDD contracts:**
1. `tests/smoke/release/test_commit_alignment.py::test_release_evidence_rejects_commit_misalignment` — 前置：所有 task predecessor 已合并且 36.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Define closed non-secret CI/release/deployment evidence schemas and reject any source-commit, wheel, manifest, or platform-state misalignment before external publication.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/smoke/release/test_manifest_image_alignment.py::test_release_rejects_ghcr_digest_different_from_frozen_manifest` — 前置：所有 task predecessor 已合并且 36.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Execute one protected source-aligned release that publishes the exact wheel/checksum and Task 2 reference manifest, then re-download/re-pull and verify both artifacts.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/smoke/release/test_render_contract.py::test_render_contract_has_no_disk_or_real_provider_secret` — 前置：所有 task predecessor 已合并且 36.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Deploy the exact capability-isolated Demo image/config to Render and freeze verified public health, scenario, isolation, and source-commit evidence.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (36.A): `python -m pytest -q -o addopts='' -m deployment_smoke tests/smoke/release/test_commit_alignment.py::test_release_evidence_rejects_commit_misalignment`
- Domain (36.A): `python -m pytest -q -o addopts='' -m deployment_smoke tests/smoke/release/test_evidence_schema.py tests/smoke/release/test_commit_alignment.py`
- Expected (36.A): closed schemas and exact identity alignment reject every missing/mismatched/non-terminal case.
- Target (36.B): `python -m pytest -q -o addopts='' -m deployment_smoke tests/smoke/release/test_manifest_image_alignment.py::test_release_rejects_ghcr_digest_different_from_frozen_manifest`
- Domain (36.B): `python -m pytest -q -o addopts='' -m deployment_smoke tests/smoke/release/test_manifest_image_alignment.py`
- External (36.B): run the protected tag pipeline; download/re-hash/clean-install the wheel; pull GHCR by RepoDigest and smoke it.
- Evidence (36.B): `python scripts/verify_release_evidence.py delivery/evidence`
- Expected (36.B): Task 2 loopback, Task 34 reproduction, built-in manifest, GHCR response, and pulled-image manifest digests are identical; released wheel hash/install pass.
- Target (36.C): `python -m pytest -q -o addopts='' -m deployment_smoke tests/smoke/release/test_render_contract.py::test_render_contract_has_no_disk_or_real_provider_secret`
- Domain (36.C): `python -m pytest -q -o addopts='' -m deployment_smoke tests/smoke/release/test_render_contract.py tests/smoke/release/test_public_demo_smoke.py`
- Live (36.C): `python scripts/verify_release_evidence.py delivery/evidence --require-live`
- Expected (36.C): `/healthz`

**Review focus:**
- SPEC (36.A): Spec compliance review checks Task 36.A's Goal, Milestone 36's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent closed delivery-evidence verifier.
- Quality (36.A): Code quality review checks closed non-secret fields, unknown/planned rejection, source/tag/platform commit equality, wheel/checksum/manifest/image alignment, freshness/terminal predicates, content-addressed identities, access metadata, cross-record consistency, and no external mutation.
- SPEC (36.B): Spec compliance review checks Task 36.B's Goal, Milestone 36's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent protected content-addressed publication contract.
- Quality (36.B): Code quality review checks protected/source/CI preflight, secret-store access, wheel/checksum identity, Task 2/34 manifest continuity, one-shot uncertain-state handling, re-download/re-hash/install, content-addressed RepoDigest pull/smoke, terminal evidence freshness, URL/artifact access control, and no invented result.
- SPEC (36.C): Spec compliance review checks Task 36.C's Goal, Milestone 36's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent Render live-Demo evidence contract.
- Quality (36.C): Code quality review checks source/image/config identity, PORT/health contract, disk/secret/socket/repository absence, endpoint isolation, deployment/URL freshness, content-addressed image binding, cold-start/trace/session/capability observations, evidence access control, and no invented live outcome.

**Done:** legacy steps 36.A, 36.B, 36.C 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T37.1: README and Final Process Evidence

**Status:** Not started
**Work package:** WP37
**Legacy steps:** 37.A, 37.B
**Goal:** Write an accurate user-facing README for installation, operation, security, recovery, distribution, CI/release/deployment, limitations, and non-goals using only verified current evidence.；Complete truthful append-preserving `SPEC_PROCESS.md` and `AGENT_LOG.md` records and fail-closed verification for M0, semantic approval, both typed Independent PLAN Review passes, cold-start, approved-document baseline materialization, every executable task, review, intervention, commit, PR, failure, and lesson.
**SPEC contracts:** SPEC §1.6; §5.3–§5.6; §8.1–§8.4; §10.1 AC-01–AC-31; §10.3; §11.3; course required artifacts, process evidence, README, CI/CD, WebUI URL, and reflection rules; `AGENTS.md` final-report rules.
**Files:** `Create: README.md`; `Create: src/vespercode/delivery/readme_verifier.py`; `Create: tests/unit/process/test_readme_contract.py`; `Create: src/vespercode/delivery/process_verifier.py`; `Read: config/dependency-closure-v1.json`; `Read: config/formal-toolchain-promotion-v1.json`; `Modify: SPEC_PROCESS.md`; `Test: tests/unit/process/test_delivery_evidence.py`
**Depends:** T01.1, T01.2, T02.1, T02.2, T03.1, T03.2, T04.1, T04.2, T05.1, T06.1, T07.1, T07.2, T08.1, T09.1, T10.1, T10.2, T11.1, T12.1, T13.1, T14.1, T15.1, T15.2, T16.1, T17.1, T18.1, T18.2, T19.1, T20.1, T20.2, T21.1, T22.1, T23.1, T24.1, T25.1, T25.2, T25.3, T26.1, T26.2, T27.1, T28.1, T29.1, T30.1, T30.2, T31.1, T32.1, T33.1, T34.1, T34.2, T35.1, T36.1, T38.1, T38.2, T38.3

**TDD contracts:**
1. `tests/unit/process/test_readme_contract.py::test_readme_fails_when_release_digest_verification_is_missing` — 前置：所有 task predecessor 已合并且 37.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Write an accurate user-facing README for installation, operation, security, recovery, distribution, CI/release/deployment, limitations, and non-goals using only verified current evidence.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/process/test_delivery_evidence.py::test_process_evidence_rejects_stale_plan_executability_result` — 前置：所有 task predecessor 已合并且 37.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Complete truthful append-preserving `SPEC_PROCESS.md` and `AGENT_LOG.md` records and fail-closed verification for M0, semantic approval, both typed Independent PLAN Review passes, cold-start, approved-document baseline materialization, every executable task, review, intervention, commit, PR, failure, and lesson.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (37.A): `python -m pytest -q tests/unit/process/test_readme_contract.py::test_readme_fails_when_release_digest_verification_is_missing`
- Domain (37.A): `python -m pytest -q tests/unit/process/test_readme_contract.py`
- Expected (37.A): all required sections, exact commands, real links/digests, threats/limitations/non-goals, and no overclaim pass.
- Target (37.B): `python -m pytest -q tests/unit/process/test_delivery_evidence.py::test_process_evidence_rejects_stale_plan_executability_result tests/unit/process/test_delivery_evidence.py::test_process_evidence_rejects_approved_document_commit_with_unapproved_spec_blob`
- Domain (37.B): `python -m pytest -q tests/unit/process/test_delivery_evidence.py`
- Expected (37.B, 1): `PASS`
- Expected (37.B, 2): `python_version`
- Expected (37.B, 3): `GO`
- Expected (37.B, 4): `FORMAL_PYTHON_IDENTITY_MISMATCH`

**Review focus:**
- SPEC (37.A): Spec compliance review checks Task 37.A's Goal, Milestone 37's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent verified-README contract.
- Quality (37.A): Code quality review checks section completeness, exact executable commands, package/source/URL identity, content digests, evidence freshness and access control, credential/threat/recovery limitations, wording accuracy, and absence of invented outcomes or compatibility promises.
- SPEC (37.B): Spec compliance review checks Task 37.B's Goal, Milestone 37 scope, Independent PLAN Review Gate and Approved-document Baseline Gate registration contracts, this Implementation boundary, exact RED, and Verification as one consistent truthful process-evidence contract with an executable typed-evidence owner.
- Quality (37.B): Code quality review checks append preservation, both complete canonical review pairs, exact candidate/semantic/SPEC/A/B/reviewer identities, reviewer independence, findings/closures and overall decision, committed approved-document containment and clean formal base, complete executable-task chronology, exact M0/toolchain/source identities, character-for-character Python comparison, evidence freshness/content digests/access control, and stable fail-closed errors without fabricated or repaired planning evidence.

**Done:** legacy steps 37.A, 37.B 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T37.2: Independent Delivery and Reflection Readiness Gate

**Status:** Not started
**Work package:** WP37
**Legacy steps:** 37.C
**Goal:** Aggregate every local/external/process/documentation check, including independently validated typed Independent PLAN Review and Approved-document Baseline evidence results, and report ready only when all 55 session tasks cover all 141 legacy steps and a valid student-authored reflection exists.
**SPEC contracts:** SPEC §1.6; §5.3–§5.6; §8.1–§8.4; §10.1 AC-01–AC-31; §10.3; §11.3; course required artifacts, process evidence, README, CI/CD, WebUI URL, and reflection rules; `AGENTS.md` final-report rules.
**Files:** `Create: scripts/verify_delivery.py`; `Create: scripts/verify_reflection.py`; `Create: tests/unit/process/test_reflection_contract.py`; `Modify: tests/unit/process/test_delivery_evidence.py`; `Modify: REFLECTION.md`
**Depends:** T37.1

**TDD contracts:**
1. `tests/unit/process/test_delivery_evidence.py::test_delivery_rejects_failed_independent_plan_review_evidence` — 前置：所有 task predecessor 已合并且 37.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“all 55 session tasks cover all 141 legacy steps and a valid student-authored reflection exists”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/process/test_delivery_evidence.py::test_delivery_rejects_failed_independent_plan_review_evidence` 的 Domain 边界矩阵 — 在首个 GREEN 后逐项加入稳定错误、并发/重放或真实适配边界；每项先 RED 再最小 GREEN。
3. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (37.C): `python -m pytest -q tests/unit/process/test_delivery_evidence.py::test_delivery_rejects_failed_independent_plan_review_evidence tests/unit/process/test_delivery_evidence.py::test_delivery_rejects_failed_approved_document_baseline_evidence`
- Domain (37.C): `python -m pytest -q tests/unit/process/test_readme_contract.py tests/unit/process/test_delivery_evidence.py tests/unit/process/test_reflection_contract.py`
- Delivery (37.C): `python scripts/verify_delivery.py --root . --require-live`
- Reflection (37.C): `python scripts/verify_reflection.py REFLECTION.md`
- Expected (37.C, 1): `PASS`
- Expected (37.C, 2): `INDEPENDENT_PLAN_REVIEW_EVIDENCE_INVALID`
- Expected (37.C, 3): `APPROVED_DOCUMENT_BASELINE_INVALID`
- Expected (37.C, 4): `EXECUTABLE_TASK_INCOMPLETE:38.G`

**Review focus:**
- SPEC (37.C): Spec compliance review checks Task 37.C's Goal, Milestone 37, Independent PLAN Review, and Approved-document Baseline contracts, this Implementation boundary, exact RED, and Verification as one consistent final readiness contract with disjoint typed-evidence aggregation.
- Quality (37.C): Code quality review checks injected-loader isolation, Task 37.B review/baseline error/decision/identity aggregation without duplicate parsing, committed-tree containment binding, complete 141-task aggregation, source/artifact identity, freshness/content digests/access control, fail-closed non-terminal handling, reflection word-count/disclosure/structure checks, student authorship protection, and absence of generated personal content or invented readiness.

**Done:** legacy steps 37.C 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T38.1: Credential, Memory, and Audit Web Workflows

**Status:** Not started
**Work package:** WP38
**Legacy steps:** 38.A, 38.B, 38.C
**Goal:** Expose hidden credential set/status/update/clear through Task 27 with no secret or derivative in any response, error, audit, log, or redisplay.；Expose authorized workspace-scoped memory list/create/confirm/clear operations without cross-workspace selection or policy/control mutation.；Render monotonic paged redacted audit projections and permit explicit clear only for an ended Run without unresolved recovery evidence.
**SPEC contracts:** SPEC §2 US-02 and US-06–US-08; §4.6 recovery; §4.7 FR-MEM; §4.8 FR-CRED; §4.9 local mode; §5.3–§5.6; §7 MemoryEntry/AuditEvent/PersistenceTransaction; §8.1–§8.2; §10.1 AC-08, AC-14, AC-16, AC-21–AC-24, AC-29; §10.3 local, Windows, and recovery verification.
**Files:** `Create: src/vespercode/web/routes_credentials.py`; `Create: src/vespercode/web/templates/credential_status.html`; `Test: tests/web/test_credential_workflow.py`; `Create: src/vespercode/web/routes_memory.py`; `Create: src/vespercode/web/templates/memory.html`; `Create: tests/web/test_memory_workflow.py`; `Create: src/vespercode/web/routes_audit.py`; `Create: src/vespercode/web/templates/audit.html`; `Create: tests/web/test_audit_workflow.py`
**Depends:** T22.1, T23.1, T27.1, T28.1, T29.1

**TDD contracts:**
1. `tests/web/test_credential_workflow.py::test_credential_response_never_contains_secret_or_derivative` — 前置：所有 task predecessor 已合并且 38.A 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Expose hidden credential set/status/update/clear through Task 27 with no secret or derivative in any response, error, audit, log, or redisplay.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/web/test_memory_workflow.py::test_memory_form_cannot_select_foreign_workspace` — 前置：所有 task predecessor 已合并且 38.B 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Expose authorized workspace-scoped memory list/create/confirm/clear operations without cross-workspace selection or policy/control mutation.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/web/test_audit_workflow.py::test_audit_page_contains_only_redacted_projection` — 前置：所有 task predecessor 已合并且 38.C 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Render monotonic paged redacted audit projections and permit explicit clear only for an ended Run without unresolved recovery evidence.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (38.A): `python -m pytest -q tests/web/test_credential_workflow.py::test_credential_response_never_contains_secret_or_derivative`
- Domain (38.A): `python -m pytest -q tests/web/test_credential_workflow.py`
- Expected (38.A): security/idempotency, secret lifetime, status fields, failure projection, escaping, labels/focus/errors, and sentinel absence pass.
- Target (38.B): `python -m pytest -q tests/web/test_memory_workflow.py::test_memory_form_cannot_select_foreign_workspace`
- Domain (38.B): `python -m pytest -q tests/web/test_memory_workflow.py`
- Expected (38.B): server-derived scope, creator/source display, stale/foreign/duplicate no-mutation, clear binding, escaping and accessibility pass.
- Target (38.C): `python -m pytest -q tests/web/test_audit_workflow.py::test_audit_page_contains_only_redacted_projection`
- Domain (38.C): `python -m pytest -q tests/web/test_audit_workflow.py`
- Expected (38.C): ordering/pagination/redaction, ended-run confirmation, recovery preservation, security and accessibility pass.

**Review focus:**
- SPEC (38.A): Spec compliance review checks Task 38.A's Goal, Milestone 38's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent credential WebUI contract.
- Quality (38.A): Code quality and Open Design review uses `ui-ux-pro-max` for the local security-operations context and checks typed service delegation, request security/idempotency, zero secret derivatives, clear scanable hierarchy, keyboard focus, labels, live errors/status, escaping, safe recovery guidance, and accessible contrast.
- SPEC (38.B): Spec compliance review checks Task 38.B's Goal, Milestone 38's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent workspace-memory WebUI contract.
- Quality (38.B): Code quality and Open Design review uses `ui-ux-pro-max` for the local security-operations context and checks server-derived scope, typed service delegation, request security, zero foreign/stale mutation, scanable state transitions, keyboard focus, labels, live errors/status, escaping, and accessible creator/source presentation.
- SPEC (38.C): Spec compliance review checks Task 38.C's Goal, Milestone 38's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent redacted-audit WebUI contract.
- Quality (38.C): Code quality and Open Design review uses `ui-ux-pro-max` for the local security-operations context and checks closed redacted projections, cursor ordering, request/access control, zero raw-body exposure, safe clear predicates, scanable pagination, keyboard focus, labels, live errors/status, escaping, recovery warnings, and accessible contrast.

**Done:** legacy steps 38.A, 38.B, 38.C 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T38.2: Recovery Operations and Production Route Composition

**Status:** Not started
**Work package:** WP38
**Legacy steps:** 38.D, 38.E, 38.F
**Goal:** Render Task 26.B preview with zero writes and allow only a separately confirmed, currently bound Task 26.C apply command without bypass controls.；Add injectable typed parsing/delegation for `vespercode recover --workspace PATH` as read-only preview and require the literal `--apply` switch for the only recovery mutation path, without owning production database or service wiring.；Install Credential, Memory, Audit, and Recovery routes through typed ports, freeze the sole production installer tuple after Run/Governance routes, and own the sole installed recovery-CLI handler/service binding after complete v1 database initialization.
**SPEC contracts:** SPEC §2 US-02 and US-06–US-08; §4.6 recovery; §4.7 FR-MEM; §4.8 FR-CRED; §4.9 local mode; §5.3–§5.6; §7 MemoryEntry/AuditEvent/PersistenceTransaction; §8.1–§8.2; §10.1 AC-08, AC-14, AC-16, AC-21–AC-24, AC-29; §10.3 local, Windows, and recovery verification.
**Files:** `Create: src/vespercode/web/routes_recovery.py`; `Create: src/vespercode/web/templates/recovery_preview.html`; `Test: tests/web/test_recovery_workflow.py`; `Modify: src/vespercode/cli.py`; `Create: tests/unit/test_recovery_cli.py`; `Create: src/vespercode/web/routes_operations.py`; `Create: src/vespercode/web/local_composition.py`; `Create: src/vespercode/cli_composition.py`
**Depends:** T07.2, T09.1, T23.1, T26.2, T28.1, T29.1, T38.1

**TDD contracts:**
1. `tests/web/test_recovery_workflow.py::test_recovery_preview_is_read_only_and_has_no_force_control` — 前置：所有 task predecessor 已合并且 38.D 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Render Task 26.B preview with zero writes and allow only a separately confirmed, currently bound Task 26.C apply command without bypass controls.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/unit/test_recovery_cli.py::test_recover_without_apply_never_writes` — 前置：所有 task predecessor 已合并且 38.E 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Add injectable typed parsing/delegation for `vespercode recover --workspace PATH` as read-only preview and require the literal `--apply` switch for the only recovery mutation path, without owning production database or service wiring.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
3. `tests/web/test_local_composition.py::test_production_installer_tuple_has_exact_order` — 前置：所有 task predecessor 已合并且 38.F 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Install Credential, Memory, Audit, and Recovery routes through typed ports, freeze the sole production installer tuple after Run/Governance routes, and own the sole installed recovery-CLI handler/service binding after complete v1 database initialization.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
4. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (38.D): `python -m pytest -q tests/web/test_recovery_workflow.py::test_recovery_preview_is_read_only_and_has_no_force_control`
- Domain (38.D): `python -m pytest -q tests/web/test_recovery_workflow.py`
- Expected (38.D): full path/status/consequence preview, exact explicit apply, zero preview write, stable unresolved blocking, security and accessibility pass.
- Target (38.E): `python -m pytest -q tests/unit/test_recovery_cli.py::test_recover_without_apply_never_writes`
- Domain (38.E): `python -m pytest -q tests/unit/test_recovery_cli.py tests/unit/test_cli.py`
- Expected (38.E): `SpyRecoveryService`
- Target (38.F): `python -m pytest -q tests/web/test_local_composition.py::test_production_installer_tuple_has_exact_order`
- CLI production (38.F): `python -m pytest -q tests/unit/test_cli_composition.py::test_installed_recover_binds_complete_database_before_handler`
- Domain (38.F): `python -m pytest -q tests/web/test_local_composition.py tests/web/test_credential_workflow.py tests/web/test_memory_workflow.py tests/web/test_audit_workflow.py tests/web/test_recovery_workflow.py tests/unit/test_recovery_cli.py tests/unit/test_cli_composition.py`
- Registry (38.F): `python -m pytest -q tests/unit/storage/test_migration_registry.py tests/web/test_local_composition.py tests/unit/test_cli_composition.py`
- Expected (38.F, 1): `0`
- Expected (38.F, 2): `vespercode serve`
- Expected (38.F, 3): `recover`

**Review focus:**
- SPEC (38.D): Spec compliance review checks Task 38.D's Goal, Milestone 38's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent read-only-first recovery WebUI contract.
- Quality (38.D): Code quality and Open Design review uses `ui-ux-pro-max` for the local security-operations context and checks typed service delegation, preview zero-write, exact apply binding/request security, stale/unresolved failure, scanable consequence hierarchy, keyboard focus, labels, live errors/status, escaping, bypass-control absence, and accessible contrast.
- SPEC (38.E): Spec compliance review checks Task 38.E's Goal, Milestone 38's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent recovery-CLI parser/delegation contract.
- Quality (38.E): Code quality review checks exact command/argument grammar, Windows path handling, injected typed handler use, preview zero-write, literal apply gating, bounded help/errors, identity/lease delegation, storage/migration import absence, and closed force/ignore/body/credential surface without imposing WebUI design gates.
- SPEC (38.F): Spec compliance review checks Task 38.F's Goal, Milestone 38's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent final local production-composition contract.
- Quality (38.F): Code quality review checks complete migration-registry-before-service ordering, exact typed Web installer tuple, sole recovery CLI handler binding, installed entry-point reachability, parser/domain-rule non-duplication, storage ownership, package import boundaries, and absence of alternate composition paths.

**Done:** legacy steps 38.D, 38.E, 38.F 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

### T38.3: Independent Cross-workflow Browser Acceptance

**Status:** Not started
**Work package:** WP38
**Legacy steps:** 38.G
**Goal:** Verify the merged local application end to end with keyboard navigation while preserving each child workflow's security, privacy, scoping, and no-bypass invariants.
**SPEC contracts:** SPEC §2 US-02 and US-06–US-08; §4.6 recovery; §4.7 FR-MEM; §4.8 FR-CRED; §4.9 local mode; §5.3–§5.6; §7 MemoryEntry/AuditEvent/PersistenceTransaction; §8.1–§8.2; §10.1 AC-08, AC-14, AC-16, AC-21–AC-24, AC-29; §10.3 local, Windows, and recovery verification.
**Files:** `Create: tests/web/test_operations_accessibility.py`
**Depends:** T38.2

**TDD contracts:**
1. `tests/web/test_operations_accessibility.py::test_operations_acceptance_runner_requires_all_workflows` — 前置：所有 task predecessor 已合并且 38.G 尚无实现；动作：运行该 legacy step 的 Target；RED：必须由“Verify the merged local application end to end with keyboard navigation while preserving each child workflow's security, privacy, scoping, and no-bypass invariants.”对应的任务归属断言稳定失败，collection/环境失败不计；GREEN：实现满足该 Goal 的最小行为。
2. `tests/web/test_operations_accessibility.py::test_operations_acceptance_runner_requires_all_workflows` 的 Domain 边界矩阵 — 在首个 GREEN 后逐项加入稳定错误、并发/重放或真实适配边界；每项先 RED 再最小 GREEN。
3. 仅在本 task 的 Files/Goal 边界内重构；重新运行全部 legacy Target 与 Domain，禁止吸收 successor 行为。

**Verification:**
- Profile: `FORMAL_OFFLINE_V1`
- Target (38.G): `python -m pytest -q tests/web/test_operations_accessibility.py::test_operations_acceptance_runner_requires_all_workflows`
- Domain (38.G): `python -m pytest -q tests/web`
- Browser (38.G): exercise credential set/status/update/clear, memory create/confirm/view/clear, paged audit/ended-run clear, and recovery preview→explicit apply using production composition and keyboard only.
- Expected (38.G): no secret/body leakage, cross-workspace access, recovery bypass, inaccessible focus/error/status, or alternate composition remains.

**Review focus:**
- SPEC (38.G): Spec compliance review checks that the missing test-owned runner guarantees RED independently of Task 38.F's production state, and that Goal, Milestone 38 scope, Implementation boundary, GREEN acceptance, and Browser verification form one fail-closed cross-workflow contract.
- Quality (38.G): Code quality and Open Design review checks deterministic bounded runner output, exact four-workflow coverage, production-interface isolation, keyboard navigation, focus order, labels, live errors/status, escaping, request/access control, readable hierarchy/contrast, secret/body redaction, server-derived scope, recovery no-bypass, and evidence truthfulness.

**Done:** legacy steps 38.G 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.

## 6. Unified Traceability

This is the sole requirement coverage table. Every implementation set and independent validation set contains session task IDs only, is non-empty, and is disjoint. Legacy IDs and Milestones are resolved through the task cards, not repeated here.

| Requirement | SPEC contract / acceptance scope | Implementation task(s) | Independent validation task(s) | Required evidence |
|---|---|---|---|---|
| US-01 | FR-ADM, FR-LOOP; NFR-PERF, NFR-USE, NFR-SEC; AC-15, AC-16, AC-21, AC-26, AC-28, AC-30, AC-31 | T06.1, T07.1, T07.2, T08.1, T09.1, T10.1, T10.2, T20.1, T20.2, T23.1, T25.1, T25.2, T25.3, T28.1, T29.1 | T31.1, T33.1, T35.1, T37.1, T37.2, T38.3 | 适用 task card 的 Target/Domain 与独立验证 task 证据。 |
| US-02 | FR-CRED, SPEC §8.1; NFR-SEC, NFR-PRIV; AC-08 | T16.1, T25.2, T27.1, T38.1, T38.2 | T31.1, T32.1, T33.1, T35.1, T37.2, T38.3 | 适用 task card 的 Target/Domain 与独立验证 task 证据。 |
| US-03 | FR-LOOP, FR-WS, FR-VAL; NFR-PERF, NFR-REL; AC-04, AC-05, AC-06, AC-17, AC-18, AC-19, AC-20, AC-25, AC-26, AC-28, AC-31 | T10.1, T10.2, T11.1, T12.1, T13.1, T17.1, T18.1, T18.2, T19.1, T20.1, T20.2, T21.1, T24.1, T25.1, T25.2, T25.3 | T31.1, T32.1, T34.2, T35.1, T37.2 | 适用 task card 的 Target/Domain 与独立验证 task 证据。 |
| US-04 | FR-GOV; NFR-SEC, NFR-PRIV; AC-13, AC-26, AC-27 | T15.1, T15.2, T16.1, T24.1, T25.1, T25.2, T25.3, T29.1 | T31.1, T32.1, T35.1, T37.1, T37.2, T38.3 | 适用 task card 的 Target/Domain 与独立验证 task 证据。 |
| US-05 | FR-GOV; NFR-REL, NFR-SEC; AC-01, AC-02, AC-03, AC-26, AC-27, AC-31 | T09.1, T12.1, T13.1, T14.1, T15.1, T15.2, T17.1, T25.2, T25.3 | T31.1, T32.1, T35.1, T37.2 | 适用 task card 的 Target/Domain 与独立验证 task 证据。 |
| US-06 | FR-PERSIST; NFR-REL, NFR-SEC; AC-07, AC-21, AC-22, AC-26, AC-29, AC-31 | T03.1, T03.2, T09.1, T12.1, T14.1, T21.1, T26.1, T26.2, T29.1, T38.2 | T31.1, T33.1, T35.1, T37.2, T38.3 | 适用 task card 的 Target/Domain 与独立验证 task 证据。 |
| US-07 | FR-MEM; NFR-OBS, NFR-PRIV; AC-14, AC-23 | T22.1, T23.1, T24.1, T38.1, T38.2 | T31.1, T35.1, T37.2, T38.3 | 适用 task card 的 Target/Domain 与独立验证 task 证据。 |
| US-08 | FR-LOOP, FR-MEM, FR-UI; NFR-USE, NFR-OBS; AC-06, AC-16, AC-27, AC-28 | T07.1, T07.2, T23.1, T25.2, T25.3, T28.1, T29.1, T38.1, T38.2 | T31.1, T33.1, T35.1, T37.1, T37.2, T38.3 | 适用 task card 的 Target/Domain 与独立验证 task 证据。 |
| US-09 | FR-UI; NFR-PERF, NFR-REL, NFR-SEC; AC-09, AC-12 | T30.1, T30.2, T34.1 | T32.1, T35.1, T36.1, T37.1, T37.2 | 适用 task card 的 Target/Domain 与独立验证 task 证据。 |
| FR-ADM | FR-ADM — request validation, Run creation, and ordered preflight | T06.1, T07.1, T07.2, T08.1, T09.1, T10.1, T10.2, T20.1, T20.2 | T31.1 | Child RED/GREEN suites prove the engine/domain/registry schema closure and zero-downstream admission failures; Windows checks prove workspace/Git/Snapshot; Task 31.A records the production call order and Task 31.B records denials. |
| FR-LOOP | FR-LOOP — loop, action protocol, context, budgets, stopping, and lifecycle | T05.1, T07.1, T11.1, T15.1, T15.2, T16.1, T17.1, T24.1, T25.1, T25.2, T25.3 | T31.1, T32.1 | Component suites prove action, context, feedback, count, progress, timeout, cancel and restart rules; reference and mechanism traces prove composition. |
| FR-WS | FR-WS — Snapshot, path boundary, strict patches, and CandidateTree | T01.1, T01.2, T04.2, T06.1, T09.1, T10.1, T10.2, T11.1, T12.1 | T31.1, T32.1 | Task 1.E `GO` and Tasks 9.A–9.D Windows evidence prove object/path behavior; domain suites and later traces prove legal correction, cursor continuity, and denials. |
| FR-GOV | FR-GOV — policy, final approval, disclosure, and real LLM authorization | T13.1, T14.1, T15.1, T15.2, T16.1, T25.1, T25.2, T25.3, T29.1 | T31.1, T32.1, T38.3 | Pure governance tests plus reference/mechanism/browser traces prove no unauthorized dispatch, network, approval consumption, or write. |
| FR-VAL | FR-VAL — Python adapter, Baseline, checks, Manifest, feedback, and formal success | T18.1, T18.2, T19.1, T20.1, T20.2, T21.1, T24.1, T25.2, T25.3 | T31.1, T34.2 | Docker commands prove isolation/report/Baseline/formal behavior; the reference flow and image smoke preserve the same Manifest and evidence. |
| FR-PERSIST | FR-PERSIST — final approval, controlled writeback, and recovery | T03.1, T03.2, T09.1, T12.1, T14.1, T21.1, T26.1, T26.2, T29.1, T38.2 | T31.1, T33.1, T38.3 | Task 3.G gate, production fault/Windows tests, recovery UI/CLI, reference terminal trace, and installed smoke prove exact writeback and three-value recovery. |
| FR-MEM | FR-MEM — memory and audit | T22.1, T23.1, T24.1, T38.1, T38.2 | T31.1, T38.3 | Domain suites prove isolation/authority/order/retention; reference and browser evidence prove scoped visible operations. |
| FR-CRED | FR-CRED — credential lifecycle | T16.1, T25.2, T27.1, T38.1, T38.2 | T31.1, T32.1, T35.1, T38.3 | WinCred smoke, zero-side-effect call-gate traces, WebUI response scans, and Windows CI evidence prove lifecycle and per-call revalidation. |
| FR-UI | FR-UI — formal local WebUI and public Demo | T28.1, T29.1, T30.1, T30.2, T38.1, T38.2 | T32.1, T33.1, T34.1, T36.1, T38.3 | Local security/browser/installed tests plus shared-core proof, Demo image health, and live public smoke prove both isolated compositions. |
| NFR-PERF | NFR-PERF — hard budgets and bounded resources | T05.1, T08.1, T11.1, T15.1, T15.2, T16.1, T18.1, T18.2, T24.1, T25.1, T25.2, T25.3, T30.1, T30.2 | T31.1, T32.1, T34.1, T34.2 | FakeClock and boundary tests prove pre-side-effect limits; Docker/Demo image smoke and reference traces prove real resource ceilings. |
| NFR-REL | NFR-REL — deterministic and fail-closed behavior | T01.1, T01.2, T02.1, T02.2, T03.1, T03.2, T04.1, T04.2, T05.1, T06.1, T07.1, T07.2, T08.1, T09.1, T10.1, T10.2, T11.1, T12.1, T13.1, T14.1, T15.1, T15.2, T16.1, T17.1, T18.1, T18.2, T19.1, T20.1, T20.2, T21.1, T22.1, T23.1, T24.1, T25.1, T25.2, T25.3, T26.1, T26.2, T30.1, T30.2 | T31.1, T32.1, T37.2 | Gate identity, dependency closure, formal toolchain promotion, canonical vectors, immutable structures, checksum-verified domain/registry closure, transactions, repeated semantic traces, shared-core provenance, and final missing-evidence rejection prove determinism/fail-close. |
| NFR-USE | NFR-USE — understandable status, decisions, diff, and recovery | T23.1, T28.1, T29.1, T37.1, T38.1, T38.2 | T33.1, T38.3 | Local WebUI/browser/accessibility tests, installed UI smoke, and README contract prove understandable non-color-only operation. |
| NFR-OBS | NFR-OBS — ordered evidence and categorized CI/release records | T07.1, T07.2, T23.1, T31.1, T32.1, T35.1, T36.1, T38.1, T38.2 | T37.1, T37.2, T38.3 | Schema history/registry checks, audit concurrency, deterministic reports, real dual-platform records, release/deployment JSON, browser evidence, and evidence-age checks prove observability. |
| NFR-SEC | NFR-SEC — declared threat-boundary mechanisms | T01.1, T01.2, T02.1, T02.2, T03.1, T03.2, T06.1, T09.1, T12.1, T13.1, T14.1, T15.1, T15.2, T16.1, T17.1, T18.1, T18.2, T21.1, T25.1, T25.2, T25.3, T26.1, T26.2, T27.1, T28.1, T29.1, T30.1, T30.2, T35.1, T36.1, T38.1, T38.2 | T31.1, T32.1, T34.1, T34.2, T37.2, T38.3 | Windows/Docker/fault/Web/Demo/dual-CI/live checks plus every credential scan prove the declared boundary without overclaiming SPEC §5.5. |
| NFR-PRIV | NFR-PRIV — local retention and minimal disclosure/storage | T15.1, T15.2, T16.1, T22.1, T23.1, T26.1, T26.2, T27.1, T30.1, T30.2, T36.1, T38.1, T38.2 | T31.1, T32.1, T38.3 | Source/record rejection, ACL/retention, WinCred, no-disk Demo, non-secret evidence, and local response scans prove minimal disclosure/storage. |
| AC-01 | AC-01 | T01.1, T01.2, T04.2, T09.1, T12.1, T13.1 | T31.1, T32.1 | Win32 gate/object tests, strict patch tests, Task 1.E `GO`, Windows job log, and denial traces. |
| AC-02 | AC-02 | T13.1, T14.1, T15.1, T15.2, T17.1, T25.2, T30.1, T30.2 | T32.1 | Policy precedence, shared-core Demo composition, and mechanism hard-DENY report prove zero dispatch/publication. |
| AC-03 | AC-03 | T07.1, T12.1, T13.1, T14.1, T20.2, T21.1, T26.1 | T31.1, T32.1 | Subject/approval/race tests and stale/expiry/duplicate approval traces prove zero write. |
| AC-04 | AC-04 | T12.1, T13.1, T20.1, T20.2, T21.1 | T31.1, T32.1 | Patch/formal/protected-artifact tests and reference/mechanism zero-container evidence. |
| AC-05 | AC-05 | T16.1, T19.1, T24.1, T25.2, T25.3, T30.1, T30.2 | T31.1, T32.1 | Main-loop, shared-core, and feedback-recovery traces prove the Task 24.C feedback consumption changes the next action once. |
| AC-06 | AC-06 | T14.1, T17.1, T20.2, T21.1, T25.2, T25.3, T29.1 | T31.1, T38.3 | Formal predicate, loop, writeback workflow, and completion → validation → final-wait/no-write evidence. |
| AC-07 | AC-07 | T12.1, T14.1, T21.1, T26.1, T29.1 | T31.1, T38.3 | Writeback preconditions/fault matrix/Web workflow plus approved FinalDiff/postimage/untouched-file digest report. |
| AC-08 | AC-08 | T27.1, T28.1, T38.1, T38.2 | T31.1, T33.1, T35.1, T38.3 | Credential status/redaction/WinCred/Web tests, cleared state, Windows CI log, and installed smoke. |
| AC-09 | AC-09 | T13.1, T17.1, T24.1, T25.2, T25.3, T30.1, T30.2 | T32.1, T34.1, T36.1 | Exact shared-pure-core call sequence, repeated Demo trace, forbidden-capability absence, Demo image, and public scenario smoke. |
| AC-10 | AC-10 | T04.1, T35.1, T37.2 | T36.1, T37.1 | Complete hash-locked dependency closure, `python -m pytest -q`, exact GitHub/GitLab contract tests, real unit-test jobs, and final process report. |
| AC-11 | AC-11 | T28.1, T29.1, T33.1, T35.1, T36.1, T37.1, T38.1, T38.2 | T37.2, T38.3 | Clean pipx/installed CLI/WebUI, real wheel job, GitHub Release wheel/SHA, and verified install/start instructions. |
| AC-12 | AC-12 | T30.1, T30.2, T34.1, T35.1, T36.1 | T32.1, T37.2 | Demo container health/capability smoke, real image-build log/digest, Render URL, and live `/healthz`. |
| AC-13 | AC-13 | T06.1, T15.1, T15.2, T16.1, T24.1, T25.1, T25.2, T25.3, T27.1, T29.1 | T31.1, T32.1 | Source/scope/budget, fresh credential, counting, adapter, disclosure UI, and zero-side-effect reference/mechanism traces. |
| AC-14 | AC-14 | T22.1, T24.1, T38.1, T38.2 | T31.1, T38.3 | Memory repository/authorization/context tests plus cross-workspace/clear and visible-operation evidence. |
| AC-15 | AC-15 | T06.1, T08.1, T09.1, T10.1, T10.2, T20.1, T20.2, T25.1, T25.3 | T31.1 | Admission-order/static tests, Windows identity/Snapshot checks, and exact PREFLIGHT/one-Snapshot E2E trace. |
| AC-16 | AC-16 | T07.1, T07.2, T23.1, T25.2, T25.3, T28.1, T29.1, T38.1, T38.2 | T31.1, T33.1, T38.3 | Migration engine/registry, audit projection/status/run/audit Web tests plus state trace and installed browser captures. |
| AC-17 | AC-17 | T05.1, T10.1, T10.2, T11.1, T17.1, T30.1, T30.2 | T31.1, T32.1 | Cursor round-trip/stale/invalid/excerpt, parser/binding, production Demo call sequence, and paged/unpaged traces. |
| AC-18 | AC-18 | T10.1, T10.2, T12.1, T17.1, T20.1, T20.2, T21.1 | T31.1 | FinalDiff/identity/patch/formal tests plus cumulative-patch, stale identity, and verified-candidate report. |
| AC-19 | AC-19 | T02.1, T02.2, T18.1, T18.2, T19.1, T20.2, T34.2 | T31.1, T35.1 | Docker gate/isolation/reference baseline, frozen digest, image smoke, and real reference-image-build logs. |
| AC-20 | AC-20 | T19.1, T20.1, T20.2, T21.1 | T31.1, T34.2 | Formal predicate/reference Docker validation plus VerifiedCandidate digest and container smoke. |
| AC-21 | AC-21 | T01.1, T01.2, T07.1, T09.1, T26.1, T26.2 | T31.1 | Named mutex/repository/fault tests, Task 1.E mutex `GO`, recovery-block trace, and Windows log. |
| AC-22 | AC-22 | T03.1, T03.2, T26.1, T26.2 | T31.1, T38.2 | Feasibility gate, deadline/external-change fault matrix, three-value report, and preview/apply evidence. |
| AC-23 | AC-23 | T22.1, T38.1, T38.2 | T31.1, T38.3 | Memory authorization and Web workflow plus creator/source audit and scoped-form evidence. |
| AC-24 | AC-24 | T01.1, T01.2, T02.1, T02.2, T03.1, T03.2, T04.1, T04.2, T18.1, T18.2, T19.1, T20.1, T20.2, T21.1, T26.1, T26.2, T27.1, T31.1, T33.1, T34.1, T34.2, T35.1, T36.1, T37.1 | T37.2 | Gate identities, dedicated Windows/Docker/E2E/fault/package/OCI/CI/live commands, and categorized URLs/digests in closed evidence JSON. |
| AC-25 | AC-25 | T02.1, T02.2, T19.1, T20.2 | T31.1, T34.2 | Gate-only normalized-input comparator, production fingerprint/Baseline tests, and stable full/target digests in reference/image reports. |
| AC-26 | AC-26 | T04.2, T05.1, T06.1, T10.1, T10.2, T12.1, T14.1, T15.1, T15.2, T16.1, T17.1, T18.1, T18.2, T19.1, T20.1, T20.2, T21.1, T24.1, T25.1, T25.2, T25.3 | T31.1, T37.1, T37.2 | CTV vectors and candidate/profile/request/fingerprint/Manifest/subject digest suites plus cross-process trace and final digest audit. |
| AC-27 | AC-27 | T07.1, T14.1, T15.1, T15.2, T25.3, T29.1 | T31.1, T38.3 | Repository/approval/ledger/wait tests plus restart/wait decisions and browser-bound decision evidence. |
| AC-28 | AC-28 | T05.1, T07.1, T08.1, T15.1, T15.2, T16.1, T17.1, T24.1, T25.1, T25.2, T25.3, T27.1 | T31.1, T32.1 | Counting/stopping/wait/credential/ledger tests plus deadline/order and cleared/unsafe zero-count reports. |
| AC-29 | AC-29 | T03.1, T03.2, T26.1, T26.2, T38.2 | T31.1, T33.1, T38.3 | External-change/recovery Web/CLI tests plus preview/apply/new-file and installed preview evidence. |
| AC-30 | AC-30 | T02.1, T02.2, T06.1, T18.1, T18.2, T20.2, T34.2, T35.1, T36.1 | T37.2 | Local OCI/loopback/digest-pull proof, exact reproduction, protected pipeline, released manifest, GHCR RepoDigest, and target pull equality. |
| AC-31 | AC-31 | T06.1, T09.1, T10.1, T10.2, T11.1, T12.1, T13.1, T14.1, T18.1, T18.2, T20.1, T20.2, T21.1, T26.1 | T31.1, T32.1 | Editable/candidate/policy/formal/persistence tamper and Windows alias tests plus legal/illegal mixed-patch and hard-DENY reports. |

## 7. Derived Waves and Delivery Conditions

### 7.1 Session-task waves

These 33 waves are mechanically derived from the sole `Depends` fields. They are explanatory projections, not a second edge source.

| Wave | Session tasks |
|---:|---|
| 1 | T01.1 |
| 2 | T01.2 |
| 3 | T02.1 |
| 4 | T02.2 |
| 5 | T03.1 |
| 6 | T03.2 |
| 7 | T04.1 |
| 8 | T04.2 |
| 9 | T05.1 |
| 10 | T06.1, T07.1, T10.1, T30.1 |
| 11 | T08.1, T15.1, T18.1, T27.1 |
| 12 | T09.1, T15.2 |
| 13 | T10.2, T16.1 |
| 14 | T11.1, T12.1, T20.1 |
| 15 | T13.1, T18.2 |
| 16 | T17.1, T19.1 |
| 17 | T20.2, T22.1 |
| 18 | T21.1, T23.1 |
| 19 | T25.1, T28.1 |
| 20 | T24.1 |
| 21 | T25.2 |
| 22 | T14.1 |
| 23 | T25.3, T26.1 |
| 24 | T26.2, T29.1, T30.2 |
| 25 | T07.2, T32.1, T38.1 |
| 26 | T34.1, T38.2 |
| 27 | T38.3 |
| 28 | T31.1 |
| 29 | T33.1, T34.2 |
| 30 | T35.1 |
| 31 | T36.1 |
| 32 | T37.1 |
| 33 | T37.2 |

### 7.2 Work-package waves

These 26 waves are mechanically derived by collapsing the session DAG through each task's `Work package`. They are explanatory projections, not a second edge source.

| Wave | Work packages |
|---:|---|
| 1 | WP01 |
| 2 | WP02 |
| 3 | WP03 |
| 4 | WP04 |
| 5 | WP05 |
| 6 | WP06, WP07-CORE, WP10-TEXT, WP30-SCENARIO |
| 7 | WP08, WP15, WP18-CONTRACT, WP27 |
| 8 | WP09, WP16 |
| 9 | WP10-SNAPSHOT |
| 10 | WP11, WP12, WP20-DETECTION |
| 11 | WP13, WP18-EXECUTION |
| 12 | WP17, WP19 |
| 13 | WP20-BASELINE, WP22 |
| 14 | WP21, WP23 |
| 15 | WP25-TURN, WP28 |
| 16 | WP24 |
| 17 | WP25-CALL |
| 18 | WP14 |
| 19 | WP25-LOOP, WP26 |
| 20 | WP07-REGISTRY, WP29, WP30-DEMO |
| 21 | WP32, WP38 |
| 22 | WP31, WP34-DEMO |
| 23 | WP33, WP34-REFERENCE |
| 24 | WP35 |
| 25 | WP36 |
| 26 | WP37 |

### 7.3 Delivery conditions

Delivery is complete only when:

- all 55 session tasks are `Complete`, each with real implementation/evidence commits and both review stages PASS;
- all 46 work packages have a finishing PASS and merged PR;
- all three feasibility milestones record terminal GO without identity drift;
- all required offline, Windows, Docker, fault, browser, package, OCI, CI, release, and live checks pass without required skip;
- credential scans are clean and no secret value appears in repository, log, evidence, artifact, image, or response;
- SPEC acceptance criteria AC-01–AC-31 and all required root deliverables are independently verified at one source commit;
- `README.md`, `SPEC_PROCESS.md`, `AGENT_LOG.md`, external evidence, distribution artifacts, CI records, GHCR identity, and public Demo URL are complete and mutually bound;
- the student-authored 1,500–2,500-word `REFLECTION.md` is present, and any language-only AI assistance is disclosed;
- no unresolved persistence transaction or Critical/Important finding remains.

SPEC §1.6 and §11.3 remain the complete v1 non-goal/future-work authority; PLAN does not restate or weaken them.

## 8. PlanAuditContractV2

### 8.1 Exact mechanical invariants

Two independently implemented verifiers must read strict UTF-8 input and fail on BOM, any CR byte, or other decoding error. `PLAN.md` and `SPEC.md` each end with exactly one LF. PLAN is at most 450 KiB and at most 60,000 whitespace-delimited words.

The candidate must contain exactly:

- 37 milestone identities represented through 141 legacy IDs;
- 46 work packages;
- 55 session task cards;
- 141 unique legacy steps with zero missing or duplicate mapping;
- a 55-node, 298-edge, zero-cycle session DAG with 33 longest-path waves;
- a 46-node, 263-edge, zero-cycle package DAG with 26 longest-path waves;
- 55 unified traceability rows: US 9, FR 9, NFR 6, AC 31;
- one complete required-field set per task card and one-line `Completion evidence`;
- zero task-card fenced implementation/test source blocks, repeated standard workflow templates, duplicate ownership sources, or duplicate dependency sources.

Every task card contains at least one canonical `Target` and one `Domain` Verification record. Legacy labels such as `RED/Target GREEN` are normalized to `Target`; task-specific `Schema`, `Build`, `Driver`, `Windows`, `Docker`, `Browser`, `Live`, `External`, and `Evidence` records remain explicit.

Every inline Verification command is a complete code span, starts with an executable token rather than a quote, has balanced quoting, and contains no ellipsis or clipped pytest node. Each TDD `path::test_name` maps to a complete Target in the same card; pytest Targets require exact normalized path and node equality, while unittest dotted Targets require the exact test function.

Every Review focus has complete `SPEC` and `Quality` records for each listed legacy step. Review sentences end in sentence punctuation and may not end at a clipped token such as `fro`, `normali`, `authori`, `seriali`, `materiali`, `minimi`, or `digest/si`, nor splice directly into another review prefix.

Verifier A/B each run private negative self-tests that inject a leading quote, truncate a pytest node, remove a Domain record, break a TDD/Target mapping, and clip a Review focus sentence; every mutation must be rejected.
Task-card Files determine primary ownership. After generator/template expansion there must be no duplicate primary owner or same-wave write conflict, except the globally authorized tracking modifiers in §2.3. Every mandatory SPEC requirement has a non-empty implementation set and a non-empty disjoint independent-validation set.

### 8.2 `PlanSemanticDigestV1`

The semantic projection preserves every byte except explicitly mutable tracking fields inside the region beginning with the exact line `## 5. Session Task Cards` and ending immediately before the exact line `## 6. Unified Traceability`:

1. replace each full `**Status:** ...` line with `**Status:** TRACKING_STATUS_EXCLUDED_V1`;
2. replace each full one-line `**Completion evidence:** ...` with `**Completion evidence:** TRACKING_EVIDENCE_EXCLUDED_V1`;
3. if historical checkbox tokens occur only in migrated completion evidence, normalize exact `[ ]` and `[x]` tokens to `[ ]`; task workflow checkboxes elsewhere are forbidden.

Compute SHA-256 over `VesperCode\0PLAN_SEMANTIC_CONTRACT_V1\0` followed by projected UTF-8 bytes. Status, allowed checkbox state, and one-line completion evidence mutations must preserve the digest. Goal, legacy mapping, SPEC contracts, Files, Depends, TDD contract, verification, review, Done, traceability, gate, workflow, wave, or audit-contract mutations must change it. Missing/duplicate/reversed boundaries, BOM, or CR must reject.

### 8.3 Independent agreement and identity binding

Verifier A and B may share only this prose contract and exact inputs; they must use independent source implementations and parsing routes. Each result binds:

- verifier source SHA-256;
- complete PLAN and SPEC SHA-256;
- both course-file SHA-256 values;
- authoritative `AGENTS.md` SHA-256;
- Git HEAD;
- `PlanSemanticDigestV1`;
- all counts, edge/wave metrics, coverage metrics, format limits, issue lists, and verdict.

All fields except the intentionally different verifier-source SHA must agree exactly. Any parser ambiguity, missing proof, exception, identity drift, issue, disagreement, or failed metamorphic test is FAIL. Mechanical PASS does not satisfy M0, either independent design review, human identity approval, or cold-start.
