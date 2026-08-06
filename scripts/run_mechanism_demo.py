"""T32.1: the headless repeatable governance-and-feedback mechanism driver.

The offline mechanism driver binds the exact fixed Mock scenario to the
production pure core — the Task 25.D ``ActionPipeline`` built from the
Task 17.A/17.B parser/binder, the Task 13 ``PolicyEngine``, the Task
17.C ``ToolDispatcher``, the Task 24.A/24.C feedback builder/repository,
the Task 25.A ``StopEvaluator``, the Task 14.A/14.C final-approval
gates, the Task 11.B paged List/Search tools, and the Task 25.C
real-call orchestrator over the Task 27.A credential port — and traces
hard DENY, protected-artifact precedence, final-approval no-write,
feedback recovery, paged continuation, semantic determinism, and the
disclosure/credential real-call gates through those production
implementations (32.A/32.B/32.C GREEN-1..GREEN-4).  Every stage records
the same exhaustive zero-effect counters (dispatch, candidate publish,
approval consumption, workspace write, check invocation, formal
validation, feedback consumption) so a guardrail can never hide a side
effect, and the fixed trace serializes into the bounded text/JSON report
with a content-addressed identity.

The driver owns no alternative guardrail rule, no preselected result
outside the fixed scenario, no local/Docker capability, no credential
access, no persistence, and no real provider call: the simulated tool
ports (Task 30.C ``DemoExecutor``) and the counting transport stub are
the only adapters, and the real-call gates prove zero
authorization/count/charge/transport/network side effects on every
failing probe before the bounded report is finalized (32.C GREEN-2).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Callable, Final, Literal, cast

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pydantic import BaseModel, ConfigDict, Field, Strict  # noqa: E402

from src.vespercode.candidate.final_diff import (  # noqa: E402
    FinalDiffEntryV1,
    FinalDiffPreimageV1,
    FinalDiffV1,
)
from src.vespercode.candidate.patch_engine import (  # noqa: E402
    ApplyCandidatePatchAction,
    CandidatePatchOutcomeV1,
)
from src.vespercode.canonical.clock import FakeClockV1  # noqa: E402
from src.vespercode.canonical.digest import domain_digest  # noqa: E402
from src.vespercode.canonical.json_v1 import (  # noqa: E402
    CanonicalValueV1,
    canonical_json_bytes,
)
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1  # noqa: E402
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1  # noqa: E402
from src.vespercode.contracts.evidence import ArtifactRefV1, DigestV1  # noqa: E402
from src.vespercode.contracts.location import RootLocationV1  # noqa: E402
from src.vespercode.contracts.optional import AbsentV1, PresentV1  # noqa: E402
from src.vespercode.contracts.run import WaitContextV1, WaitDecisionV1  # noqa: E402
from src.vespercode.credentials.port import (  # noqa: E402
    CredentialBackendProbeV1,
    CredentialBackendUnsafeError,
    CredentialMissingV1,
    CredentialStoreMutationV1,
    CredentialStatusV1,
    SecretCredentialV1,
)
from src.vespercode.demo.executor import DemoExecutor  # noqa: E402
from src.vespercode.demo.scenario import FIXED_DEMO_SCENARIO_V1  # noqa: E402
from src.vespercode.demo.types import DemoScenarioV1  # noqa: E402
from src.vespercode.governance.disclosure_decision import (  # noqa: E402
    DecideDisclosureGrantV1,
    DisclosureDecisionServiceV1,
)
from src.vespercode.governance.disclosure_ledger import DisclosureLedger  # noqa: E402
from src.vespercode.governance.disclosure_scope import (  # noqa: E402
    DirectoryDisclosureScopeV1,
    DisclosureScopeSequenceV1,
    FileDisclosureScopeV1,
)
from src.vespercode.governance.disclosure_subject import (  # noqa: E402
    DisclosureGrantSubjectV1,
    DisclosureSubjectRequestV1,
    build_disclosure_subject,
)
from src.vespercode.governance.policy import PatchPathFactV1, PolicyEngine  # noqa: E402
from src.vespercode.governance.request_sources import (  # noqa: E402
    RequestContentSegmentV1,
    RequestMessageV1,
    RequestSourceCategoryV1,
    validate_segment_sources,
)
from src.vespercode.governance.writeback_approval import (  # noqa: E402
    ConsumeWritebackApprovalV1,
    WritebackApprovalRepository,
)
from src.vespercode.governance.writeback_decision import (  # noqa: E402
    DecideFinalWritebackV1,
    FinalWritebackDecisionServiceV1,
)
from src.vespercode.governance.writeback_subject import (  # noqa: E402
    FinalWritebackBindingV1,
    FinalWritebackSubjectV1,
    build_final_writeback_subject,
)
from src.vespercode.llm.base import ModelResponse  # noqa: E402
from src.vespercode.llm.openai_adapter import (  # noqa: E402
    LLMTransportResultV1,
    OpenAILLMAdapter,
)
from src.vespercode.llm.prepared_request import prepare_openai_request  # noqa: E402
from src.vespercode.loop.action_binding import (  # noqa: E402
    action_semantic_digest,
    reset_issued_action_ids,
)
from src.vespercode.loop.action_pipeline import (  # noqa: E402
    ActionPipeline,
    ActionPipelineContextV1,
    ActionRecordRepositoryV1,
    ActionStepResultV1,
)
from src.vespercode.loop.agent_actions import AgentAction, RunCheckActionV1  # noqa: E402
from src.vespercode.loop.call_orchestrator import (  # noqa: E402
    CallOnceV1,
    CallOrchestrator,
    LLMCallResultV1,
)
from src.vespercode.loop.feedback import (  # noqa: E402
    ActionFeedbackSourceV1,
    CheckFeedbackSourceV1,
    ControlFeedbackSourceV1,
    FeedbackKindV1,
    FeedbackRecordV1,
    FeedbackSeverityV1,
    FeedbackSourceV1,
    build_feedback,
    select_feedback,
)
from src.vespercode.loop.feedback_consumption import (  # noqa: E402
    FeedbackRepositoryV1,
    consume_feedback,
)
from src.vespercode.loop.progress import ProgressDecisionV1  # noqa: E402
from src.vespercode.loop.stopping import (  # noqa: E402
    LoopEvidenceV1,
    RunLoopStateV1,
    StopEvaluator,
)
from src.vespercode.loop.turn_boundary import TurnBoundary  # noqa: E402
from src.vespercode.profiles.endpoints import OpenAIEndpointV1  # noqa: E402
from src.vespercode.profiles.llm import OpenAILLMProfileV1, load_llm_profile  # noqa: E402
from src.vespercode.profiles.reference import load_reference_profile  # noqa: E402
from src.vespercode.storage.connection import ControlDatabase  # noqa: E402
from src.vespercode.storage.migration_engine import apply_migrations  # noqa: E402
from src.vespercode.storage.migrations.v0001_run_wait import RUN_WAIT_V1_MIGRATION  # noqa: E402
from src.vespercode.storage.migrations.v0002_idempotency import (  # noqa: E402
    IDEMPOTENCY_V1_MIGRATION,
)
from src.vespercode.storage.migrations.v0003_disclosure_grants import (  # noqa: E402
    DISCLOSURE_GRANTS_V1_MIGRATION,
)
from src.vespercode.storage.migrations.v0004_disclosure_authorizations import (  # noqa: E402
    DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
)
from src.vespercode.storage.migrations.v0005_memory import MEMORY_V1_MIGRATION  # noqa: E402
from src.vespercode.storage.migrations.v0006_audit import AUDIT_V1_MIGRATION  # noqa: E402
from src.vespercode.storage.migrations.v0007_agent_turns import (  # noqa: E402
    AGENT_TURNS_V1_MIGRATION,
)
from src.vespercode.storage.migrations.v0008_feedback import FEEDBACK_V1_MIGRATION  # noqa: E402
from src.vespercode.storage.migrations.v0009_actions import ACTIONS_V1_MIGRATION  # noqa: E402
from src.vespercode.storage.migrations.v0010_writeback_approvals import (  # noqa: E402
    WRITEBACK_APPROVALS_V1_MIGRATION,
)
from src.vespercode.storage.run_repository import RunRepository  # noqa: E402
from src.vespercode.tools.dispatcher import (  # noqa: E402
    RunCheckOutcomeV1,
    ToolDispatcher,
    ToolPortsV1,
)
from src.vespercode.tools.file_actions import (  # noqa: E402
    ListFilesActionV1,
    ReadFileActionV1,
    SearchTextActionV1,
)
from src.vespercode.tools.file_results import (  # noqa: E402
    FileToolErrorV1,
    ListFilesEntryV1,
    ListFilesSuccessV1,
    OptionalListFilesCursorV1,
    OptionalSearchTextCursorV1,
    ReadFileResultV1,
    SearchTextMatchV1,
    SearchTextSuccessV1,
)
from src.vespercode.tools.list_files import list_files  # noqa: E402
from src.vespercode.tools.search_text import search_text  # noqa: E402
from src.vespercode.trees.readable import ReadableTreeV1  # noqa: E402
from src.vespercode.trees.text_classifier import TextMetadataV1  # noqa: E402
from src.vespercode.validation.check_result import CheckFindingV1, CheckResultV1  # noqa: E402

_FIXED_DIGEST: Final = "ab" * 32
"""The fixed digest identity of every sealed mechanism value."""

_DRIFTED_DIGEST: Final = "cd" * 32
"""The fixed drifted digest of the stale-approval and tree-drift probes."""

_DEFAULT_CLOCK_EPOCH: Final = "2026-08-07T09:00:00.000Z"
"""The fixed clock epoch of every mechanism run (deterministic trace)."""

_DEFAULT_RUN_ID: Final = "mechanism-run-v1"
"""The fixed mechanism run identity of every offline mechanism run."""

_WRITEBACK_RUN_ID: Final = "mechanism-writeback-run-v1"
"""The fixed writeback-gate run identity (final-approval stage)."""

_REPORT_MAX_BYTES_V1: Final = 65536
"""The bounded report bound (SPEC §5.1: one model-visible body bound)."""

# The fixed stage order of one full mechanism run: the scenario's
# governance steps, then the feedback-recovery, approval, continuation,
# and real-call gate stages.
_RUN_STAGE_ORDER_V1: Final[tuple[str, ...]] = (
    "readme-read",
    "readme-modify",
    "outside-scope-create",
    "src-patch",
    "protected-tests-patch",
    "protected-config-patch",
    "feedback-correction",
    "final-approval-no-write",
    "paged-continuation",
    "real-call-gate",
)

_FIXED_PATCH_FACTS_V1: Final[dict[str, PatchPathFactV1]] = {
    "outside-scope-create": "PATCH_PATH_NOT_EDITABLE",
    "readme-modify": "PATCH_PATH_NOT_EDITABLE",
    "src-patch": "OK",
    "protected-tests-patch": "PROTECTED_ARTIFACT_CHANGED",
    "protected-config-patch": "PROTECTED_ARTIFACT_CHANGED",
}
"""The fixed pre-policy patch facts of the governance stages (SPEC §10.4
items 1, 2, 3, and 4; the demo scenario's fixed step facts)."""

_FIXED_PATCH_TEXTS_V1: Final[dict[str, str]] = {
    "outside-scope-create": (
        "--- a/docs/outside-scope.md\n"
        "+++ b/docs/outside-scope.md\n"
        "@@ -1 +1 @@\n"
        "-README.md\n"
        "+docs/outside-scope.md\n"
    ),
    "readme-modify": (
        "--- a/README.md\n"
        "+++ b/README.md\n"
        "@@ -1 +1 @@\n"
        "-VesperCode Mock Demo\n"
        "+VesperCode Demo\n"
    ),
    "src-patch": (
        "--- a/src/example.py\n"
        "+++ b/src/example.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def example():\n"
        "-    return 0\n"
        "+    return 1\n"
    ),
    "protected-tests-patch": (
        "--- a/tests/test_example.py\n"
        "+++ b/tests/test_example.py\n"
        "@@ -1 +1 @@\n"
        "-    return 0\n"
        "+    return 1\n"
    ),
    "protected-config-patch": (
        "--- a/pyproject.toml\n"
        "+++ b/pyproject.toml\n"
        "@@ -1 +1 @@\n"
        "-[tool.ruff]\n"
        "+[tool.ruff]\n"
        '+skip = ["tests"]\n'
    ),
}
"""The fixed model-action patch texts of the governance stages (the
demo script's fixed step texts; never parsed because policy DENYs the
out-of-scope steps before dispatch)."""

_CORRECTIVE_PATCH_TEXT_V1: Final = (
    "--- a/src/example.py\n"
    "+++ b/src/example.py\n"
    "@@ -1,2 +1,2 @@\n"
    " def example():\n"
    "-    return 1\n"
    "+    return 2\n"
)
"""The fixed corrective action of the feedback-recovery stage (the next
src/** patch after the injected check failure; its semantic digest
differs from the failing first action, SPEC §10.4 item 3)."""

_WRITEBACK_EXPIRES_AT: Final = CanonicalTimestampV1("2026-08-07T09:05:00.000Z")
"""The fixed subject expiry of the writeback-gate stage."""

_REAL_CREATED_AT: Final = CanonicalTimestampV1("2026-08-07T09:00:00.000Z")
_REAL_DECIDED_AT: Final = CanonicalTimestampV1("2026-08-07T09:01:00.000Z")
_REAL_RUN_DEADLINE: Final = CanonicalTimestampV1("2026-08-07T09:15:00.000Z")
_REAL_GRANT_EXPIRY: Final = CanonicalTimestampV1("2026-08-07T09:05:00.000Z")
"""The fixed real-call gate timestamps (the expired-grant probe's
subject expires 300 seconds after the epoch, so the fixed 400_000 ms
clock advance of that probe is strictly past its subject expiry)."""

_REAL_GRANT_LATE_EXPIRY: Final = CanonicalTimestampV1("2026-08-07T09:10:00.000Z")
"""The fixed subject expiry of the post-advance probes (the clock is
already 400 seconds past the epoch when they run, so their grants stay
valid and only the probed gate can fire)."""

_REAL_GRANT_ADVANCE_MILLISECONDS: Final = 400_000
"""The fixed clock advance of the expired-grant probe (SPEC §4.4.3)."""

_REAL_BUDGET_V1: Final = 100_000
"""The fixed cumulative byte budget of every seeded disclosure grant."""

_MECHANISM_MIGRATIONS_V1: Final = (
    RUN_WAIT_V1_MIGRATION,
    IDEMPOTENCY_V1_MIGRATION,
    DISCLOSURE_GRANTS_V1_MIGRATION,
    DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
    MEMORY_V1_MIGRATION,
    AUDIT_V1_MIGRATION,
    AGENT_TURNS_V1_MIGRATION,
    FEEDBACK_V1_MIGRATION,
    ACTIONS_V1_MIGRATION,
    WRITEBACK_APPROVALS_V1_MIGRATION,
)
"""The exact contiguous migration set of the in-memory wiring."""

_TEXT_METADATA: Final = TextMetadataV1(
    encoding="UTF8", newline="LF", final_newline=True
)
"""The fixed supported-text metadata of the sealed final diff."""

_OK_RESPONSE_BODY: Final = json.dumps(
    {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"schema_version":1,"action_type":"list_files",'
                        '"root":{"kind":"ROOT"},"recursive":false,'
                        '"max_entries":1,"cursor":{"kind":"ABSENT"}}'
                    )
                }
            }
        ]
    },
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
"""The fixed transport response body of the counting stub (never parsed
into an action by the mechanism driver)."""

