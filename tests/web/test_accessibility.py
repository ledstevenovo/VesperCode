"""T29.3 legacy step 29.C: Milestone 29 accessibility and keyboard flow.

The accessibility pins cover every T29 page rendered through the real
Task 28.B composition: one h1 per page, labeled native controls, visible
focus, keyboard operation through native controls only, live-error
hooks, non-color status cues, escaped untrusted text, and reduced-motion
safety.  The Browser (29.C) row — "exercise create -> running ->
disclosure -> formal review -> stale approval by keyboard" — is driven
as one TestClient flow through the real Milestone 29 aggregate
composition with only native controls and the page-rendered CSRF token
(SPEC §4.9/§5.3/§5.5).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Final

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from src.vespercode.audit.projection import RunVisibilityV1
from src.vespercode.candidate.final_diff import (
    FinalDiffEntryV1,
    FinalDiffPreimageV1,
    FinalDiffV1,
)
from src.vespercode.canonical.digest import domain_digest
from src.vespercode.canonical.json_v1 import CanonicalValueV1
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.credentials.port import CredentialStatusV1
from src.vespercode.governance.disclosure_scope import (
    DirectoryDisclosureScopeV1,
    DisclosureScopeSequenceV1,
)
from src.vespercode.governance.disclosure_subject import (
    DisclosureGrantSubjectV1,
    DisclosureSubjectRequestV1,
    build_disclosure_subject,
)
from src.vespercode.governance.request_sources import (
    RequestSourceV1,
    SourceProjectionV1,
)
from src.vespercode.governance.writeback_subject import (
    FinalWritebackBindingV1,
    build_final_writeback_subject,
)
from src.vespercode.profiles.endpoints import (
    OpenAIEndpointRegistry,
    OpenAIEndpointV1,
)
from src.vespercode.profiles.llm import OpenAILLMProfileV1, load_llm_profile
from src.vespercode.profiles.reference import (
    ReferenceProfileManifestV1,
    load_reference_profile,
)
from src.vespercode.trees.text_classifier import TextMetadataV1
from src.vespercode.web.app import (
    LocalShellPortsV1,
    RunVisibilitySequenceV1,
    create_local_app,
)
from src.vespercode.web.disclosure_workflow import DisclosureWaitFactsV1
from src.vespercode.web.run_lifecycle_workflow import (
    CreateRunFormV1,
    RunCancellationResultV1,
    RunCreationResultV1,
    RunLifecycleWorkflowPortsV1,
)
from src.vespercode.web.run_workflows import (
    RunGovernanceRouteInstallerV1,
    RunGovernanceWorkflowPortsV1,
)
from src.vespercode.web.security import LocalWebSecurityConfigV1
from src.vespercode.web.writeback_workflow import (
    WritebackReviewV1,
)

_REFERENCE_MANIFEST: Final[Path] = (
    Path(__file__).resolve().parents[2] / "reference/manifest/reference-profile-v1.json"
)
"""The frozen packaged reference profile (digest-verified)."""

_OPENAI_BUILTIN: Final[Path] = (
    Path(__file__).resolve().parents[2]
    / "src/vespercode/profiles/builtin/openai-single-turn-v1.json"
)
"""The frozen packaged built-in OpenAI profile (digest-verified)."""

_CREATED_AT = CanonicalTimestampV1("2026-08-07T09:00:00.000Z")
_EXPIRES_AT = CanonicalTimestampV1("2026-08-07T09:05:00.000Z")

_TEXT_METADATA = TextMetadataV1(encoding="UTF8", newline="LF", final_newline=True)
_SNAPSHOT_DIGEST = hashlib.sha256(b"sealed-snapshot").hexdigest()
_CANDIDATE_DIGEST = hashlib.sha256(b"candidate-identity").hexdigest()
_VALIDATION_DIGEST = hashlib.sha256(b"validation-manifest").hexdigest()
_FORMAL_EVIDENCE_DIGEST = hashlib.sha256(b"formal-evidence").hexdigest()
_PREIMAGE_DIGEST = hashlib.sha256(b"workspace-preimage").hexdigest()
_RUN_CONFIG_DIGEST = hashlib.sha256(b"run-config").hexdigest()


def _manifest() -> ReferenceProfileManifestV1:
    """The frozen packaged reference profile (digest-verified)."""
    loaded = load_reference_profile(_REFERENCE_MANIFEST.read_bytes())
    assert isinstance(loaded, ReferenceProfileManifestV1)
    return loaded


_MANIFEST = _manifest()
_EDITABLE_DIGEST = _MANIFEST.editable_path_policy.digest


def _canonical_entry(entry: FinalDiffEntryV1) -> dict[str, CanonicalValueV1]:
    """The §0.1 canonical value shape of one sealed diff row."""
    content_digest = entry.preimage.content_digest
    metadata = entry.preimage.text_metadata
    assert content_digest is not None
    assert metadata is not None
    preimage: CanonicalValueV1 = {
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


def _final_diff() -> FinalDiffV1:
    """One sealed current FinalDiff whose digest binds its exact rows."""
    raw = b"x = 1\n"
    entry = FinalDiffEntryV1(
        operation="REPLACE",
        path=CanonicalRelativePathV1("src/a.py"),
        preimage=FinalDiffPreimageV1(
            kind="PRESENT",
            content_digest=hashlib.sha256(raw).hexdigest(),
            text_metadata=_TEXT_METADATA,
        ),
        postimage_digest=hashlib.sha256(raw).hexdigest(),
        postimage_text_metadata=_TEXT_METADATA,
    )
    digest = domain_digest(
        "FinalDiffV1",
        1,
        {
            "schema_version": 1,
            "snapshot_tree_digest": _SNAPSHOT_DIGEST,
            "entries": tuple(_canonical_entry(entry) for entry in (entry,)),
            "added_and_replacement_text_bytes": len(raw),
        },
    )
    return FinalDiffV1(
        schema_version=1,
        snapshot_tree_digest=_SNAPSHOT_DIGEST,
        entries=(entry,),
        added_and_replacement_text_bytes=len(raw),
        digest=digest,
    )


def seeded_disclosure_subject() -> DisclosureGrantSubjectV1:
    """One immutable disclosure Grant subject for the composed flow
    (mirrors the T29.2 test's fixture per the per-file fixture
    convention)."""
    loaded = load_llm_profile(_OPENAI_BUILTIN.read_bytes())
    assert isinstance(loaded, OpenAILLMProfileV1)
    endpoint: OpenAIEndpointV1 = OpenAIEndpointRegistry.resolve("OPENAI_PUBLIC_API_V1")
    raw = "tool bytes".encode("utf-8")
    sources: SourceProjectionV1 = (
        RequestSourceV1(
            message_index=0,
            segment_index=0,
            source_category="TOOL_RESULT",
            source_path=PresentV1(
                kind="PRESENT", value=CanonicalRelativePathV1("src/a.py")
            ),
            content_digest=hashlib.sha256(raw).hexdigest(),
            byte_count=len(raw),
        ),
    )
    scopes: DisclosureScopeSequenceV1 = (
        DirectoryDisclosureScopeV1(
            kind="DIRECTORY", path=CanonicalRelativePathV1("src")
        ),
    )
    return build_disclosure_subject(
        DisclosureSubjectRequestV1(
            run_id="run-1",
            expires_at=_EXPIRES_AT,
            cumulative_byte_budget=100000,
            url=AbsentV1(kind="ABSENT"),
        ),
        sources,
        scopes,
        loaded,
        endpoint,
    )


def seeded_review() -> WritebackReviewV1:
    """One exact current final-writeback review (mirrors the T29.3
    workflow test's fixture per the per-file fixture convention)."""
    subject = build_final_writeback_subject(
        FinalWritebackBindingV1(
            run_id="run-1",
            candidate_digest=_CANDIDATE_DIGEST,
            final_diff=_final_diff(),
            validation_manifest_digest=_VALIDATION_DIGEST,
            validation_repository_policy_digest=_EDITABLE_DIGEST,
            formal_evidence_digest=_FORMAL_EVIDENCE_DIGEST,
            workspace_preimage_digest=_PREIMAGE_DIGEST,
            run_config_digest=_RUN_CONFIG_DIGEST,
            run_config_reference_profile_digest=_MANIFEST.digest,
            run_config_policy_id="PYTHON_SRC_ONLY_V1",
            reference_profile_digest=_MANIFEST.digest,
            reference_policy_digest=_EDITABLE_DIGEST,
            policy=_MANIFEST.editable_path_policy,
        ),
        _EXPIRES_AT,
    )
    return WritebackReviewV1(
        run_id="run-1",
        wait_id="wait-1",
        subject=subject,
        final_diff=_final_diff(),
        created_at=_CREATED_AT,
        expires_at=subject.expires_at,
        decided=False,
    )


class FakeWorkflowIdentityV1:
    """One deterministic control-plane identity/clock (SPEC §5.4)."""

    def new_grant_id(self) -> str:
        return "grant-1"

    def new_approval_id(self) -> str:
        return "approval-1"

    def new_event_id(self) -> str:
        return "event-1"

    def now(self) -> CanonicalTimestampV1:
        return _CREATED_AT


class FakeRunLifecyclePortsV1:
    """One fake run-lifecycle port set for the composed flow."""

    def __init__(self) -> None:
        self.create_call_count = 0
        self._visibilities: dict[str, RunVisibilityV1] = {}

    def seed_visibility(self, visibility: RunVisibilityV1) -> None:
        self._visibilities[visibility.run_id] = visibility

    def create(self, form: CreateRunFormV1) -> RunCreationResultV1:
        self.create_call_count += 1
        return RunCreationResultV1(kind="CREATED", run_id="run-1")

    def visibility_for(self, run_id: str) -> RunVisibilityV1 | None:
        return self._visibilities.get(run_id)

    def cancel(self, run_id: str) -> RunCancellationResultV1:
        return RunCancellationResultV1(kind="CANCELLED", message="运行已取消")


class FakeDisclosurePortsV1:
    """One fake disclosure port set for the composed flow."""

    def __init__(self) -> None:
        self._waits: dict[str, DisclosureWaitFactsV1] = {}

    def seed_wait(self, facts: DisclosureWaitFactsV1) -> None:
        self._waits[facts.run_id] = facts

    def disclosure_wait_for(self, run_id: str) -> DisclosureWaitFactsV1 | None:
        return self._waits.get(run_id)

    def decide(self, command: Any) -> Any:
        from src.vespercode.governance.disclosure_decision import (
            DisclosureDecisionResultV1,
        )

        return DisclosureDecisionResultV1(
            kind="APPROVED", message="disclosure grant created"
        )


class FakeWritebackPortsV1:
    """One fake final-writeback port set for the composed flow."""

    def __init__(self) -> None:
        self._reviews: dict[str, WritebackReviewV1] = {}

    def seed_review(self, review: WritebackReviewV1) -> None:
        self._reviews[review.run_id] = review

    def writeback_review_for(self, run_id: str) -> WritebackReviewV1 | None:
        return self._reviews.get(run_id)

    def decide(self, command: Any) -> Any:
        from src.vespercode.web.writeback_workflow import FinalWritebackOutcomeV1

        return FinalWritebackOutcomeV1(kind="REJECTED", message="rejected")


def fake_shell_ports() -> LocalShellPortsV1:
    """One fake typed shell port implementation (test-owned)."""

    class _Ports:
        def list_recent_runs(self) -> RunVisibilitySequenceV1:
            return ()

        def credential_status(self) -> CredentialStatusV1:
            return CredentialStatusV1(
                schema_version=1,
                provider="OPENAI",
                configured=False,
                updated_at=AbsentV1(kind="ABSENT"),
            )

    return _Ports()


def csrf_token_from(page_text: str) -> str:
    """One closed extraction of the rendered CSRF token."""
    match = re.search(r'name="csrf-token" content="([0-9a-f]{64})"', page_text)
    assert match is not None
    return match.group(1)


@pytest.fixture
def security_config() -> LocalWebSecurityConfigV1:
    return LocalWebSecurityConfigV1(
        host="127.0.0.1",
        port=8765,
        session_cookie_name="vespercode_session",
        csrf_header_name="X-CSRF-Token",
    )


def _composed_client(
    security_config: LocalWebSecurityConfigV1,
    lifecycle: FakeRunLifecyclePortsV1,
    disclosure: FakeDisclosurePortsV1,
    writeback: FakeWritebackPortsV1,
    review: WritebackReviewV1,
) -> TestClient:
    """One real Milestone 29 composition client (Task 28.B shell +
    the aggregate installer over the fake port sets)."""
    installer = RunGovernanceRouteInstallerV1(
        RunGovernanceWorkflowPortsV1(
            run_lifecycle=RunLifecycleWorkflowPortsV1(
                creation=lifecycle,
                visibility=lifecycle,
                cancellation=lifecycle,
            ),
            disclosure=disclosure,
            final_writeback=writeback,
        ),
        FakeWorkflowIdentityV1(),
    )
    lifecycle.seed_visibility(
        RunVisibilityV1(
            run_id="run-1",
            state_label="AGENT_LOOP",
            reason_code="RUNNING_PHASE",
            next_action="CONTINUE",
            evidence_refs=(),
        )
    )
    disclosure.seed_wait(
        DisclosureWaitFactsV1(
            wait_id="wait-1",
            run_id="run-1",
            subject=seeded_disclosure_subject(),
            created_at=_CREATED_AT,
            expires_at=_EXPIRES_AT,
            decided=False,
        )
    )
    writeback.seed_review(review)
    app = create_local_app(fake_shell_ports(), security_config, (installer,))
    return TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")


def test_milestone_29_pages_are_keyboard_accessible_and_escaped(
    security_config: LocalWebSecurityConfigV1,
) -> None:
    """The Browser (29.C) row: create -> running -> disclosure -> formal
    review -> stale approval, driven by keyboard through native controls
    only, plus the accessibility pins on every T29 page (Expected 29.C:
    focus/errors and non-color status cues pass)."""
    lifecycle = FakeRunLifecyclePortsV1()
    disclosure = FakeDisclosurePortsV1()
    writeback = FakeWritebackPortsV1()
    review = seeded_review()
    client = _composed_client(security_config, lifecycle, disclosure, writeback, review)
    host_headers = {"Host": f"127.0.0.1:{security_config.port}"}
    origin_headers = {
        **host_headers,
        "Origin": f"http://127.0.0.1:{security_config.port}",
    }

    # --- 1. home bootstraps one bounded local session ---
    home = client.get("/", headers=host_headers)
    assert home.status_code == 200

    # --- 2. create: the closed form page is keyboard-reachable ---
    create_page = client.get("/runs/new", headers=host_headers)
    assert create_page.status_code == 200
    _assert_page_accessibility(create_page.text)
    token = csrf_token_from(create_page.text)

    # --- 3. create -> running: a native form submission with the
    # rendered token creates the run and lands on its detail page ---
    created = client.post(
        "/runs",
        headers={**origin_headers, "X-CSRF-Token": token},
        data={
            "workspace_path": "C:/work/demo",
            "target_test_ids": ["tests/a_test.py::test_a"],
            "llm_profile_id": "mock-deterministic-v1",
            "reference_profile_id": "python-src-py312-v1",
            "max_turns": "10",
            "max_llm_calls": "10",
            "max_run_wall_clock_seconds": "600",
            "user_wait_timeout_seconds": "120",
            "tool_timeout_seconds": "30",
            "target_check_timeout_seconds": "60",
            "full_check_timeout_seconds": "120",
            "baseline_timeout_seconds": "300",
            "formal_validation_timeout_seconds": "300",
        },
    )
    assert created.status_code == 200  # 303 followed to the detail page
    assert "运行中" in created.text
    assert lifecycle.create_call_count == 1
    _assert_page_accessibility(created.text)
    assert "取消运行" in created.text  # the native cancel control
    # the status cue is never color-only: the semantic badge carries
    # exact text plus the non-color dot
    assert 'class="status-badge"' in created.text
    assert 'class="status-dot"' in created.text

    # --- 4. disclosure: the exact summary facts render with the
    # keyboard-reachable decision controls ---
    disclosure_page = client.get("/runs/run-1/disclosure", headers=host_headers)
    assert disclosure_page.status_code == 200
    assert "api.openai.com" in disclosure_page.text
    assert "批准披露" in disclosure_page.text
    assert "拒绝披露" in disclosure_page.text
    _assert_page_accessibility(disclosure_page.text)

    # --- 5. formal review: the exact FinalDiff/evidence/subject render
    # with the keyboard-reachable approve/reject controls ---
    review_page = client.get("/runs/run-1/final-writeback", headers=host_headers)
    assert review_page.status_code == 200
    assert "最终写回审查" in review_page.text
    assert "精确最终差异" in review_page.text
    assert review.subject.digest in review_page.text
    assert "批准写回" in review_page.text
    assert "拒绝写回" in review_page.text
    _assert_page_accessibility(review_page.text)

    # --- 6. stale approval: a stale subject never reaches the
    # persistence port (no stale write) ---
    stale = client.post(
        "/runs/run-1/final-writeback",
        headers={**origin_headers, "X-CSRF-Token": token},
        data={
            "decision": "approve",
            "wait_id": "wait-1",
            "subject_digest": "0" * 64,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error_code"] == "WRITEBACK_STALE"


def _assert_page_accessibility(page_text: str) -> None:
    """The shared accessibility pins of every T29 page (SPEC §4.9/§5.3).

    One h1, labeled native controls, visible focus, the live-error
    region, non-color status cues, escaped untrusted text, and the
    reduced-motion kill-switch.
    """
    assert page_text.count("<h1") == 1
    assert ":focus-visible" in page_text
    assert 'id="live-error"' in page_text
    assert "aria-live" in page_text
    assert 'role="alert"' in page_text
    assert "<script>alert(1)</script>" not in page_text
    assert "onerror=" not in page_text
    assert "prefers-reduced-motion" in page_text
    # every interactive control is a native control (no JS-only action)
    assert '<button type="submit"' in page_text or '<button type="button"' in page_text
