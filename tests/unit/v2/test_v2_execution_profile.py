"""Route B / B4a: the v2 Docker execution profile record.

The v1 execution authority (``execution/docker_profile.py``,
``execution/docker_executor.py``, ``execution/materialization.py``,
and ``execution/cleanup.py``) is pydantic-bound and digest-pinned to the
frozen Task 2.G gate identities; it remains untouched read-only legacy
and nothing here imports it.

The v2 execution profile is configuration identity only: an opaque
``execution_profile_id`` plus a non-negative revision, bound to an
opaque reference profile id and revision, naming an opaque local image
reference (never a URL, registry spelling, tag, or content digest), and
carrying the fail-closed isolation parameters — network disabled,
non-root uid:gid, read-only root filesystem, all capabilities dropped,
no docker socket mount, a read-only workspace mount, and bounded
timeout/output ceilings.  Any deviation rejects at construction, and a
v1-shaped payload never parses as a v2 profile record.
"""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, fields

from vespercode.execution.v2_profile import (
    EXECUTION_MAX_OUTPUT_BYTES_V2,
    EXECUTION_MAX_TIMEOUT_SECONDS_V2,
    ExecutionProfileRecordV2,
    execution_profile_from_mapping,
)

_V1_FROZEN_REFERENCE_PROFILE_DIGEST = (
    "d0700f00f5ae2501ac9be7fbdd66d20e76c16a6c6f9ab7893c1aea71d57e927e"
)
_V1_FROZEN_DOCKER_IMAGE_DIGEST = (
    "cf0b6c5ccac588fccd07c3b9f050bff4daf550ac6e518fd06efb6e988ab1d823"
)

_PROFILE_FIELDS = (
    "execution_profile_id",
    "execution_profile_revision",
    "reference_profile_id",
    "reference_profile_revision",
    "image_reference",
    "network_disabled",
    "non_root_user",
    "read_only_rootfs",
    "all_capabilities_dropped",
    "docker_socket_mounted",
    "workspace_mount_read_only",
    "timeout_seconds",
    "max_output_bytes",
)


def _record(**overrides: object) -> ExecutionProfileRecordV2:
    values: dict[str, object] = {
        "execution_profile_id": "exec-profile-1",
        "execution_profile_revision": 4,
        "reference_profile_id": "reference-1",
        "reference_profile_revision": 3,
        "image_reference": "vespercode-validation-image",
        "network_disabled": True,
        "non_root_user": "10001:10001",
        "read_only_rootfs": True,
        "all_capabilities_dropped": True,
        "docker_socket_mounted": False,
        "workspace_mount_read_only": True,
        "timeout_seconds": 120,
        "max_output_bytes": EXECUTION_MAX_OUTPUT_BYTES_V2,
    }
    values.update(overrides)
    return ExecutionProfileRecordV2(**values)  # type: ignore[arg-type]


def _mapping(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "execution_profile_id": "exec-profile-1",
        "execution_profile_revision": 4,
        "reference_profile_id": "reference-1",
        "reference_profile_revision": 3,
        "image_reference": "vespercode-validation-image",
        "network_disabled": True,
        "non_root_user": "10001:10001",
        "read_only_rootfs": True,
        "all_capabilities_dropped": True,
        "docker_socket_mounted": False,
        "workspace_mount_read_only": True,
        "timeout_seconds": 120,
        "max_output_bytes": EXECUTION_MAX_OUTPUT_BYTES_V2,
    }
    values.update(overrides)
    return values


