# Superseded PLAN history

> This file preserves former PLAN appendices for process history. The contents are non-normative and are not part of the current implementation handoff or cold-start input.

## Appendix A. Superseded admission-gate design (historical, non-normative)

> The retired admission-gate paragraphs in this appendix record an earlier project-specific design. They are retained for process history only and are not requirements, prerequisites, acceptance criteria, or instructions for the cold-start Agent. The current normative process is §1, the current task-card contract in §8, and the execution handoff in §9; subsequent non-appendix sections remain current unless explicitly marked historical.

**Document status:** Candidate — this line records no admission decision; formal approval exists only when every §1.2 artifact passes for the exact unchanged identities.

### 1.1 Authoritative Planning Inputs

The following identities define the exact repository inputs used to author and mechanically audit this PLAN candidate. They establish candidate provenance only; they are not human approval, admission, or execution evidence. The complete PLAN SHA-256, the computed `PlanSemanticDigestV2` value, and the future commit containing this revision remain in the external review or approval record so this document does not identify itself recursively.

| Field | Value |
|---|---|
| Authoritative SPEC path | `SPEC.md` |
| Authoritative SPEC SHA-256 | `556fb14ec8dc6c22834d1611f721316559600fd0bc2f6823ee8cfa7812c23ca8` |
| Authoritative SPEC Git blob | `23ff5eb32b87f0d48c011a7535094cf7345bb451` |
| Planning input baseline Git HEAD | `cf4bcabcb6409f5e7b4210388742c200f2e8603a` |
| General course requirements path | `AI4SE_Final_Project_通用要求.md` |
| General course requirements SHA-256 | `ee0c5770847ed34caf22c62fa183a6787318a3dcbbfe863a5b06de1f53704220` |
| Harness requirements path | `AI4SE_Final_Project_A_Coding_Agent_Harness(1).md` |
| Harness requirements SHA-256 | `6c225b996302bdbe0736c4327617b99ac7575198d0537c8a19b4bb7bc2620d81` |
| Repository instructions path | `AGENTS.md` |
| Repository instructions SHA-256 | `f4e68e302cfb9cc9f383704ef3be9eb8975277a0715e5357e65070cad2738656` |
| Repository instructions provenance | Tracked planning input; contained in the planning baseline commit. |
| Initial generation timestamp | `2026-07-26T17:17:01+08:00` |
| Last semantic revision timestamp | `2026-08-02T14:49:15+08:00` |

This PLAN is the self-contained implementation plan for the exact current SPEC and the sole canonical source for executable task steps. It does not change product scope, behavior, security boundaries, non-goals, or acceptance criteria. The 141 legacy child IDs remain immutable atomic TDD microcycles and migration-trace identifiers. The 68 `TNN.X` session tasks are fresh-subagent execution/review/commit slices, not independent PR tasks. The 46 `WP...` work packages are the `AGENTS.md` independent features / independent tasks and the sole branch/worktree/PR units.

Implementation is forbidden until all gates below pass in order for the exact unchanged input identities:

1. `SPEC_M0`: independent readiness review of exact SPEC bytes and product/design completeness.
2. `PLAN_AUDIT_V3_A` and `PLAN_AUDIT_V3_B`: independently implemented mechanical audits agree on all normative metrics, identities, issues, and semantic digest.
3. `PLAN_SPEC_COMPLIANCE`: independent design-document review confirms no requirement, behavior, security invariant, non-goal, or acceptance condition was weakened.
4. `PLAN_EXECUTABILITY`: independent execution-document review confirms each session task is self-contained and feasible in one fresh-agent session.
5. Human identity approval of exact SPEC SHA-256, PLAN complete-file SHA-256, `PlanSemanticDigestV2`, course inputs, `AGENTS.md`, and Git HEAD.
6. Heterogeneous no-history cold-start retrieval and representative execution trial.
7. `APPROVED_DOCUMENT_BASELINE_V3`: commit the exact approved bytes, the immutable repository-contained admission evidence, and the non-self-referential baseline record in three ordered commits; prove the implementation base is the clean third commit.

All prior M0, PLAN audit, review, approval, cold-start, and baseline results are invalid after this non-tracking SPEC/PLAN rewrite. No embedded statement in this document is admission evidence.

### 1.2 Admission Gate Execution Contract

The seven gates above use the single contract in this section. The sole formal evidence root is the tracked repository path `process/evidence/admission-v3/` joined with the lowercase complete-file SHA-256 of the candidate `PLAN.md`. Tools may stage uncommitted working artifacts under `.worktrees/_review-packages/admission-v3/`, but no PASS decision, process registration, baseline, or verifier input may cite that temporary tree; the byte-identical accepted artifacts must be promoted into the formal root before baseline materialization. Every artifact uses strict UTF-8 JSON with repository-relative input paths and exact candidate identities. `manifest.json` records the relative path, byte length, and complete-file SHA-256 of the ten accepted pre-baseline artifacts other than itself; it does not list itself or the later `baseline.json`. An artifact may carry a `content_digest` computed over canonical JSON with that field omitted; no file embeds its own complete-file SHA-256.

| Gate | Authority and exact inputs | Independence | PASS predicate | Evidence artifact |
|---|---|---|---|---|
| `SPEC_M0` | SPEC §11.2; authoritative SPEC bytes/path/blob, both course files, repository `AGENTS.md`, and planning HEAD | One fresh reviewer session whose id is absent from the recorded SPEC author/fixer ids; the human performs the identity approval required by SPEC §11.2 | Every §11.2 item passes, no unresolved identity or requirement conflict exists, and the human approves the exact SPEC path/SHA/blob/HEAD | `m0.json` |
| `PLAN_AUDIT_V3_A` / `PLAN_AUDIT_V3_B` | PLAN §8; exact PLAN/SPEC/course/AGENTS bytes and Git HEAD | Independent source implementations and private negative self-tests | Both decisions are `PASS`, both issue lists are empty, and all result fields except verifier source SHA-256 agree | `plan-audit-a.json`, `plan-audit-b.json` |
| `PLAN_SPEC_COMPLIANCE` | `PlanReviewChecklistV1` with `review_kind=PLAN_SPEC_COMPLIANCE`; exact candidate identities and both A/B result SHA-256 values | One fresh no-history reviewer session, not a recorded PLAN/SPEC author or fixer and distinct from the executability reviewer | All `PSC-01`—`PSC-06` checks pass, the result identities match the candidate and A/B, and no Critical or Important finding remains open | `plan-spec-compliance.checklist.json`, `plan-spec-compliance.result.json` |
| `PLAN_EXECUTABILITY` | `PlanReviewChecklistV1` with `review_kind=PLAN_EXECUTABILITY`; exact candidate identities and both A/B result SHA-256 values | A second fresh no-history reviewer session, not a recorded PLAN/SPEC author or fixer, distinct from the compliance reviewer, and unable to read that review before issuing its own result | All `PEX-01`—`PEX-06` checks pass; PEX-04 evidence contains exactly one complete ordered assessment for each of the 68 session tasks, including explicit T04.2/T05.1/T09.1/T12.1 load evidence; the result identities match the candidate and A/B; and no Critical or Important finding remains open | `plan-executability.checklist.json`, `plan-executability.result.json` |
| Human PLAN identity approval | Exact SPEC SHA-256/blob, PLAN complete-file SHA-256, `PlanSemanticDigestV2`, both course-file SHA-256 values, AGENTS SHA-256, Git HEAD, A/B SHA-256 values, and both independent review-result SHA-256 values | Only the human may issue this decision; an agent may serialize but never infer or fabricate it | `approver_kind=human`, `decision=APPROVE`, every identity equals the preceding PASS evidence, and the approval timestamp follows both reviews | `human-approval.json` |
| Heterogeneous no-history cold-start | Exact human-approved inputs plus the retrieval and disposable-execution contracts below | One fresh agent type different from the PLAN authoring agent type, with no conversation, memory, prior review, or generated-result context beyond the exact approved inputs and this contract | Both cold-start artifacts return `PASS`; every listed failure condition remains false | `cold-start-retrieval.json`, `cold-start-execution.json` |
| `APPROVED_DOCUMENT_BASELINE_V3` | All preceding PASS artifacts from the tracked formal evidence root, the approved identities, and Git committed-tree facts | Mechanical committed-tree and ancestry validation; no agent judgment may substitute for Git facts | The approved-document, admission-evidence, and baseline-record commits satisfy the three-commit relation below, the formal base is the clean baseline-record commit, and the candidate semantic/SPEC/AGENTS identities remain exact | `baseline.json` |

`PlanReviewChecklistV1` has these ordered required fields:

```text
schema_version, review_kind, candidate_plan_complete_file_sha256, candidate_plan_semantic_digest_v2, candidate_spec_sha256, candidate_spec_git_blob, candidate_git_head, verifier_a_result_sha256, verifier_b_result_sha256, reviewer_id, reviewer_session_id, reviewer_agent_type, author_or_fixer_ids, independent_from, started_at, completed_at, checks, findings, content_digest
```

Each checklist `check` has ordered fields `check_id`, `status: PASS | FAIL`, and nonempty `evidence`. Each `finding` has ordered fields `finding_id`, `severity: Critical | Important | Minor`, `location`, `statement`, `evidence`, `required_change`, `status: OPEN | CLOSED`, `resolution`, and `closure_evidence`. A closed finding requires nonempty resolution and closure evidence; an open finding requires both to be empty. Finding ids are unique within one review and remain stable across repair/re-review.