NonNegativeIntV1 = Annotated[int, Strict(), Field(ge=0)]
"""One exact non-negative decimal integer counter (bools rejected)."""


def _reject_coerced_schema_version(value: object) -> object:
    """Reject bool/float/string spelling of the integer schema version."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("schema_version must be the decimal integer 1")
    return value


class MechanismDemoConfigV1(BaseModel):
    """One closed offline mechanism-driver configuration.

    Only frozen fixed values enter the config: the fixed scenario id,
    the fixed run identity, and the fixed clock epoch.  Nothing ambient
    or mutable can change the trace.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    scenario_id: Literal["mock-demo-v1"]
    run_id: str
    clock_epoch: str


class RealCallProbeTraceV1(BaseModel):
    """One closed real-call gate probe outcome (32.C GREEN-2).

    ``gate_error_code`` is the production stable stop code of a failing
    probe (``None`` when the gate passed); the counters prove zero
    authorization, count, charge, transport, network, or
    formal-capability side effects on every failing probe.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    probe_id: str
    gate_error_code: str | None
    authorization_record_count: NonNegativeIntV1
    turn_count: NonNegativeIntV1
    call_count: NonNegativeIntV1
    charge_bytes: NonNegativeIntV1
    transport_count: NonNegativeIntV1
    network_count: NonNegativeIntV1


class MechanismStepTraceV1(BaseModel):
    """One closed per-stage trace of the offline mechanism driver.

    Every guardrail stage records the same exhaustive zero-effect
    counters (dispatch, candidate publish, approval consumption,
    workspace write, check invocation, formal validation, feedback
    consumption) so a guardrail can never hide a side effect.  The trace
    binds no volatile field (no action id, turn id, record id, or
    timestamp), so its canonical form is its semantic form.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    step_id: str
    error_code: str | None = None
    dispatch_count: NonNegativeIntV1 = 0
    candidate_publish_count: NonNegativeIntV1 = 0
    approval_consumption_count: NonNegativeIntV1 = 0
    workspace_write_count: NonNegativeIntV1 = 0
    check_invocation_count: NonNegativeIntV1 = 0
    formal_validation_count: NonNegativeIntV1 = 0
    feedback_consumption_count: NonNegativeIntV1 = 0
    first_action_digest: str | None = None
    corrective_action_digest: str | None = None
    paged_list_equivalence: bool | None = None
    paged_search_equivalence: bool | None = None
    tamper_error_code: str | None = None
    stale_error_code: str | None = None
    real_call_probes: tuple[RealCallProbeTraceV1, ...] = ()


class MechanismDemoTraceV1(BaseModel):
    """One closed aggregate mechanism trace (bounded report stages).

    ``trace_id`` is the content-addressed identity of the exact stage
    sequence (the same value as ``digest``); the report serialization of
    the trace is bounded by ``_REPORT_MAX_BYTES_V1``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    trace_id: str
    scenario_id: str
    run_id: str
    stages: tuple[MechanismStepTraceV1, ...]
    digest: str

    def to_canonical_bytes(self) -> bytes:
        """The bounded §0.1 canonical report bytes of the trace."""
        return canonical_json_bytes(_trace_canonical_value(self))


class MechanismDemoResultV1(BaseModel):
    """One closed mechanism run result: the trace plus the bounded
    text/JSON report stages consumed by Tasks 32.B and 32.C."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    trace: MechanismDemoTraceV1
    report_text: str
    report_byte_count: NonNegativeIntV1
    report_digest: str
    semantic_digest: str