class ExecutionProfileRecordTests(unittest.TestCase):
    def test_a_minimal_profile_record_validates(self) -> None:
        record = _record()
        self.assertEqual(record.execution_profile_id, "exec-profile-1")
        self.assertEqual(record.execution_profile_revision, 4)
        self.assertEqual(record.reference_profile_id, "reference-1")
        self.assertEqual(record.reference_profile_revision, 3)
        self.assertEqual(record.image_reference, "vespercode-validation-image")
        self.assertTrue(record.network_disabled)
        self.assertEqual(record.non_root_user, "10001:10001")
        self.assertTrue(record.read_only_rootfs)
        self.assertTrue(record.all_capabilities_dropped)
        self.assertFalse(record.docker_socket_mounted)
        self.assertTrue(record.workspace_mount_read_only)
        self.assertEqual(record.timeout_seconds, 120)
        self.assertEqual(record.max_output_bytes, EXECUTION_MAX_OUTPUT_BYTES_V2)

    def test_the_record_field_set_is_closed(self) -> None:
        self.assertEqual(
            tuple(field.name for field in fields(ExecutionProfileRecordV2)),
            _PROFILE_FIELDS,
        )

    def test_the_record_is_immutable(self) -> None:
        record = _record()
        with self.assertRaises(FrozenInstanceError):
            record.network_disabled = False  # type: ignore[misc]

    def test_from_mapping_round_trip(self) -> None:
        record = execution_profile_from_mapping(_mapping())
        self.assertEqual(record, _record())

    def test_from_mapping_rejects_unknown_fields(self) -> None:
        payload = _mapping(schema_version=1)
        with self.assertRaises(ValueError):
            execution_profile_from_mapping(payload)

    def test_from_mapping_rejects_missing_fields(self) -> None:
        for name in _PROFILE_FIELDS:
            with self.subTest(field=name):
                payload = _mapping()
                del payload[name]
                with self.assertRaises(ValueError):
                    execution_profile_from_mapping(payload)

    def test_from_mapping_rejects_non_mapping_input(self) -> None:
        for bad in ([_mapping()], "profile", 3, None):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    execution_profile_from_mapping(bad)

    def test_a_v1_execution_request_shaped_payload_rejects(self) -> None:
        payload = {
            "schema_version": 1,
            "request_id": "req-1",
            "reference_profile_digest": _V1_FROZEN_REFERENCE_PROFILE_DIGEST,
            "docker_image_digest": _V1_FROZEN_DOCKER_IMAGE_DIGEST,
            "docker_execution_profile_version": 1,
            "profile": _mapping(),
            "argv": ["python", "-m", "pytest"],
        }
        with self.assertRaises(ValueError):
            execution_profile_from_mapping(payload)

    def test_a_v1_docker_profile_shaped_payload_rejects(self) -> None:
        payload = {
            "schema_version": 1,
            "profile_version": 1,
            "network_mode": "none",
            "user": "10001:10001",
            "read_only_rootfs": True,
            "capabilities_dropped": "ALL",
            "docker_socket_mounted": False,
            "workdir": "/workspace",
            "workspace_mount": {"target": "/workspace", "read_only": True},
            "tmpfs_mount": {"path": "/tmp"},
            "resources": {
                "cpus": 2,
                "memory_bytes": 2147483648,
                "pids_limit": 256,
                "tmpfs_size_bytes": 268435456,
                "max_output_bytes": 4194304,
            },
            "environment": {"variables": [{"name": "LANG", "value": "C.UTF-8"}]},
            "fresh_container_per_check": True,
            "pytest_plugin_autoload_disabled": True,
        }
        with self.assertRaises(ValueError):
            execution_profile_from_mapping(payload)

    def test_digest_shaped_values_reject(self) -> None:
        for field in (
            "execution_profile_id",
            "reference_profile_id",
            "image_reference",
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    _record(**{field: _V1_FROZEN_DOCKER_IMAGE_DIGEST})
        # Uppercase digest spellings reject too.
        with self.assertRaises(ValueError):
            _record(
                image_reference=_V1_FROZEN_DOCKER_IMAGE_DIGEST.upper()
            )

    def test_url_or_registry_shaped_image_references_reject(self) -> None:
        for image_reference in (
            "https://registry.example.com/vespercode/img:latest",
            "http://localhost:5000/img",
            "docker.io/library/python:3.12",
            "registry.example.com/vespercode@sha256:cf0b6c",
            "library/python",
            "vespercode/img:latest",
            "vespercode@sha256:cf0b6c",
            "vespercode img",
            " vespercode-image",
            "vespercode-image ",
        ):
            with self.subTest(image_reference=image_reference):
                with self.assertRaises(ValueError):
                    _record(image_reference=image_reference)

    def test_isolation_policy_violations_reject(self) -> None:
        for overrides in (
            {"network_disabled": False},
            {"non_root_user": "0:0"},
            {"non_root_user": "0:10001"},
            {"non_root_user": "10001:0"},
            {"read_only_rootfs": False},
            {"all_capabilities_dropped": False},
            {"docker_socket_mounted": True},
            {"workspace_mount_read_only": False},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    _record(**overrides)

    def test_non_root_user_spellings_reject(self) -> None:
        for non_root_user in (
            "root",
            "10001",
            "10001:abc",
            "10001:10001:10001",
            ":10001",
            "10001:",
            " 10001:10001",
            "10001:10001 ",
            "-1:10001",
            "010001:10001",
            "12345678901:10001",
            "",
        ):
            with self.subTest(non_root_user=non_root_user):
                with self.assertRaises(ValueError):
                    _record(non_root_user=non_root_user)

    def test_non_root_user_accepts_non_root_uid_gid_pairs(self) -> None:
        for non_root_user in ("1:1", "1000:1000", "10001:10001", "65534:65534"):
            with self.subTest(non_root_user=non_root_user):
                self.assertEqual(
                    _record(non_root_user=non_root_user).non_root_user,
                    non_root_user,
                )

    def test_timeout_seconds_bounds(self) -> None:
        for timeout_seconds in (1, 60, EXECUTION_MAX_TIMEOUT_SECONDS_V2):
            with self.subTest(timeout_seconds=timeout_seconds):
                self.assertEqual(
                    _record(timeout_seconds=timeout_seconds).timeout_seconds,
                    timeout_seconds,
                )
        for timeout_seconds in (
            0,
            -1,
            EXECUTION_MAX_TIMEOUT_SECONDS_V2 + 1,
            3600,
            1.5,
            "60",
            True,
            None,
        ):
            with self.subTest(timeout_seconds=timeout_seconds):
                with self.assertRaises(ValueError):
                    _record(timeout_seconds=timeout_seconds)

    def test_max_output_bytes_bounds(self) -> None:
        for max_output_bytes in (1, 1024, EXECUTION_MAX_OUTPUT_BYTES_V2):
            with self.subTest(max_output_bytes=max_output_bytes):
                self.assertEqual(
                    _record(max_output_bytes=max_output_bytes).max_output_bytes,
                    max_output_bytes,
                )
        for max_output_bytes in (
            0,
            -1,
            EXECUTION_MAX_OUTPUT_BYTES_V2 + 1,
            1.5,
            "1024",
            True,
            None,
        ):
            with self.subTest(max_output_bytes=max_output_bytes):
                with self.assertRaises(ValueError):
                    _record(max_output_bytes=max_output_bytes)

    def test_revisions_reject_negative_bool_and_non_int(self) -> None:
        for field in ("execution_profile_revision", "reference_profile_revision"):
            for revision in (0, 7):
                with self.subTest(field=field, revision=revision):
                    self.assertEqual(
                        getattr(_record(**{field: revision}), field), revision
                    )
            for revision in (-1, 1.5, "3", True, None):
                with self.subTest(field=field, revision=revision):
                    with self.assertRaises(ValueError):
                        _record(**{field: revision})

    def test_identifiers_reject_empty_and_oversized(self) -> None:
        for field in ("execution_profile_id", "reference_profile_id"):
            for identifier in ("", "   ", 42, None, "x" * 257):
                with self.subTest(field=field, identifier=identifier):
                    with self.assertRaises(ValueError):
                        _record(**{field: identifier})

    def test_boolean_fields_reject_non_bool_spellings(self) -> None:
        for overrides in (
            {"network_disabled": 1},
            {"network_disabled": "true"},
            {"read_only_rootfs": 1},
            {"read_only_rootfs": "true"},
            {"all_capabilities_dropped": 1},
            {"docker_socket_mounted": 0},
            {"workspace_mount_read_only": 0},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    _record(**overrides)


if __name__ == "__main__":
    unittest.main()