For `PEX-04` only, `evidence` is an ordered array of exactly 68 objects in Session Task Cards order with fields `task_id`, `estimated_elapsed_minutes` as a positive integer, nonempty `context_load_assessment`, `required_external_environment` as an array, `decision: PASS | FAIL`, and nonempty `rationale`. Task ids are unique and complete. The T04.2, T05.1, T09.1, and T12.1 rationales explicitly account for their displayed legacy-step and checkbox loads. Any `FAIL` blocks PLAN_EXECUTABILITY and identifies the task for amendment; a required split stays inside the existing work package unless independent file ownership and PR acceptance require a new work-package boundary.

`PlanReviewResultV1` has these ordered required fields:

```text
schema_version, review_kind, candidate_plan_complete_file_sha256, candidate_plan_semantic_digest_v2, candidate_spec_sha256, candidate_spec_git_blob, candidate_git_head, verifier_a_result_sha256, verifier_b_result_sha256, checklist_sha256, reviewer_id, reviewer_session_id, reviewer_agent_type, open_critical_count, open_important_count, open_minor_count, decision: PASS | FAIL, content_digest
```

A `PlanReviewResultV1` is `PASS` only when its checklist has no missing/failed check, its identities and reviewer fields exactly match the checklist and candidate, reviewer independence is proven, and both `open_critical_count` and `open_important_count` are zero. Minor findings may remain open but must be preserved in the checklist and counted; they never erase or close themselves.

The compliance checklist is exactly:

- `PSC-01`: all SPEC requirements, user stories, FR/NFR and AC rows retain implementation and independent validation coverage.
- `PSC-02`: product behavior, security boundaries, non-goals and acceptance conditions are not weakened or silently expanded.
- `PSC-03`: PLAN interfaces and implementation points do not conflict with SPEC observable semantics.
- `PSC-04`: no shared cross-session semantic contract exists only in PLAN when SPEC must own it.
- `PSC-05`: ownership, dependencies, traceability and review/verification gates preserve SPEC constraints.
- `PSC-06`: every finding is location-bound, evidenced, severity-classified and truthfully open or closed.

The executability checklist is exactly:

- `PEX-01`: all 68 session tasks contain every field and closure step required by §8.1.
- `PEX-02`: every task's displayed interfaces, RED, minimum GREEN, Target, Domain, review and Done conditions are mutually executable.
- `PEX-03`: a fresh agent needs no undisclosed cross-task design decision, file, command, credential or environment fact.
- `PEX-04`: each session task fits one fresh-agent session, proven by the complete per-task time/context/environment/rationale evidence above; independently acceptable/rejectable implementation behavior is split into session-task execution slices without creating another independent PR task unless it also requires an independent work-package boundary.
- `PEX-05`: work-package boundaries, file ownership, dependencies and parallelization produce no integration ambiguity or hidden long-lived branch dependency.
- `PEX-06`: every non-`Expected` command in an `Atomic verification` block is complete, directly runnable in its declared environment, mapped to the displayed verification expectation, and bound exactly once to one of: (a) a verbatim ordered executable checkbox before `Done`; (b) one explicitly named global verification profile command; or (c) one centrally declared mandatory derived action such as `MATRIX-RED-1`, `MATRIX-RED-2`, or a named non-task final-gate step. Missing, duplicate, ambiguous, non-verbatim, or unresolved bindings are `FAIL`. The binding key is (`task_id`, `legacy_id`, `atomic_label`), not the raw command string: repeated RED, GREEN, refactor, review, or evidence reruns are execution evidence, not additional binding declarations. A checkbox binding must target the unique role-matched ordered checkbox (`Run <legacy> Target GREEN`, `Run <legacy> Domain`, or a named remaining-Atomic checkbox) containing the exact command; duplicate canonical targets or unresolved role matches are `FAIL`.

Cold-start uses exact fixed probes. Retrieval requires the fresh agent to locate `T01.1` and `T38.2` and restate their Goal, SPEC contracts, Files, Depends, Interfaces, execution order, verification, review focus, Done, work-package boundary, and applicable Global Constraints without an Important or Critical omission. For `T01.1`, it must distinguish the 1.A pre-RED bootstrap contract from the 1.B RED/minimum-GREEN behavior cycle. Disposable execution starts `T01.1` from the exact approved candidate in an isolated throwaway worktree, completes and verifies 1.A before adding or running the 1.B RED, then performs the 1.B TDD cycle and task verification. It records bootstrap, review, RED, implementation, verification, and projected review/evidence administration time, and creates no production merge or completion claim. The hard elapsed-time limit is two hours; reaching it stops the trial and returns `FAIL`. Any missing contract, hidden context dependency, incorrect order or RED, Critical/Important constraint omission, verification failure, or inability to complete `T01.1` within the limit also returns `FAIL`.

The approved-document baseline relation is:

```text
approved_document_commit
  -> admission_evidence_commit
       -> baseline_record_commit
            == clean formal_base
                 -> T01.1 work-package branch/worktree
```

`approved_document_commit` contains the exact M0-approved SPEC raw SHA/blob, human-approved PLAN raw SHA/semantic digest, and approved `AGENTS.md` blob/SHA-256. Its direct `admission_evidence_commit` preserves every approved input byte; adds only `manifest.json` and the ten fixed accepted pre-baseline JSON artifacts under the deterministic formal evidence root; and changes only `SPEC_PROCESS.md` and `AGENT_LOG.md` outside that root to register the repository-relative paths/digests, human decision, cold-start result, and approved-document commit. Its direct `baseline_record_commit` preserves all prior bytes and adds only `baseline.json` under the same root. `baseline.json` binds `approved_document_commit`, `admission_evidence_commit`, the manifest SHA-256, every candidate SPEC/PLAN/semantic/course/AGENTS identity, and the fixed artifact digests; it neither records its own complete-file SHA-256 nor embeds `baseline_record_commit`. Mechanical validation derives the baseline-record identity from the current clean `HEAD`, requires `HEAD^ == admission_evidence_commit` and `HEAD^^ == approved_document_commit`, and proves that the two commit diffs contain only the allowed paths above. Task 1 starts only from a clean worktree whose HEAD equals `baseline_record_commit`; a working-file match, descendant with intervening changes, dirty tree, sibling, uncommitted copy, missing tracked artifact, or evidence reachable only through `.worktrees` fails the gate.

Gate invalidation is closed:

| Change | Required rerun |
|---|---|
| Only task Status, task checkbox state, or one-line Completion evidence changes under §8.3 | No admission gate; record the new complete-file PLAN SHA while preserving the semantic digest |
| Any other PLAN byte changes | A/B, both independent PLAN reviews, human PLAN approval, both cold-start probes, and baseline |
| SPEC path/bytes/blob, either course file, or applicable AGENTS bytes change | M0 and every subsequent gate |
| Either verifier source or result changes | A/B and every subsequent gate |
| Either review schema, checklist, result or reviewer-independence fact changes | Both independent PLAN reviews and every subsequent gate |
| Any admission artifact is corrected, replaced, missing, inaccessible, or identity-mismatched | That gate and every subsequent gate |
| Any semantic change after baseline materialization | Baseline is invalid immediately; no Task 1 work may start or continue |

Absence of a formal artifact, schema/order mismatch, invalid digest, untracked or repository-external formal evidence, `.worktrees` formal input, path escape, inaccessible evidence, reviewer-identity conflict, open Critical/Important finding, stale candidate identity, non-`PASS`/non-`APPROVE` decision, failed cold-start probe, or baseline ancestry/cleanliness mismatch fails closed. `SPEC_PROCESS.md` records every attempt truthfully, but only the accepted formal set may be registered as gate input with exact repository-relative paths/digests; failed or pending attempts remain chronological history and never become formal PASS inputs. `AGENT_LOG.md` records the chronological action without converting a failed or pending gate into success.

## Appendix B. Superseded PlanAuditContractV3 (historical, non-normative)

> The following text records an earlier project-specific admission and audit design. It is retained for process history only. It is not a requirement, prerequisite, acceptance criterion, or instruction for the cold-start Agent. The current normative contract is §1, §8, and §9.

### 8.1 Writing-plans conformance

Verifier A/B independently require the exact `For agentic workers` header, root Goal, Architecture, Tech Stack, Global Constraints, Planned Repository Structure, Global Execution Contract, Work Package Registry, Milestone Registry, 68 Session Task Cards, Unified Traceability, Derived Waves, this audit contract, and Execution Handoff.

`Units and authority` appears exactly once and defines: work package = the `AGENTS.md` independent feature / independent task and sole branch/worktree/PR/finishing/merge unit; session task = the smallest fresh-subagent execution/review/commit slice inside one work package and not an independent PR task; behavior legacy step = one atomic RED → minimum GREEN TDD microcycle inside a session task; `1.A` alone = the SPEC-required reviewed pre-RED gate bootstrap. The workflow and handoff must preserve one PR per work package and must never assign an independent branch, worktree, PR, finishing pass, or merge to a session task.

Every session task contains Status, Work package, Legacy steps, Goal, SPEC contracts, Files, Depends, Parallelization, Interfaces, Implementation points/exact RED/minimum GREEN contracts, task-level verification/review/completion steps, Done, and one-line Completion evidence. Every task has task-specific checkbox steps and one exact commit command block.

All 141 legacy steps are mapped exactly once. Legacy `1.A` alone contains the SPEC §11.2 pre-RED bootstrap contract, complete ordered bootstrap commands, positive integrity verification, review focus, and checkboxes proving completion before `1.B`. Every other legacy subsection contains an Atomic goal, nonempty Minimum GREEN patch contract, exact executable RED test code, stable Expected RED reason, Target and Domain commands, Atomic review focus, and checkbox actions for RED, each displayed GREEN implementation point, Target GREEN, and Domain verification. `DECLARED_RED_TARGETS_V1(L)` is the ordered set of every displayed test function or unittest method whose name starts with `test_` in a behavior legacy step's Exact RED and explicitly named staged RED code blocks. Every member must be selected by an exact `Run <Legacy> RED` checkbox command before the first GREEN implementation; first selection only by Atomic verification, Target GREEN, or Domain does not count. An explicitly declared staged RED may follow only its named runner/bootstrap prerequisite GREEN, must name the first protected behavior GREEN, and must have separate Add and Run RED checkboxes strictly between those two actions; the prerequisite action may not implement any symbol, behavior, or assertion consumed by the staged test. For every subsection listed in the Exact Boundary Matrix Registry, its effective action sequence also contains exactly one Registry-derived `MATRIX-RED-1` and exactly one `MATRIX-RED-2` after `Run <Legacy> RED` and before the first GREEN implementation. No code step may refer to an undefined "above", "similar" task, later boundary matrix, deferred implementation, or unexpanded placeholder.

