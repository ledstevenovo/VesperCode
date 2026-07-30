# Repository Guidelines

## Project Structure & Required Deliverables

This repository currently contains the course specifications only:
`AI4SE_Final_Project_通用要求.md` and
`AI4SE_Final_Project_A_Coding_Agent_Harness(1).md`. Add implementation files
only after the specification and plan are approved. Keep project artifacts at
the repository root: `SPEC.md`, `PLAN.md`, `SPEC_PROCESS.md`, `AGENT_LOG.md`,
`README.md`, and `REFLECTION.md`. Place application code under a language-
appropriate directory such as `src/`, and tests under `tests/` (or the
ecosystem's standard test directory). Keep the harness core, tool adapters,
guardrails, feedback validators, and memory components in separate modules.

## Build, Test, and Development Commands

No build tool or executable code exists yet. When selecting a stack, provide a
single documented test command (for example, `make test`) and use it in local
development and CI. The CI configuration must include a `unit-test` job and
run on every push. If the project is containerized, also document `docker
build` and `docker run` commands in `README.md`.

## Coding Style & Naming Conventions

Follow the formatter, linter, and test conventions of the chosen language;
commit their configuration files with the code. Prefer small, single-purpose
modules and explicit error handling. Name modules and files consistently with
the language ecosystem; use descriptive names such as `guardrail`,
`tool_dispatcher`, and `feedback_validator`. Do not add unrelated refactors or
dependencies.

## Testing Guidelines

Use test-driven development: write a failing test, implement the smallest
change to pass it, then refactor. Core harness mechanisms must have
deterministic, offline unit tests using an injectable mock or stub LLM. Cover
tool dispatch, dangerous-action interception, feedback-driven correction,
memory access, and stopping behavior. Include a repeatable mechanism demo
that shows guardrail interception, feedback recovery, and the chosen deep-dive
mechanism.

## Security & Configuration

Never commit API keys, `.env` files, credentials, or command-history secrets.
Support secure key entry, status checking without revealing values, updates,
and removal. Document the credential threat model, target-machine setup, and
distribution limitations in `SPEC.md` and `README.md`.

## Commits & Pull Requests

Git history is not initialized, so no existing message convention can be
inferred. Use concise imperative subjects, for example: `Add mock LLM
guardrail test`. Work in isolated worktrees, use one PR per independent task,
and record the task, responsible subagent, human edits, verification results,
and commit hash in the PR and `AGENT_LOG.md`.

## Course Project Mandatory Requirements

This repository is a Coding Agent Harness final project. The complete source
of truth is `AI4SE_Final_Project_通用要求.md` together with
`AI4SE_Final_Project_A_Coding_Agent_Harness(1).md`; the rules below make their
project-critical requirements operational for this repository.

### Project Phase and Process Evidence

- Do not add implementation code until `SPEC.md` and `PLAN.md` are complete,
  approved, and have passed the required cold-start trial by a different agent
  type with no prior conversation or memory context.
- Follow the Superpowers workflow truthfully: brainstorming, planning,
  isolated worktrees, subagent development or plan execution, TDD, review,
  and branch completion. Record any justified deviation in `AGENT_LOG.md`.
- `SPEC.md` must include the problem, at least five INVEST-style user stories,
  functional and non-functional requirements, architecture, data model,
  credential threat model, distribution, technology choices, acceptance
  criteria, risks, and a Coding Agent Harness "domain and mechanism design"
  section.
- `PLAN.md` tasks must name their goal, files, implementation points,
  intentionally failing test, verification, dependencies, and parallelizable
  work. Mark each completed task with its commit hash.
- Keep `SPEC_PROCESS.md` as evidence of brainstorming, at least three key
  iterations, accepted and rejected AI suggestions, cold-start findings, and
  resulting SPEC/PLAN revisions.
- Keep `AGENT_LOG.md` chronological. Each significant entry needs a timestamp,
  task ID, skills invoked, key prompt/context, subagent output or commit,
  human intervention, and lesson learned.

### Harness Implementation Boundary

- Implement the agent main loop in this repository: context assembly, one LLM
  call, action parsing, dispatch, result feedback, and stopping decision. Do
  not delegate this loop to LangChain AgentExecutor, AutoGen, CrewAI,
  LlamaIndex agents, or a host coding-agent runner.
- Depend only on permitted low-level components where needed (for example, a
  single-turn LLM API, HTTP client, parser, or vector store). Expose an LLM
  abstraction that accepts an injectable mock or stub.
- Provide a runnable minimum implementation for decision handling, tools,
  memory/context, governance, feedback, and configuration. Select one
  mechanism-heavy dimension as the main contribution and implement it in
  meaningful depth.
- Implement feedback sensors and dangerous-action interception as deterministic
  code, never solely as prompt instructions. A core mechanism counts only if
  it remains independently testable after replacing the real LLM with a mock.

### Testing, Security, and Delivery

- Use strict TDD for behavior changes: add and run a failing test first, add
  the smallest implementation to pass it, then refactor. Do not backfill tests
  after implementation.
- Keep deterministic, offline mock-LLM unit tests for tool dispatch, guardrail
  interception, feedback-driven correction, memory access, and stopping.
  Include a repeatable mechanism demo showing a blocked dangerous action, a
  feedback-based recovery after an injected failure, and the chosen deep-dive
  mechanism.
- Treat credentials as secrets: never hard-code, commit, print, or place them
  in command history. Implement secure first-run entry, non-revealing status,
  update, and removal; document the threat model and target-machine setup.
- Provide one documented test command and CI that runs it on every push. The
  CI configuration must contain a `unit-test` job; its final recorded run must
  pass. If a distribution method needs an artifact build, include it in CI.
- Deliver the required root artifacts (`SPEC.md`, `PLAN.md`,
  `SPEC_PROCESS.md`, `AGENT_LOG.md`, `README.md`, and `REFLECTION.md`), source,
  distribution instructions/artifacts, CI/CD records, and an accessible WebUI
  deployment URL. `README.md` must cover installation, usage, distribution,
  directory layout, secure key setup, and limitations. `REFLECTION.md` must be
  the student's own 1500--2500-word reflection; AI may only assist with
  polishing when that assistance is disclosed.
- Before committing or opening a PR, check for credentials. Use one isolated
  worktree and one PR per independent task; identify the responsible subagent
  and all human edits in the commit message or PR description.
