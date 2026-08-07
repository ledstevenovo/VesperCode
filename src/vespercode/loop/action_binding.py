"""T17.1 legacy step 17.B: Harness-owned action identity binding.

``bind_action`` binds one parsed closed ``AgentAction`` to a
Harness-generated non-empty id (SPEC §4.2.2): the semantic digest is the
§0.1 ``ActionSemanticDigestV1`` identity of the exact canonical action
including the cursor, computed from action semantics only; the instance
digest is the ``ActionInstanceDigestV1`` binding of ``{schema_version,
action_id, semantic_digest}`` using the T05.1 contracts rule, so a Harness
id change never alters the semantic digest (GREEN-1/GREEN-2).  Empty,
malformed (non-UTF-8 or over 128 bytes), and duplicate ids are rejected
with the typed ``ActionBindingErrorV1``; model-supplied identity was
already rejected by the parser.  Response parsing, List/Search cursors,
candidate/phase/policy evaluation, dispatch, and model-supplied identity
remain out of scope (GREEN-4).
"""

from __future__ import annotations

from typing import Protocol

from vespercode.canonical.digest import domain_digest
from vespercode.canonical.json_v1 import CanonicalValueV1
from vespercode.contracts.action import _instance_digest_for, _require_action_id
from vespercode.candidate.patch_engine import ApplyCandidatePatchAction
from vespercode.loop.agent_actions import (
    ActionInstanceV1,
    AgentAction,
    ProposeCompletionActionV1,
    RunCheckActionV1,
)
from vespercode.tools.file_actions import (
    ListFilesActionV1,
    ReadFileActionV1,
    SearchTextActionV1,
    _canonical_location,
)
from vespercode.tools.file_results import (
    ListFilesCursorV1,
    SearchTextCursorV1,
)


class ActionIdGeneratorV1(Protocol):
    """SPEC §4.2.2: the injectable Harness-owned action id generator.

    ``next_id`` returns one non-empty UTF-8 string of at most 128 bytes;
    the concrete generator is responsible for producing a fresh id per
    call so the same script reproduces the same instance sequence.
    """

    def next_id(self) -> str: ...


class ActionBindingErrorV1(ValueError):
    """Closed rejection for an empty, duplicate, or malformed Harness id."""


_issued_action_ids: set[str] = set()
"""The per-process set of already-bound Harness action ids.

``bind_action`` is the card's bare-function interface, so duplicate
rejection needs one deterministic per-process binding state; the run
boundary resets it explicitly (``reset_issued_action_ids``) so the same
script can reproduce the same instance sequence.
"""


def reset_issued_action_ids() -> None:
    """Reset the per-process bound-id set (deterministic test/run hook)."""
    _issued_action_ids.clear()


def _validate_action_id(action_id: str) -> str:
    """Reject empty, non-UTF-8, or over-128-byte Harness ids.

    The one shared lexical rule is the T05.1 contracts validator; the
    binder converts its ``ValueError`` into the typed
    ``ActionBindingErrorV1`` so callers can distinguish id rejection from
    other failures.
    """
    try:
        return _require_action_id(action_id)
    except ValueError as error:
        raise ActionBindingErrorV1(str(error)) from error


def _canonical_list_cursor(cursor: ListFilesCursorV1) -> CanonicalValueV1:
    """The full §0.1 value of one closed list cursor, including its own
    claimed digest (the semantic digest binds the exact action value)."""
    return {
        "schema_version": cursor.schema_version,
        "cursor_type": cursor.cursor_type,
        "visible_tree_digest": cursor.visible_tree_digest,
        "query_digest": cursor.query_digest,
        "next_directory_rank": cursor.next_directory_rank,
        "next_canonical_path": cursor.next_canonical_path.value,
        "digest": cursor.digest,
    }


def _canonical_search_cursor(cursor: SearchTextCursorV1) -> CanonicalValueV1:
    """The full §0.1 value of one closed search cursor."""
    return {
        "schema_version": cursor.schema_version,
        "cursor_type": cursor.cursor_type,
        "visible_tree_digest": cursor.visible_tree_digest,
        "query_digest": cursor.query_digest,
        "next_canonical_path": cursor.next_canonical_path.value,
        "next_match_index": cursor.next_match_index,
        "digest": cursor.digest,
    }


