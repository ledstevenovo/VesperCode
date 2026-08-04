"""T01.1 legacy step 1.B: pure workspace boundary observation evaluation.

Evaluates closed lexical/final-object/ACL observations without touching the
filesystem and returns stable pass/fail codes. This module performs no
observation I/O: no path opening, no ACL inspection, no mutex acquisition,
and no GO report construction.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal

FINAL_OBJECT_IDENTITY_UNPROVEN: str = "FINAL_OBJECT_IDENTITY_UNPROVEN"
FINAL_OBJECT_IDENTITY_MISMATCH: str = "FINAL_OBJECT_IDENTITY_MISMATCH"
FINAL_OBJECT_IDENTITY_COLLISION: str = "FINAL_OBJECT_IDENTITY_COLLISION"
FINAL_OBJECT_REPARSE_DETECTED: str = "FINAL_OBJECT_REPARSE_DETECTED"
FINAL_OBJECT_LINK_COUNT_INVALID: str = "FINAL_OBJECT_LINK_COUNT_INVALID"
ACL_OBSERVATION_UNPROVEN: str = "ACL_OBSERVATION_UNPROVEN"


@dataclass(frozen=True)
class BoundaryObservationV1:
    """Immutable snapshot of one closed workspace-boundary observation."""

    code: str
    lexical_path: str
    final_path: str
    expected_volume_serial: int
    observed_volume_serial: int
    expected_file_id_128: bytes
    observed_file_id_128: bytes
    object_kind: Literal["FILE", "DIRECTORY"]
    link_count: int
    reparse_tag: int
    acl_observable: bool


BoundaryObservationSequenceV1 = tuple[BoundaryObservationV1, ...]
StableCodeSequenceV1 = tuple[str, ...]


@dataclass(frozen=True)
class BoundaryEvaluationV1:
    """Immutable outcome of one closed observation-sequence evaluation."""

    passed: bool
    failed_codes: StableCodeSequenceV1


def evaluate_workspace_observations(
    observations: BoundaryObservationSequenceV1,
) -> BoundaryEvaluationV1:
    """Evaluate one or more observations and return the stable outcome."""
    if not observations:
        raise ValueError(
            "observations must be a non-empty BoundaryObservationSequenceV1"
        )
    identity_pair_counts = Counter(
        (obs.observed_volume_serial, obs.observed_file_id_128) for obs in observations
    )
    failed_codes: list[str] = []
    for observation in observations:
        code = _first_applicable_code(observation, identity_pair_counts)
        if code is not None:
            failed_codes.append(code)
    passed = not failed_codes
    return BoundaryEvaluationV1(passed=passed, failed_codes=tuple(failed_codes))


def _identity_is_provable(observation: BoundaryObservationV1) -> bool:
    return (
        observation.observed_volume_serial != 0
        and len(observation.observed_file_id_128) > 0
    )


def _first_applicable_code(
    observation: BoundaryObservationV1,
    identity_pair_counts: Counter[tuple[int, bytes]],
) -> str | None:
    """Return the stable code of the first applicable taxonomy row, else None."""
    if not _identity_is_provable(observation):
        return FINAL_OBJECT_IDENTITY_UNPROVEN
    if (
        observation.observed_volume_serial != observation.expected_volume_serial
        or observation.observed_file_id_128 != observation.expected_file_id_128
    ):
        return FINAL_OBJECT_IDENTITY_MISMATCH
    identity_pair = (
        observation.observed_volume_serial,
        observation.observed_file_id_128,
    )
    if identity_pair_counts[identity_pair] > 1:
        return FINAL_OBJECT_IDENTITY_COLLISION
    if observation.reparse_tag != 0:
        return FINAL_OBJECT_REPARSE_DETECTED
    if observation.link_count != 1:
        return FINAL_OBJECT_LINK_COUNT_INVALID
    if not observation.acl_observable:
        return ACL_OBSERVATION_UNPROVEN
    return None
