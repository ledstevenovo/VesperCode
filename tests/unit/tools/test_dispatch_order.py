"""T17.1 legacy step 17.C: ordered guarded tool dispatcher order tests.

Pins the deterministic pre-dispatch ordering of SPEC §4.2.5 behavior 4 and
the card GREEN-1/GREEN-2 contract: current-candidate binding, path/object
authorization, Run phase, and Task 13 policy gates run in that exact order
before one registered typed tool port is selected; every gate failure
returns a stable failure with zero port calls; only an exact allowed
current action invokes one port exactly once; a tool exception becomes a
typed failure and is never swallowed or reported as success.  The exact
card RED test (``test_hard_deny_never_invokes_tool_port``) is preserved
verbatim.
"""

from __future__ import annotations

from typing import Any, Callable

import pytest

from vespercode.candidate.patch_engine import ApplyCandidatePatchAction
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.evidence import ArtifactRefV1, DigestV1
from vespercode.contracts.location import RootLocationV1
from vespercode.contracts.optional import AbsentV1
from vespercode.contracts.run import RunPhase
from vespercode.governance.policy import PatchPathFactV1, PolicyEngine
from vespercode.loop.action_binding import (
    ActionIdGeneratorV1,
    bind_action,
    reset_issued_action_ids,
)
from vespercode.loop.agent_actions import (
    ActionInstanceV1,
    ProposeCompletionActionV1,
    RunCheckActionV1,
)
from vespercode.tools.dispatcher import (
    DispatchContextV1,
    ToolDispatcher,
)
from vespercode.tools.file_actions import (
    ListFilesActionV1,
    ReadFileActionV1,
)
from vespercode.tools.file_results import (
    ListFilesResultV1,
    ListFilesSuccessV1,
    SearchTextSuccessV1,
)
from vespercode.trees.readable import ReadableTreeV1

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


class SpyToolPorts:
    """A counting ports registry: every registered port increments
    ``total_calls`` and records its per-port call count."""

    list_files: Callable[..., Any] | None
    read_file: Callable[..., Any] | None
    search_text: Callable[..., Any] | None
    apply_candidate_patch: Callable[..., Any] | None
    run_check: Callable[..., Any] | None
    propose_completion: Callable[..., Any] | None

    def __init__(self) -> None:
        self.total_calls = 0
        self.calls: dict[str, int] = {}
        self.register("list_files", self._list_files_port)
        self.register("read_file", self._read_file_port)
        self.register("search_text", self._search_text_port)
        self.register("apply_candidate_patch", self._patch_port)
        self.register("run_check", self._run_check_port)
        self.register("propose_completion", self._completion_port)

    def register(self, name: str, port: Callable[..., Any]) -> None:
        """Install *port* under *name* wrapped with the call counter."""

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            self.total_calls += 1
            self.calls[name] = self.calls.get(name, 0) + 1
            return port(*args, **kwargs)

        setattr(self, name, wrapped)

    def _list_files_port(
        self, tree: ReadableTreeV1, action: ListFilesActionV1
    ) -> ListFilesResultV1:
        return ListFilesSuccessV1(
            kind="SUCCESS",
            entries=(),
            truncated=False,
            next_cursor=AbsentV1(kind="ABSENT"),
        )

    def _read_file_port(self, tree: ReadableTreeV1, action: Any) -> Any:
        raise AssertionError("spy default port must not be reached")

    def _search_text_port(self, tree: ReadableTreeV1, action: Any) -> Any:
        raise AssertionError("spy default port must not be reached")

    def _patch_port(self, action: ApplyCandidatePatchAction) -> Any:
        raise AssertionError("spy default port must not be reached")

    def _run_check_port(self, action: Any) -> Any:
        raise AssertionError("spy default port must not be reached")

    def _completion_port(self, action: Any) -> Any:
        raise AssertionError("spy default port must not be reached")


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


def _context(
    ports: SpyToolPorts,
    *,
    store: SpyArtifactStore | None = None,
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
        artifact_store=store if store is not None else SpyArtifactStore(),
        policy_engine=PolicyEngine(),
    )


def _patch_action(base_candidate_digest: str = _DIGEST) -> ApplyCandidatePatchAction:
    return ApplyCandidatePatchAction(
        schema_version=1,
        action_type="apply_candidate_patch",
        base_candidate_digest=base_candidate_digest,
        patch_format="UNIFIED_DIFF_V1",
        patch_text="--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@\n-x\n+x\n",
    )


def denied_instance() -> ActionInstanceV1:
    """One bound apply-candidate-patch action whose pre-policy patch-path
    fact makes the Task 13 policy evaluate DENY (every earlier gate
    passes)."""
    return bind_action(_patch_action(), fixed_ids("deny-1"))


def denied_context(ports: SpyToolPorts) -> DispatchContextV1:
    """The frozen dispatch facts for the DENY trace."""
    return _context(ports, patch_path_fact="PATCH_PATH_NOT_EDITABLE")


@pytest.fixture(autouse=True)
def _reset_binding_state() -> None:
    """Duplicate-rejection state is per process; reset for determinism."""
    reset_issued_action_ids()


@pytest.fixture
def ports() -> SpyToolPorts:
    return SpyToolPorts()


@pytest.fixture
def dispatcher() -> ToolDispatcher:
    return ToolDispatcher()


