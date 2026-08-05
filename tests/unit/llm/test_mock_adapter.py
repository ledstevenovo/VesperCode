"""T16.1 legacy step 16.A: deterministic Mock adapter behavior tests.

Pins the byte-identical offline output (the same frozen script identity
and request digest always select the same bytes), the frozen
``MockScriptV1`` identity binding (``3be1c216…94da``), the unknown-script
rejection, and the GREEN-4 import boundary (no OpenAI transport,
credential, disclosure ledger, or network client can be imported by the
Mock adapter).  Provider transport, credentials, Grant/authorization
access, request charging, and network clients remain out of scope
(GREEN-4).
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Literal

import pytest

# The Mock adapter consumes pydantic runtime contracts; the hash-locked
# gate toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from src.vespercode.llm.base import ModelResponse
from src.vespercode.llm.mock_adapter import MockLLMAdapter, MockScriptMismatchError
from src.vespercode.llm.prepared_request import (
    MockPreparedModelRequestV1,
    prepare_mock_request,
)
from src.vespercode.profiles.llm import (
    MockLLMProfileV1,
    load_llm_profile,
)
from src.vespercode.governance.request_sources import (
    RequestContentSegmentV1,
    RequestMessageV1,
)
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.contracts.optional import AbsentV1, PresentV1

_MOCK_BUILTIN = (
    Path(__file__).resolve().parents[3]
    / "src/vespercode/profiles/builtin/mock-deterministic-v1.json"
)


def mock_profile() -> MockLLMProfileV1:
    """The frozen packaged built-in Mock profile (digest-verified)."""
    loaded = load_llm_profile(_MOCK_BUILTIN.read_bytes())
    assert isinstance(loaded, MockLLMProfileV1)
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


def test_mock_generate_is_byte_identical_offline() -> None:
    request = prepare_mock_request(mock_profile(), _messages())
    adapter = MockLLMAdapter()
    first: ModelResponse = adapter.generate(request)
    second: ModelResponse = adapter.generate(request)
    assert first.text == second.text
    assert first.text_digest == second.text_digest
    assert first.byte_count == second.byte_count
    # The response digest is the plain SHA-256 of the exact text bytes.
    assert first.text_digest == hashlib.sha256(first.text.encode("utf-8")).hexdigest()
    assert first.byte_count == len(first.text.encode("utf-8"))
    # A different request digest (different messages) still selects the
    # same built-in byte-identical response: selection is a pure function
    # of the frozen script identity and the request digest.
    other = prepare_mock_request(
        mock_profile(),
        (
            RequestMessageV1(
                role="SYSTEM",
                segments=(
                    _segment("HARNESS_PROTOCOL", "A different protocol header."),
                ),
            ),
            RequestMessageV1(
                role="USER",
                segments=(_segment("TASK", "A different instruction."),),
            ),
        ),
    )
    assert other.digest != request.digest
    third = adapter.generate(other)
    assert third.text == first.text
    assert third.text_digest == first.text_digest


def test_mock_generate_binds_frozen_script_identity() -> None:
    request = prepare_mock_request(mock_profile(), _messages())
    assert request.script_id == "mock-deterministic-response-v1"
    assert request.script_digest == (
        "3be1c2165c5cf2e4d271a489809e1a7c443fcf452b66bb9a743022ee4f0894da"
    )
    response = MockLLMAdapter().generate(request)
    assert isinstance(response, ModelResponse)


def test_mock_generate_rejects_unknown_script_identity() -> None:
    profile = mock_profile()
    foreign = MockPreparedModelRequestV1.model_validate(_foreign_request_dict(profile))
    with pytest.raises(MockScriptMismatchError):
        MockLLMAdapter().generate(foreign)


def _foreign_request_dict(profile: MockLLMProfileV1) -> dict[str, object]:
    """One digest-consistent request bound to a foreign script identity."""
    from src.vespercode.canonical.digest import domain_digest
    from src.vespercode.canonical.json_v1 import CanonicalValueV1, canonical_json_bytes

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
    payload: dict[str, CanonicalValueV1] = {
        "schema_version": 1,
        "script_id": "other-script-v1",
        "script_digest": "f" * 64,
        "messages": canonical_messages,
    }
    canonical_byte_count = len(canonical_json_bytes(payload))
    digest = domain_digest(
        "MockPreparedModelRequestV1",
        1,
        {
            "schema_version": 1,
            "mode": "MOCK",
            "llm_profile_digest": profile.digest,
            "script_id": "other-script-v1",
            "script_digest": "f" * 64,
            "messages": canonical_messages,
            "canonical_byte_count": canonical_byte_count,
        },
    )
    return {
        "schema_version": 1,
        "mode": "MOCK",
        "llm_profile_digest": profile.digest,
        "script_id": "other-script-v1",
        "script_digest": "f" * 64,
        "messages": messages,
        "canonical_byte_count": canonical_byte_count,
        "digest": digest,
    }


def test_mock_adapter_imports_no_real_capability_modules() -> None:
    """GREEN-4: no transport/credential/ledger/network import surface."""
    source_path = (
        Path(__file__).resolve().parents[3] / "src/vespercode/llm/mock_adapter.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.update(alias.name.split("."))
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                imported.update(node.module.split("."))
    forbidden = {
        "httpx",
        "requests",
        "openai",
        "credentials",
        "governance",
        "storage",
        "docker",
    }
    assert not (imported & forbidden), (
        f"Mock adapter must not import real capabilities, found {imported & forbidden}"
    )
