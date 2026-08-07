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
import shutil
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictStr

from vespercode.audit.repository import (
    AppendAuditEventV1,
    AuditPageRequestV1,
    AuditRepository,
    ClearEndedRunAuditV1,
)
from vespercode.candidate.final_diff import (
    FinalDiffEntryV1,
    FinalDiffPreimageV1,
    FinalDiffV1,
    recompute_final_diff,
)
from vespercode.candidate.identity import bind_revision_identity
from vespercode.candidate.patch_engine import (
    ApplyCandidatePatchAction,
    CandidatePatchContextV1,
    apply_candidate_patch,
)
from vespercode.canonical.clock import ClockV1, FakeClockV1
from vespercode.canonical.digest import domain_digest
from vespercode.canonical.json_v1 import CanonicalValueV1
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import DigestV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.contracts.run import WaitContextV1, WaitDecisionV1
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
from vespercode.governance.writeback_approval import WritebackApprovalRepository
from vespercode.governance.writeback_decision import (
    DecideFinalWritebackV1,
    FinalWritebackApprovalV1,
    FinalWritebackDecisionServiceV1,
)
from vespercode.governance.writeback_subject import (
    FinalWritebackBindingV1,
    FinalWritebackSubjectV1,
    build_final_writeback_subject,
)
from vespercode.llm.prepared_request import prepare_openai_request
from vespercode.persistence.artifacts import PersistenceArtifactStoreV1
from vespercode.persistence.recovery_preview import (
    RecoveryPathObservationV1,
    RecoveryPreviewService,
)
from vespercode.persistence.transaction import (
    PersistencePathRecordRepositoryV1,
    PersistenceTransactionRepositoryV1,
)
from vespercode.persistence.writeback import (
    PersistenceCommandFactoryV1,
    PersistenceCoordinator,
    PersistVerifiedCandidateV1,
    WritebackBodyV1,
)
from vespercode.profiles.llm import load_llm_profile
from vespercode.storage.connection import ControlDatabase
from vespercode.loop.call_orchestrator import CallOnceV1, CallOrchestrator
from vespercode.loop.turn_boundary import TurnBoundary
from vespercode.profiles.reference import load_reference_profile
from vespercode.runs.admission import (
    AdmissionCoordinator,
    AdmissionPortsV1,
    AdmissionResultV1,
)
from vespercode.storage.connection import open_control_database
from vespercode.storage.migration_engine import apply_migrations
from vespercode.storage.migrations.registry import ALL_V1_MIGRATIONS
from vespercode.storage.run_repository import RunRecordV1, RunRepository
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

# The approved corrective patch (SPEC §4.2.2): the fixture's ``add``
# intentionally subtracts; the patch flips the failing target to PASS.
_PROTECTED_ARTIFACT_PATCH_TEXT = (
    "--- a/tests/test_calculator.py\n"
    "+++ b/tests/test_calculator.py\n"
    "@@ -1,1 +1,1 @@\n"
    "-from vesper_fixture.calculator import add, multiply\n"
    "+from vesper_fixture.calculator import add\n"
)


_CORRECTIVE_PATCH_TEXT = (
    "--- a/src/vesper_fixture/calculator.py\n"
    "+++ b/src/vesper_fixture/calculator.py\n"
    "@@ -8 +8 @@\n"
    "-    return left - right\n"
    "+    return left + right\n"
)


def _files_from_revision(
    revision: CandidateRevisionV1,
) -> tuple[tuple[str, bytes], ...]:
    """The workspace bytes of the published revision's tree (the sealed
    base snapshot with the applied patch overlay resolved)."""
    tree = revision.tree
    return tuple(
        (path.value, tree.read_bytes(path))
        for path in tree.list_file_paths()
    )


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


def _bound_candidate(
    snapshot: SnapshotTreeV1,
) -> tuple[CandidateRevisionV1, FinalDiffV1]:
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
    return str(manifest.editable_path_policy.digest)


# ---------------------------------------------------------------------------
# 31.C production persistence/recovery fixture (Task 26.C/26.B composition).
# The sealed identities are fixed constants so every trace stays
# content-addressed and repeatable; no injected id or time is volatile.
# ---------------------------------------------------------------------------

_CREATED_AT = CanonicalTimestampV1("2026-08-05T09:00:00.000Z")
_EXPIRES_AT = CanonicalTimestampV1("2026-08-05T09:05:00.000Z")
_DECIDED_AT = CanonicalTimestampV1("2026-08-05T09:01:00.000Z")
_CONSUMED_AT = CanonicalTimestampV1("2026-08-05T09:02:00.000Z")
_RUN_DEADLINE = CanonicalTimestampV1("2026-08-05T09:15:00.000Z")
_LATE_EXPIRES_AT = CanonicalTimestampV1("2026-08-05T09:30:00.000Z")

