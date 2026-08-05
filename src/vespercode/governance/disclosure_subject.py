"""T15.1 legacy step 15.C: the immutable disclosure Grant subject builder.

``build_disclosure_subject`` binds every immutable authorization fact —
the validated source projection, the canonical scopes and the projection's
canonical categories, the frozen OpenAI profile, the trusted endpoint,
the serializer identity, the harness-computed budget, and the expiry —
into one pure ``DisclosureGrantSubjectV1`` whose §0.1 digest covers every
field except itself.  Request-supplied endpoint/model/source/scope/expiry
overrides reject before any subject exists (the declared request URL is
rejected explicitly; any other override field is undeclared and rejects at
the closed request schema).  Wait/Grant creation, revocation, budget
charging, authorization records, and adapter calls remain out of scope
(GREEN-4).
"""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    StrictStr,
    field_validator,
    model_validator,
)

from src.vespercode.canonical.digest import domain_digest
from src.vespercode.canonical.json_v1 import CanonicalValueV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.evidence import _DIGEST_RE
from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.governance.disclosure_scope import (
    DisclosurePathScopeV1,
    DisclosureScopeSequenceV1,
    canonicalize_disclosure_scopes,
    scope_matches,
)
from src.vespercode.governance.request_sources import (
    RequestSourceCategoryV1,
    SourceProjectionV1,
)
from src.vespercode.profiles.endpoints import OpenAIEndpointV1
from src.vespercode.profiles.llm import OpenAILLMProfileV1

# SPEC §4.4.3: the declared enum order of the six source categories.
_CATEGORY_RANK: dict[RequestSourceCategoryV1, int] = {
    "HARNESS_PROTOCOL": 0,
    "TASK": 1,
    "FILE_CONTENT": 2,
    "TOOL_RESULT": 3,
    "MEMORY": 4,
    "FEEDBACK": 5,
}

OptionalUrlOverrideV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[str], Field(discriminator="kind")
]
"""The declared request URL-override slot: ABSENT or PRESENT(url)."""


class DisclosureSubjectRequestV1(BaseModel):
    """One closed subject-construction request (harness-computed facts only).

    The request may carry only the run identity, the harness-computed
    expiry and cumulative budget, and the declared URL-override slot.  The
    endpoint, model, source paths, scopes, and expiry are frozen inputs of
    ``build_disclosure_subject``: a request-supplied URL rejects explicitly
    (``ENDPOINT_OVERRIDE``) and any other override attempt is an undeclared
    field that the closed schema rejects before a subject exists.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: StrictStr
    expires_at: CanonicalTimestampV1
    cumulative_byte_budget: Annotated[int, Strict(), Field(ge=1, le=1310720)]
    url: OptionalUrlOverrideV1


class DisclosureGrantSubjectV1(BaseModel):
    """SPEC §4.4.3: the immutable run-level disclosure authorization subject.

    The §0.1 ``digest`` binds every other exact field (canonical scope
    order, canonical category order, frozen profile facts, budget, and
    expiry); the mutable Grant state (``consumed_bytes``/``status``) never
    enters the subject, and the model rejects any digest that does not
    equal the identity of its own fields.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    run_id: StrictStr
    llm_profile_digest: StrictStr
    provider: StrictStr
    endpoint_id: Literal["OPENAI_PUBLIC_API_V1"]
    model: StrictStr
    request_serializer_version: StrictStr
    allowed_source_paths: tuple[DisclosurePathScopeV1, ...]
    allowed_source_categories: tuple[RequestSourceCategoryV1, ...]
    redaction_profile_id: Literal["NO_CONTENT_REDACTION_V1"]
    cumulative_byte_budget: Annotated[int, Strict(), Field(ge=1, le=1310720)]
    expires_at: CanonicalTimestampV1
    digest: StrictStr

    @field_validator("digest")
    @classmethod
    def _digest_has_exact_form(cls, value: str) -> str:
        if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
            raise ValueError("must be exactly 64 lowercase hexadecimal characters")
        return value

    @model_validator(mode="after")
    def _digest_binds_every_field(self) -> DisclosureGrantSubjectV1:
        if self.digest != _subject_digest(
            run_id=self.run_id,
            llm_profile_digest=self.llm_profile_digest,
            provider=self.provider,
            endpoint_id=self.endpoint_id,
            model=self.model,
            request_serializer_version=self.request_serializer_version,
            allowed_source_paths=self.allowed_source_paths,
            allowed_source_categories=self.allowed_source_categories,
            redaction_profile_id=self.redaction_profile_id,
            cumulative_byte_budget=self.cumulative_byte_budget,
            expires_at=self.expires_at,
        ):
            raise ValueError(
                "digest must equal the §0.1 identity of every other exact field"
            )
        return self


DisclosureSubjectCodeV1: TypeAlias = Literal[
    "ENDPOINT_OVERRIDE",
    "ENDPOINT_MISMATCH",
    "SOURCE_PROJECTION_EMPTY",
    "SOURCE_SCOPE_MISMATCH",
]
"""The closed rejection codes of the subject construction contract."""