The implementation-coordination Interfaces in PLAN bind exact names/signatures for this approved implementation without overriding SPEC semantics. Cross-session observable behavior, fields, serialization, identity, state, errors, and side effects remain governed by SPEC. Any PLAN interface conflict with SPEC fails; any new shared semantic contract requires SPEC revision and renewed M0.

Every non-`Expected` command in every `Atomic verification` block is mechanically enumerated by Verifier A and Verifier B. Each command must resolve to exactly one checkbox, profile-command, or derived-action binding; the private negative self-tests include removal, duplication, reordering, ambiguity, and weakening of any such binding. `MATRIX-RED-1`/`MATRIX-RED-2` and named non-task final-gate steps are centrally declared derived actions and are not required to be repeated as task-card checkboxes. Binding resolution uses the (`task_id`, `legacy_id`, `atomic_label`) key and the role-matched canonical checkbox; repeated RED/GREEN/refactor/review/evidence reruns do not count as additional bindings.

### 8.2 Mechanical invariants

Two independently implemented verifiers read strict UTF-8 and fail on BOM, any CR byte, invalid decoding, or other than exactly one final LF. PLAN is at most 1,572,864 bytes and 180,000 whitespace-delimited words. Each session task is at most 65,536 UTF-8 bytes and 8,000 words. These caps control representation size; they never authorize omission or placeholders.

`Authoritative Planning Inputs` appears exactly once and contains every required nonempty field with repository-relative paths. Each declared SHA-256 must equal the current bytes at its declared path. The declared SPEC Git blob must equal both `git hash-object SPEC.md` and the `SPEC.md` blob tracked by the planning input baseline. The baseline commit must exist and be the verifier HEAD or its ancestor. The repository-instructions provenance must state when that working-tree input is not contained in the baseline commit. Both timestamps must be strict, timezone-bearing ISO-8601 values, and the last semantic revision must not precede initial generation. The identity table must not contain the complete PLAN SHA-256, an actual `PlanSemanticDigestV2` value, or a future commit claimed to contain the revision.

`Admission Gate Execution Contract` appears exactly once and contains the seven ordered gates, exact evidence-root derivation and filenames, both ordered review schemas, both six-item checklists, the complete 68-task PEX-04 evidence contract, reviewer-independence and PASS predicates, fixed `T01.1`/`T38.2` cold-start retrieval, disposable `T01.1` execution with a two-hour hard limit, the tracked formal evidence root and approved-document/admission-evidence/baseline-record three-commit relation whose baseline-record commit is the clean formal base, and the closed invalidation matrix. Verifier A/B validate only that this executable contract is structurally complete; they never infer that a human decision or an external admission artifact exists or passed.

The exact retained graph metrics are 68 session tasks, 141 unique legacy steps, 46 work packages, 309 deduplicated session edges, 42 session waves, 263 deduplicated package edges, 26 package waves, zero cycles, and 55 unified trace rows. Requirement coverage remains 9 US, 9 FR, 6 NFR, and 31 AC rows, each with nonempty independent implementation and validation task sets.

Milestone Registry invariants are closed:

1. The exact heading `### 4.1 Milestone Registry` appears exactly once.
2. The Registry contains exactly one header row, one separator row, and 38 single-line data rows.
3. Milestone ids are exactly the ascending sequence 1 through 38.
4. Each row contains the Milestone id plus exactly four nonempty fields: Goal, SPEC scope, Session tasks, and Aggregate completion.
5. Every session task appears in exactly one Milestone row.
6. Every session task's legacy steps resolve to one and only one Milestone id.
7. Legacy `13` resolves to Milestone 13; every `N.X` resolves to Milestone N.
8. Row N's Session tasks equal the complete task-card-derived task set for N in Session Task Cards order.
9. Row N's Goal equals `MILESTONE_GOAL_V1(N)` byte-for-byte after the sole Markdown `\|` escape is decoded.
10. Row N's SPEC scope equals `MILESTONE_SPEC_SCOPE_V1(N)` byte-for-byte after the same decoding.
11. Aggregate completion is exactly `MILESTONE_COMPLETE_V1(N)`.
12. The Registry contains no Files, Depends, ownership, branch, worktree, PR, implementation, verification, independent acceptance, or new completion field.
13. Every textual `Milestone N` reference resolves to exactly one Registry row.
14. No Milestone id outside 1 through 38 is referenced.
15. Any missing, duplicate, reordered, remapped, mutated, unparsable, multiline, unescaped-pipe, abbreviated-task, ranged-task, or ellipsis-bearing row is `FAIL`.

The Registry syntax is mechanical: every data row is one Markdown line; an in-cell `|` is encoded only as `\|`; Session tasks use exact `, ` separators; every task id matches `T[0-9]{2}\.[0-9]+`; and ranges, aliases, ellipses, and natural-language abbreviations are forbidden. Verifier A/B recompute both derived text fields from task cards rather than trusting nonempty cells. They validate the predicate definitions and exact row expressions before execution; they do not treat current `Not started` tasks as completed.

Task-card Files remain the sole execution mutation ownership source. Planned Repository Structure describes responsibility and must include every task path without assigning a conflicting writer. Shared modifiers remain limited to the explicit table in the Global Execution Contract.

Commit-bound delivery ordering is closed. Every `CI_RELEASE_LIVE_V1` action must follow creation and push of its immutable subject commit; T35.1's remote job SHA must equal its Step 31 implementation SHA. T37.1 is the sole exception to task-owned subject creation and may start external work only after both WP36 and WP38 are finished and merged, freezing the exact current main commit as `source_commit`. The three external evidence JSON records are absent from every WP36 implementation/evidence commit and from every pre-T37.1 writer; T37.1 writes them only after terminal observations, and all three `source_commit` values, GitHub/GitLab CI job SHAs, protected tag target, released wheel source, GHCR image source, and Render deployment source equal that one SHA. Any post-source change under `src/**`, `.github/**`, `.gitlab-ci.yml`, `containers/**`, `render.yaml`, `pyproject.toml`, or `requirements/**` is `FAIL` and requires a new source commit plus complete final CI/publication/deployment restart.

Verifier A/B reject missing/duplicate tasks or legacy steps, missing or contradictory execution-unit terminology, a session task described as an independent/executable PR unit, missing fields or Interfaces, an incomplete 1.A pre-RED bootstrap/review/identity contract, any Task 1 behavior RED ordered before 1.A verification, missing RED or Minimum GREEN blocks for any behavior legacy step, missing checkboxes, missing Target/Domain/Matrix commands, unmapped RED or Matrix node ids, any member of `DECLARED_RED_TARGETS_V1(L)` omitted from the applicable pre-implementation RED command set, any ordinary RED target first selected at or after the first GREEN implementation, any staged RED without an exact prerequisite/protected-GREEN boundary, any staged Add/Run RED action embedded in an implementation checkbox or not strictly between the declared prerequisite and protected GREEN, or any prerequisite GREEN that implements behavior consumed by its staged test, any Registry row whose effective action order is not exactly `Run <Legacy> RED` < `MATRIX-RED-1` < `MATRIX-RED-2` < first GREEN implementation, any `MATRIX-RED-2` command whose pytest node does not equal that row's required node, any GREEN step that still makes a Registry Matrix test RED, an Expected RED/Run RED failure-class contradiction, a behavior RED command that consumes an interpreter, runner, script, lock, module, or artifact produced only by later implementation, incomplete or duplicate 114-row boundary coverage, missing/duplicate/malformed Milestone Registry data, non-derived Milestone Goal or SPEC scope, non-bijective task/Milestone mapping, unresolved Milestone reference, generic deferred-case language, malformed commands, a missing or descriptive-only `GATE_OFFLINE_V1` gate-scan command, missing Task 1 gate-scan ownership/staging or gate-toolchain SHA binding, clipped reviews, placeholders, undefined task references, unauthorized shared writes, a PLAN_EXECUTABILITY contract whose PEX-04 evidence does not enumerate all 68 unique task ids exactly once in Session Task Cards order with every required field or does not explicitly account for T04.2/T05.1/T09.1/T12.1 legacy-step and checkbox loads, a formal admission root outside tracked `process/evidence/admission-v3/` or whose child directory name differs from the approved PLAN complete-file SHA-256, any `.worktrees`, absolute, escaped, untracked, missing, or repository-external formal evidence input, a missing or self-referential manifest, any baseline relation other than the declared three commits, admission-evidence or baseline-record commit path drift, a self-referential `baseline.json`, `formal_base` unequal to the baseline-record commit, an approved AGENTS blob absent from the approved-document commit, remote-before-commit/push ordering, T35 implementation/job SHA mismatch, final-source freeze before WP36/WP38 merge, external evidence JSON owned or written before T37.1 terminal observations, disagreement among CI/release/deployment source identities, protected tag/wheel/GHCR/Render source mismatch, protected-path drift after final-source freeze, graph drift, coverage drift, incomplete admission contracts, oversized tasks/documents, and any forbidden source or identity mismatch.

### 8.3 PlanSemanticDigestV2

