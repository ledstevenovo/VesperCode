"""T29.3 legacy step 29.C: final writeback workflow vocabulary and ports.

The module owns the closed final-writeback WebUI contract only: the
``WritebackReviewV1`` review built from the exact current FinalDiff,
verification evidence, workspace/candidate/policy identities, and
approval subject (SPEC §4.6 precondition 4 / §5.3 same-page display),
the escaped review-page rendering, the closed decision form adaptation,
the bound decision command builder, the typed workflow port, and the
``ProductionFinalWritebackWorkflowV1`` sequencing that lets only an exact
``WritebackApprovedV1`` outcome invoke the typed Task 26.E persistence
port (GREEN-2/Boundary).  Approval/persistence predicates, candidate/
diff/evidence construction, workspace/policy fields, and domain state
transitions remain out of scope (GREEN-4).
"""

from __future__ import annotations

from pathlib import Path
from typing import Final, Literal, Protocol

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup
from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr

from src.vespercode.candidate.final_diff import FinalDiffV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.evidence import DigestV1
from src.vespercode.contracts.run import WaitDecisionChoiceV1, WaitDecisionV1
from src.vespercode.governance.writeback_decision import (
    DecideFinalWritebackV1,
    FinalWritebackApprovalV1,
    FinalWritebackDecisionKindV1,
    FinalWritebackDecisionResultV1,
)
from src.vespercode.governance.writeback_subject import FinalWritebackSubjectV1
from src.vespercode.persistence.writeback import PersistenceResultV1
from src.vespercode.web.disclosure_workflow import WorkflowIdentityPortV1

_TEMPLATES_DIRECTORY: Final[str] = str(Path(__file__).resolve().parent / "templates")
"""The packaged template directory (the review page extends base.html)."""


def operation_label(operation: Literal["CREATE", "REPLACE"]) -> str:
    """One distinct user-facing text per closed diff operation (SPEC §4.3)."""
    if operation == "CREATE":
        return "创建"
    return "替换"


class WritebackReviewV1(BaseModel):
    """One exact current final-writeback review (SPEC §4.6 precondition 4).

    The review binds the wait identity, the immutable approval subject
    (which itself binds the candidate/validation/evidence/preimage/
    policy/reference identities), and the exact current ``FinalDiffV1``
    for the same-page display of diff, approval object, verification
    evidence, and workspace preimage state (SPEC §5.3).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: StrictStr
    wait_id: StrictStr
    subject: FinalWritebackSubjectV1
    final_diff: FinalDiffV1
    created_at: CanonicalTimestampV1
    expires_at: CanonicalTimestampV1
    decided: StrictBool


class FinalWritebackDecisionFormV1(BaseModel):
    """One closed final-writeback decision form adaptation (GREEN-2).

    Only the bound decision choice, the wait identity, and the subject
    digest the page rendered are accepted; candidate, diff, evidence,
    workspace, and policy fields are undeclared and reject at the closed
    schema before any domain call (Boundary).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    decision: Literal["approve", "reject"]
    wait_id: StrictStr
    subject_digest: StrictStr


class WritebackApprovedV1(BaseModel):
    """The closed APPROVED outcome carrier of one final writeback.

    Only this variant may reach the typed Task 26.E persistence port: it
    carries the exact consumed approval, the immutable subject, and the
    exact current FinalDiff the composition binds its persistence command
    to (GREEN-2/Boundary).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["APPROVED"]
    run_id: StrictStr
    approval: FinalWritebackApprovalV1
    subject: FinalWritebackSubjectV1
    final_diff: FinalDiffV1


class FinalWritebackOutcomeV1(BaseModel):
    """The closed union of one final-writeback web decision outcome.

    ``approved`` is present exactly on an APPROVED outcome and carries
    the persistence result of the exact approved writeback.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: FinalWritebackDecisionKindV1
    message: StrictStr
    approved: WritebackApprovedV1 | None = None
    persistence: PersistenceResultV1 | None = None


class FinalWritebackDeciderV1(Protocol):
    """The typed decision-service seam (bound to the Task 14.1 service
    at composition time)."""

    def decide(self, command: DecideFinalWritebackV1) -> FinalWritebackDecisionResultV1:
        """Decide the exact bound final-writeback wait atomically."""
        ...


