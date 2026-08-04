"""T03.1 legacy step 3.D: external-change and object-identity classifier tests.

Covers the closed five-value classification (PREIMAGE, POSTIMAGE,
ABSENT, EXTERNAL_CHANGE, UNPROVABLE) through pure byte-plus-object
identity comparison that fails closed on any external or unprovable
change.
"""

from __future__ import annotations

import dataclasses

import pytest

from spikes.persistence_recovery.observation import (
    GatePathObservationV1,
    classify_gate_path,
)
from spikes.persistence_recovery.protocol import (
    GatePathRecordV1,
    GatePreimageV1,
)

_PREIMAGE_DIGEST = "11" * 32
_POSTIMAGE_DIGEST = "22" * 32
_PREIMAGE_VOLUME = 7
_PREIMAGE_FILE_ID = b"\x07" * 16
_OTHER_DIGEST = "99" * 32


def record() -> GatePathRecordV1:
    """One REPLACE record whose preimage evidence is a PRESENT object."""
    return GatePathRecordV1(
        path="src/b.py",
        operation="REPLACE",
        sequence=1,
        preimage=GatePreimageV1(
            kind="PRESENT",
            raw_bytes_digest=_PREIMAGE_DIGEST,
            volume_serial=_PREIMAGE_VOLUME,
            file_id_128=_PREIMAGE_FILE_ID,
        ),
        postimage_digest=_POSTIMAGE_DIGEST,
        postimage=b"post b\n",
        durable_state="NOT_STARTED",
        backup_ref="txn-backup/0002.bin",
    )


def same_bytes_new_object() -> GatePathObservationV1:
    """An observation with preimage bytes but a replaced object identity."""
    return GatePathObservationV1(
        path="src/b.py",
        content_digest=_PREIMAGE_DIGEST,
        volume_serial=_PREIMAGE_VOLUME + 1,
        file_id_128=b"\x08" * 16,
        object_kind="FILE",
        supported=True,
    )


def create_record() -> GatePathRecordV1:
    """One CREATE record whose preimage evidence is ABSENT."""
    return GatePathRecordV1(
        path="src/a.py",
        operation="CREATE",
        sequence=1,
        preimage=GatePreimageV1(kind="ABSENT"),
        postimage_digest=_POSTIMAGE_DIGEST,
        postimage=b"post a\n",
        durable_state="NOT_STARTED",
        backup_ref="",
    )


def observation(
    content_digest: str = "",
    volume_serial: int = 0,
    file_id_128: bytes = b"",
    object_kind: str = "ABSENT",
    supported: bool = True,
) -> GatePathObservationV1:
    """One closed observation for the record's path."""
    return GatePathObservationV1(
        path="src/b.py",
        content_digest=content_digest,
        volume_serial=volume_serial,
        file_id_128=file_id_128,
        object_kind=object_kind,
        supported=supported,
    )


def test_same_bytes_with_replaced_object_is_external_change() -> None:
    assert classify_gate_path(record(), same_bytes_new_object()) == "EXTERNAL_CHANGE"


def test_matching_preimage_with_identity_is_preimage() -> None:
    current = observation(
        content_digest=_PREIMAGE_DIGEST,
        volume_serial=_PREIMAGE_VOLUME,
        file_id_128=_PREIMAGE_FILE_ID,
        object_kind="FILE",
    )
    assert classify_gate_path(record(), current) == "PREIMAGE"


def test_matching_postimage_is_postimage() -> None:
    current = observation(
        content_digest=_POSTIMAGE_DIGEST,
        volume_serial=1,
        file_id_128=b"\x01" * 16,
        object_kind="FILE",
    )
    assert classify_gate_path(record(), current) == "POSTIMAGE"


def test_missing_create_path_is_absent() -> None:
    assert (
        classify_gate_path(create_record(), observation(object_kind="ABSENT"))
        == "ABSENT"
    )


def test_missing_replace_path_is_external_change() -> None:
    assert (
        classify_gate_path(record(), observation(object_kind="ABSENT"))
        == "EXTERNAL_CHANGE"
    )


def test_directory_at_path_is_external_change() -> None:
    current = observation(
        content_digest=_OTHER_DIGEST,
        volume_serial=1,
        file_id_128=b"\x01" * 16,
        object_kind="DIRECTORY",
    )
    assert classify_gate_path(record(), current) == "EXTERNAL_CHANGE"


def test_unsupported_observation_is_unprovable() -> None:
    current = observation(
        content_digest=_PREIMAGE_DIGEST,
        volume_serial=_PREIMAGE_VOLUME,
        file_id_128=_PREIMAGE_FILE_ID,
        object_kind="FILE",
        supported=False,
    )
    assert classify_gate_path(record(), current) == "UNPROVABLE"


def test_incomplete_identity_is_unprovable() -> None:
    current = observation(
        content_digest=_POSTIMAGE_DIGEST,
        volume_serial=0,
        file_id_128=b"",
        object_kind="FILE",
    )
    assert classify_gate_path(record(), current) == "UNPROVABLE"


def test_unknown_bytes_are_external_change() -> None:
    current = observation(
        content_digest=_OTHER_DIGEST,
        volume_serial=1,
        file_id_128=b"\x01" * 16,
        object_kind="FILE",
    )
    assert classify_gate_path(record(), current) == "EXTERNAL_CHANGE"


