"""T17.1 legacy step 17.B: Harness-owned action identity binding tests.

Pins the identity contract of SPEC §4.2.2/§0.1: ``bind_action`` binds one
parsed action to a Harness-generated non-empty id plus the canonical
semantic digest (the exact ``AgentAction`` including the cursor) and the
instance digest (the ``ActionInstanceDigestV1`` binding of
``{schema_version, action_id, semantic_digest}``); empty, duplicate, or
malformed generator ids and any model-supplied identity are rejected.
The exact card RED test
(``test_same_semantics_different_harness_ids_change_instance_digest``) is
preserved verbatim.
"""

from __future__ import annotations

import pytest

from src.vespercode.canonical.digest import domain_digest
from src.vespercode.contracts.location import RootLocationV1
from src.vespercode.contracts.optional import AbsentV1
from src.vespercode.loop.action_binding import (
    ActionBindingErrorV1,
    ActionIdGeneratorV1,
    bind_action,
    reset_issued_action_ids,
)
from src.vespercode.loop.agent_actions import AgentAction, RunCheckActionV1
from src.vespercode.tools.file_actions import ListFilesActionV1

_DIGEST = "1" * 64


def action() -> AgentAction:
    """One exact closed list-files action used across binding tests."""
    return ListFilesActionV1(
        schema_version=1,
        action_type="list_files",
        root=RootLocationV1(kind="ROOT"),
        recursive=False,
        max_entries=10,
        cursor=AbsentV1(kind="ABSENT"),
    )


def fixed_ids(action_id: str) -> ActionIdGeneratorV1:
    """A deterministic generator that always yields *action_id*."""

    class _FixedIds:
        def next_id(self) -> str:
            return action_id

    return _FixedIds()


@pytest.fixture(autouse=True)
def _reset_binding_state() -> None:
    """Duplicate-rejection state is per process; reset for determinism."""
    reset_issued_action_ids()


def test_same_semantics_different_harness_ids_change_instance_digest() -> None:
    left = bind_action(action(), fixed_ids("a1"))
    right = bind_action(action(), fixed_ids("a2"))
    assert left.semantic_digest == right.semantic_digest
    assert left.instance_digest != right.instance_digest


def test_bind_action_generates_non_empty_harness_id_and_digests() -> None:
    instance = bind_action(action(), fixed_ids("action-1"))
    assert instance.action_id == "action-1"
    assert instance.semantic_digest != ""
    assert instance.instance_digest != ""
    assert instance.action.action_type == "list_files"
    # The instance digest binds {schema_version, action_id, semantic_digest}.
    assert instance.instance_digest == domain_digest(
        "ActionInstanceDigestV1",
        1,
        {
            "schema_version": 1,
            "action_id": instance.action_id,
            "semantic_digest": instance.semantic_digest,
        },
    )


def test_action_binding_identity_matrix() -> None:
    """Registry 17.B: Harness assigns canonical ids; same semantics plus
    different Harness ids changes instance digest but not semantic digest;
    invalid/duplicate ids and model-supplied ids are rejected.

    Model-supplied ids cannot reach ``bind_action`` (its input is an
    already-parsed, id-free ``AgentAction``): the 17.A parser rejects
    them with ``UNKNOWN_FIELD`` and the closed ``ActionInstanceV1``
    envelope rejects an action carrying ``action_id`` (test_agent_actions
    ``test_action_instance_binds_identity``), so this matrix covers the
    binder-reachable rows only.
    """

    # --- Same semantics, different Harness ids: semantic digest stable. ---
    left = bind_action(action(), fixed_ids("b1"))
    right = bind_action(action(), fixed_ids("b2"))
    assert left.semantic_digest == right.semantic_digest
    assert left.instance_digest != right.instance_digest
    assert left.action_id != right.action_id

    # --- Semantic digest is exact: any action field change alters it. ---
    changed = ListFilesActionV1(
        schema_version=1,
        action_type="list_files",
        root=RootLocationV1(kind="ROOT"),
        recursive=True,
        max_entries=10,
        cursor=AbsentV1(kind="ABSENT"),
    )
    assert bind_action(changed, fixed_ids("b3")).semantic_digest != left.semantic_digest

    # --- Different action types never share a semantic digest. ---
    check = RunCheckActionV1(
        schema_version=1, action_type="run_check", check_plan_id="TARGET_TESTS"
    )
    assert bind_action(check, fixed_ids("b4")).semantic_digest != left.semantic_digest

    # --- Empty generator ids are rejected. ---
    with pytest.raises(ActionBindingErrorV1):
        bind_action(action(), fixed_ids(""))

    # --- Malformed (oversized) generator ids are rejected. ---
    with pytest.raises(ActionBindingErrorV1):
        bind_action(action(), fixed_ids("x" * 129))

    # --- Duplicate generator ids are rejected on the second bind. ---
    first = bind_action(action(), fixed_ids("dup-1"))
    assert first.action_id == "dup-1"
    with pytest.raises(ActionBindingErrorV1):
        bind_action(action(), fixed_ids("dup-1"))
