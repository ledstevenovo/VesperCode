"""T30.2 legacy step 30.C: Demo executor and tool-port isolation tests.

The exact displayed RED test ``test_demo_executor_exposes_only_simulated_tool_ports``
is copied from the T30.2 card (the final assert line is 97 characters and
ruff-wrapped with unchanged semantics per the T17.1/T24.1 precedent-class
comment).  The already-RED matrix test ``test_demo_executor_isolation_matrix``
pins the PLAN 30.C row: fixed tool results, closed capabilities,
prohibited-prefix scans, and zero formal-capability construction/calls.
The demo executor owns only deterministic simulated tool-port adaptation
for Task 30.A data; shared-core sequencing, stopping, session limits, Web
routes, disk, external services, and formal capability adapters remain out
of scope (GREEN-4 boundary).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Final, cast

import pytest

pytest.importorskip("pydantic")

from src.vespercode.candidate.patch_engine import (
    ApplyCandidatePatchAction,
    CandidatePatchOutcomeV1,
)
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.contracts.optional import AbsentV1
from src.vespercode.credentials.service import CredentialService
from src.vespercode.demo.executor import (
    PROHIBITED_DEMO_MODULE_PREFIXES_V1,
    BoundActionV1,
    DemoCapabilityErrorV1,
    DemoExecutor,
    DemoToolResultV1,
)
from src.vespercode.demo.scenario import FIXED_DEMO_SCENARIO_V1
from src.vespercode.execution.docker_executor import DockerExecutor
from src.vespercode.llm.mock_adapter import MockLLMAdapter
from src.vespercode.llm.openai_adapter import OpenAILLMAdapter
from src.vespercode.loop.action_binding import (
    bind_action,
    reset_issued_action_ids,
)
from src.vespercode.loop.agent_actions import (
    RunCheckActionV1,
)
from src.vespercode.storage.run_repository import RunRepository
from src.vespercode.tools.dispatcher import RunCheckOutcomeV1
from src.vespercode.tools.file_actions import ReadFileActionV1

_FIXED_DIGEST: Final = "ab" * 32


class _SequenceIdGenerator:
    """One deterministic Harness action-id generator for the tests."""

    def __init__(self) -> None:
        self._counter = 0

    def next_id(self) -> str:
        self._counter += 1
        return f"test-demo-action-{self._counter}"


_SEQUENCE_ID_GENERATOR = _SequenceIdGenerator()


def _bound(action: Any) -> BoundActionV1:
    # One shared generator: ids keep increasing across tests, so the
    # per-process duplicate guard never fires and each binding is unique.
    return bind_action(action, _SEQUENCE_ID_GENERATOR)


@pytest.fixture
def demo_executor() -> DemoExecutor:
    return DemoExecutor()


@pytest.fixture(autouse=True)
def _reset_binding_state() -> None:
    reset_issued_action_ids()


def test_demo_executor_exposes_only_simulated_tool_ports(
    demo_executor: DemoExecutor,
) -> None:
    # The card's displayed final assert is 99 characters; ruff-wrapped with
    # the same semantics per the T17.1/T24.1 precedent-class comment.
    assert demo_executor.tool_ports().capability_kinds == {
        "DEMO_READ",
        "DEMO_PATCH",
        "DEMO_CHECK",
    }
    assert demo_executor.formal_capability_calls == 0


class _FormalAdapterProbes:
    """Count every construction of a formal capability adapter.

    The demo must never construct or call local files, formal Run/turn
    repositories, SQLite repositories, Docker, credentials, recovery,
    persistence, or real provider adapters (GREEN-2); the counting
    wrappers replace each adapter's constructor so any attempt is
    recorded and never silent.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for cls in _FORMAL_ADAPTER_PROBES:
            name = cls.__name__

            def _counting_init(
                self: object,
                *args: Any,
                _probes: _FormalAdapterProbes = self,
                _name: str = name,
                **kwargs: Any,
            ) -> None:
                _probes.calls.append(_name)

            monkeypatch.setattr(cls, "__init__", _counting_init)


_FORMAL_ADAPTER_PROBES: Final = (
    RunRepository,
    CredentialService,
    MockLLMAdapter,
    OpenAILLMAdapter,
    DockerExecutor,
)
"""The closed formal-capability adapter probe set (GREEN-2)."""


