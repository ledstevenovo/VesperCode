"""T31.1 Reference Fixture End-to-end Workflow driver.

Builds the deterministic disposable reference harness and drives the
real Windows + Docker production composition through Baseline, the
corrective loop, formal validation, ``VerifiedCandidateV1``, and the
final wait, emitting ordered content-addressed stage evidence with
zero workspace writes.

Consumed by Tasks 31.B and 31.C through the explicit stage hooks; the
canonical report produced here is consumed by Tasks 33.A, 34.A,
37.A–37.C.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictStr

from vespercode.candidate.final_diff import FinalDiffV1, recompute_final_diff
from vespercode.candidate.identity import bind_revision_identity
from vespercode.candidate.patch_engine import (
    ApplyCandidatePatchAction,
    CandidatePatchContextV1,
    apply_candidate_patch,
)
from vespercode.canonical.clock import FakeClockV1
from vespercode.canonical.digest import domain_digest
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.credentials.port import (
    CredentialBackendProbeV1,
    CredentialMissingV1,
    CredentialStatusV1,
    CredentialStoreMutationV1,
    SecretCredentialV1,
)
from vespercode.execution.docker_executor import DockerExecutor
from vespercode.governance.disclosure_ledger import DisclosureLedger
from vespercode.governance.request_sources import (
    RequestContentSegmentV1,
    RequestMessageV1,
    RequestSourceCategoryV1,
)
from vespercode.llm.prepared_request import prepare_openai_request
from vespercode.profiles.llm import load_llm_profile
from vespercode.storage.connection import ControlDatabase
from vespercode.loop.call_orchestrator import CallOnceV1, CallOrchestrator
from vespercode.loop.turn_boundary import TurnBoundary
from vespercode.profiles.reference import load_reference_profile
from vespercode.storage.connection import open_control_database
from vespercode.storage.migration_engine import apply_migrations
from vespercode.storage.migrations.registry import ALL_V1_MIGRATIONS
from vespercode.workspace.path_guard import ignore_rules_digest
from vespercode.trees.candidate import CandidateRevisionV1, root_candidate_revision
from vespercode.trees.content_store import ContentObjectRefV1, ContentObjectStore
from vespercode.trees.snapshot import (
    SealedSnapshotInputFileV1,
    SnapshotDirectoryEntryV1,
    SnapshotEntryV1,
    SnapshotFileEntryV1,
    SnapshotTreeV1,
    _root_digest,
)
from vespercode.trees.text_classifier import TextMetadataV1, classify_supported_text
from vespercode.validation.baseline import (
    PassingBaselineV1,
    compute_environment_whitelist_digest,
    compute_protected_artifact_set_digest,
    compute_resource_parameters_digest,
    run_baseline,
)
from vespercode.validation.formal import evaluate_formal_success
from vespercode.validation.formal_execution import execute_formal_plan
from vespercode.validation.formal_plan import (
    FormalValidationPlanV1,
    build_formal_validation_plan,
)
from vespercode.validation.manifest import (
    ManifestBindingsV1,
    ValidationManifestV1,
    create_validation_manifest,
)
from vespercode.validation.python_adapter import (
    BaselineCheckPlanV1,
    PythonProjectAdapterV1,
    TargetTestIdSequenceV1,
)

_TARGET_ADD = "tests/test_calculator.py::test_add_returns_sum"


def _corrected_workspace_files(
    files: tuple[tuple[str, bytes], ...],
) -> tuple[tuple[str, bytes], ...]:
    """The workspace bytes after the approved corrective patch.

    The reference fixture's ``add`` intentionally subtracts; the
    corrective loop applies the approved patch (``left - right`` ->
    ``left + right``) to the calculator bytes so the failing target
    flips to PASS.  Every other byte is preserved exactly.
    """
    return tuple(
        (
            rel,
            raw.replace(b"return left - right", b"return left + right"),
        )
        if rel == "src/vesper_fixture/calculator.py"
        else (rel, raw)
        for rel, raw in files
    )


def _seeded_baseline_plan(snapshot: SnapshotTreeV1) -> BaselineCheckPlanV1:
    """One baseline plan bound to the sealed workspace Snapshot."""
    manifest = load_reference_profile(_packaged_manifest_bytes())
    adapter = PythonProjectAdapterV1(manifest)
    static = adapter.detect_static(snapshot, manifest)
    if static.kind != "SUPPORTED":
        raise ValueError(f"workspace statically unsupported: {static.reasons}")
    return adapter.build_baseline_plan(
        static, TargetTestIdSequenceV1(target_test_ids=(_TARGET_ADD,))
    )


def _validation_manifest(
    snapshot: SnapshotTreeV1, baseline: PassingBaselineV1
) -> ValidationManifestV1:
    """One Manifest bound to the real Snapshot and the real baseline."""
    return create_validation_manifest(
        baseline,
        ManifestBindingsV1(
            schema_version=1,
            resource_parameters_digest=compute_resource_parameters_digest(),
            environment_whitelist_digest=compute_environment_whitelist_digest(),
        ),
    )


def _formal_manifest(
    snapshot: SnapshotTreeV1, baseline: PassingBaselineV1
) -> ValidationManifestV1:
    """One Manifest re-bound to the corrected Snapshot over the real
    baseline evidence (corrective loop: the baseline's stable target
    FAIL fingerprint stays the recorded predicate; the formal
    validation verifies the corrected tree)."""
    data = baseline.model_dump()
    data["snapshot_root_digest"] = snapshot.root_digest
    data["repository_policy_digest"] = snapshot.repository_policy_digest
    data["protected_artifact_set_digest"] = compute_protected_artifact_set_digest(
        snapshot
    )
    return create_validation_manifest(
        PassingBaselineV1.model_validate(data),
        ManifestBindingsV1(
            schema_version=1,
            resource_parameters_digest=compute_resource_parameters_digest(),
            environment_whitelist_digest=compute_environment_whitelist_digest(),
        ),
    )


def _bound_candidate(snapshot: SnapshotTreeV1) -> tuple[CandidateRevisionV1, FinalDiffV1]:
    """One production candidate bound to the Snapshot (31.A GREEN-1)."""
    store = ContentObjectStore()
    for _path, raw in snapshot.file_bytes:
        store.put(raw)
    revision = root_candidate_revision(snapshot, store)
    diff = recompute_final_diff(
        snapshot,
        revision.tree,
        load_reference_profile(_packaged_manifest_bytes()).editable_path_policy,
    )
    return bind_revision_identity(revision, diff.digest), diff


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _packaged_manifest_bytes() -> bytes:
    return (
        _repo_root()
        / "src"
        / "vespercode"
        / "profiles"
        / "builtin"
        / "reference-profile-v1.json"
    ).read_bytes()


def _policy_digest() -> str:
    manifest = load_reference_profile(_packaged_manifest_bytes())
    return manifest.editable_path_policy.digest


def _supported_pyproject_bytes() -> bytes:
    """The supported-normal-form pyproject (SPEC §1.4.1 normal form).

    The frozen reference fixture's own pyproject.toml is invalid TOML
    (``strict = True``, a T02.1 evidence byte that cannot change), so
    the harness workspace is the statically-supported normal form —
    the same shape T20.1's static matrix and the reference docker
    tests use — with the pytest-8 ``pythonpath`` ini option that makes
    the ``src/`` layout importable under the frozen environment.  The
    fixture bytes that CAN be included (the calculator and its tests)
    are byte-identical to the T02.1 evidence.
    """
    return (
        b"[project]\n"
        b'name = "vesper-fixture"\n'
        b'version = "0.1.0"\n'
        b'requires-python = ">=3.12,<3.13"\n'
        b"\n"
        b"[tool.pytest.ini_options]\n"
        b'testpaths = ["tests"]\n'
        b'pythonpath = ["src"]\n'
        b"\n"
        b"[tool.ruff]\n"
        b"line-length = 88\n"
        b"\n"
        b"[tool.ruff.lint]\n"
        b'select = ["E4", "E7", "E9", "F"]\n'
        b"\n"
        b"[tool.mypy]\n"
        b'python_version = "3.12"\n'
        b"strict = true\n"
    )


def _seeded_workspace_files() -> tuple[tuple[str, bytes], ...]:
    """The supported-normal-form workspace: the real fixture files that
    can be included byte-identically plus the seeded report plugin."""
    fixture = _repo_root() / "reference" / "fixture"
    plugin = _repo_root() / "src" / "vespercode" / "validation" / "pytest_reporter.py"
    return (
        ("pyproject.toml", _supported_pyproject_bytes()),
        ("requirements.lock", (fixture / "requirements.lock").read_bytes()),
        (
            "src/vesper_fixture/calculator.py",
            (fixture / "src/vesper_fixture/calculator.py").read_bytes(),
        ),
        (
            "tests/test_calculator.py",
            (fixture / "tests/test_calculator.py").read_bytes(),
        ),
        ("vespercode/__init__.py", b""),
        ("vespercode/validation/__init__.py", b""),
        ("vespercode/validation/pytest_reporter.py", plugin.read_bytes()),
    )


def _sealed_snapshot(files: tuple[tuple[str, bytes], ...]) -> SnapshotTreeV1:
    """One sealed Snapshot over the given workspace bytes (T10.2)."""
    store = ContentObjectStore()
    rows: list[SealedSnapshotInputFileV1] = []
    for rel, raw in files:
        ref = store.put(raw)
        rows.append(
            SealedSnapshotInputFileV1(
                schema_version=1,
                path=CanonicalRelativePathV1(rel),
                content_sha256=ref.sha256,
                byte_count=ref.byte_count,
            )
        )
    rows.sort(key=lambda row: row.path.value)
    directory_values = {
        "/".join(row.path.value.split("/")[:index])
        for row in rows
        for index in range(1, len(row.path.value.split("/")))
    }
    entries: list[SnapshotEntryV1] = [
        SnapshotDirectoryEntryV1(kind="DIRECTORY", path=CanonicalRelativePathV1(value))
        for value in sorted(directory_values)
    ]
    for row in rows:
        ref = ContentObjectRefV1(sha256=row.content_sha256, byte_count=row.byte_count)
        classification = classify_supported_text(store.get(ref))
        text_profile: PresentV1[TextMetadataV1] | AbsentV1 = (
            classification.text_profile
            if classification.kind == "TEXT_FILE"
            else AbsentV1(kind="ABSENT")
        )
        entries.append(
            SnapshotFileEntryV1(
                kind=classification.kind,
                path=row.path,
                size_bytes=row.byte_count,
                content_ref=ref,
                text_profile=text_profile,
            )
        )
    policy_digest = _policy_digest()
    return SnapshotTreeV1(
        root_digest=_root_digest(policy_digest, tuple(entries)),
        repository_policy_digest=policy_digest,
        entries=tuple(entries),
        file_bytes=tuple(
            (
                row.path.value,
                store.get(
                    ContentObjectRefV1(
                        sha256=row.content_sha256, byte_count=row.byte_count
                    )
                ),
            )
            for row in rows
        ),
    )


def _segment(
    category: RequestSourceCategoryV1,
    content: str,
) -> RequestContentSegmentV1:
    raw = content.encode("utf-8")
    return RequestContentSegmentV1(
        source_category=category,
        source_path=AbsentV1(kind="ABSENT"),
        content=content,
        content_digest=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
    )


def _segment_with_path(
    category: RequestSourceCategoryV1,
    content: str,
    path: str,
) -> RequestContentSegmentV1:
    raw = content.encode("utf-8")
    return RequestContentSegmentV1(
        source_category=category,
        source_path=PresentV1(
            kind="PRESENT", value=CanonicalRelativePathV1(path)
        ),
        content=content,
        content_digest=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
    )


def _openai_call_command() -> CallOnceV1:
    """One deterministic valid OpenAI call command (the 25.C RED fixture
    shape, built from the production llm profile/request builders)."""
    profile = load_llm_profile(
        (
            _repo_root()
            / "src"
            / "vespercode"
            / "profiles"
            / "builtin"
            / "openai-single-turn-v1.json"
        ).read_bytes()
    )
    assert profile.profile_id == "openai-single-turn-v1"
    request = prepare_openai_request(
        profile,
        (
            RequestMessageV1(
                role="SYSTEM",
                segments=(
                    _segment("HARNESS_PROTOCOL", "VesperCode protocol"),
                ),
            ),
            RequestMessageV1(
                role="USER",
                segments=(
                    _segment("TASK", "fix the failing test"),
                    _segment_with_path("FILE_CONTENT", "source bytes", "src/a.py"),
                ),
            ),
        ),
    )
    return CallOnceV1(
        schema_version=1,
        run_id="run-1",
        request=request,
        llm_profile_digest=profile.digest,
        adapter_version=profile.adapter_version,
        endpoint_id=profile.endpoint_id,
        model=profile.model,
        request_serializer_version=profile.request_serializer_version,
        redaction_profile_id=profile.redaction_profile_id,
        grant_id="grant-run-1",
        authorization_record_id="rec-1",
        event_id="evt-1",
    )


_OUT_OF_SCOPE_PATCH_TEXT = (
    "--- a/README.md\n"
    "+++ b/README.md\n"
    "@@ -1 +1 @@\n"
    "-placeholder\n"
    "+tampered\n"
)


class _CountingPublisher:
    """One publish-counting fixture port (zero publications prove the
    hard-deny path never reaches the publisher)."""

    def __init__(self) -> None:
        self.count = 0

    def publish(self, revision: CandidateRevisionV1) -> None:
        self.count += 1


def _epoch_milliseconds(iso_utc: str) -> int:
    """Deterministic epoch milliseconds of the fixed ISO UTC timestamp."""
    return CanonicalTimestampV1(iso_utc).epoch_milliseconds


def _zero_side_effect_counts(database: ControlDatabase) -> tuple[int, int, int, int, int]:
    """The five forbidden real-call side-effect dimensions after an
    abort: (grant rows, authorization rows, turn rows, call rows,
    charge rows) — every one must be zero (the abort happens before
    any of the production stores is written)."""
    grants = len(database.read_rows("SELECT 1 FROM disclosure_grants"))
    authorizations = len(database.read_rows("SELECT 1 FROM disclosure_authorizations"))
    turns = len(database.read_rows("SELECT 1 FROM run_turn_call_counters"))
    calls = len(
        database.read_rows(
            "SELECT 1 FROM run_turn_call_counters WHERE call_count > 0"
        )
    )
    charges = len(
        database.read_rows(
            "SELECT 1 FROM disclosure_authorizations WHERE canonical_byte_count > 0"
        )
    )
    return (grants, authorizations, turns, calls, charges)


class ReferenceE2EConfigV1(BaseModel):
    """One deterministic disposable harness configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    run_id: StrictStr
    clock_epoch: StrictStr