class DisclosureSubjectError(ValueError):
    """Closed rejection of an override or uncovered subject construction."""

    def __init__(self, error_code: DisclosureSubjectCodeV1, message: str) -> None:
        super().__init__(f"{error_code}: {message}")
        self.error_code = error_code


def _scope_to_canonical(scope: DisclosurePathScopeV1) -> dict[str, CanonicalValueV1]:
    """One scope's canonical value shape (SPEC §4.4.3)."""
    if scope.kind == "ROOT":
        return {"kind": "ROOT"}
    return {"kind": scope.kind, "path": scope.path.value}


def _subject_digest(
    *,
    run_id: str,
    llm_profile_digest: str,
    provider: str,
    endpoint_id: str,
    model: str,
    request_serializer_version: str,
    allowed_source_paths: tuple[DisclosurePathScopeV1, ...],
    allowed_source_categories: tuple[RequestSourceCategoryV1, ...],
    redaction_profile_id: str,
    cumulative_byte_budget: int,
    expires_at: CanonicalTimestampV1,
) -> str:
    """The §0.1 identity of every exact subject field except the digest."""
    return domain_digest(
        "DisclosureGrantSubjectV1",
        1,
        {
            "schema_version": 1,
            "run_id": run_id,
            "llm_profile_digest": llm_profile_digest,
            "provider": provider,
            "endpoint_id": endpoint_id,
            "model": model,
            "request_serializer_version": request_serializer_version,
            "allowed_source_paths": tuple(
                _scope_to_canonical(scope) for scope in allowed_source_paths
            ),
            "allowed_source_categories": tuple(allowed_source_categories),
            "redaction_profile_id": redaction_profile_id,
            "cumulative_byte_budget": cumulative_byte_budget,
            "expires_at": expires_at.value,
        },
    )


def _canonical_categories(
    sources: SourceProjectionV1,
) -> tuple[RequestSourceCategoryV1, ...]:
    """The projection's unique categories in the SPEC §4.4.3 enum order."""
    return tuple(
        sorted(
            {source.source_category for source in sources},
            key=lambda category: _CATEGORY_RANK[category],
        )
    )


def build_disclosure_subject(
    request: DisclosureSubjectRequestV1,
    sources: SourceProjectionV1,
    scopes: DisclosureScopeSequenceV1,
    profile: OpenAILLMProfileV1,
    endpoint: OpenAIEndpointV1,
) -> DisclosureGrantSubjectV1:
    """Build one pure immutable disclosure Grant subject (SPEC §4.4.3).

    The subject binds the frozen profile facts, the trusted endpoint
    identity, the canonical scopes and the projection's canonical
    categories, and the harness-computed budget/expiry.  A request-supplied
    URL, a profile/endpoint identity mismatch, an empty source projection,
    or any path-bearing source outside the canonical scopes rejects before
    a subject exists.
    """
    if request.url.kind == "PRESENT":
        raise DisclosureSubjectError(
            "ENDPOINT_OVERRIDE",
            "request URL cannot override the trusted endpoint",
        )
    if profile.endpoint_id != endpoint.endpoint_id:
        raise DisclosureSubjectError(
            "ENDPOINT_MISMATCH",
            "frozen profile endpoint must equal the trusted endpoint identity",
        )
    if len(sources) == 0:
        raise DisclosureSubjectError(
            "SOURCE_PROJECTION_EMPTY",
            "at least one validated source is required to build a subject",
        )
    canonical_scopes = canonicalize_disclosure_scopes(scopes)
    categories = _canonical_categories(sources)
    for source in sources:
        if source.source_path.kind == "PRESENT" and not any(
            scope_matches(scope, source.source_path.value) for scope in canonical_scopes
        ):
            raise DisclosureSubjectError(
                "SOURCE_SCOPE_MISMATCH",
                f"source path {source.source_path.value.value!r} lies outside "
                "the canonical disclosure scopes",
            )
    digest = _subject_digest(
        run_id=request.run_id,
        llm_profile_digest=profile.digest,
        provider=profile.provider,
        endpoint_id=profile.endpoint_id,
        model=profile.model,
        request_serializer_version=profile.request_serializer_version,
        allowed_source_paths=canonical_scopes,
        allowed_source_categories=categories,
        redaction_profile_id=profile.redaction_profile_id,
        cumulative_byte_budget=request.cumulative_byte_budget,
        expires_at=request.expires_at,
    )
    return DisclosureGrantSubjectV1(
        schema_version=1,
        run_id=request.run_id,
        llm_profile_digest=profile.digest,
        provider=profile.provider,
        endpoint_id=profile.endpoint_id,
        model=profile.model,
        request_serializer_version=profile.request_serializer_version,
        allowed_source_paths=canonical_scopes,
        allowed_source_categories=categories,
        redaction_profile_id=profile.redaction_profile_id,
        cumulative_byte_budget=request.cumulative_byte_budget,
        expires_at=request.expires_at,
        digest=digest,
    )