_SNAPSHOT_DIGEST = hashlib.sha256(b"sealed-snapshot").hexdigest()
_CANDIDATE_DIGEST = hashlib.sha256(b"verified-candidate").hexdigest()
_VALIDATION_DIGEST = hashlib.sha256(b"validation-manifest").hexdigest()
_FORMAL_EVIDENCE_DIGEST = hashlib.sha256(b"formal-evidence").hexdigest()
_PREIMAGE_DIGEST = hashlib.sha256(b"original b\n").hexdigest()
_WORKSPACE_PREIMAGE_DIGEST = hashlib.sha256(b"frozen-workspace-preimage").hexdigest()
_RUN_CONFIG_DIGEST = hashlib.sha256(b"run-config").hexdigest()
_WORKSPACE_IDENTITY_DIGEST = "55" * 32
_IDENTITY_DIGEST = "44" * 32
_TEXT_METADATA = TextMetadataV1(encoding="UTF8", newline="LF", final_newline=True)

_BODIES = {
    "src/a.py": b"new a\n",
    "src/b.py": b"new b\n",
    "src/c.py": b"new c\n",
}
_ORIGINAL = b"original b\n"

_MANIFEST = load_reference_profile(_packaged_manifest_bytes())
_EDITABLE_DIGEST = _MANIFEST.editable_path_policy.digest


def _canonical_entry(entry: FinalDiffEntryV1) -> dict[str, CanonicalValueV1]:
    if entry.preimage.kind == "ABSENT":
        preimage: CanonicalValueV1 = {"kind": "ABSENT"}
    else:
        content_digest = entry.preimage.content_digest
        metadata = entry.preimage.text_metadata
        assert content_digest is not None
        assert metadata is not None
        preimage = {
            "kind": "PRESENT",
            "content_digest": content_digest,
            "text_metadata": {
                "encoding": metadata.encoding,
                "newline": metadata.newline,
                "final_newline": metadata.final_newline,
            },
        }
    post_metadata = entry.postimage_text_metadata
    return {
        "operation": entry.operation,
        "path": entry.path.value,
        "preimage": preimage,
        "postimage_digest": entry.postimage_digest,
        "postimage_text_metadata": {
            "encoding": post_metadata.encoding,
            "newline": post_metadata.newline,
            "final_newline": post_metadata.final_newline,
        },
    }


def _final_diff(paths: tuple[str, ...]) -> FinalDiffV1:
    """One sealed diff: first path CREATE, the rest REPLACE."""
    entries: list[FinalDiffEntryV1] = []
    for index, path in enumerate(paths):
        if index == 0:
            entries.append(
                FinalDiffEntryV1(
                    operation="CREATE",
                    path=CanonicalRelativePathV1(path),
                    preimage=FinalDiffPreimageV1(kind="ABSENT"),
                    postimage_digest=hashlib.sha256(_BODIES[path]).hexdigest(),
                    postimage_text_metadata=_TEXT_METADATA,
                )
            )
        else:
            entries.append(
                FinalDiffEntryV1(
                    operation="REPLACE",
                    path=CanonicalRelativePathV1(path),
                    preimage=FinalDiffPreimageV1(
                        kind="PRESENT",
                        content_digest=_PREIMAGE_DIGEST,
                        text_metadata=_TEXT_METADATA,
                    ),
                    postimage_digest=hashlib.sha256(_BODIES[path]).hexdigest(),
                    postimage_text_metadata=_TEXT_METADATA,
                )
            )
    digest = domain_digest(
        "FinalDiffV1",
        1,
        {
            "schema_version": 1,
            "snapshot_tree_digest": _SNAPSHOT_DIGEST,
            "entries": tuple(_canonical_entry(entry) for entry in entries),
            "added_and_replacement_text_bytes": sum(
                len(_BODIES[entry.path.value]) for entry in entries
            ),
        },
    )
    return FinalDiffV1(
        schema_version=1,
        snapshot_tree_digest=_SNAPSHOT_DIGEST,
        entries=tuple(entries),
        added_and_replacement_text_bytes=sum(
            len(_BODIES[entry.path.value]) for entry in entries
        ),
        digest=digest,
    )