@pytest.fixture
def formal_adapter_probes(
    monkeypatch: pytest.MonkeyPatch,
) -> _FormalAdapterProbes:
    probes = _FormalAdapterProbes()
    probes.install(monkeypatch)
    return probes


def _demo_import_surface() -> list[str]:
    """Every absolute module name imported by the Demo package itself.

    The scan reads the demo package's own import statements (``import
    X`` / ``from X import Y``) — the import surface the card's
    prohibited-prefix guard covers; transitive imports of the shared
    pure core are production modules, not the Demo's own surface.
    """
    demo_root = Path(__file__).resolve().parents[2] / "src" / "vespercode" / "demo"
    imports: list[str] = []
    for module_path in sorted(demo_root.glob("*.py")):
        if module_path.name == "__init__.py":
            continue
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imports.append(node.module)
    return imports


def _prohibited_import_hits(imports: list[str]) -> list[str]:
    """The imports of the Demo package that hit a prohibited prefix."""
    hits: list[str] = []
    for module in imports:
        if not module.startswith("src."):
            continue
        candidate = module[len("src.") :]
        for prefix in PROHIBITED_DEMO_MODULE_PREFIXES_V1:
            if candidate == prefix or candidate.startswith(prefix + "."):
                hits.append(module)
    return hits


def test_demo_executor_isolation_matrix(
    demo_executor: DemoExecutor,
    formal_adapter_probes: _FormalAdapterProbes,
) -> None:
    """PLAN 30.C row: fixed tool results, closed capabilities,
    prohibited-prefix scans, and zero formal-capability construction/calls
    pass.
    """
    # Closed capabilities: the three simulated kinds only.
    ports = demo_executor.tool_ports()
    assert ports.capability_kinds == {"DEMO_READ", "DEMO_PATCH", "DEMO_CHECK"}
    # The three non-Demo ports stay unregistered (the shared dispatcher
    # fails closed with UNKNOWN_CAPABILITY and zero port calls).
    assert ports.list_files is None
    assert ports.search_text is None
    assert ports.propose_completion is None

    # Prohibited-prefix scan: the demo package's own import surface
    # contains no formal capability adapter module.  The surface must be
    # non-empty first, so a vacuous scan (wrong root, empty glob) can
    # never pass as a green check.
    surface = _demo_import_surface()
    assert surface
    assert _prohibited_import_hits(surface) == []

    # Fixed action/result mappings over Task 30.A fixed values.
    read_result = demo_executor.execute(
        _bound(
            ReadFileActionV1(
                schema_version=1,
                action_type="read_file",
                path=CanonicalRelativePathV1("README.md"),
                start_line=1,
                line_count=10,
                max_bytes=1024,
            )
        )
    )
    assert read_result.capability_kind == "DEMO_READ"
    assert read_result.status == "SUCCEEDED"
    assert read_result.fixed_result == FIXED_DEMO_SCENARIO_V1.source
    assert read_result.error_code is None

    patch_result = demo_executor.execute(
        _bound(
            ApplyCandidatePatchAction(
                schema_version=1,
                action_type="apply_candidate_patch",
                base_candidate_digest=_FIXED_DIGEST,
                patch_format="UNIFIED_DIFF_V1",
                patch_text=FIXED_DEMO_SCENARIO_V1.expected_patch,
            )
        )
    )
    assert patch_result.capability_kind == "DEMO_PATCH"
    assert patch_result.status == "SUCCEEDED"
    assert patch_result.fixed_result == FIXED_DEMO_SCENARIO_V1.expected_patch

    check_result = demo_executor.execute(
        _bound(
            RunCheckActionV1(
                schema_version=1,
                action_type="run_check",
                check_plan_id="FULL_PYTEST",
            )
        )
    )
    assert check_result.capability_kind == "DEMO_CHECK"
    assert check_result.status == "FAILED"
    assert check_result.error_code == "CHECK_FAILED"
    assert check_result.fixed_result == FIXED_DEMO_SCENARIO_V1.injected_failure

    # Deterministic: a second executor over the same fixed values produces
    # the identical closed results (canonical bytes).
    second = DemoExecutor()
    assert (
        second.execute(
            _bound(
                ReadFileActionV1(
                    schema_version=1,
                    action_type="read_file",
                    path=CanonicalRelativePathV1("README.md"),
                    start_line=1,
                    line_count=10,
                    max_bytes=1024,
                )
            )
        ).to_canonical_bytes()
        == read_result.to_canonical_bytes()
    )
    assert second.formal_capability_calls == 0

    # Zero formal-capability construction/calls after exercising the full
    # simulated surface.
    assert formal_adapter_probes.calls == []
    assert demo_executor.formal_capability_calls == 0


