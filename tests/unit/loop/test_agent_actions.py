"""T17.1 legacy step 17.A: closed model-action vocabulary tests.

Pins the closed SPEC §4.2.2 schemas owned by 17.A: ``RunCheckActionV1``
and ``ProposeCompletionActionV1`` reject unknown fields and require every
field with no parser defaults; the ``AgentAction`` union is closed to the
six registered model actions; ``ActionInstanceV1`` binds the Harness id,
semantic digest, and instance digest to the action value; ``ParseErrorV1``
is one stable closed error.  Parsing, identity generation, policy, and
dispatch are tested by their owning modules.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vespercode.canonical.digest import domain_digest
from vespercode.loop.agent_actions import (
    ActionInstanceV1,
    AgentAction,
    ParseErrorV1,
    ProposeCompletionActionV1,
    RunCheckActionV1,
    _validate_agent_action,
)

_DIGEST = "1" * 64


def test_run_check_action_is_closed() -> None:
    action = RunCheckActionV1(
        schema_version=1, action_type="run_check", check_plan_id="FULL_PYTEST"
    )
    assert action.check_plan_id == "FULL_PYTEST"
    # Unknown fields are rejected.
    with pytest.raises(ValidationError):
        RunCheckActionV1.model_validate(
            {
                "schema_version": 1,
                "action_type": "run_check",
                "check_plan_id": "TARGET_TESTS",
                "executable": "/bin/sh",
            }
        )
    # A missing field is not defaulted.
    with pytest.raises(ValidationError):
        RunCheckActionV1.model_validate(
            {"schema_version": 1, "action_type": "run_check"}
        )
    # An unknown check plan is rejected.
    with pytest.raises(ValidationError):
        RunCheckActionV1.model_validate(
            {"schema_version": 1, "action_type": "run_check", "check_plan_id": "ALL"}
        )
    # The action carries no command text (SPEC §4.2.2).
    assert set(RunCheckActionV1.model_fields) == {
        "schema_version",
        "action_type",
        "check_plan_id",
    }


def test_propose_completion_action_is_closed() -> None:
    action = ProposeCompletionActionV1(
        schema_version=1,
        action_type="propose_completion",
        candidate_digest=_DIGEST,
        rationale_summary="done",
    )
    assert action.candidate_digest == _DIGEST
    with pytest.raises(ValidationError):
        ProposeCompletionActionV1.model_validate(
            {
                "schema_version": 1,
                "action_type": "propose_completion",
                "candidate_digest": _DIGEST,
            }
        )
    # The candidate digest must be a 64-hex identity.
    with pytest.raises(ValidationError):
        ProposeCompletionActionV1.model_validate(
            {
                "schema_version": 1,
                "action_type": "propose_completion",
                "candidate_digest": "not-a-digest",
                "rationale_summary": "done",
            }
        )
    # The rationale is bounded at 2048 UTF-8 bytes.
    with pytest.raises(ValidationError):
        ProposeCompletionActionV1.model_validate(
            {
                "schema_version": 1,
                "action_type": "propose_completion",
                "candidate_digest": _DIGEST,
                "rationale_summary": "x" * 2049,
            }
        )
    # Unknown fields are rejected.
    with pytest.raises(ValidationError):
        ProposeCompletionActionV1.model_validate(
            {
                "schema_version": 1,
                "action_type": "propose_completion",
                "candidate_digest": _DIGEST,
                "rationale_summary": "done",
                "success": True,
            }
        )


def test_agent_action_union_is_closed_to_six_types() -> None:
    from vespercode.candidate.patch_engine import ApplyCandidatePatchAction
    from vespercode.canonical.path_v1 import CanonicalRelativePathV1
    from vespercode.contracts.location import RootLocationV1
    from vespercode.contracts.optional import AbsentV1
    from vespercode.tools.file_actions import (
        ListFilesActionV1,
        ReadFileActionV1,
        SearchTextActionV1,
    )

    members: list[AgentAction] = [
        ListFilesActionV1(
            schema_version=1,
            action_type="list_files",
            root=RootLocationV1(kind="ROOT"),
            recursive=False,
            max_entries=10,
            cursor=AbsentV1(kind="ABSENT"),
        ),
        ReadFileActionV1(
            schema_version=1,
            action_type="read_file",
            path=CanonicalRelativePathV1("src/a.py"),
            start_line=1,
            line_count=10,
            max_bytes=1024,
        ),
        SearchTextActionV1(
            schema_version=1,
            action_type="search_text",
            query="def",
            roots=(RootLocationV1(kind="ROOT"),),
            case_sensitive=False,
            context_lines=0,
            max_results=5,
            cursor=AbsentV1(kind="ABSENT"),
        ),
        ApplyCandidatePatchAction(
            schema_version=1,
            action_type="apply_candidate_patch",
            base_candidate_digest=_DIGEST,
            patch_format="UNIFIED_DIFF_V1",
            patch_text="--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@\n-x\n+x\n",
        ),
        RunCheckActionV1(
            schema_version=1, action_type="run_check", check_plan_id="RUFF"
        ),
        ProposeCompletionActionV1(
            schema_version=1,
            action_type="propose_completion",
            candidate_digest=_DIGEST,
            rationale_summary="done",
        ),
    ]
    for member in members:
        parsed = _validate_agent_action(member.model_dump())
        assert parsed.action_type == member.action_type


def test_action_instance_binds_identity() -> None:
    from vespercode.contracts.location import RootLocationV1
    from vespercode.contracts.optional import AbsentV1
    from vespercode.tools.file_actions import ListFilesActionV1

    action = ListFilesActionV1(
        schema_version=1,
        action_type="list_files",
        root=RootLocationV1(kind="ROOT"),
        recursive=False,
        max_entries=10,
        cursor=AbsentV1(kind="ABSENT"),
    )
    semantic = "0" * 64
    instance = ActionInstanceV1(
        schema_version=1,
        action_id="harness-1",
        semantic_digest=semantic,
        instance_digest=domain_digest(
            "ActionInstanceDigestV1",
            1,
            {
                "schema_version": 1,
                "action_id": "harness-1",
                "semantic_digest": semantic,
            },
        ),
        action=action,
    )
    assert instance.action.action_type == "list_files"
    # A forged instance digest is rejected.
    with pytest.raises(ValidationError):
        ActionInstanceV1.model_validate(
            {
                "schema_version": 1,
                "action_id": "harness-1",
                "semantic_digest": semantic,
                "instance_digest": "9" * 64,
                "action": action,
            }
        )
    # An empty or oversized Harness id is rejected.
    with pytest.raises(ValidationError):
        ActionInstanceV1.model_validate(
            {
                "schema_version": 1,
                "action_id": "",
                "semantic_digest": semantic,
                "instance_digest": domain_digest(
                    "ActionInstanceDigestV1",
                    1,
                    {
                        "schema_version": 1,
                        "action_id": "",
                        "semantic_digest": semantic,
                    },
                ),
                "action": action,
            }
        )
    with pytest.raises(ValidationError):
        ActionInstanceV1.model_validate(
            {
                "schema_version": 1,
                "action_id": "x" * 129,
                "semantic_digest": semantic,
                "instance_digest": domain_digest(
                    "ActionInstanceDigestV1",
                    1,
                    {
                        "schema_version": 1,
                        "action_id": "x" * 129,
                        "semantic_digest": semantic,
                    },
                ),
                "action": action,
            }
        )
    # The action value cannot carry a model-supplied id through this
    # envelope either: the closed union rejects the extra key.
    with pytest.raises(ValidationError):
        ActionInstanceV1.model_validate(
            {
                "schema_version": 1,
                "action_id": "harness-1",
                "semantic_digest": semantic,
                "instance_digest": domain_digest(
                    "ActionInstanceDigestV1",
                    1,
                    {
                        "schema_version": 1,
                        "action_id": "harness-1",
                        "semantic_digest": semantic,
                    },
                ),
                "action": {
                    "schema_version": 1,
                    "action_type": "list_files",
                    "action_id": "model-1",
                    "root": {"kind": "ROOT"},
                    "recursive": False,
                    "max_entries": 10,
                    "cursor": {"kind": "ABSENT"},
                },
            }
        )


def test_parse_error_is_closed_stable_error() -> None:
    error = ParseErrorV1(
        schema_version=1, error_code="UNKNOWN_FIELD", bounded_message="denied"
    )
    assert error.error_code == "UNKNOWN_FIELD"
    assert error.bounded_message == "denied"
    with pytest.raises(ValidationError):
        ParseErrorV1.model_validate(
            {"schema_version": 1, "error_code": "SOME_CODE", "bounded_message": "x"}
        )
    with pytest.raises(ValidationError):
        ParseErrorV1.model_validate(
            {"schema_version": 1, "error_code": "UNKNOWN_FIELD"}
        )
