"""T15.1 legacy step 15.C: immutable disclosure Grant subject builder tests.

Pins the closed subject schema (every field except the self-digest is
bound by the §0.1 identity), the frozen-profile/trusted-endpoint binding
(the request URL can never override the endpoint), the canonical
scope/category ordering, the source-coverage gate, and the digest drift of
every bound fact.  Wait/Grant creation, revocation, budget charging,
authorization records, and adapter calls remain out of scope (GREEN-4).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

# The builder consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips cleanly
# there (formal env runs it fully).
pytest.importorskip("pydantic")

from src.vespercode.canonical.digest import domain_digest
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.governance.disclosure_scope import (
    DirectoryDisclosureScopeV1,
    DisclosureScopeSequenceV1,
    FileDisclosureScopeV1,
)
from src.vespercode.governance.disclosure_subject import (
    DisclosureGrantSubjectV1,
    DisclosureSubjectError,
    DisclosureSubjectRequestV1,
    build_disclosure_subject,
)
from src.vespercode.governance.request_sources import (
    RequestSourceCategoryV1,
    RequestSourceV1,
    SourceProjectionV1,
)
from src.vespercode.profiles.endpoints import OpenAIEndpointV1
from src.vespercode.profiles.llm import OpenAILLMProfileV1, load_llm_profile

_CREATED_AT = CanonicalTimestampV1("2026-08-05T09:00:00.000Z")
_EXPIRES_AT = CanonicalTimestampV1("2026-08-05T09:05:00.000Z")
_OPENAI_BUILTIN = (
    Path(__file__).resolve().parents[3]
    / "src/vespercode/profiles/builtin/openai-single-turn-v1.json"
)


def profile() -> OpenAILLMProfileV1:
    """The frozen packaged built-in OpenAI profile (digest-verified)."""
    loaded = load_llm_profile(_OPENAI_BUILTIN.read_bytes())
    assert isinstance(loaded, OpenAILLMProfileV1)
    return loaded


def profile_with_model(model: str) -> OpenAILLMProfileV1:
    """A second frozen OpenAI profile: same facts except *model*."""
    base = profile()
    fixed = base.fixed_parameters
    digest = domain_digest(
        "OpenAILLMProfileV1",
        1,
        {
            "schema_version": base.schema_version,
            "profile_id": base.profile_id,
            "mode": base.mode,
            "provider": base.provider,
            "endpoint_id": base.endpoint_id,
            "model": model,
            "adapter_version": base.adapter_version,
            "request_serializer_version": base.request_serializer_version,
            "fixed_parameters": {
                "schema_version": fixed.schema_version,
                "max_output_tokens": fixed.max_output_tokens,
                "temperature": fixed.temperature.model_dump(),
                "top_p": fixed.top_p.model_dump(),
                "seed": fixed.seed.model_dump(),
                "response_format": fixed.response_format,
            },
            "redaction_profile_id": base.redaction_profile_id,
        },
    )
    return OpenAILLMProfileV1(
        schema_version=base.schema_version,
        profile_id=base.profile_id,
        mode=base.mode,
        provider=base.provider,
        endpoint_id=base.endpoint_id,
        model=model,
        adapter_version=base.adapter_version,
        request_serializer_version=base.request_serializer_version,
        fixed_parameters=fixed,
        redaction_profile_id=base.redaction_profile_id,
        digest=digest,
    )


def endpoint() -> OpenAIEndpointV1:
    return OpenAIEndpointV1(
        endpoint_id="OPENAI_PUBLIC_API_V1",
        scheme="https",
        host="api.openai.com",
        effective_port=443,
        base_path="/v1",
    )


def request(
    run_id: str = "run-15c",
    budget: int = 100_000,
    expires_at: CanonicalTimestampV1 = _EXPIRES_AT,
    url: AbsentV1 | PresentV1[str] = AbsentV1(kind="ABSENT"),
) -> DisclosureSubjectRequestV1:
    return DisclosureSubjectRequestV1(
        run_id=run_id,
        expires_at=expires_at,
        cumulative_byte_budget=budget,
        url=url,
    )


def request_with_url_override() -> DisclosureSubjectRequestV1:
    return request(url=PresentV1(kind="PRESENT", value="https://evil.example.com/v1"))


def source(
    category: RequestSourceCategoryV1 = "TOOL_RESULT",
    source_path: str | None = "src/a.py",
    content: str = "tool bytes",
) -> RequestSourceV1:
    raw = content.encode("utf-8")
    return RequestSourceV1(
        message_index=0,
        segment_index=0,
        source_category=category,
        source_path=(
            AbsentV1(kind="ABSENT")
            if source_path is None
            else PresentV1(kind="PRESENT", value=CanonicalRelativePathV1(source_path))
        ),
        content_digest=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
    )


def sources() -> SourceProjectionV1:
    return (source(),)


def scopes() -> DisclosureScopeSequenceV1:
    return (
        DirectoryDisclosureScopeV1(
            kind="DIRECTORY", path=CanonicalRelativePathV1("src")
        ),
    )


def test_subject_uses_frozen_endpoint_not_request_url() -> None:
    with pytest.raises(DisclosureSubjectError, match="ENDPOINT_OVERRIDE"):
        build_disclosure_subject(
            request_with_url_override(), sources(), scopes(), profile(), endpoint()
        )


def test_subject_binds_every_frozen_fact() -> None:
    subject = build_disclosure_subject(
        request(), sources(), scopes(), profile(), endpoint()
    )
    assert subject.schema_version == 1
    assert subject.run_id == "run-15c"
    assert subject.llm_profile_digest == profile().digest
    assert subject.provider == "openai"
    assert subject.endpoint_id == "OPENAI_PUBLIC_API_V1"
    assert subject.model == "gpt-4.1-mini"
    assert subject.request_serializer_version == "1"
    assert subject.allowed_source_paths == scopes()
    assert subject.allowed_source_categories == ("TOOL_RESULT",)
    assert subject.redaction_profile_id == "NO_CONTENT_REDACTION_V1"
    assert subject.cumulative_byte_budget == 100_000
    assert subject.expires_at == _EXPIRES_AT
    assert len(subject.digest) == 64


def test_identical_inputs_produce_identical_digest() -> None:
    first = build_disclosure_subject(
        request(), sources(), scopes(), profile(), endpoint()
    )
    second = build_disclosure_subject(
        request(), sources(), scopes(), profile(), endpoint()
    )
    assert first.digest == second.digest


def test_run_id_drift_changes_digest() -> None:
    assert (
        build_disclosure_subject(
            request(run_id="run-other"), sources(), scopes(), profile(), endpoint()
        ).digest
        != build_disclosure_subject(
            request(), sources(), scopes(), profile(), endpoint()
        ).digest
    )


def test_budget_drift_changes_digest() -> None:
    assert (
        build_disclosure_subject(
            request(budget=99_999), sources(), scopes(), profile(), endpoint()
        ).digest
        != build_disclosure_subject(
            request(), sources(), scopes(), profile(), endpoint()
        ).digest
    )


def test_expiry_drift_changes_digest() -> None:
    later = CanonicalTimestampV1("2026-08-05T09:10:00.000Z")
    assert (
        build_disclosure_subject(
            request(expires_at=later), sources(), scopes(), profile(), endpoint()
        ).digest
        != build_disclosure_subject(
            request(), sources(), scopes(), profile(), endpoint()
        ).digest
    )


def test_source_drift_changes_digest() -> None:
    other_sources = (
        source(category="FILE_CONTENT", source_path="src/b.py", content="other"),
    )
    assert (
        build_disclosure_subject(
            request(), other_sources, scopes(), profile(), endpoint()
        ).digest
        != build_disclosure_subject(
            request(), sources(), scopes(), profile(), endpoint()
        ).digest
    )


def test_scope_drift_changes_digest() -> None:
    other_scopes = (
        FileDisclosureScopeV1(kind="FILE", path=CanonicalRelativePathV1("src/a.py")),
    )
    assert (
        build_disclosure_subject(
            request(), sources(), other_scopes, profile(), endpoint()
        ).digest
        != build_disclosure_subject(
            request(), sources(), scopes(), profile(), endpoint()
        ).digest
    )


def test_profile_drift_changes_digest() -> None:
    other_profile = profile_with_model("gpt-4.1")
    assert other_profile.digest != profile().digest
    assert (
        build_disclosure_subject(
            request(), sources(), scopes(), other_profile, endpoint()
        ).digest
        != build_disclosure_subject(
            request(), sources(), scopes(), profile(), endpoint()
        ).digest
    )


def test_subject_rejects_path_source_outside_canonical_scopes() -> None:
    narrow_scopes = (
        FileDisclosureScopeV1(kind="FILE", path=CanonicalRelativePathV1("src/a.py")),
    )
    with pytest.raises(DisclosureSubjectError, match="SOURCE_SCOPE_MISMATCH"):
        build_disclosure_subject(
            request(),
            (source(source_path="src/b.py"),),
            narrow_scopes,
            profile(),
            endpoint(),
        )


def test_subject_rejects_empty_source_projection() -> None:
    with pytest.raises(DisclosureSubjectError, match="SOURCE_PROJECTION_EMPTY"):
        build_disclosure_subject(request(), (), scopes(), profile(), endpoint())


def test_subject_categories_derived_and_sorted_by_enum_order() -> None:
    mixed_sources = (
        source(category="FEEDBACK", source_path=None, content="feedback"),
        source(category="TASK", source_path=None, content="task"),
        source(category="MEMORY", source_path=None, content="memory"),
    )
    subject = build_disclosure_subject(
        request(), mixed_sources, scopes(), profile(), endpoint()
    )
    assert subject.allowed_source_categories == ("TASK", "MEMORY", "FEEDBACK")


def test_subject_scope_order_is_canonical() -> None:
    subject = build_disclosure_subject(
        request(),
        (source(source_path=None, content="pathless fact"),),
        (
            FileDisclosureScopeV1(kind="FILE", path=CanonicalRelativePathV1("z.py")),
            DirectoryDisclosureScopeV1(
                kind="DIRECTORY", path=CanonicalRelativePathV1("a")
            ),
            FileDisclosureScopeV1(kind="FILE", path=CanonicalRelativePathV1("a.py")),
        ),
        profile(),
        endpoint(),
    )
    assert subject.allowed_source_paths == (
        FileDisclosureScopeV1(kind="FILE", path=CanonicalRelativePathV1("a.py")),
        FileDisclosureScopeV1(kind="FILE", path=CanonicalRelativePathV1("z.py")),
        DirectoryDisclosureScopeV1(kind="DIRECTORY", path=CanonicalRelativePathV1("a")),
    )


def test_subject_accepts_pathless_sources_with_empty_scopes() -> None:
    subject = build_disclosure_subject(
        request(),
        (source(category="TOOL_RESULT", source_path=None, content="summary"),),
        (),
        profile(),
        endpoint(),
    )
    assert subject.allowed_source_paths == ()
    assert subject.allowed_source_categories == ("TOOL_RESULT",)


def test_request_rejects_unknown_override_fields() -> None:
    """Model/source/scope/expiry overrides are undeclared and reject."""
    with pytest.raises(Exception):
        DisclosureSubjectRequestV1(  # type: ignore[call-arg]
            run_id="run-15c",
            expires_at=_EXPIRES_AT,
            cumulative_byte_budget=100_000,
            url=AbsentV1(kind="ABSENT"),
            model="gpt-5",
        )
    with pytest.raises(Exception):
        DisclosureSubjectRequestV1(  # type: ignore[call-arg]
            run_id="run-15c",
            expires_at=_EXPIRES_AT,
            cumulative_byte_budget=100_000,
            url=AbsentV1(kind="ABSENT"),
            scope_paths=["src"],
        )


def test_subject_builder_is_pure() -> None:
    frozen_profile = profile()
    frozen_endpoint = endpoint()
    frozen_sources = sources()
    frozen_scopes = scopes()
    first = build_disclosure_subject(
        request(), frozen_sources, frozen_scopes, frozen_profile, frozen_endpoint
    )
    second = build_disclosure_subject(
        request(), frozen_sources, frozen_scopes, frozen_profile, frozen_endpoint
    )
    assert first == second
    assert frozen_sources[0].content_digest == sources()[0].content_digest


def test_subject_self_digest_binds_every_field() -> None:
    """A tampered digest field rejects at construction (model validator)."""
    subject = build_disclosure_subject(
        request(), sources(), scopes(), profile(), endpoint()
    )
    with pytest.raises(Exception):
        DisclosureGrantSubjectV1(
            schema_version=1,
            run_id=subject.run_id,
            llm_profile_digest=subject.llm_profile_digest,
            provider=subject.provider,
            endpoint_id=subject.endpoint_id,
            model=subject.model,
            request_serializer_version=subject.request_serializer_version,
            allowed_source_paths=subject.allowed_source_paths,
            allowed_source_categories=subject.allowed_source_categories,
            redaction_profile_id=subject.redaction_profile_id,
            cumulative_byte_budget=subject.cumulative_byte_budget,
            expires_at=subject.expires_at,
            digest="0" * 64,
        )


def test_disclosure_subject_drift_matrix() -> None:
    """PLAN Registry row 15.C.

    Subject uses frozen endpoint id; any source, scope, label, byte count,
    endpoint, Run, or expiry drift changes digest; request URL cannot
    override endpoint.
    """
    baseline = build_disclosure_subject(
        request(), sources(), scopes(), profile(), endpoint()
    )

    # Run drift.
    assert (
        build_disclosure_subject(
            request(run_id="run-other"), sources(), scopes(), profile(), endpoint()
        ).digest
        != baseline.digest
    )
    # Byte-count (budget) drift.
    assert (
        build_disclosure_subject(
            request(budget=1), sources(), scopes(), profile(), endpoint()
        ).digest
        != baseline.digest
    )
    # Expiry drift.
    assert (
        build_disclosure_subject(
            request(expires_at=CanonicalTimestampV1("2026-08-05T09:10:00.000Z")),
            sources(),
            scopes(),
            profile(),
            endpoint(),
        ).digest
        != baseline.digest
    )
    # Source drift (category set changes).
    assert (
        build_disclosure_subject(
            request(),
            (source(category="FEEDBACK", source_path=None, content="fact"),),
            scopes(),
            profile(),
            endpoint(),
        ).digest
        != baseline.digest
    )
    # Scope drift.
    assert (
        build_disclosure_subject(
            request(),
            sources(),
            (
                FileDisclosureScopeV1(
                    kind="FILE", path=CanonicalRelativePathV1("src/a.py")
                ),
            ),
            profile(),
            endpoint(),
        ).digest
        != baseline.digest
    )
    # Label/profile drift (frozen profile identity changes).
    assert (
        build_disclosure_subject(
            request(), sources(), scopes(), profile_with_model("gpt-4.1"), endpoint()
        ).digest
        != baseline.digest
    )
    # The subject always uses the frozen endpoint id.
    assert baseline.endpoint_id == "OPENAI_PUBLIC_API_V1"
    # Request URL cannot override the endpoint.
    with pytest.raises(DisclosureSubjectError, match="ENDPOINT_OVERRIDE"):
        build_disclosure_subject(
            request_with_url_override(), sources(), scopes(), profile(), endpoint()
        )
    # Identical facts restore the identical digest.
    assert (
        build_disclosure_subject(
            request(), sources(), scopes(), profile(), endpoint()
        ).digest
        == baseline.digest
    )