def test_hard_deny_never_invokes_tool_port(
    dispatcher: ToolDispatcher, ports: SpyToolPorts
) -> None:
    result = dispatcher.dispatch(denied_instance(), denied_context(ports))
    assert result.error.code == "POLICY_DENY"
    assert ports.total_calls == 0


def test_dispatch_order_exception_matrix(
    dispatcher: ToolDispatcher, ports: SpyToolPorts
) -> None:
    """Registry 17.C: parse precedes policy and dispatch; DENY never calls
    tool; ALLOW calls one tool once; tool exception becomes typed feedback;
    no exception is swallowed or reported as success."""

    # --- Stale candidate binding fails before phase/policy: zero calls. ---
    stale = dispatcher.dispatch(
        bind_action(
            _patch_action(base_candidate_digest="9" * 64), fixed_ids("stale-1")
        ),
        _context(ports),
    )
    assert stale.error.code == "STALE_CANDIDATE"
    assert stale.status == "REJECTED"
    assert ports.total_calls == 0

    # --- Path/object authorization fails before phase/policy: zero calls. ---
    read_sensitive = bind_action(
        _read_action("src/.env"),
        fixed_ids("path-1"),
    )
    sensitive = dispatcher.dispatch(read_sensitive, _context(ports))
    assert sensitive.error.code == "SENSITIVE_PATH"
    assert sensitive.status == "REJECTED"
    assert ports.total_calls == 0

    # --- Forbidden phase fails before policy: zero calls. ---
    check = dispatcher.dispatch(
        bind_action(
            RunCheckActionV1(
                schema_version=1, action_type="run_check", check_plan_id="RUFF"
            ),
            fixed_ids("phase-1"),
        ),
        _context(ports, run_phase="FORMAL_VALIDATION"),
    )
    assert check.error.code == "ACTION_NOT_ALLOWED_IN_PHASE"
    assert check.status == "REJECTED"
    assert ports.total_calls == 0

    # --- Hard DENY (Task 13 policy) never invokes any port. ---
    denied = dispatcher.dispatch(denied_instance(), denied_context(ports))
    assert denied.error.code == "POLICY_DENY"
    assert denied.status == "REJECTED"
    assert ports.total_calls == 0

    # --- An ALLOWed exact current action invokes exactly one port once. ---
    allowed = dispatcher.dispatch(
        bind_action(_list_action(), fixed_ids("allow-1")),
        _context(ports),
    )
    assert allowed.status == "SUCCEEDED"
    assert allowed.result_type == "ListFilesResult"
    assert allowed.payload_ref.kind == "PRESENT"
    assert ports.total_calls == 1
    assert ports.calls == {"list_files": 1}

    # --- A tool exception becomes a typed failure, never success. ---
    ports.register("apply_candidate_patch", _raising_port())
    raised = dispatcher.dispatch(
        bind_action(_patch_action(), fixed_ids("exc-1")),
        _context(ports),
    )
    assert raised.status == "FAILED"
    assert raised.error.code == "TOOL_EXCEPTION"
    assert raised.error.bounded_message != ""
    assert ports.total_calls == 2

    # --- An unregistered capability fails closed with zero calls. ---
    ports.propose_completion = None
    unknown = dispatcher.dispatch(
        bind_action(_completion_action(), fixed_ids("cap-1")),
        _context(ports),
    )
    assert unknown.error.code == "UNKNOWN_CAPABILITY"
    assert unknown.status == "REJECTED"
    assert ports.total_calls == 2

    # --- An invalid port result is never reported as success. ---
    ports.register("read_file", _invalid_result_port())
    invalid = dispatcher.dispatch(
        bind_action(_read_action("src/a.py"), fixed_ids("bad-1")),
        _context(ports),
    )
    assert invalid.status == "FAILED"
    assert invalid.error.code == "INVALID_RESULT"
    assert ports.total_calls == 3

    # --- A non-file port returning a file success payload is an invalid
    # result with zero publication, never a raw error and never success. ---
    ports.register(
        "apply_candidate_patch",
        lambda action: SearchTextSuccessV1(
            kind="SUCCESS",
            matches=(),
            truncated=False,
            next_cursor=AbsentV1(kind="ABSENT"),
            skipped_non_text_count=0,
        ),
    )
    mismatched = dispatcher.dispatch(
        bind_action(_patch_action(), fixed_ids("bad-2")),
        _context(ports),
    )
    assert mismatched.status == "FAILED"
    assert mismatched.error.code == "INVALID_RESULT"
    assert ports.total_calls == 4


def _list_action() -> ListFilesActionV1:
    return ListFilesActionV1(
        schema_version=1,
        action_type="list_files",
        root=RootLocationV1(kind="ROOT"),
        recursive=False,
        max_entries=10,
        cursor=AbsentV1(kind="ABSENT"),
    )


def _read_action(path: str) -> ReadFileActionV1:
    return ReadFileActionV1(
        schema_version=1,
        action_type="read_file",
        path=CanonicalRelativePathV1(path),
        start_line=1,
        line_count=10,
        max_bytes=1024,
    )


def _completion_action() -> ProposeCompletionActionV1:
    return ProposeCompletionActionV1(
        schema_version=1,
        action_type="propose_completion",
        candidate_digest=_DIGEST,
        rationale_summary="done",
    )


def _raising_port() -> Callable[..., Any]:
    def port(action: Any) -> Any:
        raise RuntimeError("boom")

    return port


def _invalid_result_port() -> Callable[..., Any]:
    def port(tree: Any, action: Any) -> Any:
        return object()

    return port
