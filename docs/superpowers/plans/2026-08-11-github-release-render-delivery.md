# GitHub Release and Render Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish VesperCode `v0.1.0` through a protected GitHub workflow, deploy the isolated Demo on Render Free, and close T37 with fresh source-aligned live evidence.

**Architecture:** A Windows job builds and installs the wheel; a dependent Linux publication job reproduces the frozen reference OCI, pushes and pulls the identical digest through GHCR, creates the GitHub Release, and emits one observation artifact. A later delivery commit binds Render to the frozen tag commit, deploys the Blueprint, writes three terminal evidence records, and passes the live delivery gate.

**Tech Stack:** GitHub Actions, PowerShell, Bash, Python 3.12, pytest, Pydantic, Docker 29.1.3, buildx 0.30.1, GHCR, GitHub CLI, Render Blueprint.

---

## File map

- Create `.github/workflows/release.yml`: protected manual release workflow.
- Create `tests/unit/process/test_github_release_workflow.py`: offline static release-workflow contract.
- Modify `render.yaml`: bind `SOURCE_COMMIT` to the frozen tag commit after publication.
- Create `delivery/evidence/ci-v1.json`: terminal Actions evidence.
- Create `delivery/evidence/release-v1.json`: terminal Release/GHCR evidence.
- Create `delivery/evidence/deployment-v1.json`: terminal Render evidence.
- Modify `README.md`: replace only statements invalidated by completed publication/deployment.
- Modify `PLAN.md`: terminalize T37.1/T37.2 and 37.A–37.C with real evidence.
- Modify `AGENT_LOG.md`: append C1–F chronology, authorization, commands, PRs, and outcomes.
- Modify `SPEC_PROCESS.md`: append the final publication/deployment/document-check record.

### Task 1: Add the failing GitHub release workflow contract

**Files:**
- Create: `tests/unit/process/test_github_release_workflow.py`
- Test: `tests/unit/process/test_github_release_workflow.py`

- [ ] **Step 1: Write the static contract tests**

```python
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOW = _ROOT / ".github" / "workflows" / "release.yml"


def _workflow_text() -> str:
    return _WORKFLOW.read_text(encoding="utf-8")


def test_release_workflow_has_closed_admission_and_permissions() -> None:
    text = _workflow_text()
    for required in (
        "push:",
        "tags:",
        '- "v*"',
        "environment: release",
        "contents: write",
        "packages: write",
        "concurrency:",
        "cancel-in-progress: false",
        "^v[0-9]+\\.[0-9]+\\.[0-9]+$",
        "GITHUB_REF_NAME",
        "git rev-list -n 1",
        'if version != "0.1.0":',
    ):
        assert required in text


def test_release_workflow_proves_wheel_and_reference_publication() -> None:
    text = _workflow_text()
    for required in (
        "runs-on: windows-latest",
        "python -m build --wheel --no-isolation --outdir dist-release",
        "vespercode.exe --help",
        "docker/setup-docker-action@v4",
        'version: "v29.1.3"',
        "docker/setup-buildx-action@v3",
        'version: "v0.30.1"',
        "scripts/run_reference_image_smoke.py",
        "ghcr.io/ledstevenovo/vespercode-reference",
        "cf0b6c5ccac588fccd07c3b9f050bff4daf550ac6e518fd06efb6e988ab1d823",
        "docker push",
        "docker pull",
        "gh release create",
        "release-observation.json",
        "actions/upload-artifact@v4",
    ):
        assert required in text
```

- [ ] **Step 2: Run RED**

Run:

```powershell
.venv-formal\Scripts\python.exe -m pytest -q tests\unit\process\test_github_release_workflow.py
```

Expected: collection reaches both tests and fails because `.github/workflows/release.yml` does not exist.

- [ ] **Step 3: Commit RED evidence only after GREEN is available**

Do not commit a permanently failing tree. Preserve the terminal output in the C1 AGENT_LOG record and continue directly to Task 2.

### Task 2: Implement the protected release workflow

**Files:**
- Create: `.github/workflows/release.yml`
- Test: `tests/unit/process/test_github_release_workflow.py`

- [ ] **Step 1: Add the closed workflow header and preflight**