def _canonical_action(action: AgentAction) -> dict[str, CanonicalValueV1]:
    """The exact §0.1 canonical value of one closed action.

    Binds every schema field including the cursor (SPEC §4.2.2 semantic
    digest: "包含 cursor 在内的精确 AgentAction"); the cursor's own
    claimed digest is part of the exact action value the model supplied.
    """
    if isinstance(action, ListFilesActionV1):
        cursor: CanonicalValueV1 = {"kind": "ABSENT"}
        if action.cursor.kind == "PRESENT":
            cursor = {
                "kind": "PRESENT",
                "value": _canonical_list_cursor(action.cursor.value),
            }
        return {
            "schema_version": action.schema_version,
            "action_type": action.action_type,
            "root": _canonical_location(action.root),
            "recursive": action.recursive,
            "max_entries": action.max_entries,
            "cursor": cursor,
        }
    if isinstance(action, ReadFileActionV1):
        return {
            "schema_version": action.schema_version,
            "action_type": action.action_type,
            "path": action.path.value,
            "start_line": action.start_line,
            "line_count": action.line_count,
            "max_bytes": action.max_bytes,
        }
    if isinstance(action, SearchTextActionV1):
        cursor = {"kind": "ABSENT"}
        if action.cursor.kind == "PRESENT":
            cursor = {
                "kind": "PRESENT",
                "value": _canonical_search_cursor(action.cursor.value),
            }
        return {
            "schema_version": action.schema_version,
            "action_type": action.action_type,
            "query": action.query,
            "roots": tuple(_canonical_location(root) for root in action.roots),
            "case_sensitive": action.case_sensitive,
            "context_lines": action.context_lines,
            "max_results": action.max_results,
            "cursor": cursor,
        }
    if isinstance(action, ApplyCandidatePatchAction):
        return {
            "schema_version": action.schema_version,
            "action_type": action.action_type,
            "base_candidate_digest": action.base_candidate_digest,
            "patch_format": action.patch_format,
            "patch_text": action.patch_text,
        }
    if isinstance(action, RunCheckActionV1):
        return {
            "schema_version": action.schema_version,
            "action_type": action.action_type,
            "check_plan_id": action.check_plan_id,
        }
    if isinstance(action, ProposeCompletionActionV1):
        return {
            "schema_version": action.schema_version,
            "action_type": action.action_type,
            "candidate_digest": action.candidate_digest,
            "rationale_summary": action.rationale_summary,
        }
    raise TypeError(f"not a closed AgentAction: {type(action).__name__}")


def action_semantic_digest(action: AgentAction) -> str:
    """The §0.1 ``ActionSemanticDigestV1`` identity of one exact action.

    Computed from action semantics only — the exact canonical action
    bytes — never from the Harness id, so the same semantics always
    produce the same digest (GREEN-2).
    """
    return domain_digest("ActionSemanticDigestV1", 1, _canonical_action(action))


def bind_action(
    action: AgentAction, id_generator: ActionIdGeneratorV1
) -> ActionInstanceV1:
    """Bind one parsed action to a Harness-generated id and both digests.

    Rejects empty, malformed (non-UTF-8 or over 128 bytes), and duplicate
    generator ids with ``ActionBindingErrorV1``; the semantic digest is a
    pure function of the action and the instance digest binds
    ``{schema_version, action_id, semantic_digest}`` (GREEN-1/GREEN-2).
    """
    action_id = _validate_action_id(id_generator.next_id())
    if action_id in _issued_action_ids:
        raise ActionBindingErrorV1(f"Harness action id {action_id!r} was already bound")
    _issued_action_ids.add(action_id)
    semantic_digest = action_semantic_digest(action)
    instance_digest = _instance_digest_for(action_id, semantic_digest)
    return ActionInstanceV1(
        schema_version=1,
        action_id=action_id,
        action=action,
        semantic_digest=semantic_digest,
        instance_digest=instance_digest,
    )