`PlanSemanticDigestV2` hashes the complete normalized PLAN document. The sole tracking-normalization window begins with the exact full line `## 5. Session Task Cards` and ends immediately before the exact full line `## 6. Unified Traceability`. Only inside that window:

1. each full-line `**Status:** ...` value to `TRACKING_STATUS_EXCLUDED_V2`;
2. every task-step checkbox token `[ ]` or `[x]` to `[ ]`;
3. each full-line `**Completion evidence:** ...` value to `TRACKING_EVIDENCE_EXCLUDED_V2`.

All bytes outside that window, including the complete `### 4.1 Milestone Registry`, are preserved byte-for-byte in the semantic projection. Input is no-BOM UTF-8; CRLF is normalized to LF and a bare CR is rejected. Compute SHA-256 over `VesperCode\0PLAN_SEMANTIC_CONTRACT_V2\0` followed by the complete projected PLAN UTF-8 bytes. Status, legitimate task checkbox state, and one-line completion evidence changes preserve the digest. Any Milestone Goal, Milestone SPEC scope, Milestone Session tasks order/membership, aggregate-completion expression, Goal, file, interface, implementation point, RED/GREEN code, command, dependency, review, traceability, wave, workflow, header, constraint, or audit-contract change must change it.

### 8.4 Independent agreement and identity binding

Verifier A and Verifier B use independent implementations and private negative self-tests for: missing required header; removed or contradictory work-package/session-task/legacy-step terminology; injected one-PR-per-session-task wording; removed Interfaces or checkbox; removed or reordered the 1.A pre-RED bootstrap/review/identity steps; moved any Task 1 behavior RED before 1.A verification; removed the exact `GATE_OFFLINE_V1` PowerShell gate-scan command, Task 1 gate-scan ownership/staging, or gate-toolchain gate-scan SHA binding; removed RED code or Minimum GREEN contract from a behavior legacy step; removed the 7.D schema-owner node from its pre-GREEN RED command; removed the 38.F CLI-production node from its pre-GREEN RED command; embedded either 4.A post-bootstrap Add/Run RED action back inside an implementation checkbox; moved the 4.A post-bootstrap Run RED before its bootstrap prerequisite or at/after its protected closure GREEN; changed the 4.A prerequisite GREEN to implement a staged-test symbol; injected Expected RED/Run RED failure-class contradiction; changed a behavior RED command to consume an interpreter, runner, script, lock, module, or artifact produced only by later implementation; injected placeholder; generic deferred-case language; removed, duplicated, or malformed 114-row Boundary Matrix Registry entry; removed, duplicated, moved after the first GREEN, or reordered `MATRIX-RED-1`/`MATRIX-RED-2`; retained a GREEN step that makes a Registry Matrix test RED; removed, duplicated, reordered, remapped, truncated, multiline, unescaped-pipe, abbreviated-task, ranged-task, ellipsis-bearing, or otherwise malformed Milestone Registry entry; changed Milestone Goal or SPEC scope byte; changed Milestone Session tasks order or membership; changed aggregate-completion expression; task omitted from or duplicated across Milestones; mixed legacy prefixes within one task; unresolved or out-of-range Milestone reference; removed Matrix command; Matrix node mismatch; missing exact oracle; leading-quote/truncated command; removed Domain; RED/Target mismatch; clipped review; graph/coverage mutation; removed one task from, duplicated one task in, reordered, removed a required field from, or inserted a nonpositive time estimate into the PEX-04 evidence contract; removed explicit T04.2, T05.1, T09.1, or T12.1 legacy-step/checkbox-load treatment; replaced the tracked formal admission root with `.worktrees`, an absolute path, an escaped path, or an untracked path; removed or self-included a manifest entry; inserted `baseline.json` into the pre-baseline manifest; collapsed or reordered the approved-document/admission-evidence/baseline-record relation; widened either evidence-commit allowed-path diff; embedded the baseline record's own file hash or commit; changed `formal_base` away from the baseline-record commit; removed the approved AGENTS blob from the approved-document commit; removed the T37.B untracked-worktree RED node from its pre-GREEN Target; remote CI/release/Render action before subject commit or push; T35 remote SHA changed away from its implementation SHA; old-CI/new-tag source mismatch; external evidence JSON inserted into a WP36 implementation/evidence commit or written before T37.1 terminal observations; Render deployment before WP36 and WP38 merge; disagreement among the three evidence `source_commit` values; protected tag, released wheel, GHCR, or Render source mismatch; protected-path drift after `source_commit`; missing or duplicated planning-input identity; changed identity path, SHA-256, SPEC blob, baseline, provenance, or timestamp; forbidden self-referential PLAN identity; missing admission gate/schema/checklist/evidence path; changed cold-start task/time limit; broken baseline relation or invalidation coverage; semantic-digest tracking and non-tracking mutations, including proof that every Milestone Registry semantic mutation changes `PlanSemanticDigestV2`.

Each result binds PlanAuditContractV3, PLAN/SPEC/course/AGENTS SHA-256 identities, Git HEAD, verifier source SHA-256, PlanSemanticDigestV2, every metric above, sorted issues, and PASS/FAIL. Results agree field-for-field except verifier source SHA-256 and are evidence only for their exact unchanged inputs.

## Appendix C. Superseded Task T37.1 (historical, non-normative)

> The following former T37.1 card is retained only as process history. It is not a current task contract and its admission, review, identity, or baseline requirements must not be followed.

**Status:** Not started
**Work package:** WP37
**Legacy steps:** 37.A, 37.B
**Goal:** Execute one final source-aligned live delivery closure against the exact current main `source_commit` frozen after both WP36 and WP38 are finished and merged: require complete GitHub/GitLab CI for that SHA, publish the protected tag/Release/GHCR artifacts, deploy the same source/image/config to Render, and write the three external evidence JSON records only from terminal-aligned facts.；Write an accurate user-facing README for installation, operation, security, recovery, distribution, CI/release/deployment, limitations, and non-goals using only verified current evidence.；Complete truthful append-preserving `SPEC_PROCESS.md` and `AGENT_LOG.md` records and fail-closed verification for the course document check, disposable cold-start trial and findings/revisions, every executable task, review, intervention, commit, PR, failure, and lesson.
**SPEC contracts:** SPEC §1.6; §5.3–§5.6; §8.1–§8.4; §10.1 AC-01–AC-31; §10.3; §11.3; course required artifacts, process evidence, README, CI/CD, WebUI URL, and reflection rules; `AGENTS.md` final-report rules.

**Files:**
- Create: `delivery/evidence/ci-v1.json`
- Create: `delivery/evidence/release-v1.json`
- Create: `delivery/evidence/deployment-v1.json`
- Create: `README.md`
- Create: `scripts/verify_readme_contract.py`
- Create: `tests/unit/process/test_readme_contract.py`
- Create: `scripts/verify_process_evidence.py`
- Read: `SPEC.md`
- Read: `PLAN.md`
- Read: `SPEC_PROCESS.md`
- Read: `AGENT_LOG.md`
- Read: `config/dependency-closure-v1.json`
- Read: `config/formal-toolchain-promotion-v1.json`
- Modify: `SPEC_PROCESS.md`
- Test: `tests/unit/process/test_delivery_evidence.py`

**Depends:** T01.1, T01.2, T02.3, T02.4, T03.1, T03.2, T04.1, T04.2, T05.1, T06.4, T07.3, T07.4, T08.1, T09.1, T10.1, T10.2, T11.1, T12.1, T13.1, T14.1, T15.1, T15.2, T16.1, T17.1, T18.1, T18.2, T19.1, T20.1, T20.2, T21.1, T22.1, T23.1, T24.1, T25.1, T25.2, T25.3, T26.1, T26.2, T27.1, T28.3, T29.3, T30.1, T30.2, T31.1, T32.1, T33.1, T34.1, T34.2, T35.1, T36.3, T38.1, T38.2, T38.3
**Parallelization:** Start only after every task/non-task gate in **Depends** has passed. Same-wave execution is allowed only when expanded writable paths are disjoint; the WP37 branch and PR remain the sole package integration boundary.

**Interfaces:**
- **Consumes / Produces (T37.1 live closure):** Consumes the exact current main commit after both WP36 and WP38 are finished and merged as the existing shared `source_commit`, the committed T35/T36 CI/release/Render contracts, the final GitHub three-job and GitLab four-job terminal results for that SHA, the final-source wheel/checksum, Task 2/34 manifest identity, and confirmed Render observations. Produces `delivery/evidence/ci-v1.json`, `delivery/evidence/release-v1.json`, and `delivery/evidence/deployment-v1.json` whose existing `source_commit` values are byte-identical; adds no new evidence-schema field. Before any evidence write, the protected tag equals that SHA, publication verification is `ACCEPTED`, Render reports that SHA and exact image/config, and `git diff` from `source_commit` rejects changes under `src/**`, `.github/**`, `.gitlab-ci.yml`, `containers/**`, `render.yaml`, `pyproject.toml`, or `requirements/**`.
- **Consumes / Produces (37.A):** Produces `verify_readme_contract(path: Path) -> ReadmeContractResultV1` plus the exact documented commands/URLs/digests and section contract enumerated by Milestone 37.
- **Consumes / Produces (37.B):** Consumes the current `SPEC.md` and `PLAN.md`, `SPEC_PROCESS.md`, `AGENT_LOG.md`, the terminal `gates/evidence/workspace-boundary-go-v1.json`, dependency/toolchain records, and task/review/commit/PR evidence. Produces `ProcessEvidenceResultV1` through a read-only, fail-closed process-record checker; it executes no repository code and does not create a separate admission or approval artifact.

**Implementation points, exact RED, and minimum GREEN contracts:**

#### Legacy step 37.A: Verified README