class _FixedVisibleTree:
    """The fixed sealed visible tree of the pipeline steps (empty)."""

    @property
    def digest(self) -> str:
        return _FIXED_DIGEST

    def list_directories(self) -> tuple[CanonicalRelativePathV1, ...]:
        return ()

    def list_file_paths(self) -> tuple[CanonicalRelativePathV1, ...]:
        return ()

    def read_bytes(self, path: CanonicalRelativePathV1) -> bytes:
        raise KeyError(path)


class _PagedVisibleTree:
    """One fixed sealed visible tree of the continuation stage.

    The tree exposes the exact fixed files and directories of
    ``_PAGED_TREE_A_FILES_V1`` / ``_PAGED_TREE_B_FILES_V1`` with the
    fixed digest identity, so the production paged List/Search tools
    page and the tamper/stale cursor probes bind exactly.
    """

    def __init__(self, digest: str, files: dict[str, str]) -> None:
        self._digest = digest
        self._files = files
        self._directories = tuple(
            CanonicalRelativePathV1(path)
            for path in sorted(
                {path.rsplit("/", 1)[0] for path in files if "/" in path}
            )
        )

    @property
    def digest(self) -> str:
        return self._digest

    def list_directories(self) -> tuple[CanonicalRelativePathV1, ...]:
        return self._directories

    def list_file_paths(self) -> tuple[CanonicalRelativePathV1, ...]:
        return tuple(CanonicalRelativePathV1(path) for path in sorted(self._files))

    def read_bytes(self, path: CanonicalRelativePathV1) -> bytes:
        try:
            return self._files[path.value].encode("utf-8")
        except KeyError as error:
            raise KeyError(path) from error


_PAGED_TREE_A_FILES_V1: Final = {
    "README.md": "VesperCode Mock Demo\n",
    "src/a.py": "def a():\n    return 1\n",
    "src/b.py": "def b():\n    return 2\n",
    "src/c.py": "def c():\n    return 3\n",
    "tests/test_example.py": "def test_example():\n    assert True\n",
}
"""The fixed continuation-stage tree A (five files, three matches for
the literal query ``return``)."""

_PAGED_TREE_B_FILES_V1: Final = {
    "README.md": "VesperCode Mock Demo\n",
    "src/a.py": "def a():\n    return 10\n",
    "src/b.py": "def b():\n    return 20\n",
    "src/c.py": "def c():\n    return 30\n",
    "tests/test_example.py": "def test_example():\n    assert True\n",
}
"""The fixed drifted continuation-stage tree B (different bytes, so the
digest drift of the stale probe is real)."""


class _FixedArtifactStore:
    """One fixed in-memory artifact store (file-tool payload publication
    returns the fixed sealed reference; no disk is ever touched)."""

    def put(self, payload: object) -> ArtifactRefV1:
        del payload
        return ArtifactRefV1(
            artifact_id="mechanism-artifact-v1",
            digest=DigestV1(value=_FIXED_DIGEST),
        )


class _CountingWorkspacePort:
    """One counting simulated workspace write port (SPEC §10.4 item 5).

    ``replace``/``delete`` are the only authoritative-write operations;
    the count proves whether a final approval let a write through.  No
    real workspace is ever touched.
    """

    def __init__(self) -> None:
        self._write_count = 0

    @property
    def write_count(self) -> int:
        return self._write_count

    def replace(self, path: CanonicalRelativePathV1, body: bytes) -> None:
        del path, body
        self._write_count += 1

    def delete(self, path: CanonicalRelativePathV1) -> None:
        del path
        self._write_count += 1


class _FixedActionIdGenerator:
    """One deterministic Harness action-id generator (the same action id
    sequence never repeats, so binding stays deterministic)."""

    def __init__(self) -> None:
        self._counter = 0

    def next_id(self) -> str:
        self._counter += 1
        return f"mechanism-action-{self._counter}"


class _FixedTurnIdGenerator:
    """One deterministic Task 25.B turn-id generator.

    The real-call turns carry their own prefix so they never collide
    with the pipeline's mechanism-turn rows in the same wiring."""

    def __init__(self) -> None:
        self._counter = 0

    def next_id(self) -> str:
        self._counter += 1
        return f"mechanism-call-turn-{self._counter}"


class _RecordingToolPortsV1:
    """The closed six-port holder with the recording wrappers.

    Satisfies the shared Task 17.C ``ToolPortsV1`` shape: the fixed
    Task 30.C simulated read/patch/check ports are registered (the
    wrappers count candidate publications and check invocations) and the
    other three stay ``None``.
    """

    list_files = None
    search_text = None
    propose_completion = None

    def __init__(self, ports: ToolPortsV1, record: "_RecordingPorts") -> None:
        self._ports = ports
        self._record = record

    def read_file(
        self, tree: ReadableTreeV1, action: ReadFileActionV1
    ) -> ReadFileResultV1:
        port = self._ports.read_file
        assert port is not None
        return port(tree, action)

    def apply_candidate_patch(
        self, action: ApplyCandidatePatchAction
    ) -> CandidatePatchOutcomeV1:
        port = self._ports.apply_candidate_patch
        assert port is not None
        result = port(action)
        if result.kind == "PUBLISHED":
            self._record.candidate_publish_count += 1
        return result

    def run_check(self, action: RunCheckActionV1) -> RunCheckOutcomeV1:
        port = self._ports.run_check
        assert port is not None
        result = port(action)
        self._record.check_invocation_count += 1
        return result


class _RecordingPorts:
    """Counting wrappers over the fixed Task 30.C simulated ports.

    The inner ports are the production ``DemoExecutor`` ports (the fixed
    scenario mapping); the wrappers only count candidate-publish and
    check-invocation events so the trace can prove zero side effects on
    DENY stages and exactly-one publication on ALLOW stages.
    """

    def __init__(self, executor: DemoExecutor) -> None:
        self.candidate_publish_count = 0
        self.check_invocation_count = 0
        self._ports = executor.tool_ports()

    @property
    def tool_ports(self) -> ToolPortsV1:
        return _RecordingToolPortsV1(self._ports, self)  # type: ignore[return-value]


class _FakeCredentialStore:
    """One closed Task 27.B credential store port double.

    ``probe_backend``/``get_for_call`` are the only operations the real
    call gate performs; every probe outcome is configured explicitly, so
    the missing/cleared and unsafe-backend probes are deterministic.
    """

    def __init__(self) -> None:
        self.backend_unsafe = False
        self.credential_missing = False

    def configure(self, *, backend_unsafe: bool, credential_missing: bool) -> None:
        self.backend_unsafe = backend_unsafe
        self.credential_missing = credential_missing

    def probe_backend(self) -> CredentialBackendProbeV1:
        if self.backend_unsafe:
            raise CredentialBackendUnsafeError(
                "backend is not the verified Windows Credential Manager"
            )
        return CredentialBackendProbeV1(
            schema_version=1,
            backend_id="WINDOWS_CREDENTIAL_MANAGER",
            capability="READ_WRITE_DELETE",
        )

    def get_for_call(self, provider: str) -> SecretCredentialV1 | CredentialMissingV1:
        if self.credential_missing:
            return CredentialMissingV1(schema_version=1, kind="MISSING")
        return SecretCredentialV1.from_hidden_input("mechanism-demo-fixed-secret")

    def set(
        self, provider: str, secret: SecretCredentialV1
    ) -> CredentialStoreMutationV1:
        raise NotImplementedError("the mechanism driver never mutates credentials")

    def status(self, provider: str) -> CredentialStatusV1:
        raise NotImplementedError("the mechanism driver never reads credential status")

    def clear(self, provider: str) -> CredentialStoreMutationV1:
        raise NotImplementedError("the mechanism driver never clears credentials")


class _CountingTransport:
    """One counting HTTP transport stub (SPEC §6.1 test double).

    ``post`` counts every invocation and returns the fixed 200 response
    body; it never opens a socket, so ``network_count`` stays zero and
    the declared adapter is the only difference of the positive probe.
    """

    def __init__(self) -> None:
        self.count = 0

    def post(
        self,
        url: str,
        headers: object,
        body: bytes,
    ) -> LLMTransportResultV1:
        del url, headers, body
        self.count += 1
        return LLMTransportResultV1(
            status_code=200,
            headers=(),
            body=_OK_RESPONSE_BODY,
        )


@dataclass(frozen=True)
class _RealCallCounters:
    """One snapshot of the real-call side-effect counters."""

    records: int
    turns: int
    calls: int
    charge: int
    transport: int


