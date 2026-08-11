# GitHub Release and Render Delivery Design

## Goal

Complete T37 through one fail-closed GitHub-native release path: publish the
`v0.1.0` Windows wheel and the frozen reference OCI image, deploy the isolated
Demo on Render Free, record only terminal external facts, and make the live
delivery gate pass without skips, invented evidence, paid resources, or tag
rewrites.

## Frozen decisions

- GitHub is the authority for source, tag, Release, Actions, and GHCR.
- The release tag is `v0.1.0`, matching `pyproject.toml` version `0.1.0`.
- The published reference image identity is exactly
  `sha256:cf0b6c5ccac588fccd07c3b9f050bff4daf550ac6e518fd06efb6e988ab1d823`.
- Render uses the committed Blueprint, the `main` branch, the Free plan, no
  disk, no database, no real-provider secret, and no paid upgrade.
- A published tag is immutable. No workflow may move, delete, or recreate it.
- Infrastructure failures may be retried at most twice. Required checks are
  never skipped or bypassed.

## Considered approaches

### 1. GitHub-native protected workflow (selected)

Use a repository `release` Environment, an immutable `v*` tag ruleset, a
GitHub Actions workflow, `GITHUB_TOKEN`, GitHub Release, and GHCR. This uses the
already-authoritative repository, supports public artifacts without storing a
new long-lived token, and can produce one source-aligned observation artifact.

### 2. Complete the dormant GitLab publisher

This would match the old static contract, but there is no GitLab project,
protected tag, Windows runner, or configured variables. Creating and operating
that platform adds an unrelated second authority and cannot complete
unattended with the current external state.

### 3. Manual local publication

Local `gh` and `docker push` could be faster, but publication would not be
admitted by a protected CI environment and its evidence would be harder to
reproduce. It remains an emergency diagnostic path, not the delivery path.

## Architecture

### Protected admission

The repository has one `release` Environment. It has no required reviewer so
the approved unattended run can finish, but it admits only release tags. A
repository ruleset matches `refs/tags/v*` and rejects tag update and deletion.
The ordinary `ci.yml` remains read-only. Only the publication job in
`release.yml` receives `contents: write` and `packages: write`.

The workflow accepts strict `tag_name` and `source_commit` inputs. Before any
write, it resolves the remote tag commit, requires the tag to be `v0.1.0`,
requires the package version to be `0.1.0`, requires `source_commit` to be 40
lowercase hexadecimal characters, and requires the tag commit to equal that
frozen source commit selected after the C1 PR merges and its `main` CI succeeds.

### Wheel path

A Windows GitHub-hosted job checks out the tag, installs the committed locked
development environment, builds exactly one wheel, computes its lowercase
SHA-256, creates an isolated virtual environment, installs that wheel, and
runs `vespercode --help`. It uploads the wheel and checksum as workflow
artifacts. The publishing job refuses zero or multiple wheels, a malformed
checksum, or a recomputation mismatch.

### Reference image path

A Linux job checks out the same tag and invokes the existing frozen reference
image smoke driver. That driver reproduces and loads the Task-2 OCI identity,
proves the loopback registry round trip, fixture, executor, and isolation
contracts, and leaves the verified local image tagged
`vespercode-reference:local`.

The publication job logs in to GHCR with the ephemeral `GITHUB_TOKEN`, retags
the verified local identity, and pushes
`ghcr.io/ledstevenovo/vespercode-reference:v0.1.0`. It reads the resulting
RepoDigest, requires it to equal the frozen digest, removes the local release
tag, pulls by digest, and requires the pulled RepoDigest to equal the same
value. Any registry transformation that changes the manifest fails closed and
prevents Release creation.

### GitHub Release and observation

Only after wheel installation, image smoke, push, pull, and all identity checks
pass does the workflow create the public GitHub Release. The wheel and checksum
are its only binary attachments. The workflow writes a non-secret JSON
observation artifact containing the source commit, tag, release id/URL, Actions
run id/URL, wheel SHA-256, frozen manifest digest, GHCR RepoDigest, pulled
digest, terminal booleans, and UTC timestamp. T37 consumes this artifact
through the existing `verify_release_publication_result` contract before
writing `release-v1.json`.

### Render deployment

After release succeeds, a narrow delivery commit replaces only the
`SOURCE_COMMIT` placeholder in `render.yaml` with the frozen release commit.
The existing Render Blueprint creates `vespercode-demo` from `main` on the Free
plan. The deployment is accepted only when Render reports terminal success,
`GET /healthz` succeeds from the public internet, the closed Demo route surface
is observed, and the deployed configuration contains the exact frozen source
identity with no disk, database, repository credential, or secret.

### Evidence and finalization

The three records are written together from terminal observations:

- `ci-v1.json`: the successful source-aligned release Actions run.
- `release-v1.json`: GitHub Release, wheel, GHCR, pull, and digest facts.
- `deployment-v1.json`: Render deployment id, public URL, source identity, and
  confirmed Demo image identity.

All three records share one `source_commit`; release and CI share one run id
and URL; all timestamps are timezone-qualified and less than 24 hours old when
the live gate runs. README, PLAN, AGENT_LOG, and SPEC_PROCESS are updated only
after these facts exist. The terminal PR may change documentation and evidence
after the tagged source commit; it never changes or retargets the release tag.

## Error handling

- Source, tag, version, wheel count, checksum, or digest mismatch: stop before
  external publication.
- GHCR push followed by digest mismatch: do not create the GitHub Release; do
  not alter the frozen tag; report the failed publication truthfully.
- GitHub or runner transient failure: retry the same immutable run at most two
  times.
- Render asks for payment, credit card, reauthentication, or a non-Free plan:
  stop Render mutation and retain the already-valid GitHub release.
- Render deployment or public smoke failure: do not write successful
  deployment evidence and do not terminalize T37.
- Any required gate failure: fix within task scope and rerun; never skip,
  deselect, or admin-merge around it.

## Verification

- Static tests parse `release.yml` and require the exact triggers, permissions,
  environment, tag/version/source checks, Windows wheel smoke, frozen digest,
  GHCR push/pull, Release attachments, and observation artifact.
- Existing publication verifier tests cover deterministic mismatch priority.
- Existing Render tests cover the closed Blueprint and deployment matrix.
- Before C1 merge: target/domain tests, ruff, mypy, credential scan, diff check,
  and GitHub CI.
- Before external publication: the frozen `main` SHA has all three CI jobs
  green and the tag is absent.
- Before completion: live release evidence, public health/Demo smoke, all T37
  domain tests, the full applicable suite, static analysis, credential scan,
  `verify_delivery.py --live`, final PR CI, and the merged `main` SHA.

## Success criteria

The goal is complete only when `v0.1.0`, its public GitHub Release, the public
GHCR digest, the public Render Demo URL, all three fresh aligned evidence files,
terminal T37 records, the live delivery gate, final CI, and the final merged
`main` commit are all directly observable and successful.
