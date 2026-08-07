"""T33.1 legacy step 33.A: versioned wheel contents tests.

The exact RED pins one clean wheel containing every declared runtime
module/template/static asset (the frozen console entry point included)
and excluding tests, source evidence, credentials, VCS data, and
prohibited members (GREEN-1); the artifact matrix pins the one
filename/version/RECORD/resource/digest/entry-point contract of the
exact §5.1 wheel artifact matrix (Expected 33.A: one wheel, correct
filename/version/RECORD/resources, independent digest, zero prohibited
member).
"""

from __future__ import annotations

import hashlib
from typing import Final

import pytest

from scripts.run_package_smoke import WheelArchive

pytestmark = pytest.mark.package_smoke

PROJECT_VERSION_V1: Final = "0.1.0"
"""The frozen distribution version (pyproject [project] ``version``)."""

_PACKAGED_HTMX_SHA256_V1: Final = (
    "e209dda5c8235479f3166defc7750e1dbcd5a5c1808b7792fc2e6733768fb447"
)
"""The pinned packaged htmx asset SHA-256 (Task 28.C identity)."""

_PACKAGED_HTMX_BYTE_LENGTH_V1: Final = 50917
"""The pinned packaged htmx asset byte length (Task 28.C identity)."""

REQUIRED_RUNTIME_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "vespercode/__init__.py",
        "vespercode/audit/event.py",
        "vespercode/audit/projection.py",
        "vespercode/audit/repository.py",
        "vespercode/audit/retention.py",
        "vespercode/candidate/final_diff.py",
        "vespercode/candidate/identity.py",
        "vespercode/candidate/patch_engine.py",
        "vespercode/candidate/unified_diff.py",
        "vespercode/canonical/clock.py",
        "vespercode/canonical/digest.py",
        "vespercode/canonical/json_v1.py",
        "vespercode/canonical/path_v1.py",
        "vespercode/canonical/timestamp_v1.py",
        "vespercode/cli.py",
        "vespercode/cli_composition.py",
        "vespercode/contracts/action.py",
        "vespercode/contracts/evidence.py",
        "vespercode/contracts/location.py",
        "vespercode/contracts/optional.py",
        "vespercode/contracts/run.py",
        "vespercode/credentials/port.py",
        "vespercode/credentials/service.py",
        "vespercode/credentials/wincred_store.py",
        "vespercode/demo/app.py",
        "vespercode/demo/executor.py",
        "vespercode/demo/healthcheck.py",
        "vespercode/demo/runner.py",
        "vespercode/demo/scenario.py",
        "vespercode/demo/templates/demo.html",
        "vespercode/demo/types.py",
        "vespercode/execution/cleanup.py",
        "vespercode/execution/docker_executor.py",
        "vespercode/execution/docker_profile.py",
        "vespercode/execution/materialization.py",
        "vespercode/governance/disclosure_decision.py",
        "vespercode/governance/disclosure_ledger.py",
        "vespercode/governance/disclosure_revocation.py",
        "vespercode/governance/disclosure_scope.py",
        "vespercode/governance/disclosure_subject.py",
        "vespercode/governance/policy.py",
        "vespercode/governance/request_sources.py",
        "vespercode/governance/writeback_approval.py",
        "vespercode/governance/writeback_decision.py",
        "vespercode/governance/writeback_subject.py",
        "vespercode/llm/base.py",
        "vespercode/llm/call_result.py",
        "vespercode/llm/mock_adapter.py",
        "vespercode/llm/openai_adapter.py",
        "vespercode/llm/openai_serializer.py",
        "vespercode/llm/prepared_request.py",
        "vespercode/loop/action_binding.py",
        "vespercode/loop/action_parser.py",
        "vespercode/loop/action_pipeline.py",
        "vespercode/loop/agent_actions.py",
        "vespercode/loop/call_orchestrator.py",
        "vespercode/loop/cancellation.py",
        "vespercode/loop/context_projection.py",
        "vespercode/loop/engine.py",
        "vespercode/loop/feedback.py",
        "vespercode/loop/feedback_consumption.py",
        "vespercode/loop/progress.py",
        "vespercode/loop/restart.py",
        "vespercode/loop/stopping.py",
        "vespercode/loop/turn_boundary.py",
        "vespercode/loop/wait_control.py",
        "vespercode/memory/clear.py",
        "vespercode/memory/entry.py",
        "vespercode/memory/repository.py",
        "vespercode/memory/selection.py",
        "vespercode/persistence/artifacts.py",
        "vespercode/persistence/path_record.py",
        "vespercode/persistence/recovery.py",
        "vespercode/persistence/recovery_apply.py",
        "vespercode/persistence/recovery_preview.py",
        "vespercode/persistence/transaction.py",
        "vespercode/persistence/writeback.py",
        "vespercode/profiles/builtin/mock-deterministic-v1.json",
        "vespercode/profiles/builtin/openai-single-turn-v1.json",
        "vespercode/profiles/builtin/reference-profile-v1.json",
        "vespercode/profiles/editable.py",
        "vespercode/profiles/endpoints.py",
        "vespercode/profiles/llm.py",
        "vespercode/profiles/reference.py",
        "vespercode/profiles/registry.py",
        "vespercode/project/dependency_closure.py",
        "vespercode/project/toolchain_promotion.py",
        "vespercode/runs/admission.py",
        "vespercode/runs/lifecycle.py",
        "vespercode/runs/request.py",
        "vespercode/storage/connection.py",
        "vespercode/storage/idempotency.py",
        "vespercode/storage/migration_engine.py",
        "vespercode/storage/migrations/__init__.py",
        "vespercode/storage/migrations/registry.py",
        "vespercode/storage/migrations/v0001_run_wait.py",
        "vespercode/storage/migrations/v0002_idempotency.py",
        "vespercode/storage/migrations/v0003_disclosure_grants.py",
        "vespercode/storage/migrations/v0004_disclosure_authorizations.py",
        "vespercode/storage/migrations/v0005_memory.py",
        "vespercode/storage/migrations/v0006_audit.py",
        "vespercode/storage/migrations/v0007_agent_turns.py",
        "vespercode/storage/migrations/v0008_feedback.py",
        "vespercode/storage/migrations/v0009_actions.py",
        "vespercode/storage/migrations/v0010_writeback_approvals.py",
        "vespercode/storage/migrations/v0011_persistence.py",
        "vespercode/storage/migrations/v0012_recovery.py",
        "vespercode/storage/run_repository.py",
        "vespercode/tools/dispatcher.py",
        "vespercode/tools/file_actions.py",
        "vespercode/tools/file_results.py",
        "vespercode/tools/list_files.py",
        "vespercode/tools/read_file.py",
        "vespercode/tools/search_text.py",
        "vespercode/trees/candidate.py",
        "vespercode/trees/content_store.py",
        "vespercode/trees/readable.py",
        "vespercode/trees/snapshot.py",
        "vespercode/trees/text_classifier.py",
        "vespercode/validation/baseline.py",
        "vespercode/validation/check_result.py",
        "vespercode/validation/failure_fingerprint.py",
        "vespercode/validation/formal.py",
        "vespercode/validation/formal_execution.py",
        "vespercode/validation/formal_plan.py",
        "vespercode/validation/manifest.py",
        "vespercode/validation/pytest_evidence.py",
        "vespercode/validation/pytest_reporter.py",
        "vespercode/validation/python_adapter.py",
        "vespercode/web/app.py",
        "vespercode/web/disclosure_workflow.py",
        "vespercode/web/local_composition.py",
        "vespercode/web/routes_audit.py",
        "vespercode/web/routes_credentials.py",
        "vespercode/web/routes_disclosure.py",
        "vespercode/web/routes_memory.py",
        "vespercode/web/routes_operations.py",
        "vespercode/web/routes_recovery.py",
        "vespercode/web/routes_runs.py",
        "vespercode/web/routes_writeback.py",
        "vespercode/web/run_lifecycle_workflow.py",
        "vespercode/web/run_workflows.py",
        "vespercode/web/security.py",
        "vespercode/web/static/htmx.min.js",
        "vespercode/web/templates/audit.html",
        "vespercode/web/templates/base.html",
        "vespercode/web/templates/components/status_badge.html",
        "vespercode/web/templates/credential_status.html",
        "vespercode/web/templates/disclosure_wait.html",
        "vespercode/web/templates/home.html",
        "vespercode/web/templates/memory.html",
        "vespercode/web/templates/recovery_preview.html",
        "vespercode/web/templates/run_create.html",
        "vespercode/web/templates/run_detail.html",
        "vespercode/web/writeback_workflow.py",
        "vespercode/workspace/git_preflight.py",
        "vespercode/workspace/identity_win32.py",
        "vespercode/workspace/mutex_win32.py",
        "vespercode/workspace/object_win32.py",
        "vespercode/workspace/path_guard.py",
        f"vespercode-{PROJECT_VERSION_V1}.dist-info/entry_points.txt",
    }
)
"""Every declared runtime module/template/static asset of the wheel plus
the frozen console entry point (33.A GREEN-1).  The dist-info member
name carries the frozen project version so the entry-point requirement
binds the exact versioned wheel."""

