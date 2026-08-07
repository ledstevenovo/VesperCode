"""T29.3 legacy step 29.C: final writeback WebUI and governance composition.

The exact RED pins the smallest stale-subject rejection (a stale
final-writeback form rejects with 409 and never reaches the Task 26.E
persistence port); the matrix pins the Expected (29.C) line — exact
installer order, secure posts, no stale write, escaped evidence,
focus/errors, and non-color status cues pass — plus the production
"only ``WritebackApprovedV1`` invokes the persistence port" sequencing
through the real ``ProductionFinalWritebackWorkflowV1``.  Per the
SPEC_PROCESS section-49 precedent the card's "exact section 5.1 matrix"
reference is non-operative; the Expected (29.C) line is the matrix
authority.

Fixture interpretation (T28.1 M3-precedent class, same as T29.1/T29.2):
the ``local_web_client`` fixture is a test-local composition mirror whose
middleware logic mirrors the Task 28.B shell verbatim with a
deterministic-token session manager, so the card's header-only RED post
passes the exact security order and reaches the closed-form validation.
The ``workflow_ports`` fixture is the real ``ProductionFinalWritebackWorkflowV1``
over fake decider/review sub-ports and a recording persistence spy, so
the route tests exercise the production sequencing itself.  The
substantive production composition is pinned by the real-composition
domain test and the Task 28.2 app-composition tests.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable, Final, cast

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from vespercode.candidate.final_diff import (
    FinalDiffEntryV1,
    FinalDiffPreimageV1,
    FinalDiffV1,
)
from vespercode.canonical.digest import domain_digest
from vespercode.canonical.json_v1 import CanonicalValueV1
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import DigestV1
from vespercode.contracts.optional import AbsentV1
from vespercode.contracts.run import WaitDecisionV1
from vespercode.credentials.port import CredentialStatusV1
from vespercode.governance.disclosure_decision import (
    DisclosureDecisionResultV1,
)
from vespercode.governance.writeback_decision import (
    DecideFinalWritebackV1,
    FinalWritebackApprovalV1,
    FinalWritebackDecisionResultV1,
    FinalWritebackDecisionKindV1,
)
from vespercode.governance.writeback_subject import (
    FinalWritebackBindingV1,
    FinalWritebackSubjectV1,
    build_final_writeback_subject,
)
from vespercode.persistence.writeback import PersistenceResultV1
from vespercode.profiles.reference import (
    ReferenceProfileManifestV1,
    load_reference_profile,
)
from vespercode.audit.projection import RunVisibilityV1
from vespercode.trees.text_classifier import TextMetadataV1
from vespercode.web.app import RunVisibilitySequenceV1, create_local_app
from vespercode.web.disclosure_workflow import DisclosureWaitFactsV1
from vespercode.web.routes_writeback import FinalWritebackRouteInstallerV1
from vespercode.web.run_workflows import (
    RunGovernanceRouteInstallerV1,
    RunGovernanceWorkflowPortsV1,
)
from vespercode.web.run_lifecycle_workflow import (
    CreateRunFormV1,
    RunCancellationResultV1,
    RunCreationResultV1,
    RunLifecycleWorkflowPortsV1,
)
from vespercode.web.security import (
    LocalRequestErrorCodeV1,
    LocalSessionManager,
    LocalWebSecurityConfigV1,
    is_loopback_host,
    local_request_rejection_payload,
    local_request_status,
    local_response_security_headers,
    verify_local_request,
)
from vespercode.web.writeback_workflow import (
    ProductionFinalWritebackWorkflowV1,
    WritebackApprovedV1,
    WritebackReviewV1,
)

_FIXED_TOKEN: Final[str] = "f" * 64
"""One deterministic 256-bit hex session/CSRF token (closed token form)."""

_MIRROR_NONCE: Final[str] = "test-nonce-1234567890"
"""One deterministic closed CSP nonce form for the test-local mirror."""

_TEMPLATES_DIRECTORY: Final[str] = str(
    Path(__file__).resolve().parents[2] / "src/vespercode/web/templates"
)
"""The packaged template directory (mirror app needs the same loader)."""

_REFERENCE_MANIFEST: Final[Path] = (
    Path(__file__).resolve().parents[2] / "reference/manifest/reference-profile-v1.json"
)
"""The frozen packaged reference profile (digest-verified)."""

_CREATED_AT = CanonicalTimestampV1("2026-08-07T09:00:00.000Z")
_EXPIRES_AT = CanonicalTimestampV1("2026-08-07T09:05:00.000Z")
_DECIDED_AT = CanonicalTimestampV1("2026-08-07T09:01:00.000Z")
"""One fixed deterministic instant for the injectable fake clock."""

_TEXT_METADATA = TextMetadataV1(encoding="UTF8", newline="LF", final_newline=True)
_SNAPSHOT_DIGEST = hashlib.sha256(b"sealed-snapshot").hexdigest()
_CANDIDATE_DIGEST = hashlib.sha256(b"candidate-identity").hexdigest()
_VALIDATION_DIGEST = hashlib.sha256(b"validation-manifest").hexdigest()
_FORMAL_EVIDENCE_DIGEST = hashlib.sha256(b"formal-evidence").hexdigest()
_PREIMAGE_DIGEST = hashlib.sha256(b"workspace-preimage").hexdigest()
_RUN_CONFIG_DIGEST = hashlib.sha256(b"run-config").hexdigest()


def manifest() -> ReferenceProfileManifestV1:
    """The frozen packaged reference profile (digest-verified)."""
    loaded = load_reference_profile(_REFERENCE_MANIFEST.read_bytes())
    assert isinstance(loaded, ReferenceProfileManifestV1)
    return loaded


_MANIFEST = manifest()
_EDITABLE_DIGEST = _MANIFEST.editable_path_policy.digest


def _canonical_entry(entry: FinalDiffEntryV1) -> dict[str, CanonicalValueV1]:
    """The §0.1 canonical value shape of one sealed diff row."""
    preimage: CanonicalValueV1
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


def _final_diff(path: str = "src/a.py", raw: bytes = b"x = 1\n") -> FinalDiffV1:
    """One sealed current FinalDiff whose digest binds its exact rows."""
    entry = FinalDiffEntryV1(
        operation="REPLACE",
        path=CanonicalRelativePathV1(path),
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


def writeback_subject(run_id: str = "run-1") -> FinalWritebackSubjectV1:
    """One exact current writeback subject for the declared run."""
    return build_final_writeback_subject(
        FinalWritebackBindingV1(
            run_id=run_id,
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


def writeback_review(run_id: str = "run-1", decided: bool = False) -> WritebackReviewV1:
    """One exact current final-writeback review for the declared run."""
    subject = writeback_subject(run_id)
    return WritebackReviewV1(
        run_id=run_id,
        wait_id="wait-1",
        subject=subject,
        final_diff=_final_diff(),
        created_at=_CREATED_AT,
        expires_at=subject.expires_at,
        decided=decided,
    )


def valid_writeback_decision() -> dict[str, str]:
    """One valid bound final-writeback decision form body."""
    return {
        "decision": "approve",
        "wait_id": "wait-1",
        "subject_digest": writeback_subject().digest,
    }


def approval() -> FinalWritebackApprovalV1:
    """One PENDING final-writeback approval bound to the seeded subject."""
    return FinalWritebackApprovalV1(
        schema_version=1,
        approval_id="approval-1",
        subject_digest=DigestV1(value=writeback_subject().digest),
        run_id="run-1",
        wait_id="wait-1",
        created_at=_DECIDED_AT,
        status="PENDING",
    )


def decided_command() -> DecideFinalWritebackV1:
    """One valid bound final-writeback decision command."""
    subject = writeback_subject()
    return DecideFinalWritebackV1(
        decision=WaitDecisionV1(
            wait_id="wait-1",
            run_id="run-1",
            wait_kind="FINAL_WRITEBACK",
            subject_digest=DigestV1(value=subject.digest),
            decision="APPROVE",
            event_id="event-1",
            decided_at=_DECIDED_AT,
        ),
        subject=subject,
        approval_id="approval-1",
    )


def _fixed_token_generator() -> Callable[[], str]:
    """One deterministic session/CSRF token generator (SPEC §5.4)."""

    def generate() -> str:
        return _FIXED_TOKEN

    return generate


def valid_local_security_headers() -> dict[str, str]:
    """One fully valid loopback request-header set (Host + Origin + CSRF)."""
    return {
        "Host": "127.0.0.1:8765",
        "Origin": "http://127.0.0.1:8765",
        "X-CSRF-Token": _FIXED_TOKEN,
    }


class FakeWorkflowIdentityV1:
    """One deterministic control-plane identity/clock (SPEC §5.4)."""

    def new_grant_id(self) -> str:
        return "grant-1"

    def new_approval_id(self) -> str:
        return "approval-1"

    def new_event_id(self) -> str:
        return "event-1"

    def now(self) -> CanonicalTimestampV1:
        return _DECIDED_AT


class SpyFinalWritebackDeciderV1:
    """One spy decider sub-port of the production workflow."""

    def __init__(self) -> None:
        self.call_count = 0
        self.decide_result = FinalWritebackDecisionResultV1(
            kind="APPROVED",
            message="final-writeback approval created",
            approval=approval(),
        )
        self._commands: list[DecideFinalWritebackV1] = []

    def decide(self, command: DecideFinalWritebackV1) -> FinalWritebackDecisionResultV1:
        self.call_count += 1
        self._commands.append(command)
        return self.decide_result

    @property
    def last_command(self) -> DecideFinalWritebackV1 | None:
        return self._commands[-1] if self._commands else None


class SpyWritebackReviewProviderV1:
    """One spy review-provider sub-port of the production workflow."""

    def __init__(self) -> None:
        self._reviews: dict[str, WritebackReviewV1] = {}

    def seed_review(self, review: WritebackReviewV1) -> None:
        self._reviews[review.run_id] = review

    def writeback_review_for(self, run_id: str) -> WritebackReviewV1 | None:
        return self._reviews.get(run_id)


class SpyPersistencePortV1:
    """One recording Task 26.E persistence-port spy."""

    def __init__(self) -> None:
        self.call_count = 0
        self._approved: list[WritebackApprovedV1] = []

    def persist_approved(self, approved: WritebackApprovedV1) -> PersistenceResultV1:
        self.call_count += 1
        self._approved.append(approved)
        return PersistenceResultV1(
            schema_version=1,
            outcome="SUCCEEDED",
            error_code=None,
            transaction_id="txn-1",
            workspace_write_count=1,
            message="writeback committed",
        )

    @property
    def last_approved(self) -> WritebackApprovedV1 | None:
        return self._approved[-1] if self._approved else None


class SpyRunGovernanceWorkflowPorts:
    """The run-governance workflow-port spy fixture.

    The real ``ProductionFinalWritebackWorkflowV1`` over fake decider and
    review sub-ports and a recording persistence spy, so the route tests
    exercise the production \"only APPROVED invokes persistence\"
    sequencing end to end.
    """

    def __init__(self) -> None:
        self._decider = SpyFinalWritebackDeciderV1()
        self._reviews = SpyWritebackReviewProviderV1()
        self._persistence = SpyPersistencePortV1()
        self._workflow = ProductionFinalWritebackWorkflowV1(
            decider=self._decider,
            reviews=self._reviews,
            persistence=self._persistence,
        )

    def seed_review(self, review: WritebackReviewV1) -> None:
        self._reviews.seed_review(review)

    def set_decide_result(self, result: FinalWritebackDecisionResultV1) -> None:
        self._decider.decide_result = result

    def writeback_review_for(self, run_id: str) -> WritebackReviewV1 | None:
        return self._workflow.writeback_review_for(run_id)

    def decide(self, command: DecideFinalWritebackV1) -> Any:
        return self._workflow.decide(command)

    @property
    def persistence_call_count(self) -> int:
        return self._persistence.call_count

    @property
    def decide_call_count(self) -> int:
        return self._decider.call_count

    @property
    def last_approved(self) -> WritebackApprovedV1 | None:
        return self._persistence.last_approved

    @property
    def last_command(self) -> DecideFinalWritebackV1 | None:
        return self._decider.last_command


def _rejection_response(error_code: LocalRequestErrorCodeV1) -> JSONResponse:
    """One closed rejection response carrying the exact security headers."""
    payload = local_request_rejection_payload(error_code)
    response = JSONResponse(
        status_code=local_request_status(error_code), content=payload
    )
    for name, value in local_response_security_headers().items():
        response.headers[name] = value
    return response


def _build_local_app(
    security_config: LocalWebSecurityConfigV1,
    installer: FinalWritebackRouteInstallerV1,
) -> tuple[FastAPI, LocalSessionManager]:
    """One test-local shell mirroring the Task 28.B composition."""
    manager = LocalSessionManager(
        security_config, token_generator=_fixed_token_generator()
    )
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.local_security_config = security_config
    app.state.local_session_manager = manager
    app.state.local_templates = Jinja2Templates(directory=_TEMPLATES_DIRECTORY)

    @app.middleware("http")
    async def _local_security_middleware(request: Request, call_next: Any) -> Any:
        assert isinstance(
            request, Request
        )  # the runtime contract is a starlette Request
        request.state.csp_nonce = _MIRROR_NONCE
        if not is_loopback_host(request.headers.get("host", "")):
            return _rejection_response("HOST_REJECTED")
        if request.url.path.startswith("/static/"):
            response = await call_next(request)
            _attach_headers(response, None)
            return response
        cookie_value = request.cookies.get(security_config.session_cookie_name)
        if cookie_value is None:
            return _rejection_response("SESSION_MISSING")
        session = manager.get(cookie_value)
        if session is None:
            return _rejection_response("SESSION_INVALID")
        if not manager.is_active(session):
            return _rejection_response("SESSION_EXPIRED")
        authorization = verify_local_request(request, session)
        if not authorization.authorized:
            assert authorization.error_code is not None
            return _rejection_response(authorization.error_code)
        request.state.local_session = session
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        _attach_headers(
            response, _MIRROR_NONCE if "text/html" in content_type else None
        )
        return response

    installer.install(app)
    return app, manager


def _attach_headers(response: Any, csp_nonce: str | None) -> None:
    """Attach the exact CSP and response security headers to one response."""
    for name, value in local_response_security_headers(csp_nonce).items():
        response.headers[name] = value


@pytest.fixture
def workflow_ports() -> SpyRunGovernanceWorkflowPorts:
    return SpyRunGovernanceWorkflowPorts()


@pytest.fixture
def stale_writeback_form() -> dict[str, str]:
    return {
        "decision": "approve",
        "wait_id": "wait-1",
        "subject_digest": "0" * 64,
    }


@pytest.fixture
def security_config() -> LocalWebSecurityConfigV1:
    return LocalWebSecurityConfigV1(
        host="127.0.0.1",
        port=8765,
        session_cookie_name="vespercode_session",
        csrf_header_name="X-CSRF-Token",
    )


@pytest.fixture
def local_web_client(
    security_config: LocalWebSecurityConfigV1,
    workflow_ports: SpyRunGovernanceWorkflowPorts,
) -> TestClient:
    workflow_ports.seed_review(writeback_review())
    installer = FinalWritebackRouteInstallerV1(workflow_ports, FakeWorkflowIdentityV1())
    app, manager = _build_local_app(security_config, installer)
    client = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")
    session = manager.create()
    client.cookies.set(security_config.session_cookie_name, session.session_id)
    return client


def test_stale_writeback_subject_never_calls_persistence(
    local_web_client: TestClient,
    workflow_ports: SpyRunGovernanceWorkflowPorts,
    stale_writeback_form: dict[str, str],
) -> None:
    response = local_web_client.post(
        "/runs/run-1/final-writeback",
        headers=valid_local_security_headers(),
        data=stale_writeback_form,
    )
    assert response.status_code == 409
    assert workflow_ports.persistence_call_count == 0


def test_writeback_web_workflow_matrix(
    local_web_client: TestClient,
    security_config: LocalWebSecurityConfigV1,
    workflow_ports: SpyRunGovernanceWorkflowPorts,
) -> None:
    """The exact final-writeback WebUI matrix (Expected 29.C authority).

    Exact installer order, secure posts, no stale write, escaped
    evidence, focus/errors, and non-color status cues pass; only an exact
    APPROVED outcome reaches the Task 26.E persistence port.
    """
    client = local_web_client
    headers = valid_local_security_headers()
    app = cast(FastAPI, client.app)
    spy = workflow_ports
    review = writeback_review()
    subject = review.subject

    # --- the review page renders the exact FinalDiff/evidence/subject ---
    page = client.get("/runs/run-1/final-writeback", headers=headers)
    assert page.status_code == 200
    text = page.text
    for label in (
        "最终写回审查",
        "候选摘要",
        "最终差异摘要",
        "验证清单摘要",
        "正式验证证据摘要",
        "工作区前映像摘要",
        "策略摘要",
        "参考画像摘要",
        "批准主题摘要",
        "有效期至",
        "精确最终差异",
    ):
        assert label in text
    assert "替换" in text  # the exact REPLACE operation label
    assert "src/a.py" in text  # the exact diff path
    assert review.final_diff.digest in text
    assert subject.candidate_digest in text
    assert subject.validation_manifest_digest in text
    assert subject.formal_evidence_digest in text
    assert subject.workspace_preimage_digest in text
    assert subject.policy_digest in text
    assert subject.reference_profile_digest in text
    assert subject.digest in text
    assert subject.expires_at.value in text
    assert f'value="{review.wait_id}"' in text  # the hidden binding
    assert f'value="{subject.digest}"' in text
    assert "批准写回" in text
    assert "拒绝写回" in text
    # the page never accepts candidate/diff/evidence/workspace/policy fields
    for forbidden in ("workspace_path", "policy_digest", "api_key"):
        assert forbidden not in text
    # the CSRF delivery wiring is present (Task 28.A header form)
    assert 'name="csrf-token"' in text
    assert f'content="{_FIXED_TOKEN}"' in text
    assert 'hx-post="/runs/run-1/final-writeback"' in text
    assert "htmx:configRequest" in text

    # --- a valid approve reaches the decider once and the persistence
    # port exactly once through the production sequencing ---
    approved = client.post(
        "/runs/run-1/final-writeback",
        headers=headers,
        data=valid_writeback_decision(),
        follow_redirects=False,
    )
    assert approved.status_code == 303
    assert approved.headers["location"] == "/runs/run-1"
    assert spy.decide_call_count == 1
    assert spy.persistence_call_count == 1
    command = spy.last_command
    assert command is not None
    assert command.decision.wait_id == "wait-1"
    assert command.decision.run_id == "run-1"
    assert command.decision.wait_kind == "FINAL_WRITEBACK"
    assert command.decision.subject_digest.value == subject.digest
    assert command.decision.decision == "APPROVE"
    assert command.decision.event_id == "event-1"
    assert command.decision.decided_at == _DECIDED_AT
    assert command.subject == subject
    assert command.approval_id == "approval-1"
    carried = spy.last_approved
    assert carried is not None
    assert carried.kind == "APPROVED"
    assert carried.run_id == "run-1"
    assert carried.approval == approval()
    assert carried.subject == subject
    assert carried.final_diff == review.final_diff  # the exact current diff

    # --- a valid reject never reaches the persistence port ---
    spy.set_decide_result(
        FinalWritebackDecisionResultV1(
            kind="REJECTED", message="final-writeback wait rejected"
        )
    )
    rejected = client.post(
        "/runs/run-1/final-writeback",
        headers=headers,
        data={**valid_writeback_decision(), "decision": "reject"},
        follow_redirects=False,
    )
    assert rejected.status_code == 303
    assert spy.decide_call_count == 2
    assert spy.persistence_call_count == 1  # zero additional persistence calls

    # --- override and unknown fields reject before any domain call
    # (Boundary: routes cannot accept candidate/diff/evidence/workspace/
    # policy fields or duplicate approval/persistence predicates) ---
    for override in (
        {"candidate_digest": "0" * 64},
        {"final_diff_digest": "0" * 64},
        {"validation_manifest_digest": "0" * 64},
        {"formal_evidence_digest": "0" * 64},
        {"workspace_preimage_digest": "0" * 64},
        {"policy_digest": "0" * 64},
        {"workspace_path": "C:/other"},
        {"x-extra": "value"},
    ):
        overridden = client.post(
            "/runs/run-1/final-writeback",
            headers=headers,
            data={**valid_writeback_decision(), **override},
        )
        assert overridden.status_code == 422
        assert overridden.json()["error_code"] == "FORM_INVALID"
    assert spy.decide_call_count == 2  # zero additional domain calls
    assert spy.persistence_call_count == 1

    # --- a stale subject rejects 409 before any domain call ---
    stale = client.post(
        "/runs/run-1/final-writeback",
        headers=headers,
        data={
            "decision": "approve",
            "wait_id": "wait-1",
            "subject_digest": "0" * 64,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error_code"] == "WRITEBACK_STALE"
    wrong_wait = client.post(
        "/runs/run-1/final-writeback",
        headers=headers,
        data={**valid_writeback_decision(), "wait_id": "wait-other"},
    )
    assert wrong_wait.status_code == 409
    assert wrong_wait.json()["error_code"] == "WRITEBACK_STALE"
    assert spy.decide_call_count == 2  # zero domain calls after staleness
    assert spy.persistence_call_count == 1

    # --- invalid decision values reject at the closed schema ---
    invalid_decision = client.post(
        "/runs/run-1/final-writeback",
        headers=headers,
        data={**valid_writeback_decision(), "decision": "maybe"},
    )
    assert invalid_decision.status_code == 422
    assert invalid_decision.json()["error_code"] == "FORM_INVALID"
    assert spy.decide_call_count == 2

    # --- the closed port-outcome mappings are pinned ---
    spy.set_decide_result(
        FinalWritebackDecisionResultV1(
            kind="REPLAY", message="wait decision already recorded identically"
        )
    )
    replayed = client.post(
        "/runs/run-1/final-writeback",
        headers=headers,
        data=valid_writeback_decision(),
        follow_redirects=False,
    )
    assert replayed.status_code == 303
    spy.set_decide_result(
        FinalWritebackDecisionResultV1(
            kind="CONFLICT", message="wait decision already recorded differently"
        )
    )
    conflicted = client.post(
        "/runs/run-1/final-writeback",
        headers=headers,
        data=valid_writeback_decision(),
    )
    assert conflicted.status_code == 409
    assert conflicted.json()["error_code"] == "WRITEBACK_CONFLICT"
    spy.set_decide_result(
        FinalWritebackDecisionResultV1(
            kind="EXPIRED", message="final-writeback wait already expired"
        )
    )
    expired = client.post(
        "/runs/run-1/final-writeback",
        headers=headers,
        data=valid_writeback_decision(),
    )
    assert expired.status_code == 409
    assert expired.json()["error_code"] == "WRITEBACK_DECISION_REJECTED"
    assert expired.json()["message"] == "final-writeback wait already expired"
    assert spy.persistence_call_count == 1  # never more than the one approve

    # --- unknown run is a closed 404 ---
    unknown = client.get("/runs/run-missing/final-writeback", headers=headers)
    assert unknown.status_code == 404
    assert unknown.json()["error_code"] == "WRITEBACK_REVIEW_NOT_FOUND"

    # --- a decided review renders no decision controls (state-aware) ---
    spy.seed_review(writeback_review(decided=True))
    decided_page = client.get("/runs/run-1/final-writeback", headers=headers)
    assert decided_page.status_code == 200
    assert "该写回等待已处理" in decided_page.text
    assert "批准写回" not in decided_page.text
    assert "拒绝写回" not in decided_page.text

    # --- untrusted run text is escaped everywhere (SPEC §4.9) ---
    untrusted_review = writeback_review(run_id="<img src=x onerror=alert(1)>")
    spy.seed_review(untrusted_review)
    escaped = client.get(
        "/runs/%3Cimg%20src=x%20onerror=alert(1)%3E/final-writeback",
        headers=headers,
    )
    assert escaped.status_code == 200
    assert "<img src=x onerror=alert(1)>" not in escaped.text
    assert "&lt;img src=x onerror=alert(1)&gt;" in escaped.text

    # --- the Task 28.A boundary rejects before every port call, and the
    # exact security headers ride on every T29 response ---
    spy.seed_review(writeback_review())
    fresh = TestClient(app, base_url=f"http://127.0.0.1:{security_config.port}")
    no_session = fresh.post(
        "/runs/run-1/final-writeback",
        headers={"Host": f"127.0.0.1:{security_config.port}"},
        data=valid_writeback_decision(),
    )
    assert no_session.status_code == 401
    assert no_session.json()["error_code"] == "SESSION_MISSING"
    bad_origin = client.post(
        "/runs/run-1/final-writeback",
        headers={
            "Host": "127.0.0.1:8765",
            "Origin": "https://attacker.example",
            "X-CSRF-Token": _FIXED_TOKEN,
        },
        data=valid_writeback_decision(),
    )
    assert bad_origin.status_code == 403
    assert bad_origin.json()["error_code"] == "ORIGIN_REJECTED"
    assert spy.decide_call_count == 5  # zero domain calls after rejections
    assert spy.persistence_call_count == 1
    page_headers = page.headers
    assert page_headers["x-content-type-options"] == "nosniff"
    assert page_headers["x-frame-options"] == "DENY"
    assert page_headers["referrer-policy"] == "no-referrer"
    assert page_headers["content-security-policy"].startswith("default-src 'self'")
    assert f"'nonce-{_MIRROR_NONCE}'" in page_headers["content-security-policy"]


def test_only_approved_outcome_invokes_the_persistence_port(
    workflow_ports: SpyRunGovernanceWorkflowPorts,
) -> None:
    """The production sequencing invariant: every closed decision kind
    except APPROVED returns with zero persistence calls (GREEN-2/Boundary:
    only ``WritebackApprovedV1`` may create a Task 26.E persistence
    command)."""
    workflow_ports.seed_review(writeback_review())
    command = decided_command()
    kinds: tuple[FinalWritebackDecisionKindV1, ...] = (
        "REJECTED",
        "STALE",
        "EXPIRED",
        "BINDING_MISMATCH",
        "CANCELLED",
        "NOT_FOUND",
        "REPLAY",
        "CONFLICT",
    )
    for kind in kinds:
        workflow_ports.set_decide_result(
            FinalWritebackDecisionResultV1(kind=kind, message=f"{kind} outcome")
        )
        outcome = workflow_ports.decide(command)
        assert outcome.kind == kind
        assert outcome.approved is None
        assert workflow_ports.persistence_call_count == 0
    # the exact APPROVED outcome invokes the persistence port once with
    # the approved carrier bound to the exact approval/subject/diff
    workflow_ports.set_decide_result(
        FinalWritebackDecisionResultV1(
            kind="APPROVED",
            message="final-writeback approval created",
            approval=approval(),
        )
    )
    outcome = workflow_ports.decide(command)
    assert outcome.kind == "APPROVED"
    assert outcome.approved is not None
    assert outcome.approved.approval == approval()
    assert outcome.approved.subject == command.subject
    assert outcome.approved.final_diff == writeback_review().final_diff
    assert workflow_ports.persistence_call_count == 1


def test_governance_installer_installs_all_milestone_29_routes_in_order(
    security_config: LocalWebSecurityConfigV1,
    workflow_ports: SpyRunGovernanceWorkflowPorts,
) -> None:
    """The deterministic Milestone 29 installer composition: the run
    lifecycle routes, then the disclosure routes, then the final-writeback
    routes, in the exact order (Expected 29.C: exact installer order)."""
    workflow_ports.seed_review(writeback_review())
    lifecycle = _MinimalRunLifecyclePorts()
    disclosure = _MinimalDisclosurePorts()

    class _ShellPorts:
        def list_recent_runs(self) -> RunVisibilitySequenceV1:
            return ()

        def credential_status(self) -> CredentialStatusV1:
            return CredentialStatusV1(
                schema_version=1,
                provider="OPENAI",
                configured=False,
                updated_at=AbsentV1(kind="ABSENT"),
            )

    installer = RunGovernanceRouteInstallerV1(
        RunGovernanceWorkflowPortsV1(
            run_lifecycle=RunLifecycleWorkflowPortsV1(
                creation=lifecycle,
                visibility=lifecycle,
                cancellation=lifecycle,
            ),
            disclosure=disclosure,
            final_writeback=workflow_ports,
        ),
        FakeWorkflowIdentityV1(),
    )
    app = create_local_app(_ShellPorts(), security_config, (installer,))
    paths_and_methods = [
        (getattr(route, "methods", None), getattr(route, "path", None))
        for route in app.routes
        if getattr(route, "path", None) is not None
    ]
    assert paths_and_methods == [
        ({"GET"}, "/"),
        ({"GET"}, "/runs/new"),
        ({"POST"}, "/runs"),
        ({"GET"}, "/runs/{run_id}"),
        ({"POST"}, "/runs/{run_id}/cancel"),
        ({"GET"}, "/runs/{run_id}/disclosure"),
        ({"POST"}, "/runs/{run_id}/disclosure"),
        ({"GET"}, "/runs/{run_id}/final-writeback"),
        ({"POST"}, "/runs/{run_id}/final-writeback"),
    ]


class _MinimalRunLifecyclePorts:
    """One minimal run-lifecycle spy for the aggregate composition test."""

    def __init__(self) -> None:
        self.create_call_count = 0

    def create(self, form: CreateRunFormV1) -> RunCreationResultV1:
        self.create_call_count += 1
        return RunCreationResultV1(kind="CREATED", run_id="run-1")

    def visibility_for(self, run_id: str) -> RunVisibilityV1:
        return RunVisibilityV1(
            run_id=run_id,
            state_label="AGENT_LOOP",
            reason_code="RUNNING_PHASE",
            next_action="CONTINUE",
            evidence_refs=(),
        )

    def cancel(self, run_id: str) -> RunCancellationResultV1:
        return RunCancellationResultV1(kind="CANCELLED", message="运行已取消")


class _MinimalDisclosurePorts:
    """One minimal disclosure spy for the aggregate composition test."""

    def __init__(self) -> None:
        self.decide_call_count = 0

    def disclosure_wait_for(self, run_id: str) -> DisclosureWaitFactsV1 | None:
        return None

    def decide(self, command: Any) -> DisclosureDecisionResultV1:
        self.decide_call_count += 1
        return DisclosureDecisionResultV1(
            kind="APPROVED", message="disclosure grant created"
        )
