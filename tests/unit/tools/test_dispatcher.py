"""T17.1 legacy step 17.C: ordered guarded tool dispatcher behavior tests.

Pins the dispatcher's guarded ordering, exact port selection, pure-result
conversion, bounded artifact publication, and exception envelopes: every
gate failure returns a stable failure with zero port calls, an exact
allowed current action invokes exactly one registered port once, file-tool
results publish through the artifact store into ``payload_ref``, patch /
check / completion outcomes convert by their closed kinds, and a tool
exception or an invalid result is a typed failure — never success.
"""

from __future__ import annotations

from typing import Any, Callable

import pytest
from pydantic import ValidationError

from src.vespercode.candidate.patch_engine import (
    ApplyCandidatePatchAction,
    CandidatePatchOutcomeV1,
)
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.contracts.evidence import ArtifactRefV1, DigestV1
from src.vespercode.contracts.location import RootLocationV1
from src.vespercode.contracts.optional import AbsentV1
from src.vespercode.contracts.run import RunPhase
from src.vespercode.governance.policy import PatchPathFactV1, PolicyEngine
from src.vespercode.loop.action_binding import (
    ActionIdGeneratorV1,
    bind_action,
    reset_issued_action_ids,
)
from src.vespercode.loop.agent_actions import (
    ProposeCompletionActionV1,
    RunCheckActionV1,
)
from src.vespercode.tools.dispatcher import (
    ActionResultV1,
    CompletionOutcomeV1,
    DispatchContextV1,
    DispatchErrorV1,
    RunCheckOutcomeV1,
    ToolDispatcher,
    publish_file_tool_outcome,
)
from src.vespercode.tools.file_actions import (
    ListFilesActionV1,
    ReadFileActionV1,
)
from src.vespercode.tools.file_results import (
    FileToolErrorV1,
    ListFilesSuccessV1,
    SearchTextSuccessV1,
)
from src.vespercode.trees.readable import ReadableTreeV1

_DIGEST = "1" * 64


def fixed_ids(action_id: str) -> ActionIdGeneratorV1:
    """A deterministic generator that always yields *action_id*."""

    class _FixedIds:
        def next_id(self) -> str:
            return action_id

    return _FixedIds()


def empty_tree() -> ReadableTreeV1:
    """The minimal protocol-only visible tree: empty, digest ``_DIGEST``."""

    class _EmptyTree:
        digest = _DIGEST

        def list_directories(self) -> tuple[Any, ...]:
            return ()

        def list_file_paths(self) -> tuple[Any, ...]:
            return ()

        def read_bytes(self, path: Any) -> bytes:
            raise KeyError(path)

    return _EmptyTree()


def list_action(max_entries: int = 10) -> ListFilesActionV1:
    return ListFilesActionV1(
        schema_version=1,
        action_type="list_files",
        root=RootLocationV1(kind="ROOT"),
        recursive=False,
        max_entries=max_entries,
        cursor=AbsentV1(kind="ABSENT"),
    )


def read_action(path: str = "src/a.py") -> ReadFileActionV1:
    return ReadFileActionV1(
        schema_version=1,
        action_type="read_file",
        path=CanonicalRelativePathV1(path),
        start_line=1,
        line_count=10,
        max_bytes=1024,
    )


def patch_action(base_candidate_digest: str = _DIGEST) -> ApplyCandidatePatchAction:
    return ApplyCandidatePatchAction(
        schema_version=1,
        action_type="apply_candidate_patch",
        base_candidate_digest=base_candidate_digest,
        patch_format="UNIFIED_DIFF_V1",
        patch_text="--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@\n-x\n+x\n",
    )


class SpyToolPorts:
    """A counting ports registry with replaceable per-port behavior."""

    list_files: Callable[..., Any] | None
    read_file: Callable[..., Any] | None
    search_text: Callable[..., Any] | None
    apply_candidate_patch: Callable[..., Any] | None
    run_check: Callable[..., Any] | None
    propose_completion: Callable[..., Any] | None

    def __init__(self) -> None:
        self.total_calls = 0
        self.calls: dict[str, int] = {}
        self.behavior: dict[str, Callable[..., Any]] = {
            "list_files": lambda tree, action: ListFilesSuccessV1(
                kind="SUCCESS",
                entries=(),
                truncated=False,
                next_cursor=AbsentV1(kind="ABSENT"),
            ),
            "read_file": lambda tree, action: FileToolErrorV1(
                kind="ERROR",
                error_code="FILE_NOT_FOUND",
                bounded_message="no such file",
            ),
            "search_text": lambda tree, action: FileToolErrorV1(
                kind="ERROR",
                error_code="FILE_NOT_FOUND",
                bounded_message="spy default",
            ),
            "apply_candidate_patch": lambda action: CandidatePatchOutcomeV1(
                kind="REJECTED",
                error_code="PATCH_CONTEXT_MISMATCH",
                reason="hunk mismatch",
            ),
            "run_check": lambda action: RunCheckOutcomeV1(kind="COMPLETED"),
            "propose_completion": lambda action: CompletionOutcomeV1(
                kind="VALIDATION_REQUESTED"
            ),
        }
        for name in self.behavior:
            self.register(name, self.behavior[name])

    def register(self, name: str, port: Callable[..., Any]) -> None:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            self.total_calls += 1
            self.calls[name] = self.calls.get(name, 0) + 1
            return port(*args, **kwargs)

        setattr(self, name, wrapped)