**Atomic goal:** Write an accurate user-facing README for installation, operation, security, recovery, distribution, CI/release/deployment, limitations, and non-goals using only verified current evidence.

**Minimum GREEN patch contract:**

```text
Owned files: - Create: README.md - Create: scripts/verify_readme_contract.py - Create: tests/unit/process/test_readme_contract.py
Interface: Produces `verify_readme_contract(path: Path) -> ReadmeContractResultV1` plus the exact documented commands/URLs/digests and section contract enumerated by Milestone 37.
GREEN-1: Derive every README installation, usage, secure-key, recovery, distribution, CI/release, GHCR, Render, directory, limitation, and non-goal statement from the exact completed task evidence and current package interfaces.
GREEN-2: Implement `verify_readme_contract` as a deterministic document check for the required sections, exact command forms, referenced artifact identities, security boundaries, and prohibited compatibility or capability overclaims.
GREEN-3: Make `test_readme_fails_when_release_digest_verification_is_missing` GREEN by requiring actionable reference-image digest verification instructions tied to the real released content identity.
GREEN-4: Own user-facing documentation and its static verifier only. New capability, result fabrication, process-history rewriting, reflection authorship, and substitution of planned values for missing external evidence remain out of scope.
Boundary: No new capability, compatibility promise, exception, or invented external result may appear. Commands must match installed/package/live evidence.
```

**Exact RED test code:**

```python
def test_readme_fails_when_release_digest_verification_is_missing(
    repository_copy: Path,
) -> None:
    write_readme_without_section(repository_copy, "Reference image digest verification")
    result = verify_readme_contract(repository_copy / "README.md")
    assert "README_REFERENCE_DIGEST_INSTRUCTIONS_MISSING" in result.error_codes
```

**Expected RED:** the test runner reaches `test_readme_fails_when_release_digest_verification_is_missing`, but its first task-owned assertion fails because requiring actionable reference-image digest verification instructions tied to the real released content identity has not been implemented; collection, runner startup, unrelated import, or environment failure does not count

**Atomic verification:**
- Target (37.A): `python -m pytest -q tests/unit/process/test_readme_contract.py::test_readme_fails_when_release_digest_verification_is_missing`
- Domain (37.A): `python -m pytest -q tests/unit/process/test_readme_contract.py`
- Expected (37.A): all required sections, exact commands, real links/digests, threats/limitations/non-goals, and no overclaim pass.

**Atomic review focus:**
- SPEC (37.A): Spec compliance review checks Task 37.A's Goal, Milestone 37's four-field aggregate and SPEC scope, this Implementation boundary, exact RED, and Verification as one consistent verified-README contract.
- Quality (37.A): Code quality review checks section completeness, exact executable commands, package/source/URL identity, content digests, evidence freshness and access control, credential/threat/recovery limitations, wording accuracy, and absence of invented outcomes or compatibility promises.

- [ ] **Step 1: Freeze the final delivery source commit.** Start only after both WP36 and WP38 are finished and merged. Check out the exact current main commit containing all prerequisite product/runtime, CI, image, publication-verifier, and `render.yaml` changes; require a clean tree, record that 40-hex SHA as the sole existing-schema `source_commit`, and reject a branch-only, unmerged, mutable, or evidence-derived substitute.
- [ ] **Step 2: Run final dual-platform CI for `source_commit`.** Require the GitHub main push run's exact `unit-test`, `reference-image-build`, and `demo-image-build` jobs and the GitLab main pipeline's exact `unit-test`, Windows `wheel-build-smoke`, `reference-image-build`, and `demo-image-build` jobs to report the Step 1 SHA, terminal PASS, accessible URLs/ids, final-source wheel/checksum, Task 2/34-aligned image digests, and no release credential in ordinary jobs. Missing, skipped, stale, different-SHA, inaccessible, or non-terminal results stop before any publication.
- [ ] **Step 3: Execute the one protected Release/GHCR publication.** Require the protected tag, GitLab release context, GitHub tag lookup, Step 2 CI records, and final-source wheel to identify the exact Step 1 SHA before checking protected secrets or mutating externally. Publish once without retry after uncertain state; independently download/re-hash/clean-install the wheel, push the frozen Task 2/34 manifest/blobs, pull GHCR by RepoDigest, inspect/smoke it, and require the committed T36.2 `verify_release_publication_result` to return `ACCEPTED`.
- [ ] **Step 4: Execute the exact Render deployment.** Deploy only the Step 1 main `source_commit` through the committed T36.3 `render.yaml` and exact Task 34.B Demo image/config; require the reported deployment source SHA and image digest to match, then confirm terminal public URL, bounded cold start, `/healthz`, fixed Mock scenario, simulation label, session isolation, and absence of formal/local/recovery capabilities. Missing, failed, partial, stale, or mismatched state stops without evidence writing.
- [ ] **Step 5: Write and verify the three external evidence records.** Create `delivery/evidence/ci-v1.json`, `release-v1.json`, and `deployment-v1.json` only from the confirmed terminal facts above; require all existing `source_commit` fields to equal the Step 1 SHA, run `python scripts/verify_release_evidence.py delivery/evidence --require-live`, and require `git diff --exit-code <source_commit> -- src .github .gitlab-ci.yml containers render.yaml pyproject.toml requirements` to prove zero protected-subject drift. Evidence/documentation/tests/scripts may follow; any product, CI, image, package, dependency, or deployment-config change requires a new source commit and complete restart from Step 1.
- [ ] **Step 6: Add the exact 37.A RED test.** Copy the complete displayed test into the declared Test file without changing implementation files.
- [ ] **Step 7: Run 37.A RED.** Run `python -m pytest -q tests/unit/process/test_readme_contract.py::test_readme_fails_when_release_digest_verification_is_missing`. Expected: FAIL for “the test runner reaches `test_readme_fails_when_release_digest_verification_is_missing`, but its first task-owned assertion fails because requiring actionable reference-image digest verification instructions tied to the real released content identity has not been implemented; collection, runner startup, unrelated import, or environment failure does not count”. Collection, import, environment, unrelated, or already-failing tests do not count.
- [ ] **Step 8: Implement 37.A GREEN-1.** Derive every README installation, usage, secure-key, recovery, distribution, CI/release, GHCR, Render, directory, limitation, and non-goal statement from the exact completed task evidence and current package interfaces.
- [ ] **Step 9: Implement 37.A GREEN-2.** Implement `verify_readme_contract` as a deterministic document check for the required sections, exact command forms, referenced artifact identities, security boundaries, and prohibited compatibility or capability overclaims.
- [ ] **Step 10: Implement 37.A GREEN-3.** Make `test_readme_fails_when_release_digest_verification_is_missing` GREEN by requiring actionable reference-image digest verification instructions tied to the real released content identity.
- [ ] **Step 11: Implement 37.A GREEN-4.** Own user-facing documentation and its static verifier only. New capability, result fabrication, process-history rewriting, reflection authorship, and substitution of planned values for missing external evidence remain out of scope.
- [ ] **Step 12: Run 37.A Target GREEN.** Re-run `python -m pytest -q tests/unit/process/test_readme_contract.py::test_readme_fails_when_release_digest_verification_is_missing`; require exit 0 and the displayed RED assertion to pass.
- [ ] **Step 13: Run 37.A Domain.** Run `python -m pytest -q tests/unit/process/test_readme_contract.py`; require exit 0 and every displayed Atomic verification expectation to hold.

#### Legacy step 37.B: Final Process and Agent Evidence Record

**Atomic goal:** Complete truthful append-preserving `SPEC_PROCESS.md` and `AGENT_LOG.md` records and fail-closed verification for the lightweight document check, disposable cold-start findings and revisions, every executable task, review, intervention, commit, PR, failure, and lesson.

**Minimum GREEN patch contract:**

```text
Owned files: - Create: scripts/verify_process_evidence.py - Read: SPEC.md - Read: PLAN.md - Read: SPEC_PROCESS.md - Read: AGENT_LOG.md - Read: config/dependency-closure-v1.json - Read: config/formal-toolchain-promotion-v1.json - Modify: SPEC_PROCESS.md (preserve history; append exact final evidence only) - Modify: AGENT_LOG.md (append-only final chronology) - Test: tests/unit/process/test_delivery_evidence.py (process-record cases)
Interface: Read the current document and process records plus the fixed terminal Task 1.E GO file and dependency/toolchain records as data; produce `ProcessEvidenceResultV1` from truthful, read-only checks without executing repository code.
GREEN-1: Append only truthful document-check, cold-start, task, review, intervention, commit, PR, failure, and lesson records while preserving every prior `SPEC_PROCESS.md` and `AGENT_LOG.md` entry.
GREEN-2: Implement the process-record checker as a read-only, fail-closed parser of the current `SPEC_PROCESS.md` and `AGENT_LOG.md`; require the document-check result, selected cold-start task IDs, Agent/session constraints, questions, blocking points, outputs, verification results, human confirmation, resulting revisions, and formal handoff to be recorded when those stages occur.
GREEN-3: Implement `verify_process_evidence` to reject missing, contradictory, fabricated, or non-append-preserving process records, missing task/review/commit/PR chronology, false completion claims, and evidence that belongs to a temporary or unrelated worktree; accept ordinary repository-root process records without a cryptographic admission root or semantic digest.
EVIDENCE_COMMIT_DERIVATION_V1: For each executable session task, derive one unique evidence commit from Git history as the direct child of that task's implementation commit. Require its diff to contain only that task's `Status`, executed task-step checkbox states, one-line `Completion evidence` in `PLAN.md`, and one append-only `AGENT_LOG.md` entry; reconcile task order and PR metadata; expose the derived evidence commit SHA in the verifier result; and never require that SHA inside the evidence commit itself.
GREEN-4: Own readiness aggregation, reflection structure checks, truthful final PLAN status/evidence updates, and explicitly requested disclosed language polishing only. Human decisions, student authorship, external outcomes, and missing evidence remain outside automation.
Boundary: Preserve historical failures/revisions; never fabricate approval, cold-start pass, baseline materialization, subagent, review, commit, PR, human edit, or external outcome. Derive the exact formal admission root from the approved PLAN SHA; accept only canonical JSON tracked beneath that repository path and reject `.worktrees`, absolute, escaped, missing, untracked, or repository-external evidence without importing or executing repository code. Require the manifest-bound checklist/result pairs to match each other, the registered approved candidate identity, matching A/B results, reviewer-independence evidence, finding/closure records, and overall decision. Require the approved-document commit to contain the exact approved SPEC raw SHA/blob, PLAN complete SHA/semantic digest, and AGENTS blob/SHA-256; require its direct admission-evidence child and direct baseline-record grandchild to obey the exact allowed-path diffs; require `baseline.json` to bind the first two commits and all approved identities without embedding its own file hash or commit; and require the uniquely derived baseline-record commit to be the actual clean Task 1 formal base. A working-file match cannot substitute for tracked committed-tree containment or ancestry. Compare the final PLAN by recomputed `PlanSemanticDigestV2`; permitted Status/checkbox/one-line Completion-evidence updates may change the raw complete-file SHA but no other semantic drift is accepted. Load the two unique toolchain JSON records as data, require `dependency_closure.python_version == formal_toolchain_promotion.python_version == gate_evidence.python_version` by exact string comparison, and validate the public compatibility range `>=3.12,<3.13` independently; range membership never replaces exact equality.
```

