# VesperCode v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft — awaiting M0 approval, human PLAN approval, and cold-start validation

**Authoritative SPEC:** `SPEC.md`

**Authoritative SPEC SHA-256:** `80ccc86d9c06bdf7b4fed8673e2e6879942ca2cbc2b07c91bf1276b19a7447aa`

**Authoritative SPEC Git blob (`git hash-object --no-filters`):** `2cc522eeb2eb61e75ce96b6500ebbfdf8db18499`

**Planning baseline Git commit:** `f6aa9897ca8e9f3cab86143b880a306d96a252e1`

**Course requirements:** `AI4SE_Final_Project_通用要求.md`

**Harness requirements:** `AI4SE_Final_Project_A_Coding_Agent_Harness(1).md`

**Generated:** 2026-07-26, Asia/Taipei (UTC+08:00)

**Planning method:** The installed `superpowers:writing-plans` skill was loaded and used to produce this plan. The user-selected repository-root location overrides the skill's default dated-plan location.

**Implementation prohibition:** Formal implementation, CI work, release work, and deployment are prohibited until M0 approves the exact SPEC identity, a human approves the exact SPEC plus `PlanSemanticDigestV1` contract, and the heterogeneous-agent cold-start gate below passes.

**Cold-start isolation:** Cold-start trial code, branches, worktrees, and commits must be disposable, must not be merged, and must not be reused by formal implementation.

**Completion evidence rule:** Only an executable integer or dotted child Task receives an actual implementation commit SHA, and only after its tests and both review gates pass. A split Milestone receives no aggregate implementation SHA or PR; its completion is derived from its exact children. A SHA must never be predicted, prefilled, or invented. Because a commit cannot contain its own SHA, every executable task uses an implementation commit followed by a narrow PLAN/`AGENT_LOG.md` evidence commit in the same PR. SPEC §11.2 mechanically normalizes every syntactically matching `Status`, checkbox, and one-line `Completion evidence` field in the Formal Tasks region, including the aggregate fields retained inside Milestone contracts. Retained Milestone tracking/checklist fields are frozen and ignored by execution; only truthful executable-task tracking updates are authorized without semantic reapproval.

**PLAN content address:** The approval record must compute both the complete-file SHA-256 and SPEC §11.2 `PlanSemanticDigestV1` externally. Neither digest is embedded into this file because doing so would create a self-referential identity. Complete-file SHA-256 identifies each evidence snapshot; semantic approval and cold-start bind `PlanSemanticDigestV1`.

**Goal:** Build VesperCode v1, a Windows 11 local governance-first Coding Agent Harness that repairs stable failures in the single supported Python reference profile, validates immutable candidates in locked Docker execution, and writes an exact user-approved diff back through recoverable 1–3-file persistence.

**Architecture:** A Python control plane owns strict request admission, immutable Snapshot/Candidate trees, a sequential single-call agent loop, deterministic tools and feedback, governance, disclosure, validation, persistence, memory, audit, and lifecycle state. Win32 adapters establish workspace and object identity, Docker Desktop executes locked pytest/Ruff/Mypy checks against read-only candidate trees, SQLite stores control records, and Mock/OpenAI adapters implement the low-level LLM boundary. A loopback FastAPI/HTMX WebUI exposes formal local capabilities; a separately composed public Mock Demo exposes only fixed simulated capabilities.

**Tech Stack:** Python `>=3.12,<3.13`; Hatchling as the locked PEP 517 wheel backend; FastAPI and Pydantic v2; server-rendered HTML and HTMX with Open Design and `ui-ux-pro-max` review; SQLite; pywin32/Win32 APIs; keyring with mandatory Windows Credential Manager backend verification; a custom `LLMAdapter` with deterministic Mock and one OpenAI single-turn adapter; Docker SDK for Python; pytest 8.x with a Harness-owned machine-readable report plugin, Ruff, and Mypy; GitHub Actions via `.github/workflows/ci.yml`; GitLab CI via `.gitlab-ci.yml`; wheel plus pipx; OCI images; GitHub Release and GHCR; Render Web Service.

## Global Constraints

- The formal host boundary is Windows 11 x64. macOS, Linux hosts, and Windows containers are unsupported.
- Harness Python is `>=3.12,<3.13`.
- Docker Desktop must run Linux containers. Formal project code never runs on the host.
- The sole reference profile id is `python-src-py312-v1`. `ReferenceProfileManifestV1` is the only mapping for `requirements_lock_digest`, immutable Docker image digest, Docker execution profile version `1`, Python/pytest/report-plugin/Ruff/Mypy versions, check-plan version, and the embedded editable policy.
- The sole editable policy is `EditablePathPolicyV1(schema_version=1, policy_id="PYTHON_SRC_ONLY_V1", editable_directory_roots=["src"], allowed_operations=["CREATE","REPLACE"])`. A path must be a strict `src/` descendant. User input, config, model output, repository text, approval, and disclosure cannot widen it.
- Only `CREATE` and `REPLACE` are supported. `DELETE`, `RENAME`, binary changes, link changes, mode changes, fuzzy application, and offset guessing are unsupported.
- A repository has at most 5,000 tracked files, 128 MiB total tracked raw bytes, and 4 MiB per tracked file. A canonical path has at most 240 characters and each segment at most 100 characters.
- An editable file is at most 128 KiB. The current candidate changes at most 3 files, creates at most 1 file, and has at most 131,072 bytes across complete `CREATE`/`REPLACE` postimages.
- Supported editable text is strict UTF-8 or UTF-8 BOM, uniform LF or CRLF, no bare CR or mixed newline, no U+0000, and a required final newline.
- Formal containers use `--network none`, a non-root user, read-only root filesystem, `cap-drop=ALL`, no Docker socket, a read-only `/workspace` CandidateTree, bounded tmpfs/cache directories, at most 2 CPU, 2 GiB memory, 256 PIDs, 256 MiB tmpfs, and 4 MiB check output. Every check gets a fresh container and fresh materialized candidate tree.
- Task 2 defines the sole orchestration-side ephemeral-registry profile; Task 34 and ordinary CI may only reproduce that exact profile. It binds to `127.0.0.1` on an OS-assigned free port, uses a digest-pinned registry image, accepts no credentials, exposes no LAN/public port, never supplies network access to check containers, and deletes container/data on every success/failure/cancel path. This is a local feasibility transport, not GHCR publication.
- `ReferenceProfileManifestV1.docker_image_digest` is the lowercase `sha256:` digest of one fixed single-platform OCI manifest. It is never a local image ID, config digest, tag, or index digest. The final reference manifest is generated only after Task 2 proves local OCI export, loopback registry response, and digest pull all identify the same manifest bytes; that final manifest must not enter its bound image's context, layers, config, annotations, or attestations.
- The environment allowlist is exactly `PYTHONHASHSEED=0`, `TZ=UTC`, `LANG=C.UTF-8`, `LC_ALL=C.UTF-8`, `PYTHONDONTWRITEBYTECODE=1`, plus the closed report-channel variables defined by Docker execution profile v1. Pytest plugin autoload is disabled.
- Baseline and formal validation use closed adapter-generated argv for pytest 8.x, Ruff, and Mypy. The model cannot provide a shell, executable, argv, environment, working directory, or arbitrary node ids.
- A baseline uses collect-only twice, full pytest once, an independent target rerun once, Ruff once, and Mypy once, each in a fresh execution. Every target must have identical `CALL/FAIL` fingerprints in full baseline and target rerun; every non-target must pass; forbidden pytest states and incomplete reports fail closed.
- `MockLLMProfileV1(profile_id="mock-deterministic-v1")` and `OpenAILLMProfileV1(profile_id="openai-single-turn-v1")` are the only LLM profile variants.
- The only real endpoint is `OPENAI_PUBLIC_API_V1 → https://api.openai.com:443/v1`. Custom base URLs, unknown endpoints, environment overrides, and cross-origin redirect replay are prohibited.
- OpenAI credentials reside only in Windows Credential Manager. First-run hidden entry, non-revealing status, update, clear, and unsafe-backend rejection are mandatory. Credentials never enter repository files, URLs, CLI arguments, logs, SQLite, images, artifacts, or test fixtures.
- Every real OpenAI call re-probes the Windows Credential Manager backend and executes `get_for_call("OPENAI")` before Grant charge, durable authorization record, turn/call count, or network. A missing/cleared credential or unsafe backend stops the Run with zero increments and no automatic retry; PREFLIGHT readiness never substitutes for this check.
- List/Search use distinct canonical cursor types bound to visible-tree digest, cursor-free query digest, next stable scan position, and their own digest. `CONTINUATION_STALE` and `CONTINUATION_INVALID` return zero partial result; paged and unpaged results must be identical without duplicates or omissions.
- LangChain `AgentExecutor`, AutoGen, CrewAI, LlamaIndex Agent, OpenAI Agents SDK runner, and host coding-agent runners must not implement the delivered main loop.
- The repository implements context assembly, exactly one LLM call per turn, action parsing, policy, dispatch, result feedback, and stop evaluation. Replacing the real LLM with Mock/Stub must leave tool dispatch, governance, feedback correction, memory, and stopping deterministically testable offline.
- All behavior changes use strict TDD: write and run the intended RED test, make the smallest GREEN change, then refactor without changing behavior.
- Tasks 1–3 use one Task 1-owned feasibility-gate bootstrap: an isolated `.venv-gate`, `requirements/gate.lock` with exact direct/transitive versions and distribution hashes, explicit gate pytest/Ruff/Mypy configs, and `scripts/run_gate_checks.py`. Every gate command must use that environment and configuration; global tools and Task 4 project configuration are invalid inputs.
- Task 1 selects, records, reviews, and freezes the exact Python/pytest/Ruff/Mypy versions and all gate file SHA-256 values. Tasks 2–3 consume those exact identities without re-resolution. Task 4.A and Task 4.F each persist the exact Task 1 `python_version` and compare it character-for-character with the Task 1.E terminal `GO` evidence; the public compatibility range remains `>=3.12,<3.13` and never substitutes for that exact interpreter identity. The PLAN intentionally does not guess time-sensitive patch versions before the lock is created; a Task 1 GO is impossible until the complete hash-locked file and installed-version evidence exist.
- Task 4.A is the sole complete v1 project dependency-closure owner. It creates the dependency tables, Python range, reviewed source/index policy, minimal package identity, and hash-complete `requirements/dev.lock`; the closure includes every declared direct runtime, build/distribution, and development/verification dependency plus every transitive distribution and hash. Runtime families include FastAPI, Pydantic v2, pywin32, keyring with Windows Credential Manager verification support, Docker SDK for Python, and every low-level HTTP, test-client, template/form, or serving package imported or invoked directly by project code. Build/distribution families include Hatchling and `build`; development/verification families include pytest 8.x, Ruff, Mypy, and every directly used typing/test support package. Vendored HTMX remains package data, not a Python dependency. `requirements/gate.lock`, `requirements/reference.lock`, and `requirements/demo.lock` remain separate immutable profiles under Tasks 1.A, 2.A, and 34.B respectively and never merge into `requirements/dev.lock`.
- Task 4.A selects the reviewed exact patch versions, transitive distributions, markers, and hashes at execution time without inventing them in this PLAN. The exact Task 1 Python patch and every overlapping pytest/Ruff/Mypy version are preserved. Task 4.F alone promotes those frozen interpreter/tool identities, marker definitions, static rules, build backend, and canonical formal commands into the non-dependency sections of `pyproject.toml`.
- After Task 4.A completes, no task may add, remove, resolve, upgrade, downgrade, or install an undeclared project package. Discovery of a missing package stops the current task. Any dependency-closure change requires a non-tracking PLAN semantic revision, dependency review, recomputation of every affected mechanical structure and digest, renewed human PLAN approval, and a repeated heterogeneous cold-start; M0 also repeats if the authoritative SPEC identity or requirements change. Ad-hoc installation and silent regeneration of `requirements/dev.lock` are prohibited. Rebuilding `.venv-formal` from the unchanged `requirements/dev.lock` with `--require-hashes --no-deps` is only materialization of the already-declared exact/hash-verified closure and is not a dependency change; resolution, upgrade, extra installation, or re-locking remains prohibited and triggers this fail-closed amendment rule.
- Task 4.A solely owns `scripts/bootstrap_formal_env.py`. In every fresh formal-task worktree, the candidate interpreter is located only with `py -3.12`; before creating, rebuilding, or using `.venv-formal`, the bootstrap reads the Task 1.E terminal `GO` toolchain identity and requires `platform.python_version() == gate_evidence.python_version`. A mismatch exits nonzero before the environment is created or used. The bootstrap then materializes only the immutable `requirements/dev.lock` closure with `.venv-formal\Scripts\python.exe -m pip install --disable-pip-version-check --require-hashes --no-deps -r requirements/dev.lock`; it never reads another worktree's `.venv-gate`, invokes an ambient bare `python`, resolves packages, upgrades, or rewrites the lock.
- The canonical offline suite is logically `python -m pytest -q`, executed in formal worktrees as `.venv-formal\Scripts\python.exe -m pytest -q`. Task 4.A runs its dependency-closure RED and lock/config consistency checks through that exact interpreter without claiming the formal tool configuration exists; Task 4.F establishes the canonical offline and closure commands through the same interpreter. Every later task also runs the logical commands `python -m ruff format --check .`, `python -m ruff check .`, and `python -m mypy src tests` from the verified `.venv-formal` environment.
- The five standard closure commands referenced by Tasks 5–38 are exactly `python -m ruff format --check .`, `python -m ruff check .`, `python -m mypy src tests`, `python scripts/scan_credentials.py --changed --redact --fail-on-match`, and `git diff --check`.
- One executable formal task uses one fresh implementation subagent, one isolated worktree, one branch, and one PR. Split Milestones use none. Use `superpowers:using-git-worktrees` before creating each formal worktree and `superpowers:test-driven-development` for every behavior change.
- A task first receives a spec-compliance review and then a code-quality review. Critical or Important findings block dependents until the implementing or explicitly assigned repair subagent closes them and the same review stage passes.
- Every executable-task completion appends truthful evidence to `AGENT_LOG.md`, records the real implementation SHA in this PLAN, and identifies the responsible subagent, human edits, tests, review results, and PR URL. Milestone status is mechanically derived from child evidence.
- PLAN semantic approval follows SPEC §11.2 exactly: normalize no-BOM UTF-8/LF, exclude only enumerated task tracking fields, prepend the declared domain, and hash with SHA-256. Any other PLAN byte change requires renewed semantic approval and cold-start validation.
- Parallel tasks may implement in separate worktrees, but their PR merges and append-only edits to `PLAN.md` and `AGENT_LOG.md` are serialized in task-number order within a wave.
- Before every implementation commit, run `python scripts/scan_credentials.py --changed --redact --fail-on-match` after Task 4 creates it. Tasks 1–3 use their explicit filename-only PowerShell scan. No scan may print a matched value.
- `REFLECTION.md` is written by the student in 1,500–2,500 words. An agent may only perform disclosed language polishing after a human draft exists and may run structural checks without authoring the substantive body.
- SPEC §1.6 and §11.3 non-goals must not acquire v1 implementation tasks, tests, release gates, or hidden compatibility branches.

## Planned Repository Structure

The paths below lock file ownership before task decomposition. Files are small, responsibility-based units; no generic `service.py`, `models.py`, `utils.py`, `helpers.py`, or all-purpose control-plane module is planned.

### Project, process, and delivery

| Path | Single responsibility |
|---|---|
| `pyproject.toml` | Section-frozen project configuration: Task 4.A alone owns dependency tables, Python range, dependency source/index policy, and minimal package identity; Task 4.F alone adds the build backend and pytest/Ruff/Mypy/tooling configuration; Task 33.A alone later adds package data, version, distribution metadata, and the console entry point |
| `requirements/gate.lock` | Task 1-frozen exact direct/transitive feasibility-gate dependencies and distribution hashes consumed unchanged by Tasks 2–3 |
| `requirements/dev.lock` | Exact hash-complete environment closure used by formal local/CI verification, including all declared runtime, build/distribution, and development/verification packages plus every transitive distribution |
| `requirements/reference.lock` | Exact dependency set accepted by `python-src-py312-v1` and hashed by its manifest |
| `requirements/demo.lock` | Exact hash-locked public Demo runtime dependencies with no formal capability extras |
| `PLAN.md` | Content-addressed implementation tasks, dependencies, status, and real completion evidence |
| `AGENT_LOG.md` | Append-only chronological task, subagent, review, human-intervention, and verification evidence |
| `SPEC_PROCESS.md` | Brainstorming history plus cold-start findings and resulting approved SPEC/PLAN revisions |
| `README.md` | Installation, usage, layout, credential setup, distribution, deployment, threat boundary, and limitations |
| `REFLECTION.md` | Student-authored reflection; implementation agents do not author the body |
| `scripts/scan_credentials.py` | Redacted filename-only credential-pattern gate over an explicit changed-file set |
| `scripts/run_gate_checks.py` | Sole Task 1–3 command adapter that verifies the gate environment/lock identities and supplies explicit pytest/Ruff/Mypy configuration |
| `scripts/run_reference_e2e.py` | Repeatable formal reference-fixture workflow driver |
| `scripts/run_mechanism_demo.py` | Repeatable Mock-LLM governance and feedback mechanism demonstration |
| `scripts/run_package_smoke.py` | Clean-wheel build, isolated pipx install, CLI/WebUI, and cleanup smoke driver |
| `scripts/run_reference_image_smoke.py` | Task 2-frozen reference OCI reproduction/inspection/runtime smoke driver |
| `scripts/run_demo_image_smoke.py` | Curated Demo OCI build/capability/health smoke driver |
| `scripts/verify_ci_contract.py` | Exact GitHub Actions and GitLab job/trigger/credential-boundary contract checker |
| `scripts/verify_release_evidence.py` | Content-addressed release/deployment evidence and optional live-endpoint verifier |
| `scripts/verify_delivery.py` | Read-only completeness and evidence-age checker for final course delivery |
| `scripts/verify_reflection.py` | Read-only declaration and 1,500–2,500-word structural checker |
| `.github/workflows/ci.yml` | GitHub Actions `unit-test`, `reference-image-build`, and `demo-image-build` jobs on every push/pull request, with no publishing credentials or actions |
| `.gitlab-ci.yml` | GitLab `unit-test`, `wheel-build-smoke`, `reference-image-build`, and `demo-image-build` jobs plus protected tag release |
| `render.yaml` | Public Mock Demo Render service, Docker runtime, health path, and no-persistent-disk configuration |
| `delivery/evidence/ci-v1.json` | Real last-passing GitHub workflow/job and GitLab pipeline/job identities with categorized evidence |
| `delivery/evidence/release-v1.json` | Real source commit, GitHub Release, wheel, and GHCR immutable identity evidence |
| `delivery/evidence/deployment-v1.json` | Real Render deployment, public URL, health, and fixed-scenario smoke evidence |

### Project foundation records

| Path | Single responsibility |
|---|---|
| `src/vespercode/project/dependency_closure.py` | Task 4.A-owned declared-set/lock validator plus strict loader for the unique dependency-closure record |
| `config/dependency-closure-v1.json` | Unique persistent, machine-readable, non-secret `DependencyClosureV1` record carrying the public Python range and exact Task 1 Python identity |
| `scripts/bootstrap_formal_env.py` | Task 4.A-owned fail-closed `.venv-formal` materializer that verifies Task 1 exact Python identity before hash-only/no-dependency installation |
| `src/vespercode/project/toolchain_promotion.py` | Task 4.F-owned strict loader and gate-to-formal comparison for the promotion record |
| `config/formal-toolchain-promotion-v1.json` | Unique persistent, machine-readable, non-secret `FormalToolchainPromotionV1` record carrying the exact promoted Python/tool/config identities |

### Feasibility gates

| Path | Single responsibility |
|---|---|
| `gates/pytest.ini` | Gate-only pytest addopts and registration of every marker needed before Task 4 |
| `gates/ruff.toml` | Gate-only Ruff target/version-compatible formatting and lint rules |
| `gates/mypy.ini` | Gate-only strict Mypy configuration for spike and feasibility-test paths |
| `spikes/win32_workspace_boundary/probe.py` | Standalone Win32 identity, object, collision, ACL, and named-mutex feasibility probe |
| `spikes/win32_workspace_boundary/report.py` | Closed GO/NO-GO evidence schema for Task 1 |
| `spikes/docker_reference_boundary/probe.py` | Standalone OCI export, loopback registry lifecycle, no-self-reference, image-policy, mount, resource, report, and fingerprint feasibility probe |
| `spikes/docker_reference_boundary/report.py` | Closed Task 2 GO/NO-GO schema binding gate toolchain, registry lifecycle, three-way image digest, report, and boundary evidence |
| `spikes/docker_reference_boundary/pytest_reporter.py` | Gate-only explicitly loaded pytest event reporter proving complete machine-readable Task 2 evidence |
| `spikes/docker_reference_boundary/failure_fingerprint_probe.py` | Gate-only normalizer/comparator for stable Task 19 fingerprint inputs; never a production `FailureFingerprintV1` implementation |
| `spikes/persistence_recovery/protocol.py` | Standalone 1–3-file write/recovery prototype with typed preimages |
| `spikes/persistence_recovery/faults.py` | Enumerated deterministic interruption points for Task 3 |
| `spikes/persistence_recovery/report.py` | Closed GO/NO-GO matrix for Task 3 |
| `tests/feasibility/windows/test_workspace_boundary_gate.py` | Task 1 deterministic and Windows-backed gate tests |
| `tests/feasibility/docker/test_reference_boundary_gate.py` | Task 2 manifest and Docker-boundary tests |
| `tests/feasibility/persistence/test_recovery_gate.py` | Task 3 exhaustive fault-injection tests |

### Canonical contracts and profiles

| Path | Single responsibility |
|---|---|
| `src/vespercode/canonical/json_v1.py` | Exact canonical JSON encoding and Unicode-scalar validation |
| `src/vespercode/canonical/timestamp_v1.py` | Strict `CanonicalTimestampV1` parsing and epoch-millisecond conversion |
| `src/vespercode/canonical/clock.py` | Injectable system/fake UTC epoch-millisecond clock used before canonical timestamp creation |
| `src/vespercode/canonical/digest.py` | Domain-separated SHA-256 calculation |
| `src/vespercode/canonical/path_v1.py` | Lexical `CanonicalRelativePathV1` validation without filesystem access |
| `src/vespercode/contracts/optional.py` | Closed `ABSENT`/`PRESENT` discriminated unions |
| `src/vespercode/contracts/location.py` | `RepositoryLocationV1` and `DisclosurePathScopeV1` unions |
| `src/vespercode/contracts/run.py` | Run ids, limits, statuses, phases, wait kinds, and run-config value objects |
| `src/vespercode/contracts/action.py` | Shared action/result enums and immutable action identity value objects |
| `src/vespercode/contracts/evidence.py` | Shared digest, artifact reference, and bounded error value objects |
| `src/vespercode/profiles/editable.py` | Sole immutable `EditablePathPolicyV1` and segment-aware matching |
| `src/vespercode/profiles/reference.py` | `ReferenceProfileManifestV1` schema and integrity verification |
| `src/vespercode/profiles/llm.py` | Closed Mock/OpenAI LLM profile manifest variants |
| `src/vespercode/profiles/endpoints.py` | Sole trusted OpenAI endpoint mapping |
| `src/vespercode/profiles/registry.py` | Read-only built-in manifest registry |
| `src/vespercode/profiles/builtin/reference-profile-v1.json` | Packaged immutable reference profile bytes |
| `src/vespercode/profiles/builtin/mock-deterministic-v1.json` | Packaged immutable Mock profile bytes |
| `src/vespercode/profiles/builtin/openai-single-turn-v1.json` | Packaged immutable OpenAI profile bytes |

### State, admission, and Windows workspace boundary

| Path | Single responsibility |
|---|---|
| `src/vespercode/storage/connection.py` | SQLite connection policy, foreign keys, WAL choice, and transaction context |
| `src/vespercode/storage/migration_engine.py` | Closed `MigrationV1`, checksum history, and injectable ordered/atomic migration runner; no application-domain DDL or final registry import |
| `src/vespercode/storage/migrations/__init__.py` | Migration package marker with no registry or side-effect import |
| `src/vespercode/storage/migrations/v0001_run_wait.py` | Task 7.B immutable Run/config/wait schema migration |
| `src/vespercode/storage/migrations/v0002_idempotency.py` | Task 7.C immutable event-idempotency schema migration |
| `src/vespercode/storage/migrations/v0003_disclosure_grants.py` | Task 15.D immutable disclosure subject/Grant schema migration |
| `src/vespercode/storage/migrations/v0004_disclosure_authorizations.py` | Task 15.E immutable disclosure-authorization schema migration |
| `src/vespercode/storage/migrations/v0005_memory.py` | Task 22.A immutable workspace-memory schema migration |
| `src/vespercode/storage/migrations/v0006_audit.py` | Task 23.A immutable redacted-audit schema migration |
| `src/vespercode/storage/migrations/v0007_agent_turns.py` | Task 25.B immutable active-turn/counter schema migration |
| `src/vespercode/storage/migrations/v0008_feedback.py` | Task 24.C immutable feedback/consume-once schema migration |
| `src/vespercode/storage/migrations/v0009_actions.py` | Task 25.D immutable action-record schema migration |
| `src/vespercode/storage/migrations/v0010_writeback_approvals.py` | Task 14.B immutable final-writeback subject/approval schema migration |
| `src/vespercode/storage/migrations/v0011_persistence.py` | Task 26.A immutable persistence transaction/path schema migration |
| `src/vespercode/storage/migrations/v0012_recovery.py` | Task 26.C immutable terminal recovery-result schema migration |
| `src/vespercode/storage/migrations/registry.py` | Task 7.D sole composition of the exact immutable v1 migration constants as `ALL_V1_MIGRATIONS` |
| `src/vespercode/storage/run_repository.py` | Run, wait, and lifecycle compare-and-update persistence |
| `src/vespercode/storage/idempotency.py` | Event idempotency-key digest and conflict enforcement |
| `src/vespercode/runs/lifecycle.py` | Closed legal run transitions and terminal-state invariants |
| `src/vespercode/runs/request.py` | Strict `ValidateRunRequestV1`, validation, and frozen `RunConfigSnapshot` |
| `src/vespercode/runs/admission.py` | Ordered PREFLIGHT orchestration and zero-downstream-call failure semantics |
| `src/vespercode/workspace/identity_win32.py` | Canonical absolute path, volume identity, and final directory object identity |
| `src/vespercode/workspace/object_win32.py` | Final file/directory identity, reparse, ADS, hard-link, and ACL inspection |
| `src/vespercode/workspace/mutex_win32.py` | Cross-process named mutex keyed by workspace identity digest |
| `src/vespercode/workspace/git_preflight.py` | Sealed Git config/index/HEAD/blob/ignore/attribute preflight |
| `src/vespercode/workspace/path_guard.py` | Lexical plus final-object authorization and collision rejection |

### Immutable trees, candidate changes, and tools

| Path | Single responsibility |
|---|---|
| `src/vespercode/trees/content_store.py` | Immutable raw-byte content objects addressed by digest |
| `src/vespercode/trees/snapshot.py` | Single sealed `SnapshotTree` construction and integrity verification |
| `src/vespercode/trees/text_classifier.py` | Shared `SupportedTextFileV1` classification and `TextMetadataV1` |
| `src/vespercode/trees/candidate.py` | Immutable CandidateTree overlay and parent-independent tree digest |
| `src/vespercode/candidate/unified_diff.py` | Strict `UNIFIED_DIFF_V1` parser |
| `src/vespercode/candidate/patch_engine.py` | Whole-patch validation and atomic CandidateRevision derivation |
| `src/vespercode/candidate/final_diff.py` | `FinalDiffV1` and complete-postimage byte accounting |
| `src/vespercode/candidate/identity.py` | `CandidateIdentityV1` three-way digest |
| `src/vespercode/tools/file_actions.py` | Closed list/read/literal-search action schemas, cursor-free query identities, and distinct cursor inputs |
| `src/vespercode/tools/file_results.py` | Closed list/read/search result schemas, typed next cursors, and continuation error contracts |
| `src/vespercode/tools/list_files.py` | Stable directory-first listing over an immutable tree |
| `src/vespercode/tools/read_file.py` | Bounded line/byte reads over classified text |
| `src/vespercode/tools/search_text.py` | Stable literal search with non-text accounting |
| `src/vespercode/tools/dispatcher.py` | Phase-aware dispatch to explicitly registered tool ports |

### Governance, LLM boundary, loop, and validation

| Path | Single responsibility |
|---|---|
| `src/vespercode/governance/policy.py` | Versioned non-overridable `ALLOW/ASK/DENY` policy evaluation |
| `src/vespercode/governance/writeback_subject.py` | `FinalWritebackSubjectV1` construction and staleness checks |
| `src/vespercode/governance/writeback_approval.py` | Atomic one-time approval lifecycle |
| `src/vespercode/governance/request_sources.py` | Request segments, exact sources, path/category validation, and byte counts |
| `src/vespercode/governance/disclosure_subject.py` | `DisclosureGrantSubjectV1` construction and scope matching |
| `src/vespercode/governance/disclosure_ledger.py` | Grant state, atomic cumulative budget charge, and authorization records |
| `src/vespercode/llm/base.py` | Low-level single-turn `LLMAdapter` protocol and `ModelResponse` |
| `src/vespercode/llm/prepared_request.py` | Closed Mock/OpenAI prepared-request variants and digest validation |
| `src/vespercode/llm/mock_adapter.py` | Deterministic script-bound Mock adapter |
| `src/vespercode/llm/openai_serializer.py` | Exact segment-to-OpenAI body serialization |
| `src/vespercode/llm/openai_adapter.py` | One non-retried OpenAI call at the trusted endpoint |
| `src/vespercode/llm/call_result.py` | Closed `LLMCallResultV1` mode/status combinations |
| `src/vespercode/loop/agent_actions.py` | Six-action discriminated union plus check/completion action schemas |
| `src/vespercode/loop/action_parser.py` | Exactly-one-action JSON parsing with unknown-field rejection |
| `src/vespercode/loop/action_binding.py` | Harness action id plus semantic and instance digests |
| `src/vespercode/loop/context_projection.py` | Deterministic context assembly, source segments, and trimming |
| `src/vespercode/loop/feedback.py` | Structured bounded feedback creation, ordering, and single-turn consumption |
| `src/vespercode/loop/stopping.py` | Pure budget, invalid-output, and terminal stop aggregation over explicit component decisions |
| `src/vespercode/loop/progress.py` | Pure repeated-action and no-progress window calculation |
| `src/vespercode/loop/turn_boundary.py` | Single-active-turn and exact turn/call counter transitions |
| `src/vespercode/loop/call_orchestrator.py` | Fresh credential/authorization ordering and exactly one Mock/OpenAI call |
| `src/vespercode/loop/action_pipeline.py` | One parse → bind → policy → dispatch → feedback action step |
| `src/vespercode/loop/wait_control.py` | Wait enter/resume/expiry binding |
| `src/vespercode/loop/cancellation.py` | Deterministic cancellation safe-point evaluation |
| `src/vespercode/loop/restart.py` | Non-persistent active-turn restart fail-close |
| `src/vespercode/loop/engine.py` | Thin sequential composition of the Task 25.A–25.F components |
| `src/vespercode/execution/docker_profile.py` | Closed Docker execution profile v1 parameters and digest |
| `src/vespercode/execution/docker_executor.py` | Fresh-container execution with hard resource and mount boundaries |
| `src/vespercode/validation/check_result.py` | Closed pytest/Ruff/Mypy result and stable error schemas |
| `src/vespercode/validation/pytest_evidence.py` | Strict `PytestEvidenceV1` event validation |
| `src/vespercode/validation/pytest_reporter.py` | Harness-owned pytest report plugin |
| `src/vespercode/validation/failure_fingerprint.py` | Stable `CALL/FAIL` fingerprint normalization |
| `src/vespercode/validation/python_adapter.py` | Static detection plus closed baseline/validation check-plan generation |
| `src/vespercode/validation/baseline.py` | Ordered baseline and runtime-compatibility evaluation |
| `src/vespercode/validation/manifest.py` | Immutable `ValidationManifestV1` creation |
| `src/vespercode/validation/formal.py` | Full formal-success predicate and `VerifiedCandidate` creation |

### Persistence, memory, credentials, audit, and presentation

| Path | Single responsibility |
|---|---|
| `src/vespercode/persistence/path_record.py` | Typed preimage/postimage and per-path durable progress |
| `src/vespercode/persistence/transaction.py` | PREPARED/WRITING/terminal transaction state and durable transitions |
| `src/vespercode/persistence/artifacts.py` | Current-user ACL-verified backups and evidence artifacts |
| `src/vespercode/persistence/writeback.py` | Approval-bound atomic replace sequence and post-write verification |
| `src/vespercode/persistence/recovery_preview.py` | Read-only recovery inspection and three-value classification |
| `src/vespercode/persistence/recovery_apply.py` | Bound explicit recovery mutation under the workspace lease |
| `src/vespercode/persistence/recovery.py` | Thin public RecoveryService composition of preview and apply |
| `src/vespercode/memory/entry.py` | Closed memory kinds, creators, sources, and forbidden content |
| `src/vespercode/memory/repository.py` | Workspace-isolated memory CRUD |
| `src/vespercode/memory/selection.py` | Deterministic 20-entry/16-KiB context selection |
| `src/vespercode/audit/event.py` | Redacted immutable audit event schema |
| `src/vespercode/audit/repository.py` | Per-run monotonic audit sequence |
| `src/vespercode/audit/projection.py` | User-facing state/evidence projection without internal storage leakage |
| `src/vespercode/audit/retention.py` | 30-day ended-run audit cleanup that preserves unresolved recovery |
| `src/vespercode/credentials/port.py` | Credential store protocol used by the control plane |
| `src/vespercode/credentials/wincred_store.py` | Windows Credential Manager adapter and backend capability probe |
| `src/vespercode/credentials/service.py` | Hidden-entry set/status/update/clear lifecycle plus fail-closed per-call backend revalidation/read |
| `src/vespercode/web/security.py` | Loopback, Host/Origin, local session, CSRF, and security headers |
| `src/vespercode/web/app.py` | Formal local FastAPI composition root |
| `src/vespercode/web/local_composition.py` | Final typed local service/route assembly used by `vespercode serve` |
| `src/vespercode/web/run_lifecycle_workflow.py` | Typed run create/status/cancel application workflow |
| `src/vespercode/web/disclosure_workflow.py` | Typed disclosure-decision application workflow |
| `src/vespercode/web/writeback_workflow.py` | Typed exact-approval to persistence application workflow |
| `src/vespercode/web/run_workflows.py` | Milestone 29 typed workflow-port aggregate and route installer |
| `src/vespercode/web/routes_runs.py` | Run creation, state, and cancel routes |
| `src/vespercode/web/routes_disclosure.py` | Grant display and decision routes |
| `src/vespercode/web/routes_writeback.py` | Exact final diff review and writeback decision routes |
| `src/vespercode/web/routes_operations.py` | Deterministic registration of credential, memory, audit, and recovery routers |
| `src/vespercode/web/routes_credentials.py` | Non-revealing credential lifecycle routes |
| `src/vespercode/web/routes_memory.py` | Workspace memory view/create/confirm/clear routes |
| `src/vespercode/web/routes_recovery.py` | Recovery preview and explicit apply routes |
| `src/vespercode/web/routes_audit.py` | Redacted audit and evidence routes |
| `src/vespercode/web/templates/` | Server HTML templates with escaped untrusted text and accessible state labels |
| `src/vespercode/web/static/htmx.min.js` | Vendored pinned HTMX asset; no runtime CDN dependency |
| `src/vespercode/demo/types.py` | `DemoRunStatus`, `DemoDecision`, and demo-only identities |
| `src/vespercode/demo/scenario.py` | Versioned fixed Mock responses, simulated tool-result fixtures, and expected trace labels; no parser, policy, feedback, or stop rules |
| `src/vespercode/demo/executor.py` | `ToolPortsV1` adapter returning only fixed simulated results with zero formal capability adapters |
| `src/vespercode/demo/runner.py` | Public Demo orchestration through the shared Task 13/17/24/25 parser, policy, dispatcher, feedback, and stop core |
| `src/vespercode/demo/app.py` | Public Demo FastAPI composition of shared pure core plus Demo-only ports, sessions, renderer, and `/healthz` |
| `src/vespercode/demo/healthcheck.py` | Stdlib-only loopback `/healthz` probe used by the Demo container |
| `src/vespercode/demo/templates/demo.html` | Escaped, accessible, persistently simulation-labeled Demo presentation |
| `src/vespercode/cli.py` | `serve`, `recover`, status, and help entry points without secret arguments |
| `src/vespercode/cli_composition.py` | Task 38.F sole production recovery-CLI handler/service wiring after complete v1 database initialization |
| `src/vespercode/delivery/evidence.py` | Closed non-secret CI, release, and deployment evidence schemas |
| `src/vespercode/delivery/readme_verifier.py` | Read-only README section/command/link/digest contract verifier |
| `src/vespercode/delivery/process_verifier.py` | Read-only M0/cold-start/task/review/commit/PR process-evidence verifier |

### Fixtures, images, and test environments

| Path | Single responsibility |
|---|---|
| `reference/fixture/pyproject.toml` | Sole supported fixture pytest/Ruff/Mypy config |
| `reference/fixture/requirements.lock` | Fixture copy whose digest must match the built-in manifest |
| `reference/fixture/src/vesper_fixture/calculator.py` | Small deterministic defect and repair target under `src/` |
| `reference/fixture/tests/test_calculator.py` | Stable failing target plus passing non-target tests |
| `reference/manifest/reference-profile-v1.json` | Published manifest bytes bound to wheel and image digest |
| `containers/reference/Dockerfile` | Digest-pinned formal execution image recipe |
| `containers/demo/Dockerfile` | Public Demo image containing no formal capability adapters |
| `tests/unit/` | Offline deterministic unit tests by matching package responsibility |
| `tests/integration/windows/` | Real Win32 identity, path, ACL, Credential Manager, mutex, and persistence tests |
| `tests/integration/docker/` | Real Docker isolation, report, and reference-profile tests |
| `tests/fault_injection/persistence/` | Every persistence interruption and external-change point |
| `tests/e2e/reference/` | Full Windows + Docker + Mock-LLM reference workflow |
| `tests/e2e/mechanism/` | Governance interception, feedback correction, and deep-governance demo |
| `tests/web/` | Local WebUI security, workflows, status, rendering, and accessibility tests |
| `tests/demo/` | Demo capability absence, deterministic trace, session limit, and health tests |
| `tests/smoke/package/` | Wheel, SHA-256, clean pipx, and CLI/WebUI smoke tests |
| `tests/smoke/images/` | Reference and Demo OCI build/run contract tests |
| `tests/smoke/release/` | GitHub/GHCR/Render evidence-schema and alignment tests |

### Durable record storage classification and v1 migration ownership

This table is the complete storage-class decision for every SPEC §7 entity plus the additional durable repository records named by this PLAN. Each row has exactly one storage class. `SQLite migration owner` names the sole executable task that may introduce the listed v1 table; later tasks may consume or transactionally update that table only through the declared repository interface. `local artifact/config owner` means an ACL-restricted content-addressed artifact or immutable packaged configuration, not a SQLite body column. `in-memory only` means the state intentionally ends with the bounded process/session. `value object/no durable table` means the value may be embedded canonically in an owning record or referenced by digest but has no independent v1 table.

| SPEC §7 / PLAN record | Storage class | Sole owner and v1 representation |
|---|---|---|
| Migration history (PLAN migration-engine record) | SQLite migration owner | Task 7.A bootstraps only table `schema_migrations` with columns `(version PRIMARY KEY, name UNIQUE, checksum, applied_at)` inside `migration_engine.py`; no domain DDL is permitted there. |
| Run | SQLite migration owner | Task 7.B, `v0001_run_wait.py`, table `runs`; primary key `run_id`, immutable config FK, lifecycle revision compare-and-update fields, deadline/status/phase, and no body/secret columns. |
| RunLimitsV1 | value object/no durable table | Task 5.B owns the closed value; Task 8.A canonically embeds it inside the Task 7.B `run_config_snapshots` record. |
| EditablePathPolicyV1 | local artifact/config owner | Task 6.A owns the packaged immutable policy and digest; only the digest may be referenced by control records. |
| ReferenceProfileManifestV1 | local artifact/config owner | Task 6.B owns the packaged manifest bytes and digest. |
| LLMProfileManifestV1 | local artifact/config owner | Task 6.C owns the packaged Mock/OpenAI manifest bytes and digests. |
| RunConfigSnapshot | SQLite migration owner | Task 7.B, `v0001_run_wait.py`, table `run_config_snapshots`; primary key `config_snapshot_id`, unique canonical digest, frozen profile/policy/target/limit identities, and no credential value. |
| WorkspaceLease | in-memory only | Task 9.B owns the held Win32 named-mutex/handle lifetime; audit may retain bounded identity/timestamp facts, but SQLite never substitutes for the OS lease. |
| WaitContext | SQLite migration owner | Task 7.B, `v0001_run_wait.py`, table `wait_contexts`; primary key `wait_id`, FK `run_id → runs`, unique active wait per Run, exact kind/subject/expiry/decision binding, and no subject body. |
| SnapshotTree | local artifact/config owner | Tasks 10.A/10.C own content-addressed file bodies and the immutable tree manifest under the current-user artifact root; SQLite may retain only root digest/ref through owning Run records. |
| StaticProjectProfileResult | value object/no durable table | Task 20.A owns the closed result; its digest/evidence ref may be attached to Run/audit facts. |
| RepositoryLocationV1 | value object/no durable table | Task 5.E owns the closed location union. |
| ListFilesEntryV1 | value object/no durable table | Task 11.A owns the bounded result value. |
| RuntimeCompatibilityResult | local artifact/config owner | Task 20.B owns the bounded baseline evidence artifact; only digest/ref and closed status may enter control/audit records. |
| FailureFingerprintV1 | value object/no durable table | Task 19.C owns the deterministic derived value; owning evidence artifacts retain the source report. |
| ValidationManifestV1 | local artifact/config owner | Task 20.B owns the immutable manifest artifact and digest; control rows store only its identity/ref. |
| FinalDiffV1 | local artifact/config owner | Task 12.D owns the immutable structured artifact; complete postimage bytes remain in the Task 10.A content store and SQLite stores only allowed digest/ref fields. |
| CandidateIdentityV1 | value object/no durable table | Task 12.D owns the derived three-way identity. |
| CandidateRevision | local artifact/config owner | Tasks 12.B/12.C own the immutable candidate-tree artifact and parent metadata; ordinary turn restart remains non-persistent. |
| AgentTurn | SQLite migration owner | Task 25.B, `v0007_agent_turns.py`, table `agent_turns`; primary key `turn_id`, FK `run_id → runs`, partial uniqueness for one active turn per Run, exact counters/revision/outcome, and body-free request/result refs only. |
| ActionRecord | SQLite migration owner | Task 25.D, `v0009_actions.py`, table `action_records`; primary key `action_id`, FK `turn_id → agent_turns`, unique `(turn_id, action_id)`, digests/decision/result ref only, and no action/result body. |
| FeedbackRecord | SQLite migration owner | Task 24.C, `v0008_feedback.py`, table `feedback_records`; primary key `feedback_id`, nullable FK `consumed_by_turn_id → agent_turns`, one-winner consume predicate, bounded payload plus evidence refs, and no raw check body. |
| FinalWritebackSubjectV1 | SQLite migration owner | Task 14.B, `v0010_writeback_approvals.py`, table `final_writeback_subjects`; primary/unique subject digest, exact immutable binding columns, and artifact digests/refs rather than postimage bytes. |
| FinalWritebackApproval | SQLite migration owner | Task 14.B, `v0010_writeback_approvals.py`, table `final_writeback_approvals`; primary key `approval_id`, FK subject digest and wait id, one terminal decision plus one `PENDING → CONSUMED` winner, and no workspace bytes. |
| DisclosureGrantSubjectV1 | SQLite migration owner | Task 15.D, `v0003_disclosure_grants.py`, table `disclosure_grant_subjects`; primary/unique subject digest, frozen provider/endpoint/model/serializer/scope/category/budget/expiry facts, and no segment content. |
| DisclosureGrant | SQLite migration owner | Task 15.D, `v0003_disclosure_grants.py`, table `disclosure_grants`; primary key `grant_id`, FK subject digest/run/wait, `consumed_bytes` and `ACTIVE/REVOKED` state. Task 15.F owns the exact active-to-revoked transaction on this existing row; SPEC defines no separate revocation entity or v1 revocation table. |
| RequestContentSegmentV1 | local artifact/config owner | Tasks 15.A/25.C own the ACL-restricted complete prepared-request artifact; SQLite authorization/audit rows may retain only verified source indexes, paths, byte counts, digests, and refs. |
| MockAdapterPayloadV1 | local artifact/config owner | Task 16.A owns immutable Mock script/config plus bounded request artifact identity; it has no control table. |
| PreparedModelRequestV1 | local artifact/config owner | Tasks 16.A/16.B/25.C own the ACL-restricted request artifact; only request digest/ref and allowed source facts may be referenced in SQLite. |
| DisclosureAuthorizationRecordV1 | SQLite migration owner | Task 15.E, `v0004_disclosure_authorizations.py`, table `disclosure_authorizations`; primary key `authorization_id`, FK `grant_id → disclosure_grants`, unique request identity/charge, exact body-free actual-source projection, and no refund/body column. |
| LLMCallResultV1 | local artifact/config owner | Tasks 16.A/16.B/25.C own the ACL-restricted bounded response/error artifact; `agent_turns`, `action_records`, and audit may retain only closed status, digest, and ref. |
| PytestEvidenceV1 | local artifact/config owner | Task 19.B owns the complete bounded report artifact and integrity digest; SQLite stores at most an allowed digest/ref. |
| CheckResult | local artifact/config owner | Task 19.A owns the structured result plus ACL-restricted raw-output artifact; raw output never enters SQLite. |
| VerifiedCandidate | local artifact/config owner | Task 21.C owns the immutable verification evidence artifact and digest; writeback subject/approval rows bind its identity/ref. |
| PersistenceTransaction | SQLite migration owner | Task 26.A, `v0011_persistence.py`, table `persistence_transactions`; primary key `transaction_id`, FKs to Run/approval, unique active transaction per workspace, exact state/digests/artifact refs, and no backup bytes. |
| PersistencePathRecord | SQLite migration owner | Task 26.A, `v0011_persistence.py`, table `persistence_path_records`; composite primary key `(transaction_id, sequence)`, FK to transaction, unique `(transaction_id, canonical_path)`, operation/preimage/postimage digests and progress evidence refs only. |
| RecoveryResult | SQLite migration owner | Task 26.C, `v0012_recovery.py`, table `recovery_results`; primary key `recovery_result_id`, FK/unique terminal `transaction_id`, closed disposition and evidence digest/ref only. Recovery backup bytes stay in Task 26.A ACL artifacts. |
| MemoryEntry | SQLite migration owner | Task 22.A, `v0005_memory.py`, table `memory_entries`; primary key `memory_id`, indexed workspace identity, closed kind/creator/source/bounds/timestamps and nullable clear tombstone; no secret, permission, or complete source body. |
| AuditEvent | SQLite migration owner | Task 23.A, `v0006_audit.py`, table `audit_events`; composite uniqueness `(run_id, sequence)`, FK `run_id → runs`, allowlisted bounded redacted payload and evidence refs only. |
| Idempotency event (PLAN repository record) | SQLite migration owner | Task 7.C, `v0002_idempotency.py`, table `idempotency_events`; composite primary key `(scope, event_id)`, immutable request/result digests, and no reconstructed domain body. |
| Content object / complete file body (PLAN artifact record) | local artifact/config owner | Task 10.A owns digest-verified ACL-restricted bytes; control rows retain only content digests/refs. |
| Persistence backup and raw recovery evidence (PLAN artifact record) | local artifact/config owner | Task 26.A owns ACL-restricted bytes and verified refs; Task 26.C never copies the bodies into `recovery_results`. |
| Credential record (PLAN external-store record) | local artifact/config owner | Task 27.B owns the Windows Credential Manager entry outside repository artifacts and SQLite; status/audit exposes no value or derivative. |
| DemoSession | in-memory only | Task 30.A owns the bounded expiring Demo session store; it is capability-isolated from the formal control database. |
| DemoDecision | in-memory only | Task 30.A owns the fixed-scenario decision in its Demo session; it cannot become a formal authorization. |

The ordered migration sequence is exactly v0001 through v0012 with no duplicate, gap, or unexpected version. A domain migration test applies Task 7.A's engine to the tuple of the actual immutable predecessor constants plus the current constant; no domain task edits or imports `registry.py`. Task 7.D alone imports the twelve constants, verifies the declared `(version, name, checksum)` order, and exports `ALL_V1_MIGRATIONS`. Its test-only owner map applies every exact prefix to empty temporary SQLite, proves each version's newly visible `sqlite_schema` table delta matches the sole-owner rows above, handles Task 7.A's `schema_migrations` bootstrap separately at v0001, and proves the final set is exactly all 18 declared SQLite tables; production registry code neither contains nor imports that expected map. Complete file bodies, complete LLM requests/responses, raw check output, and recovery backup bytes remain current-user ACL-restricted artifacts; only the explicitly allowed digests/refs above may enter SQLite, and credentials never do.

## M0 — SPEC Readiness Gate

M0 is not a formal implementation task and has no task number. This PLAN revision remains a non-authoritative draft until every M0 check passes.

1. Resolve exactly one authoritative SPEC path from the user's designation, document status, and current Git/filesystem facts. Any unresolved competing SPEC candidate fails M0.
2. Recompute, never copy, the authoritative SPEC identities with SHA-256 and `git hash-object --no-filters SPEC.md`, and record `git rev-parse HEAD`.
3. Compare the exact SPEC against `AI4SE_Final_Project_通用要求.md`, `AI4SE_Final_Project_A_Coding_Agent_Harness(1).md`, and applicable `AGENTS.md`; any conflict or missing mandatory deliverable fails M0.
4. Confirm all known blockers are closed in the exact SPEC: GitHub Actions plus GitLab CI; canonical List/Search cursors; per-real-call credential revalidation; `PlanSemanticDigestV1` execution-tracking exclusions; a Task 1-owned reproducible gate bootstrap that Tasks 2–3 consume without Task 4 or global pytest/Ruff/Mypy; and Task 2's no-credential loopback-registry digest round-trip/no-self-reference contract with real GHCR publication reserved for Task 36.
5. Require the human to approve the exact authoritative SPEC path, SHA-256, Git blob, and baseline commit. Record the approval externally in `SPEC_PROCESS.md`; never write a digest into the file it identifies.
6. For this draft, the recomputed candidate identity is `SPEC.md`, SHA-256 `80ccc86d9c06bdf7b4fed8673e2e6879942ca2cbc2b07c91bf1276b19a7447aa`, Git blob `2cc522eeb2eb61e75ce96b6500ebbfdf8db18499`, baseline commit `f6aa9897ca8e9f3cab86143b880a306d96a252e1`. These values are observations, not an approval.
7. If any check or approval fails, return to SPEC revision/clarification. Do not freeze this PLAN, run cold-start work, or begin Task 1.

After M0 passes, compute `PlanSemanticDigestV1` exactly as SPEC §11.2: normalize the no-BOM UTF-8 PLAN to LF; only inside `## Formal Tasks` through the byte before `## Task Dependency DAG`, normalize `**Status:** ...`, `[ ]`/`[x]`, and one-line `**Completion evidence:** ...` using the declared replacement tokens; leave every other byte intact; hash `b"VesperCode\0PLAN_SEMANTIC_CONTRACT_V1\0" + projected_plan_bytes` with SHA-256. Store that digest and the complete-file PLAN SHA-256 in the external approval record. Only those three enumerated tracking updates preserve semantic approval; every other PLAN change requires a new semantic digest, human approval, and cold-start.

## Pre-implementation Cold-start Gate

This gate is not a formal implementation task and has no task number.

1. M0 must have passed, and the user must approve the exact `SPEC.md` SHA-256/Git blob plus externally computed `PlanSemanticDigestV1` as one semantic contract. The complete `PLAN.md` SHA-256 is recorded as the audit snapshot.
2. The trial agent must be a different agent type from the primary development agent.
3. The trial uses a new session with no prior conversation, memory, `AGENT_LOG.md`, `SPEC_PROCESS.md`, `TASK_HANDOFF.md`, or oral explanation.
4. The trial agent receives only the approved SPEC and PLAN.
5. The user selects one or two tasks from formal Tasks 1–3 for an isolated 1–2-hour execution-readiness trial.
6. The trial agent must stop and ask when a contract is uncertain; guessing is a failure signal.
7. Trial code, branch, worktree, and commits are disposable, unmerged, and unavailable to formal implementation.
8. Record every pause, misunderstanding, implicit assumption, contract gap, and deviation in `SPEC_PROCESS.md`.
9. Revise SPEC or PLAN when the trial exposes a real gap. Any SPEC change or non-tracking PLAN change requires rerunning M0 as applicable, recomputing identities, and repeating human approval and cold-start; the three enumerated execution-tracking changes alone do not.
10. Record the final approved SPEC identity, `PlanSemanticDigestV1`, complete PLAN SHA-256 audit snapshot, heterogeneous agent type, exact trial scope, findings, revisions, and pass decision.
11. Formal Task 1 remains blocked until this gate passes.

## Formal Tasks

### Formal Task Decomposition Contract

- A heading named `Milestone N` is a non-executable traceability container. It may retain the former Task's aggregate Goal, SPEC references, file inventory, interfaces, acceptance example, review checklist, and proposed branch text so no domain contract is lost, but none of those retained tracking fields or steps authorizes execution. A Milestone has no implementation branch, worktree, commit, evidence commit, or PR of its own; its status and completion evidence are derived only from all listed executable child tasks.
- A heading named `Task N.X` is one formal executable task. Each child receives a fresh subagent, branch, worktree, implementation commit, two review gates, evidence commit, and PR.
- The executable registry is closed: retained integer Task 13 plus 134 dotted child Tasks, for 135 executable Tasks total. The 37 `Milestone N` headings are non-executable containers and never appear as nodes in canonical DAG, wave, ownership, coverage, test-environment, or release structures.
- An implementer may rely only on Global Constraints, the applicable Milestone contract, and their own child-task block. Child blocks therefore declare exact files, interfaces, dependencies, RED test, implementation boundary, and commands.
- Every executable child follows this exact workflow:
  1. Add the displayed intentionally failing test without production implementation.
  2. Run the child `Target` command and record the expected contract-specific failure.
  3. Implement only the interfaces and behavior named in the child block.
  4. Re-run `Target` and obtain GREEN.
  5. Refactor only the child-owned files without behavior change; re-run `Target`.
  6. Run the child `Domain` command and every declared real-environment command.
  7. Run `python -m pytest -q`.
  8. Run all five standard closure commands from Global Constraints.
  9. Request a fresh SPEC-compliance review using the child Goal, references, RED/GREEN evidence, and declared artifacts.
  10. Close every Critical/Important SPEC finding and repeat Steps 6–9.
  11. Request a fresh code-quality review focused on the child-owned files and interfaces.
  12. Close every Critical/Important quality finding and repeat Steps 6–11.
  13. Commit only the child-owned implementation/tests, record the real SHA and evidence in the same PR, then merge in dependency/wave order.
- A child test block may contain several assertions only when they prove one primary behavior. A second independently rejectable behavior requires another child task.
- A final composition/acceptance child may consume prior children but may not silently add their missing production behavior. Browser, CI, registry, release, and deployment children use verifier-first TDD locally and then require the declared real external result.
- Prose refers to an aggregate only as `Milestone N`. Every executable reference uses exact `Task N.X`, except retained integer Task 13; completion of a split Milestone is derived only when all of its exact children are complete.

### Milestone 1: Win32 Workspace Safety Boundary Feasibility Gate

**Status:** Not started

**Goal:** Produce a Windows 11 x64 GO/NO-GO artifact proving that VesperCode can bind lexical paths to stable Win32 volume/final-object identities and enforce the required cross-process workspace boundary.

**SPEC / FR / NFR / AC references:** SPEC §0.1 `CanonicalRelativePathV1`; §1.4.3; §4.1 behavior 6–10; §4.3 behavior 4–5; §5.2; §5.5; §10.1 AC-01, AC-15, AC-21, AC-26, AC-31; §10.3 Windows integration; §11.2 item 1.

**Dependencies:** None — after cold-start gate.

**Blocks:** Task 1.E is the terminal gate. Its `NO_GO` blocks every later executable Task and requires SPEC revision plus a new approved digest pair.

**Parallelization:** Sequential.

**Recommended branch:** `codex/task-01-win32-boundary-gate`

**Recommended worktree:** `.worktrees/task-01-win32-boundary-gate`

**Files:**
- Create: `requirements/gate.lock`
- Create: `gates/pytest.ini`
- Create: `gates/ruff.toml`
- Create: `gates/mypy.ini`
- Create: `scripts/run_gate_checks.py`
- Create: `spikes/win32_workspace_boundary/probe.py`
- Create: `spikes/win32_workspace_boundary/report.py`
- Test: `tests/feasibility/windows/test_workspace_boundary_gate.py`
- Modify: `PLAN.md` (completion record only; line is intentionally unresolved until execution)
- Modify: `AGENT_LOG.md` (append-only execution evidence)

**Interfaces:**
- Consumes: Windows 11 x64; Python `>=3.12,<3.13`; an isolated `.venv-gate`; a disposable NTFS workspace; Win32 handle, volume, file-information, ACL, and named-mutex APIs. No global pytest/Ruff/Mypy or later formal-project file is a valid dependency.
- Produces:
  - a reviewed `requirements/gate.lock` containing exact direct/transitive versions and distribution hashes for pytest 8.x, Ruff, Mypy, and the minimum typed Windows test dependencies
  - `GateArgumentSequenceV1`, an immutable ordered tuple of zero or more `str` values, and `BoundaryObservationSequenceV1`, an immutable ordered tuple of one or more `BoundaryObservationV1` values
  - `run_gate_checks(command: GateCommandV1, arguments: GateArgumentSequenceV1) -> int`
  - `GateToolchainEvidenceV1(python_version: str, pytest_version: str, ruff_version: str, mypy_version: str, gate_lock_sha256: str, pytest_config_sha256: str, ruff_config_sha256: str, mypy_config_sha256: str, runner_sha256: str)`
  - `WorkspaceObjectIdentityV1(canonical_absolute_path: str, volume_serial_number: int, file_id_128: bytes, object_kind: Literal["FILE","DIRECTORY"], link_count: int, reparse_tag: int)`
  - `WorkspaceObjectProbeResultV1(observations: BoundaryObservationSequenceV1, cleanup_verified: bool)`
  - `probe_workspace_objects(workspace: Path, case_manifest: BoundaryCaseManifestV1) -> WorkspaceObjectProbeResultV1`
  - `WorkspaceMutexProbeResultV1(workspace_identity_digest: str, contender_count: int, maximum_concurrent_holders: int, timeout_count: int, cleanup_verified: bool)`
  - `probe_workspace_mutex(workspace_identity_digest: str, contender_count: int, timeout_ms: int) -> WorkspaceMutexProbeResultV1`
  - `WorkspaceBoundaryGateReportV1(outcome: Literal["GO","NO_GO"], gate_toolchain: GateToolchainEvidenceV1, object_probe: WorkspaceObjectProbeResultV1, mutex_probe: WorkspaceMutexProbeResultV1, evaluation: BoundaryEvaluationV1, evidence_digest: str)`
  - `assemble_workspace_boundary_report(toolchain: GateToolchainEvidenceV1, object_probe: WorkspaceObjectProbeResultV1, mutex_probe: WorkspaceMutexProbeResultV1) -> WorkspaceBoundaryGateReportV1`

**Implementation points:**
- Before the first RED command, create `.venv-gate` with Python 3.12, install only with `--require-hashes -r requirements/gate.lock`, and capture exact installed versions. The lock is GO evidence: it must enumerate every direct/transitive distribution and hash, and Tasks 2–3 may not resolve or upgrade it.
- `gates/pytest.ini` registers `windows_integration` and `docker_integration` plus every later feasibility marker used before Task 4.A; `gates/ruff.toml` and `gates/mypy.ini` fully specify the spike/test rules. `scripts/run_gate_checks.py` rejects the wrong interpreter, a lock/config digest mismatch, implicit pytest config, and commands outside its four-value enum.
- Every pytest call uses `-c gates/pytest.ini`; every Ruff/Mypy call uses its exact gate config. The runner must expose the fully constructed argv in non-secret GO evidence, never delegate to a shell, and never search upward for `pyproject.toml`.
- Open paths with no-follow semantics and obtain normalized final path, volume serial, 128-bit file id, kind, reparse tag, link count, and observable ACL from handles, not string normalization alone.
- Reject device paths, UNC paths, drive-relative paths, ADS, reserved names, trailing dots/spaces, `.`/`..`, empty segments, and aliases before authorization.
- Create controlled case-fold and Unicode-collision names and prove collision detection is deterministic without Unicode normalization in canonical identities.
- Create real symlink, junction/reparse, and hard-link cases. A final object mismatch, reparse object, or link count greater than one must fail closed.
- Compare file and directory final identities before and after open. Any lexical/final mismatch is `NO_GO`.
- Launch two independent processes against the same named mutex and prove at most one holder enters the critical section.
- Exercise an ACL-denied child and an ACL-safe child. If safe ACL state cannot be observed without reading protected content, return `NO_GO`.
- The report contains one named observation for every required contract plus `GateToolchainEvidenceV1`. GO is calculated only when the complete required-name set is present and passing and every installed version and gate file SHA-256 matches the frozen bootstrap; callers cannot supply `outcome`.

**Implementation boundary:** This executable Task owns one feasibility decision: whether the complete Task 1 Win32 workspace boundary can produce `GO` under the frozen gate bootstrap. Bootstrap files are supporting inputs to that single predicate; no production workspace adapter or later application behavior is implemented.

**Intentionally failing test:**

```python
def test_gate_fails_when_lexical_path_and_final_object_disagree(
    ntfs_boundary_case: NTFSBoundaryCase,
) -> None:
    object_probe = probe_workspace_objects(
        ntfs_boundary_case.workspace,
        ntfs_boundary_case.case_manifest,
    )
    mutex_probe = probe_workspace_mutex(
        ntfs_boundary_case.workspace_identity_digest,
        contender_count=2,
        timeout_ms=2_000,
    )
    report = assemble_workspace_boundary_report(
        ntfs_boundary_case.toolchain,
        object_probe,
        mutex_probe,
    )
    assert report.outcome == "NO_GO"
    assert report.object_probe.observations[0].code == "FINAL_OBJECT_IDENTITY_MISMATCH"
    assert report.evaluation.passed is False
```

**Verification:**
- Bootstrap: `py -3.12 -m venv .venv-gate`, then `.venv-gate\Scripts\python.exe -m pip install --disable-pip-version-check --require-hashes -r requirements/gate.lock`
- Target: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/windows/test_workspace_boundary_gate.py::test_gate_fails_when_lexical_path_and_final_object_disagree -q`
- Domain: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/windows/test_workspace_boundary_gate.py -q`
- Cross-process probe: `.venv-gate\Scripts\python.exe spikes/win32_workspace_boundary/probe.py --workspace tests/.tmp/win32-gate --json-report tests/.tmp/win32-gate-report.json`
- Expected: hash-locked installation succeeds; target and full test exit `0`; probe exits `0`, reports `outcome="GO"`, lists every required observation with `passed=true`, and records exact Python/pytest/Ruff/Mypy plus lock/config/runner SHA-256 values. Any unpinned distribution, digest drift, unsupported fixture, or unprovable identity exits nonzero with `outcome="NO_GO"`.

**Review gate:**
1. Spec compliance review checks the gate bootstrap contract plus every bullet in §11.2 item 1 and AC-01/15/21/24/26/31 against a named observation and verifies that no global tool, implicit config, unpinned dependency, or string-only fallback can yield GO.
2. Code quality review checks handle lifetime, deterministic cleanup, process race orchestration, Windows error mapping, no-follow deletion, and test independence.
3. Critical or Important findings, a missing case, or NO-GO blocks Task 2.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Establish the exact gate bootstrap and write the failing final-object test.** Create the hash-complete `requirements/gate.lock`, the three explicit `gates/` configs, and `scripts/run_gate_checks.py`; record the version-selection source and complete direct/transitive hashes in the review evidence. Create the test above and the `NTFSBoundaryCase` fixture in `tests/feasibility/windows/test_workspace_boundary_gate.py`; mark the module `windows_integration`, and make the fixture create a real junction whose lexical child resolves outside the authorized directory.
- [ ] **Step 2: Build the isolated gate environment and run RED.** Run the two Bootstrap commands, then the exact Target command above. Expected: the install uses only locked hashes; the test exits nonzero because `probe_workspace_objects`, `probe_workspace_mutex`, and `assemble_workspace_boundary_report` do not exist. A global-tool fallback, missing hash, unregistered marker, or implicit config is a gate failure, not permission to continue.
- [ ] **Step 3: Implement the smallest handle-based probe.**

  ```python
  object_probe = probe_workspace_objects(workspace, case_manifest)
  mutex_probe = probe_workspace_mutex(
      workspace_identity_digest,
      contender_count=2,
      timeout_ms=2_000,
  )
  report = assemble_workspace_boundary_report(toolchain, object_probe, mutex_probe)
  ```

  `probe_workspace_objects` must use Win32 handle information and return a stable error observation when any identity field cannot be proven; the mutex probe and report assembler remain their exact child-owned boundaries.
- [ ] **Step 4: Run GREEN.** Re-run the exact Target command through `.venv-gate` and `scripts/run_gate_checks.py`. Expected: exit `0`, with the junction rejected by final-object identity rather than by a lexical prefix comparison.
- [ ] **Step 5: Refactor without behavior change.** Keep observation evaluation, Win32 object probing, mutex probing, and closed report assembly in their exact Task 1.B–1.E owner modules; do not add a production workspace adapter in this task.
- [ ] **Step 6: Run the complete Windows gate.** Run the exact Full gate command through `.venv-gate` and the gate runner. Expected: all collision, ADS, device/UNC/drive-relative, reparse, hard-link, file/directory identity, ACL, and mutex cases pass, and the report includes matching toolchain/file identities.
- [ ] **Step 7: Run the current offline suite.** Run `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- -q`. Expected: exit `0`; only existing documentation/gate tests run at this stage and pytest reports `gates/pytest.ini` as its sole project config.
- [ ] **Step 8: Run static, whitespace, and secret checks.** Run `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py ruff-format -- spikes/win32_workspace_boundary tests/feasibility/windows`, `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py ruff-check -- spikes/win32_workspace_boundary tests/feasibility/windows`, `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py mypy -- spikes/win32_workspace_boundary tests/feasibility/windows`, and `git diff --check`. Then run this filename-only scan:

  ```powershell
  $patterns = @('api[_-]?key\s*[:=]', 'private[_-]?key\s*[:=]', 'credential\s*[:=]', 'password\s*[:=]')
  Get-ChildItem spikes\win32_workspace_boundary,tests\feasibility\windows -Recurse -File |
    Select-String -Pattern $patterns -List |
    Select-Object -ExpandProperty Path
  ```

  Expected: the runner verifies every gate digest; static commands exit `0`, `git diff --check` is silent, and the scan prints no paths.
- [ ] **Step 9: Request spec compliance review.** Give a fresh read-only reviewer Task 1, SPEC §0.1/§1.4.3/§4.1/§4.3/§11.2, and the complete diff. Require a case-by-case GO/NO-GO table.
- [ ] **Step 10: Close spec findings.** The responsible Task 1 subagent makes only the minimal changes for all Critical/Important findings, reruns Steps 6–8, and obtains a passing spec re-review.
- [ ] **Step 11: Request code quality review.** Give a fresh read-only reviewer the passing spec result, implementation, tests, and gate report. Require explicit inspection of handle cleanup and race determinism.
- [ ] **Step 12: Close quality findings.** The responsible or explicitly assigned repair subagent closes every Critical/Important quality finding, reruns Steps 6–8, and obtains a passing quality re-review.
- [ ] **Step 13: Commit, record, and open one PR only after GO.** Task 1.E commits the gate evidence only after `GO`; its `NO_GO` records findings in `SPEC_PROCESS.md`, stops without marking Milestone 1 complete, and opens no implementation PR for later Tasks.

### Milestone 2: Reference Profile and Docker Execution Boundary Feasibility Gate

**Status:** Not started

**Goal:** Prove that one content-addressed reference profile, fixture, dependency lock, and single-platform OCI image can complete a no-credential loopback-registry digest round-trip and execute complete pytest/Ruff/Mypy evidence inside the frozen no-network, non-root, read-only Docker boundary.

**SPEC / FR / NFR / AC references:** SPEC §1.4.1 `ReferenceProfileManifestV1`; §1.4.5; §4.1 behavior 11–13; §4.5; §5.5; §8.2; §8.4; §10.1 AC-04, AC-19, AC-20, AC-24, AC-25, AC-30; §10.3 Docker integration; §11.2 item 2.

**Dependencies:** Task 1 GO.

**Blocks:** Task 2.G is the terminal gate. Its `NO_GO`, any digest transformation, manifest self-reference, external-registry attempt, or temporary-registry cleanup failure blocks every later executable Task and requires SPEC revision plus renewed approval.

**Parallelization:** Sequential.

**Recommended branch:** `codex/task-02-reference-docker-gate`

**Recommended worktree:** `.worktrees/task-02-reference-docker-gate`

**Files:**
- Create: `requirements/reference.lock`
- Create: `reference/fixture/pyproject.toml`
- Create: `reference/fixture/requirements.lock`
- Create: `reference/fixture/src/vesper_fixture/calculator.py`
- Create: `reference/fixture/tests/test_calculator.py`
- Create: `reference/manifest/reference-profile-v1.json`
- Create: `containers/reference/Dockerfile`
- Create: `spikes/docker_reference_boundary/probe.py`
- Create: `spikes/docker_reference_boundary/report.py`
- Create: `spikes/docker_reference_boundary/pytest_reporter.py`
- Create: `spikes/docker_reference_boundary/failure_fingerprint_probe.py`
- Test: `tests/feasibility/docker/test_reference_boundary_gate.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 1 GO evidence and its immutable `requirements/gate.lock`, gate configs, runner, tool versions, and SHA-256 matrix; Docker Desktop Linux-container mode; a digest-pinned Linux base image; a digest-pinned loopback registry image embedded as a closed Task 2 probe constant. Task 2 may add the separately locked reference-image dependencies, but may not re-resolve or upgrade the host gate toolchain.
- Produces:
  - `ReferenceBuildInputV1(base_image_digest: str, registry_image_digest: str, requirements_digest: str, fixture_tree_digest: str, tool_versions_digest: str, build_recipe_version: str)` and `freeze_reference_build_input(root: Path) -> ReferenceBuildInputV1`
  - `ReferenceImageBuildEvidenceV1(local_oci_manifest_digest: str, image_config_digest: str, recipe_digest: str, platform: str, self_reference_scan_passed: bool)` and `build_reference_image(build_input: ReferenceBuildInputV1) -> ReferenceImageBuildEvidenceV1`
  - `LoopbackRegistryEvidenceV1(registry_image_digest: str, bind_host: Literal["127.0.0.1"], assigned_port: int, credentials_used: Literal[False], external_push_count: Literal[0], local_oci_manifest_digest: str, registry_repo_digest: str, digest_pull_repo_digest: str, cleanup_verified: bool)` and `probe_loopback_registry(build: ReferenceImageBuildEvidenceV1) -> LoopbackRegistryEvidenceV1`
  - `ContainerIsolationEvidenceV1(network_disabled: bool, non_root: bool, root_read_only: bool, capabilities_dropped: bool, docker_socket_absent: bool, workspace_read_only: bool, tmpfs_bounded: bool, cpu_limit: int, memory_limit_bytes: int, pid_limit: int, cleanup_verified: bool)` and `probe_reference_container(build: ReferenceImageBuildEvidenceV1, fixture: Path) -> ContainerIsolationEvidenceV1`
  - `GatePytestEventSequenceV1`, an immutable ordered tuple of `GatePytestEventV1` values, `GatePytestReportV1(planned_node_ids: TestIdSequenceV1, collected_node_ids: TestIdSequenceV1, events: GatePytestEventSequenceV1, normal_end: bool, exit_code: int, integrity_digest: str)`, and `validate_gate_pytest_report(report: GatePytestReportV1) -> GatePytestEvidenceResultV1`
  - `GateFailureFingerprintInputV1(node_id: str, phase: Literal["CALL"], outcome: Literal["FAIL"], normalized_message: str, location: CanonicalGateLocationV1)`, `GateFingerprintComparisonV1(equal: bool, left_digest: str, right_digest: str)`, `normalize_call_fail_input(report: GatePytestReportV1, node_id: str) -> GateFailureFingerprintInputV1`, and `compare_failure_inputs(left: GateFailureFingerprintInputV1, right: GateFailureFingerprintInputV1) -> GateFingerprintComparisonV1`
  - `ReferenceProfileManifestV1`, `DockerBoundaryGateReportV1(outcome: Literal["GO","NO_GO"], build_input: ReferenceBuildInputV1, build: ReferenceImageBuildEvidenceV1, registry: LoopbackRegistryEvidenceV1, isolation: ContainerIsolationEvidenceV1, pytest_evidence: GatePytestEvidenceResultV1, fingerprint: GateFingerprintComparisonV1, gate_toolchain: GateToolchainEvidenceV1, evidence_digest: str)`, and `assemble_reference_gate_report(command: AssembleReferenceGateReportV1) -> DockerBoundaryGateReportV1`
  - a fixed reference fixture whose target failure has one byte-identical normalized `GateFailureFingerprintInputV1` across independent runs; Task 19.C remains the sole owner of production `FailureFingerprintV1`

**Implementation points:**
- Pin the base image and loopback registry image by digest and every Python dependency by exact version/hash. `requirements/reference.lock` and the fixture copy must be byte-identical.
- Freeze one Linux target platform, builder version, manifest media type, compression parameters, and provenance/SBOM attestation settings. Export one OCI manifest, compute `local_oci_manifest_digest`, push the exact manifest/blobs to the loopback registry, capture its returned `registry_repo_digest`, pull by that digest, and require the pulled `digest_pull_repo_digest` to equal both.
- Start the temporary registry with an OS-assigned loopback port, no credentials, no Docker Desktop credential reuse, no LAN/public binding, and fresh disposable data. Cleanup must be verified after success, failure, timeout, cancellation, and an injected probe exception.
- Generate the final `ReferenceProfileManifestV1` only after the three digest observations agree. The manifest binds that digest, requirements digest, execution profile version `1`, exact tool versions, check-plan version, and immutable editable policy.
- The final reference manifest and any file containing its `digest` or `docker_image_digest` are forbidden from the image build context, layers, config, annotations, and attestations. Image-contained tool/profile evidence must be a separate non-self-referential build record.
- The Dockerfile must copy the exact gate reporter and fingerprint probe bytes whose versions/SHA-256 values appear in `DockerBoundaryGateReportV1`; the gate fails when image-observed bytes, report identities, Task 1 toolchain identities, or the `ReferenceProfileManifestV1.report_plugin_version` relation disagree.
- Build the image before execution; the gate must never install dependencies or build an image while a check is running.
- Invoke a fresh container and fresh candidate materialization for collect-only, full pytest, target rerun, Ruff, and Mypy.
- Inspect runtime user, capabilities, mounts, network mode, root filesystem, Docker-socket absence, tmpfs, CPU, memory, PID, and output limits from the actual container configuration.
- The candidate tree is mounted read-only at `/workspace`; all caches and reports use bounded tmpfs. A fixture write attempt into `/workspace` must fail without corrupting the machine-readable report.
- The gate report plugin must be loaded by explicit `-p spikes.docker_reference_boundary.pytest_reporter` (or an equally explicit closed runner argument recorded in evidence), with pytest autoload disabled. It emits complete ordered events, normal end marker, planned/collected node ids, exit code, and integrity digest. Missing, truncated, duplicate, implicitly loaded, or identity-mismatched evidence produces NO-GO.
- Execute the target failure twice in independent containers and use `failure_fingerprint_probe.py` to prove byte-identical normalized `CALL/FAIL` inputs. The probe may normalize and compare Task 19.C inputs only; it must not expose `FailureFingerprintV1`, production error taxonomy, or a production validator.
- Record the local OCI, loopback registry, and digest-pull identities during the gate. They must be equal to `ReferenceProfileManifestV1.docker_image_digest`; local image ID/config digest remain diagnostic only. GHCR publication is Task 36.B; this task must not authenticate to or push any external registry.

**Implementation boundary:** This executable Task owns one feasibility decision: whether the exact reference image/profile can complete the declared digest round-trip and locked execution proof. It adds no production Docker executor, registry publication, CI, release, or alternate profile.

**Intentionally failing test:**

```python
def test_gate_rejects_loopback_registry_digest_mismatch() -> None:
    assert assemble_reference_gate_report(mismatched_digest_command()).outcome == "NO_GO"
```

**Verification:**
- Target: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_reference_boundary_gate.py::test_gate_rejects_loopback_registry_digest_mismatch -q`
- Domain: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_reference_boundary_gate.py -q`
- Real build/probe: `.venv-gate\Scripts\python.exe spikes/docker_reference_boundary/probe.py --manifest-output reference/manifest/reference-profile-v1.json --fixture reference/fixture --registry-bind 127.0.0.1 --registry-port 0 --pytest-plugin spikes.docker_reference_boundary.pytest_reporter --fingerprint-probe spikes/docker_reference_boundary/failure_fingerprint_probe.py --report tests/.tmp/docker-gate-report.json`
- Expected: Task 1 gate identities match before execution; target/full tests exit `0`; real probe exits `0` with `outcome="GO"`; local OCI, loopback registry, and digest-pull digests equal the final `ReferenceProfileManifestV1.docker_image_digest`; the registry used no credential/external binding and was removed with its data; the image excludes the final manifest; explicit reporter load, reporter/probe SHA-256, complete reports, byte-identical failure inputs, and all frozen boundary checks pass.

**Review gate:**
1. Spec compliance review maps the immutable Task 1 bootstrap, explicit reporter load, reporter/probe identity binding, loopback-only registry lifecycle, three-way digest equality, no-self-reference build order, every §1.4.5 flag, manifest field, check, normalized Task 19 input, and image/lock/fixture relation to executable evidence; it rejects any claim that the probe is the Task 19 production implementation or GHCR publication.
2. Code quality review checks Docker/registry cleanup on every exit, free-port allocation without race-prone probing, timeout/output enforcement, manifest canonicalization, deterministic fixture behavior, and zero credential/external-network/install fallback.
3. Critical/Important findings, missing real Docker evidence, or NO-GO blocks Task 3.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the digest-mismatch RED test.** Create the exact test above plus a closed fake inspection object; also add the writable-candidate-mount rejection case as a second pure test. Mark real-Docker cases `docker_integration`, keep pure inspection cases marker-free, and require callers to receive `outcome` from evaluation rather than set it.
- [ ] **Step 2: Run RED.** Verify Task 1 lock/config/runner SHA-256 values, then run the exact Target command above. Expected: nonzero because manifest and boundary evaluators do not exist; any bootstrap drift fails before pytest.
- [ ] **Step 3: Implement the smallest child-owned evidence composition and final report assembler.**

  ```python
  build_input = freeze_reference_build_input(fixture_root)
  build = build_reference_image(build_input)
  registry = probe_loopback_registry(build)
  isolation = probe_reference_container(build, fixture_root)
  pytest_evidence = validate_gate_pytest_report(pytest_report)
  first_input = normalize_call_fail_input(first_pytest_report, target_node_id)
  second_input = normalize_call_fail_input(second_pytest_report, target_node_id)
  fingerprint = compare_failure_inputs(first_input, second_input)
  report = assemble_reference_gate_report(assemble_command)
  ```

  `assemble_command` is the exact `AssembleReferenceGateReportV1` value containing those Task 2.A–2.F child results and Task 1 gate toolchain evidence. Task 2.G validates and assembles it but does not repeat any upstream operation. Implement the gate-only reporter and fingerprint input comparator in their two owned modules; neither may import a future production `src/vespercode/validation` module.
- [ ] **Step 4: Run GREEN.** Re-run the exact Target command through Task 1's environment/runner. Expected: exit `0` with the sole failed code `OCI_REGISTRY_DIGEST_MISMATCH`.
- [ ] **Step 5: Refactor without behavior change.** Keep OCI export/digesting, loopback registry lifecycle, manifest generation, Docker inspection, report validation, reporter events, and failure-input comparison as separate responsibilities in the four planned spike files; the registry lifecycle owns cleanup through one `try/finally` boundary.
- [ ] **Step 6: Run the real reference boundary gate.** Build from `containers/reference/Dockerfile`, export the frozen single-platform OCI manifest, start the digest-pinned registry on `127.0.0.1:0`, push/pull by digest, generate the final manifest only after equality, and run the exact Real build/probe command above. Require explicit `-p spikes.docker_reference_boundary.pytest_reporter` with autoload disabled. Expected: GO with three equal digests, zero credential/external push, verified registry cleanup, no final-manifest image member, and the existing no-network/non-root/read-only/tmpfs/report/fingerprint contracts.
- [ ] **Step 7: Run the current offline suite.** Run `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- -q`. Expected: exit `0`; Docker is invoked only by the explicit Step 6 probe and Task 1's gate identities remain unchanged.
- [ ] **Step 8: Run static, whitespace, and secret checks.** Run `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py ruff-format -- spikes/docker_reference_boundary tests/feasibility/docker reference`, `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py ruff-check -- spikes/docker_reference_boundary tests/feasibility/docker reference`, `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py mypy -- spikes/docker_reference_boundary tests/feasibility/docker`, and `git diff --check`. Run the Task 1 filename-only PowerShell scan over `spikes\docker_reference_boundary`, `tests\feasibility\docker`, `reference`, `containers\reference`, and `requirements`. Expected: the runner verifies Task 1 identities, all commands exit `0`, and no path is printed.
- [ ] **Step 9: Request spec compliance review.** Give a fresh read-only reviewer Task 2, SPEC §1.4.1/§1.4.5/§4.5/§8.2/§8.4/§11.2, manifest bytes, image inspection, and complete report.
- [ ] **Step 10: Close spec findings.** The responsible subagent makes minimal fixes, rebuilds the image, reruns Steps 6–8, and obtains a passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require a fresh read-only reviewer to inspect image reproducibility inputs, loopback binding/port allocation, registry data cleanup on every exit, no credential-store use, manifest build-context exclusion, report completeness, and false-GO prevention.
- [ ] **Step 12: Close quality findings.** The responsible or explicitly assigned repair subagent closes all Critical/Important findings, reruns Steps 6–8, and obtains a passing quality re-review.
- [ ] **Step 13: Commit, record, and open one PR only after GO.** Task 2.G commits the gate evidence only after `GO`; its `NO_GO` records the evidence, stops without marking Milestone 2 complete, and opens no implementation PR for later Tasks.

### Milestone 3: One-to-Three-File Persistence and Recovery Feasibility Gate

**Status:** Not started

**Goal:** Prove through exhaustive deterministic fault injection that mixed `CREATE`/`REPLACE` persistence across 1–3 files can only resolve as `COMMITTED`, `ROLLED_BACK`, or `UNRESOLVED`, with correct deadline and external-change behavior.

**SPEC / FR / NFR / AC references:** SPEC §1.4.4; §4.2.6 deadline rules; §4.6; §5.2; §5.5; §5.6; §10.1 AC-07, AC-21, AC-22, AC-29, AC-31; §10.3 recovery fault injection; §11.2 item 3.

**Dependencies:** Task 2 GO.

**Blocks:** Task 3.G is the terminal gate. Its `NO_GO` blocks every later executable Task and release work and requires a formal SPEC revision; silently reducing the scope to one file is forbidden.

**Parallelization:** Sequential.

**Recommended branch:** `codex/task-03-persistence-recovery-gate`

**Recommended worktree:** `.worktrees/task-03-persistence-recovery-gate`

**Files:**
- Create: `spikes/persistence_recovery/protocol.py`
- Create: `spikes/persistence_recovery/faults.py`
- Create: `spikes/persistence_recovery/report.py`
- Test: `tests/feasibility/persistence/test_recovery_gate.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Tasks 1 and 2 GO evidence; the unchanged Task 1 gate lock/config/runner/tool identity matrix; a disposable Windows NTFS workspace; a SQLite transaction log outside the target repository; the SPEC-global `allowed_operations` contract restricted to one to three sorted CREATE/REPLACE operations with at most one CREATE. Task 3 may not resolve dependencies or read Task 4.A configuration.
- Produces:
  - `GateWriteEntrySequenceV1` and `FaultCaseResultSequenceV1`, immutable ordered tuples of zero or more values of their named item types
  - `prepare_transaction(workspace: Path, entries: GateWriteEntrySequenceV1, deadline_ms: int, clock: ClockPort, faults: FaultPort) -> GateTransactionV1`
  - `apply_transaction(transaction_id: str, fault_point: PersistenceFaultPointV1, clock: ClockPort) -> GatePersistenceResultV1`
  - `preview_recovery(workspace: Path, transaction_id: str) -> GateRecoveryPreviewV1`
  - `apply_recovery(command: GateRecoveryCommandV1) -> GateRecoveryResultV1`
  - `GateRecoveryDispositionV1 = Literal["COMMITTED","ROLLED_BACK","UNRESOLVED"]`
  - `PersistenceRecoveryGateReportV1(outcome: Literal["GO","NO_GO"], cases: FaultCaseResultSequenceV1, evidence_digest: str)`

**Implementation points:**
- Validate 1–3 unique canonical paths, at most one CREATE, typed `PRESENT`/`ABSENT` preimages, and matching operation/preimage combinations before PREPARED.
- Store transaction and per-path records durably outside the workspace. Store safe backups for REPLACE and no backup for CREATE.
- Use same-directory temporary files, flush file contents, synchronize directory metadata where supported, and atomically replace one sorted path at a time.
- Record durable progress after observing actual postimage bytes and a supported final object. Durable state may lag actual bytes; recovery always observes bytes, metadata, and identity again.
- Inject interruption before/after PREPARED, before/after WRITING, before/after every replace, before/after every durable state write, and before/after terminal state persistence.
- Expiry before the first workspace write yields zero write and ROLLED_BACK/STOPPED evidence. Expiry after any path may have changed performs no more workspace writes or implicit rollback and yields UNRESOLVED/RECOVERY_REQUIRED evidence.
- Inject external byte changes and object-identity changes at every path boundary. Unknown current content or identity can never be deleted, overwritten, or called safe.
- Preview is byte-for-byte read-only for workspace, log, and backups. Apply requires explicit invocation and reacquires the workspace mutex.
- CREATE returns to ABSENT only when the current file exactly matches this transaction's postimage and remains a supported object.
- The complete Cartesian case matrix must pass for one, two, and three files with mixed operations. GO is derived only when every required case has its expected disposition and write-count invariant.
- The GO report repeats and verifies the Task 1 Python/pytest/Ruff/Mypy and lock/config/runner SHA-256 matrix before running any case; mismatch is NO-GO even if every persistence assertion would otherwise pass.

**Implementation boundary:** This executable Task owns one feasibility decision: whether the fixed 1–3-file prototype can classify every declared interruption as COMMITTED, ROLLED_BACK, or UNRESOLVED. It implements no production persistence service, Web/CLI recovery, or wider file operation.

**Intentionally failing test:**

```python
def test_deadline_after_first_replace_stops_writes_and_requires_recovery(
    three_file_transaction: GateTransactionHarness,
) -> None:
    three_file_transaction.expire_after("replace:0")
    result = three_file_transaction.apply()
    assert result.disposition == "UNRESOLVED"
    assert result.run_state == "RECOVERY_REQUIRED"
    assert result.workspace_write_count == 1
    assert three_file_transaction.path_bytes(1) == three_file_transaction.preimage_bytes(1)
    assert three_file_transaction.path_bytes(2) == three_file_transaction.preimage_bytes(2)
```

**Verification:**
- Target: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_recovery_gate.py::test_deadline_after_first_replace_stops_writes_and_requires_recovery -q`
- Domain: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_recovery_gate.py -q`
- Standalone report: `.venv-gate\Scripts\python.exe spikes/persistence_recovery/report.py --workspace tests/.tmp/persistence-gate --output tests/.tmp/persistence-gate-report.json`
- Expected: Task 1 identities match and all commands exit `0`; report outcome is GO and records the gate identity matrix; every case is one of the three dispositions; preview has zero writes; post-first-write expiry performs no subsequent workspace write; all UNRESOLVED cases keep the workspace blocked.

**Review gate:**
1. Spec compliance review first verifies the unchanged Task 1 gate bootstrap, then checks every §4.6 fault point, typed preimage rule, deadline branch, preview/apply rule, object-identity branch, and three-value disposition.
2. Code quality review checks fsync/replace ordering, fault determinism, test isolation, cleanup, durable-state lag handling, and absence of a single-file fallback.
3. Critical/Important findings or NO-GO blocks Task 4 and all release work.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the post-first-replace deadline RED test.** Add the exact test above with a three-entry `REPLACE, CREATE, REPLACE` harness and deterministic fake clock/fault port; mark cases that use real Win32 objects `windows_integration`.
- [ ] **Step 2: Run RED.** Verify the Task 1 gate identity matrix, then run the exact Target command above. Expected: nonzero because the transaction protocol and fault port do not exist; bootstrap drift fails before pytest.
- [ ] **Step 3: Implement the minimum transaction state machine.**

  ```python
  def apply_transaction(
      transaction_id: str,
      fault_point: PersistenceFaultPointV1,
      clock: ClockPort,
  ) -> GatePersistenceResultV1:
      tx = load_and_verify_transaction(transaction_id)
      for record in tx.path_records:
          if tx.any_path_may_have_changed and clock.expired():
              return persist_unresolved(tx, reason="DEADLINE_AFTER_WRITE")
          if clock.expired():
              return persist_zero_write_rollback(tx, reason="DEADLINE_BEFORE_WRITE")
          replace_one_verified_path(tx, record, fault_point)
      return verify_all_postimages_and_commit(tx)
  ```

  `replace_one_verified_path` must expose named fault checkpoints on both sides of the file replace and progress-state persistence.
- [ ] **Step 4: Run GREEN.** Re-run the exact Target command through Task 1's environment/runner. Expected: exit `0`; exactly one workspace write occurs and the remaining paths retain preimages.
- [ ] **Step 5: Refactor without behavior change.** Separate typed records, fault checkpoints, actual-byte classification, and report aggregation into the three planned files; preserve checkpoint names as a closed enum.
- [ ] **Step 6: Run the complete fault matrix.** Run the exact Complete matrix command through `.venv-gate` and the gate runner. Expected: all 1/2/3-file, CREATE/REPLACE, state-lag, external-change, preview/apply, deadline, and interruption cases pass and the report preserves Task 1 identities.
- [ ] **Step 7: Run the current offline suite.** Run `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- -q`. Expected: exit `0` with `gates/pytest.ini` as the sole project config.
- [ ] **Step 8: Run static, whitespace, and secret checks.** Run `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py ruff-format -- spikes/persistence_recovery tests/feasibility/persistence`, `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py ruff-check -- spikes/persistence_recovery tests/feasibility/persistence`, `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py mypy -- spikes/persistence_recovery tests/feasibility/persistence`, and `git diff --check`. Run the Task 1 filename-only PowerShell scan over the Task 3 paths. Expected: the runner verifies all Task 1 identities, all commands exit `0`, and no path is printed.
- [ ] **Step 9: Request spec compliance review.** Give a fresh read-only reviewer Task 3, SPEC §4.2.6/§4.6/§10.3/§11.2, the closed fault list, the entire matrix output, and the GO report.
- [ ] **Step 10: Close spec findings.** The responsible subagent makes minimal corrections, reruns Steps 6–8, and obtains a passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require a fresh read-only reviewer to inspect ordering, durable-state lag, fake/real filesystem separation, and false-safe recovery paths.
- [ ] **Step 12: Close quality findings.** The responsible or explicitly assigned repair subagent closes all Critical/Important findings, reruns Steps 6–8, and obtains a passing quality re-review.
- [ ] **Step 13: Commit, record, and open one PR only after GO.** Task 3.G commits the gate evidence only after `GO`; its `NO_GO` records the evidence, stops without marking Milestone 3 complete, and triggers formal SPEC revision rather than a reduced persistence scope.

### Milestone 4: Project Foundation and CanonicalizationV1

**Execution notice:** Non-executable aggregate contract. Only Tasks 4.A, 4.F, 4.B, 4.C, 4.D, and 4.E are executable; they separately own complete dependency closure, formal toolchain promotion, canonical bytes/digests, canonical time, lexical paths, and credential scanning. This Milestone is complete only when all six exact children are complete.

**Status:** Not started

**Goal:** Establish the installable Python 3.12 project and implement the one canonical byte/digest/timestamp contract on which every subsequent identity depends.

**SPEC / FR / NFR / AC references:** SPEC §0; §0.1 and CTV-01–CTV-07; §5.2; §9; §10.1 AC-10 and AC-26; course requirements §3.6, §4.8, §5; `AGENTS.md` build/test, TDD, and credential-scan rules.

**Dependencies:** Tasks 1, 2, and 3 with Task 3 `GO`, including the unchanged Task 1 gate bootstrap identity carried through Tasks 2 and 3.

**Blocks:** Tasks 5–38.

**Parallelization:** Sequential.

**Recommended branch:** `codex/task-04-canonical-foundation`

**Recommended worktree:** `.worktrees/task-04-canonical-foundation`

**Files:**
- Create: `pyproject.toml`
- Create: `requirements/dev.lock`
- Create: `src/vespercode/__init__.py`
- Create: `src/vespercode/project/dependency_closure.py`
- Create: `config/dependency-closure-v1.json`
- Create: `scripts/bootstrap_formal_env.py`
- Create: `src/vespercode/project/toolchain_promotion.py`
- Create: `config/formal-toolchain-promotion-v1.json`
- Create: `src/vespercode/canonical/json_v1.py`
- Create: `src/vespercode/canonical/timestamp_v1.py`
- Create: `src/vespercode/canonical/clock.py`
- Create: `src/vespercode/canonical/digest.py`
- Create: `src/vespercode/canonical/path_v1.py`
- Create: `scripts/scan_credentials.py`
- Test: `tests/unit/canonical/test_json_v1.py`
- Test: `tests/unit/canonical/test_timestamp_v1.py`
- Test: `tests/unit/canonical/test_clock.py`
- Test: `tests/unit/canonical/test_digest_vectors.py`
- Test: `tests/unit/canonical/test_path_v1.py`
- Test: `tests/unit/process/test_dependency_closure.py`
- Test: `tests/unit/process/test_toolchain_promotion.py`
- Test: `tests/unit/process/test_scan_credentials.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Tasks 1–3 GO evidence; the frozen `requirements/gate.lock`, `gates/` configs, `scripts/run_gate_checks.py`, exact Task 1 `python_version`, tool versions, and all GO-report identity matrices as read-only promotion inputs; public Python compatibility range `>=3.12,<3.13`; exact CTV-01–CTV-07 bytes and digests from SPEC §0.1.
- Produces:
  - `DependencyClosureV1(python_range: Literal[">=3.12,<3.13"], python_version: str, runtime_direct_names: tuple[str, ...], build_direct_names: tuple[str, ...], development_direct_names: tuple[str, ...], locked_distributions: tuple[LockedDistributionV1, ...], source_policy_digest: str, closure_digest: str)` persisted uniquely by Task 4.A at `config/dependency-closure-v1.json`
  - `FormalToolchainPromotionV1(python_version: str, gate_lock_sha256: str, pytest_version: str, ruff_version: str, mypy_version: str, marker_digest: str, static_rule_digest: str)` persisted uniquely by Task 4.F at `config/formal-toolchain-promotion-v1.json`
  - `bootstrap_formal_environment(root: Path, gate_evidence: GateToolchainEvidenceV1) -> FormalEnvironmentBootstrapResultV1`
  - `CanonicalValueV1 = str | int | bool | tuple[CanonicalValueV1, ...] | Mapping[str, CanonicalValueV1]`
  - `canonical_json_bytes(value: CanonicalValueV1) -> bytes`
  - `domain_digest(object_type: str, schema_version: int, value: Mapping[str, CanonicalValueV1]) -> str`
  - `CanonicalTimestampV1.parse(value: str) -> CanonicalTimestampV1`
  - `CanonicalTimestampV1.from_epoch_milliseconds(value: int) -> CanonicalTimestampV1`
  - `ClockV1.now() -> CanonicalTimestampV1`
  - `SystemClockV1` for production and `FakeClockV1` for deterministic tests
  - `validate_canonical_relative_path(value: str) -> CanonicalRelativePathV1`
  - `scan_changed_files(paths: Sequence[Path]) -> CredentialScanReportV1`
  - canonical offline command `python -m pytest -q`

**Implementation points:**
- Encode mappings by raw Unicode scalar code-point key order; never normalize strings.
- Reject isolated surrogates, float, NaN, infinity, null, non-string keys, undeclared Python object types, and integers outside the signed 64-bit range used by v1 schemas.
- Emit direct UTF-8 for all non-required escapes; use the exact lowercase control escapes; do not escape `/`, U+2028, or U+2029.
- Construct the digest prefix exactly as `UTF8("VesperCode") || 0x00 || UTF8(object_type) || 0x00 || ASCII(schema_version) || 0x00`.
- Parse only `YYYY-MM-DDTHH:MM:SS.sssZ`; validate Gregorian dates and reject leap seconds and alternate UTC spellings before digesting.
- `SystemClockV1` reads UTC epoch milliseconds and immediately converts through `CanonicalTimestampV1.from_epoch_milliseconds`; all decision, deadline, expiry, and evidence code receives a `ClockV1` port, while tests advance `FakeClockV1` explicitly.
- Lexical canonical paths reject empty/root sentinels, absolute/drive/UNC/device forms, ADS, empty/dot/parent segments, trailing slash/dot/space, and reserved device names. Win32 final-object validation remains Task 9.
- Task 4.A declares every direct dependency family in the Tech Stack, classifies it as runtime, build/distribution, or development/verification, records the public Python range, exact Task 1 `python_version`, Python marker, and reviewed source/index policy, and freezes every direct and transitive distribution with exact hashes in `requirements/dev.lock`. Its one closure RED fails on any missing/extra/misclassified direct dependency, missing transitive distribution/hash, inconsistent Python marker/source policy, mismatch between `pyproject.toml` and the lock, or character-for-character mismatch between the persisted closure `python_version` and Task 1.E terminal `GO` evidence.
- Task 4.A's bootstrap locates the candidate interpreter with `py -3.12`, reads Task 1.E terminal `GO` identity before any `.venv-formal` creation/use, and fails unless `platform.python_version() == gate_evidence.python_version`. It installs every and only locked distribution with `--require-hashes --no-deps`; it never resolves, upgrades, re-locks, reads another worktree's `.venv-gate`, or treats an ambient bare `python` as an input.
- Task 4.F promotes the Task 1-verified exact Python/pytest/Ruff/Mypy patch versions, marker definitions, and static rules into tooling/build sections of `pyproject.toml`; it does not select or resolve any package. It generates a promotion comparison mapping every Task 1 gate version/marker/Ruff/Mypy rule to its formal destination and persists the exact Python identity in its unique record. Any deliberate difference requires a SPEC/PLAN-compatible explanation plus fresh Task 1–3 execution and GO evidence before Task 4 can pass; any silent version/config drift fails closed.
- `config/dependency-closure-v1.json` and `config/formal-toolchain-promotion-v1.json` are the sole persistent, machine-readable, non-secret records for their respective v1 schemas; no log, environment directory, test output, or prose completion note substitutes for either JSON record.
- Preserve `requirements/gate.lock`, `gates/`, `scripts/run_gate_checks.py`, the Task 2 reporter/probe, and all three GO reports as immutable reproducibility evidence; formal commands never rewrite or delete them.
- `pyproject.toml` keeps the public runtime range from SPEC. Task 4.A owns only its dependency tables, Python range, reviewed source/index policy, and minimal package identity; Task 4.F owns only its build backend and pytest/Ruff/Mypy/tooling sections; Task 33.A may later change only package data, version, distribution metadata, and the console entry point. No later modifier may change dependency tables, the Python range, dependency sources, or `requirements/dev.lock`.
- Task 4.A freezes exact reviewed Hatchling and `build` distributions and hashes in the closure; Task 4.F configures Hatchling as the PEP 517 backend. Task 33.A cannot choose or change the backend.
- Register the exact pytest markers `windows_integration`, `docker_integration`, `reference_e2e`, `package_smoke`, `oci_smoke`, and `deployment_smoke`. Default `python -m pytest -q` excludes these six real-environment groups; every dedicated environment command clears default addopts and selects its marker explicitly.
- The credential scanner accepts an explicit changed-file list, reports only paths and rule ids, redacts matched values, ignores binary bytes, and exits nonzero on a match.

**Intentionally failing test:**

```python
def test_ctv_01_exact_bytes_and_digest() -> None:
    value = {
        "tags": (),
        "schema_version": 1,
        "optional_note": {"kind": "ABSENT"},
        "label": "x",
    }
    assert canonical_json_bytes(value) == (
        b'{"label":"x","optional_note":{"kind":"ABSENT"},'
        b'"schema_version":1,"tags":[]}'
    )
    assert domain_digest("CanonicalizationProbeV1", 1, value) == (
        "1923bd578b2110ae145622050b4b6d10171c4b8fca4a383be06fa9f78d1ca782"
    )
```

**Verification:**
- Target RED/GREEN: `.venv-formal\Scripts\python.exe -m pytest -q tests/unit/canonical/test_digest_vectors.py::test_ctv_01_exact_bytes_and_digest`
- Domain: `.venv-formal\Scripts\python.exe -m pytest -q tests/unit/canonical tests/unit/process/test_scan_credentials.py`
- Full: `.venv-formal\Scripts\python.exe -m pytest -q`
- Expected: all CTV vectors, timestamp/path rejection cases, and scanner redaction tests pass offline.

**Review gate:**
1. Spec compliance review compares every encoded byte and rejection in CTV-01–CTV-07, verifies the complete dependency closure, compares both persisted records' `python_version` character-for-character with Task 1.E terminal `GO` evidence, verifies the gate-to-formal promotion map and absence of silent version/config drift, and verifies the project commands match SPEC §9.
2. Code quality review checks recursion bounds, scalar validation, deterministic error types, type checking, package boundaries, and scanner non-disclosure.
3. Critical/Important findings block Task 5.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Verify the dependency closure and gate promotion inputs, then write the CTV-01 RED test.** Require the completed Task 4.A closure record and lock/config consistency result; recompute all Task 1 gate file SHA-256 values, compare them with the Task 2/3 GO records, compare `DependencyClosureV1.python_version` and `FormalToolchainPromotionV1.python_version` character-for-character with Task 1.E terminal `GO` `GateToolchainEvidenceV1.python_version`, and require the completed Task 4.F gate-to-formal version/marker/Ruff/Mypy mapping. Add the exact test above and keep the expected bytes split only at Python literal boundaries; any identity mismatch stops before RED.
- [ ] **Step 2: Run RED.** Run `.venv-formal\Scripts\python.exe -m pytest -q tests/unit/canonical/test_digest_vectors.py::test_ctv_01_exact_bytes_and_digest`. Expected: nonzero because the canonical functions do not exist.
- [ ] **Step 3: Implement the minimal canonical encoder and digest.**

  ```python
  def domain_digest(
      object_type: str,
      schema_version: int,
      value: Mapping[str, CanonicalValueV1],
  ) -> str:
      payload = canonical_json_bytes(value)
      prefix = b"VesperCode\x00" + object_type.encode("utf-8")
      prefix += b"\x00" + str(schema_version).encode("ascii") + b"\x00"
      return hashlib.sha256(prefix + payload).hexdigest()
  ```

  `canonical_json_bytes` must use a dedicated recursive encoder; calling a standard JSON serializer and patching its output is not sufficient.
- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0` and exact byte/digest equality.
- [ ] **Step 5: Refactor without behavior change.** Separate string/scalar encoding, timestamp parsing, domain digesting, and lexical path validation into the planned files; keep one public function for each responsibility.
- [ ] **Step 6: Run domain, closure, and promotion tests.** Run `.venv-formal\Scripts\python.exe -m pytest -q tests/unit/canonical tests/unit/process/test_dependency_closure.py tests/unit/process/test_toolchain_promotion.py tests/unit/process/test_scan_credentials.py` and mechanically compare both records' exact `python_version`, the dependency closure, and formal versions/markers/Ruff/Mypy rules with their frozen inputs. Expected: CTV-01–CTV-07, invalid timestamps, path sentinels, redacted scanner behavior, dependency closure, exact Python identity, and every promotion mapping pass; a difference without the required semantic revision/reapproval or fresh Task 1–3 GO evidence fails.
- [ ] **Step 7: Run the unified offline suite.** Run `.venv-formal\Scripts\python.exe -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run formatter, Ruff, Mypy, credential scan, and whitespace checks.** Run `.venv-formal\Scripts\python.exe -m ruff format --check .`, `.venv-formal\Scripts\python.exe -m ruff check .`, `.venv-formal\Scripts\python.exe -m mypy src tests`, `.venv-formal\Scripts\python.exe scripts/scan_credentials.py --changed --redact --fail-on-match`, and `git diff --check`. Expected: all exit `0` and no matched value is printed.
- [ ] **Step 9: Request spec compliance review.** Give a fresh read-only reviewer Task 4, SPEC §0.1/§9/AC-26, exact CTV fixtures, dependency lock, and diff.
- [ ] **Step 10: Close spec findings.** The Task 4 subagent fixes every Critical/Important finding, reruns Steps 6–8, and obtains a passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require a fresh read-only reviewer to inspect Unicode correctness, recursion/size bounds, deterministic errors, scanner redaction, and package configuration.
- [ ] **Step 12: Close quality findings.** The responsible or named repair subagent closes Critical/Important findings, reruns Steps 6–8, and obtains a passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit implementation with subject `Add canonical project foundation`; capture its SHA; update this task and `AGENT_LOG.md` with the gate-to-formal comparison and any explicitly revalidated difference; commit evidence with subject `Record Task 4 completion evidence`; push and open the single Task 4 PR. The commit must retain every gate bootstrap and Task 2 reporter/probe evidence file unchanged.

### Milestone 5: Closed Schemas and Shared Value Objects

**Status:** Not started

**Goal:** Define frozen, unknown-field-rejecting public value objects and discriminated unions shared by every domain without creating a catch-all model module.

**SPEC / FR / NFR / AC references:** SPEC §0.1 closed-schema rules; §4.2.1–§4.2.2 shared status/action contracts; §4.4.3–§4.4.4 location/source unions; §7 data model; §10.1 AC-17, AC-26, AC-27, AC-28.

**Dependencies:** Task 4.E.

**Blocks:** Tasks 6–29 and 31–38.

**Parallelization:** Sequential.

**Recommended branch:** `codex/task-05-closed-contracts`

**Recommended worktree:** `.worktrees/task-05-closed-contracts`

**Files:**
- Create: `src/vespercode/contracts/optional.py`
- Create: `src/vespercode/contracts/location.py`
- Create: `src/vespercode/contracts/run.py`
- Create: `src/vespercode/contracts/action.py`
- Create: `src/vespercode/contracts/evidence.py`
- Test: `tests/unit/contracts/test_optional.py`
- Test: `tests/unit/contracts/test_location.py`
- Test: `tests/unit/contracts/test_run.py`
- Test: `tests/unit/contracts/test_action.py`
- Test: `tests/unit/contracts/test_evidence.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: `domain_digest` from Task 4.B, `CanonicalTimestampV1` from Task 4.C, and `validate_canonical_relative_path` from Task 4.D.
- Produces:
  - frozen Pydantic base policy `extra="forbid"` with explicit `schema_version`
  - `AbsentV1`, `PresentV1[T]`, and every named optional union required by SPEC
  - `RepositoryLocationV1 = RootLocationV1 | PathLocationV1`
  - `DisclosurePathScopeV1 = RootScopeV1 | FileScopeV1 | DirectoryScopeV1`
  - `RunStatus`, `RunPhase`, `RunStateV1`, `WaitKind`, `RunLimitsV1`, `WaitContextV1`
  - `WaitDecisionChoiceV1 = Literal["APPROVE", "REJECT"]`
  - `WaitDecisionV1(wait_id: str, run_id: str, wait_kind: WaitKind, subject_digest: DigestV1, decision: WaitDecisionChoiceV1, event_id: str, decided_at: CanonicalTimestampV1)`
  - `CheckPlanIdV1 = TARGET_TESTS | FULL_PYTEST | RUFF | MYPY`
  - `ActionStatusV1`, `PolicyDecisionV1`, `ActionErrorV1`, `ActionResultV1`, `ActionInstanceV1`
  - `ArtifactRefV1`, `DigestV1`, and bounded stable error-code value objects

**Implementation points:**
- Every schema field is explicit; omission, `None`, extra fields, wrong discriminator, or cross-variant fields fail before digest creation.
- Optional semantics use `ABSENT`/`PRESENT`; empty string and empty tuple remain distinct valid values only where a consuming schema allows them.
- Repository root exists only as `{"kind":"ROOT"}`. Path variants call Task 4 lexical canonicalization and reject trailing slashes.
- `RunStatus` has exactly `CREATED`, `RUNNING`, `WAITING_USER`, `RECOVERY_REQUIRED`, `SUCCEEDED`, `STOPPED`; `RunPhase` has exactly the five current SPEC phases.
- A user wait decision is a closed value object that binds `wait_id`, `run_id`, `wait_kind`, and `subject_digest` plus one `APPROVE|REJECT` choice, a caller-generated idempotency event id, and a server-clock timestamp. It carries no target state, Grant, approval, persistence command, or policy override.
- `RunLimitsV1` validates all nine explicit fields and their hard ranges without defaults.
- Action identity separates Harness `action_id`, semantic digest, and instance digest; model-facing action payloads do not inherit `action_id`.
- Bounded messages enforce byte limits on UTF-8 bytes rather than Python character count.

**Implementation boundary:** This executable Task freezes one closed cross-layer value-object vocabulary and its validation/round-trip behavior. It adds no repository, service orchestration, policy decision, external adapter, or UI behavior.

**Intentionally failing test:**

```python
def test_repository_root_requires_the_closed_root_variant() -> None:
    assert RepositoryLocationV1.validate_python({"kind": "ROOT"}) == RootLocationV1(
        kind="ROOT"
    )
    with pytest.raises(ValidationError):
        RepositoryLocationV1.validate_python({"kind": "PATH", "path": "."})
    with pytest.raises(ValidationError):
        RepositoryLocationV1.validate_python({"kind": "ROOT", "path": "src"})
```

**Verification:**
- Target: `python -m pytest -q tests/unit/contracts/test_location.py::test_repository_root_requires_the_closed_root_variant`
- Domain: `python -m pytest -q tests/unit/contracts`
- Full: `python -m pytest -q`
- Expected: exact variants pass and omitted/unknown/cross-variant/null inputs fail deterministically.

**Review gate:**
1. Spec compliance review maps each public enum/union to its single SPEC definition and verifies no old handoff types enter current code.
2. Code quality review checks module responsibility, type aliases, immutable configuration, byte bounds, and absence of inheritance that permits extra fields.
3. Critical/Important findings block Tasks 6 and 7.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the root-union RED test.** Add the exact test and explicit imports; do not create a string root sentinel fixture.
- [ ] **Step 2: Run RED.** Run the target command above. Expected: nonzero because the location union does not exist.
- [ ] **Step 3: Implement the minimum closed location types.**

  ```python
  class RootLocationV1(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=True)
      kind: Literal["ROOT"]

  class PathLocationV1(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=True)
      kind: Literal["PATH"]
      path: CanonicalRelativePathV1

  RepositoryLocationV1 = TypeAdapter(
      Annotated[RootLocationV1 | PathLocationV1, Field(discriminator="kind")]
  )
  ```

- [ ] **Step 4: Run GREEN.** Re-run the target command. Expected: exit `0`.
- [ ] **Step 5: Refactor without behavior change.** Place optional, location, run, action, and evidence contracts only in their planned responsibility files; remove any duplicate enum declaration.
- [ ] **Step 6: Run domain tests.** Run `python -m pytest -q tests/unit/contracts`. Expected: all union, unknown-field, immutability, range, and byte-bound tests pass.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run the five standard formatter/lint/type/credential/whitespace commands from Global Constraints. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Supply Task 5, SPEC §0.1/§4.2/§4.4/§7, and a generated list of exported symbols.
- [ ] **Step 10: Close spec findings.** Make minimal corrections, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of Pydantic discriminators, generic optional typing, byte counts, public exports, and circular imports.
- [ ] **Step 12: Close quality findings.** Close Critical/Important issues, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add closed shared contracts`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 5 PR.

### Milestone 6: Built-in Profile Registry and Frozen Configuration

**Status:** Not started

**Goal:** Implement the sole editable/reference profile, the closed Mock/OpenAI LLM profiles, the trusted endpoint map, and immutable config resolution.

**SPEC / FR / NFR / AC references:** SPEC §1.4.1; §4.1 input and behavior 1–4; §4.4.3 endpoint/profile fields; §5.2; §7 profile/config rows; §8.2; §9; §10.1 AC-13, AC-15, AC-26, AC-30, AC-31.

**Dependencies:** Task 5.

**Blocks:** Tasks 8, 12–21, 24–29, and 31–38.

**Parallelization:** Parallel with early Tasks 7.A–7.C after Task 5; these tasks own disjoint files. Late Task 7.D is not part of this wave.

**Recommended branch:** `codex/task-06-profile-registry`

**Recommended worktree:** `.worktrees/task-06-profile-registry`

**Files:**
- Create: `src/vespercode/profiles/editable.py`
- Create: `src/vespercode/profiles/reference.py`
- Create: `src/vespercode/profiles/llm.py`
- Create: `src/vespercode/profiles/endpoints.py`
- Create: `src/vespercode/profiles/registry.py`
- Create: `src/vespercode/profiles/builtin/reference-profile-v1.json`
- Create: `src/vespercode/profiles/builtin/mock-deterministic-v1.json`
- Create: `src/vespercode/profiles/builtin/openai-single-turn-v1.json`
- Test: `tests/unit/profiles/test_editable.py`
- Test: `tests/unit/profiles/test_reference.py`
- Test: `tests/unit/profiles/test_llm.py`
- Test: `tests/unit/profiles/test_endpoints.py`
- Test: `tests/unit/profiles/test_registry.py`
- Modify: `reference/manifest/reference-profile-v1.json` (synchronize Task 2 artifact after digest validation)
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 4.B digest functions; Task 4.D path functions; Task 5 frozen contracts; Task 2 image/lock/tool evidence.
- Produces:
  - `EditablePathPolicyV1.matches(path: CanonicalRelativePathV1, operation: EditableOperationV1) -> bool`
  - `ReferenceProfileManifestV1.verify_integrity(gate_manifest: GateReferenceProfileManifestV1) -> None`
  - `MockLLMProfileV1`, `OpenAILLMProfileV1`, and `LLMProfileManifestV1`
  - `OpenAIEndpointRegistry.resolve(endpoint_id: str) -> OpenAIEndpointV1`
  - `ProfileRegistry.resolve_reference(profile_id: str) -> ReferenceProfileManifestV1`
  - `ProfileRegistry.resolve_llm(profile_id: str) -> LLMProfileManifestV1`

**Implementation points:**
- The editable policy bytes are built in, read-only, digest-verified, and exactly match `src` plus `CREATE/REPLACE`; matching is by path segment, not string prefix.
- Load manifests with `importlib.resources`; reject missing, duplicate, extra, invalid-digest, or cross-profile data at process composition before a Run can be created.
- The reference manifest must exactly match Task 2 requirements/image/execution/tool/check-plan evidence.
- The Mock profile binds adapter version, script id, and script digest and contains no OpenAI fields.
- The OpenAI profile binds provider, endpoint id, exact model, adapter version, serializer version, explicit fixed parameters, and `NO_CONTENT_REDACTION_V1`; it contains no script fields.
- Before the built-in OpenAI manifest is finalized, verify a provider-supported exact model using official OpenAI documentation and record the choice/date/source in `AGENT_LOG.md`. Inability to verify a model blocks this task; it does not authorize a guessed model or custom endpoint.
- The endpoint registry has one immutable entry and ignores `OPENAI_BASE_URL` and equivalent environment values.
- User/request/config payloads containing endpoint overrides or editable-policy overrides are rejected by Task 8; this task exposes no mutator.

**Implementation boundary:** This executable Task owns one immutable built-in profile lookup/validation behavior over the three shipped JSON records. It adds no user-editable configuration, request admission, credential access, network call, or runtime compatibility decision.

**Intentionally failing test:**

```python
@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/a.py", True),
        ("src/pkg/a.py", True),
        ("src", False),
        ("src-old/a.py", False),
        ("src2/a.py", False),
        ("README.md", False),
    ],
)
def test_editable_policy_uses_directory_segments(path: str, expected: bool) -> None:
    assert BUILTIN_EDITABLE_POLICY.matches(path, "REPLACE") is expected
```

**Verification:**
- Target: `python -m pytest -q tests/unit/profiles/test_editable.py::test_editable_policy_uses_directory_segments`
- Domain: `python -m pytest -q tests/unit/profiles`
- Full: `python -m pytest -q`
- Expected: only the two strict descendants pass; built-in manifests and copied reference manifest have verified digests; endpoint resolution always returns `https://api.openai.com:443/v1`.

**Review gate:**
1. Spec compliance review performs a field-for-field manifest comparison and verifies no second policy, profile source, endpoint, model override, or runtime image choice exists.
2. Code quality review checks resource loading, immutable cache behavior, digest error handling, segment matching, and deterministic registry startup.
3. Critical/Important findings block Task 8.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the segment-boundary RED test.** Add the parameterized test exactly as shown.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because `BUILTIN_EDITABLE_POLICY` does not exist.
- [ ] **Step 3: Implement the minimal immutable policy.**

  ```python
  def matches(
      self,
      path: CanonicalRelativePathV1,
      operation: EditableOperationV1,
  ) -> bool:
      segments = path.split("/")
      return operation in self.allowed_operations and segments[:1] == ["src"] and len(segments) > 1
  ```

  Construction must verify the built-in digest and exact field values.
- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0`.
- [ ] **Step 5: Refactor without behavior change.** Keep endpoint, editable policy, reference manifest, LLM manifest, and registry responsibilities isolated; use one read-only composition cache.
- [ ] **Step 6: Run domain tests.** Run `python -m pytest -q tests/unit/profiles`. Expected: manifest integrity, mode-field exclusion, endpoint immutability, environment override resistance, and registry uniqueness pass.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Provide Task 6, SPEC §1.4.1/§4.1/§4.4/§8.2/AC-30/AC-31, all three built-in manifest bytes, Task 2 report, and official model-source record.
- [ ] **Step 10: Close spec findings.** Correct only contract mismatches, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of manifest parsing, resource packaging, digest verification, cache immutability, and environment isolation.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add immutable profile registry`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 6 PR.

### Milestone 7: SQLite Repository, Idempotency, and Run Lifecycle

**Execution notice:** Non-executable aggregate contract. Only Tasks 7.A–7.D are executable. Tasks 7.A–7.C own the early migration framework, Run/wait repository, and idempotency ledger; late Task 7.D owns only final v1 migration-registry composition after every domain migration producer completes. Aggregate Task 7 is never a graph predecessor.

**Status:** Not started

**Goal:** Establish a domain-independent transactional migration engine, early Run/wait/idempotency storage, and one late checksum-verified composition whose test-only prefix audit proves every domain-owned v1 migration introduces exactly its declared tables and the final database has exactly the 18 classified SQLite tables, without storing secrets or application bodies.

**SPEC / FR / NFR / AC references:** SPEC §4.2.1; §4.2.7; §4.7 audit ordering; §5.2; §5.4; §5.6; §7 complete data model and storage split; §10.1 AC-16, AC-21, AC-27, AC-28.

**Dependencies:** Tasks 7.A–7.C depend on exact Task 5 children as listed in the canonical DAG. Task 7.D depends on every exact v1 migration producer: Tasks 7.B, 7.C, 14.B, 15.D, 15.E, 22.A, 23.A, 24.C, 25.B, 25.D, 26.A, and 26.C.

**Blocks:** Early Tasks 7.A–7.C block their exact repository consumers. Task 38.F is the only runtime/full-database consumer of late Task 7.D and passes that composition transitively to E2E/package consumers; Task 37.B separately depends on 7.D only to verify final process/evidence completeness.

**Parallelization:** Tasks 7.A–7.C may proceed with the early storage wave after Task 5. Task 7.D is composition-only and runs after all twelve migration producers; merge/evidence updates remain serialized.

**Recommended branch:** `codex/task-07-sqlite-lifecycle`

**Recommended worktree:** `.worktrees/task-07-sqlite-lifecycle`

**Files:**
- Create: `src/vespercode/storage/connection.py`
- Create: `src/vespercode/storage/migration_engine.py`
- Create: `src/vespercode/storage/migrations/__init__.py`
- Create: `src/vespercode/storage/migrations/v0001_run_wait.py`
- Create: `src/vespercode/storage/migrations/v0002_idempotency.py`
- Create: `src/vespercode/storage/migrations/registry.py`
- Create: `src/vespercode/storage/run_repository.py`
- Create: `src/vespercode/storage/idempotency.py`
- Create: `src/vespercode/runs/lifecycle.py`
- Test: `tests/unit/storage/test_connection.py`
- Test: `tests/unit/storage/test_migration_engine.py`
- Test: `tests/unit/storage/test_run_wait_migration.py`
- Test: `tests/unit/storage/test_idempotency_migration.py`
- Test: `tests/unit/storage/test_migration_registry.py`
- Test: `tests/unit/storage/test_run_repository.py`
- Test: `tests/unit/storage/test_idempotency.py`
- Test: `tests/unit/runs/test_lifecycle.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 5 run/wait/evidence contracts; Task 4 canonical digests/timestamps.
- Produces:
  - `open_control_database(path: Path) -> ControlDatabase`
  - `ControlDatabase.immediate_transaction() -> AbstractContextManager[ControlTransactionV1]`
  - `MigrationV1(version: int, name: str, checksum: DigestV1, apply: MigrationApplyV1)`
  - `apply_migrations(db: ControlDatabase, migrations: tuple[MigrationV1, ...]) -> MigrationResultV1`
  - `RUN_WAIT_V1_MIGRATION`, `IDEMPOTENCY_V1_MIGRATION`, and late `ALL_V1_MIGRATIONS`
  - `RunRepository.insert_created(run: RunRecordV1) -> None`
  - `RunRepository.compare_and_transition(command: TransitionCommandV1) -> TransitionResultV1`
  - `RunRepository.create_wait(context: WaitContextV1) -> None`
  - `WaitDecisionLockResultV1 = LockedWaitDecisionV1(kind="LOCKED", wait: WaitContextV1, transaction_id: str) | WaitDecisionUnavailableV1(kind: Literal["STALE", "ALREADY_DECIDED", "CANCELLED"], error_code: str)`
  - `RunRepository.lock_wait_for_decision(tx: ControlTransactionV1, decision: WaitDecisionV1) -> WaitDecisionLockResultV1`
  - `RunRepository.commit_wait_decision(tx: ControlTransactionV1, lock: LockedWaitDecisionV1, decision: WaitDecisionV1) -> WaitDecisionResultV1`
  - `RunRepository.expire_wait(tx: ControlTransactionV1, lock: LockedWaitDecisionV1, now: CanonicalTimestampV1) -> WaitDecisionResultV1`
  - `IdempotencyRepository.record_or_replay(tx: ControlTransactionV1, scope: str, event_id: str, request_digest: str, result_digest: str) -> IdempotencyResultV1`
  - `LifecycleRules.evaluate(current: RunStateV1, event: LifecycleEventV1) -> RunStateV1`

**Implementation points:**
- Enable foreign keys and explicit transactions. Standalone public repository methods own one transaction boundary; the three wait-decision primitives require one caller-owned `ControlTransactionV1`, reject a transaction from another database, and exist only so Tasks 14 and 15 can atomically store the domain decision before the Run transition.
- Task 7.A owns only connection/transaction policy, the closed migration descriptor, `schema_migrations` checksum history, and an ordered idempotent atomic runner. It may bootstrap only migration-history metadata and may neither contain domain DDL nor import the incomplete/final registry.
- Task 7.B owns v0001 Run/config/wait DDL with exact keys, uniqueness, foreign keys, and prohibited-column assertions; Task 7.C owns v0002 idempotency DDL under the same rule.
- Every later SQLite-owning domain task owns exactly one immutable migration module and focused schema contract test. It applies the actual predecessor constants plus its own constant through Task 7.A and never edits the final registry.
- Task 7.D contains no DDL or repository behavior. It imports exactly the twelve declared producer constants, requires versions 1–12 with the expected names/order/checksums, rejects missing/duplicate/gapped/reordered/unexpected/drifted migrations, and exports `ALL_V1_MIGRATIONS`. Only `test_migration_registry.py` owns the exact expected table-delta map: it applies prefixes v0001 through v0012 to empty temporary SQLite, subtracts the Task 7.A `schema_migrations` bootstrap from the v0001 domain delta, and checks both every version delta and the final exact 18-table set.
- Run creation, phase/status transition, wait creation/decision, approval/grant budget hooks, and monotonic sequence allocation use compare-and-update predicates.
- Legal lifecycle follows SPEC §4.2.7 exactly; terminal states cannot reopen; non-persistence restart stops; persistence/recovery remains Task 26's specialized path.
- `lock_wait_for_decision` validates and locks the active wait plus all four binding fields without changing the Run. The appropriate Task 14/15 coordinator records the Approval or Grant outcome in the same transaction before `commit_wait_decision`; rollback at any point leaves both the domain record and Run state unchanged.
- `commit_wait_decision` derives its target solely from the locked wait kind and decision: approved disclosure returns to a new `AGENT_LOOP` entry, approved final writeback enters `RUNNING(PERSISTENCE)`, and rejection stops with the stable reason. `expire_wait` is the only timeout path. Callers cannot supply a target state.
- A stale, wrong-kind, cancelled, or duplicate decision cannot obtain `LockedWaitDecisionV1` and therefore cannot create a domain record or transition the Run. An otherwise exact but expired wait may be locked only so the owning Task 14/15 coordinator can record its permitted expiry evidence and call `expire_wait`; `commit_wait_decision` rejects it.
- Same idempotency key plus same request digest returns the first result; same key plus different digest returns `EVENT_ID_REUSE_CONFLICT`.
- Coordinators calculate the closed decision/result digest before mutation, call `record_or_replay` inside their existing `ControlTransactionV1`, and mutate only on `NEW`. `REPLAY` reconstructs the stored typed result from its domain record and `CONFLICT` performs no mutation.
- SQLite contains no credential value, complete file body, complete LLM request/response, raw check output, or recovery backup bytes.
- Transaction errors propagate as typed control-store failures; no exception is swallowed or converted to success.

**Intentionally failing test:**

```python
def test_same_wait_decision_can_win_only_once(
    control_database: ControlDatabase,
    run_repository: RunRepository,
    disclosure_wait: WaitContextV1,
    fixed_clock: FakeClockV1,
) -> None:
    run_repository.create_wait(disclosure_wait)
    decision = WaitDecisionV1(
        wait_id=disclosure_wait.wait_id,
        run_id=disclosure_wait.run_id,
        wait_kind=WaitKind.DISCLOSURE_GRANT,
        subject_digest=disclosure_wait.subject_digest,
        decision="APPROVE",
        event_id="evt-wait-1",
        decided_at=fixed_clock.now(),
    )
    with control_database.immediate_transaction() as tx:
        lock_result = run_repository.lock_wait_for_decision(tx, decision)
        assert isinstance(lock_result, LockedWaitDecisionV1)
        first = run_repository.commit_wait_decision(
            tx, lock_result, decision
        )
    with control_database.immediate_transaction() as tx:
        second = run_repository.lock_wait_for_decision(tx, decision)
    assert first.kind == "APPLIED"
    assert second.kind == "ALREADY_DECIDED"
    assert run_repository.get(disclosure_wait.run_id).status == RunStatus.RUNNING
```

**Verification:**
- Target: `python -m pytest -q tests/unit/storage/test_run_repository.py::test_same_wait_decision_can_win_only_once`
- Domain: `python -m pytest -q tests/unit/storage tests/unit/runs`
- Full: `python -m pytest -q`
- Expected: the engine's order/idempotency/atomicity/checksum tests, exact v0001/v0002 schema contracts, final registry descriptor closure, every v0001–v0012 prefix table delta, the exact final 18-table set, and concurrent decision/idempotency/lifecycle cases pass on temporary SQLite databases.

**Review gate:**
1. Spec compliance review checks the entire transition matrix, wait binding, restart boundary, idempotency result, prohibited stored content, each version's exact table-owner delta, and the final 18-table set.
2. Code quality review checks transaction ownership, rollback behavior, migration checksums, prefix-by-prefix `sqlite_schema` introspection, test-only owner-map isolation, concurrency tests, repository API size, and typed failures.
3. Critical/Important findings block Task 8.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the one-winner wait RED test.** Add the exact test and create the wait/run fixtures through repository public APIs.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because the repository and lifecycle rules do not exist.
- [ ] **Step 3: Implement the minimum compare-and-transition path.**

  ```python
  def commit_wait_decision(
      self,
      tx: ControlTransactionV1,
      lock: LockedWaitDecisionV1,
      decision: WaitDecisionV1,
  ) -> WaitDecisionResultV1:
      verify_same_transaction(tx, lock)
      verify_wait_binding(lock.wait, decision)
      target = self._rules.target_for_wait_decision(lock.wait, decision.decision)
      tx.mark_wait_decided(lock.wait.wait_id, decision)
      tx.transition_run(
          lock.wait.run_id,
          expected=RunStatus.WAITING_USER,
          target=target,
      )
      return WaitDecisionResultV1(kind="APPLIED")
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0`.
- [ ] **Step 5: Refactor without behavior change.** Keep SQL connection, migration engine, immutable domain migration modules, final registry, run repository, idempotency, and pure lifecycle rules separate; remove duplicate transition logic from repository methods.
- [ ] **Step 6: Run domain tests.** Run `python -m pytest -q tests/unit/storage tests/unit/runs`. Expected: all transition, migration, rollback, replay, conflict, and concurrent winner tests pass.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Give a fresh reviewer Tasks 7.A–7.D, SPEC §4.2.7/§5.2/§7, the complete storage-class/owner map, schema dumps, producer/registry closure, and tests.
- [ ] **Step 10: Close spec findings.** Apply minimal fixes, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of SQLite isolation, deadlock/rollback paths, migration drift, public API boundaries, and data minimization.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Each executable child records only its own real commit/review/PR evidence; aggregate completion is derived after Task 7.D and creates no aggregate implementation commit or PR.

### Milestone 8: Strict Run Request and Ordered Admission Coordinator

**Execution notice:** Non-executable aggregate contract. Only Tasks 8.A–8.B own files, RED/GREEN cycles, branches, commits, evidence, and PRs.

**Status:** Not started

**Goal:** Validate explicit run requests, freeze immutable config, create `CREATED`, and orchestrate PREFLIGHT in the exact zero-downstream-call failure order.

**SPEC / FR / NFR / AC references:** SPEC §4.1 FR-ADM in full; §4.2.7 lifecycle entry; §5.1; §5.3; §10.1 AC-15, AC-16, AC-21, AC-26, AC-28, AC-30, AC-31.

**Dependencies:** Tasks 6 and 7.

**Blocks:** Tasks 9, 20, 25, 28–29, and 31–38.

**Parallelization:** Sequential after Tasks 6 and 7.

**Recommended branch:** `codex/task-08-run-admission`

**Recommended worktree:** `.worktrees/task-08-run-admission`

**Files:**
- Create: `src/vespercode/runs/request.py`
- Create: `src/vespercode/runs/admission.py`
- Test: `tests/unit/runs/test_request.py`
- Test: `tests/unit/runs/test_admission.py`
- Test: `tests/unit/runs/test_admission_order.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: `RunLimitsV1` and run contracts from Task 5; `ProfileRegistry` from Task 6; `RunRepository` and lifecycle rules from Tasks 7.B–7.C.
- Produces:
  - `ValidateRunRequestV1`
  - `validate_request(request: Mapping[str, object], profiles: ProfileRegistry) -> ValidatedRunRequestV1 | ConfigInvalidV1`
  - `freeze_run_config(request: ValidatedRunRequestV1) -> RunConfigSnapshotV1`
  - `create_run(request: ValidatedRunRequestV1, repository: RunRepository) -> RunCreatedV1`
  - `RunRequestService.validate_and_create(raw_request: Mapping[str, object]) -> RunCreatedV1 | ConfigInvalidV1`
  - `AdmissionPortsV1(workspace, recovery, snapshot, static_profile, execution_readiness, credential_readiness, baseline)`
  - `AdmissionCoordinator.start_run(run_id: str) -> AdmissionResultV1`

**Implementation points:**
- Reject unknown/missing fields, duplicate or more than 20 target ids, empty or over-1024-byte ids, out-of-range limits, unknown profiles, custom endpoint/base URL, and editable-policy override before run id creation.
- Canonically sort the target set for binding while retaining enough validation information to reject duplicate input.
- Freeze all nine explicit limits, LLM profile digest, and sole reference profile digest in a secret-free `RunConfigSnapshotV1`.
- Insert CREATED before start. On start, atomically enter `RUNNING(PREFLIGHT)`, freeze `started_at` and `run_deadline`, and invoke ports in this order: workspace identity/lease → recovery gate → Snapshot prechecks → create/seal one Snapshot → static detection → reference execution readiness → applicable OpenAI credential/endpoint readiness → BASELINE.
- Each failure prevents every subsequent port. Snapshot precheck failure creates no Snapshot; Snapshot creation failure calls no static/readiness/baseline port; static failure calls no readiness/baseline port.
- Static detection receives the exact sealed Snapshot and cannot request a second Snapshot or mutable workspace handle.
- No Agent file action, LLM call, project execution, dependency install, image build, or workspace write occurs in rejected PREFLIGHT.
- Dynamic runtime compatibility belongs to BASELINE and cannot be reported as static unsupported.

**Intentionally failing test:**

```python
def test_custom_base_url_is_rejected_without_creating_a_run(
    request_service: RunRequestService,
    run_repository: SpyRunRepository,
) -> None:
    request = valid_request_dict()
    request["base_url"] = "https://example.invalid/v1"
    result = request_service.validate_and_create(request)
    assert result.kind == "CONFIG_INVALID"
    assert run_repository.insert_count == 0
```

**Verification:**
- Target: `python -m pytest -q tests/unit/runs/test_request.py::test_custom_base_url_is_rejected_without_creating_a_run`
- Domain: `python -m pytest -q tests/unit/runs/test_request.py tests/unit/runs/test_admission.py tests/unit/runs/test_admission_order.py`
- Full: `python -m pytest -q`
- Expected: request permutations bind identically; invalid inputs create zero runs; every failure-point test shows zero downstream calls.

**Review gate:**
1. Spec compliance review traces all thirteen FR-ADM behaviors and every deterministic test bullet to code/tests.
2. Code quality review checks dependency-injected ports, ordered control flow, error typing, clock boundaries, and no mixed static/dynamic concerns.
3. Critical/Important findings block Task 9.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the custom-base-URL RED test.** Add the exact test and a spy repository whose only mutating method increments `insert_count`.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because strict request validation does not exist.
- [ ] **Step 3: Implement the minimum strict validation path.**

  ```python
  class RunRequestService:
      def __init__(self, profiles: ProfileRegistry, repository: RunRepository) -> None:
          self._profiles = profiles
          self._repository = repository

      def validate_and_create(
          self,
          raw_request: Mapping[str, object],
      ) -> RunCreatedV1 | ConfigInvalidV1:
          validated = validate_request(raw_request, self._profiles)
          if isinstance(validated, ConfigInvalidV1):
              return validated
          return create_run(validated, self._repository)
  ```

  Pydantic validation must complete before `insert_created`.
- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0`, `CONFIG_INVALID`, zero insert.
- [ ] **Step 5: Refactor without behavior change.** Isolate request parsing/config freezing from ordered admission; keep ports explicit and avoid importing concrete Win32/Docker adapters.
- [ ] **Step 6: Run domain tests.** Run the domain command above. Expected: all config, order, deadline, and zero-downstream-call cases pass.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Give a fresh reviewer Task 8, complete SPEC §4.1, port call traces, and request fixtures.
- [ ] **Step 10: Close spec findings.** Apply minimal fixes, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of strict schemas, port boundaries, error propagation, clock injection, and mutation ordering.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add strict run admission`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 8 PR.

### Milestone 9: Production Win32 Workspace Identity and Git Preflight

**Execution notice:** Non-executable aggregate contract. Only Tasks 9.A–9.D are executable; they separately own Win32 identity/object inspection, the workspace mutex, sealed Git preflight, and handle-bound path authorization.

**Status:** Not started

**Goal:** Convert the Task 1 GO findings into the production workspace adapter, path guard, named mutex, Git sealed preflight, and ACL-observable artifact boundary used by admission and persistence.

**SPEC / FR / NFR / AC references:** SPEC §0.1 path identity; §1.4.1 Git rules; §1.4.2–§1.4.4; §4.1 behavior 6–10; §4.3 behavior 4–5; §4.6 ACL/lease requirements; §5.5; §10.1 AC-01, AC-15, AC-21, AC-26, AC-29, AC-31.

**Dependencies:** Tasks 1, 5, 7, and 8.

**Blocks:** Tasks 10, 12, 26, 28–29, 31–37, and 38.

**Parallelization:** Sequential after Task 8.

**Recommended branch:** `codex/task-09-win32-workspace`

**Recommended worktree:** `.worktrees/task-09-win32-workspace`

**Files:**
- Create: `src/vespercode/workspace/identity_win32.py`
- Create: `src/vespercode/workspace/object_win32.py`
- Create: `src/vespercode/workspace/mutex_win32.py`
- Create: `src/vespercode/workspace/git_preflight.py`
- Create: `src/vespercode/workspace/path_guard.py`
- Test: `tests/unit/workspace/test_path_guard.py`
- Test: `tests/unit/workspace/test_git_preflight.py`
- Test: `tests/integration/windows/test_workspace_identity.py`
- Test: `tests/integration/windows/test_workspace_objects.py`
- Test: `tests/integration/windows/test_named_mutex.py`
- Test: `tests/integration/windows/test_git_preflight.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 1 probe semantics/evidence; Task 4 canonical path/digest; Task 5 evidence contracts; Tasks 7.B–7.C Run/idempotency storage hooks; Task 8.B `AdmissionPortsV1`, specifically its workspace port.
- Produces:
  - `resolve_workspace_identity(locator: Path) -> WorkspaceIdentityV1`
  - `inspect_workspace_object(root: WorkspaceIdentityV1, path: CanonicalRelativePathV1) -> FinalObjectIdentityV1`
  - `WorkspaceMutex.acquire(identity: WorkspaceIdentityV1, timeout_ms: int) -> WorkspaceLeaseV1`
  - `WorkspaceMutex.release(lease: WorkspaceLeaseV1) -> None`
  - `run_git_snapshot_prechecks(identity: WorkspaceIdentityV1, reference: ReferenceProfileManifestV1) -> GitPreflightResultV1`
  - `PathGuard.authorize_existing(root: WorkspaceIdentityV1, path: CanonicalRelativePathV1, expected_kind: WorkspaceObjectKindV1) -> AuthorizedObjectHandleV1`
  - `PathGuard.authorize_create(root: WorkspaceIdentityV1, path: CanonicalRelativePathV1) -> AuthorizedParentHandleV1`

**Implementation points:**
- Use production pywin32/Win32 wrappers behind narrow functions and preserve Task 1's handle-derived volume/file identity checks.
- Derive mutex names from the domain-separated workspace identity digest; retain the OS handle until formal terminal/recovery handoff.
- Reject all unsupported lexical forms before opening, then verify final object identity, authorized-root ancestry, reparse tag, link count, kind, and collision map from handles.
- Freeze repository config, attributes, ignore policy, HEAD, and index. Disable system/global config, external excludes, filters, autocrlf conversion, and external attribute sources.
- Reject unmerged/non-stage-0/intent-to-add/skip-worktree/assume-unchanged entries, index tree unequal to HEAD, tracked bytes unequal to HEAD blobs, forbidden conversions, unsupported untracked files, submodule/LFS/sparse/filter states, sensitive tracked paths, and case/Unicode aliases.
- Accepted ignored untracked files never enter Snapshot, container, disclosure, or diff.
- Return a sealed preflight object with HEAD digest, tracked raw-byte observations, mode/object identities, ignore/attribute/config digests, repository-policy digest, and the sole editable-policy digest.
- If an ACL or identity fact cannot be proven, return a stable rejection; never fall back to string-only authorization.
- Mark every file under `tests/integration/windows/` with `windows_integration`; keep pure fake/fixture tests under `tests/unit/workspace/` marker-free.

**Intentionally failing test:**

```python
def test_tracked_file_with_skip_worktree_is_rejected_before_snapshot(
    sealed_git_repo: GitRepositoryFixture,
) -> None:
    sealed_git_repo.set_index_flag("src/a.py", skip_worktree=True)
    result = run_git_snapshot_prechecks(
        sealed_git_repo.identity,
        sealed_git_repo.reference_manifest,
    )
    assert result.kind == "REJECTED"
    assert result.error_code == "UNSUPPORTED_REPOSITORY"
    assert sealed_git_repo.snapshot_create_count == 0
```

**Verification:**
- Unit target: `python -m pytest -q tests/unit/workspace/test_git_preflight.py::test_tracked_file_with_skip_worktree_is_rejected_before_snapshot`
- Domain unit: `python -m pytest -q tests/unit/workspace`
- Windows integration: `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_workspace_identity.py tests/integration/windows/test_workspace_objects.py tests/integration/windows/test_named_mutex.py tests/integration/windows/test_git_preflight.py`
- Full offline: `python -m pytest -q`
- Expected: unit/offline tests pass everywhere; integration tests pass on the project Windows runner and never skip a required boundary case.

**Review gate:**
1. Spec compliance review compares production behavior with Task 1 GO evidence and every Git/filesystem rejection in SPEC.
2. Code quality review checks handle ownership, command construction without shell, Git environment isolation, error mapping, deterministic cleanup, and no TOCTOU claim beyond SPEC.
3. Critical/Important findings block Task 10.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the skip-worktree RED test.** Add the exact test using a real temporary Git repository fixture and a spy Snapshot factory.
- [ ] **Step 2: Run RED.** Run the unit target command. Expected: nonzero because production Git preflight does not exist.
- [ ] **Step 3: Implement the smallest sealed-index check.**

  ```python
  def run_git_snapshot_prechecks(
      identity: WorkspaceIdentityV1,
      reference: ReferenceProfileManifestV1,
  ) -> GitPreflightResultV1:
      sealed = inspect_git_with_isolated_config(identity)
      reject_special_index_flags(sealed.index_entries)
      verify_head_index_and_worktree_bytes(sealed)
      return build_preflight_result(sealed, reference.editable_path_policy)
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0`, with `UNSUPPORTED_REPOSITORY` and zero Snapshot creation.
- [ ] **Step 5: Refactor without behavior change.** Separate final-object inspection, mutex ownership, Git inspection, and policy/path decisions; do not duplicate Task 4 lexical parsing.
- [ ] **Step 6: Run unit and real Windows tests.** Run both domain-unit and Windows-integration commands. Expected: all required cases pass without skip.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0` with Windows-marked integration tests excluded by the committed pytest configuration on non-Windows environments and required on the Windows job.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Give a fresh reviewer Task 9, Task 1 GO report, SPEC §1.4.1–§1.4.4/§4.1/§4.3, and real integration logs.
- [ ] **Step 10: Close spec findings.** Apply minimal fixes, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of handle lifetime, Git subprocess arguments/environment, mutex races, ACL checks, and deletion safety.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add Win32 workspace preflight`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 9 PR.

### Milestone 10: SnapshotTree, Content Objects, and Supported Text Classification

**Status:** Not started

**Goal:** Construct the Run's sole immutable SnapshotTree from sealed preflight bytes and provide one shared raw-byte text classifier for all file tools and candidate operations.

**SPEC / FR / NFR / AC references:** SPEC §1.4.1 `StaticProjectProfileCheckV1`; §1.4.4; §4.1 behavior 8–10; §4.2.2 `SupportedTextFileV1`; §4.3 behavior 1–3; §7 Snapshot/List entry rows; §10.1 AC-04, AC-15, AC-17, AC-18, AC-26, AC-31.

**Dependencies:** Tasks 5 and 9.D.

**Blocks:** Tasks 11–12, 20, 22, 31–37, and 38.

**Parallelization:** Sequential after Task 9.

**Recommended branch:** `codex/task-10-snapshot-content`

**Recommended worktree:** `.worktrees/task-10-snapshot-content`

**Files:**
- Create: `src/vespercode/trees/content_store.py`
- Create: `src/vespercode/trees/snapshot.py`
- Create: `src/vespercode/trees/text_classifier.py`
- Test: `tests/unit/trees/test_content_store.py`
- Test: `tests/unit/trees/test_snapshot.py`
- Test: `tests/unit/trees/test_text_classifier.py`
- Test: `tests/integration/windows/test_snapshot_from_preflight.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 9.C `GitPreflightResultV1` with exact tracked bytes/object identities and frozen policy; Task 4.B digest; Task 5 closed evidence contracts.
- Produces:
  - `ContentObjectStore.put(raw_bytes: bytes) -> ContentObjectRefV1`
  - `ContentObjectStore.get(ref: ContentObjectRefV1) -> bytes`
  - `create_snapshot(preflight: AcceptedGitPreflightV1, store: ContentObjectStore, classifier: SupportedTextClassifierV1) -> SnapshotTreeV1`
  - `verify_snapshot(snapshot: SnapshotTreeV1, store: ContentObjectStore) -> SnapshotIntegrityResultV1`
  - `classify_supported_text(raw_bytes: bytes) -> TextFileClassificationV1`
  - `TextMetadataV1(encoding: Literal["UTF8","UTF8_BOM"], newline: Literal["LF","CRLF"], final_newline: Literal[True])`

**Implementation points:**
- Create exactly one Snapshot per Run from the sealed preflight object; no API accepts a mutable workspace path or creates a replacement Snapshot.
- Store every tracked ordinary file's exact bytes by raw SHA-256 content reference and bind path, size, Git mode, object identity, and content reference in deterministic canonical-path order.
- Enforce 5,000-file, 128-MiB total, 4-MiB per-file, and path length/segment limits before publishing the Snapshot.
- The Snapshot root digest binds entries plus the repository-policy digest carrying the sole editable-policy digest.
- Verify every content reference, byte size, ordering, unique path, collision map, and policy digest before publication; no partial Snapshot is visible.
- Classify UTF-8 LF and UTF-8 BOM/CRLF with required final newline as TEXT_FILE. Invalid UTF-8, U+0000, bare/mixed newline, no final newline, and empty file are NON_TEXT_FILE but remain valid ordinary Snapshot entries.
- Classification is a pure function over raw bytes and is the only classifier subsequent file tools may import.
- Content retrieval verifies digest and length; a mismatch returns `TREE_INTEGRITY_FAILED` and no bytes.
- Mark `tests/integration/windows/test_snapshot_from_preflight.py` with `windows_integration`; the classifier/content/Snapshot fake tests remain in the default offline suite.

**Implementation boundary:** This executable Task owns one immutable Snapshot construction/integrity behavior from sealed preflight bytes. It does not inspect mutable Git state, authorize workspace paths, construct candidates, expose search tools, or execute project code.

**Intentionally failing test:**

```python
@pytest.mark.parametrize(
    ("raw", "kind"),
    [
        (b"alpha\n", "TEXT_FILE"),
        (b"\xef\xbb\xbfalpha\r\n", "TEXT_FILE"),
        (b"", "NON_TEXT_FILE"),
        (b"alpha", "NON_TEXT_FILE"),
        (b"alpha\r\nbeta\n", "NON_TEXT_FILE"),
        (b"alpha\x00\n", "NON_TEXT_FILE"),
    ],
)
def test_supported_text_classifier_is_closed(raw: bytes, kind: str) -> None:
    assert classify_supported_text(raw).kind == kind
```

**Verification:**
- Target: `python -m pytest -q tests/unit/trees/test_text_classifier.py::test_supported_text_classifier_is_closed`
- Domain: `python -m pytest -q tests/unit/trees`
- Windows integration: `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_snapshot_from_preflight.py`
- Full: `python -m pytest -q`
- Expected: classification table, content corruption, limit, ordering, duplicate/collision, and one-Snapshot tests pass.

**Review gate:**
1. Spec compliance review traces every Snapshot source/binding/limit/classification rule and proves ignored untracked files never enter.
2. Code quality review checks streaming limits, immutable storage API, hash verification, memory use, sorting, and pure classifier reuse.
3. Critical/Important findings block Task 11.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the closed-classifier RED test.** Add the exact parameter table and assert metadata for both TEXT_FILE rows in separate focused assertions.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because the classifier does not exist.
- [ ] **Step 3: Implement the minimal byte classifier.**

  ```python
  def classify_supported_text(raw_bytes: bytes) -> TextFileClassificationV1:
      encoding, body = split_optional_utf8_bom(raw_bytes)
      text = decode_strict_unicode_scalars(body)
      newline = detect_uniform_newline(text)
      if not text or "\x00" in text or newline is None or not text.endswith(("\n", "\r\n")):
          return TextFileClassificationV1(kind="NON_TEXT_FILE")
      return TextFileClassificationV1(
          kind="TEXT_FILE",
          metadata=TextMetadataV1(encoding=encoding, newline=newline, final_newline=True),
      )
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0`.
- [ ] **Step 5: Refactor without behavior change.** Keep raw content storage, Snapshot assembly, and classification independent; Snapshot code may call but not redefine the classifier.
- [ ] **Step 6: Run domain and Windows tests.** Run both domain and integration commands. Expected: all pass; no required Windows case is skipped on the Windows runner.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Provide Task 10, SPEC §1.4.4/§4.1/§4.2.2/§4.3, preflight fixture, and Snapshot canonical projection.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of digest verification, limits, byte decoding, immutable interfaces, and memory behavior.
- [ ] **Step 12: Close quality findings.** Close Critical/Important issues, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add immutable snapshot content`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 10 PR.

### Milestone 11: Read-only List, Read, and Literal Search Tools

**Execution notice:** Non-executable aggregate contract. Only Tasks 11.A–11.B are executable.

**Status:** Not started

**Goal:** Implement deterministic, bounded repository inspection over the current immutable tree while preserving the sole shared text classification and closed result contracts.

**SPEC / FR / NFR / AC references:** SPEC §4.2.2 file actions/results and `SupportedTextFileV1`; §4.2.8; §4.3 input/behavior 2–5; §5.1; §7 `RepositoryLocationV1`/`ListFilesEntryV1`; §10.1 AC-01, AC-17, AC-26, AC-31; §10.3 offline core tests.

**Dependencies:** Tasks 5 and 10.

**Blocks:** Tasks 17, 24–25, 29, and 31–32.

**Parallelization:** Parallel with Task 12 after Task 10; the tasks own disjoint implementation files.

**Recommended branch:** `codex/task-11-readonly-file-tools`

**Recommended worktree:** `.worktrees/task-11-readonly-file-tools`

**Files:**
- Create: `src/vespercode/tools/file_actions.py`
- Create: `src/vespercode/tools/file_results.py`
- Create: `src/vespercode/tools/list_files.py`
- Create: `src/vespercode/tools/read_file.py`
- Create: `src/vespercode/tools/search_text.py`
- Test: `tests/unit/tools/test_file_actions.py`
- Test: `tests/unit/tools/test_list_files.py`
- Test: `tests/unit/tools/test_read_file.py`
- Test: `tests/unit/tools/test_search_text.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 5 `RepositoryLocationV1`, `ActionResultV1`, `ArtifactRefV1`, and stable error objects; Task 10 `SnapshotTreeV1`, `TextMetadataV1`, and `classify_supported_text`.
- Produces:
  - `ListFilesQueryV1`, `SearchTextQueryV1`, `ListFilesCursorV1`, `SearchTextCursorV1`, and their distinct `ABSENT|PRESENT` unions
  - `ListFilesActionV1`, `ReadFileActionV1`, and `SearchTextActionV1`, with required typed cursor fields on List/Search
  - `ListFilesEntryV1`, `ListFilesResultV1`, `ReadFileResultV1`, `SearchMatchV1`, and `SearchTextResultV1`, with typed `next_cursor`
  - `FileToolActionV1 = ListFilesActionV1 | ReadFileActionV1 | SearchTextActionV1`
  - `FileToolResultV1 = ListFilesResultV1 | ReadFileResultV1 | SearchTextResultV1`
  - `list_files(tree: SnapshotTreeV1 | CandidateTreeV1, action: ListFilesActionV1) -> ListFilesResultV1`
  - `read_file(tree: SnapshotTreeV1 | CandidateTreeV1, action: ReadFileActionV1) -> ReadFileResultV1`
  - `search_text(tree: SnapshotTreeV1 | CandidateTreeV1, action: SearchTextActionV1) -> SearchTextResultV1`
  - `ReadableTreeV1` protocol exposing immutable path/type/raw-byte lookup without a workspace path

**Implementation points:**
- Parse every action with required fields, `extra="forbid"`, exact byte/range limits, canonical locations, unique roots, and the rule that `ROOT` is the sole root when present.
- List only entries visible in the supplied immutable tree. Synthesize directories deterministically, classify every ordinary file with Task 10's function, and sort by `(directory_rank, canonical_path)`.
- Reject a list `PATH` that is not an existing directory before traversing. List is not constrained by `EditablePathPolicyV1`.
- Read performs path/object/type checks before range checks. A `NON_TEXT_FILE` pure result carries `FILE_NOT_TEXT` and no body; Task 17.C alone converts it to `ActionResultV1(status=FAILED, payload_ref=ABSENT, error=PRESENT(FILE_NOT_TEXT))`.
- Preserve original line order, BOM/newline metadata, exact raw-byte digest, requested byte cap, actual line range, and EOF. A start beyond a supported text file's final source line returns `READ_RANGE_OUT_OF_BOUNDS`.
- Search is literal only. Traverse roots and entries in canonical order, preserve `(path,line,column)` ordering, bind excerpts to their file paths, and count each actually visited non-text ordinary file once.
- Search directed at one non-text file succeeds with zero matches and `skipped_non_text_count=1`; a directory never increments that counter.
- Validate the complete pure result against the closed schema before returning it. An invalid variant combination or untruncatable over-limit result returns the typed `INTERNAL_ERROR` failure with no partial payload; Task 17.C alone publishes successful bounded payloads to ArtifactStore.
- Build each cursor from its distinct concrete type, visible-tree digest, cursor-free query digest, next stable scan position, and self-excluding digest. Include the cursor in `ActionSemanticDigestV1` but exclude it from the query digest.
- List resumes at the exact next `(directory_rank, canonical_path)`. Search de-duplicates overlapping roots into canonical file order and resumes at `(next_canonical_path, next_match_index)`, advancing across no-match and non-text files.
- Enforce `truncated=true` iff a typed `next_cursor=PRESENT` exists; complete results use `truncated=false` and `ABSENT`. A visible-tree mismatch returns `CONTINUATION_STALE`; wrong type, digest, query, encoding, or position returns `CONTINUATION_INVALID`; both publish zero partial payload.
- Bound every Search excerpt to 1024 UTF-8 bytes on a Unicode scalar boundary so one match cannot prevent forward progress under the 32-KiB result cap.

**Intentionally failing test:**

```python
def test_list_cursor_pages_equal_unpaged_without_gaps(
    tree_with_nested_entries: ReadableTreeV1,
) -> None:
    first_action = ListFilesActionV1(
        schema_version=1,
        action_type="list_files",
        root={"kind": "ROOT"},
        recursive=True,
        max_entries=2,
        cursor={"kind": "ABSENT"},
    )
    first = list_files(
        tree_with_nested_entries,
        first_action,
    )
    second = list_files(
        tree_with_nested_entries,
        ListFilesActionV1(
            schema_version=1,
            action_type="list_files",
            root={"kind": "ROOT"},
            recursive=True,
            max_entries=500,
            cursor=first.next_cursor,
        ),
    )
    unpaged = list_files(
        tree_with_nested_entries,
        ListFilesActionV1(
            schema_version=1,
            action_type="list_files",
            root={"kind": "ROOT"},
            recursive=True,
            max_entries=500,
            cursor={"kind": "ABSENT"},
        ),
    )
    assert first.entries + second.entries == unpaged.entries
    assert len({entry.path for entry in unpaged.entries}) == len(
        unpaged.entries
    )
    assert second.next_cursor.kind == "ABSENT"
```

**Verification:**
- Target: `python -m pytest -q tests/unit/tools/test_list_files.py::test_list_cursor_pages_equal_unpaged_without_gaps`
- Domain: `python -m pytest -q tests/unit/tools`
- Full: `python -m pytest -q`
- Expected: action-schema rejection, shared classification, ordering, canonical cursor round trips, stale/invalid zero-partial failures, paged/unpaged equivalence, 1024-byte excerpts, byte/range, root alias, non-text, and invalid-result cases all pass offline.

**Review gate:**
1. Spec compliance review traces every action/query/cursor/result field, digest input, ordering rule, continuation failure, limit, non-text rule, and editable-policy independence to §4.2.2.
2. Code quality review checks bounded forward-only iteration, raw-byte accounting, cursor/query digest separation, stable ordering, pure typed results, and that no tool reads a workspace path; ArtifactStore publication remains solely in Task 17.C.
3. Critical/Important findings block Task 17.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the cursor round-trip RED test.** Add the exact test above with at least one directory and three files so the first page truncates.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because the list action, typed cursor, and continuation implementation do not exist.
- [ ] **Step 3: Implement the minimum typed List continuation path.**

  ```python
  def list_files(
      tree: SnapshotTreeV1 | CandidateTreeV1,
      action: ListFilesActionV1,
  ) -> ListFilesResultV1:
      query = ListFilesQueryV1.from_action(action)
      ordered = build_directory_first_entries(tree, query)
      start = validate_and_resolve_list_cursor(action.cursor, tree.digest, query)
      page, next_position = take_bounded_page(ordered, start, query.max_entries)
      result = ListFilesResultV1.from_page(
          page,
          next_cursor=make_list_cursor(tree.digest, query.digest, next_position),
      )
      return result
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0`; concatenated pages equal the unpaged order with no duplicate path.
- [ ] **Step 5: Refactor without behavior change.** Keep action/result schemas, traversal, read slicing, and literal matching in the five planned modules; import rather than duplicate the Task 10 classifier.
- [ ] **Step 6: Run domain tests.** Run `python -m pytest -q tests/unit/tools`. Expected: all closed-schema, ordering, location, List/Search pagination, tree/query/type/digest tamper, overlap/no-match/non-text forward progress, excerpt cap, classification, byte/range, and publication tests pass.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Provide Task 11, SPEC §4.2.2/§4.2.8/§4.3, cursor digest vectors, paged/unpaged result fixtures, and stale/invalid zero-partial traces.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of iterator bounds, byte slicing, stable order, pure classification reuse, and artifact-store side effects.
- [ ] **Step 12: Close quality findings.** Close every Critical/Important issue, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add deterministic read-only tools`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 11 PR.

### Milestone 12: CandidateTree, Strict Patch Engine, and FinalDiffV1

**Execution notice:** Non-executable aggregate contract. Only Tasks 12.A–12.D are executable; they separately own strict diff parsing, immutable CandidateTree overlays, atomic patch application, and FinalDiff/candidate identity.

**Status:** Not started

**Goal:** Derive immutable candidates from exact unified patches and recompute the sole policy-bound structured diff and semantic candidate identity atomically.

**SPEC / FR / NFR / AC references:** SPEC §1.4.2–§1.4.4; §4.2.2 `ApplyCandidatePatchAction`; §4.3 in full; §4.4.1 path-policy binding; §4.5 pre-check policy revalidation; §7 Candidate/FinalDiff rows; §10.1 AC-01, AC-04, AC-07, AC-18, AC-26, AC-31.

**Dependencies:** Tasks 6, 9, and 10.

**Blocks:** Tasks 13–14, 17–18, 20–21, 25–26, 31–32, and 38.

**Parallelization:** Parallel with Task 11 after Task 10; these tasks own disjoint files.

**Recommended branch:** `codex/task-12-candidate-patch-engine`

**Recommended worktree:** `.worktrees/task-12-candidate-patch-engine`

**Files:**
- Create: `src/vespercode/trees/candidate.py`
- Create: `src/vespercode/candidate/unified_diff.py`
- Create: `src/vespercode/candidate/patch_engine.py`
- Create: `src/vespercode/candidate/final_diff.py`
- Create: `src/vespercode/candidate/identity.py`
- Test: `tests/unit/trees/test_candidate.py`
- Test: `tests/unit/candidate/test_unified_diff.py`
- Test: `tests/unit/candidate/test_patch_engine.py`
- Test: `tests/unit/candidate/test_final_diff.py`
- Test: `tests/unit/candidate/test_identity.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 6 `EditablePathPolicyV1` and `ReferenceProfileManifestV1`; Task 9 `AuthorizedObjectHandleV1`, `AuthorizedParentHandleV1`, and frozen ignore decisions; Task 10 `SnapshotTreeV1`, `ContentObjectStore`, `TextMetadataV1`, and `classify_supported_text`.
- Produces:
  - `ApplyCandidatePatchAction`
  - `CandidateTreeV1`, `CandidateRevisionV1`, and `CandidateIdentityV1`
  - `FinalDiffPreimageV1`, `FinalDiffEntryV1`, and `FinalDiffV1`
  - `parse_unified_diff_v1(patch_text: str) -> ParsedPatchV1 | PatchParseFailureV1`
  - `apply_candidate_patch(action: ApplyCandidatePatchAction, current: CandidateRevisionV1, context: CandidatePatchContextV1) -> CandidatePatchOutcomeV1`
  - `recompute_final_diff(snapshot: SnapshotTreeV1, candidate: CandidateTreeV1, policy: EditablePathPolicyV1) -> FinalDiffV1`
  - `build_candidate_identity(snapshot_tree_digest: str, candidate_tree_digest: str, final_diff_digest: str) -> CandidateIdentityV1`

**Implementation points:**
- Parse a no-BOM UTF-8/LF patch completely before any candidate derivation; accept only the exact headers and hunk grammar in `UNIFIED_DIFF_V1`.
- Reject delete, rename, mode, binary, timestamp, no-newline marker, case-only path change, malformed ranges, duplicate entry paths, and trailing unparsed bytes.
- Check failures in the frozen order: patch/Schema → canonical/workspace/alias → final-object/sensitive → protected artifact → editable policy → candidate limits.
- Match every old hunk line and context byte against the candidate identified by `base_candidate_digest`; never use fuzzy matching, automatic offsets, or partial application.
- Preserve existing BOM, uniform newline, and final newline. New files use UTF-8 without BOM, LF, and a final newline.
- Build all postimages in a private overlay, validate supported text and object/path policy for the whole patch, then publish exactly one immutable child revision or none.
- Recompute `FinalDiffV1` from Snapshot versus the complete candidate after every patch. Sort entries by canonical path and derive `CREATE/ABSENT` or `REPLACE/PRESENT` combinations.
- Count complete raw postimages, including BOM, CRLF bytes, non-ASCII UTF-8 bytes, and final newline. Enforce at most 3 files, 1 create, 128 KiB total postimages, and 128 KiB per editable file.
- Revalidate every final entry against the one policy in the reference manifest. A policy/Snapshot/tree mismatch is `TREE_INTEGRITY_FAILED`; a non-editable path is `PATCH_PATH_NOT_EDITABLE`.
- Candidate identity binds only Snapshot root, CandidateTree digest, and FinalDiff digest. Revision ids, parent ids, timestamps, and other audit metadata cannot alter it.

**Intentionally failing test:**

```python
def test_mixed_legal_and_noneditable_patch_has_no_candidate_side_effect(
    candidate_context: CandidatePatchContextV1,
    candidate_publisher: SpyCandidatePublisher,
) -> None:
    action = patch_action(
        candidate_context.current.candidate_digest,
        replace_src_a_and_readme_patch(),
    )
    outcome = apply_candidate_patch(
        action,
        candidate_context.current,
        context=candidate_context.with_publisher(candidate_publisher),
    )
    assert outcome.status == "REJECTED"
    assert outcome.error_code == "PATCH_PATH_NOT_EDITABLE"
    assert candidate_publisher.publish_count == 0
    assert candidate_context.current.candidate_digest == candidate_context.initial_digest
```

**Verification:**
- Target: `python -m pytest -q tests/unit/candidate/test_patch_engine.py::test_mixed_legal_and_noneditable_patch_has_no_candidate_side_effect`
- Domain: `python -m pytest -q tests/unit/candidate tests/unit/trees/test_candidate.py`
- Full: `python -m pytest -q`
- Expected: grammar, priority, exact hunk, atomicity, text preservation, full-postimage accounting, cumulative limits, identity restoration, and policy-tamper tests pass.

**Review gate:**
1. Spec compliance review traces every `UNIFIED_DIFF_V1`, error-priority, `FinalDiffV1`, candidate-identity, and editable-policy invariant in §4.3.
2. Code quality review checks parser totality, overlay immutability, byte accounting, deterministic sorting, digest construction, and zero-publication failures.
3. Critical/Important findings block Task 13 and every validation/persistence consumer.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the mixed-patch RED test.** Add the exact test and fixed patch bytes containing one valid `src/a.py` replacement and one structurally valid `README.md` replacement.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because the candidate patch pipeline does not exist.
- [ ] **Step 3: Implement the minimum whole-patch transaction.**

  ```python
  def apply_candidate_patch(
      action: ApplyCandidatePatchAction,
      current: CandidateRevisionV1,
      *,
      context: CandidatePatchContextV1,
  ) -> CandidatePatchOutcomeV1:
      require_current_digest(action.base_candidate_digest, current)
      parsed = parse_unified_diff_v1(action.patch_text)
      staged = stage_exact_postimages(parsed, current.tree)
      validate_all_entries(staged, context)
      final_diff = recompute_final_diff(context.snapshot, staged.tree, context.policy)
      identity = build_candidate_identity(
          context.snapshot.root_digest, staged.tree.digest, final_diff.digest
      )
      return context.publisher.publish(staged, final_diff, identity)
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0`, stable policy error, and zero publication.
- [ ] **Step 5: Refactor without behavior change.** Keep parsing, application, tree overlay, final-diff construction, and identity calculation in their planned modules.
- [ ] **Step 6: Run domain tests.** Run the domain command. Expected: all parser, application, integrity, limit, and digest tests pass.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Supply Task 12, SPEC §1.4.2–§1.4.4/§4.3/AC-18/AC-31, byte fixtures, and error-priority table.
- [ ] **Step 10: Close spec findings.** Apply minimal fixes, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of parser bounds, staged overlay isolation, collision handling, byte preservation, and digest inputs.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add strict candidate patch engine`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 12 PR.

### Task 13: Versioned PolicyEngine and Non-overridable DENY

**Status:** Not started

**Goal:** Centralize deterministic `ALLOW/ASK/DENY` evaluation so unsafe capabilities and non-editable candidate changes cannot be approved, prompted around, or dispatched.

**SPEC / FR / NFR / AC references:** SPEC §1.4.2–§1.4.3; §4.2.3; §4.3 error priority; §4.4.1; §5.2; §5.5; §10.1 AC-01, AC-02, AC-04, AC-06, AC-26, AC-31; §10.4 mechanism demo items 1–4.

**Dependencies:** Tasks 5.D, 6.E, and 12.D.

**Blocks:** Tasks 14.A, 17.C, 25.D, 30.A, 31.A, 31.B, 32.A, and 37.B.

**Parallelization:** Parallelizable with Task 18.A; Task 13 and Task 18.A each start only after their exact executable Dependencies are satisfied, and they own disjoint files.

**Recommended branch:** `codex/task-13-policy-engine`

**Recommended worktree:** `.worktrees/task-13-policy-engine`

**Files:**
- Create: `src/vespercode/governance/policy.py`
- Test: `tests/unit/governance/test_policy.py`
- Test: `tests/unit/governance/test_policy_precedence.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 5.C `PolicyDecisionV1`/`ActionInstanceV1`; Tasks 6.A and 6.B immutable editable/reference policy digests; Task 12.D action and recomputed candidate/final-diff facts.
- Produces:
  - `PolicyContextV1(run_phase: RunPhase, reference_profile_digest: str, editable_policy_digest: str, candidate_facts: CandidatePolicyFactsV1)`
  - `PolicyEvaluationV1(decision: Literal["ALLOW","ASK","DENY"], policy_digest: str, reason_code: str)`
  - `PolicyEngine.evaluate(action: ActionInstanceV1, context: PolicyContextV1) -> PolicyEvaluationV1`
  - `POLICY_VERSION = "GOVERNANCE_POLICY_V1"` and one domain-separated `policy_digest`

**Implementation points:**
- Calculate the governance policy digest from the versioned rule table plus the sole editable policy digest. Do not read prompt text, repository files, mutable config, Grant, or approval state.
- Allow only registered, schema-valid list/read/literal-search, current-candidate patch, frozen check-plan, and completion-proposal actions in `RUNNING(AGENT_LOOP)`.
- Return `ASK` only for the control-plane final writeback operation; model actions cannot manufacture that operation or any other approval subject.
- Return `DENY` for non-editable or protected paths, sensitive paths/objects, arbitrary commands, shell fields, acceptance/config/control-plane modifications, unknown capabilities, and phase-forbidden actions.
- Preserve the more specific stable path/protected/sensitive reason produced by deterministic pre-policy facts. An approval never converts a `DENY` evaluation into `ALLOW`.
- Policy evaluation has no side effects and cannot call a tool, create a wait, consume an approval, or mutate a candidate.
- Cache decisions only by policy digest, action semantic digest, and immutable context digest; never use action instance id or mutable approval status.

**Implementation boundary:** This executable Task owns one pure, versioned `ALLOW | ASK | DENY` evaluation over immutable facts. It cannot persist approvals, dispatch tools, widen policy, access secrets, or perform external side effects.

**Intentionally failing test:**

```python
def test_user_approval_cannot_override_noneditable_path_deny(
    policy_engine: PolicyEngine,
    noneditable_patch_instance: ActionInstanceV1,
    noneditable_context: PolicyContextV1,
) -> None:
    evaluation = policy_engine.evaluate(noneditable_patch_instance, noneditable_context)
    assert evaluation.decision == "DENY"
    assert evaluation.reason_code == "PATCH_PATH_NOT_EDITABLE"
    with pytest.raises(TypeError):
        cast(Any, policy_engine).evaluate(
            noneditable_patch_instance,
            noneditable_context,
            approval=object(),
        )
```

**Verification:**
- Target: `python -m pytest -q tests/unit/governance/test_policy.py::test_user_approval_cannot_override_noneditable_path_deny`
- Domain: `python -m pytest -q tests/unit/governance/test_policy.py tests/unit/governance/test_policy_precedence.py`
- Full: `python -m pytest -q`
- Expected: all action/phase decisions, hard-deny sources, reason priorities, cache keys, and policy-digest propagation pass offline.

**Review gate:**
1. Spec compliance review compares the complete rule table with §4.4.1 and proves approval, Grant, config, prompt, and repository content cannot widen it.
2. Code quality review checks rule exhaustiveness, pure evaluation, stable precedence, digest/cache keys, and unknown-action fail-closed behavior.
3. Critical/Important findings block all dispatch, approval, and mechanism-demo work.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the approval-override RED test.** Add the exact test and assert the policy API rejects an injected `approval` keyword rather than accepting an override channel.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because `PolicyEngine` does not exist.
- [ ] **Step 3: Implement the minimum closed decision table.**

  ```python
  def evaluate(
      self,
      action: ActionInstanceV1,
      context: PolicyContextV1,
  ) -> PolicyEvaluationV1:
      require_policy_binding(context, self.policy_digest)
      hard_reason = first_hard_deny_reason(action, context)
      if hard_reason is not None:
          return PolicyEvaluationV1.deny(self.policy_digest, hard_reason)
      return evaluate_registered_safe_action(action, context, self.policy_digest)
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0` with `DENY` and the exact path reason.
- [ ] **Step 5: Refactor without behavior change.** Keep immutable rule data, precedence calculation, digest creation, and evaluation separate within `policy.py`.
- [ ] **Step 6: Run domain tests.** Run the domain command. Expected: every registered action and hard-deny source has an explicit passing case.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Provide Task 13, SPEC §4.2.3/§4.4.1/AC-02/AC-31, the serialized rule table, and decision fixtures.
- [ ] **Step 10: Close spec findings.** Apply minimal fixes, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of exhaustiveness, precedence, purity, cache identity, and immutable inputs.
- [ ] **Step 12: Close quality findings.** Close every Critical/Important issue, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add non-overridable policy engine`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 13 PR.

### Milestone 14: FinalWritebackSubject and One-time Approval

**Status:** Not started

**Goal:** Construct the exact formal-writeback subject and allow one atomic, unexpired, still-current approval consumption without authorizing any other capability.

**SPEC / FR / NFR / AC references:** SPEC §4.2.7 final-writeback wait; §4.4.1–§4.4.2; §4.6 writeback preconditions; §5.2; §7 subject/approval rows; §10.1 AC-02, AC-03, AC-06, AC-07, AC-27, AC-31.

**Dependencies:** Exact child dependencies are canonical: Task 14.A consumes Tasks 7.C/12.D/13/20.B/21.C; Task 14.B additionally consumes Task 25.D as the v0009 predecessor; Task 14.C consumes the resulting v0010 approval repository. Aggregate Task 14 is not a predecessor.

**Blocks:** Tasks 25–26, 29, 31–32, and 38.

**Parallelization:** Sequential after Task 21 because it consumes the final validation contracts.

**Recommended branch:** `codex/task-14-writeback-approval`

**Recommended worktree:** `.worktrees/task-14-writeback-approval`

**Files:**
- Create: `src/vespercode/storage/migrations/v0010_writeback_approvals.py`
- Create: `src/vespercode/governance/writeback_subject.py`
- Create: `src/vespercode/governance/writeback_approval.py`
- Test: `tests/unit/storage/test_writeback_approvals_migration.py`
- Test: `tests/unit/governance/test_writeback_subject.py`
- Test: `tests/unit/governance/test_writeback_approval.py`
- Test: `tests/unit/governance/test_writeback_approval_race.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 4.C `ClockV1`; Task 7.A `ControlDatabase.immediate_transaction`; Task 7.B wait lock/commit/expiry primitives and run repositories; Task 7.C idempotency; Task 12.D `CandidateIdentityV1`/`FinalDiffV1`; Task 13 policy digest; Task 20.B `ValidationManifestV1`; Task 21 `VerifiedCandidateV1` and formal evidence digest.
- Produces:
  - `FinalWritebackBindingV1`, `FinalWritebackSubjectV1`, and pure `build_final_writeback_subject(binding: FinalWritebackBindingV1, expires_at: CanonicalTimestampV1) -> FinalWritebackSubjectV1`
  - immutable `WRITEBACK_APPROVALS_V1_MIGRATION = MigrationV1(version=10, name="writeback_approvals_v1", ...)`, `DecideFinalWritebackV1`, closed `FinalWritebackDecisionResultV1`, and `FinalWritebackDecisionServiceV1.decide(command: DecideFinalWritebackV1) -> FinalWritebackDecisionResultV1`
  - `ConsumeWritebackApprovalV1`, `ApprovalConsumptionResultV1`, `WritebackApprovalRepository.consume(command: ConsumeWritebackApprovalV1) -> ApprovalConsumptionResultV1`, and `verify_consumable(approval: FinalWritebackApprovalV1, command: ConsumeWritebackApprovalV1) -> None`

**Implementation points:**
- Recompute the current `FinalDiffV1`, enforce non-empty editable entries, and verify the reference/Snapshot/Manifest/governance policy identities before creating a subject or wait.
- Calculate `action_semantic_digest` only from schema version, `final_writeback`, candidate digest, and final-diff digest.
- Subject digest includes every immutable field in SPEC §4.4.2 except its own digest. Approval id, creation time, and mutable approval status do not alter it.
- Bind the wait id/run id/kind/subject/expiry exactly. Only `FINAL_WRITEBACK` from `FORMAL_VALIDATION` is accepted.
- `FinalWritebackDecisionServiceV1` reads `now` from its injected Task 4.C `ClockV1`, converts the specialized command to Task 5 `WaitDecisionV1`, locks the wait through Task 7.B, reloads the current subject/binding, and performs the approval-record mutation plus wait transition in the same `ControlTransactionV1`. User input cannot supply a decision timestamp.
- Its closed result discriminators and payloads are `WritebackApprovedV1(kind="APPROVED", approval_id, subject_digest)`, `WritebackRejectedV1(kind="REJECTED", approval_id, subject_digest, error_code="APPROVAL_REJECTED")`, `WritebackExpiredV1(kind="EXPIRED", approval_id, subject_digest, error_code="APPROVAL_EXPIRED")`, `WritebackStaleV1(kind="STALE", error_code="APPROVAL_STALE")`, and `WritebackAlreadyDecidedV1(kind="ALREADY_DECIDED", error_code="WAIT_STALE")`.
- The decision event id uses Task 7.C idempotency in that same transaction: exact replay returns the originally stored typed result; reuse with different decision bytes returns `EVENT_ID_REUSE_CONFLICT`; neither path creates another approval or persistence attempt.
- An exact `APPROVE` creates one `FinalWritebackApprovalV1(status="PENDING")` and moves the Run to `RUNNING(PERSISTENCE)`; it does not consume the approval and does not write the workspace. Task 26.A is the only consumer.
- `REJECT` records `status="REJECTED"` and stops the Run. A server-observed expired wait records `status="EXPIRED"` through the expiry path. Both return closed non-approved results and make zero persistence calls.
- Consumption compares approval id, wait binding, subject digest, time, current candidate/diff/Manifest/evidence/workspace/config/policy/profile fields, and `PENDING` status in one transaction.
- Consumption additionally proves the same wait has one durable `APPROVE` decision and the Run is in `RUNNING(PERSISTENCE)`; possession of an id or a pre-decision `PENDING` row can never authorize a write.
- Exactly one concurrent consumer may change `PENDING` to `CONSUMED`. Stale, expired, rejected, or already-consumed records cannot execute writeback.
- Approval objects cannot be cast or copied into a Disclosure Grant, Demo decision, local tool approval, or hard-DENY override.

**Implementation boundary:** This executable Task owns one final-writeback approval subject/state machine with one-time atomic consumption. It does not authorize disclosure, persist workspace bytes, perform recovery, render UI, or override a hard policy denial.

**Intentionally failing test:**

```python
def test_exact_writeback_approval_can_be_consumed_only_once(
    decision_service: FinalWritebackDecisionServiceV1,
    approval_repository: WritebackApprovalRepository,
    final_writeback_wait: WaitContextV1,
    current_binding: FinalWritebackBindingV1,
    fixed_clock: FakeClockV1,
) -> None:
    decision = decision_service.decide(
        DecideFinalWritebackV1(
            wait_id=final_writeback_wait.wait_id,
            run_id=final_writeback_wait.run_id,
            wait_kind="FINAL_WRITEBACK",
            subject_digest=final_writeback_wait.subject_digest,
            decision="APPROVE",
            event_id="evt-writeback-approve-1",
        )
    )
    assert decision.kind == "APPROVED"
    consume = ConsumeWritebackApprovalV1(
        approval_id=decision.approval_id,
        wait_id=final_writeback_wait.wait_id,
        run_id=final_writeback_wait.run_id,
        subject_digest=decision.subject_digest,
        current=current_binding,
        consumed_at=fixed_clock.now(),
    )
    first = approval_repository.consume(consume)
    second = approval_repository.consume(consume)
    assert first.kind == "CONSUMED"
    assert second.kind == "ALREADY_CONSUMED"
```

**Verification:**
- Target: `python -m pytest -q tests/unit/governance/test_writeback_approval.py::test_exact_writeback_approval_can_be_consumed_only_once`
- Domain: `python -m pytest -q tests/unit/governance/test_writeback_subject.py tests/unit/governance/test_writeback_approval.py tests/unit/governance/test_writeback_approval_race.py`
- Full: `python -m pytest -q`
- Expected: subject vectors, field staleness, expiry, rejection, policy mismatch, duplicate/racing consumption, and authorization-type isolation pass.

**Review gate:**
1. Spec compliance review performs a field-by-field subject and lifecycle comparison with §4.4.2, §4.2.7, and §4.6 preconditions.
2. Code quality review checks transaction predicates, clock injection, subject canonicalization, race tests, and absence of generic approval conversion APIs.
3. Critical/Important findings block persistence and WebUI approval routes.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the one-consumer RED test.** Add the exact test and obtain the pending approval only through `FinalWritebackDecisionServiceV1.decide`; direct fixture/repository insertion is forbidden.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because the writeback subject and repository do not exist.
- [ ] **Step 3: Implement the minimum atomic consumption.** The underscored helpers in this example are private/local implementation details inside the Task 14.B/14.C services, have no downstream consumer, and are not Milestone APIs.

  ```python
  def decide(
      self,
      command: DecideFinalWritebackV1,
  ) -> FinalWritebackDecisionResultV1:
      now = self._clock.now()
      wait_decision = command.to_wait_decision(decided_at=now)
      with self._db.immediate_transaction() as tx:
          lock_result = self._runs.lock_wait_for_decision(tx, wait_decision)
          if isinstance(lock_result, WaitDecisionUnavailableV1):
              return _map_writeback_wait_failure(lock_result)
          lock = lock_result
          subject, current = self._bindings._load_for_update(tx, command.run_id)
          binding = _verify_writeback_binding(subject, current, now)
          if binding.kind == "EXPIRED":
              expired = self._approvals._record_expired(tx, lock.wait, subject, now)
              self._runs.expire_wait(tx, lock, now)
              return WritebackExpiredV1(
                  kind="EXPIRED",
                  approval_id=expired.approval_id,
                  subject_digest=subject.digest,
                  error_code="APPROVAL_EXPIRED",
              )
          if binding.kind != "CURRENT":
              return WritebackStaleV1(
                  kind="STALE",
                  error_code="APPROVAL_STALE",
              )
          approval = self._approvals._record_user_decision(
              tx, lock.wait, subject, command.decision, now
          )
          self._runs.commit_wait_decision(tx, lock, wait_decision)
          if approval.status == "PENDING":
              return WritebackApprovedV1(
                  kind="APPROVED",
                  approval_id=approval.approval_id,
                  subject_digest=approval.subject_digest,
              )
          return WritebackRejectedV1(
              kind="REJECTED",
              approval_id=approval.approval_id,
              subject_digest=approval.subject_digest,
              error_code="APPROVAL_REJECTED",
          )

  def consume(
      self,
      command: ConsumeWritebackApprovalV1,
  ) -> ApprovalConsumptionResultV1:
      with self._db.immediate_transaction() as tx:
          approval = tx._load_writeback_approval(command.approval_id)
          verify_consumable(approval, command)
          changed = tx._consume_if_pending(approval.approval_id, command.subject_digest)
          if not changed:
              return ApprovalConsumptionResultV1(
                  kind="ALREADY_CONSUMED",
                  approval_id=approval.approval_id,
              )
          return ApprovalConsumptionResultV1(
              kind="CONSUMED",
              approval_id=approval.approval_id,
          )
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0`; only the first call returns `CONSUMED`.
- [ ] **Step 5: Refactor without behavior change.** Separate subject construction/current-binding verification from transactional approval state changes.
- [ ] **Step 6: Run domain tests.** Run the domain command. Expected: all immutable binding, lifecycle, race, and type-isolation cases pass.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Provide Task 14, SPEC §4.2.7/§4.4.2/§4.6, canonical subject bytes, and concurrent results.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of SQL compare-and-update, expiry races, binding inputs, and approval-type isolation.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add one-time writeback approval`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 14 PR.

### Milestone 15: DisclosureGrant Subjects and Authorization Ledger

**Status:** Not started

**Goal:** Authorize exact OpenAI request sources and cumulative bytes through immutable Grant subjects and atomic per-request authorization records without storing request bodies.

**SPEC / FR / NFR / AC references:** SPEC §4.2.7 disclosure wait; §4.4.3–§4.4.4 source/scope/budget contracts; §5.1–§5.2; §5.5–§5.6; §7 disclosure rows; §10.1 AC-13, AC-26, AC-27, AC-28.

**Dependencies:** Tasks 6 and 7.C.

**Blocks:** Tasks 16, 24–25, 29, and 31–32.

**Parallelization:** Parallel with Tasks 8, 23, 27, and 30 after Tasks 6 and 7; file ownership is disjoint.

**Recommended branch:** `codex/task-15-disclosure-ledger`

**Recommended worktree:** `.worktrees/task-15-disclosure-ledger`

**Files:**
- Create: `src/vespercode/storage/migrations/v0003_disclosure_grants.py`
- Create: `src/vespercode/storage/migrations/v0004_disclosure_authorizations.py`
- Create: `src/vespercode/governance/request_sources.py`
- Create: `src/vespercode/governance/disclosure_subject.py`
- Create: `src/vespercode/governance/disclosure_ledger.py`
- Test: `tests/unit/storage/test_disclosure_grants_migration.py`
- Test: `tests/unit/storage/test_disclosure_authorizations_migration.py`
- Test: `tests/unit/governance/test_request_sources.py`
- Test: `tests/unit/governance/test_disclosure_subject.py`
- Test: `tests/unit/governance/test_disclosure_scope.py`
- Test: `tests/unit/governance/test_disclosure_ledger.py`
- Test: `tests/unit/governance/test_disclosure_budget_race.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 4.C `ClockV1`; Task 5 path/location/optional/evidence and `WaitDecisionV1` contracts; Task 6 frozen OpenAI profile and endpoint mapping; Task 7.A `ControlDatabase.immediate_transaction`; Task 7.B wait lock/commit/expiry primitives; Task 7.C idempotency.
- Produces:
  - `RequestSourceCategoryV1`, `RequestContentSegmentV1`, `RequestMessageV1`, and `RequestSourceV1`
  - `RequestMessageSequenceV1`, an immutable ordered tuple of zero or more `RequestMessageV1` values
  - `DisclosureGrantSubjectV1`, `DisclosureGrantV1`, and `DisclosureAuthorizationRecordV1`
  - `DecideDisclosureGrantV1(wait_id: str, run_id: str, wait_kind: Literal["DISCLOSURE_GRANT"], subject_digest: DigestV1, decision: WaitDecisionChoiceV1, event_id: str)`
  - `DisclosureDecisionResultV1 = GrantActivatedV1 | DisclosureRejectedV1 | DisclosureExpiredV1 | DisclosureStaleV1 | DisclosureAlreadyDecidedV1`
  - result discriminators and payloads: `GrantActivatedV1(kind="GRANT_ACTIVATED", grant_id, subject_digest)`; `DisclosureRejectedV1(kind="REJECTED", error_code="DISCLOSURE_GRANT_REJECTED")`; `DisclosureExpiredV1(kind="EXPIRED", error_code="DISCLOSURE_GRANT_EXPIRED")`; `DisclosureStaleV1(kind="STALE", error_code="WAIT_STALE")`; `DisclosureAlreadyDecidedV1(kind="ALREADY_DECIDED", error_code="WAIT_STALE")`
  - `RevokeDisclosureGrantV1(grant_id: str, run_id: str, subject_digest: DigestV1, event_id: str)`
  - `AuthorizePreparedRequestV1(request_digest: str, messages: RequestMessageSequenceV1, canonical_byte_count: int, llm_profile_digest: str, provider: str, endpoint_id: str, model: str, request_serializer_version: str, redaction_profile_id: str, remaining_turns: int, remaining_calls: int, remaining_wall_clock_ms: int)`
  - `build_disclosure_subject(request: DisclosureSubjectRequestV1, sources: SourceProjectionV1, scopes: DisclosureScopeSequenceV1, profile: OpenAILLMProfileV1, endpoint: OpenAIEndpointV1) -> DisclosureGrantSubjectV1`
  - `validate_segment_sources(messages: RequestMessageSequenceV1) -> SourceProjectionV1`
  - `scope_matches(scope: DisclosurePathScopeV1, path: CanonicalRelativePathV1) -> bool`
  - `DisclosureDecisionServiceV1.decide(command: DecideDisclosureGrantV1) -> DisclosureDecisionResultV1`
  - `DisclosureLedger.authorize(command: AuthorizePreparedRequestV1) -> DisclosureAuthorizationOutcomeV1`
  - `DisclosureRevocationServiceV1.revoke(command: RevokeDisclosureGrantV1) -> GrantMutationResultV1`

**Implementation points:**
- Validate source category/path presence exactly: protocol/task/memory are pathless; file content has a path; tool result/feedback uses a path whenever the fact belongs to one file.
- Verify each segment's no-BOM UTF-8 `content_digest` and byte count before a prepared-request digest or ledger transaction can exist.
- Canonically sort scopes and categories. `ROOT` is exclusive; empty scopes authorize no path-bearing source; reject duplicates and Windows/Unicode aliases.
- Match `FILE` only exactly and `DIRECTORY` by equal path or the `path + "/"` descendant boundary.
- Build Grant subject endpoint/model/serializer/redaction values only from the frozen profile and built-in endpoint. Mutable status and consumed bytes do not alter the subject.
- Create the disclosure wait only from `AGENT_LOOP`; bind wait/run/kind/subject/expiry exactly.
- `DisclosureDecisionServiceV1` reads `now` from its injected Task 4.C `ClockV1`, converts the specialized command to Task 5 `WaitDecisionV1`, locks the wait through Task 7.B, reloads the immutable subject/profile/endpoint, and applies Grant creation plus Task 7.B transition in one `ControlTransactionV1`. `DisclosureRevocationServiceV1` separately locks and revokes only the exact active Grant. User input cannot supply an activation, rejection, expiry, or revocation timestamp.
- Subject reload and active-Grant insertion inside `DisclosureDecisionServiceV1.decide` are Task 15.D `_private/local` transaction helpers (for example `_load_disclosure_subject_for_update(...)` and `_activate_disclosure_grant(...)`), not exported repository/ledger callables; no downstream Task consumes them directly.
- The decision event id is recorded/replayed through Task 7.C idempotency in the same transaction. Exact replay returns the original typed result; conflicting bytes return `EVENT_ID_REUSE_CONFLICT`; neither path creates or activates another Grant.
- Exact `APPROVE` inserts one `DisclosureGrantV1(status="ACTIVE", consumed_bytes=0)` before atomically returning the Run to a new `AGENT_LOOP` entry. `REJECT` or an expired wait creates no Grant, stops through the closed wait lifecycle, and cannot call the real adapter.
- Revocation binds grant/run/subject/event/time, changes only an active matching Grant to `REVOKED`, and never transitions a Run by itself. Task 25.G must create the newly required disclosure wait when positive wall-clock time remains.
- Derive exactly one `RequestSourceV1` per request segment using zero-based message/segment indexes. Missing, duplicate, additional, or mismatched candidates return `INTERNAL_ERROR` before any ledger mutation.
- In one immediate transaction, revalidate active Grant, subject, scope/category, exact request digest, endpoint, redaction profile, remaining run/call budget, and cumulative byte budget; then charge bytes and persist one body-free authorization record.
- Equality with the limit sets Grant status to `EXHAUSTED`; insufficient budget, scope, expiry, revocation, or a lost race creates no record and consumes zero bytes.
- A committed charge is never refunded for adapter error, unknown delivery, or process interruption. The ledger exposes no API to retrieve source bodies.

**Implementation boundary:** This executable Task owns one disclosure subject/Grant/authorization ledger and atomic budget-charge behavior. It does not serialize/call an LLM, read credentials, count turns, dispatch tools, or authorize final writeback.

**Intentionally failing test:**

```python
def test_directory_scope_does_not_match_string_prefix_alias() -> None:
    scope = DirectoryScopeV1(kind="DIRECTORY", path="src")
    assert scope_matches(scope, "src") is True
    assert scope_matches(scope, "src/pkg/a.py") is True
    assert scope_matches(scope, "src-old/a.py") is False
```

**Verification:**
- Target: `python -m pytest -q tests/unit/governance/test_disclosure_scope.py::test_directory_scope_does_not_match_string_prefix_alias`
- Domain: `python -m pytest -q tests/unit/governance/test_request_sources.py tests/unit/governance/test_disclosure_subject.py tests/unit/governance/test_disclosure_scope.py tests/unit/governance/test_disclosure_ledger.py tests/unit/governance/test_disclosure_budget_race.py`
- Full: `python -m pytest -q`
- Expected: source presence, scope aliases, empty/root scope, subject digest, wait binding, exact projection, charge, exhaustion, rejection, and concurrent budget tests pass.

**Review gate:**
1. Spec compliance review traces every subject field, path/category rule, derived source, charge order, zero-side-effect failure, and non-refund rule to §4.4.3–§4.4.4.
2. Code quality review checks canonical sorting, segment byte verification, transaction predicates, race determinism, body-free storage, and endpoint immutability.
3. Critical/Important findings block prepared requests and real LLM calls.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the directory-boundary RED test.** Add the exact test and construct the scope through the closed discriminator.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because scope matching does not exist.
- [ ] **Step 3: Implement the minimum segment-aware scope matcher.**

  ```python
  def scope_matches(
      scope: DisclosurePathScopeV1,
      path: CanonicalRelativePathV1,
  ) -> bool:
      if scope.kind == "ROOT":
          return True
      if scope.kind == "FILE":
          return path == scope.path
      return path == scope.path or path.startswith(scope.path + "/")
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0`; `src-old/a.py` remains outside the directory scope.
- [ ] **Step 5: Refactor without behavior change.** Keep source validation, immutable subject construction, and transactional ledger behavior in separate planned modules.
- [ ] **Step 6: Run domain tests.** Run the domain command. Expected: all source, scope, projection, wait, budget, and concurrency cases pass.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Supply Task 15, SPEC §4.2.7/§4.4.3–§4.4.4/AC-13, canonical vectors, and transaction traces.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of body isolation, byte accounting, scope semantics, transaction atomicity, and concurrent limit handling.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add atomic disclosure authorization`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 15 PR.

### Milestone 16: Closed Prepared Requests and Mock/OpenAI Adapters

**Execution notice:** Non-executable aggregate contract. Only Tasks 16.A–16.B are executable.

**Status:** Not started

**Goal:** Implement the low-level single-turn LLM boundary with mode-specific request digests, exact payload-byte accounting, trusted OpenAI routing, and closed call-result combinations.

**SPEC / FR / NFR / AC references:** SPEC §4.2.1; §4.2.5; §4.2.8 LLM errors; §4.4.3–§4.4.4 prepared request/call sequence; §5.1–§5.2; §5.5; §7 LLM rows; §9 LLM choice; §10.1 AC-05, AC-13, AC-26, AC-28.

**Dependencies:** Tasks 6, 15, and 27.

**Blocks:** Tasks 17, 24–25, 29, and 31–32.

**Parallelization:** Parallel with Tasks 9 and 28 after Tasks 15 and 27; file ownership is disjoint.

**Recommended branch:** `codex/task-16-llm-boundary`

**Recommended worktree:** `.worktrees/task-16-llm-boundary`

**Files:**
- Create: `src/vespercode/llm/base.py`
- Create: `src/vespercode/llm/prepared_request.py`
- Create: `src/vespercode/llm/mock_adapter.py`
- Create: `src/vespercode/llm/openai_serializer.py`
- Create: `src/vespercode/llm/openai_adapter.py`
- Create: `src/vespercode/llm/call_result.py`
- Test: `tests/unit/llm/test_prepared_request.py`
- Test: `tests/unit/llm/test_mock_adapter.py`
- Test: `tests/unit/llm/test_openai_serializer.py`
- Test: `tests/unit/llm/test_openai_adapter.py`
- Test: `tests/unit/llm/test_call_result.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 6 `MockLLMProfileV1`, `OpenAILLMProfileV1`, and `OpenAIEndpointV1`; Task 15 messages, sources, Grant ledger, and durable authorization record; Task 27 `SecretCredentialV1` and credential lookup port.
- Produces:
  - `PreparedModelRequestV1 = MockPreparedModelRequestV1 | OpenAIPreparedModelRequestV1`
  - `MockAdapterPayloadV1`, `OpenAIFixedParametersV1`, `ModelResponse`, and `LLMCallResultV1`
  - `prepare_mock_request(profile: MockLLMProfileV1, messages: tuple[RequestMessageV1, ...]) -> MockPreparedModelRequestV1`
  - `prepare_openai_request(profile: OpenAILLMProfileV1, messages: tuple[RequestMessageV1, ...]) -> OpenAIPreparedModelRequestV1`
  - `LLMAdapter.generate(request: PreparedModelRequestV1) -> ModelResponse`
  - `MockLLMAdapter.generate(request: MockPreparedModelRequestV1) -> ModelResponse`
  - `OpenAILLMAdapter.bind(authorization: DisclosureAuthorizationRecordV1, credential: SecretCredentialV1) -> BoundOpenAILLMAdapterV1`
  - `BoundOpenAILLMAdapterV1.generate(request: OpenAIPreparedModelRequestV1) -> ModelResponse`

**Implementation points:**
- Reject unknown, missing, cross-mode, null, or profile-inconsistent fields before computing a request digest. The two concrete request type names are distinct digest domains.
- For Mock, canonicalize the exact `MockAdapterPayloadV1` interpreted by the script and use its canonical JSON byte length. Never construct or inspect Grant, credential, endpoint, provider, model, redaction, or authorization fields.
- For OpenAI, concatenate segment content in message order without inserting source metadata or implicit separators, serialize one exact request body, and bind `canonical_byte_count` to its final UTF-8 bytes.
- Validate source/path presence and content digest/byte count through Task 15 before either request is frozen; enforce 1–128 messages, 1–1024 total segments, and 64 KiB request bytes.
- Construct the OpenAI transport only from the built-in endpoint mapping. Ignore `OPENAI_BASE_URL` and equivalent SDK environment overrides; accept no base URL parameter.
- Use an injectable transport with one initial request, no automatic retry, and redirect handling disabled. A cross-origin redirect returns `LLM_ENDPOINT_MISMATCH` before replaying content.
- Bind a per-call OpenAI adapter to one durable authorization record and the fresh in-memory secret wrapper obtained by the call gate for that exact attempt, then expose the same one-argument `generate(request)` protocol. The adapter never caches or re-fetches credentials; an inconsistent record or missing fresh binding causes zero transport calls.
- Define and validate the closed `LLMCallResultV1` combinations: success has response digest and no error; every other status has no response digest and one stable error. Mock forbids `DELIVERY_UNKNOWN` and always has an absent authorization reference; OpenAI always has a present record reference. Task 25.C alone constructs this orchestration result from a provider response or typed adapter failure.
- A transport ambiguity may produce `DELIVERY_UNKNOWN`; failure, ambiguity, or a pre-call crash never causes an automatic retry or byte refund.
- Keep secret values in a non-serializable redacted wrapper passed directly to transport authorization headers. No adapter output, exception, repr, or log may reveal them.

**Intentionally failing test:**

```python
def test_mock_prepared_request_rejects_openai_fields(
    mock_profile: MockLLMProfileV1,
    valid_messages: tuple[RequestMessageV1, ...],
) -> None:
    raw = valid_mock_request_dict(mock_profile, valid_messages)
    raw["endpoint_id"] = "OPENAI_PUBLIC_API_V1"
    with pytest.raises(ValidationError):
        MockPreparedModelRequestV1.model_validate(raw)
```

**Verification:**
- Target: `python -m pytest -q tests/unit/llm/test_prepared_request.py::test_mock_prepared_request_rejects_openai_fields`
- Domain: `python -m pytest -q tests/unit/llm`
- Full: `python -m pytest -q`
- Expected: mode unions, distinct digest domains, exact byte counts, serializer vectors, malicious environment, endpoint mismatch, redirect, no-retry, fresh per-attempt credential/authorization binding, result combinations, and secret-redaction tests pass offline.

**Review gate:**
1. Spec compliance review traces both request variants and the complete request → source/endpoint validation → per-call credential revalidation → Grant/record → count → call/result ordering in §4.4.4.
2. Code quality review checks serializer byte identity, environment isolation, transport redirect policy, secret wrapper behavior, no-retry control flow, and result-schema validation.
3. Critical/Important findings block action parsing, context projection, and the main loop.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the cross-mode RED test.** Add the exact test and construct the otherwise valid request through fixed profile/message fixtures.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because concrete prepared-request schemas do not exist.
- [ ] **Step 3: Implement the minimum discriminated request variants.**

  ```python
  PreparedModelRequestV1 = TypeAdapter(
      Annotated[
          MockPreparedModelRequestV1 | OpenAIPreparedModelRequestV1,
          Field(discriminator="mode"),
      ]
  )

  def prepare_mock_request(
      profile: MockLLMProfileV1,
      messages: tuple[RequestMessageV1, ...],
  ) -> MockPreparedModelRequestV1:
      payload = MockAdapterPayloadV1.from_profile(profile, messages)
      return MockPreparedModelRequestV1.from_payload(profile, payload)
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0`; the extra OpenAI field is rejected.
- [ ] **Step 5: Refactor without behavior change.** Keep protocol, prepared schemas, Mock behavior, serialization, OpenAI transport, and call-result validation in the six planned modules.
- [ ] **Step 6: Run domain tests.** Run `python -m pytest -q tests/unit/llm`. Expected: all mode, byte, digest, transport, result, and secret-isolation cases pass.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0` with no network request.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0` and no secret value is printed.
- [ ] **Step 9: Request spec compliance review.** Provide Task 16, SPEC §4.2.1/§4.4.4/AC-05/AC-13/AC-28, byte vectors, and transport traces.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of mode typing, serializer determinism, HTTP target enforcement, redirect handling, error mapping, and secret lifetime.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add closed single-turn LLM adapters`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 16 PR.

### Milestone 17: Agent Action Parser, Identity Binding, and Dispatcher

**Status:** Not started

**Goal:** Parse exactly one closed model action, assign Harness-owned semantic/instance identity, and dispatch it only after candidate, path, phase, and policy checks.

**SPEC / FR / NFR / AC references:** SPEC §4.2.1–§4.2.3; §4.2.5 behavior 3–5; §4.2.8; §4.3 candidate binding; §4.4.1; §5.1–§5.2; §7 ActionRecord; §10.1 AC-02, AC-06, AC-17, AC-18, AC-26, AC-28, AC-31.

**Dependencies:** Tasks 5, 11.B, 12.D, 13, 16.A, and 16.B.

**Blocks:** Tasks 25, 29, and 31–32.

**Parallelization:** Parallel with Task 19 after Tasks 13 and 16; file ownership is disjoint.

**Recommended branch:** `codex/task-17-action-dispatch`

**Recommended worktree:** `.worktrees/task-17-action-dispatch`

**Files:**
- Create: `src/vespercode/loop/agent_actions.py`
- Create: `src/vespercode/loop/action_parser.py`
- Create: `src/vespercode/loop/action_binding.py`
- Create: `src/vespercode/tools/dispatcher.py`
- Test: `tests/unit/loop/test_agent_actions.py`
- Test: `tests/unit/loop/test_action_parser.py`
- Test: `tests/unit/loop/test_action_binding.py`
- Test: `tests/unit/tools/test_dispatcher.py`
- Test: `tests/unit/tools/test_dispatch_order.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 5 shared action/result identities and `CheckPlanIdV1`; Tasks 11.A and 11.B file actions; Tasks 12.A and 12.B patch action/current candidate; Task 13 `PolicyEngine`; Task 16.A `ModelResponse`.
- Produces:
  - `RunCheckAction`, `ProposeCompletionAction`, and closed `AgentAction`
  - `ActionParser.parse(response: ModelResponse) -> AgentAction | ParseErrorV1`
  - `bind_action(action: AgentAction, id_generator: ActionIdGeneratorV1) -> ActionInstanceV1`
  - `DispatchContextV1(run_id: str, phase: RunPhase, current_candidate_digest: str, policy_context: PolicyContextV1, ports: ToolPortsV1)`
  - `ArtifactStorePortV1.put(payload: FileToolResultV1) -> ArtifactRefV1`
  - `FileToolOutcomeV1`, the file-action subset of `ActionResultV1`
  - `publish_file_tool_outcome(instance: ActionInstanceV1, result: FileToolResultV1, artifact_store: ArtifactStorePortV1) -> FileToolOutcomeV1`
  - `ToolDispatcher.dispatch(instance: ActionInstanceV1, context: DispatchContextV1) -> ActionResultV1`
  - `ToolPortsV1(list_files, read_file, search_text, apply_candidate_patch, run_check, propose_completion)`

**Implementation points:**
- Accept only a JSON object containing one action and no surrounding text. Reject arrays, multiple objects, markdown fences, unknown action types, unknown fields, omissions, defaults, and model-supplied `action_id`.
- Compose the six-action discriminated union from the exact upstream schemas. `RunCheckAction` accepts only four `CheckPlanIdV1` values and no executable/argv/environment/working-directory fields.
- Validate all lengths and path/location rules before action identity creation; invalid model output produces no action id.
- Calculate the semantic digest over the exact `AgentAction`, including List/Search cursor; calculate the cursor-free query digest only in Task 11.B; calculate instance digest over schema version, injected non-empty action id, and semantic digest.
- Enforce the dispatch order: closed schema → base/current candidate binding → path/object facts → phase matrix → policy → exact registered port.
- Phase-forbidden actions return `ACTION_NOT_ALLOWED_IN_PHASE` and never create an approval. A hard `DENY` never invokes the port and publishes a structured rejection.
- Candidate-stale patch/completion/check requests are rejected before policy and tool calls. File reads/searches/listing use the current immutable tree but are not restricted to `src/**`.
- Task 11 file ports return only their exact typed pure results. Task 17.C validates each complete `FileToolResultV1`, converts deterministic failures to a zero-payload `FileToolOutcomeV1`, and publishes successful bounded payloads atomically through `ArtifactStorePortV1`; illegal combinations or a port exception fail closed as `INTERNAL_ERROR`.
- Track repeated-action semantics by semantic digest/result digest, not action id; the main-loop counters remain Task 25.

**Implementation boundary:** This executable Task owns one closed action parse → identity-bind → phase-aware dispatch boundary. It does not assemble context, call an LLM, evaluate stopping, persist loop state, or implement concrete tool/domain behavior.

**Intentionally failing test:**

```python
def test_model_cannot_supply_action_id(action_parser: ActionParser) -> None:
    response = ModelResponse(
        content=(
            '{"schema_version":1,"action_type":"list_files",'
            '"action_id":"model-owned","root":{"kind":"ROOT"},'
            '"recursive":true,"max_entries":20,"cursor":{"kind":"ABSENT"}}'
        )
    )
    parsed = action_parser.parse(response)
    assert isinstance(parsed, ParseErrorV1)
    assert parsed.error_code == "ACTION_SCHEMA_INVALID"
```

**Verification:**
- Target: `python -m pytest -q tests/unit/loop/test_action_parser.py::test_model_cannot_supply_action_id`
- Domain: `python -m pytest -q tests/unit/loop/test_agent_actions.py tests/unit/loop/test_action_parser.py tests/unit/loop/test_action_binding.py tests/unit/tools/test_dispatcher.py tests/unit/tools/test_dispatch_order.py`
- Full: `python -m pytest -q`
- Expected: all six schemas, required typed List/Search cursor fields, invalid output forms, identity vectors including cursor changes, stale/phase/policy order, zero-dispatch rejection, and result-envelope tests pass.

**Review gate:**
1. Spec compliance review verifies every action field including typed cursor, the six-action/phase matrix, action/query/cursor digest separation, and ordered validation path against §4.2.
2. Code quality review checks parser strictness, union exhaustiveness, port typing, error containment, deterministic IDs in tests, and result publication atomicity.
3. Critical/Important findings block the main-loop integration.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the model-owned-ID RED test.** Add the exact response and assert no ID-generator invocation.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because the parser and closed action union do not exist.
- [ ] **Step 3: Implement the minimum exact-one-object parser.**

  ```python
  def parse(self, response: ModelResponse) -> AgentAction | ParseErrorV1:
      raw = parse_one_json_object_without_trailing_text(response.content)
      try:
          return AgentActionAdapter.validate_python(raw)
      except ValidationError as exc:
          return ParseErrorV1.from_validation_error("ACTION_SCHEMA_INVALID", exc)
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0` with the stable schema error and zero generated IDs.
- [ ] **Step 5: Refactor without behavior change.** Keep action composition, parsing, identity binding, and phase/policy dispatch in the four planned modules.
- [ ] **Step 6: Run domain tests.** Run the domain command. Expected: all schema, identity, ordering, phase, stale-candidate, and zero-side-effect cases pass.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Supply Task 17, SPEC §4.2.1–§4.2.3/§4.2.5/AC-17, action fixtures, and dispatch call traces.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of JSON framing, Pydantic union closure, digest inputs, phase gates, policy placement, and exception conversion.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add closed action dispatch`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 17 PR.

### Milestone 18: Production Docker Execution Boundary

**Status:** Not started

**Goal:** Execute each frozen check in a fresh, locked Linux container over a newly materialized read-only CandidateTree and return bounded raw evidence without interpreting pass/fail.

**SPEC / FR / NFR / AC references:** SPEC §1.4.1 runtime compatibility; §1.4.5; §4.1 readiness; §4.3 cleanup; §4.5 adapter/check execution; §5.1; §5.5; §8.2; §10.1 AC-04, AC-19, AC-20, AC-24, AC-25, AC-30; §10.3 Docker integration.

**Dependencies:** Tasks 2, 4.E, 5, 6, 10, and 12.D; Task 2 `GO` is the non-task entry gate.

**Blocks:** Tasks 19–21, 25, 31, 34–36, and 38.

**Parallelization:** Parallel with Task 13 after Task 12; file ownership is disjoint.

**Recommended branch:** `codex/task-18-docker-executor`

**Recommended worktree:** `.worktrees/task-18-docker-executor`

**Files:**
- Create: `src/vespercode/execution/docker_profile.py`
- Create: `src/vespercode/execution/docker_executor.py`
- Test: `tests/unit/execution/test_docker_profile.py`
- Test: `tests/unit/execution/test_docker_request.py`
- Test: `tests/unit/execution/test_docker_executor.py`
- Test: `tests/integration/docker/test_execution_isolation.py`
- Test: `tests/integration/docker/test_fresh_candidate_materialization.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 2 GO manifest/image evidence; Task 5 `CheckPlanIdV1`/`ArtifactRefV1`; Task 6 verified reference profile; Task 10 content store; Task 12.B CandidateTree and Task 12.D FinalDiff integrity.
- Produces:
  - `ExecutionArgumentSequenceV1`, an immutable ordered tuple of zero or more strings
  - `DockerExecutionProfileV1`
  - `ExecutionRequestV1(check_kind: CheckPlanIdV1, argv: ExecutionArgumentSequenceV1, environment: Mapping[str, str], candidate_tree_digest: str, timeout_seconds: int)`
  - `RawExecutionResultV1(exit_code: int | None, stdout_ref: ArtifactRefV1, stderr_ref: ArtifactRefV1, report_ref: ArtifactRefV1 | None, output_bytes: int, timed_out: bool, execution_identity_digest: str)`
  - `DockerReadinessService.verify(reference: ReferenceProfileManifestV1) -> ExecutionReadinessResultV1`
  - `DockerExecutor.execute(request: ExecutionRequestV1, candidate: MaterializedCandidateV1) -> RawExecutionResultV1`
  - `materialize_candidate(candidate: CandidateTreeV1, root: AuthorizedExecutionRootV1) -> MaterializedCandidateV1`

**Implementation points:**
- Verify Docker Desktop Linux mode, exact locally present RepoDigest, image/profile/tool mapping, daemon target, and absence of an image-build/install path before admission readiness succeeds.
- Build requests only from adapter-generated tuple argv and the exact environment allowlist. Never invoke a shell or accept executable/environment/working-directory fields from the model.
- Before container creation, verify current Candidate/FinalDiff/policy integrity and materialize exact content objects into a fresh UUID directory with a recorded root identity.
- Start each check with network disabled, non-root user, read-only root, all capabilities dropped, no Docker socket/device mounts, read-only `/workspace`, bounded tmpfs/cache mounts, 2 CPU, 2 GiB memory, 256 PIDs, and 256 MiB tmpfs.
- Apply the minimum of check timeout and remaining run deadline. Stop/kill the exact container on timeout and return a typed timed-out raw result.
- Stream stdout/stderr/report through independent bounded collectors. Crossing 4 MiB returns `CHECK_OUTPUT_LIMIT_EXCEEDED`; truncated evidence can never be interpreted as PASS.
- Verify candidate bytes before and after execution and prove no project-tree write. Mutation yields `EXECUTION_WORKSPACE_MUTATED`.
- Remove the exact container and verified UUID materialization root without following links. Cleanup failure records the exact residual artifact, forbids root-name reuse, and fails the run.
- Every invocation uses a new materialization and new container id; no cache, tmpfs, container, or report artifact is reused between checks.

**Implementation boundary:** This executable Task owns one fresh-container execution boundary for a prebuilt closed `ExecutionRequestV1`. It cannot choose commands from model/repository text, interpret check results, decide Baseline/formal success, build images, or write the workspace.

**Intentionally failing test:**

```python
def test_execution_request_rejects_network_or_writable_workspace() -> None:
    raw = valid_execution_request_dict()
    raw["network_mode"] = "bridge"
    raw["workspace_read_only"] = False
    with pytest.raises(ValidationError):
        ExecutionRequestV1.model_validate(raw)
```

**Verification:**
- Target: `python -m pytest -q tests/unit/execution/test_docker_request.py::test_execution_request_rejects_network_or_writable_workspace`
- Domain: `python -m pytest -q tests/unit/execution`
- Docker integration: `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_execution_isolation.py tests/integration/docker/test_fresh_candidate_materialization.py`
- Full: `python -m pytest -q`
- Expected: offline request/profile tests pass; Docker tests prove every locked boundary, fresh identity, output/timeout enforcement, tree immutability, and exact cleanup.

**Review gate:**
1. Spec compliance review compares every Docker flag, mount, resource, environment, freshness, output, timeout, integrity, and readiness rule with §1.4.5 and §4.5.
2. Code quality review checks SDK argument construction, container/root identity ownership, streaming caps, cancellation, cleanup safety, and absence of shell/image-build code.
3. Critical/Important findings or a skipped required Docker case block Task 19.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the locked-request RED test.** Add the exact test and a valid request fixture containing only the closed production fields.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because the execution profile/request schema does not exist.
- [ ] **Step 3: Implement the minimum immutable execution request.**

  ```python
  class ExecutionRequestV1(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=True)
      schema_version: Literal[1]
      check_kind: CheckPlanIdV1
      argv: tuple[str, ...]
      environment: FrozenEnvironmentV1
      candidate_tree_digest: DigestV1
      timeout_seconds: PositiveInt
  ```

  Container policy fields come only from verified `DockerExecutionProfileV1`, not request input.
- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0`; network/workspace override fields are rejected.
- [ ] **Step 5: Refactor without behavior change.** Keep profile validation, request/materialization, SDK execution, bounded collection, integrity checks, and cleanup as explicit internal stages.
- [ ] **Step 6: Run domain and Docker tests.** Run both domain and Docker integration commands. Expected: all required Docker cases execute and pass without skip.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0` without contacting Docker.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Give a fresh reviewer Task 18, Task 2 GO report, SPEC §1.4.5/§4.5, SDK call captures, and integration evidence.
- [ ] **Step 10: Close spec findings.** Apply minimal fixes, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of no-shell arguments, Docker cleanup, path identity, streaming memory bounds, timeouts, and daemon error mapping.
- [ ] **Step 12: Close quality findings.** Close every Critical/Important issue, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add locked Docker executor`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 18 PR.

### Milestone 19: Pytest Evidence, Check Results, and Failure Fingerprints

**Execution notice:** Non-executable aggregate contract. Only Tasks 19.A–19.C are executable; they separately own closed check results, authoritative pytest evidence, and stable failure fingerprints.

**Status:** Not started

**Goal:** Turn complete machine-readable pytest/Ruff/Mypy artifacts into closed check evidence and stable target failure fingerprints without trusting exit code or truncated text.

**SPEC / FR / NFR / AC references:** SPEC §1.4.1 runtime compatibility; §4.5 `PytestEvidenceV1`, fingerprint, check execution, errors, and deterministic tests; §5.2; §5.5 trust assumption; §7 evidence rows; §10.1 AC-19, AC-20, AC-24, AC-25, AC-26.

**Dependencies:** Tasks 4–6 and 18.

**Blocks:** Tasks 20–22, 24–25, 31–32, 34–36, and 38.

**Parallelization:** Parallel with Task 17 after Task 18; file ownership is disjoint.

**Recommended branch:** `codex/task-19-check-evidence`

**Recommended worktree:** `.worktrees/task-19-check-evidence`

**Files:**
- Create: `src/vespercode/validation/check_result.py`
- Create: `src/vespercode/validation/pytest_evidence.py`
- Create: `src/vespercode/validation/pytest_reporter.py`
- Create: `src/vespercode/validation/failure_fingerprint.py`
- Test: `tests/unit/validation/test_check_result.py`
- Test: `tests/unit/validation/test_pytest_evidence.py`
- Test: `tests/unit/validation/test_pytest_reporter.py`
- Test: `tests/unit/validation/test_failure_fingerprint.py`
- Test: `tests/unit/validation/test_ruff_mypy_parsing.py`
- Test: `tests/integration/docker/test_pytest_report_channel.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 4 canonicalization/path/digest; Task 5 optional/evidence contracts; Task 6 frozen tool versions; Task 18 `RawExecutionResultV1`.
- Produces:
  - `ErrorPhase`, `TestStatus`, `PytestEventV1`, `PytestEvidenceV1`, and `StructuredExceptionV1`
  - `FailureFingerprintV1` and `ProjectFrameSignatureV1`
  - `CheckResultV1(status: Literal["PASS","FAIL","ERROR","TIMEOUT","NOT_RUN"], check_kind: CheckPlanIdV1, structured_findings: tuple[CheckFindingV1, ...], raw_digest: str)`
  - `parse_pytest_evidence(raw: bytes, expectation: PytestReportExpectationV1) -> PytestParseOutcomeV1`
  - `build_failure_fingerprint(evidence: PytestEvidenceV1, node_id: str, normalization: FingerprintNormalizationContextV1) -> FingerprintOutcomeV1`
  - `parse_ruff_result(raw: RawExecutionResultV1, profile: ReferenceProfileManifestV1) -> CheckResultV1`
  - `parse_mypy_result(raw: RawExecutionResultV1, profile: ReferenceProfileManifestV1) -> CheckResultV1`

**Implementation points:**
- The Harness-owned pytest plugin emits the exact ordered event schema, explicit `ABSENT/PRESENT` fields, counts, normal end marker, and canonical integrity digest through the closed report channel.
- Reject missing/end-out-of-order, sequence gaps, duplicates, unknown events, illegal event-field combinations, plan/collection mismatch, version mismatch, digest mismatch, truncation, or output-limit evidence as `REPORTER_INVALID`.
- Treat stdout/stderr and pytest exit code only as bounded diagnostics; neither can synthesize missing structured facts or PASS.
- Parse Ruff and Mypy only in profile-frozen formats and versions. Unknown category, malformed/truncated record, or incomplete report becomes `CHECK_ERROR`.
- Create a fingerprint only for an exact target `CALL/FAIL` with complete structured exception data.
- Normalize only known execution root, tmp root, run/container id, and reporter-marked object addresses. Preserve user numbers, time-like text, and hexadecimal values.
- Include only Snapshot paths, function names, and line numbers in call order. Exclude framework/stdlib/site-packages frames and volatile event metadata.
- Missing or unsafe-to-normalize content returns `TARGET_UNSTABLE`; non-assertion failures explicitly bind absent assertion diff.
- Validate the closed `CheckResultV1` status/finding combinations before publication.

**Intentionally failing test:**

```python
def test_missing_session_end_is_reporter_invalid(
    complete_pytest_report_dict: dict[str, object],
) -> None:
    complete_pytest_report_dict["events"] = complete_pytest_report_dict["events"][:-1]
    complete_pytest_report_dict["integrity_digest"] = recompute_report_digest(
        complete_pytest_report_dict
    )
    outcome = parse_pytest_evidence(
        canonical_json_bytes(complete_pytest_report_dict),
        expectation=expected_full_pytest_report(),
    )
    assert outcome.kind == "ERROR"
    assert outcome.error_code == "REPORTER_INVALID"
    assert outcome.evidence is None
```

**Verification:**
- Target: `python -m pytest -q tests/unit/validation/test_pytest_evidence.py::test_missing_session_end_is_reporter_invalid`
- Domain: `python -m pytest -q tests/unit/validation`
- Docker integration: `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_pytest_report_channel.py`
- Full: `python -m pytest -q`
- Expected: all event/state corruption, version, output, Ruff/Mypy, normalization, phase, fingerprint stability/instability, and real report-channel cases pass.

**Review gate:**
1. Spec compliance review maps the complete evidence schema, invalidity table, trust assumption, normalization algorithm, and check-status semantics to §4.5.
2. Code quality review checks plugin/parser separation, total validation, bounded raw handling, normalization allowlist, version dispatch, and deterministic fixtures.
3. Critical/Important findings or a skipped Docker report-channel test block Baseline and formal validation.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the missing-end RED test.** Add the exact test with a canonical complete report fixture, then remove only the final event.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because the evidence parser does not exist.
- [ ] **Step 3: Implement the minimum full-report validator.**

  ```python
  def parse_pytest_evidence(
      raw: bytes,
      *,
      expectation: PytestReportExpectationV1,
  ) -> PytestParseOutcomeV1:
      document = decode_closed_report(raw)
      validate_event_sequence(document.events)
      require_normal_session_end(document)
      require_expected_collection(document, expectation)
      require_integrity_digest(document)
      return PytestParseOutcomeV1.evidence(document)
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0` with `REPORTER_INVALID` and no evidence.
- [ ] **Step 5: Refactor without behavior change.** Keep result schemas, report parsing, plugin emission, and fingerprint normalization in their four planned modules.
- [ ] **Step 6: Run domain and Docker tests.** Run both domain and Docker integration commands. Expected: all offline cases and the real report channel pass without skip.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Provide Task 19, SPEC §4.5/AC-25, schema fixtures, corruption matrix, normalization vectors, and Docker report evidence.
- [ ] **Step 10: Close spec findings.** Apply minimal fixes, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of parser completeness, plugin/report coupling, raw bounds, normalization precision, and status combinations.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add authoritative check evidence`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 19 PR.

### Milestone 20: Python Adapter, Baseline, and ValidationManifestV1

**Execution notice:** Non-executable aggregate contract. Only Tasks 20.A–20.B are executable.

**Status:** Not started

**Goal:** Detect the sole static project profile from the sealed Snapshot, run the exact stable-failure baseline, evaluate runtime compatibility, and freeze the immutable validation contract.

**SPEC / FR / NFR / AC references:** SPEC §1.4.1 `PythonProjectProfileV1`, static detection, runtime compatibility; §4.1 behavior 9–13; §4.5 adapter boundary, baseline, Manifest, errors/tests; §5.1–§5.2; §7 static/runtime/Manifest rows; §10.1 AC-04, AC-15, AC-19, AC-20, AC-25, AC-26, AC-30–AC-31.

**Dependencies:** Tasks 5, 6, 8, 10, 18, and 19.

**Blocks:** Tasks 14, 21, 25, 29, 31, 34–36, and 38.

**Parallelization:** Parallel with Task 22 after Task 19; file ownership is disjoint.

**Recommended branch:** `codex/task-20-baseline-manifest`

**Recommended worktree:** `.worktrees/task-20-baseline-manifest`

**Files:**
- Create: `src/vespercode/validation/python_adapter.py`
- Create: `src/vespercode/validation/baseline.py`
- Create: `src/vespercode/validation/manifest.py`
- Test: `tests/unit/validation/test_python_adapter_static.py`
- Test: `tests/unit/validation/test_check_plan.py`
- Test: `tests/unit/validation/test_baseline.py`
- Test: `tests/unit/validation/test_runtime_compatibility.py`
- Test: `tests/unit/validation/test_manifest.py`
- Test: `tests/integration/docker/test_reference_baseline.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 5 `CheckPlanIdV1`; Task 6 reference manifest; Task 8 admission ports/config/targets; Task 10 sealed Snapshot; Task 18 executor; Task 19 check evidence/fingerprints.
- Produces:
  - `TargetTestIdSequenceV1`, an immutable ordered tuple of one or more target ids
  - `StaticProjectProfileResultV1 = SupportedProjectV1 | UnsupportedProjectV1`
  - `PythonProjectAdapterV1.detect_static(snapshot: SnapshotTreeV1, reference_manifest: ReferenceProfileManifestV1) -> StaticProjectProfileResultV1`
  - `PythonProjectAdapterV1.build_baseline_plan(static_profile: SupportedProjectV1, target_test_ids: TargetTestIdSequenceV1) -> BaselineCheckPlanV1`
  - `PythonProjectAdapterV1.build_formal_plan(manifest: ValidationManifestV1, candidate: CandidateIdentityV1) -> FormalValidationCheckPlanV1`
  - `BaselineResultV1 = PassingBaselineV1 | BaselineBlockedV1`
  - `run_baseline(plan: BaselineCheckPlanV1, snapshot: SnapshotTreeV1, executor: DockerExecutor) -> BaselineResultV1`
  - `create_validation_manifest(baseline: PassingBaselineV1, bindings: ManifestBindingsV1) -> ValidationManifestV1`

**Implementation points:**
- Static detection reads only the sealed Snapshot and built-in manifest; it binds Snapshot root, repository policy, and reference digest in both supported and unsupported variants.
- Require exact tracked structure/config/lock/profile conditions from `StaticProjectProfileCheckV1`; do not run project code, reread Git/workspace state, create a Snapshot, or decide runtime compatibility.
- Generate all collect/full/target/Ruff/Mypy argv and environment from one versioned adapter/check-plan table. The model and repository cannot supply commands.
- Execute baseline in the exact order: collect-only A, collect-only B, full pytest, target-only rerun, Ruff, Mypy; each check receives a fresh Docker invocation and candidate materialization.
- Require identical, non-empty collection sets. Every target must be present and produce identical complete `CALL/FAIL` fingerprints in full and target rerun.
- Require every non-target actually run and PASS; reject skip, xfail, xpass, deselect, not-run, any error phase, timeout, report failure, Ruff failure, or Mypy failure.
- Task 20.B evaluates image/tool/profile/environment/read-only/runtime facts as `COMPATIBLE` or a structured `BASELINE_BLOCKED` through a private local `_evaluate_runtime_compatibility` helper. It is not exported, has no downstream consumer, and cannot replace `run_baseline`; no Manifest is created for a blocked result.
- Build all Manifest fields explicitly, sort only the specified target/test record collections, preserve the two collect evidence digests in execution order, and verify every tool/image/policy/Snapshot binding against the same reference profile.
- Unknown, contradictory, truncated, unstable, or mismatched evidence fails closed with a stable baseline error; a pytest exit code alone never passes.

**Intentionally failing test:**

```python
def test_target_that_passes_in_full_baseline_creates_no_manifest(
    baseline_plan: BaselineCheckPlanV1,
    snapshot: SnapshotTreeV1,
    executor: DockerExecutor,
) -> None:
    result = run_baseline(baseline_plan, snapshot, executor)
    assert isinstance(result, BaselineBlockedV1)
    assert result.reason == "TARGET_NOT_REPRODUCED"
```

**Verification:**
- Target: `python -m pytest -q tests/unit/validation/test_baseline.py::test_target_that_passes_in_full_baseline_creates_no_manifest`
- Domain: `python -m pytest -q tests/unit/validation/test_python_adapter_static.py tests/unit/validation/test_check_plan.py tests/unit/validation/test_baseline.py tests/unit/validation/test_runtime_compatibility.py tests/unit/validation/test_manifest.py`
- Docker integration: `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_reference_baseline.py`
- Full: `python -m pytest -q`
- Expected: static order/binding, fixed plans, all baseline rejection predicates, exact stable target fingerprints, compatibility, Manifest vectors, and reference Docker baseline pass.

**Review gate:**
1. Spec compliance review traces all static checks, admission ordering, six baseline executions, compatibility outcomes, and every Manifest field to §1.4.1 and §4.5.
2. Code quality review checks adapter/core separation, check-plan closure, executor-call ordering, immutable evidence aggregation, stable sorting, and Manifest integrity validation.
3. Critical/Important findings or a skipped required Docker baseline block formal validation.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the target-PASS RED test.** Add the exact test with complete reports in which only the target outcome violates the stable-failure contract.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because the baseline evaluator does not exist.
- [ ] **Step 3: Implement the minimum target-reproduction predicate.** `_require_stable_targets` is a private local Task 20.B helper with no downstream consumer, not an alternate Milestone API.

  ```python
  def _require_stable_targets(
      full: PytestEvidenceV1,
      rerun: PytestEvidenceV1,
      targets: tuple[str, ...],
  ) -> tuple[FailureFingerprintV1, ...]:
      full_fingerprints = fingerprints_for_call_fail_targets(full, targets)
      rerun_fingerprints = fingerprints_for_call_fail_targets(rerun, targets)
      if fingerprint_digests(full_fingerprints) != fingerprint_digests(rerun_fingerprints):
          raise BaselineBlockedError("TARGET_NOT_REPRODUCED")
      return full_fingerprints
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0`, blocked baseline, and no Manifest.
- [ ] **Step 5: Refactor without behavior change.** Keep static detection/check plans, ordered baseline evaluation, runtime compatibility, and Manifest construction in the three planned modules.
- [ ] **Step 6: Run domain and Docker tests.** Run both domain and Docker integration commands. Expected: all offline cases and real reference baseline pass without skip.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Provide Task 20, SPEC §1.4.1/§4.1/§4.5/AC-15/AC-25, call traces, Manifest bytes, and Docker evidence.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of static purity, execution order, target/non-target predicates, evidence ownership, digest binding, and adapter boundaries.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add stable baseline manifest`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 20 PR.

### Milestone 21: Formal Validation and VerifiedCandidate

**Status:** Not started

**Goal:** Revalidate the entire candidate/policy/environment binding, execute the complete frozen formal plan, and create `VerifiedCandidateV1` only when every success predicate is proven.

**SPEC / FR / NFR / AC references:** SPEC §4.2.3 formal-validation phase; §4.2.5 completion; §4.3 candidate identity; §4.4.2 final subject inputs; §4.5 check execution and formal success predicate; §4.6 writeback inputs; §7 VerifiedCandidate; §10.1 AC-03–AC-07, AC-18, AC-20, AC-26–AC-28, AC-31.

**Dependencies:** Tasks 12.D, 18, 19.C, and 20.B.

**Blocks:** Tasks 14, 25–26, 29, 31–32, and 38.

**Parallelization:** Parallel with Task 24 after Tasks 20 and 22; file ownership is disjoint.

**Recommended branch:** `codex/task-21-formal-validation`

**Recommended worktree:** `.worktrees/task-21-formal-validation`

**Files:**
- Create: `src/vespercode/validation/formal.py`
- Test: `tests/unit/validation/test_formal_plan.py`
- Test: `tests/unit/validation/test_formal_predicate.py`
- Test: `tests/unit/validation/test_verified_candidate.py`
- Test: `tests/integration/docker/test_reference_formal_validation.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 12.D current `CandidateRevisionV1`, `FinalDiffV1`, and policy integrity; Task 18 Docker executor; Task 19.C authoritative check results; Task 20.B `ValidationManifestV1` and Python adapter.
- Produces:
  - `FormalValidationPlanV1`, `FormalValidationRequestV1`, and `build_formal_validation_plan(manifest: ValidationManifestV1, candidate: CandidateRevisionV1, final_diff: FinalDiffV1) -> FormalValidationPlanV1`
  - `FormalValidationEvidenceV1` and `execute_formal_plan(plan: FormalValidationPlanV1, executor: DockerExecutionPortV1) -> FormalValidationEvidenceV1`
  - `FormalValidationOutcomeV1`
  - `VerifiedCandidateV1(candidate_id: str, candidate_digest: str, final_diff_digest: str, validation_manifest_digest: str, formal_result_digest: str)`
  - `evaluate_formal_success(manifest: ValidationManifestV1, candidate: CandidateRevisionV1, plan: FormalValidationPlanV1, evidence: FormalValidationEvidenceV1) -> VerifiedCandidateV1 | FormalValidationFailureV1`

**Implementation points:**
- Enter formal validation only from a valid current-candidate completion proposal; Agent actions and turn consumption are disabled during this phase.
- Before any container call, recompute FinalDiff, validate every editable path, and verify reference/Snapshot/repository/governance/Manifest policy identities. Path or integrity failure creates zero containers.
- Build the complete frozen collect/full pytest/Ruff/Mypy plan from the Manifest and versioned adapter; the model cannot select or remove a formal check.
- Give every check a fresh container/tree and apply both per-check timeout and the smaller remaining formal/run deadlines.
- Require the final collection set to equal the Manifest exactly and every collected node to have one actually executed `PASS`.
- Reject every skip, xfail, xpass, deselect, not-run, collection/setup/call/teardown/environment error, timeout, incomplete report, Ruff failure, or Mypy failure even when pytest exits zero.
- Prove each baseline target changed from its Manifest-bound stable `CALL/FAIL` fingerprint to final PASS.
- Revalidate candidate tree, FinalDiff, protected artifacts, check plan, versions, image/resource/environment digests, and read-only execution evidence after all checks.
- Derive `formal_result_digest` from the complete ordered formal evidence. Construct no `VerifiedCandidateV1` until the entire closed predicate succeeds.
- A failed formal run emits structured feedback and returns to a new `AGENT_LOOP`; it does not reuse a stale completion action or final approval.

**Implementation boundary:** This executable Task owns one pure formal-success predicate and `VerifiedCandidate` construction from immutable evidence. It does not execute checks, repair code, approve/write files, or publish final Run success.

**Intentionally failing test:**

```python
def test_pytest_exit_zero_with_skipped_node_creates_no_verified_candidate(
    validation_manifest: ValidationManifestV1,
    current_candidate: CandidateRevisionV1,
    formal_plan: FormalValidationPlanV1,
    formal_evidence_with_skip: FormalValidationEvidenceV1,
) -> None:
    outcome = evaluate_formal_success(
        validation_manifest,
        current_candidate,
        formal_plan,
        formal_evidence_with_skip,
    )
    assert isinstance(outcome, FormalValidationFailureV1)
    assert outcome.error_code == "FORMAL_VALIDATION_FAILED"
    assert outcome.verified_candidate is None
```

**Verification:**
- Target: `python -m pytest -q tests/unit/validation/test_formal_predicate.py::test_pytest_exit_zero_with_skipped_node_creates_no_verified_candidate`
- Domain: `python -m pytest -q tests/unit/validation/test_formal_plan.py tests/unit/validation/test_formal_predicate.py tests/unit/validation/test_verified_candidate.py`
- Docker integration: `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_reference_formal_validation.py`
- Full: `python -m pytest -q`
- Expected: every forbidden status/error, collection drift, target transition, tool/environment/protected-file/policy drift, timeout, post-check mutation, and all-pass reference case is covered.

**Review gate:**
1. Spec compliance review checks all eight formal-success clauses and the phase/lifecycle transitions against §4.2 and §4.5.
2. Code quality review checks evidence completeness, ordered execution, deadline composition, immutable bindings, zero-container precheck failure, and one construction site for `VerifiedCandidateV1`.
3. Critical/Important findings or a skipped Docker formal test block final approval and persistence.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the skipped-node RED test.** Add the exact test with a valid exit code and one complete structured SKIP event.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because the formal predicate does not exist.
- [ ] **Step 3: Implement the minimum child-owned formal-validation composition.**

  ```python
  plan = build_formal_validation_plan(
      validation_manifest,
      current_candidate,
      final_diff,
  )
  evidence = execute_formal_plan(plan, executor)
  outcome = evaluate_formal_success(
      validation_manifest,
      current_candidate,
      plan,
      evidence,
  )
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0`, no verified candidate.
- [ ] **Step 5: Refactor without behavior change.** Separate plan construction, precheck integrity, evidence aggregation, formal predicate, and verified-candidate construction within `formal.py`.
- [ ] **Step 6: Run domain and Docker tests.** Run both domain and Docker integration commands. Expected: all predicate cases and the real reference formal run pass without skip.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Provide Task 21, SPEC §4.2.3/§4.5/§4.6/AC-20, execution traces, and verified-candidate digest vectors.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of complete predicates, timeout ordering, artifact binding, error feedback, and verified-object construction.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add formal success predicate`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 21 PR.

### Milestone 22: Workspace-isolated Repository Memory

**Status:** Not started

**Goal:** Persist only authorized structured memory, select it deterministically within strict limits, isolate it by workspace identity, and make user clearing effective for every future context.

**SPEC / FR / NFR / AC references:** SPEC §4.2.4 context memory; §4.7 memory write/selection/clear; §5.2; §5.4; §5.6; §7 MemoryEntry; §10.1 AC-14, AC-23, AC-26; §10.3 offline tests.

**Dependencies:** Exact child dependencies are canonical; Task 22.A additionally follows Task 15.E so v0005 is tested with actual v0001–v0004 predecessors.

**Blocks:** Tasks 24–25, 29, 31, and 38.

**Parallelization:** Parallel with Task 20 after Task 19; file ownership is disjoint.

**Recommended branch:** `codex/task-22-repository-memory`

**Recommended worktree:** `.worktrees/task-22-repository-memory`

**Files:**
- Create: `src/vespercode/storage/migrations/v0005_memory.py`
- Create: `src/vespercode/memory/entry.py`
- Create: `src/vespercode/memory/repository.py`
- Create: `src/vespercode/memory/selection.py`
- Test: `tests/unit/storage/test_memory_migration.py`
- Test: `tests/unit/memory/test_entry.py`
- Test: `tests/unit/memory/test_repository.py`
- Test: `tests/unit/memory/test_selection.py`
- Test: `tests/unit/memory/test_authorization.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 7.A control database and Task 7.C idempotency primitives; Task 10 workspace/Snapshot identity; Task 19.A structured check and Task 19.C fingerprint sources.
- Produces:
  - `MemoryKindV1`, `MemoryCreatorV1`, `MemorySourceV1`, and `MemoryEntryV1`
  - `MemoryEntrySequenceV1`, an immutable ordered tuple of zero or more `MemoryEntryV1` values
  - `MemoryRepository.create(command: CreateMemoryCommandV1) -> MemoryMutationResultV1`
  - `MemoryRepository.confirm(command: ConfirmProjectConventionV1) -> MemoryMutationResultV1`
  - `MemoryRepository.list(workspace_identity_digest: str) -> MemoryEntrySequenceV1`
  - `ClearMemoryCommandV1`, `MemoryClearResultV1`, and `MemoryClearService.clear(command: ClearMemoryCommandV1) -> MemoryClearResultV1`
  - `select_memory(query: MemorySelectionQueryV1, entries: MemoryEntrySequenceV1) -> MemorySelectionV1`

**Implementation points:**
- Permit `PROJECT_CONVENTION` only from explicit user creation/confirmation, `USER_DECISION` only from a real control-plane decision, and `RUN_SUMMARY`/`KNOWN_FAILURE` only from ended-run structured records.
- Reject model-originated generic writes, free-form model summaries, missing/forged sources, complete source files, credentials, authorization power, policy/config/Manifest overrides, and over-limit content.
- Store creator, structured source reference, current workspace identity, timestamps, untrusted marker, and a bounded summary; do not store full request/response, source file body, secret, or raw unbounded output.
- Query only the exact workspace identity. No path-name similarity, Git remote, profile, or user label can bridge workspace isolation.
- Select at most 20 entries and 16 KiB by frozen kind priority, most recent update, then stable id; calculate bytes from the exact context segment content.
- Current Snapshot/check evidence always supersedes conflicting memory. Memory remains untrusted context and cannot affect governance, approval, Grant, config, validation, or persistence predicates.
- Clear uses a transaction and tombstones/removes selection eligibility before success. Future selection cannot return a cleared entry; past audit/authorization facts remain unchanged.
- Expose a non-secret list/view projection suitable for the local WebUI.

**Implementation boundary:** This executable Task owns one workspace-isolated memory CRUD/selection behavior with closed creator/source rules. It cannot alter policy/config/approval/success, append audit events, read another workspace, or create general model-originated memory.

**Intentionally failing test:**

```python
def test_memory_never_crosses_workspace_identity(
    memory_repository: MemoryRepository,
    workspace_a: str,
    workspace_b: str,
) -> None:
    created = memory_repository.create(user_project_convention(workspace_a, "Use src/"))
    assert created.kind == "CREATED"
    assert memory_repository.list(workspace_b) == ()
    assert select_memory_for(workspace_b, memory_repository).entries == ()
```

**Verification:**
- Target: `python -m pytest -q tests/unit/memory/test_repository.py::test_memory_never_crosses_workspace_identity`
- Domain: `python -m pytest -q tests/unit/memory`
- Full: `python -m pytest -q`
- Expected: creator/source authorization, forbidden content, isolation, deterministic 20/16-KiB selection, conflict precedence, idempotency, and clear-effect tests pass.

**Review gate:**
1. Spec compliance review maps each memory kind/creator/source, selection rule, conflict rule, and clear behavior to §4.7.
2. Code quality review checks workspace keys, byte bounds, deterministic sort, transaction behavior, forbidden-field validation, and WebUI projection.
3. Critical/Important findings block context projection and memory routes.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the cross-workspace RED test.** Add the exact test using two unrelated fixed identity digests and one temporary SQLite database.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because the memory repository does not exist.
- [ ] **Step 3: Implement the minimum workspace-scoped query.**

  ```python
  def list(
      self,
      workspace_identity_digest: str,
  ) -> tuple[MemoryEntryV1, ...]:
      rows = self._db.fetch_all(
          "SELECT * FROM memory_entry "
          "WHERE workspace_identity_digest = ? AND cleared_at IS NULL",
          (workspace_identity_digest,),
      )
      return tuple(MemoryEntryV1.from_row(row) for row in rows)
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0` and no cross-workspace row.
- [ ] **Step 5: Refactor without behavior change.** Keep entry/source validation, persistence, and deterministic selection in the three planned modules.
- [ ] **Step 6: Run domain tests.** Run `python -m pytest -q tests/unit/memory`. Expected: all authorization, isolation, sorting, byte, clear, and forbidden-content cases pass.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Provide Task 22, SPEC §4.2.4/§4.7/AC-14/AC-23, schema rows, and selection vectors.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of SQL scoping, source authority, byte accounting, deterministic order, and tombstone semantics.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add workspace-isolated memory`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 22 PR.

### Milestone 23: Redacted Audit and User-facing Visibility Projection

**Execution notice:** Non-executable aggregate contract. Only Tasks 23.A–23.C are executable; they separately own redacted event storage, user-facing visibility projection, and retention/clear behavior.

**Status:** Not started

**Goal:** Record immutable, monotonically ordered, data-minimized control evidence and project it into understandable run state without exposing internal storage or restricted content.

**SPEC / FR / NFR / AC references:** SPEC §4.7 audit; §5.3–§5.6; §7 AuditEvent; §8.4 evidence separation; §10.1 AC-08, AC-13, AC-16, AC-21–AC-24, AC-27–AC-29; §10.3 evidence matrix.

**Dependencies:** Tasks 7.B, 7.C, and 22.A as assigned to exact executable children.

**Blocks:** Tasks 25–26, 28–29, 31, 36–37, and 38.

**Parallelization:** The pure projection/retention children remain parallel where their exact dependencies allow; Task 23.A follows the v0005 owner Task 22.A so v0006 can be tested with its actual predecessors. Late Task 7.D is downstream, not a prerequisite.

**Recommended branch:** `codex/task-23-audit-projection`

**Recommended worktree:** `.worktrees/task-23-audit-projection`

**Files:**
- Create: `src/vespercode/storage/migrations/v0006_audit.py`
- Create: `src/vespercode/audit/event.py`
- Create: `src/vespercode/audit/repository.py`
- Create: `src/vespercode/audit/projection.py`
- Create: `src/vespercode/audit/retention.py`
- Test: `tests/unit/storage/test_audit_migration.py`
- Test: `tests/unit/audit/test_event.py`
- Test: `tests/unit/audit/test_repository.py`
- Test: `tests/unit/audit/test_projection.py`
- Test: `tests/unit/audit/test_retention.py`
- Test: `tests/unit/audit/test_redaction.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Tasks 7.B–7.C Run/wait lifecycle and idempotency; Task 23.A itself owns v0006 audit DDL and monotonic sequence allocation.
- Produces:
  - `AuditEventV1(run_id: str, sequence: int, event_type: AuditEventTypeV1, redacted_payload: AuditPayloadV1, created_at: CanonicalTimestampV1)`
  - `AuditRepository.append(command: AppendAuditEventV1) -> AuditAppendResultV1`
  - `AuditRepository.list_run(run_id: str, page: AuditPageRequestV1) -> AuditPageV1`
  - `AuditRepository.clear_ended_run(command: ClearEndedRunAuditV1) -> AuditClearResultV1`
  - `build_run_visibility(run: RunRecordV1, waits: WaitContextSequenceV1, events: AuditEventSequenceV1) -> RunVisibilityV1`
  - `apply_audit_retention(now: CanonicalTimestampV1, repository: AuditRepository) -> AuditRetentionResultV1`

**Implementation points:**
- Define an allowlisted event/payload union for lifecycle, action digest/result, policy decision, approvals, Grants, authorization metadata, checks, recovery, and terminal evidence.
- Reject credential values, secret-derived values, complete file/request/response bodies, unbounded output, raw recovery backups, database rows, and unknown payload fields before append.
- Bound/redact paths, summaries, and error text with stable indicators; retain exact non-secret digests, ids, codes, statuses, and evidence references.
- Allocate one unique increasing sequence per run in the same transaction as append. Duplicate idempotency keys replay; conflicting reuse fails.
- Agent/model inputs cannot append, edit, reorder, or delete audit events.
- Project every formal status/phase/wait/recovery/terminal state into distinct user labels and stable reasons; never infer PASS from exit code, missing evidence, or a terminal-looking message.
- Retain ended-run audit for 30 days and permit explicit user clearing. Preserve unresolved recovery transaction/evidence references regardless of ordinary retention.
- Export separates evidence environment categories and never claims an external CI/deployment result that is absent from recorded evidence.

**Intentionally failing test:**

```python
def test_audit_rejects_complete_request_body_and_secret_fields(
    audit_repository: AuditRepository,
) -> None:
    command = append_event(
        event_type="LLM_CALL",
        payload={"request_body": "source text", "api_key": "not-a-real-secret"},
    )
    result = audit_repository.append(command)
    assert result.kind == "REJECTED"
    assert result.error_code == "AUDIT_STORE_FAILED"
    assert audit_repository.event_count == 0
```

**Verification:**
- Target: `python -m pytest -q tests/unit/audit/test_redaction.py::test_audit_rejects_complete_request_body_and_secret_fields`
- Domain: `python -m pytest -q tests/unit/audit`
- Full: `python -m pytest -q`
- Expected: payload closure, monotonic concurrency, replay/conflict, redaction bounds, status mapping, explicit clear, retention, and unresolved-recovery preservation tests pass.

**Review gate:**
1. Spec compliance review maps every required event class, prohibited content, status label, retention, and evidence-separation rule to §4.7 and NFR-OBS/PRIV.
2. Code quality review checks sequence transactions, allowlisted schemas, redaction at the boundary, pagination, retention queries, and projection isolation.
3. Critical/Important findings block local UI, persistence integration, and release evidence.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the forbidden-payload RED test.** Add the exact test with inert sentinel strings and assert the rejected command is never inserted.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because the audit event union and repository do not exist.
- [ ] **Step 3: Implement the minimum allowlisted append boundary.**

  ```python
  def append(self, command: AppendAuditEventV1) -> AuditAppendResultV1:
      payload = AuditPayloadAdapter.validate_python(command.payload)
      reject_prohibited_audit_content(payload)
      with self._db.immediate_transaction() as tx:
          sequence = tx.allocate_run_sequence(command.run_id)
          event = AuditEventV1.from_command(command, sequence, payload)
          tx.insert_audit_event(event)
      return AuditAppendResultV1.appended(event)
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0`, stable rejection, and zero rows.
- [ ] **Step 5: Refactor without behavior change.** Keep event schemas, transactional repository, user projection, and retention behavior in the four planned modules.
- [ ] **Step 6: Run domain tests.** Run `python -m pytest -q tests/unit/audit`. Expected: all content, order, projection, clear, retention, and recovery-preservation cases pass.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0` and sentinel values do not appear in output.
- [ ] **Step 9: Request spec compliance review.** Supply Task 23, SPEC §4.7/§5.3–§5.6/§10.3, event union, retention fixtures, and visibility snapshots.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of sequence allocation, data minimization, pagination, projection typing, and retention safety.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add redacted audit projection`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 23 PR.

### Milestone 24: ContextProjection and Structured Feedback

**Status:** Not started

**Goal:** Assemble the exact bounded, source-attributed turn context and consume deterministic structured feedback while preserving all mandatory protocol, candidate, target, and recent-failure facts.

**SPEC / FR / NFR / AC references:** SPEC §4.2.4–§4.2.6; §4.4.4 source segments; §4.5 structured feedback; §5.1–§5.2; §5.5 disclosure isolation; §7 FeedbackRecord; §10.1 AC-05, AC-13–AC-14, AC-17, AC-26, AC-28.

**Dependencies:** Exact child dependencies are canonical; Task 24.C additionally follows Task 25.B so v0008 can enforce `consumed_by_turn_id → agent_turns` against actual v0007.

**Blocks:** Tasks 25 and 31–32.

**Parallelization:** Parallel with Task 21 after Tasks 19 and 22; file ownership is disjoint.

**Recommended branch:** `codex/task-24-context-feedback`

**Recommended worktree:** `.worktrees/task-24-context-feedback`

**Files:**
- Create: `src/vespercode/storage/migrations/v0008_feedback.py`
- Create: `src/vespercode/loop/context_projection.py`
- Create: `src/vespercode/loop/feedback.py`
- Test: `tests/unit/storage/test_feedback_migration.py`
- Test: `tests/unit/loop/test_context_projection.py`
- Test: `tests/unit/loop/test_context_trimming.py`
- Test: `tests/unit/loop/test_context_sources.py`
- Test: `tests/unit/loop/test_feedback.py`
- Test: `tests/unit/loop/test_feedback_consumption.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 10 candidate/tree facts; Task 11.B path-bound tool results; Task 15 request segment/source contracts; Task 16.A mode-independent messages; Task 19.A checks and Task 19.C fingerprints; Task 22 selected memory.
- Produces:
  - `FeedbackRecordV1`, `FeedbackSelectionV1`, and `ContextProjectionV1`
  - `FeedbackRecordSequenceV1` and `FeedbackReferenceSequenceV1`, immutable ordered tuples of zero or more values of their named item types
  - `build_feedback(source: CheckResultV1 | ActionResultV1 | StableControlErrorV1, clock: ClockV1) -> FeedbackRecordSequenceV1`
  - `select_feedback(records: FeedbackRecordSequenceV1) -> FeedbackSelectionV1`
  - `build_context(inputs: ContextProjectionInputsV1) -> ContextProjectionV1 | ContextBudgetFailureV1`
  - `consume_feedback(turn_id: str, refs: FeedbackReferenceSequenceV1, repository: FeedbackRepositoryV1) -> FeedbackConsumptionResultV1`
  - `ContextProjectionV1.messages: RequestMessageSequenceV1` with frozen digest and canonical byte count

**Implementation points:**
- Assemble categories in this order: Harness protocol/action schema; frozen task/targets/budget; candidate/current FinalDiff/recent action; unconsumed feedback; selected memory; explicitly read file/tool fragments.
- Split multi-path tool facts into one path-bound segment per path plus a separate pathless control segment. Never downgrade file names, excerpts, or matches into a pathless tool result.
- Enforce category/path presence through Task 15, recompute each segment's content digest/byte count, and freeze all source facts with final trimmed content.
- Select at most 10 feedback records and 32 KiB by severity, creation time, then stable id. Preserve the newest failure classification, location, bounded summary, and evidence reference.
- Trim in the exact order: oldest memory, oldest successful action summaries, then non-recent file fragments. Never trim protocol/schema, targets, current candidate binding, or newest failure feedback.
- If mandatory content still exceeds 64 KiB, return `CONTEXT_BUDGET_EXCEEDED` without preparing a request, creating a turn, consuming feedback, charging a Grant, or calling an adapter.
- Context never includes credentials, local session tokens, recovery backup bytes, approval power, complete unrequested files, or raw unbounded check output.
- Bind selected feedback references into the next turn and consume them atomically at turn creation; one feedback record cannot be consumed by multiple turns.
- The same inputs, clock, IDs, and boundaries produce the same messages, source segments, trimming decisions, and digest.

**Implementation boundary:** This executable Task owns one deterministic context/structured-feedback projection and single-turn consumption behavior. It does not call the LLM, parse/dispatch actions, evaluate stopping, mutate candidate/workspace state, or bypass disclosure authorization.

**Intentionally failing test:**

```python
def test_trimming_never_removes_most_recent_failure_feedback(
    oversized_context_inputs: ContextProjectionInputsV1,
) -> None:
    projection = build_context(oversized_context_inputs)
    assert isinstance(projection, ContextProjectionV1)
    assert oversized_context_inputs.most_recent_failure.id in projection.feedback_refs
    assert projection.contains_category("HARNESS_PROTOCOL")
    assert projection.contains_current_candidate_binding is True
    assert projection.canonical_byte_count <= 65536
```

**Verification:**
- Target: `python -m pytest -q tests/unit/loop/test_context_trimming.py::test_trimming_never_removes_most_recent_failure_feedback`
- Domain: `python -m pytest -q tests/unit/loop/test_context_projection.py tests/unit/loop/test_context_trimming.py tests/unit/loop/test_context_sources.py tests/unit/loop/test_feedback.py tests/unit/loop/test_feedback_consumption.py`
- Full: `python -m pytest -q`
- Expected: order, path attribution, byte/digest checks, feedback bounds, trim priority, mandatory-overflow failure, single consumption, and deterministic replay pass.

**Review gate:**
1. Spec compliance review traces every projection section, source rule, feedback bound, trim priority, and pre-turn failure rule to §4.2.4 and §4.4.4.
2. Code quality review checks immutable assembly, byte measurement, stable ordering, path splitting, forbidden-source isolation, and feedback transaction races.
3. Critical/Important findings block the main loop and mechanism demo.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the mandatory-feedback RED test.** Add the exact test with bounded mandatory sections and removable memory/success/file fragments that exceed the first projection.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because projection/trimming does not exist.
- [ ] **Step 3: Implement the minimum ordered trimming loop.**

  ```python
  def build_context(
      inputs: ContextProjectionInputsV1,
  ) -> ContextProjectionV1 | ContextBudgetFailureV1:
      sections = assemble_ordered_sections(inputs)
      for trim_class in ("OLDEST_MEMORY", "OLDEST_SUCCESS", "NON_RECENT_FILE"):
          sections = trim_until_within_budget(sections, trim_class, 65536)
          if canonical_payload_bytes(sections) <= 65536:
              return freeze_projection(sections)
      return freeze_or_budget_failure(sections, 65536)
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0`; mandatory feedback remains and payload is within budget.
- [ ] **Step 5: Refactor without behavior change.** Keep projection/source construction separate from feedback creation/selection/consumption.
- [ ] **Step 6: Run domain tests.** Run the domain command. Expected: all ordering, attribution, trim, byte, isolation, and consumption cases pass.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Provide Task 24, SPEC §4.2.4–§4.2.6/§4.4.4/§4.5, source matrices, and trimming snapshots.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of ordering, canonical byte calculations, segment splitting, trim termination, and feedback races.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add bounded context feedback`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 24 PR.

### Milestone 25: Sequential Main Loop and Stopping Semantics

**Execution notice:** Non-executable aggregate contract. Only Tasks 25.A–25.G are executable; their expanded modules replace the aggregate two-file inventory below.

**Status:** Not started

**Goal:** Implement the repository-owned sequential context → authorize → one LLM call → parse → policy → dispatch → feedback → stop loop with exact counting, waits, budgets, progress, cancellation, and fail-closed lifecycle.

**SPEC / FR / NFR / AC references:** SPEC §3.2 dimensions; §4.2 in full; §4.4.4 call ordering; §4.5 feedback/formal transition; §5.1–§5.4; §7 AgentTurn/Action/Feedback; §9 LLM boundary; §10.1 AC-02, AC-05–AC-06, AC-13, AC-15–AC-18, AC-20, AC-27–AC-28, AC-31; Harness requirement prohibiting high-level agent executors.

**Dependencies:** Exact child dependencies span Tasks 7.B–7.C, 8.A–8.B, and the declared 11–24 children; Task 25.B additionally follows Task 23.A for v0007, while Task 25.D follows Task 24.C for v0009. Late Task 7.D is downstream.

**Blocks:** Tasks 29 and 31–32.

**Parallelization:** Parallel with Task 26 after Task 14 and Task 24; these tasks own disjoint files.

**Recommended branch:** `codex/task-25-main-loop`

**Recommended worktree:** `.worktrees/task-25-main-loop`

**Files:**
- Create: `src/vespercode/storage/migrations/v0007_agent_turns.py`
- Create: `src/vespercode/storage/migrations/v0009_actions.py`
- Create: `src/vespercode/loop/stopping.py`
- Create: `src/vespercode/loop/engine.py`
- Test: `tests/unit/storage/test_agent_turns_migration.py`
- Test: `tests/unit/storage/test_actions_migration.py`
- Test: `tests/unit/loop/test_stopping.py`
- Test: `tests/unit/loop/test_progress.py`
- Test: `tests/unit/loop/test_turn_counting.py`
- Test: `tests/unit/loop/test_main_loop.py`
- Test: `tests/unit/loop/test_main_loop_failures.py`
- Test: `tests/unit/loop/test_wait_lifecycle.py`
- Test: `tests/unit/loop/test_restart_behavior.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Tasks 7.B–7.C lifecycle/storage; Task 8 run/deadline; Task 11–13 tools/candidate/policy; Task 14–16 waits/authorization/adapters; Task 17 parser/dispatcher; Task 18–21 checks/Baseline/formal validation; Task 22–24 memory/audit/context/feedback.
- Produces:
  - `ProgressWindowV1` and `StopDecisionV1 = ContinueV1 | ValidateV1 | StopV1`
  - `ProgressEvaluator.evaluate(window: ProgressWindowV1, observation: ProgressObservationV1) -> ProgressDecisionV1`
  - `StopEvaluator.evaluate(state: RunLoopStateV1, evidence: LoopEvidenceV1, progress: ProgressDecisionV1, now: CanonicalTimestampV1) -> StopDecisionV1`
  - `TurnBoundary.begin(run_id: str, expected_state: RunStateV1) -> BeginTurnResultV1`
  - `TurnBoundary.record_call_started(run_id: str, turn_id: str, expected_revision: int) -> RecordCallStartedResultV1`
  - `TurnBoundary.close_turn(run_id: str, turn_id: str, outcome: TurnOutcomeV1, expected_revision: int) -> CloseTurnResultV1`
  - `CallOrchestrator.call_once(command: CallOnceV1) -> LLMCallResultV1`
  - `ActionPipeline.execute(response: ModelResponse, context: ActionPipelineContextV1) -> ActionStepResultV1`
  - `WaitController.enter(wait: WaitContextV1, now: CanonicalTimestampV1) -> WaitTransitionResultV1`
  - `WaitController.resume(wait: WaitContextV1, decision: WaitDecisionV1, now: CanonicalTimestampV1) -> WaitTransitionResultV1`
  - `WaitController.expire(wait: WaitContextV1, now: CanonicalTimestampV1) -> WaitTransitionResultV1`
  - `CancellationController.evaluate_safe_point(run: RunRecordV1, cancellation_requested: bool) -> CancellationDecisionV1`
  - `RestartGuard.inspect(run) -> RestartDispositionV1`
  - `AgentLoopEngine.step(run_id: str) -> LoopStepResultV1`
  - `AgentLoopEngine.run_until_boundary(run_id: str) -> LoopBoundaryResultV1`
  - `build_call_result(request: PreparedModelRequestV1, authorization_ref: OptionalAuthorizationRecordRefV1, outcome: AdapterOutcomeV1) -> LLMCallResultV1`

**Implementation points:**
- Permit one active turn per run and one adapter call per turn. Never use LangChain AgentExecutor, AutoGen, CrewAI, LlamaIndex Agent, OpenAI Agents SDK runner, or a host coding-agent loop.
- Build context first. For Mock, freeze/validate the concrete request/profile/script/adapter. For OpenAI, obtain/reuse Grant, freeze the request, validate exact sources and endpoint/adapter target, then re-probe Windows Credential Manager and call `get_for_call("OPENAI")` before any Grant charge or authorization record.
- If the per-call credential is missing/cleared or the backend is unsafe, stop the current Run with `CREDENTIAL_MISSING` or `CREDENTIAL_BACKEND_UNSAFE`; do not charge the Grant, create a durable record, increment turn/call, call transport, or automatically retry. PREFLIGHT readiness is never reused as proof.
- Only after the per-call credential check succeeds may the gate atomically charge the Grant and persist the derived authorization record. Only when that transaction succeeds, the exact request remains ready, budgets remain, and the adapter is about to be called may it atomically create the turn and increment turn/call.
- A caught control-plane failure after that boundary but before adapter call records `NOT_ATTEMPTED`; adapter error or invalid output consumes the count; no path retries or reuses the turn.
- Parse and bind one action, then enforce candidate/path/phase/policy/dispatch order. Publish one structured result and derive bounded feedback.
- Bind and consume selected feedback refs at the next turn boundary. A completion action only transitions to trusted formal validation; failed formal validation creates feedback and a new loop entry.
- Compute repeated-action count from identical semantic action plus semantic result on the same candidate. Stop on the third consecutive repeat.
- Count progress only for candidate digest change, a new semantic check result on the current candidate, or formal-validation entry. Stop after six consecutive no-progress turns.
- Enforce at most two consecutive invalid model outputs, explicit configured/hard turn and call limits, every sub-timeout, minimum remaining run deadline, and user-wait expiry before the next side effect.
- Observe cancel at action boundaries, wait state, and before the first persistence replacement. Once persistence may have replaced a file, defer to Task 26.
- `StopEvaluator` can only continue, request validation, or stop; it cannot publish `SUCCEEDED`. Only Task 26 persistence/recovery can publish formal success.
- On process restart outside persistence/recovery, stop with `PROCESS_RESTARTED_DURING_RUN`; do not restore waits/turns or resend requests.

**Intentionally failing test:**

```python
def test_failed_check_feedback_changes_the_next_mock_action(
    loop_harness: DeterministicLoopHarness,
) -> None:
    trace = loop_harness.run(
        script_id="failure-then-correction-v1",
        injected_check_results=(failed_target_check("assert 1 == 2"),),
    )
    assert trace.actions[0].action_type == "apply_candidate_patch"
    assert trace.actions[1].action_type == "run_check"
    assert trace.actions[2].action_type == "apply_candidate_patch"
    assert trace.actions[2].semantic_digest != trace.actions[0].semantic_digest
    assert trace.turns[2].consumed_feedback_refs == (trace.feedback[0].id,)
```

**Verification:**
- Target: `python -m pytest -q tests/unit/loop/test_main_loop.py::test_failed_check_feedback_changes_the_next_mock_action`
- Domain: `python -m pytest -q tests/unit/loop/test_stopping.py tests/unit/loop/test_progress.py tests/unit/loop/test_turn_counting.py tests/unit/loop/test_main_loop.py tests/unit/loop/test_main_loop_failures.py tests/unit/loop/test_wait_lifecycle.py tests/unit/loop/test_restart_behavior.py`
- Full: `python -m pytest -q`
- Expected: sequential trace, exact count boundary, Mock/OpenAI authorization differences, cleared/unsafe per-call credential zero-side-effect stops, invalid-output limit, repeated/no-progress, all timeouts, waits, cancellation, restart, feedback, validation transition, and no-false-success tests pass offline.

**Review gate:**
1. Spec compliance review traces every §4.2 behavior, timeout row, credential/Grant/record/count boundary, lifecycle transition, and §4.4.4 real/Mock call order to code/tests.
2. Code quality review checks state-machine clarity, single active turn, transaction boundaries, injected clocks/IDs/ports, exception paths, semantic counters, and absence of hidden retries.
3. Critical/Important findings block all workflow UI and end-to-end demonstrations.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the feedback-change RED test.** Add the exact deterministic script, injected check result, and action/feedback assertions.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because the repository-owned loop engine does not exist.
- [ ] **Step 3: Implement the minimum one-step sequential loop.**

  ```python
  def step(self, run_id: str) -> LoopStepResultV1:
      inputs = self.load_step_inputs(run_id)
      restart = self.restart_guard.inspect(inputs.run)
      cancellation = self.cancellation_controller.evaluate_safe_point(
          inputs.run,
          inputs.cancellation_requested,
      )
      if self.is_pre_turn_stop(restart, cancellation):
          return self.compose_pre_turn_boundary(inputs, restart, cancellation)
      projection = self.context_builder.build(inputs.loop_state)
      turn = self.turn_boundary.begin(run_id, inputs.expected_state)
      call_result = self.call_orchestrator.call_once(
          self.compose_call_once(inputs, projection, turn)
      )
      action_step = self.action_pipeline.execute(
          inputs.model_response_for(call_result),
          inputs.action_pipeline_context,
      )
      progress = self.progress_evaluator.evaluate(
          inputs.progress_window,
          inputs.progress_observation_for(action_step),
      )
      decision = self.stop_evaluator.evaluate(
          inputs.loop_state,
          inputs.loop_evidence_for(action_step),
          progress,
          inputs.now,
      )
      closed = self.turn_boundary.close_turn(
          run_id,
          turn.turn_id,
          self.compose_turn_outcome(call_result, action_step, decision),
          turn.revision,
      )
      return self.compose_loop_step_result(action_step, decision, closed)
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0` with one-time feedback consumption, a changed correction action, and a closed `ContinueV1 | ValidateV1 | StopV1` decision persisted only by the owning turn/lifecycle boundary.
- [ ] **Step 5: Refactor without behavior change.** Keep pure stopping/progress rules separate from the sequential orchestration engine; leave domain work behind injected ports.
- [ ] **Step 6: Run domain tests.** Run the domain command. Expected: all count, per-call credential removal/backend-change, Grant/record ordering, call, action, feedback, progress, wait, timeout, cancel, restart, and stop cases pass; failed credential rechecks have zero charged bytes, record, count, and transport increments.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0` with Mock/Stub adapters and no network or Docker.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Provide Task 25, complete SPEC §4.2/§4.4.4, state-transition traces, count tables, and failure injections.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of loop ownership, transaction/call boundaries, dependency directions, retry absence, counter identities, and restart behavior.
- [ ] **Step 12: Close quality findings.** Close every Critical/Important issue, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add sequential agent loop`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 25 PR.

### Milestone 26: Production Persistence and Three-value Recovery

**Execution notice:** Non-executable aggregate contract. Only Tasks 26.A–26.C are executable; their recovery preview/apply split replaces the aggregate `recovery.py` inventory below.

**Status:** Not started

**Goal:** Write the exact approved 1–3-file FinalDiff through durable per-path evidence and recover every interruption as only `COMMITTED`, `ROLLED_BACK`, or `UNRESOLVED`.

**SPEC / FR / NFR / AC references:** SPEC §4.2.6–§4.2.7 persistence cancellation/lifecycle; §4.4.2 approval; §4.6 in full; §5.2; §5.5–§5.6; §7 persistence rows; §8.2 recovery CLI; §10.1 AC-03, AC-07, AC-21–AC-22, AC-26–AC-29, AC-31; §10.3 recovery fault injection.

**Dependencies:** Task 3 GO and exact children under Tasks 7.B–7.C, 9, 12, 14, 21, and 23 as listed in the canonical DAG. Late Task 7.D depends on Tasks 26.A and 26.C and is not a persistence prerequisite.

**Blocks:** Tasks 29, 31, 33–37, and 38.

**Parallelization:** Parallel with Task 25 after Task 14 and Task 21; file ownership is disjoint.

**Recommended branch:** `codex/task-26-persistence-recovery`

**Recommended worktree:** `.worktrees/task-26-persistence-recovery`

**Files:**
- Create: `src/vespercode/storage/migrations/v0011_persistence.py`
- Create: `src/vespercode/storage/migrations/v0012_recovery.py`
- Create: `src/vespercode/persistence/path_record.py`
- Create: `src/vespercode/persistence/transaction.py`
- Create: `src/vespercode/persistence/artifacts.py`
- Create: `src/vespercode/persistence/writeback.py`
- Create: `src/vespercode/persistence/recovery.py`
- Test: `tests/unit/storage/test_persistence_migration.py`
- Test: `tests/unit/storage/test_recovery_migration.py`
- Test: `tests/unit/persistence/test_path_record.py`
- Test: `tests/unit/persistence/test_transaction.py`
- Test: `tests/unit/persistence/test_writeback_preconditions.py`
- Test: `tests/unit/persistence/test_recovery_decision.py`
- Test: `tests/fault_injection/persistence/test_writeback_fault_matrix.py`
- Test: `tests/fault_injection/persistence/test_deadline_faults.py`
- Test: `tests/fault_injection/persistence/test_external_change_faults.py`
- Test: `tests/integration/windows/test_persistence_acl_and_identity.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Tasks 7.B–7.C lifecycle/storage; Task 9 workspace lease/final-object identity; Task 12 FinalDiff/postimages/policy; Task 14 consumed approval authorization; Task 21 VerifiedCandidate/formal evidence; Task 23 audit append.
- Produces:
  - `PreimageV1`, `PostimageV1`, `PersistencePathRecordV1`, and `PersistenceTransactionV1`
  - `PersistenceCommandFactoryV1.for_approved_run(run_id: str, approval_id: str, event_id: str) -> PersistVerifiedCandidateV1`
  - `PersistenceCoordinator.persist(command: PersistVerifiedCandidateV1) -> PersistenceResultV1`
  - `RecoveryService.preview(workspace: WorkspaceIdentityV1) -> RecoveryPreviewV1`
  - `RecoveryService.apply(command: ApplyRecoveryV1) -> RecoveryResultV1`
  - `RecoveryDispositionV1 = Literal["COMMITTED","ROLLED_BACK","UNRESOLVED"]`
  - `has_unresolved_transaction(workspace_identity_digest: str) -> bool`

**Implementation points:**
- Before consuming approval, recompute FinalDiff, enforce 1–3 non-empty entries and at most one create, verify every editable path, and prove candidate/Manifest/evidence/workspace/config/policy/profile identity.
- `PersistenceCommandFactoryV1` loads the verified candidate, canonical FinalDiff, Manifest/evidence, workspace preimage, lease/config/policy/profile bindings, and approval by server-side ids. It rejects a non-PERSISTENCE Run or non-pending/mismatched approval and accepts no candidate bytes, diff, evidence, workspace path, or policy field from WebUI form data.
- Build typed records in canonical path sequence: CREATE has `ABSENT` and no backup; REPLACE has `PRESENT` and a verified backup reference. Reject any other combination before `PREPARED`.
- Place transaction log, backups, and evidence only under the current user's local application-data root. Verify ACL permits the current user and required OS principals before writing source bytes.
- Persist `PREPARED` and every path record before workspace writes. Recheck lease, all preimages/object identities, approved entries, and policy immediately before the first write; failure leaves all paths `NOT_STARTED`.
- Move to `WRITING` before the first replacement. For each path, recheck lease/preimage/object, write and flush a same-directory temporary file, synchronize directory metadata where supported, atomically replace, observe postimage/object, then persist `REPLACED` and `VERIFIED` evidence.
- Validate all expected postimages and every untouched tracked file before `COMMITTED`. Only then publish Run `SUCCEEDED`.
- Check `run_deadline` before every authoritative write. Expiry before the first write produces zero writes, `ROLLED_BACK`, and `STOPPED`; expiry after any path may have changed produces no more workspace writes, `UNRESOLVED`, and `RECOVERY_REQUIRED`.
- Treat durable path state as lagging evidence, not current truth. Recovery rereads raw bytes, text metadata, object identity, backups, and transaction evidence before deciding.
- Preview is strictly read-only for workspace, transaction, backups, and audit. Apply reacquires the same workspace lease and requires explicit confirmation.
- Recovery returns COMMITTED only when every postimage is proven, ROLLED_BACK only when every preimage is proven, otherwise UNRESOLVED. It has no force-success/ignore option.
- Delete a CREATE to restore `ABSENT` only if its current bytes exactly equal this transaction's postimage and its object remains supported. External change, link/special object, or unknown identity is never deleted.
- Keep unresolved logs/backups and block new runs. After a terminal disposition, retain digest evidence and remove body backups only under the frozen retention policy.

**Intentionally failing test:**

```python
def test_deadline_after_first_replacement_stops_all_further_writes(
    persistence_harness: PersistenceFaultHarness,
    three_path_transaction: PersistVerifiedCandidateV1,
) -> None:
    result = persistence_harness.run(
        three_path_transaction,
        expire_deadline_after="PATH_1_REPLACE",
    )
    assert result.transaction_state == "UNRESOLVED"
    assert result.run_status == "RECOVERY_REQUIRED"
    assert result.workspace_write_count == 1
    assert result.path_records[1].durable_state == "NOT_STARTED"
    assert result.path_records[2].durable_state == "NOT_STARTED"
```

**Verification:**
- Target: `python -m pytest -q tests/fault_injection/persistence/test_deadline_faults.py::test_deadline_after_first_replacement_stops_all_further_writes`
- Domain: `python -m pytest -q tests/unit/persistence tests/fault_injection/persistence`
- Windows integration: `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_persistence_acl_and_identity.py`
- Full: `python -m pytest -q`
- Expected: complete 1–3-file fault matrix, state-before/after crash, mixed create/replace, all deadline points, pre/post mismatch, ACL, external change, preview/apply, stale state correction, and safe cleanup pass.

**Review gate:**
1. Spec compliance review maps every §4.6 precondition, transition, deadline branch, recovery disposition, and admission block to test evidence and Task 3 GO findings.
2. Code quality review checks durable ordering, fsync/replace semantics, object/lease rechecks, ACL enforcement, fault-injection completeness, deletion safety, and transaction recovery.
3. Critical/Important findings or a missing fault point block local workflows, E2E, and distribution.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the post-replacement deadline RED test.** Add the exact test with three path records and a deterministic clock/fault hook after the first atomic replace.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because the production persistence coordinator does not exist.
- [ ] **Step 3: Implement the minimum deadline fail-closed branch.**

  ```python
  def require_write_deadline(
      transaction: PersistenceTransactionV1,
      clock: ClockV1,
  ) -> None:
      if clock.now() < transaction.run_deadline:
          return
      if all(record.durable_state == "NOT_STARTED" for record in transaction.path_records):
          raise DeadlineBeforeWriteV1()
      raise PersistenceUncertainV1("PERSISTENCE_UNCERTAIN")
  ```

  The coordinator catches the second outcome by persisting `UNRESOLVED` without another workspace write.
- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0`, exactly one write, and `RECOVERY_REQUIRED`.
- [ ] **Step 5: Refactor without behavior change.** Keep record schemas, state transitions, ACL artifacts, writeback orchestration, and recovery classification in the five planned modules.
- [ ] **Step 6: Run domain and Windows tests.** Run both domain and Windows integration commands. Expected: every required fault point executes and passes without skip.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`; real Windows tests remain excluded.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0` and backup bodies are not printed.
- [ ] **Step 9: Request spec compliance review.** Provide Task 26, Task 3 GO matrix, SPEC §4.6/AC-22/AC-29, transaction traces, and Windows evidence.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of durable state order, crash windows, file handles, ACLs, flush/replace, deadlines, recovery deletion, and cleanup.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add recoverable writeback transaction`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 26 PR.

### Milestone 27: Windows Credential Manager Lifecycle

**Execution notice:** Non-executable aggregate contract. Only Tasks 27.A–27.B are executable; they separately own the pure credential lifecycle boundary and the real Windows Credential Manager adapter/proof.

**Status:** Not started

**Goal:** Provide hidden first-run OpenAI credential set/status/update/clear through a verified Windows Credential Manager backend with no secret disclosure or fallback storage.

**SPEC / FR / NFR / AC references:** SPEC §4.1 OpenAI readiness; §4.8 in full; §5.5 credential threat; §5.6; §8.1; §8.2; §10.1 AC-08, AC-13, AC-15, AC-24, AC-28; §10.3 Windows integration.

**Dependencies:** Tasks 4–6.

**Blocks:** Tasks 16, 28–29, 31, 33, 35–37, and 38.

**Parallelization:** Parallel with Tasks 8, 15, 23, and 30 after Task 6; file ownership is disjoint.

**Recommended branch:** `codex/task-27-wincred-lifecycle`

**Recommended worktree:** `.worktrees/task-27-wincred-lifecycle`

**Files:**
- Create: `src/vespercode/credentials/port.py`
- Create: `src/vespercode/credentials/wincred_store.py`
- Create: `src/vespercode/credentials/service.py`
- Test: `tests/unit/credentials/test_service.py`
- Test: `tests/unit/credentials/test_status.py`
- Test: `tests/unit/credentials/test_backend_rejection.py`
- Test: `tests/unit/credentials/test_call_lookup.py`
- Test: `tests/unit/credentials/test_log_redaction.py`
- Test: `tests/integration/windows/test_wincred_smoke.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 4 bounded errors/timestamps and credential scanner; Task 5 closed result contracts; Task 6 sole OpenAI provider/profile readiness.
- Produces:
  - `SecretCredentialV1` non-serializable/redacted wrapper
  - `CredentialStorePortV1.set(provider: Literal["OPENAI"], secret: SecretCredentialV1) -> CredentialStoreMutationV1`
  - `CredentialStorePortV1.get_for_call(provider: Literal["OPENAI"]) -> SecretCredentialV1 | CredentialMissingV1`
  - `CredentialStorePortV1.status(provider: Literal["OPENAI"]) -> CredentialStatusV1`
  - `CredentialStorePortV1.clear(provider: Literal["OPENAI"]) -> CredentialStoreMutationV1`
  - `WindowsCredentialManagerStore.probe_backend() -> CredentialBackendProbeV1`
  - `CredentialService.set/status/update/clear` with closed public results
  - `CredentialService.get_for_call(provider: Literal["OPENAI"]) -> SecretCredentialV1 | CredentialErrorV1`

**Implementation points:**
- Support only OPENAI and one versioned Credential Manager target name. Reject empty/invalid input before touching the store.
- Accept a secret only from an in-memory WebUI password field service call; expose no CLI argument, URL, environment import, config file, log, audit payload, SQLite field, or printable object path.
- At startup and before/after each mutation, prove the active backend is Windows Credential Manager and perform capability/status checks without revealing stored bytes.
- Before every `get_for_call("OPENAI")`, independently re-probe the actual backend and read the current entry from Windows Credential Manager. Never satisfy a call from PREFLIGHT status or a cached secret.
- Reject plaintext-file, environment, dummy, fail, or unknown keyring backends as `CREDENTIAL_BACKEND_UNSAFE`; never attempt fallback storage.
- Status exposes only configured boolean, provider, and updated timestamp. It omits secret, length, prefix/suffix, hash, and any guessable derivative.
- Update overwrites the old entry only after backend verification and returns explicit success/failure. Clear reports a real deletion error and cannot claim absence after a failed delete.
- Map backend exceptions to stable codes while redacting messages and object representations.
- The Windows smoke creates a generated non-production test secret, verifies only configured state, clears it in `finally`, and proves the final state is unconfigured.
- Unit and Windows tests clear the credential after a successful readiness/status check, then prove the next `get_for_call` returns `CREDENTIAL_MISSING`; switching the fake backend after readiness returns `CREDENTIAL_BACKEND_UNSAFE`.

**Intentionally failing test:**

```python
def test_credential_status_never_contains_secret_or_derivative(
    credential_service: CredentialService,
    fake_safe_store: FakeCredentialStore,
) -> None:
    secret = SecretCredentialV1.from_hidden_input("test-sentinel-value")
    assert credential_service.set("OPENAI", secret).kind == "STORED"
    status = credential_service.status("OPENAI")
    rendered = status.model_dump_json()
    assert status.configured is True
    assert "test-sentinel-value" not in rendered
    assert "length" not in rendered
    assert "digest" not in rendered
```

**Verification:**
- Target: `python -m pytest -q tests/unit/credentials/test_status.py::test_credential_status_never_contains_secret_or_derivative`
- Domain: `python -m pytest -q tests/unit/credentials`
- Windows integration: `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_wincred_smoke.py`
- Full: `python -m pytest -q`
- Expected: safe/unsafe backend, set/status/overwrite/clear failure, per-call re-probe, cleared-after-readiness lookup, missing credential, exception/log redaction, and real Credential Manager cleanup tests pass.

**Review gate:**
1. Spec compliance review traces every §4.8 and §8.1 behavior, storage prohibition, readiness use, per-real-call lookup, and Windows smoke cleanup.
2. Code quality review checks backend identity detection, secret wrapper lifetime/repr, exception redaction, overwrite/delete semantics, and test cleanup.
3. Critical/Important findings or a skipped Windows credential smoke block OpenAI mode and release.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the non-revealing-status RED test.** Add the exact test with an inert sentinel and a fake store that records only call counts.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because the credential service does not exist.
- [ ] **Step 3: Implement the minimum non-revealing status projection.**

  ```python
  def status(self, provider: Literal["OPENAI"]) -> CredentialStatusV1:
      probe = self._store.probe_backend()
      require_safe_windows_backend(probe)
      record = self._store.status(provider)
      return CredentialStatusV1(
          schema_version=1,
          provider=provider,
          configured=record.configured,
          updated_at=record.updated_at,
      )
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0` with no secret-derived field.
- [ ] **Step 5: Refactor without behavior change.** Keep the secret/store protocol, WinCred adapter, and public lifecycle service in the three planned modules.
- [ ] **Step 6: Run domain and Windows tests.** Run both domain and Windows integration commands. Expected: all unit cases, cleared-after-readiness and unsafe-backend call lookups, and the real set/status/get-for-call/clear smoke pass without skip and leave no test credential.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0` and sentinel values are absent from output.
- [ ] **Step 9: Request spec compliance review.** Provide Task 27, SPEC §4.8/§5.5/§8.1/AC-08, redacted call traces, and final cleared Windows status.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of secret ownership, backend probe precision, exception paths, overwrite atomicity, and cleanup guarantees.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add safe Windows credential lifecycle`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 27 PR.

### Milestone 28: Loopback WebUI Security and Application Shell

**Execution notice:** Non-executable aggregate contract. Only Tasks 28.A–28.B are executable.

**Status:** Not started

**Goal:** Compose a formal local FastAPI application that is reachable only on loopback, rejects hostile Host/Origin/CSRF requests, renders untrusted text safely, and exposes unambiguous lifecycle navigation.

**SPEC / FR / NFR / AC references:** SPEC §4.9 local mode and tests; §5.3; §5.5 WebUI threat; §8.2 `vespercode serve`; §9 UI choice; §10.1 AC-08, AC-11, AC-13, AC-16, AC-24; course WebUI deliverable.

**Dependencies:** Exact executable children under Tasks 7.B–7.C, 8, 23, and 27 as listed in the canonical DAG; Task 38.F is the only runtime consumer of late Task 7.D, while Task 37.B separately consumes its final process/evidence record.

**Blocks:** Tasks 29, 31, 33, 35–37, and 38.

**Parallelization:** Parallel with Tasks 9 and 16 after Tasks 8, 23, and 27; file ownership is disjoint.

**Recommended branch:** `codex/task-28-local-web-security`

**Recommended worktree:** `.worktrees/task-28-local-web-security`

**Files:**
- Create: `src/vespercode/web/security.py`
- Create: `src/vespercode/web/app.py`
- Create: `src/vespercode/web/templates/base.html`
- Create: `src/vespercode/web/templates/home.html`
- Create: `src/vespercode/web/templates/components/status_badge.html`
- Create: `src/vespercode/web/static/htmx.min.js`
- Create: `src/vespercode/cli.py`
- Test: `tests/web/test_security.py`
- Test: `tests/web/test_html_escaping.py`
- Test: `tests/web/test_status_labels.py`
- Test: `tests/web/test_app_composition.py`
- Test: `tests/unit/test_cli.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 7.B Run records; Task 8 run creation contract; Task 23 `RunVisibilityV1`; Task 27 credential service port.
- Produces:
  - `LocalShellPortsV1.list_recent_runs() -> RunVisibilitySequenceV1`
  - `LocalShellPortsV1.credential_status() -> CredentialStatusV1`
  - `LocalRouteInstallerV1.install(app: FastAPI) -> None`
  - `create_local_app(shell_ports: LocalShellPortsV1, security: LocalWebSecurityConfigV1, route_installers: LocalRouteInstallerSequenceV1) -> FastAPI`
  - `LocalSessionManager.create() -> LocalSessionV1`
  - `verify_local_request(request: Request, session: LocalSessionV1) -> LocalRequestAuthorizationV1`
  - `render_status_badge(visibility: RunVisibilityV1) -> Markup`
  - CLI commands `vespercode --help` and `vespercode serve --host 127.0.0.1 --port 8765`

**Implementation points:**
- Permit serve binding only to `127.0.0.1`; reject `0.0.0.0`, LAN addresses, hostnames, Unix sockets, and user-configured remote binding in formal mode.
- Generate a cryptographically random local session token at process start, store it only in memory/secure cookie context, and never include it in URLs or logs.
- Accept only the configured loopback Host/port and same-origin Origin. Apply CSRF tokens to every state-changing form/HTMX request with constant-time comparison.
- Set CSP, frame denial, MIME sniffing prevention, referrer policy, restrictive permissions policy, secure cache behavior, and HttpOnly/SameSite cookie attributes appropriate to loopback HTTP.
- Render all repository/model/error text through autoescaping and explicit text nodes. Never mark untrusted HTML safe.
- Vendor one pinned HTMX asset with recorded digest; use no runtime CDN, analytics, telemetry, or extra network request.
- Show distinct labels for CREATED, every RUNNING phase, WAITING_USER, RECOVERY_REQUIRED, SUCCEEDED, and STOPPED; include stable user-facing reason/next action without internal database fields.
- Compose only typed service ports and an explicit ordered tuple of route installers. Route handlers cannot import SQLite internals, secret store internals, Docker client, or recovery backup bodies; Tasks 29 and 38 do not modify `app.py`.
- `vespercode serve` validates startup profiles, storage, credential-backend capability, and local security before listening; secrets are not CLI parameters.
- During implementation review, invoke `ui-ux-pro-max` for interaction/accessibility and safe-rendering review, then record accepted/rejected recommendations in `AGENT_LOG.md`.

**Intentionally failing test:**

```python
def test_state_change_rejects_non_loopback_origin(
    local_web_client: TestClient,
    valid_csrf_headers: dict[str, str],
) -> None:
    response = local_web_client.post(
        "/runs",
        headers={**valid_csrf_headers, "Origin": "https://attacker.example"},
        data=valid_run_form_data(),
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "ORIGIN_REJECTED"
```

**Verification:**
- Target: `python -m pytest -q tests/web/test_security.py::test_state_change_rejects_non_loopback_origin`
- Domain: `python -m pytest -q tests/web/test_security.py tests/web/test_html_escaping.py tests/web/test_status_labels.py tests/web/test_app_composition.py tests/unit/test_cli.py`
- Full: `python -m pytest -q`
- Expected: binding, Host/Origin/CSRF, session, headers, escaping, status labels, capability composition, pinned asset, startup, and CLI argument tests pass offline.

**Review gate:**
1. Spec compliance review traces every local-mode capability/security/status requirement and confirms no public binding or secret argument.
2. Code quality review plus `ui-ux-pro-max` review checks middleware order, token lifecycle, headers, templates, accessibility, keyboard/focus/error behavior, and port boundaries.
3. Critical/Important findings block workflow pages and package smoke.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the hostile-Origin RED test.** Add the exact test with a valid session and CSRF token so Origin is the only failing condition.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because the local app/security middleware does not exist.
- [ ] **Step 3: Implement the minimum same-origin guard.**

  ```python
  def require_same_origin(request: Request, expected_origin: str) -> None:
      origin = request.headers.get("origin")
      if origin != expected_origin:
          raise LocalWebSecurityError("ORIGIN_REJECTED", status_code=403)
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0` and no run creation port call.
- [ ] **Step 5: Refactor without behavior change.** Keep security/session checks, app composition, templates/assets, and CLI startup separated by their planned files.
- [ ] **Step 6: Run domain tests.** Run the domain command. Expected: all security, rendering, status, composition, and CLI cases pass.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Provide Task 28, SPEC §4.9/§5.3/§5.5/§8.2, route inventory, headers, binding tests, and screenshots from local browser verification.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rerun Steps 6–8, open the app in a browser, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality and UI/UX review.** Invoke `ui-ux-pro-max`; require inspection of middleware, templates, accessibility, focus/errors, untrusted text, status comprehension, and dependency registration.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important code and UI findings, rerun Steps 6–8, recheck the browser flows, and obtain passing re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add secure loopback WebUI shell`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 28 PR.

### Milestone 29: Local Run and Governance WebUI Workflows

**Execution notice:** Non-executable aggregate contract. Only Tasks 29.A–29.C are executable; their workflow/route split replaces the aggregate file inventory below.

**Status:** Not started

**Goal:** Expose run creation/status, disclosure decisions, cancellation, exact diff review, and final writeback approval through typed, safe, state-aware pages without bypassing domain rules.

**SPEC / FR / NFR / AC references:** SPEC §2 US-01, US-03–US-06, US-08; §4.2.7 waits; §4.4.2–§4.4.3 UI disclosures; §4.6 writeback review; §4.9 local run capabilities; §5.3–§5.5; §8.2; §10.1 AC-03, AC-06–AC-07, AC-13, AC-15–AC-16, AC-21, AC-27–AC-28, AC-31.

**Dependencies:** Tasks 8, 14–16, 21, 23, 25–26, and 28.

**Blocks:** Tasks 31, 33, 35–38.

**Parallelization:** Parallel with Task 32 after Tasks 25–28; both own disjoint files. Task 38 starts only after this installer's interface and PR are merged.

**Recommended branch:** `codex/task-29-local-web-workflows`

**Recommended worktree:** `.worktrees/task-29-local-web-workflows`

**Files:**
- Create: `src/vespercode/web/run_workflows.py`
- Create: `src/vespercode/web/routes_runs.py`
- Create: `src/vespercode/web/routes_disclosure.py`
- Create: `src/vespercode/web/templates/run_create.html`
- Create: `src/vespercode/web/templates/run_detail.html`
- Create: `src/vespercode/web/templates/disclosure_wait.html`
- Test: `tests/web/test_run_workflow.py`
- Test: `tests/web/test_disclosure_workflow.py`
- Test: `tests/web/test_writeback_workflow.py`
- Test: `tests/web/test_accessibility.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 8 `ValidateRunRequestV1`, validation/creation/admission services; Task 14 `DecideFinalWritebackV1` and `FinalWritebackDecisionServiceV1`; Task 15 `DecideDisclosureGrantV1` and `DisclosureDecisionServiceV1`; Task 16 endpoint display facts; Task 21 formal evidence; Task 23 `RunVisibilityV1`; Task 25 engine/cancel; Task 26 `PersistenceCommandFactoryV1` and `PersistenceCoordinator`; Task 28 security/app shell and `LocalRouteInstallerV1`.
- Produces:
  - Task 29.A child-owned `RunCreationWorkflowPortV1`, `RunVisibilityWorkflowPortV1`, `RunCancellationWorkflowPortV1`, their closed result unions, and `RunLifecycleRouteInstallerV1`
  - `DisclosureDecisionWorkflowPortV1.decide(command: DecideDisclosureGrantV1) -> DisclosureDecisionResultV1`
  - `AuthorizationSummaryV1`, `build_authorization_summary(subject: DisclosureGrantSubjectV1, endpoint: OpenAIEndpointV1) -> AuthorizationSummaryV1`, `render_authorization_summary(summary: AuthorizationSummaryV1) -> Markup`, and `DisclosureRouteInstallerV1.install(app: FastAPI) -> None`
  - Task 29.C child-owned `FinalWritebackWorkflowPortV1`, `ProductionFinalWritebackWorkflowV1`, `WritebackReviewV1`, `RunGovernanceWorkflowPortsV1`, and `RunGovernanceRouteInstallerV1`
  - The Task 29.A closed run-creation result union has `RUNNING | CONFIG_INVALID | STOPPED` discriminators; only `RUNNING` and `STOPPED` contain a server-created run id, while `CONFIG_INVALID` proves no Run was created
  - The Task 29.C child-owned `FinalWritebackWorkflowResultV1` is a closed union with exact `PERSISTED | REJECTED | EXPIRED | STALE | ALREADY_DECIDED | STOPPED | RECOVERY_REQUIRED` discriminators and the applicable Task 14/26 typed result, never a free-form exception
  - closed route form adapters that accept only visible request fields, exact wait bindings, `APPROVE|REJECT`, CSRF/session data handled by Task 28, and an idempotency event id; Task 14/15 services obtain `decided_at` from their injected `ClockV1`
  - `AuthorizationSummaryV1`, `RenderedFinalDiffV1`, `FormalEvidenceProjectionV1`, and `WritebackReviewV1` as view-only, escaped projections with no domain mutation method
  - server-rendered pages for every formal run state and governance decision
  - Rendering of the final writeback review is an internal Task 29.C route-composition detail, not a separate exported Milestone API

**Implementation points:**
- Run creation exposes every required request/limit/profile field and no base URL/editable-policy/secret override. Invalid input shows stable reasons and creates no run.
- Run detail displays phase/status, targets, budgets, recent actions/results, feedback, checks, and safe next action from Task 23; forbidden test states never render as passing.
- Disclosure page shows provider, endpoint id, trusted `api.openai.com` host, model, exact category/path scopes using human labels, cumulative budget/usage, expiry, and the no-content-redaction warning.
- Final writeback page shows the exact deterministic diff, Manifest summary, formal evidence, workspace preimage status, and subject expiry together. Approval posts the exact wait/run/kind/subject binding.
- Disclosure posts only through `DisclosureDecisionWorkflowPortV1`; it cannot construct, activate, reject, expire, revoke, or charge a Grant in a route.
- `ProductionFinalWritebackWorkflowV1` first calls Task 14. Only an exact `WritebackApprovedV1` may call Task 26 `PersistenceCommandFactoryV1.for_approved_run` and then `PersistenceCoordinator.persist` once. The form never supplies candidate/diff/evidence/workspace/policy fields. Stale, rejected, expired, duplicate, wrong-type, or failed Task 14 results make zero factory and persistence calls; hard DENY has no approval button.
- `RunGovernanceWorkflowPortsV1` exposes no raw `ControlDatabase`, repository, Grant ledger, approval repository, adapter, or standalone persistence port. Production composition supplies only the five declared workflow protocols.
- Every post uses Task 28 session/Host/Origin/CSRF protection, an idempotency event id, closed form parsing, and typed service ports.
- Escape all untrusted text, use semantic HTML/labels/focusable controls/live error regions, and verify keyboard-only workflows and status-independent color cues.

**Intentionally failing test:**

```python
def test_stale_writeback_subject_never_calls_persistence(
    local_web_client: TestClient,
    workflow_ports: SpyRunGovernanceWorkflowPorts,
    stale_writeback_form: dict[str, str],
) -> None:
    response = local_web_client.post(
        "/runs/run-1/final-writeback",
        headers=valid_local_security_headers(),
        data=stale_writeback_form,
    )
    assert response.status_code == 409
    assert "APPROVAL_STALE" in response.text
    assert workflow_ports.persistence_call_count == 0
```

**Verification:**
- Target: `python -m pytest -q tests/web/test_writeback_workflow.py::test_stale_writeback_subject_never_calls_persistence`
- Domain: `python -m pytest -q tests/web/test_run_workflow.py tests/web/test_disclosure_workflow.py tests/web/test_writeback_workflow.py tests/web/test_accessibility.py`
- Full: `python -m pytest -q`
- Browser verification: start `vespercode serve` against deterministic fake ports and exercise create → running → disclosure → formal review → stale approval using keyboard navigation.
- Expected: all run/governance pages, safe failures, endpoint/scope labels, exact review binding, escaping, and accessibility tests pass.

**Review gate:**
1. Spec compliance review traces US-01, US-03–US-06, US-08 and each run/governance §4.9 capability to a route, test, and typed domain call with no bypass.
2. Code quality plus UI/UX review checks route size, form closure, idempotency, CSRF coverage, safe rendering, accessibility, state comprehension, and absence of domain duplication.
3. Critical/Important findings block E2E, package smoke, and delivery.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the stale-subject RED test.** Add the exact test with a valid local session/CSRF binding and a spy persistence port.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because workflow routes are not registered.
- [ ] **Step 3: Implement the minimum final-writeback route.**

  ```python
  @router.post("/runs/{run_id}/final-writeback")
  def decide_final_writeback(
      run_id: str,
      form: FinalWritebackDecisionFormV1,
      ports: RunGovernanceWorkflowPortsV1 = Depends(run_governance_workflow_ports),
  ) -> Response:
      command = form.to_command(run_id=run_id)
      result = ports.final_writeback.decide(command)
      if result.kind != "PERSISTED":
          return render_writeback_error(result)
      return redirect_to_run(run_id)
  ```

  `ProductionFinalWritebackWorkflowV1`, not the route, validates the decision through Task 14 and delegates the one permitted persistence attempt to Task 26; Task 26 revalidates and consumes the exact approval before any workspace write.
- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0`, HTTP 409, and zero persistence calls.
- [ ] **Step 5: Refactor without behavior change.** Keep each route module focused on one workflow and keep all domain predicates behind typed ports.
- [ ] **Step 6: Run domain and browser tests.** Run the exact domain command, then execute the browser verification workflow. Expected: tests pass and every run/governance page/decision renders and behaves correctly.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Provide Task 29, SPEC US-01/US-03–US-06/US-08, §4.2.7/§4.4/§4.6/§4.9, route matrix, tests, and browser captures.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality and UI/UX review.** Require inspection of typed boundaries, security on every post, idempotency, templates, accessibility, error recovery, and no domain-rule duplication.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important code and UI findings, rerun Steps 6–8, repeat browser verification, and obtain passing re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add local governance workflows`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 29 PR.

### Milestone 30: Capability-isolated Public Mock Demo

**Execution notice:** Non-executable aggregate contract. Only Tasks 30.A–30.B are executable.

**Status:** Not started

**Goal:** Deliver a deterministic, short-lived public scenario that reuses only the production pure parser/binding/policy/dispatcher/action-pipeline/feedback/context/stopping modules through Demo-only simulated tool ports and identities, with no formal loop engine, Run/turn repository, local files, Docker, credentials, recovery, persistence, or real provider.

**SPEC / FR / NFR / AC references:** SPEC §1.5 public demo goal; §2.9 US-09; §4.2.1 Demo states; §4.9 public Demo; §5.1–§5.2; §5.5–§5.6; §6.4; §7 Demo rows; §8.3; §10.1 AC-02, AC-05, AC-09, AC-12, AC-17, AC-24; §10.4 visual scenario.

**Dependencies:** Tasks 4–5, 13, 17, and 24–25.

**Blocks:** Tasks 32 and 34–37.

**Parallelization:** Parallel with Task 29 after Task 25; it imports shared pure core modules but no formal capability adapter.

**Recommended branch:** `codex/task-30-public-mock-demo`

**Recommended worktree:** `.worktrees/task-30-public-mock-demo`

**Files:**
- Create: `src/vespercode/demo/types.py`
- Create: `src/vespercode/demo/scenario.py`
- Create: `src/vespercode/demo/executor.py`
- Create: `src/vespercode/demo/runner.py`
- Create: `src/vespercode/demo/app.py`
- Create: `src/vespercode/demo/healthcheck.py`
- Create: `src/vespercode/demo/templates/demo.html`
- Test: `tests/demo/test_types.py`
- Test: `tests/demo/test_scenario.py`
- Test: `tests/demo/test_trace_determinism.py`
- Test: `tests/demo/test_shared_core_composition.py`
- Test: `tests/demo/test_capability_isolation.py`
- Test: `tests/demo/test_session_limits.py`
- Test: `tests/demo/test_health.py`
- Test: `tests/demo/test_rendering.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 4.E canonical path utilities; Task 5.D evidence/artifact contracts; Task 13 `PolicyEngine`; Tasks 17.A–17.C `ActionParser.parse`, `bind_action`, `ToolDispatcher`, and `ToolPortsV1`; Tasks 24.A–24.C `build_feedback`, context projection, and feedback consumption; Task 25.A `StopEvaluator.evaluate`; Task 25.D `ActionPipeline.execute`.
- Produces:
  - Task 30.A child-owned `DemoScenarioV1`, `DemoRunStatus`, `DemoDecision`, and `DemoTraceV1`
  - `DemoExecutor.tool_ports() -> ToolPortsV1`, whose six callables return only the exact fixed simulated pure/domain result types accepted by Task 17.C for the built-in scenario
  - `DemoScenarioRunner.advance(session: DemoSessionV1, decision: DemoDecisionV1 | None) -> DemoStepResultV1`
  - exact constant `DEMO_SHARED_CORE_MODULES_V1: frozenset[str] = frozenset({"vespercode.governance.policy", "vespercode.loop.agent_actions", "vespercode.loop.action_parser", "vespercode.loop.action_binding", "vespercode.loop.context_projection", "vespercode.loop.feedback", "vespercode.loop.stopping", "vespercode.loop.action_pipeline", "vespercode.tools.dispatcher"})`
  - `create_demo_app(config: DemoAppConfigV1) -> FastAPI`
  - `healthcheck.main() -> int`, using only a bounded stdlib HTTP request to loopback `/healthz`
  - `GET /healthz` and fixed-scenario Demo routes

**Implementation points:**
- Define Demo-only states/ids/subject digests. No Demo type subclasses, validates as, serializes to, or converts into a formal Run, Approval, Grant, AuditEvent, VerifiedCandidate, or persistence command.
- The versioned built-in script contains only fixed Mock model responses, simulated tool-result fixtures, and presentation labels. It defines no action parser, policy rule, feedback selector/consumer, stop evaluator, or alternative state-machine semantics.
- `DemoScenarioRunner.advance` must execute the fixed sequence `Mock response → Task 25.D ActionPipeline.execute`, whose injected production components perform `ActionParser.parse → bind_action → PolicyEngine.evaluate → ToolDispatcher.dispatch with DemoExecutor.tool_ports() → build_feedback/select_feedback/consume_feedback`, then `Task 25.A StopEvaluator.evaluate → Demo result`. A hard `DENY` skips dispatch; a simulated check failure must change the next Mock action only through the Task 24 feedback projection.
- The fixed scenario shows a non-editable hard DENY, one failed simulated check followed by a different correction action, protected-artifact rejection, formal-looking simulated pass, and no write without simulated approval.
- All code/result/diff text is fixed package data; accept no repository path, upload, arbitrary prompt, command, external URL, provider setting, or secret.
- Register only `DemoExecutor`, in-memory session store, clock/id generator, and template renderer as capability adapters. Compose only the exact Task 13/17.A–17.C/24.A–24.C/25.A/25.D pure modules in `DEMO_SHARED_CORE_MODULES_V1`; shared pure core is not a capability adapter. Dependency graph tests must prove every `PROHIBITED_DEMO_MODULE_PREFIXES_V1` member, including the formal engine/storage/file/WinCred/Docker/recovery/SQLite/OpenAI boundaries, is absent.
- The in-memory Demo session store implements the Task 24 `FeedbackRepositoryV1` port only for the current five-minute session. It performs no disk/database write and discards feedback on completion, expiry, reset, or error.
- Use only Task 25.A `StopEvaluator` for terminal meaning. Never import, construct, subclass, wrap, or adapt the formal loop engine; never construct a formal Run/turn repository or recovery lifecycle. Demo session transitions adapt `StopDecisionV1` to `DEMO_COMPLETED | DEMO_FAILED` and never create a formal stop/audit record.
- Limit a session to 20 actions and five minutes; limit process concurrency to 10 using an atomic semaphore. Reject or expire excess sessions deterministically.
- Create a fresh UUID session, keep it only in process memory, discard it at completion/expiry/reset, and create no cross-process recovery.
- `DemoDecisionV1` binds demo session/subject/decision/time and advances only the fixed script.
- Render a persistent “simulated public demo” label and make status/error transitions distinguishable without color alone.
- Expose `/healthz` without session state and return success only when scenario assets and capability registry validate.
- Read platform `PORT` only in the Demo app and healthcheck process entry points; the app binds `0.0.0.0` and the healthcheck probes `127.0.0.1` with a strict timeout. Neither behavior is shared with formal local serve.

**Intentionally failing test:**

```python
def test_demo_step_invokes_shared_core_and_only_demo_tool_ports(
    shared_core_spies: SharedCoreSpies,
    demo_runner: DemoScenarioRunner,
    demo_session: DemoSessionV1,
) -> None:
    result = demo_runner.advance(demo_session, decision=None)
    assert shared_core_spies.calls == (
        "ActionPipeline.execute",
        "ActionParser.parse",
        "bind_action",
        "PolicyEngine.evaluate",
        "ToolDispatcher.dispatch",
        "build_feedback",
        "select_feedback",
        "consume_feedback",
        "StopEvaluator.evaluate",
    )
    assert result.executor_kind == "DEMO_EXECUTOR"
    assert shared_core_spies.formal_capability_calls == 0
```

**Verification:**
- Target: `python -m pytest -q tests/demo/test_shared_core_composition.py::test_demo_step_invokes_shared_core_and_only_demo_tool_ports`
- Domain: `python -m pytest -q tests/demo`
- Full: `python -m pytest -q`
- Expected: the runtime call trace proves production parser/policy/dispatcher/feedback/stop reuse; only Demo tool ports execute; type isolation, fixed trace determinism, decision binding, forbidden-capability absence, action/time/concurrency limits, expiry/reset, rendering, and health tests pass offline.

**Review gate:**
1. Spec compliance review maps SPEC §6.4's shared parser/policy/feedback/stop flow and every prohibited formal capability to explicit runtime-call, registry, type, and zero-call assertions.
2. Code quality review checks production-core imports, Demo-only `ToolPortsV1`, absence of duplicate parser/policy/feedback/stop logic, in-memory lifecycle, concurrency guard, fixed-input validation, template escaping, and formal/local composition separation.
3. Critical/Important findings block Demo image, public deployment, and delivery.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the shared-core composition RED test.** Add the exact test using call-recording wrappers around the production Task 13/17/24/25 components and explicit zero-call spies for every forbidden capability; do not infer reuse from labels, class-name strings, or source inspection.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because the Demo runner and shared-core composition do not exist.
- [ ] **Step 3: Implement the minimum shared-core Demo composition.** `_load_builtin_demo_scenario` and `_compose_demo_fastapi` are private/local Task 30.B composition helpers with no downstream consumer; the exported app boundary remains the child-owned `create_demo_app(config: DemoAppConfigV1) -> FastAPI`.

  ```python
  def create_demo_app(config: DemoAppConfigV1) -> FastAPI:
      scenario = _load_builtin_demo_scenario("governance-feedback-v1")
      executor = DemoExecutor(scenario)
      action_pipeline = ActionPipeline(
          parser=ActionParser(),
          binder=bind_action,
          policy=PolicyEngine(),
          dispatcher=ToolDispatcher(),
          feedback_builder=build_feedback,
          feedback_selector=select_feedback,
          feedback_consumer=consume_feedback,
      )
      runner = DemoScenarioRunner(
          action_pipeline=action_pipeline,
          tool_ports=executor.tool_ports(),
          context_builder=build_context,
          stop_evaluator=StopEvaluator(),
      )
      capabilities = DemoCapabilityRegistryV1(
          demo_executor=executor,
          demo_sessions=InMemoryDemoSessionStore(config.clock),
          demo_renderer=DemoRenderer(),
      )
      return _compose_demo_fastapi(capabilities, runner, config)
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0` with the exact shared-core call sequence, only `DEMO_EXECUTOR` dispatch, zero forbidden-capability calls, and no formal object conversion.
- [ ] **Step 5: Refactor without behavior change.** Keep Demo types, fixed data-only scenario, simulated tool ports, shared-core runner, app composition, and the stdlib health probe in their six planned modules; remove any duplicate parser, policy, feedback, or stop rule.
- [ ] **Step 6: Run domain tests.** Run `python -m pytest -q tests/demo`. Expected: all shared-core reuse, isolation, trace, feedback-change, limit, decision, reset, rendering, and health cases pass.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Provide Task 30, SPEC §4.2.1/§4.9/§6.4/§8.3/AC-02/AC-05/AC-09/AC-12/AC-17, shared-core call trace, dependency registry, forbidden-capability counters, repeated traces, and local browser captures.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of production-core reuse, absence of parallel parser/policy/feedback/stop implementations, Demo-only tool ports, import/capability isolation, fixed assets, session concurrency, expiry, template safety, and formal-type separation.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8, repeat the fixed scenario twice, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add isolated public Mock Demo`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 30 PR.

### Milestone 31: Reference Fixture End-to-end Workflow

**Execution notice:** Non-executable aggregate contract. Only Tasks 31.A–31.C are executable.

**Status:** Not started

**Goal:** Prove the complete Windows + Docker + Mock-LLM formal workflow from strict admission through stable baseline, feedback correction, formal validation, exact approval, persistence, audit, and recovery-safe terminal evidence.

**SPEC / FR / NFR / AC references:** SPEC §1.4 reference profile; §2 US-01 and US-03–US-08; §4.1–§4.8; §5.1–§5.6; §6.2; §7; §10.1 AC-01–AC-08, AC-13–AC-31; §10.3 reference fixture E2E; course repeatable mechanism/demo requirement.

**Dependencies:** Tasks 9–29 and 38.

**Blocks:** Tasks 33–37.

**Parallelization:** Sequential after Tasks 29 and 38 because it validates the merged formal application.

**Recommended branch:** `codex/task-31-reference-e2e`

**Recommended worktree:** `.worktrees/task-31-reference-e2e`

**Files:**
- Create: `scripts/run_reference_e2e.py`
- Create: `tests/e2e/reference/test_reference_success.py`
- Create: `tests/e2e/reference/test_reference_denials.py`
- Create: `tests/e2e/reference/test_reference_waits.py`
- Create: `tests/e2e/reference/test_reference_no_write.py`
- Create: `tests/e2e/reference/test_reference_audit.py`
- Create: `tests/e2e/reference/test_reference_call_gate.py`
- Create: `tests/e2e/reference/test_reference_recovery_block.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: production composition from Tasks 9–29 and both Task 29/38 route installers; Task 2 reference fixture/profile/image; deterministic Mock profile/script; disposable NTFS Git workspace; Docker Desktop Linux mode.
- Produces:
  - `run_reference_e2e(config: ReferenceE2EConfigV1) -> ReferenceE2EResultV1`
  - `ReferenceE2ETraceV1` containing content-addressed run, turn, action, feedback, check, wait, approval, persistence, memory, and audit evidence references
  - CLI report at a caller-supplied local evidence path with no secret or complete source-body duplication
  - one repeatable success trace and explicit denial/no-write/recovery-block traces

**Implementation points:**
- Copy the fixed reference fixture to a disposable NTFS Git workspace, establish exact HEAD/index bytes, pull/verify the immutable reference image, and use only built-in Mock/reference profiles and explicit limits.
- Treat the Task 2 GO fixture bytes as immutable input. If E2E exposes a fixture-contract defect, reopen the affected gate/profile tasks and renew approval rather than editing the fixture in this task.
- Prove admission order, one sealed Snapshot, static support, readiness, two collect-only runs, full/target stable fingerprints, Ruff/Mypy, and Manifest creation before any Agent file action.
- Script read/search plus a structurally valid `docs/**` patch hard DENY, a protected-artifact patch rejection, a legal but failing `src/**` patch, target-check feedback, a different corrective patch, and completion proposal.
- Force both List and Search through multiple canonical cursor pages and compare their concatenation with unpaged results; inject a changed visible-tree digest and a tampered cursor to prove `CONTINUATION_STALE`/`CONTINUATION_INVALID` with zero partial artifact.
- Prove Mock requests/results have no OpenAI fields, credential/Grant/authorization/network calls stay zero, and feedback is consumed once by the corrective turn.
- In a separate no-network OpenAI call-gate scenario with Fake transport and a safe credential port, pass PREFLIGHT/readiness, clear the credential before the next real-call attempt, and prove `CREDENTIAL_MISSING` stops the Run before Grant charge, authorization record, turn/call count, or transport. Repeat with an unsafe backend and `CREDENTIAL_BACKEND_UNSAFE`.
- Execute the complete formal plan and prove VerifiedCandidate creation only after all success predicates.
- Cover final-wait rejection, expiry, wrong binding, no approval, and exact approval. Every non-exact branch writes zero files.
- On exact approval, prove writeback bytes equal FinalDiff postimages, untouched files remain equal to Snapshot, and the Run reaches SUCCEEDED only after write verification/COMMITTED.
- Add a separate injected uncertain transaction, prove admission blocks the same workspace, preview writes zero bytes, and explicit recovery produces only a proven disposition.
- Assert memory source authority/isolation and redacted monotonic audit evidence across the trace.
- Run the entire success scenario twice from identical fixture inputs and compare semantic action/state/evidence digests while excluding injected volatile ids/times.

**Intentionally failing test:**

```python
def test_verified_candidate_without_final_approval_never_writes_workspace(
    reference_e2e_harness: ReferenceE2EHarness,
) -> None:
    result = reference_e2e_harness.run_until_final_wait(
        decision="REJECT",
    )
    assert result.verified_candidate_created is True
    assert result.workspace_write_count == 0
    assert result.final_status == "STOPPED"
    assert result.stop_reason == "WAIT_REJECTED"
```

**Verification:**
- Target: `python -m pytest -q -o addopts='' -m reference_e2e tests/e2e/reference/test_reference_no_write.py::test_verified_candidate_without_final_approval_never_writes_workspace`
- E2E suite: `python -m pytest -q -o addopts='' -m reference_e2e tests/e2e/reference`
- Script: `python scripts/run_reference_e2e.py --workspace-root tests/.tmp/reference-e2e --report tests/.tmp/reference-e2e-report.json`
- Full: `python -m pytest -q`
- Expected: target and E2E suite pass on Windows + Docker without skip; script exits `0`, records exact semantic evidence, proves paged List/Search equivalence and the cleared/unsafe credential zero-side-effect call gate, and leaves no credential, unresolved transaction, or execution copy.

**Review gate:**
1. Spec compliance review walks the E2E trace against every referenced FR/AC and confirms tests exercise production composition rather than replacing core mechanisms with stubs.
2. Code quality review checks fixture isolation, deterministic comparisons, failure cleanup, evidence redaction, script repeatability, and clear unit/integration/E2E boundaries.
3. Critical/Important findings or a skipped required environment case block package, images, CI, and delivery.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the no-approval RED test.** Add the exact test using production services with only the LLM and clock/ID sources deterministic.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because the E2E composition/driver does not exist.
- [ ] **Step 3: Implement the minimum deterministic E2E driver.**

  ```python
  def run_reference_e2e(
      config: ReferenceE2EConfigV1,
  ) -> ReferenceE2EResultV1:
      workspace = prepare_disposable_reference_workspace(config)
      app = compose_formal_application(config.with_workspace(workspace))
      trace = drive_mock_scenario(app, config.script)
      return verify_and_freeze_reference_trace(trace, workspace, config)
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0`; VerifiedCandidate exists but workspace writes remain zero.
- [ ] **Step 5: Refactor without behavior change.** Keep environment setup, formal application composition, scenario driving, assertions, evidence freezing, and cleanup as explicit driver stages.
- [ ] **Step 6: Run the E2E suite and script.** Run both commands. Expected: all scenarios, including cursor pagination and both per-call credential failure paths, pass without skip and the standalone report is reproducible.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0` without running the marked E2E suite.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Provide Task 31, SPEC §4.1–§4.8/§10.3, full trace/report digests, environment versions, and cleanup evidence.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of production wiring, fixture determinism, assertion coverage, failure cleanup, report minimization, and flake resistance.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8 twice, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add reference end-to-end workflow`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 31 PR.

### Milestone 32: Repeatable Governance and Feedback Mechanism Demo

**Execution notice:** Non-executable aggregate contract. Only Tasks 32.A–32.C are executable.

**Status:** Not started

**Goal:** Produce one deterministic offline demonstration that visibly proves hard governance interception, feedback-driven correction, protected-artifact defense, approval gating, and zero unauthorized real-provider calls.

**SPEC / FR / NFR / AC references:** SPEC §3.1–§3.3 main contribution; §4.4 policy/disclosure; §4.5 feedback; §4.9 Demo scenario; §10.1 AC-02, AC-04–AC-06, AC-09, AC-13, AC-17, AC-20, AC-26–AC-28, AC-31; §10.4 mechanism demo; Harness course mechanism-demo requirement.

**Dependencies:** Tasks 12–13, 15–17, 19, 24–25, and 30.

**Blocks:** Tasks 33–37.

**Parallelization:** Parallel with Task 38 after Task 30; it owns only mechanism fixtures, tests, and the driver script.

**Recommended branch:** `codex/task-32-mechanism-demo`

**Recommended worktree:** `.worktrees/task-32-mechanism-demo`

**Files:**
- Create: `scripts/run_mechanism_demo.py`
- Create: `tests/e2e/mechanism/test_hard_deny.py`
- Create: `tests/e2e/mechanism/test_feedback_recovery.py`
- Create: `tests/e2e/mechanism/test_protected_artifacts.py`
- Create: `tests/e2e/mechanism/test_approval_gate.py`
- Create: `tests/e2e/mechanism/test_disclosure_gate.py`
- Create: `tests/e2e/mechanism/test_credential_recheck.py`
- Create: `tests/e2e/mechanism/test_continuation_gate.py`
- Create: `tests/e2e/mechanism/test_trace_determinism.py`
- Create: `tests/e2e/mechanism/test_shared_core_reuse.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 12 candidate pipeline; Task 13 real policy; Task 15 disclosure ledger; Task 16 Mock/real stub adapters; Task 17 parser/binder/dispatcher; Task 19 structured check fixtures; Task 24 feedback/context; Task 25 loop/stop core; Task 30 `DemoScenarioRunner`, Demo tool ports, and public scenario expectations.
- Produces:
  - `run_mechanism_demo(config: MechanismDemoConfigV1) -> MechanismDemoResultV1`
  - `MechanismDemoTraceV1` with ordered actions, decisions, dispatch counts, candidate digests, feedback refs, adapter calls, waits, and terminal proof
  - a text-safe console summary and canonical JSON report at caller-selected paths
  - a runtime reuse assertion that the formal harness and public Demo invoke the same exact Task 13, 17.A–17.C, 24.A–24.C, 25.A, and 25.D pure implementations, plus a separate presentation-label alignment assertion; formal engine composition is outside this comparison

**Implementation points:**
- First action submits a valid `docs/outside-scope.md` create; prove path syntax passes, policy returns `DENY/PATCH_PATH_NOT_EDITABLE`, and both dispatch/publish counts remain zero.
- Read README through the allowed file tool, then attempt to modify it; prove read succeeds and patch remains a hard DENY.
- Force List and Search to truncate, consume their distinct returned cursors, and prove concatenated pages equal unpaged results without repeated/omitted paths, matches, or non-text counts; tampered/tree-stale cursors return zero partial payload.
- Apply one legal `src/**` patch whose injected target check fails; create bounded structured feedback and prove the next Mock action changes semantically and consumes that feedback once.
- Attempt to modify a protected test/config artifact; prove `PROTECTED_ARTIFACT_CHANGED` wins before check execution.
- Apply the corrected candidate, pass the formal predicate, then withhold final approval and prove authoritative write count remains zero.
- Exercise a real-adapter spy first with no Grant/record, then with an otherwise valid Grant but a credential cleared after readiness, and finally with a backend changed to unsafe. Prove transport calls, turn/call increments, authorization records, and charged bytes remain zero; the latter two paths return `CREDENTIAL_MISSING` and `CREDENTIAL_BACKEND_UNSAFE` and stop without retry.
- Run the same fixed inputs twice and compare policy decisions, semantic action/result digests, candidate identities, feedback consumption, and terminal state.
- Keep the script offline: use fixed tree/check/transport and fake safe/unsafe credential fixtures, no workspace write, no Docker, no real keyring, no provider request, and no external URL.
- Run Task 30's `DemoScenarioRunner` headlessly with call-recording wrappers around the exact `DEMO_SHARED_CORE_MODULES_V1` functions, including `ActionPipeline.execute` and `StopEvaluator.evaluate`. Prove both compositions execute that shared pure subset and only the Demo dispatches through `DemoExecutor.tool_ports()`; engine coverage remains in the separate formal-loop trace.
- Compare scenario meaning and labels only after runtime reuse is proven. Never convert Demo decisions/types into formal objects, and never treat label equality as evidence of implementation reuse.

**Intentionally failing test:**

```python
def test_outside_scope_patch_is_denied_before_dispatch_or_publish(
    mechanism_harness: MechanismHarness,
) -> None:
    trace = mechanism_harness.run_step("outside-scope-create")
    assert trace.policy_decision == "DENY"
    assert trace.error_code == "PATCH_PATH_NOT_EDITABLE"
    assert trace.dispatch_count == 0
    assert trace.candidate_publish_count == 0


def test_formal_and_demo_compositions_execute_the_same_core_implementations(
    formal_harness: MechanismHarness,
    demo_runner: DemoScenarioRunner,
    shared_core_spies: SharedCoreSpies,
    demo_session: DemoSessionV1,
) -> None:
    formal_harness.run_step("feedback-correction")
    demo_runner.advance(demo_session, decision=None)
    assert shared_core_spies.formal_shared_pure_implementations == (
        ActionPipeline.execute,
        ActionParser.parse,
        bind_action,
        PolicyEngine.evaluate,
        ToolDispatcher.dispatch,
        build_feedback,
        select_feedback,
        consume_feedback,
        StopEvaluator.evaluate,
    )
    assert (
        shared_core_spies.demo_shared_pure_implementations
        == shared_core_spies.formal_shared_pure_implementations
    )
    assert shared_core_spies.demo_executor_calls > 0
    assert shared_core_spies.demo_formal_capability_calls == 0
```

**Verification:**
- Target: `python -m pytest -q tests/e2e/mechanism/test_hard_deny.py::test_outside_scope_patch_is_denied_before_dispatch_or_publish`
- Shared-core target: `python -m pytest -q tests/e2e/mechanism/test_shared_core_reuse.py::test_formal_and_demo_compositions_execute_the_same_core_implementations`
- Mechanism suite: `python -m pytest -q tests/e2e/mechanism`
- Script: `python scripts/run_mechanism_demo.py --report tests/.tmp/mechanism-demo-report.json`
- Full: `python -m pytest -q`
- Expected: all nine mechanism tests pass offline; script exits `0`; formal and Demo compositions have verified production-core provenance/call sequences while retaining separate state types and execution ports; two formal traces have identical semantic evidence and zero unauthorized capability calls, continuation pages are exact, and both credential failure traces have zero Grant/record/count/network increments.

**Review gate:**
1. Spec compliance review maps each §6.4/§10.4 item and main-contribution question to explicit production-core runtime-call and trace assertions; label alignment alone is insufficient.
2. Code quality review checks shared implementation provenance, fixture determinism, trace schema, no hidden external dependency, meaningful assertions, separate Demo/formal execution ports, and public/formal type separation.
3. Critical/Important findings block package, CI, and final course delivery.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the pre-dispatch DENY RED test.** Add the exact test with a structurally valid outside-scope patch.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because the mechanism harness/trace does not exist.
- [ ] **Step 3: Implement the minimum trace driver.**

  ```python
  def run_step(self, step_id: str) -> MechanismStepTraceV1:
      response = self.script.response_for(step_id)
      action_step = self.action_pipeline.execute(
          response,
          self.action_pipeline_context_for(step_id),
      )
      return self.trace_action_step(action_step)
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0`, zero dispatch, and zero candidate publication.
- [ ] **Step 5: Refactor without behavior change.** Keep fixed inputs, production-core composition, public-Demo headless composition, runtime reuse capture, semantic/label comparison, and console/report rendering as separate driver responsibilities.
- [ ] **Step 6: Run the mechanism suite and script.** Run both commands. Expected: every governance, feedback, approval, disclosure, cursor, credential-recheck, and shared-core reuse scenario passes; Demo dispatch uses only simulated ports; the report contains only bounded non-secret evidence.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Provide Task 32, SPEC §3/§6.4/§10.4, formal and Demo core-call traces, implementation provenance, both trace digests, capability counters, and the separate public-Demo label-alignment table.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of production mechanism reuse in both compositions, absence of label-only proof, assertions, deterministic IDs/clocks, no external calls, report bounds, execution-port separation, and type isolation.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8 twice, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add repeatable mechanism demo`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 32 PR.

### Milestone 33: Wheel Build and Clean pipx Distribution Smoke

**Execution notice:** Non-executable aggregate contract. Only Tasks 33.A–33.B are executable.

**Status:** Not started

**Goal:** Build one versioned wheel with all required local assets, publish its SHA-256, and prove clean Windows pipx installation, CLI help, loopback WebUI startup, and recovery preview entry points.

**SPEC / FR / NFR / AC references:** SPEC §5.4 evidence; §8.2 local distribution; §8.4 `wheel-build-smoke`; §9 package choice; §10.1 AC-08, AC-10–AC-11, AC-24, AC-26, AC-29–AC-30; §10.3 package smoke; course distribution requirement.

**Dependencies:** Tasks 26, 28–29, 31–32, and 38.

**Blocks:** Tasks 35–37.

**Parallelization:** Parallel with Task 34 after Tasks 31–32; package and image files are disjoint.

**Recommended branch:** `codex/task-33-wheel-pipx`

**Recommended worktree:** `.worktrees/task-33-wheel-pipx`

**Files:**
- Create: `scripts/run_package_smoke.py`
- Create: `tests/smoke/package/test_wheel_contents.py`
- Create: `tests/smoke/package/test_wheel_digest.py`
- Create: `tests/smoke/package/test_pipx_install.py`
- Create: `tests/smoke/package/test_installed_cli.py`
- Create: `tests/smoke/package/test_installed_webui.py`
- Modify: `pyproject.toml` (package data, version, distribution metadata, and console entry point only)
- Modify: `src/vespercode/cli.py` (installed-resource resolution only if smoke exposes a packaging defect)
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: completed package/application from Tasks 26–32 and 38; Task 6 built-in manifests; Task 28 CLI/app shell plus Task 29 and Task 38 route installers/templates.
- Produces:
  - `python -m build --wheel` yielding exactly one filename matching `dist/vespercode-{project_version}-py3-none-any.whl`
  - adjacent wheel SHA-256 evidence
  - `run_package_smoke(config: PackageSmokeConfigV1) -> PackageSmokeResultV1`
  - clean pipx-installed `vespercode --help`, `serve`, and `recover --workspace` command surface
  - saved smoke report containing package version, source commit, wheel filename/digest, Python/pipx versions, and redacted command outcomes

**Implementation points:**
- Pin and lock the build backend/tool versions. Build from a clean tracked source tree and fail if zero or multiple wheel files are produced.
- Include templates, pinned HTMX, all three built-in profiles, Demo scenario assets, and required report plugin resources; exclude tests, spikes, local databases, evidence bodies, credentials, `.env`, and VCS metadata.
- Verify wheel filename/version/metadata, RECORD hashes, source commit metadata, and independently calculated lowercase SHA-256.
- Install the exact local wheel path into a fresh project-specific pipx home/bin directory on Windows; do not test by importing the source checkout.
- Run installed `vespercode --help`, start `vespercode serve` on a reserved loopback port with deterministic safe fake ports, fetch one page, and stop cleanly.
- Invoke the fixed production installer tuple from Task 38 through installed `vespercode serve`; prove run, disclosure, credential status, memory, redacted audit, and recovery-preview pages resolve without importing the source checkout.
- Run installed recovery preview against a no-transaction disposable workspace and prove it makes zero writes; never use `--apply` in package smoke.
- Fail if templates/assets/manifests cannot be loaded from installed resources or if serve attempts non-loopback binding.
- Remove the isolated pipx environment and temporary application data after evidence capture without touching user-wide pipx installations.
- Document `pipx install dist/vespercode-{project_version}-py3-none-any.whl` as canonical until a real index publication is separately proven.

**Intentionally failing test:**

```python
def test_built_wheel_contains_all_runtime_resources(
    built_wheel: WheelArchive,
) -> None:
    assert built_wheel.contains("vespercode/web/templates/base.html")
    assert built_wheel.contains("vespercode/web/templates/credential_status.html")
    assert built_wheel.contains("vespercode/web/templates/recovery_preview.html")
    assert built_wheel.contains("vespercode/web/static/htmx.min.js")
    assert built_wheel.contains("vespercode/profiles/builtin/reference-profile-v1.json")
    assert built_wheel.contains("vespercode/demo/templates/demo.html")
```

**Verification:**
- Target: `python -m pytest -q -o addopts='' -m package_smoke tests/smoke/package/test_wheel_contents.py::test_built_wheel_contains_all_runtime_resources`
- Build: `python -m build --wheel`
- Package smoke: `python -m pytest -q -o addopts='' -m package_smoke tests/smoke/package`
- Driver: `python scripts/run_package_smoke.py --dist dist --require-one-wheel --report tests/.tmp/package-smoke-report.json`
- Full: `python -m pytest -q`
- Expected: one wheel builds; digest verifies; clean Windows pipx install, installed-resource, CLI/WebUI, and preview checks pass; cleanup succeeds.

**Review gate:**
1. Spec compliance review maps wheel contents, canonical install/start/recover commands, SHA evidence, Windows environment, and resource/profile identity to §8.2/§8.4.
2. Code quality review checks package inclusion/exclusion, clean environment isolation, subprocess bounds, server teardown, digest calculation, and no source-tree fallback.
3. Critical/Important findings or a non-Windows substitute block CI and release.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the wheel-resource RED test.** Add the exact test and a build fixture that inspects the archive without importing the checkout.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because package metadata/resources are not configured and no wheel exists.
- [ ] **Step 3: Implement the minimum package-data configuration.**

  ```toml
  [project.scripts]
  vespercode = "vespercode.cli:main"

  [tool.hatch.build.targets.wheel]
  packages = ["src/vespercode"]

  [tool.hatch.build.targets.wheel.force-include]
  "src/vespercode/web/templates" = "vespercode/web/templates"
  "src/vespercode/web/static" = "vespercode/web/static"
  "src/vespercode/profiles/builtin" = "vespercode/profiles/builtin"
  "src/vespercode/demo/templates" = "vespercode/demo/templates"
  ```

- [ ] **Step 4: Run GREEN.** Rebuild and rerun Step 2. Expected: exit `0` with every required resource present.
- [ ] **Step 5: Refactor without behavior change.** Keep package config declarative and put build/install/start/cleanup orchestration only in the smoke driver.
- [ ] **Step 6: Run build, package smoke, and driver.** Run all three commands with the actual versioned filename. Expected: every package test passes in a clean Windows environment.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0` without package-smoke markers.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands and scan wheel member names for prohibited files. Expected: all exit `0` with no prohibited member.
- [ ] **Step 9: Request spec compliance review.** Provide Task 33, SPEC §8.2/§8.4/AC-11, wheel member list, digest, clean pipx log, and server/recovery evidence.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rebuild from clean source, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of metadata, resource lookup, environment isolation, process cleanup, filename/digest evidence, and exclusion rules.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rebuild, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add wheel and pipx smoke`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 33 PR.

### Milestone 34: Reference and Demo OCI Image Smoke

**Execution notice:** Non-executable aggregate contract. Only Tasks 34.A–34.B are executable.

**Status:** Not started

**Goal:** Reproduce the Task 2-frozen formal-reference OCI manifest and its already-proven loopback-registry digest round-trip, build the public-Demo image with the Task 30-curated shared pure core, and prove its formal capability adapters remain absent alongside the distinct runtime, health, digest, and locked-execution contracts.

**SPEC / FR / NFR / AC references:** SPEC §1.4.1/§1.4.5; §4.5 Docker checks; §4.9 Demo; §5.5–§5.6; §6.4 shared core; §8.2–§8.4; §9; §10.1 AC-04, AC-09, AC-12, AC-19–AC-20, AC-24–AC-25, AC-30; §10.3 OCI smoke.

**Dependencies:** Tasks 18, 20, and 30–32.

**Blocks:** Tasks 35–37.

**Parallelization:** Parallel with Task 33 after Tasks 31–32; Task 34 builds a curated Demo runtime rather than installing the formal wheel.

**Recommended branch:** `codex/task-34-oci-images`

**Recommended worktree:** `.worktrees/task-34-oci-images`

**Files:**
- Create: `containers/demo/Dockerfile`
- Create: `requirements/demo.lock`
- Create: `tests/smoke/images/test_reference_image_contract.py`
- Create: `tests/smoke/images/test_reference_fixture_smoke.py`
- Create: `tests/smoke/images/test_demo_image_contract.py`
- Create: `tests/smoke/images/test_demo_container_health.py`
- Create: `tests/smoke/images/test_image_capability_separation.py`
- Create: `scripts/run_reference_image_smoke.py`
- Create: `scripts/run_demo_image_smoke.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 2 reference recipe/GO mapping, fixed builder/output parameters, digest-pinned registry image, and loopback-registry evidence; Task 18 executor contract; Task 20 adapter/report tools; Task 30 Demo entry point; Tasks 31–32 reference/mechanism evidence.
- Produces:
  - a local content-addressed reference image whose OCI/loopback/digest-pull digest equals Task 2, plus a separate Demo image
  - `run_image_smoke(config: ImageSmokeConfigV1) -> ImageSmokeResultV1`
  - verified reference image tool/execution-profile report
  - Demo `/healthz`, fixed trace, PORT, non-persistence, and capability-absence report
  - immutable image digests recorded only after real builds

**Implementation points:**
- Reference recipe pins the Linux base by digest, installs only hash/version-locked requirements at build time, contains the exact Python/pytest/plugin/Ruff/Mypy versions, and exposes no runtime package installation.
- Treat Task 2's `containers/reference/Dockerfile`, reference lock, fixture, manifest bytes, builder/output parameters, registry image digest, and GO report as read-only inputs. Re-run its no-credential loopback-registry procedure and require local OCI, registry response, digest pull, Task 2 GO `docker_image_digest`, and Task 6 manifest `docker_image_digest` all to equal; a mismatch returns NO-GO, reopens Tasks 2/6 and approval, and never edits the manifest in this task.
- Set the fixed non-root user, report entry point/assets, work/tmp/cache ownership, and no Docker client/socket dependency in the reference image.
- Build and inspect the reference image, then invoke it through the production executor to prove no network, read-only root/workspace, tmpfs/cache, resource caps, full report, fingerprint, and reference fixture behavior.
- Demo recipe contains only the public Demo application/runtime/static assets, Task 30 `DEMO_SHARED_CORE_MODULES_V1` plus their reviewed Task 4.E/5.D import closure, and a non-root user. It does not copy the formal engine, Run/turn/SQLite storage, formal local composition, file-action implementations, WinCred adapter, OpenAI adapter, recovery/persistence code, Docker executor/client/socket, release credentials, or target repository.
- Build the Demo runtime from an explicit allowlist containing `src/vespercode/demo/`, the exact `DEMO_SHARED_CORE_MODULES_V1` tuple, their reviewed Task 4.E/5.D canonical/contract import closure, and the exact hash-locked `requirements/demo.lock`; do not install the full formal VesperCode wheel. Fail if static import closure contains a module outside that allowlist or matches any `PROHIBITED_DEMO_MODULE_PREFIXES_V1` member.
- Demo reads PORT, binds `0.0.0.0`, serves `/healthz`, retains no persistent disk/state, and reproduces the fixed scenario in a real container.
- Inspect both image histories/filesystems/configs for forbidden secret/config members and capability separation; never log environment values.
- Compute local image ids/digests from real builds, but use only the fixed single-platform OCI/registry manifest digest as identity. The reference digest must match the Task 2 GO report and frozen manifest; do not claim a GHCR RepoDigest until Task 36 pushes and re-pulls it.
- Verify Task 2's already-approved no-self-reference invariant by inspecting the rebuilt context, layers, config, annotations, and attestations for the final manifest/digest. Finding a cycle invalidates Task 2's GO and reopens Tasks 2/6 immediately; Task 34 is not allowed to become the first feasibility checkpoint or insert a tag/placeholder digest.

**Intentionally failing test:**

```python
def test_demo_image_contains_shared_core_but_no_formal_adapters(
    built_demo_image: OCIImageInspection,
) -> None:
    members = built_demo_image.python_members
    assert "vespercode.demo.app" in members
    assert "vespercode.demo.runner" in members
    assert "vespercode.loop.action_parser" in members
    assert "vespercode.governance.policy" in members
    assert "vespercode.loop.feedback" in members
    assert "vespercode.loop.stopping" in members
    assert "vespercode.loop.action_pipeline" in members
    assert not any(
        member == prefix or member.startswith(prefix + ".")
        for member in members
        for prefix in PROHIBITED_DEMO_MODULE_PREFIXES_V1
    )
    assert built_demo_image.has_docker_socket_mount is False
```

**Verification:**
- Target: `python -m pytest -q -o addopts='' -m oci_smoke tests/smoke/images/test_image_capability_separation.py::test_demo_image_contains_shared_core_but_no_formal_adapters`
- Builds: `docker build --pull=false -f containers/reference/Dockerfile -t vespercode-reference:local .` and `docker build --pull=false -f containers/demo/Dockerfile -t vespercode-demo:local .`
- Image smoke: `python -m pytest -q -o addopts='' -m oci_smoke tests/smoke/images`
- Reference driver: `python scripts/run_reference_image_smoke.py --reference vespercode-reference:local --report tests/.tmp/reference-image-smoke-report.json`
- Demo driver: `python scripts/run_demo_image_smoke.py --demo vespercode-demo:local --report tests/.tmp/demo-image-smoke-report.json`
- Full: `python -m pytest -q`
- Expected: both real builds and all contract/smoke tests pass; digests and versions are recorded from inspection; Demo contains the exact shared pure core and has zero formal capability adapters.

**Review gate:**
1. Spec compliance review compares reference/Demo recipes, the exact shared-pure-core/prohibited-adapter module sets, loopback-registry evidence, no-self-reference inspection, and real runtime evidence with §1.4.5, §4.9, §6.4, §8.2–§8.4, and Task 2 GO; Task 34 cannot manufacture or replace missing Task 2 feasibility evidence.
2. Code quality review checks build contexts, layer contents, non-root ownership, entry points, health checks, reproducibility, digest capture, and capability separation.
3. Critical/Important findings, any mismatch with Task 2's digest round-trip, or any violation of Task 2's no-self-reference evidence blocks CI/release and reopens Tasks 2/6.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the Demo-capability RED test.** Add the exact inspection test and require a real built image fixture.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because the Demo image does not exist.
- [ ] **Step 3: Implement the minimum Demo multi-stage image.**

  ```python
  base_digest = task_2_go_report.base_image_digest
  demo_runtime = build_demo_runtime_allowlist(
      source_root=Path("src"),
      allowed_modules=(
          "vespercode.demo.types",
          "vespercode.demo.scenario",
          "vespercode.demo.executor",
          "vespercode.demo.runner",
          "vespercode.demo.app",
          "vespercode.demo.healthcheck",
          "vespercode.canonical.json_v1",
          "vespercode.canonical.timestamp_v1",
          "vespercode.canonical.digest",
          "vespercode.contracts.optional",
          "vespercode.contracts.location",
          "vespercode.contracts.run",
          "vespercode.contracts.action",
          "vespercode.contracts.evidence",
          *DEMO_SHARED_CORE_MODULES_V1,
      ),
      dependency_lock=Path("requirements/demo.lock"),
  )
  write_demo_recipe(
      base_image=base_digest,
      runtime_artifact=demo_runtime,
      uid=10001,
      health_command=("python", "-m", "vespercode.demo.healthcheck"),
      command=("python", "-m", "vespercode.demo.app"),
  )
  ```

  The generated committed Dockerfile contains the real digest-pinned `FROM` line and exact curated artifact digest; the generator rejects a tag, missing digest, non-allowlisted module, or unhashed dependency.
- [ ] **Step 4: Run GREEN.** Build the Demo image and rerun Step 2. Expected: exit `0` with the exact shared pure-core modules present and every prohibited formal capability adapter absent.
- [ ] **Step 5: Refactor without behavior change.** Minimize build contexts/layers and keep reference and Demo runtime assets explicitly separate.
- [ ] **Step 6: Run both builds, Task 2 loopback round-trip, image smoke, and driver.** Run all commands using Task 2's frozen builder/output/registry inputs. Expected: all real-container contracts pass without skip; the reference OCI, loopback response, digest-pull, Task 2 GO `docker_image_digest`, and Task 6 manifest `docker_image_digest` are identical; registry cleanup is verified; no final manifest bytes occur in the image.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0` without OCI-smoke markers.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands plus image history/member scans. Expected: all exit `0` with no secret/prohibited member.
- [ ] **Step 9: Request spec compliance review.** Provide Task 34, Task 2 GO report, SPEC §1.4.5/§4.9/§8, recipes, build logs, inspections, digests, and smoke report.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rebuild both images, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of contexts, base/lock pinning, layer cache leakage, users/permissions, health, entry points, and separation.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rebuild, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add reference and Demo image smoke`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 34 PR.

### Milestone 35: Dual GitHub Actions and GitLab CI Contracts

**Execution notice:** Non-executable aggregate contract. Only Tasks 35.A–35.C are executable.

**Status:** Not started

**Goal:** Close both course CI loops: run exact no-publish GitHub Actions jobs on every push/pull request and exact GitLab jobs for offline, Windows wheel, image, and protected-release evidence.

**SPEC / FR / NFR / AC references:** SPEC §5.4 NFR-OBS; §5.5 release credentials; §8.4 in full; §9 CI choice; §10.1 AC-10–AC-12, AC-24, AC-30; §10.3 GitHub Actions/GitLab/package/image evidence; course common requirements for GitHub Actions on every push and `.gitlab-ci.yml` `unit-test`.

**Dependencies:** Tasks 33 and 34.

**Blocks:** Tasks 36–37.

**Parallelization:** Sequential after Tasks 33–34 because it integrates their exact commands and artifacts.

**Recommended branch:** `codex/task-35-dual-ci`

**Recommended worktree:** `.worktrees/task-35-dual-ci`

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.gitlab-ci.yml`
- Create: `scripts/verify_ci_contract.py`
- Create: `tests/unit/process/test_github_actions_contract.py`
- Create: `tests/unit/process/test_gitlab_ci_contract.py`
- Create: `tests/unit/process/test_ci_release_rules.py`
- Create: `tests/unit/process/test_ci_secret_boundaries.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 4 locked test/static commands; Task 33 wheel/pipx driver; Task 34 image drivers; GitHub push/pull-request/fork contexts; GitLab push/MR/main/protected-tag contexts; project-specific Windows 11 x64 runner.
- Produces:
  - GitHub Actions exact jobs `unit-test`, `reference-image-build`, and `demo-image-build`
  - GitLab exact jobs `unit-test`, `wheel-build-smoke`, `reference-image-build`, and `demo-image-build`
  - `verify_ci_contract(github_path: Path, gitlab_path: Path) -> DualCIContractResultV1`
  - GitHub workflow/test/image-smoke and GitLab JUnit/wheel/digest/pipx/image/Demo artifacts with retention
  - protected tag release stage that verifies GitLab commit, GitHub same-name tag commit, and wheel source commit before any publish operation

**Implementation points:**
- GitHub Actions `unit-test`, `reference-image-build`, and `demo-image-build` run on every push and pull request. The first runs locked Python 3.12 `python -m pytest -q`; both image jobs run Task 34 real builds and smoke. The reference job may use Task 2's credential-free loopback registry inside the job, but neither image job may contact an external registry.
- GitHub Actions declares only read permissions required to checkout; it accepts no publishing secrets, uses no release/external-registry login or push command, and works in fork pull requests without secret-dependent skips.
- GitLab `unit-test` runs on every push/MR in locked Python 3.12 and saves a report. `wheel-build-smoke` runs on every push/MR only on the project-specific Windows 11 x64 runner and executes Task 33.
- GitLab `reference-image-build` runs on every push/MR/protected version tag; `demo-image-build` runs on every MR and main push; both execute the exact Task 34 drivers.
- Express GitLab triggers with `rules` that avoid duplicate/missing pipelines. The dual contract test enumerates GitHub push/PR/fork and GitLab push/MR/main/protected/unprotected tag/fork contexts.
- GitHub Actions and ordinary GitLab push/MR/fork jobs receive no GitHub Release/GHCR/Render credentials and cannot log in to or push an external registry image or create a Release. Task 2/34's loopback-only registry round-trip remains allowed and must clean up within the job.
- Protected tag release uses distinct masked/protected least-privilege GitHub Release and GHCR credentials, verifies three-way commit identity first, pushes reference image, reads its registry RepoDigest, re-pulls by digest, smokes it, verifies the wheel manifest digest, then publishes the exact wheel and checksum.
- A missing Windows runner, failed upstream lookup, digest mismatch, unavailable image, or smoke failure fails the job and blocks merge/release.
- Pin CI images and dependency installation to reviewed locks. Do not print masked variables, Docker auth content, key values, or environment dumps.
- Save source commit, tool/runner versions, test categories, artifact digests, GitHub workflow/job URLs, GitLab pipeline/job URLs, and smoke results for Task 36 without claiming success until real runs finish.

**Intentionally failing test:**

```python
def test_both_ci_platforms_run_unit_tests_on_code_change(
    dual_ci_contract: DualCIContractResultV1,
) -> None:
    assert dual_ci_contract.github.job_names == {
        "unit-test", "reference-image-build", "demo-image-build"
    }
    assert dual_ci_contract.gitlab.job_names >= {
        "unit-test", "wheel-build-smoke",
        "reference-image-build", "demo-image-build",
    }
    assert dual_ci_contract.github.runs("unit-test", event="push")
    assert dual_ci_contract.github.runs("unit-test", event="pull_request")
    assert dual_ci_contract.gitlab.runs(
        "unit-test", event="merge_request", branch="feature"
    )
```

**Verification:**
- Target: `python -m pytest -q tests/unit/process/test_github_actions_contract.py::test_both_ci_platforms_run_unit_tests_on_code_change`
- Contract: `python scripts/verify_ci_contract.py .github/workflows/ci.yml .gitlab-ci.yml`
- Domain: `python -m pytest -q tests/unit/process/test_github_actions_contract.py tests/unit/process/test_gitlab_ci_contract.py tests/unit/process/test_ci_release_rules.py tests/unit/process/test_ci_secret_boundaries.py`
- Full: `python -m pytest -q`
- Real CI: push the Task 35 branch, open a GitHub pull request and GitLab merge request, and require every applicable mandatory job on both platforms; after merge require both platforms' main/push job sets.
- Expected: local contract/tests pass; GitHub shows three exact no-external-publish jobs for push/PR, GitLab shows four exact jobs/triggers with Windows runner use, both perform real image builds and local loopback round-trip where required, ordinary contexts have no external registry/release actions, and all required artifacts pass.

**Review gate:**
1. Spec compliance review performs a row-by-row comparison with §8.4 and both course CI requirements, verifying each platform/event context, real environment, saved evidence, no-publish GitHub boundary, and GitLab release order.
2. Code quality review checks both YAML files, reuse/readability, trigger/rule exclusivity, artifact flow, runner labels/tags, lock use, shell portability, secret scoping, and failure propagation.
3. Critical/Important findings or an absent/failed required real job block release and final delivery.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the dual-platform trigger RED test.** Add the exact test and parsers that evaluate GitHub events and GitLab rule contexts without contacting either platform.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because neither CI file exists.
- [ ] **Step 3: Implement the minimum mandatory CI jobs on both platforms.**

  ```yaml
  # .github/workflows/ci.yml
  on: [push, pull_request]
  permissions:
    contents: read
  jobs:
    unit-test:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - run: python -m pytest -q

  # .gitlab-ci.yml
  unit-test:
    stage: test
    script:
      - python -m pytest -q
    rules:
      - if: '$CI_PIPELINE_SOURCE == "push"'
      - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
  ```

  Record the reviewed `actions/checkout@v4` resolution in the dependency lock/evidence; add GitHub's two image jobs and GitLab's remaining three exact jobs with their frozen runners/triggers and Task 33/34 commands before GREEN.
- [ ] **Step 4: Run GREEN.** Re-run Step 2 and the contract command. Expected: exit `0` with exactly three GitHub jobs, all four GitLab mandatory jobs, and every required event match.
- [ ] **Step 5: Refactor without behavior change.** Use narrowly scoped per-platform reuse for locked setup and artifact handling without hiding job-specific triggers or credential permissions.
- [ ] **Step 6: Run domain tests and validate both real CI platforms.** Run local domain/contract commands, then push/open the GitHub PR and GitLab MR. Expected: every required job passes and saves platform-specific evidence.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands plus CI secret-boundary tests. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Provide Task 35, SPEC §8.4/AC-10–AC-12/AC-24/AC-30, both evaluated event matrices, actual workflow/pipeline job URLs, runner facts, permission/secret traces, and artifacts.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rerun Steps 6–8 in new runs on both platforms, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of events/rules, job isolation, GitHub permissions, Windows/Docker runners, locks, artifacts, GitLab release ordering, and credential exposure.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8 on both platforms, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add dual-platform CI contracts`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 35 PR.

### Milestone 36: GitHub Release, GHCR, and Render Deployment Evidence

**Execution notice:** Non-executable aggregate contract. Only Tasks 36.A–36.C are executable.

**Status:** Not started

**Goal:** Execute and record the protected content-addressed release, prove wheel/GHCR/manifest identity, deploy the capability-isolated Demo to Render, and verify the public service without inventing any external result.

**SPEC / FR / NFR / AC references:** SPEC §5.4–§5.6; §8.2–§8.4; §10.1 AC-10–AC-12, AC-24, AC-30; §10.3 package/public smoke; course CI/CD record and accessible WebUI URL deliverables.

**Dependencies:** Task 35 with passing GitHub Actions and GitLab main/source-commit runs.

**Blocks:** Task 37.

**Parallelization:** Sequential because tag, GHCR, Release, Render deployment, and evidence must bind one exact source commit and verified artifact set.

**Recommended branch:** `codex/task-36-release-deployment`

**Recommended worktree:** `.worktrees/task-36-release-deployment`

**Files:**
- Create: `render.yaml`
- Create: `src/vespercode/delivery/evidence.py`
- Create: `delivery/evidence/README.md`
- Create: `delivery/evidence/ci-v1.json` (populate only from real passing GitHub workflow and GitLab pipeline results)
- Create: `delivery/evidence/release-v1.json` (populate only from a real GitHub Release/GHCR result)
- Create: `delivery/evidence/deployment-v1.json` (populate only from a real Render deployment)
- Create: `scripts/verify_release_evidence.py`
- Create: `tests/smoke/release/test_evidence_schema.py`
- Create: `tests/smoke/release/test_commit_alignment.py`
- Create: `tests/smoke/release/test_manifest_image_alignment.py`
- Create: `tests/smoke/release/test_render_contract.py`
- Create: `tests/smoke/release/test_public_demo_smoke.py`
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 2 frozen `docker_image_digest` and loopback-registry evidence; Task 35 passing GitHub Actions workflow plus GitLab protected release pipeline; actual GitLab/GitHub/Render identities; version tag; wheel/digest; GHCR RepoDigest; Demo image/deployment; public health/scenario responses.
- Produces:
  - `ReleaseEvidenceV1`, `CIReleaseEvidenceV1`, and `DeploymentEvidenceV1`
  - `load_and_verify_release_evidence(root: Path, require_live: bool) -> DeliveryEvidenceResultV1`
  - a real GitHub Release URL with the exact versioned wheel and SHA-256
  - `ghcr.io/ledstevenovo/vespercode-reference@sha256:{registry_repo_digest}` verified by re-pull and smoke
  - a real Render public Demo URL verified at `/healthz` and through the fixed scenario

**Implementation points:**
- Before tagging/publishing, require passing latest GitHub Actions and GitLab CI results for the exact source commit, plus clean synchronization between GitLab commit, GitHub commit, intended tag commit, and wheel source commit.
- Human operators provide independent least-privilege protected GitHub Release, GHCR, and Render authorization through platform secret stores; never place values in files, commands, logs, artifacts, images, or responses.
- Run the protected tag pipeline. Rebuild or import the exact Task 2 single-platform OCI manifest using its frozen builder/output/media-type/compression/attestation inputs; fail before publishing when the local manifest digest differs from Task 2, or when any commit lookup, wheel digest, manifest, image build, or credential scope check is missing or inconsistent.
- Push the exact Task 2-identified manifest/blobs to GHCR, obtain the registry-returned RepoDigest, re-pull by digest, run tool/profile/reference smoke, and verify Task 2 loopback RepoDigest, wheel manifest `docker_image_digest`, GHCR RepoDigest, and pulled-image RepoDigest are identical. GHCR transformation or a rebuild mismatch is a release failure, never a reason to rewrite the manifest.
- Publish the exact wheel and adjacent SHA-256 to the matching GitHub Release; download them through the public Release path, rehash, clean-install, and start the local WebUI.
- Configure Render from `render.yaml` using the Demo Dockerfile, main branch, `/healthz`, platform PORT, no persistent disk, and no real key/socket/repository credential.
- Verify public health, simulated labeling, fixed trace, session isolation, and absence of local/recovery/real-provider endpoints. Record free-instance cold-start behavior without weakening health semantics.
- Evidence JSON stores only non-secret GitHub workflow/job and GitLab pipeline/job URLs/ids, commits, versions, timestamps, immutable digests, environment categories, and smoke outcomes; every object rejects unknown fields.
- The verifier checks live endpoints only when `require_live=true`; a local schema test cannot substitute for live release/deployment evidence.
- Any absent/non-terminal/failed external state leaves the task incomplete and the release readiness gate closed.

**Intentionally failing test:**

```python
def test_release_evidence_rejects_commit_misalignment(
    valid_release_evidence: dict[str, object],
) -> None:
    valid_release_evidence["github_tag_commit"] = "0" * 40
    with pytest.raises(ValidationError):
        ReleaseEvidenceV1.model_validate(valid_release_evidence)
```

**Verification:**
- Target: `python -m pytest -q -o addopts='' -m deployment_smoke tests/smoke/release/test_commit_alignment.py::test_release_evidence_rejects_commit_misalignment`
- Local schema/domain: `python -m pytest -q -o addopts='' -m deployment_smoke tests/smoke/release/test_evidence_schema.py tests/smoke/release/test_commit_alignment.py tests/smoke/release/test_manifest_image_alignment.py tests/smoke/release/test_render_contract.py`
- Live verification: `python scripts/verify_release_evidence.py delivery/evidence --require-live`
- Public smoke: `python -m pytest -q -o addopts='' -m deployment_smoke tests/smoke/release/test_public_demo_smoke.py`
- Full: `python -m pytest -q`
- Expected: schema checks pass; protected pipeline succeeds; downloaded wheel SHA verifies; Task 2 loopback digest, rebuilt local OCI digest, wheel manifest, GHCR RepoDigest, and pulled image agree; live Demo health/scenario/capability smoke passes.

**Review gate:**
1. Spec compliance review traces both §8 CI closures plus every release/deployment step, Task 2-to-GHCR digest continuity, credential boundary, and AC-10/11/12/24/30 evidence to real URLs/jobs/digests.
2. Code quality review checks evidence schema/verifier, Render config, live-smoke timeouts, secret minimization, immutable identities, and distinction between planned/local/live evidence.
3. Critical/Important findings or any missing/nonpassing external result block Task 37 and course delivery.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the commit-alignment RED test.** Add the exact test with valid-shaped evidence and one deliberately different tag commit.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because the release evidence schema does not exist.
- [ ] **Step 3: Implement the minimum closed alignment validator.**

  ```python
  @model_validator(mode="after")
  def require_one_source_commit(self) -> Self:
      commits = {
          self.gitlab_commit,
          self.github_tag_commit,
          self.wheel_source_commit,
      }
      if len(commits) != 1:
          raise ValueError("release source commits do not match")
      return self
  ```

- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0` because misaligned evidence is rejected.
- [ ] **Step 5: Refactor without behavior change.** Keep evidence schemas, local consistency checks, live probes, and platform configuration separate.
- [ ] **Step 6: Execute protected release/deployment and live verification.** Before external push, prove the rebuilt/imported OCI manifest digest equals Task 2; then use platform-protected credentials, require GHCR to return the same digest, pull by digest, and run the live verifier/public smoke. Expected: all external operations reach confirmed success with real immutable evidence and Task 2/local/wheel/GHCR/pulled identities agree.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0` without live deployment markers.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands and scan evidence/image histories for secret fields. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Provide Task 36, SPEC §8/§10.3, actual GitHub workflow and GitLab pipeline job URLs, Release/GHCR/Render URLs, digests, downloaded artifacts, and live smoke results.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, publish a new correctly versioned release if immutable artifacts changed, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality review.** Require inspection of evidence trust boundaries, live probe robustness, platform config, digest comparisons, secret hygiene, and artifact immutability.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8, and obtain passing quality re-review.
- [ ] **Step 13: Commit and record.** Commit real non-secret evidence with subject `Record release and Demo deployment`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 36 PR.

### Milestone 37: README, Process Evidence, Delivery Gate, and Human Reflection Checkpoint

**Execution notice:** Non-executable aggregate contract. Only Tasks 37.A–37.C are executable; the substantive reflection remains a separate human gate.

**Status:** Not started

**Goal:** Finish the required project artifacts, verify every implementation/review/release claim against real evidence, document secure use and limitations, and accept only a student-authored 1,500–2,500-word reflection.

**SPEC / FR / NFR / AC references:** SPEC §1.6; §5.3–§5.6; §8.1–§8.4; §10.1 AC-01–AC-31; §10.3; §11.3; course required artifacts, process evidence, README, CI/CD, WebUI URL, and reflection rules; `AGENTS.md` final-report rules.

**Dependencies:** Tasks 31–36 and 38, complete cold-start evidence, and a student-authored reflection draft.

**Blocks:** Final release readiness only.

**Parallelization:** Sequential final task; it verifies all prior evidence and must not race any task that updates `PLAN.md`, `AGENT_LOG.md`, delivery evidence, or README facts.

**Recommended branch:** `codex/task-37-delivery-docs`

**Recommended worktree:** `.worktrees/task-37-delivery-docs`

**Files:**
- Create: `README.md`
- Create: `scripts/verify_delivery.py`
- Create: `scripts/verify_reflection.py`
- Create: `tests/unit/process/test_readme_contract.py`
- Create: `tests/unit/process/test_delivery_evidence.py`
- Create: `tests/unit/process/test_reflection_contract.py`
- Modify: `SPEC_PROCESS.md` (cold-start/final process evidence only; preserve historical content)
- Modify: `AGENT_LOG.md` (append-only final chronology/evidence)
- Modify: `REFLECTION.md` (student owns substantive text; agent edits only disclosed language polish after explicit request)
- Modify: `PLAN.md` (final real task/evidence status only)

**Interfaces:**
- Consumes: every completed task record/commit/review/test; final SPEC/PLAN approval chain; real CI/release/deployment evidence; student-authored reflection.
- Produces:
  - complete `README.md`
  - `verify_delivery(root: Path, require_live: bool) -> DeliveryReadinessResultV1`
  - `verify_reflection(path: Path) -> ReflectionContractResultV1`
  - final append-only `SPEC_PROCESS.md`/`AGENT_LOG.md` evidence
  - one closed release-readiness report with no invented status

**Implementation points:**
- README documents prerequisites, Release download, SHA verification, local-wheel pipx install, directory layout, `vespercode serve`, run workflow, exact recovery preview/apply, secure credential set/status/update/clear, reference/LLM manifests, model/endpoint, Docker image digest verification, and limitations.
- Explain `NO_CONTENT_REDACTION_V1`, source scope/category disclosure, sensitive-path residual risk, pytest report-channel trust assumption, Win32/Docker boundaries, unsupported platforms/projects/operations, and every §1.6/§11.3 non-goal.
- Record real GitHub/GitLab project URLs, synchronization direction/method/date, GitHub Release URL, GHCR digest, Render URL/health path/cold start, and actual last-passing GitHub workflow/job plus GitLab pipeline/job evidence.
- `SPEC_PROCESS.md` contains brainstorming, at least three iterations, accepted/rejected suggestions, M0 SPEC path/SHA-256/blob/baseline/human approval, approved `PlanSemanticDigestV1` plus complete PLAN audit SHA-256, cold-start agent type/scope/pauses/findings/revisions/pass, and no fabricated approval or trial.
- `AGENT_LOG.md` remains chronological with timestamp, task id, skills, context, responsible subagent, human edits, real commits/PRs/reviews/tests, failures, interventions, and lesson for every significant task.
- Delivery verifier validates all 135 executable Task completion records and all 37 derived Milestone states, real SHAs in repository history, closed Critical/Important findings, required files, both CI platforms' exact job evidence, wheel/image/release/deployment alignment, no unresolved recovery, credential scan, and evidence freshness. It also requires `requirements/gate.lock`, all three `gates/` configs, `scripts/run_gate_checks.py`, the Task 2.D/2.E/2.F reporter/evidence/fingerprint producers, Task 1.E, 2.G, and 3.G GO reports, `config/dependency-closure-v1.json`, and `config/formal-toolchain-promotion-v1.json`; recomputed SHA-256/version matrices must match across all three reports and both records, and both persisted `python_version` values must equal Task 1.E terminal `GO` `GateToolchainEvidenceV1.python_version` character-for-character. The public `>=3.12,<3.13` range is checked separately and cannot satisfy exact identity. Milestone 2 evidence must prove digest-pinned loopback registry, loopback-only bind, zero credentials/external pushes, cleanup on every exit, no final-manifest image member, and local OCI/registry/digest-pull equality with final `ReferenceProfileManifestV1.docker_image_digest`; Task 36.B must prove GHCR returned the same digest.
- Reflection verifier checks 1,500–2,500 words, required disclosure of any AI language polishing, and presence of student-specific process analysis; it never generates or scores substantive personal reflection.
- Do not modify the reflection body unless the student supplies a complete draft and explicitly requests polishing. Record every agent edit/disclosure; otherwise report the checkpoint incomplete.
- Re-run all mandatory offline, Windows, Docker, E2E, fault, WebUI, package, image, and live smoke commands in their declared environments or bind the verifier to current saved real evidence.
- Make no new capability, compatibility branch, test exception, or scope promise in documentation.

**Intentionally failing test:**

```python
def test_readme_fails_when_release_digest_verification_is_missing(
    repository_copy: Path,
) -> None:
    write_readme_without_section(repository_copy, "Reference image digest verification")
    result = verify_delivery(repository_copy, require_live=False)
    assert result.ready is False
    assert "README_REFERENCE_DIGEST_INSTRUCTIONS_MISSING" in result.error_codes
```

**Verification:**
- Target: `python -m pytest -q tests/unit/process/test_readme_contract.py::test_readme_fails_when_release_digest_verification_is_missing`
- Domain: `python -m pytest -q tests/unit/process/test_readme_contract.py tests/unit/process/test_delivery_evidence.py tests/unit/process/test_reflection_contract.py`
- Offline full: `python -m pytest -q`
- Delivery: `python scripts/verify_delivery.py --root . --require-live`
- Reflection: `python scripts/verify_reflection.py REFLECTION.md`
- Expected: documentation/process/reflection contract tests pass; all environment evidence is current and passing; delivery reports ready only when every required real artifact and student reflection exists.

**Review gate:**
1. Spec compliance review checks README/process/log/reflection/delivery evidence against every course artifact, M0/semantic approval/cold-start records, gate bootstrap/reporter/probe identity continuity, Task 2 loopback-registry/no-self-reference evidence, Task 36 GHCR continuity, both CI closures, SPEC §8–§11, all AC rows, and explicit non-goals.
2. Code quality/editorial review checks verifier correctness, link/command accuracy, evidence freshness, privacy, no overclaim, readable structure, and disclosed limited reflection assistance.
3. Any Critical/Important finding, missing real evidence, false claim, absent student reflection, or live failure keeps final readiness closed.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the missing-README-section RED test.** Add the exact test using a disposable repository copy and no network.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because README/verifier contracts do not exist.
- [ ] **Step 3: Implement the minimum explicit documentation check.**

  ```python
  REQUIRED_README_SECTIONS = (
      "Installation from GitHub Release",
      "Reference image digest verification",
      "Secure credential lifecycle",
      "Disclosure boundary",
      "Recovery preview and apply",
      "Deployment architecture",
      "Known limitations and non-goals",
  )
  ```

  `verify_delivery` must parse real evidence schemas rather than search for success words.
- [ ] **Step 4: Run GREEN.** Create the accurate README section set and rerun Step 2. Expected: the focused fixture passes while missing sections remain rejected.
- [ ] **Step 5: Refactor without behavior change.** Separate README/process/task/commit/gate-bootstrap/CI/artifact/live/reflection checks and return all stable failures in one bounded report. The gate-bootstrap check recomputes file hashes, parses Task 1–3 GO matrices, strictly loads `config/dependency-closure-v1.json` and `config/formal-toolchain-promotion-v1.json`, and compares each record's exact `python_version` character-for-character with Task 1.E terminal `GO` evidence before comparing the remaining closure/promotion identities, all without executing untrusted project code.
- [ ] **Step 6: Run domain, full, delivery, and reflection checks.** Run all listed commands. Expected: all pass only with real current evidence and a valid student-authored reflection.
- [ ] **Step 7: Re-run required environment suites.** Run or verify current saved evidence for Windows, Docker, reference E2E, persistence faults, WebUI browser, package, OCI, CI, release, and public Demo. Expected: no required skip or stale result.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands plus a repository credential scan over tracked release artifacts. Expected: all exit `0`.
- [ ] **Step 9: Request spec compliance review.** Provide Task 37, course files, SPEC §8–§11/all AC rows, README, logs, process file, delivery report, and reflection authorship disclosure.
- [ ] **Step 10: Close spec findings.** Apply minimal factual/documentation/verifier corrections without authoring the reflection body, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality/editorial review.** Require inspection of every command/link, verifier false-positive/negative risks, evidence ages, security wording, non-goals, and AI-assistance disclosure.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important issues, rerun Steps 6–8, and obtain passing quality/editorial re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Complete verified course delivery`; capture SHA; append final evidence to this task and `AGENT_LOG.md`; commit the final evidence record; push and open one Task 37 PR.

### Milestone 38: Credential, Memory, Audit, and Recovery WebUI Workflows

**Execution notice:** Non-executable aggregate contract. Only Tasks 38.A–38.G are executable; Tasks 38.A–38.E own workflows, 38.F owns composition, and 38.G owns cross-workflow acceptance.

**Status:** Not started

**Goal:** Expose the remaining formal local operations—non-revealing credential lifecycle, workspace-scoped memory, redacted audit, and read-only-first recovery—through typed, secure, accessible pages plus the exact recovery CLI entry point whose sole production binding uses the complete v1 database composition, without duplicating or bypassing domain services.

**SPEC / FR / NFR / AC references:** SPEC §2 US-02 and US-06–US-08; §4.6 recovery; §4.7 FR-MEM; §4.8 FR-CRED; §4.9 local mode; §5.3–§5.6; §7 MemoryEntry/AuditEvent/PersistenceTransaction; §8.1–§8.2; §10.1 AC-08, AC-14, AC-16, AC-21–AC-24, AC-29; §10.3 local, Windows, and recovery verification.

**Dependencies:** Tasks 9, 22–23, 26–29.

**Blocks:** Tasks 31, 33, and 35–37.

**Parallelization:** Sequential after Task 29. Task 32 may execute alongside Task 29, but Task 38 begins after the Task 29 installer is merged so it can freeze the sole production route order.

**Recommended branch:** `codex/task-38-local-operations-web`

**Recommended worktree:** `.worktrees/task-38-local-operations-web`

**Files:**
- Create: `src/vespercode/web/local_composition.py`
- Create: `src/vespercode/web/routes_operations.py`
- Create: `src/vespercode/cli_composition.py`
- Create: `src/vespercode/web/routes_credentials.py`
- Create: `src/vespercode/web/routes_memory.py`
- Create: `src/vespercode/web/routes_recovery.py`
- Create: `src/vespercode/web/routes_audit.py`
- Create: `src/vespercode/web/templates/credential_status.html`
- Create: `src/vespercode/web/templates/memory.html`
- Create: `src/vespercode/web/templates/recovery_preview.html`
- Create: `src/vespercode/web/templates/audit.html`
- Test: `tests/web/test_credential_workflow.py`
- Test: `tests/web/test_memory_workflow.py`
- Test: `tests/web/test_audit_workflow.py`
- Test: `tests/web/test_recovery_workflow.py`
- Test: `tests/web/test_operations_accessibility.py`
- Test: `tests/web/test_local_composition.py`
- Test: `tests/unit/test_recovery_cli.py`
- Test: `tests/unit/test_cli_composition.py`
- Modify: `src/vespercode/cli.py` (Task 38.E adds only `recover --workspace PATH` parsing/typed delegation and its explicit `--apply` switch; Task 38.F adds only the production recover-handler binding)
- Modify: `PLAN.md` (completion record only)
- Modify: `AGENT_LOG.md` (append only)

**Interfaces:**
- Consumes: Task 7.D `ALL_V1_MIGRATIONS` through Task 38.F; Task 9 workspace identity/lease resolution; Task 22 `MemoryRepository.create/confirm/list/clear`; Task 23 `AuditRepository.list_run/clear_ended_run` and redacted `AuditPageV1`; Task 26 `RecoveryService.preview/apply`; Task 27 `CredentialService.set/status/update/clear`; Task 28 `LocalRouteInstallerV1`, `LocalShellPortsV1`, CLI root, local-session authorization, CSRF protection, and escaped template shell; Task 29 `RunGovernanceRouteInstallerV1` and `RunGovernanceWorkflowPortsV1`.
- Produces:
  - `LocalOperationsRouteInstallerV1(ports: LocalOperationsWorkflowPortsV1).install(app: FastAPI) -> None`
  - `LocalOperationsWorkflowPortsV1(credentials: CredentialWorkflowPortsV1, memory: MemoryWorkflowPortsV1, audit: AuditWorkflowPortsV1, recovery: RecoveryWorkflowPortsV1)`
  - `ProductionLocalWorkflowPortsV1(shell: LocalShellPortsV1, governance: RunGovernanceWorkflowPortsV1, operations: LocalOperationsWorkflowPortsV1)`
  - `build_local_route_installers(ports: ProductionLocalWorkflowPortsV1) -> LocalRouteInstallerSequenceV1`, returning exactly `(RunGovernanceRouteInstallerV1(ports.governance), LocalOperationsRouteInstallerV1(ports.operations))`
  - `build_local_application(ports: ProductionLocalWorkflowPortsV1, security: LocalWebSecurityConfigV1) -> FastAPI`, which calls Task 28 `create_local_app` with `ports.shell` and that exact installer tuple
  - Task 38.E `install_recover_command(app, recovery_handler: RecoveryCliHandlerV1) -> None`, accepting an injected Spy in unit tests and owning no production default
  - Task 38.F `bind_production_recover_command(app, database_path: Path, workspace_service: WorkspaceServiceV1) -> None`, which initializes the complete registry, constructs the Task 26 recovery service/handler, then injects it into Task 38.E
  - `CredentialWorkflowPortsV1.set(provider: Literal["OPENAI"], secret: SecretCredentialV1, event_id: str) -> CredentialMutationResultV1`
  - `CredentialWorkflowPortsV1.status(provider: Literal["OPENAI"]) -> CredentialStatusV1`
  - `CredentialWorkflowPortsV1.update(provider: Literal["OPENAI"], secret: SecretCredentialV1, event_id: str) -> CredentialMutationResultV1`
  - `CredentialWorkflowPortsV1.clear(provider: Literal["OPENAI"], event_id: str) -> CredentialMutationResultV1`
  - `MemoryWorkflowPortsV1.list(run_id: str) -> tuple[MemoryEntryV1, ...]`
  - `MemoryWorkflowPortsV1.create(command: CreateMemoryForRunV1) -> MemoryMutationResultV1`
  - `MemoryWorkflowPortsV1.confirm(command: ConfirmMemoryForRunV1) -> MemoryMutationResultV1`
  - `MemoryWorkflowPortsV1.clear(command: ClearMemoryForRunV1) -> MemoryMutationResultV1`
  - `AuditWorkflowPortsV1.list_run(run_id: str, page: AuditPageRequestV1) -> AuditPageV1`
  - `AuditWorkflowPortsV1.clear_ended_run(command: ClearEndedRunAuditV1) -> AuditClearResultV1`
  - `RecoveryWorkflowPortsV1.preview(run_id: str) -> RecoveryPreviewV1`
  - `RecoveryWorkflowPortsV1.apply(command: ApplyRecoveryForRunV1) -> RecoveryResultV1`
  - closed `CreateMemoryForRunV1`, `ConfirmMemoryForRunV1`, and `ClearMemoryForRunV1` commands containing a Run id, operation-specific visible input, and idempotency event id; none accepts a workspace identity
  - closed `ApplyRecoveryForRunV1(run_id, transaction_id, preview_digest, confirmation, event_id)`; the workflow resolves the authoritative workspace and constructs Task 26 `ApplyRecoveryV1`
  - `render_recovery_preview(preview: RecoveryPreviewV1) -> HTMLResponse`
  - CLI commands `vespercode recover --workspace PATH` for preview and `vespercode recover --workspace PATH --apply` for explicit application, both delegating to Task 26 after Task 9 identity/lease resolution
  - server-rendered credential, memory, audit, and recovery pages with closed form adapters and stable error projections

**Implementation points:**
- Register the four routers through `LocalOperationsRouteInstallerV1`; do not modify Task 28's `app.py`, import SQLite internals, inspect WinCred directly, read recovery backup bodies, or reproduce any domain predicate in a route.
- Build the sole production installer tuple in `local_composition.py` in the fixed order Task 29 run/governance routes then Task 38 local-operations routes. In `cli_composition.py`, apply Task 7.D's complete `ALL_V1_MIGRATIONS` through Task 7.A before constructing the Task 26 recovery repository/service and binding that handler to Task 38.E's parser. `vespercode serve` and installed `vespercode recover` use only these production compositions; tests and package smoke cannot substitute a source-only tuple or production handler.
- Credential entry uses only a password form body held for the duration of the Task 27 service call. Neither successful nor failed responses, templates, audit events, exception text, form redisplay, URLs, or logs contain the secret, its length, prefix/suffix, hash, or another derivative.
- Credential status shows only provider, configured state, and updated timestamp. Set/update/clear call the verified backend service and render explicit stable failures; a failed clear never displays an unconfigured state.
- Memory workspace identity is resolved server-side from the authorized Run/session. The UI permits user-authored `PROJECT_CONVENTION`, explicit confirmation, view, and clear, but exposes no model-originated generic write, cross-workspace selector, or field capable of changing policy, Manifest, approval, disclosure, configuration, or success conditions.
- Memory create/confirm pages show the untrusted/source status before mutation. Clear is idempotently bound to the exact workspace and entry; a stale, missing, or foreign entry changes no memory row.
- Audit pages paginate by Task 23's closed page request, preserve monotonic order, display only redacted payload projections, and never reveal full file/request/response bodies, credentials, backup bodies, or internal database fields.
- Audit clear is available only for an ended Run, is explicitly confirmed, and delegates to `clear_ended_run`; unresolved recovery evidence remains protected. Active-run, foreign-run, stale, or duplicate-invalid requests make zero deletion calls.
- Recovery begins with `preview`, which is read-only for the workspace, transaction, backups, and audit. The page shows transaction summary, every affected path, actual pre/post/unknown match status, proposed disposition, and the consequences of COMMITTED, ROLLED_BACK, or UNRESOLVED.
- Recovery apply requires a separate explicit confirmation bound to the current preview/run/workspace/transaction and an idempotency event id. It reacquires the Task 26 lease through the service; the UI offers no force-success, ignore, skip-path, edit-record, or user-declared-abandon control.
- Task 38.E parses `--workspace`, defaults to preview, invokes apply only for literal `--apply`, and delegates through an injected typed handler so `SpyRecoveryService` unit tests require no database or 7.D dependency. Task 38.F alone supplies the installed production handler: it resolves the workspace through Task 9, initializes the full registry before service construction, and delegates to Task 26. Neither layer accepts transaction edits, disposition override, force/ignore flags, credentials, secrets, or recovery-body arguments.
- `UNRESOLVED` remains visibly `RECOVERY_REQUIRED` and blocking. Only service-proven COMMITTED or ROLLED_BACK results render terminal next actions; routes never convert exceptions, stale previews, or partial results into success.
- Every state-changing request uses Task 28's session, Host, Origin, CSRF, closed-form, and idempotency checks before its first domain call. All untrusted text remains escaped, and forms use semantic labels, keyboard focus, live error regions, non-color-only states, and confirmation copy that names the exact effect.
- The Task 33 installed-WebUI smoke must invoke the production `vespercode serve` composition and prove both installers and all formal local capabilities are reachable without a service-locator or untyped port registry.

**Intentionally failing test:**

`local_web_client` and `operations_ports` are fixtures defined in `tests/web/test_recovery_workflow.py`; `SpyLocalOperationsPorts` implements the exact Task 38 protocols and exposes only call counters.

```python
def test_recovery_preview_is_read_only_and_has_no_force_control(
    local_web_client: TestClient,
    operations_ports: SpyLocalOperationsPorts,
) -> None:
    response = local_web_client.get(
        "/runs/run-recovery/recovery",
        headers=valid_local_security_headers(),
    )
    assert response.status_code == 200
    assert operations_ports.recovery_preview_call_count == 1
    assert operations_ports.recovery_apply_call_count == 0
    assert operations_ports.workspace_write_count == 0
    assert 'name="force"' not in response.text
    assert 'name="ignore"' not in response.text
```

**Verification:**
- Target: `python -m pytest -q tests/web/test_recovery_workflow.py::test_recovery_preview_is_read_only_and_has_no_force_control`
- Domain: `python -m pytest -q tests/web/test_credential_workflow.py tests/web/test_memory_workflow.py tests/web/test_audit_workflow.py tests/web/test_recovery_workflow.py tests/web/test_operations_accessibility.py tests/web/test_local_composition.py tests/unit/test_recovery_cli.py tests/unit/test_cli_composition.py`
- Full: `python -m pytest -q`
- Browser verification: start `vespercode serve` with deterministic fake application ports and exercise hidden credential set/status/update/clear, memory create/confirm/view/clear, paginated redacted audit/ended-run clear, and recovery preview → explicit apply using keyboard navigation.
- Expected: the production installer order is exact; secrets never enter output; workspace scoping and creator rules hold; audit remains redacted/ordered; WebUI and CLI preview perform zero writes; only explicit `--apply` can request recovery application; installed preview/apply both initialize the complete registry before Task 26 service construction; the parser remains independently testable with a Spy; no bypass control exists; service results govern recovery state; and all pages meet local security/accessibility requirements.

**Review gate:**
1. Spec compliance review traces every §4.6–§4.9 local capability, user operation, forbidden path, recovery disposition, creator/source rule, and credential/audit privacy rule to one route, test, and exact upstream service call.
2. Code quality plus UI/UX review checks installer and recovery-CLI production composition, registry-before-service ordering, parser/production-binding separation, form/CLI argument closure, server-derived scope, security ordering, idempotency, secret lifetime, escaped projections, accessible confirmations/errors, and absence of duplicated domain logic.
3. Critical/Important findings block E2E, package smoke, CI, release, and final delivery.

**Completion evidence:** Not yet executed. On completion record the actual commit SHA, responsible subagent, tests executed, review results, human edits and PR URL.

- [ ] **Step 1: Write the read-only-preview RED test.** Add the exact test with a valid local session, a fully populated recovery projection, and spies for preview, apply, and workspace writes.
- [ ] **Step 2: Run RED.** Run the target command. Expected: nonzero because the local operations installer and recovery route are not registered.
- [ ] **Step 3: Implement the minimum read-only recovery route.**

  ```python
  @router.get("/runs/{run_id}/recovery")
  def preview_recovery(
      run_id: str,
      ports: RecoveryWorkflowPortsV1 = Depends(recovery_workflow_ports),
  ) -> Response:
      preview = ports.preview(run_id)
      return render_recovery_preview(preview)
  ```

  `ports.preview` derives and authorizes the workspace from the Run/session and delegates to Task 26; the renderer has no apply side effect.
- [ ] **Step 4: Run GREEN.** Re-run Step 2. Expected: exit `0`, exactly one preview call, zero apply/workspace writes, and no force/ignore control.
- [ ] **Step 5: Refactor without behavior change.** Keep router installation, each workflow adapter, recovery CLI parsing, production recovery-CLI wiring, closed form parsing, and templates separated in the planned files; retain all credential/memory/audit/recovery predicates in Tasks 22, 23, 26, and 27.
- [ ] **Step 6: Run domain and browser tests.** Run the exact domain command and browser workflow. Expected: every operation succeeds or fails through its typed upstream service, with no secret output, cross-workspace access, audit-body leakage, recovery bypass, or accessibility failure.
- [ ] **Step 7: Run the unified offline suite.** Run `python -m pytest -q`. Expected: exit `0`.
- [ ] **Step 8: Run closure checks.** Run all five standard formatter/lint/type/credential/whitespace commands and scan rendered-response fixtures for the inert credential sentinel. Expected: all exit `0` and the sentinel is absent.
- [ ] **Step 9: Request spec compliance review.** Provide Task 38, SPEC §4.6–§4.9/§5.3–§5.6, route/service matrix, response fixtures, browser captures, and zero-side-effect spy evidence.
- [ ] **Step 10: Close spec findings.** Apply minimal corrections, rerun Steps 6–8, and obtain passing spec re-review.
- [ ] **Step 11: Request code quality and UI/UX review.** Require inspection of route/CLI boundaries, security/idempotency ordering, scope derivation, secret handling, pagination, confirmation semantics, safe rendering, keyboard/focus/error behavior, and installer composition.
- [ ] **Step 12: Close quality findings.** Close all Critical/Important code and UI findings, rerun Steps 6–8, repeat browser verification, and obtain passing re-review.
- [ ] **Step 13: Commit and record.** Commit with subject `Add local operations workflows`; capture SHA; update this task and `AGENT_LOG.md`; commit evidence; push and open one Task 38 PR.

## Executable Child Tasks for Split Milestones

The child tasks below are the only executable units for Milestones 1–12, 14–38 except retained executable Task 13. Their file ownership replaces the corresponding aggregate ownership row. Every child also modifies only its own tracking line in `PLAN.md` and appends its own evidence to `AGENT_LOG.md`.

#### Task 1.A: Hash-locked Feasibility Gate Bootstrap

**Status:** Not started

**Goal:** Create the sole Python 3.12 feasibility environment, frozen configs, and closed command runner used by every Task 1–3 proof.

**Dependencies:** None; M0 approval and cold-start PASS are non-task entry gates.

**Files:**
- Create: `requirements/gate.lock`
- Create: `gates/pytest.ini`
- Create: `gates/ruff.toml`
- Create: `gates/mypy.ini`
- Create: `scripts/run_gate_checks.py`
- Test: `tests/feasibility/gate/test_gate_bootstrap.py`

**Interfaces:** Produces `GateCommandV1 = Literal["pytest","ruff-format","ruff-check","mypy"]`, `GateArgumentSequenceV1`, an immutable ordered tuple of zero or more strings, `GateToolchainEvidenceV1(python_version: str, pytest_version: str, ruff_version: str, mypy_version: str, gate_lock_sha256: str, pytest_config_sha256: str, ruff_config_sha256: str, mypy_config_sha256: str, runner_sha256: str)`, and `run_gate_checks(command: GateCommandV1, arguments: GateArgumentSequenceV1) -> int`.

**Intentionally failing test:**

```python
class GateBootstrapContractTest(unittest.TestCase):
    def test_required_bootstrap_artifacts_are_declared(self) -> None:
        root = Path(__file__).resolve().parents[3]
        required = (
            "requirements/gate.lock",
            "gates/pytest.ini",
            "gates/ruff.toml",
            "gates/mypy.ini",
            "scripts/run_gate_checks.py",
        )
        missing = tuple(path for path in required if not (root / path).is_file())
        self.assertEqual(
            missing,
            (),
            "MISSING_BOOTSTRAP_ARTIFACTS:" + ",".join(missing),
        )
```

**Expected RED:** the entry-runnable stdlib test starts without `.venv-gate`, pytest, or `scripts/run_gate_checks.py` and fails its assertion with `MISSING_BOOTSTRAP_ARTIFACTS:` followed by the absent lock/config/runner paths; runner startup failure is not accepted.

**Implementation boundary:** Own only lock/config/runner identity and closed argv construction. Do not call Win32, Docker, persistence, or interpret any feasibility observation.

**Verification:**
- Target: `py -3.12 -m unittest -v tests.feasibility.gate.test_gate_bootstrap.GateBootstrapContractTest.test_required_bootstrap_artifacts_are_declared`
- Domain: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/gate/test_gate_bootstrap.py -q`
- Expected GREEN: the Target assertion passes after all five artifacts exist; hash-only installation succeeds; the Domain command exits `0`; wrong interpreter/config/digest/command cases fail closed.

**Completion evidence:** Not yet executed.

#### Task 1.B: Pure Workspace Boundary Observation Evaluator

**Status:** Not started

**Goal:** Evaluate closed lexical/final-object/ACL observations without touching the filesystem and return stable pass/fail codes.

**Dependencies:** Task 1.A.

**Files:**
- Create: `spikes/win32_workspace_boundary/evaluator.py`
- Test: `tests/feasibility/windows/test_workspace_boundary_evaluator.py`

**Interfaces:** Produces `BoundaryObservationV1(code: str, lexical_path: str, final_path: str, expected_volume_serial: int, observed_volume_serial: int, expected_file_id_128: bytes, observed_file_id_128: bytes, object_kind: Literal["FILE","DIRECTORY"], link_count: int, reparse_tag: int, acl_observable: bool)`, `BoundaryObservationSequenceV1`, an immutable ordered tuple of one or more observations, `BoundaryEvaluationV1(passed: bool, failed_codes: StableCodeSequenceV1)`, and pure `evaluate_workspace_observations(observations: BoundaryObservationSequenceV1) -> BoundaryEvaluationV1`.

**Intentionally failing test:**

```python
def test_unprovable_final_identity_fails_closed() -> None:
    result = evaluate_workspace_observations((unprovable_identity_observation(),))
    assert result.failed_codes == ("FINAL_OBJECT_IDENTITY_UNPROVEN",)
```

**Expected RED:** the closed evaluator and stable failure taxonomy do not exist.

**Implementation boundary:** Own only deterministic observation evaluation. Do not open paths, inspect ACLs, acquire mutexes, or create a GO report.

**Verification:**
- Target: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/windows/test_workspace_boundary_evaluator.py::test_unprovable_final_identity_fails_closed -q`
- Domain: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/windows/test_workspace_boundary_evaluator.py -q`
- Expected GREEN: every missing/mismatched/collision/reparse/link/ACL observation maps to one stable closed result and both commands exit `0`.

**Completion evidence:** Not yet executed.

#### Task 1.C: Real Win32 Object, Collision, and ACL Probe

**Status:** Not started

**Goal:** Produce real handle-derived identity, collision, reparse/hard-link, and ACL observations from a disposable NTFS workspace.

**Dependencies:** Tasks 1.A and 1.B.

**Files:**
- Create: `spikes/win32_workspace_boundary/object_probe.py`
- Test: `tests/feasibility/windows/test_workspace_object_probe.py`

**Interfaces:** Produces `WorkspaceObjectIdentityV1(canonical_absolute_path: str, volume_serial_number: int, file_id_128: bytes, object_kind: Literal["FILE","DIRECTORY"], link_count: int, reparse_tag: int)`, `WorkspaceObjectProbeResultV1(observations: BoundaryObservationSequenceV1, cleanup_verified: bool)`, and `probe_workspace_objects(workspace: Path, case_manifest: BoundaryCaseManifestV1) -> WorkspaceObjectProbeResultV1`.

**Intentionally failing test:**

```python
def test_junction_target_identity_is_observed_from_handle(ntfs_fixture: Path) -> None:
    result = probe_workspace_objects(ntfs_fixture, junction_case_manifest())
    assert result.observations[0].code == "REPARSE_OBJECT_REJECTED"
```

**Expected RED:** no handle-derived object probe exists; lexical normalization alone cannot satisfy the assertion.

**Implementation boundary:** Own real object/path/ACL observation and cleanup only. Do not acquire the workspace mutex or decide the aggregate GO outcome.

**Verification:**
- Target: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/windows/test_workspace_object_probe.py::test_junction_target_identity_is_observed_from_handle -q`
- Domain: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/windows/test_workspace_object_probe.py -q`
- Expected GREEN: all collision, device/UNC/ADS, reparse, hard-link, file/directory, and ACL fixtures produce closed observations and verified cleanup.

**Completion evidence:** Not yet executed.

#### Task 1.D: Cross-process Workspace Mutex Probe

**Status:** Not started

**Goal:** Prove two independent Windows processes cannot concurrently hold the same workspace-identity mutex.

**Dependencies:** Tasks 1.A and 1.B.

**Files:**
- Create: `spikes/win32_workspace_boundary/mutex_probe.py`
- Test: `tests/feasibility/windows/test_workspace_mutex_probe.py`

**Interfaces:** Produces `WorkspaceMutexProbeResultV1(workspace_identity_digest: str, contender_count: int, maximum_concurrent_holders: int, timeout_count: int, cleanup_verified: bool)` and `probe_workspace_mutex(workspace_identity_digest: str, contender_count: int, timeout_ms: int) -> WorkspaceMutexProbeResultV1`.

**Intentionally failing test:**

```python
def test_two_processes_never_hold_one_workspace_mutex_together() -> None:
    result = probe_workspace_mutex("a" * 64, contender_count=2, timeout_ms=2_000)
    assert result.maximum_concurrent_holders == 1
```

**Expected RED:** the cross-process mutex probe does not exist.

**Implementation boundary:** Own only mutex naming, acquisition timing, contender evidence, handle release, and cleanup. Do not inspect workspace paths or aggregate other observations.

**Verification:**
- Target: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/windows/test_workspace_mutex_probe.py::test_two_processes_never_hold_one_workspace_mutex_together -q`
- Domain: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/windows/test_workspace_mutex_probe.py -q`
- Expected GREEN: contention, timeout, abandoned-owner, distinct-workspace, and cleanup cases pass on Windows.

**Completion evidence:** Not yet executed.

#### Task 1.E: Workspace Boundary GO Report and Identity Continuity

**Status:** Not started

**Goal:** Assemble the exact Task 1 GO/NO-GO report only when bootstrap, object/ACL, and mutex evidence are complete and identity-consistent.

**Dependencies:** Tasks 1.A, 1.B, 1.C, and 1.D.

**Files:**
- Create: `spikes/win32_workspace_boundary/report.py`
- Create: `spikes/win32_workspace_boundary/probe.py`
- Test: `tests/feasibility/windows/test_workspace_boundary_gate.py`

**Interfaces:** Produces `WorkspaceBoundaryGateReportV1(outcome: Literal["GO","NO_GO"], gate_toolchain: GateToolchainEvidenceV1, object_probe: WorkspaceObjectProbeResultV1, mutex_probe: WorkspaceMutexProbeResultV1, evaluation: BoundaryEvaluationV1, evidence_digest: str)` and `assemble_workspace_boundary_report(toolchain: GateToolchainEvidenceV1, object_probe: WorkspaceObjectProbeResultV1, mutex_probe: WorkspaceMutexProbeResultV1) -> WorkspaceBoundaryGateReportV1`.

**Intentionally failing test:**

```python
def test_gate_refuses_go_when_mutex_evidence_is_missing() -> None:
    report = assemble_workspace_boundary_report(toolchain(), object_probe(), missing_mutex_probe())
    assert report.outcome == "NO_GO"
```

**Expected RED:** no closed report assembler enforces completeness and identity continuity.

**Implementation boundary:** Own only final report completeness, digest, and GO decision. Do not re-probe Windows or mutate Task 1.A–1.D evidence.

**Verification:**
- Target: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/windows/test_workspace_boundary_gate.py::test_gate_refuses_go_when_mutex_evidence_is_missing -q`
- Domain: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/windows/test_workspace_boundary_gate.py -q`
- Expected GREEN: only complete identity-matching evidence yields GO; all missing/drifted/unprovable evidence yields NO_GO.

**Completion evidence:** Not yet executed.

#### Task 2.A: Locked Reference Fixture and Build Input Contract

**Status:** Not started

**Goal:** Freeze one reference fixture, dependency lock, tool versions, and non-self-referential build-input manifest.

**Dependencies:** Task 1.E.

**Files:**
- Create: `requirements/reference.lock`
- Create: `reference/fixture/pyproject.toml`
- Create: `reference/fixture/requirements.lock`
- Create: `reference/fixture/src/vesper_fixture/calculator.py`
- Create: `reference/fixture/tests/test_calculator.py`
- Create: `spikes/docker_reference_boundary/input_contract.py`
- Test: `tests/feasibility/docker/test_reference_input_contract.py`

**Interfaces:** Produces `ReferenceBuildInputV1(base_image_digest: str, registry_image_digest: str, requirements_digest: str, fixture_tree_digest: str, tool_versions_digest: str, build_recipe_version: str)` and `freeze_reference_build_input(root: Path) -> ReferenceBuildInputV1`.

**Intentionally failing test:**

```python
def test_reference_lock_and_fixture_lock_must_be_byte_identical() -> None:
    assert freeze_reference_build_input(reference_root()).requirements_digest == fixture_lock_digest()
```

**Expected RED:** the closed build-input contract and dual-lock equality check do not exist.

**Implementation boundary:** Own fixture and locked input identities only. Do not build images, start registries, run checks, or write the final reference manifest.

**Verification:**
- Target: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_reference_input_contract.py::test_reference_lock_and_fixture_lock_must_be_byte_identical -q`
- Domain: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_reference_input_contract.py -q`
- Expected GREEN: exact lock/fixture/tool/build parameters freeze deterministically and reject drift.

**Completion evidence:** Not yet executed.

#### Task 2.B: Reproducible OCI Build and No-self-reference Proof

**Status:** Not started

**Goal:** Build the frozen reference image and prove its manifest is reproducible and contains no final manifest/digest self-reference.

**Dependencies:** Tasks 1.A and 2.A.

**Files:**
- Create: `containers/reference/Dockerfile`
- Create: `spikes/docker_reference_boundary/image_builder.py`
- Test: `tests/feasibility/docker/test_reference_image_reproducibility.py`

**Interfaces:** Produces `ReferenceImageBuildEvidenceV1(local_oci_manifest_digest: str, image_config_digest: str, recipe_digest: str, platform: str, self_reference_scan_passed: bool)` and `build_reference_image(build_input: ReferenceBuildInputV1) -> ReferenceImageBuildEvidenceV1`.

**Intentionally failing test:**

```python
def test_final_manifest_is_absent_from_image_members(build_fixture: BuildFixture) -> None:
    result = build_reference_image(build_fixture.input)
    assert result.self_reference_scan_passed is True
```

**Expected RED:** no reproducible builder or layer/config/annotation self-reference scan exists.

**Implementation boundary:** Own local OCI build/reproduction and no-self-reference inspection. Do not start a registry or execute validation checks.

**Verification:**
- Target: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_reference_image_reproducibility.py::test_final_manifest_is_absent_from_image_members -q`
- Domain: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_reference_image_reproducibility.py -q`
- Expected GREEN: repeated frozen builds yield the same single-platform OCI digest and no final manifest member.

**Completion evidence:** Not yet executed.

#### Task 2.C: Loopback Registry Lifecycle and Three-way Digest

**Status:** Not started

**Goal:** Push the exact local OCI manifest to a credential-free loopback registry, pull by digest, and verify cleanup plus three-way digest equality.

**Dependencies:** Tasks 1.A and 2.B.

**Files:**
- Create: `spikes/docker_reference_boundary/registry_probe.py`
- Test: `tests/feasibility/docker/test_loopback_registry_probe.py`

**Interfaces:** Produces `LoopbackRegistryEvidenceV1(registry_image_digest: str, bind_host: Literal["127.0.0.1"], assigned_port: int, credentials_used: Literal[False], external_push_count: Literal[0], local_oci_manifest_digest: str, registry_repo_digest: str, digest_pull_repo_digest: str, cleanup_verified: bool)` and `probe_loopback_registry(build: ReferenceImageBuildEvidenceV1) -> LoopbackRegistryEvidenceV1`.

**Intentionally failing test:**

```python
def test_registry_digest_transformation_fails() -> None:
    result = probe_loopback_registry(transformed_registry_fixture())
    assert result.registry_repo_digest == result.local_oci_manifest_digest
```

**Expected RED:** the loopback registry lifecycle and exact digest comparison do not exist.

**Implementation boundary:** Own registry bind/push/pull/cleanup evidence only. Do not build the image, execute fixture checks, or publish externally.

**Verification:**
- Target: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_loopback_registry_probe.py::test_registry_digest_transformation_fails -q`
- Domain: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_loopback_registry_probe.py -q`
- Expected GREEN: local/registry/pull digests match; credential, external bind/push, cleanup, and injected-failure cases close deterministically.

**Completion evidence:** Not yet executed.

#### Task 2.D: Reference Container Isolation Probe

**Status:** Not started

**Goal:** Prove one fresh reference container enforces the frozen no-network, non-root, read-only, bounded execution boundary.

**Dependencies:** Tasks 1.A and 2.B.

**Files:**
- Create: `spikes/docker_reference_boundary/execution_probe.py`
- Test: `tests/feasibility/docker/test_reference_container_isolation.py`

**Interfaces:** Produces `ContainerIsolationEvidenceV1(network_disabled: bool, non_root: bool, root_read_only: bool, capabilities_dropped: bool, docker_socket_absent: bool, workspace_read_only: bool, tmpfs_bounded: bool, cpu_limit: int, memory_limit_bytes: int, pid_limit: int, cleanup_verified: bool)` and `probe_reference_container(build: ReferenceImageBuildEvidenceV1, fixture: Path) -> ContainerIsolationEvidenceV1`.

**Intentionally failing test:**

```python
def test_workspace_write_attempt_is_rejected(reference_container: ReferenceContainer) -> None:
    evidence = probe_reference_container(reference_container.build, reference_container.fixture)
    assert evidence.workspace_read_only is True
```

**Expected RED:** no real container configuration probe produces closed isolation evidence.

**Implementation boundary:** Own container configuration/runtime isolation and cleanup observations. Do not interpret pytest results or compute fingerprints.

**Verification:**
- Target: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_reference_container_isolation.py::test_workspace_write_attempt_is_rejected -q`
- Domain: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_reference_container_isolation.py -q`
- Expected GREEN: every required runtime control is observed from a real container and cleanup is verified.

**Completion evidence:** Not yet executed.

#### Task 2.E: Authoritative Gate Pytest Evidence

**Status:** Not started

**Goal:** Emit complete explicitly loaded pytest lifecycle evidence for collection, full run, and target rerun inside the reference boundary.

**Dependencies:** Tasks 1.A and 2.D.

**Files:**
- Create: `spikes/docker_reference_boundary/pytest_reporter.py`
- Test: `tests/feasibility/docker/test_gate_pytest_evidence.py`

**Interfaces:** Produces `GatePytestEventSequenceV1`, an immutable ordered tuple of `GatePytestEventV1` values, `GatePytestReportV1(planned_node_ids: TestIdSequenceV1, collected_node_ids: TestIdSequenceV1, events: GatePytestEventSequenceV1, normal_end: bool, exit_code: int, integrity_digest: str)`, and `validate_gate_pytest_report(report: GatePytestReportV1) -> GatePytestEvidenceResultV1`.

**Intentionally failing test:**

```python
def test_missing_teardown_event_invalidates_gate_report() -> None:
    assert validate_gate_pytest_report(report_without_teardown()).passed is False
```

**Expected RED:** the explicit reporter and complete-event validator do not exist.

**Implementation boundary:** Own pytest event capture/completeness only. Do not decide Docker isolation, image identity, failure stability, or aggregate GO.

**Verification:**
- Target: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_gate_pytest_evidence.py::test_missing_teardown_event_invalidates_gate_report -q`
- Domain: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_gate_pytest_evidence.py -q`
- Expected GREEN: missing/truncated/duplicate/implicit/mismatched evidence fails and complete explicit reports pass.

**Completion evidence:** Not yet executed.

#### Task 2.F: Gate Failure Input Stability Probe

**Status:** Not started

**Goal:** Prove two independent target-failure runs produce byte-identical normalized gate fingerprint inputs without defining the production fingerprint.

**Dependencies:** Tasks 1.A and 2.E.

**Files:**
- Create: `spikes/docker_reference_boundary/failure_fingerprint_probe.py`
- Test: `tests/feasibility/docker/test_gate_failure_input_stability.py`

**Interfaces:** Produces `GateFailureFingerprintInputV1(node_id: str, phase: Literal["CALL"], outcome: Literal["FAIL"], normalized_message: str, location: CanonicalGateLocationV1)`, `GateFingerprintComparisonV1(equal: bool, left_digest: str, right_digest: str)`, `normalize_call_fail_input(report: GatePytestReportV1, node_id: str) -> GateFailureFingerprintInputV1`, and `compare_failure_inputs(left: GateFailureFingerprintInputV1, right: GateFailureFingerprintInputV1) -> GateFingerprintComparisonV1`.

**Intentionally failing test:**

```python
def test_independent_target_failures_have_identical_inputs() -> None:
    comparison = compare_failure_inputs(first_failure_input(), second_failure_input())
    assert comparison.equal is True
```

**Expected RED:** no gate-only normalization/comparison implementation exists.

**Implementation boundary:** Own gate-only normalized input comparison. Do not create production `FailureFingerprintV1`, run a registry, or decide GO.

**Verification:**
- Target: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_gate_failure_input_stability.py::test_independent_target_failures_have_identical_inputs -q`
- Domain: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_gate_failure_input_stability.py -q`
- Expected GREEN: stable independent inputs compare equal and every semantic input difference compares unequal.

**Completion evidence:** Not yet executed.

#### Task 2.G: Reference Profile Manifest and Docker Gate GO

**Status:** Not started

**Goal:** Freeze `ReferenceProfileManifestV1` and emit GO only when build, registry, isolation, pytest, and fingerprint evidence are complete and identity-consistent.

**Dependencies:** Tasks 1.E, 2.A, 2.B, 2.C, 2.D, 2.E, and 2.F.

**Files:**
- Create: `reference/manifest/reference-profile-v1.json`
- Create: `spikes/docker_reference_boundary/probe.py`
- Create: `spikes/docker_reference_boundary/report.py`
- Test: `tests/feasibility/docker/test_reference_boundary_gate.py`

**Interfaces:** Produces `ReferenceProfileManifestV1`, `DockerBoundaryGateReportV1(outcome: Literal["GO","NO_GO"], build_input: ReferenceBuildInputV1, build: ReferenceImageBuildEvidenceV1, registry: LoopbackRegistryEvidenceV1, isolation: ContainerIsolationEvidenceV1, pytest_evidence: GatePytestEvidenceResultV1, fingerprint: GateFingerprintComparisonV1, gate_toolchain: GateToolchainEvidenceV1, evidence_digest: str)`, and `assemble_reference_gate_report(command: AssembleReferenceGateReportV1) -> DockerBoundaryGateReportV1`.

**Intentionally failing test:**

```python
def test_gate_rejects_loopback_registry_digest_mismatch() -> None:
    assert assemble_reference_gate_report(mismatched_digest_command()).outcome == "NO_GO"
```

**Expected RED:** no final manifest/report assembler checks every producer identity.

**Implementation boundary:** Own final manifest/report bytes and GO decision only. Never rebuild, re-run, rewrite, authenticate to, or externally publish upstream evidence.

**Verification:**
- Target: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_reference_boundary_gate.py::test_gate_rejects_loopback_registry_digest_mismatch -q`
- Domain: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/docker/test_reference_boundary_gate.py -q`
- Expected GREEN: complete matching evidence yields GO; every missing/drifted/transformed input yields NO_GO.

**Completion evidence:** Not yet executed.

#### Task 3.A: Durable Persistence Transaction Protocol

**Status:** Not started

**Goal:** Define and durably record the sorted one-to-three-path PREPARED/WRITING/terminal transaction protocol without applying recovery.

**Dependencies:** Task 2.G.

**Files:**
- Create: `spikes/persistence_recovery/protocol.py`
- Test: `tests/feasibility/persistence/test_transaction_protocol.py`

**Interfaces:** Produces `GateWriteEntrySequenceV1`, an immutable ordered tuple of one to three `GateWriteEntryV1` values, `GateTransactionV1`, `GatePathRecordV1`, and `prepare_transaction(workspace: Path, entries: GateWriteEntrySequenceV1, deadline_ms: int, clock: ClockPort, faults: FaultPort) -> GateTransactionV1`.

**Intentionally failing test:**

```python
def test_prepare_rejects_two_create_operations() -> None:
    assert prepare_transaction(workspace(), two_create_entries(), 1_000, clock(), faults()).error_code == "TOO_MANY_CREATES"
```

**Expected RED:** the closed transaction protocol and entry validation do not exist.

**Implementation boundary:** Own durable transaction/path record creation and state invariants. Do not replace workspace files, evaluate deadlines, classify recovery, or inspect real identities.

**Verification:**
- Target: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_transaction_protocol.py::test_prepare_rejects_two_create_operations -q`
- Domain: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_transaction_protocol.py -q`
- Expected GREEN: invalid cardinality/order/preimage/state transitions fail before workspace mutation and valid PREPARED records persist.

**Completion evidence:** Not yet executed.

#### Task 3.B: Deterministic Write Fault Matrix

**Status:** Not started

**Goal:** Apply sorted CREATE/REPLACE operations with deterministic interruption around every replace and durable-state write.

**Dependencies:** Task 3.A.

**Files:**
- Create: `spikes/persistence_recovery/faults.py`
- Test: `tests/feasibility/persistence/test_write_fault_matrix.py`

**Interfaces:** Produces `PersistenceFaultPointV1`, `PersistenceFaultSequenceV1`, an immutable ordered tuple of all required fault points, `GatePersistenceResultV1`, and `apply_transaction(transaction_id: str, fault_point: PersistenceFaultPointV1, clock: ClockPort) -> GatePersistenceResultV1`.

**Intentionally failing test:**

```python
def test_interruption_after_each_replace_has_durable_observation() -> None:
    assert run_all_replace_faults(three_path_transaction()).missing_fault_points == ()
```

**Expected RED:** no complete enumerated fault matrix or write implementation exists.

**Implementation boundary:** Own sorted temp/flush/replace/progress writes and injected interruption points. Do not decide deadline policy, external-change safety, or recovery disposition.

**Verification:**
- Target: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_write_fault_matrix.py::test_interruption_after_each_replace_has_durable_observation -q`
- Domain: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_write_fault_matrix.py -q`
- Expected GREEN: every before/after PREPARED/WRITING/replace/progress/terminal fault point is observed deterministically.

**Completion evidence:** Not yet executed.

#### Task 3.C: Persistence Deadline Stop Semantics

**Status:** Not started

**Goal:** Stop before any write on pre-write expiry and stop all subsequent workspace writes after post-write expiry.

**Dependencies:** Tasks 3.A and 3.B.

**Files:**
- Create: `spikes/persistence_recovery/deadline.py`
- Test: `tests/feasibility/persistence/test_persistence_deadlines.py`

**Interfaces:** Produces `DeadlineDispositionV1 = Literal["STOPPED_ZERO_WRITE","RECOVERY_REQUIRED"]`, `DeadlineEvaluationV1(disposition: DeadlineDispositionV1, further_workspace_writes_allowed: bool)`, and `evaluate_persistence_deadline(transaction: GateTransactionV1, observed_write_count: int, now_ms: int) -> DeadlineEvaluationV1`.

**Intentionally failing test:**

```python
def test_deadline_after_first_replace_forbids_next_write() -> None:
    result = evaluate_persistence_deadline(expired_transaction(), observed_write_count=1, now_ms=2_000)
    assert result.further_workspace_writes_allowed is False
```

**Expected RED:** the explicit pre/post-first-write deadline evaluator does not exist.

**Implementation boundary:** Own pure deadline disposition and write-stop authorization. Do not inspect current file identity or apply rollback/recovery.

**Verification:**
- Target: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_persistence_deadlines.py::test_deadline_after_first_replace_forbids_next_write -q`
- Domain: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_persistence_deadlines.py -q`
- Expected GREEN: all deadline boundaries deterministically allow zero or no further writes as specified.

**Completion evidence:** Not yet executed.

#### Task 3.D: External-change and Object-identity Classifier

**Status:** Not started

**Goal:** Classify current bytes/object identity against preimage/postimage evidence and fail closed on any external or unprovable change.

**Dependencies:** Tasks 1.B, 3.A, and 3.B.

**Files:**
- Create: `spikes/persistence_recovery/observation.py`
- Test: `tests/feasibility/persistence/test_external_change_classifier.py`

**Interfaces:** Produces `GatePathObservationV1(path: str, content_digest: str, volume_serial: int, file_id_128: bytes, object_kind: str, supported: bool)`, `GatePathClassificationV1 = Literal["PREIMAGE","POSTIMAGE","ABSENT","EXTERNAL_CHANGE","UNPROVABLE"]`, and pure `classify_gate_path(record: GatePathRecordV1, observation: GatePathObservationV1) -> GatePathClassificationV1`.

**Intentionally failing test:**

```python
def test_same_bytes_with_replaced_object_is_external_change() -> None:
    assert classify_gate_path(record(), same_bytes_new_object()) == "EXTERNAL_CHANGE"
```

**Expected RED:** no byte-plus-object classifier exists.

**Implementation boundary:** Own pure observation classification. Do not read a workspace, decide aggregate recovery, or write/delete any path.

**Verification:**
- Target: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_external_change_classifier.py::test_same_bytes_with_replaced_object_is_external_change -q`
- Domain: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_external_change_classifier.py -q`
- Expected GREEN: byte/object mismatches and unprovable identities always classify unsafe.

**Completion evidence:** Not yet executed.

#### Task 3.E: Read-only Recovery Preview and Three-value Classification

**Status:** Not started

**Goal:** Produce a byte-for-byte read-only recovery preview with only COMMITTED, ROLLED_BACK, or UNRESOLVED.

**Dependencies:** Tasks 3.C and 3.D.

**Files:**
- Create: `spikes/persistence_recovery/recovery_preview.py`
- Test: `tests/feasibility/persistence/test_recovery_preview.py`

**Interfaces:** Produces `GateRecoveryDispositionV1 = Literal["COMMITTED","ROLLED_BACK","UNRESOLVED"]`, `GateRecoveryPreviewV1(transaction_id: str, disposition: GateRecoveryDispositionV1, path_classifications: GatePathClassificationSequenceV1, workspace_write_count: Literal[0])`, and `preview_recovery(workspace: Path, transaction_id: str) -> GateRecoveryPreviewV1`.

**Intentionally failing test:**

```python
def test_preview_is_byte_for_byte_read_only(preview_fixture: PreviewFixture) -> None:
    preview_recovery(preview_fixture.workspace, preview_fixture.transaction_id)
    assert preview_fixture.after_digest() == preview_fixture.before_digest()
```

**Expected RED:** no read-only preview/classifier exists.

**Implementation boundary:** Own observation collection and three-value preview only. Never change workspace, transaction log, or backups.

**Verification:**
- Target: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_recovery_preview.py::test_preview_is_byte_for_byte_read_only -q`
- Domain: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_recovery_preview.py -q`
- Expected GREEN: every mixed-path state maps to one disposition with zero writes.

**Completion evidence:** Not yet executed.

#### Task 3.F: Explicit Recovery Application

**Status:** Not started

**Goal:** Apply only a previously previewed safe recovery while holding the workspace mutex and preserve unknown/external objects.

**Dependencies:** Tasks 1.D and 3.E.

**Files:**
- Create: `spikes/persistence_recovery/recovery_apply.py`
- Test: `tests/feasibility/persistence/test_recovery_apply.py`

**Interfaces:** Produces `GateRecoveryCommandV1(workspace: Path, transaction_id: str, preview_digest: str, explicit_apply: Literal[True])`, `GateRecoveryResultV1(disposition: GateRecoveryDispositionV1, changed_paths: CanonicalPathSequenceV1, evidence_digest: str)`, and `apply_recovery(command: GateRecoveryCommandV1) -> GateRecoveryResultV1`.

**Intentionally failing test:**

```python
def test_apply_never_deletes_externally_replaced_create() -> None:
    result = apply_recovery(command_for_external_create())
    assert result.disposition == "UNRESOLVED"
```

**Expected RED:** no explicit mutex-bound recovery application exists.

**Implementation boundary:** Own explicit safe recovery writes and terminal record update. Do not infer intent without a bound preview or modify UNRESOLVED paths.

**Verification:**
- Target: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_recovery_apply.py::test_apply_never_deletes_externally_replaced_create -q`
- Domain: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_recovery_apply.py -q`
- Expected GREEN: only exact safe pre/postimage cases change and external/unprovable cases remain untouched.

**Completion evidence:** Not yet executed.

#### Task 3.G: Real NTFS Recovery Proof and Gate Report

**Status:** Not started

**Goal:** Run the complete fault/deadline/external-change/preview/apply matrix on disposable NTFS objects and emit the Task 3 GO/NO-GO report.

**Dependencies:** Tasks 1.E, 2.G, 3.A, 3.B, 3.C, 3.D, 3.E, and 3.F.

**Files:**
- Create: `spikes/persistence_recovery/report.py`
- Test: `tests/feasibility/persistence/test_recovery_gate.py`

**Interfaces:** Produces `FaultCaseResultSequenceV1`, an immutable ordered tuple of every required `FaultCaseResultV1`, `PersistenceRecoveryGateReportV1(outcome: Literal["GO","NO_GO"], cases: FaultCaseResultSequenceV1, gate_toolchain: GateToolchainEvidenceV1, workspace_probe_digest: str, evidence_digest: str)`, and `run_persistence_recovery_gate(workspace: Path) -> PersistenceRecoveryGateReportV1`.

**Intentionally failing test:**

```python
def test_missing_external_identity_case_forces_no_go(ntfs_workspace: Path) -> None:
    assert run_persistence_recovery_gate(ntfs_workspace).outcome == "NO_GO"
```

**Expected RED:** no real-environment coverage/identity aggregator exists.

**Implementation boundary:** Own real NTFS case execution, coverage completeness, cleanup, and final GO decision. Do not change the pure protocol/evaluators or silently reduce the matrix.

**Verification:**
- Target: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_recovery_gate.py::test_missing_external_identity_case_forces_no_go -q`
- Domain: `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py pytest -- tests/feasibility/persistence/test_recovery_gate.py -q`
- Expected GREEN: every named fault/deadline/external-change/preview/apply case runs on NTFS, cleanup is verified, and only a complete matrix yields GO.

**Completion evidence:** Not yet executed.

#### Task 4.A: Complete v1 Dependency Closure

**Status:** Not started

**Goal:** Create the minimal Python 3.12 project identity and freeze the sole complete, reviewed, hash-locked v1 runtime/build/development dependency closure without package, classification, marker, source, or lock ambiguity.

**SPEC references:** Milestone 4 project/tooling scope; SPEC §9; course one-command test and locked-tool requirements.

**Dependencies:** Tasks 1.E, 2.G, and 3.G.

**Files:**
- Create: `pyproject.toml`
- Create: `requirements/dev.lock`
- Create: `src/vespercode/__init__.py`
- Create: `src/vespercode/project/dependency_closure.py`
- Create: `config/dependency-closure-v1.json`
- Create: `scripts/bootstrap_formal_env.py`
- Test: `tests/unit/process/test_dependency_closure.py`

**Interfaces:** Consumes the declared PLAN Tech Stack, public Python range `>=3.12,<3.13`, exact Task 1.E terminal `GO` `GateToolchainEvidenceV1.python_version`, and unchanged Task 2.G/3.G identity matrices. `src/vespercode/project/dependency_closure.py` produces `DeclaredDependencySetV1(runtime_direct_names: tuple[str, ...], build_direct_names: tuple[str, ...], development_direct_names: tuple[str, ...])`, `LockedDistributionV1(name: str, version: str, classification: Literal["RUNTIME","BUILD","DEVELOPMENT"], python_marker: str, hashes: tuple[str, ...])`, `DependencyClosureV1(python_range: Literal[">=3.12,<3.13"], python_version: str, runtime_direct_names: tuple[str, ...], build_direct_names: tuple[str, ...], development_direct_names: tuple[str, ...], locked_distributions: tuple[LockedDistributionV1, ...], source_policy_digest: str, closure_digest: str)`, `DependencyClosureValidationReportV1(missing_direct: tuple[str, ...], extra_or_misclassified_direct: tuple[str, ...], missing_transitive_or_hash: tuple[str, ...], marker_or_source_mismatches: tuple[str, ...], gate_tool_version_mismatches: tuple[str, ...], python_version_mismatches: tuple[str, ...])`, `load_dependency_closure(root: Path) -> DependencyClosureV1`, and `validate_dependency_closure(root: Path, reviewed_plan_stack: DeclaredDependencySetV1) -> DependencyClosureValidationReportV1`. `scripts/bootstrap_formal_env.py` produces `bootstrap_formal_environment(root: Path, gate_evidence: GateToolchainEvidenceV1) -> FormalEnvironmentBootstrapResultV1`, where `FormalEnvironmentBootstrapResultV1(python_version: str, lock_sha256: str, installed_distribution_names: tuple[str, ...])`.

**Intentionally failing test:**

```python
def test_declared_v1_dependency_closure_is_complete(
    reviewed_plan_stack: DeclaredDependencySetV1,
    gate_evidence: GateToolchainEvidenceV1,
) -> None:
    report = validate_dependency_closure(Path("."), reviewed_plan_stack)
    record = load_dependency_closure(Path("."))
    assert record.python_version == gate_evidence.python_version
    assert report.missing_direct == ()
    assert report.extra_or_misclassified_direct == ()
    assert report.missing_transitive_or_hash == ()
    assert report.marker_or_source_mismatches == ()
    assert report.gate_tool_version_mismatches == ()
    assert report.python_version_mismatches == ()
```

Expected RED: import/configuration failure because the project dependency tables, source policy, hash-complete environment lock, closure validator/loader, unique persisted closure record, and verified formal environment do not exist.

**Implementation boundary:** This child is the sole owner of all `pyproject.toml` dependency tables, the public Python range, dependency source/index policy, minimal package identity, `requirements/dev.lock`, `src/vespercode/project/dependency_closure.py`, the unique persistent machine-readable non-secret `config/dependency-closure-v1.json`, and `scripts/bootstrap_formal_env.py`. It declares and classifies every direct runtime, build/distribution, and development/verification family listed by the PLAN; inventories every low-level HTTP/TestClient/template/form/server or typing/test package imported or invoked directly so none is hidden as a transitive; freezes every direct/transitive distribution and hash; preserves exact Task 1 Python/pytest/Ruff/Mypy versions; and writes the closure record only when its `python_version` equals Task 1.E terminal `GO` evidence character-for-character. Before creating, rebuilding, or using `.venv-formal`, the bootstrap locates the candidate only with `py -3.12`, reads that terminal `GO` identity, evaluates `platform.python_version() == gate_evidence.python_version`, and exits nonzero on mismatch. On equality it creates/rebuilds `.venv-formal` and invokes only `.venv-formal\Scripts\python.exe -m pip install --disable-pip-version-check --require-hashes --no-deps -r requirements/dev.lock`; this hash-only materialization is not a dependency change. The bootstrap never reads another worktree's `.venv-gate`, invokes an ambient bare `python`, resolves, upgrades, installs an undeclared distribution, or re-locks. This child does not configure the build backend, pytest markers, Ruff, Mypy, canonical commands, package data/version/distribution metadata/entry point, canonical values, paths, scanning, or application behavior. It never modifies Task 1–3 evidence or the separate gate/reference/Demo locks.

**Verification:**
- Bootstrap/rebuild: `py -3.12 scripts/bootstrap_formal_env.py`
- RED/Target GREEN: `.venv-formal\Scripts\python.exe -m pytest -q tests/unit/process/test_dependency_closure.py::test_declared_v1_dependency_closure_is_complete`
- Domain: `.venv-formal\Scripts\python.exe -m pytest -q tests/unit/process/test_dependency_closure.py`
- Expected GREEN: all checks exit `0`; the bootstrap proves exact Task 1 Python equality before environment creation/use; every declared direct family is present and correctly classified; every transitive distribution has exact hashes and a consistent Python marker/source policy; the lock, dependency tables, and unique persisted record agree; `record.python_version == gate_evidence.python_version`; and overlapping pytest/Ruff/Mypy versions exactly match Task 1.

**Completion evidence:** Not yet executed.

#### Task 4.F: Formal Toolchain Promotion

**Status:** Not started

**Goal:** Promote the exact Task 1 pytest/Ruff/Mypy identities, marker set, and static rules into the sole formal offline toolchain and configure the locked build backend without changing the completed dependency closure.

**SPEC references:** Milestone 4 project/tooling scope; SPEC §9 and §11.2; course one-command test and locked-tool requirements.

**Dependencies:** Tasks 1.E, 2.G, 3.G, and 4.A.

**Files:**
- Modify: `pyproject.toml` (build backend and pytest/Ruff/Mypy/tooling sections only)
- Create: `src/vespercode/project/toolchain_promotion.py`
- Create: `config/formal-toolchain-promotion-v1.json`
- Test: `tests/unit/process/test_toolchain_promotion.py`

**Interfaces:** Consumes `DependencyClosureV1` from Task 4.A, exact `GateToolchainEvidenceV1` from Task 1.A, unchanged Task 1.E/2.G/3.G terminal GO identity matrices, and the verified `.venv-formal` interpreter materialized only by Task 4.A's bootstrap; produces `FormalToolchainPromotionV1(python_version: str, gate_lock_sha256: str, pytest_version: str, ruff_version: str, mypy_version: str, marker_digest: str, static_rule_digest: str)`, `load_formal_toolchain_promotion(root: Path) -> FormalToolchainPromotionV1`, and the logical exact commands `python -m pytest -q`, `python -m ruff format --check .`, `python -m ruff check .`, and `python -m mypy src tests`, each executed through `.venv-formal\Scripts\python.exe`.

**Intentionally failing test:**

```python
def test_formal_toolchain_matches_frozen_gate_identity(
    gate_evidence: GateToolchainEvidenceV1,
) -> None:
    record = load_formal_toolchain_promotion(Path("."))
    assert record.python_version == gate_evidence.python_version
    assert record.gate_lock_sha256 == gate_evidence.gate_lock_sha256
    assert record.pytest_version == gate_evidence.pytest_version
    assert record.ruff_version == gate_evidence.ruff_version
    assert record.mypy_version == gate_evidence.mypy_version
```

**Expected RED:** import/configuration failure because the promotion loader, unique persisted promotion record, build backend, formal marker/static-rule configuration, and canonical commands do not exist.

**Implementation boundary:** This child solely owns `src/vespercode/project/toolchain_promotion.py` and the unique persistent machine-readable non-secret `config/formal-toolchain-promotion-v1.json`, and may modify only the build-system and pytest/Ruff/Mypy/tooling sections of Task 4.A-owned `pyproject.toml`. It consumes but never owns, creates, repairs, or mutates `.venv-formal` or `scripts/bootstrap_formal_env.py`. It first requires `.venv-formal\Scripts\python.exe` to report exactly the Task 1.E terminal `GO` `python_version`, then persists the same exact value. It registers exactly `windows_integration`, `docker_integration`, `reference_e2e`, `package_smoke`, `oci_smoke`, and `deployment_smoke`; excludes those six markers from the default offline suite; makes every dedicated environment command clear default addopts, select exactly one marker, and name its test root; and records the gate-to-formal comparison. It may not add/remove/resolve/install a package, change dependency tables, Python range, minimal package identity, dependency source/index policy, `requirements/dev.lock`, or any separate lock. Discovery of a missing package stops this task and triggers the global dependency-change rule.

**Verification:**
- Bootstrap/rebuild through the Task 4.A-owned consumer interface: `py -3.12 scripts/bootstrap_formal_env.py`
- RED/Target GREEN: `.venv-formal\Scripts\python.exe -m pytest -q tests/unit/process/test_toolchain_promotion.py::test_formal_toolchain_matches_frozen_gate_identity`
- Domain: `.venv-formal\Scripts\python.exe -m pytest -q tests/unit/process/test_dependency_closure.py tests/unit/process/test_toolchain_promotion.py`
- Closure: `.venv-formal\Scripts\python.exe -m ruff format --check .`; `.venv-formal\Scripts\python.exe -m ruff check .`; `.venv-formal\Scripts\python.exe -m mypy src tests`
- Expected GREEN: all commands exit `0`; `record.python_version == gate_evidence.python_version`; all recorded tool versions/hashes equal frozen gate and dependency evidence; the six real-environment markers are excluded from the default suite; dedicated commands are closed; and dependency tables/lock/source policy plus the Task 4.A closure record are byte-identical to Task 4.A output.

**Completion evidence:** Not yet executed.

#### Task 4.B: Canonical JSON Bytes and Domain-separated Digests

**Status:** Not started

**Goal:** Encode every v1 canonical value into exact bytes and compute the sole domain-separated SHA-256 identity.

**SPEC references:** Milestone 4 canonical-byte scope; SPEC §0.1 CTV-01–CTV-07 and AC-10/AC-26.

**Dependencies:** Task 4.F.

**Files:**
- Create: `src/vespercode/canonical/json_v1.py`
- Create: `src/vespercode/canonical/digest.py`
- Test: `tests/unit/canonical/test_json_v1.py`
- Test: `tests/unit/canonical/test_digest_vectors.py`

**Interfaces:** Produces recursive `CanonicalValueV1 = str | int | bool | CanonicalArrayV1 | Mapping[str, CanonicalValueV1]`, where `CanonicalArrayV1` is an immutable ordered tuple of zero or more `CanonicalValueV1` items; also produces `canonical_json_bytes(value: CanonicalValueV1) -> bytes` and `domain_digest(object_type: str, schema_version: int, value: Mapping[str, CanonicalValueV1]) -> str`.

**Intentionally failing test:**

```python
def test_ctv_01_exact_bytes_and_digest() -> None:
    value = {"tags": (), "schema_version": 1, "optional_note": {"kind": "ABSENT"}, "label": "x"}
    assert canonical_json_bytes(value) == b'{"label":"x","optional_note":{"kind":"ABSENT"},"schema_version":1,"tags":[]}'
    assert domain_digest("CanonicalizationProbeV1", 1, value) == "1923bd578b2110ae145622050b4b6d10171c4b8fca4a383be06fa9f78d1ca782"
```

Expected RED: import failure because `canonical_json_bytes` and `domain_digest` do not exist.

**Implementation boundary:** This child owns Unicode-scalar validation, canonical encoding, and digest prefixing only; it does not parse time, validate paths, scan files, or choose tool versions.

**Verification:**
- Target: `python -m pytest -q tests/unit/canonical/test_digest_vectors.py::test_ctv_01_exact_bytes_and_digest`
- Domain: `python -m pytest -q tests/unit/canonical/test_json_v1.py tests/unit/canonical/test_digest_vectors.py`
- Expected GREEN: both commands exit `0`; CTV-01–CTV-07 exact bytes/digests and all forbidden scalar/value cases pass.

**Completion evidence:** Not yet executed.

#### Task 4.C: Canonical Timestamp and Injectable Clock

**Status:** Not started

**Goal:** Accept only the v1 UTC millisecond timestamp form and make every current-time observation injectable and deterministic.

**SPEC references:** Milestone 4 time scope; SPEC §0.1 canonical timestamp and clock rules.

**Dependencies:** Task 4.B.

**Files:**
- Create: `src/vespercode/canonical/timestamp_v1.py`
- Create: `src/vespercode/canonical/clock.py`
- Test: `tests/unit/canonical/test_timestamp_v1.py`
- Test: `tests/unit/canonical/test_clock.py`

**Interfaces:** Produces `CanonicalTimestampV1.parse(value: str) -> CanonicalTimestampV1`, `CanonicalTimestampV1.from_epoch_milliseconds(value: int) -> CanonicalTimestampV1`, protocol `ClockV1.now() -> CanonicalTimestampV1`, `SystemClockV1`, and `FakeClockV1.advance(milliseconds: int) -> None`.

**Intentionally failing test:**

```python
def test_fake_clock_advances_exact_milliseconds() -> None:
    clock = FakeClockV1.from_epoch_milliseconds(0)
    clock.advance(milliseconds=1)
    assert clock.now().value == "1970-01-01T00:00:00.001Z"
```

Expected RED: import failure because the timestamp and clock types do not exist.

**Implementation boundary:** This child owns Gregorian parsing, epoch-millisecond conversion, and clock injection only; it adds no decision, expiry, lifecycle, or filesystem policy.

**Verification:**
- Target: `python -m pytest -q tests/unit/canonical/test_clock.py::test_fake_clock_advances_exact_milliseconds`
- Domain: `python -m pytest -q tests/unit/canonical/test_timestamp_v1.py tests/unit/canonical/test_clock.py`
- Expected GREEN: both commands exit `0`; exact formatting, invalid-date/leap-second rejection, and deterministic advancement pass.

**Completion evidence:** Not yet executed.

#### Task 4.D: Lexical Canonical Relative Path

**Status:** Not started

**Goal:** Reject every unsupported lexical path form before any filesystem access and return the sole canonical relative-path representation.

**SPEC references:** Milestone 4 lexical-path scope; SPEC §0.1 path rules and §1.4.2 boundaries.

**Dependencies:** Task 4.C.

**Files:**
- Create: `src/vespercode/canonical/path_v1.py`
- Test: `tests/unit/canonical/test_path_v1.py`

**Interfaces:** Produces `CanonicalRelativePathV1(value: str)` and `validate_canonical_relative_path(value: str) -> CanonicalRelativePathV1`.

**Intentionally failing test:**

```python
def test_device_and_parent_paths_are_rejected() -> None:
    for value in ("CON", "src/../a.py", r"C:\src\a.py", "//server/share/a.py"):
        with pytest.raises(CanonicalPathErrorV1):
            validate_canonical_relative_path(value)
```

Expected RED: import failure because the canonical path validator does not exist.

**Implementation boundary:** This child performs lexical validation only. Final-object identity, ancestry, alias, reparse, ADS, and link authorization remain Tasks 9.A and 9.D.

**Verification:**
- Target: `python -m pytest -q tests/unit/canonical/test_path_v1.py::test_device_and_parent_paths_are_rejected`
- Domain: `python -m pytest -q tests/unit/canonical/test_path_v1.py`
- Expected GREEN: both commands exit `0`; root/absolute/device/ADS/dot/trailing/reserved-name sentinels are rejected deterministically.

**Completion evidence:** Not yet executed.

#### Task 4.E: Redacted Changed-file Credential Scanner

**Status:** Not started

**Goal:** Fail a changed-file credential scan on a match while reporting only bounded paths and rule ids and never the matched value.

**SPEC references:** Milestone 4 scanner scope; course credential rules; repository pre-commit scan requirement.

**Dependencies:** Task 4.D.

**Files:**
- Create: `scripts/scan_credentials.py`
- Test: `tests/unit/process/test_scan_credentials.py`

**Interfaces:** Produces `CredentialScanFindingV1(path: str, rule_id: str)`, `CredentialScanFindingSequenceV1`, an immutable ordered tuple of zero or more findings, `CredentialScanReportV1(findings: CredentialScanFindingSequenceV1, scanned_file_count: int)`, `scan_changed_files(paths: Sequence[Path]) -> CredentialScanReportV1`, and CLI `python scripts/scan_credentials.py --changed --redact --fail-on-match`.

**Intentionally failing test:**

```python
def test_scanner_reports_rule_without_matched_value(tmp_path: Path) -> None:
    candidate = tmp_path / "sample.txt"
    candidate.write_text("api_key=test-sentinel-value", encoding="utf-8")
    report = scan_changed_files((candidate,))
    rendered = report.model_dump_json()
    assert report.findings[0].rule_id == "GENERIC_API_KEY"
    assert "test-sentinel-value" not in rendered
```

Expected RED: import failure because the changed-file scanner does not exist.

**Implementation boundary:** This child reads only an explicit path list, treats binary input as non-text, and emits no file contents, match offsets, derivatives, or network requests.

**Verification:**
- Target: `python -m pytest -q tests/unit/process/test_scan_credentials.py::test_scanner_reports_rule_without_matched_value`
- Domain: `python -m pytest -q tests/unit/process/test_scan_credentials.py`
- Expected GREEN: both commands exit `0`; match/no-match/binary/path-error cases are bounded and no sentinel is printed.

**Completion evidence:** Not yet executed.

#### Task 5.A: Closed Optional-value Contracts

**Status:** Not started

**Goal:** Define closed generic optional-value objects so every absent/present field is explicit and cannot collapse into nullable ambiguity.

**Dependencies:** Task 4.F.

**Files:**
- Create: `src/vespercode/contracts/optional.py`
- Test: `tests/unit/contracts/test_optional.py`

**Interfaces:** Produces `AbsentV1`, `PresentV1[T]`, and every named closed optional union required by SPEC.

**Intentionally failing test:**

```python
def test_present_optional_requires_value() -> None:
    with pytest.raises(ValidationError):
        PresentV1[str].model_validate({"kind": "PRESENT"})
```

**Expected RED:** the closed generic present/absent optional union does not exist.

**Implementation boundary:** Own optional-value schemas only. Do not define repository locations, disclosure scopes, Run state, actions, evidence, profile matching, or persistence behavior.

**Verification:**
- Target: `python -m pytest -q tests/unit/contracts/test_optional.py::test_present_optional_requires_value`
- Domain: `python -m pytest -q tests/unit/contracts/test_optional.py`
- Expected GREEN: every named present/absent union round-trips, missing/unknown/mixed variants reject deterministically, and both commands exit `0`.

**Completion evidence:** Not yet executed.

#### Task 5.B: Run, Phase, Wait, and Limit Contracts

**Status:** Not started

**Goal:** Define the closed Run state/phase/wait/limit vocabulary and exact specialized wait-decision envelope.

**Dependencies:** Tasks 4.C and 5.A.

**Files:**
- Create: `src/vespercode/contracts/run.py`
- Test: `tests/unit/contracts/test_run.py`

**Interfaces:** Produces `RunStatus`, `RunPhase`, `RunStateV1`, `WaitKind`, `RunLimitsV1`, `WaitContextV1`, `WaitDecisionChoiceV1 = Literal["APPROVE","REJECT"]`, and `WaitDecisionV1(wait_id: str, run_id: str, wait_kind: WaitKind, subject_digest: DigestV1, decision: WaitDecisionChoiceV1, event_id: str, decided_at: CanonicalTimestampV1)`.

**Intentionally failing test:**

```python
def test_running_state_requires_exact_phase() -> None:
    with pytest.raises(ValidationError):
        RunStateV1.model_validate({"status": "RUNNING"})
```

**Expected RED:** the closed Run/wait state contracts do not exist.

**Implementation boundary:** Own value-object validation only. Do not implement lifecycle transitions, repositories, decision services, or clocks.

**Verification:**
- Target: `python -m pytest -q tests/unit/contracts/test_run.py::test_running_state_requires_exact_phase`
- Domain: `python -m pytest -q tests/unit/contracts/test_run.py`
- Expected GREEN: every legal state/phase/wait/limit combination round-trips and every illegal combination rejects.

**Completion evidence:** Not yet executed.

#### Task 5.C: Action, Policy-decision, and Result Contracts

**Status:** Not started

**Goal:** Define the shared closed action identity, policy decision, stable action error, and action-result envelopes.

**Dependencies:** Tasks 4.B, 5.A, and 5.B.

**Files:**
- Create: `src/vespercode/contracts/action.py`
- Test: `tests/unit/contracts/test_action.py`

**Interfaces:** Produces `CheckPlanIdV1 = Literal["TARGET_TESTS","FULL_PYTEST","RUFF","MYPY"]`, `ActionStatusV1`, `PolicyDecisionV1`, `ActionErrorV1`, `ActionResultV1`, and `ActionInstanceV1(action_id: str, semantic_digest: str, instance_digest: str, action: SharedActionV1)`.

**Intentionally failing test:**

```python
def test_success_result_rejects_error_payload() -> None:
    with pytest.raises(ValidationError):
        ActionResultV1.model_validate(success_with_error_payload())
```

**Expected RED:** no closed action/result union enforces payload/status consistency.

**Implementation boundary:** Own schemas and cross-field validation only. Do not parse model JSON, evaluate policy, dispatch, or execute checks.

**Verification:**
- Target: `python -m pytest -q tests/unit/contracts/test_action.py::test_success_result_rejects_error_payload`
- Domain: `python -m pytest -q tests/unit/contracts/test_action.py`
- Expected GREEN: legal actions/results validate and unknown/mixed/contradictory envelopes reject.

**Completion evidence:** Not yet executed.

#### Task 5.D: Evidence, Artifact, Digest, and Stable Error Contracts

**Status:** Not started

**Goal:** Define the shared closed evidence/artifact/digest/location vocabulary consumed across tools, validation, audit, and delivery.

**Dependencies:** Tasks 4.B, 5.A, 5.B, 5.C, and 5.E.

**Files:**
- Create: `src/vespercode/contracts/evidence.py`
- Test: `tests/unit/contracts/test_evidence.py`

**Interfaces:** Produces `ArtifactRefV1`, `DigestV1`, `StableControlErrorV1`, `EvidenceLocationV1`, `StableCodeSequenceV1`, an immutable ordered tuple of zero or more stable error codes, and common closed evidence-envelope validation.

**Intentionally failing test:**

```python
def test_artifact_reference_rejects_unbound_digest() -> None:
    with pytest.raises(ValidationError):
        ArtifactRefV1.model_validate({"artifact_id": "a1", "digest": ""})
```

**Expected RED:** the shared evidence/artifact contract does not exist.

**Implementation boundary:** Own shared evidence schemas only. Do not create artifacts, store bytes, append audit events, or interpret validation outcomes.

**Verification:**
- Target: `python -m pytest -q tests/unit/contracts/test_evidence.py::test_artifact_reference_rejects_unbound_digest`
- Domain: `python -m pytest -q tests/unit/contracts/test_evidence.py`
- Expected GREEN: every evidence variant is closed/digest-bound and invalid/unknown combinations reject.

**Completion evidence:** Not yet executed.

#### Task 5.E: Repository-location and Disclosure-scope Contracts

**Status:** Not started

**Goal:** Define canonical repository-location and disclosure-path-scope value objects with no ambiguous root/path representation.

**Dependencies:** Task 4.E.

**Files:**
- Create: `src/vespercode/contracts/location.py`
- Test: `tests/unit/contracts/test_location.py`

**Interfaces:** Produces `RepositoryLocationV1 = RootLocationV1 | PathLocationV1` and `DisclosurePathScopeV1 = RootScopeV1 | FileScopeV1 | DirectoryScopeV1`.

**Intentionally failing test:**

```python
def test_repository_root_rejects_path_field() -> None:
    with pytest.raises(ValidationError):
        RootLocationV1.model_validate({"kind": "ROOT", "path": "src"})
```

**Expected RED:** the closed discriminated repository-location and disclosure-scope unions do not exist.

**Implementation boundary:** Own repository-location and disclosure-scope schemas only. Do not define generic optional values, Run state, actions, evidence, profile matching, or persistence behavior.

**Verification:**
- Target: `python -m pytest -q tests/unit/contracts/test_location.py::test_repository_root_rejects_path_field`
- Domain: `python -m pytest -q tests/unit/contracts/test_location.py`
- Expected GREEN: all unknown/ambiguous/root/path/scope variants reject deterministically and both commands exit `0`.

**Completion evidence:** Not yet executed.

#### Task 6.A: Immutable Editable-path Policy

**Status:** Not started

**Goal:** Implement the sole built-in editable path/operation policy and deterministic segment-boundary matching.

**Dependencies:** Tasks 4.D and 5.D.

**Files:**
- Create: `src/vespercode/profiles/editable.py`
- Test: `tests/unit/profiles/test_editable.py`

**Interfaces:** Produces `EditableOperationV1 = Literal["CREATE","REPLACE"]`, `EditablePathPolicyV1(policy_digest: str, roots: CanonicalPathSequenceV1, operations: EditableOperationSequenceV1)`, and `EditablePathPolicyV1.matches(path: CanonicalRelativePathV1, operation: EditableOperationV1) -> bool`.

**Intentionally failing test:**

```python
def test_src_prefix_without_segment_boundary_is_not_editable() -> None:
    assert built_in_editable_policy().matches(path("src_backup/x.py"), "REPLACE") is False
```

**Expected RED:** the immutable segment-boundary policy does not exist.

**Implementation boundary:** Own only built-in editable path/operation matching and digest. Do not resolve profiles, endpoints, requests, or mutable overrides.

**Verification:**
- Target: `python -m pytest -q tests/unit/profiles/test_editable.py::test_src_prefix_without_segment_boundary_is_not_editable`
- Domain: `python -m pytest -q tests/unit/profiles/test_editable.py`
- Expected GREEN: only canonical `src` descendants and CREATE/REPLACE match; aliases and overrides reject.

**Completion evidence:** Not yet executed.

#### Task 6.B: Reference Profile Manifest Contract

**Status:** Not started

**Goal:** Load and integrity-check the built-in reference manifest against Task 2.G image, lock, tool, execution, and check-plan evidence.

**Dependencies:** Tasks 2.G, 4.B, and 5.D.

**Files:**
- Create: `src/vespercode/profiles/reference.py`
- Create: `src/vespercode/profiles/builtin/reference-profile-v1.json`
- Test: `tests/unit/profiles/test_reference.py`
- Modify: `reference/manifest/reference-profile-v1.json` (synchronize only after digest validation)

**Interfaces:** Produces production `ReferenceProfileManifestV1` and `ReferenceProfileManifestV1.verify_integrity(gate_manifest: GateReferenceProfileManifestV1) -> None`.

**Intentionally failing test:**

```python
def test_reference_profile_rejects_image_digest_drift() -> None:
    with pytest.raises(ProfileIntegrityError, match="IMAGE_DIGEST_MISMATCH"):
        load_reference_profile(drifted_image_digest_bytes())
```

**Expected RED:** the production manifest integrity contract and packaged resource do not exist.

**Implementation boundary:** Own production manifest parsing/integrity and package-data copy. Do not build images, choose editable policy, resolve endpoints, or mutate gate evidence.

**Verification:**
- Target: `python -m pytest -q tests/unit/profiles/test_reference.py::test_reference_profile_rejects_image_digest_drift`
- Domain: `python -m pytest -q tests/unit/profiles/test_reference.py`
- Expected GREEN: exact Task 2.G identities load and every missing/extra/drifted field rejects.

**Completion evidence:** Not yet executed.

#### Task 6.C: Closed Mock and OpenAI LLM Profiles

**Status:** Not started

**Goal:** Define immutable mutually exclusive Mock and OpenAI LLM profile contracts and packaged built-ins.

**Dependencies:** Tasks 4.B and 5.D.

**Files:**
- Create: `src/vespercode/profiles/llm.py`
- Create: `src/vespercode/profiles/builtin/mock-deterministic-v1.json`
- Create: `src/vespercode/profiles/builtin/openai-single-turn-v1.json`
- Test: `tests/unit/profiles/test_llm.py`

**Interfaces:** Produces `MockLLMProfileV1`, `OpenAILLMProfileV1`, `LLMProfileManifestV1 = MockLLMProfileV1 | OpenAILLMProfileV1`, and `load_llm_profile(raw: bytes) -> LLMProfileManifestV1`.

**Intentionally failing test:**

```python
def test_mock_profile_rejects_openai_fields() -> None:
    with pytest.raises(ValidationError):
        load_llm_profile(mock_profile_with_endpoint())
```

**Expected RED:** the mutually exclusive closed LLM profile union does not exist.

**Implementation boundary:** Own profile schemas/resource integrity only. Do not resolve endpoint URLs, serialize requests, read credentials, or call adapters.

**Verification:**
- Target: `python -m pytest -q tests/unit/profiles/test_llm.py::test_mock_profile_rejects_openai_fields`
- Domain: `python -m pytest -q tests/unit/profiles/test_llm.py`
- Expected GREEN: exact built-ins load and cross-mode/unknown/mutable fields reject.

**Completion evidence:** Not yet executed.

#### Task 6.D: Trusted OpenAI Endpoint Map

**Status:** Not started

**Goal:** Resolve only the built-in public OpenAI endpoint ID to an immutable trusted endpoint record.

**Dependencies:** Tasks 5.E and 6.C.

**Files:**
- Create: `src/vespercode/profiles/endpoints.py`
- Test: `tests/unit/profiles/test_endpoints.py`

**Interfaces:** Produces `OpenAIEndpointV1(endpoint_id: Literal["OPENAI_PUBLIC_API_V1"], base_url: Literal["https://api.openai.com/v1"])` and `OpenAIEndpointRegistry.resolve(endpoint_id: str) -> OpenAIEndpointV1`.

**Intentionally failing test:**

```python
def test_endpoint_registry_rejects_user_url() -> None:
    with pytest.raises(UnknownEndpointError):
        OpenAIEndpointRegistry.resolve("https://proxy.invalid/v1")
```

**Expected RED:** the closed endpoint map does not exist.

**Implementation boundary:** Own endpoint ID-to-record resolution only. Do not accept URLs/config overrides, prepare HTTP requests, or manage credentials.

**Verification:**
- Target: `python -m pytest -q tests/unit/profiles/test_endpoints.py::test_endpoint_registry_rejects_user_url`
- Domain: `python -m pytest -q tests/unit/profiles/test_endpoints.py`
- Expected GREEN: the sole built-in ID resolves and every other ID/URL rejects without network access.

**Completion evidence:** Not yet executed.

#### Task 6.E: Built-in Profile Registry Resolution

**Status:** Not started

**Goal:** Resolve exact built-in editable/reference/LLM/endpoint profiles and reject missing, duplicate, extra, or cross-profile data before Run creation.

**Dependencies:** Tasks 6.A, 6.B, 6.C, and 6.D.

**Files:**
- Create: `src/vespercode/profiles/registry.py`
- Test: `tests/unit/profiles/test_registry.py`

**Interfaces:** Produces `ProfileRegistry.resolve_reference(profile_id: str) -> ReferenceProfileManifestV1`, `ProfileRegistry.resolve_llm(profile_id: str) -> LLMProfileManifestV1`, `ProfileRegistry.resolve_editable(policy_id: str) -> EditablePathPolicyV1`, and `ProfileRegistry.resolve_endpoint(endpoint_id: str) -> OpenAIEndpointV1`.

**Intentionally failing test:**

```python
def test_registry_rejects_duplicate_profile_id() -> None:
    with pytest.raises(DuplicateProfileError):
        build_profile_registry(duplicate_reference_resources())
```

**Expected RED:** the composition registry does not exist.

**Implementation boundary:** Own built-in resource enumeration, integrity delegation, and exact ID resolution. Do not add mutators, external discovery, request validation, or adapter behavior.

**Verification:**
- Target: `python -m pytest -q tests/unit/profiles/test_registry.py::test_registry_rejects_duplicate_profile_id`
- Domain: `python -m pytest -q tests/unit/profiles/test_registry.py`
- Expected GREEN: exact built-ins resolve deterministically and every ambiguity/drift/unknown ID rejects before a Run exists.

**Completion evidence:** Not yet executed.

#### Task 7.A: Domain-independent SQLite Migration Framework

**Status:** Not started

**Goal:** Open the local control database with explicit transaction semantics and apply an injected tuple of closed migrations in order, atomically, idempotently, and fail-closed on checksum drift without knowing any application-domain schema.

**SPEC references:** Milestone 7 migration-framework scope; SPEC §5.2 and §7 storage split.

**Dependencies:** Task 5.D.

**Files:**
- Create: `src/vespercode/storage/connection.py`
- Create: `src/vespercode/storage/migration_engine.py`
- Create: `src/vespercode/storage/migrations/__init__.py`
- Test: `tests/unit/storage/test_connection.py`
- Test: `tests/unit/storage/test_migration_engine.py`

**Interfaces:** Produces `open_control_database(path: Path) -> ControlDatabase`, `ControlDatabase.immediate_transaction() -> AbstractContextManager[ControlTransactionV1]`, closed `MigrationV1(version: int, name: str, checksum: DigestV1, apply: MigrationApplyV1)`, and `apply_migrations(db: ControlDatabase, migrations: tuple[MigrationV1, ...]) -> MigrationResultV1`.

**Intentionally failing test:**

```python
def test_changed_applied_migration_checksum_fails_closed(
    control_database: ControlDatabase,
    synthetic_migrations: tuple[MigrationV1, ...],
) -> None:
    apply_migrations(control_database, synthetic_migrations)
    control_database.replace_recorded_migration_checksum(version=1, checksum="0" * 64)
    result = apply_migrations(control_database, synthetic_migrations)
    assert result.kind == "MIGRATION_CHECKSUM_MISMATCH"
```

Expected RED: import failure because the database, closed migration descriptor, checksum history, and injected runner do not exist.

**Implementation boundary:** This child owns connection flags, transaction identity, the `schema_migrations` bootstrap, closed descriptor validation, checksum calculation/history, and injected runner only. It contains no application-domain DDL, domain migration constant, repository behavior, transition, replay, projection, retention, or import of `migrations/registry.py`. Synthetic RED fixtures prove strict order, replay idempotency, whole-batch rollback/atomicity, duplicate/gap rejection, and checksum drift without importing any application domain.

**Verification:**
- Target: `python -m pytest -q tests/unit/storage/test_migration_engine.py::test_changed_applied_migration_checksum_fails_closed`
- Domain: `python -m pytest -q tests/unit/storage/test_connection.py tests/unit/storage/test_migration_engine.py`
- Expected GREEN: both commands exit `0`; foreign keys, transaction identity, first apply, replay, strict order, duplicate/gap rejection, whole-batch rollback, and checksum-drift cases pass using synthetic migrations only.

**Completion evidence:** Not yet executed.

#### Task 7.B: Transactional Run and Wait Lifecycle

**Status:** Not started

**Goal:** Apply the closed Run/wait transition matrix atomically so exactly one correctly bound wait decision can win.

**SPEC references:** Milestone 7 lifecycle scope; SPEC §4.2.1, §4.2.7, §5.4, and Run/Wait rows in §7.

**Dependencies:** Task 7.A.

**Files:**
- Create: `src/vespercode/storage/migrations/v0001_run_wait.py`
- Create: `src/vespercode/storage/run_repository.py`
- Create: `src/vespercode/runs/lifecycle.py`
- Test: `tests/unit/storage/test_run_wait_migration.py`
- Test: `tests/unit/storage/test_run_repository.py`
- Test: `tests/unit/runs/test_lifecycle.py`

**Interfaces:** Produces immutable `RUN_WAIT_V1_MIGRATION = MigrationV1(version=1, name="run_wait_v1", ...)`, `RunRepository.insert_created(run: RunRecordV1) -> None`, `RunRepository.compare_and_transition(command: TransitionCommandV1) -> TransitionResultV1`, `RunRepository.create_wait(context: WaitContextV1) -> None`, `RunRepository.lock_wait_for_decision(tx: ControlTransactionV1, decision: WaitDecisionV1) -> WaitDecisionLockResultV1`, `RunRepository.commit_wait_decision(tx: ControlTransactionV1, lock: LockedWaitDecisionV1, decision: WaitDecisionV1) -> WaitDecisionResultV1`, `RunRepository.expire_wait(tx: ControlTransactionV1, lock: LockedWaitDecisionV1, now: CanonicalTimestampV1) -> WaitDecisionResultV1`, and `LifecycleRules.evaluate(current: RunStateV1, event: LifecycleEventV1) -> RunStateV1`.

**Intentionally failing test:**

```python
def test_same_wait_decision_can_win_only_once(run_repository: RunRepository, decision: WaitDecisionV1) -> None:
    first = decide_wait_once(run_repository, decision)
    second = lock_wait_once(run_repository, decision)
    assert first.kind == "APPLIED"
    assert second.kind == "ALREADY_DECIDED"
```

Expected RED: import failure because the Run repository and lifecycle rules do not exist.

**Schema RED:** `tests/unit/storage/test_run_wait_migration.py::test_run_wait_migration_has_exact_schema` applies only `RUN_WAIT_V1_MIGRATION` through Task 7.A and asserts exact `run_config_snapshots`, `runs`, and `wait_contexts` tables; their primary/foreign/unique keys; one active wait per Run; lifecycle revision predicates; and absence of credential, complete request/response, file-body, raw-output, or backup-byte columns.

**Implementation boundary:** This child owns one coupled Run/config/wait storage behavior: immutable v0001 DDL, Run/wait persistence, and pure target-state derivation. It may test through `(RUN_WAIT_V1_MIGRATION,)`, cannot edit the final registry, and owns no approval, Grant, authorization, idempotency replay, audit projection, or persistence-recovery schema.

**Verification:**
- Target: `python -m pytest -q tests/unit/storage/test_run_repository.py::test_same_wait_decision_can_win_only_once`
- Schema: `python -m pytest -q tests/unit/storage/test_run_wait_migration.py::test_run_wait_migration_has_exact_schema`
- Domain: `python -m pytest -q tests/unit/storage/test_run_wait_migration.py tests/unit/storage/test_run_repository.py tests/unit/runs/test_lifecycle.py`
- Expected GREEN: all commands exit `0`; the exact schema/prohibited-column contract plus full transition table, binding, rollback, expiry, terminal, and one-winner cases pass.

**Completion evidence:** Not yet executed.

#### Task 7.C: Transaction-bound Idempotency Ledger

**Status:** Not started

**Goal:** Return the first result for an identical event request and reject reuse of the same event id for different request bytes without performing domain mutation.

**SPEC references:** Milestone 7 idempotency scope; SPEC §4.2.7 and §5.4.

**Dependencies:** Task 7.B.

**Files:**
- Create: `src/vespercode/storage/migrations/v0002_idempotency.py`
- Create: `src/vespercode/storage/idempotency.py`
- Test: `tests/unit/storage/test_idempotency_migration.py`
- Test: `tests/unit/storage/test_idempotency.py`

**Interfaces:** Produces immutable `IDEMPOTENCY_V1_MIGRATION = MigrationV1(version=2, name="idempotency_v1", ...)` and `IdempotencyRepository.record_or_replay(tx: ControlTransactionV1, scope: str, event_id: str, request_digest: str, result_digest: str) -> IdempotencyResultV1`, where `IdempotencyResultV1` is the closed `NEW | REPLAY | EVENT_ID_REUSE_CONFLICT` union.

**Intentionally failing test:**

```python
def test_event_id_reuse_with_different_request_is_conflict(
    repository: IdempotencyRepository,
    transaction: ControlTransactionV1,
) -> None:
    assert repository.record_or_replay(transaction, "wait", "evt-1", "a" * 64, "b" * 64).kind == "NEW"
    assert repository.record_or_replay(transaction, "wait", "evt-1", "c" * 64, "d" * 64).kind == "EVENT_ID_REUSE_CONFLICT"
```

Expected RED: import failure because the idempotency repository does not exist.

**Schema RED:** `tests/unit/storage/test_idempotency_migration.py::test_idempotency_migration_has_exact_schema` applies `(RUN_WAIT_V1_MIGRATION, IDEMPOTENCY_V1_MIGRATION)` and asserts the sole `idempotency_events` table, composite primary key `(scope, event_id)`, immutable request/result digests, and absence of domain-result/body/secret columns.

**Implementation boundary:** This child owns one coupled idempotency storage behavior: immutable v0002 DDL and the transaction-bound repository. It stores only scope/event/request/result identities inside a caller-owned Task 7.A transaction, cannot edit the final registry, reconstruct domain results, transition Runs, or mutate on replay/conflict.

**Verification:**
- Target: `python -m pytest -q tests/unit/storage/test_idempotency.py::test_event_id_reuse_with_different_request_is_conflict`
- Schema: `python -m pytest -q tests/unit/storage/test_idempotency_migration.py::test_idempotency_migration_has_exact_schema`
- Domain: `python -m pytest -q tests/unit/storage/test_idempotency_migration.py tests/unit/storage/test_idempotency.py`
- Expected GREEN: all commands exit `0`; exact v0002 schema, NEW, identical REPLAY, conflict, transaction rollback, and concurrency cases pass.

**Completion evidence:** Not yet executed.

#### Task 7.D: Complete V1 Migration Registry Composition

**Status:** Not started

**Goal:** Compose the exact immutable domain migration constants into the sole complete v1 registry and, through a test-only expected owner map, fail closed when any required migration or per-version/final SQLite table ownership is missing, duplicated, introduced by the wrong version, early, late, reordered, unexpected, or checksum-drifted.

**SPEC references:** Milestone 7 final registry scope; SPEC §5.2, §5.6, and complete §7 storage classification.

**Dependencies:** Tasks 7.B, 7.C, 14.B, 15.D, 15.E, 22.A, 23.A, 24.C, 25.B, 25.D, 26.A, and 26.C.

**Blocks:** Tasks 37.B and 38.F.

**Files:**
- Create: `src/vespercode/storage/migrations/registry.py`
- Test: `tests/unit/storage/test_migration_registry.py`

**Interfaces:** Consumes exactly `RUN_WAIT_V1_MIGRATION`, `IDEMPOTENCY_V1_MIGRATION`, `DISCLOSURE_GRANTS_V1_MIGRATION`, `DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION`, `MEMORY_V1_MIGRATION`, `AUDIT_V1_MIGRATION`, `AGENT_TURNS_V1_MIGRATION`, `FEEDBACK_V1_MIGRATION`, `ACTIONS_V1_MIGRATION`, `WRITEBACK_APPROVALS_V1_MIGRATION`, `PERSISTENCE_V1_MIGRATION`, and `RECOVERY_V1_MIGRATION`; produces `ALL_V1_MIGRATIONS: tuple[MigrationV1, ...]`.

**Intentionally failing test:**

```python
def test_registry_rejects_missing_required_domain_migration() -> None:
    incomplete = tuple(
        migration
        for migration in expected_v1_domain_migrations()
        if migration.name != "feedback_v1"
    )
    with pytest.raises(MigrationRegistryError, match="MIGRATION_SET_INCOMPLETE"):
        compose_v1_migrations(incomplete)


EXPECTED_V1_TABLE_DELTAS_BY_VERSION = {
    1: {"run_config_snapshots", "runs", "wait_contexts"},
    2: {"idempotency_events"},
    3: {"disclosure_grant_subjects", "disclosure_grants"},
    4: {"disclosure_authorizations"},
    5: {"memory_entries"},
    6: {"audit_events"},
    7: {"agent_turns"},
    8: {"feedback_records"},
    9: {"action_records"},
    10: {"final_writeback_subjects", "final_writeback_approvals"},
    11: {"persistence_transactions", "persistence_path_records"},
    12: {"recovery_results"},
}


def test_registry_prefixes_match_exact_schema_owner_map(
    empty_control_database: ControlDatabase,
) -> None:
    before: set[str] = set()
    for version in range(1, 13):
        statements: list[str] = []
        empty_control_database.set_trace_callback(statements.append)
        apply_migrations(
            empty_control_database,
            ALL_V1_MIGRATIONS[:version],
        )
        empty_control_database.set_trace_callback(None)
        domain_create_targets = (
            create_table_targets(statements) - {"schema_migrations"}
        )
        assert domain_create_targets == (
            EXPECTED_V1_TABLE_DELTAS_BY_VERSION[version]
        )
        assert no_if_not_exists_for_domain_tables(statements)
        after = {
            row[0]
            for row in empty_control_database.execute(
                "SELECT name FROM sqlite_schema "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        framework_delta = {"schema_migrations"} if version == 1 else set()
        assert after - before == (
            EXPECTED_V1_TABLE_DELTAS_BY_VERSION[version] | framework_delta
        )
        before = after

    expected_final = {"schema_migrations"} | set().union(
        *EXPECTED_V1_TABLE_DELTAS_BY_VERSION.values()
    )
    assert len(expected_final) == 18
    assert before == expected_final
```

`create_table_targets` is a strict test-only parser for SQLite `CREATE TABLE` trace statements; it rejects an unparseable domain statement, and `no_if_not_exists_for_domain_tables` permits framework bootstrap handling only for `schema_migrations`. Expected RED: import failure because no final registry/composition contract exists. After the registry exists, the schema-owner RED still fails if a migration introduces an undeclared table, omits its declared table, attempts to repeat an already owned table, or moves a table to an earlier/later version; v0001 alone may add the framework-owned `schema_migrations` table in addition to its exact domain delta.

**Implementation boundary:** This child is composition-only. It owns no DDL, connection policy, migration execution, domain repository, fixture table, or product behavior and cannot modify any domain migration module. The declared direct predecessor set must equal the complete migration-producer set. Production `registry.py` checks exact versions `1..12`, exact expected names/order, unique checksums, and descriptor checksums before exporting the tuple. The exact table-delta/final-set map exists only in `test_migration_registry.py`; production registry code cannot import, export, derive behavior from, or duplicate it. Prefix application uses Task 7.A unchanged, and read-only `sqlite_schema` introspection asserts ownership without creating a second schema owner.

**Verification:**
- Target: `python -m pytest -q tests/unit/storage/test_migration_registry.py::test_registry_rejects_missing_required_domain_migration`
- Schema owner: `python -m pytest -q tests/unit/storage/test_migration_registry.py::test_registry_prefixes_match_exact_schema_owner_map`
- Domain: `python -m pytest -q tests/unit/storage/test_migration_registry.py tests/unit/storage/test_migration_engine.py`
- Expected GREEN: all three commands exit `0`; exact complete composition applies atomically; every prefix adds only its owner-map delta; v0001 separately adds framework `schema_migrations`; the final set equals exactly 18 tables; and missing/duplicate/wrong-owner/early/late/gapped/reordered/unexpected/checksum-drifted inputs fail closed.

**Completion evidence:** Not yet executed.

#### Task 8.A: Strict Run Request and Frozen Configuration

**Status:** Not started

**Goal:** Reject every invalid or ambiguous run request before a run id exists, and create one `CREATED` Run with an immutable `RunConfigSnapshotV1` for valid input.

**SPEC references:** Milestone 8 references; owns request parsing, validation, canonical target binding, config freezing, and initial Run creation only.

**Dependencies:** Tasks 6.E and 7.C.

**Blocks:** Tasks 8.B and 37.B.

**Parallelization:** Parallelizable with Tasks 15.A, 23.A, and 27.A; each task starts only after its exact executable Dependencies are satisfied.

**Branch/worktree:** `codex/task-8a-run-request`; `.worktrees/task-8a-run-request`.

**Files:**
- Create: `src/vespercode/runs/request.py`
- Test: `tests/unit/runs/test_request.py`

**Interfaces:** Consumes Task 6.E `ProfileRegistry` and Task 7.B `RunRepository`; produces `ValidateRunRequestV1`, `ValidatedRunRequestV1`, `RunConfigSnapshotV1`, `validate_request(request: Mapping[str, object], profiles: ProfileRegistry) -> ValidatedRunRequestV1 | ConfigInvalidV1`, `freeze_run_config(request: ValidatedRunRequestV1) -> RunConfigSnapshotV1`, `create_run(request: ValidatedRunRequestV1, repository: RunRepository) -> RunCreatedV1`, and `RunRequestService.validate_and_create(raw_request: Mapping[str, object]) -> RunCreatedV1 | ConfigInvalidV1`.

**Intentionally failing test:**

```python
def test_custom_base_url_is_rejected_without_creating_a_run(
    request_service: RunRequestService,
    run_repository: SpyRunRepository,
) -> None:
    result = request_service.validate_and_create(
        valid_request_dict() | {"base_url": "https://attacker.example"}
    )
    assert result.kind == "CONFIG_INVALID"
    assert run_repository.insert_count == 0
```

**Implementation boundary:** Closed-field validation and config freezing end after the atomic `CREATED` insert. This task does not acquire a workspace lease, create a Snapshot, run readiness checks, or start PREFLIGHT.

**Verification:**
- Target: `python -m pytest -q tests/unit/runs/test_request.py::test_custom_base_url_is_rejected_without_creating_a_run`
- Domain: `python -m pytest -q tests/unit/runs/test_request.py`
- Expected: invalid requests produce stable reasons and zero inserts; valid permutations bind one identical frozen config and create exactly one Run.

**Completion evidence:** Not yet executed.

#### Task 8.B: Ordered Admission Coordinator

**Status:** Not started

**Goal:** Move one existing `CREATED` Run through the exact PREFLIGHT port order while every failure prevents all later calls and forbidden side effects.

**SPEC references:** Milestone 8 references; owns PREFLIGHT transition, deadline freezing, port ordering, one-Snapshot rule, and zero-downstream-call failure behavior.

**Dependencies:** Task 8.A.

**Blocks:** Tasks 9.A, 20.A, 25.B, 25.G, 28.A, 29.A, and 37.B.

**Parallelization:** Sequential after Task 8.A.

**Branch/worktree:** `codex/task-8b-admission`; `.worktrees/task-8b-admission`.

**Files:**
- Create: `src/vespercode/runs/admission.py`
- Test: `tests/unit/runs/test_admission.py`
- Test: `tests/unit/runs/test_admission_order.py`

**Interfaces:** Produces `AdmissionPortsV1(workspace: WorkspaceAdmissionPortV1, recovery: RecoveryAdmissionPortV1, snapshot: SnapshotAdmissionPortV1, static_profile: StaticProfileAdmissionPortV1, execution_readiness: ExecutionReadinessPortV1, credential_readiness: CredentialReadinessPortV1, baseline: BaselineAdmissionPortV1)` and `AdmissionCoordinator.start_run(run_id: str) -> AdmissionResultV1`; consumes Task 8.A's frozen Run and Task 7.B lifecycle repository.

**Intentionally failing test:**

```python
def test_snapshot_precheck_failure_calls_no_later_admission_port(
    admission: AdmissionCoordinator,
    ports: RecordingAdmissionPorts,
) -> None:
    ports.snapshot_precheck_result = rejected("SNAPSHOT_PRECHECK_FAILED")
    result = admission.start_run("run-1")
    assert result.error_code == "SNAPSHOT_PRECHECK_FAILED"
    assert ports.calls == ("workspace", "recovery", "snapshot_precheck")
```

**Implementation boundary:** The coordinator calls only declared ports and lifecycle operations. It cannot import concrete Win32, Docker, credential, Snapshot, or baseline implementations.

**Verification:**
- Target: `python -m pytest -q tests/unit/runs/test_admission_order.py::test_snapshot_precheck_failure_calls_no_later_admission_port`
- Domain: `python -m pytest -q tests/unit/runs/test_admission.py tests/unit/runs/test_admission_order.py`
- Expected: every failure-point trace is an exact prefix of the required order; rejected PREFLIGHT performs no Agent action, LLM call, execution, install, image build, or workspace write.

**Completion evidence:** Not yet executed.

#### Task 9.A: Win32 Workspace and Final-object Identity

**Status:** Not started

**Goal:** Resolve one handle-derived workspace identity and reject every unprovable, aliased, reparse, ADS, hard-link, kind, or ACL final object.

**SPEC references:** Milestone 9 identity/object scope; SPEC §0.1 path identity, §1.4.2–§1.4.4, §4.1, and AC-01/AC-21/AC-31.

**Dependencies:** Tasks 1.E, 5.D, 7.C, and 8.B.

**Files:**
- Create: `src/vespercode/workspace/identity_win32.py`
- Create: `src/vespercode/workspace/object_win32.py`
- Test: `tests/integration/windows/test_workspace_identity.py`
- Test: `tests/integration/windows/test_workspace_objects.py`

**Interfaces:** Produces `resolve_workspace_identity(locator: Path) -> WorkspaceIdentityV1` and `inspect_workspace_object(root: WorkspaceIdentityV1, path: CanonicalRelativePathV1) -> FinalObjectIdentityV1`.

**Intentionally failing test:**

```python
def test_reparse_final_object_is_rejected(
    workspace_identity: WorkspaceIdentityV1,
    reparse_path: CanonicalRelativePathV1,
) -> None:
    with pytest.raises(WorkspaceObjectRejectedV1) as error:
        inspect_workspace_object(workspace_identity, reparse_path)
    assert error.value.error_code == "UNSUPPORTED_WORKSPACE_OBJECT"
```

Expected RED: import failure because the production Win32 identity/object adapters do not exist.

**Implementation boundary:** This child owns handle-derived identity, ancestry, object kind, reparse/ADS/link/ACL facts, and stable rejection only. It does not acquire the mutex, inspect Git, decide editable policy, or authorize create/replace.

**Verification:**
- Target: `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_workspace_objects.py::test_reparse_final_object_is_rejected`
- Domain: `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_workspace_identity.py tests/integration/windows/test_workspace_objects.py`
- Expected GREEN: both commands exit `0` on the Windows runner with no required skip; every Task 1 identity/object sentinel matches the production adapter.

**Completion evidence:** Not yet executed.

#### Task 9.B: Cross-process Workspace Mutex

**Status:** Not started

**Goal:** Give one process exclusive ownership of a workspace-identity-derived named mutex until explicit lease release.

**SPEC references:** Milestone 9 lease scope; SPEC §4.1 and §4.6 lease requirements; AC-21.

**Dependencies:** Task 9.A.

**Files:**
- Create: `src/vespercode/workspace/mutex_win32.py`
- Test: `tests/integration/windows/test_named_mutex.py`

**Interfaces:** Produces `WorkspaceMutex.acquire(identity: WorkspaceIdentityV1, timeout_ms: int) -> WorkspaceLeaseV1` and `WorkspaceMutex.release(lease: WorkspaceLeaseV1) -> None`.

**Intentionally failing test:**

```python
def test_second_process_cannot_acquire_same_workspace_mutex(
    workspace_identity: WorkspaceIdentityV1,
) -> None:
    first = WorkspaceMutex.acquire(workspace_identity, timeout_ms=1000)
    try:
        assert child_process_try_acquire(workspace_identity, timeout_ms=50).kind == "TIMED_OUT"
    finally:
        WorkspaceMutex.release(first)
```

Expected RED: import failure because the production named-mutex adapter does not exist.

**Implementation boundary:** This child derives one stable mutex name from `WorkspaceIdentityV1`, owns handle lifetime, timeout, and release only; it performs no Git/object/path/persistence operation.

**Verification:**
- Target: `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_named_mutex.py::test_second_process_cannot_acquire_same_workspace_mutex`
- Domain: `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_named_mutex.py`
- Expected GREEN: both commands exit `0` on the Windows runner; same-workspace exclusion, different-workspace independence, timeout, release, and crashed-child cleanup pass.

**Completion evidence:** Not yet executed.

#### Task 9.C: Sealed Git Snapshot Preflight

**Status:** Not started

**Goal:** Freeze and validate the exact Git config/index/HEAD/worktree/ignore/attribute state before Snapshot creation.

**SPEC references:** Milestone 9 Git scope; SPEC §1.4.1, §4.1 behavior 6–10, AC-15, and AC-26.

**Dependencies:** Task 9.B.

**Files:**
- Create: `src/vespercode/workspace/git_preflight.py`
- Test: `tests/unit/workspace/test_git_preflight.py`
- Test: `tests/integration/windows/test_git_preflight.py`

**Interfaces:** Produces `run_git_snapshot_prechecks(identity: WorkspaceIdentityV1, reference: ReferenceProfileManifestV1) -> GitPreflightResultV1`.

**Intentionally failing test:**

```python
def test_tracked_file_with_skip_worktree_is_rejected_before_snapshot(
    sealed_git_repo: GitRepositoryFixture,
) -> None:
    sealed_git_repo.set_index_flag("src/a.py", skip_worktree=True)
    result = run_git_snapshot_prechecks(sealed_git_repo.identity, sealed_git_repo.reference_manifest)
    assert result.error_code == "UNSUPPORTED_REPOSITORY"
    assert sealed_git_repo.snapshot_create_count == 0
```

Expected RED: import failure because sealed Git preflight does not exist.

**Implementation boundary:** This child invokes Git without a shell under closed config/environment and returns sealed non-secret observations only. It does not create a Snapshot, inspect candidate paths, acquire a lease, or write repository bytes.

**Verification:**
- Target: `python -m pytest -q tests/unit/workspace/test_git_preflight.py::test_tracked_file_with_skip_worktree_is_rejected_before_snapshot`
- Domain: `python -m pytest -q tests/unit/workspace/test_git_preflight.py`
- Windows: `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_git_preflight.py`
- Expected GREEN: all commands exit `0`; every forbidden config/index/worktree/conversion/alias state rejects before Snapshot creation.

**Completion evidence:** Not yet executed.

#### Task 9.D: Handle-bound Existing/create Path Authorization

**Status:** Not started

**Goal:** Authorize an existing object or create parent only when lexical, final-object, root-ancestry, alias, sensitive-path, and editable-policy facts all match.

**SPEC references:** Milestone 9 path-guard scope; SPEC §1.4.2–§1.4.4, §4.3, and AC-01/AC-29/AC-31.

**Dependencies:** Task 9.C.

**Files:**
- Create: `src/vespercode/workspace/path_guard.py`
- Test: `tests/unit/workspace/test_path_guard.py`

**Interfaces:** Produces `PathGuard.authorize_existing(root: WorkspaceIdentityV1, path: CanonicalRelativePathV1, expected_kind: WorkspaceObjectKindV1) -> AuthorizedObjectHandleV1` and `PathGuard.authorize_create(root: WorkspaceIdentityV1, path: CanonicalRelativePathV1) -> AuthorizedParentHandleV1`.

**Intentionally failing test:**

```python
def test_create_rejects_case_alias_of_existing_path(path_guard: PathGuard) -> None:
    result = path_guard.authorize_create(workspace_identity(), canonical_path("src/A.py"))
    assert result.error_code == "PATH_ALIAS_COLLISION"
    assert result.authorized_parent is None
```

Expected RED: import failure because `PathGuard` does not exist.

**Implementation boundary:** This child combines Task 4.D lexical paths with Task 9.A observations and frozen Git/ignore facts; it cannot fall back to string authorization, mutate the workspace, parse patches, or widen editable policy.

**Verification:**
- Target: `python -m pytest -q tests/unit/workspace/test_path_guard.py::test_create_rejects_case_alias_of_existing_path`
- Domain: `python -m pytest -q tests/unit/workspace/test_path_guard.py`
- Expected GREEN: both commands exit `0`; existing/create ancestry, kind, alias, sensitive, reparse/ADS/link, and root-escape cases fail closed.

**Completion evidence:** Not yet executed.

#### Task 10.A: Immutable Content Object Store

**Status:** Not started

**Goal:** Store and retrieve exact immutable file bytes by verified raw SHA-256 content reference.

**Dependencies:** Tasks 5.D and 9.D.

**Files:**
- Create: `src/vespercode/trees/content_store.py`
- Test: `tests/unit/trees/test_content_store.py`

**Interfaces:** Produces `ContentObjectRefV1(sha256: str, byte_count: int)`, `ContentObjectStore.put(raw_bytes: bytes) -> ContentObjectRefV1`, and `ContentObjectStore.get(ref: ContentObjectRefV1) -> bytes`.

**Intentionally failing test:**

```python
def test_get_rejects_bytes_whose_digest_drifted(store: ContentObjectStore) -> None:
    ref = store.put(b"stable")
    store.inject_corruption(ref, b"changed")
    with pytest.raises(ContentIntegrityError):
        store.get(ref)
```

**Expected RED:** the digest-verifying immutable content store does not exist.

**Implementation boundary:** Own content-addressed bytes only. Do not classify text, construct Snapshots, read mutable workspace paths, or authorize edits.

**Verification:**
- Target: `python -m pytest -q tests/unit/trees/test_content_store.py::test_get_rejects_bytes_whose_digest_drifted`
- Domain: `python -m pytest -q tests/unit/trees/test_content_store.py`
- Expected GREEN: put/get/dedup/integrity cases pass and corruption fails closed.

**Completion evidence:** Not yet executed.

#### Task 10.B: Shared Supported-text Classifier

**Status:** Not started

**Goal:** Classify raw bytes once for all file tools and candidate operations under the exact UTF-8/newline rules.

**Dependencies:** Task 5.D.

**Files:**
- Create: `src/vespercode/trees/text_classifier.py`
- Test: `tests/unit/trees/test_text_classifier.py`

**Interfaces:** Produces `TextMetadataV1(encoding: Literal["UTF8","UTF8_BOM"], newline: Literal["LF","CRLF"], final_newline: Literal[True])`, `TextFileClassificationV1 = SupportedTextFileV1 | NonTextFileV1`, and pure `classify_supported_text(raw_bytes: bytes) -> TextFileClassificationV1`.

**Intentionally failing test:**

```python
def test_mixed_newlines_are_non_text() -> None:
    assert classify_supported_text(b"a\\r\\nb\\n").kind == "NON_TEXT_FILE"
```

**Expected RED:** the shared byte classifier does not exist.

**Implementation boundary:** Own pure byte classification only. Do not store content, build trees, normalize bytes, or read filesystem paths.

**Verification:**
- Target: `python -m pytest -q tests/unit/trees/test_text_classifier.py::test_mixed_newlines_are_non_text`
- Domain: `python -m pytest -q tests/unit/trees/test_text_classifier.py`
- Expected GREEN: UTF-8/BOM/LF/CRLF/final-newline cases classify exactly and invalid/binary/mixed cases remain valid non-text entries.

**Completion evidence:** Not yet executed.

#### Task 10.C: Sole SnapshotTree Construction and Verification

**Status:** Not started

**Goal:** Construct the Run's sole immutable SnapshotTree from sealed Git-preflight bytes and verify all content, ordering, identity, and policy bindings.

**Dependencies:** Tasks 9.D, 10.A, and 10.B.

**Files:**
- Create: `src/vespercode/trees/snapshot.py`
- Test: `tests/unit/trees/test_snapshot.py`
- Test: `tests/integration/windows/test_snapshot_from_preflight.py`

**Interfaces:** Produces `SnapshotTreeV1`, `SnapshotIntegrityResultV1`, `create_snapshot(preflight: AcceptedGitPreflightV1, store: ContentObjectStore, classifier: SupportedTextClassifierV1) -> SnapshotTreeV1`, and `verify_snapshot(snapshot: SnapshotTreeV1, store: ContentObjectStore) -> SnapshotIntegrityResultV1`.

**Intentionally failing test:**

```python
def test_snapshot_rejects_preflight_object_identity_drift() -> None:
    with pytest.raises(SnapshotIntegrityError, match="PREFLIGHT_OBJECT_DRIFT"):
        create_snapshot(drifted_preflight(), store(), classifier())
```

**Expected RED:** no single-Snapshot constructor binds sealed bytes/object identities.

**Implementation boundary:** Own Snapshot entry construction/root digest/verification only. Never reread mutable repository paths or redefine content/classification rules.

**Verification:**
- Target: `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_snapshot_from_preflight.py::test_snapshot_rejects_preflight_object_identity_drift`
- Domain: `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_snapshot_from_preflight.py`
- Expected GREEN: exact sealed preflight builds one verified deterministic Snapshot and every size/order/content/object/policy drift rejects.

**Completion evidence:** Not yet executed.

#### Task 11.A: Snapshot-bound Read Tool and Common File Contracts

**Status:** Not started

**Goal:** Freeze the common file action/result contracts and implement bounded text reads that can observe only the bound immutable tree.

**SPEC references:** Milestone 11 references; owns list/read/search shared schemas and `ReadFile` behavior, but not discovery pagination.

**Dependencies:** Tasks 5.D and 10.C.

**Blocks:** Tasks 11.B and 37.B.

**Parallelization:** Parallelizable with Task 12.A once the exact Dependencies of both executable children are satisfied.

**Branch/worktree:** `codex/task-11a-read-tool`; `.worktrees/task-11a-read-tool`.

**Files:**
- Create: `src/vespercode/tools/file_actions.py`
- Create: `src/vespercode/tools/file_results.py`
- Create: `src/vespercode/tools/read_file.py`
- Test: `tests/unit/tools/test_file_actions.py`
- Test: `tests/unit/tools/test_read_file.py`

**Interfaces:** Produces `FileToolActionV1 = ListFilesActionV1 | ReadFileActionV1 | SearchTextActionV1`, `FileToolResultV1 = ListFilesResultV1 | ReadFileResultV1 | SearchTextResultV1`, `ReadFileActionV1`, `ReadFileResultV1`, and `read_file(tree: SnapshotTreeV1 | CandidateTreeV1, action: ReadFileActionV1) -> ReadFileResultV1`.

**Intentionally failing test:**

```python
def test_read_uses_only_bound_snapshot_bytes(
    sealed_snapshot: SnapshotTree,
    live_workspace: SpyWorkspace,
) -> None:
    result = read_file(sealed_snapshot, read_action("src/example.py", 1, 20))
    assert result.text == sealed_snapshot.expected_text("src/example.py")
    assert live_workspace.read_count == 0
```

**Implementation boundary:** Read validates the classified Snapshot object, line/byte bounds, BOM/newline metadata, and artifact truncation. It performs no filesystem, cursor, policy, or dispatch operation.

**Verification:**
- Target: `python -m pytest -q tests/unit/tools/test_read_file.py::test_read_uses_only_bound_snapshot_bytes`
- Domain: `python -m pytest -q tests/unit/tools/test_file_actions.py tests/unit/tools/test_read_file.py`
- Expected: closed schemas reject unknown fields and Read never observes mutable workspace state.

**Completion evidence:** Not yet executed.

#### Task 11.B: Canonically Paged List and Literal Search

**Status:** Not started

**Goal:** Implement stable List/Search discovery whose distinct canonical cursors reproduce unpaged results exactly and fail closed on tampering or tree drift.

**SPEC references:** Milestone 11 references and Resolved OD-01.

**Dependencies:** Task 11.A.

**Blocks:** Tasks 17.A, 17.C, 24.A, 25.D, 31.A, 31.B, 32.B, and 37.B.

**Parallelization:** Sequential after Task 11.A because it consumes the frozen common cursor/result contracts.

**Branch/worktree:** `codex/task-11b-paged-discovery`; `.worktrees/task-11b-paged-discovery`.

**Files:**
- Create: `src/vespercode/tools/list_files.py`
- Create: `src/vespercode/tools/search_text.py`
- Test: `tests/unit/tools/test_list_files.py`
- Test: `tests/unit/tools/test_search_text.py`

**Interfaces:** Produces `list_files(tree: SnapshotTreeV1 | CandidateTreeV1, action: ListFilesActionV1) -> ListFilesResultV1` and `search_text(tree: SnapshotTreeV1 | CandidateTreeV1, action: SearchTextActionV1) -> SearchTextResultV1`; uses separate List/Search cursor types binding visible-tree digest, cursor-free query digest, next scan position, and cursor self-digest.

**Intentionally failing test:**

```python
def test_paged_discovery_equals_unpaged_without_duplicates(
    discovery_fixture: DiscoveryFixture,
) -> None:
    assert discovery_fixture.collect_list_pages(limit=2) == discovery_fixture.list_unpaged()
    assert discovery_fixture.collect_search_pages(limit=2) == discovery_fixture.search_unpaged()
```

**Implementation boundary:** Stable sorting and continuation are pure immutable-tree operations. `CONTINUATION_INVALID` and `CONTINUATION_STALE` return zero partial rows or artifacts.

**Verification:**
- Target: `python -m pytest -q tests/unit/tools/test_list_files.py::test_paged_discovery_equals_unpaged_without_duplicates`
- Domain: `python -m pytest -q tests/unit/tools/test_list_files.py tests/unit/tools/test_search_text.py`
- Expected: paged/unpaged equality, stable ordering, non-text accounting, and tampered/stale zero-payload failures all pass.

**Completion evidence:** Not yet executed.

#### Task 12.A: Strict UNIFIED_DIFF_V1 Parser

**Status:** Not started

**Goal:** Parse the complete no-BOM UTF-8/LF `UNIFIED_DIFF_V1` grammar or return one closed parse failure without deriving candidate state.

**SPEC references:** Milestone 12 parser scope; SPEC §4.3 patch grammar, error ordering, and AC-01/AC-31.

**Dependencies:** Tasks 6.E, 9.D, and 10.C.

**Files:**
- Create: `src/vespercode/candidate/unified_diff.py`
- Test: `tests/unit/candidate/test_unified_diff.py`

**Interfaces:** Produces `parse_unified_diff_v1(patch_text: str) -> ParsedPatchV1 | PatchParseFailureV1`.

**Intentionally failing test:**

```python
def test_trailing_unparsed_patch_bytes_are_rejected() -> None:
    result = parse_unified_diff_v1(valid_replace_patch() + "\ntrailing")
    assert result.kind == "PATCH_PARSE_FAILED"
    assert result.error_code == "PATCH_SCHEMA_INVALID"
```

Expected RED: import failure because the strict parser does not exist.

**Implementation boundary:** This child validates only complete headers, ranges, hunks, entry uniqueness, and prohibited diff forms. It does not read a tree, match old bytes, apply edits, enforce candidate limits, or publish a revision.

**Verification:**
- Target: `python -m pytest -q tests/unit/candidate/test_unified_diff.py::test_trailing_unparsed_patch_bytes_are_rejected`
- Domain: `python -m pytest -q tests/unit/candidate/test_unified_diff.py`
- Expected GREEN: both commands exit `0`; valid CREATE/REPLACE parses and every delete/rename/mode/binary/timestamp/no-newline/malformed/trailing case rejects deterministically.

**Completion evidence:** Not yet executed.

#### Task 12.B: Immutable CandidateTree Overlay

**Status:** Not started

**Goal:** Derive an immutable content-addressed child tree from complete staged postimages while leaving its parent tree unchanged.

**SPEC references:** Milestone 12 tree scope; SPEC §4.3 CandidateTree/CandidateRevision rules and AC-18.

**Dependencies:** Task 12.A.

**Files:**
- Create: `src/vespercode/trees/candidate.py`
- Test: `tests/unit/trees/test_candidate.py`

**Interfaces:** Produces `CandidatePostimageSequenceV1`, an immutable ordered tuple of zero or more `CandidatePostimageV1` items, plus `CandidateTreeV1`, `CandidateRevisionV1`, and `derive_candidate_revision(parent: CandidateRevisionV1, postimages: CandidatePostimageSequenceV1) -> CandidateRevisionV1`.

**Intentionally failing test:**

```python
def test_child_revision_does_not_mutate_parent(parent_revision: CandidateRevisionV1) -> None:
    child = derive_candidate_revision(parent_revision, (replace_postimage("src/a.py", b"x = 2\n"),))
    assert child.tree.read_bytes(canonical_path("src/a.py")) == b"x = 2\n"
    assert parent_revision.tree.read_bytes(canonical_path("src/a.py")) == b"x = 1\n"
```

Expected RED: import failure because immutable candidate revisions do not exist.

**Implementation boundary:** This child owns immutable overlay lookup, sorted tree digest, parent independence, and content-store references only. It does not parse patches, authorize paths, publish through a transaction, compute FinalDiff, or decide policy.

**Verification:**
- Target: `python -m pytest -q tests/unit/trees/test_candidate.py::test_child_revision_does_not_mutate_parent`
- Domain: `python -m pytest -q tests/unit/trees/test_candidate.py`
- Expected GREEN: both commands exit `0`; replace/create overlays, parent independence, deterministic order, missing content, and tree-integrity cases pass.

**Completion evidence:** Not yet executed.

#### Task 12.C: Atomic Exact Candidate Patch Transaction

**Status:** Not started

**Goal:** Apply one parsed patch exactly against the named base candidate and publish one validated revision or no revision.

**SPEC references:** Milestone 12 application scope; SPEC §4.2.2, §4.3 atomicity/error priority, and AC-04/AC-07/AC-31.

**Dependencies:** Task 12.B.

**Files:**
- Create: `src/vespercode/candidate/patch_engine.py`
- Test: `tests/unit/candidate/test_patch_engine.py`

**Interfaces:** Produces `ApplyCandidatePatchAction` and `apply_candidate_patch(action: ApplyCandidatePatchAction, current: CandidateRevisionV1, context: CandidatePatchContextV1) -> CandidatePatchOutcomeV1`.

**Intentionally failing test:**

```python
def test_mixed_legal_and_noneditable_patch_has_no_candidate_side_effect(
    candidate_context: CandidatePatchContextV1,
    candidate_publisher: SpyCandidatePublisher,
) -> None:
    outcome = apply_candidate_patch(patch_action(candidate_context.current.candidate_digest, replace_src_a_and_readme_patch()), candidate_context.current, candidate_context.with_publisher(candidate_publisher))
    assert outcome.error_code == "PATCH_PATH_NOT_EDITABLE"
    assert candidate_publisher.publish_count == 0
```

Expected RED: import failure because the atomic patch engine does not exist.

**Implementation boundary:** This child consumes Task 12.A parsing, Task 12.B staging, Task 9.D authorization, and the frozen policy; it performs exact hunk matching and whole-patch validation only. FinalDiff construction and semantic identity belong to Task 12.D.

**Verification:**
- Target: `python -m pytest -q tests/unit/candidate/test_patch_engine.py::test_mixed_legal_and_noneditable_patch_has_no_candidate_side_effect`
- Domain: `python -m pytest -q tests/unit/candidate/test_patch_engine.py`
- Expected GREEN: both commands exit `0`; base-digest, exact-hunk, priority, text preservation, limits, collision, and zero-publication failure cases pass.

**Completion evidence:** Not yet executed.

#### Task 12.D: FinalDiffV1 and Candidate Identity

**Status:** Not started

**Goal:** Recompute the complete Snapshot-to-candidate structured diff and bind its exact digest with Snapshot and CandidateTree digests.

**SPEC references:** Milestone 12 FinalDiff/identity scope; SPEC §4.3, §4.4.1, §7 Candidate/FinalDiff rows, AC-18/AC-26.

**Dependencies:** Task 12.C.

**Files:**
- Create: `src/vespercode/candidate/final_diff.py`
- Create: `src/vespercode/candidate/identity.py`
- Test: `tests/unit/candidate/test_final_diff.py`
- Test: `tests/unit/candidate/test_identity.py`

**Interfaces:** Produces `FinalDiffPreimageV1`, `FinalDiffEntryV1`, `FinalDiffV1`, `recompute_final_diff(snapshot: SnapshotTreeV1, candidate: CandidateTreeV1, policy: EditablePathPolicyV1) -> FinalDiffV1`, and `build_candidate_identity(snapshot_tree_digest: str, candidate_tree_digest: str, final_diff_digest: str) -> CandidateIdentityV1`.

**Intentionally failing test:**

```python
def test_candidate_identity_ignores_revision_metadata(
    snapshot: SnapshotTreeV1,
    candidate: CandidateTreeV1,
    policy: EditablePathPolicyV1,
) -> None:
    final_diff = recompute_final_diff(snapshot, candidate, policy)
    left = build_candidate_identity(snapshot.root_digest, candidate.digest, final_diff.digest)
    right = build_candidate_identity(snapshot.root_digest, candidate.digest, final_diff.digest)
    assert left.digest == right.digest
```

Expected RED: import failure because FinalDiff and candidate identity do not exist.

**Implementation boundary:** This child deterministically sorts/counts complete postimages, revalidates the sole policy, and hashes only the three declared roots. It cannot apply a patch, publish a revision, approve a writeback, or access the mutable workspace.

**Verification:**
- Target: `python -m pytest -q tests/unit/candidate/test_identity.py::test_candidate_identity_ignores_revision_metadata`
- Domain: `python -m pytest -q tests/unit/candidate/test_final_diff.py tests/unit/candidate/test_identity.py`
- Expected GREEN: both commands exit `0`; CREATE/REPLACE preimages, byte accounting, ordering, policy/tree mismatch, identity restoration, and metadata independence pass.

**Completion evidence:** Not yet executed.

#### Task 14.A: Pure Final-writeback Subject and Binding

**Status:** Not started

**Goal:** Build the immutable final-writeback subject/binding from exact current candidate, policy, validation, Run, and expiry facts.

**Dependencies:** Tasks 7.C, 12.D, 13, 20.B, and 21.C.

**Files:**
- Create: `src/vespercode/governance/writeback_subject.py`
- Test: `tests/unit/governance/test_writeback_subject.py`

**Interfaces:** Produces `FinalWritebackBindingV1`, `FinalWritebackSubjectV1`, and pure `build_final_writeback_subject(binding: FinalWritebackBindingV1, expires_at: CanonicalTimestampV1) -> FinalWritebackSubjectV1`.

**Intentionally failing test:**

```python
def test_subject_digest_changes_when_final_diff_changes() -> None:
    assert build_subject(binding("a")).subject_digest != build_subject(binding("b")).subject_digest
```

**Expected RED:** the closed subject/binding builder does not exist.

**Implementation boundary:** Own pure subject/binding schema, canonical bytes, and digest only. Do not create waits, persist decisions, consume approvals, or write the workspace.

**Verification:**
- Target: `python -m pytest -q tests/unit/governance/test_writeback_subject.py::test_subject_digest_changes_when_final_diff_changes`
- Domain: `python -m pytest -q tests/unit/governance/test_writeback_subject.py`
- Expected GREEN: every bound fact affects the digest and mutable/user-supplied decision facts cannot enter the subject.

**Completion evidence:** Not yet executed.

#### Task 14.B: Final-writeback Wait Decision Lifecycle

**Status:** Not started

**Goal:** Apply APPROVE/REJECT/expiry/stale decisions atomically to the exact final-writeback wait with idempotent event replay.

**Dependencies:** Tasks 4.C, 5.B, 7.B, 7.C, 14.A, and 25.D.

**Files:**
- Create: `src/vespercode/storage/migrations/v0010_writeback_approvals.py`
- Create: `src/vespercode/governance/writeback_decision.py`
- Test: `tests/unit/storage/test_writeback_approvals_migration.py`
- Test: `tests/unit/governance/test_writeback_decision.py`

**Interfaces:** Produces immutable `WRITEBACK_APPROVALS_V1_MIGRATION = MigrationV1(version=10, name="writeback_approvals_v1", ...)`, `DecideFinalWritebackV1`, closed `FinalWritebackDecisionResultV1`, and `FinalWritebackDecisionServiceV1.decide(command: DecideFinalWritebackV1) -> FinalWritebackDecisionResultV1`.

**Intentionally failing test:**

```python
def test_expired_wait_cannot_create_pending_approval(service: FinalWritebackDecisionServiceV1) -> None:
    result = service.decide(approve_expired_wait())
    assert result.kind == "EXPIRED"
    assert service.approval_count() == 0
```

**Expected RED:** no clock-owned atomic decision lifecycle exists.

**Schema RED:** `tests/unit/storage/test_writeback_approvals_migration.py::test_writeback_approval_migration_has_exact_schema` applies the exact v0001–v0009 predecessors plus v0010 and asserts only `final_writeback_subjects` and `final_writeback_approvals`, their subject/wait/Run foreign keys, unique subject/decision constraints, one `PENDING → CONSUMED` winner fields, and absence of postimage/workspace/request/response/secret columns.

**Implementation boundary:** Own one coupled final-writeback decision storage behavior: immutable v0010 DDL, wait locking, current-subject reload, APPROVE/REJECT/expiry/stale result, and idempotent event record. Task 14.C consumes the existing approval row but owns no schema. This task cannot edit the final registry, consume an approval, or persist candidate bytes.

**Verification:**
- Target: `python -m pytest -q tests/unit/governance/test_writeback_decision.py::test_expired_wait_cannot_create_pending_approval`
- Schema: `python -m pytest -q tests/unit/storage/test_writeback_approvals_migration.py::test_writeback_approval_migration_has_exact_schema`
- Domain: `python -m pytest -q tests/unit/storage/test_writeback_approvals_migration.py tests/unit/governance/test_writeback_decision.py`
- Expected GREEN: exact v0010 schema plus approve/reject/expire/stale/replay/conflict cases are atomic and only exact current APPROVE creates one PENDING approval.

**Completion evidence:** Not yet executed.

#### Task 14.C: One-time Concurrent Writeback Approval Consumption

**Status:** Not started

**Goal:** Consume one exact current PENDING final-writeback approval at most once under concurrent/replayed attempts.

**Dependencies:** Tasks 7.A, 7.C, 14.A, 14.B, and 21.C.

**Files:**
- Create: `src/vespercode/governance/writeback_approval.py`
- Test: `tests/unit/governance/test_writeback_approval.py`
- Test: `tests/unit/governance/test_writeback_approval_race.py`

**Interfaces:** Produces `ConsumeWritebackApprovalV1`, `ApprovalConsumptionResultV1`, `WritebackApprovalRepository.consume(command: ConsumeWritebackApprovalV1) -> ApprovalConsumptionResultV1`, and `verify_consumable(approval: FinalWritebackApprovalV1, command: ConsumeWritebackApprovalV1) -> None`.

**Intentionally failing test:**

```python
def test_concurrent_consumers_get_exactly_one_success(repository: WritebackApprovalRepository) -> None:
    results = run_two_consumers(repository, consumable_command())
    assert sorted(result.kind for result in results) == ["ALREADY_CONSUMED", "CONSUMED"]
```

**Expected RED:** no transaction-bound consume-once repository exists.

**Implementation boundary:** Own current-binding verification and one-time consumption transaction only. Do not create/decide waits, construct subjects, or write the workspace.

**Verification:**
- Target: `python -m pytest -q tests/unit/governance/test_writeback_approval_race.py::test_concurrent_consumers_get_exactly_one_success`
- Domain: `python -m pytest -q tests/unit/governance/test_writeback_approval.py tests/unit/governance/test_writeback_approval_race.py`
- Expected GREEN: exactly one matching consumer succeeds and stale/expired/mismatched/replayed attempts create no second consumption.

**Completion evidence:** Not yet executed.

#### Task 15.A: Request-source and Segment Validation

**Status:** Not started

**Goal:** Validate exact request message/segment source categories, paths, content digests, indexes, and byte counts before subject construction.

**Dependencies:** Tasks 4.B and 5.D.

**Files:**
- Create: `src/vespercode/governance/request_sources.py`
- Test: `tests/unit/governance/test_request_sources.py`

**Interfaces:** Produces `RequestSourceCategoryV1`, `RequestContentSegmentV1`, `RequestMessageV1`, `RequestSourceV1`, `RequestMessageSequenceV1`, an immutable ordered tuple of one or more request messages, and `validate_segment_sources(messages: RequestMessageSequenceV1) -> SourceProjectionV1`.

**Intentionally failing test:**

```python
def test_file_segment_requires_canonical_path() -> None:
    with pytest.raises(SourceValidationError, match="FILE_PATH_REQUIRED"):
        validate_segment_sources(messages_with_pathless_file_segment())
```

**Expected RED:** the closed source/segment validator does not exist.

**Implementation boundary:** Own source category/path/index/digest/byte validation only. Do not match Grant scope, build subjects, decide waits, or charge bytes.

**Verification:**
- Target: `python -m pytest -q tests/unit/governance/test_request_sources.py::test_file_segment_requires_canonical_path`
- Domain: `python -m pytest -q tests/unit/governance/test_request_sources.py`
- Expected GREEN: exact source/path rules and content identities pass; missing/duplicate/mismatched segments reject before mutation.

**Completion evidence:** Not yet executed.

#### Task 15.B: Pure Disclosure Scope Matching

**Status:** Not started

**Goal:** Canonicalize disclosure scopes and match ROOT/FILE/DIRECTORY only at exact path-segment boundaries.

**Dependencies:** Tasks 4.D, 5.E, and 15.A.

**Files:**
- Create: `src/vespercode/governance/disclosure_scope.py`
- Test: `tests/unit/governance/test_disclosure_scope.py`

**Interfaces:** Produces `DisclosureScopeSequenceV1`, an immutable canonical ordered tuple of disclosure scopes, `canonicalize_disclosure_scopes(scopes: DisclosureScopeSequenceV1) -> DisclosureScopeSequenceV1`, and pure `scope_matches(scope: DisclosurePathScopeV1, path: CanonicalRelativePathV1) -> bool`.

**Intentionally failing test:**

```python
def test_directory_scope_does_not_match_string_prefix_sibling() -> None:
    assert scope_matches(directory_scope("src"), path("src_backup/a.py")) is False
```

**Expected RED:** the canonical segment-boundary matcher does not exist.

**Implementation boundary:** Own pure scope canonicalization/matching only. Do not inspect message bodies, build Grants, persist decisions, or authorize requests.

**Verification:**
- Target: `python -m pytest -q tests/unit/governance/test_disclosure_scope.py::test_directory_scope_does_not_match_string_prefix_sibling`
- Domain: `python -m pytest -q tests/unit/governance/test_disclosure_scope.py`
- Expected GREEN: ROOT/FILE/DIRECTORY semantics, alias rejection, ordering, duplicate, and empty-scope cases pass exactly.

**Completion evidence:** Not yet executed.

#### Task 15.C: Pure Disclosure Grant Subject

**Status:** Not started

**Goal:** Build the immutable disclosure Grant subject from validated sources, canonical scopes/categories, frozen profile, endpoint, serializer, and expiry.

**Dependencies:** Tasks 4.C, 6.C, 6.D, 15.A, and 15.B.

**Files:**
- Create: `src/vespercode/governance/disclosure_subject.py`
- Test: `tests/unit/governance/test_disclosure_subject.py`

**Interfaces:** Produces `DisclosureGrantSubjectV1` and pure `build_disclosure_subject(request: DisclosureSubjectRequestV1, sources: SourceProjectionV1, scopes: DisclosureScopeSequenceV1, profile: OpenAILLMProfileV1, endpoint: OpenAIEndpointV1) -> DisclosureGrantSubjectV1`.

**Intentionally failing test:**

```python
def test_subject_uses_frozen_endpoint_not_request_url() -> None:
    with pytest.raises(DisclosureSubjectError, match="ENDPOINT_OVERRIDE"):
        build_disclosure_subject(request_with_url_override(), sources(), scopes(), profile(), endpoint())
```

**Expected RED:** no immutable Grant subject builder binds the frozen sources/profile/endpoint.

**Implementation boundary:** Own pure subject bytes/digest only. Do not create a wait/Grant, revoke, charge bytes, or call an adapter.

**Verification:**
- Target: `python -m pytest -q tests/unit/governance/test_disclosure_subject.py::test_subject_uses_frozen_endpoint_not_request_url`
- Domain: `python -m pytest -q tests/unit/governance/test_disclosure_subject.py`
- Expected GREEN: every immutable authorization fact is bound and all endpoint/model/source/scope/expiry overrides reject.

**Completion evidence:** Not yet executed.

#### Task 15.D: Disclosure Grant Decision Lifecycle

**Status:** Not started

**Goal:** Atomically approve/reject/expire/stale/replay the exact disclosure wait and create at most one matching active Grant.

**Dependencies:** Tasks 4.C, 5.B, 7.B, 7.C, and 15.C.

**Files:**
- Create: `src/vespercode/storage/migrations/v0003_disclosure_grants.py`
- Create: `src/vespercode/governance/disclosure_decision.py`
- Test: `tests/unit/storage/test_disclosure_grants_migration.py`
- Test: `tests/unit/governance/test_disclosure_decision.py`

**Interfaces:** Produces immutable `DISCLOSURE_GRANTS_V1_MIGRATION = MigrationV1(version=3, name="disclosure_grants_v1", ...)`, `DisclosureGrantV1`, `DecideDisclosureGrantV1`, `DisclosureDecisionResultV1`, and `DisclosureDecisionServiceV1.decide(command: DecideDisclosureGrantV1) -> DisclosureDecisionResultV1`.

**Intentionally failing test:**

```python
def test_expired_disclosure_wait_creates_no_grant(service: DisclosureDecisionServiceV1) -> None:
    assert service.decide(approve_expired_disclosure()).kind == "EXPIRED"
    assert service.grant_count() == 0
```

**Expected RED:** no transaction-bound Grant decision lifecycle exists.

**Schema RED:** `tests/unit/storage/test_disclosure_grants_migration.py::test_disclosure_grant_migration_has_exact_schema` applies v0001–v0003 and asserts only `disclosure_grant_subjects` and `disclosure_grants`, exact Run/wait/subject foreign keys, unique active decision/Grant identities, cumulative-byte/status bounds including `ACTIVE/REVOKED`, and absence of segment/request/response/credential bodies. Task 15.F records revocation by the exact active-to-revoked update on this table; SPEC defines no separate revocation entity/table.

**Implementation boundary:** Own one coupled Grant-decision storage behavior: immutable v0003 DDL, wait decision, active Grant creation, expiry/stale/replay handling, idempotency, and return-to-loop transition. It cannot edit the final registry, perform Task 15.F revocation, validate request bodies, or authorize/charge a prepared request.

**Verification:**
- Target: `python -m pytest -q tests/unit/governance/test_disclosure_decision.py::test_expired_disclosure_wait_creates_no_grant`
- Schema: `python -m pytest -q tests/unit/storage/test_disclosure_grants_migration.py::test_disclosure_grant_migration_has_exact_schema`
- Domain: `python -m pytest -q tests/unit/storage/test_disclosure_grants_migration.py tests/unit/governance/test_disclosure_decision.py`
- Expected GREEN: exact v0003 schema plus approve/reject/expire/stale/replay cases are atomic and never create duplicate/invalid Grants.

**Completion evidence:** Not yet executed.

#### Task 15.E: Transactional Disclosure Authorization Ledger

**Status:** Not started

**Goal:** Revalidate one prepared request against the current active Grant and atomically charge cumulative bytes exactly once under races.

**Dependencies:** Tasks 7.A, 7.C, 15.A, 15.B, 15.C, 15.D, and 15.F.

**Files:**
- Create: `src/vespercode/storage/migrations/v0004_disclosure_authorizations.py`
- Create: `src/vespercode/governance/disclosure_ledger.py`
- Test: `tests/unit/storage/test_disclosure_authorizations_migration.py`
- Test: `tests/unit/governance/test_disclosure_ledger.py`
- Test: `tests/unit/governance/test_disclosure_budget_race.py`

**Interfaces:** Produces immutable `DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION = MigrationV1(version=4, name="disclosure_authorizations_v1", ...)`, `AuthorizePreparedRequestV1`, `DisclosureAuthorizationRecordV1`, `DisclosureAuthorizationOutcomeV1`, and `DisclosureLedger.authorize(command: AuthorizePreparedRequestV1) -> DisclosureAuthorizationOutcomeV1`.

**Intentionally failing test:**

```python
def test_two_requests_cannot_overdraw_one_grant(ledger: DisclosureLedger) -> None:
    results = authorize_concurrently(ledger, two_requests_each_requiring_remaining_budget())
    assert sum(result.kind == "AUTHORIZED" for result in results) == 1
```

**Expected RED:** no immediate-transaction authorization/byte-charge ledger exists.

**Schema RED:** `tests/unit/storage/test_disclosure_authorizations_migration.py::test_disclosure_authorization_migration_has_exact_schema` applies v0001–v0004 and asserts the sole `disclosure_authorizations` table, FK `grant_id → disclosure_grants`, unique request/charge identity, exact body-free actual-source projection/digests/byte counts, and absence of content, complete request/response, credential, or refund columns.

**Implementation boundary:** Own one coupled authorization-ledger storage behavior: immutable v0004 DDL, fresh Grant/subject/scope/category/request/budget revalidation, and body-free authorization record. It cannot edit the final registry, decide/revoke Grants, serialize/call an LLM, or refund committed charges.

**Verification:**
- Target: `python -m pytest -q tests/unit/governance/test_disclosure_budget_race.py::test_two_requests_cannot_overdraw_one_grant`
- Schema: `python -m pytest -q tests/unit/storage/test_disclosure_authorizations_migration.py::test_disclosure_authorization_migration_has_exact_schema`
- Domain: `python -m pytest -q tests/unit/storage/test_disclosure_authorizations_migration.py tests/unit/governance/test_disclosure_ledger.py tests/unit/governance/test_disclosure_budget_race.py`
- Expected GREEN: exact v0004 schema; only exact authorized requests commit one charge; scope/expiry/revocation/budget/race failures charge zero.

**Completion evidence:** Not yet executed.

#### Task 15.F: Active Disclosure Grant Revocation

**Status:** Not started

**Goal:** Atomically revoke only the exact matching active disclosure Grant, with idempotent replay and no mutation for stale or mismatched subjects.

**Dependencies:** Tasks 7.A, 7.C, 15.C, and 15.D.

**Files:**
- Create: `src/vespercode/governance/disclosure_revocation.py`
- Test: `tests/unit/governance/test_disclosure_revocation.py`

**Interfaces:** Produces `RevokeDisclosureGrantV1`, `GrantMutationResultV1`, and `DisclosureRevocationServiceV1.revoke(command: RevokeDisclosureGrantV1) -> GrantMutationResultV1`.

**Intentionally failing test:**

```python
def test_revoke_rejects_mismatched_subject(
    service: DisclosureRevocationServiceV1,
) -> None:
    result = service.revoke(revoke_command_for_other_subject())
    assert result.kind == "SUBJECT_MISMATCH"
    assert service.active_grant_count() == 1
```

**Expected RED:** no separate transaction-bound disclosure revocation service exists.

**Implementation boundary:** Own active-to-revoked mutation, subject/run binding, and idempotent revocation replay only. Do not approve/reject/expire waits, create Grants, authorize prepared requests, charge budgets, or refund committed charges.

**Verification:**
- Target: `python -m pytest -q tests/unit/governance/test_disclosure_revocation.py::test_revoke_rejects_mismatched_subject`
- Domain: `python -m pytest -q tests/unit/governance/test_disclosure_revocation.py`
- Expected GREEN: only the exact active Grant revokes once; stale/mismatched/replayed commands are deterministic, mutate no unrelated Grant, and both commands exit `0`.

**Completion evidence:** Not yet executed.

#### Task 16.A: Closed Prepared Requests and Deterministic Mock Adapter

**Status:** Not started

**Goal:** Build closed Mock/OpenAI prepared-request contracts and a deterministic Mock adapter with no provider, credential, Grant, authorization, or network behavior.

**SPEC references:** Milestone 16 references; owns common LLM protocol, prepared requests, Mock adapter, and closed call-result schema.

**Dependencies:** Tasks 6.E and 15.E.

**Blocks:** Tasks 16.B, 17.A, and 37.B.

**Parallelization:** Parallelizable with Task 9.A once each exact executable Dependencies field is satisfied; Task 16.A itself does not consume credentials.

**Branch/worktree:** `codex/task-16a-prepared-mock`; `.worktrees/task-16a-prepared-mock`.

**Files:**
- Create: `src/vespercode/llm/base.py`
- Create: `src/vespercode/llm/prepared_request.py`
- Create: `src/vespercode/llm/mock_adapter.py`
- Create: `src/vespercode/llm/call_result.py`
- Test: `tests/unit/llm/test_prepared_request.py`
- Test: `tests/unit/llm/test_mock_adapter.py`
- Test: `tests/unit/llm/test_call_result.py`

**Interfaces:** Produces protocol `LLMAdapter.generate(request: PreparedModelRequestV1) -> ModelResponse`, closed `PreparedModelRequestV1 = MockPreparedModelRequestV1 | OpenAIPreparedModelRequestV1`, `ModelResponse`, closed `LLMCallResultV1`, `prepare_mock_request(profile: MockLLMProfileV1, messages: tuple[RequestMessageV1, ...]) -> MockPreparedModelRequestV1`, `prepare_openai_request(profile: OpenAILLMProfileV1, messages: tuple[RequestMessageV1, ...]) -> OpenAIPreparedModelRequestV1`, and `MockLLMAdapter.generate(request: MockPreparedModelRequestV1) -> ModelResponse`.

**Intentionally failing test:**

```python
def test_mock_request_rejects_openai_transport_fields() -> None:
    with pytest.raises(ValidationError):
        MockPreparedModelRequestV1.model_validate(
            valid_mock_request() | {"endpoint_id": "OPENAI_PUBLIC_API_V1"}
        )
```

**Implementation boundary:** Mock outputs are selected only by frozen script id and request digest. No Mock code imports OpenAI transport, credentials, disclosure ledger, or a network client.

**Verification:**
- Target: `python -m pytest -q tests/unit/llm/test_prepared_request.py::test_mock_request_rejects_openai_transport_fields`
- Domain: `python -m pytest -q tests/unit/llm/test_prepared_request.py tests/unit/llm/test_mock_adapter.py tests/unit/llm/test_call_result.py`
- Expected: closed mode/status combinations and byte-identical Mock responses pass offline with zero real-capability calls.

**Completion evidence:** Not yet executed.

#### Task 16.B: Single-call OpenAI Serialization and Transport

**Status:** Not started

**Goal:** Serialize one authorized `OpenAIPreparedModelRequestV1` to the sole trusted endpoint and perform at most one non-retried transport call through a freshly bound adapter.

**SPEC references:** Milestone 16 references; owns OpenAI serialization, redirect/endpoint enforcement, transport invocation, and error projection.

**Dependencies:** Tasks 15.E, 16.A, and 27.B.

**Blocks:** Tasks 17.C, 24.B, 25.C, 29.B, 31.A, 31.B, 32.C, and 37.B.

**Parallelization:** Sequential after Task 16.A.

**Branch/worktree:** `codex/task-16b-openai-adapter`; `.worktrees/task-16b-openai-adapter`.

**Files:**
- Create: `src/vespercode/llm/openai_serializer.py`
- Create: `src/vespercode/llm/openai_adapter.py`
- Test: `tests/unit/llm/test_openai_serializer.py`
- Test: `tests/unit/llm/test_openai_adapter.py`

**Interfaces:** Produces `serialize_openai_request(request: OpenAIPreparedModelRequestV1) -> OpenAIRequestBodyV1`, `OpenAILLMAdapter.bind(authorization: DisclosureAuthorizationRecordV1, credential: SecretCredentialV1) -> BoundOpenAILLMAdapterV1`, and `BoundOpenAILLMAdapterV1.generate(request: OpenAIPreparedModelRequestV1) -> ModelResponse`; consumes only Task 15.E authorization and a Task 27.B fresh secret wrapper supplied for this call.

**Intentionally failing test:**

```python
def test_openai_adapter_never_retries_transport(
    adapter: OpenAILLMAdapter,
    failing_transport: RecordingTransport,
) -> None:
    bound = adapter.bind(valid_authorization(), test_secret())
    with pytest.raises(OpenAITransportFailure):
        bound.generate(valid_openai_prepared_request())
    assert failing_transport.call_count == 1
```

**Implementation boundary:** The unbound adapter cannot generate. The bound adapter accepts no custom base URL, alternate endpoint, retry policy, environment credential, or redirect replay and returns only `ModelResponse` or raises one bounded typed adapter failure. Per-call credential/Grant/count ordering and `LLMCallResultV1` construction belong to Task 25.C.

**Verification:**
- Target: `python -m pytest -q tests/unit/llm/test_openai_adapter.py::test_openai_adapter_never_retries_transport`
- Domain: `python -m pytest -q tests/unit/llm/test_openai_serializer.py tests/unit/llm/test_openai_adapter.py`
- Expected: exact body vectors, one transport call, trusted endpoint enforcement, bounded responses, and redacted failures pass.

**Completion evidence:** Not yet executed.

#### Task 17.A: Strict Single-action Model Response Parser

**Status:** Not started

**Goal:** Parse exactly one closed model action object with no surrounding text, defaults, unknown fields, or model-supplied Harness identity.

**Dependencies:** Tasks 5.C, 11.B, 12.A, and 16.A.

**Files:**
- Create: `src/vespercode/loop/agent_actions.py`
- Create: `src/vespercode/loop/action_parser.py`
- Test: `tests/unit/loop/test_agent_actions.py`
- Test: `tests/unit/loop/test_action_parser.py`

**Interfaces:** Produces closed `AgentAction`, `ModelResponse`, `ParseErrorV1`, and `ActionParser.parse(response: ModelResponse) -> AgentAction | ParseErrorV1`.

**Intentionally failing test:**

```python
def test_model_supplied_action_id_is_rejected(parser: ActionParser) -> None:
    assert parser.parse(response_with_action_id()).error_code == "UNKNOWN_FIELD"
```

**Expected RED:** the strict parser/action union does not exist.

**Implementation boundary:** Own response JSON framing and closed action schema only. Do not generate identity, evaluate policy/phase, or dispatch tools.

**Verification:**
- Target: `python -m pytest -q tests/unit/loop/test_action_parser.py::test_model_supplied_action_id_is_rejected`
- Domain: `python -m pytest -q tests/unit/loop/test_agent_actions.py tests/unit/loop/test_action_parser.py`
- Expected GREEN: exactly one valid action parses and every framing/field/type/omission/default/identity violation returns a stable parse error.

**Completion evidence:** Not yet executed.

#### Task 17.B: Harness-owned Action Identity Binding

**Status:** Not started

**Goal:** Bind one parsed action to a Harness-generated non-empty ID plus canonical semantic and instance digests.

**Dependencies:** Tasks 4.B, 5.C, and 17.A.

**Files:**
- Create: `src/vespercode/loop/action_binding.py`
- Test: `tests/unit/loop/test_action_binding.py`

**Interfaces:** Produces `ActionIdGeneratorV1.next_id() -> str`, `action_semantic_digest(action: AgentAction) -> str`, and `bind_action(action: AgentAction, id_generator: ActionIdGeneratorV1) -> ActionInstanceV1`.

**Intentionally failing test:**

```python
def test_same_semantics_different_harness_ids_change_instance_digest() -> None:
    left = bind_action(action(), fixed_ids("a1"))
    right = bind_action(action(), fixed_ids("a2"))
    assert left.semantic_digest == right.semantic_digest
    assert left.instance_digest != right.instance_digest
```

**Expected RED:** no canonical action identity binder exists.

**Implementation boundary:** Own action semantic/instance identity only. Do not parse responses, calculate List/Search query cursors, evaluate policy, or dispatch.

**Verification:**
- Target: `python -m pytest -q tests/unit/loop/test_action_binding.py::test_same_semantics_different_harness_ids_change_instance_digest`
- Domain: `python -m pytest -q tests/unit/loop/test_action_binding.py`
- Expected GREEN: semantic and instance identities bind exact action bytes/ID and reject empty, duplicate, or malformed Harness IDs.

**Completion evidence:** Not yet executed.

#### Task 17.C: Ordered Guarded Tool Dispatcher

**Status:** Not started

**Goal:** Dispatch a bound action only after current-candidate, path/object, phase, and policy gates pass in the required order.

**Dependencies:** Tasks 9.D, 11.B, 12.D, 13, 16.B, and 17.B.

**Files:**
- Create: `src/vespercode/tools/dispatcher.py`
- Test: `tests/unit/tools/test_dispatcher.py`
- Test: `tests/unit/tools/test_dispatch_order.py`

**Interfaces:** Produces `DispatchContextV1`, `ArtifactStorePortV1.put(payload: FileToolResultV1) -> ArtifactRefV1`, `FileToolOutcomeV1`, `publish_file_tool_outcome(instance: ActionInstanceV1, result: FileToolResultV1, artifact_store: ArtifactStorePortV1) -> FileToolOutcomeV1`, `ToolPortsV1(list_files, read_file, search_text, apply_candidate_patch, run_check, propose_completion)` whose three file ports use the exact Task 11.A/11.B pure signatures, and `ToolDispatcher.dispatch(instance: ActionInstanceV1, context: DispatchContextV1) -> ActionResultV1`.

**Intentionally failing test:**

```python
def test_hard_deny_never_invokes_tool_port(dispatcher: ToolDispatcher, ports: SpyToolPorts) -> None:
    result = dispatcher.dispatch(denied_instance(), denied_context(ports))
    assert result.error.code == "POLICY_DENY"
    assert ports.total_calls == 0
```

**Expected RED:** no ordered guarded dispatcher exists.

**Implementation boundary:** Own deterministic pre-dispatch ordering, exact port selection, Task 11 pure-result conversion, bounded ArtifactStore publication, result-envelope validation, and exception conversion. Do not parse/bind actions, implement tools, or create approval waits.

**Verification:**
- Target: `python -m pytest -q tests/unit/tools/test_dispatch_order.py::test_hard_deny_never_invokes_tool_port`
- Domain: `python -m pytest -q tests/unit/tools/test_dispatcher.py tests/unit/tools/test_dispatch_order.py`
- Expected GREEN: stale/path/phase/policy failures call zero ports; only an exact allowed current action invokes one registered port.

**Completion evidence:** Not yet executed.

#### Task 18.A: Closed Docker Execution Request and Readiness

**Status:** Not started

**Goal:** Build and validate the sole executable/profile/environment/resource request and verify the frozen reference image is locally ready.

**Dependencies:** Tasks 2.G, 5.D, and 6.E.

**Files:**
- Create: `src/vespercode/execution/docker_profile.py`
- Test: `tests/unit/execution/test_docker_profile.py`
- Test: `tests/unit/execution/test_docker_request.py`

**Interfaces:** Produces `ExecutionArgumentSequenceV1`, an immutable ordered tuple of command arguments, `DockerExecutionProfileV1`, `ExecutionRequestV1`, and `DockerReadinessService.verify(reference: ReferenceProfileManifestV1) -> ExecutionReadinessResultV1`.

**Intentionally failing test:**

```python
def test_execution_request_rejects_model_executable_field() -> None:
    with pytest.raises(ValidationError):
        ExecutionRequestV1.model_validate(request_with_executable())
```

**Expected RED:** the closed request/profile/readiness contracts do not exist.

**Implementation boundary:** Own schema/resource/profile readiness only. Do not materialize trees, create containers, collect output, interpret results, or build/install images.

**Verification:**
- Target: `python -m pytest -q tests/unit/execution/test_docker_request.py::test_execution_request_rejects_model_executable_field`
- Domain: `python -m pytest -q tests/unit/execution/test_docker_profile.py tests/unit/execution/test_docker_request.py`
- Expected GREEN: only adapter-built frozen argv/environment/resources validate and image/profile/daemon drift fails before container creation.

**Completion evidence:** Not yet executed.

#### Task 18.B: Fresh Candidate Materialization

**Status:** Not started

**Goal:** Materialize one verified CandidateTree into a fresh identity-bound execution root and verify exact bytes before container creation.

**Dependencies:** Tasks 4.E, 9.D, 10.C, 12.D, and 18.A.

**Files:**
- Create: `src/vespercode/execution/materialization.py`
- Test: `tests/unit/execution/test_materialization.py`
- Test: `tests/integration/docker/test_fresh_candidate_materialization.py`

**Interfaces:** Produces `AuthorizedExecutionRootV1`, `MaterializedCandidateV1`, and `materialize_candidate(candidate: CandidateTreeV1, root: AuthorizedExecutionRootV1) -> MaterializedCandidateV1`.

**Intentionally failing test:**

```python
def test_materialization_rejects_content_object_digest_drift() -> None:
    with pytest.raises(MaterializationError, match="CONTENT_DIGEST_MISMATCH"):
        materialize_candidate(candidate_with_corrupt_object(), fresh_root())
```

**Expected RED:** no fresh identity-bound candidate materializer exists.

**Implementation boundary:** Own fresh root allocation, exact content write, identity/path verification, and pre-execution digest. Do not create containers, interpret checks, or persist to the real workspace.

**Verification:**
- Target: `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_fresh_candidate_materialization.py::test_materialization_rejects_content_object_digest_drift`
- Domain: `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_fresh_candidate_materialization.py`
- Expected GREEN: each invocation creates a unique verified root and every content/path/object drift fails before Docker.

**Completion evidence:** Not yet executed.

#### Task 18.C: Isolated Docker Check Execution

**Status:** Not started

**Goal:** Execute one closed request in one fresh locked container with no network/root/write/socket and bounded time/resources/output.

**Dependencies:** Tasks 2.G, 18.A, and 18.B.

**Files:**
- Create: `src/vespercode/execution/docker_executor.py`
- Test: `tests/unit/execution/test_docker_executor.py`
- Test: `tests/integration/docker/test_execution_isolation.py`
- Test: `tests/integration/docker/test_execution_output_limits.py`

**Interfaces:** Produces `RawExecutionResultV1` and `DockerExecutor.execute(request: ExecutionRequestV1, candidate: MaterializedCandidateV1) -> RawExecutionResultV1`.

**Intentionally failing test:**

```python
def test_output_limit_kills_exact_container(executor: DockerExecutor) -> None:
    result = executor.execute(output_flood_request(), materialized_candidate())
    assert result.error_code == "CHECK_OUTPUT_LIMIT_EXCEEDED"
    assert result.container_stopped is True
```

**Expected RED:** no bounded real Docker executor exists.

**Implementation boundary:** Own container creation, isolation, deadline, bounded collectors, stop/kill, and raw evidence only. Do not parse PASS/FAIL or delete materialization roots.

**Verification:**
- Target: `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_execution_output_limits.py::test_output_limit_kills_exact_container`
- Domain: `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_execution_isolation.py tests/integration/docker/test_execution_output_limits.py`
- Expected GREEN: exact isolation/resource/deadline/output controls hold and each execution returns bounded raw evidence.

**Completion evidence:** Not yet executed.

#### Task 18.D: Execution Post-integrity and Cleanup

**Status:** Not started

**Goal:** Reverify Candidate/materialization bytes after execution and remove the exact container/root without following links or hiding residue.

**Dependencies:** Tasks 10.C, 12.D, and 18.C.

**Files:**
- Create: `src/vespercode/execution/cleanup.py`
- Test: `tests/integration/docker/test_execution_cleanup.py`
- Test: `tests/integration/docker/test_execution_workspace_integrity.py`

**Interfaces:** Produces `ExecutionCleanupResultV1(container_removed: bool, materialization_removed: bool, workspace_unchanged: bool, residual_artifact: ArtifactRefV1 | None)` and `finalize_execution(result: RawExecutionResultV1, candidate: CandidateTreeV1, materialized: MaterializedCandidateV1) -> ExecutionCleanupResultV1`.

**Intentionally failing test:**

```python
def test_post_execution_candidate_mutation_fails_closed() -> None:
    result = finalize_execution(raw_result(), candidate(), mutated_materialization())
    assert result.workspace_unchanged is False
```

**Expected RED:** no post-integrity/cleanup verifier exists.

**Implementation boundary:** Own post-run byte verification and exact cleanup/residue evidence only. Do not execute checks, classify check outcomes, reuse roots, or mutate the real workspace.

**Verification:**
- Target: `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_execution_workspace_integrity.py::test_post_execution_candidate_mutation_fails_closed`
- Domain: `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_execution_cleanup.py tests/integration/docker/test_execution_workspace_integrity.py`
- Expected GREEN: clean runs remove exact resources; mutation/link/cleanup failures return explicit non-success residue evidence.

**Completion evidence:** Not yet executed.

#### Task 19.A: Closed Check Results and Static-tool Parsing

**Status:** Not started

**Goal:** Convert bounded Ruff and Mypy executions into the sole closed `CheckResultV1` combinations and fail malformed, truncated, or version-inconsistent output closed.

**SPEC references:** Milestone 19 check-result scope; SPEC §4.5 check execution/errors, §5.2, and AC-19/AC-20/AC-24.

**Dependencies:** Tasks 4.E, 5.D, 6.E, and 18.D.

**Files:**
- Create: `src/vespercode/validation/check_result.py`
- Test: `tests/unit/validation/test_check_result.py`
- Test: `tests/unit/validation/test_ruff_mypy_parsing.py`

**Interfaces:** Produces `CheckFindingSequenceV1`, an immutable ordered tuple of zero or more `CheckFindingV1` items, `CheckResultV1(status: Literal["PASS","FAIL","ERROR","TIMEOUT","NOT_RUN"], check_kind: CheckPlanIdV1, structured_findings: CheckFindingSequenceV1, raw_digest: str)`, `parse_ruff_result(raw: RawExecutionResultV1, profile: ReferenceProfileManifestV1) -> CheckResultV1`, and `parse_mypy_result(raw: RawExecutionResultV1, profile: ReferenceProfileManifestV1) -> CheckResultV1`.

**Intentionally failing test:**

```python
def test_truncated_ruff_output_is_check_error(
    reference_profile: ReferenceProfileManifestV1,
) -> None:
    result = parse_ruff_result(truncated_ruff_execution(), reference_profile)
    assert result.status == "ERROR"
    assert result.structured_findings[0].error_code == "CHECK_ERROR"
```

Expected RED: import failure because the check-result schema and static-tool parsers do not exist.

**Implementation boundary:** This child validates only closed status/finding combinations and profile-frozen Ruff/Mypy formats. It does not emit/parse pytest reports, normalize failures, execute containers, or decide Baseline success.

**Verification:**
- Target: `python -m pytest -q tests/unit/validation/test_ruff_mypy_parsing.py::test_truncated_ruff_output_is_check_error`
- Domain: `python -m pytest -q tests/unit/validation/test_check_result.py tests/unit/validation/test_ruff_mypy_parsing.py`
- Expected GREEN: both commands exit `0`; PASS/FAIL/error/version/malformed/truncated combinations map to the closed schema.

**Completion evidence:** Not yet executed.

#### Task 19.B: Authoritative Pytest Event Report

**Status:** Not started

**Goal:** Emit and validate one complete ordered pytest event report whose integrity and normal end are authoritative over exit code or console text.

**SPEC references:** Milestone 19 pytest-evidence scope; SPEC §4.5 `PytestEvidenceV1`, trust boundary, and AC-19/AC-25.

**Dependencies:** Task 19.A.

**Files:**
- Create: `src/vespercode/validation/pytest_evidence.py`
- Create: `src/vespercode/validation/pytest_reporter.py`
- Test: `tests/unit/validation/test_pytest_evidence.py`
- Test: `tests/unit/validation/test_pytest_reporter.py`
- Test: `tests/integration/docker/test_pytest_report_channel.py`

**Interfaces:** Produces `ErrorPhase`, `TestStatus`, `PytestEventV1`, `PytestEvidenceV1`, `StructuredExceptionV1`, and `parse_pytest_evidence(raw: bytes, expectation: PytestReportExpectationV1) -> PytestParseOutcomeV1`.

**Intentionally failing test:**

```python
def test_missing_session_end_is_reporter_invalid(
    complete_pytest_report_dict: dict[str, object],
) -> None:
    complete_pytest_report_dict["events"] = complete_pytest_report_dict["events"][:-1]
    complete_pytest_report_dict["integrity_digest"] = recompute_report_digest(complete_pytest_report_dict)
    outcome = parse_pytest_evidence(canonical_json_bytes(complete_pytest_report_dict), expected_full_pytest_report())
    assert outcome.error_code == "REPORTER_INVALID"
    assert outcome.evidence is None
```

Expected RED: import failure because the production reporter/parser do not exist.

**Implementation boundary:** This child owns plugin emission, report-channel bounds, complete schema/sequence/collection/version/digest validation, and stable reporter errors only. It cannot synthesize PASS from exit code/stdout, build fingerprints, or run Baseline.

**Verification:**
- Target: `python -m pytest -q tests/unit/validation/test_pytest_evidence.py::test_missing_session_end_is_reporter_invalid`
- Domain: `python -m pytest -q tests/unit/validation/test_pytest_evidence.py tests/unit/validation/test_pytest_reporter.py`
- Docker: `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_pytest_report_channel.py`
- Expected GREEN: all commands exit `0`; corruption matrices pass offline and the real Docker report channel passes without a required skip.

**Completion evidence:** Not yet executed.

#### Task 19.C: Stable Target Failure Fingerprint

**Status:** Not started

**Goal:** Produce a stable fingerprint only for one complete exact target `CALL/FAIL`, with allowlisted volatility removed and user failure content preserved.

**SPEC references:** Milestone 19 fingerprint scope; SPEC §4.5 fingerprint normalization, AC-25, and AC-26.

**Dependencies:** Task 19.B.

**Files:**
- Create: `src/vespercode/validation/failure_fingerprint.py`
- Test: `tests/unit/validation/test_failure_fingerprint.py`

**Interfaces:** Produces `FailureFingerprintV1`, `ProjectFrameSignatureV1`, and `build_failure_fingerprint(evidence: PytestEvidenceV1, node_id: str, normalization: FingerprintNormalizationContextV1) -> FingerprintOutcomeV1`.

**Intentionally failing test:**

```python
def test_user_hexadecimal_value_is_not_normalized_away(
    failing_evidence: PytestEvidenceV1,
) -> None:
    outcome = build_failure_fingerprint(failing_evidence, "tests/test_a.py::test_value", normalization_context())
    assert outcome.kind == "STABLE"
    assert "deadbeef" in outcome.normalized_exception_text
```

Expected RED: import failure because fingerprint normalization does not exist.

**Implementation boundary:** This child consumes complete Task 19.B evidence and normalizes only the execution root, tmp root, run/container id, and reporter-marked object addresses. It does not parse raw reports, execute checks, compare Baselines, or normalize user numbers/time/hex text.

**Verification:**
- Target: `python -m pytest -q tests/unit/validation/test_failure_fingerprint.py::test_user_hexadecimal_value_is_not_normalized_away`
- Domain: `python -m pytest -q tests/unit/validation/test_failure_fingerprint.py`
- Expected GREEN: both commands exit `0`; CALL/FAIL gating, frame inclusion, assertion-diff absence, stable allowlist, and TARGET_UNSTABLE cases pass.

**Completion evidence:** Not yet executed.

#### Task 20.A: Static Python Support Detection and Frozen Check Plan

**Status:** Not started

**Goal:** Determine support from one sealed Snapshot without execution and generate the complete closed Python check plan.

**SPEC references:** Milestone 20 references; owns static detection and adapter-generated collect/full/target/Ruff/Mypy plans.

**Dependencies:** Tasks 5.D, 6.E, 8.B, and 10.C.

**Blocks:** Tasks 20.B and 37.B.

**Parallelization:** Parallelizable with Task 22.A once the exact Dependencies of both executable children are satisfied.

**Branch/worktree:** `codex/task-20a-python-check-plan`; `.worktrees/task-20a-python-check-plan`.

**Files:**
- Create: `src/vespercode/validation/python_adapter.py`
- Test: `tests/unit/validation/test_python_adapter_static.py`
- Test: `tests/unit/validation/test_check_plan.py`

**Interfaces:** Produces `TargetTestIdSequenceV1`, an immutable ordered tuple of one or more target ids, `StaticProjectProfileResultV1 = SupportedProjectV1 | UnsupportedProjectV1`, `PythonProjectAdapterV1.detect_static(snapshot: SnapshotTreeV1, reference_manifest: ReferenceProfileManifestV1) -> StaticProjectProfileResultV1`, `PythonProjectAdapterV1.build_baseline_plan(static_profile: SupportedProjectV1, target_test_ids: TargetTestIdSequenceV1) -> BaselineCheckPlanV1`, and `PythonProjectAdapterV1.build_formal_plan(manifest: ValidationManifestV1, candidate: CandidateIdentityV1) -> FormalValidationCheckPlanV1`.

**Intentionally failing test:**

```python
def test_static_unsupported_result_performs_no_execution(
    adapter: PythonProjectAdapterV1,
    executor: SpyExecutor,
) -> None:
    result = adapter.detect_static(unsupported_snapshot(), frozen_reference_manifest())
    assert result.kind == "UNSUPPORTED"
    assert executor.call_count == 0
```

**Implementation boundary:** Detection reads only Snapshot facts. Runtime/import/tool compatibility is not static unsupported and belongs to Task 20.B.

**Verification:**
- Target: `python -m pytest -q tests/unit/validation/test_python_adapter_static.py::test_static_unsupported_result_performs_no_execution`
- Domain: `python -m pytest -q tests/unit/validation/test_python_adapter_static.py tests/unit/validation/test_check_plan.py`
- Expected: supported/unsupported classifications and exact closed argv/order vectors pass with zero static execution.

**Completion evidence:** Not yet executed.

#### Task 20.B: Stable Baseline and ValidationManifestV1

**Status:** Not started

**Goal:** Execute the frozen baseline sequence, require stable target failure evidence, and publish `ValidationManifestV1` only after every baseline predicate succeeds.

**SPEC references:** Milestone 20 references; owns runtime compatibility, baseline orchestration, stable fingerprint comparison, and Manifest publication.

**Dependencies:** Tasks 18.D, 19.C, and 20.A.

**Blocks:** Tasks 14.A, 21.A, 21.C, 31.A, 34.A, and 37.B.

**Parallelization:** Sequential after Task 20.A.

**Branch/worktree:** `codex/task-20b-baseline-manifest`; `.worktrees/task-20b-baseline-manifest`.

**Files:**
- Create: `src/vespercode/validation/baseline.py`
- Create: `src/vespercode/validation/manifest.py`
- Test: `tests/unit/validation/test_baseline.py`
- Test: `tests/unit/validation/test_runtime_compatibility.py`
- Test: `tests/unit/validation/test_manifest.py`
- Test: `tests/integration/docker/test_reference_baseline.py`

**Interfaces:** Produces `BaselineResultV1 = PassingBaselineV1 | BaselineBlockedV1`, `run_baseline(plan: BaselineCheckPlanV1, snapshot: SnapshotTreeV1, executor: DockerExecutor) -> BaselineResultV1`, and `create_validation_manifest(baseline: PassingBaselineV1, bindings: ManifestBindingsV1) -> ValidationManifestV1`; consumes Task 20.A's exact plan, Task 18.D closed execution boundary, and Task 19.C authoritative check/fingerprint evidence.

**Intentionally failing test:**

```python
def test_unstable_target_fingerprint_creates_no_manifest(
    baseline_fixture: BaselineFixture,
    executor: DockerExecutor,
) -> None:
    result = run_baseline(
        baseline_fixture.plan_with_mismatched_target_fingerprints,
        baseline_fixture.snapshot,
        executor,
    )
    assert isinstance(result, BaselineBlockedV1)
    assert result.reason == "BASELINE_UNSTABLE"
```

**Implementation boundary:** Every check gets a fresh execution. Forbidden pytest states, non-target failure, collection drift, incomplete report, Ruff/Mypy failure, or unstable full/target fingerprints prevent Manifest creation.

**Verification:**
- Target: `python -m pytest -q tests/unit/validation/test_baseline.py::test_unstable_target_fingerprint_creates_no_manifest`
- Domain: `python -m pytest -q tests/unit/validation/test_baseline.py tests/unit/validation/test_runtime_compatibility.py tests/unit/validation/test_manifest.py`
- Docker: `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_reference_baseline.py`
- Expected: only the exact stable reference failure publishes one immutable Manifest.

**Completion evidence:** Not yet executed.

#### Task 21.A: Formal Validation Plan and Pre-execution Integrity

**Status:** Not started

**Goal:** Recompute current candidate/policy/environment bindings and freeze the complete collect/full pytest/Ruff/Mypy formal plan before any container call.

**Dependencies:** Tasks 12.D, 19.C, and 20.B.

**Files:**
- Create: `src/vespercode/validation/formal_plan.py`
- Test: `tests/unit/validation/test_formal_plan.py`
- Test: `tests/unit/validation/test_formal_preflight.py`

**Interfaces:** Produces `FormalValidationPlanV1`, `FormalValidationRequestV1`, and `build_formal_validation_plan(manifest: ValidationManifestV1, candidate: CandidateRevisionV1, final_diff: FinalDiffV1) -> FormalValidationPlanV1`.

**Intentionally failing test:**

```python
def test_stale_candidate_produces_zero_execution_requests() -> None:
    result = build_formal_validation_plan(manifest(), stale_candidate(), final_diff())
    assert result.error_code == "CANDIDATE_STALE"
    assert result.execution_requests == ()
```

**Expected RED:** no pre-execution integrity/plan builder exists.

**Implementation boundary:** Own pure binding revalidation and complete request-plan construction. Do not call Docker, interpret results, or create `VerifiedCandidateV1`.

**Verification:**
- Target: `python -m pytest -q tests/unit/validation/test_formal_preflight.py::test_stale_candidate_produces_zero_execution_requests`
- Domain: `python -m pytest -q tests/unit/validation/test_formal_plan.py tests/unit/validation/test_formal_preflight.py`
- Expected GREEN: exact current inputs create the complete frozen plan and every stale/drifted/protected input yields zero execution requests.

**Completion evidence:** Not yet executed.

#### Task 21.B: Complete Formal Check Execution

**Status:** Not started

**Goal:** Execute every request in the frozen formal plan with a fresh Task 18 boundary and collect complete ordered check evidence.

**Dependencies:** Tasks 18.D and 21.A.

**Files:**
- Create: `src/vespercode/validation/formal_execution.py`
- Test: `tests/integration/docker/test_reference_formal_validation.py`
- Test: `tests/integration/docker/test_formal_execution_completeness.py`

**Interfaces:** Produces `FormalValidationEvidenceV1` and `execute_formal_plan(plan: FormalValidationPlanV1, executor: DockerExecutionPortV1) -> FormalValidationEvidenceV1`.

**Intentionally failing test:**

```python
def test_executor_must_run_every_frozen_request_once(executor: SpyDockerExecutionPortV1) -> None:
    evidence = execute_formal_plan(four_check_plan(), executor)
    assert evidence.executed_request_ids == four_check_plan().request_ids
```

**Expected RED:** no formal execution coordinator exists.

**Implementation boundary:** Own ordered invocation and complete raw/check evidence collection. Do not choose checks, alter the plan, evaluate formal success, return to loop, or create approvals.

**Verification:**
- Target: `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_formal_execution_completeness.py::test_executor_must_run_every_frozen_request_once`
- Domain: `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker/test_reference_formal_validation.py tests/integration/docker/test_formal_execution_completeness.py`
- Expected GREEN: every frozen request runs once with fresh boundaries and missing/duplicate/cleanup-failed evidence remains explicit.

**Completion evidence:** Not yet executed.

#### Task 21.C: Pure Formal Success and VerifiedCandidate

**Status:** Not started

**Goal:** Evaluate the complete formal predicate and create `VerifiedCandidateV1` only for exact current complete passing evidence.

**Dependencies:** Tasks 12.D, 19.C, 20.B, 21.A, and 21.B.

**Files:**
- Create: `src/vespercode/validation/formal.py`
- Test: `tests/unit/validation/test_formal_predicate.py`
- Test: `tests/unit/validation/test_verified_candidate.py`

**Interfaces:** Produces `FormalValidationOutcomeV1`, `VerifiedCandidateV1`, and pure `evaluate_formal_success(manifest: ValidationManifestV1, candidate: CandidateRevisionV1, plan: FormalValidationPlanV1, evidence: FormalValidationEvidenceV1) -> VerifiedCandidateV1 | FormalValidationFailureV1`.

**Intentionally failing test:**

```python
def test_missing_teardown_evidence_cannot_verify_candidate() -> None:
    result = evaluate_formal_success(manifest(), candidate(), plan(), evidence_without_teardown())
    assert isinstance(result, FormalValidationFailureV1)
```

**Expected RED:** no pure closed formal predicate/VerifiedCandidate builder exists.

**Implementation boundary:** Own final evidence predicate, digest, and VerifiedCandidate construction only. Do not execute checks, build plans, mutate lifecycle, or write candidate bytes.

**Verification:**
- Target: `python -m pytest -q tests/unit/validation/test_formal_predicate.py::test_missing_teardown_evidence_cannot_verify_candidate`
- Domain: `python -m pytest -q tests/unit/validation/test_formal_predicate.py tests/unit/validation/test_verified_candidate.py`
- Expected GREEN: only complete passing current evidence verifies; every skip/error/timeout/missing/drift/fingerprint mismatch returns a typed failure.

**Completion evidence:** Not yet executed.

#### Task 22.A: Authorized Workspace Memory Creation and Repository

**Status:** Not started

**Goal:** Create/confirm only authorized structured memory with exact workspace identity, creator/source, bounded content, and no authorization power.

**Dependencies:** Tasks 7.A, 7.C, 10.C, 15.E, and 19.C.

**Files:**
- Create: `src/vespercode/storage/migrations/v0005_memory.py`
- Create: `src/vespercode/memory/entry.py`
- Create: `src/vespercode/memory/repository.py`
- Test: `tests/unit/storage/test_memory_migration.py`
- Test: `tests/unit/memory/test_entry.py`
- Test: `tests/unit/memory/test_repository.py`
- Test: `tests/unit/memory/test_authorization.py`

**Interfaces:** Produces immutable `MEMORY_V1_MIGRATION = MigrationV1(version=5, name="memory_v1", ...)`, `MemoryKindV1`, `MemoryCreatorV1`, `MemorySourceV1`, `MemoryEntryV1`, `MemoryRepository.create(command: CreateMemoryCommandV1) -> MemoryMutationResultV1`, and `MemoryRepository.confirm(command: ConfirmProjectConventionV1) -> MemoryMutationResultV1`.

**Intentionally failing test:**

```python
def test_model_originated_project_convention_is_rejected(repository: MemoryRepository) -> None:
    result = repository.create(model_project_convention_command())
    assert result.error_code == "MEMORY_CREATOR_FORBIDDEN"
```

**Expected RED:** no closed memory entry/repository authority boundary exists.

**Schema RED:** `tests/unit/storage/test_memory_migration.py::test_memory_migration_has_exact_schema` applies v0001–v0005 and asserts the sole `memory_entries` table, primary key/workspace indexes, bounded kind/creator/source/timestamps, clear tombstone fields required by Task 22.C, and absence of secret, permission, authorization, or complete-source-body columns.

**Implementation boundary:** Own one coupled workspace-memory storage behavior: immutable v0005 DDL and authorized create/confirm repository operations. It cannot edit the final registry, select context, clear entries, append audit, or allow memory to affect governance/config/validation.

**Verification:**
- Target: `python -m pytest -q tests/unit/memory/test_authorization.py::test_model_originated_project_convention_is_rejected`
- Schema: `python -m pytest -q tests/unit/storage/test_memory_migration.py::test_memory_migration_has_exact_schema`
- Domain: `python -m pytest -q tests/unit/storage/test_memory_migration.py tests/unit/memory/test_entry.py tests/unit/memory/test_repository.py tests/unit/memory/test_authorization.py`
- Expected GREEN: exact v0005 schema; only allowed creator/source/kind combinations persist in the exact workspace and forbidden/full/secret/over-limit content rejects.

**Completion evidence:** Not yet executed.

#### Task 22.B: Deterministic Workspace Memory Listing and Selection

**Status:** Not started

**Goal:** List and select only eligible non-cleared entries from the exact workspace under frozen priority, recency, count, and byte limits.

**Dependencies:** Tasks 10.C, 19.C, and 22.A.

**Files:**
- Create: `src/vespercode/memory/selection.py`
- Test: `tests/unit/memory/test_selection.py`
- Test: `tests/unit/memory/test_workspace_isolation.py`

**Interfaces:** Produces `MemoryEntrySequenceV1`, an immutable ordered tuple of memory entries, `MemoryRepository.list(workspace_identity_digest: str) -> MemoryEntrySequenceV1`, and pure `select_memory(query: MemorySelectionQueryV1, entries: MemoryEntrySequenceV1) -> MemorySelectionV1`.

**Intentionally failing test:**

```python
def test_selection_never_crosses_workspace_identity(repository: MemoryRepository) -> None:
    assert repository.list("workspace-b") == ()
```

**Expected RED:** no exact-workspace list/selection boundary exists.

**Implementation boundary:** Own eligible listing and pure deterministic selection only. Do not create/confirm/clear memory or override current Snapshot/check evidence.

**Verification:**
- Target: `python -m pytest -q tests/unit/memory/test_workspace_isolation.py::test_selection_never_crosses_workspace_identity`
- Domain: `python -m pytest -q tests/unit/memory/test_selection.py tests/unit/memory/test_workspace_isolation.py`
- Expected GREEN: exact workspace/count/byte/priority/recency ordering is deterministic and no other workspace or cleared entry appears.

**Completion evidence:** Not yet executed.

#### Task 22.C: Transactional Memory Clear

**Status:** Not started

**Goal:** Make an explicit authorized memory clear transaction immediately exclude the targeted workspace entries from every future selection.

**Dependencies:** Tasks 7.A, 7.C, 22.A, and 22.B.

**Files:**
- Create: `src/vespercode/memory/clear.py`
- Test: `tests/unit/memory/test_clear.py`

**Interfaces:** Produces `ClearMemoryCommandV1`, `MemoryClearResultV1`, and `MemoryClearService.clear(command: ClearMemoryCommandV1) -> MemoryClearResultV1`.

**Intentionally failing test:**

```python
def test_successful_clear_is_immediately_ineligible_for_selection() -> None:
    service, selector = memory_clear_fixture()
    service.clear(clear_workspace_command())
    assert selector.select(query()).entries == ()
```

**Expected RED:** no transaction-bound clear service exists.

**Implementation boundary:** Own clear authority, tombstone/removal transaction, and post-commit eligibility guarantee. Do not delete immutable audit/source facts or affect another workspace.

**Verification:**
- Target: `python -m pytest -q tests/unit/memory/test_clear.py::test_successful_clear_is_immediately_ineligible_for_selection`
- Domain: `python -m pytest -q tests/unit/memory/test_clear.py`
- Expected GREEN: exact authorized clears take effect atomically; replay is idempotent and cross-workspace/forged/partial failures change nothing.

**Completion evidence:** Not yet executed.

#### Task 23.A: Redacted Monotonic Audit Event Repository

**Status:** Not started

**Goal:** Append one allowlisted, data-minimized audit event under a unique increasing per-Run sequence or reject it with zero rows.

**SPEC references:** Milestone 23 event/repository scope; SPEC §4.7, §5.3–§5.6, §7 AuditEvent, and AC-08/AC-13/AC-16.

**Dependencies:** Tasks 7.C and 22.A.

**Files:**
- Create: `src/vespercode/storage/migrations/v0006_audit.py`
- Create: `src/vespercode/audit/event.py`
- Create: `src/vespercode/audit/repository.py`
- Test: `tests/unit/storage/test_audit_migration.py`
- Test: `tests/unit/audit/test_event.py`
- Test: `tests/unit/audit/test_repository.py`
- Test: `tests/unit/audit/test_redaction.py`

**Interfaces:** Produces immutable `AUDIT_V1_MIGRATION = MigrationV1(version=6, name="audit_v1", ...)`, `AuditEventV1(run_id: str, sequence: int, event_type: AuditEventTypeV1, redacted_payload: AuditPayloadV1, created_at: CanonicalTimestampV1)`, `AuditRepository.append(command: AppendAuditEventV1) -> AuditAppendResultV1`, `AuditRepository.list_run(run_id: str, page: AuditPageRequestV1) -> AuditPageV1`, and `AuditRepository.clear_ended_run(command: ClearEndedRunAuditV1) -> AuditClearResultV1`.

**Intentionally failing test:**

```python
def test_audit_rejects_complete_request_body_and_secret_fields(
    audit_repository: AuditRepository,
) -> None:
    result = audit_repository.append(append_event("LLM_CALL", {"request_body": "source text", "api_key": "inert-sentinel"}))
    assert result.error_code == "AUDIT_STORE_FAILED"
    assert audit_repository.event_count == 0
```

Expected RED: import failure because the closed event union and repository do not exist.

**Schema RED:** `tests/unit/storage/test_audit_migration.py::test_audit_migration_has_exact_schema` applies v0001–v0006 and asserts the sole `audit_events` table, FK `run_id → runs`, unique `(run_id, sequence)`, bounded allowlisted payload/evidence refs and timestamps, and absence of secret, complete request/response, file body, raw check output, or recovery backup columns.

**Implementation boundary:** This child owns one coupled audit storage behavior: immutable v0006 DDL, allowlisted payload boundary, redaction/bounds, sequence transaction, pagination, ended-Run explicit clear, and replay/conflict handling. It cannot edit the final registry, map user-visible Run state, or perform time-based retention.

**Verification:**
- Target: `python -m pytest -q tests/unit/audit/test_redaction.py::test_audit_rejects_complete_request_body_and_secret_fields`
- Schema: `python -m pytest -q tests/unit/storage/test_audit_migration.py::test_audit_migration_has_exact_schema`
- Domain: `python -m pytest -q tests/unit/storage/test_audit_migration.py tests/unit/audit/test_event.py tests/unit/audit/test_repository.py tests/unit/audit/test_redaction.py`
- Expected GREEN: all commands exit `0`; exact v0006 schema, forbidden-content zero-row behavior, ordering, replay/conflict, pagination, redaction, and ended-Run clear cases pass.

**Completion evidence:** Not yet executed.

#### Task 23.B: User-facing Run Visibility Projection

**Status:** Not started

**Goal:** Project each formal Run/phase/wait/recovery/terminal fact into one distinct bounded user-visible state and reason without inferring success from missing evidence.

**SPEC references:** Milestone 23 projection scope; SPEC §4.7, NFR-OBS/NFR-PRIV, AC-16, and §10.3.

**Dependencies:** Task 23.A.

**Files:**
- Create: `src/vespercode/audit/projection.py`
- Test: `tests/unit/audit/test_projection.py`

**Interfaces:** Produces `WaitContextSequenceV1` and `AuditEventSequenceV1`, immutable ordered tuples of their named item types, and `build_run_visibility(run: RunRecordV1, waits: WaitContextSequenceV1, events: AuditEventSequenceV1) -> RunVisibilityV1`.

**Intentionally failing test:**

```python
def test_recovery_required_is_never_projected_as_stopped(
    recovery_run: RunRecordV1,
    recovery_events: tuple[AuditEventV1, ...],
) -> None:
    visibility = build_run_visibility(recovery_run, (), recovery_events)
    assert visibility.state_label == "RECOVERY_REQUIRED"
    assert visibility.next_action == "REVIEW_RECOVERY"
```

Expected RED: import failure because the visibility projector does not exist.

**Implementation boundary:** This child is a pure projection over typed Tasks 7.B/23.A facts. It cannot query SQLite, append/clear events, expose internal rows/bodies, infer PASS, or change lifecycle state.

**Verification:**
- Target: `python -m pytest -q tests/unit/audit/test_projection.py::test_recovery_required_is_never_projected_as_stopped`
- Domain: `python -m pytest -q tests/unit/audit/test_projection.py`
- Expected GREEN: both commands exit `0`; every CREATED/RUNNING phase/wait/recovery/terminal mapping is distinct, bounded, stable, and redacted.

**Completion evidence:** Not yet executed.

#### Task 23.C: Audit Retention with Recovery Preservation

**Status:** Not started

**Goal:** Remove only eligible audit records older than 30 days while preserving every unresolved-recovery reference and active/non-ended Run.

**SPEC references:** Milestone 23 retention scope; SPEC §4.7 retention and AC-21/AC-22/AC-24.

**Dependencies:** Task 23.B.

**Files:**
- Create: `src/vespercode/audit/retention.py`
- Test: `tests/unit/audit/test_retention.py`

**Interfaces:** Produces `apply_audit_retention(now: CanonicalTimestampV1, repository: AuditRepository) -> AuditRetentionResultV1`.

**Intentionally failing test:**

```python
def test_retention_preserves_unresolved_recovery_evidence(
    audit_repository: AuditRepository,
    day_31: CanonicalTimestampV1,
) -> None:
    seed_old_unresolved_recovery(audit_repository)
    result = apply_audit_retention(day_31, audit_repository)
    assert result.deleted_event_count == 0
    assert audit_repository.list_run("run-recovery", first_page()).items
```

Expected RED: import failure because the retention evaluator does not exist.

**Implementation boundary:** This child owns the 30-day eligibility query and recovery-preservation predicate only. It cannot clear active Runs, change transactions, erase backup bodies, create projections, or treat missing evidence as terminal.

**Verification:**
- Target: `python -m pytest -q tests/unit/audit/test_retention.py::test_retention_preserves_unresolved_recovery_evidence`
- Domain: `python -m pytest -q tests/unit/audit/test_retention.py`
- Expected GREEN: both commands exit `0`; cutoff boundaries, active/ended classification, explicit preservation, idempotent rerun, and bounded result counts pass.

**Completion evidence:** Not yet executed.

#### Task 24.A: Structured Feedback Construction and Selection

**Status:** Not started

**Goal:** Convert stable check/action/control failures into deterministic bounded feedback records and select the most relevant unconsumed records.

**Dependencies:** Tasks 4.C, 5.D, 11.B, and 19.C.

**Files:**
- Create: `src/vespercode/loop/feedback.py`
- Test: `tests/unit/loop/test_feedback.py`

**Interfaces:** Produces `FeedbackRecordV1`, `FeedbackRecordSequenceV1`, an immutable ordered tuple of feedback records, `FeedbackSelectionV1`, `build_feedback(source: CheckResultV1 | ActionResultV1 | StableControlErrorV1, clock: ClockV1) -> FeedbackRecordSequenceV1`, and `select_feedback(records: FeedbackRecordSequenceV1) -> FeedbackSelectionV1`.

**Intentionally failing test:**

```python
def test_newest_failure_survives_feedback_limit() -> None:
    selection = select_feedback(over_limit_records_with_newest_failure())
    assert selection.records[-1].id == "newest-failure"
```

**Expected RED:** no structured feedback builder/selector exists.

**Implementation boundary:** Own pure feedback normalization, severity/order/limit selection, and evidence references. Do not assemble messages, consume records, call an LLM, or mutate Run state.

**Verification:**
- Target: `python -m pytest -q tests/unit/loop/test_feedback.py::test_newest_failure_survives_feedback_limit`
- Domain: `python -m pytest -q tests/unit/loop/test_feedback.py`
- Expected GREEN: stable inputs produce stable records/order and newest required failure survives exact count/byte limits.

**Completion evidence:** Not yet executed.

#### Task 24.B: Deterministic Bounded Context Projection

**Status:** Not started

**Goal:** Assemble the exact source-attributed message projection and trim only allowed categories under the frozen context budget.

**Dependencies:** Tasks 10.C, 15.E, 16.B, 22.B, and 24.A.

**Files:**
- Create: `src/vespercode/loop/context_projection.py`
- Test: `tests/unit/loop/test_context_projection.py`
- Test: `tests/unit/loop/test_context_trimming.py`
- Test: `tests/unit/loop/test_context_sources.py`

**Interfaces:** Produces `ContextProjectionV1(messages: RequestMessageSequenceV1, source_projection: SourceProjectionV1, canonical_byte_count: int, projection_digest: str)`, `ContextBudgetFailureV1`, and pure `build_context(inputs: ContextProjectionInputsV1) -> ContextProjectionV1 | ContextBudgetFailureV1`.

**Intentionally failing test:**

```python
def test_trimming_never_removes_most_recent_failure_feedback() -> None:
    projection = build_context(oversized_context_inputs())
    assert "most-recent-failure" in projection.feedback_refs
```

**Expected RED:** no deterministic source-preserving context projector exists.

**Implementation boundary:** Own pure category assembly, source projection, trimming, canonical bytes, and digest. Do not consume feedback, create turns, authorize disclosure, or call adapters.

**Verification:**
- Target: `python -m pytest -q tests/unit/loop/test_context_trimming.py::test_trimming_never_removes_most_recent_failure_feedback`
- Domain: `python -m pytest -q tests/unit/loop/test_context_projection.py tests/unit/loop/test_context_trimming.py tests/unit/loop/test_context_sources.py`
- Expected GREEN: mandatory facts remain, trim order/budgets/source paths are exact, and impossible mandatory content returns zero-side-effect budget failure.

**Completion evidence:** Not yet executed.

#### Task 24.C: Atomic Feedback-to-turn Consumption

**Status:** Not started

**Goal:** Bind selected feedback references to one new turn and consume them atomically so no record can be attached to multiple turns.

**Dependencies:** Tasks 7.A, 7.C, 24.A, 24.B, and 25.B.

**Files:**
- Create: `src/vespercode/storage/migrations/v0008_feedback.py`
- Create: `src/vespercode/loop/feedback_consumption.py`
- Test: `tests/unit/storage/test_feedback_migration.py`
- Test: `tests/unit/loop/test_feedback_consumption.py`

**Interfaces:** Produces immutable `FEEDBACK_V1_MIGRATION = MigrationV1(version=8, name="feedback_v1", ...)`, `FeedbackReferenceSequenceV1`, an immutable ordered tuple of feedback ids, `FeedbackRepositoryV1.append(records: FeedbackRecordSequenceV1) -> FeedbackAppendResultV1`, `FeedbackConsumptionResultV1`, and `consume_feedback(turn_id: str, refs: FeedbackReferenceSequenceV1, repository: FeedbackRepositoryV1) -> FeedbackConsumptionResultV1`.

**Intentionally failing test:**

```python
def test_two_turns_cannot_consume_one_feedback_record(repository: FeedbackRepositoryV1) -> None:
    results = consume_for_two_turns(repository, "feedback-1")
    assert sorted(result.kind for result in results) == ["ALREADY_CONSUMED", "CONSUMED"]
```

**Expected RED:** no transaction-bound feedback consumption service exists.

**Schema RED:** `tests/unit/storage/test_feedback_migration.py::test_feedback_migration_has_exact_schema` applies v0001–v0008 and asserts the sole `feedback_records` table, primary key, nullable FK `consumed_by_turn_id → agent_turns`, one-winner consume predicate, bounded payload/evidence refs, and absence of raw check output, complete request/response, file body, or credential columns.

**Implementation boundary:** Own one coupled feedback-repository behavior: immutable v0008 DDL, append of Task 24.A's already validated bounded records, turn/reference binding, and consume-once transaction. It cannot edit the final registry, rebuild/select feedback, assemble messages, create adapter calls, or mutate candidate/workspace state.

**Verification:**
- Target: `python -m pytest -q tests/unit/loop/test_feedback_consumption.py::test_two_turns_cannot_consume_one_feedback_record`
- Schema: `python -m pytest -q tests/unit/storage/test_feedback_migration.py::test_feedback_migration_has_exact_schema`
- Domain: `python -m pytest -q tests/unit/storage/test_feedback_migration.py tests/unit/loop/test_feedback_consumption.py`
- Expected GREEN: exact v0008 schema; exactly one turn consumes each record; replay is stable and conflicts/missing refs change nothing.

**Completion evidence:** Not yet executed.

#### Task 25.A: Pure Stop and Progress Evaluation

**Status:** Not started

**Goal:** Decide repeated-action, no-progress, budget, invalid-output, cancel, and deadline stops from immutable inputs without performing loop side effects.

**SPEC references:** Milestone 25 stopping/progress requirements.

**Dependencies:** Tasks 5.D, 7.C, 14.C, and 24.C.

**Blocks:** Tasks 25.G, 30.A, 32.A, and 37.B.

**Parallelization:** Parallel with Tasks 25.B, 25.C, 25.E, and 25.F after dependencies freeze their interfaces.

**Branch/worktree:** `codex/task-25a-stop-progress`; `.worktrees/task-25a-stop-progress`.

**Files:**
- Create: `src/vespercode/loop/stopping.py`
- Create: `src/vespercode/loop/progress.py`
- Test: `tests/unit/loop/test_stopping.py`
- Test: `tests/unit/loop/test_progress.py`

**Interfaces:** Produces `ProgressWindowV1`, `ProgressEvaluator.evaluate(window: ProgressWindowV1, observation: ProgressObservationV1) -> ProgressDecisionV1`, and `StopEvaluator.evaluate(state: RunLoopStateV1, evidence: LoopEvidenceV1, progress: ProgressDecisionV1, now: CanonicalTimestampV1) -> StopDecisionV1`. Both are pure and clock values are explicit inputs.

**Intentionally failing test:**

```python
def test_repeated_semantic_action_stops_at_exact_limit() -> None:
    state = state_with_same_action_digest(repetitions=3)
    decision = StopEvaluator().evaluate(
        state,
        loop_evidence(state),
        no_progress_decision(state),
        current_time(state),
    )
    assert isinstance(decision, StopV1)
    assert decision.reason == "REPEATED_ACTION_LIMIT"
```

**Implementation boundary:** No repository, LLM, action parser, dispatcher, wait, or audit call is allowed.

**Verification:**
- Target: `python -m pytest -q tests/unit/loop/test_stopping.py::test_repeated_semantic_action_stops_at_exact_limit`
- Domain: `python -m pytest -q tests/unit/loop/test_stopping.py tests/unit/loop/test_progress.py`
- Expected: exact boundary tables are deterministic and side-effect free.

**Completion evidence:** Not yet executed.

#### Task 25.B: Active Turn and Call Counting Boundary

**Status:** Not started

**Goal:** Atomically establish one active turn and define exactly which successful pre-call boundary increments turn/call counters.

**SPEC references:** Milestone 25 counting and single-active-turn requirements.

**Dependencies:** Tasks 7.C, 8.B, and 23.A.

**Blocks:** Tasks 7.D, 24.C, 25.C, 25.G, and 37.B.

**Parallelization:** Parallel with Task 25.A.

**Branch/worktree:** `codex/task-25b-turn-boundary`; `.worktrees/task-25b-turn-boundary`.

**Files:**
- Create: `src/vespercode/storage/migrations/v0007_agent_turns.py`
- Create: `src/vespercode/loop/turn_boundary.py`
- Test: `tests/unit/storage/test_agent_turns_migration.py`
- Test: `tests/unit/loop/test_turn_counting.py`

**Interfaces:** Produces immutable `AGENT_TURNS_V1_MIGRATION = MigrationV1(version=7, name="agent_turns_v1", ...)`, `TurnBoundary.begin(run_id: str, expected_state: RunStateV1) -> BeginTurnResultV1`, `TurnBoundary.record_call_started(run_id: str, turn_id: str, expected_revision: int) -> RecordCallStartedResultV1`, and `TurnBoundary.close_turn(run_id: str, turn_id: str, outcome: TurnOutcomeV1, expected_revision: int) -> CloseTurnResultV1`, using Task 7.B compare-and-update operations.

**Intentionally failing test:**

```python
def test_pre_call_failure_does_not_increment_turn_or_call(
    boundary: TurnBoundary,
) -> None:
    result = boundary.abort_before_call("run-1", "CREDENTIAL_MISSING")
    assert result.turn_count == 0
    assert result.call_count == 0
```

**Schema RED:** `tests/unit/storage/test_agent_turns_migration.py::test_agent_turn_migration_has_exact_schema` applies v0001–v0007 and asserts the sole `agent_turns` table, FK `run_id → runs`, unique/partial one-active-turn constraint, exact revision/turn/call/outcome fields, body-free request/result refs, and absence of complete request/response/credential columns.

**Implementation boundary:** This task owns one coupled active-turn storage behavior: immutable v0007 DDL and exact counter/active-turn state changes. It cannot edit the final registry, prepare, authorize, or invoke an LLM call.

**Verification:**
- Target: `python -m pytest -q tests/unit/loop/test_turn_counting.py::test_pre_call_failure_does_not_increment_turn_or_call`
- Schema: `python -m pytest -q tests/unit/storage/test_agent_turns_migration.py::test_agent_turn_migration_has_exact_schema`
- Domain: `python -m pytest -q tests/unit/storage/test_agent_turns_migration.py tests/unit/loop/test_turn_counting.py`
- Expected: exact v0007 schema; every credential/Grant/readiness/transport boundary has an explicit exact count outcome and concurrent starts admit one active turn.

**Completion evidence:** Not yet executed.

#### Task 25.C: One Authorized LLM Call Orchestration

**Status:** Not started

**Goal:** Prepare and perform exactly one Mock or OpenAI call, enforcing fresh credential and authorization ordering before Task 25.B records call start.

**SPEC references:** Milestone 25 one-call requirements and Global Constraints per-real-call credential order.

**Dependencies:** Tasks 15.E, 16.B, 25.B, and 27.B.

**Blocks:** Tasks 25.G and 37.B.

**Parallelization:** Parallel with Tasks 25.A, 25.D, 25.E, and 25.F after Task 25.B.

**Branch/worktree:** `codex/task-25c-call-orchestrator`; `.worktrees/task-25c-call-orchestrator`.

**Files:**
- Create: `src/vespercode/loop/call_orchestrator.py`
- Test: `tests/unit/loop/test_call_orchestrator.py`

**Interfaces:** Produces `build_call_result(request: PreparedModelRequestV1, authorization_ref: OptionalAuthorizationRecordRefV1, outcome: AdapterOutcomeV1) -> LLMCallResultV1` and `CallOrchestrator.call_once(command: CallOnceV1) -> LLMCallResultV1`; consumes Task 16.B's exact unbound/bound `generate` adapters, Task 15.E authorization ledger, Task 27.B `get_for_call`, and Task 25.B counting port.

**Intentionally failing test:**

```python
def test_cleared_credential_stops_before_every_charge_or_count(
    orchestrator: CallOrchestrator,
    spies: RealCallSpies,
) -> None:
    result = orchestrator.call_once(valid_openai_call())
    assert result.error_code == "CREDENTIAL_MISSING"
    assert spies.counts() == {"grant": 0, "authorization": 0, "turn": 0, "call": 0, "transport": 0}
```

**Implementation boundary:** This orchestration child alone converts a `ModelResponse` or bounded adapter failure into `LLMCallResultV1`. No retry, provider fallback, cached credential, or reconstruction after uncertain transport is permitted.

**Verification:**
- Target: `python -m pytest -q tests/unit/loop/test_call_orchestrator.py::test_cleared_credential_stops_before_every_charge_or_count`
- Domain: `python -m pytest -q tests/unit/loop/test_call_orchestrator.py tests/unit/loop/test_turn_counting.py`
- Expected: Mock calls never touch real ports; OpenAI calls follow the exact credential→Grant→authorization→count→transport order once.

**Completion evidence:** Not yet executed.

#### Task 25.D: Parse, Policy, Dispatch, and Feedback Step

**Status:** Not started

**Goal:** Convert one model response into at most one bound action, evaluate policy, dispatch only ALLOW, and produce/consume structured feedback exactly once.

**SPEC references:** Milestone 25 action-step requirements.

**Dependencies:** Tasks 11.B, 12.D, 13, 17.C, 19.C, and 24.C.

**Blocks:** Tasks 7.D, 14.B, 25.G, 30.A, 32.A, and 37.B.

**Parallelization:** Parallel with Tasks 25.A, 25.C, 25.E, and 25.F.

**Branch/worktree:** `codex/task-25d-action-pipeline`; `.worktrees/task-25d-action-pipeline`.

**Files:**
- Create: `src/vespercode/storage/migrations/v0009_actions.py`
- Create: `src/vespercode/loop/action_pipeline.py`
- Test: `tests/unit/storage/test_actions_migration.py`
- Test: `tests/unit/loop/test_action_pipeline.py`
- Test: `tests/unit/loop/test_main_loop_failures.py` (action-step cases only)

**Interfaces:** Produces immutable `ACTIONS_V1_MIGRATION = MigrationV1(version=9, name="actions_v1", ...)` and `ActionPipeline.execute(response: ModelResponse, context: ActionPipelineContextV1) -> ActionStepResultV1` using the exact Tasks 17.A–17.C parser/binder/dispatcher, Task 13 policy, and Task 24.A/24.C feedback functions/repository.

**Intentionally failing test:**

```python
def test_policy_deny_skips_dispatch_and_returns_feedback(
    pipeline: ActionPipeline,
    dispatcher: SpyDispatcher,
) -> None:
    result = pipeline.execute(outside_scope_patch_response(), valid_context())
    assert result.policy_decision == "DENY"
    assert dispatcher.call_count == 0
    assert result.feedback.error_code == "PATCH_PATH_NOT_EDITABLE"
```

**Schema RED:** `tests/unit/storage/test_actions_migration.py::test_action_migration_has_exact_schema` applies v0001–v0009 and asserts the sole `action_records` table, primary key/FK `turn_id → agent_turns`, unique per-turn action identity, exact instance/semantic digests, policy decision/result ref, and absence of action input/result body, raw output, file body, or credential columns.

**Implementation boundary:** This child owns one coupled action-step storage behavior: immutable v0009 DDL and the single parse/policy/dispatch/feedback/action-record transaction. It cannot edit the final registry or own LLM invocation, counters, waits, restart, or the outer loop.

**Verification:**
- Target: `python -m pytest -q tests/unit/loop/test_action_pipeline.py::test_policy_deny_skips_dispatch_and_returns_feedback`
- Schema: `python -m pytest -q tests/unit/storage/test_actions_migration.py::test_action_migration_has_exact_schema`
- Domain: `python -m pytest -q tests/unit/storage/test_actions_migration.py tests/unit/loop/test_action_pipeline.py tests/unit/loop/test_main_loop_failures.py`
- Expected: exact v0009 schema; invalid, DENY, tool failure, check feedback, completion proposal, and consume-once traces pass without hidden dispatch.

**Completion evidence:** Not yet executed.

#### Task 25.E: Wait, Deadline, and Cancellation Control

**Status:** Not started

**Goal:** Pause only at declared waits, expire against the smaller applicable deadline, and honor cancellation only at deterministic safe points.

**SPEC references:** Milestone 25 wait/deadline/cancel requirements.

**Dependencies:** Tasks 7.C and 14.C.

**Blocks:** Tasks 25.G and 37.B.

**Parallelization:** Parallel with Tasks 25.A, 25.C, 25.D, and 25.F.

**Branch/worktree:** `codex/task-25e-wait-control`; `.worktrees/task-25e-wait-control`.

**Files:**
- Create: `src/vespercode/loop/wait_control.py`
- Create: `src/vespercode/loop/cancellation.py`
- Test: `tests/unit/loop/test_wait_lifecycle.py`

**Interfaces:** Produces `WaitController.enter(wait: WaitContextV1, now: CanonicalTimestampV1) -> WaitTransitionResultV1`, `WaitController.resume(wait: WaitContextV1, decision: WaitDecisionV1, now: CanonicalTimestampV1) -> WaitTransitionResultV1`, `WaitController.expire(wait: WaitContextV1, now: CanonicalTimestampV1) -> WaitTransitionResultV1`, and `CancellationController.evaluate_safe_point(run: RunRecordV1, cancellation_requested: bool) -> CancellationDecisionV1`.

**Intentionally failing test:**

```python
def test_expired_wait_never_resumes_agent_action(
    wait_control: WaitController,
) -> None:
    wait = expired_wait()
    result = wait_control.resume(wait, valid_decision(), after(wait.expires_at))
    assert result.kind == "WAIT_EXPIRED"
    assert result.resume_action is None
```

**Implementation boundary:** Wait/cancel logic consumes persisted bindings and injected time only; it cannot call the LLM, tool dispatcher, or persistence writer.

**Verification:**
- Target: `python -m pytest -q tests/unit/loop/test_wait_lifecycle.py::test_expired_wait_never_resumes_agent_action`
- Domain: `python -m pytest -q tests/unit/loop/test_wait_lifecycle.py`
- Expected: reject/expiry/wrong binding/duplicate decision/cancel safe-point tables all pass.

**Completion evidence:** Not yet executed.

#### Task 25.F: Non-persistent Restart Fail-close

**Status:** Not started

**Goal:** Detect an interrupted non-persistent Agent turn after process restart and stop without reconstructing, retrying, or resending it.

**SPEC references:** Milestone 25 restart requirements and SPEC non-goal excluding ordinary-turn recovery.

**Dependencies:** Tasks 7.C and 23.C.

**Blocks:** Tasks 25.G and 37.B.

**Parallelization:** Parallel with Tasks 25.A, 25.C, 25.D, and 25.E.

**Branch/worktree:** `codex/task-25f-restart-failclose`; `.worktrees/task-25f-restart-failclose`.

**Files:**
- Create: `src/vespercode/loop/restart.py`
- Test: `tests/unit/loop/test_restart_behavior.py`

**Interfaces:** Produces `RestartGuard.inspect(run) -> RestartDispositionV1`.

**Intentionally failing test:**

```python
def test_restart_during_active_turn_stops_without_resend(
    restart_guard: RestartGuard,
) -> None:
    result = restart_guard.inspect(run_with_unfinished_turn())
    assert result.stop_reason == "PROCESS_RESTART_DURING_TURN"
    assert result.resend_allowed is False
```

**Implementation boundary:** It may emit one typed stop/audit command but cannot reconstruct provider requests, consume waits, or invoke a tool.

**Verification:**
- Target: `python -m pytest -q tests/unit/loop/test_restart_behavior.py::test_restart_during_active_turn_stops_without_resend`
- Domain: `python -m pytest -q tests/unit/loop/test_restart_behavior.py`
- Expected: every interrupted non-persistent phase fails closed with zero resend.

**Completion evidence:** Not yet executed.

#### Task 25.G: Thin Sequential Agent Loop Composition

**Status:** Not started

**Goal:** Compose Tasks 25.A–25.F into the formal sequential loop without reimplementing any child rule.

**SPEC references:** Milestone 25 complete loop contract.

**Dependencies:** Tasks 8.B, 17.C, 21.C, 24.C, 25.A, 25.B, 25.C, 25.D, 25.E, and 25.F.

**Blocks:** Tasks 29.A, 31.A, and 37.B.

**Parallelization:** Sequential after Tasks 8.B, 17.C, 21.C, 24.C, 25.A, 25.B, 25.C, 25.D, 25.E, and 25.F.

**Branch/worktree:** `codex/task-25g-loop-engine`; `.worktrees/task-25g-loop-engine`.

**Files:**
- Create: `src/vespercode/loop/engine.py`
- Test: `tests/unit/loop/test_main_loop.py`
- Test: `tests/unit/loop/test_main_loop_failures.py` (composition cases only)

**Interfaces:** Produces `AgentLoopEngine.step(run_id: str) -> LoopStepResultV1` and `AgentLoopEngine.run_until_boundary(run_id: str) -> LoopBoundaryResultV1` by dependency injection of `StopEvaluator`, `TurnBoundary`, `CallOrchestrator`, `ActionPipeline`, `WaitController`, `CancellationController`, and `RestartGuard`.

**Intentionally failing test:**

```python
def test_one_engine_step_calls_each_stage_once_in_order(
    engine: AgentLoopEngine,
    stages: RecordingLoopStages,
) -> None:
    engine.step("run-1")
    assert stages.calls == ("context", "call_once", "action_pipeline", "progress", "stop", "close_turn")
```

**Implementation boundary:** `engine.py` contains orchestration only: no policy table, parser, feedback rule, count predicate, retry, wait predicate, or restart predicate.

**Verification:**
- Target: `python -m pytest -q tests/unit/loop/test_main_loop.py::test_one_engine_step_calls_each_stage_once_in_order`
- Domain: `python -m pytest -q tests/unit/loop/test_main_loop.py tests/unit/loop/test_main_loop_failures.py`
- Expected: Mock/OpenAI, correction, wait, cancel, stop, and completion compositions use the child implementations and preserve exactly one active turn/call.

**Completion evidence:** Not yet executed.

#### Task 26.A: Approval-bound Verified Writeback Transaction

**Status:** Not started

**Goal:** Persist one exact approved `FinalDiffV1` through durable preimages, backups, per-path progress, atomic replaces, verification, and `COMMITTED`.

**SPEC references:** Milestone 26 writeback requirements.

**Dependencies:** Tasks 3.G, 7.C, 9.D, 12.D, 14.C, 21.C, and 23.C.

**Non-task entry gate:** The terminal Task 3.G outcome is `GO`.

**Blocks:** Tasks 7.D, 26.B, 29.C, 31.A, and 37.B.

**Parallelization:** Parallelizable with Tasks 25.A, 25.B, 25.C, 25.D, 25.E, 25.F, and 25.G once each exact executable Dependencies field is satisfied.

**Branch/worktree:** `codex/task-26a-writeback`; `.worktrees/task-26a-writeback`.

**Files:**
- Create: `src/vespercode/storage/migrations/v0011_persistence.py`
- Create: `src/vespercode/persistence/path_record.py`
- Create: `src/vespercode/persistence/transaction.py`
- Create: `src/vespercode/persistence/artifacts.py`
- Create: `src/vespercode/persistence/writeback.py`
- Test: `tests/unit/storage/test_persistence_migration.py`
- Test: `tests/unit/persistence/test_path_record.py`
- Test: `tests/unit/persistence/test_transaction.py`
- Test: `tests/unit/persistence/test_writeback_preconditions.py`
- Test: `tests/fault_injection/persistence/test_writeback_fault_matrix.py`

**Interfaces:** Produces immutable `PERSISTENCE_V1_MIGRATION = MigrationV1(version=11, name="persistence_v1", ...)`, the Milestone 26 path/transaction/artifact contracts, `PersistenceCommandFactoryV1.for_approved_run(run_id: str, approval_id: str, event_id: str) -> PersistVerifiedCandidateV1`, and `PersistenceCoordinator.persist(command: PersistVerifiedCandidateV1) -> PersistenceResultV1`.

**Intentionally failing test:**

```python
def test_missing_exact_approval_writes_no_workspace_bytes(
    persistence: PersistenceCoordinator,
    workspace: SpyWorkspace,
) -> None:
    result = persistence.persist(command_without_consumable_approval())
    assert result.error_code == "APPROVAL_REQUIRED"
    assert workspace.write_count == 0
```

**Schema RED:** `tests/unit/storage/test_persistence_migration.py::test_persistence_migration_has_exact_schema` applies v0001–v0011 and asserts only `persistence_transactions` and `persistence_path_records`, Run/approval/transaction foreign keys, unique active workspace transaction and `(transaction_id, canonical_path)` identities, composite ordered path key, closed states/digests/artifact refs, and absence of postimage/preimage/backup body or credential columns.

**Implementation boundary:** This task owns one coupled durable writeback storage behavior: immutable v0011 DDL and the persistence transaction/path repository used by the approval-bound write protocol. It cannot edit the final registry, consumes Task 14 approval once immediately before the first authoritative write, and never decides recovery disposition.

**Verification:**
- Target: `python -m pytest -q tests/unit/persistence/test_writeback_preconditions.py::test_missing_exact_approval_writes_no_workspace_bytes`
- Schema: `python -m pytest -q tests/unit/storage/test_persistence_migration.py::test_persistence_migration_has_exact_schema`
- Domain: `python -m pytest -q tests/unit/storage/test_persistence_migration.py tests/unit/persistence/test_path_record.py tests/unit/persistence/test_transaction.py tests/unit/persistence/test_writeback_preconditions.py tests/fault_injection/persistence/test_writeback_fault_matrix.py`
- Expected: exact v0011 schema and byte/identity checks pass; any interruption leaves a durable non-terminal transaction rather than false success.

**Completion evidence:** Not yet executed.

#### Task 26.B: Read-only Recovery Preview and Three-value Classification

**Status:** Not started

**Goal:** Inspect a non-terminal transaction and current object/byte identities without writing, returning only proven `COMMITTED`, `ROLLED_BACK`, or `UNRESOLVED`.

**SPEC references:** Milestone 26 recovery preview and disposition requirements.

**Dependencies:** Task 26.A.

**Blocks:** Tasks 26.C and 37.B.

**Parallelization:** Sequential after Task 26.A defines durable records.

**Branch/worktree:** `codex/task-26b-recovery-preview`; `.worktrees/task-26b-recovery-preview`.

**Files:**
- Create: `src/vespercode/persistence/recovery_preview.py`
- Test: `tests/unit/persistence/test_recovery_decision.py`

**Interfaces:** Produces `PersistencePathRecordSequenceV1` and `RecoveryPathObservationSequenceV1`, immutable ordered tuples of their named item types, `RecoveryPreviewService.preview_transaction(transaction_id: str) -> RecoveryPreviewV1`, and pure `classify_recovery(records: PersistencePathRecordSequenceV1, observations: RecoveryPathObservationSequenceV1) -> RecoveryDispositionV1`.

**Intentionally failing test:**

```python
def test_recovery_preview_is_read_only(
    recovery: RecoveryPreviewService,
    workspace: SpyWorkspace,
) -> None:
    preview = recovery.preview_transaction("tx-1")
    assert preview.disposition in ("COMMITTED", "ROLLED_BACK", "UNRESOLVED")
    assert workspace.write_count == 0
```

**Implementation boundary:** Preview may inspect metadata and digest-safe evidence but never mutate workspace, backups, transaction rows, or audit state.

**Verification:**
- Target: `python -m pytest -q tests/unit/persistence/test_recovery_decision.py::test_recovery_preview_is_read_only`
- Domain: `python -m pytest -q tests/unit/persistence/test_recovery_decision.py`
- Expected: mixed/unknown/external-change states fail to `UNRESOLVED` with zero writes.

**Completion evidence:** Not yet executed.

#### Task 26.C: Explicit Recovery Apply and Production Fault Acceptance

**Status:** Not started

**Goal:** Apply only a current bound recovery preview under the workspace lease and prove the production protocol across deadline, external-change, ACL, and Windows identity faults.

**SPEC references:** Milestone 26 recovery apply and production acceptance requirements.

**Dependencies:** Tasks 7.C, 9.D, 23.C, and 26.B.

**Blocks:** Tasks 7.D, 31.C, 33.A, 37.B, 38.D, and 38.E.

**Parallelization:** Sequential after Task 26.B.

**Branch/worktree:** `codex/task-26c-recovery-apply`; `.worktrees/task-26c-recovery-apply`.

**Files:**
- Create: `src/vespercode/storage/migrations/v0012_recovery.py`
- Create: `src/vespercode/persistence/recovery_apply.py`
- Create: `src/vespercode/persistence/recovery.py`
- Test: `tests/unit/storage/test_recovery_migration.py`
- Test: `tests/fault_injection/persistence/test_deadline_faults.py`
- Test: `tests/fault_injection/persistence/test_external_change_faults.py`
- Test: `tests/integration/windows/test_persistence_acl_and_identity.py`

**Interfaces:** Produces immutable `RECOVERY_V1_MIGRATION = MigrationV1(version=12, name="recovery_v1", ...)`, `RecoveryService.preview(workspace: WorkspaceIdentityV1) -> RecoveryPreviewV1` by selecting the workspace-bound transaction and delegating only to Task 26.B `preview_transaction(transaction_id: str)`, `RecoveryService.apply(command: ApplyRecoveryV1) -> RecoveryResultV1` using Task 26.A artifacts/records, and read-only `has_unresolved_transaction(workspace_identity_digest: str) -> bool`.

**Intentionally failing test:**

```python
def test_stale_preview_cannot_apply_recovery(
    recovery: RecoveryService,
    workspace: SpyWorkspace,
) -> None:
    result = recovery.apply(command_with_stale_preview_digest())
    assert result.error_code == "RECOVERY_PREVIEW_STALE"
    assert workspace.write_count == 0
```

**Schema RED:** `tests/unit/storage/test_recovery_migration.py::test_recovery_migration_has_exact_schema` applies v0001–v0012 and asserts the sole `recovery_results` table, unique FK `transaction_id → persistence_transactions`, closed disposition/evidence digest/ref/timestamp fields, and absence of backup/preimage/postimage/raw-output/credential bodies.

**Implementation boundary:** This task owns one coupled terminal-recovery storage behavior: immutable v0012 DDL and the exact apply transaction that records one service-proven terminal result. It cannot edit the final registry. Its admission predicate is read-only and returns false only after a service-proven terminal disposition; it cannot mutate or bypass recovery. There is no force, ignore, skip-path, edit-record, or user-declared success path; only service-proven terminal dispositions unblock admission.

**Verification:**
- Target: `python -m pytest -q tests/fault_injection/persistence/test_external_change_faults.py::test_stale_preview_cannot_apply_recovery`
- Schema: `python -m pytest -q tests/unit/storage/test_recovery_migration.py::test_recovery_migration_has_exact_schema`
- Domain: `python -m pytest -q tests/unit/storage/test_recovery_migration.py tests/fault_injection/persistence`
- Windows: `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_persistence_acl_and_identity.py`
- Expected: exact v0012 schema and the complete production matrix produce only the three declared dispositions and never overwrite an unproven external change.

**Completion evidence:** Not yet executed.

#### Task 27.A: Pure Non-revealing Credential Lifecycle

**Status:** Not started

**Goal:** Enforce the OPENAI-only set/status/update/clear/get-for-call contract through a redacted non-serializable secret wrapper and a verified store port.

**SPEC references:** Milestone 27 service scope; SPEC §4.8, §5.5–§5.6, §8.1–§8.2, and AC-08/AC-13/AC-28.

**Dependencies:** Tasks 4.E, 5.D, and 6.E.

**Files:**
- Create: `src/vespercode/credentials/port.py`
- Create: `src/vespercode/credentials/service.py`
- Test: `tests/unit/credentials/test_service.py`
- Test: `tests/unit/credentials/test_status.py`
- Test: `tests/unit/credentials/test_backend_rejection.py`
- Test: `tests/unit/credentials/test_call_lookup.py`
- Test: `tests/unit/credentials/test_log_redaction.py`

**Interfaces:** Produces `SecretCredentialV1`, `CredentialStorePortV1.set(provider: Literal["OPENAI"], secret: SecretCredentialV1) -> CredentialStoreMutationV1`, `CredentialStorePortV1.get_for_call(provider: Literal["OPENAI"]) -> SecretCredentialV1 | CredentialMissingV1`, `CredentialStorePortV1.status(provider: Literal["OPENAI"]) -> CredentialStatusV1`, `CredentialStorePortV1.clear(provider: Literal["OPENAI"]) -> CredentialStoreMutationV1`, `CredentialService.set(provider: Literal["OPENAI"], secret: SecretCredentialV1) -> CredentialMutationResultV1`, `CredentialService.status(provider: Literal["OPENAI"]) -> CredentialStatusV1`, `CredentialService.update(provider: Literal["OPENAI"], secret: SecretCredentialV1) -> CredentialMutationResultV1`, `CredentialService.clear(provider: Literal["OPENAI"]) -> CredentialMutationResultV1`, and `CredentialService.get_for_call(provider: Literal["OPENAI"]) -> SecretCredentialV1 | CredentialErrorV1`.

**Intentionally failing test:**

```python
def test_credential_status_never_contains_secret_or_derivative(
    credential_service: CredentialService,
) -> None:
    secret = SecretCredentialV1.from_hidden_input("inert-sentinel-value")
    assert credential_service.set("OPENAI", secret).kind == "STORED"
    rendered = credential_service.status("OPENAI").model_dump_json()
    assert "inert-sentinel-value" not in rendered
    assert "length" not in rendered
    assert "digest" not in rendered
```

Expected RED: import failure because the credential port/service and secret wrapper do not exist.

**Implementation boundary:** This child owns provider/input closure, backend-probe ordering, public lifecycle results, per-call re-probe/read, and exception/repr/log redaction against injectable fake ports. It does not implement WinCred, accept CLI/env/file secrets, or run a real Windows proof.

**Verification:**
- Target: `python -m pytest -q tests/unit/credentials/test_status.py::test_credential_status_never_contains_secret_or_derivative`
- Domain: `python -m pytest -q tests/unit/credentials`
- Expected GREEN: both commands exit `0`; safe/unsafe backend, set/status/update/clear failure, cleared-after-readiness, fresh call lookup, and redaction cases pass offline.

**Completion evidence:** Not yet executed.

#### Task 27.B: Windows Credential Manager Adapter and Real Proof

**Status:** Not started

**Goal:** Implement the sole WinCred store port and prove real set/status/get-for-call/clear lifecycle with final cleanup and no fallback backend.

**SPEC references:** Milestone 27 adapter scope; SPEC §4.8 Windows backend requirements, §10.3 Windows integration, AC-15/AC-24/AC-28.

**Dependencies:** Task 27.A.

**Files:**
- Create: `src/vespercode/credentials/wincred_store.py`
- Test: `tests/integration/windows/test_wincred_smoke.py`

**Interfaces:** Produces `WindowsCredentialManagerStore.probe_backend() -> CredentialBackendProbeV1` and a concrete `WindowsCredentialManagerStore` implementation of every `CredentialStorePortV1` method declared by Task 27.A.

**Intentionally failing test:**

```python
def test_wincred_smoke_clears_generated_test_entry(
    wincred_store: WindowsCredentialManagerStore,
) -> None:
    secret = generated_test_secret()
    try:
        assert wincred_store.set("OPENAI", secret).kind == "STORED"
        assert wincred_store.status("OPENAI").configured is True
        assert isinstance(wincred_store.get_for_call("OPENAI"), SecretCredentialV1)
    finally:
        wincred_store.clear("OPENAI")
    assert wincred_store.status("OPENAI").configured is False
```

Expected RED: import failure because the Windows Credential Manager adapter does not exist.

**Implementation boundary:** This child maps one versioned target name to WinCred, proves backend capability around mutations/reads, redacts backend failures, and cleans the generated test entry in `finally`. It adds no fallback store, cache, environment import, CLI secret, Web form, or transport call.

**Verification:**
- Target: `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_wincred_smoke.py::test_wincred_smoke_clears_generated_test_entry`
- Domain: `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows/test_wincred_smoke.py`
- Expected GREEN: both commands exit `0` on the Windows runner without skip; backend identity, overwrite/delete errors, fresh lookup, cleared state, and final cleanup pass without secret output.

**Completion evidence:** Not yet executed.

#### Task 28.A: Loopback Request Security Boundary

**Status:** Not started

**Goal:** Enforce loopback-only binding, local session, Host, Origin, CSRF, and response security headers before every route-domain call.

**SPEC references:** Milestone 28 local Web security and threat-model requirements.

**Dependencies:** Tasks 7.C, 8.B, 23.C, and 27.B.

**Blocks:** Tasks 28.B and 37.B.

**Parallelization:** Parallelizable with Tasks 9.A, 9.B, 9.C, 9.D, and 16.B once each exact executable Dependencies field is satisfied.

**Branch/worktree:** `codex/task-28a-web-security`; `.worktrees/task-28a-web-security`.

**Files:**
- Create: `src/vespercode/web/security.py`
- Test: `tests/web/test_security.py`

**Interfaces:** Produces `LocalWebSecurityConfigV1(host: Literal["127.0.0.1"], port: int, session_cookie_name: str, csrf_header_name: str)`, `LocalSessionManager.create() -> LocalSessionV1`, and `verify_local_request(request: Request, session: LocalSessionV1) -> LocalRequestAuthorizationV1`.

**Intentionally failing test:**

```python
def test_state_change_rejects_non_loopback_origin(
    local_web_client: TestClient,
    valid_csrf_headers: dict[str, str],
) -> None:
    response = local_web_client.post(
        "/runs",
        headers={**valid_csrf_headers, "Origin": "https://attacker.example"},
        data=valid_run_form_data(),
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "ORIGIN_REJECTED"
```

**Implementation boundary:** Security middleware owns authorization ordering only and cannot import domain repositories, credentials, Docker, or recovery bodies.

**Verification:**
- Target: `python -m pytest -q tests/web/test_security.py::test_state_change_rejects_non_loopback_origin`
- Domain: `python -m pytest -q tests/web/test_security.py`
- Expected: binding, session, Host/Origin/CSRF and headers fail before all spy domain calls.

**Completion evidence:** Not yet executed.

#### Task 28.B: Safe Local Application Shell and Serve CLI

**Status:** Not started

**Goal:** Compose the extensible local FastAPI shell, escaped/status-accessible templates, pinned HTMX asset, and loopback-only `vespercode serve` entry point.

**SPEC references:** Milestone 28 application-shell, rendering, status, startup, and usability requirements.

**Dependencies:** Task 28.A.

**Blocks:** Tasks 29.A, 29.B, 29.C, 31.A, 33.A, 37.B, 38.A, 38.B, 38.C, 38.D, and 38.E.

**Parallelization:** Sequential after Task 28.A.

**Branch/worktree:** `codex/task-28b-local-shell`; `.worktrees/task-28b-local-shell`.

**Files:**
- Create: `src/vespercode/web/app.py`
- Create: `src/vespercode/web/templates/base.html`
- Create: `src/vespercode/web/templates/home.html`
- Create: `src/vespercode/web/templates/components/status_badge.html`
- Create: `src/vespercode/web/static/htmx.min.js`
- Create: `src/vespercode/cli.py`
- Test: `tests/web/test_html_escaping.py`
- Test: `tests/web/test_status_labels.py`
- Test: `tests/web/test_app_composition.py`
- Test: `tests/unit/test_cli.py`

**Interfaces:** Produces protocol `LocalShellPortsV1.list_recent_runs() -> RunVisibilitySequenceV1`, `LocalShellPortsV1.credential_status() -> CredentialStatusV1`, protocol `LocalRouteInstallerV1.install(app: FastAPI) -> None`, `LocalRouteInstallerSequenceV1`, an immutable ordered tuple of route installers, `create_local_app(shell_ports: LocalShellPortsV1, security: LocalWebSecurityConfigV1, route_installers: LocalRouteInstallerSequenceV1) -> FastAPI`, `render_status_badge(visibility: RunVisibilityV1) -> Markup`, and CLI `vespercode serve --host 127.0.0.1 --port 8765`.

**Intentionally failing test:**

```python
def test_untrusted_run_text_is_escaped(local_web_client: TestClient) -> None:
    response = local_web_client.get("/", headers=valid_local_security_headers())
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
```

**Implementation boundary:** The shell installs only typed route installers and exposes no service locator. Formal serve rejects non-loopback hosts and secret CLI parameters.

**Verification:**
- Target: `python -m pytest -q tests/web/test_html_escaping.py::test_untrusted_run_text_is_escaped`
- Domain: `python -m pytest -q tests/web/test_html_escaping.py tests/web/test_status_labels.py tests/web/test_app_composition.py tests/unit/test_cli.py`
- Browser: open the loopback shell and verify status labels, keyboard focus, live errors, CSP, and no CDN request.
- Expected: safe rendering, exact status comprehension, installer order, packaged asset loading, and CLI argument closure pass.

**Completion evidence:** Not yet executed.

#### Task 29.A: Run Lifecycle WebUI

**Status:** Not started

**Goal:** Expose strict Run creation, state/status detail, and cancellation through closed secure forms and typed workflow ports.

**SPEC references:** Milestone 29 run creation/status/cancel requirements.

**Dependencies:** Tasks 8.B, 23.C, 25.G, and 28.B.

**Blocks:** Tasks 29.C and 37.B.

**Parallelization:** Parallel with Task 29.B.

**Branch/worktree:** `codex/task-29a-run-web`; `.worktrees/task-29a-run-web`.

**Files:**
- Create: `src/vespercode/web/run_lifecycle_workflow.py`
- Create: `src/vespercode/web/routes_runs.py`
- Create: `src/vespercode/web/templates/run_create.html`
- Create: `src/vespercode/web/templates/run_detail.html`
- Test: `tests/web/test_run_workflow.py`

**Interfaces:** Produces `RunCreationWorkflowPortV1`, `RunVisibilityWorkflowPortV1`, `RunCancellationWorkflowPortV1`, their closed result unions, and `RunLifecycleRouteInstallerV1`.

**Intentionally failing test:**

```python
def test_invalid_run_form_creates_no_run(
    local_web_client: TestClient,
    workflow_ports: SpyRunLifecyclePorts,
) -> None:
    response = local_web_client.post(
        "/runs", headers=valid_local_security_headers(), data={"base_url": "https://bad.example"}
    )
    assert response.status_code == 422
    assert workflow_ports.create_call_count == 0
```

**Implementation boundary:** Routes perform Task 28 security and closed form adaptation only. Run rules and state transitions remain in Tasks 8, 23, and 25.

**Verification:**
- Target: `python -m pytest -q tests/web/test_run_workflow.py::test_invalid_run_form_creates_no_run`
- Domain: `python -m pytest -q tests/web/test_run_workflow.py`
- Expected: create/status/cancel states render safely, idempotently, and without exposing forbidden override fields.

**Completion evidence:** Not yet executed.

#### Task 29.B: Disclosure Decision WebUI

**Status:** Not started

**Goal:** Render exact provider/endpoint/category/path/budget disclosure facts and submit only a bound approve/reject decision to the Task 15 workflow.

**SPEC references:** Milestone 29 disclosure requirements.

**Dependencies:** Tasks 15.E, 16.B, 23.C, and 28.B.

**Blocks:** Tasks 29.C and 37.B.

**Parallelization:** Parallel with Task 29.A.

**Branch/worktree:** `codex/task-29b-disclosure-web`; `.worktrees/task-29b-disclosure-web`.

**Files:**
- Create: `src/vespercode/web/disclosure_workflow.py`
- Create: `src/vespercode/web/routes_disclosure.py`
- Create: `src/vespercode/web/templates/disclosure_wait.html`
- Test: `tests/web/test_disclosure_workflow.py`

**Interfaces:** Produces `DisclosureDecisionWorkflowPortV1.decide(command: DecideDisclosureGrantV1) -> DisclosureDecisionResultV1`, `AuthorizationSummaryV1`, `build_authorization_summary(subject: DisclosureGrantSubjectV1, endpoint: OpenAIEndpointV1) -> AuthorizationSummaryV1`, `render_authorization_summary(summary: AuthorizationSummaryV1) -> Markup`, and `DisclosureRouteInstallerV1.install(app: FastAPI) -> None`.

**Intentionally failing test:**

```python
def test_disclosure_form_cannot_supply_scope_or_endpoint_override(
    local_web_client: TestClient,
    disclosure_ports: SpyDisclosurePorts,
) -> None:
    response = local_web_client.post(
        "/runs/run-1/disclosure",
        headers=valid_local_security_headers(),
        data=valid_disclosure_decision() | {"base_url": "https://bad.example"},
    )
    assert response.status_code == 422
    assert disclosure_ports.decide_call_count == 0
```

**Implementation boundary:** The form cannot construct or mutate a Grant, source scope, byte budget, endpoint, credential, or clock value.

**Verification:**
- Target: `python -m pytest -q tests/web/test_disclosure_workflow.py::test_disclosure_form_cannot_supply_scope_or_endpoint_override`
- Domain: `python -m pytest -q tests/web/test_disclosure_workflow.py`
- Expected: exact human labels, no-content-redaction warning, expiry, budget, and closed decision binding pass.

**Completion evidence:** Not yet executed.

#### Task 29.C: Final Writeback WebUI and Governance Route Composition

**Status:** Not started

**Goal:** Render the exact FinalDiff/evidence/subject, delegate one bound final decision, call persistence only after exact approval, and install all Milestone 29 routes.

**SPEC references:** Milestone 29 final writeback and local workflow composition requirements.

**Dependencies:** Tasks 14.C, 21.C, 26.A, 28.B, 29.A, and 29.B.

**Blocks:** Tasks 31.A, 33.A, 37.B, 38.A, 38.B, 38.C, 38.D, and 38.F.

**Parallelization:** Sequential after Tasks 29.A and 29.B.

**Branch/worktree:** `codex/task-29c-writeback-web`; `.worktrees/task-29c-writeback-web`.

**Files:**
- Create: `src/vespercode/web/writeback_workflow.py`
- Create: `src/vespercode/web/routes_writeback.py`
- Create: `src/vespercode/web/run_workflows.py`
- Test: `tests/web/test_writeback_workflow.py`
- Test: `tests/web/test_accessibility.py`

**Interfaces:** Produces `FinalWritebackWorkflowPortV1`, `ProductionFinalWritebackWorkflowV1`, `WritebackReviewV1`, `RunGovernanceWorkflowPortsV1`, and `RunGovernanceRouteInstallerV1`.

**Intentionally failing test:**

```python
def test_stale_writeback_subject_never_calls_persistence(
    local_web_client: TestClient,
    workflow_ports: SpyRunGovernanceWorkflowPorts,
    stale_writeback_form: dict[str, str],
) -> None:
    response = local_web_client.post(
        "/runs/run-1/final-writeback",
        headers=valid_local_security_headers(),
        data=stale_writeback_form,
    )
    assert response.status_code == 409
    assert workflow_ports.persistence_call_count == 0
```

**Implementation boundary:** Only `WritebackApprovedV1` may create a Task 26.A persistence command. Routes cannot accept candidate/diff/evidence/workspace/policy fields or duplicate approval/persistence predicates.

**Verification:**
- Target: `python -m pytest -q tests/web/test_writeback_workflow.py::test_stale_writeback_subject_never_calls_persistence`
- Domain: `python -m pytest -q tests/web/test_writeback_workflow.py tests/web/test_accessibility.py tests/web/test_run_workflow.py tests/web/test_disclosure_workflow.py`
- Browser: exercise create → running → disclosure → formal review → stale approval by keyboard.
- Expected: exact installer order, secure posts, no stale write, escaped evidence, focus/errors, and non-color status cues pass.

**Completion evidence:** Not yet executed.

#### Task 30.A: Headless Capability-isolated Demo Core

**Status:** Not started

**Goal:** Implement Demo-only types, fixed scenario data, simulated tool ports, shared-core runner, and bounded in-memory sessions without formal capability adapters.

**SPEC references:** Milestone 30 shared-core, fixed-scenario, type-isolation, and session-limit requirements.

**Dependencies:** Tasks 4.E, 5.D, 13, 17.C, 24.C, 25.A, and 25.D.

**Blocks:** Tasks 30.B, 32.A, and 37.B.

**Parallelization:** Parallelizable with Tasks 29.A, 29.B, and 29.C once each exact executable Dependencies field is satisfied.

**Branch/worktree:** `codex/task-30a-demo-core`; `.worktrees/task-30a-demo-core`.

**Files:**
- Create: `src/vespercode/demo/types.py`
- Create: `src/vespercode/demo/scenario.py`
- Create: `src/vespercode/demo/executor.py`
- Create: `src/vespercode/demo/runner.py`
- Test: `tests/demo/test_types.py`
- Test: `tests/demo/test_scenario.py`
- Test: `tests/demo/test_trace_determinism.py`
- Test: `tests/demo/test_shared_core_composition.py`
- Test: `tests/demo/test_session_limits.py`

**Interfaces:** Produces `DemoScenarioV1`, `DemoExecutor.tool_ports() -> ToolPortsV1`, `DemoScenarioRunner.advance(session: DemoSessionV1, decision: DemoDecisionV1 | None) -> DemoStepResultV1`, `DemoRunStatus`, `DemoDecision`, `DemoTraceV1`, and exact constant `DEMO_SHARED_CORE_MODULES_V1: frozenset[str] = frozenset({"vespercode.governance.policy", "vespercode.loop.agent_actions", "vespercode.loop.action_parser", "vespercode.loop.action_binding", "vespercode.loop.context_projection", "vespercode.loop.feedback", "vespercode.loop.stopping", "vespercode.loop.action_pipeline", "vespercode.tools.dispatcher"})`.

**Intentionally failing test:**

```python
def test_demo_step_invokes_shared_core_and_only_demo_tool_ports(
    shared_core_spies: SharedCoreSpies,
    demo_runner: DemoScenarioRunner,
    demo_session: DemoSessionV1,
) -> None:
    result = demo_runner.advance(demo_session, decision=None)
    assert shared_core_spies.calls == (
        "ActionPipeline.execute",
        "ActionParser.parse",
        "bind_action",
        "PolicyEngine.evaluate",
        "ToolDispatcher.dispatch",
        "build_feedback",
        "select_feedback",
        "consume_feedback",
        "StopEvaluator.evaluate",
    )
    assert result.executor_kind == "DEMO_EXECUTOR"
    assert shared_core_spies.formal_capability_calls == 0
```

**Implementation boundary:** The scenario stores only data. Composition constructs the production Task 25.D `ActionPipeline` from the exact Task 13/17.A–17.C/24.A/24.C components, injects that instance into `DemoScenarioRunner`, and wraps its real `ActionPipeline.execute` call in the runtime spy trace; Task 24.B context and Task 25.A stopping remain injected production pure functions. No Demo module copies their orchestration, and every prohibited formal-capability module prefix is absent. Sessions are in-memory, five-minute/20-action/10-concurrent bounded, and non-recoverable.

**Verification:**
- Target: `python -m pytest -q tests/demo/test_shared_core_composition.py::test_demo_step_invokes_shared_core_and_only_demo_tool_ports`
- Domain: `python -m pytest -q tests/demo/test_types.py tests/demo/test_scenario.py tests/demo/test_trace_determinism.py tests/demo/test_shared_core_composition.py tests/demo/test_session_limits.py`
- Expected: shared-call provenance, fixed trace, type isolation, limit/expiry/reset, and zero formal-capability calls pass.

**Completion evidence:** Not yet executed.

#### Task 30.B: Public Demo Web Application and Health Boundary

**Status:** Not started

**Goal:** Present the headless Demo through an escaped simulation-labeled FastAPI app with `/healthz`, platform PORT handling, and explicit capability-absence verification.

**SPEC references:** Milestone 30 public application, rendering, health, and deployment-boundary requirements.

**Dependencies:** Task 30.A.

**Blocks:** Tasks 32.C, 34.B, and 37.B.

**Parallelization:** Sequential after Task 30.A.

**Branch/worktree:** `codex/task-30b-demo-app`; `.worktrees/task-30b-demo-app`.

**Files:**
- Create: `src/vespercode/demo/app.py`
- Create: `src/vespercode/demo/healthcheck.py`
- Create: `src/vespercode/demo/templates/demo.html`
- Test: `tests/demo/test_capability_isolation.py`
- Test: `tests/demo/test_health.py`
- Test: `tests/demo/test_rendering.py`

**Interfaces:** Produces `create_demo_app(config: DemoAppConfigV1) -> FastAPI`, `healthcheck.main() -> int`, `GET /healthz -> 200 {"status":"ok","mode":"simulation"}`, and closed fixed-scenario routes `POST /demo/sessions -> DemoSessionCreatedV1` and `POST /demo/sessions/{session_id}/advance -> DemoStepResultV1`.

**Intentionally failing test:**

```python
def test_demo_app_registers_no_formal_capability_adapter(
    demo_app: FastAPI,
) -> None:
    assert demo_app.state.capability_kinds == {"DEMO_EXECUTOR", "DEMO_SESSION", "DEMO_RENDERER"}
```

**Implementation boundary:** No repository path/upload/prompt/URL/provider/secret input, disk persistence, local route, recovery, SQLite, WinCred, Docker, or OpenAI adapter is registered.

**Verification:**
- Target: `python -m pytest -q tests/demo/test_capability_isolation.py::test_demo_app_registers_no_formal_capability_adapter`
- Domain: `python -m pytest -q tests/demo/test_capability_isolation.py tests/demo/test_health.py tests/demo/test_rendering.py`
- Browser: execute the fixed scenario with keyboard and verify persistent simulation labeling and non-color status.
- Expected: health validates assets/registry, PORT boundaries hold, and forbidden capabilities/endpoints remain absent.

**Completion evidence:** Not yet executed.

#### Task 31.A: Reference E2E Harness and Happy Path

**Status:** Not started

**Goal:** Build the deterministic disposable reference harness and prove admission through stable baseline, corrective loop, formal validation, and `VerifiedCandidateV1`.

**SPEC references:** Milestone 31 complete production-workflow references; owns reusable E2E driver and success path up to final wait.

**Dependencies:** Tasks 9.D, 10.C, 11.B, 12.D, 13, 14.C, 15.E, 16.B, 17.C, 18.D, 19.C, 20.B, 21.C, 22.C, 23.C, 24.C, 25.G, 26.A, 27.B, 28.B, 29.C, and 38.F.

**Blocks:** Tasks 31.B, 31.C, and 37.B.

**Parallelization:** Sequential after Tasks 9.D, 10.C, 11.B, 12.D, 13, 14.C, 15.E, 16.B, 17.C, 18.D, 19.C, 20.B, 21.C, 22.C, 23.C, 24.C, 25.G, 26.A, 27.B, 28.B, 29.C, and 38.F.

**Branch/worktree:** `codex/task-31a-reference-happy`; `.worktrees/task-31a-reference-happy`.

**Files:**
- Create: `scripts/run_reference_e2e.py`
- Create: `tests/e2e/reference/test_reference_success.py`

**Interfaces:** Produces `ReferenceE2EHarness.run(config: ReferenceE2EConfigV1) -> ReferenceE2EResultV1`, `run_reference_e2e(config: ReferenceE2EConfigV1) -> ReferenceE2EResultV1`, and content-addressed `ReferenceE2ETraceV1` stages consumed by Tasks 31.B and 31.C.

**Intentionally failing test:**

```python
def test_reference_happy_path_reaches_verified_candidate(
    reference_e2e_harness: ReferenceE2EHarness,
) -> None:
    result = reference_e2e_harness.run_until_final_wait()
    assert result.verified_candidate_created is True
    assert result.workspace_write_count == 0
```

**Implementation boundary:** Use production composition with only LLM/clock/id fixtures deterministic. Fixture bytes are immutable and the driver exposes explicit stage hooks rather than scenario-specific alternate core logic.

**Verification:**
- Target: `python -m pytest -q -o addopts='' -m reference_e2e tests/e2e/reference/test_reference_success.py::test_reference_happy_path_reaches_verified_candidate`
- Domain: same as Target.
- Expected: the real Windows + Docker + Mock happy path reaches a bound VerifiedCandidate and final wait without writing.

**Completion evidence:** Not yet executed.

#### Task 31.B: Reference Safety and Negative Gates

**Status:** Not started

**Goal:** Prove canonical continuation, hard denial, protected-artifact defense, final-wait no-write branches, and per-real-call credential fail-close in the production E2E harness.

**SPEC references:** Milestone 31 denial, cursor, wait, and call-gate requirements.

**Dependencies:** Tasks 11.B, 13, 14.C, 15.E, 16.B, 27.B, and 31.A.

**Blocks:** Tasks 31.C and 37.B.

**Parallelization:** Sequential after Task 31.A; test files are disjoint from Task 31.C.

**Branch/worktree:** `codex/task-31b-reference-safety`; `.worktrees/task-31b-reference-safety`.

**Files:**
- Create: `tests/e2e/reference/test_reference_denials.py`
- Create: `tests/e2e/reference/test_reference_waits.py`
- Create: `tests/e2e/reference/test_reference_no_write.py`
- Create: `tests/e2e/reference/test_reference_call_gate.py`

**Interfaces:** Consumes Task 31.A stage hooks only; produces denial/wait/call-gate trace assertions without changing production code or the reference fixture.

**Intentionally failing test:**

```python
def test_cleared_credential_has_zero_real_call_side_effects(
    reference_e2e_harness: ReferenceE2EHarness,
) -> None:
    result = reference_e2e_harness.run_cleared_credential_call_gate()
    assert result.error_code == "CREDENTIAL_MISSING"
    assert result.real_call_side_effect_counts == (0, 0, 0, 0, 0)
```

**Implementation boundary:** Each negative scenario must prove zero partial artifact/write/dispatch/network where required. Tests cannot replace production ports with alternate policy/parser/feedback implementations.

**Verification:**
- Target: `python -m pytest -q -o addopts='' -m reference_e2e tests/e2e/reference/test_reference_call_gate.py::test_cleared_credential_has_zero_real_call_side_effects`
- Domain: `python -m pytest -q -o addopts='' -m reference_e2e tests/e2e/reference/test_reference_denials.py tests/e2e/reference/test_reference_waits.py tests/e2e/reference/test_reference_no_write.py tests/e2e/reference/test_reference_call_gate.py`
- Expected: every denial/wait/cursor/credential branch produces the exact stable reason and zero forbidden side effects.

**Completion evidence:** Not yet executed.

#### Task 31.C: Reference Persistence, Recovery, Audit, and Determinism

**Status:** Not started

**Goal:** Complete exact approved writeback, uncertain recovery blocking, memory/audit evidence, cleanup, and two-run semantic determinism in the reference harness.

**SPEC references:** Milestone 31 persistence, recovery, evidence, repeatability, and report requirements.

**Dependencies:** Tasks 26.C, 31.A, 31.B, and 38.G.

**Blocks:** Tasks 33.A, 34.A, 37.A, and 37.B.

**Parallelization:** Sequential after Tasks 26.C, 31.A, 31.B, and 38.G; this is the final reference E2E child.

**Branch/worktree:** `codex/task-31c-reference-terminal`; `.worktrees/task-31c-reference-terminal`.

**Files:**
- Create: `tests/e2e/reference/test_reference_audit.py`
- Create: `tests/e2e/reference/test_reference_recovery_block.py`

**Interfaces:** Consumes Task 31.A's `ReferenceE2EHarness`/`ReferenceE2ETraceV1`, Task 31.B scenario hooks, production Task 26.C recovery, Tasks 22.A–22.C memory evidence, and Task 23.C audit visibility/retention evidence; produces the finalized `ReferenceE2EResultV1` and standalone canonical report consumed by Tasks 33.A, 34.A, 37.A, 37.B, and 37.C.

**Intentionally failing test:**

```python
def test_uncertain_transaction_blocks_new_admission_until_proven_recovery(
    reference_e2e_harness: ReferenceE2EHarness,
) -> None:
    result = reference_e2e_harness.run_uncertain_recovery_scenario()
    assert result.preview_write_count == 0
    assert result.second_admission_error == "RECOVERY_REQUIRED"
```

**Implementation boundary:** Exact approval is the only write path. Determinism comparison excludes only declared injected volatile ids/times; cleanup may not delete unresolved recovery evidence.

**Verification:**
- Target: `python -m pytest -q -o addopts='' -m reference_e2e tests/e2e/reference/test_reference_recovery_block.py::test_uncertain_transaction_blocks_new_admission_until_proven_recovery`
- Domain: `python -m pytest -q -o addopts='' -m reference_e2e tests/e2e/reference`
- Script: `python scripts/run_reference_e2e.py --workspace-root tests/.tmp/reference-e2e --report tests/.tmp/reference-e2e-report.json`
- Expected: exact postimages commit, recovery remains three-valued, audit is redacted/monotonic, two semantic traces match, and cleanup is proven.

**Completion evidence:** Not yet executed.

#### Task 32.A: Offline Governance Mechanism Trace

**Status:** Not started

**Goal:** Build the headless mechanism driver and prove hard DENY, protected-artifact precedence, final-approval no-write, and bounded canonical reporting.

**SPEC references:** Milestone 32 governance and approval mechanism requirements.

**Dependencies:** Tasks 12.D, 13, 17.C, 24.C, 25.A, 25.D, and 30.A.

**Blocks:** Tasks 32.B, 32.C, and 37.B.

**Parallelization:** Parallelizable with Tasks 38.A, 38.B, 38.C, 38.D, 38.E, 38.F, and 38.G once each exact executable Dependencies field is satisfied.

**Branch/worktree:** `codex/task-32a-governance-trace`; `.worktrees/task-32a-governance-trace`.

**Files:**
- Create: `scripts/run_mechanism_demo.py`
- Create: `tests/e2e/mechanism/test_hard_deny.py`
- Create: `tests/e2e/mechanism/test_protected_artifacts.py`
- Create: `tests/e2e/mechanism/test_approval_gate.py`

**Interfaces:** Produces `MechanismHarness.run(config: MechanismDemoConfigV1) -> MechanismDemoResultV1`, `run_mechanism_demo(config: MechanismDemoConfigV1) -> MechanismDemoResultV1`, `MechanismDemoTraceV1`, and bounded text/JSON report stages consumed by Tasks 32.B and 32.C.

**Intentionally failing test:**

```python
def test_outside_scope_patch_is_denied_before_dispatch_or_publish(
    mechanism_harness: MechanismHarness,
) -> None:
    trace = mechanism_harness.run_step("outside-scope-create")
    assert trace.error_code == "PATCH_PATH_NOT_EDITABLE"
    assert trace.dispatch_count == trace.candidate_publish_count == 0
```

**Implementation boundary:** The driver is offline and invokes production parser/policy/dispatcher/feedback/stop components; it cannot introduce alternative mechanism rules.

**Verification:**
- Target: `python -m pytest -q tests/e2e/mechanism/test_hard_deny.py::test_outside_scope_patch_is_denied_before_dispatch_or_publish`
- Domain: `python -m pytest -q tests/e2e/mechanism/test_hard_deny.py tests/e2e/mechanism/test_protected_artifacts.py tests/e2e/mechanism/test_approval_gate.py`
- Expected: all governance blocks occur before forbidden dispatch/publish/write.

**Completion evidence:** Not yet executed.

#### Task 32.B: Feedback Recovery and Continuation Determinism Trace

**Status:** Not started

**Goal:** Prove failing-check feedback changes the next action once and that paged List/Search plus repeated mechanism runs are semantically deterministic.

**SPEC references:** Milestone 32 feedback, continuation, and determinism requirements.

**Dependencies:** Tasks 11.B, 19.C, 24.C, and 32.A.

**Blocks:** Tasks 32.C and 37.B.

**Parallelization:** Sequential after Task 32.A's driver.

**Branch/worktree:** `codex/task-32b-feedback-trace`; `.worktrees/task-32b-feedback-trace`.

**Files:**
- Create: `tests/e2e/mechanism/test_feedback_recovery.py`
- Create: `tests/e2e/mechanism/test_continuation_gate.py`
- Create: `tests/e2e/mechanism/test_trace_determinism.py`

**Interfaces:** Consumes only Task 32.A `MechanismHarness`/`MechanismDemoTraceV1` stages plus production Tasks 11.B, 19.C, and 24.C behavior; produces the feedback-recovery, continuation, and determinism stages appended to `MechanismDemoTraceV1` and consumed by Task 32.C.

**Intentionally failing test:**

```python
def test_failed_check_feedback_changes_next_action_once(
    mechanism_harness: MechanismHarness,
) -> None:
    trace = mechanism_harness.run_feedback_recovery()
    assert trace.first_action_digest != trace.corrective_action_digest
    assert trace.feedback_consumption_count == 1
```

**Implementation boundary:** No test may preselect the corrective action outside the fixed Mock response/feedback input or compare only presentation labels.

**Verification:**
- Target: `python -m pytest -q tests/e2e/mechanism/test_feedback_recovery.py::test_failed_check_feedback_changes_next_action_once`
- Domain: `python -m pytest -q tests/e2e/mechanism/test_feedback_recovery.py tests/e2e/mechanism/test_continuation_gate.py tests/e2e/mechanism/test_trace_determinism.py`
- Expected: feedback is consumed once, cursor pages are exact, tamper/stale returns zero payload, and repeated semantic traces match.

**Completion evidence:** Not yet executed.

#### Task 32.C: Shared-core Provenance and Real-call Zero-side-effect Proof

**Status:** Not started

**Goal:** Prove formal and public Demo compositions execute the same exact pure-core subset while disclosure/credential failures create zero unauthorized real-call side effects.

**SPEC references:** Milestone 32 shared-core, disclosure, credential, and capability-isolation requirements.

**Dependencies:** Tasks 15.E, 16.B, 27.B, 30.B, 32.A, and 32.B.

**Blocks:** Tasks 33.A, 34.A, 34.B, 37.A, and 37.B.

**Parallelization:** Sequential after Tasks 15.E, 16.B, 27.B, 30.B, 32.A, and 32.B; this is the final mechanism child.

**Branch/worktree:** `codex/task-32c-shared-core-proof`; `.worktrees/task-32c-shared-core-proof`.

**Files:**
- Create: `tests/e2e/mechanism/test_disclosure_gate.py`
- Create: `tests/e2e/mechanism/test_credential_recheck.py`
- Create: `tests/e2e/mechanism/test_shared_core_reuse.py`

**Interfaces:** Consumes Task 32.A `MechanismHarness`/`MechanismDemoTraceV1`, Task 32.B evidence stages, Task 15.E/16.B disclosure/adapter contracts, Task 27.B credential port, and Task 30.B Demo composition; produces the finalized `MechanismDemoTraceV1` report with exact `DEMO_SHARED_CORE_MODULES_V1` implementation provenance, ordered pure-core calls, prohibited-capability absence, adapter counters, and separate formal/Demo presentation alignment.

**Intentionally failing test:**

```python
def test_formal_and_demo_execute_same_core_implementations(
    formal_harness: MechanismHarness,
    demo_runner: DemoScenarioRunner,
    shared_core_spies: SharedCoreSpies,
) -> None:
    formal_harness.run_step("feedback-correction")
    demo_runner.advance(new_demo_session(), decision=None)
    assert shared_core_spies.formal_shared_pure_implementations == (
        ActionPipeline.execute,
        ActionParser.parse,
        bind_action,
        PolicyEngine.evaluate,
        ToolDispatcher.dispatch,
        build_feedback,
        select_feedback,
        consume_feedback,
        StopEvaluator.evaluate,
    )
    assert (
        shared_core_spies.demo_shared_pure_implementations
        == shared_core_spies.formal_shared_pure_implementations
    )
    assert shared_core_spies.demo_formal_capability_calls == 0
```

**Implementation boundary:** Label equality is not reuse proof. Provenance equality covers only the pure modules in `DEMO_SHARED_CORE_MODULES_V1`; formal engine execution is recorded only in the separate formal-loop trace. Missing/unsafe credentials and missing Grants stop before authorization, count, charge, or transport.

**Verification:**
- Target: `python -m pytest -q tests/e2e/mechanism/test_shared_core_reuse.py::test_formal_and_demo_execute_same_core_implementations`
- Domain: `python -m pytest -q tests/e2e/mechanism`
- Script: `python scripts/run_mechanism_demo.py --report tests/.tmp/mechanism-demo-report.json`
- Expected: implementation provenance matches, Demo uses only simulated ports, and every real-call gate counter remains zero.

**Completion evidence:** Not yet executed.

#### Task 33.A: Versioned Wheel Contents and Digest

**Status:** Not started

**Goal:** Build exactly one versioned wheel containing every required runtime resource, excluding prohibited files, and publish an independently verified SHA-256.

**SPEC references:** Milestone 33 wheel build/content/digest requirements.

**Dependencies:** Tasks 26.C, 28.B, 29.C, 31.C, 32.C, and 38.F.

**Blocks:** Tasks 33.B, 36.B, and 37.B.

**Parallelization:** Parallelizable with Tasks 34.A and 34.B once each exact executable Dependencies field is satisfied.

**Branch/worktree:** `codex/task-33a-wheel-build`; `.worktrees/task-33a-wheel-build`.

**Files:**
- Modify: `pyproject.toml` (package data, version, distribution metadata, and console entry point only)
- Create: `tests/smoke/package/test_wheel_contents.py`
- Create: `tests/smoke/package/test_wheel_digest.py`

**Interfaces:** Produces exactly one `dist/vespercode-{project_version}-py3-none-any.whl` and adjacent lowercase SHA-256 evidence.

**Intentionally failing test:**

```python
def test_built_wheel_contains_all_runtime_resources(
    built_wheel: WheelArchive,
) -> None:
    assert REQUIRED_RUNTIME_MEMBERS <= built_wheel.members
    assert PROHIBITED_WHEEL_MEMBERS.isdisjoint(built_wheel.members)
```

**Implementation boundary:** Packaging is declarative and may correct only installed-resource lookup defects exposed by the smoke. It may modify package data, version, distribution metadata, and the console entry point only; dependency tables, Python range, dependency sources/index policy, `requirements/dev.lock`, build backend, and pytest/Ruff/Mypy/tooling configuration are immutable. Tests/source/evidence/credentials/VCS metadata are excluded.

**Verification:**
- Target: `python -m pytest -q -o addopts='' -m package_smoke tests/smoke/package/test_wheel_contents.py::test_built_wheel_contains_all_runtime_resources`
- Build: `python -m build --wheel`
- Domain: `python -m pytest -q -o addopts='' -m package_smoke tests/smoke/package/test_wheel_contents.py tests/smoke/package/test_wheel_digest.py`
- Expected: one wheel, correct filename/version/RECORD/resources, independent digest, and zero prohibited member.

**Completion evidence:** Not yet executed.

#### Task 33.B: Clean pipx Installed-package Smoke

**Status:** Not started

**Goal:** Install Task 33.A's exact wheel into an isolated Windows pipx home and prove installed CLI, production WebUI composition, and read-only recovery preview without source-checkout fallback.

**SPEC references:** Milestone 33 clean installation and installed-entry-point requirements.

**Dependencies:** Tasks 33.A and 38.G.

**Blocks:** Tasks 35.A, 35.B, 37.A, and 37.B.

**Parallelization:** Sequential after Task 33.A.

**Branch/worktree:** `codex/task-33b-pipx-smoke`; `.worktrees/task-33b-pipx-smoke`.

**Files:**
- Create: `scripts/run_package_smoke.py`
- Create: `tests/smoke/package/test_pipx_install.py`
- Create: `tests/smoke/package/test_installed_cli.py`
- Create: `tests/smoke/package/test_installed_webui.py`
- Modify: `src/vespercode/cli.py` only if installed-resource resolution fails

**Interfaces:** Produces `run_package_smoke(config: PackageSmokeConfigV1) -> PackageSmokeResultV1` with wheel/source/Python/pipx identities and redacted command outcomes.

**Intentionally failing test:**

```python
def test_installed_cli_does_not_import_source_checkout(
    clean_pipx_install: InstalledPackage,
) -> None:
    result = clean_pipx_install.run("vespercode", "--help")
    assert result.exit_code == 0
    assert clean_pipx_install.source_checkout_import_count == 0
```

**Implementation boundary:** Use fresh project-specific pipx home/bin/app data, reserved loopback port, production installer tuple, and cleanup in `finally`; never use `recover --apply`.

**Verification:**
- Target: `python -m pytest -q -o addopts='' -m package_smoke tests/smoke/package/test_installed_cli.py::test_installed_cli_does_not_import_source_checkout`
- Domain: `python -m pytest -q -o addopts='' -m package_smoke tests/smoke/package`
- Driver: `python scripts/run_package_smoke.py --dist dist --require-one-wheel --report tests/.tmp/package-smoke-report.json`
- Expected: clean install, help/serve/formal pages/recovery preview and cleanup pass on Windows with zero source fallback or preview write.

**Completion evidence:** Not yet executed.

#### Task 34.A: Reference OCI Reproduction and Isolation Smoke

**Status:** Not started

**Goal:** Reproduce the Task 2-frozen reference OCI manifest exactly and prove its production executor/profile/fixture isolation contract.

**SPEC references:** Milestone 34 reference image, digest continuity, no-self-reference, and isolation requirements.

**Dependencies:** Tasks 2.G, 18.D, 20.B, 31.C, and 32.C.

**Non-task entry gate:** The terminal Task 2.G outcome is `GO`.

**Blocks:** Tasks 35.A, 35.B, 36.B, 37.A, and 37.B.

**Parallelization:** Parallel with Task 34.B.

**Branch/worktree:** `codex/task-34a-reference-image`; `.worktrees/task-34a-reference-image`.

**Files:**
- Create: `scripts/run_reference_image_smoke.py`
- Create: `tests/smoke/images/test_reference_image_contract.py`
- Create: `tests/smoke/images/test_reference_fixture_smoke.py`

**Interfaces:** Produces the verified reference image inspection and exact local OCI/loopback/digest-pull comparison against Task 2.G/Task 6.B.

**Intentionally failing test:**

```python
def test_rebuilt_reference_manifest_matches_frozen_task2_digest(
    rebuilt_reference_image: OCIImageInspection,
) -> None:
    assert rebuilt_reference_image.manifest_digest == task2_go_digest()
    assert rebuilt_reference_image.manifest_digest == packaged_reference_manifest_digest()
```

**Implementation boundary:** Task 2 recipe/lock/fixture/manifest/builder/output/registry inputs are read-only. Any mismatch is NO-GO and reopens Tasks 2/6 rather than rewriting the manifest.

**Verification:**
- Target: `python -m pytest -q -o addopts='' -m oci_smoke tests/smoke/images/test_reference_image_contract.py::test_rebuilt_reference_manifest_matches_frozen_task2_digest`
- Build: `docker build --pull=false -f containers/reference/Dockerfile -t vespercode-reference:local .`
- Domain: `python -m pytest -q -o addopts='' -m oci_smoke tests/smoke/images/test_reference_image_contract.py tests/smoke/images/test_reference_fixture_smoke.py`
- Driver: `python scripts/run_reference_image_smoke.py --reference vespercode-reference:local --report tests/.tmp/reference-image-smoke-report.json`
- Expected: exact digest continuity, no self-reference, non-root/no-network/read-only/resource/report/fixture smoke, and registry cleanup pass.

**Completion evidence:** Not yet executed.

#### Task 34.B: Curated Demo OCI Capability and Health Smoke

**Status:** Not started

**Goal:** Build a Demo-only image from an explicit shared-core allowlist and prove health, fixed trace, non-persistence, and absence of every formal capability adapter.

**SPEC references:** Milestone 34 Demo image, shared-core, capability-separation, and health requirements.

**Dependencies:** Tasks 30.B and 32.C.

**Blocks:** Tasks 35.A, 35.B, 36.C, 37.A, and 37.B.

**Parallelization:** Parallel with Task 34.A.

**Branch/worktree:** `codex/task-34b-demo-image`; `.worktrees/task-34b-demo-image`.

**Files:**
- Create: `containers/demo/Dockerfile`
- Create: `requirements/demo.lock`
- Create: `scripts/run_demo_image_smoke.py`
- Create: `tests/smoke/images/test_demo_image_contract.py`
- Create: `tests/smoke/images/test_demo_container_health.py`
- Create: `tests/smoke/images/test_image_capability_separation.py`

**Interfaces:** Produces `run_image_smoke(config: ImageSmokeConfigV1) -> ImageSmokeResultV1`, Demo image digest, filesystem/import inspection, `/healthz`, fixed-trace report, and exact `PROHIBITED_DEMO_MODULE_PREFIXES_V1: frozenset[str] = frozenset({"vespercode.loop.engine", "vespercode.loop.turn_boundary", "vespercode.loop.call_orchestrator", "vespercode.storage", "vespercode.workspace", "vespercode.tools.list_files", "vespercode.tools.read_file", "vespercode.tools.search_text", "vespercode.execution", "vespercode.persistence", "vespercode.credentials", "vespercode.llm.openai_adapter", "vespercode.audit", "vespercode.memory", "vespercode.web", "vespercode.cli_composition"})`.

**Intentionally failing test:**

```python
def test_demo_image_contains_shared_core_but_no_formal_adapters(
    built_demo_image: OCIImageInspection,
) -> None:
    assert set(DEMO_SHARED_CORE_MODULES_V1) <= built_demo_image.python_members
    assert not any(
        member == prefix or member.startswith(prefix + ".")
        for member in built_demo_image.python_members
        for prefix in PROHIBITED_DEMO_MODULE_PREFIXES_V1
    )
```

**Implementation boundary:** Build from the reviewed allowlist and hash-locked Demo requirements, not the formal wheel. No formal engine, Run/turn/SQLite repository, WinCred/OpenAI/file/Docker/persistence/recovery/local-composition code, socket, secret, or repository enters the image.

**Verification:**
- Target: `python -m pytest -q -o addopts='' -m oci_smoke tests/smoke/images/test_image_capability_separation.py::test_demo_image_contains_shared_core_but_no_formal_adapters`
- Build: `docker build --pull=false -f containers/demo/Dockerfile -t vespercode-demo:local .`
- Domain: `python -m pytest -q -o addopts='' -m oci_smoke tests/smoke/images/test_demo_image_contract.py tests/smoke/images/test_demo_container_health.py tests/smoke/images/test_image_capability_separation.py`
- Driver: `python scripts/run_demo_image_smoke.py --demo vespercode-demo:local --report tests/.tmp/demo-image-smoke-report.json`
- Expected: curated import closure, non-root PORT/health/fixed trace, no persistence, and capability absence pass.

**Completion evidence:** Not yet executed.

#### Task 35.A: GitHub Actions Verification Workflow

**Status:** Not started

**Goal:** Run exact `unit-test`, `reference-image-build`, and `demo-image-build` verification jobs on every GitHub push and pull request with no publishing secret or action.

**SPEC references:** Milestone 35 GitHub Actions and course push/PR requirements.

**Dependencies:** Tasks 33.B, 34.A, and 34.B.

**Blocks:** Tasks 35.C and 37.B.

**Parallelization:** Parallel with Task 35.B.

**Branch/worktree:** `codex/task-35a-github-actions`; `.worktrees/task-35a-github-actions`.

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `tests/unit/process/test_github_actions_contract.py`

**Interfaces:** Produces the exact three GitHub jobs, push/PR event contract, read-only permissions, locked setup, artifacts, and no-external-publish boundary.

**Intentionally failing test:**

```python
def test_github_runs_three_no_publish_jobs_on_push_and_pr(
    github_contract: GitHubActionsContractV1,
) -> None:
    assert github_contract.job_names == {"unit-test", "reference-image-build", "demo-image-build"}
    assert github_contract.runs_all(events={"push", "pull_request"})
    assert github_contract.external_publish_actions == ()
```

**Implementation boundary:** Fork PRs work without secrets. Loopback registry inside reference build is allowed; external registry login/push, Release, GHCR, or Render action is forbidden.

**Verification:**
- Target: `python -m pytest -q tests/unit/process/test_github_actions_contract.py::test_github_runs_three_no_publish_jobs_on_push_and_pr`
- Domain: `python -m pytest -q tests/unit/process/test_github_actions_contract.py`
- Real: push the branch and open a GitHub PR; require all applicable jobs to pass and save real URLs/artifacts.
- Expected: exact jobs/events/permissions/locks/real builds pass with no publish credential/action.

**Completion evidence:** Not yet executed.

#### Task 35.B: GitLab Verification Pipeline

**Status:** Not started

**Goal:** Run exact GitLab `unit-test`, Windows `wheel-build-smoke`, `reference-image-build`, and `demo-image-build` jobs in all required push/MR/main/tag contexts without release secrets in ordinary pipelines.

**SPEC references:** Milestone 35 GitLab verification requirements.

**Dependencies:** Tasks 33.B, 34.A, and 34.B.

**Blocks:** Tasks 35.C and 37.B.

**Parallelization:** Parallel with Task 35.A.

**Branch/worktree:** `codex/task-35b-gitlab-ci`; `.worktrees/task-35b-gitlab-ci`.

**Files:**
- Create: `.gitlab-ci.yml`
- Create: `tests/unit/process/test_gitlab_ci_contract.py`

**Interfaces:** Produces the four exact verification jobs, exclusive `rules`, project Windows runner binding, locked commands, and saved reports/artifacts.

**Intentionally failing test:**

```python
def test_gitlab_runs_all_four_verification_jobs_for_merge_request(
    gitlab_contract: GitLabContractV1,
) -> None:
    assert gitlab_contract.jobs_for(event="merge_request", branch="feature") == {
        "unit-test", "wheel-build-smoke", "reference-image-build", "demo-image-build"
    }
```

**Implementation boundary:** Ordinary push/MR/fork jobs have no release/GHCR/Render credential or external push action; missing Windows runner or smoke failure fails the pipeline.

**Verification:**
- Target: `python -m pytest -q tests/unit/process/test_gitlab_ci_contract.py::test_gitlab_runs_all_four_verification_jobs_for_merge_request`
- Domain: `python -m pytest -q tests/unit/process/test_gitlab_ci_contract.py`
- Real: push/open a GitLab MR and require the applicable four jobs, then the main-push set, to pass.
- Expected: exact contexts, runner, commands, artifacts and no-secret ordinary boundary pass.

**Completion evidence:** Not yet executed.

#### Task 35.C: Protected Release Rules and Dual-platform Evidence

**Status:** Not started

**Goal:** Add fail-closed protected-tag release rules, verify commit/digest/secret ordering, and freeze real passing GitHub/GitLab source-commit evidence without performing the release.

**SPEC references:** Milestone 35 protected release and dual-platform evidence requirements.

**Dependencies:** Tasks 35.A and 35.B; their passing real branch/MR/main results are non-task entry gates.

**Blocks:** Tasks 36.A, 36.B, 36.C, 37.A, and 37.B.

**Parallelization:** Sequential after Tasks 35.A and 35.B.

**Branch/worktree:** `codex/task-35c-ci-release-contract`; `.worktrees/task-35c-ci-release-contract`.

**Files:**
- Modify: `.gitlab-ci.yml` (protected release rules/stage only)
- Create: `scripts/verify_ci_contract.py`
- Create: `tests/unit/process/test_ci_release_rules.py`
- Create: `tests/unit/process/test_ci_secret_boundaries.py`

**Interfaces:** Produces `verify_ci_contract(github_path: Path, gitlab_path: Path) -> DualCIContractResultV1`, the complete event matrix, protected credential boundary, three-way source-commit precondition, and categorized platform evidence for Task 36.A.

**Intentionally failing test:**

```python
def test_unprotected_tag_cannot_enter_release_stage(
    dual_ci_contract: DualCIContractResultV1,
) -> None:
    assert dual_ci_contract.gitlab.runs_release(tag="v1.0.0", protected=False) is False
```

**Implementation boundary:** This child validates release ordering but does not create a GitHub Release, push GHCR, or deploy Render. Missing/failed external runs leave it incomplete.

**Verification:**
- Target: `python -m pytest -q tests/unit/process/test_ci_release_rules.py::test_unprotected_tag_cannot_enter_release_stage`
- Domain: `python -m pytest -q tests/unit/process/test_github_actions_contract.py tests/unit/process/test_gitlab_ci_contract.py tests/unit/process/test_ci_release_rules.py tests/unit/process/test_ci_secret_boundaries.py`
- Contract: `python scripts/verify_ci_contract.py .github/workflows/ci.yml .gitlab-ci.yml`
- Real: require passing GitHub and GitLab main/source-commit job sets and record their URLs/ids.
- Expected: protected release ordering, three-way commit precheck, secret scoping, event matrix and real evidence pass.

**Completion evidence:** Not yet executed.

#### Task 36.A: Closed Delivery Evidence and Commit/Digest Alignment

**Status:** Not started

**Goal:** Define closed non-secret CI/release/deployment evidence schemas and reject any source-commit, wheel, manifest, or platform-state misalignment before external publication.

**SPEC references:** Milestone 36 evidence-schema, identity, and verifier requirements.

**Dependencies:** Task 35.C.

**Blocks:** Tasks 36.B, 36.C, and 37.B.

**Parallelization:** Sequential after Task 35.C.

**Branch/worktree:** `codex/task-36a-delivery-evidence`; `.worktrees/task-36a-delivery-evidence`.

**Files:**
- Create: `src/vespercode/delivery/evidence.py`
- Create: `delivery/evidence/README.md`
- Create: `delivery/evidence/ci-v1.json` from real Task 35.C evidence
- Create: `scripts/verify_release_evidence.py`
- Create: `tests/smoke/release/test_evidence_schema.py`
- Create: `tests/smoke/release/test_commit_alignment.py`

**Interfaces:** Produces `CIReleaseEvidenceV1`, `ReleaseEvidenceV1`, `DeploymentEvidenceV1`, and `load_and_verify_release_evidence(root, require_live)`.

**Intentionally failing test:**

```python
def test_release_evidence_rejects_commit_misalignment(
    valid_release_evidence: dict[str, object],
) -> None:
    valid_release_evidence["github_tag_commit"] = "0" * 40
    with pytest.raises(ValidationError):
        ReleaseEvidenceV1.model_validate(valid_release_evidence)
```

**Implementation boundary:** Unknown fields and invented/planned/non-terminal external results are rejected. Evidence stores only non-secret ids, URLs, commits, digests, timestamps, environment categories, and outcomes.

**Verification:**
- Target: `python -m pytest -q -o addopts='' -m deployment_smoke tests/smoke/release/test_commit_alignment.py::test_release_evidence_rejects_commit_misalignment`
- Domain: `python -m pytest -q -o addopts='' -m deployment_smoke tests/smoke/release/test_evidence_schema.py tests/smoke/release/test_commit_alignment.py`
- Expected: closed schemas and exact identity alignment reject every missing/mismatched/non-terminal case.

**Completion evidence:** Not yet executed.

#### Task 36.B: GitHub Release and GHCR Content-addressed Publication

**Status:** Not started

**Goal:** Execute one protected source-aligned release that publishes the exact wheel/checksum and Task 2 reference manifest, then re-download/re-pull and verify both artifacts.

**SPEC references:** Milestone 36 GitHub Release/GHCR/credential/digest continuity requirements.

**Dependencies:** Tasks 2.G, 33.A, 34.A, 35.C, and 36.A.

**Non-task entry gates:** The terminal Task 2.G outcome is `GO`, and the source-commit CI result passes.

**Blocks:** Tasks 36.C, 37.A, and 37.B.

**Parallelization:** Sequential after Tasks 2.G, 33.A, 34.A, 35.C, and 36.A; this is a protected external operation.

**Branch/worktree:** `codex/task-36b-github-ghcr-release`; `.worktrees/task-36b-github-ghcr-release`.

**Files:**
- Create: `delivery/evidence/release-v1.json` only from confirmed external results
- Create: `tests/smoke/release/test_manifest_image_alignment.py`

**Interfaces:** Produces a real GitHub Release URL, released wheel/checksum identities, `ghcr.io/ledstevenovo/vespercode-reference@sha256:{manifest_digest}`, digest re-pull/smoke evidence, and closed `ReleaseEvidenceV1`.

**Intentionally failing test:**

```python
def test_release_rejects_ghcr_digest_different_from_frozen_manifest(
    release_evidence: ReleaseEvidenceV1,
) -> None:
    assert release_evidence.ghcr_repo_digest == release_evidence.reference_manifest_digest
```

**Implementation boundary:** Human-provided protected least-privilege credentials stay in platform secret stores. A registry transformation, missing lookup, digest mismatch, or failed smoke aborts; it never rewrites the manifest.

**Verification:**
- Target: `python -m pytest -q -o addopts='' -m deployment_smoke tests/smoke/release/test_manifest_image_alignment.py::test_release_rejects_ghcr_digest_different_from_frozen_manifest`
- Domain: `python -m pytest -q -o addopts='' -m deployment_smoke tests/smoke/release/test_manifest_image_alignment.py`
- External: run the protected tag pipeline; download/re-hash/clean-install the wheel; pull GHCR by RepoDigest and smoke it.
- Evidence: `python scripts/verify_release_evidence.py delivery/evidence`
- Expected: Task 2 loopback, Task 34 reproduction, built-in manifest, GHCR response, and pulled-image manifest digests are identical; released wheel hash/install pass.

**Completion evidence:** Not yet executed.

#### Task 36.C: Render Deployment and Live Public Demo Evidence

**Status:** Not started

**Goal:** Deploy the exact capability-isolated Demo image/config to Render and freeze verified public health, scenario, isolation, and source-commit evidence.

**SPEC references:** Milestone 36 Render/live Demo requirements.

**Dependencies:** Tasks 34.B, 35.C, 36.A, and 36.B.

**Blocks:** Tasks 37.A and 37.B.

**Parallelization:** Sequential after Tasks 34.B, 35.C, 36.A, and 36.B; the release identity must freeze the source commit.

**Branch/worktree:** `codex/task-36c-render-deploy`; `.worktrees/task-36c-render-deploy`.

**Files:**
- Create: `render.yaml`
- Create: `delivery/evidence/deployment-v1.json` only from a confirmed Render deployment
- Create: `tests/smoke/release/test_render_contract.py`
- Create: `tests/smoke/release/test_public_demo_smoke.py`

**Interfaces:** Produces a real Render public URL, deployment id/source commit/image digest, `/healthz`, fixed scenario, session isolation, capability-absence evidence, and closed `DeploymentEvidenceV1`.

**Intentionally failing test:**

```python
def test_render_contract_has_no_disk_or_real_provider_secret(
    render_contract: RenderContractV1,
) -> None:
    assert render_contract.persistent_disks == ()
    assert render_contract.secret_names == ()
```

**Implementation boundary:** Use `containers/demo/Dockerfile`, platform PORT, `/healthz`, no disk/key/socket/repository credential, and no formal/local/recovery endpoints. Missing or failed live state leaves the task incomplete.

**Verification:**
- Target: `python -m pytest -q -o addopts='' -m deployment_smoke tests/smoke/release/test_render_contract.py::test_render_contract_has_no_disk_or_real_provider_secret`
- Domain: `python -m pytest -q -o addopts='' -m deployment_smoke tests/smoke/release/test_render_contract.py tests/smoke/release/test_public_demo_smoke.py`
- Live: `python scripts/verify_release_evidence.py delivery/evidence --require-live`
- Expected: real `/healthz`, fixed trace, simulation label, session isolation, cold-start facts, and capability absence pass.

**Completion evidence:** Not yet executed.

#### Task 37.A: Verified README

**Status:** Not started

**Goal:** Write an accurate user-facing README for installation, operation, security, recovery, distribution, CI/release/deployment, limitations, and non-goals using only verified current evidence.

**SPEC references:** Milestone 37 README and course documentation requirements.

**Dependencies:** Tasks 31.C, 32.C, 33.B, 34.A, 34.B, 35.C, 36.B, 36.C, and 38.G.

**Blocks:** Task 37.C.

**Parallelization:** May run in parallel with Task 37.B after Tasks 31.C, 32.C, 33.B, 34.A, 34.B, 35.C, 36.B, 36.C, and 38.G have completed.

**Branch/worktree:** `codex/task-37a-readme`; `.worktrees/task-37a-readme`.

**Files:**
- Create: `README.md`
- Create: `src/vespercode/delivery/readme_verifier.py`
- Create: `tests/unit/process/test_readme_contract.py`

**Interfaces:** Produces `verify_readme_contract(path: Path) -> ReadmeContractResultV1` plus the exact documented commands/URLs/digests and section contract enumerated by Milestone 37.

**Intentionally failing test:**

```python
def test_readme_fails_when_release_digest_verification_is_missing(
    repository_copy: Path,
) -> None:
    write_readme_without_section(repository_copy, "Reference image digest verification")
    result = verify_readme_contract(repository_copy / "README.md")
    assert "README_REFERENCE_DIGEST_INSTRUCTIONS_MISSING" in result.error_codes
```

**Implementation boundary:** No new capability, compatibility promise, exception, or invented external result may appear. Commands must match installed/package/live evidence.

**Verification:**
- Target: `python -m pytest -q tests/unit/process/test_readme_contract.py::test_readme_fails_when_release_digest_verification_is_missing`
- Domain: `python -m pytest -q tests/unit/process/test_readme_contract.py`
- Expected: all required sections, exact commands, real links/digests, threats/limitations/non-goals, and no overclaim pass.

**Completion evidence:** Not yet executed.

#### Task 37.B: Final Process and Agent Evidence Record

**Status:** Not started

**Goal:** Complete truthful append-preserving `SPEC_PROCESS.md` and `AGENT_LOG.md` records for M0, semantic approval, cold-start, every executable task, review, intervention, commit, PR, failure, and lesson.

**SPEC references:** Milestone 37 process/log evidence and course Superpowers-workflow requirements.

**Dependencies:** Tasks 1.A, 1.B, 1.C, 1.D, 1.E, 2.A, 2.B, 2.C, 2.D, 2.E, 2.F, 2.G, 3.A, 3.B, 3.C, 3.D, 3.E, 3.F, 3.G, 4.A, 4.F, 4.B, 4.C, 4.D, 4.E, 5.A, 5.B, 5.C, 5.D, 5.E, 6.A, 6.B, 6.C, 6.D, 6.E, 7.A, 7.B, 7.C, 7.D, 8.A, 8.B, 9.A, 9.B, 9.C, 9.D, 10.A, 10.B, 10.C, 11.A, 11.B, 12.A, 12.B, 12.C, 12.D, 13, 14.A, 14.B, 14.C, 15.A, 15.B, 15.C, 15.D, 15.E, 15.F, 16.A, 16.B, 17.A, 17.B, 17.C, 18.A, 18.B, 18.C, 18.D, 19.A, 19.B, 19.C, 20.A, 20.B, 21.A, 21.B, 21.C, 22.A, 22.B, 22.C, 23.A, 23.B, 23.C, 24.A, 24.B, 24.C, 25.A, 25.B, 25.C, 25.D, 25.E, 25.F, 25.G, 26.A, 26.B, 26.C, 27.A, 27.B, 28.A, 28.B, 29.A, 29.B, 29.C, 30.A, 30.B, 31.A, 31.B, 31.C, 32.A, 32.B, 32.C, 33.A, 33.B, 34.A, 34.B, 35.A, 35.B, 35.C, 36.A, 36.B, 36.C, 38.A, 38.B, 38.C, 38.D, 38.E, 38.F, and 38.G.

**Blocks:** Task 37.C.

**Parallelization:** May run in parallel with Task 37.A only after Tasks 1.A, 1.B, 1.C, 1.D, 1.E, 2.A, 2.B, 2.C, 2.D, 2.E, 2.F, 2.G, 3.A, 3.B, 3.C, 3.D, 3.E, 3.F, 3.G, 4.A, 4.F, 4.B, 4.C, 4.D, 4.E, 5.A, 5.B, 5.C, 5.D, 5.E, 6.A, 6.B, 6.C, 6.D, 6.E, 7.A, 7.B, 7.C, 7.D, 8.A, 8.B, 9.A, 9.B, 9.C, 9.D, 10.A, 10.B, 10.C, 11.A, 11.B, 12.A, 12.B, 12.C, 12.D, 13, 14.A, 14.B, 14.C, 15.A, 15.B, 15.C, 15.D, 15.E, 15.F, 16.A, 16.B, 17.A, 17.B, 17.C, 18.A, 18.B, 18.C, 18.D, 19.A, 19.B, 19.C, 20.A, 20.B, 21.A, 21.B, 21.C, 22.A, 22.B, 22.C, 23.A, 23.B, 23.C, 24.A, 24.B, 24.C, 25.A, 25.B, 25.C, 25.D, 25.E, 25.F, 25.G, 26.A, 26.B, 26.C, 27.A, 27.B, 28.A, 28.B, 29.A, 29.B, 29.C, 30.A, 30.B, 31.A, 31.B, 31.C, 32.A, 32.B, 32.C, 33.A, 33.B, 34.A, 34.B, 35.A, 35.B, 35.C, 36.A, 36.B, 36.C, 38.A, 38.B, 38.C, 38.D, 38.E, 38.F, and 38.G have completed and no predecessor is still writing evidence.

**Branch/worktree:** `codex/task-37b-process-evidence`; `.worktrees/task-37b-process-evidence`.

**Files:**
- Create: `src/vespercode/delivery/process_verifier.py`
- Read: `config/dependency-closure-v1.json`
- Read: `config/formal-toolchain-promotion-v1.json`
- Modify: `SPEC_PROCESS.md` (preserve history; add exact final evidence only)
- Modify: `AGENT_LOG.md` (append-only final chronology)
- Test: `tests/unit/process/test_delivery_evidence.py` (process-record cases)

**Interfaces:** Consumes the Task 1.E terminal `GO` `GateToolchainEvidenceV1`, `load_dependency_closure(root: Path) -> DependencyClosureV1`, and `load_formal_toolchain_promotion(root: Path) -> FormalToolchainPromotionV1` as strict read-only record inputs; produces `verify_process_evidence(root: Path) -> ProcessEvidenceResultV1` with stable missing/mismatch codes and no execution of repository code.

**Intentionally failing test:**

```python
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
```

**Implementation boundary:** Preserve historical failures/revisions; never fabricate approval, cold-start pass, subagent, review, commit, PR, human edit, or external outcome. Load the two unique JSON records as data without importing or executing repository code, require `dependency_closure.python_version == formal_toolchain_promotion.python_version == gate_evidence.python_version` by exact string comparison, and report stable missing/schema/identity errors. Validate the public compatibility range `>=3.12,<3.13` independently; range membership never replaces exact equality.

**Verification:**
- Target: `python -m pytest -q tests/unit/process/test_delivery_evidence.py::test_process_evidence_rejects_formal_python_identity_drift`
- Domain: `python -m pytest -q tests/unit/process/test_delivery_evidence.py`
- Expected: M0/PLAN identities, child task chronology, reviews and real repository SHAs/PRs reconcile exactly; both persistent records exist and parse; both records' `python_version` values equal Task 1.E terminal `GO` evidence character-for-character; a range-only match fails with `FORMAL_PYTHON_IDENTITY_MISMATCH`.

**Completion evidence:** Not yet executed.

#### Task 37.C: Delivery and Reflection Readiness Gate

**Status:** Not started

**Goal:** Aggregate every local/external/process/documentation check and report ready only with all 135 executable Tasks plus a valid student-authored reflection.

**SPEC references:** Milestone 37 delivery gate and reflection constraints.

**Dependencies:** Tasks 37.A and 37.B; a complete student-authored `REFLECTION.md` is a non-task entry gate.

**Blocks:** Final course delivery only.

**Parallelization:** Sequential after Tasks 37.A and 37.B; this is the final executable task.

**Branch/worktree:** `codex/task-37c-delivery-gate`; `.worktrees/task-37c-delivery-gate`.

**Files:**
- Create: `scripts/verify_delivery.py`
- Create: `scripts/verify_reflection.py`
- Create: `tests/unit/process/test_reflection_contract.py`
- Modify: `tests/unit/process/test_delivery_evidence.py` (aggregate readiness cases only)
- Modify: `PLAN.md` (final truthful statuses/evidence only)
- Modify: `REFLECTION.md` only after explicit language-polish request; student owns substantive text

**Interfaces:** Produces `verify_delivery(root: Path, require_live: bool) -> DeliveryReadinessResultV1` and `verify_reflection(path: Path) -> ReflectionContractResultV1`.

**Intentionally failing test:**

```python
def test_delivery_rejects_incomplete_executable_child(
    repository_copy: Path,
) -> None:
    mark_child_incomplete(repository_copy, "38.G")
    result = verify_delivery(repository_copy, require_live=False)
    assert "EXECUTABLE_TASK_INCOMPLETE:38.G" in result.error_codes
```

**Implementation boundary:** Parse real schemas/history/task records rather than success words. Reflection checks word count, disclosure, and student-specific structure but never generates or scores substantive personal content.

**Verification:**
- Target: `python -m pytest -q tests/unit/process/test_delivery_evidence.py::test_delivery_rejects_incomplete_executable_child`
- Domain: `python -m pytest -q tests/unit/process/test_readme_contract.py tests/unit/process/test_delivery_evidence.py tests/unit/process/test_reflection_contract.py`
- Delivery: `python scripts/verify_delivery.py --root . --require-live`
- Reflection: `python scripts/verify_reflection.py REFLECTION.md`
- Expected: readiness passes only when all 135 executable Tasks, reviews, environments, artifacts, live evidence, documents, and student reflection are current and valid.

**Completion evidence:** Not yet executed.

#### Task 38.A: Credential Lifecycle WebUI

**Status:** Not started

**Goal:** Expose hidden credential set/status/update/clear through Task 27 with no secret or derivative in any response, error, audit, log, or redisplay.

**SPEC references:** Milestone 38 credential WebUI requirements.

**Dependencies:** Tasks 27.B, 28.B, and 29.C.

**Blocks:** Tasks 37.B and 38.F.

**Parallelization:** Parallelizable with Tasks 38.B, 38.C, 38.D, and 38.E.

**Branch/worktree:** `codex/task-38a-credential-web`; `.worktrees/task-38a-credential-web`.

**Files:**
- Create: `src/vespercode/web/routes_credentials.py`
- Create: `src/vespercode/web/templates/credential_status.html`
- Test: `tests/web/test_credential_workflow.py`

**Interfaces:** Produces `CredentialWorkflowPortsV1` with exact methods `CredentialWorkflowPortsV1.set(provider: Literal["OPENAI"], secret: SecretCredentialV1, event_id: str) -> CredentialMutationResultV1`, `CredentialWorkflowPortsV1.status(provider: Literal["OPENAI"]) -> CredentialStatusV1`, `CredentialWorkflowPortsV1.update(provider: Literal["OPENAI"], secret: SecretCredentialV1, event_id: str) -> CredentialMutationResultV1`, and `CredentialWorkflowPortsV1.clear(provider: Literal["OPENAI"], event_id: str) -> CredentialMutationResultV1`, plus `CredentialRouteInstallerV1`.

**Intentionally failing test:**

```python
def test_credential_response_never_contains_secret_or_derivative(
    credential_client: TestClient,
) -> None:
    response = credential_client.post(
        "/credentials/openai", headers=valid_local_security_headers(), data={"secret": "inert-sentinel"}
    )
    assert "inert-sentinel" not in response.text
    assert "length" not in response.text and "digest" not in response.text
```

**Implementation boundary:** Secret exists only in the password-form service-call lifetime. Failed clear/update renders the service's real state and never claims false success.

**Verification:**
- Target: `python -m pytest -q tests/web/test_credential_workflow.py::test_credential_response_never_contains_secret_or_derivative`
- Domain: `python -m pytest -q tests/web/test_credential_workflow.py`
- Expected: security/idempotency, secret lifetime, status fields, failure projection, escaping, labels/focus/errors, and sentinel absence pass.

**Completion evidence:** Not yet executed.

#### Task 38.B: Workspace Memory WebUI

**Status:** Not started

**Goal:** Expose authorized workspace-scoped memory list/create/confirm/clear operations without cross-workspace selection or policy/control mutation.

**SPEC references:** Milestone 38 memory WebUI requirements.

**Dependencies:** Tasks 22.C, 23.C, 28.B, and 29.C.

**Blocks:** Tasks 37.B and 38.F.

**Parallelization:** Parallelizable with Tasks 38.A, 38.C, 38.D, and 38.E.

**Branch/worktree:** `codex/task-38b-memory-web`; `.worktrees/task-38b-memory-web`.

**Files:**
- Create: `src/vespercode/web/routes_memory.py`
- Create: `src/vespercode/web/templates/memory.html`
- Create: `tests/web/test_memory_workflow.py`

**Interfaces:** Produces `MemoryWorkflowPortsV1` with exact methods `MemoryWorkflowPortsV1.list(run_id: str) -> tuple[MemoryEntryV1, ...]`, `MemoryWorkflowPortsV1.create(command: CreateMemoryForRunV1) -> MemoryMutationResultV1`, `MemoryWorkflowPortsV1.confirm(command: ConfirmMemoryForRunV1) -> MemoryMutationResultV1`, and `MemoryWorkflowPortsV1.clear(command: ClearMemoryForRunV1) -> MemoryMutationResultV1`, plus `MemoryRouteInstallerV1`; route commands contain Run id and operation-visible fields but no client-selected workspace identity.

**Intentionally failing test:**

```python
def test_memory_form_cannot_select_foreign_workspace(
    memory_client: TestClient,
    memory_ports: SpyMemoryPorts,
) -> None:
    response = memory_client.post(
        "/runs/run-1/memory", headers=valid_local_security_headers(),
        data=valid_memory_form() | {"workspace_id": "foreign"},
    )
    assert response.status_code == 422
    assert memory_ports.create_call_count == 0
```

**Implementation boundary:** Only user-authored `PROJECT_CONVENTION` follows create→confirm; no generic model write or field affecting policy/Manifest/approval/disclosure/config/success is accepted.

**Verification:**
- Target: `python -m pytest -q tests/web/test_memory_workflow.py::test_memory_form_cannot_select_foreign_workspace`
- Domain: `python -m pytest -q tests/web/test_memory_workflow.py`
- Expected: server-derived scope, creator/source display, stale/foreign/duplicate no-mutation, clear binding, escaping and accessibility pass.

**Completion evidence:** Not yet executed.

#### Task 38.C: Redacted Audit WebUI

**Status:** Not started

**Goal:** Render monotonic paged redacted audit projections and permit explicit clear only for an ended Run without unresolved recovery evidence.

**SPEC references:** Milestone 38 audit WebUI requirements.

**Dependencies:** Tasks 23.C, 28.B, and 29.C.

**Blocks:** Tasks 37.B and 38.F.

**Parallelization:** Parallelizable with Tasks 38.A, 38.B, 38.D, and 38.E.

**Branch/worktree:** `codex/task-38c-audit-web`; `.worktrees/task-38c-audit-web`.

**Files:**
- Create: `src/vespercode/web/routes_audit.py`
- Create: `src/vespercode/web/templates/audit.html`
- Create: `tests/web/test_audit_workflow.py`

**Interfaces:** Produces `AuditWorkflowPortsV1` with exact methods `AuditWorkflowPortsV1.list_run(run_id: str, page: AuditPageRequestV1) -> AuditPageV1` and `AuditWorkflowPortsV1.clear_ended_run(command: ClearEndedRunAuditV1) -> AuditClearResultV1`, plus `AuditRouteInstallerV1` using Task 23.B closed page projection and Task 23.C clear command.

**Intentionally failing test:**

```python
def test_audit_page_contains_only_redacted_projection(
    audit_client: TestClient,
) -> None:
    response = audit_client.get("/runs/run-1/audit", headers=valid_local_security_headers())
    assert "raw-request-sentinel" not in response.text
    assert "backup-body-sentinel" not in response.text
```

**Implementation boundary:** Routes never read internal DB fields or full file/request/response/credential/backup bodies. Active/foreign/stale/unsafe clear requests make zero delete calls.

**Verification:**
- Target: `python -m pytest -q tests/web/test_audit_workflow.py::test_audit_page_contains_only_redacted_projection`
- Domain: `python -m pytest -q tests/web/test_audit_workflow.py`
- Expected: ordering/pagination/redaction, ended-run confirmation, recovery preservation, security and accessibility pass.

**Completion evidence:** Not yet executed.

#### Task 38.D: Read-only-first Recovery WebUI

**Status:** Not started

**Goal:** Render Task 26.B preview with zero writes and allow only a separately confirmed, currently bound Task 26.C apply command without bypass controls.

**SPEC references:** Milestone 38 recovery WebUI requirements.

**Dependencies:** Tasks 9.D, 23.C, 26.C, 28.B, and 29.C.

**Blocks:** Tasks 37.B and 38.F.

**Parallelization:** Parallelizable with Tasks 38.A, 38.B, 38.C, and 38.E.

**Branch/worktree:** `codex/task-38d-recovery-web`; `.worktrees/task-38d-recovery-web`.

**Files:**
- Create: `src/vespercode/web/routes_recovery.py`
- Create: `src/vespercode/web/templates/recovery_preview.html`
- Test: `tests/web/test_recovery_workflow.py`

**Interfaces:** Produces `RecoveryWorkflowPortsV1` with exact methods `RecoveryWorkflowPortsV1.preview(run_id: str) -> RecoveryPreviewV1` and `RecoveryWorkflowPortsV1.apply(command: ApplyRecoveryForRunV1) -> RecoveryResultV1`, `render_recovery_preview(preview: RecoveryPreviewV1) -> HTMLResponse`, and `RecoveryRouteInstallerV1`; apply accepts only `run_id`, `transaction_id`, `preview_digest`, confirmation, and event id.

**Intentionally failing test:**

```python
def test_recovery_preview_is_read_only_and_has_no_force_control(
    local_web_client: TestClient,
    operations_ports: SpyLocalOperationsPorts,
) -> None:
    response = local_web_client.get("/runs/run-recovery/recovery", headers=valid_local_security_headers())
    assert operations_ports.recovery_apply_call_count == operations_ports.workspace_write_count == 0
    assert 'name="force"' not in response.text and 'name="ignore"' not in response.text
```

**Implementation boundary:** No force/ignore/skip/edit/abandon control. Only service-proven terminal results unblock; stale preview/exception/partial result never renders success.

**Verification:**
- Target: `python -m pytest -q tests/web/test_recovery_workflow.py::test_recovery_preview_is_read_only_and_has_no_force_control`
- Domain: `python -m pytest -q tests/web/test_recovery_workflow.py`
- Expected: full path/status/consequence preview, exact explicit apply, zero preview write, stable unresolved blocking, security and accessibility pass.

**Completion evidence:** Not yet executed.

#### Task 38.E: Recovery CLI

**Status:** Not started

**Goal:** Add injectable typed parsing/delegation for `vespercode recover --workspace PATH` as read-only preview and require the literal `--apply` switch for the only recovery mutation path, without owning production database or service wiring.

**SPEC references:** Milestone 38 recovery CLI requirements.

**Dependencies:** Tasks 9.D, 26.C, and 28.B.

**Blocks:** Tasks 37.B and 38.F.

**Parallelization:** Parallelizable with Tasks 38.A, 38.B, 38.C, and 38.D.

**Branch/worktree:** `codex/task-38e-recovery-cli`; `.worktrees/task-38e-recovery-cli`.

**Files:**
- Modify: `src/vespercode/cli.py` (recover command only)
- Create: `tests/unit/test_recovery_cli.py`

**Interfaces:** Produces exact preview/apply CLI parsing and `install_recover_command(app, recovery_handler: RecoveryCliHandlerV1) -> None`; unit tests inject `SpyRecoveryService`, while the handler delegates after Task 9.D identity/lease resolution to Task 26.C services.

**Intentionally failing test:**

```python
def test_recover_without_apply_never_writes(
    cli_runner: CliRunner,
    recovery_service: SpyRecoveryService,
) -> None:
    result = cli_runner.invoke(app, ["recover", "--workspace", "C:\\repo"])
    assert result.exit_code == 0
    assert recovery_service.preview_call_count == 1
    assert recovery_service.apply_call_count == 0
```

**Implementation boundary:** This child owns only the recover command parser, closed arguments, typed delegation, help/error projection, and injection seam. It opens no control database, applies no migration, constructs no repository or production `RecoveryService`, and provides no production default handler; Task 38.F alone owns that binding. No transaction edit, disposition override, force/ignore, credential, secret, or recovery-body CLI argument exists.

**Verification:**
- Target: `python -m pytest -q tests/unit/test_recovery_cli.py::test_recover_without_apply_never_writes`
- Domain: `python -m pytest -q tests/unit/test_recovery_cli.py tests/unit/test_cli.py`
- Expected: default preview zero-write, literal apply requirement, safe errors, help text, closed argument surface, and injection through `SpyRecoveryService` pass without opening SQLite or importing Task 7.D.

**Completion evidence:** Not yet executed.

#### Task 38.F: Final Local Operations and Production Route Composition

**Status:** Not started

**Goal:** Install Credential, Memory, Audit, and Recovery routes through typed ports, freeze the sole production installer tuple after Run/Governance routes, and own the sole installed recovery-CLI handler/service binding after complete v1 database initialization.

**SPEC references:** Milestone 38 composition and package-reachability requirements.

**Dependencies:** Tasks 7.D, 29.C, 38.A, 38.B, 38.C, 38.D, and 38.E.

**Blocks:** Tasks 31.A, 33.A, 37.B, and 38.G.

**Parallelization:** Sequential after Tasks 7.D, 29.C, 38.A, 38.B, 38.C, 38.D, and 38.E.

**Branch/worktree:** `codex/task-38f-local-composition`; `.worktrees/task-38f-local-composition`.

**Files:**
- Create: `src/vespercode/web/routes_operations.py`
- Create: `src/vespercode/web/local_composition.py`
- Create: `src/vespercode/cli_composition.py`
- Modify: `src/vespercode/cli.py` (production recover-handler binding only, authorized by Task 28.B after Task 38.E freezes parsing)
- Test: `tests/web/test_local_composition.py`
- Test: `tests/unit/test_cli_composition.py`

**Interfaces:** Consumes Task 7.D `ALL_V1_MIGRATIONS`, Task 7.A `apply_migrations`, Task 38.E `install_recover_command`, and the existing Task 26.C recovery-service contract through its Task 38.D/38.E dependency closure; produces `initialize_production_control_database(path: Path) -> ControlDatabase`, `build_production_recovery_cli_handler(db: ControlDatabase, workspace_service: WorkspaceServiceV1) -> RecoveryCliHandlerV1`, `bind_production_recover_command(app, database_path: Path, workspace_service: WorkspaceServiceV1) -> None`, `LocalOperationsWorkflowPortsV1(credentials: CredentialWorkflowPortsV1, memory: MemoryWorkflowPortsV1, audit: AuditWorkflowPortsV1, recovery: RecoveryWorkflowPortsV1)`, `LocalOperationsRouteInstallerV1(ports: LocalOperationsWorkflowPortsV1).install(app: FastAPI) -> None`, `ProductionLocalWorkflowPortsV1(shell: LocalShellPortsV1, governance: RunGovernanceWorkflowPortsV1, operations: LocalOperationsWorkflowPortsV1)`, `build_local_route_installers(ports: ProductionLocalWorkflowPortsV1) -> LocalRouteInstallerSequenceV1`, and `build_local_application(ports: ProductionLocalWorkflowPortsV1, security: LocalWebSecurityConfigV1) -> FastAPI`.

**Intentionally failing test:**

```python
def test_production_installer_tuple_has_exact_order(
    production_ports: ProductionLocalWorkflowPortsV1,
) -> None:
    installers = build_local_route_installers(production_ports)
    assert tuple(type(item).__name__ for item in installers) == (
        "RunGovernanceRouteInstallerV1", "LocalOperationsRouteInstallerV1"
    )


@pytest.mark.parametrize(
    ("arguments", "terminal_event"),
    (
        (("recover", "--workspace", "C:\\repo"), "preview"),
        (("recover", "--workspace", "C:\\repo", "--apply"), "apply"),
    ),
)
def test_installed_recover_binds_complete_database_before_handler(
    installed_cli_runner: InstalledCliRunner,
    production_recovery_probe: ProductionRecoveryProbe,
    arguments: tuple[str, ...],
    terminal_event: str,
) -> None:
    result = installed_cli_runner.invoke(arguments)
    assert result.exit_code == 0
    assert production_recovery_probe.applied_migrations == ALL_V1_MIGRATIONS
    assert production_recovery_probe.events == (
        "apply_complete_registry",
        "construct_recovery_service",
        terminal_event,
    )
```

The installed CLI fixture resolves the configured `vespercode` console entry point and cannot call a source-only helper directly. Expected RED: `cli_composition.py` and its production binding do not exist, so installed preview/apply cannot prove registry-before-service ordering even though Task 38.E's Spy unit test remains independently executable.

**Implementation boundary:** The only permitted storage composition is `apply_migrations(db, ALL_V1_MIGRATIONS)` before constructing any typed repository/service port. This task owns one final local production-composition behavior across Web and CLI entry points: `local_composition.py` wires routes and `cli_composition.py` wires only the Task 38.E recover parser to the same initialized repository/service graph. Its authorized `cli.py` edit selects that production handler only; it cannot change command syntax, help/errors, preview/apply branching, or any other CLI feature. This task may import the Task 7.A engine and Task 7.D registry only for composition; it contains no DDL, migration reordering, parser copy, recovery predicate, service locator, untyped registry, duplicate domain behavior, other SQLite internals, or alternate package-smoke composition.

**Verification:**
- Target: `python -m pytest -q tests/web/test_local_composition.py::test_production_installer_tuple_has_exact_order`
- CLI production: `python -m pytest -q tests/unit/test_cli_composition.py::test_installed_recover_binds_complete_database_before_handler`
- Domain: `python -m pytest -q tests/web/test_local_composition.py tests/web/test_credential_workflow.py tests/web/test_memory_workflow.py tests/web/test_audit_workflow.py tests/web/test_recovery_workflow.py tests/unit/test_recovery_cli.py tests/unit/test_cli_composition.py`
- Registry: `python -m pytest -q tests/unit/storage/test_migration_registry.py tests/web/test_local_composition.py tests/unit/test_cli_composition.py`
- Expected: all four commands exit `0`; the complete registry applies before Web port or CLI recovery-service construction; exact route order and all typed ports/routes are reachable; installed recover preview/apply use the sole production handler; Task 38.E's Spy tests remain database-independent; and `vespercode serve`/`recover` use only the declared production compositions.

**Completion evidence:** Not yet executed.

#### Task 38.G: Cross-workflow Browser and Accessibility Acceptance

**Status:** Not started

**Goal:** Verify the merged local application end to end with keyboard navigation while preserving each child workflow's security, privacy, scoping, and no-bypass invariants.

**SPEC references:** Milestone 38 browser, security, usability, and accessibility acceptance requirements.

**Dependencies:** Task 38.F.

**Blocks:** Tasks 31.C, 33.B, 37.A, and 37.B.

**Parallelization:** Sequential after Task 38.F; no additional scheduling predecessor.

**Branch/worktree:** `codex/task-38g-operations-acceptance`; `.worktrees/task-38g-operations-acceptance`.

**Files:**
- Create: `tests/web/test_operations_accessibility.py`

**Interfaces:** Produces browser captures and a bounded acceptance report for credential, memory, audit, and recovery flows through the production application; adds no production interface.

**Intentionally failing test:**

```python
def test_every_operations_form_has_label_focus_and_live_error_region(
    rendered_operations_pages: tuple[str, ...],
) -> None:
    for page in rendered_operations_pages:
        assert_accessible_form_contract(page)
```

**Implementation boundary:** This child may fix only integration/accessibility defects in the owning child via that child's repair/re-review process; it cannot hide missing behavior in a broad browser test.

**Verification:**
- Target: `python -m pytest -q tests/web/test_operations_accessibility.py::test_every_operations_form_has_label_focus_and_live_error_region`
- Domain: `python -m pytest -q tests/web`
- Browser: exercise credential set/status/update/clear, memory create/confirm/view/clear, paged audit/ended-run clear, and recovery preview→explicit apply using production composition and keyboard only.
- Expected: no secret/body leakage, cross-workspace access, recovery bypass, inaccessible focus/error/status, or alternate composition remains.

**Completion evidence:** Not yet executed.

## Task Dependency DAG

Milestone ids remain stable traceability containers, but only retained integer Task 13 and the 134 dotted child Tasks are executable. The direct dependency table below is the sole machine-readable edge set.

The `Task predecessors` column contains only exact executable Task ids separated by commas; `—` means no task predecessor. Human approvals, GO outcomes, identity checks, reflection authorship, and real-platform results remain non-task gates in the executable Task block.

| Executable task | Task predecessors | Required predecessor output or non-task gate |
|---|---|---|
| 1.A | — | M0 PASS, human approval of the exact SPEC/PLAN semantic contract, and heterogeneous cold-start PASS. |
| 1.B | 1.A | Frozen hash-locked gate runner and configuration identities. |
| 1.C | 1.A, 1.B | Gate runner plus pure workspace-boundary evaluator. |
| 1.D | 1.A, 1.B | Gate runner plus pure workspace-mutex evaluator. |
| 1.E | 1.A, 1.B, 1.C, 1.D | Complete Task 1 observations, evaluators, and frozen toolchain identity; GO is required. |
| 2.A | 1.E | Task 1 GO and frozen bootstrap identity. |
| 2.B | 1.A, 2.A | Gate runner plus exact reference fixture/manifest bytes. |
| 2.C | 1.A, 2.B | Gate runner plus frozen reference build inputs. |
| 2.D | 1.A, 2.B | Gate runner plus frozen reporter and fingerprint probe contracts. |
| 2.E | 1.A, 2.D | Gate runner plus authoritative pytest evidence contract. |
| 2.F | 1.A, 2.E | Gate runner plus stable normalized fingerprint inputs. |
| 2.G | 1.E, 2.A, 2.B, 2.C, 2.D, 2.E, 2.F | Complete Task 2 build, registry, isolation, pytest, and fingerprint evidence; GO is required. |
| 3.A | 2.G | Task 2 GO and unchanged gate-bootstrap identity. |
| 3.B | 3.A | Closed persistence fault vocabulary and deterministic fault port. |
| 3.C | 3.A, 3.B | Gate persistence protocol plus injected fault observations. |
| 3.D | 1.B, 3.A, 3.B | Workspace evaluator, persistence protocol, and fault vocabulary. |
| 3.E | 3.C, 3.D | Exact transaction protocol and final-object persistence observations. |
| 3.F | 1.D, 3.E | Mutex evaluator plus persisted transaction observations. |
| 3.G | 1.E, 2.G, 3.A, 3.B, 3.C, 3.D, 3.E, 3.F | Complete Task 3 fault matrix and recovery evidence; GO is required. |
| 4.A | 1.E, 2.G, 3.G | All three feasibility gates GO with unchanged bootstrap identity and the complete declared v1 dependency set. |
| 4.F | 1.E, 2.G, 3.G, 4.A | Complete reviewed dependency closure plus exact terminal gate identities and GO evidence. |
| 4.B | 4.F | Complete v1 dependency closure and frozen formal toolchain promotion. |
| 4.C | 4.B | Canonical JSON and digest contracts. |
| 4.D | 4.C | Canonical timestamp and clock contracts. |
| 4.E | 4.D | Canonical lexical path contract. |
| 5.A | 4.F | Complete v1 dependency closure and frozen formal toolchain promotion. |
| 5.B | 4.C, 5.A | Canonical time plus location/run identities. |
| 5.C | 4.B, 5.A, 5.B | Canonical digest plus shared action/policy identities. |
| 5.D | 4.B, 5.A, 5.B, 5.C, 5.E | Complete closed shared contract set. |
| 5.E | 4.E | Canonical repository-location and disclosure-scope contracts. |
| 6.A | 4.D, 5.D | Canonical time plus closed shared contracts. |
| 6.B | 2.G, 4.B, 5.D | Task 2 reference evidence, canonical identity, and shared contracts. |
| 6.C | 4.B, 5.D | Canonical identity plus shared endpoint/profile contracts. |
| 6.D | 5.E, 6.C | Location contracts plus endpoint/profile schemas. |
| 6.E | 6.A, 6.B, 6.C, 6.D | Complete validated built-in profile registry and immutable digests. |
| 7.A | 5.D | Shared storage and transaction identities. |
| 7.B | 7.A | Domain-independent migration engine plus transactional connection contract. |
| 7.C | 7.B | Transactional Run/wait lifecycle plus immutable v0001 migration. |
| 7.D | 7.B, 7.C, 14.B, 15.D, 15.E, 22.A, 23.A, 24.C, 25.B, 25.D, 26.A, 26.C | Exact twelve domain migration constants; sole complete `ALL_V1_MIGRATIONS` composition. |
| 8.A | 6.E, 7.C | Frozen profiles and complete Run storage/lifecycle contracts. |
| 8.B | 8.A | Frozen `RunRequestV1` and request/config digests. |
| 9.A | 1.E, 5.D, 7.C, 8.B | Task 1 GO plus admitted Run/storage contracts. |
| 9.B | 9.A | Handle-derived workspace/final-object identity. |
| 9.C | 9.B | Held cross-process workspace lease. |
| 9.D | 9.C | Sealed Git preflight evidence. |
| 10.A | 5.D, 9.D | Shared contracts and complete workspace/Git/path authorization boundary. |
| 10.B | 5.D | Shared content-object identities. |
| 10.C | 9.D, 10.A, 10.B | Immutable SnapshotTree, content objects, and supported-text classification. |
| 11.A | 5.D, 10.C | Shared action/result contracts and immutable Snapshot content. |
| 11.B | 11.A | Common file-action/result contracts and Read boundary. |
| 12.A | 6.E, 9.D, 10.C | Editable policy/profile, object/path guard, and Snapshot contracts. |
| 12.B | 12.A | Complete strict unified-diff parse contract. |
| 12.C | 12.B | Immutable CandidateTree overlay contract. |
| 12.D | 12.C | Atomic exact patch transaction contract. |
| 13 | 5.D, 6.E, 12.D | Shared policy/action identities, frozen policy/profile, and candidate/path facts. |
| 14.A | 7.C, 12.D, 13, 20.B, 21.C | Run state, exact candidate/policy, Manifest, and verified-candidate evidence. |
| 14.B | 4.C, 5.B, 7.B, 7.C, 14.A, 25.D | Canonical time, durable Run state, exact approval subject, and actual v0001–v0009 migration predecessors. |
| 14.C | 7.A, 7.C, 14.A, 14.B, 21.C | Transactional storage, one-time approval, and verified-candidate evidence. |
| 15.A | 4.B, 5.D | Canonical digest and shared disclosure identities. |
| 15.B | 4.D, 5.E, 15.A | Canonical time/location plus disclosure subject contract. |
| 15.C | 4.C, 6.C, 6.D, 15.A, 15.B | Endpoint/profile contracts and canonical disclosure bindings. |
| 15.D | 4.C, 5.B, 7.B, 7.C, 15.C | Canonical time, durable Run state, and disclosure authorization facts. |
| 15.E | 7.A, 7.C, 15.A, 15.B, 15.C, 15.D, 15.F | Complete transactional authorization ledger and disclosure grants. |
| 15.F | 7.A, 7.C, 15.C, 15.D | Exact active-Grant revocation service. |
| 16.A | 6.E, 15.E | Frozen LLM profiles and disclosure subjects/ledger. |
| 16.B | 15.E, 16.A, 27.B | Authorization, prepared-request/call-result contracts, and fresh secret wrapper. |
| 17.A | 5.C, 11.B, 12.A, 16.A | Closed shared actions, paged tools, strict diff parser, and common `ModelResponse`. |
| 17.B | 4.B, 5.C, 17.A | Canonical identity, shared actions, and closed action parser. |
| 17.C | 9.D, 11.B, 12.D, 13, 16.B, 17.B | Bound workspace/tools/candidate/policy/adapter facts and parsed actions. |
| 18.A | 2.G, 5.D, 6.E | Task 2 Docker GO plus shared/profile execution contracts. |
| 18.B | 4.E, 9.D, 10.C, 12.D, 18.A | Canonical path, authorized Snapshot/Candidate, and execution request. |
| 18.C | 2.G, 18.A, 18.B | Frozen image identity plus bounded execution inputs. |
| 18.D | 10.C, 12.D, 18.C | Complete production Docker execution boundary and immutable results. |
| 19.A | 4.E, 5.D, 6.E, 18.D | Canonical/shared/profile contracts and bounded Docker execution output. |
| 19.B | 19.A | Closed static-tool result contract. |
| 19.C | 19.B | Complete authoritative pytest evidence contract. |
| 20.A | 5.D, 6.E, 8.B, 10.C | Shared/profile/admission and single-Snapshot facts. |
| 20.B | 18.D, 19.C, 20.A | Docker executor, authoritative check evidence/fingerprints, and frozen check plan. |
| 21.A | 12.D, 19.C, 20.B | Candidate, authoritative check evidence, Baseline, and Manifest. |
| 21.B | 18.D, 21.A | Docker execution output plus formal validation predicate. |
| 21.C | 12.D, 19.C, 20.B, 21.A, 21.B | Complete formal validation and immutable `VerifiedCandidate`. |
| 22.A | 7.A, 7.C, 10.C, 15.E, 19.C | Storage, workspace Snapshot content, actual v0001–v0004 migrations, and validation redaction contracts. |
| 22.B | 10.C, 19.C, 22.A | Snapshot/check facts plus workspace-isolated memory repository. |
| 22.C | 7.A, 7.C, 22.A, 22.B | Complete authorized repository-memory lifecycle. |
| 23.A | 7.C, 22.A | Durable Run/event ordering plus actual v0001–v0005 migrations. |
| 23.B | 23.A | Redacted monotonic audit event repository. |
| 23.C | 23.B | Complete user-facing visibility projection. |
| 24.A | 4.C, 5.D, 11.B, 19.C | Canonical time, shared/tool, and validation-result contracts. |
| 24.B | 10.C, 15.E, 16.B, 22.B, 24.A | Snapshot, disclosure, adapter, memory, and context projection facts. |
| 24.C | 7.A, 7.C, 24.A, 24.B, 25.B | Complete structured feedback projection, durable context bindings, and actual v0007 turn schema. |
| 25.A | 5.D, 7.C, 14.C, 24.C | Limits/lifecycle, final-approval state, and structured feedback/progress facts. |
| 25.B | 7.C, 8.B, 23.A | Active Run, admitted immutable limits/deadline, and actual v0001–v0006 migrations. |
| 25.C | 15.E, 16.B, 25.B, 27.B | Grant/authorization, adapter, turn-boundary, and fresh credential contracts. |
| 25.D | 11.B, 12.D, 13, 17.C, 19.C, 24.C | Tools, candidate, policy, parser/dispatcher, validation result, and feedback contracts. |
| 25.E | 7.C, 14.C | Durable lifecycle and final approval/wait bindings. |
| 25.F | 7.C, 23.C | Durable active-run state and complete redacted audit services. |
| 25.G | 8.B, 17.C, 21.C, 24.C, 25.A, 25.B, 25.C, 25.D, 25.E, 25.F | Complete child loop contracts plus formal-validation transition. |
| 26.A | 3.G, 7.C, 9.D, 12.D, 14.C, 21.C, 23.C | Task 3 `GO`; lifecycle/lease/diff/approval/verified/audit contracts. |
| 26.B | 26.A | Durable transaction/path/artifact records produced by Task 26.A. |
| 26.C | 7.C, 9.D, 23.C, 26.B | Lifecycle/lease/audit plus bound recovery preview/classification. |
| 27.A | 4.E, 5.D, 6.E | Canonical/shared/endpoint contracts and locked dependency environment. |
| 27.B | 27.A | Pure closed credential service/store-port contract. |
| 28.A | 7.C, 8.B, 23.C, 27.B | Durable session/run facts, audit projection, and credential-service ports. |
| 28.B | 28.A | Frozen loopback/Host/Origin/session/CSRF/header boundary. |
| 29.A | 8.B, 23.C, 25.G, 28.B | Admission, visible audit state, complete loop service, and safe shell. |
| 29.B | 15.E, 16.B, 23.C, 28.B | Disclosure ledger/adapter result, audit projection, and safe shell. |
| 29.C | 14.C, 21.C, 26.A, 28.B, 29.A, 29.B | Approval/verification/writeback contracts and prior governance routes. |
| 30.A | 4.E, 5.D, 13, 17.C, 24.C, 25.A, 25.D | Canonical/shared contracts and real shared policy/parser/feedback/stop components. |
| 30.B | 30.A | Capability-isolated headless Demo core and Demo-only ports. |
| 31.A | 9.D, 10.C, 11.B, 12.D, 13, 14.C, 15.E, 16.B, 17.C, 18.D, 19.C, 20.B, 21.C, 22.C, 23.C, 24.C, 25.G, 26.A, 27.B, 28.B, 29.C, 38.F | Complete formal happy-path composition and exact reference profile. |
| 31.B | 11.B, 13, 14.C, 15.E, 16.B, 27.B, 31.A | Reusable E2E driver plus safety, authorization, and credential boundaries. |
| 31.C | 26.C, 31.A, 31.B, 38.G | Recovery service, reusable E2E trace, complete negative E2E driver, and accepted local operations composition. |
| 32.A | 12.D, 13, 17.C, 24.C, 25.A, 25.D, 30.A | Candidate/policy/action/feedback/stop contracts and shared-core Demo composition. |
| 32.B | 11.B, 19.C, 24.C, 32.A | Continuation/check evidence/feedback contracts plus mechanism driver. |
| 32.C | 15.E, 16.B, 27.B, 30.B, 32.A, 32.B | Disclosure/credential/call boundaries, public Demo, and complete mechanism traces. |
| 33.A | 26.C, 28.B, 29.C, 31.C, 32.C, 38.F | Complete runtime, local composition, E2E/mechanism closure, and package metadata readiness. |
| 33.B | 33.A, 38.G | Exact wheel/digest and browser-accepted installed workflows. |
| 34.A | 2.G, 18.D, 20.B, 31.C, 32.C | Task 2 `GO`, frozen OCI recipe/digest, execution/baseline, and final evidence. |
| 34.B | 30.B, 32.C | Public Demo app plus capability/reuse proof. |
| 35.A | 33.B, 34.A, 34.B | Passing package and both OCI smoke contracts. |
| 35.B | 33.B, 34.A, 34.B | Passing package and both OCI smoke contracts. |
| 35.C | 35.A, 35.B | Passing real GitHub workflow and GitLab pipeline results for the same source commit. |
| 36.A | 35.C | Protected dual-platform CI contract and categorized real evidence. |
| 36.B | 2.G, 33.A, 34.A, 35.C, 36.A | Task 2 frozen digest, wheel/image readiness, protected release rules, and closed evidence schema. |
| 36.C | 34.B, 35.C, 36.A, 36.B | Demo image, protected CI closure, closed evidence, and released source identity. |
| 37.A | 31.C, 32.C, 33.B, 34.A, 34.B, 35.C, 36.B, 36.C, 38.G | Stable verified commands, artifacts, URLs/digests, limitations, and browser evidence. |
| 37.B | 1.A, 1.B, 1.C, 1.D, 1.E, 2.A, 2.B, 2.C, 2.D, 2.E, 2.F, 2.G, 3.A, 3.B, 3.C, 3.D, 3.E, 3.F, 3.G, 4.A, 4.F, 4.B, 4.C, 4.D, 4.E, 5.A, 5.B, 5.C, 5.D, 5.E, 6.A, 6.B, 6.C, 6.D, 6.E, 7.A, 7.B, 7.C, 7.D, 8.A, 8.B, 9.A, 9.B, 9.C, 9.D, 10.A, 10.B, 10.C, 11.A, 11.B, 12.A, 12.B, 12.C, 12.D, 13, 14.A, 14.B, 14.C, 15.A, 15.B, 15.C, 15.D, 15.E, 15.F, 16.A, 16.B, 17.A, 17.B, 17.C, 18.A, 18.B, 18.C, 18.D, 19.A, 19.B, 19.C, 20.A, 20.B, 21.A, 21.B, 21.C, 22.A, 22.B, 22.C, 23.A, 23.B, 23.C, 24.A, 24.B, 24.C, 25.A, 25.B, 25.C, 25.D, 25.E, 25.F, 25.G, 26.A, 26.B, 26.C, 27.A, 27.B, 28.A, 28.B, 29.A, 29.B, 29.C, 30.A, 30.B, 31.A, 31.B, 31.C, 32.A, 32.B, 32.C, 33.A, 33.B, 34.A, 34.B, 35.A, 35.B, 35.C, 36.A, 36.B, 36.C, 38.A, 38.B, 38.C, 38.D, 38.E, 38.F, 38.G | Complete per-task process evidence through Task 36.C, the v1 migration registry, and all Task 38 children. |
| 37.C | 37.A, 37.B | Complete student-authored 1,500–2,500-word reflection and final human readiness decision. |
| 38.A | 27.B, 28.B, 29.C | Credential service, safe shell, and governance route composition. |
| 38.B | 22.C, 23.C, 28.B, 29.C | Memory/audit services, safe shell, and governance route composition. |
| 38.C | 23.C, 28.B, 29.C | Audit projection, safe shell, and governance route composition. |
| 38.D | 9.D, 23.C, 26.C, 28.B, 29.C | Workspace/audit/recovery service, safe shell, and governance route composition. |
| 38.E | 9.D, 26.C, 28.B | Workspace/recovery service and existing CLI shell. |
| 38.F | 7.D, 29.C, 38.A, 38.B, 38.C, 38.D, 38.E | Exact complete v1 migration registry, local workflow routers, and CLI operation contract. |
| 38.G | 38.F | Frozen production local composition; acceptance adds no production behavior. |

## Parallel Worktree Waves

M0, human approval, and cold-start are pre-wave gates, not executable Tasks. There are **70 executable dependency waves** numbered 1–70. The `Executable tasks` column is the sole machine-readable membership set and contains exact Task ids only. Every predecessor must be in an earlier wave; tasks in one row may run in parallel only when their expanded owned core-file sets are disjoint. Evidence merges remain serialized by displayed Task order.

| Wave | Executable tasks | Execution and conflict rule |
|---|---|---|
| 1 | 1.A | Freeze the hash-locked gate toolchain/config/runner after all pre-wave gates pass. |
| 2 | 1.B | Implement the pure workspace-boundary evaluator. |
| 3 | 1.C, 1.D | Run disjoint workspace-object and mutex observation producers. |
| 4 | 1.E | Assemble Task 1 evidence; GO is required before later waves. |
| 5 | 2.A | Freeze exact reference fixture and manifest bytes. |
| 6 | 2.B | Implement frozen reference image build inputs. |
| 7 | 2.C, 2.D | Build/registry and reporter/fingerprint contracts own disjoint files. |
| 8 | 2.E | Capture authoritative feasibility pytest evidence. |
| 9 | 2.F | Freeze normalized failure fingerprint inputs. |
| 10 | 2.G | Assemble Task 2 evidence; GO is required before later waves. |
| 11 | 3.A | Freeze the closed persistence gate protocol. |
| 12 | 3.B | Implement deterministic fault vocabulary and injection port. |
| 13 | 3.C, 3.D | Transaction and final-object observation producers own disjoint files. |
| 14 | 3.E | Implement fault-safe persistence transaction observations. |
| 15 | 3.F | Implement recovery classification and held-mutex proof. |
| 16 | 3.G | Assemble Task 3 evidence; GO is required before later waves. |
| 17 | 4.A | Freeze the complete reviewed v1 dependency closure and minimal package identity. |
| 18 | 4.F | Promote the frozen gate toolchain and configure the locked build backend without changing dependencies. |
| 19 | 4.B, 5.A | Canonical JSON/digests and optional values own disjoint files. |
| 20 | 4.C | Implement canonical time and injected clock. |
| 21 | 4.D, 5.B | Lexical paths and Run contracts own disjoint files. |
| 22 | 4.E, 5.C | Credential scan and shared action contracts own disjoint files. |
| 23 | 5.E | Freeze repository-location and disclosure-scope contracts. |
| 24 | 5.D | Complete the closed shared contract set. |
| 25 | 6.A, 6.B, 6.C, 7.A, 10.B, 15.A | Profile, storage, content, and disclosure foundations own disjoint files. |
| 26 | 6.D, 7.B, 15.B | Registry assembly, Run lifecycle, and disclosure subjects own disjoint files. |
| 27 | 6.E, 7.C, 15.C | Profile validation, idempotency, and authorization rules own disjoint files. |
| 28 | 8.A, 15.D, 18.A, 27.A | Request, Grant-decision/v0003, Docker-request, and credential-port files are disjoint. |
| 29 | 8.B, 15.F, 27.B | Admission, Grant revocation, and WinCred adapter files are disjoint. |
| 30 | 9.A, 15.E | Identity and authorization-ledger/v0004 files are disjoint. |
| 31 | 9.B, 16.A | Mutex and Mock-adapter files are disjoint. |
| 32 | 9.C, 16.B | Git preflight and OpenAI-transport files are disjoint. |
| 33 | 9.D | Complete path authorization before later Snapshot/candidate consumers. |
| 34 | 10.A | Implement Snapshot capture and content objects. |
| 35 | 10.C | Seal SnapshotTree and content-object identities. |
| 36 | 11.A, 12.A, 20.A | Read tools, diff parsing, and static support planning own disjoint files. |
| 37 | 11.B, 12.B | Paged discovery and CandidateTree overlays own disjoint files. |
| 38 | 12.C, 17.A | Atomic patch application and action parser own disjoint files. |
| 39 | 12.D, 17.B | FinalDiff identity and action binding own disjoint files. |
| 40 | 13, 18.B | Pure policy and Docker isolation inputs own disjoint files. |
| 41 | 17.C, 18.C | Dispatcher and container lifecycle own disjoint files. |
| 42 | 18.D | Seal production Docker execution results. |
| 43 | 19.A | Freeze closed static-tool result contracts. |
| 44 | 19.B | Implement authoritative pytest event evidence. |
| 45 | 19.C | Implement stable target failure fingerprints. |
| 46 | 20.B, 22.A, 24.A | Baseline/Manifest, memory repository, and context facts own disjoint files. |
| 47 | 21.A, 22.B, 23.A | Formal plan, memory selection, and audit/v0006 files are disjoint. |
| 48 | 21.B, 22.C, 23.B, 24.B, 25.B | Validation execution, memory clear, audit projection, context projection, and turn/v0007 files are disjoint. |
| 49 | 21.C, 23.C, 24.C, 25.C | VerifiedCandidate, audit retention, feedback/v0008, and call-orchestration files are disjoint. |
| 50 | 14.A, 25.D, 25.F, 28.A | Approval subject, action/v0009, restart, and Web-security files are disjoint. |
| 51 | 14.B, 28.B | Writeback-approval/v0010 and application-shell files are disjoint. |
| 52 | 14.C, 29.B | Approval consumption and disclosure-UI files are disjoint. |
| 53 | 25.A, 25.E, 26.A | Stop/progress, wait/cancel, and writeback own disjoint files. |
| 54 | 25.G, 26.B, 30.A | Loop composition, recovery preview, and Demo core own disjoint files. |
| 55 | 26.C, 29.A, 30.B, 32.A | Recovery, Run UI, Demo app, and governance trace own disjoint files. |
| 56 | 7.D, 29.C, 32.B, 38.E | Final migration registry, governance composition, feedback trace, and recovery CLI own disjoint files. |
| 57 | 32.C, 38.A, 38.B, 38.C, 38.D | Shared-core proof and four local-operation workflows own disjoint files. |
| 58 | 34.B, 38.F | Demo OCI smoke and local route composition own disjoint files. |
| 59 | 31.A, 38.G | Reference happy path and browser acceptance consume frozen composition. |
| 60 | 31.B | Add reference negative safety/call-gate cases. |
| 61 | 31.C | Complete persistence/recovery/audit/determinism reference evidence. |
| 62 | 33.A, 34.A | Wheel build and reference image smoke own disjoint artifacts. |
| 63 | 33.B | Clean pipx smoke consumes the exact wheel. |
| 64 | 35.A, 35.B | GitHub Actions and GitLab verification proceed independently. |
| 65 | 35.C | Protected release rules and dual-platform evidence wait for both platforms. |
| 66 | 36.A | Freeze closed delivery evidence and identity alignment. |
| 67 | 36.B | Execute protected GitHub Release/GHCR publication. |
| 68 | 36.C | Deploy and verify the exact public Demo source commit. |
| 69 | 37.A, 37.B | README and final process/log evidence use stable producer facts and disjoint files. |
| 70 | 37.C | Final delivery/reflection gate waits for all executable Tasks and the student-authored reflection. |

Every executable task uses a fresh subagent, branch, worktree, and PR. Milestones use none. Parallel worktrees may not update shared execution evidence concurrently: implementation commits may proceed in parallel, but merges and append-only `PLAN.md`/`AGENT_LOG.md` evidence commits occur in displayed task order within the wave.

## Planned File Ownership Matrix

The mechanically checked core-file set is formed only from exact backticked repository paths in `Owned core files`; brace notation expands the comma-separated filenames inside one directory and is not a filesystem wildcard. `None (test/evidence-only)` declares that a Task owns no production/configuration core file; its exact supporting files remain frozen in that Task's `Files` block. A Task that modifies another Task's core file is named only under `Authorized subsequent modifiers`, never as a second primary owner. `PLAN.md` and `AGENT_LOG.md` are shared evidence files outside the parallel core-file set and may receive completion evidence only under the serialized merge rule.

| Primary task | Owned core files | Authorized subsequent modifiers | Serialization rule |
|---|---|---|---|
| 1.A | `requirements/gate.lock`; `gates/{pytest.ini,ruff.toml,mypy.ini}`; `scripts/run_gate_checks.py`; `tests/feasibility/gate/test_gate_bootstrap.py` | None | Gate bootstrap/config identity freezes before 1.B–1.E. |
| 1.B | `spikes/win32_workspace_boundary/evaluator.py`; `tests/feasibility/windows/test_workspace_boundary_evaluator.py` | None | Pure evaluator only; no Win32 calls. |
| 1.C | `spikes/win32_workspace_boundary/object_probe.py`; `tests/feasibility/windows/test_workspace_object_probe.py` | None | Workspace object observation only. |
| 1.D | `spikes/win32_workspace_boundary/mutex_probe.py`; `tests/feasibility/windows/test_workspace_mutex_probe.py` | None | Workspace mutex observation only. |
| 1.E | `spikes/win32_workspace_boundary/{report.py,probe.py}`; `tests/feasibility/windows/test_workspace_boundary_gate.py` | None | Assembles immutable evidence; later tasks verify identities and never rewrite Milestone 1 files. |
| 2.A | `requirements/reference.lock`; `reference/fixture/{pyproject.toml,requirements.lock,src/vesper_fixture/calculator.py,tests/test_calculator.py}`; `spikes/docker_reference_boundary/input_contract.py`; `tests/feasibility/docker/test_reference_input_contract.py` | None | Freezes exact reference inputs before image work. |
| 2.B | `containers/reference/Dockerfile`; `spikes/docker_reference_boundary/image_builder.py`; `tests/feasibility/docker/test_reference_image_reproducibility.py` | None | Owns deterministic reference-image build only. |
| 2.C | `spikes/docker_reference_boundary/registry_probe.py`; `tests/feasibility/docker/test_loopback_registry_probe.py` | None | Owns loopback registry proof and cleanup only. |
| 2.D | `spikes/docker_reference_boundary/execution_probe.py`; `tests/feasibility/docker/test_reference_container_isolation.py` | None | Owns closed container-isolation observations. |
| 2.E | `spikes/docker_reference_boundary/pytest_reporter.py`; `tests/feasibility/docker/test_gate_pytest_evidence.py` | None | Owns authoritative gate pytest evidence only. |
| 2.F | `spikes/docker_reference_boundary/failure_fingerprint_probe.py`; `tests/feasibility/docker/test_gate_failure_input_stability.py` | None | Owns normalized failure fingerprints only. |
| 2.G | `reference/manifest/reference-profile-v1.json`; `spikes/docker_reference_boundary/{probe.py,report.py}`; `tests/feasibility/docker/test_reference_boundary_gate.py` | Task 6.B synchronizes the validated manifest into package data | Task 34.A treats Milestone 2 inputs as read-only and reproduces the frozen digest; Task 36.B alone adds real GHCR evidence. |
| 3.A | `spikes/persistence_recovery/protocol.py`; `tests/feasibility/persistence/test_transaction_protocol.py` | None | Owns the closed gate transaction protocol. |
| 3.B | `spikes/persistence_recovery/faults.py`; `tests/feasibility/persistence/test_write_fault_matrix.py` | None | Owns deterministic fault injection only. |
| 3.C | `spikes/persistence_recovery/deadline.py`; `tests/feasibility/persistence/test_persistence_deadlines.py` | None | Owns deadline observations only. |
| 3.D | `spikes/persistence_recovery/observation.py`; `tests/feasibility/persistence/test_external_change_classifier.py` | None | Owns final-object/external-change observations only. |
| 3.E | `spikes/persistence_recovery/recovery_preview.py`; `tests/feasibility/persistence/test_recovery_preview.py` | None | Owns read-only recovery preview only. |
| 3.F | `spikes/persistence_recovery/recovery_apply.py`; `tests/feasibility/persistence/test_recovery_apply.py` | None | Owns guarded recovery apply only. |
| 3.G | `spikes/persistence_recovery/report.py`; `tests/feasibility/persistence/test_recovery_gate.py` | None | Gate evidence freezes before Task 4.A. |
| 4.A | `pyproject.toml`; `requirements/dev.lock`; `src/vespercode/__init__.py`; `src/vespercode/project/dependency_closure.py`; `config/dependency-closure-v1.json`; `scripts/bootstrap_formal_env.py` | Task 4.F changes only build-system and pytest/Ruff/Mypy/tooling sections of `pyproject.toml`; Task 33.A changes only package-data/version/distribution-metadata/console-entry-point sections of `pyproject.toml` | Sole dependency/Python/source-policy/lock/closure-record/formal-bootstrap owner; never modifies Milestone 1 gate files, and no later task changes dependency tables, Python range, dependency sources, `requirements/dev.lock`, the closure verifier/record, or bootstrap. |
| 4.F | `src/vespercode/project/toolchain_promotion.py`; `config/formal-toolchain-promotion-v1.json` | None | Sole promotion verifier/record owner; consumes Task 4.A's `.venv-formal` bootstrap and authorized `pyproject.toml` tooling-only modification without becoming a second owner of `pyproject.toml`, the bootstrap, or the dependency closure. |
| 4.B | `src/vespercode/canonical/{json_v1.py,digest.py}` | None | Owns canonical bytes and domain digest only. |
| 4.C | `src/vespercode/canonical/{timestamp_v1.py,clock.py}` | None | Owns time parsing/conversion and injected clocks only. |
| 4.D | `src/vespercode/canonical/path_v1.py` | None | Owns lexical path validation only. |
| 4.E | `scripts/scan_credentials.py` | None | Owns redacted changed-file scanning only. |
| 5.A | `src/vespercode/contracts/optional.py`; `tests/unit/contracts/test_optional.py` | None | Owns closed optional-value objects only. |
| 5.B | `src/vespercode/contracts/run.py`; `tests/unit/contracts/test_run.py` | None | Owns Run/lifecycle value objects only. |
| 5.C | `src/vespercode/contracts/action.py`; `tests/unit/contracts/test_action.py` | None | Owns action/policy value objects only. |
| 5.D | `src/vespercode/contracts/evidence.py`; `tests/unit/contracts/test_evidence.py` | None | Completes shared evidence contracts; duplicate declarations are review failures. |
| 5.E | `src/vespercode/contracts/location.py`; `tests/unit/contracts/test_location.py` | None | Owns repository-location and disclosure-scope value objects only. |
| 6.A | `src/vespercode/profiles/editable.py`; `tests/unit/profiles/test_editable.py` | None | Owns editable-policy parsing and digest only. |
| 6.B | `src/vespercode/profiles/reference.py`; `src/vespercode/profiles/builtin/reference-profile-v1.json`; `tests/unit/profiles/test_reference.py` | Task 2.G authorizes synchronization of `reference/manifest/reference-profile-v1.json` | Task 34.A reproduces the frozen image digest and revalidates these integrity vectors. |
| 6.C | `src/vespercode/profiles/llm.py`; `src/vespercode/profiles/builtin/{mock-deterministic-v1.json,openai-single-turn-v1.json}`; `tests/unit/profiles/test_llm.py` | None | Owns closed LLM profile schemas and built-ins. |
| 6.D | `src/vespercode/profiles/endpoints.py`; `tests/unit/profiles/test_endpoints.py` | None | Owns endpoint policy only. |
| 6.E | `src/vespercode/profiles/registry.py`; `tests/unit/profiles/test_registry.py` | None | Owns registry assembly and immutable profile-digest lookup. |
| 7.A | `src/vespercode/storage/{connection.py,migration_engine.py}`; `src/vespercode/storage/migrations/__init__.py`; `tests/unit/storage/{test_connection.py,test_migration_engine.py}` | None | Owns only connection/transaction policy, `schema_migrations`, closed descriptors, and the injected migration runner; no domain DDL or registry import. |
| 7.B | `src/vespercode/storage/migrations/v0001_run_wait.py`; `src/vespercode/storage/run_repository.py`; `src/vespercode/runs/lifecycle.py`; `tests/unit/storage/test_run_wait_migration.py` | None | Sole v0001 owner plus Run/config/wait transactions and transition rules; cannot edit the final registry. |
| 7.C | `src/vespercode/storage/migrations/v0002_idempotency.py`; `src/vespercode/storage/idempotency.py`; `tests/unit/storage/test_idempotency_migration.py` | None | Sole v0002 owner plus transaction-bound event replay ledger; cannot edit the final registry. |
| 7.D | `src/vespercode/storage/migrations/registry.py`; `tests/unit/storage/test_migration_registry.py` | None | Sole `ALL_V1_MIGRATIONS` composition owner; no DDL or repository behavior. |
| 8.A | `src/vespercode/runs/request.py`; `tests/unit/runs/test_request.py` | None | Request/config freeze completes before admission. |
| 8.B | `src/vespercode/runs/admission.py`; `tests/unit/runs/{test_admission.py,test_admission_order.py}` | None | Admission consumers use ports; no concrete adapter may move into these files. |
| 9.A | `src/vespercode/workspace/{identity_win32.py,object_win32.py}` | None | Owns all handle-derived workspace/final-object facts. |
| 9.B | `src/vespercode/workspace/mutex_win32.py` | None | Owns named-mutex lease lifetime only. |
| 9.C | `src/vespercode/workspace/git_preflight.py` | None | Owns sealed Git observations only. |
| 9.D | `src/vespercode/workspace/path_guard.py` | None | Owns existing/create path authorization only. |
| 10.A | `src/vespercode/trees/content_store.py`; `tests/unit/trees/test_content_store.py` | None | Owns content objects and digest-verified storage only. |
| 10.B | `src/vespercode/trees/text_classifier.py`; `tests/unit/trees/test_text_classifier.py` | None | Owns supported-text classification only. |
| 10.C | `src/vespercode/trees/snapshot.py`; `tests/unit/trees/test_snapshot.py`; `tests/integration/windows/test_snapshot_from_preflight.py` | None | Seals SnapshotTree; downstream tasks import content/classifier contracts without redefining them. |
| 11.A | `src/vespercode/tools/{file_actions.py,file_results.py,read_file.py}`; `tests/unit/tools/{test_file_actions.py,test_read_file.py}` | None | Common contracts freeze before discovery; dispatcher registration remains Task 17. |
| 11.B | `src/vespercode/tools/{list_files.py,search_text.py}`; `tests/unit/tools/{test_list_files.py,test_search_text.py}` | None | List/Search share only Task 11.A contracts and distinct canonical cursor types. |
| 12.A | `src/vespercode/candidate/unified_diff.py` | None | Owns complete strict diff parsing only. |
| 12.B | `src/vespercode/trees/candidate.py` | None | Owns immutable CandidateTree overlays only. |
| 12.C | `src/vespercode/candidate/patch_engine.py` | None | Owns exact atomic patch transactions only. |
| 12.D | `src/vespercode/candidate/{final_diff.py,identity.py}` | None | Owns FinalDiff reconstruction and three-root identity only. |
| 13 | `src/vespercode/governance/policy.py` | None | Mechanism/UI tasks consume policy results only. |
| 14.A | `src/vespercode/governance/writeback_subject.py`; `tests/unit/governance/test_writeback_subject.py` | None | Owns exact final-writeback subject identity only. |
| 14.B | `src/vespercode/storage/migrations/v0010_writeback_approvals.py`; `src/vespercode/governance/writeback_decision.py`; `tests/unit/storage/test_writeback_approvals_migration.py`; `tests/unit/governance/test_writeback_decision.py` | None | Sole v0010 owner plus decision/expiry transaction rules; Task 14.C consumes the schema without owning it. |
| 14.C | `src/vespercode/governance/writeback_approval.py`; `tests/unit/governance/{test_writeback_approval.py,test_writeback_approval_race.py}` | None | Persistence and UI consume one-time approval interfaces and cannot duplicate consume logic. |
| 15.A | `src/vespercode/governance/request_sources.py`; `tests/unit/governance/test_request_sources.py` | None | Owns closed request-source vocabulary only. |
| 15.B | `src/vespercode/governance/disclosure_scope.py`; `tests/unit/governance/test_disclosure_scope.py` | None | Owns disclosure scope normalization only. |
| 15.C | `src/vespercode/governance/disclosure_subject.py`; `tests/unit/governance/test_disclosure_subject.py` | None | Owns canonical disclosure subject binding only. |
| 15.D | `src/vespercode/storage/migrations/v0003_disclosure_grants.py`; `src/vespercode/governance/disclosure_decision.py`; `tests/unit/storage/test_disclosure_grants_migration.py`; `tests/unit/governance/test_disclosure_decision.py` | None | Sole v0003 subject/Grant schema owner plus decision transitions; Task 15.F mutates the existing Grant row without a second schema. |
| 15.E | `src/vespercode/storage/migrations/v0004_disclosure_authorizations.py`; `src/vespercode/governance/disclosure_ledger.py`; `tests/unit/storage/test_disclosure_authorizations_migration.py`; `tests/unit/governance/{test_disclosure_ledger.py,test_disclosure_budget_race.py}` | None | Sole v0004 authorization schema owner; LLM/UI tasks consume the ledger through immutable interfaces. |
| 15.F | `src/vespercode/governance/disclosure_revocation.py`; `tests/unit/governance/test_disclosure_revocation.py` | None | Owns exact active-Grant revocation and idempotent replay only. |
| 16.A | `src/vespercode/llm/{base.py,prepared_request.py,mock_adapter.py,call_result.py}` | None | Mock owns no real-provider capability; exact supporting tests are frozen in Task 16.A. |
| 16.B | `src/vespercode/llm/{openai_serializer.py,openai_adapter.py}` | None | Task 25.C composes the adapter through ports only; exact supporting tests are frozen in Task 16.B. |
| 17.A | `src/vespercode/loop/{agent_actions.py,action_parser.py}`; `tests/unit/loop/{test_agent_actions.py,test_action_parser.py}` | None | Owns the closed six-action parser only. |
| 17.B | `src/vespercode/loop/action_binding.py`; `tests/unit/loop/test_action_binding.py` | None | Owns Harness-issued action identity binding only. |
| 17.C | `src/vespercode/tools/dispatcher.py`; `tests/unit/tools/{test_dispatcher.py,test_dispatch_order.py}` | None | Main-loop orchestration consumes the closed dispatcher and cannot add a seventh model action. |
| 18.A | `src/vespercode/execution/docker_profile.py`; `tests/unit/execution/{test_docker_profile.py,test_docker_request.py}` | None | Owns immutable Docker profile/request construction only. |
| 18.B | `src/vespercode/execution/materialization.py`; `tests/unit/execution/test_materialization.py`; `tests/integration/docker/test_fresh_candidate_materialization.py` | None | Owns fresh candidate materialization only. |
| 18.C | `src/vespercode/execution/docker_executor.py`; `tests/unit/execution/test_docker_executor.py`; `tests/integration/docker/{test_execution_isolation.py,test_execution_output_limits.py}` | None | Owns bounded container execution only. |
| 18.D | `src/vespercode/execution/cleanup.py`; `tests/integration/docker/{test_execution_cleanup.py,test_execution_workspace_integrity.py}` | None | Image tasks provide artifacts; they do not weaken cleanup or runtime policy. |
| 19.A | `src/vespercode/validation/check_result.py` | None | Owns closed check results and Ruff/Mypy parsing. |
| 19.B | `src/vespercode/validation/{pytest_evidence.py,pytest_reporter.py}` | None | Owns authoritative pytest report emission/validation. |
| 19.C | `src/vespercode/validation/failure_fingerprint.py` | None | Owns allowlisted failure normalization only. |
| 20.A | `src/vespercode/validation/python_adapter.py` | None | Static detection/check-plan generation performs no execution; exact supporting tests are frozen in Task 20.A. |
| 20.B | `src/vespercode/validation/{baseline.py,manifest.py}` | None | Task 21.A consumes the frozen Manifest and Task 20.A plan; exact supporting tests are frozen in Task 20.B. |
| 21.A | `src/vespercode/validation/formal_plan.py`; `tests/unit/validation/{test_formal_plan.py,test_formal_preflight.py}` | None | Owns the frozen formal validation plan and preflight only. |
| 21.B | `src/vespercode/validation/formal_execution.py`; `tests/integration/docker/{test_reference_formal_validation.py,test_formal_execution_completeness.py}` | None | Owns complete formal-check execution evidence only. |
| 21.C | `src/vespercode/validation/formal.py`; `tests/unit/validation/{test_formal_predicate.py,test_verified_candidate.py}` | None | Only this child may create `VerifiedCandidateV1`. |
| 22.A | `src/vespercode/storage/migrations/v0005_memory.py`; `src/vespercode/memory/{entry.py,repository.py}`; `tests/unit/storage/test_memory_migration.py`; `tests/unit/memory/{test_entry.py,test_repository.py,test_authorization.py}` | None | Sole v0005 owner plus workspace-bound memory storage and creator authorization. |
| 22.B | `src/vespercode/memory/selection.py`; `tests/unit/memory/{test_selection.py,test_workspace_isolation.py}` | None | Owns authorized memory selection only. |
| 22.C | `src/vespercode/memory/clear.py`; `tests/unit/memory/test_clear.py` | None | Context/UI consume the complete memory lifecycle through public interfaces. |
| 23.A | `src/vespercode/storage/migrations/v0006_audit.py`; `src/vespercode/audit/{event.py,repository.py}`; `tests/unit/storage/test_audit_migration.py` | None | Sole v0006 owner plus redacted event schemas, ordering, paging, and clear. |
| 23.B | `src/vespercode/audit/projection.py` | None | Owns pure user-visible state projection. |
| 23.C | `src/vespercode/audit/retention.py` | None | Owns retention and unresolved-recovery preservation. |
| 24.A | `src/vespercode/loop/feedback.py`; `tests/unit/loop/test_feedback.py` | None | Owns structured feedback values and validation only. |
| 24.B | `src/vespercode/loop/context_projection.py`; `tests/unit/loop/{test_context_projection.py,test_context_trimming.py,test_context_sources.py}` | None | Owns authorized context assembly and trimming only. |
| 24.C | `src/vespercode/storage/migrations/v0008_feedback.py`; `src/vespercode/loop/feedback_consumption.py`; `tests/unit/storage/test_feedback_migration.py`; `tests/unit/loop/test_feedback_consumption.py` | None | Sole v0008 owner plus feedback append/consume-once transaction; Tasks 25.D and 25.G do not reimplement it. |
| 25.A | `src/vespercode/loop/{stopping.py,progress.py}`; `tests/unit/loop/{test_stopping.py,test_progress.py}` | None | Pure stopping/progress rules only. |
| 25.B | `src/vespercode/storage/migrations/v0007_agent_turns.py`; `src/vespercode/loop/turn_boundary.py`; `tests/unit/storage/test_agent_turns_migration.py`; `tests/unit/loop/test_turn_counting.py` | None | Sole v0007 owner plus all turn/call counter state changes. |
| 25.C | `src/vespercode/loop/call_orchestrator.py`; `tests/unit/loop/test_call_orchestrator.py` | None | Owns exactly-one-call ordering, no retry. |
| 25.D | `src/vespercode/storage/migrations/v0009_actions.py`; `src/vespercode/loop/action_pipeline.py`; `tests/unit/storage/test_actions_migration.py`; `tests/unit/loop/test_action_pipeline.py` | None | Sole v0009 owner plus one parse/policy/dispatch/feedback/action-record step. |
| 25.E | `src/vespercode/loop/{wait_control.py,cancellation.py}`; `tests/unit/loop/test_wait_lifecycle.py` | None | Owns wait/deadline/cancel safe points. |
| 25.F | `src/vespercode/loop/restart.py`; `tests/unit/loop/test_restart_behavior.py` | None | Owns restart fail-close only. |
| 25.G | `src/vespercode/loop/engine.py`; `tests/unit/loop/{test_main_loop.py,test_main_loop_failures.py}` | None | Thin composition only; no child rule duplication or external framework. |
| 26.A | `src/vespercode/storage/migrations/v0011_persistence.py`; `src/vespercode/persistence/{path_record.py,transaction.py,artifacts.py,writeback.py}`; `tests/unit/storage/test_persistence_migration.py` | None | Sole v0011 owner plus approval-bound write transaction, not recovery classification. |
| 26.B | `src/vespercode/persistence/recovery_preview.py` | None | Read-only preview/classification only; exact supporting tests are frozen in Task 26.B. |
| 26.C | `src/vespercode/storage/migrations/v0012_recovery.py`; `src/vespercode/persistence/{recovery_apply.py,recovery.py}`; `tests/unit/storage/test_recovery_migration.py` | None | Sole v0012 terminal-result owner; CLI/WebUI consume the same composed recovery service. |
| 27.A | `src/vespercode/credentials/{port.py,service.py}` | None | Owns secret wrapper, store protocol, and pure lifecycle service. |
| 27.B | `src/vespercode/credentials/wincred_store.py` | None | Owns the sole real WinCred implementation. |
| 28.A | `src/vespercode/web/security.py`; `tests/web/test_security.py` | None | Every later Web child consumes this boundary before its first domain call. |
| 28.B | `src/vespercode/web/app.py`; `src/vespercode/web/templates/{base.html,home.html}`; `src/vespercode/web/templates/components/status_badge.html`; `src/vespercode/web/static/htmx.min.js`; `src/vespercode/cli.py` | 38.E adds only recover parsing and typed delegation to `src/vespercode/cli.py`; 38.F adds only its production recover-handler binding; 33.B may later correct installed-resource lookup in that file | Route children install through ports and never modify `src/vespercode/web/app.py`; wave order is 38.E parser, 38.F production binding, then any 33.B installed-resource correction. |
| 29.A | `src/vespercode/web/{run_lifecycle_workflow.py,routes_runs.py}`; `src/vespercode/web/templates/{run_create.html,run_detail.html}` | None | Run create/status/cancel only. |
| 29.B | `src/vespercode/web/{disclosure_workflow.py,routes_disclosure.py}`; `src/vespercode/web/templates/disclosure_wait.html` | None | Disclosure decision only. |
| 29.C | `src/vespercode/web/{writeback_workflow.py,routes_writeback.py,run_workflows.py}` | None | Owns final writeback and Milestone 29 installer composition; exact supporting tests are frozen in Task 29.C. |
| 30.A | `src/vespercode/demo/{types.py,scenario.py,executor.py,runner.py}`; headless Demo tests | None | Shared core plus Demo-only ports/sessions; no Web or formal adapter. |
| 30.B | `src/vespercode/demo/{app.py,healthcheck.py,templates/demo.html}`; capability/health/render tests | None | Task 34.B packages these files without formal capability adapters. |
| 31.A | `scripts/run_reference_e2e.py` | None | Owns reusable driver/happy path; reference fixture remains immutable. |
| 31.B | None (test/evidence-only) | None | Exact supporting files are `tests/e2e/reference/{test_reference_denials.py,test_reference_waits.py,test_reference_no_write.py,test_reference_call_gate.py}`; consumes Task 31.A hooks without modifying production core or fixture. |
| 31.C | None (test/evidence-only) | None | Exact supporting files are `tests/e2e/reference/{test_reference_audit.py,test_reference_recovery_block.py}`; finalizes terminal/determinism evidence. |
| 32.A | `scripts/run_mechanism_demo.py` | None | Owns reusable offline trace driver; exact supporting tests are frozen in Task 32.A. |
| 32.B | None (test/evidence-only) | None | Exact supporting files are `tests/e2e/mechanism/{test_feedback_recovery.py,test_continuation_gate.py,test_trace_determinism.py}`; consumes Task 32.A driver only. |
| 32.C | None (test/evidence-only) | None | Exact supporting files are `tests/e2e/mechanism/{test_disclosure_gate.py,test_credential_recheck.py,test_shared_core_reuse.py}`; finalizes provenance and zero-side-effect evidence. |
| 33.A | None (authorized metadata modification plus test/evidence) | Task 4.A authorizes Task 33.A to modify package-data/version/distribution-metadata/console-entry-point fields in `pyproject.toml` | Produces one exact wheel/digest without becoming a second owner of `pyproject.toml`; dependency/Python/source/lock/build-backend/tooling sections remain immutable. |
| 33.B | `scripts/run_package_smoke.py` | Task 28.B authorizes an installed-resource-only correction in `src/vespercode/cli.py` | Consumes Task 33.A wheel; no source fallback. |
| 34.A | `scripts/run_reference_image_smoke.py` | None | Milestone 2 recipe/manifest inputs are read-only; exact supporting tests are frozen in Task 34.A. |
| 34.B | `containers/demo/Dockerfile`; `requirements/demo.lock`; `scripts/run_demo_image_smoke.py` | None | Curated Demo image only; exact supporting tests are frozen in Task 34.B. |
| 35.A | `.github/workflows/ci.yml` | None | GitHub remains no-publish; exact supporting contract test is frozen in Task 35.A. |
| 35.B | `.gitlab-ci.yml` | Task 35.C adds only the protected release stage/rules to `.gitlab-ci.yml` | Four verification jobs only. |
| 35.C | `scripts/verify_ci_contract.py` | Task 35.B authorizes the protected release-stage/rule modification to `.gitlab-ci.yml` | Freezes dual-platform contract/evidence; performs no release and is not a second owner of `.gitlab-ci.yml`. |
| 36.A | `src/vespercode/delivery/evidence.py`; `delivery/evidence/README.md`; `delivery/evidence/ci-v1.json`; `scripts/verify_release_evidence.py` | None | Closed schemas and local alignment only; exact supporting tests are frozen in Task 36.A. |
| 36.B | `delivery/evidence/release-v1.json` | None | File receives only real confirmed Release/GHCR values. |
| 36.C | `render.yaml`; `delivery/evidence/deployment-v1.json` | None | Files receive only real confirmed Render values; exact supporting tests are frozen in Task 36.C. |
| 37.A | `README.md`; `src/vespercode/delivery/readme_verifier.py` | None | Documentation contract only; no application behavior. |
| 37.B | `src/vespercode/delivery/process_verifier.py` | Appends only to `SPEC_PROCESS.md` and `AGENT_LOG.md` under their existing ownership rules | Preserves history, reads both Task 4 records without modifying them, and verifies all executable child evidence plus exact Task 1 Python identity continuity. |
| 37.C | `scripts/{verify_delivery.py,verify_reflection.py}` | Human owns substantive `REFLECTION.md` | Final gate only; no application or SPEC changes. |
| 38.A | `src/vespercode/web/routes_credentials.py`; `src/vespercode/web/templates/credential_status.html` | None | Credential workflow only. |
| 38.B | `src/vespercode/web/routes_memory.py`; `src/vespercode/web/templates/memory.html` | None | Memory workflow only. |
| 38.C | `src/vespercode/web/routes_audit.py`; `src/vespercode/web/templates/audit.html` | None | Audit workflow only. |
| 38.D | `src/vespercode/web/routes_recovery.py`; `src/vespercode/web/templates/recovery_preview.html` | None | Recovery Web workflow only. |
| 38.E | None (authorized core-file modification plus test) | Task 28.B authorizes only recover parsing/typed delegation in `src/vespercode/cli.py`; Task 38.F alone owns the production handler/service composition | Preview by default; literal apply only; injectable Spy tests; no database initialization or production default; Task 38.E is not a second owner of `src/vespercode/cli.py`. |
| 38.F | `src/vespercode/web/{routes_operations.py,local_composition.py}`; `src/vespercode/cli_composition.py`; `tests/unit/test_cli_composition.py`; local composition test | Task 28.B authorizes only the production recover-handler binding in `src/vespercode/cli.py` after Task 38.E freezes parsing | Sole Web installer and recovery-CLI production composition; complete registry precedes all repository/service construction; no parser or recovery behavior duplication. |
| 38.G | `tests/web/test_operations_accessibility.py`; browser evidence | None | Cross-workflow acceptance adds no production behavior. |
| Shared evidence | `PLAN.md`; `AGENT_LOG.md` | Every completed task, evidence-only | Merge and append in ascending task order within each wave; only SPEC §11.2 tracking fields preserve `PlanSemanticDigestV1`, while any other PLAN change triggers reapproval and cold-start. |
| Process record | `SPEC_PROCESS.md` | Cold-start recorder plus Tasks 37.B and 37.C final evidence | Historical content is preserved; only truthful append/revision evidence is permitted. |

## US → FR → NFR → AC → Task Traceability Matrix

Every task list in the four coverage matrices below contains exact executable Task ids only. Milestone ids, numeric ranges, and expansion shorthand are invalid in these matrices. `Implementation tasks` name the behavior owners; `Independent validation/delivery tasks` name a later Task that exercises, packages, reviews, or records the behavior without becoming a second implementation owner.

| User story | FR contract | NFR contract | Explicit AC set | Implementation tasks | Independent validation/delivery tasks |
|---|---|---|---|---|---|
| US-01 Configure and safely start a run | FR-ADM, FR-LOOP | NFR-PERF, NFR-USE, NFR-SEC | AC-15, AC-16, AC-21, AC-26, AC-28, AC-30, AC-31 | 6.A, 6.B, 6.C, 6.D, 6.E, 7.A, 7.B, 7.C, 7.D, 8.A, 8.B, 9.A, 9.B, 9.C, 9.D, 10.A, 10.B, 10.C, 20.A, 20.B, 23.A, 23.B, 23.C, 25.A, 25.B, 25.C, 25.D, 25.E, 25.F, 25.G, 28.A, 28.B, 29.A, 29.C | 31.A, 31.B, 31.C, 33.B, 35.A, 35.B, 35.C, 37.A, 37.B, 37.C, 38.G |
| US-02 Safely manage a real LLM credential | FR-CRED, SPEC §8.1 | NFR-SEC, NFR-PRIV | AC-08 | 16.B, 25.C, 27.A, 27.B, 38.A, 38.F | 31.B, 32.C, 33.B, 35.B, 35.C, 37.C, 38.G |
| US-03 Repair an existing stable failure | FR-LOOP, FR-WS, FR-VAL | NFR-PERF, NFR-REL | AC-04, AC-05, AC-06, AC-17, AC-18, AC-19, AC-20, AC-25, AC-26, AC-28, AC-31 | 10.A, 10.B, 10.C, 11.A, 11.B, 12.A, 12.B, 12.C, 12.D, 13, 17.A, 17.B, 17.C, 18.A, 18.B, 18.C, 18.D, 19.A, 19.B, 19.C, 20.A, 20.B, 21.A, 21.B, 21.C, 24.A, 24.B, 24.C, 25.A, 25.B, 25.C, 25.D, 25.E, 25.F, 25.G | 31.A, 31.B, 31.C, 32.A, 32.B, 32.C, 34.A, 35.A, 35.B, 37.C |
| US-04 Control external data disclosure | FR-GOV | NFR-SEC, NFR-PRIV | AC-13, AC-26, AC-27 | 15.A, 15.B, 15.C, 15.D, 15.E, 15.F, 16.A, 16.B, 24.A, 24.B, 24.C, 25.B, 25.C, 25.G, 29.B, 29.C | 31.B, 32.C, 35.A, 35.B, 35.C, 37.B, 37.C, 38.G |
| US-05 Rely on deterministic guardrails and one-time approval | FR-GOV | NFR-REL, NFR-SEC | AC-01, AC-02, AC-03, AC-26, AC-27, AC-31 | 9.A, 9.B, 9.C, 9.D, 12.A, 12.B, 12.C, 12.D, 13, 14.A, 14.B, 14.C, 15.A, 15.B, 15.C, 15.D, 15.E, 15.F, 17.A, 17.B, 17.C, 25.D, 25.E, 25.G | 31.B, 31.C, 32.A, 32.C, 35.A, 35.B, 37.C |
| US-06 Review, persist, and recover a verified diff | FR-PERSIST | NFR-REL, NFR-SEC | AC-07, AC-21, AC-22, AC-26, AC-29, AC-31 | 3.A, 3.B, 3.C, 3.D, 3.E, 3.F, 3.G, 9.A, 9.B, 9.C, 9.D, 12.A, 12.B, 12.C, 12.D, 14.A, 14.B, 14.C, 21.A, 21.B, 21.C, 26.A, 26.B, 26.C, 29.C, 38.D, 38.E, 38.F | 31.C, 33.B, 35.A, 35.B, 37.C, 38.G |
| US-07 Inspect and clear repository memory | FR-MEM | NFR-OBS, NFR-PRIV | AC-14, AC-23 | 22.A, 22.B, 22.C, 23.A, 23.B, 23.C, 24.A, 24.B, 24.C, 38.B, 38.F | 31.C, 35.A, 35.B, 37.C, 38.G |
| US-08 Understand status and audit evidence | FR-LOOP, FR-MEM, FR-UI | NFR-USE, NFR-OBS | AC-06, AC-16, AC-27, AC-28 | 7.A, 7.B, 7.C, 7.D, 23.A, 23.B, 23.C, 25.F, 25.G, 28.A, 28.B, 29.A, 29.C, 38.C, 38.F | 31.C, 33.B, 35.A, 35.B, 37.A, 37.C, 38.G |
| US-09 Run the public Mock Demo | FR-UI | NFR-PERF, NFR-REL, NFR-SEC | AC-09, AC-12 | 30.A, 30.B, 34.B | 32.A, 32.B, 32.C, 35.A, 35.B, 35.C, 36.A, 36.C, 37.A, 37.C |

## FR Coverage Matrix

| Functional requirement | Implementation tasks | Independent verification tasks | Verification/evidence contract |
|---|---|---|---|
| FR-ADM — request validation, Run creation, and ordered preflight | 6.A, 6.B, 6.C, 6.D, 6.E, 7.A, 7.B, 7.C, 7.D, 8.A, 8.B, 9.A, 9.B, 9.C, 9.D, 10.A, 10.B, 10.C, 20.A, 20.B | 31.A, 31.B | Child RED/GREEN suites prove the engine/domain/registry schema closure and zero-downstream admission failures; Windows checks prove workspace/Git/Snapshot; Task 31.A records the production call order and Task 31.B records denials. |
| FR-LOOP — loop, action protocol, context, budgets, stopping, and lifecycle | 5.A, 5.B, 5.C, 5.D, 5.E, 7.B, 7.C, 11.A, 11.B, 15.A, 15.B, 15.C, 15.D, 15.E, 15.F, 16.A, 16.B, 17.A, 17.B, 17.C, 24.A, 24.B, 24.C, 25.A, 25.B, 25.C, 25.D, 25.E, 25.F, 25.G | 31.A, 31.B, 31.C, 32.A, 32.B, 32.C | Component suites prove action, context, feedback, count, progress, timeout, cancel and restart rules; reference and mechanism traces prove composition. |
| FR-WS — Snapshot, path boundary, strict patches, and CandidateTree | 1.A, 1.B, 1.C, 1.D, 1.E, 4.B, 4.D, 6.A, 6.B, 6.C, 6.D, 6.E, 9.A, 9.B, 9.C, 9.D, 10.A, 10.B, 10.C, 11.A, 11.B, 12.A, 12.B, 12.C, 12.D | 31.A, 31.B, 32.A, 32.B | Task 1.E `GO` and Tasks 9.A–9.D Windows evidence prove object/path behavior; domain suites and later traces prove legal correction, cursor continuity, and denials. |
| FR-GOV — policy, final approval, disclosure, and real LLM authorization | 13, 14.A, 14.B, 14.C, 15.A, 15.B, 15.C, 15.D, 15.E, 15.F, 16.A, 16.B, 25.B, 25.C, 25.D, 25.E, 25.G, 29.B, 29.C | 31.B, 31.C, 32.A, 32.C, 38.G | Pure governance tests plus reference/mechanism/browser traces prove no unauthorized dispatch, network, approval consumption, or write. |
| FR-VAL — Python adapter, Baseline, checks, Manifest, feedback, and formal success | 18.A, 18.B, 18.C, 18.D, 19.A, 19.B, 19.C, 20.A, 20.B, 21.A, 21.B, 21.C, 24.A, 24.B, 24.C, 25.D, 25.G | 31.A, 31.C, 34.A | Docker commands prove isolation/report/Baseline/formal behavior; the reference flow and image smoke preserve the same Manifest and evidence. |
| FR-PERSIST — final approval, controlled writeback, and recovery | 3.A, 3.B, 3.C, 3.D, 3.E, 3.F, 3.G, 9.A, 9.B, 9.C, 9.D, 12.A, 12.B, 12.C, 12.D, 14.A, 14.B, 14.C, 21.A, 21.B, 21.C, 26.A, 26.B, 26.C, 29.C, 38.D, 38.E, 38.F | 31.C, 33.B, 38.G | Task 3.G gate, production fault/Windows tests, recovery UI/CLI, reference terminal trace, and installed smoke prove exact writeback and three-value recovery. |
| FR-MEM — memory and audit | 22.A, 22.B, 22.C, 23.A, 23.B, 23.C, 24.A, 24.B, 24.C, 38.B, 38.C, 38.F | 31.C, 38.G | Domain suites prove isolation/authority/order/retention; reference and browser evidence prove scoped visible operations. |
| FR-CRED — credential lifecycle | 16.B, 25.C, 27.A, 27.B, 38.A, 38.F | 31.B, 32.C, 35.B, 35.C, 38.G | WinCred smoke, zero-side-effect call-gate traces, WebUI response scans, and Windows CI evidence prove lifecycle and per-call revalidation. |
| FR-UI — formal local WebUI and public Demo | 28.A, 28.B, 29.A, 29.B, 29.C, 30.A, 30.B, 38.A, 38.B, 38.C, 38.D, 38.E, 38.F | 32.C, 33.B, 34.B, 36.C, 38.G | Local security/browser/installed tests plus shared-core proof, Demo image health, and live public smoke prove both isolated compositions. |

## NFR Coverage Matrix

| Non-functional requirement | Implementation tasks | Independent verification tasks | Test environment / release evidence |
|---|---|---|---|
| NFR-PERF — hard budgets and bounded resources | 5.A, 5.B, 5.C, 5.D, 5.E, 8.A, 8.B, 11.A, 11.B, 15.A, 15.B, 15.C, 15.D, 15.E, 15.F, 16.A, 16.B, 18.A, 18.B, 18.C, 18.D, 24.A, 24.B, 24.C, 25.A, 25.B, 25.C, 25.D, 25.E, 25.G, 30.A, 30.B | 31.A, 31.B, 32.B, 34.A, 34.B | FakeClock and boundary tests prove pre-side-effect limits; Docker/Demo image smoke and reference traces prove real resource ceilings. |
| NFR-REL — deterministic and fail-closed behavior | 1.A, 1.B, 1.C, 1.D, 1.E, 2.A, 2.B, 2.C, 2.D, 2.E, 2.F, 2.G, 3.A, 3.B, 3.C, 3.D, 3.E, 3.F, 3.G, 4.A, 4.F, 4.B, 4.C, 4.D, 4.E, 5.A, 5.B, 5.C, 5.D, 5.E, 6.A, 6.B, 6.C, 6.D, 6.E, 7.A, 7.B, 7.C, 7.D, 8.A, 8.B, 9.A, 9.B, 9.C, 9.D, 10.A, 10.B, 10.C, 11.A, 11.B, 12.A, 12.B, 12.C, 12.D, 13, 14.A, 14.B, 14.C, 15.A, 15.B, 15.C, 15.D, 15.E, 15.F, 16.A, 16.B, 17.A, 17.B, 17.C, 18.A, 18.B, 18.C, 18.D, 19.A, 19.B, 19.C, 20.A, 20.B, 21.A, 21.B, 21.C, 22.A, 22.B, 22.C, 23.A, 23.B, 23.C, 24.A, 24.B, 24.C, 25.A, 25.B, 25.C, 25.D, 25.E, 25.F, 25.G, 26.A, 26.B, 26.C, 30.A | 30.B, 31.A, 31.B, 31.C, 32.A, 32.B, 32.C, 37.C | Gate identity, dependency closure, formal toolchain promotion, canonical vectors, immutable structures, checksum-verified domain/registry closure, transactions, repeated semantic traces, shared-core provenance, and final missing-evidence rejection prove determinism/fail-close. |
| NFR-USE — understandable status, decisions, diff, and recovery | 23.A, 23.B, 23.C, 28.A, 28.B, 29.A, 29.B, 29.C, 37.A, 38.A, 38.B, 38.C, 38.D, 38.E, 38.F | 33.B, 38.G | Local WebUI/browser/accessibility tests, installed UI smoke, and README contract prove understandable non-color-only operation. |
| NFR-OBS — ordered evidence and categorized CI/release records | 7.A, 7.B, 7.C, 7.D, 23.A, 23.B, 23.C, 31.A, 31.B, 31.C, 32.A, 32.B, 32.C, 35.A, 35.B, 35.C, 36.A, 36.B, 36.C, 38.C, 38.F | 37.B, 37.C, 38.G | Schema history/registry checks, audit concurrency, deterministic reports, real dual-platform records, release/deployment JSON, browser evidence, and evidence-age checks prove observability. |
| NFR-SEC — declared threat-boundary mechanisms | 1.A, 1.B, 1.C, 1.D, 1.E, 2.A, 2.B, 2.C, 2.D, 2.E, 2.F, 2.G, 3.A, 3.B, 3.C, 3.D, 3.E, 3.F, 3.G, 6.A, 6.B, 6.C, 6.D, 6.E, 9.A, 9.B, 9.C, 9.D, 12.A, 12.B, 12.C, 12.D, 13, 14.A, 14.B, 14.C, 15.A, 15.B, 15.C, 15.D, 15.E, 15.F, 16.A, 16.B, 17.A, 17.B, 17.C, 18.A, 18.B, 18.C, 18.D, 21.A, 21.B, 21.C, 25.A, 25.B, 25.C, 25.D, 25.E, 25.F, 25.G, 26.A, 26.B, 26.C, 27.A, 27.B, 28.A, 28.B, 29.A, 29.B, 29.C, 30.A, 30.B, 35.A, 35.B, 35.C, 36.A, 36.B, 38.A, 38.B, 38.C, 38.D, 38.E, 38.F | 31.B, 31.C, 32.A, 32.C, 34.A, 34.B, 36.C, 37.C, 38.G | Windows/Docker/fault/Web/Demo/dual-CI/live checks plus every credential scan prove the declared boundary without overclaiming SPEC §5.5. |
| NFR-PRIV — local retention and minimal disclosure/storage | 15.A, 15.B, 15.C, 15.D, 15.E, 15.F, 16.A, 16.B, 22.A, 22.B, 22.C, 23.A, 23.B, 23.C, 26.A, 26.B, 26.C, 27.A, 27.B, 30.A, 30.B, 36.A, 38.A, 38.B, 38.C, 38.D, 38.F | 31.B, 31.C, 32.C, 36.C, 38.G | Source/record rejection, ACL/retention, WinCred, no-disk Demo, non-secret evidence, and local response scans prove minimal disclosure/storage. |

## AC Coverage Matrix

| AC | Implementation tasks | Independent validation tasks | Concrete test / required delivery evidence |
|---|---|---|---|
| AC-01 | 1.A, 1.B, 1.C, 1.D, 1.E, 4.B, 4.D, 9.A, 9.B, 9.C, 9.D, 12.A, 12.B, 12.C, 12.D, 13 | 31.B, 32.A | Win32 gate/object tests, strict patch tests, Task 1.E `GO`, Windows job log, and denial traces. |
| AC-02 | 13, 14.A, 14.B, 14.C, 15.A, 15.B, 15.C, 15.D, 15.E, 15.F, 17.A, 17.B, 17.C, 25.D, 30.A | 32.A, 32.C | Policy precedence, shared-core Demo composition, and mechanism hard-DENY report prove zero dispatch/publication. |
| AC-03 | 7.B, 7.C, 12.C, 12.D, 13, 14.A, 14.B, 14.C, 20.B, 21.A, 21.B, 21.C, 26.A | 31.B, 31.C, 32.A | Subject/approval/race tests and stale/expiry/duplicate approval traces prove zero write. |
| AC-04 | 12.A, 12.B, 12.C, 12.D, 13, 20.A, 20.B, 21.A, 21.B, 21.C | 31.B, 32.A | Patch/formal/protected-artifact tests and reference/mechanism zero-container evidence. |
| AC-05 | 16.A, 19.A, 19.B, 19.C, 24.A, 24.B, 24.C, 25.D, 25.G, 30.A | 31.A, 32.B, 32.C | Main-loop, shared-core, and feedback-recovery traces prove the Task 24.C feedback consumption changes the next action once. |
| AC-06 | 14.A, 14.B, 14.C, 17.A, 17.B, 17.C, 20.B, 21.A, 21.B, 21.C, 25.D, 25.G, 29.C | 31.A, 31.C, 38.G | Formal predicate, loop, writeback workflow, and completion → validation → final-wait/no-write evidence. |
| AC-07 | 12.D, 14.A, 14.B, 14.C, 21.A, 21.B, 21.C, 26.A, 29.C | 31.C, 38.G | Writeback preconditions/fault matrix/Web workflow plus approved FinalDiff/postimage/untouched-file digest report. |
| AC-08 | 27.A, 27.B, 28.A, 28.B, 38.A, 38.F | 31.B, 33.B, 35.B, 35.C, 38.G | Credential status/redaction/WinCred/Web tests, cleared state, Windows CI log, and installed smoke. |
| AC-09 | 13, 17.A, 17.B, 17.C, 24.A, 24.B, 24.C, 25.A, 25.D, 30.A, 30.B | 32.A, 32.B, 32.C, 34.B, 36.C | Exact shared-pure-core call sequence, repeated Demo trace, forbidden-capability absence, Demo image, and public scenario smoke. |
| AC-10 | 4.A, 4.F, 35.A, 35.B, 37.C | 35.C, 36.A, 37.B | Complete hash-locked dependency closure, `python -m pytest -q`, exact GitHub/GitLab contract tests, real unit-test jobs, and final process report. |
| AC-11 | 28.A, 28.B, 29.A, 29.B, 29.C, 33.A, 33.B, 35.A, 35.B, 35.C, 36.A, 36.B, 37.A, 38.A, 38.B, 38.C, 38.D, 38.E, 38.F | 37.C, 38.G | Clean pipx/installed CLI/WebUI, real wheel job, GitHub Release wheel/SHA, and verified install/start instructions. |
| AC-12 | 30.A, 30.B, 34.B, 35.A, 35.B, 35.C, 36.A, 36.C | 32.C, 37.C | Demo container health/capability smoke, real image-build log/digest, Render URL, and live `/healthz`. |
| AC-13 | 6.A, 6.B, 6.C, 6.D, 6.E, 15.A, 15.B, 15.C, 15.D, 15.E, 15.F, 16.A, 16.B, 24.A, 24.B, 24.C, 25.B, 25.C, 25.G, 27.A, 27.B, 29.B, 29.C | 31.B, 32.C | Source/scope/budget, fresh credential, counting, adapter, disclosure UI, and zero-side-effect reference/mechanism traces. |
| AC-14 | 22.A, 22.B, 22.C, 24.A, 24.B, 24.C, 38.B, 38.F | 31.C, 38.G | Memory repository/authorization/context tests plus cross-workspace/clear and visible-operation evidence. |
| AC-15 | 6.A, 6.B, 6.C, 6.D, 6.E, 8.A, 8.B, 9.A, 9.B, 9.C, 9.D, 10.A, 10.B, 10.C, 20.A, 20.B, 25.B, 25.G | 31.A | Admission-order/static tests, Windows identity/Snapshot checks, and exact PREFLIGHT/one-Snapshot E2E trace. |
| AC-16 | 7.A, 7.B, 7.C, 7.D, 23.A, 23.B, 23.C, 25.F, 25.G, 28.A, 28.B, 29.A, 38.C, 38.F | 31.C, 33.B, 38.G | Migration engine/registry, audit projection/status/run/audit Web tests plus state trace and installed browser captures. |
| AC-17 | 5.A, 5.B, 5.C, 5.D, 5.E, 10.A, 10.B, 10.C, 11.A, 11.B, 17.A, 17.B, 17.C, 30.A | 31.B, 32.B, 32.C | Cursor round-trip/stale/invalid/excerpt, parser/binding, production Demo call sequence, and paged/unpaged traces. |
| AC-18 | 10.A, 10.B, 10.C, 12.A, 12.B, 12.C, 12.D, 17.A, 17.B, 17.C, 20.A, 20.B, 21.A, 21.B, 21.C | 31.A, 31.C | FinalDiff/identity/patch/formal tests plus cumulative-patch, stale identity, and verified-candidate report. |
| AC-19 | 2.A, 2.B, 2.C, 2.D, 2.E, 2.F, 2.G, 18.A, 18.B, 18.C, 18.D, 19.A, 19.B, 19.C, 20.B, 34.A | 31.A, 35.A, 35.B | Docker gate/isolation/reference baseline, frozen digest, image smoke, and real reference-image-build logs. |
| AC-20 | 19.A, 19.B, 19.C, 20.A, 20.B, 21.A, 21.B, 21.C | 31.A, 31.C, 34.A | Formal predicate/reference Docker validation plus VerifiedCandidate digest and container smoke. |
| AC-21 | 1.A, 1.B, 1.C, 1.D, 1.E, 7.A, 7.B, 9.B, 26.A, 26.C | 31.C | Named mutex/repository/fault tests, Task 1.E mutex `GO`, recovery-block trace, and Windows log. |
| AC-22 | 3.A, 3.B, 3.C, 3.D, 3.E, 3.F, 3.G, 26.A, 26.B, 26.C | 31.C, 38.D, 38.E | Feasibility gate, deadline/external-change fault matrix, three-value report, and preview/apply evidence. |
| AC-23 | 22.A, 22.B, 22.C, 38.B, 38.F | 31.C, 38.G | Memory authorization and Web workflow plus creator/source audit and scoped-form evidence. |
| AC-24 | 1.A, 1.B, 1.C, 1.D, 1.E, 2.A, 2.B, 2.C, 2.D, 2.E, 2.F, 2.G, 3.A, 3.B, 3.C, 3.D, 3.E, 3.F, 3.G, 4.A, 4.B, 4.C, 4.D, 4.E, 18.A, 18.B, 18.C, 18.D, 19.A, 19.B, 19.C, 20.A, 20.B, 21.A, 21.B, 21.C, 26.A, 26.B, 26.C, 27.A, 27.B, 31.A, 31.B, 31.C, 33.A, 33.B, 34.A, 34.B, 35.A, 35.B, 35.C, 36.A, 36.B, 36.C, 37.B | 37.C | Gate identities, dedicated Windows/Docker/E2E/fault/package/OCI/CI/live commands, and categorized URLs/digests in closed evidence JSON. |
| AC-25 | 2.A, 2.B, 2.C, 2.D, 2.E, 2.F, 2.G, 19.C, 20.B | 31.A, 31.C, 34.A | Gate-only normalized-input comparator, production fingerprint/Baseline tests, and stable full/target digests in reference/image reports. |
| AC-26 | 4.B, 4.C, 4.D, 5.A, 5.B, 5.C, 5.D, 5.E, 6.A, 6.B, 6.C, 6.D, 6.E, 10.A, 10.B, 10.C, 12.D, 14.A, 14.B, 14.C, 15.A, 15.B, 15.C, 15.D, 15.E, 15.F, 16.A, 16.B, 17.A, 17.B, 17.C, 18.A, 18.B, 18.C, 18.D, 19.C, 20.A, 20.B, 21.A, 21.B, 21.C, 24.A, 24.B, 24.C, 25.A, 25.B, 25.C, 25.D, 25.E, 25.F, 25.G | 31.C, 37.B, 37.C | CTV vectors and candidate/profile/request/fingerprint/Manifest/subject digest suites plus cross-process trace and final digest audit. |
| AC-27 | 7.B, 7.C, 14.A, 14.B, 14.C, 15.A, 15.B, 15.C, 15.D, 15.E, 15.F, 25.E, 25.G, 29.B, 29.C | 31.B, 31.C, 38.G | Repository/approval/ledger/wait tests plus restart/wait decisions and browser-bound decision evidence. |
| AC-28 | 5.A, 5.B, 5.C, 5.D, 5.E, 7.B, 7.C, 8.A, 8.B, 15.A, 15.B, 15.C, 15.D, 15.E, 15.F, 16.A, 16.B, 17.A, 17.B, 17.C, 24.A, 24.B, 24.C, 25.A, 25.B, 25.C, 25.E, 25.G, 27.A, 27.B | 31.B, 32.C | Counting/stopping/wait/credential/ledger tests plus deadline/order and cleared/unsafe zero-count reports. |
| AC-29 | 3.A, 3.B, 3.C, 3.D, 3.E, 3.F, 3.G, 26.A, 26.B, 26.C, 38.D, 38.E, 38.F | 31.C, 33.B, 38.G | External-change/recovery Web/CLI tests plus preview/apply/new-file and installed preview evidence. |
| AC-30 | 2.A, 2.B, 2.C, 2.D, 2.E, 2.F, 2.G, 6.A, 6.B, 6.C, 6.D, 6.E, 18.A, 18.B, 18.C, 18.D, 20.B, 34.A, 35.A, 35.B, 35.C, 36.A, 36.B | 37.C | Local OCI/loopback/digest-pull proof, exact reproduction, protected pipeline, released manifest, GHCR RepoDigest, and target pull equality. |
| AC-31 | 6.A, 6.B, 6.C, 6.D, 6.E, 9.A, 9.B, 9.C, 9.D, 10.A, 10.B, 10.C, 11.A, 11.B, 12.A, 12.B, 12.C, 12.D, 13, 14.A, 14.B, 14.C, 18.A, 18.B, 18.C, 18.D, 20.A, 20.B, 21.A, 21.B, 21.C, 26.A | 31.A, 31.B, 31.C, 32.A, 32.C | Editable/candidate/policy/formal/persistence tamper and Windows alias tests plus legal/illegal mixed-patch and hard-DENY reports. |

## Test Environment Matrix

Every `Owning tasks` cell below contains exact executable Task ids only. The feasibility children under Milestones 1, 2, and 3 run only through the environment frozen by Task 1.A. Task 4.A then freezes the complete formal dependency closure, exact Task 1 Python identity, and sole `.venv-formal` bootstrap; Task 4.F separately promotes that exact interpreter/tool identity, marker set, and static rules. In every fresh formal worktree, `py -3.12 scripts/bootstrap_formal_env.py` must compare `platform.python_version()` character-for-character with Task 1.E terminal `GO` evidence before creating or using `.venv-formal`, then install only `requirements/dev.lock` with `--require-hashes --no-deps`. Task 4.F's pytest configuration makes logical `python -m pytest -q`, executed as `.venv-formal\Scripts\python.exe -m pytest -q`, the deterministic formal offline command by excluding all six real-environment markers. A dedicated formal environment command always clears default addopts, selects exactly one marker, and names its test root.

| Layer | Exact environment and command | Owning tasks | Required proof | Saved evidence |
|---|---|---|---|---|
| Feasibility gate bootstrap | Windows 11 x64; `py -3.12 -m venv .venv-gate`; hash-only install from `requirements/gate.lock`; all checks via `.venv-gate\Scripts\python.exe scripts/run_gate_checks.py {pytest|ruff-format|ruff-check|mypy} -- <explicit-targets>`; Task 2.C starts a digest-pinned registry on `127.0.0.1` with an OS-assigned port | 1.A, 1.B, 1.C, 1.D, 1.E, 2.A, 2.B, 2.C, 2.D, 2.E, 2.F, 2.G, 3.A, 3.B, 3.C, 3.D, 3.E, 3.F, 3.G | Exact dependency hashes/markers/config; no global/Task 4 project config; Task 2.D/2.E/2.F reporter, evidence, and stable failure inputs; fixed OCI parameters, local OCI → loopback RepoDigest → digest-pull equality, zero credentials/external push, no manifest self-reference, verified cleanup; unchanged Milestone 1 identities in Milestones 2 and 3 | Tool/file SHA-256, install log, registry image/config/bind/cleanup evidence, three equal digests, and Milestone 1, 2, and 3 `GO` reports |
| Offline unit tests | Fresh Windows worktree; `py -3.12 scripts/bootstrap_formal_env.py`; exact Task 1 `python_version`; hash-only/no-dependency materialization from immutable `requirements/dev.lock`; no network/Docker/WinCred during tests; `.venv-formal\Scripts\python.exe -m pytest -q` | 4.A, 4.F, 4.B, 4.C, 4.D, 4.E, 5.A, 5.B, 5.C, 5.D, 5.E, 6.A, 6.B, 6.C, 6.D, 6.E, 7.A, 7.B, 7.C, 7.D, 8.A, 8.B, 9.C, 9.D, 10.A, 10.B, 10.C, 11.A, 11.B, 12.A, 12.B, 12.C, 12.D, 13, 14.A, 14.B, 14.C, 15.A, 15.B, 15.C, 15.D, 15.E, 15.F, 16.A, 16.B, 17.A, 17.B, 17.C, 18.A, 18.B, 18.C, 18.D, 19.A, 19.B, 19.C, 20.A, 20.B, 21.A, 21.B, 21.C, 22.A, 22.B, 22.C, 23.A, 23.B, 23.C, 24.A, 24.B, 24.C, 25.A, 25.B, 25.C, 25.D, 25.E, 25.F, 25.G, 26.A, 26.B, 26.C, 27.A, 28.A, 28.B, 29.A, 29.B, 29.C, 30.A, 30.B, 32.A, 32.B, 32.C, 35.A, 35.B, 35.C, 37.A, 37.B, 37.C, 38.A, 38.B, 38.C, 38.D, 38.E, 38.F, 38.G | Bootstrap rejects non-exact Python before environment creation/use; dependency closure and both unique records match terminal gate evidence; formal toolchain promotion, canonical vectors, closed schemas/cursors, migration engine/domain/registry closure, Mock/Stub core, policy, requests, per-call credential failure ordering, parsers, transactions, feedback, loop, memory, audit, WebUI client, Demo logic | Bootstrap identity/install result, both persistent Task 4 records, local output, plus GitHub Actions and GitLab CI `unit-test` report artifacts |
| Windows integration tests | Project-specific Windows 11 x64 runner; `python -m pytest -q -o addopts='' -m windows_integration tests/integration/windows tests/feasibility/windows` | 1.A, 1.B, 1.C, 1.D, 1.E, 9.A, 9.B, 9.C, 10.A, 10.B, 10.C, 26.A, 26.C, 27.B | NTFS/Win32 final identity, path collision, ADS, reparse/hard link, named mutex, Git bytes, Snapshot source, ACL, persistence, WinCred lifecycle and fresh per-call lookup | Runner OS/Python/Git versions, test report, cleared credential state |
| Docker integration tests | Docker Desktop Linux mode; `python -m pytest -q -o addopts='' -m docker_integration tests/integration/docker tests/feasibility/docker` | 2.A, 2.B, 2.C, 2.D, 2.E, 2.F, 2.G, 18.A, 18.B, 18.C, 18.D, 19.B, 20.B, 21.A, 21.B, 21.C | Immutable image/profile mapping, loopback registry round-trip/no-self-reference/cleanup, check containers with no network/root/write/socket, tmpfs/resources, complete reports, Baseline, formal validation | Docker/builder/registry versions, three-way image digest, lifecycle inspection, report/test artifacts |
| Reference fixture E2E | Windows + Docker + Mock profile; `python -m pytest -q -o addopts='' -m reference_e2e tests/e2e/reference` | 31.A, 31.B, 31.C | Complete production admission → Baseline → feedback correction → formal validation → wait → exact writeback/recovery-block flow | Canonical Task 31.A/31.B/31.C traces/reports, final tree digests, cleanup evidence |
| Persistence fault injection | FakeClock/FaultPort offline: `python -m pytest -q tests/fault_injection/persistence`; real identity/ACL cases use the Windows command | 3.A, 3.B, 3.C, 3.D, 3.E, 3.F, 3.G, 26.A, 26.B, 26.C | Every named crash/deadline/state-lag/external-change point across 1–3 mixed files; preview zero write; three dispositions only | Gate and production fault matrices, transaction/evidence digests |
| WebUI local tests | TestClient plus loopback browser; `python -m pytest -q tests/web` followed by the Tasks 29.A, 29.B, 29.C, 38.A, 38.B, 38.C, 38.D, 38.E, 38.F, and 38.G keyboard workflows | 28.A, 28.B, 29.A, 29.B, 29.C, 38.A, 38.B, 38.C, 38.D, 38.E, 38.F, 38.G | Host/Origin/CSRF/session/headers, escaping, state labels, all local workflows, accessibility, no domain bypass | Test report and browser screenshots/captures without secrets |
| Public Mock Demo smoke | Offline `python -m pytest -q tests/demo`; real container/public checks run under `oci_smoke` and `deployment_smoke` | 30.A, 30.B, 32.A, 32.B, 32.C, 34.B, 36.C | Fixed deterministic trace; runtime reuse only of the exact Task 13, 17.A–17.C, 24.A–24.C, 25.A, and 25.D pure modules; Demo-only state/tool ports; complete prohibited-module absence; session/time/concurrency bounds; health | Exact shared-pure-core implementation provenance/call sequence, prohibited-capability absence/counters, repeated trace digests, Demo image digest, deployment id, public URL/health result |
| Wheel/pipx smoke | Project Windows runner; `python -m pytest -q -o addopts='' -m package_smoke tests/smoke/package` | 33.A, 33.B, 35.A, 35.B, 35.C, 36.A, 36.B | One wheel, RECORD/resources, SHA-256, clean pipx install, installed CLI/WebUI, recovery preview, cleanup | Wheel filename/version/digest, pipx/Python versions, installed smoke log |
| OCI image smoke | Docker runner; `python -m pytest -q -o addopts='' -m oci_smoke tests/smoke/images` | 34.A, 34.B, 35.A, 35.B, 35.C | Real reference/Demo builds, runtime contracts, tool/profile/fixture health, capability separation | Build logs, local image digests, inspections, container smoke report |
| Dual CI contract and runs | GitHub Actions push/PR plus GitLab push/MR/main/tag; `python scripts/verify_ci_contract.py .github/workflows/ci.yml .gitlab-ci.yml` | 35.A, 35.B, 35.C, 36.A, 37.B, 37.C | Exact job/event matrices, real test/image builds, no-publish/no-secret GitHub boundary, GitLab Windows wheel and protected release boundary | Real GitHub workflow/job and GitLab pipeline/job URLs, reports, image digests, permission/secret checks |
| Release/deployment smoke | Protected GitLab release runner plus public network; `python -m pytest -q -o addopts='' -m deployment_smoke tests/smoke/release` and `python scripts/verify_release_evidence.py delivery/evidence --require-live` | 35.C, 36.A, 36.B, 36.C, 37.C | Both source-commit CI closures, commit alignment, released wheel re-download, GHCR digest re-pull, manifest match, Render health/scenario/capability absence | Real workflow/pipeline/job URLs, Release URL, GHCR RepoDigest, Render URL, closed evidence JSON |

No parser-only test, Linux wheel install, manually copied log, tag-based image reference, or local schema result can replace a required Windows, Docker, package, OCI, CI, or live deployment result.

## Plan Mechanical Closure Audit

This audit is mandatory after every non-tracking PLAN edit. It parses only the exact executable headings and the canonical tables in this section; prose Milestone contracts are not executable graph nodes. The current semantic revision passes all checks below:

| Invariant | Current measured result | Status |
|---|---|---|
| Executable registry | 135 unique executable Tasks: retained integer Task 13 plus 134 dotted child Tasks; 37 Milestones remain non-executable containers | PASS |
| Dependency table | 135 unique rows, 578 exact predecessor edges, one root (`1.A`), zero missing/self/unknown edges | PASS |
| DAG topology | 135/135 nodes topologically sorted; 135/135 reachable from root `1.A`; zero cycles, isolated nodes, or unreachable nodes | PASS |
| Executable waves | 70 longest-path waves, 135/135 Tasks assigned exactly once, zero predecessor-in-same-or-later-wave violations | PASS |
| Ownership | 135 unique Task rows, 328 expanded core paths, zero duplicate primary owners | PASS |
| Parallel conflicts | Zero same-wave intersections across expanded core-file ownership sets | PASS |
| Migration ownership | One framework owner; 12 ordered domain migration owners for exact v0001–v0012; one composition-only registry owner whose 12 direct predecessors equal all producers; its test-only prefix audit proves exact per-version table deltas and the final 18-table set; all runtime/full-database consumers depend transitively on Task 7.D | PASS |
| Interface provenance | All 135 Task blocks declare exact `Interfaces` without placeholder signatures; all 578 edges target an existing executable producer or a documented ordering/evidence predecessor. | PASS |
| Requirement coverage | 9/9 US, 9/9 FR, 6/6 NFR, and 31/31 AC rows each have non-empty, valid, disjoint implementation and independent validation Task sets | PASS |
| Test environments | 12/12 environment rows contain only existing exact executable Task ids | PASS |
| Stale executable shorthand | Zero ranges, natural-language dependency sets, or aggregate Milestone ids in the canonical DAG, Wave, ownership target, coverage, Test Environment, or Release Gate structures | PASS |
| Release count | Release Gate requires exactly the same 135 executable Tasks | PASS |

The audit fails closed if a later parser finds a count mismatch, unknown Task id, duplicate membership/owner, cycle, unreachable node, non-earlier dependency, parallel core-file collision, missing producer, uncovered requirement, aggregate Milestone target, range, or natural-language dependency. Stable Milestone headings and their retained non-executable domain contracts are intentional and are not stale executable references.

## Release Readiness Gate

Release readiness is `PASS` only when every condition below is true at the same source commit:

- All **135 executable Tasks** are complete and each records a real implementation commit SHA, responsible subagent, human edits, exact tests, spec review, code-quality review, and PR URL. All 37 Milestones derive complete status from their exact children and have no aggregate implementation commit or PR.
- The exact release registry is: 1.A, 1.B, 1.C, 1.D, 1.E, 2.A, 2.B, 2.C, 2.D, 2.E, 2.F, 2.G, 3.A, 3.B, 3.C, 3.D, 3.E, 3.F, 3.G, 4.A, 4.F, 4.B, 4.C, 4.D, 4.E, 5.A, 5.B, 5.C, 5.D, 5.E, 6.A, 6.B, 6.C, 6.D, 6.E, 7.A, 7.B, 7.C, 7.D, 8.A, 8.B, 9.A, 9.B, 9.C, 9.D, 10.A, 10.B, 10.C, 11.A, 11.B, 12.A, 12.B, 12.C, 12.D, 13, 14.A, 14.B, 14.C, 15.A, 15.B, 15.C, 15.D, 15.E, 15.F, 16.A, 16.B, 17.A, 17.B, 17.C, 18.A, 18.B, 18.C, 18.D, 19.A, 19.B, 19.C, 20.A, 20.B, 21.A, 21.B, 21.C, 22.A, 22.B, 22.C, 23.A, 23.B, 23.C, 24.A, 24.B, 24.C, 25.A, 25.B, 25.C, 25.D, 25.E, 25.F, 25.G, 26.A, 26.B, 26.C, 27.A, 27.B, 28.A, 28.B, 29.A, 29.B, 29.C, 30.A, 30.B, 31.A, 31.B, 31.C, 32.A, 32.B, 32.C, 33.A, 33.B, 34.A, 34.B, 35.A, 35.B, 35.C, 36.A, 36.B, 36.C, 37.A, 37.B, 37.C, 38.A, 38.B, 38.C, 38.D, 38.E, 38.F, and 38.G.
- Task 7.A's engine passes independent order/idempotency/atomicity/checksum tests; every v0001–v0012 domain owner passes its exact table/key/unique/FK/prohibited-column contract; Task 7.D's direct predecessors equal the twelve migration producers; `ALL_V1_MIGRATIONS` has exact versions/names/order/checksums with no missing/duplicate/gap/unexpected entry; its test-only prefix audit proves each migration's exact owner-map table delta plus the final 18-table set including framework `schema_migrations`; and Task 38.F applies only that tuple before constructing production Web ports or the installed recover CLI's Task 26 service/handler, while Task 38.E parser tests remain injectable and database-independent.
- M0 records the human-approved current SPEC path/SHA-256/blob/baseline and confirms the gate-bootstrap contract; Tasks 1.E, 2.G, and 3.G have `GO` outcomes under a cold-start record covering the approved `PlanSemanticDigestV1`.
- `requirements/gate.lock`, `gates/pytest.ini`, `gates/ruff.toml`, `gates/mypy.ini`, `scripts/run_gate_checks.py`, the Task 2.D/2.E/2.F reporter/evidence/fingerprint producers, the Task 1.E, 2.G, and 3.G `GO` reports, `config/dependency-closure-v1.json`, and `config/formal-toolchain-promotion-v1.json` remain present; Task 37.B recomputes their SHA-256/version matrix and proves both records' `python_version` values equal Task 1.E terminal `GO` `GateToolchainEvidenceV1.python_version` character-for-character before proving the remaining closure/promotion identities match without silent drift.
- Task 2.G `GO` proves a digest-pinned loopback-only registry with no credentials/external pushes, verified cleanup, no final-manifest self-reference, and local OCI/registry/digest-pull equality with final `ReferenceProfileManifestV1.docker_image_digest`; Task 34.A reproduces that exact identity, and Task 36.B's GHCR RepoDigest equals it.
- Every Critical or Important review finding is closed and the same review stage passed after the fix.
- The Task 4.A dependency tables, public Python range `>=3.12,<3.13`, exact Task 1 `python_version`, source/index policy, `requirements/dev.lock`, and unique closure record still match the reviewed closure; Task 4.F's unique promotion record carries the same exact `python_version`; `.venv-formal\Scripts\python.exe -m pytest -q`, Ruff format, Ruff lint, and strict Mypy pass from the environment materialized only by `py -3.12 scripts/bootstrap_formal_env.py` with `--require-hashes --no-deps` under Task 4.F's unchanged formal tooling configuration.
- All required Windows, Docker, reference E2E, persistence fault, WebUI/browser, package, OCI, and live smoke results pass without a required skip.
- Task 35.A's latest `.github/workflows/ci.yml` workflow for the released source commit passes exact `unit-test`, `reference-image-build`, and `demo-image-build` jobs for the applicable push/pull-request contract, with no publish credential/action.
- Task 35.B's latest `.gitlab-ci.yml` pipeline for the released source commit passes all applicable exact jobs: `unit-test`, `wheel-build-smoke`, `reference-image-build`, and `demo-image-build`; Task 35.C proves both platform results and protected release rules refer to the same source commit.
- The changed-file scan and final repository-wide credential scan report no credential match, and no secret value appears in logs, images, wheel, evidence, or artifacts.
- Exactly one versioned wheel builds, its SHA-256 verifies after GitHub Release download, and clean Windows pipx installation starts the installed CLI/WebUI.
- The released reference image is pulled from GHCR by RepoDigest; Task 2.G loopback RepoDigest, Task 34.A reproduction, the wheel's built-in `ReferenceProfileManifestV1.docker_image_digest`, Task 36.B GHCR RepoDigest, and target-machine inspection all identify the same OCI manifest bytes.
- The Demo OCI image passes capability/health smoke and the recorded Render public URL is reachable, simulation-labeled, and unable to access local/recovery/real-provider capabilities.
- Task 37.A's `README.md` contains verified installation, usage, distribution, directory, credential, disclosure, recovery, platform/threat limitation, CI/release, GHCR, and deployment instructions with real URLs/digests.
- `AGENT_LOG.md` is chronological and complete for every significant task, review, intervention, failure, commit, PR, and lesson.
- Task 37.B proves `SPEC_PROCESS.md` contains brainstorming, three or more iterations, accepted/rejected suggestions, M0 SPEC identity/approval, PLAN semantic/full audit identities, and cold-start agent/scope/findings/revisions/pass evidence.
- Task 26.C and Task 37.C prove no unresolved persistence transaction exists in the delivery workspace, and retention/cleanup evidence preserves required terminal digests.
- `REFLECTION.md` is the student's own 1,500–2,500-word reflection; any agent language polish is explicitly requested, bounded, and disclosed.
- `python scripts/verify_delivery.py --root . --require-live` and `python scripts/verify_reflection.py REFLECTION.md` both pass against current evidence.

## Explicit v1 Non-goals

The following items are copied from authoritative SPEC §1.6 and have no v1 implementation task, test exception, compatibility branch, or release gate:

- 生产级通用 Coding Agent 或任意仓库兼容。
- 自然语言缺陷生成复现测试、`ValidationManifestV2` 或测试生成审批。
- 多 Agent、并行 turn、分布式任务、供应商调用对账或自动重发。
- 普通 Agent turn 的跨进程恢复。
- 通用 quarantine allocator、分布式 reconciliation 或多层 cleanup 状态机。
- Agent/Harness 正式运行中自动 commit、push、PR、依赖安装、镜像构建或对外发布；SPEC §8.4 的项目交付 CI 不属于 Agent 能力。
- 识别所有秘密格式、消除所有提示注入或对恶意宿主管理员提供隔离。
- 验证以破坏 Python 解释器、pytest、固定报告插件、容器内报告通道或检查进程为目的的主动恶意项目代码。
- 删除、重命名、二进制修改、文件模式变更或超过 3 文件的持久化事务。

The following future-work items are copied from authoritative SPEC §11.3 and are also excluded:

- `NaturalLanguageDefect`、测试提案审批和 `ValidationManifestV2`。
- 更宽松但仍确定性的 skip/xfail 基线比较。
- 多语言 `ProjectAdapter` 和更多预构建 reference profile。
- 供应商请求重试、跨进程调用对账和普通 turn 恢复。
- 删除、重命名、二进制补丁和更广 Git 策略。
- 多用户部署、分布式配额和生产级工件清理。
- 独立低权限测试用户、进程外认证报告通道或更强沙箱，用于验证主动攻击 Python/pytest/报告插件的项目。
- 超过 3 文件的持久化事务。

## Resolved Decisions and Human Approval Required

The two prior design decisions are resolved in the current SPEC/PLAN contract and are no longer implementation choices:

1. **Resolved OD-01 = A.** List/Search use distinct canonical cursor round trips binding visible-tree digest, cursor-free query digest, stable next scan position, and cursor self-digest. Cursor type/query/position/digest errors are `CONTINUATION_INVALID`; tree changes are `CONTINUATION_STALE`; both return zero partial result. Tasks 11.A, 11.B, and 17 must implement this exact contract.
2. **Resolved OD-02 = B.** SPEC §11.2 `PlanSemanticDigestV1` excludes only enumerated task Status, checkbox state, and one-line Completion evidence tracking fields. Complete-file PLAN SHA-256 remains an audit identity. Any other PLAN change requires a new semantic approval and cold-start.

No unresolved product-design choice remains. The following human actions are mandatory process gates:

- Complete M0 and approve the exact `SPEC.md` path, SHA-256, Git blob, and baseline commit in the external record.
- Approve the externally calculated `PlanSemanticDigestV1` and complete-file PLAN SHA-256 audit snapshot for that SPEC.
- Select the heterogeneous cold-start agent type and one or two of Tasks 1, 2, and 3 for the disposable readiness trial, then approve the recorded pass/revision outcome.
- Make the project-specific Windows 11 x64 GitLab Runner and protected least-privilege GitHub Release, GHCR, and Render authorizations available only at their declared waves.
- Write the substantive 1,500–2,500-word `REFLECTION.md` and explicitly decide whether any language-only polishing is requested.