class SpyArtifactStore:
    """One artifact-store spy recording ``put`` calls."""

    def __init__(self) -> None:
        self.put_calls = 0
        self.raise_on_put = False

    def put(self, payload: Any) -> ArtifactRefV1:
        self.put_calls += 1
        if self.raise_on_put:
            raise RuntimeError("store failure")
        return ArtifactRefV1(artifact_id="artifact-1", digest=DigestV1(value="0" * 64))


@pytest.fixture(autouse=True)
def _reset_binding_state() -> None:
    reset_issued_action_ids()


@pytest.fixture
def dispatcher() -> ToolDispatcher:
    return ToolDispatcher()


@pytest.fixture
def ports() -> SpyToolPorts:
    return SpyToolPorts()


@pytest.fixture
def store() -> SpyArtifactStore:
    return SpyArtifactStore()


def context(
    ports: SpyToolPorts,
    store: SpyArtifactStore,
    *,
    run_phase: RunPhase = "AGENT_LOOP",
    current_candidate_digest: str | None = _DIGEST,
    patch_path_fact: PatchPathFactV1 | None = "OK",
) -> DispatchContextV1:
    return DispatchContextV1(
        run_phase=run_phase,
        current_candidate_digest=current_candidate_digest,
        final_diff_digest=_DIGEST,
        editable_policy_digest="3" * 64,
        reference_profile_digest="2" * 64,
        patch_path_fact=patch_path_fact,
        visible_tree=empty_tree(),
        ports=ports,
        artifact_store=store,
        policy_engine=PolicyEngine(),
    )


def test_dispatch_allowed_list_invokes_one_port_once_and_publishes(
    dispatcher: ToolDispatcher,
    ports: SpyToolPorts,
    store: SpyArtifactStore,
) -> None:
    instance = bind_action(list_action(), fixed_ids("d-1"))
    result = dispatcher.dispatch(instance, context(ports, store))
    assert result.status == "SUCCEEDED"
    assert result.result_type == "ListFilesResult"
    assert result.payload_ref.kind == "PRESENT"
    assert result.payload_ref.value.artifact_id == "artifact-1"
    assert result.error.kind == "ABSENT"
    assert result.action_id == "d-1"
    assert result.semantic_digest == instance.semantic_digest
    assert result.instance_digest == instance.instance_digest
    assert ports.total_calls == 1
    assert ports.calls == {"list_files": 1}
    assert store.put_calls == 1


def test_dispatch_file_tool_error_is_typed_failure_with_tool_code(
    dispatcher: ToolDispatcher,
    ports: SpyToolPorts,
    store: SpyArtifactStore,
) -> None:
    result = dispatcher.dispatch(
        bind_action(read_action(), fixed_ids("d-2")), context(ports, store)
    )
    assert result.status == "FAILED"
    assert result.error.code == "FILE_NOT_FOUND"
    assert result.payload_ref.kind == "ABSENT"
    assert store.put_calls == 0


def test_dispatch_patch_outcome_conversion(
    dispatcher: ToolDispatcher,
    ports: SpyToolPorts,
    store: SpyArtifactStore,
) -> None:
    rejected = dispatcher.dispatch(
        bind_action(patch_action(), fixed_ids("d-3")), context(ports, store)
    )
    assert rejected.status == "FAILED"
    assert rejected.result_type == "ApplyCandidatePatchResult"
    assert rejected.error.code == "PATCH_CONTEXT_MISMATCH"
    assert rejected.payload_ref.kind == "ABSENT"

    ports.register(
        "apply_candidate_patch",
        lambda action: CandidatePatchOutcomeV1(
            kind="REJECTED",
            error_code="PATCH_PATH_NOT_EDITABLE",
            reason="not editable",
        ),
    )
    again = dispatcher.dispatch(
        bind_action(patch_action(), fixed_ids("d-4")), context(ports, store)
    )
    assert again.status == "FAILED"
    assert again.error.code == "PATCH_PATH_NOT_EDITABLE"