**Exact RED test code:**

```python
def test_process_evidence_rejects_stale_plan_executability_result(
    repository_copy: Path,
) -> None:
    rewrite_registered_plan_review_candidate_identity(
        repository_copy,
        review_kind="PLAN_EXECUTABILITY",
        plan_complete_file_sha256="0" * 64,
    )
    result = verify_process_evidence(repository_copy)
    assert (
        "PLAN_REVIEW_CANDIDATE_IDENTITY_MISMATCH:PLAN_EXECUTABILITY"
        in result.error_codes
    )


def test_process_evidence_rejects_untracked_worktree_admission_root(
    repository_copy: Path,
) -> None:
    register_admission_evidence_root(
        repository_copy,
        ".worktrees/_review-packages/admission-v3/" + "a" * 64,
    )
    result = verify_process_evidence(repository_copy)
    assert "ADMISSION_EVIDENCE_ROOT_NOT_TRACKED" in result.error_codes


def test_process_evidence_rejects_missing_child_task_review(
    repository_copy: Path,
) -> None:
    remove_review_record(repository_copy, "25.D")
    result = verify_process_evidence(repository_copy)
    assert "TASK_REVIEW_EVIDENCE_MISSING:25.D" in result.error_codes


def test_process_evidence_rejects_formal_python_identity_drift(
    repository_copy: Path,
) -> None:
    record_path = (
        repository_copy / "config/formal-toolchain-promotion-v1.json"
    )
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["python_version"] = "different-exact-patch"
    record_path.write_text(
        json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    result = verify_process_evidence(repository_copy)
    assert "FORMAL_PYTHON_IDENTITY_MISMATCH" in result.error_codes


def test_process_evidence_rejects_approved_document_commit_with_unapproved_spec_blob(
    repository_copy: Path,
) -> None:
    register_approved_document_commit(
        repository_copy,
        create_commit_with_unapproved_spec_blob(repository_copy),
    )
    result = verify_process_evidence(repository_copy)
    assert (
        "APPROVED_DOCUMENT_BASELINE_SPEC_BLOB_MISMATCH"
        in result.error_codes
    )
```

**Expected RED:** `rewrite_registered_plan_review_candidate_identity` changes only the executability result's candidate PLAN SHA, recomputes that result's canonical self-digest and registered file SHA, and deliberately leaves the checklist, approval, A/B, and process candidate identities unchanged. `register_admission_evidence_root` changes only the formal-root registration to the displayed existing local `.worktrees` tree while preserving its readable JSON bytes/digests. The baseline fixture registers an accessible commit whose `SPEC.md` blob is not the M0-approved blob. The fixtures and existing process verifier load successfully, then the new tests fail because no implementation detects the isolated review-candidate disagreement, untracked temporary evidence root, or committed-SPEC mismatch and emits the three declared stable errors. A file/self-digest mismatch, missing fixture/record, collection/import failure, repository-code execution, or unrelated process/toolchain error does not count as RED.

**Atomic verification:**
- Target (37.B): `python -m pytest -q tests/unit/process/test_delivery_evidence.py::test_process_evidence_rejects_stale_plan_executability_result tests/unit/process/test_delivery_evidence.py::test_process_evidence_rejects_untracked_worktree_admission_root tests/unit/process/test_delivery_evidence.py::test_process_evidence_rejects_approved_document_commit_with_unapproved_spec_blob tests/unit/process/test_delivery_evidence.py::test_process_evidence_rejects_missing_child_task_review tests/unit/process/test_delivery_evidence.py::test_process_evidence_rejects_formal_python_identity_drift`
- Domain (37.B): `python -m pytest -q tests/unit/process/test_delivery_evidence.py`
- Expected (37.B, 1): `PASS`
- Expected (37.B, 2): `python_version`
- Expected (37.B, 3): `GO`
- Expected (37.B, 4): `FORMAL_PYTHON_IDENTITY_MISMATCH`
- Expected (37.B, 5): `ADMISSION_EVIDENCE_ROOT_NOT_TRACKED`

**Atomic review focus:**
- SPEC (37.B): Spec compliance review checks Task 37.B's Goal, Milestone 37 scope, Independent PLAN Review Gate and Approved-document Baseline Gate registration contracts, this Implementation boundary, exact RED, and Verification as one consistent truthful process-evidence contract with an executable typed-evidence owner.
- Quality (37.B): Code quality review checks append preservation, the exact tracked formal root and complete manifest, both complete canonical review pairs, exact candidate/semantic/SPEC/AGENTS/A/B/reviewer identities, reviewer independence, findings/closures and overall decision, the three-commit allowed-path relation and uniquely derived clean formal base, complete executable-task chronology, exact M0/toolchain/source identities, character-for-character Python comparison, evidence freshness/content digests/access control, and stable fail-closed errors without fabricated or repaired planning evidence.

- [ ] **Step 14: Add the exact 37.B RED test.** Copy the complete displayed test into the declared Test file without changing implementation files.
- [ ] **Step 15: Run 37.B RED.** Run `python -m pytest -q tests/unit/process/test_delivery_evidence.py::test_process_evidence_rejects_stale_plan_executability_result tests/unit/process/test_delivery_evidence.py::test_process_evidence_rejects_untracked_worktree_admission_root tests/unit/process/test_delivery_evidence.py::test_process_evidence_rejects_approved_document_commit_with_unapproved_spec_blob tests/unit/process/test_delivery_evidence.py::test_process_evidence_rejects_missing_child_task_review tests/unit/process/test_delivery_evidence.py::test_process_evidence_rejects_formal_python_identity_drift`. Expected: FAIL for “`rewrite_registered_plan_review_candidate_identity` changes only the executability result's candidate PLAN SHA, recomputes that result's canonical self-digest and registered file SHA, and deliberately leaves the checklist, approval, A/B, and process candidate identities unchanged. `register_admission_evidence_root` changes only the formal-root registration to the displayed existing local `.worktrees` tree while preserving its readable JSON bytes/digests. The baseline fixture registers an accessible commit whose `SPEC.md` blob is not the M0-approved blob. The fixtures and existing process verifier load successfully, then the new tests fail because no implementation detects the isolated review-candidate disagreement, untracked temporary evidence root, or committed-SPEC mismatch and emits the three declared stable errors. A file/self-digest mismatch, missing fixture/record, collection/import failure, repository-code execution, or unrelated process/toolchain error does not count as RED”. Collection, import, environment, unrelated, or already-failing tests do not count.
- [ ] **Step 16: Implement 37.B GREEN-1.** Append only truthful M0, semantic-approval, typed Independent PLAN Review, cold-start, approved-document baseline, task, review, intervention, commit, PR, failure, and lesson records while preserving every prior `SPEC_PROCESS.md` and `AGENT_LOG.md` entry.
- [ ] **Step 17: Implement 37.B GREEN-2.** Implement `verify_independent_plan_review_evidence` as a read-only, fail-closed parser of both canonical checklist/result pairs from the exact manifest-bound tracked admission root and their process registration. Require exact schema/order/digests, distinct valid review kinds, reviewer independence from every recorded author/fixer, matching post-M0 A/B identities, candidate PLAN/SPEC/semantic identities, complete findings and closures, two `PASS` verdicts, and a matching overall `PASS` decision.
- [ ] **Step 18: Implement 37.B GREEN-3.** Implement `verify_process_evidence` to expose both typed results; reject any formal root other than the exact tracked repository path derived from the approved PLAN SHA and verify every manifest entry; require the approved-document commit to contain the M0-approved SPEC raw SHA/blob, human-approved PLAN complete SHA/semantic digest, and approved AGENTS blob/SHA-256; require its direct admission-evidence child to preserve approved bytes and change only the fixed pre-baseline evidence root plus `SPEC_PROCESS.md`/`AGENT_LOG.md`; require that child's direct baseline-record child to add only `baseline.json`; derive that unique baseline-record commit from Git history and prove it was the clean Task 1 formal base; reconcile all executable-task chronology and repository identities; require the final PLAN's recomputed `PlanSemanticDigestV2` to equal the reviewed/approved candidate digest despite permitted tracking-only byte changes; and require both unique dependency/toolchain records to equal the Task 1.E exact Python identity.
- [ ] **Step 19: Implement 37.B GREEN-4.** Own read-only validation and truthful final process-record append only. The pre-implementation reviews, approval, cold-start, baseline materialization, and their registration remain non-task process actions; this task may neither create, repair, reinterpret, or fabricate their evidence nor execute repository code or author reflection content.
- [ ] **Step 20: Run 37.B Target GREEN.** Re-run `python -m pytest -q tests/unit/process/test_delivery_evidence.py::test_process_evidence_rejects_stale_plan_executability_result tests/unit/process/test_delivery_evidence.py::test_process_evidence_rejects_untracked_worktree_admission_root tests/unit/process/test_delivery_evidence.py::test_process_evidence_rejects_approved_document_commit_with_unapproved_spec_blob tests/unit/process/test_delivery_evidence.py::test_process_evidence_rejects_missing_child_task_review tests/unit/process/test_delivery_evidence.py::test_process_evidence_rejects_formal_python_identity_drift`; require exit 0 and every displayed RED assertion to pass.
- [ ] **Step 21: Run 37.B Domain.** Run `python -m pytest -q tests/unit/process/test_delivery_evidence.py`; require exit 0 and every displayed Atomic verification expectation to hold.

