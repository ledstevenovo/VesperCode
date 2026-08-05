"""T06.3 legacy step 6.D: trusted OpenAI endpoint map tests.

Only the built-in public OpenAI endpoint ID resolves to the immutable
trusted endpoint record; every raw URL, ``base_url``, config override,
unknown id, and alternate record rejects without network access.  HTTP
request preparation, URL overrides, credential management, and network
calls remain out of scope (GREEN-4).
"""

from __future__ import annotations

import pytest

# The endpoint is a pydantic runtime contract; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from src.vespercode.profiles.endpoints import (
    OpenAIEndpointRegistry,
    OpenAIEndpointV1,
    UnknownEndpointError,
)


def test_endpoint_registry_rejects_user_url() -> None:
    endpoint = OpenAIEndpointRegistry.resolve("OPENAI_PUBLIC_API_V1")
    assert (
        endpoint.endpoint_id,
        endpoint.scheme,
        endpoint.host,
        endpoint.effective_port,
        endpoint.base_path,
    ) == ("OPENAI_PUBLIC_API_V1", "https", "api.openai.com", 443, "/v1")
    assert not hasattr(endpoint, "base_url")

    with pytest.raises(UnknownEndpointError):
        OpenAIEndpointRegistry.resolve("https://proxy.invalid/v1")


def test_endpoint_resolution_matrix() -> None:
    """The sole built-in ID resolves; every other ID, URL, and override
    rejects without network access (Expected 6.D)."""
    endpoint = OpenAIEndpointRegistry.resolve("OPENAI_PUBLIC_API_V1")
    assert endpoint.endpoint_id == "OPENAI_PUBLIC_API_V1"
    assert endpoint.scheme == "https"
    assert endpoint.host == "api.openai.com"
    assert endpoint.effective_port == 443
    assert endpoint.base_path == "/v1"
    assert OpenAIEndpointRegistry.resolve("OPENAI_PUBLIC_API_V1") == endpoint
    # Raw user URLs, base_url, config overrides, and unknown ids reject.
    for unknown_id in (
        "https://proxy.invalid/v1",
        "base_url",
        "OPENAI_PUBLIC_API_V2",
        "openai_public_api_v1",
        "OPENAI",
        "api.openai.com",
        "",
        "https://api.openai.com/v1",
        "openai-single-turn-v1",
    ):
        with pytest.raises(UnknownEndpointError):
            OpenAIEndpointRegistry.resolve(unknown_id)
    for non_string in (None, 443, b"OPENAI_PUBLIC_API_V1"):
        with pytest.raises(UnknownEndpointError):
            OpenAIEndpointRegistry.resolve(non_string)  # type: ignore[arg-type]
    # The record is closed: missing, unknown, extra, type-confused, or
    # alternate values reject before a record exists.
    for bad_fields in (
        {},
        {
            "endpoint_id": "OTHER_ENDPOINT_V1",
            "scheme": "https",
            "host": "api.openai.com",
            "effective_port": 443,
            "base_path": "/v1",
        },
        {
            "endpoint_id": "OPENAI_PUBLIC_API_V1",
            "scheme": "http",
            "host": "api.openai.com",
            "effective_port": 443,
            "base_path": "/v1",
        },
        {
            "endpoint_id": "OPENAI_PUBLIC_API_V1",
            "scheme": "https",
            "host": "api.example.com",
            "effective_port": 443,
            "base_path": "/v1",
        },
        {
            "endpoint_id": "OPENAI_PUBLIC_API_V1",
            "scheme": "https",
            "host": "api.openai.com",
            "effective_port": 444,
            "base_path": "/v1",
        },
        {
            "endpoint_id": "OPENAI_PUBLIC_API_V1",
            "scheme": "https",
            "host": "api.openai.com",
            "effective_port": 443,
            "base_path": "/v2",
        },
        {
            "endpoint_id": "OPENAI_PUBLIC_API_V1",
            "scheme": "https",
            "host": "api.openai.com",
            "effective_port": "443",
            "base_path": "/v1",
        },
        {
            "endpoint_id": "OPENAI_PUBLIC_API_V1",
            "scheme": "https",
            "host": "api.openai.com",
            "effective_port": 443.0,
            "base_path": "/v1",
        },
        {
            "endpoint_id": "OPENAI_PUBLIC_API_V1",
            "scheme": "https",
            "host": "api.openai.com",
            "effective_port": True,
            "base_path": "/v1",
        },
        {
            "endpoint_id": "OPENAI_PUBLIC_API_V1",
            "scheme": "https",
            "host": "api.openai.com",
            "effective_port": 443,
            "base_path": "/v1",
            "base_url": "https://api.openai.com/v1",
        },
        {
            "endpoint_id": "OPENAI_PUBLIC_API_V1",
            "scheme": "https",
            "host": "api.openai.com",
            "effective_port": 443,
            "base_path": "/v1",
            "extra_field": 1,
        },
    ):
        with pytest.raises(ValidationError):
            OpenAIEndpointV1.model_validate(bad_fields)
    # The resolved record carries exactly the five trusted fields.
    assert OpenAIEndpointV1.model_fields.keys() == {
        "endpoint_id",
        "scheme",
        "host",
        "effective_port",
        "base_path",
    }
    # The returned record is immutable.
    with pytest.raises(ValidationError):
        setattr(endpoint, "host", "evil.example")
    with pytest.raises(ValidationError):
        setattr(endpoint, "base_path", "/v2")