class WritebackReviewProviderV1(Protocol):
    """The typed review-read seam (bound to the run/audit reads at
    composition time; the WebUI never touches the database directly)."""

    def writeback_review_for(self, run_id: str) -> WritebackReviewV1 | None:
        """Return the exact current review of one run, or None."""
        ...


class ApprovedWritebackPersistencePortV1(Protocol):
    """The typed Task 26.E persistence port of the composition.

    Only an exact ``WritebackApprovedV1`` may invoke it; the composition
    binds the approval/subject/diff facts into the Task 26.E persistence
    command (``PersistenceCommandFactoryV1``), never the WebUI.
    """

    def persist_approved(self, approved: WritebackApprovedV1) -> PersistenceResultV1:
        """Persist the exact approved writeback, or close."""
        ...


class ProductionFinalWritebackWorkflowV1:
    """The production final-writeback workflow sequencing (29.C).

    Composes the injected typed ports — the decider (Task 14.1 decision
    service), the review provider (run/audit reads), and the Task 26.E
    persistence port.  Only an exact APPROVED decision result reaches the
    persistence port; every other closed outcome returns with zero
    persistence calls (GREEN-2/Boundary).
    """

    def __init__(
        self,
        *,
        decider: FinalWritebackDeciderV1,
        reviews: WritebackReviewProviderV1,
        persistence: ApprovedWritebackPersistencePortV1,
    ) -> None:
        self._decider = decider
        self._reviews = reviews
        self._persistence = persistence

    def writeback_review_for(self, run_id: str) -> WritebackReviewV1 | None:
        """Forward the exact current review through the provider."""
        return self._reviews.writeback_review_for(run_id)

    def decide(self, command: DecideFinalWritebackV1) -> FinalWritebackOutcomeV1:
        """Decide and, only on an exact APPROVED result, invoke the
        persistence port once with the approved carrier."""
        result = self._decider.decide(command)
        if result.kind != "APPROVED" or result.approval is None:
            return FinalWritebackOutcomeV1(kind=result.kind, message=result.message)
        review = self._reviews.writeback_review_for(command.decision.run_id)
        if review is None:
            return FinalWritebackOutcomeV1(
                kind="NOT_FOUND", message="writeback review is unavailable"
            )
        approved = WritebackApprovedV1(
            kind="APPROVED",
            run_id=command.decision.run_id,
            approval=result.approval,
            subject=command.subject,
            final_diff=review.final_diff,
        )
        persistence = self._persistence.persist_approved(approved)
        return FinalWritebackOutcomeV1(
            kind="APPROVED",
            message=result.message,
            approved=approved,
            persistence=persistence,
        )


class FinalWritebackWorkflowPortV1(Protocol):
    """The typed final-writeback workflow port (injection seam)."""

    def writeback_review_for(self, run_id: str) -> WritebackReviewV1 | None:
        """Return the exact current review of one run, or None."""
        ...

    def decide(self, command: DecideFinalWritebackV1) -> FinalWritebackOutcomeV1:
        """Decide the exact bound wait; only APPROVED invokes persistence."""
        ...


def build_final_writeback_decision_command(
    review: WritebackReviewV1,
    decision: WaitDecisionChoiceV1,
    identity: WorkflowIdentityPortV1,
) -> DecideFinalWritebackV1:
    """One bound decision command from the exact current review facts.

    The subject (with every candidate/diff/evidence/preimage/policy/
    reference identity) comes from the review — the form can never
    supply candidate/diff/evidence/workspace/policy fields — and the
    decision binds wait/run/kind/subject digest plus the harness-
    generated approval/event ids and time (AC-27).
    """
    return DecideFinalWritebackV1(
        decision=WaitDecisionV1(
            wait_id=review.wait_id,
            run_id=review.run_id,
            wait_kind="FINAL_WRITEBACK",
            subject_digest=DigestV1(value=review.subject.digest),
            decision=decision,
            event_id=identity.new_event_id(),
            decided_at=identity.now(),
        ),
        subject=review.subject,
        approval_id=identity.new_approval_id(),
    )


