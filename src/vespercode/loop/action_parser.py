"""T17.1 legacy step 17.A: the strict single-action model response parser.

``ActionParser.parse`` consumes one closed ``ModelResponse`` and returns
either the closed ``AgentAction`` union or one stable ``ParseErrorV1``
(SPEC §4.2.2/§4.2.5): the total input must be exactly one JSON object —
JSON whitespace around it is allowed, but malformed JSON, non-object
values, multiple objects, and trailing non-whitespace bytes are rejected
as framing violations; the object is then validated against the closed
union whose every variant rejects unknown fields and requires every field,
so defaults, omissions, wrong types, cross-variant fields, and unknown
action types all fail with the stable code; and any model-supplied
Harness action identity (``action_id``) is rejected before schema
validation with ``UNKNOWN_FIELD`` (GREEN-2/GREEN-3).  Parsing has no side
effects: no identity generation, no policy/phase evaluation, no dispatch
(GREEN-4).
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from vespercode.canonical.path_v1 import (
    CanonicalPathErrorV1,
    CanonicalRelativePathV1,
)
from vespercode.llm.base import ModelResponse
from vespercode.loop.agent_actions import (
    AgentAction,
    ParseErrorCodeV1,
    ParseErrorV1,
    _validate_agent_action,
)

_MAX_BOUNDED_MESSAGE_BYTES = 256


def _coerce_paths(value: dict[str, Any]) -> dict[str, Any]:
    """Map every JSON string path/root/cursor position into the canonical
    path dataclass the closed action schemas require.

    The model response carries repository paths as plain JSON strings; the
    T11.1 file-action schemas store them as ``CanonicalRelativePathV1``
    instances, so the parser performs the one lexical canonicalization
    before union validation.  A rejected path form raises
    ``CanonicalPathErrorV1`` (a ``ValueError``), which the caller converts
    into ``FIELD_INVALID``.
    """

    def _path(value: Any) -> CanonicalRelativePathV1:
        if not isinstance(value, str):
            raise ValueError("canonical path must be a JSON string")
        return CanonicalRelativePathV1(value)

    action_type = value.get("action_type")
    if action_type == "read_file" and isinstance(value.get("path"), str):
        value["path"] = _path(value["path"])
    elif action_type == "list_files":
        root = value.get("root")
        if isinstance(root, dict) and root.get("kind") == "PATH":
            root["path"] = _path(root["path"])
    elif action_type == "search_text":
        roots = value.get("roots")
        if isinstance(roots, list):
            for root in roots:
                if isinstance(root, dict) and root.get("kind") == "PATH":
                    root["path"] = _path(root["path"])
    cursor = value.get("cursor")
    if isinstance(cursor, dict) and cursor.get("kind") == "PRESENT":
        cursor_value = cursor.get("value")
        if isinstance(cursor_value, dict) and isinstance(
            cursor_value.get("next_canonical_path"), str
        ):
            cursor_value["next_canonical_path"] = _path(
                cursor_value["next_canonical_path"]
            )
    return value


def _parse_error(code: ParseErrorCodeV1, detail: str) -> ParseErrorV1:
    """One stable parse error with a bounded, non-empty message."""
    message = f"model response is not a valid single action: {detail}"
    return ParseErrorV1(
        schema_version=1,
        error_code=code,
        bounded_message=message[:_MAX_BOUNDED_MESSAGE_BYTES],
    )


def _classify_validation_error(error: ValidationError) -> ParseErrorCodeV1:
    """Map one closed-schema validation error to the stable parse code."""
    for item in error.errors():
        kind = item.get("type")
        if kind == "extra_forbidden":
            return "UNKNOWN_FIELD"
        if kind == "missing":
            return "MISSING_FIELD"
        if kind == "union_tag_not_found":
            return "MISSING_FIELD"
        if kind == "union_tag_invalid":
            return "UNKNOWN_ACTION_TYPE"
    return "FIELD_INVALID"


class ActionParser:
    """One strict, side-effect-free parser over closed model responses."""

    def parse(self, response: ModelResponse) -> AgentAction | ParseErrorV1:
        """Parse exactly one closed model action object, or fail stably.

        The total input must be exactly one JSON object: JSON whitespace
        around it is permitted, but malformed JSON, a non-object value,
        multiple objects, and trailing non-whitespace bytes are framing
        violations (``NOT_JSON_OBJECT``).  A model-supplied Harness action
        identity is rejected with ``UNKNOWN_FIELD`` before schema
        validation; unknown fields, omissions, defaults, wrong types, and
        unknown action types return their stable codes.
        """
        try:
            value = json.JSONDecoder().decode(response.text)
        except json.JSONDecodeError:
            return _parse_error(
                "NOT_JSON_OBJECT",
                "the response is not exactly one JSON value (malformed JSON, "
                "multiple objects, or trailing content)",
            )
        if not isinstance(value, dict):
            return _parse_error(
                "NOT_JSON_OBJECT", "the response JSON value must be one object"
            )
        if "action_id" in value:
            return _parse_error(
                "UNKNOWN_FIELD",
                "the model must not supply a Harness action identity",
            )
        try:
            _coerce_paths(value)
        except (CanonicalPathErrorV1, ValueError):
            return _parse_error(
                "FIELD_INVALID", "the action object carries an invalid canonical path"
            )
        try:
            return _validate_agent_action(value)
        except ValidationError as error:
            code = _classify_validation_error(error)
            detail = "the action object violates the closed schema"
            if code == "UNKNOWN_FIELD":
                detail = "the action object carries an unknown field"
            elif code == "MISSING_FIELD":
                detail = "the action object omits a required field"
            elif code == "UNKNOWN_ACTION_TYPE":
                detail = "the action object declares an unknown action type"
            return _parse_error(code, detail)