def test_dispatch_run_check_outcome_conversion(
    dispatcher: ToolDispatcher,
    ports: SpyToolPorts,
    store: SpyArtifactStore,
) -> None:
    instance = bind_action(
        RunCheckActionV1(
            schema_version=1, action_type="run_check", check_plan_id="RUFF"
        ),
        fixed_ids("d-5"),
    )
    ok = dispatcher.dispatch(instance, context(ports, store))
    assert ok.status == "SUCCEEDED"
    assert ok.result_type == "RunCheckResult"

    ports.register(
        "run_check",
        lambda action: RunCheckOutcomeV1(
            kind="REJECTED", error_code="UNKNOWN_CAPABILITY", bounded_message="no"
        ),
    )
    rejected = dispatcher.dispatch(instance, context(ports, store))
    assert rejected.status == "FAILED"
    assert rejected.error.code == "UNKNOWN_CAPABILITY"


def test_dispatch_completion_outcome_conversion(
    dispatcher: ToolDispatcher,
    ports: SpyToolPorts,
    store: SpyArtifactStore,
) -> None:
    instance = bind_action(
        ProposeCompletionActionV1(
            schema_version=1,
            action_type="propose_completion",
            candidate_digest=_DIGEST,
            rationale_summary="done",
        ),
        fixed_ids("d-6"),
    )
    ok = dispatcher.dispatch(instance, context(ports, store))
    assert ok.status == "SUCCEEDED"
    assert ok.result_type == "ProposeCompletionResult"
    # A stale completion candidate never invokes the port.
    stale = dispatcher.dispatch(
        bind_action(
            ProposeCompletionActionV1(
                schema_version=1,
                action_type="propose_completion",
                candidate_digest="9" * 64,
                rationale_summary="done",
            ),
            fixed_ids("d-7"),
        ),
        context(ports, store),
    )
    assert stale.error.code == "STALE_CANDIDATE"
    assert ports.total_calls == 1


def test_dispatch_tool_exception_is_typed_failure(
    dispatcher: ToolDispatcher,
    ports: SpyToolPorts,
    store: SpyArtifactStore,
) -> None:
    def exploding(tree: Any, action: Any) -> Any:
        raise RuntimeError("boom")

    ports.register("read_file", exploding)
    result = dispatcher.dispatch(
        bind_action(read_action(), fixed_ids("d-8")), context(ports, store)
    )
    assert result.status == "FAILED"
    assert result.error.code == "TOOL_EXCEPTION"
    assert result.error.bounded_message is not None
    assert "RuntimeError" in result.error.bounded_message


def test_dispatch_invalid_result_is_typed_failure(
    dispatcher: ToolDispatcher,
    ports: SpyToolPorts,
    store: SpyArtifactStore,
) -> None:
    ports.register("read_file", lambda tree, action: object())
    result = dispatcher.dispatch(
        bind_action(read_action(), fixed_ids("d-9")), context(ports, store)
    )
    assert result.status == "FAILED"
    assert result.error.code == "INVALID_RESULT"
    assert result.error.kind == "PRESENT"


def test_dispatch_mismatched_result_family_is_invalid(
    dispatcher: ToolDispatcher,
    ports: SpyToolPorts,
    store: SpyArtifactStore,
) -> None:
    # A list_files port returning a search success payload is not a valid
    # list result: it must fail closed without publishing anything.
    ports.register(
        "list_files",
        lambda tree, action: SearchTextSuccessV1(
            kind="SUCCESS",
            matches=(),
            truncated=False,
            next_cursor=AbsentV1(kind="ABSENT"),
            skipped_non_text_count=0,
        ),
    )
    result = dispatcher.dispatch(
        bind_action(list_action(), fixed_ids("d-9b")), context(ports, store)
    )
    assert result.status == "FAILED"
    assert result.error.code == "INVALID_RESULT"
    assert result.payload_ref.kind == "ABSENT"
    assert store.put_calls == 0


def test_dispatch_artifact_publication_failure_is_typed(
    dispatcher: ToolDispatcher,
    ports: SpyToolPorts,
    store: SpyArtifactStore,
) -> None:
    store.raise_on_put = True
    result = dispatcher.dispatch(
        bind_action(list_action(), fixed_ids("d-10")), context(ports, store)
    )
    assert result.status == "FAILED"
    assert result.error.code == "ARTIFACT_PUBLICATION_FAILED"
    assert result.payload_ref.kind == "ABSENT"
    assert store.put_calls == 1