```yaml
name: Release

on:
  push:
    tags:
      - "v*"

permissions:
  contents: read

concurrency:
  group: release-${{ github.ref_name }}
  cancel-in-progress: false

jobs:
  preflight:
    runs-on: ubuntu-latest
    outputs:
      source_commit: ${{ steps.identity.outputs.source_commit }}
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.ref_name }}
          fetch-depth: 0
      - id: identity
        shell: bash
        run: |
          set -euo pipefail
          TAG_NAME="$GITHUB_REF_NAME"
          SOURCE_COMMIT=$(git rev-list -n 1 "$TAG_NAME")
          [[ "$TAG_NAME" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]
          test "$TAG_NAME" = "v0.1.0"
          [[ "$SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]]
          test "$(git rev-list -n 1 "$TAG_NAME")" = "$SOURCE_COMMIT"
          test "$(git rev-parse HEAD)" = "$SOURCE_COMMIT"
          python - <<'PY'
          import tomllib
          with open("pyproject.toml", "rb") as stream:
              version = tomllib.load(stream)["project"]["version"]
          if version != "0.1.0":
              raise SystemExit(f"unexpected project version: {version}")
          PY
          echo "source_commit=$SOURCE_COMMIT" >> "$GITHUB_OUTPUT"
```

- [ ] **Step 2: Add the Windows wheel-build-smoke job**

```yaml
  wheel-build-smoke:
    needs: preflight
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.ref_name }}
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: requirements/dev.lock
      - name: Install locked Windows development dependencies
        run: python -m pip install --require-hashes -r requirements/dev.lock
      - name: Build and install the release wheel
        shell: pwsh
        run: |
          $ErrorActionPreference = "Stop"
          python -m build --wheel --no-isolation --outdir dist-release
          $wheels = @(Get-ChildItem dist-release -Filter *.whl)
          if ($wheels.Count -ne 1) { throw "expected exactly one wheel" }
          $wheel = $wheels[0]
          $sha256 = (Get-FileHash $wheel.FullName -Algorithm SHA256).Hash.ToLower()
          if ($sha256 -notmatch "^[0-9a-f]{64}$") { throw "malformed wheel digest" }
          Set-Content dist-release/vespercode.sha256 "$sha256  $($wheel.Name)"
          python -m venv venv-release-smoke
          ./venv-release-smoke/Scripts/python.exe -m pip install --require-hashes -r requirements/dev.lock
          ./venv-release-smoke/Scripts/python.exe -m pip install --no-deps $wheel.FullName
          ./venv-release-smoke/Scripts/vespercode.exe --help
      - uses: actions/upload-artifact@v4
        with:
          name: release-wheel
          path: |
            dist-release/*.whl
            dist-release/vespercode.sha256
          if-no-files-found: error
          retention-days: 30
```

- [ ] **Step 3: Add the Linux protected publication job**

