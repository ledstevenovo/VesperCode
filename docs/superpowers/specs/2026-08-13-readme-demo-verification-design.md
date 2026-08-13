# README Demo Verification Guide Design

## Goal

Make the repository landing page immediately usable for course evaluation: a reviewer can find every public delivery link, understand the actual product form, and complete the fixed public Demo verification without searching through the rest of the README.

## Scope

Modify only `README.md`. Do not change product code, tests, workflows, Render configuration, delivery evidence, reflection text, release `v0.1.0`, or the frozen product identity.

## Information architecture

Insert two sections directly after `## 当前状态` and before the technical reference-image digest section:

1. `## Project links` — GitHub repository, `v0.1.0` Release, public Render Demo, `/healthz`, and final main CI.
2. `## Public Demo verification` — the exact fixed interaction sequence and expected outcomes.

The verification section begins with a concise boundary statement: the assessed product is a Windows-local Coding Agent Harness delivered as source, wheel, local WebUI, and a controlled Docker validation environment; Render is a credential-free fixed simulation for public evaluation.

## Verification sequence

Document these observable steps:

1. Open the Demo and confirm the `SIMULATION` banner and absence of prompt, repository upload, provider, and secret inputs.
2. Start a session.
3. Execute four next steps and observe `DENIED`, `DENIED`, `CHECK_FAILED`, `DENIED` for the four named patch actions.
4. Continue once more and observe `DEMO_WAITING_USER`; reject and observe `FINAL_WRITEBACK REJECTED`.
5. Approve and observe `FINAL_WRITEBACK COMPLETED`, `DEMO_COMPLETED`, and all three action controls disabled.
6. Open `/healthz` and expect HTTP 200 with the exact simulation JSON body.

Mention the Render Free cold-start delay of 50 seconds or more as an expected platform limitation.

## Validation

- Run `scripts/verify_readme_contract.py README.md`.
- Run the changed-file credential scan and `git diff --check`.
- Confirm every documented URL and state token matches already recorded T37 evidence.
- Review the final README diff to ensure no unrelated section is rewritten.
