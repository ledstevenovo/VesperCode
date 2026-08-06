"""T30.2 legacy step 30.C: the deterministic in-memory Demo executor.

``DemoExecutor`` owns only deterministic simulated tool-port adaptation
over Task 30.A fixed values (GREEN-1..GREEN-4): the closed
``DEMO_READ``/``DEMO_PATCH``/``DEMO_CHECK`` capabilities map the fixed
source, expected patch, and injected failure to closed fixed results with
no ambient input — no clock, file, random id, or external state.  The
``tool_ports`` holder registers exactly the three Demo ports on the shared
Task 17.C ``ToolPortsV1`` shape and leaves list/search/propose unregistered
(the shared dispatcher then fails closed with ``UNKNOWN_CAPABILITY`` and
zero port calls).  ``PROHIBITED_DEMO_MODULE_PREFIXES_V1`` is the closed
prohibited-module surface of the Demo package (GREEN-2): local files,
formal Run/turn repositories, SQLite repositories, Docker, credentials,
WinCred, recovery, persistence, and real provider adapters must stay
absent from the Demo import surface, and ``formal_capability_calls`` is
the closed zero-count proof that no formal capability adapter is ever
constructed or called.  Shared-core sequencing, stopping, session limits,
Web routes, disk, external services, and formal capability adapters remain
out of scope (GREEN-4/Boundary).
"""

from __future__ import annotations

import hashlib
from typing import Callable, Final, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    model_validator,
)

from src.vespercode.candidate.patch_engine import (
    ApplyCandidatePatchAction,
    CandidatePatchOutcomeV1,
)
from src.vespercode.canonical.json_v1 import canonical_json_bytes
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.demo.scenario import FIXED_DEMO_SCENARIO_V1
from src.vespercode.demo.types import DemoScenarioV1
from src.vespercode.loop.agent_actions import (
    ActionInstanceV1,
    ProposeCompletionActionV1,
    RunCheckActionV1,
)
from src.vespercode.tools.dispatcher import (
    CompletionOutcomeV1,
    RunCheckOutcomeV1,
)
from src.vespercode.tools.file_actions import (
    ListFilesActionV1,
    ReadFileActionV1,
    SearchTextActionV1,
)
from src.vespercode.tools.file_results import (
    ListFilesResultV1,
    ReadFileResultV1,
    ReadFileSuccessV1,
    SearchTextResultV1,
)
from src.vespercode.trees.candidate import (
    CandidateOverlayEntryV1,
    CandidateRevisionV1,
    CandidateTreeV1,
    digest_candidate_tree,
)
from src.vespercode.trees.content_store import ContentObjectStore
from src.vespercode.trees.readable import ReadableTreeV1
from src.vespercode.trees.snapshot import SnapshotTreeV1

DemoCapabilityKindV1: TypeAlias = Literal["DEMO_READ", "DEMO_PATCH", "DEMO_CHECK"]
"""The closed simulated tool-capability kinds of the Demo executor
(card GREEN-1: ``DEMO_READ``, ``DEMO_PATCH``, ``DEMO_CHECK``)."""

PROHIBITED_DEMO_MODULE_PREFIXES_V1: Final[frozenset[str]] = frozenset(
    {
        "vespercode.audit",
        "vespercode.credentials",
        "vespercode.execution",
        "vespercode.llm.mock_adapter",
        "vespercode.llm.openai_adapter",
        "vespercode.llm.openai_serializer",
        "vespercode.llm.prepared_request",
        "vespercode.llm.call_result",
        "vespercode.memory",
        "vespercode.persistence",
        "vespercode.runs",
        "vespercode.storage.run_repository",
        "vespercode.workspace",
    }
)
"""The closed prohibited module prefixes of the Demo package (card 30.C
interface / GREEN-2): local files, formal Run/turn repositories, SQLite
repositories, Docker, credentials, WinCred, recovery, persistence, and
real provider adapters must stay absent from the Demo import surface.

The prefix rule is exact module-boundary matching: a module path is
prohibited when it equals a prefix or starts with ``prefix + "."``; the
shared pure-core modules (``vespercode.loop.*``, ``vespercode.tools.*``,
``vespercode.governance.policy``) and value/utility modules
(``vespercode.canonical.*``, ``vespercode.contracts.*``,
``vespercode.storage.connection``) are not capability adapters and are
not listed."""

BoundActionV1: TypeAlias = ActionInstanceV1
"""The Demo-facing alias of the shared bound-action envelope
(SPEC §4.2.2 ``ActionInstanceV1`` from the shared pure core); the
executor consumes one bound action and returns one closed simulated
tool result."""