```yaml
  publish:
    needs: [preflight, wheel-build-smoke]
    runs-on: ubuntu-latest
    environment: release
    permissions:
      contents: write
      packages: write
    env:
      IMAGE: ghcr.io/ledstevenovo/vespercode-reference
      FROZEN_DIGEST: sha256:cf0b6c5ccac588fccd07c3b9f050bff4daf550ac6e518fd06efb6e988ab1d823
      TAG_NAME: ${{ github.ref_name }}
      SOURCE_COMMIT: ${{ needs.preflight.outputs.source_commit }}
      GH_TOKEN: ${{ github.token }}
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.ref_name }}
          fetch-depth: 0
      - uses: docker/setup-docker-action@v4
        with:
          version: "v29.1.3"
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: requirements/dev.lock
      - uses: docker/setup-buildx-action@v3
        with:
          version: "v0.30.1"
      - name: Install locked Linux development dependencies
        run: python -m pip install --no-deps $(grep -E '^(ast-serialize|charset-normalizer|librt|markupsafe|mypy|pydantic-core|ruff)==' requirements/dev.lock | cut -d' ' -f1) && grep -vE '^(ast-serialize|charset-normalizer|librt|markupsafe|mypy|pydantic-core|ruff|pywin32|pywin32-ctypes)==' requirements/dev.lock > /tmp/dev-lock-linux.txt && python -m pip install --require-hashes --no-deps -r /tmp/dev-lock-linux.txt
      - uses: actions/download-artifact@v4
        with:
          name: release-wheel
          path: dist-release
      - name: Verify the wheel artifact
        shell: bash
        run: |
          set -euo pipefail
          mapfile -t wheels < <(find dist-release -maxdepth 1 -type f -name '*.whl')
          test "${#wheels[@]}" -eq 1
          cd dist-release
          sha256sum --check vespercode.sha256
      - name: Reproduce the frozen reference image and smoke it
        run: PYTHONPATH=src python scripts/run_reference_image_smoke.py --report tests/.tmp/release-reference-smoke.json
      - name: Publish and re-pull the frozen reference image
        id: image
        shell: bash
        run: |
          set -euo pipefail
          echo "$GH_TOKEN" | docker login ghcr.io -u "$GITHUB_ACTOR" --password-stdin
          docker tag vespercode-reference:local "$IMAGE:$TAG_NAME"
          docker push "$IMAGE:$TAG_NAME"
          docker pull "$IMAGE:$TAG_NAME"
          repo_digest=$(docker image inspect "$IMAGE:$TAG_NAME" --format '{{range .RepoDigests}}{{println .}}{{end}}' | grep "^$IMAGE@sha256:" | head -n 1 | cut -d@ -f2)
          test "$repo_digest" = "$FROZEN_DIGEST"
          docker image rm "$IMAGE:$TAG_NAME"
          docker pull "$IMAGE@$FROZEN_DIGEST"
          pulled_digest=$(docker image inspect "$IMAGE@$FROZEN_DIGEST" --format '{{range .RepoDigests}}{{println .}}{{end}}' | grep "^$IMAGE@sha256:" | head -n 1 | cut -d@ -f2)
          test "$pulled_digest" = "$FROZEN_DIGEST"
          echo "repo_digest=$repo_digest" >> "$GITHUB_OUTPUT"
          echo "pulled_digest=$pulled_digest" >> "$GITHUB_OUTPUT"
      - name: Create the GitHub Release and observation
        env:
          REPO_DIGEST: ${{ steps.image.outputs.repo_digest }}
          PULLED_DIGEST: ${{ steps.image.outputs.pulled_digest }}
        shell: bash
        run: |
          set -euo pipefail
          wheel=$(find dist-release -maxdepth 1 -type f -name '*.whl')
          wheel_name=$(basename "$wheel")
          wheel_sha256=$(cut -d' ' -f1 dist-release/vespercode.sha256)
          if gh release view "$TAG_NAME" --repo "$GITHUB_REPOSITORY" >/dev/null 2>&1; then
            mapfile -t assets < <(gh release view "$TAG_NAME" --repo "$GITHUB_REPOSITORY" --json assets --jq '.assets[].name')
            test "${#assets[@]}" -eq 2
            printf '%s\n' "${assets[@]}" | grep -Fxq "$wheel_name"
            printf '%s\n' "${assets[@]}" | grep -Fxq vespercode.sha256
            mkdir existing-release
            gh release download "$TAG_NAME" --repo "$GITHUB_REPOSITORY" --dir existing-release --pattern "$wheel_name" --pattern vespercode.sha256
            existing_wheel_sha256=$(sha256sum "existing-release/$wheel_name" | cut -d' ' -f1)
            test "$existing_wheel_sha256" = "$wheel_sha256"
            cmp existing-release/vespercode.sha256 dist-release/vespercode.sha256
          else
            gh release create "$TAG_NAME" "$wheel" dist-release/vespercode.sha256 --repo "$GITHUB_REPOSITORY" --verify-tag --title "VesperCode $TAG_NAME" --notes "First verified VesperCode course-project release."
          fi
          release_json=$(gh api "repos/$GITHUB_REPOSITORY/releases/tags/$TAG_NAME")
          export RELEASE_ID=$(jq -r '.id' <<<"$release_json")
          export RELEASE_URL=$(jq -r '.html_url' <<<"$release_json")
          export WHEEL_SHA256="$wheel_sha256"
          export CI_RUN_ID="$GITHUB_RUN_ID"
          export CI_RUN_URL="$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID"
          python - <<'PY'
          import json, os
          from datetime import datetime, timezone
          payload = {
              "source_commit": os.environ["SOURCE_COMMIT"],
              "tag_name": os.environ["TAG_NAME"],
              "released_wheel_sha256": os.environ["WHEEL_SHA256"],
              "ghcr_repo_digest": os.environ["REPO_DIGEST"],
              "pulled_image_digest": os.environ["PULLED_DIGEST"],
              "wheel_install_passed": True,
              "image_smoke_passed": True,
              "release_id": os.environ["RELEASE_ID"],
              "release_url": os.environ["RELEASE_URL"],
              "ci_run_id": os.environ["CI_RUN_ID"],
              "ci_run_url": os.environ["CI_RUN_URL"],
              "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
          }
          with open("release-observation.json", "w", encoding="utf-8", newline="\n") as stream:
              json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2)
              stream.write("\n")
          PY
      - uses: actions/upload-artifact@v4
        with:
          name: release-observation
          path: |
            release-observation.json
            tests/.tmp/release-reference-smoke.json
          if-no-files-found: error
          retention-days: 90
```