class MechanismHarness:
    """The offline governance-and-feedback mechanism driver.

    ``run`` executes the full fixed stage sequence and returns the
    bounded result; ``run_step`` executes one declared stage; the
    production pipeline, policy, dispatcher, feedback, stop, approval,
    continuation, and real-call gates drive every stage (32.A/32.B/32.C
    GREEN-1..GREEN-4).
    """

    def __init__(
        self,
        config: MechanismDemoConfigV1 | None = None,
        scenario: DemoScenarioV1 = FIXED_DEMO_SCENARIO_V1,
    ) -> None:
        self._config = config if config is not None else default_mechanism_config()
        self._scenario = scenario
        self._clock = FakeClockV1(
            CanonicalTimestampV1(self._config.clock_epoch).epoch_milliseconds
        )
        connection = sqlite3.connect(
            ":memory:",
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        self._database = ControlDatabase(connection)
        apply_migrations(self._database, _MECHANISM_MIGRATIONS_V1)
        self._pipeline = ActionPipeline()
        self._policy_engine = PolicyEngine()
        self._dispatcher = ToolDispatcher()
        self._feedback_repository = FeedbackRepositoryV1(self._database)
        self._action_record_repository = ActionRecordRepositoryV1(self._database)
        self._stopping = StopEvaluator()
        self._visible_tree = _FixedVisibleTree()
        self._artifact_store = _FixedArtifactStore()
        self._action_id_generator = _FixedActionIdGenerator()
        reset_issued_action_ids()
        self._executor = DemoExecutor(scenario)
        self._ports = _RecordingPorts(self._executor)
        self._write_port = _CountingWorkspacePort()
        self._turn_sequence = 0
        self._has_run = False
        self._paged_tree_a = _PagedVisibleTree(_FIXED_DIGEST, _PAGED_TREE_A_FILES_V1)
        self._paged_tree_b = _PagedVisibleTree(_DRIFTED_DIGEST, _PAGED_TREE_B_FILES_V1)
        self._manifest = load_reference_profile(
            (
                Path(__file__).resolve().parents[1]
                / "src/vespercode/profiles/builtin/reference-profile-v1.json"
            ).read_bytes()
        )
        self._openai_profile = _load_openai_profile()
        self._credential_store = _FakeCredentialStore()
        self._transport = _CountingTransport()
        self._orchestrator = CallOrchestrator(
            boundary=TurnBoundary(
                self._database,
                clock=self._clock,
                turn_id_generator=_FixedTurnIdGenerator(),
            ),
            ledger=DisclosureLedger(self._database, Path(":memory:")),
            credential_store=self._credential_store,
            openai_adapter=OpenAILLMAdapter(transport=self._transport),
            clock=self._clock,
        )
        self._steps: dict[str, Callable[[], MechanismStepTraceV1]] = {
            "readme-read": self._stage_readme_read,
            "readme-modify": self._make_patch_deny_stage("readme-modify"),
            "outside-scope-create": self._make_patch_deny_stage("outside-scope-create"),
            "src-patch": self._stage_src_patch,
            "protected-tests-patch": self._make_patch_deny_stage(
                "protected-tests-patch"
            ),
            "protected-config-patch": self._make_patch_deny_stage(
                "protected-config-patch"
            ),
            "feedback-correction": self._stage_feedback_correction,
            "final-approval-no-write": self._stage_approval_no_write,
            "approval-consume-exact": self._stage_approval_consume_exact,
            "paged-continuation": self._stage_paged_continuation,
            "real-call-gate": self._stage_real_call_gate,
        }

    @property
    def database(self) -> ControlDatabase:
        """The ephemeral in-memory wiring of the real production
        components (read-only inspection surface for the tests)."""
        return self._database

    @property
    def counting_write_port(self) -> _CountingWorkspacePort:
        """The counting simulated workspace port of the approval gate."""
        return self._write_port

    @property
    def paged_trees(self) -> tuple[_PagedVisibleTree, _PagedVisibleTree]:
        """The two fixed continuation trees (base and drifted)."""
        return self._paged_tree_a, self._paged_tree_b

    def writeback_subject(
        self,
        expires_at: CanonicalTimestampV1 = _WRITEBACK_EXPIRES_AT,
    ) -> FinalWritebackSubjectV1:
        """The fixed current writeback subject (production builder); the
        expiry is the fixed future value unless the expired-approval
        probe supplies a past one."""
        return self._build_writeback_subject(_FIXED_DIGEST, expires_at)

    def seed_final_writeback_approval(
        self,
        subject: FinalWritebackSubjectV1,
        approval_id: str,
    ) -> None:
        """Seed one PENDING final-writeback approval through the
        production wait/decision flow (SPEC §4.4.2)."""
        wait_id = f"wait-{approval_id}"
        self._insert_writeback_run()
        RunRepository(self._database).create_wait(
            WaitContextV1(
                wait_id=wait_id,
                run_id=_WRITEBACK_RUN_ID,
                wait_kind="FINAL_WRITEBACK",
                source_phase="FORMAL_VALIDATION",
                subject_digest=DigestV1(value=subject.digest),
                created_at=_REAL_CREATED_AT,
                expires_at=subject.expires_at,
            )
        )
        result = FinalWritebackDecisionServiceV1(self._database).decide(
            DecideFinalWritebackV1(
                decision=WaitDecisionV1(
                    wait_id=wait_id,
                    run_id=_WRITEBACK_RUN_ID,
                    wait_kind="FINAL_WRITEBACK",
                    subject_digest=DigestV1(value=subject.digest),
                    decision="APPROVE",
                    event_id=f"evt-{approval_id}",
                    decided_at=_REAL_DECIDED_AT,
                ),
                subject=subject,
                approval_id=approval_id,
            )
        )
        if result.kind != "APPROVED":
            raise ValueError(f"approval seeding failed: {result.kind}")

    def approval_repository(self) -> WritebackApprovalRepository:
        """The production transactional approval gate over the wiring."""
        return WritebackApprovalRepository(self._database)

    def run(self, config: MechanismDemoConfigV1 | None = None) -> MechanismDemoResultV1:
        """Execute the full fixed stage sequence and finalize the
        bounded report (32.A GREEN-1/GREEN-2, 32.C GREEN-2).  The
        optional config must match the harness's bound config (a
        different config is a closed rejection).

        One mechanism run is once-only per harness: the production
        feedback replay semantics and the seeded approval/grant rows
        make a second run on the same harness produce a different (not
        a repeated) trace, so repeated runs — like the Task 30.D
        runner's fresh sessions — use a fresh harness (the deterministic
        identity is proven across fresh harnesses)."""
        if config is not None and config != self._config:
            raise ValueError("the run config must match the harness config")
        if self._has_run:
            raise ValueError(
                "the mechanism run is once-only per harness; repeated runs"
                " use a fresh harness"
            )
        self._has_run = True
        stages = tuple(self.run_step(step_id) for step_id in _RUN_STAGE_ORDER_V1)
        identity = domain_digest(
            "MechanismDemoTraceV1",
            1,
            {
                "schema_version": 1,
                "scenario_id": self._config.scenario_id,
                "run_id": self._config.run_id,
                "stages": tuple(
                    canonical_json_bytes(stage.model_dump(exclude_none=True)).decode(
                        "utf-8"
                    )
                    for stage in stages
                ),
            },
        )
        trace = MechanismDemoTraceV1(
            schema_version=1,
            trace_id=identity,
            scenario_id=self._config.scenario_id,
            run_id=self._config.run_id,
            stages=stages,
            digest=identity,
        )
        report_bytes = trace.to_canonical_bytes()
        if len(report_bytes) > _REPORT_MAX_BYTES_V1:
            raise ValueError("the mechanism report exceeds its bounded size")
        report_text = report_bytes.decode("utf-8")
        semantic_digest = domain_digest(
            "MechanismDemoSemanticV1",
            1,
            {
                "schema_version": 1,
                "scenario_id": self._config.scenario_id,
                "run_id": self._config.run_id,
                "stages": tuple(
                    canonical_json_bytes(stage.model_dump(exclude_none=True)).decode(
                        "utf-8"
                    )
                    for stage in stages
                ),
            },
        )
        return MechanismDemoResultV1(
            schema_version=1,
            trace=trace,
            report_text=report_text,
            report_byte_count=len(report_bytes),
            report_digest=hashlib.sha256(report_bytes).hexdigest(),
            semantic_digest=semantic_digest,
        )

    def run_step(self, step_id: str) -> MechanismStepTraceV1:
        """Execute one declared mechanism stage."""
        step = self._steps.get(step_id)
        if step is None:
            raise ValueError(f"unknown mechanism step {step_id!r}")
        return step()

    def run_feedback_recovery(self) -> MechanismStepTraceV1:
        """The feedback-recovery stage (32.B RED contract)."""
        return self._stage_feedback_correction()

    # ------------------------------------------------------------------
    # 32.A governance stages
    # ------------------------------------------------------------------

    def _stage_readme_read(self) -> MechanismStepTraceV1:
        """The read_file action on README.md is never DENYed (SPEC
        §10.4 item 2): ALLOW, one dispatch through the fixed simulated
        read port, zero candidate publish (quality-review Q2 note: the
        port returns the fixed scenario source; what is proven is that
        reading is allowed, not that a real README.md exists)."""
        action = ReadFileActionV1(
            schema_version=1,
            action_type="read_file",
            path=CanonicalRelativePathV1("README.md"),
            start_line=1,
            line_count=1,
            max_bytes=1024,
        )
        result, _digest, _consumed = self._drive_pipeline(action, None)
        self._stop_decision()
        return MechanismStepTraceV1(
            schema_version=1,
            step_id="readme-read",
            error_code=None,
            dispatch_count=1 if result.dispatch_result is not None else 0,
            candidate_publish_count=0,
        )

    def _make_patch_deny_stage(
        self, step_id: str
    ) -> Callable[[], MechanismStepTraceV1]:
        """One fixed patch step through the production DENY trace.

        The pre-policy fact decides before dispatch: the outside-scope
        create and README modify are ``PATCH_PATH_NOT_EDITABLE`` hard
        DENYs and the protected-tests patch is ``PROTECTED_ARTIFACT_CHANGED``
        (SPEC §10.4 items 1, 2, and 4) — every guardrail fires before
        dispatch, publish, approval consumption, or real-provider access.
        """
        fact = _FIXED_PATCH_FACTS_V1[step_id]
        action = ApplyCandidatePatchAction(
            schema_version=1,
            action_type="apply_candidate_patch",
            base_candidate_digest=_FIXED_DIGEST,
            patch_format="UNIFIED_DIFF_V1",
            patch_text=_FIXED_PATCH_TEXTS_V1[step_id],
        )

        def _run() -> MechanismStepTraceV1:
            publishes_before = self._ports.candidate_publish_count
            checks_before = self._ports.check_invocation_count
            result, _digest, _consumed = self._drive_pipeline(action, fact)
            # The production policy decision is the authority: the
            # recorded error code is the same fact the production engine
            # maps to its DENY reason (quality-review M2 pin).
            assert result.policy_decision == "DENY"
            self._stop_decision()
            return MechanismStepTraceV1(
                schema_version=1,
                step_id=step_id,
                error_code=fact,
                dispatch_count=1 if result.dispatch_result is not None else 0,
                candidate_publish_count=(
                    self._ports.candidate_publish_count - publishes_before
                ),
                check_invocation_count=(
                    self._ports.check_invocation_count - checks_before
                ),
                formal_validation_count=0,
            )

        return _run

    def _stage_src_patch(self) -> MechanismStepTraceV1:
        """The fixed legal src/** patch (SPEC §10.4 item 3): ALLOW,
        exactly one dispatch and one candidate publish."""
        action = ApplyCandidatePatchAction(
            schema_version=1,
            action_type="apply_candidate_patch",
            base_candidate_digest=_FIXED_DIGEST,
            patch_format="UNIFIED_DIFF_V1",
            patch_text=_FIXED_PATCH_TEXTS_V1["src-patch"],
        )
        publishes_before = self._ports.candidate_publish_count
        result, _digest, _consumed = self._drive_pipeline(action, "OK")
        self._stop_decision()
        return MechanismStepTraceV1(
            schema_version=1,
            step_id="src-patch",
            error_code=None,
            dispatch_count=1 if result.dispatch_result is not None else 0,
            candidate_publish_count=(
                self._ports.candidate_publish_count - publishes_before
            ),
        )

    # ------------------------------------------------------------------
    # 32.B feedback-recovery stage
    # ------------------------------------------------------------------

    def _stage_feedback_correction(self) -> MechanismStepTraceV1:
        """The injected failing check changes the next action once.

        Turn 1 is the fixed failing src/** patch (dispatched and
        published); the fixed injected check failure then materializes
        as structured CHECK feedback through the production Task 24.A
        builder and is appended; turn 2 binds the production Task 24.B
        selection and consumes it exactly once while proposing the fixed
        corrective action (SPEC §10.4 item 3, 32.B GREEN-1).
        """
        first_action = ApplyCandidatePatchAction(
            schema_version=1,
            action_type="apply_candidate_patch",
            base_candidate_digest=_FIXED_DIGEST,
            patch_format="UNIFIED_DIFF_V1",
            patch_text=_FIXED_PATCH_TEXTS_V1["src-patch"],
        )
        corrective_action = ApplyCandidatePatchAction(
            schema_version=1,
            action_type="apply_candidate_patch",
            base_candidate_digest=_FIXED_DIGEST,
            patch_format="UNIFIED_DIFF_V1",
            patch_text=_CORRECTIVE_PATCH_TEXT_V1,
        )
        publishes_before = self._ports.candidate_publish_count
        _first_result, first_digest, _consumed = self._drive_pipeline(
            first_action, "OK", select_after=False
        )
        records = build_feedback(self._fixed_check_result(), self._clock)
        append_outcome = self._feedback_repository.append(records)
        if append_outcome.kind != "APPENDED":
            raise ValueError(f"check feedback append failed: {append_outcome.kind}")
        selection = select_feedback(self._rehydrate_feedback_records())
        _corrective_result, corrective_digest, consumed = self._drive_pipeline(
            corrective_action,
            "OK",
            consumed_feedback_refs=selection.refs,
        )
        self._stop_decision()
        return MechanismStepTraceV1(
            schema_version=1,
            step_id="feedback-correction",
            error_code=None,
            dispatch_count=2,
            candidate_publish_count=(
                self._ports.candidate_publish_count - publishes_before
            ),
            feedback_consumption_count=consumed,
            first_action_digest=first_digest,
            corrective_action_digest=corrective_digest,
        )

    # ------------------------------------------------------------------
    # 32.A final-approval gate stages
    # ------------------------------------------------------------------

    def _stage_approval_no_write(self) -> MechanismStepTraceV1:
        """No final approval, no authoritative write (SPEC §10.4 item 5).

        The production Task 14.C approval gate decides both probes — a
        nonexistent approval (``NOT_FOUND``) and a stale approval bound
        to a drifted subject (``STALE``) — with zero consumption and zero
        workspace writes.
        """
        subject = self.writeback_subject()
        repository = self.approval_repository()
        writes_before = self._write_port.write_count
        missing = repository.consume(
            ConsumeWritebackApprovalV1(
                approval_id="mechanism-approval-none",
                subject=subject,
                event_id="evt-approval-none",
                consumed_at=self._clock.now(),
            )
        )
        if missing.kind != "NOT_FOUND":
            raise ValueError(f"missing approval consumed: {missing.kind}")
        drifted = self._build_writeback_subject(_DRIFTED_DIGEST)
        self.seed_final_writeback_approval(drifted, "mechanism-approval-stale")
        stale = repository.consume(
            ConsumeWritebackApprovalV1(
                approval_id="mechanism-approval-stale",
                subject=subject,
                event_id="evt-approval-stale",
                consumed_at=self._clock.now(),
            )
        )
        if stale.kind != "STALE":
            raise ValueError(f"stale approval consumed: {stale.kind}")
        return MechanismStepTraceV1(
            schema_version=1,
            step_id="final-approval-no-write",
            error_code="APPROVAL_REQUIRED",
            approval_consumption_count=0,
            workspace_write_count=self._write_port.write_count - writes_before,
        )

    def _stage_approval_consume_exact(self) -> MechanismStepTraceV1:
        """The exact PENDING approval is the sole write entry: one
        consumption, then exactly one simulated workspace write (SPEC
        §4.4.2/AC-03)."""
        subject = self.writeback_subject()
        self.seed_final_writeback_approval(subject, "mechanism-approval-exact")
        repository = self.approval_repository()
        outcome = repository.consume(
            ConsumeWritebackApprovalV1(
                approval_id="mechanism-approval-exact",
                subject=subject,
                event_id="evt-approval-exact",
                consumed_at=self._clock.now(),
            )
        )
        if outcome.kind != "CONSUMED":
            raise ValueError(f"exact approval not consumed: {outcome.kind}")
        writes_before = self._write_port.write_count
        self._write_port.replace(CanonicalRelativePathV1("src/example.py"), b"x = 1\n")
        return MechanismStepTraceV1(
            schema_version=1,
            step_id="approval-consume-exact",
            error_code=None,
            approval_consumption_count=1,
            workspace_write_count=self._write_port.write_count - writes_before,
        )

    # ------------------------------------------------------------------
    # 32.B continuation stage
    # ------------------------------------------------------------------

    def _stage_paged_continuation(self) -> MechanismStepTraceV1:
        """The production paged List/Search continuation over the fixed
        tree: paged equals unpaged with exact cursor identity, a
        tampered cursor returns ``CONTINUATION_INVALID`` and a tree
        drift ``CONTINUATION_STALE``, both with zero payload (SPEC
        §4.2.8/AC-17, 32.B GREEN-2)."""
        tree = self._paged_tree_a
        list_equivalent = self._paged_list_walk(tree)
        search_equivalent = self._paged_search_walk(tree)
        tamper_code = self._tamper_probe(tree)
        stale_code = self._stale_probe(tree)
        return MechanismStepTraceV1(
            schema_version=1,
            step_id="paged-continuation",
            error_code=None,
            paged_list_equivalence=list_equivalent,
            paged_search_equivalence=search_equivalent,
            tamper_error_code=tamper_code,
            stale_error_code=stale_code,
        )

    def _paged_list_walk(self, tree: ReadableTreeV1) -> bool:
        """Paged list equals unpaged list, with no duplicates/omissions."""
        unpaged = list_files(tree, _list_action(500, AbsentV1(kind="ABSENT")))
        assert isinstance(unpaged, ListFilesSuccessV1)
        collected: list[ListFilesEntryV1] = []
        cursor: OptionalListFilesCursorV1 = AbsentV1(kind="ABSENT")
        while True:
            page = list_files(tree, _list_action(2, cursor))
            assert isinstance(page, ListFilesSuccessV1)
            collected.extend(page.entries)
            if page.next_cursor.kind == "ABSENT":
                break
            cursor = page.next_cursor
        return len(collected) == len(unpaged.entries) and all(
            entry.path.value == expected.path.value
            for entry, expected in zip(collected, unpaged.entries)
        )

    def _paged_search_walk(self, tree: ReadableTreeV1) -> bool:
        """Paged search equals unpaged search, with no duplicates/omissions."""
        unpaged = search_text(tree, _search_action(100, AbsentV1(kind="ABSENT")))
        assert isinstance(unpaged, SearchTextSuccessV1)
        collected: list[SearchTextMatchV1] = []
        cursor: OptionalSearchTextCursorV1 = AbsentV1(kind="ABSENT")
        while True:
            page = search_text(tree, _search_action(2, cursor))
            assert isinstance(page, SearchTextSuccessV1)
            collected.extend(page.matches)
            if page.next_cursor.kind == "ABSENT":
                break
            cursor = page.next_cursor
        return len(collected) == len(unpaged.matches) and all(
            match.path.value == expected.path.value
            and match.line == expected.line
            and match.column == expected.column
            for match, expected in zip(collected, unpaged.matches)
        )

    def _tamper_probe(self, tree: ReadableTreeV1) -> str | None:
        """One internally tampered cursor returns CONTINUATION_INVALID
        with zero payload."""
        first = list_files(tree, _list_action(2, AbsentV1(kind="ABSENT")))
        assert isinstance(first, ListFilesSuccessV1)
        assert first.next_cursor.kind == "PRESENT"
        tampered = first.next_cursor.value.model_copy(
            update={"next_canonical_path": CanonicalRelativePathV1("zzz")}
        )
        result = list_files(
            tree,
            _list_action(2, PresentV1(kind="PRESENT", value=tampered)),
        )
        if isinstance(result, FileToolErrorV1):
            return result.error_code
        return None

    def _stale_probe(self, tree: ReadableTreeV1) -> str | None:
        """A consistently bound cursor against a drifted tree returns
        CONTINUATION_STALE with zero payload."""
        first = list_files(tree, _list_action(2, AbsentV1(kind="ABSENT")))
        assert isinstance(first, ListFilesSuccessV1)
        assert first.next_cursor.kind == "PRESENT"
        result = list_files(
            self._paged_tree_b,
            _list_action(2, first.next_cursor),
        )
        if isinstance(result, FileToolErrorV1):
            return result.error_code
        return None

    # ------------------------------------------------------------------
    # 32.C real-call gate stage
    # ------------------------------------------------------------------

    def _stage_real_call_gate(self) -> MechanismStepTraceV1:
        """The disclosure/credential real-call gates (SPEC §4.4.4/AC-13,
        32.C GREEN-2): missing disclosure, expired grant, scope-exceeded
        grant, missing/cleared credential, and unsafe backend each stop
        before authorization, count, charge, transport, or network; the
        exact authorized probe is the only path that passes the gate and
        performs exactly one transport through the declared counting
        stub."""
        probes = (
            self._probe_missing_grant(),
            self._probe_grant_expired(),
            self._probe_scope_exceeded(),
            self._probe_credential_missing(),
            self._probe_credential_backend_unsafe(),
            self._probe_authorized(),
        )
        return MechanismStepTraceV1(
            schema_version=1,
            step_id="real-call-gate",
            error_code=None,
            real_call_probes=probes,
        )

    def _probe_missing_grant(self) -> RealCallProbeTraceV1:
        """No DisclosureGrant exists: the real-call gate stops before
        every side effect (SPEC §10.4 item 6)."""
        run_id = "mechanism-real-missing"
        self._insert_real_run(run_id)
        self._credential_store.configure(backend_unsafe=False, credential_missing=False)
        before = self._read_real_counters(run_id, "mechanism-grant-none")
        result = self._orchestrator.call_once(
            self._real_call_command(run_id, "mechanism-grant-none")
        )
        return self._probe_trace(
            "missing-disclosure", run_id, "mechanism-grant-none", before, result
        )

    def _probe_grant_expired(self) -> RealCallProbeTraceV1:
        """An expired DisclosureGrant stops with the stable
        DISCLOSURE_GRANT_EXPIRED code and zero side effects."""
        run_id = "mechanism-real-expired"
        grant_id = "mechanism-grant-expired"
        subject = self._grant_subject(run_id, _REAL_GRANT_EXPIRY)
        self._seed_disclosure_grant(
            run_id, grant_id, subject, "wait-real-expired", "evt-seed-expired"
        )
        self._credential_store.configure(backend_unsafe=False, credential_missing=False)
        before = self._read_real_counters(run_id, grant_id)
        self._clock.advance(_REAL_GRANT_ADVANCE_MILLISECONDS)
        result = self._orchestrator.call_once(self._real_call_command(run_id, grant_id))
        return self._probe_trace("grant-expired", run_id, grant_id, before, result)

    def _probe_scope_exceeded(self) -> RealCallProbeTraceV1:
        """A grant that does not cover the request's source path stops
        with DISCLOSURE_SCOPE_EXCEEDED and zero side effects (AC-13)."""
        run_id = "mechanism-real-scope"
        grant_id = "mechanism-grant-scope"
        subject = self._grant_subject(
            run_id,
            _REAL_GRANT_LATE_EXPIRY,
            scope_path="src/a.py",
            file_scope=True,
        )
        self._seed_disclosure_grant(
            run_id, grant_id, subject, "wait-real-scope", "evt-seed-scope"
        )
        self._credential_store.configure(backend_unsafe=False, credential_missing=False)
        before = self._read_real_counters(run_id, grant_id)
        result = self._orchestrator.call_once(
            self._real_call_command(run_id, grant_id, path="src/b.py")
        )
        return self._probe_trace("scope-exceeded", run_id, grant_id, before, result)

    def _probe_credential_missing(self) -> RealCallProbeTraceV1:
        """A cleared/missing credential stops with CREDENTIAL_MISSING
        before Grant consumption, authorization, count, or transport
        (SPEC §4.4.4/AC-13)."""
        run_id = "mechanism-real-credential"
        grant_id = "mechanism-grant-credential"
        subject = self._grant_subject(run_id, _REAL_GRANT_LATE_EXPIRY)
        self._seed_disclosure_grant(
            run_id, grant_id, subject, "wait-real-credential", "evt-seed-credential"
        )
        self._credential_store.configure(backend_unsafe=False, credential_missing=True)
        before = self._read_real_counters(run_id, grant_id)
        result = self._orchestrator.call_once(self._real_call_command(run_id, grant_id))
        return self._probe_trace("credential-missing", run_id, grant_id, before, result)

    def _probe_credential_backend_unsafe(self) -> RealCallProbeTraceV1:
        """An unsafe credential backend stops with
        CREDENTIAL_BACKEND_UNSAFE and zero side effects (AC-13)."""
        run_id = "mechanism-real-unsafe"
        grant_id = "mechanism-grant-unsafe"
        subject = self._grant_subject(run_id, _REAL_GRANT_LATE_EXPIRY)
        self._seed_disclosure_grant(
            run_id, grant_id, subject, "wait-real-unsafe", "evt-seed-unsafe"
        )
        self._credential_store.configure(backend_unsafe=True, credential_missing=False)
        before = self._read_real_counters(run_id, grant_id)
        result = self._orchestrator.call_once(self._real_call_command(run_id, grant_id))
        return self._probe_trace(
            "credential-backend-unsafe", run_id, grant_id, before, result
        )

    def _probe_authorized(self) -> RealCallProbeTraceV1:
        """The exact authorized probe is the only path that passes the
        real-call gate: one authorization record, one turn, one call,
        the exact byte charge, and exactly one transport through the
        declared counting stub with zero real network (32.C matrix:
        only the formal path may pass the real-call gate)."""
        run_id = "mechanism-real-authorized"
        grant_id = "mechanism-grant-authorized"
        subject = self._grant_subject(run_id, _REAL_GRANT_LATE_EXPIRY)
        self._seed_disclosure_grant(
            run_id, grant_id, subject, "wait-real-authorized", "evt-seed-authorized"
        )
        self._credential_store.configure(backend_unsafe=False, credential_missing=False)
        before = self._read_real_counters(run_id, grant_id)
        result = self._orchestrator.call_once(self._real_call_command(run_id, grant_id))
        return self._probe_trace("authorized", run_id, grant_id, before, result)

    # ------------------------------------------------------------------
    # shared pipeline and wiring helpers
    # ------------------------------------------------------------------

    def _drive_pipeline(
        self,
        action: AgentAction,
        patch_path_fact: PatchPathFactV1 | None,
        *,
        consumed_feedback_refs: tuple[str, ...] = (),
        select_after: bool = True,
    ) -> tuple[ActionStepResultV1, str, int]:
        """Drive one fixed action through the production pipeline and
        return the step result, the bound action's semantic digest, and
        the number of feedback records consumed by this step (the
        pipeline-internal consumption plus the Task 24.B/24.C
        post-step selection/consumption of the runner flow)."""
        self._turn_sequence += 1
        turn_id = f"mechanism-turn-{self._turn_sequence}"
        self._insert_mechanism_turn(turn_id)
        response = _model_response(action)
        context = ActionPipelineContextV1(
            turn_id=turn_id,
            consumed_feedback_refs=consumed_feedback_refs,
            run_phase="AGENT_LOOP",
            editable_policy_digest=_FIXED_DIGEST,
            reference_profile_digest=_FIXED_DIGEST,
            current_candidate_digest=_FIXED_DIGEST,
            final_diff_digest=None,
            patch_path_fact=patch_path_fact,
            visible_tree=self._visible_tree,
            ports=self._ports.tool_ports,
            artifact_store=self._artifact_store,
            policy_engine=self._policy_engine,
            dispatcher=self._dispatcher,
            feedback_repository=self._feedback_repository,
            action_record_repository=self._action_record_repository,
            clock=self._clock,
            action_id_generator=self._action_id_generator,
        )
        result = self._pipeline.execute(response, context)
        consumed = 0
        if result.consume_outcome is not None and result.consume_outcome.kind == (
            "CONSUMED"
        ):
            consumed += len(result.consume_outcome.consumed_refs)
        if select_after:
            selection = select_feedback(self._rehydrate_feedback_records())
            if selection.refs:
                outcome = consume_feedback(
                    turn_id, selection.refs, self._feedback_repository
                )
                if outcome.kind == "CONSUMED":
                    consumed += len(outcome.consumed_refs)
        return result, action_semantic_digest(action), consumed

    def _stop_decision(self) -> None:
        """Evaluate the real shared stop decision over the fixed state
        (recorded nowhere; the shared StopEvaluator invocation is proven
        by the 32.C provenance spies)."""
        self._stopping.evaluate(
            RunLoopStateV1(
                turn_count=0,
                call_count=0,
                max_turns=20,
                max_llm_calls=20,
                run_deadline=CanonicalTimestampV1("2026-08-07T09:20:00.000Z"),
                wait_deadline=None,
            ),
            LoopEvidenceV1(
                completion_requested=False,
                cancellation_honored=False,
            ),
            ProgressDecisionV1(
                has_progress=False,
                consecutive_no_progress_turns=0,
                consecutive_repeated_semantic=0,
                consecutive_invalid_outputs=0,
            ),
            self._clock.now(),
        )

    def _fixed_check_result(self) -> CheckResultV1:
        """The fixed failing check result of the injected failure."""
        return CheckResultV1(
            status="FAIL",
            check_kind="FULL_PYTEST",
            structured_findings=(
                CheckFindingV1(
                    error_code="CHECK_FAILED",
                    message=(
                        f"the fixed injected failure: {self._scenario.injected_failure}"
                    ),
                    location=None,
                ),
            ),
            raw_digest=_FIXED_DIGEST,
        )

    def _rehydrate_feedback_records(self) -> tuple[FeedbackRecordV1, ...]:
        """Every stored feedback record, in append order (the Task 24.C
        repository exposes no read-back API, so the driver rehydrates the
        stored rows itself — the same pure row-to-value mapping as the
        Task 30.D runner)."""
        rows = self._database.read_rows(
            "SELECT feedback_id, kind, severity, created_at, summary,"
            " source_ref, bounded_payload, evidence_refs, consumed_by_turn_id"
            " FROM feedback_records ORDER BY rowid"
        )
        return tuple(_rehydrate_feedback_row(row) for row in rows)

    def _insert_mechanism_turn(self, turn_id: str) -> None:
        """Insert one in-memory mechanism turn row for the real
        pipeline's feedback consumption and action-record storage (the
        v0007 schema admits at most one ACTIVE turn per run, so every
        mechanism turn carries its own fixed run identity, exactly like
        the Task 30.D runner's per-step demo run rows)."""
        with self._database.immediate_transaction() as tx:
            tx.execute(
                "INSERT INTO agent_turns (turn_id, run_id, status)"
                " VALUES (?, ?, 'ACTIVE')",
                (turn_id, f"mechanism-run-{self._turn_sequence}"),
            )

    def _build_writeback_subject(
        self,
        candidate_digest: str,
        expires_at: CanonicalTimestampV1 = _WRITEBACK_EXPIRES_AT,
    ) -> FinalWritebackSubjectV1:
        """One sealed current writeback subject (production builder)."""
        raw = b"x = 1\n"
        entry = FinalDiffEntryV1(
            operation="REPLACE",
            path=CanonicalRelativePathV1("src/example.py"),
            preimage=FinalDiffPreimageV1(
                kind="PRESENT",
                content_digest=hashlib.sha256(raw).hexdigest(),
                text_metadata=_TEXT_METADATA,
            ),
            postimage_digest=hashlib.sha256(raw).hexdigest(),
            postimage_text_metadata=_TEXT_METADATA,
        )
        diff = FinalDiffV1(
            schema_version=1,
            snapshot_tree_digest=_FIXED_DIGEST,
            entries=(entry,),
            added_and_replacement_text_bytes=len(raw),
            digest=domain_digest(
                "FinalDiffV1",
                1,
                {
                    "schema_version": 1,
                    "snapshot_tree_digest": _FIXED_DIGEST,
                    "entries": (_canonical_final_diff_entry(entry),),
                    "added_and_replacement_text_bytes": len(raw),
                },
            ),
        )
        return build_final_writeback_subject(
            FinalWritebackBindingV1(
                run_id=_WRITEBACK_RUN_ID,
                candidate_digest=candidate_digest,
                final_diff=diff,
                validation_manifest_digest=_FIXED_DIGEST,
                validation_repository_policy_digest=(
                    self._manifest.editable_path_policy.digest
                ),
                formal_evidence_digest=_FIXED_DIGEST,
                workspace_preimage_digest=_FIXED_DIGEST,
                run_config_digest=_FIXED_DIGEST,
                run_config_reference_profile_digest=self._manifest.digest,
                run_config_policy_id="PYTHON_SRC_ONLY_V1",
                reference_profile_digest=self._manifest.digest,
                reference_policy_digest=self._manifest.editable_path_policy.digest,
                policy=self._manifest.editable_path_policy,
            ),
            expires_at,
        )

    def _insert_writeback_run(self) -> None:
        """Insert the fixed writeback-gate run row (wiring only; the
        production decision service owns the wait and approval rows)."""
        _insert_run_row(
            self._database,
            _WRITEBACK_RUN_ID,
            "WAITING_USER",
            None,
            "snap-writeback",
        )

    def _grant_subject(
        self,
        run_id: str,
        expires_at: CanonicalTimestampV1,
        *,
        scope_path: str = "src/a.py",
        request_path: str = "src/a.py",
        file_scope: bool = False,
    ) -> DisclosureGrantSubjectV1:
        """One sealed disclosure subject over the fixed request sources
        (production builder; the scope always covers the subject's own
        request sources, so every seeded grant is internally consistent
        and the scope-exceeded probe drifts only at probe time)."""
        sources = validate_segment_sources(_messages(request_path))
        scopes: DisclosureScopeSequenceV1
        if file_scope:
            scopes = (
                FileDisclosureScopeV1(
                    kind="FILE", path=CanonicalRelativePathV1(scope_path)
                ),
            )
        else:
            scopes = (
                DirectoryDisclosureScopeV1(
                    kind="DIRECTORY", path=CanonicalRelativePathV1("src")
                ),
            )
        return build_disclosure_subject(
            DisclosureSubjectRequestV1(
                run_id=run_id,
                expires_at=expires_at,
                cumulative_byte_budget=_REAL_BUDGET_V1,
                url=AbsentV1(kind="ABSENT"),
            ),
            sources,
            scopes,
            self._openai_profile,
            _openai_endpoint(),
        )

    def _seed_disclosure_grant(
        self,
        run_id: str,
        grant_id: str,
        subject: DisclosureGrantSubjectV1,
        wait_id: str,
        event_id: str,
    ) -> None:
        """Seed one ACTIVE disclosure grant through the production
        wait/decision flow (SPEC §4.4.3)."""
        self._insert_real_run(run_id)
        RunRepository(self._database).create_wait(
            WaitContextV1(
                wait_id=wait_id,
                run_id=run_id,
                wait_kind="DISCLOSURE_GRANT",
                source_phase="AGENT_LOOP",
                subject_digest=DigestV1(value=subject.digest),
                created_at=_REAL_CREATED_AT,
                expires_at=subject.expires_at,
            )
        )
        outcome = DisclosureDecisionServiceV1(self._database).decide(
            DecideDisclosureGrantV1(
                decision=WaitDecisionV1(
                    wait_id=wait_id,
                    run_id=run_id,
                    wait_kind="DISCLOSURE_GRANT",
                    subject_digest=DigestV1(value=subject.digest),
                    decision="APPROVE",
                    event_id=event_id,
                    decided_at=_REAL_DECIDED_AT,
                ),
                subject=subject,
                grant_id=grant_id,
            )
        )
        if outcome.kind != "APPROVED":
            raise ValueError(f"grant seeding failed: {outcome.kind}")

    def _real_call_command(
        self,
        run_id: str,
        grant_id: str,
        *,
        path: str = "src/a.py",
    ) -> CallOnceV1:
        """One fixed real-call command over the frozen OpenAI profile
        (production prepared request; no ambient input)."""
        profile = self._openai_profile
        request = prepare_openai_request(profile, _messages(path))
        return CallOnceV1(
            schema_version=1,
            run_id=run_id,
            request=request,
            llm_profile_digest=profile.digest,
            adapter_version=profile.adapter_version,
            endpoint_id=profile.endpoint_id,
            model=profile.model,
            request_serializer_version=profile.request_serializer_version,
            redaction_profile_id=profile.redaction_profile_id,
            grant_id=grant_id,
            authorization_record_id=f"rec-{run_id}",
            event_id=f"evt-{run_id}",
        )

    def _insert_real_run(self, run_id: str) -> None:
        """Insert one fixed real-call run row (wiring only; the run
        stays WAITING_USER until the production decision service resumes
        it to RUNNING(AGENT_LOOP))."""
        _insert_run_row(self._database, run_id, "WAITING_USER", None, f"snap-{run_id}")

    def _read_real_counters(self, run_id: str, grant_id: str) -> _RealCallCounters:
        """One snapshot of the real-call side-effect counters."""
        rows = self._database.read_rows(
            "SELECT COUNT(*) FROM disclosure_authorizations"
        )
        records = int(rows[0][0])
        turns = calls = 0
        counter = self._database.read_rows(
            "SELECT turn_count, call_count FROM run_turn_call_counters"
            " WHERE run_id = ?",
            (run_id,),
        )
        if counter:
            turns, calls = int(counter[0][0]), int(counter[0][1])
        charge = 0
        grants = self._database.read_rows(
            "SELECT consumed_bytes FROM disclosure_grants WHERE grant_id = ?",
            (grant_id,),
        )
        if grants:
            charge = int(grants[0][0])
        return _RealCallCounters(
            records=records,
            turns=turns,
            calls=calls,
            charge=charge,
            transport=self._transport.count,
        )

    def _probe_trace(
        self,
        probe_id: str,
        run_id: str,
        grant_id: str,
        before: _RealCallCounters,
        result: LLMCallResultV1,
    ) -> RealCallProbeTraceV1:
        """One closed probe outcome from the exact counter deltas."""
        after = self._read_real_counters(run_id, grant_id)
        return RealCallProbeTraceV1(
            schema_version=1,
            probe_id=probe_id,
            gate_error_code=result.error_code,
            authorization_record_count=after.records - before.records,
            turn_count=after.turns - before.turns,
            call_count=after.calls - before.calls,
            charge_bytes=after.charge - before.charge,
            transport_count=after.transport - before.transport,
            network_count=0,
        )


def _load_openai_profile() -> OpenAILLMProfileV1:
    """The frozen built-in OpenAI profile (packaged JSON, offline)."""
    loaded = load_llm_profile(
        (
            Path(__file__).resolve().parents[1]
            / "src/vespercode/profiles/builtin/openai-single-turn-v1.json"
        ).read_bytes()
    )
    assert isinstance(loaded, OpenAILLMProfileV1)
    return loaded


def _openai_endpoint() -> OpenAIEndpointV1:
    """The frozen built-in OpenAI endpoint (SPEC §4.4.4)."""
    return OpenAIEndpointV1(
        endpoint_id="OPENAI_PUBLIC_API_V1",
        scheme="https",
        host="api.openai.com",
        effective_port=443,
        base_path="/v1",
    )


def _insert_run_row(
    database: ControlDatabase,
    run_id: str,
    status: str,
    phase: str | None,
    snapshot_id: str,
) -> None:
    """Insert one run wiring row (the test-established raw-row shape;
    no formal Run service exists in the offline driver)."""
    with database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots (config_snapshot_id, digest,"
            " llm_profile_id, reference_profile_id, policy_id, target_test_ids,"
            " limits_digest, frozen_at)"
            " VALUES (?, ?, 'openai-single-turn-v1', 'python-src-py312-v1',"
            " 'PYTHON_SRC_ONLY_V1', '[]', ?, ?)",
            (
                snapshot_id,
                hashlib.sha256(snapshot_id.encode("utf-8")).hexdigest(),
                "c" * 64,
                _REAL_CREATED_AT.value,
            ),
        )
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES (?, 'ws-1', ?, ?, ?, 1, ?, ?)",
            (
                run_id,
                snapshot_id,
                status,
                phase,
                _REAL_CREATED_AT.value,
                _REAL_RUN_DEADLINE.value,
            ),
        )