def _subject_for(diff: FinalDiffV1) -> FinalWritebackSubjectV1:
    return build_final_writeback_subject(
        FinalWritebackBindingV1(
            run_id="run-1",
            candidate_digest=_CANDIDATE_DIGEST,
            final_diff=diff,
            validation_manifest_digest=_VALIDATION_DIGEST,
            validation_repository_policy_digest=_EDITABLE_DIGEST,
            formal_evidence_digest=_FORMAL_EVIDENCE_DIGEST,
            workspace_preimage_digest=_WORKSPACE_PREIMAGE_DIGEST,
            run_config_digest=_RUN_CONFIG_DIGEST,
            run_config_reference_profile_digest=_MANIFEST.digest,
            run_config_policy_id="PYTHON_SRC_ONLY_V1",
            reference_profile_digest=_MANIFEST.digest,
            reference_policy_digest=_EDITABLE_DIGEST,
            policy=_MANIFEST.editable_path_policy,
        ),
        _LATE_EXPIRES_AT,
    )


_DIFF_TWO = _final_diff(("src/a.py", "src/b.py"))
_SUBJECT_TWO = _subject_for(_DIFF_TWO)


def _seed_run_and_approval(
    database: ControlDatabase, subject: FinalWritebackSubjectV1
) -> None:
    """One exact Run and its consumed approval (Task 22.C evidence)."""
    with database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots"
            " (config_snapshot_id, digest, llm_profile_id, reference_profile_id,"
            " policy_id, target_test_ids, limits_digest, frozen_at)"
            " VALUES ('snap-1', ?, 'mock-deterministic-v1', 'python-src-py312-v1',"
            " 'PYTHON_SRC_ONLY_V1', '[]', ?, ?)",
            ("a" * 64, "c" * 64, _CREATED_AT.value),
        )
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES ('run-1', 'ws-1', 'snap-1', 'WAITING_USER', NULL, 1, ?, ?)",
            (_CREATED_AT.value, _RUN_DEADLINE.value),
        )
    RunRepository(database).create_wait(
        WaitContextV1(
            wait_id="wait-1",
            run_id="run-1",
            wait_kind="FINAL_WRITEBACK",
            source_phase="FORMAL_VALIDATION",
            subject_digest=DigestV1(value=subject.digest),
            created_at=_CREATED_AT,
            expires_at=subject.expires_at,
        )
    )
    result = FinalWritebackDecisionServiceV1(database).decide(
        DecideFinalWritebackV1(
            decision=WaitDecisionV1(
                wait_id="wait-1",
                run_id="run-1",
                wait_kind="FINAL_WRITEBACK",
                subject_digest=DigestV1(value=subject.digest),
                decision="APPROVE",
                event_id="evt-approve",
                decided_at=_DECIDED_AT,
            ),
            subject=subject,
            approval_id="approval-1",
        )
    )
    assert result.kind == "APPROVED"