- [ ] **Step 4: Run GREEN and the release domain**

Run:

```powershell
.venv-formal\Scripts\python.exe -m pytest -q tests\unit\process\test_github_release_workflow.py tests\unit\process\test_ci_release_rules.py tests\smoke\release\test_manifest_image_alignment.py tests\smoke\release\test_commit_alignment.py
```

Expected: all selected tests pass.

- [ ] **Step 5: Run static and secret checks**

```powershell
.venv-formal\Scripts\python.exe -m ruff check tests\unit\process\test_github_release_workflow.py
.venv-formal\Scripts\python.exe -m ruff format --check tests\unit\process\test_github_release_workflow.py
.venv-formal\Scripts\python.exe scripts\scan_credentials.py --changed --redact --fail-on-match
git diff --check
```

Expected: every command exits 0.

- [ ] **Step 6: Commit C1 implementation**

```powershell
git add .github/workflows/release.yml tests/unit/process/test_github_release_workflow.py
git commit -m "ci: add protected GitHub release workflow"
```

### Task 3: Merge C1 and freeze the release source

**Files:**
- Modify: `AGENT_LOG.md` only if required to record C1 before the release PR.

- [ ] **Step 1: Run the complete applicable local gate**

Run the repository's documented formal test, ruff, mypy, gate, credential, and
diff commands exactly as recorded in README/AGENT_LOG. No new deselection or
skip is permitted.

- [ ] **Step 2: Push and open the C1 PR**

Push `codex/release-delivery`, create a ready PR to `main`, and include RED,
GREEN, static checks, authorization boundaries, and responsible-agent facts.

- [ ] **Step 3: Require GitHub CI and merge**

Wait for `unit-test`, `reference-image-build`, and `demo-image-build` in both
push and pull-request contexts. Merge only when the PR is `CLEAN` and every
check is `SUCCESS`.

- [ ] **Step 4: Freeze source identity**

Fetch the merge commit and save it as `source_commit`. Verify the post-merge
main push run has the same `headSha` and all three jobs successful. Recheck that
`refs/tags/v0.1.0` and the corresponding Release are absent.

### Task 4: Configure protection and publish `v0.1.0`

**Files:**
- External GitHub configuration: `release` Environment and `v*` tag ruleset.
- External artifacts: annotated tag, GitHub Release, GHCR image, workflow observation.

- [ ] **Step 1: Create the release Environment**

Use the GitHub API to create `release` with custom deployment ref policy and
allow the `v*` tag pattern. Configure no required reviewer, no timer, and no
secrets.

- [ ] **Step 2: Create the immutable tag ruleset**

Create one active tag ruleset matching `refs/tags/v*` that rejects update,
deletion, and non-fast-forward movement. Read it back and verify its target,
conditions, enforcement, and rules before creating the tag.

- [ ] **Step 3: Create and push the annotated tag**

```powershell
$sourceCommit = (git rev-parse origin/main).Trim()
if ($sourceCommit -notmatch '^[0-9a-f]{40}$') { throw 'invalid frozen source commit' }
git tag -a v0.1.0 $sourceCommit -m "VesperCode v0.1.0"
git push origin refs/tags/v0.1.0
```

Expected: the remote peeled tag commit equals `source_commit`. Never issue a
tag delete or force update.

- [ ] **Step 4: Monitor the tag-triggered Release workflow**

The successful tag push automatically creates one `Release` workflow run.
Resolve its run id by workflow name, event `push`, branch `v0.1.0`, source
commit, and creation time. Wait with `gh run watch --exit-status`. A transient
GitHub failure may rerun the same immutable run at most twice.

- [ ] **Step 5: Verify terminal publication**

Download `release-observation`, recompute the wheel attachment digest, query
the tag and Release, pull
`ghcr.io/ledstevenovo/vespercode-reference@sha256:cf0b6c5ccac588fccd07c3b9f050bff4daf550ac6e518fd06efb6e988ab1d823`, and call
`verify_release_publication_result`. Continue only on `ACCEPTED`.

- [ ] **Step 6: Make the GHCR package public**

Read the package visibility. If it is private, use the authenticated package
settings UI/API to set `vespercode-reference` public, then verify an anonymous
manifest request can resolve the frozen digest.

#### Immutable-tag recovery amendment

