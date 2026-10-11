# VesperCode v2

VesperCode is a governance-first Coding Agent Harness. The current source
line is **v2 relaxed identity alpha (`0.2.0a0`)**: it uses ordinary opaque
runtime IDs, revision checks, deterministic policy code, an injectable Mock
LLM, scoped feedback memory, and a fresh SQLite control database.

The released **v1 (`0.1.0`)** contract is frozen and retained as historical
read-only material. V1's SHA-256/content-addressed identity chain is not used
as the v2 authorization model.

## Current status

- v2 offline vertical slice implemented under `src/vespercode/*/v2.py`,
  `runtime_v2.py`, `governance/relaxed_policy.py`, and
  `storage/v2_database.py`.
- Route A (real local filesystem writeback and recovery) is implemented:
  approval-bound atomic CREATE/REPLACE, durable transaction states with a
  journal, restart-safe recovery preview/apply/rollback, and a real
  boundary-checked disk port composed into `V2Harness`.
- Route B1 (candidate/validation/reference-profile identity) is
  implemented as contracts and v3-schema storage: candidate control
  identity with bounded status, diff records bound to candidate revisions
  via ordinary artifact IDs, reference profile records keyed by id +
  revision with declared metadata as configuration, validation run/result
  records with a bounded status/error, and a fail-closed five-key evidence
  binding check.
- Route B2 (disclosure/provider/credential control plane) is implemented
  as contracts, pure policy, v3-schema storage, and the provider call
  boundary: grants keyed by `grant_id`/`disclosure_id` with an explicit
  user approval (`PENDING` → `ACTIVE`), expiry, byte budget, and granted
  source categories/path scopes; per-request authorizations charged
  atomically (scope, budget, replay, and endpoint/profile binding checks
  in one transaction) with a one-shot `AUTHORIZED` → `CONSUMED` state;
  provider endpoints bound to reference profiles by control IDs and
  revisions; an injectable credential port whose redacted secret wrapper
  never leaks a value, length, or derivative — its only accessor is
  capability-gated, with no capability on any public API — and a
  one-call, no-retry provider service that consumes each authorization
  one-shot through a fully revalidating atomic ledger gate (binding,
  status, grant `ACTIVE`/unexpired at the consume-time clock, and
  endpoint/profile binding) before the single transport call, then
  discards raw provider exceptions behind a closed failure code.
- Route B3 (local CLI/WebUI integration) is implemented as a
  standard-library-only, v2-only integration layer: the shared
  `V2LocalShell` composes the Route A harness and the B2 credential
  port behind closed operations (run start behind an injected LLM
  boundary, revision-bound writeback approval/apply with the
  control-plane directory additionally denied, durable recovery
  preview/apply, non-revealing credential/disclosure projections);
  the closed `vespercode-v2` CLI (run, status, writeback, recovery,
  credential-status, disclosure-status, serve — preview by default,
  `--apply` explicit, no provider/secret/shell options); and the v2
  local WebUI (a framework-agnostic app over the shell with the fixed
  HOST → SESSION → ORIGIN → CSRF order, allowlisted typed form
  contracts, the literal `CONFIRM` gate on every mutation, escaped
  bounded HTML, and a single-threaded loopback `http.server` adapter
  that binds `127.0.0.1` only). No new database tables and no
  third-party dependency were introduced.
