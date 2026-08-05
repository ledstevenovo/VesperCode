"""T16.1 legacy step 16.B: exact segment-to-OpenAI body serialization tests.

Pins the exact request-body vectors: segment contents are concatenated in
order with no implicit separator and no source metadata, the role maps
``SYSTEM``/``USER`` to ``system``/``user``, the frozen
``max_output_tokens`` and fixed JSON-object response format appear, the
``ABSENT`` optional fixed parameters are omitted and ``PRESENT``
parameters map ``value_milli / 1000`` to the vendor float, and the exact
final UTF-8 body bytes equal the request's ``canonical_byte_count`` (the
byte length the serializer hands to the transport).  Unknown, extra, or
cross-mode fields reject before any body exists.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal, cast

import pytest

# The serializer consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips cleanly
# there (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from src.vespercode.canonical.digest import domain_digest
from src.vespercode.canonical.json_v1 import CanonicalValueV1
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.governance.request_sources import (
    RequestContentSegmentV1,
    RequestMessageV1,
)
from src.vespercode.llm.openai_serializer import (
    openai_request_body_bytes,
    serialize_openai_request,
)
from src.vespercode.llm.prepared_request import (
    OpenAIRequestBodyV1,
    OpenAIPreparedModelRequestV1,
    prepare_openai_request,
)
from src.vespercode.profiles.llm import (
    OpenAILLMProfileV1,
    OpenAIFixedParametersV1,
    load_llm_profile,
)

_OPENAI_BUILTIN = (
    Path(__file__).resolve().parents[3]
    / "src/vespercode/profiles/builtin/openai-single-turn-v1.json"
)


def openai_profile() -> OpenAILLMProfileV1:
    """The frozen packaged built-in OpenAI profile (digest-verified)."""
    loaded = load_llm_profile(_OPENAI_BUILTIN.read_bytes())
    assert isinstance(loaded, OpenAILLMProfileV1)
    return loaded


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


def _message(
    role: Literal["SYSTEM", "USER"], *segments: RequestContentSegmentV1
) -> RequestMessageV1:
    return RequestMessageV1(role=role, segments=segments)


def _messages() -> tuple[RequestMessageV1, ...]:
    """Two messages; the USER message concatenates three segments in order."""
    return (
        _message("SYSTEM", _segment("HARNESS_PROTOCOL", "VesperCode v1 protocol.")),
        _message(
            "USER",
            _segment("TASK", "Fix the failing test."),
            _segment("TOOL_RESULT", "check failed", path="src/example.py"),
            _segment(
                "FILE_CONTENT",
                "def example():\n    return 0\n",
                path="src/example.py",
            ),
        ),
    )


def _typed_request() -> OpenAIPreparedModelRequestV1:
    """One digest-consistent request with the standard message sequence."""
    return prepare_openai_request(openai_profile(), _messages())


def test_serialize_exact_body_vector() -> None:
    request = _typed_request()
    body = serialize_openai_request(request)
    assert body.model == "gpt-4.1-mini"
    assert body.max_output_tokens == 8192
    assert body.response_format.type == "json_object"
    assert body.temperature.kind == "ABSENT"
    assert body.top_p.kind == "ABSENT"
    assert body.seed.kind == "ABSENT"
    assert len(body.messages) == 2
    assert body.messages[0].role == "system"
    assert body.messages[0].content == "VesperCode v1 protocol."
    assert body.messages[1].role == "user"
    # Segment contents are concatenated in order with no separator and no
    # source metadata.
    assert body.messages[1].content == (
        "Fix the failing test.check faileddef example():\n    return 0\n"
    )
    # The exact final UTF-8 body bytes are the request's canonical byte
    # count and carry exactly the vendor fields (ABSENT optionals omitted).
    raw = openai_request_body_bytes(request)
    assert len(raw) == request.canonical_byte_count
    decoded = json.loads(raw.decode("utf-8"))
    assert decoded == {
        "model": "gpt-4.1-mini",
        "messages": [
            {"role": "system", "content": "VesperCode v1 protocol."},
            {
                "role": "user",
                "content": "Fix the failing test.check failed"
                "def example():\n    return 0\n",
            },
        ],
        "max_output_tokens": 8192,
        "response_format": {"type": "json_object"},
    }
    assert set(decoded) == {
        "max_output_tokens",
        "messages",
        "model",
        "response_format",
    }


def test_serialize_optional_fixed_parameters_map_to_vendor_values() -> None:
    custom_fixed = {
        "schema_version": 1,
        "max_output_tokens": 2048,
        "temperature": {"kind": "PRESENT", "value_milli": 500},
        "top_p": {"kind": "PRESENT", "value_milli": 900},
        "seed": {"kind": "PRESENT", "value": 7},
        "response_format": "JSON_OBJECT",
    }
    request = _request_with_fixed_parameters(custom_fixed)
    body = serialize_openai_request(request)
    assert body.max_output_tokens == 2048
    assert body.temperature.kind == "PRESENT"
    assert body.temperature.value == 0.5
    assert body.top_p.kind == "PRESENT"
    assert body.top_p.value == 0.9
    assert body.seed.kind == "PRESENT"
    assert body.seed.value == 7
    raw = openai_request_body_bytes(request)
    decoded = json.loads(raw.decode("utf-8"))
    assert decoded["temperature"] == 0.5
    assert decoded["top_p"] == 0.9
    assert decoded["seed"] == 7
    assert len(raw) == request.canonical_byte_count


def _request_with_fixed_parameters(
    fixed_parameters: dict[str, object],
) -> OpenAIPreparedModelRequestV1:
    """One digest-consistent request carrying exact custom fixed parameters."""
    profile = openai_profile()
    messages = _messages()
    canonical_messages = tuple(
        {
            "role": message.role,
            "segments": tuple(
                {
                    "source_category": seg.source_category,
                    "source_path": (
                        {"kind": "ABSENT"}
                        if seg.source_path.kind == "ABSENT"
                        else {
                            "kind": "PRESENT",
                            "value": seg.source_path.value.value,
                        }
                    ),
                    "content": seg.content,
                    "content_digest": seg.content_digest,
                    "byte_count": seg.byte_count,
                }
                for seg in message.segments
            ),
        }
        for message in messages
    )
    # Recompute the exact body bytes for the custom fixed parameters.
    body_dict: dict[str, object] = {
        "model": profile.model,
        "messages": tuple(
            {
                "role": "system" if message.role == "SYSTEM" else "user",
                "content": "".join(seg.content for seg in message.segments),
            }
            for message in messages
        ),
        "max_output_tokens": fixed_parameters["max_output_tokens"],
    }
    temperature = fixed_parameters["temperature"]
    top_p = fixed_parameters["top_p"]
    seed = fixed_parameters["seed"]
    assert isinstance(temperature, dict) and isinstance(top_p, dict)
    assert isinstance(seed, dict)
    if temperature["kind"] == "PRESENT":
        value_milli = temperature["value_milli"]
        assert isinstance(value_milli, int)
        body_dict["temperature"] = value_milli / 1000
    if top_p["kind"] == "PRESENT":
        value_milli = top_p["value_milli"]
        assert isinstance(value_milli, int)
        body_dict["top_p"] = value_milli / 1000
    if seed["kind"] == "PRESENT":
        body_dict["seed"] = seed["value"]
    body_dict["response_format"] = {"type": "json_object"}
    canonical_byte_count = len(
        json.dumps(
            body_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    )
    digest = domain_digest(
        "OpenAIPreparedModelRequestV1",
        1,
        {
            "schema_version": 1,
            "mode": "OPENAI",
            "llm_profile_digest": profile.digest,
            "provider": profile.provider,
            "endpoint_id": profile.endpoint_id,
            "model": profile.model,
            "request_serializer_version": profile.request_serializer_version,
            "messages": canonical_messages,
            "fixed_parameters": cast(CanonicalValueV1, fixed_parameters),
            "redaction_profile_id": profile.redaction_profile_id,
            "canonical_byte_count": canonical_byte_count,
        },
    )
    return OpenAIPreparedModelRequestV1(
        schema_version=1,
        mode="OPENAI",
        llm_profile_digest=profile.digest,
        provider=profile.provider,
        endpoint_id=profile.endpoint_id,
        model=profile.model,
        request_serializer_version=profile.request_serializer_version,
        messages=messages,
        fixed_parameters=cast(OpenAIFixedParametersV1, fixed_parameters),
        redaction_profile_id=profile.redaction_profile_id,
        canonical_byte_count=canonical_byte_count,
        digest=digest,
    )


def test_serialize_never_emits_source_metadata() -> None:
    raw = openai_request_body_bytes(_typed_request()).decode("utf-8")
    assert "source_category" not in raw
    assert "source_path" not in raw
    assert "content_digest" not in raw
    assert "byte_count" not in raw
    assert "src/example.py" not in raw


def test_body_model_rejects_unknown_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        OpenAIRequestBodyV1.model_validate(
            {
                "model": "gpt-4.1-mini",
                "messages": ({"role": "user", "content": "x"},),
                "max_output_tokens": 8192,
                "temperature": {"kind": "ABSENT"},
                "top_p": {"kind": "ABSENT"},
                "seed": {"kind": "ABSENT"},
                "response_format": {"type": "json_object"},
                "extra": 1,
            }
        )
    with pytest.raises(ValidationError):
        OpenAIRequestBodyV1.model_validate(
            {
                "model": "gpt-4.1-mini",
                "messages": ({"role": "assistant", "content": "x"},),
                "max_output_tokens": 8192,
                "temperature": {"kind": "ABSENT"},
                "top_p": {"kind": "ABSENT"},
                "seed": {"kind": "ABSENT"},
                "response_format": {"type": "json_object"},
            }
        )
    with pytest.raises(ValidationError):
        OpenAIRequestBodyV1.model_validate(
            {
                "model": "gpt-4.1-mini",
                "messages": (),
                "max_output_tokens": 8192,
                "temperature": {"kind": "ABSENT"},
                "top_p": {"kind": "ABSENT"},
                "seed": {"kind": "ABSENT"},
                "response_format": {"type": "json_object"},
            }
        )