def _model_response(action: AgentAction) -> ModelResponse:
    """One fixed closed model response for a script action."""
    text = json.dumps(action.model_dump(), sort_keys=True, separators=(",", ":"))
    raw = text.encode("utf-8")
    return ModelResponse(
        schema_version=1,
        text=text,
        text_digest=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
    )


def _canonical_final_diff_entry(entry: FinalDiffEntryV1) -> dict[str, CanonicalValueV1]:
    """The §0.1 canonical value of one final-diff entry."""
    preimage = entry.preimage
    assert preimage.content_digest is not None
    assert preimage.text_metadata is not None
    preimage_value: dict[str, CanonicalValueV1] = {
        "kind": "PRESENT",
        "content_digest": preimage.content_digest,
        "text_metadata": {
            "encoding": preimage.text_metadata.encoding,
            "newline": preimage.text_metadata.newline,
            "final_newline": preimage.text_metadata.final_newline,
        },
    }
    post_metadata = entry.postimage_text_metadata
    post_metadata_value: dict[str, CanonicalValueV1] = {
        "encoding": post_metadata.encoding,
        "newline": post_metadata.newline,
        "final_newline": post_metadata.final_newline,
    }
    return {
        "operation": entry.operation,
        "path": entry.path.value,
        "preimage": preimage_value,
        "postimage_digest": entry.postimage_digest,
        "postimage_text_metadata": post_metadata_value,
    }