The first `v0.1.0` run built and installed the wheel but its Windows CLI smoke
failed while printing Chinese help through the runner's default `cp1252`
stdout. No publish job ran. The tag is already protected and must not move.
Recover through a narrow PR that adds `PYTHONUTF8=1` and a parameter-free
`workflow_dispatch` admission fixed to `v0.1.0` and
`d31bdeeafe8ad65b60fac213e23fcab9dffdd7aa`. The recovery must run only from
`refs/heads/main`, while all jobs checkout the fixed tag and repeat the same
identity, wheel, image, Release, and observation gates. Temporarily add a
`main` branch deployment policy to the `release` Environment only for this
run; remove it immediately after the run reaches terminal success, then verify
that the Environment again contains exactly the `v*` tag policy. Do not
delete, recreate, or move `v0.1.0`.

### Task 5: Bind and deploy the Render Blueprint

**Files:**
- Modify: `render.yaml`
- Test: `tests/smoke/release/test_render_contract.py`
- Test: `tests/smoke/release/test_public_demo_smoke.py`

- [ ] **Step 1: Replace the zero SOURCE_COMMIT value**

Set the `SOURCE_COMMIT` value in `render.yaml` to the exact frozen
`source_commit`. Change no plan, repository, Dockerfile, port, health path,
disk, database, or secret field.

- [ ] **Step 2: Verify the bound Blueprint**

```powershell
.venv-formal\Scripts\python.exe -m pytest -q tests\smoke\release\test_render_contract.py tests\smoke\release\test_public_demo_smoke.py
```

Expected: the static/domain tests pass with the bound source identity.

- [ ] **Step 3: Commit, push, PR, and merge the binding**

Create a narrow commit, push it, open a ready PR, wait for all required checks,
and merge. Do not alter `v0.1.0`; it continues to point at `source_commit`.

- [ ] **Step 4: Deploy the approved Blueprint**

Use the already-authenticated Render browser session, retain Blueprint name
`VesperCode`, branch `main`, root `render.yaml`, service
`vespercode-demo`, and Free plan. Stop if Render requests payment,
reauthentication, a card, or a non-Free resource.

- [ ] **Step 5: Verify the public terminal deployment**

Record the real deployment id, service URL, deployed commit/config identity,
and confirmed Demo image digest. Require terminal success, then request
`/healthz` and the public Demo routes from outside Render. Accept only the
closed four-route surface and Mock/fixture behavior.

### Task 6: Write live evidence and terminalize T37

**Files:**
- Create: `delivery/evidence/ci-v1.json`
- Create: `delivery/evidence/release-v1.json`
- Create: `delivery/evidence/deployment-v1.json`
- Modify: `README.md`
- Modify: `PLAN.md`
- Modify: `AGENT_LOG.md`
- Modify: `SPEC_PROCESS.md`

- [ ] **Step 1: Materialize the three records from observations**

Use the source commit and Actions run from `release-observation.json`, the
queried GitHub Release/GHCR values, and the Render terminal deployment. Write
only schema-v1 fields accepted by `vespercode.delivery.evidence`; remove the
`sha256:` prefix only for evidence fields whose schema requires bare 64-hex.

- [ ] **Step 2: Verify evidence before terminal documentation**

```powershell
.venv-formal\Scripts\python.exe scripts\verify_release_evidence.py --live delivery\evidence
```

Expected: exit 0 with all records `SUCCEEDED`, fresh, and source-aligned.

- [ ] **Step 3: Update terminal documentation**

Replace README's truthful “not yet published/deployed” statements with the
real Release URL, immutable GHCR reference, public Render URL, and verification
instructions. Mark T37.1/T37.2 and 37.A–37.C terminal in PLAN with real commits,
reviews, runs, and PRs. Append chronological records to AGENT_LOG and
SPEC_PROCESS; never rewrite earlier historical entries.

- [ ] **Step 4: Run the final completion audit**

Run the reflection, README, process, release, and delivery verifiers; T37
domain tests; the full applicable suite; ruff; mypy; credential scan; Docker
reference/Demo smoke; and `git diff --check`. Run `verify_delivery.py --live`
last, while evidence remains within the 24-hour freshness window.

- [ ] **Step 5: Final PR, CI, merge, and merged-main audit**

Commit the evidence/docs closure, push, create a ready PR, require all checks,
and merge. Fetch remote `main`, rerun the read-only terminal verifiers on that
exact tree, and verify the public Release, GHCR digest, Render health URL, three
evidence records, tag identity, and final main CI one final time.

- [ ] **Step 6: Mark the persistent goal complete**

Only after every success criterion in the design has direct current evidence,
mark the active goal complete and report URLs, commits, digests, test counts,
and any non-blocking platform warning.