class DemoToolResultV1(BaseModel):
    """One closed deterministic simulated tool result (card 30.C).

    Binds the capability kind, the closed status, the result family, the
    exact fixed value from the Task 30.A scenario, and the stable error
    code of a failing result; SUCCEEDED never carries an error and FAILED
    always does (the closed action/result mapping, GREEN-1).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    capability_kind: DemoCapabilityKindV1
    status: Literal["SUCCEEDED", "FAILED"]
    result_type: Literal[
        "ReadFileResult",
        "ApplyCandidatePatchResult",
        "RunCheckResult",
    ]
    fixed_result: StrictStr
    error_code: Literal["CHECK_FAILED"] | None = None

    @model_validator(mode="after")
    def _require_exact_outcome(self) -> DemoToolResultV1:
        if self.status == "FAILED" and self.error_code is None:
            raise ValueError("FAILED demo results require the stable error code")
        if self.status == "SUCCEEDED" and self.error_code is not None:
            raise ValueError("SUCCEEDED demo results carry no error code")
        return self

    def to_canonical_bytes(self) -> bytes:
        """The exact §0.1 canonical bytes of the closed result.

        The absent error code is omitted (``None`` = absent, the §0.1
        closed-union convention; the canonical encoder forbids null), so
        the same fixed result always produces the same canonical bytes.
        """
        return canonical_json_bytes(self.model_dump(exclude_none=True))


class DemoCapabilityErrorV1(ValueError):
    """Closed rejection of a non-Demo capability request.

    The executor maps exactly the three closed Demo capabilities; a bound
    list/search/propose action is not a Demo capability and is rejected
    before any simulated result exists."""


class DemoToolPortsV1:
    """The closed six-port holder of the Demo executor (card 30.C).

    Satisfies the shared Task 17.C ``ToolPortsV1`` shape: the three Demo
    ports are registered with their exact typed signatures and the other
    three stay ``None`` (the shared dispatcher fails closed with
    ``UNKNOWN_CAPABILITY`` and zero port calls).  ``capability_kinds`` is
    the demo-owned closed capability registry the card's RED reads.
    """

    capability_kinds: frozenset[str]
    list_files: Callable[[ReadableTreeV1, ListFilesActionV1], ListFilesResultV1] | None
    read_file: Callable[[ReadableTreeV1, ReadFileActionV1], ReadFileResultV1] | None
    search_text: (
        Callable[[ReadableTreeV1, SearchTextActionV1], SearchTextResultV1] | None
    )
    apply_candidate_patch: (
        Callable[[ApplyCandidatePatchAction], CandidatePatchOutcomeV1] | None
    )
    run_check: Callable[[RunCheckActionV1], RunCheckOutcomeV1] | None
    propose_completion: (
        Callable[[ProposeCompletionActionV1], CompletionOutcomeV1] | None
    )

    def __init__(
        self,
        *,
        read_file: Callable[[ReadableTreeV1, ReadFileActionV1], ReadFileResultV1],
        apply_candidate_patch: Callable[
            [ApplyCandidatePatchAction], CandidatePatchOutcomeV1
        ],
        run_check: Callable[[RunCheckActionV1], RunCheckOutcomeV1],
    ) -> None:
        self.capability_kinds: frozenset[str] = frozenset(
            {"DEMO_READ", "DEMO_PATCH", "DEMO_CHECK"}
        )
        self.list_files = None
        self.search_text = None
        self.propose_completion = None
        self.read_file = read_file
        self.apply_candidate_patch = apply_candidate_patch
        self.run_check = run_check


_FIXED_DIGEST: Final = "ab" * 32
"""The fixed digest identity of every sealed Demo value (closed fixed
data over Task 30.A's frozen scenario)."""

_FIXED_REVISION_ID: Final = "root:demo-revision-v1"
"""The fixed root candidate-revision id of the simulated patch outcome."""


def _fixed_candidate_revision(scenario: DemoScenarioV1) -> CandidateRevisionV1:
    """The one fixed PUBLISHED patch outcome over the expected patch.

    The simulated patch applies the exact ``expected_patch`` bytes to the
    fixed ``src/example.py`` path; the sealed snapshot is empty and the
    tree digest is the deterministic §0.1 identity of the snapshot root
    and the single overlay row, so the same fixed data always produces
    the same revision (GREEN-1).
    """
    store = ContentObjectStore()
    content_ref = store.put(scenario.expected_patch.encode("utf-8"))
    snapshot = SnapshotTreeV1(
        root_digest=_FIXED_DIGEST,
        repository_policy_digest=_FIXED_DIGEST,
        entries=(),
        file_bytes=(),
    )
    overlay = (
        CandidateOverlayEntryV1(
            schema_version=1,
            operation="REPLACE",
            path=CanonicalRelativePathV1("src/example.py"),
            content_ref=content_ref,
        ),
    )
    tree = CandidateTreeV1(
        schema_version=1,
        snapshot=snapshot,
        store=store,
        overlay=overlay,
        digest=digest_candidate_tree(snapshot.root_digest, overlay),
    )
    return CandidateRevisionV1(
        schema_version=1,
        revision_id=_FIXED_REVISION_ID,
        parent_revision_id=None,
        candidate_digest=tree.digest,
        tree=tree,
    )


class DemoExecutor:
    """The deterministic in-memory Demo executor (30.C GREEN-1..GREEN-4).

    Every simulated result is a pure function of the closed fixed
    scenario values and the bound action — no clock, file, random id, or
    external state can enter (``no ambient input``).  The executor never
    constructs or calls a formal capability adapter:
    ``formal_capability_calls`` is the closed literal zero proof, and the
    prohibited-prefix constant is the declarative guard the tests scan
    against the Demo package's own import surface (GREEN-2).
    """

    def __init__(self, scenario: DemoScenarioV1 = FIXED_DEMO_SCENARIO_V1) -> None:
        self._scenario = scenario
        self._fixed_revision = _fixed_candidate_revision(scenario)
        self._source_digest = hashlib.sha256(
            scenario.source.encode("utf-8")
        ).hexdigest()
        self._source_line_count = scenario.source.count("\n") + (
            0 if scenario.source.endswith("\n") else 1
        )
        self._ports = DemoToolPortsV1(
            read_file=self._demo_read_port,
            apply_candidate_patch=self._demo_patch_port,
            run_check=self._demo_check_port,
        )

    def tool_ports(self) -> DemoToolPortsV1:
        """The closed Demo port holder (exactly three registered ports)."""
        return self._ports

    def execute(self, action: BoundActionV1) -> DemoToolResultV1:
        """One closed simulated tool result over the fixed values.

        The mapping is closed: READ returns the fixed source, PATCH
        returns the fixed expected patch as a SUCCEEDED result, CHECK
        returns the fixed injected failure as a FAILED result, and every
        non-Demo action is rejected with ``DemoCapabilityErrorV1`` before
        any result exists (GREEN-1).
        """
        inner = action.action
        if isinstance(inner, ReadFileActionV1):
            return DemoToolResultV1(
                schema_version=1,
                capability_kind="DEMO_READ",
                status="SUCCEEDED",
                result_type="ReadFileResult",
                fixed_result=self._scenario.source,
                error_code=None,
            )
        if isinstance(inner, ApplyCandidatePatchAction):
            return DemoToolResultV1(
                schema_version=1,
                capability_kind="DEMO_PATCH",
                status="SUCCEEDED",
                result_type="ApplyCandidatePatchResult",
                fixed_result=self._scenario.expected_patch,
                error_code=None,
            )
        if isinstance(inner, RunCheckActionV1):
            return DemoToolResultV1(
                schema_version=1,
                capability_kind="DEMO_CHECK",
                status="FAILED",
                result_type="RunCheckResult",
                fixed_result=self._scenario.injected_failure,
                error_code="CHECK_FAILED",
            )
        raise DemoCapabilityErrorV1(
            f"the Demo executor supports only the closed DEMO_READ, DEMO_PATCH,"
            f" and DEMO_CHECK capabilities, not {inner.action_type!r}"
        )

    @property
    def formal_capability_calls(self) -> int:
        """The closed zero-count proof: no formal capability adapter can
        be constructed or called by the Demo executor (GREEN-2)."""
        return 0

    def _demo_read_port(
        self, tree: ReadableTreeV1, action: ReadFileActionV1
    ) -> ReadFileResultV1:
        """The fixed DEMO_READ port: the full fixed source, always.

        The visible tree and the requested window are ignored — the
        simulated result is the exact fixed scenario source (closed
        mapping, no ambient input).
        """
        return ReadFileSuccessV1(
            kind="SUCCESS",
            path=action.path,
            file_digest=self._source_digest,
            start_line=1,
            end_line=self._source_line_count,
            eof=True,
            text=self._scenario.source,
        )

    def _demo_patch_port(
        self, action: ApplyCandidatePatchAction
    ) -> CandidatePatchOutcomeV1:
        """The fixed DEMO_PATCH port: the one PUBLISHED fixed revision.

        The simulated patch applies the exact expected patch and returns
        the same sealed revision for every patch action (closed mapping,
        no ambient input).
        """
        return CandidatePatchOutcomeV1(
            kind="PUBLISHED",
            error_code=None,
            reason=None,
            revision=self._fixed_revision,
            candidate_tree_digest=self._fixed_revision.candidate_digest,
        )

    def _demo_check_port(self, action: RunCheckActionV1) -> RunCheckOutcomeV1:
        """The fixed DEMO_CHECK port: the check always runs.

        Whether the fixed check PASSes or FAILs is the check result's own
        status (the runner materializes the fixed injected failure as
        structured feedback); the port itself only reports that the
        frozen check plan ran (SPEC §4.2.2).
        """
        return RunCheckOutcomeV1(
            kind="COMPLETED",
            error_code=None,
            bounded_message=None,
        )