PROHIBITED_WHEEL_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        # tests and the source checkout never enter the wheel
        "tests",
        "tests/",
        "src",
        "src/",
        # source evidence and repository tooling never enter the wheel
        "reference",
        "reference/",
        "scripts",
        "scripts/",
        "docs",
        "docs/",
        "gates",
        "gates/",
        "process",
        "process/",
        "spikes",
        "spikes/",
        "config",
        "config/",
        "containers",
        "containers/",
        "requirements",
        "requirements/",
        "dist",
        "dist/",
        # VCS data never enters the wheel
        ".git",
        ".git/",
        ".gitignore",
        ".gitattributes",
        ".gitmodules",
        ".hg",
        ".hg/",
        ".svn",
        ".svn/",
        # Python bytecode and interpreter junk never enter the wheel
        "__pycache__",
        "__pycache__/",
        ".venv",
        ".venv/",
        ".venv-gate",
        ".venv-gate/",
        ".venv-formal",
        ".venv-formal/",
        # credential files never enter the wheel (the runtime
        # ``vespercode/credentials`` module is required, not prohibited)
        ".env",
        ".env.local",
        ".env.production",
        ".env.example",
        "id_rsa",
        "id_rsa.pub",
        "id_ed25519",
        "id_ed25519.pub",
        "credentials.json",
        "keyring.json",
    }
)
"""The exact closed set of prohibited wheel members (tests, source
evidence, credentials, VCS data, and junk prefixes).  ``WheelArchive``
expands every member's ancestor directory prefixes, so the disjoint
check catches any prohibited name or prefix."""


