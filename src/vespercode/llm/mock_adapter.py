"""T16.1 legacy step 16.A: the deterministic script-bound Mock adapter.

``MockLLMAdapter.generate`` accepts exactly the ``MOCK`` variant and
selects its output as a pure function of the frozen script identity and
the request digest only (no other input is ever consulted): the built-in
``MockScriptV1`` resource (identity ``3be1c216…94da`` over
``{schema_version: 1, profile_id: "mock-deterministic-v1", script_id:
"mock-deterministic-response-v1"}``, the T06.3-frozen digest) maps every
request to one byte-identical closed action envelope, so identical
requests produce identical responses with zero provider, credential,
Grant, authorization, or network behavior.
Any other script identity rejects with ``MockScriptMismatchError`` before
any output exists.  The scripted multi-turn scenario construction (which
request digests the loop feeds per turn) belongs to the successor loop
tasks; this adapter owns only the closed deterministic selection.
"""

from __future__ import annotations

import hashlib
from typing import Final

from vespercode.llm.base import ModelResponse
from vespercode.llm.prepared_request import MockPreparedModelRequestV1

# The frozen built-in Mock script resource (T06.3 packaged identity):
# script_digest is the §0.1 MockScriptV1 identity over the exact
# {schema_version: 1, profile_id: "mock-deterministic-v1", script_id}.
_BUILTIN_SCRIPT_ID: Final = "mock-deterministic-response-v1"
_BUILTIN_SCRIPT_DIGEST: Final = (
    "3be1c2165c5cf2e4d271a489809e1a7c443fcf452b66bb9a743022ee4f0894da"
)

# The built-in script's byte-identical response: the canonical JSON of the
# minimal valid closed action envelope (a ``list_files`` action at the
# repository root, no cursor) that the successor parser can accept.  The
# response identity (``text_digest``/``byte_count``) binds these exact
# bytes, so every response is byte-stable offline.
_MOCK_RESPONSE_TEXT: Final = (
    '{"schema_version":1,"action_type":"list_files","root":{"kind":"ROOT"},'
    '"recursive":false,"max_entries":1,"cursor":{"kind":"ABSENT"}}'
)


class MockScriptMismatchError(ValueError):
    """Closed rejection: the request script identity is not the built-in."""

    def __init__(self, script_id: str) -> None:
        super().__init__(f"unknown Mock script identity {script_id!r}")
        self.script_id = script_id


class MockLLMAdapter:
    """The deterministic offline Mock adapter (SPEC §4.2.1, AC-05).

    ``generate`` verifies the frozen script identity against the built-in
    resource, then returns the byte-identical closed response.  The
    adapter imports no OpenAI transport, credential, disclosure ledger, or
    network client (GREEN-4 boundary).
    """

    def generate(self, request: MockPreparedModelRequestV1) -> ModelResponse:
        """Return the byte-identical script response for *request*.

        Only the frozen script identity (and the request digest bound by
        the request's own validated §0.1 identity) selects the output; no
        credential, Grant, authorization, or network behavior ever occurs.
        """
        if (
            request.script_id != _BUILTIN_SCRIPT_ID
            or request.script_digest != _BUILTIN_SCRIPT_DIGEST
        ):
            raise MockScriptMismatchError(request.script_id)
        raw = _MOCK_RESPONSE_TEXT.encode("utf-8")
        return ModelResponse(
            schema_version=1,
            text=_MOCK_RESPONSE_TEXT,
            text_digest=hashlib.sha256(raw).hexdigest(),
            byte_count=len(raw),
        )
