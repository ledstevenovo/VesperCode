"""T03.1 legacy step 3.D: external-change and object-identity classifier.

Classifies one immutable path record plus one current observation
through pure byte-plus-object identity comparison into the closed
five-value classification (PREIMAGE, POSTIMAGE, ABSENT,
EXTERNAL_CHANGE, UNPROVABLE), failing closed on any external or
unprovable change.  This module is pure and side-effect free: it never
reads a workspace, decides aggregate recovery, or writes/deletes any
path.

Precedence (documented and pinned by the matrix tests):

1. An unsupported observation is UNPROVABLE.
2. An absent path is ABSENT exactly when the record's preimage is
   ABSENT (an unapplied CREATE); otherwise its deletion is an
   EXTERNAL_CHANGE.
3. A non-FILE object kind (directory, special object) at the path is an
   EXTERNAL_CHANGE.
4. An incomplete observation (empty content digest, zero volume serial,
   or empty file id) is UNPROVABLE: safety is never inferred from
   content bytes alone.
5. Bytes exactly matching the postimage classify POSTIMAGE (even when
   they also match the preimage: a no-op replace is provably at the
   postimage).
6. Bytes exactly matching a PRESENT preimage classify PREIMAGE only
   when the object identity also matches; the same bytes with a
   replaced object identity classify EXTERNAL_CHANGE.
7. Everything else is EXTERNAL_CHANGE.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from spikes.persistence_recovery.protocol import GatePathRecordV1

GatePathClassificationV1 = Literal[
    "PREIMAGE", "POSTIMAGE", "ABSENT", "EXTERNAL_CHANGE", "UNPROVABLE"
]


@dataclass(frozen=True)
class GatePathObservationV1:
    """Immutable current observation of one path.

    ``content_digest`` is empty when the path is absent; ``volume_serial``
    and ``file_id_128`` are the Win32 object identity pair (zeros/empty
    when absent or unprovable); ``object_kind`` is one of ABSENT, FILE,
    DIRECTORY, or SPECIAL; ``supported`` is False when the observation
    cannot be trusted (failed read, ACL, or kind inspection).
    """

    path: str
    content_digest: str
    volume_serial: int
    file_id_128: bytes
    object_kind: str
    supported: bool


def classify_gate_path(
    record: GatePathRecordV1,
    observation: GatePathObservationV1,
) -> GatePathClassificationV1:
    """Classify *observation* against *record*'s preimage/postimage evidence.

    Pure: the same immutable inputs always produce the identical closed
    classification.
    """
    if not observation.supported:
        return "UNPROVABLE"
    if observation.object_kind == "ABSENT":
        if record.preimage.kind == "ABSENT":
            return "ABSENT"
        return "EXTERNAL_CHANGE"
    if observation.object_kind != "FILE":
        return "EXTERNAL_CHANGE"
    if (
        not observation.content_digest
        or observation.volume_serial == 0
        or len(observation.file_id_128) == 0
    ):
        return "UNPROVABLE"
    if observation.content_digest == record.postimage_digest:
        return "POSTIMAGE"
    if (
        record.preimage.kind == "PRESENT"
        and observation.content_digest == record.preimage.raw_bytes_digest
    ):
        if (
            observation.volume_serial == record.preimage.volume_serial
            and observation.file_id_128 == record.preimage.file_id_128
        ):
            return "PREIMAGE"
        return "EXTERNAL_CHANGE"
    return "EXTERNAL_CHANGE"