- Route B4a (Docker validation execution profile and the injectable
  execution/readiness boundary) is implemented as standard-library,
  v2-only contract modules plus injectable ports: an
  `ExecutionProfileRecordV2` keyed by opaque execution-profile and
  reference-profile ids + revisions with fail-closed isolation
  parameters (network disabled, non-root uid:gid, read-only rootfs,
  all capabilities dropped, no docker socket, read-only workspace
  mount, bounded timeout/output ceilings, an opaque local image token
  — no URL, registry/tag, digest spelling, or credential field can be
  represented); a closed `ExecutionActionRequestV2` that binds the B1
  control plane (`run_id`, `candidate_id`, `candidate_revision`) and
  whose argv is a frozen per-kind grammar projection of those control
  fields (a shell command string, or a request naming one candidate
  in its binding and another in its argv, is not representable); a
  `V2ExecutionService` enforcing profile binding → a structural
  citation gate (the production service itself requires the request
  to cite a `validation_run_id`: an uncited request rejects with the
  closed `VALIDATION_BINDING_REQUIRED` code before the binding port
  is even consulted, so no binding-port choice — fake or real — can
  bypass the validation requirement) → control-plane
  binding (an injectable read-only lookup over the request's five
  binding keys — run, candidate, the citation,
  and the reference profile id/revision: unknown or foreign
  run/candidate pairs, stale candidate revisions,
  and missing/foreign/stale/profile-mismatched/corrupted or
  non-PASSED cited validations all reject with zero readiness/executor
  calls) → readiness → exactly one executor call
  with no retry and sanitized, bounded, closed outcomes;
  `V2ExecutionTestService` is the explicitly test-only subclass that
  relaxes exactly the citation gate for the offline fakes
  (non-production, never constructed by any harness, CLI, or WebUI);
  deterministic
  `FakeV2BindingLookup`/`FakeV2Executor`/`FakeV2Readiness` for fully
  offline testing. Route B4b-02A adds the production database-backed
  binding (`DatabaseBackedExecutionBinding`, a read-only adapter over
  the real v2 control database: citation required, run/candidate row
  revalidation, the cited validation bound to the current candidate
  revision under the request's reference profile and terminal PASSED,
  corrupt or missing rows failing closed — no writes, no cache, no
  fake data); and an optional read-only Docker readiness probe
  (`docker image inspect` then `docker info`, closed argv,
  `shell=False`, injectable command runner) — no container is ever
  created, run, pulled, or pushed by the probe, and the unit job
  never touches the real edge. Route B4b-01 adds the opt-in real
  container execution adapter (`SubprocessDockerExecutorV2`, the
  execution plane's second and last subprocess edge): it accepts
  only the closed structured request + profile records (never a
  shell string or arbitrary argv), treats the profile's image token
  as an opaque local image (never pulled, pushed, or built —
  `docker create --pull never` makes the no-pull rule structural),
  runs ONE bounded `docker create` → `docker inspect` (daemon-side
  drift verification before start) → `docker start --attach`
  sequence with network none, the profile's non-root uid:gid,
  read-only rootfs, all capabilities dropped, no docker socket, one
  READ-ONLY workspace bind (operator-configured, never
  request-driven), and frozen memory/pids/cpu/tmpfs bounds, under
  one monotonic timeout budget and a fail-closed output cap; on
  timeout it stops the container, it ALWAYS removes the container
  it created, every drift/overflow/phase failure maps to a closed
  FAILED result with no CLI/daemon error text, and nothing is ever
  retried. The injectable command runner keeps the offline unit job
  deterministic; the real subprocess edge is exercised only by the
  opt-in integration suite.
- Route B4b-02B (the independent v2 alpha wheel/release path) is
  implemented as a separate, manually dispatched workflow
  (`.github/workflows/release-v2-alpha.yml`) that never touches the
  frozen v1 release workflow: it verifies the `0.2.0a0` package
  identity (pyproject version, both console entry points, the package
  `V2_VERSION` pin), runs the documented offline v2 unit suite, builds
  exactly one `vespercode-0.2.0a0-py3-none-any.whl` with the locked
  build toolchain, smoke-installs it with `--no-deps` through
  `vespercode-v2 --help`, and uploads the wheel plus its adjacent
  `<wheel>.whl.sha256` evidence as one CI artifact (`v2-alpha-wheel`).
  The path is read-only (`contents: read`), secretless, and publishes
  nothing — no GitHub Release object, no registry image, no public
  deployment, and no v1 image identity is claimed for v2. The offline
  guard (`tests/unit/v2/process/test_v2_alpha_release_path.py` and the
  extended `tests/unit/v2/test_v2_wheel_contract.py`) pins the package
  identity, the two-entry console boundary (the legacy `vespercode`
  entry stays the frozen v1 CLI; `vespercode-v2` targets
  `vespercode.cli_v2:main`), the wheel member hygiene, and the
  workflow isolation on every push. Route B4b-02C1 gives the B2
  credential and provider ports their production real-plane
  implementations as injectable, offline-testable adapters — the
  OS credential adapter (`credentials/v2_os_store.py`: Windows
  Credential Manager behind an injectable backend port, lazy
  pywin32 imports, fail-closed backend probes, the disjoint
  `vespercode/v2/` target namespace, a metadata-only non-revealing
  status, and no cache) and the real provider transport adapter
  (`providers/v2_transport.py`: the closed built-in provider address
  map, an injectable HTTP edge, strict timeout/body/output bounds,
  one call, no redirect follow, no retry, and full exception
  redaction) — with the storage-reveal capability keeping the raw
  secret inside exactly two capability-gated frames (the OS-store
  write frame and the one provider transport call frame). The
  remaining Route B work — B4b-02C2 (public deployment: any
  non-loopback binding, TLS, or remote operator surface) and the
  wiring of the new adapters (or the B4b-02A binding) into any
  caller — is **not started**.
- v2 tests are deterministic and require no API key, network, Docker, or
  third-party package:

  ```powershell
  $env:PYTHONPATH = (Resolve-Path .\src).Path
  python -m unittest discover -s tests\unit\v2 -v
  ```

- The Route B4b-01 real-Docker integration suite is separate and
  opt-in (NOT part of the recorded test command): it requires the
  docker CLI, a reachable daemon, and a token-named local image
  (tag one first, e.g. `docker tag <image>
  vespercode-validation-image`), skips honestly with the exact
  reason otherwise, mounts only a throwaway temporary workspace
  read-only, and removes the containers it creates:

  ```powershell
  python -m unittest discover -s tests\integration\docker -p "test_v2_execution_adapter.py" -v
  ```

- The Route B4b-02C1 real-WinCred integration suite is separate and
  opt-in (NOT part of the recorded test command): it requires Windows
  with pywin32 and the explicit `VESPERCODE_V2_WINCRED_INTEGRATION=1`
  opt-in (it writes clearly-fake test values to the current user's
  real Credential Manager), skips honestly with the exact reason
  otherwise, refuses to clobber unknown pre-existing entries, deletes
  every entry it creates, and proves zero `vespercode/v2/` residue:

  ```powershell
  $env:VESPERCODE_V2_WINCRED_INTEGRATION = "1"
  python -m unittest discover -s tests\integration\windows -p "test_v2_os_credential_store.py" -v
  ```

- The slice covers run creation, opaque IDs, path/action governance,
  one-call-per-turn loop behavior, feedback correction, scoped memory,
  stopping, candidate revision checks, one-shot writeback approval, real
  writeback/recovery, Windows reparse-point refusal, the Route B3 local
  integration layer (closed CLI, loopback WebUI, shared shell), and the
  Route B4a execution plane (fail-closed Docker validation execution
  profile, closed execution request contract, injectable
  execution/readiness ports with deterministic fakes, and an optional
  read-only Docker readiness probe), the Route B4b-01 real
  container execution adapter (an opt-in, isolated, bounded
  subprocess Docker adapter behind the same ports), the Route
  B4b-02B v2 alpha release path (a manual source-artifact workflow
  isolated from the frozen v1 release), and the Route B4b-02C1
  production credential/transport adapters (the OS credential store
  and the real provider transport boundary, both injectable and
  offline-testable behind the B2 ports).
- The wiring of the production database-backed binding, the OS
  credential adapter, and the real provider transport adapter into
  any caller (loop, CLI, or WebUI) remains Route B work: the shipped
  default port implementation is still the injectable in-memory
  fake, no real network call exists in the offline unit suite, and
  the real WinCred backend is proven only by the opt-in integration
  suite; v1 implementations are not silently reused as v2 identity
  gates.

## Version and compatibility boundary

| Line | Database | Identity semantics | Status |
|---|---|---|---|
| `0.1.0` | caller-selected legacy SQLite | SHA-256/canonical digest bindings | frozen, read-only history |
| `0.2.0a0` | `vespercode-v2.sqlite` | UUID references + integer revisions | current source alpha |

Do not point the v2 initializer at a v1 database. V2 refuses any database that
contains the v1 `schema_migrations` table, including mixed v1/v2 metadata. V1
and v2 candidate trees, evidence, approvals, and database rows are not
implicitly interoperable.

## Reference image digest verification

The reference-image digest instructions belong to the frozen v1 release only.
V2 does not pull, compare, or authorize execution from a Docker image digest.
For historical v1 verification, use the release record and the frozen
`README_v1_frozen.md`; do not treat that evidence as a v2 startup requirement.

## Installation

The repository's full historical v1 environment targets Python 3.12. The v2
offline slice uses only the Python standard library and is supported on
`>=3.12,<3.13`, matching package metadata. The distribution exposes two
console entry points: the legacy `vespercode` script still targets the
frozen v1 CLI (a v1 compatibility surface that v2 never imports), and the
new `vespercode-v2` script targets the closed v2 local CLI
(`vespercode.cli_v2:main`) added in Route B3. The v2 alpha wheel is
produced by the B4b-02B release path (the manual
`release-v2-alpha.yml` workflow builds it and uploads it as a CI
artifact); installing and exercising the wheel locally remains the
responsibility of the pytest/pipx-gated package smoke environment,
which was not run on the current offline host. From a source
checkout, run the CLI through `python -m vespercode.cli_v2` with
`PYTHONPATH=src`.

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -m unittest discover -s tests\unit\v2 -v
python -m compileall -q src\vespercode\contracts\v2_identity.py `
  src\vespercode\governance\relaxed_policy.py `
  src\vespercode\storage\v2_database.py `
  src\vespercode\llm\v2.py `
  src\vespercode\memory\v2.py `
  src\vespercode\tools\v2_dispatcher.py `
  src\vespercode\loop\v2_engine.py `
  src\vespercode\runtime_v2.py
```

The documented test command is the v2 unit command above. CI must keep a
`unit-test` job on every push and run that command without credentials.

## Usage

The v2 composition root is injectable and offline:

```python
from pathlib import Path

from vespercode.llm.v2 import ScriptedLLMV2
from vespercode.runtime_v2 import V2Harness, V2HarnessConfig

root = Path("C:/work/example")
harness = V2Harness(V2HarnessConfig(root, root / ".vespercode"))
try:
    result = harness.run(
        "repair the failing example",
        ScriptedLLMV2([
            {"action_type": "REPLACE", "path": "tests/test_example.py", "content": "bad"},
            {"action_type": "REPLACE", "path": "src/example.py", "content": "fixed"},
            {"action_type": "DONE"},
        ]),
    )
finally:
    harness.close()
```

The first write is denied by deterministic governance; its feedback is scoped
to the run and presented to the next turn; the second write is allowed; DONE
settles the run. The in-memory staging port is deliberately not an authority
for real repository writeback — real files are only written by the explicit
writeback flow below.

### Real filesystem writeback (Route A)

After a run stages content, the harness can record it as a candidate and
write it to the real workspace only after an explicit approval:

```python
from vespercode.contracts.v2_writeback import WritebackRequestV2
from vespercode.llm.v2 import ScriptedLLMV2
from vespercode.runtime_v2 import V2Harness, V2HarnessConfig
from pathlib import Path

harness = V2Harness(V2HarnessConfig(Path("my-workspace"), Path("my-control")))
try:
    result = harness.run("repair the example", ScriptedLLMV2([...actions...]))
    identity = harness.stage_candidate(result.run_id)
    approval_id = harness.database.create_writeback_approval(
        run_id=result.run_id,
        candidate_id=identity.candidate_id,
        candidate_revision=identity.revision,
    )
    outcome = harness.writeback_service.request_writeback(
        WritebackRequestV2(
            run_id=result.run_id,
            candidate_id=identity.candidate_id,
            candidate_revision=identity.revision,
            approval_id=approval_id,
            operations=harness.staged_operations(),
        )
    )
finally:
    harness.close()
```

Stale candidates, missing or consumed approvals, policy denials, duplicate
targets, and CREATE/REPLACE mismatches return without touching a single
file. A fault mid-write leaves a durable `UNRESOLVED` transaction; a new
harness over the same control database recovers it:

```python
for transaction_id in harness.recovery_service.pending_transaction_ids():
    preview = harness.recovery_service.preview(transaction_id)
    if not preview.blocked:
        harness.recovery_service.apply(transaction_id)   # or rollback(...)
```

Recovery compares ordinary bytes against the durable journal; a target that
matches neither the journal nor its recorded original blocks recovery
fail-closed.

### The v2 local CLI (Route B3)

`vespercode-v2` (or `python -m vespercode.cli_v2` from a source checkout)
is the closed, offline, loopback-only v2 command line over one workspace.
Writeback and recovery are **previews by default**; nothing is written
without `--apply`:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -m vespercode.cli_v2 run --workspace C:\work\example --task "repair the failing example"
python -m vespercode.cli_v2 status --workspace C:\work\example
python -m vespercode.cli_v2 writeback --workspace C:\work\example --task "repair the failing example"            # preview only
python -m vespercode.cli_v2 writeback --workspace C:\work\example --task "repair the failing example" --apply     # approval + atomic write
python -m vespercode.cli_v2 recovery --workspace C:\work\example                                                   # list pending
python -m vespercode.cli_v2 recovery --workspace C:\work\example --transaction-id <ID>                              # preview one
python -m vespercode.cli_v2 recovery --workspace C:\work\example --transaction-id <ID> --apply                     # apply it
python -m vespercode.cli_v2 credential-status --workspace C:\work\example --provider openai
python -m vespercode.cli_v2 disclosure-status --workspace C:\work\example
python -m vespercode.cli_v2 serve --workspace C:\work\example                                                     # loopback WebUI on 127.0.0.1:8766
```

Notes, honestly bounded: the command grammar is closed — there is no
shell, argv passthrough, provider URL, secret, policy, or profile
option, `--provider` exists only as the bounded lookup key of the
non-revealing `credential-status`; `run` and `writeback` need an LLM
boundary composed by the caller (the shipped default composes none, so
they fail closed with `NO_LLM_BOUNDARY` — no real provider transport
exists in this slice); a `writeback` runs its own loop pass because
staged content is process-local by Route A's architecture, and a fresh
process cannot apply a previous process's staging (use the durable
`recovery` commands); the control database lives under
`<workspace>/.vespercode` and is additionally denied to writeback, so
staged content can never replace it even after an approval.

### The v2 local WebUI (Route B3)

`vespercode-v2 serve` composes the same shell into a local WebUI and
serves it on the literal loopback host only (`127.0.0.1`, default
port 8766) through the standard library's `http.server` — no FastAPI,
no third-party package, single-threaded, and nothing about a request
is logged. Open `http://127.0.0.1:8766/` in a browser on the same
machine; a safe read establishes a local session automatically, and
every mutation form requires the page's CSRF token, the literal
`CONFIRM`, and the bound opaque run/candidate/revision/transaction
IDs. Pages carry only bounded control-plane facts: statuses, revisions,
counts, and timestamps — never a secret, file content, or request body.
Requests authorize through the manager-bound boundary in the fixed
HOST → SESSION → ORIGIN → CSRF order: the session check resolves the
cookie through the WebUI's own session manager and requires a
registered, still-live session — a forged or expired session value
rejects before any form parsing or domain call, and no session-taking
authorization variant exists, so no route handler can bypass the
manager by passing an arbitrary session object. State-changing
requests additionally require a loopback Origin matching the request's
own Host and the session's CSRF token; safe reads require neither,
and a GET that fails only the session check auto-establishes a fresh
session from the same manager.
The WebUI shares the single-threaded server with its shell, so serve it
from the process that owns the workspace (the `serve` command does
exactly that; restarts log browsers out because sessions are in-memory
and bounded).

## Repeatable v2 mechanism demo

Run:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python scripts\run_v2_demo.py --report tests\.tmp\v2-demo-report.json
```

The report demonstrates the three required Harness behaviors: a blocked
dangerous action, feedback-driven recovery, and the revision-bound governance
mechanism. It contains statuses and bounded messages only; no credentials or
file bodies are emitted.

## Directory layout

```text
src/vespercode/contracts/v2_identity.py   # opaque UUID reference types
src/vespercode/contracts/v2_writeback.py   # frozen writeback/port contracts
src/vespercode/contracts/v2_validation.py  # validation run/result + evidence binding (Route B1)
src/vespercode/candidate/v2_candidate.py   # candidate control identity + diff records (Route B1)
src/vespercode/profiles/v2_reference.py    # reference profile record (Route B1)
src/vespercode/profiles/v2_endpoints.py    # provider endpoint record (Route B2)
src/vespercode/governance/v2_disclosure.py # grant/authorization records + pure scope/budget/expiry policy (Route B2)
src/vespercode/credentials/v2_port.py     # injectable credential port + redacted secret wrapper (Route B2)
src/vespercode/credentials/v2_os_store.py # production OS credential adapter: Windows Credential Manager backend, fail-closed probes (Route B4b-02C1)
src/vespercode/providers/v2_call.py        # one-call, no-retry provider boundary (Route B2)
src/vespercode/providers/v2_transport.py  # real provider transport adapter: closed address map, injectable HTTP edge, strict bounds (Route B4b-02C1)
src/vespercode/governance/relaxed_policy.py
src/vespercode/storage/v2_database.py     # fresh v2 SQLite schema (v3)
src/vespercode/llm/v2.py                  # injectable scripted LLM seam
src/vespercode/memory/v2.py               # run-scoped feedback memory
src/vespercode/tools/v2_dispatcher.py     # policy-first tool dispatch + staging port
src/vespercode/loop/v2_engine.py          # self-owned main loop
src/vespercode/workspace/v2_boundary.py   # real path/object boundary
src/vespercode/workspace/v2_disk.py      # atomic real-disk workspace port
src/vespercode/persistence/v2_writeback.py # approval-bound atomic writeback
src/vespercode/persistence/v2_recovery.py  # durable recovery preview/apply/rollback
src/vespercode/runtime_v2.py              # v2 composition root
src/vespercode/shell_v2.py                # local services shell shared by CLI/WebUI (Route B3)
src/vespercode/web/v2_security.py         # loopback security boundary (Route B3)
src/vespercode/web/v2_forms.py            # typed allowlisted form contracts (Route B3)
src/vespercode/web/v2_app.py              # framework-agnostic WebUI application (Route B3)
src/vespercode/web/v2_server.py           # stdlib loopback server adapter (Route B3)
src/vespercode/cli_v2.py                  # closed v2 CLI (`vespercode-v2`, Route B3)
src/vespercode/execution/v2_profile.py    # execution profile record, opaque ids + revisions (Route B4a)
src/vespercode/execution/v2_execution.py  # execution request/result/outcome contracts + ports (Route B4a)
src/vespercode/execution/v2_executor.py   # execution service + deterministic fakes (Route B4a)
src/vespercode/execution/v2_docker_probe.py # optional read-only Docker readiness probe (Route B4a)
src/vespercode/execution/v2_docker_executor.py # opt-in real container execution adapter (Route B4b-01)
tests/unit/v2/                            # offline v2 tests
tests/integration/docker/test_v2_execution_adapter.py # opt-in real-Docker integration test (Route B4b-01)
scripts/run_v2_demo.py                    # repeatable mechanism demo
scripts/run_v2_execution_probe_demo.py    # opt-in read-only Docker probe evidence script (Route B4a)
SPEC.md                                    # current v2 contract
PLAN.md                                    # current v2 execution plan
SPEC_v1_frozen.md / PLAN_v1_frozen.md     # read-only v1 contract history
README_v1_frozen.md                       # read-only v1 README history
```

## Secure key setup

The v2 alpha makes no real external-provider call by default and therefore
accepts no API key through any CLI argument or web form. The Route B2
credential port (`credentials/v2_port.py`) enforces the storage rules:
hidden input is wrapped in a redacted, non-comparable, non-serializable
secret object; the two accessors are capability-gated — `reveal` requires
the provider-call reveal capability (only the provider call boundary
obtains it, between its own frame and the single transport edge) and
`reveal_for_storage` requires the storage capability (only the OS
credential adapter obtains it, between the storage extraction and the
backend write) — no public API of the package exposes either capability,
and the two are never interchangeable, so ordinary direct use of a wrapper
cannot obtain the raw secret; status output carries the provider, a
configured flag, and an update time — never a value, length, or
derivative; and no v2 table has a column that could accept a credential.

B4b-02C1 adds the production OS-backed implementation behind the same
port (`credentials/v2_os_store.py`): `OSV2CredentialProvider` over the
target platform's secure OS credential store (Windows Credential Manager
on supported Windows). It is an injectable production adapter, not a
wired caller: the local shell and CLI keep the deterministic in-memory
fake as their default (process-local, always reporting
`configured: no` in a fresh process). Its security contract: the
platform libraries (`win32cred`/`pywintypes`) are optional and imported
lazily inside functions only, so the v2 wheel stays standard-library
only and a host without them fails closed with a static closed error
(never a fallback backend, file store, or environment import); every
operation first proves the backend (identity in the closed backend set
plus a real write/read/delete probe cycle of the backend's own
`vespercode/v2/probe` target); credentials are stored under the
`vespercode/v2/credential/<provider>` namespace of the current user's
store (disjoint from the probe target and from all v1
`vespercode/v1/` targets — the v1 credential service is never the v2
authority); `set` re-verifies the backend after the write and retains
nothing; `get_for_call` re-probes and reads fresh with no cache;
`status` reads metadata only (the stored value is never decoded on the
status path); `clear` deletes idempotently; and an unavailable,
unsafe, malformed, or identity-mismatched backend or entry fails
closed with a static closed error that never carries the secret, its
length, or any derivative.

The corresponding real transport adapter (`providers/v2_transport.py`)
sends to exactly the declared provider endpoint/profile: no URL,
`base_url`, header set, argv, or shell input is accepted anywhere; the
sole trusted destination derives from the closed built-in provider
address map; the request body is the bounded control-plane projection;
exactly one HTTP call happens per authorization with the closed
timeout, no redirect following, and no retry; and every failure maps
to one closed static outcome — the response body and the credential
never appear in any response, outcome, record, or database byte.

The Route B3 CLI and WebUI add no key entry point at all: no CLI
argument or web form accepts a secret, a provider URL, or a credential
— the only provider-shaped input is the bounded `--provider` lookup
key of the non-revealing `credential-status` command. The real OS
backend can be proven by the opt-in Windows integration suite:

```powershell
python -m unittest discover -s tests\integration\windows -p "test_v2_os_credential_store.py" -v
```

It requires Windows with pywin32 and the explicit
`VESPERCODE_V2_WINCRED_INTEGRATION=1` opt-in (it writes clearly-fake
test values to the current user's real Credential Manager, refuses to
clobber unknown pre-existing entries, deletes what it creates, and
proves zero `vespercode/v2/` residue); it skips honestly with the
exact reason otherwise.

The v2 policy treats model output, repository text, tool results, and memory
as untrusted. It does not grant shell execution, arbitrary executable paths,
arbitrary arguments, Docker socket access, or network access. A policy DENY
cannot be turned into ALLOW by a user approval field or by changing an opaque
ID.

## Distribution

The v2 alpha is currently distributed from source for offline evaluation; the
v2 alpha wheel and deployment are versioned separately from the v1 release at
every boundary. The B4b-02B release path is the separate, manually dispatched
`.github/workflows/release-v2-alpha.yml` workflow: it verifies the `0.2.0a0`
identity, runs the offline v2 unit suite, builds exactly one
`vespercode-0.2.0a0-py3-none-any.whl` with the locked build toolchain,
smoke-installs it with `--no-deps` through `vespercode-v2 --help`, and uploads
the wheel plus its `<wheel>.whl.sha256` evidence as the `v2-alpha-wheel` CI
artifact (30-day retention). The path is read-only and secretless and
publishes nothing: no GitHub Release object, no registry image, no public
deployment, and no v1 image identity for v2 authorization. The frozen v1
release workflow stays byte-unchanged and pinned to its own v1 admission
identity; note that it triggers on every pushed `v*` tag and fails closed on
those pins, so pushing a v2 alpha tag starts it to no effect — the v2 alpha
path needs no tag at all. Packaging is guarded on every push: every v2
production module
must be declared in the wheel package contract
(`REQUIRED_RUNTIME_MEMBERS` in `tests/smoke/package/test_wheel_contents.py`)
and covered by the Hatchling wheel selection; the offline guards
`tests/unit/v2/test_v2_wheel_contract.py` (member/metadata/entry-point
coherence) and
`tests/unit/v2/process/test_v2_alpha_release_path.py` (release-path
isolation) fail the unit job when a v2 module is missing from either, when
the two console entries drift, or when the release paths mix identities, so
source-only test passes cannot hide a wheel that would omit v2 code.
Building and installing the actual wheel locally
remains the responsibility of the separate pytest/pipx-gated package smoke
environment. The v1 release remains available at:

- Release: <https://github.com/ledstevenovo/VesperCode/releases/tag/v0.1.0>
- Historical public simulation: <https://vespercode-demo.onrender.com>
- Historical health endpoint: <https://vespercode-demo.onrender.com/healthz>

Those URLs expose the frozen v1 simulation, not a v2 local-workspace service;
they do not imply that v2 has public repository, credential, Docker, or real
LLM capability.

If containerizing the v2 alpha after the integration tasks are complete, use
the standard commands and document the exact image version separately:

```powershell
docker build -t vespercode-v2:local .
docker run --rm --network none vespercode-v2:local
```

No container image digest is a v2 identity or authorization requirement.

## Web UI

Route B3 ships a v2 local WebUI: `vespercode-v2 serve` binds the literal
loopback host `127.0.0.1` only (default port 8766) through the standard
library's `http.server`, with the fixed HOST → SESSION → ORIGIN → CSRF
request order whose session check is manager-bound (the cookie must
resolve to a session registered in and live at the WebUI's own session
manager — forged or expired session values reject before any form
parsing or domain call), bounded in-memory sessions, allowlisted typed
forms, the `CONFIRM` gate on every mutation, escaped bounded HTML, and
silent request logging. It is a local single-user tool: any process on the
same machine that can reach the loopback port can talk to it, sessions
die with the serve process, and no public deployment exists (B4 is not
started). The historical Render URL below is the fixed v1 simulation and
cannot access a caller's workspace, credentials, or v2 database.

- Historical public simulation: <https://vespercode-demo.onrender.com>
- Historical health endpoint: <https://vespercode-demo.onrender.com/healthz>

## CI/CD

The current `unit-test` GitHub Actions job runs the documented offline v2
command, `python -m unittest discover -s tests/unit/v2 -v`, on every push and
pull request. The protected v1 release workflow is not a v2 identity or
authorization path; do not use it to publish a v2 alpha. The v2 alpha
release path is the separate, manually dispatched
`.github/workflows/release-v2-alpha.yml` workflow (B4b-02B): read-only
(`contents: read`), secretless, publishing nothing beyond the
`v2-alpha-wheel` CI artifact, and never touching the frozen v1 release
workflow (which stays byte-unchanged, triggered only by its own `v*` tag
admission and its own frozen v1 pins).

## Limitations

- The agent loop stages in memory; real files are written only through the
  approval-gated writeback service. Writeback does not create intermediate
  directories: a target whose parent directory does not exist is a mismatch,
  not an implicit `mkdir -p`.
- REPLACE publication is compare-and-publish: immediately before the atomic
  replace, the target must still hold exactly the bytes observed at preflight
  (ordinary byte/text comparison; no digest). An external modification is
  refused with a durable `UNRESOLVED` transaction and zero unsafe overwrite.
  A residual micro-window remains between that comparison and the rename —
  neither Win32 nor POSIX offers an atomic compare-and-rename — and recovery
  drift detection still fails closed after any such event. Targets that are
  not valid UTF-8 are refused rather than compared.
- Recovery rollback is content-bound in both directions: removing a file a
  writeback created compares the current bytes to the journaled content
  immediately before the unlink, and restoring a replaced file expects the
  applied bytes, so externally changed content is refused (FAILED, the
  transaction stays non-terminal) rather than deleted or overwritten. The
  workspace port protocol exposes no unbound removal.
- Writeback content is UTF-8 text; binary files are out of scope for this
  alpha. The durable journal stores staged file content in the local v2
  control database (required for recovery); sensitive paths are denied by
  policy, and a deterministic conservative marker scanner refuses
  secret-like staged content and secret-like REPLACE originals before the
  approval is consumed — zero writes, a PENDING approval, and no
  transaction. The scanner is marker-based: it can refuse benign code
  that merely mentions credential handling (documented false positive)
  and cannot catch an unstructured random secret with no recognizable
  marker (documented gap).
- Recovery refuses corrupted journals before any state advance: an active
  transaction with no journal rows, rows bound to a different transaction,
  non-contiguous positions, or malformed row shapes raise a closed failure
  that leaks no journal content, and the transaction is never advanced to
  a terminal state.
- A crash between a temporary file write and the atomic publish can leave an
  orphaned `.vespercode-v2-*.tmp` file in the workspace; recovery does not
  sweep these automatically. Win32 has no directory fsync, so a power loss
  in a narrow window after `COMMITTED` could theoretically lose the rename.
- The alpha has no real LLM provider or external disclosure path. In
  particular the B3 surfaces compose no LLM by default: `run` and
  `writeback` fail closed with `NO_LLM_BOUNDARY` until a caller
  injects an LLM boundary, and no CLI argument or web form can supply
  one (no provider URL, secret, or transport exists on either surface).
- Route B4b-02C1 additions: the production OS credential adapter and
  the real provider transport adapter exist as injectable
  implementations behind the B2 ports, but neither is wired into any
  caller — the shipped default remains the in-memory fake. The real
  Windows Credential Manager backend needs pywin32 (not carried by
  the standard-library-only v2 wheel) and fails closed with a static
  closed error without it; it is proven only by the opt-in
  integration suite
  (`tests/integration/windows/test_v2_os_credential_store.py`:
  Windows + pywin32 + `VESPERCODE_V2_WINCRED_INTEGRATION=1`, honest
  skips otherwise). The real httpx HTTP edge is never exercised by
  any recorded run (the offline unit suite uses injectable fake edges
  only), its request body is the bounded control-plane projection —
  not authorized content (the content-bearing completions payload is
  a later slice) — and its read timeout is enforced by the edge
  itself as passed by the adapter (a non-cooperating injected edge
  could ignore it; the edge is a trusted seam). A composed provider
  call proves the control plane permitted it and the transport
  boundary executed — no recorded run has contacted a real provider.
- Route B3 additions: staged content is process-local (Route A's
  architecture), so the shell binds each run's writeback to the staged
  operations observed when that run was staged — a fresh process cannot
  apply a previous process's staging and must use durable recovery; the
  WebUI session store is in-memory and bounded (restarts log browsers
  out; safe reads re-establish sessions automatically); the WebUI task
  bound is 4096 characters, the same as the CLI's; the serve
  composition shares one SQLite control connection with its shell, so
  the WebUI must be served by the thread that created its shell (the
  `serve` command does; an embedding that serves from another thread
  fails loudly with SQLite's thread check); 413/415 rejections drain
  the rejected body bounded (16 MiB cap) so ordinary over-post clients
  can read the rejection, but a larger body is abandoned and the
  connection closes after the rejection. B4b-02B release automation is
  complete as a manual source-artifact workflow; B4b-02C1 (the OS
  credential adapter and the real provider transport boundary) is
  complete as injectable, offline-testable adapters; B4b-02C2 public
  deployment is **not started**.
- Route B4a additions: the execution profile is configuration
  identity, not an authorization gate — it cannot prove image bytes
  match a pinned reference (the v1 digest chain is deliberately
  gone), so a profile revision only declares which configuration the
  operator bound.  The request binds the B1 control plane (run,
  candidate, and the candidate's current revision) through an
  injectable read-only lookup: B4a shipped the deterministic fake and
  a test-local adapter, and B4b-02A shipped the production read-only
  database-backed binding (with the validation-citation gate) — but
  the binding is UNWIRED into any caller and check-time only, and the
  execution plane
  still has no harness/CLI composition and no persistence of its own
  (one-shot consume, profile persistence, and validation-execution
  recording remain future wiring); its
  real subprocess edges are never exercised by the offline unit job
  (both edge modules' unit tests run against the injectable fake
  runner; the real edges are opt-in integration-only).  The optional
  read-only probe resolves the opaque image token verbatim
  (`docker image inspect <token>`), so on hosts whose images exist
  only under registry/tag spellings (the closed token charset
  excludes `:` and `/`) readiness honestly answers
  IMAGE_NOT_AVAILABLE even though a tagged image is present — the
  operator works around this by tagging a local image to the token
  (`docker tag <image> vespercode-validation-image`); a persisted
  token-to-reference mapping table remains future wiring.
- Route B4b-01 additions (the real container execution adapter): the
  adapter is opt-in and operator-driven — no v2 code composes it
  automatically; it exists to be wired behind the B4a service gates
  (profile binding → control-plane binding → readiness) by explicit
  operator code, and the offline unit job drives it only through the
  injectable fake runner.  The profile's `image_reference` is an
  opaque LOCAL image token: the adapter never pulls, pushes,
  builds, or parses a content digest (`docker create --pull never`
  makes the no-pull rule structural — an absent image is a
  fail-closed create error), and no registry credential exists
  anywhere in the argv.  The adapter freezes the resource bounds the
  v2 profile record does not represent (CPU 2, memory 2 GiB, pids
  256, a 256 MB `/tmp` tmpfs, a 30 s cleanup timeout); the profile
  supplies only the run timeout and the output cap, and the
  workspace mount comes from adapter configuration, never from a
  request.  Honest limits: a workspace path containing a comma is
  rejected at construction (the `--mount` value is comma-delimited);
  cleanup is best-effort — if the daemon becomes unreachable after a
  container was created, a stopped (or, after a failed stop, still
  running) container can be left behind for the operator to remove,
  and a failed cleanup never changes the already determined result;
  on timeout the runner kills the CLI attach process and the
  adapter then issues `docker stop --time 0`; and the binding gate is
  still check-time only — a candidate can advance between the
  binding lookup and the real run (one-shot consume of the binding
  is B4b-02 database wiring).  The recorded real-daemon evidence run
  produced FAILED (exit 1) because the operator-tagged demo image
  has no `vespercode-validate` entrypoint — no SUCCEEDED run over
  the real daemon is claimed.
- Route B4b-02B additions (the v2 alpha release path): the workflow is
  manual (`workflow_dispatch`) and publishes nothing — the
  `v2-alpha-wheel` artifact is a transient CI artifact (30-day
  retention), not a distribution channel, so the alpha is still
  installed from source for evaluation; the real wheel build/install
  smoke inside the workflow has not been executed on this offline host
  (no `build`, pytest, or pipx here) and is not claimed — it is
  defined by the committed workflow and pinned by the offline static
  contract; and the frozen v1 release workflow still triggers on
  every pushed `v*` tag (it fails closed on its own v1 admission
  pins), so pushing a v2 alpha tag is pointless — the v2 alpha path
  requires no tag and binds to the checked-out source commit.
- Route B1 validation records are control-plane facts only: they prove
  which candidate revision a run recorded under which reference profile
  revision, not that bytes are unchanged across processes or machines, and
  no validation execution is recorded from a real run yet (the B4b-01
  container adapter exists behind the execution ports and the B4b-02A
  database binding resolves cited validation records read-only, but no
  caller composes them to execute and record a real validation run).
  Terminal outcomes
  are written only while the recorded binding is still current (the
  candidate has not advanced and the referenced profile revision
  still revalidates); a drifted run stays PENDING instead of
  terminalizing misleading evidence. The bounded error message is the only
  diagnostic retained. The v1 digest-bound
  candidate/validation/reference modules remain untouched read-only
  legacy and are never imported by the v2 identity modules.
- Revision checks detect control-plane state changes; they do not prove that
  bytes are unchanged across processes or machines.
- Windows symlink/reparse behavior requires the dedicated Windows integration
  environment before claiming production-grade path safety; junction
  (reparse-point) tests run on ordinary Windows hosts, and the symlink test
  skips where creation is unavailable.
- V1 digest modules, release evidence, and tests remain in the repository as
  legacy history. Their presence does not mean v2 provides the same
  content-integrity guarantee.

## Process and verification records

The migration rationale and interrupted-session decisions are recorded in
`SPEC_PROCESS.md` and `AGENT_LOG.md`. Before claiming completion, run the v2
unit command, syntax compilation, `git diff --check`, and the repository's
credential scan. Never commit API keys, `.env` files, credentials, or command
history containing secrets.

## B4b-02C2: public deployment intentionally not implemented

The real v2 Harness remains a local single-user tool. `vespercode-v2 serve` binds `127.0.0.1` only; no public v2 service or URL is claimed. Public deployment is intentionally excluded until a separate multi-user security design covers authentication, tenant/workspace isolation, cloud credential storage, TLS, quotas, audit retention, and remote sandboxing.