def _trace_canonical_value(
    trace: MechanismDemoTraceV1,
) -> dict[str, CanonicalValueV1]:
    """The §0.1 canonical value of one aggregate trace."""
    return {
        "schema_version": 1,
        "trace_id": trace.trace_id,
        "scenario_id": trace.scenario_id,
        "run_id": trace.run_id,
        "stages": tuple(stage.model_dump(exclude_none=True) for stage in trace.stages),
    }


def _rehydrate_feedback_row(row: sqlite3.Row) -> FeedbackRecordV1:
    """One stored feedback row back into its closed record value
    (fail-closed on unknown kinds; the Task 30.D runner's exact
    mapping)."""
    source_facts = json.loads(str(row["source_ref"]))
    kind = str(row["kind"])
    source_ref: FeedbackSourceV1
    if kind == "CHECK":
        path: AbsentV1 | PresentV1[CanonicalRelativePathV1] = AbsentV1(kind="ABSENT")
        if source_facts["path"]["kind"] == "PRESENT":
            path = PresentV1(
                kind="PRESENT",
                value=CanonicalRelativePathV1(source_facts["path"]["value"]),
            )
        source_ref = CheckFeedbackSourceV1(
            kind="CHECK",
            check_kind=source_facts["check_kind"],
            path=path,
        )
    elif kind == "ACTION":
        source_ref = ActionFeedbackSourceV1(
            kind="ACTION",
            action_id=source_facts["action_id"],
            semantic_digest=source_facts["semantic_digest"],
        )
    elif kind == "CONTROL":
        source_ref = ControlFeedbackSourceV1(
            kind="CONTROL",
            error_code=source_facts["error_code"],
        )
    else:
        raise ValueError(f"unknown feedback record kind {kind!r}")
    consumed = (
        str(row["consumed_by_turn_id"])
        if row["consumed_by_turn_id"] is not None
        else None
    )
    return FeedbackRecordV1(
        id=str(row["feedback_id"]),
        kind=cast("FeedbackKindV1", kind),
        severity=cast("FeedbackSeverityV1", str(row["severity"])),
        created_at=CanonicalTimestampV1(str(row["created_at"])),
        summary=str(row["summary"]),
        source_ref=source_ref,
        bounded_payload=str(row["bounded_payload"]),
        evidence_refs=tuple(json.loads(str(row["evidence_refs"]))),
        consumed_by_turn=consumed,
    )


