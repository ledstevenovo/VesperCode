"""T29.2 legacy step 29.B: disclosure decision workflow vocabulary and ports.

The module owns the closed disclosure WebUI contract only: the immutable
``AuthorizationSummaryV1`` built exclusively from the exact bound
disclosure subject and the trusted endpoint record (SPEC §4.4.3 — the
displayed provider/endpoint/host/model/categories/paths/budget/expiry
never come from the environment, the request, ordinary config, or DNS
text), the escaped summary rendering with exact human labels and the
``NO_CONTENT_REDACTION_V1`` warning, the closed decision form adaptation,
the bound decision command builder (the route can never construct,
widen, or mutate a Grant), and the typed workflow port over which the
routes submit exactly one approve/reject decision after the Task 28
request security.  Grant construction, authorization policy, source
scope, endpoint selection, credential handling, clocks, and domain state
remain out of scope (GREEN-4).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Final, Literal, Protocol

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup
from pydantic import BaseModel, ConfigDict, Field, Strict, StrictBool, StrictStr

from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.evidence import DigestV1
from src.vespercode.contracts.run import WaitDecisionChoiceV1, WaitDecisionV1
from src.vespercode.governance.disclosure_decision import (
    DecideDisclosureGrantV1,
    DisclosureDecisionResultV1,
)
from src.vespercode.governance.disclosure_scope import DisclosurePathScopeV1
from src.vespercode.governance.disclosure_subject import DisclosureGrantSubjectV1
from src.vespercode.governance.request_sources import RequestSourceCategoryV1
from src.vespercode.profiles.endpoints import OpenAIEndpointV1

_TEMPLATES_DIRECTORY: Final[str] = str(Path(__file__).resolve().parent / "templates")
"""The packaged template directory (the summary fragment shares it)."""

CATEGORY_LABELS_V1: Final[dict[RequestSourceCategoryV1, str]] = {
    "HARNESS_PROTOCOL": "协议来源",
    "TASK": "任务",
    "FILE_CONTENT": "文件内容",
    "TOOL_RESULT": "工具结果",
    "MEMORY": "记忆",
    "FEEDBACK": "反馈",
}
"""One distinct user-facing text per closed source category (SPEC §4.4.3)."""


def scope_label(scope: DisclosurePathScopeV1) -> str:
    """The exact user-facing disclosure scope label (SPEC §4.4.3).

    ROOT renders as \"整个仓库\", FILE as \"单个文件：<path>\", and
    DIRECTORY as \"目录及其后代：<path>\" — never a trailing-\"/\" string
    sentinel.
    """
    if scope.kind == "ROOT":
        return "整个仓库"
    if scope.kind == "FILE":
        return f"单个文件：{scope.path.value}"
    return f"目录及其后代：{scope.path.value}"


class AuthorizationSummaryV1(BaseModel):
    """One immutable authorization summary of the exact bound subject.

    Every displayed fact comes from the disclosure subject and the
    trusted built-in endpoint record; the host is resolved from the
    endpoint map, never from the environment, the request, ordinary
    config, or DNS text (SPEC §4.4.3).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: StrictStr
    endpoint_id: StrictStr
    endpoint_host: StrictStr
    model: StrictStr
    categories: tuple[RequestSourceCategoryV1, ...]
    source_scopes: tuple[DisclosurePathScopeV1, ...]
    cumulative_byte_budget: Annotated[int, Strict(), Field(ge=1, le=1310720)]
    expires_at: CanonicalTimestampV1
    redaction_profile_id: Literal["NO_CONTENT_REDACTION_V1"]


def build_authorization_summary(
    subject: DisclosureGrantSubjectV1,
    endpoint: OpenAIEndpointV1,
) -> AuthorizationSummaryV1:
    """Build the summary only from the exact bound subject and endpoint.

    The endpoint host is the trusted built-in record's literal; a raw
    URL, ``base_url``, or alternate record can never enter the summary
    (SPEC §4.4.3 display contract).
    """
    return AuthorizationSummaryV1(
        provider=subject.provider,
        endpoint_id=subject.endpoint_id,
        endpoint_host=endpoint.host,
        model=subject.model,
        categories=subject.allowed_source_categories,
        source_scopes=subject.allowed_source_paths,
        cumulative_byte_budget=subject.cumulative_byte_budget,
        expires_at=subject.expires_at,
        redaction_profile_id=subject.redaction_profile_id,
    )


_SUMMARY_ENV = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIRECTORY), autoescape=True
)
"""The dedicated summary environment: autoescape is always on, so the
summary can never render untrusted text as executable markup."""

