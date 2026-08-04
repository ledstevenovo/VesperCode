"""T01.1 step 1.B: pure boundary observation evaluation (feasibility)."""

from __future__ import annotations

from typing import Literal

from spikes.win32_workspace_boundary.evaluator import (
    BoundaryObservationV1,
    evaluate_workspace_observations,
)


def make_observation(
    *,
    code: str = "OBS_1",
    lexical_path: str = "work",
    final_path: str = "work",
    expected_volume_serial: int = 0x5EED,
    observed_volume_serial: int = 0x5EED,
    expected_file_id_128: bytes = b"e" * 16,
    observed_file_id_128: bytes = b"e" * 16,
    object_kind: Literal["FILE", "DIRECTORY"] = "FILE",
    link_count: int = 1,
    reparse_tag: int = 0,
    acl_observable: bool = True,
) -> BoundaryObservationV1:
    return BoundaryObservationV1(
        code=code,
        lexical_path=lexical_path,
        final_path=final_path,
        expected_volume_serial=expected_volume_serial,
        observed_volume_serial=observed_volume_serial,
        expected_file_id_128=expected_file_id_128,
        observed_file_id_128=observed_file_id_128,
        object_kind=object_kind,
        link_count=link_count,
        reparse_tag=reparse_tag,
        acl_observable=acl_observable,
    )


def unprovable_identity_observation() -> BoundaryObservationV1:
    return make_observation(observed_volume_serial=0, observed_file_id_128=b"")


def test_unprovable_final_identity_fails_closed() -> None:
    result = evaluate_workspace_observations((unprovable_identity_observation(),))
    assert result.failed_codes == ("FINAL_OBJECT_IDENTITY_UNPROVEN",)


def test_boundary_failure_taxonomy_matrix() -> None:
    row_cases = (
        (
            unprovable_identity_observation(),
            "FINAL_OBJECT_IDENTITY_UNPROVEN",
        ),
        (
            make_observation(observed_volume_serial=1, observed_file_id_128=b"x" * 16),
            "FINAL_OBJECT_IDENTITY_MISMATCH",
        ),
        (
            make_observation(reparse_tag=0x80000009),
            "FINAL_OBJECT_REPARSE_DETECTED",
        ),
        (
            make_observation(link_count=2),
            "FINAL_OBJECT_LINK_COUNT_INVALID",
        ),
        (
            make_observation(acl_observable=False),
            "ACL_OBSERVATION_UNPROVEN",
        ),
    )
    for observation, expected_code in row_cases:
        result = evaluate_workspace_observations((observation,))
        assert result.failed_codes == (expected_code,)
        assert result.passed is False
    collision = evaluate_workspace_observations(
        (make_observation(code="A"), make_observation(code="B"))
    )
    assert collision.failed_codes == (
        "FINAL_OBJECT_IDENTITY_COLLISION",
        "FINAL_OBJECT_IDENTITY_COLLISION",
    )
    clean = evaluate_workspace_observations((make_observation(code="CLEAN"),))
    assert clean.failed_codes == ()
    assert clean.passed is True


def test_combined_observation_precedence_and_order() -> None:
    result = evaluate_workspace_observations(
        (
            make_observation(
                code="UNPROVEN_AND_REPARSE",
                reparse_tag=1,
                link_count=2,
                acl_observable=False,
                observed_volume_serial=0,
                observed_file_id_128=b"",
            ),
            make_observation(
                code="MISMATCH_AND_ACL",
                observed_volume_serial=7,
                observed_file_id_128=b"y" * 16,
                acl_observable=False,
            ),
            make_observation(code="COLLISION_AND_REPARSE", reparse_tag=1),
            make_observation(code="COLLISION_AND_REPARSE_2", reparse_tag=1),
            make_observation(
                code="REPARSE_AND_LINK",
                expected_volume_serial=0x7777,
                observed_volume_serial=0x7777,
                expected_file_id_128=b"r" * 16,
                observed_file_id_128=b"r" * 16,
                reparse_tag=2,
                link_count=3,
            ),
            make_observation(
                code="LINK_AND_ACL",
                expected_volume_serial=0x8888,
                observed_volume_serial=0x8888,
                expected_file_id_128=b"l" * 16,
                observed_file_id_128=b"l" * 16,
                link_count=0,
                acl_observable=False,
            ),
            make_observation(
                code="ACL_ONLY",
                expected_volume_serial=0x9999,
                observed_volume_serial=0x9999,
                expected_file_id_128=b"a" * 16,
                observed_file_id_128=b"a" * 16,
                acl_observable=False,
            ),
            make_observation(
                code="CLEAN",
                expected_volume_serial=0xAAAA,
                observed_volume_serial=0xAAAA,
                expected_file_id_128=b"c" * 16,
                observed_file_id_128=b"c" * 16,
            ),
        )
    )
    assert result.failed_codes == (
        "FINAL_OBJECT_IDENTITY_UNPROVEN",
        "FINAL_OBJECT_IDENTITY_MISMATCH",
        "FINAL_OBJECT_IDENTITY_COLLISION",
        "FINAL_OBJECT_IDENTITY_COLLISION",
        "FINAL_OBJECT_REPARSE_DETECTED",
        "FINAL_OBJECT_LINK_COUNT_INVALID",
        "ACL_OBSERVATION_UNPROVEN",
    )
    assert result.passed is False


def test_empty_observation_sequence_is_rejected() -> None:
    try:
        evaluate_workspace_observations(())
    except ValueError:
        return
    raise AssertionError("empty observation sequence must be rejected")