def _segment(
    category: RequestSourceCategoryV1,
    content: str,
    path: str | None = None,
) -> RequestContentSegmentV1:
    """One fixed request content segment."""
    raw = content.encode("utf-8")
    return RequestContentSegmentV1(
        source_category=category,
        source_path=(
            AbsentV1(kind="ABSENT")
            if path is None
            else PresentV1(kind="PRESENT", value=CanonicalRelativePathV1(path))
        ),
        content=content,
        content_digest=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
    )


def _messages(path: str = "src/a.py") -> tuple[RequestMessageV1, ...]:
    """The fixed two-message request: protocol + task + one source file."""
    return (
        RequestMessageV1(
            role="SYSTEM",
            segments=(_segment("HARNESS_PROTOCOL", "VesperCode protocol"),),
        ),
        RequestMessageV1(
            role="USER",
            segments=(
                _segment("TASK", "fix the failing test"),
                _segment("FILE_CONTENT", "source bytes", path),
            ),
        ),
    )


def _list_action(
    max_entries: int,
    cursor: OptionalListFilesCursorV1,
) -> ListFilesActionV1:
    """One fixed list action over the repository root."""
    return ListFilesActionV1(
        schema_version=1,
        action_type="list_files",
        root=RootLocationV1(kind="ROOT"),
        recursive=True,
        max_entries=max_entries,
        cursor=cursor,
    )