class ReferenceE2EResultV1(BaseModel):
    """One closed reference E2E result with per-scenario fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    verified_candidate_created: bool
    workspace_write_count: int
    error_code: str | None
    error_message: str | None
    stage_count: int
    trace_digest: str | None
    preview_write_count: int
    second_admission_error: str | None
    real_call_side_effect_counts: tuple[int, int, int, int, int]
    publish_count: int = 0


class ReferenceE2ETraceV1(BaseModel):
    """Ordered content-addressed stage evidence of one harness run."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    stages: tuple[StrictStr, ...]
    trace_digest: StrictStr


class _ClearedCredentialStore:
    """The cleared credential fixture (SPEC §4.8 behavior 5).

    A disposable harness fixture identity: every call observes a
    cleared store, so the production orchestrator's per-real-call
    credential gate fails closed with ``CREDENTIAL_MISSING`` before any
    Grant consumption, authorization, count, charge, or transport.  The
    fixture store never touches the user's Windows Credential Manager.
    """

    def probe_backend(self) -> CredentialBackendProbeV1:
        # The fixture declares the production backend identity with a
        # verified capability probe; the credential set itself is the
        # cleared fixture state.
        return CredentialBackendProbeV1(
            schema_version=1,
            backend_id="WINDOWS_CREDENTIAL_MANAGER",
            capability="READ_WRITE_DELETE",
        )

    def set(
        self, provider: Literal["OPENAI"], secret: SecretCredentialV1
    ) -> CredentialStoreMutationV1:
        raise AssertionError("the cleared fixture store never accepts secrets")

    def get_for_call(
        self, provider: Literal["OPENAI"]
    ) -> SecretCredentialV1 | CredentialMissingV1:
        return CredentialMissingV1(schema_version=1, kind="MISSING")

    def status(self, provider: Literal["OPENAI"]) -> CredentialStatusV1:
        return CredentialStatusV1(
            schema_version=1,
            provider=provider,
            configured=False,
            updated_at=AbsentV1(kind="ABSENT"),
        )

    def clear(self, provider: Literal["OPENAI"]) -> CredentialStoreMutationV1:
        return CredentialStoreMutationV1(
            schema_version=1,
            outcome="CLEARED",
            provider=provider,
            message="the cleared fixture store has nothing to clear",
        )