def test_demo_ports_return_fixed_tool_results(demo_executor: DemoExecutor) -> None:
    """The three registered ports return the exact fixed values over the
    Task 30.A scenario (closed action/result mappings, no ambient input)."""
    ports = demo_executor.tool_ports()
    assert ports.read_file is not None
    assert ports.apply_candidate_patch is not None
    assert ports.run_check is not None

    read_action = ReadFileActionV1(
        schema_version=1,
        action_type="read_file",
        path=CanonicalRelativePathV1("README.md"),
        start_line=1,
        line_count=10,
        max_bytes=1024,
    )
    from src.vespercode.tools.file_results import ReadFileSuccessV1

    read = ports.read_file(cast(Any, None), read_action)
    assert isinstance(read, ReadFileSuccessV1)
    assert read.text == FIXED_DEMO_SCENARIO_V1.source
    assert read.eof is True

    patch = ports.apply_candidate_patch(
        ApplyCandidatePatchAction(
            schema_version=1,
            action_type="apply_candidate_patch",
            base_candidate_digest=_FIXED_DIGEST,
            patch_format="UNIFIED_DIFF_V1",
            patch_text=FIXED_DEMO_SCENARIO_V1.expected_patch,
        )
    )
    assert isinstance(patch, CandidatePatchOutcomeV1)
    assert patch.kind == "PUBLISHED"
    assert patch.revision is not None
    assert patch.revision.revision_id == "root:demo-revision-v1"

    check = ports.run_check(
        RunCheckActionV1(
            schema_version=1,
            action_type="run_check",
            check_plan_id="FULL_PYTEST",
        )
    )
    assert isinstance(check, RunCheckOutcomeV1)
    assert check.kind == "COMPLETED"
    assert check.error_code is None


def test_demo_executor_rejects_unregistered_capabilities(
    demo_executor: DemoExecutor,
) -> None:
    """list/search/propose are not Demo capabilities: the closed executor
    rejects them and the shared dispatcher would fail closed with zero
    calls (the ports stay unregistered)."""
    from src.vespercode.loop.agent_actions import ProposeCompletionActionV1
    from src.vespercode.tools.file_actions import ListFilesActionV1

    for action in (
        ListFilesActionV1(
            schema_version=1,
            action_type="list_files",
            root=cast(Any, {"kind": "ROOT"}),
            recursive=False,
            max_entries=10,
            cursor=AbsentV1(kind="ABSENT"),
        ),
        ProposeCompletionActionV1(
            schema_version=1,
            action_type="propose_completion",
            candidate_digest=_FIXED_DIGEST,
            rationale_summary="demo completion",
        ),
    ):
        with pytest.raises(DemoCapabilityErrorV1):
            demo_executor.execute(_bound(action))


def test_demo_tool_result_envelope_is_closed_and_deterministic() -> None:
    """The closed DemoToolResultV1 envelope: extra fields and contradictory
    SUCCEEDED-with-error shapes reject; the fixed values serialize to one
    canonical form."""
    from pydantic import ValidationError

    fixed = DemoToolResultV1(
        schema_version=1,
        capability_kind="DEMO_READ",
        status="SUCCEEDED",
        result_type="ReadFileResult",
        fixed_result=FIXED_DEMO_SCENARIO_V1.source,
        error_code=None,
    )
    assert (
        fixed.to_canonical_bytes()
        == DemoToolResultV1(
            schema_version=1,
            capability_kind="DEMO_READ",
            status="SUCCEEDED",
            result_type="ReadFileResult",
            fixed_result=FIXED_DEMO_SCENARIO_V1.source,
            error_code=None,
        ).to_canonical_bytes()
    )
    with pytest.raises(ValidationError):
        DemoToolResultV1(
            schema_version=1,
            capability_kind="DEMO_READ",
            status="FAILED",
            result_type="ReadFileResult",
            fixed_result=FIXED_DEMO_SCENARIO_V1.source,
            error_code=None,
        )
    with pytest.raises(ValidationError):
        DemoToolResultV1.model_validate({**fixed.model_dump(), "forbidden": "extra"})
