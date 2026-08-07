"""T16.1 legacy step 16.B: single-call trusted OpenAI adapter tests.

Pins the exact RED (``test_openai_adapter_never_retries_transport``:
exactly one non-retried transport attempt through a freshly bound
adapter), the bind contract (unbound adapters cannot generate; the bound
adapter accepts only the Task 15.E authorization plus a fresh Task 27.B
secret wrapper), the sole trusted endpoint URL derived from the built-in
``OpenAIEndpointV1`` map (never a custom URL, environment credential,
alternate endpoint, retry policy, or redirect replay), the exact
serialized request body, bounded responses, and redacted failures.
``test_openai_transport_endpoint_serialization_matrix`` implements the
operative 16.B matrix row (PLAN Registry line 11390): "one call uses the
frozen endpoint and canonical serialization; redirect cross-origin,
timeout, malformed response, HTTP failure, or transport uncertainty
performs no retry and returns the declared typed failure."
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal, Mapping

import pytest

# The adapter consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips cleanly
# there (formal env runs it fully).
pytest.importorskip("pydantic")

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.credentials.port import SecretCredentialV1
from vespercode.governance.disclosure_ledger import (
    DisclosureAuthorizationRecordV1,
)
from vespercode.governance.request_sources import (
    RequestContentSegmentV1,
    RequestMessageV1,
    validate_segment_sources,
)
from vespercode.llm.base import ModelResponse
from vespercode.llm.openai_adapter import (
    BoundOpenAILLMAdapterV1,
    LLMTransportError,
    LLMTransportResultV1,
    OpenAILLMAdapter,
    OpenAITransportFailure,
)
from vespercode.llm.openai_serializer import openai_request_body_bytes
from vespercode.llm.prepared_request import (
    OpenAIPreparedModelRequestV1,
    prepare_openai_request,
)
from vespercode.profiles.endpoints import OpenAIEndpointRegistry
from vespercode.profiles.llm import OpenAILLMProfileV1, load_llm_profile

_OPENAI_BUILTIN = (
    Path(__file__).resolve().parents[3]
    / "src/vespercode/profiles/builtin/openai-single-turn-v1.json"
)
_TRUSTED_URL = "https://api.openai.com:443/v1/chat/completions"
_FIXED_CREATED_AT = CanonicalTimestampV1("2026-08-05T09:00:00.000Z")


def openai_profile() -> OpenAILLMProfileV1:
    """The frozen packaged built-in OpenAI profile (digest-verified)."""
    loaded = load_llm_profile(_OPENAI_BUILTIN.read_bytes())
    assert isinstance(loaded, OpenAILLMProfileV1)
    return loaded


def test_secret() -> SecretCredentialV1:
    """A fresh Task 27.B-style hidden secret wrapper for one call."""
    return SecretCredentialV1.from_hidden_input("vespercode-test-secret-0001")


test_secret.__test__ = False  # type: ignore[attr-defined]  # helper, not a test


def _segment(
    category: Literal[
        "HARNESS_PROTOCOL", "TASK", "FILE_CONTENT", "TOOL_RESULT", "MEMORY", "FEEDBACK"
    ],
    content: str,
    *,
    path: str | None = None,
) -> RequestContentSegmentV1:
    raw = content.encode("utf-8")
    source_path = (
        AbsentV1(kind="ABSENT")
        if path is None
        else PresentV1(kind="PRESENT", value=CanonicalRelativePathV1(path))
    )
    return RequestContentSegmentV1(
        source_category=category,
        source_path=source_path,
        content=content,
        content_digest=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
    )


def _messages() -> tuple[RequestMessageV1, ...]:
    return (
        RequestMessageV1(
            role="SYSTEM",
            segments=(_segment("HARNESS_PROTOCOL", "VesperCode v1 protocol."),),
        ),
        RequestMessageV1(
            role="USER",
            segments=(
                _segment("TASK", "Fix the failing test."),
                _segment(
                    "FILE_CONTENT",
                    "def example():\n    return 0\n",
                    path="src/example.py",
                ),
            ),
        ),
    )


def valid_openai_prepared_request() -> OpenAIPreparedModelRequestV1:
    """One digest-consistent OpenAI prepared request from the frozen profile."""
    return prepare_openai_request(openai_profile(), _messages())


def valid_authorization(
    request: OpenAIPreparedModelRequestV1 | None = None,
    *,
    request_digest: str | None = None,
    endpoint_id: str | None = None,
) -> DisclosureAuthorizationRecordV1:
    """The Task 15.E authorization record for the exact prepared request.

    ``actual_sources`` is the exact one-to-one projection of the request's
    segments and ``request_digest`` binds the exact request (SPEC §4.4.4);
    *request_digest* and *endpoint_id* override the binding for mismatch
    tests.
    """
    prepared = valid_openai_prepared_request() if request is None else request
    return DisclosureAuthorizationRecordV1(
        schema_version=1,
        authorization_record_id="authz-1",
        grant_id="grant-1",
        grant_subject_digest="d" * 64,
        llm_profile_digest=prepared.llm_profile_digest,
        provider=prepared.provider,
        endpoint_id=prepared.endpoint_id if endpoint_id is None else endpoint_id,
        model=prepared.model,
        request_serializer_version=prepared.request_serializer_version,
        request_digest=prepared.digest if request_digest is None else request_digest,
        actual_sources=validate_segment_sources(prepared.messages),
        canonical_byte_count=prepared.canonical_byte_count,
        redaction_profile_id=prepared.redaction_profile_id,
        created_at=_FIXED_CREATED_AT,
    )


def _ok_body(content: str) -> bytes:
    """One vendor chat-completions 200 body carrying *content*."""
    return json.dumps({"choices": [{"message": {"content": content}}]}).encode("utf-8")


class RecordingTransport:
    """A fake transport that records exactly one attempt and fails/returns.

    ``call_count`` is the recorded number of transport attempts; the
    recorded URL, headers, and body prove the frozen endpoint and exact
    canonical serialization.
    """

    def __init__(
        self,
        *,
        result: LLMTransportResultV1 | None = None,
        error: Exception | None = None,
    ) -> None:
        self._result = result
        self._error = error
        self.call_count = 0
        self.last_url = ""
        self.last_headers: dict[str, str] = {}
        self.last_body = b""

    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> LLMTransportResultV1:
        self.call_count += 1
        self.last_url = url
        self.last_headers = dict(headers)
        self.last_body = body
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


@pytest.fixture
def failing_transport() -> RecordingTransport:
    """One transport that records a single failed attempt."""
    return RecordingTransport(error=LLMTransportError("simulated network failure"))


@pytest.fixture
def adapter(failing_transport: RecordingTransport) -> OpenAILLMAdapter:
    """The unbound adapter bound to the failing transport at construction."""
    return OpenAILLMAdapter(transport=failing_transport)


def test_openai_adapter_never_retries_transport(
    adapter: OpenAILLMAdapter,
    failing_transport: RecordingTransport,
) -> None:
    bound = adapter.bind(valid_authorization(), test_secret())
    with pytest.raises(OpenAITransportFailure):
        bound.generate(valid_openai_prepared_request())
    assert failing_transport.call_count == 1


# ---------------------------------------------------------------------------
# 16.B matrix (PLAN Registry 16.B row, operative authority): one call uses
# the frozen endpoint and canonical serialization; redirect cross-origin,
# timeout, malformed response, HTTP failure, or transport uncertainty
# performs no retry and returns the declared typed failure.
# ---------------------------------------------------------------------------


def test_openai_transport_endpoint_serialization_matrix() -> None:
    # --- success: one call, frozen endpoint, canonical serialization ---
    content = '{"schema_version":1,"action_type":"list_files"}'
    ok_transport = RecordingTransport(
        result=LLMTransportResultV1(
            status_code=200,
            headers=(("content-type", "application/json"),),
            body=_ok_body(content),
        )
    )
    request = valid_openai_prepared_request()
    bound = OpenAILLMAdapter(transport=ok_transport).bind(
        valid_authorization(request), test_secret()
    )
    response = bound.generate(request)
    assert ok_transport.call_count == 1
    assert ok_transport.last_url == _TRUSTED_URL
    assert ok_transport.last_body == openai_request_body_bytes(request)
    assert len(ok_transport.last_body) == request.canonical_byte_count
    assert ok_transport.last_headers["Content-Type"] == "application/json"
    assert ok_transport.last_headers["Authorization"] == (
        "Bearer vespercode-test-secret-0001"
    )
    assert isinstance(response, ModelResponse)
    assert response.text == content

    # --- redirect cross-origin: typed failure, no retry, no re-send ---
    redirect_transport = RecordingTransport(
        result=LLMTransportResultV1(
            status_code=302,
            headers=(("location", "https://evil.example/v1/chat/completions"),),
            body=b"",
        )
    )
    bound = OpenAILLMAdapter(transport=redirect_transport).bind(
        valid_authorization(), test_secret()
    )
    with pytest.raises(OpenAITransportFailure) as redirect_exc:
        bound.generate(valid_openai_prepared_request())
    assert redirect_exc.value.error_code == "LLM_ENDPOINT_MISMATCH"
    assert redirect_transport.call_count == 1

    # --- timeout: typed failure, no retry ---
    timeout_transport = RecordingTransport(error=TimeoutError("simulated timeout"))
    bound = OpenAILLMAdapter(transport=timeout_transport).bind(
        valid_authorization(), test_secret()
    )
    with pytest.raises(OpenAITransportFailure) as timeout_exc:
        bound.generate(valid_openai_prepared_request())
    assert timeout_exc.value.error_code == "LLM_CALL_FAILED"
    assert timeout_transport.call_count == 1

    # --- HTTP failure: typed failure, no retry ---
    http_transport = RecordingTransport(
        result=LLMTransportResultV1(status_code=500, headers=(), body=b"internal error")
    )
    bound = OpenAILLMAdapter(transport=http_transport).bind(
        valid_authorization(), test_secret()
    )
    with pytest.raises(OpenAITransportFailure) as http_exc:
        bound.generate(valid_openai_prepared_request())
    assert http_exc.value.error_code == "LLM_CALL_FAILED"
    assert http_transport.call_count == 1

    # --- malformed response: typed failure, no retry ---
    malformed_transport = RecordingTransport(
        result=LLMTransportResultV1(
            status_code=200, headers=(), body=b"not json at all"
        )
    )
    bound = OpenAILLMAdapter(transport=malformed_transport).bind(
        valid_authorization(), test_secret()
    )
    with pytest.raises(OpenAITransportFailure) as malformed_exc:
        bound.generate(valid_openai_prepared_request())
    assert malformed_exc.value.error_code == "LLM_CALL_FAILED"
    assert malformed_transport.call_count == 1

    # --- transport uncertainty: typed failure, no retry ---
    uncertain_transport = RecordingTransport(
        error=LLMTransportError("delivery unknown")
    )
    bound = OpenAILLMAdapter(transport=uncertain_transport).bind(
        valid_authorization(), test_secret()
    )
    with pytest.raises(OpenAITransportFailure) as uncertain_exc:
        bound.generate(valid_openai_prepared_request())
    assert uncertain_exc.value.error_code == "LLM_CALL_FAILED"
    assert uncertain_transport.call_count == 1

    # --- bounded responses: oversized content and raw body fail closed ---
    oversized_transport = RecordingTransport(
        result=LLMTransportResultV1(
            status_code=200, headers=(), body=_ok_body("x" * 65537)
        )
    )
    bound = OpenAILLMAdapter(transport=oversized_transport).bind(
        valid_authorization(), test_secret()
    )
    with pytest.raises(OpenAITransportFailure) as oversized_exc:
        bound.generate(valid_openai_prepared_request())
    assert oversized_exc.value.error_code == "LLM_CALL_FAILED"
    assert oversized_transport.call_count == 1

    raw_oversized_transport = RecordingTransport(
        result=LLMTransportResultV1(
            status_code=200, headers=(), body=b"x" * (1024 * 1024 + 1)
        )
    )
    bound = OpenAILLMAdapter(transport=raw_oversized_transport).bind(
        valid_authorization(), test_secret()
    )
    with pytest.raises(OpenAITransportFailure) as raw_oversized_exc:
        bound.generate(valid_openai_prepared_request())
    assert raw_oversized_exc.value.error_code == "LLM_CALL_FAILED"
    assert raw_oversized_transport.call_count == 1


# ---------------------------------------------------------------------------
# Bind contract and boundary enforcement.
# ---------------------------------------------------------------------------


def test_unbound_adapter_cannot_generate() -> None:
    unbound = OpenAILLMAdapter()
    assert not hasattr(unbound, "generate")


def test_bind_requires_task_15e_authorization_and_fresh_test_secret() -> None:
    bound = OpenAILLMAdapter().bind(valid_authorization(), test_secret())
    assert bound is not None


def test_generate_rejects_endpoint_mismatch_before_any_transport_call() -> None:
    """A forged authorization with a foreign endpoint never reaches transport.

    ``bind`` resolves the authorization's endpoint through the built-in
    registry (a foreign id fails there), so this pins the bound adapter's
    own defense-in-depth check: endpoint inconsistency is
    ``LLM_ENDPOINT_MISMATCH`` (SPEC §4.4.4) with zero transport calls.
    """
    transport = RecordingTransport(
        result=LLMTransportResultV1(status_code=200, headers=(), body=_ok_body("{}"))
    )
    forged = valid_authorization(endpoint_id="EVIL_API_V1")
    bound = BoundOpenAILLMAdapterV1(
        transport=transport,
        authorization=forged,
        credential=test_secret(),
        endpoint=OpenAIEndpointRegistry.resolve("OPENAI_PUBLIC_API_V1"),
    )
    with pytest.raises(OpenAITransportFailure) as mismatch_exc:
        bound.generate(valid_openai_prepared_request())
    assert mismatch_exc.value.error_code == "LLM_ENDPOINT_MISMATCH"
    assert transport.call_count == 0


def test_generate_rejects_mismatched_authorization_with_zero_transport_calls() -> None:
    transport = RecordingTransport(
        result=LLMTransportResultV1(status_code=200, headers=(), body=_ok_body("{}"))
    )
    foreign = valid_authorization(request_digest="e" * 64)
    bound = OpenAILLMAdapter(transport=transport).bind(foreign, test_secret())
    with pytest.raises(OpenAITransportFailure) as mismatch_exc:
        bound.generate(valid_openai_prepared_request())
    assert mismatch_exc.value.error_code == "INTERNAL_ERROR"
    assert transport.call_count == 0


def test_failure_messages_are_bounded_and_redacted() -> None:
    transport = RecordingTransport(
        result=LLMTransportResultV1(
            status_code=500, headers=(), body=b"sk-vespercode-0001-body"
        )
    )
    bound = OpenAILLMAdapter(transport=transport).bind(
        valid_authorization(), test_secret()
    )
    with pytest.raises(OpenAITransportFailure) as failure:
        bound.generate(valid_openai_prepared_request())
    message = str(failure.value)
    assert "vespercode-test-secret-0001" not in message
    assert "sk-vespercode-0001-body" not in message
    assert "api.openai.com" not in message


def test_generate_returns_only_model_response_or_typed_failure() -> None:
    transport = RecordingTransport(
        result=LLMTransportResultV1(
            status_code=200,
            headers=(("content-type", "application/json"),),
            body=_ok_body('{"schema_version":1}'),
        )
    )
    bound = OpenAILLMAdapter(transport=transport).bind(
        valid_authorization(), test_secret()
    )
    response = bound.generate(valid_openai_prepared_request())
    assert isinstance(response, ModelResponse)