_SUMMARY_TEMPLATE_SOURCE = """<dl class="authorization-summary">
  <dt>供应商</dt><dd>{{ summary.provider }}</dd>
  <dt>端点标识</dt><dd>{{ summary.endpoint_id }}</dd>
  <dt>目的主机</dt><dd>{{ summary.endpoint_host }}</dd>
  <dt>模型</dt><dd>{{ summary.model }}</dd>
  <dt>来源类别</dt><dd>{{ categories_text }}</dd>
  <dt>来源路径</dt><dd>{{ scopes_text }}</dd>
  <dt>累计字节预算</dt><dd>{{ summary.cumulative_byte_budget }} 字节</dd>
  <dt>有效期至</dt><dd>{{ summary.expires_at.value }}</dd>
  <dt>脱敏配置</dt><dd>{{ summary.redaction_profile_id }}</dd>
</dl>
<p class="redaction-warning">警告：被选择的项目正文将在规范裁剪后原样发送；敏感路径拒绝不等于通用秘密扫描（NO_CONTENT_REDACTION_V1 不扫描正文）。</p>
"""


def render_authorization_summary(summary: AuthorizationSummaryV1) -> Markup:
    """One escaped authorization-summary fragment (autoescape always on).

    The exact human labels, the byte budget, the expiry, and the
    no-content-redaction warning render as escaped markup; untrusted
    path text can never execute as repository HTML (SPEC §4.4.3/§4.9).
    """
    categories_text = "、".join(CATEGORY_LABELS_V1[c] for c in summary.categories)
    scopes_text = "、".join(scope_label(scope) for scope in summary.source_scopes)
    template = _SUMMARY_ENV.from_string(_SUMMARY_TEMPLATE_SOURCE)
    return Markup(
        template.render(
            summary=summary,
            categories_text=categories_text,
            scopes_text=scopes_text,
        )
    )


class DisclosureWaitFactsV1(BaseModel):
    """One exact current disclosure wait of one run (read-only).

    The subject is the immutable authorization subject the wait binds
    (SPEC §4.2.7/AC-27); ``decided`` is the state-aware flag the page
    uses to stop rendering decision controls.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    wait_id: StrictStr
    run_id: StrictStr
    subject: DisclosureGrantSubjectV1
    created_at: CanonicalTimestampV1
    expires_at: CanonicalTimestampV1
    decided: StrictBool


class DisclosureDecisionFormV1(BaseModel):
    """One closed disclosure decision form adaptation (GREEN-2).

    Only the bound decision choice, the wait identity, and the subject
    digest the page rendered are accepted; scope, endpoint, budget,
    credential, and clock overrides are undeclared fields and reject at
    the closed schema before the workflow port is called.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    decision: Literal["approve", "reject"]
    wait_id: StrictStr
    subject_digest: StrictStr


class WorkflowIdentityPortV1(Protocol):
    """One injected control-plane identity/clock seam (SPEC §5.4).

    Tests inject deterministic id generators and clocks; the values are
    never form-derived, so the WebUI cannot construct, widen, or mutate
    a Grant, scope, budget, endpoint, credential, or clock value.
    """

    def new_grant_id(self) -> str:
        """One harness-generated Grant identity."""
        ...

    def new_approval_id(self) -> str:
        """One harness-generated final-approval identity."""
        ...

    def new_event_id(self) -> str:
        """One harness-generated decision event identity."""
        ...

    def now(self) -> CanonicalTimestampV1:
        """The sole current-time source of one decision."""
        ...


def build_disclosure_decision_command(
    wait: DisclosureWaitFactsV1,
    decision: WaitDecisionChoiceV1,
    identity: WorkflowIdentityPortV1,
) -> DecideDisclosureGrantV1:
    """One bound decision command from the exact current wait facts.

    The provider, endpoint, model, source paths, categories, budget, and
    expiry all come from the wait's immutable subject — the form can
    never widen or mutate them — and the decision binds wait/run/kind/
    subject digest plus the harness-generated event and time (AC-27).
    """
    return DecideDisclosureGrantV1(
        decision=WaitDecisionV1(
            wait_id=wait.wait_id,
            run_id=wait.run_id,
            wait_kind="DISCLOSURE_GRANT",
            subject_digest=DigestV1(value=wait.subject.digest),
            decision=decision,
            event_id=identity.new_event_id(),
            decided_at=identity.now(),
        ),
        subject=wait.subject,
        grant_id=identity.new_grant_id(),
    )


class DisclosureDecisionWorkflowPortV1(Protocol):
    """The typed disclosure-decision workflow port (injection seam).

    The port owns Grant construction, authorization policy, source
    scope, endpoint selection, credential handling, clocks, and domain
    state (Task 15); the routes only adapt the closed form and forward
    the outcome (GREEN-4).
    """

    def disclosure_wait_for(self, run_id: str) -> DisclosureWaitFactsV1 | None:
        """Return the exact current disclosure wait of one run, or None."""
        ...

    def decide(self, command: DecideDisclosureGrantV1) -> DisclosureDecisionResultV1:
        """Decide the exact bound disclosure wait atomically."""
        ...