def test_built_wheel_contains_all_runtime_resources(
    built_wheel: WheelArchive,
) -> None:
    assert REQUIRED_RUNTIME_MEMBERS <= built_wheel.members
    assert PROHIBITED_WHEEL_MEMBERS.isdisjoint(built_wheel.members)


def test_wheel_artifact_matrix(built_wheel: WheelArchive) -> None:
    """The exact wheel artifact matrix (Expected 33.A).

    Pins exactly one versioned wheel with the correct filename/version,
    the frozen console entry point, the correct METADATA, the complete
    RECORD, the pinned packaged assets, the adjacent lowercase
    independent digest evidence, and zero prohibited member.
    """
    expected_name = f"vespercode-{PROJECT_VERSION_V1}-py3-none-any.whl"
    assert built_wheel.name == expected_name
    assert built_wheel.version == PROJECT_VERSION_V1
    wheels = list(built_wheel.wheel_path.parent.glob("vespercode-*.whl"))
    assert wheels == [built_wheel.wheel_path]

    # --- the frozen console entry point ---
    entry_points = built_wheel.member_bytes(
        f"vespercode-{PROJECT_VERSION_V1}.dist-info/entry_points.txt"
    ).decode("utf-8")
    assert "[console_scripts]" in entry_points
    assert "vespercode = vespercode.cli:main" in entry_points

    # --- the frozen distribution metadata ---
    metadata = built_wheel.member_bytes(
        f"vespercode-{PROJECT_VERSION_V1}.dist-info/METADATA"
    ).decode("utf-8")
    assert "Name: vespercode" in metadata
    assert f"Version: {PROJECT_VERSION_V1}" in metadata

    # --- the pinned packaged assets ship with their exact identity ---
    htmx = built_wheel.member_bytes("vespercode/web/static/htmx.min.js")
    assert len(htmx) == _PACKAGED_HTMX_BYTE_LENGTH_V1
    assert hashlib.sha256(htmx).hexdigest() == _PACKAGED_HTMX_SHA256_V1
    demo_template = built_wheel.member_bytes("vespercode/demo/templates/demo.html")
    assert (
        b"<!doctype html>" in demo_template.lower() or b"<html" in demo_template.lower()
    )
    reference_profile = built_wheel.member_bytes(
        "vespercode/profiles/builtin/reference-profile-v1.json"
    )
    assert b'"schema_version"' in reference_profile

    # --- RECORD lists every member exactly once ---
    recorded = {entry.path for entry in built_wheel.record_entries}
    assert recorded == set(built_wheel.member_names)

    # --- the adjacent lowercase SHA-256 evidence is independent ---
    assert built_wheel.evidence_path is not None
    assert built_wheel.evidence_path.name == f"{expected_name}.sha256"
    assert built_wheel.evidence_sha256 == built_wheel.sha256
    assert built_wheel.evidence_sha256.islower()

    # --- zero prohibited member ---
    assert PROHIBITED_WHEEL_MEMBERS.isdisjoint(built_wheel.members)