_REVIEW_ENV = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIRECTORY), autoescape=True
)
"""The dedicated review environment: autoescape is always on, so the
review page can never render untrusted paths or evidence text as
executable markup."""

_REVIEW_PAGE_SOURCE = """{% extends "base.html" %}
{% block content %}
<section aria-labelledby="writeback-heading">
  <meta name="csrf-token" content="{{ csrf_token }}">
  <h1 id="writeback-heading">最终写回审查</h1>
  <p class="run-id">运行 {{ review.run_id }}</p>
  <dl class="writeback-review">
    <dt>等待</dt><dd>{{ review.wait_id }}</dd>
    <dt>候选摘要</dt><dd class="digest">{{ review.subject.candidate_digest }}</dd>
    <dt>最终差异摘要</dt><dd class="digest">{{ review.final_diff.digest }}</dd>
    <dt>验证清单摘要</dt><dd class="digest">{{ review.subject.validation_manifest_digest }}</dd>
    <dt>正式验证证据摘要</dt><dd class="digest">{{ review.subject.formal_evidence_digest }}</dd>
    <dt>工作区前映像摘要</dt><dd class="digest">{{ review.subject.workspace_preimage_digest }}</dd>
    <dt>策略摘要</dt><dd class="digest">{{ review.subject.policy_digest }}</dd>
    <dt>参考画像摘要</dt><dd class="digest">{{ review.subject.reference_profile_digest }}</dd>
    <dt>批准主题摘要</dt><dd class="digest">{{ review.subject.digest }}</dd>
    <dt>有效期至</dt><dd>{{ review.expires_at.value }}</dd>
  </dl>
  <h2>精确最终差异</h2>
  <ul class="final-diff">
    {% for entry in review.final_diff.entries %}
    <li>{{ operation_label(entry.operation) }} {{ entry.path.value }}（后映像 {{ entry.postimage_digest }}）</li>
    {% endfor %}
  </ul>
  {% if review.decided %}
  <p role="status">该写回等待已处理，不再接受决定。</p>
  {% else %}
  <form
    method="post"
    action="/runs/{{ review.run_id }}/final-writeback"
    hx-post="/runs/{{ review.run_id }}/final-writeback"
    hx-target="#content"
    hx-select="#content"
    hx-swap="outerHTML"
  >
    <input type="hidden" name="wait_id" value="{{ review.wait_id }}">
    <input type="hidden" name="subject_digest" value="{{ review.subject.digest }}">
    <button type="submit" name="decision" value="approve">批准写回</button>
    <button type="submit" name="decision" value="reject">拒绝写回</button>
  </form>
  {% endif %}
  <p><a href="/runs/{{ review.run_id }}">返回运行详情</a></p>
  <script nonce="{{ csp_nonce }}">
    // The decision form runs through htmx, which attaches the server-
    // rendered CSRF token header before every POST (the Task 28.A
    // boundary accepts only the header form; the HttpOnly session cookie
    // is never readable by script).  The script is authorized only by the
    // per-request CSP nonce — there is no unsafe-inline bypass.  The
    // listener is registered on document.body at page load and the token
    // is session-stable, so it keeps serving the region swaps: a swapped
    // copy of this script carries the swap response's own nonce, which
    // the original document's CSP does not authorize (harmless).
    (function () {
      "use strict";
      var meta = document.querySelector('meta[name="csrf-token"]');
      var token = meta ? meta.getAttribute("content") : "";
      document.body.addEventListener("htmx:configRequest", function (event) {
        event.detail.headers["X-CSRF-Token"] = token;
      });
    })();
  </script>
</section>
{% endblock %}
"""


def render_writeback_review_page(
    review: WritebackReviewV1,
    *,
    csrf_token: str,
    csp_nonce: str,
) -> Markup:
    """One escaped final-writeback review page (autoescape always on).

    The exact FinalDiff entries, every verification/identity digest, and
    the approval subject render escaped with the state-aware approve/
    reject controls and the CSRF token delivery (SPEC §4.6/§4.9/§5.3).
    """
    template = _REVIEW_ENV.from_string(_REVIEW_PAGE_SOURCE)
    return Markup(
        template.render(
            review=review,
            csrf_token=csrf_token,
            csp_nonce=csp_nonce,
            operation_label=operation_label,
        )
    )