**Task-level verification, review, and completion:**

- [ ] **Step 22: Refactor only inside T37.1.** Improve names and local structure in declared writable Files without changing the displayed interfaces, observable behavior, or successor scope; rerun every legacy Target and Domain after the refactor.
- [ ] **Step 23: Run the FORMAL_OFFLINE_V1 closure.** Execute every exact command defined for `FORMAL_OFFLINE_V1` in the Global Execution Contract, including the changed-file redacted credential scan and `git diff --check`; record actual results in `AGENT_LOG.md`.
- [ ] **Step 24: Request T37.1 SPEC review.** Use `superpowers:requesting-code-review` with the Goal, SPEC contracts, Interfaces, minimum GREEN contracts, RED/GREEN evidence, and task diff. Require an explicit verdict.
- [ ] **Step 25: Close T37.1 SPEC findings.** Fix every Critical/Important finding, rerun affected Targets, Domains, and profile commands, and obtain same-stage re-review PASS.
- [ ] **Step 26: Request T37.1 quality review.** Use `superpowers:requesting-code-review` only after SPEC review PASS; review the task diff against every Atomic review focus line.
- [ ] **Step 27: Close T37.1 quality findings.** Fix every Critical/Important finding, rerun affected checks, and obtain same-stage re-review PASS.
- [ ] **Step 28: Commit T37.1 evidence and documentation.** Stage only the task-owned confirmed external JSON records, README, delivery-only scripts/tests, and truthful `SPEC_PROCESS.md` append; create the task implementation commit after both review stages PASS and never stage a protected source-subject path.

```bash
git add -- "README.md" "scripts/verify_readme_contract.py" "tests/unit/process/test_readme_contract.py" "scripts/verify_process_evidence.py" "SPEC_PROCESS.md" "tests/unit/process/test_delivery_evidence.py" "delivery/evidence/ci-v1.json" "delivery/evidence/release-v1.json" "delivery/evidence/deployment-v1.json"
git commit -m "Implement T37.1 README and Final Process Evidence"
```

- [ ] **Step 29: Record T37.1 completion evidence.** In a narrow evidence commit, update only this task's Status/Completion evidence and append `AGENT_LOG.md` with the Step 1 source SHA, real T37.1 evidence/documentation implementation SHA, all terminal CI/tag/release/GHCR/Render URLs and digests, responsible fresh subagent, human edits, exact commands/results, review/re-review verdicts, and PR URL.
- [ ] **Step 30: Continue or finish WP37.** If another session task remains in this package, hand the same branch/PR to a new fresh subagent. Otherwise use `superpowers:finishing-a-development-branch`, verify the package result, and merge only after all predecessors and gates remain valid.

**Done:** the exact current main `source_commit` frozen after both WP36 and WP38 are finished and merged has complete same-SHA GitHub/GitLab CI, protected tag/Release/GHCR, Render deployment, three verified external JSON records, and zero protected-subject drift；legacy steps 37.A, 37.B 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审。
**Completion evidence:** Not yet executed.
## Appendix D. Superseded Task T37.2 (historical, non-normative)

> The following former T37.2 card is retained only as process history. It is not a current task contract and its admission, review, identity, or baseline requirements must not be followed.

**Status:** Not started
**Work package:** WP37
**Legacy steps:** 37.C
**Goal:** Aggregate the local/external/process/documentation checks and report ready only when all 68 session tasks cover all 141 legacy steps and a valid student-authored reflection exists.
**SPEC contracts:** SPEC §1.6; §5.3–§5.6; §8.1–§8.4; §10.1 AC-01–AC-31; §10.3; §11.3; course required artifacts, process evidence, README, CI/CD, WebUI URL, and reflection rules; `AGENTS.md` final-report rules.

**Files:**
- Create: `scripts/verify_delivery.py`
- Create: `scripts/verify_reflection.py`
- Create: `tests/unit/process/test_reflection_contract.py`
- Modify: `tests/unit/process/test_delivery_evidence.py`
- Modify: `REFLECTION.md`

**Depends:** T37.1
**Parallelization:** Start only after every task/non-task gate in **Depends** has passed. Same-wave execution is allowed only when expanded writable paths are disjoint; the WP37 branch and PR remain the sole package integration boundary.

**Interfaces:**
- **Consumes / Produces (37.C):** Consumes Task 37.B's `verify_process_evidence(root: Path) -> ProcessEvidenceResultV1` through `ProcessEvidenceLoader = Callable[[Path], ProcessEvidenceResultV1]`, plus T37.1's three live evidence records and their common existing-schema `source_commit`. Produces `verify_delivery(root: Path, require_live: bool, *, process_evidence_loader: ProcessEvidenceLoader = verify_process_evidence) -> DeliveryReadinessResultV1` and `verify_reflection(path: Path) -> ReflectionContractResultV1`. The injected loader exists only to test this aggregate checker independently of Task 37.B; delivery readiness also rejects any post-source change under `src/**`, `.github/**`, `.gitlab-ci.yml`, `containers/**`, `render.yaml`, `pyproject.toml`, or `requirements/**`. The final `require_live=True` delivery and reflection invocations are deferred to `FINAL_DELIVERY_POST_MERGE_V1` after WP37 merge.

**Implementation points, exact RED, and minimum GREEN contracts:**

#### Legacy step 37.C: Delivery and Reflection Readiness Gate

**Atomic goal:** Aggregate every local, external, process, and documentation check, and report ready only when all 68 session tasks are terminal and identity-aligned, all 141 legacy TDD steps are mapped exactly once, their required Target/Domain/profile evidence is PASS, and a valid student-authored reflection exists.

**Minimum GREEN patch contract:**