def test_postimage_precedence_when_bytes_match_both() -> None:
    """A no-op replace whose preimage and postimage bytes coincide is
    provably at the postimage."""
    no_op = dataclasses.replace(record(), postimage_digest=_PREIMAGE_DIGEST)
    current = observation(
        content_digest=_PREIMAGE_DIGEST,
        volume_serial=_PREIMAGE_VOLUME,
        file_id_128=_PREIMAGE_FILE_ID,
        object_kind="FILE",
    )
    assert classify_gate_path(no_op, current) == "POSTIMAGE"


def test_classifier_is_pure_and_immutable() -> None:
    first = classify_gate_path(record(), same_bytes_new_object())
    second = classify_gate_path(record(), same_bytes_new_object())
    assert first == second == "EXTERNAL_CHANGE"
    with pytest.raises(dataclasses.FrozenInstanceError):
        same_bytes_new_object().content_digest = "00" * 32  # type: ignore[misc]


def test_external_change_classification_matrix() -> None:
    """Every closed byte/object combination classifies deterministically:
    postimage bytes win over coincident preimage bytes, same bytes with a
    replaced identity are EXTERNAL_CHANGE, and unsupported or incomplete
    identity is UNPROVABLE (never safe from content digest alone)."""
    rows: list[tuple[GatePathRecordV1, GatePathObservationV1, str]] = [
        # CREATE record (preimage ABSENT, postimage "22"*32)
        (create_record(), observation(object_kind="ABSENT"), "ABSENT"),
        (
            create_record(),
            observation(
                content_digest=_POSTIMAGE_DIGEST,
                volume_serial=1,
                file_id_128=b"\x01" * 16,
                object_kind="FILE",
            ),
            "POSTIMAGE",
        ),
        (
            create_record(),
            observation(content_digest=_POSTIMAGE_DIGEST, object_kind="FILE"),
            "UNPROVABLE",
        ),
        (
            create_record(),
            observation(
                content_digest=_POSTIMAGE_DIGEST,
                volume_serial=1,
                file_id_128=b"\x01" * 16,
                object_kind="FILE",
                supported=False,
            ),
            "UNPROVABLE",
        ),
        (
            create_record(),
            observation(
                content_digest=_OTHER_DIGEST,
                volume_serial=1,
                file_id_128=b"\x01" * 16,
                object_kind="FILE",
            ),
            "EXTERNAL_CHANGE",
        ),
        (
            create_record(),
            observation(
                content_digest="",
                volume_serial=1,
                file_id_128=b"\x01" * 16,
                object_kind="FILE",
            ),
            "UNPROVABLE",
        ),
        (
            create_record(),
            observation(
                content_digest=_OTHER_DIGEST,
                volume_serial=1,
                file_id_128=b"\x01" * 16,
                object_kind="DIRECTORY",
            ),
            "EXTERNAL_CHANGE",
        ),
        (
            create_record(),
            observation(
                content_digest=_OTHER_DIGEST,
                volume_serial=1,
                file_id_128=b"\x01" * 16,
                object_kind="SPECIAL",
            ),
            "EXTERNAL_CHANGE",
        ),
        # REPLACE record (preimage PRESENT "11"*32 vol 7 fid 07, postimage "22"*32)
        (record(), observation(object_kind="ABSENT"), "EXTERNAL_CHANGE"),
        (
            record(),
            observation(
                content_digest=_PREIMAGE_DIGEST,
                volume_serial=_PREIMAGE_VOLUME,
                file_id_128=_PREIMAGE_FILE_ID,
                object_kind="FILE",
            ),
            "PREIMAGE",
        ),
        (
            record(),
            observation(
                content_digest=_PREIMAGE_DIGEST,
                volume_serial=_PREIMAGE_VOLUME + 1,
                file_id_128=b"\x08" * 16,
                object_kind="FILE",
            ),
            "EXTERNAL_CHANGE",
        ),
        (
            record(),
            observation(
                content_digest=_POSTIMAGE_DIGEST,
                volume_serial=1,
                file_id_128=b"\x01" * 16,
                object_kind="FILE",
            ),
            "POSTIMAGE",
        ),
        (
            record(),
            observation(
                content_digest=_OTHER_DIGEST,
                volume_serial=1,
                file_id_128=b"\x01" * 16,
                object_kind="FILE",
            ),
            "EXTERNAL_CHANGE",
        ),
        (
            record(),
            observation(
                content_digest=_POSTIMAGE_DIGEST,
                volume_serial=0,
                file_id_128=b"",
                object_kind="FILE",
            ),
            "UNPROVABLE",
        ),
        (
            record(),
            observation(
                content_digest=_PREIMAGE_DIGEST,
                volume_serial=_PREIMAGE_VOLUME,
                file_id_128=_PREIMAGE_FILE_ID,
                object_kind="FILE",
                supported=False,
            ),
            "UNPROVABLE",
        ),
        (
            record(),
            observation(content_digest=_PREIMAGE_DIGEST, object_kind="FILE"),
            "UNPROVABLE",
        ),
        (
            record(),
            observation(
                content_digest=_PREIMAGE_DIGEST,
                volume_serial=_PREIMAGE_VOLUME,
                file_id_128=_PREIMAGE_FILE_ID,
                object_kind="DIRECTORY",
            ),
            "EXTERNAL_CHANGE",
        ),
        (
            record(),
            observation(
                content_digest=_PREIMAGE_DIGEST,
                volume_serial=_PREIMAGE_VOLUME,
                file_id_128=_PREIMAGE_FILE_ID,
                object_kind="SPECIAL",
            ),
            "EXTERNAL_CHANGE",
        ),
    ]
    for path_record, current, expected in rows:
        assert classify_gate_path(path_record, current) == expected, current
