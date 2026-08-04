"""T02.4 legacy step 2.F: gate failure input stability probe.

Normalizes one explicit pytest ``CALL``/``FAIL`` event from a gate pytest
report into an immutable ``GateFailureFingerprintInputV1`` and compares two
independent normalized inputs through ``GateFingerprintComparisonV1``.

The gate normalization is a closed, deterministic subset of the SPEC §4.5
normalization rules: line endings are unified to LF, runtime object
addresses (``0x``-prefixed hexadecimal) are replaced with one fixed
placeholder, and the host temp root is replaced with another fixed
placeholder.  The input binds node id, phase, outcome, normalized message,
and canonical crash location, so two independent equal failures compare
equal and any semantic input difference compares unequal.

Owns gate-only normalized input comparison only.  The production
``FailureFingerprintV1``, registry lifecycle, and aggregate GO remain out of
scope (steps 2.C, 2.G).
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from typing import Literal

from spikes.docker_reference_boundary.pytest_reporter import (
    GatePytestReportV1,
    _domain_separated_digest,
)

ADDRESS_PLACEHOLDER = "<ADDRESS>"
TMP_ROOT_PLACEHOLDER = "<TMP_ROOT>"

_ADDRESS_RE = re.compile(r"\b0x[0-9a-fA-F]{6,}\b")


@dataclass(frozen=True)
class CanonicalGateLocationV1:
    """The canonical crash location: repository-relative path, function, line."""

    relative_path: str
    function_name: str
    line_number: int


@dataclass(frozen=True)
class GateFailureFingerprintInputV1:
    """One immutable normalized ``CALL``/``FAIL`` gate fingerprint input."""

    node_id: str
    phase: Literal["CALL"]
    outcome: Literal["FAIL"]
    normalized_message: str
    location: CanonicalGateLocationV1


@dataclass(frozen=True)
class GateFingerprintComparisonV1:
    """The closed comparison result of two gate failure fingerprint inputs."""

    equal: bool
    left_digest: str
    right_digest: str


def _normalize_message(message: str) -> str:
    """The closed gate message normalization.

    Unifies line endings to LF and replaces only the runtime addresses and
    the host temp root that SPEC §4.5 names as volatile; no other digits,
    timestamps, or hexadecimal values are ever removed.
    """
    normalized = message.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _ADDRESS_RE.sub(ADDRESS_PLACEHOLDER, normalized)
    tmp_root = tempfile.gettempdir()
    for variant in (tmp_root, tmp_root.replace("\\", "/")):
        normalized = normalized.replace(variant, TMP_ROOT_PLACEHOLDER)
    return normalized


def _input_digest(input_: GateFailureFingerprintInputV1) -> str:
    """The SPEC §0.1 identity of one normalized gate fingerprint input."""
    body = {
        "node_id": input_.node_id,
        "phase": input_.phase,
        "outcome": input_.outcome,
        "normalized_message": input_.normalized_message,
        "location": {
            "relative_path": input_.location.relative_path,
            "function_name": input_.location.function_name,
            "line_number": input_.location.line_number,
        },
    }
    return _domain_separated_digest("GateFailureFingerprintInputV1", 1, body)


def normalize_call_fail_input(
    report: GatePytestReportV1, node_id: str
) -> GateFailureFingerprintInputV1:
    """Normalize one explicit ``CALL``/``FAIL`` event into one immutable input.

    Fails closed with ``ValueError`` when the report carries no
    ``TEST_PHASE`` event with the exact node id, ``CALL`` phase, and ``FAIL``
    outcome, so no implicit or partial failure can ever become fingerprint
    input.
    """
    for event in report.events:
        if (
            event.event_type == "TEST_PHASE"
            and event.node_id == node_id
            and event.phase == "CALL"
            and event.outcome == "FAIL"
        ):
            if (
                event.normalized_message is None
                or event.relative_path is None
                or event.function_name is None
                or event.line_number is None
            ):
                raise ValueError(
                    f"CALL/FAIL event for target {node_id} lacks a structured exception"
                )
            return GateFailureFingerprintInputV1(
                node_id=node_id,
                phase="CALL",
                outcome="FAIL",
                normalized_message=_normalize_message(event.normalized_message),
                location=CanonicalGateLocationV1(
                    relative_path=event.relative_path,
                    function_name=event.function_name,
                    line_number=event.line_number,
                ),
            )
    raise ValueError(f"no CALL/FAIL event for target {node_id}")


def compare_failure_inputs(
    left: GateFailureFingerprintInputV1,
    right: GateFailureFingerprintInputV1,
) -> GateFingerprintComparisonV1:
    """Compare two immutable normalized inputs by their full bound identity."""
    left_digest = _input_digest(left)
    right_digest = _input_digest(right)
    equal = left == right and left_digest == right_digest
    return GateFingerprintComparisonV1(
        equal=equal, left_digest=left_digest, right_digest=right_digest
    )