def test_dispatch_policy_deny_message_carries_reason(
    dispatcher: ToolDispatcher,
    ports: SpyToolPorts,
    store: SpyArtifactStore,
) -> None:
    result = dispatcher.dispatch(
        bind_action(patch_action(), fixed_ids("d-11")),
        context(ports, store, patch_path_fact="PATCH_PATH_NOT_EDITABLE"),
    )
    assert result.error.code == "POLICY_DENY"
    assert result.error.bounded_message is not None
    assert "PATCH_PATH_NOT_EDITABLE" in result.error.bounded_message
    assert ports.total_calls == 0


def test_dispatch_stale_candidate_and_phase_are_rejected(
    dispatcher: ToolDispatcher,
    ports: SpyToolPorts,
    store: SpyArtifactStore,
) -> None:
    stale = dispatcher.dispatch(
        bind_action(patch_action(base_candidate_digest="9" * 64), fixed_ids("d-12")),
        context(ports, store),
    )
    assert stale.error.code == "STALE_CANDIDATE"
    assert ports.total_calls == 0

    phase = dispatcher.dispatch(
        bind_action(list_action(), fixed_ids("d-13")),
        context(ports, store, run_phase="BASELINE"),
    )
    assert phase.error.code == "ACTION_NOT_ALLOWED_IN_PHASE"
    assert ports.total_calls == 0


def test_dispatch_sensitive_path_is_rejected_before_any_call(
    dispatcher: ToolDispatcher,
    ports: SpyToolPorts,
    store: SpyArtifactStore,
) -> None:
    result = dispatcher.dispatch(
        bind_action(read_action(".env"), fixed_ids("d-14")), context(ports, store)
    )
    assert result.error.code == "SENSITIVE_PATH"
    assert ports.total_calls == 0


def test_publish_file_tool_outcome_binds_instance_and_result() -> None:
    instance = bind_action(list_action(), fixed_ids("d-15"))
    payload = ListFilesSuccessV1(
        kind="SUCCESS",
        entries=(),
        truncated=False,
        next_cursor=AbsentV1(kind="ABSENT"),
    )
    outcome = publish_file_tool_outcome(instance, payload, SpyArtifactStore())
    assert outcome.kind == "PUBLISHED"
    assert outcome.action_id == "d-15"
    assert outcome.instance_digest == instance.instance_digest
    assert outcome.artifact_ref is not None

    failing = SpyArtifactStore()
    failing.raise_on_put = True
    rejected = publish_file_tool_outcome(instance, payload, failing)
    assert rejected.kind == "REJECTED"
    assert rejected.error_code == "ARTIFACT_PUBLICATION_FAILED"
    assert rejected.bounded_message != ""


def test_action_result_envelope_is_closed() -> None:
    instance = bind_action(list_action(), fixed_ids("d-16"))
    base = {
        "schema_version": 1,
        "action_id": instance.action_id,
        "semantic_digest": instance.semantic_digest,
        "instance_digest": instance.instance_digest,
        "result_type": "ListFilesResult",
        "payload_ref": {"kind": "ABSENT"},
    }
    # SUCCEEDED cannot carry error data.
    with pytest.raises(ValidationError):
        ActionResultV1.model_validate(
            {
                **base,
                "status": "SUCCEEDED",
                "error": {
                    "kind": "PRESENT",
                    "code": "POLICY_DENY",
                    "bounded_message": "no",
                },
            }
        )
    # FAILED/REJECTED must carry error data.
    with pytest.raises(ValidationError):
        ActionResultV1.model_validate(
            {**base, "status": "FAILED", "error": {"kind": "ABSENT"}}
        )
    # A forged instance digest is rejected.
    with pytest.raises(ValidationError):
        ActionResultV1.model_validate(
            {
                **base,
                "instance_digest": "9" * 64,
                "status": "FAILED",
                "error": {
                    "kind": "PRESENT",
                    "code": "POLICY_DENY",
                    "bounded_message": "no",
                },
            }
        )
    # The closed optional error enforces its exact shape.
    with pytest.raises(ValidationError):
        DispatchErrorV1.model_validate(
            {"kind": "PRESENT", "code": "", "bounded_message": "x"}
        )
    with pytest.raises(ValidationError):
        DispatchErrorV1.model_validate(
            {"kind": "ABSENT", "code": "POLICY_DENY", "bounded_message": None}
        )