```text
Owned files: - Create: scripts/verify_delivery.py - Create: scripts/verify_reflection.py - Create: tests/unit/process/test_reflection_contract.py - Modify: tests/unit/process/test_delivery_evidence.py (aggregate readiness cases only) - Modify: PLAN.md (final truthful statuses/evidence only) - Modify: REFLECTION.md only after explicit language-polish request; student owns substantive text
Interface: Consumes Task 37.B's `verify_process_evidence(root: Path) -> ProcessEvidenceResultV1` through `ProcessEvidenceLoader`, plus T37.1's three live evidence records and their common existing-schema `source_commit`. Produces `verify_delivery(root: Path, require_live: bool, *, process_evidence_loader: ProcessEvidenceLoader = verify_process_evidence) -> DeliveryReadinessResultV1` and `verify_reflection(path: Path) -> ReflectionContractResultV1`. Delivery readiness also rejects any post-source change under `src/**`, `.github/**`, `.gitlab-ci.yml`, `containers/**`, `render.yaml`, `pyproject.toml`, or `requirements/**`.
GREEN-1: Implement `verify_delivery` as a fail-closed aggregate over real task, process, environment, artifact, document, and live-evidence records, requiring a truthful process-record result, all 68 session tasks terminal and identity-aligned, all 141 legacy TDD steps mapped exactly once with their required Target/Domain/profile evidence PASS, one common CI/release/deployment `source_commit`, exact CI/tag/wheel/GHCR/Render binding to that commit, and zero protected-subject path drift from it to delivery HEAD. The task-local Target/Domain tests may use `require_live=False` and injected process evidence; the live invocation is a final-gate action only after T37.2 is terminal and WP37 is merged.
GREEN-2: Implement `verify_reflection` to check only the student-authored 1500–2500-word range, required disclosure, file structure, and parseability; substantive personal content is neither generated nor scored.
GREEN-3: Make the declared process-evidence RED probes GREEN by returning a stable process-record error before any readiness success when the injected Task 37.B result is failed, even if every executable child and other delivery input is valid.
GREEN-4: Own readiness aggregation, reflection structure checks, truthful final PLAN status/evidence updates, and explicitly requested disclosed language polishing only. Human decisions, student authorship, external outcomes, and missing evidence remain outside automation.
Boundary: Aggregate the Task 37.B process result without duplicating its parser or treating success words as evidence. Fail closed on every missing, contradictory, fabricated, or non-terminal record. `source_commit` is the immutable product identity for wheel, release, GHCR, Render, and the three existing external evidence records. `delivery_head` is the later final-main SHA after WP37 merge and is the identity for final PLAN tracking, README/process/reflection state, and `FINAL_DELIVERY_POST_MERGE_V1`; it may contain only delivery-only changes allowed after source freeze. Require byte-identical existing `source_commit` values across CI/release/deployment records and reject any later change under `src/**`, `.github/**`, `.gitlab-ci.yml`, `containers/**`, `render.yaml`, `pyproject.toml`, or `requirements/**`; evidence, documentation, tests, delivery-only scripts, PLAN tracking, and append-only logs do not become a new release source. Reflection checks word count, disclosure, and student-specific structure but never generates or scores substantive personal content.
```

**Exact RED test code:**

```python
def test_delivery_rejects_failed_process_evidence(
    repository_copy: Path,
    failed_process_evidence: ProcessEvidenceResultV1,
) -> None:
    result = verify_delivery(
        repository_copy,
        require_live=False,
        process_evidence_loader=lambda _: failed_process_evidence,
    )
    assert "PROCESS_EVIDENCE_INVALID" in result.error_codes


def test_delivery_rejects_contradictory_process_evidence(
    repository_copy: Path,
    contradictory_process_evidence: ProcessEvidenceResultV1,
) -> None:
    result = verify_delivery(
        repository_copy,
        require_live=False,
        process_evidence_loader=lambda _: contradictory_process_evidence,
    )
    assert "PROCESS_EVIDENCE_INVALID" in result.error_codes


def test_delivery_rejects_incomplete_executable_child(
    repository_copy: Path,
) -> None:
    mark_child_incomplete(repository_copy, "38.G")
    result = verify_delivery(repository_copy, require_live=False)
    assert "LEGACY_STEP_INCOMPLETE:38.G" in result.error_codes


def test_delivery_rejects_protected_path_drift_after_source_commit(
    repository_copy: Path,
) -> None:
    change_protected_path_after_source_commit(repository_copy, "src/vespercode/demo/app.py")
    result = verify_delivery(repository_copy, require_live=True)
    assert "DELIVERY_SOURCE_DRIFT:src/vespercode/demo/app.py" in result.error_codes
```

**Expected RED:** the readiness verifier and injected fixtures load successfully, then the new tests fail because `verify_delivery` does not reject failed or contradictory process evidence, emit `PROCESS_EVIDENCE_INVALID`, or reject the isolated protected-path mutation with `DELIVERY_SOURCE_DRIFT:src/vespercode/demo/app.py`. A Task 37.B parsing failure, missing fixture/record, incomplete child, absent reflection, collection/import failure, or unavailable unrelated live evidence does not count as RED.

**Atomic verification:**
- Target (37.C): `python -m pytest -q tests/unit/process/test_delivery_evidence.py::test_delivery_rejects_failed_process_evidence tests/unit/process/test_delivery_evidence.py::test_delivery_rejects_contradictory_process_evidence tests/unit/process/test_delivery_evidence.py::test_delivery_rejects_incomplete_executable_child tests/unit/process/test_delivery_evidence.py::test_delivery_rejects_protected_path_drift_after_source_commit`
- Domain (37.C): `python -m pytest -q tests/unit/process/test_readme_contract.py tests/unit/process/test_delivery_evidence.py tests/unit/process/test_reflection_contract.py`
- Expected (37.C, 1): the displayed Target and Domain commands exit `0`; final live delivery/reflection verification is deferred to `FINAL_DELIVERY_POST_MERGE_V1`.
- Expected (37.C, 2): `PROCESS_EVIDENCE_INVALID`
- Expected (37.C, 3): `PROCESS_EVIDENCE_INVALID`
- Expected (37.C, 4): `LEGACY_STEP_INCOMPLETE:38.G`
- Expected (37.C, 5): `DELIVERY_SOURCE_DRIFT:src/vespercode/demo/app.py`

**Atomic review focus:**
- SPEC (37.C): Spec compliance review checks Task 37.C's Goal, Milestone 37, process-record and final-delivery contracts, this Implementation boundary, exact RED, and Verification as one consistent final readiness contract.
- Quality (37.C): Code quality review checks injected-loader isolation, Task 37.B process-result aggregation without duplicate parsing, complete session-task and legacy-step aggregation, common source/CI/tag/wheel/GHCR/Render identity, protected-path drift rejection, freshness/content digests/access control, fail-closed non-terminal handling, reflection word-count/disclosure/structure checks, student authorship protection, and absence of generated personal content or invented readiness.

- [ ] **Step 1: Add the exact 37.C RED tests.** Copy the complete displayed tests into the declared Test file without changing implementation files.
- [ ] **Step 2: Run 37.C RED.** Run `python -m pytest -q tests/unit/process/test_delivery_evidence.py::test_delivery_rejects_failed_process_evidence tests/unit/process/test_delivery_evidence.py::test_delivery_rejects_contradictory_process_evidence tests/unit/process/test_delivery_evidence.py::test_delivery_rejects_incomplete_executable_child tests/unit/process/test_delivery_evidence.py::test_delivery_rejects_protected_path_drift_after_source_commit`. Expected: FAIL for “the readiness verifier and injected fixtures load successfully, then the new tests fail because `verify_delivery` does not reject failed or contradictory process evidence, emit `PROCESS_EVIDENCE_INVALID`, or reject the isolated protected-path mutation with `DELIVERY_SOURCE_DRIFT:src/vespercode/demo/app.py`. A Task 37.B parsing failure, missing fixture/record, incomplete child, absent reflection, collection/import failure, or unavailable unrelated live evidence does not count as RED”. Collection, import, environment, unrelated, or already-failing tests do not count.
- [ ] **Step 3: Implement 37.C GREEN-1.** Implement `verify_delivery` as a fail-closed aggregate over real task, process, environment, artifact, document, and live-evidence records, requiring a truthful process-record result, all 68 session tasks terminal and identity-aligned, all 141 legacy TDD steps mapped exactly once with their required Target/Domain/profile evidence PASS, one common CI/release/deployment `source_commit`, exact CI/tag/wheel/GHCR/Render binding to that commit, and zero protected-subject path drift from it to delivery HEAD.
- [ ] **Step 4: Implement 37.C GREEN-2.** Implement `verify_reflection` to check only the student-authored 1500–2500-word range, required disclosure, file structure, and parseability; substantive personal content is neither generated nor scored.
- [ ] **Step 5: Implement 37.C GREEN-3.** Make the declared process-evidence RED probes GREEN by returning `PROCESS_EVIDENCE_INVALID` before any readiness success when the injected Task 37.B result is failed or contradictory, even if every executable child and other delivery input is valid.
- [ ] **Step 6: Implement 37.C GREEN-4.** Own readiness aggregation, reflection structure checks, truthful final PLAN status/evidence updates, and explicitly requested disclosed language polishing only. Human decisions, student authorship, external outcomes, and missing evidence remain outside automation.
- [ ] **Step 7: Run 37.C Target GREEN.** Re-run `python -m pytest -q tests/unit/process/test_delivery_evidence.py::test_delivery_rejects_failed_process_evidence tests/unit/process/test_delivery_evidence.py::test_delivery_rejects_contradictory_process_evidence tests/unit/process/test_delivery_evidence.py::test_delivery_rejects_incomplete_executable_child tests/unit/process/test_delivery_evidence.py::test_delivery_rejects_protected_path_drift_after_source_commit`; require exit 0 and every displayed RED assertion to pass.
- [ ] **Step 8: Run 37.C Domain.** Run `python -m pytest -q tests/unit/process/test_readme_contract.py tests/unit/process/test_delivery_evidence.py tests/unit/process/test_reflection_contract.py`; require exit 0 and every displayed Atomic verification expectation to hold.

**Task-level verification, review, and completion:**

- [ ] **Step 9: Refactor only inside T37.2.** Improve names and local structure in declared writable Files without changing the displayed interfaces, observable behavior, or successor scope; rerun every legacy Target and Domain after the refactor.
- [ ] **Step 10: Run the FORMAL_OFFLINE_V1 closure.** Execute every exact command defined for `FORMAL_OFFLINE_V1` in the Global Execution Contract, including the changed-file redacted credential scan and `git diff --check`; record actual results in `AGENT_LOG.md`.
- [ ] **Step 11: Request T37.2 SPEC review.** Use `superpowers:requesting-code-review` with the Goal, SPEC contracts, Interfaces, minimum GREEN contracts, RED/GREEN evidence, and task diff. Require an explicit verdict.
- [ ] **Step 12: Close T37.2 SPEC findings.** Fix every Critical/Important finding, rerun affected Targets, Domains, and profile commands, and obtain same-stage re-review PASS.
- [ ] **Step 13: Request T37.2 quality review.** Use `superpowers:requesting-code-review` only after SPEC review PASS; review the task diff against every Atomic review focus line.
- [ ] **Step 14: Close T37.2 quality findings.** Fix every Critical/Important finding, rerun affected checks, and obtain same-stage re-review PASS.
- [ ] **Step 15: Commit T37.2 implementation.** Stage only the task-owned implementation/tests and create one implementation commit after both review stages PASS.

```bash
git add -- "scripts/verify_delivery.py" "scripts/verify_reflection.py" "tests/unit/process/test_reflection_contract.py" "tests/unit/process/test_delivery_evidence.py" "REFLECTION.md"
git commit -m "Implement T37.2 Independent Delivery and Reflection Readiness Gate"
```

- [ ] **Step 16: Record T37.2 completion evidence.** In a narrow evidence commit, update only this task's Status/Completion evidence and append `AGENT_LOG.md` with the real implementation SHA, responsible fresh subagent, human edits, exact commands/results, review/re-review verdicts, and PR URL.
- [ ] **Step 17: Continue or finish WP37.** If another session task remains in this package, hand the same branch/PR to a new fresh subagent. Otherwise use `superpowers:finishing-a-development-branch`, verify the package result, and merge only after all predecessors and gates remain valid.

**Done:** legacy steps 37.C 的 Target、Domain、适用真实环境和全局 profile 均通过；Critical/Important finding 全部关闭并复审；没有行为被延后到 successor。
**Completion evidence:** Not yet executed.