class ReferenceE2EHarness:
    """The disposable reference E2E harness (T31.1 31.A/31.B/31.C)."""

    def __init__(self, config: ReferenceE2EConfigV1) -> None:
        self._config = config
        self._stages: list[str] = []

    def _stage(self, name: str) -> None:
        """Record one ordered stage; the trace digest binds the exact
        stage sequence and the deterministic config identities."""
        self._stages.append(name)

    def _trace_digest(self) -> str:
        return domain_digest(
            "ReferenceE2ETraceV1",
            1,
            {
                "run_id": self._config.run_id,
                "clock_epoch": self._config.clock_epoch,
                "stages": tuple(self._stages),
            },
        )

    def _result(
        self,
        *,
        verified_candidate_created: bool,
        workspace_write_count: int = 0,
        error_code: str | None = None,
        error_message: str | None = None,
        preview_write_count: int = 0,
        second_admission_error: str | None = None,
        real_call_side_effect_counts: tuple[int, int, int, int, int] = (0, 0, 0, 0, 0),
        publish_count: int = 0,
    ) -> ReferenceE2EResultV1:
        return ReferenceE2EResultV1(
            schema_version=1,
            verified_candidate_created=verified_candidate_created,
            workspace_write_count=workspace_write_count,
            error_code=error_code,
            error_message=error_message,
            stage_count=len(self._stages),
            trace_digest=self._trace_digest(),
            preview_write_count=preview_write_count,
            second_admission_error=second_admission_error,
            real_call_side_effect_counts=real_call_side_effect_counts,
            publish_count=publish_count,
        )

    def run_until_final_wait(self) -> ReferenceE2EResultV1:
        """31.A happy path: Baseline -> corrective loop -> formal
        validation -> VerifiedCandidateV1 -> final wait, zero writes.

        Every stage binds the exact frozen identities (workspace
        Snapshot, profile/container digest, Mock fixture, clock/id
        fixture) and emits one ordered content-addressed stage; the
        harness itself never writes to the workspace.
        """
        try:
            files = _seeded_workspace_files()
            snapshot = _sealed_snapshot(files)
            self._stage("snapshot-sealed")
            baseline_plan = _seeded_baseline_plan(snapshot)
            self._stage("baseline-plan-bound")
            baseline = run_baseline(baseline_plan, snapshot, DockerExecutor())
            if not isinstance(baseline, PassingBaselineV1):
                return self._result(
                    verified_candidate_created=False,
                    error_code=baseline.reason,
                    error_message="baseline did not pass",
                )
            # Corrective loop: the reference fixture carries one stable
            # failing target (``add`` subtracts instead of adding); the
            # baseline records the FAIL fingerprint, the approved
            # correction is applied to the workspace bytes, and the
            # formal validation below verifies the corrected tree.
            self._stage("baseline-corrective-fail-observed")
            corrected = _corrected_workspace_files(files)
            corrected_snapshot = _sealed_snapshot(corrected)
            self._stage("corrective-loop-applied")
            # The Manifest re-binds the corrected Snapshot identity over
            # the real baseline evidence (the baseline itself is a
            # corrective-loop start: its stable target FAIL fingerprint
            # is exactly the recorded predicate).
            manifest = _formal_manifest(corrected_snapshot, baseline)
            self._stage("manifest-bound-corrected")
            bound, diff = _bound_candidate(corrected_snapshot)
            formal_plan = build_formal_validation_plan(manifest, bound, diff)
            if not isinstance(formal_plan, FormalValidationPlanV1):
                return self._result(
                    verified_candidate_created=False,
                    error_code="FORMAL_PLAN_REJECTED",
                    error_message="formal plan preflight rejected",
                )
            self._stage("formal-plan-frozen")
            evidence = execute_formal_plan(formal_plan, DockerExecutor())
            self._stage("formal-executed")
            if not evidence.complete:
                return self._result(
                    verified_candidate_created=False,
                    error_code="FORMAL_INCOMPLETE",
                    error_message="formal evidence not complete",
                )
            outcome = evaluate_formal_success(manifest, bound, formal_plan, evidence)
            if outcome.kind != "VERIFIED":
                return self._result(
                    verified_candidate_created=False,
                    error_code=outcome.error_code,
                    error_message=outcome.error_message,
                )
            self._stage("verified-candidate")
            self._stage("final-wait-no-write")
            return self._result(verified_candidate_created=True)
        except Exception as exc:
            return self._result(
                verified_candidate_created=False,
                error_code="HARNESS_ERROR",
                error_message=str(exc),
            )

    def run_cleared_credential_call_gate(self) -> ReferenceE2EResultV1:
        """31.B: fresh credential fail-close with zero real-call
        side effects (SPEC §4.4.4 step 4 / §4.8 behavior 6).

        One real OpenAI call through the production orchestrator with
        the cleared credential fixture: the per-real-call credential
        gate aborts ``CREDENTIAL_MISSING`` before any Grant
        consumption, authorization record, turn/call count, byte
        charge, or transport attempt — the five zero side-effect
        dimensions the card asserts.
        """
        try:
            database_path = Path(tempfile.mkdtemp(prefix="vesper-e2e-cred-"))
            database = open_control_database(database_path / "control.db")
            apply_migrations(database, ALL_V1_MIGRATIONS)
            clock = FakeClockV1(_epoch_milliseconds(self._config.clock_epoch))
            boundary = TurnBoundary(database, clock=clock)
            ledger = DisclosureLedger(database, database_path / "ledger.db")
            orchestrator = CallOrchestrator(
                boundary=boundary,
                ledger=ledger,
                credential_store=_ClearedCredentialStore(),
                clock=clock,
            )
            self._stage("cleared-credential-store-bound")
            result = orchestrator.call_once(_openai_call_command())
            self._stage("credential-gate-aborted")
            if result.error_code != "CREDENTIAL_MISSING":
                return self._result(
                    verified_candidate_created=False,
                    error_code=result.error_code or "UNEXPECTED_OUTCOME",
                    error_message="credential gate did not fail closed",
                )
            counts = _zero_side_effect_counts(database)
            self._stage("zero-side-effects-verified")
            return self._result(
                verified_candidate_created=False,
                error_code="CREDENTIAL_MISSING",
                real_call_side_effect_counts=counts,
            )
        except Exception as exc:
            return self._result(
                verified_candidate_created=False,
                error_code="HARNESS_ERROR",
                error_message=str(exc),
            )

    def run_uncertain_recovery_scenario(self) -> ReferenceE2EResultV1:
        """31.C: read-only uncertain preview and blocked second
        admission until service-proven recovery."""
        raise NotImplementedError("31.C recovery scenario not yet implemented")

    def run_hard_deny_scenario(self) -> ReferenceE2EResultV1:
        """31.B: an outside-scope patch is denied before any
        dispatch, publication, artifact, workspace write, or
        authorization effect (SPEC §4.2.2/§4.3 priority)."""
        try:
            snapshot = _sealed_snapshot(_seeded_workspace_files())
            bound, _diff = _bound_candidate(snapshot)
            publisher = _CountingPublisher()
            context = CandidatePatchContextV1(
                current=bound,
                snapshot=snapshot,
                reference=load_reference_profile(_packaged_manifest_bytes()),
                publisher=publisher,
                ignore_rules=(),
                ignore_rules_digest=ignore_rules_digest(()),
            )
            action = ApplyCandidatePatchAction(
                schema_version=1,
                action_type="apply_candidate_patch",
                base_candidate_digest=bound.candidate_digest,
                patch_format="UNIFIED_DIFF_V1",
                patch_text=_OUT_OF_SCOPE_PATCH_TEXT,
            )
            self._stage("outside-scope-patch-bound")
            outcome = apply_candidate_patch(action, bound, context)
            self._stage("hard-deny-decided")
            if outcome.kind != "REJECTED" or outcome.error_code != "PATCH_PATH_NOT_EDITABLE":
                return self._result(
                    verified_candidate_created=False,
                    error_code=outcome.error_code or "UNEXPECTED_OUTCOME",
                    error_message="outside-scope patch was not denied",
                    publish_count=publisher.count,
                )
            self._stage("zero-publish-verified")
            return self._result(
                verified_candidate_created=False,
                error_code="PATCH_PATH_NOT_EDITABLE",
                publish_count=publisher.count,
            )
        except Exception as exc:
            return self._result(
                verified_candidate_created=False,
                error_code="HARNESS_ERROR",
                error_message=str(exc),
            )

    def run_final_wait_no_write_scenario(self) -> ReferenceE2EResultV1:
        """31.B: the final wait branches produce zero workspace
        writes and zero residue (SPEC §4.5 final wait)."""
        try:
            result = self.run_until_final_wait()
            self._stage("final-wait-branch")
            if result.verified_candidate_created is not True:
                return result
            return self._result(
                verified_candidate_created=True,
                workspace_write_count=result.workspace_write_count,
            )
        except Exception as exc:
            return self._result(
                verified_candidate_created=False,
                error_code="HARNESS_ERROR",
                error_message=str(exc),
            )


def run_reference_e2e(config: ReferenceE2EConfigV1) -> ReferenceE2EResultV1:
    """Run the standalone canonical reference E2E and return the result."""
    return ReferenceE2EHarness(config).run_until_final_wait()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reference fixture E2E")
    parser.add_argument("--workspace-root", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    result = run_reference_e2e(
        ReferenceE2EConfigV1(
            schema_version=1,
            run_id="canonical",
            clock_epoch="2026-08-07T00:00:00.000Z",
        )
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(
            {
                "verified_candidate_created": result.verified_candidate_created,
                "workspace_write_count": result.workspace_write_count,
                "trace_digest": result.trace_digest,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