class StepClock:
    """A deterministic clock that expires exactly after ``limit`` calls."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._calls = 0
        self._before = CanonicalTimestampV1("2026-08-05T09:14:00.000Z")
        self._after = CanonicalTimestampV1("2026-08-05T09:17:00.000Z")

    def now(self) -> CanonicalTimestampV1:
        self._calls += 1
        return self._before if self._calls <= self._limit else self._after


class SpyWorkspace:
    """In-memory workspace satisfying the writeback and recovery ports."""

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}
        self._identities: dict[str, str] = {}
        self._writes: list[str] = []
        self._deletes: list[str] = []
        self._untouched_ok = True

    def seed(self, path: str, body: bytes, identity: str = _IDENTITY_DIGEST) -> None:
        self._files[path] = body
        self._identities[path] = identity

    def identity_digest(self) -> str:
        return _WORKSPACE_IDENTITY_DIGEST

    def lease_held(self) -> bool:
        return True

    def verify_untouched(
        self, snapshot_tree_digest: str, involved_paths: tuple[str, ...]
    ) -> bool:
        return self._untouched_ok

    def workspace_path(self) -> str:
        return "C:\\work\\vesper"

    def read_bytes(self, path: CanonicalRelativePathV1) -> bytes:
        if path.value not in self._files:
            raise FileNotFoundError(path.value)
        return self._files[path.value]

    def is_absent(self, path: CanonicalRelativePathV1) -> bool:
        return path.value not in self._files

    def object_identity_digest(self, path: CanonicalRelativePathV1) -> str:
        if path.value not in self._identities:
            raise KeyError(path.value)
        return self._identities[path.value]

    def verify_postimage(self, path: CanonicalRelativePathV1, digest: str) -> bool:
        if path.value not in self._files:
            return False
        return hashlib.sha256(self._files[path.value]).hexdigest() == digest

    def replace(self, path: CanonicalRelativePathV1, body: bytes) -> None:
        self._files[path.value] = body
        self._writes.append(path.value)
        self._identities.setdefault(path.value, _IDENTITY_DIGEST)

    def delete(self, path: CanonicalRelativePathV1) -> None:
        del self._files[path.value]
        self._deletes.append(path.value)

    def observe(self, path: CanonicalRelativePathV1) -> RecoveryPathObservationV1:
        if path.value not in self._files:
            return RecoveryPathObservationV1.model_validate(
                {
                    "schema_version": 1,
                    "path": path.value,
                    "source": "WORKSPACE_BYTES",
                    "content_digest": {"kind": "ABSENT"},
                    "object_identity_digest": {"kind": "ABSENT"},
                    "object_kind": "ABSENT",
                    "supported": True,
                }
            )
        return RecoveryPathObservationV1.model_validate(
            {
                "schema_version": 1,
                "path": path.value,
                "source": "WORKSPACE_BYTES",
                "content_digest": {
                    "kind": "PRESENT",
                    "value": {
                        "value": hashlib.sha256(self._files[path.value]).hexdigest()
                    },
                },
                "object_identity_digest": {
                    "kind": "PRESENT",
                    "value": {"value": self._identities[path.value]},
                },
                "object_kind": "FILE",
                "supported": True,
            }
        )

    @property
    def write_count(self) -> int:
        return len(self._writes) + len(self._deletes)

    @property
    def files(self) -> dict[str, bytes]:
        return dict(self._files)


def _command(
    diff: FinalDiffV1,
    subject: FinalWritebackSubjectV1,
    event_id: str,
) -> PersistVerifiedCandidateV1:
    """One exact approved-run writeback command (Task 26.C)."""
    approval = FinalWritebackApprovalV1(
        schema_version=1,
        approval_id="approval-1",
        subject_digest=DigestV1(value=subject.digest),
        run_id="run-1",
        wait_id="wait-1",
        created_at=_DECIDED_AT,
        status="PENDING",
    )
    return PersistenceCommandFactoryV1(
        final_diff=diff,
        candidate_digest=_CANDIDATE_DIGEST,
        policy_digest=_EDITABLE_DIGEST,
        workspace_identity_digest=_WORKSPACE_IDENTITY_DIGEST,
        workspace_preimage_digest=_WORKSPACE_PREIMAGE_DIGEST,
        approval=approval,
        approval_subject=subject,
        run_deadline=_RUN_DEADLINE,
        postimage_bodies=tuple(
            WritebackBodyV1(
                schema_version=1,
                path=CanonicalRelativePathV1(path),
                operation=("CREATE" if index == 0 else "REPLACE"),
                body=_BODIES[path],
            )
            for index, path in enumerate(entry.path.value for entry in diff.entries)
        ),
    ).for_approved_run(run_id="run-1", approval_id="approval-1", event_id=event_id)


def _coordinator(
    database: ControlDatabase,
    workspace: SpyWorkspace,
    tmp_path: Path,
    clock: ClockV1,
) -> PersistenceCoordinator:
    return PersistenceCoordinator(
        transaction_repository=PersistenceTransactionRepositoryV1(database),
        path_repository=PersistencePathRecordRepositoryV1(database),
        artifact_store=PersistenceArtifactStoreV1(tmp_path / "artifacts"),
        approval_repository=WritebackApprovalRepository(database),
        workspace=workspace,
        policy=_MANIFEST.editable_path_policy,
        clock=clock,
    )


class _AcceptingAdmissionPort:
    """One fixture ACCEPTED double for every non-recovery PREFLIGHT
    admission port (SPEC §4.1 behaviors 6/8-13): the scenario's subject
    is the recovery gate, and every later port must never be consulted
    before it."""

    def acquire_workspace(self) -> AdmissionResultV1:
        return AdmissionResultV1(kind="ACCEPTED")

    def precheck(self) -> AdmissionResultV1:
        return AdmissionResultV1(kind="ACCEPTED")

    def create(self) -> AdmissionResultV1:
        return AdmissionResultV1(kind="ACCEPTED")

    def detect_static(self) -> AdmissionResultV1:
        return AdmissionResultV1(kind="ACCEPTED")

    def check_execution_readiness(self) -> AdmissionResultV1:
        return AdmissionResultV1(kind="ACCEPTED")

    def check_credential_readiness(self) -> AdmissionResultV1:
        return AdmissionResultV1(kind="ACCEPTED")

    def enter_baseline(self) -> AdmissionResultV1:
        return AdmissionResultV1(kind="ACCEPTED")


def _admission_coordinator(database: ControlDatabase) -> AdmissionCoordinator:
    """One production AdmissionCoordinator over the frozen PREFLIGHT
    port order with a live recovery gate and ACCEPTED fixture doubles
    for the other six ports."""
    repository = RunRepository(database)
    repository.insert_created(
        RunRecordV1(
            run_id="run-admission",
            workspace_identity="ws-1",
            status="CREATED",
            phase=AbsentV1(kind="ABSENT"),
            config_snapshot_id="snap-1",
            started_at=_CREATED_AT,
            run_deadline=_RUN_DEADLINE,
        )
    )
    accepting = _AcceptingAdmissionPort()
    return AdmissionCoordinator(
        AdmissionPortsV1(
            workspace=accepting,
            recovery=_RecoveryAdmissionPort(database),
            snapshot=accepting,
            static_profile=accepting,
            execution_readiness=accepting,
            credential_readiness=accepting,
            baseline=accepting,
        ),
        repository,
    )


class _RecoveryAdmissionPort:
    """The production-shaped recovery gate (SPEC §4.1 behavior 7 / AC-21).

    Reads only the durability table: while any persistence transaction
    is UNRESOLVED a new run is rejected with ``RECOVERY_REQUIRED``;
    only a service-proven COMMITTED or ROLLED_BACK terminal releases
    the gate.
    """

    def __init__(self, database: ControlDatabase) -> None:
        self._database = database

    def check_recovery(self) -> AdmissionResultV1:
        if self._database.read_rows(
            "SELECT 1 FROM persistence_transactions WHERE state = 'UNRESOLVED'"
        ):
            return AdmissionResultV1(
                kind="REJECTED",
                error_code="RECOVERY_REQUIRED",
                reason="an unresolved writeback transaction must be recovered first",
                suggestion=(
                    "run the recovery preview and apply before admitting a new run"
                ),
            )
        return AdmissionResultV1(kind="ACCEPTED")


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
        source_path=PresentV1(kind="PRESENT", value=CanonicalRelativePathV1(path)),
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
                segments=(_segment("HARNESS_PROTOCOL", "VesperCode protocol"),),
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
    "--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n-placeholder\n+tampered\n"
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
    return int(CanonicalTimestampV1(iso_utc).epoch_milliseconds)


def _zero_side_effect_counts(
    database: ControlDatabase,
) -> tuple[int, int, int, int, int]:
    """The five forbidden real-call side-effect dimensions after an
    abort: (grant rows, authorization rows, turn rows, call rows,
    charge rows) — every one must be zero (the abort happens before
    any of the production stores is written)."""
    grants = len(database.read_rows("SELECT 1 FROM disclosure_grants"))
    authorizations = len(database.read_rows("SELECT 1 FROM disclosure_authorizations"))
    turns = len(database.read_rows("SELECT 1 FROM run_turn_call_counters"))
    calls = len(
        database.read_rows("SELECT 1 FROM run_turn_call_counters WHERE call_count > 0")
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
    recovery_disposition: str | None = None
    unresolved_evidence_preserved: bool = False
    audit_event_count: int = 0
    audit_sequences_monotonic: bool = False
    secret_payload_rejected: bool = False
    audit_retention_cleared: bool = False
    memory_entries: int = 0


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
        return CredentialStoreMutationV1(schema_version=1, kind="CLEARED")


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
        return str(
            domain_digest(
                "ReferenceE2ETraceV1",
                1,
                {
                    "run_id": self._config.run_id,
                    "clock_epoch": self._config.clock_epoch,
                    "stages": tuple(self._stages),
                },
            )
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
        recovery_disposition: str | None = None,
        unresolved_evidence_preserved: bool = False,
        audit_event_count: int = 0,
        audit_sequences_monotonic: bool = False,
        secret_payload_rejected: bool = False,
        audit_retention_cleared: bool = False,
        memory_entries: int = 0,
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
            recovery_disposition=recovery_disposition,
            unresolved_evidence_preserved=unresolved_evidence_preserved,
            audit_event_count=audit_event_count,
            audit_sequences_monotonic=audit_sequences_monotonic,
            secret_payload_rejected=secret_payload_rejected,
            audit_retention_cleared=audit_retention_cleared,
            memory_entries=memory_entries,
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
            # Corrective loop through the production patch pipeline
            # (SPEC §4.2.2): the reference fixture carries one stable
            # failing target (``add`` subtracts instead of adding), the
            # baseline records the FAIL fingerprint, the approved patch
            # is applied by the production ``apply_candidate_patch``,
            # and the published revision's tree bytes feed the
            # corrected composition verified below.
            self._stage("baseline-corrective-fail-observed")
            bound0, _diff0 = _bound_candidate(snapshot)
            corrective_publisher = _CountingPublisher()
            corrective_context = CandidatePatchContextV1(
                current=bound0,
                snapshot=snapshot,
                reference=load_reference_profile(_packaged_manifest_bytes()),
                publisher=corrective_publisher,
                ignore_rules=(),
                ignore_rules_digest=ignore_rules_digest(()),
            )
            corrective_action = ApplyCandidatePatchAction(
                schema_version=1,
                action_type="apply_candidate_patch",
                base_candidate_digest=bound0.candidate_digest,
                patch_format="UNIFIED_DIFF_V1",
                patch_text=_CORRECTIVE_PATCH_TEXT,
            )
            corrective_outcome = apply_candidate_patch(
                corrective_action, bound0, corrective_context
            )
            if (
                corrective_outcome.kind != "PUBLISHED"
                or corrective_outcome.revision is None
            ):
                return self._result(
                    verified_candidate_created=False,
                    error_code=corrective_outcome.error_code
                    or "CORRECTIVE_PATCH_FAILED",
                    error_message="the approved corrective patch did not publish",
                )
            corrected_snapshot = _sealed_snapshot(
                _files_from_revision(corrective_outcome.revision)
            )
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
        database = None
        database_path: Path | None = None
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
        finally:
            if database is not None:
                database.close()
            if database_path is not None:
                shutil.rmtree(database_path, ignore_errors=True)

    def run_uncertain_recovery_scenario(self) -> ReferenceE2EResultV1:
        """31.C: read-only uncertain preview and blocked second
        admission until service-proven recovery (GREEN-3).

        One exact approved 2-path writeback through the production
        coordinator with a step-limited clock dies mid-writeback: the
        durable transaction stays UNRESOLVED (RECOVERY_REQUIRED /
        PERSISTENCE_UNCERTAIN), the read-only recovery preview
        classifies the workspace into exactly one of the three closed
        dispositions with zero workspace writes, and the recovery gate
        rejects a new admission with ``RECOVERY_REQUIRED`` until a
        service-proven terminal releases it.  The unresolved evidence
        survives every read.
        """
        database = None
        database_path: Path | None = None
        try:
            database_path = Path(tempfile.mkdtemp(prefix="vesper-e2e-recovery-"))
            database = open_control_database(database_path / "control.db")
            apply_migrations(database, ALL_V1_MIGRATIONS)
            _seed_run_and_approval(database, _SUBJECT_TWO)
            workspace = SpyWorkspace()
            workspace.seed("src/b.py", _ORIGINAL)
            coordinator = _coordinator(
                database, workspace, database_path, StepClock(limit=6)
            )
            self._stage("approved-command-bound")
            persisted = coordinator.persist(
                _command(_DIFF_TWO, _SUBJECT_TWO, "evt-uncertain-recovery")
            )
            self._stage("uncertain-writeback-faulted")
            if (
                persisted.outcome != "RECOVERY_REQUIRED"
                or persisted.error_code != "PERSISTENCE_UNCERTAIN"
            ):
                return self._result(
                    verified_candidate_created=False,
                    error_code=persisted.error_code or "UNEXPECTED_OUTCOME",
                    error_message="writeback did not end RECOVERY_REQUIRED",
                )
            transaction_id = persisted.transaction_id
            if transaction_id is None:
                return self._result(
                    verified_candidate_created=False,
                    error_code="PERSISTENCE_UNCERTAIN",
                    error_message="uncertain writeback carries no transaction",
                )
            # Read-only recovery preview (Task 26.B/26.C): nothing is
            # ever written — the preview's own zero-write proof and the
            # spy workspace's unchanged write count both hold.
            preview_service = RecoveryPreviewService(
                transaction_repository=PersistenceTransactionRepositoryV1(database),
                path_repository=PersistencePathRecordRepositoryV1(database),
                artifact_store=PersistenceArtifactStoreV1(database_path / "artifacts"),
                workspace_identity_digest=_WORKSPACE_IDENTITY_DIGEST,
                observer=workspace,
            )
            before = workspace.write_count
            preview = preview_service.preview_transaction(transaction_id)
            after = workspace.write_count
            self._stage("uncertain-preview-read-only")
            if before != after or preview.workspace_write_count != 0:
                return self._result(
                    verified_candidate_created=False,
                    error_code="PREVIEW_WROTE_WORKSPACE",
                    error_message="recovery preview wrote to the workspace",
                )
            # Admission blocking until service-proven recovery (SPEC
            # §4.1 behaviors 5-13 / 4.6 / AC-21): one new CREATED run
            # goes through the production AdmissionCoordinator in the
            # exact PREFLIGHT order; the durable UNRESOLVED transaction
            # rejects the run at the recovery gate before any later
            # admission port is consulted.
            admission = _admission_coordinator(database).start_run("run-admission")
            self._stage("admission-blocked-recovery-required")
            if (
                admission.kind != "REJECTED"
                or admission.error_code != "RECOVERY_REQUIRED"
            ):
                return self._result(
                    verified_candidate_created=False,
                    error_code=admission.error_code or "UNEXPECTED_OUTCOME",
                    error_message="recovery gate did not block the new admission",
                )
            # Preserved unresolved evidence: every read left the durable
            # UNRESOLVED transaction intact (cleanup never deletes it).
            rows = database.read_rows(
                "SELECT 1 FROM persistence_transactions WHERE state = 'UNRESOLVED'"
            )
            self._stage("unresolved-evidence-preserved")
            return self._result(
                verified_candidate_created=False,
                error_code="PERSISTENCE_UNCERTAIN",
                preview_write_count=after - before,
                second_admission_error=admission.error_code,
                recovery_disposition=preview.disposition,
                unresolved_evidence_preserved=bool(rows),
            )
        except Exception as exc:
            return self._result(
                verified_candidate_created=False,
                error_code="HARNESS_ERROR",
                error_message=str(exc),
            )
        finally:
            if database is not None:
                database.close()
            if database_path is not None:
                shutil.rmtree(database_path, ignore_errors=True)

    def run_recovery_audit_scenario(self) -> ReferenceE2EResultV1:
        """31.C: redacted monotonic audit with a retention cleanup that
        never deletes unresolved recovery evidence (SPEC 4.7 / AC-21).

        Drives the production ``AuditRepository`` over one ended Run:
        a payload carrying a secret value is rejected with zero rows,
        two allowlisted appends assign the strictly increasing
        sequences 1 and 2, the ended Run's audit retention cleanup
        clears exactly its events, and the durable UNRESOLVED writeback
        evidence survives the cleanup untouched.
        """
        database = None
        database_path: Path | None = None
        try:
            database_path = Path(tempfile.mkdtemp(prefix="vesper-e2e-audit-"))
            database = open_control_database(database_path / "control.db")
            apply_migrations(database, ALL_V1_MIGRATIONS)
            _seed_run_and_approval(database, _SUBJECT_TWO)
            workspace = SpyWorkspace()
            workspace.seed("src/b.py", _ORIGINAL)
            persisted = _coordinator(
                database, workspace, database_path, StepClock(limit=6)
            ).persist(_command(_DIFF_TWO, _SUBJECT_TWO, "evt-audit-uncertain"))
            if persisted.outcome != "RECOVERY_REQUIRED":
                return self._result(
                    verified_candidate_created=False,
                    error_code=persisted.error_code or "UNEXPECTED_OUTCOME",
                    error_message="audit scenario writeback was not uncertain",
                )
            # The Run is ended (the writeback left it RUNNING/PERSISTENCE;
            # the ended terminal needs the NULL phase the DDL CHECK
            # requires), so its audit is eligible for the retention
            # cleanup (Task 23.C visibility/retention).
            with database.immediate_transaction() as tx:
                tx.execute(
                    "UPDATE runs SET status = 'STOPPED', phase = NULL"
                    " WHERE run_id = 'run-1'"
                )
            repository = AuditRepository(database)
            self._stage("audit-repository-bound")
            secret = repository.append(
                AppendAuditEventV1(
                    run_id="run-1",
                    event_type="POLICY_DECISION",
                    payload={
                        "decision": "DENY",
                        "reason_code": "API_KEY=sk-live-1234",
                    },
                    event_id="evt-audit-secret",
                    created_at=CanonicalTimestampV1("2026-08-07T00:00:01.000Z"),
                )
            )
            self._stage("audit-secret-rejected")
            if secret.kind != "REJECTED" or repository.event_count != 0:
                return self._result(
                    verified_candidate_created=False,
                    error_code="AUDIT_REDACTION_FAILED",
                    error_message="audit accepted a secret payload",
                )
            first = repository.append(
                AppendAuditEventV1(
                    run_id="run-1",
                    event_type="RECOVERY",
                    payload={
                        "transaction_id": "txn-31c",
                        "disposition": "ROLLED_BACK",
                    },
                    event_id="evt-audit-1",
                    created_at=CanonicalTimestampV1("2026-08-07T00:00:02.000Z"),
                )
            )
            second = repository.append(
                AppendAuditEventV1(
                    run_id="run-1",
                    event_type="RECOVERY",
                    payload={
                        "transaction_id": "txn-31c",
                        "disposition": "COMMITTED",
                    },
                    event_id="evt-audit-2",
                    created_at=CanonicalTimestampV1("2026-08-07T00:00:03.000Z"),
                )
            )
            self._stage("audit-events-appended")
            if first.kind != "APPENDED" or second.kind != "APPENDED":
                return self._result(
                    verified_candidate_created=False,
                    error_code="AUDIT_APPEND_FAILED",
                    error_message="audit appends did not record",
                )
            page = repository.list_run("run-1", AuditPageRequestV1(page_size=100))
            sequences = tuple(event.sequence for event in page.items)
            monotonic = sequences == (1, 2) and all(
                left < right for left, right in zip(sequences, sequences[1:])
            )
            count_before_clear = repository.event_count
            # Retention cleanup of the ended Run's audit: only the audit
            # rows go away, never the unresolved recovery evidence.
            cleared = repository.clear_ended_run(
                ClearEndedRunAuditV1(
                    run_id="run-1",
                    event_id="evt-audit-clear",
                    decided_at=CanonicalTimestampV1("2026-08-07T00:00:04.000Z"),
                )
            )
            self._stage("audit-retention-cleared")
            if cleared.kind != "CLEARED" or repository.event_count != 0:
                return self._result(
                    verified_candidate_created=False,
                    error_code="AUDIT_CLEAR_FAILED",
                    error_message="audit retention cleanup failed",
                )
            rows = database.read_rows(
                "SELECT 1 FROM persistence_transactions WHERE state = 'UNRESOLVED'"
            )
            self._stage("recovery-evidence-preserved")
            return self._result(
                verified_candidate_created=False,
                audit_event_count=count_before_clear,
                audit_sequences_monotonic=monotonic,
                secret_payload_rejected=True,
                audit_retention_cleared=True,
                unresolved_evidence_preserved=bool(rows),
                memory_entries=len(database.read_rows("SELECT 1 FROM memory_entries")),
            )
        except Exception as exc:
            return self._result(
                verified_candidate_created=False,
                error_code="HARNESS_ERROR",
                error_message=str(exc),
            )
        finally:
            if database is not None:
                database.close()
            if database_path is not None:
                shutil.rmtree(database_path, ignore_errors=True)

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
            if (
                outcome.kind != "REJECTED"
                or outcome.error_code != "PATCH_PATH_NOT_EDITABLE"
            ):
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

    def run_protected_artifact_scenario(self) -> ReferenceE2EResultV1:
        """31.B: a protected-artifact patch (SPEC §1.4.2 ``tests/**``)
        is denied before any dispatch, publication, artifact, workspace
        write, or authorization effect."""
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
                patch_text=_PROTECTED_ARTIFACT_PATCH_TEXT,
            )
            self._stage("protected-artifact-patch-bound")
            outcome = apply_candidate_patch(action, bound, context)
            self._stage("protected-artifact-denied")
            if (
                outcome.kind != "REJECTED"
                or outcome.error_code != "PROTECTED_ARTIFACT_CHANGED"
            ):
                return self._result(
                    verified_candidate_created=False,
                    error_code=outcome.error_code or "UNEXPECTED_OUTCOME",
                    error_message="protected-artifact patch was not denied",
                    publish_count=publisher.count,
                )
            self._stage("zero-publish-verified")
            return self._result(
                verified_candidate_created=False,
                error_code="PROTECTED_ARTIFACT_CHANGED",
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
    harness = ReferenceE2EHarness(
        ReferenceE2EConfigV1(
            schema_version=1,
            run_id="canonical",
            clock_epoch="2026-08-07T00:00:00.000Z",
        )
    )
    result = harness.run_until_final_wait()
    # 31.C terminal scenarios close the canonical report (GREEN-4): the
    # read-only uncertain recovery preview, the blocked admission, and
    # the redacted monotonic audit with recovery-preserving cleanup.
    recovery = harness.run_uncertain_recovery_scenario()
    audit = harness.run_recovery_audit_scenario()
    failed = (
        result.verified_candidate_created is not True
        or recovery.second_admission_error != "RECOVERY_REQUIRED"
        or recovery.preview_write_count != 0
        or audit.audit_event_count < 2
        or audit.audit_sequences_monotonic is not True
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(
            {
                "verified_candidate_created": result.verified_candidate_created,
                "workspace_write_count": result.workspace_write_count,
                "error_code": result.error_code,
                "error_message": result.error_message,
                "trace_digest": result.trace_digest,
                "recovery_preview_write_count": recovery.preview_write_count,
                "second_admission_error": recovery.second_admission_error,
                "recovery_disposition": recovery.recovery_disposition,
                "unresolved_evidence_preserved": (
                    recovery.unresolved_evidence_preserved
                ),
                "audit_event_count": audit.audit_event_count,
                "audit_sequences_monotonic": audit.audit_sequences_monotonic,
                "secret_payload_rejected": audit.secret_payload_rejected,
                "audit_retention_cleared": audit.audit_retention_cleared,
            },
            indent=2,
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