def _search_action(
    max_results: int,
    cursor: OptionalSearchTextCursorV1,
) -> SearchTextActionV1:
    """One fixed literal search action over the repository root."""
    return SearchTextActionV1(
        schema_version=1,
        action_type="search_text",
        query="return",
        roots=(RootLocationV1(kind="ROOT"),),
        case_sensitive=True,
        context_lines=0,
        max_results=max_results,
        cursor=cursor,
    )


def run_mechanism_demo(
    config: MechanismDemoConfigV1,
) -> MechanismDemoResultV1:
    """One fresh offline mechanism run (module-level driver entry)."""
    return MechanismHarness(config=config).run(config)


def default_mechanism_config() -> MechanismDemoConfigV1:
    """The one fixed offline mechanism configuration."""
    return MechanismDemoConfigV1(
        schema_version=1,
        scenario_id="mock-demo-v1",
        run_id=_DEFAULT_RUN_ID,
        clock_epoch=_DEFAULT_CLOCK_EPOCH,
    )


def main(argv: list[str] | None = None) -> int:
    """The headless driver CLI: finalize and write the bounded JSON
    report to the declared path (32.C Script command)."""
    parser = argparse.ArgumentParser(
        prog="run_mechanism_demo",
        description="Run the repeatable governance-and-feedback mechanism demo",
    )
    parser.add_argument(
        "--report",
        required=True,
        help="the report JSON output path (bounded canonical report)",
    )
    args = parser.parse_args(argv)
    result = run_mechanism_demo(default_mechanism_config())
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    # The written file is exactly the bounded report bytes the result
    # binds (report_byte_count and report_digest match the file;
    # quality-review M4 pin).
    path.write_bytes(result.report_text.encode("utf-8"))
    print(
        f"mechanism demo: {len(result.trace.stages)} stages,"
        f" {result.report_byte_count} report bytes,"
        f" trace {result.trace.trace_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
