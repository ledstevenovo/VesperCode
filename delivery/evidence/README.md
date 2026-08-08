# Delivery Evidence (T36.1, 36.A)

Closed non-secret evidence records for the CI run, the protected
release, and the deployment.  T37.1 performs the protected external
operations and writes exactly these records from terminal results;
`load_and_verify_release_evidence` (and the CLI below) is the read-only
verifier that must accept the records before any external publication
or evidence write.

## Files

Each record is one JSON file under the evidence root:

| File | Record | Contents |
|---|---|---|
| `ci-v1.json` | `CIReleaseEvidenceV1` | confirmed run id/URL, source commit, environment category, terminal status, recorded-at timestamp |
| `release-v1.json` | `ReleaseEvidenceV1` | tag, source commit, tag commit, wheel SHA-256, reference manifest digest, GHCR repo digest, pulled image digest, release/CI URLs, access flags |
| `deployment-v1.json` | `DeploymentEvidenceV1` | deployment id, source commit, demo image digest, Render URL, access flags |

All records are closed (`extra = "forbid"`), non-secret (ids, URLs,
commits, digests, timestamps, environment categories, terminal
outcomes, and boolean access metadata only), and content-addressed
(40-hex commits, 64-hex SHA-256 digests, ISO-8601 timestamps, HTTP(S)
URLs).  `access_metadata` holds only boolean publicity flags; values
are strictly boolean, so no credential or secret can ever be carried
in it.

## Alignment rules (fail-closed)

Inside one record:

- `github_tag_commit == source_commit` — the release tag must point at
  the frozen source commit.
- `reference_manifest_digest == ghcr_repo_digest == pulled_image_digest`
  — SPEC AC-30 three-way digest equality (the wheel SHA-256 is an
  independent fourth artifact, not part of the image identity): the
  published GHCR image must be the frozen Task 2 reference manifest
  image, and the pulled image must be exactly that published image.
- `schema_version` is closed at 1; timestamps are full
  timezone-qualified ISO-8601 instants (`YYYY-MM-DDTHH:MM:SSZ` or
  `+HH:MM`) so freshness is always verifiable.

Across records (`load_and_verify_release_evidence`):

- `ci-v1.json`, `release-v1.json`, `deployment-v1.json` must share the
  exact same `source_commit`.
- `release-v1.json`'s `ci_run_id` and `ci_run_url` must equal the CI
  record's — the release must cite the very CI run recorded as
  evidence.  (`environment_category` is deliberately allowed to differ
  across records: CI on GitHub Actions with a manually triggered local
  deployment is legitimate.)
- With `require_live=True`: every record must be `SUCCEEDED` and its
  `recorded_at` must be fresh (within 24 h of verification).

Anything else — a missing file, unknown field, malformed digest or
timestamp, non-terminal status, planned/invented record, or any
misalignment — is rejected with `ValueError` / `ValidationError` and no
partial evidence is accepted.

## CLI

```bash
python scripts/verify_release_evidence.py <evidence_root> [--live]
```

Exit 0 with the aligned bundle on success; exit 1 with the reason on
any rejection.  The verifier is read-only: it never mutates the
evidence store and performs zero external I/O beyond reading the three
files.
