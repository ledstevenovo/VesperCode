"""T06.3 legacy step 6.C: closed Mock and OpenAI LLM profile tests.

The immutable Mock and OpenAI variants are mutually exclusive: Mock data
can never carry OpenAI configuration, every unknown, extra, or mutable
field rejects, and each packaged built-in resource has exactly one
integrity identity.  Endpoint resolution, request serialization,
credential access, and adapter calls remain out of scope (GREEN-4).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# The profiles are pydantic runtime contracts; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from src.vespercode.canonical.digest import domain_digest
from src.vespercode.profiles.llm import (
    MockLLMProfileV1,
    OpenAILLMProfileV1,
    PresentIntegerParameterV1,
    PresentTemperatureMilliV1,
    PresentTopPMilliV1,
    load_llm_profile,
)

# The frozen §0.1 identity pins of the packaged built-ins (computed by the
# implementer with the T04.2 canonical encoder and independently recomputed
# by both review stages).
_MOCK_SCRIPT_DIGEST = "3be1c2165c5cf2e4d271a489809e1a7c443fcf452b66bb9a743022ee4f0894da"
_MOCK_DIGEST = "3fd39f821cae060b3bd0b382bfcd4843cbb465269b1487200582d4bb4346e4a9"
_OPENAI_DIGEST = "cb46690ef08202e120b71823d3de8ae1c31c903af6b0129984a9a4e893dd3f9c"


def packaged_mock_profile_bytes() -> bytes:
    """The packaged immutable Mock profile bytes."""
    path = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "vespercode"
        / "profiles"
        / "builtin"
        / "mock-deterministic-v1.json"
    )
    return path.read_bytes()


def packaged_openai_profile_bytes() -> bytes:
    """The packaged immutable OpenAI profile bytes."""
    path = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "vespercode"
        / "profiles"
        / "builtin"
        / "openai-single-turn-v1.json"
    )
    return path.read_bytes()


def mock_profile_with_endpoint() -> bytes:
    """The smallest cross-mode payload: the mock profile carrying an
    OpenAI endpoint field, which the closed schema must reject."""
    payload = json.loads(packaged_mock_profile_bytes())
    payload["endpoint_id"] = "OPENAI_PUBLIC_API_V1"
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def _raw_drifted_bytes(packaged: bytes, **drifted_fields: object) -> bytes:
    """Drifted payload bytes for schema-level rejection rows.

    The closed schema rejects these rows before any digest acceptance, so
    the digest value only needs to be form-valid, not self-consistent.
    """
    payload = json.loads(packaged)
    payload.update(drifted_fields)
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def _self_consistent_openai_bytes(**drifted_fields: object) -> bytes:
    """OpenAI payload bytes with the §0.1 digest recomputed over the
    drifted fields, exactly like a real attacker would produce."""
    payload = json.loads(packaged_openai_profile_bytes())
    payload.pop("digest")
    payload.update(drifted_fields)
    payload["digest"] = domain_digest("OpenAILLMProfileV1", 1, payload)
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def test_mock_profile_rejects_openai_fields() -> None:
    with pytest.raises(ValidationError):
        load_llm_profile(mock_profile_with_endpoint())


def test_llm_profile_closed_union_matrix() -> None:
    """Exact built-ins load; every cross-mode, unknown, extra, mutable, or
    type-confused field rejects deterministically (Expected 6.C)."""
    mock = load_llm_profile(packaged_mock_profile_bytes())
    assert mock.mode == "MOCK"
    assert mock.schema_version == 1
    assert mock.profile_id == "mock-deterministic-v1"
    assert mock.adapter_version == "1"
    assert mock.script_id == "mock-deterministic-response-v1"
    assert mock.script_digest == _MOCK_SCRIPT_DIGEST
    assert mock.digest == _MOCK_DIGEST
    assert load_llm_profile(packaged_mock_profile_bytes()) == mock

    openai = load_llm_profile(packaged_openai_profile_bytes())
    assert openai.mode == "OPENAI"
    assert openai.schema_version == 1
    assert openai.profile_id == "openai-single-turn-v1"
    assert openai.provider == "openai"
    assert openai.endpoint_id == "OPENAI_PUBLIC_API_V1"
    assert openai.model == "gpt-4.1-mini"
    assert openai.adapter_version == "1"
    assert openai.request_serializer_version == "1"
    assert openai.redaction_profile_id == "NO_CONTENT_REDACTION_V1"
    assert openai.fixed_parameters.schema_version == 1
    assert openai.fixed_parameters.max_output_tokens == 8192
    assert openai.fixed_parameters.temperature.kind == "ABSENT"
    assert openai.fixed_parameters.top_p.kind == "ABSENT"
    assert openai.fixed_parameters.seed.kind == "ABSENT"
    assert openai.fixed_parameters.response_format == "JSON_OBJECT"
    assert openai.digest == _OPENAI_DIGEST
    assert load_llm_profile(packaged_openai_profile_bytes()) == openai

    # Cross-mode fields reject: Mock never carries OpenAI configuration.
    for openai_field in (
        "provider",
        "endpoint_id",
        "model",
        "request_serializer_version",
        "redaction_profile_id",
        "fixed_parameters",
    ):
        with pytest.raises(ValidationError):
            load_llm_profile(
                _raw_drifted_bytes(packaged_mock_profile_bytes(), **{openai_field: "x"})
            )
    # OpenAI never carries Mock script fields.
    for mock_field in ("script_id", "script_digest"):
        with pytest.raises(ValidationError):
            load_llm_profile(
                _raw_drifted_bytes(packaged_openai_profile_bytes(), **{mock_field: "x"})
            )
    # Unknown, missing, and renamed fields reject on both variants.
    for packaged, drift in (
        (packaged_mock_profile_bytes(), {"extra_field": 1}),
        (packaged_openai_profile_bytes(), {"extra_field": 1}),
        (packaged_mock_profile_bytes(), {"mode": "GEMINI"}),
        (packaged_openai_profile_bytes(), {"mode": "GEMINI"}),
        (packaged_mock_profile_bytes(), {"profile_id": "openai-single-turn-v1"}),
        (packaged_openai_profile_bytes(), {"profile_id": "mock-deterministic-v1"}),
        (packaged_mock_profile_bytes(), {"mode": "MOCK", "kind": "PRESENT"}),
    ):
        with pytest.raises(ValidationError):
            load_llm_profile(_raw_drifted_bytes(packaged, **drift))
    for packaged in (packaged_mock_profile_bytes(), packaged_openai_profile_bytes()):
        payload = json.loads(packaged)
        del payload["mode"]
        with pytest.raises(ValidationError):
            load_llm_profile(json.dumps(payload, sort_keys=True).encode("utf-8"))
    # A drifted digest (same body) rejects before any identity exists.
    for packaged in (packaged_mock_profile_bytes(), packaged_openai_profile_bytes()):
        with pytest.raises(ValidationError):
            load_llm_profile(_raw_drifted_bytes(packaged, digest="0" * 64))
    # Type-confused schema versions and digest forms reject.
    for packaged in (packaged_mock_profile_bytes(), packaged_openai_profile_bytes()):
        for schema_version in (2, True, 1.0, "1"):
            with pytest.raises(ValidationError):
                load_llm_profile(
                    _raw_drifted_bytes(packaged, schema_version=schema_version)
                )
    for packaged in (packaged_mock_profile_bytes(), packaged_openai_profile_bytes()):
        for bad_digest in ("x", "0" * 63, "0" * 65, "A" * 64):
            with pytest.raises(ValidationError):
                load_llm_profile(_raw_drifted_bytes(packaged, digest=bad_digest))
    # Non-JSON and non-object bytes reject deterministically.
    for non_object_bytes in (b"not json", b"[]", b"null", b"\xff\xfe"):
        with pytest.raises(ValueError):
            load_llm_profile(non_object_bytes)
    # OpenAIFixedParametersV1 bounds reject and PRESENT rows round-trip.
    for bad_fixed in (
        {"max_output_tokens": 0},
        {"max_output_tokens": 8193},
        {"max_output_tokens": True},
        {"response_format": "TEXT"},
        {"temperature": {"kind": "PRESENT", "value_milli": 2001}},
        {"temperature": {"kind": "PRESENT", "value_milli": -1}},
        {"top_p": {"kind": "PRESENT", "value_milli": 1001}},
        {"seed": {"kind": "PRESENT", "value": 2**63}},
        {"seed": {"kind": "PRESENT", "value": -(2**63) - 1}},
        {"temperature": {"kind": "PRESENT"}},
        {"seed": {"kind": "ABSENT", "value": 1}},
    ):
        payload = json.loads(packaged_openai_profile_bytes())
        payload["fixed_parameters"].update(bad_fixed)
        with pytest.raises(ValidationError):
            load_llm_profile(json.dumps(payload, sort_keys=True).encode("utf-8"))
    present = load_llm_profile(
        _self_consistent_openai_bytes(
            fixed_parameters={
                "schema_version": 1,
                "max_output_tokens": 4096,
                "temperature": {"kind": "PRESENT", "value_milli": 2000},
                "top_p": {"kind": "PRESENT", "value_milli": 1000},
                "seed": {"kind": "PRESENT", "value": 42},
                "response_format": "JSON_OBJECT",
            }
        )
    )
    assert isinstance(present, OpenAILLMProfileV1)
    temperature = present.fixed_parameters.temperature
    assert isinstance(temperature, PresentTemperatureMilliV1)
    assert temperature.kind == "PRESENT"
    assert temperature.value_milli == 2000
    top_p = present.fixed_parameters.top_p
    assert isinstance(top_p, PresentTopPMilliV1)
    assert top_p.value_milli == 1000
    seed = present.fixed_parameters.seed
    assert isinstance(seed, PresentIntegerParameterV1)
    assert seed.value == 42
    assert present.fixed_parameters.max_output_tokens == 4096
    # The signed 64-bit seed domain accepts its exact extremes.
    for extreme_seed in (2**63 - 1, -(2**63)):
        extreme = load_llm_profile(
            _self_consistent_openai_bytes(
                fixed_parameters={
                    "schema_version": 1,
                    "max_output_tokens": 8192,
                    "temperature": {"kind": "ABSENT"},
                    "top_p": {"kind": "ABSENT"},
                    "seed": {"kind": "PRESENT", "value": extreme_seed},
                    "response_format": "JSON_OBJECT",
                }
            )
        )
        assert isinstance(extreme, OpenAILLMProfileV1)
        extreme_seed_value = extreme.fixed_parameters.seed
        assert isinstance(extreme_seed_value, PresentIntegerParameterV1)
        assert extreme_seed_value.value == extreme_seed
    # The lower bounds of every fixed parameter also accept.
    lower_bound = load_llm_profile(
        _self_consistent_openai_bytes(
            fixed_parameters={
                "schema_version": 1,
                "max_output_tokens": 1,
                "temperature": {"kind": "PRESENT", "value_milli": 0},
                "top_p": {"kind": "PRESENT", "value_milli": 0},
                "seed": {"kind": "ABSENT"},
                "response_format": "JSON_OBJECT",
            }
        )
    )
    assert isinstance(lower_bound, OpenAILLMProfileV1)
    lower_temperature = lower_bound.fixed_parameters.temperature
    assert isinstance(lower_temperature, PresentTemperatureMilliV1)
    assert lower_temperature.value_milli == 0
    lower_top_p = lower_bound.fixed_parameters.top_p
    assert isinstance(lower_top_p, PresentTopPMilliV1)
    assert lower_top_p.value_milli == 0
    assert lower_bound.fixed_parameters.max_output_tokens == 1
    # Frozen records reject every mutation attempt deterministically.
    with pytest.raises(ValidationError):
        setattr(mock, "adapter_version", "2")
    with pytest.raises(ValidationError):
        setattr(openai, "model", "other-model")
    # The closed union discriminant is stable and rejects unknown modes.
    assert isinstance(mock, MockLLMProfileV1)
    assert isinstance(openai, OpenAILLMProfileV1)
    assert not isinstance(mock, OpenAILLMProfileV1)
    assert not isinstance(openai, MockLLMProfileV1)
