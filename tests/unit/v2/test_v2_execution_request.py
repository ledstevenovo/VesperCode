"""Route B / B4a + B4b-02A: the v2 execution request contract.

The execution port accepts one closed structured request — never a
shell or command string.  The request names its control-plane bindings:
the request itself, the execution profile, the reference profile, and
the run/candidate it targets — each an opaque id plus non-negative
revisions, the candidate revision included — an ``action_kind`` from
the closed v2 execution vocabulary, whose per-kind grammar pins the
frozen argv executable token and the exact argument count, and the
B1 validation run the production binding requires
(``validation_run_id``; ``None`` stays the B4a isolated-fake spelling,
while the production database binding fails closed on an uncited
request).

For ``VALIDATE_CANDIDATE`` the two argv argument slots are not free
tokens: they must be exactly the request's bound ``candidate_id`` and
the decimal spelling of its ``candidate_revision``, so the
adapter-facing argv is a closed projection of the request's own
control fields and cannot drift from them — a request that names one
candidate in its binding and another in its argv is not
representable.  Every argument is still a bounded opaque token (no
paths, URLs, options, whitespace, control characters, or
digest-shaped spellings).  The validation citation is a control-plane
key only: it is never projected into the argv.

The request schema has no image, URL, registry, credential, secret,
environment, command, or shell field at all: a user-supplied image or
credential cannot enter the execution plane through the request.
"""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, fields

from vespercode.execution.v2_execution import (
    EXECUTION_ACTION_GRAMMARS_V2,
    EXECUTION_ACTION_KINDS_V2,
    ExecutionActionRequestV2,
)

_V1_FROZEN_DOCKER_IMAGE_DIGEST = (
    "cf0b6c5ccac588fccd07c3b9f050bff4daf550ac6e518fd06efb6e988ab1d823"
)

_REQUEST_FIELDS = (
    "request_id",
    "execution_profile_id",
    "execution_profile_revision",
    "reference_profile_id",
    "reference_profile_revision",
    "run_id",
    "candidate_id",
    "candidate_revision",
    "action_kind",
    "argv",
    "validation_run_id",
)


def _request(**overrides: object) -> ExecutionActionRequestV2:
    values: dict[str, object] = {
        "request_id": "exec-request-1",
        "execution_profile_id": "exec-profile-1",
        "execution_profile_revision": 4,
        "reference_profile_id": "reference-1",
        "reference_profile_revision": 3,
        "run_id": "run-1",
        "candidate_id": "cand-0001",
        "candidate_revision": 3,
        "action_kind": "VALIDATE_CANDIDATE",
        "argv": ("vespercode-validate", "cand-0001", "3"),
    }
    values.update(overrides)
    return ExecutionActionRequestV2(**values)  # type: ignore[arg-type]


class ExecutionActionRequestTests(unittest.TestCase):
    def test_a_minimal_request_validates(self) -> None:
        request = _request()
        self.assertEqual(request.request_id, "exec-request-1")
        self.assertEqual(request.execution_profile_id, "exec-profile-1")
        self.assertEqual(request.execution_profile_revision, 4)
        self.assertEqual(request.reference_profile_id, "reference-1")
        self.assertEqual(request.reference_profile_revision, 3)
        self.assertEqual(request.run_id, "run-1")
        self.assertEqual(request.candidate_id, "cand-0001")
        self.assertEqual(request.candidate_revision, 3)
        self.assertEqual(request.action_kind, "VALIDATE_CANDIDATE")
        self.assertEqual(request.argv, ("vespercode-validate", "cand-0001", "3"))

    def test_the_request_field_set_is_closed(self) -> None:
        self.assertEqual(
            tuple(field.name for field in fields(ExecutionActionRequestV2)),
            _REQUEST_FIELDS,
        )

    def test_no_image_url_credential_or_command_field_exists(self) -> None:
        for field in fields(ExecutionActionRequestV2):
            for fragment in (
                "image",
                "url",
                "registry",
                "credential",
                "secret",
                "token",
                "command",
                "shell",
                "env",
                "network",
                "mount",
                "digest",
            ):
                self.assertNotIn(
                    fragment,
                    field.name,
                    f"the request schema must not carry a {fragment} field",
                )

    def test_the_closed_action_vocabulary_is_pinned(self) -> None:
        self.assertEqual(EXECUTION_ACTION_KINDS_V2, frozenset({"VALIDATE_CANDIDATE"}))
        self.assertEqual(
            EXECUTION_ACTION_GRAMMARS_V2["VALIDATE_CANDIDATE"],
            ("vespercode-validate", 2),
        )
        # The grammar table is a read-only view: the vocabulary cannot
        # be widened at runtime.
        with self.assertRaises(TypeError):
            EXECUTION_ACTION_GRAMMARS_V2["VALIDATE_CANDIDATE"] = ("x", 1)  # type: ignore[index]

    def test_a_shell_command_string_never_becomes_argv(self) -> None:
        for argv in (
            "rm -rf /workspace",
            "vespercode-validate cand-0001 3",
            "python -m pytest tests/",
            "",
        ):
            with self.subTest(argv=argv):
                with self.assertRaises(ValueError) as raised:
                    _request(argv=argv)
                self.assertIn("shell", str(raised.exception))

    def test_argv_must_be_a_sequence_of_strings(self) -> None:
        for argv in (3, None, {"vespercode-validate": 1}, {"a", "b"}, 3.5):
            with self.subTest(argv=argv):
                with self.assertRaises(ValueError):
                    _request(argv=argv)
        with self.assertRaises(ValueError):
            _request(argv=(1, 2, 3))
        with self.assertRaises(ValueError):
            _request(argv=("vespercode-validate", 3, "x"))

    def test_a_list_argv_normalizes_to_a_tuple(self) -> None:
        request = _request(argv=["vespercode-validate", "cand-0001", "3"])
        self.assertEqual(request.argv, ("vespercode-validate", "cand-0001", "3"))
        self.assertIsInstance(request.argv, tuple)

    def test_argv_first_token_must_be_the_frozen_executable(self) -> None:
        for argv in (
            ("python", "-m", "pytest"),
            ("VESPERCODE-VALIDATE", "cand-0001", "3"),
            ("vespercode-validate ", "cand-0001", "3"),
            ("/bin/vespercode-validate", "cand-0001", "3"),
        ):
            with self.subTest(argv=argv):
                with self.assertRaises(ValueError):
                    _request(argv=argv)

    def test_argv_argument_count_is_closed_per_kind(self) -> None:
        for argv in (
            ("vespercode-validate",),
            ("vespercode-validate", "cand-0001"),
            ("vespercode-validate", "cand-0001", "3", "extra"),
            (),
        ):
            with self.subTest(argv=argv):
                with self.assertRaises(ValueError):
                    _request(argv=argv)

    def test_argv_arguments_must_not_be_option_tokens(self) -> None:
        for argv in (
            ("vespercode-validate", "--verbose", "3"),
            ("vespercode-validate", "-v", "3"),
            ("vespercode-validate", "cand-0001", "--evil"),
            ("vespercode-validate", "cand-0001", "-x"),
        ):
            with self.subTest(argv=argv):
                with self.assertRaises(ValueError):
                    _request(argv=argv)

    def test_argv_arguments_must_be_bounded_opaque_tokens(self) -> None:
        for argument in (
            "src/app.py",
            "a b",
            "",
            "a" * 65,
            "can\td1",
            "can\nd1",
            "can'd",
            '"cand"',
            "cand;1",
            "cand$1",
            "cand\\1",
            "cand/1",
            "cand:1",
            "cand=1",
            "cand-ü",
            "-leading",
        ):
            with self.subTest(argument=argument):
                with self.assertRaises(ValueError):
                    _request(argv=("vespercode-validate", argument, "3"))
        for argument in ("cand-0001", "3", "a.b-c_9", "A9"):
            with self.subTest(argument=argument):
                # The candidate binding follows the argument slot, so
                # the closed projection stays consistent by
                # construction.
                request = _request(
                    argv=("vespercode-validate", argument, "3"),
                    candidate_id=argument,
                )
                self.assertEqual(request.argv[1], argument)

    def test_argv_arguments_reject_digest_shaped_tokens(self) -> None:
        with self.assertRaises(ValueError):
            _request(
                argv=(
                    "vespercode-validate",
                    _V1_FROZEN_DOCKER_IMAGE_DIGEST,
                    "3",
                )
            )

    def test_argv_arguments_are_bound_to_the_control_fields(self) -> None:
        # argv[1] must be exactly the request's own candidate_id.
        with self.assertRaises(ValueError) as raised:
            _request(argv=("vespercode-validate", "cand-0002", "3"))
        self.assertIn("candidate_id", str(raised.exception))
        # argv[2] must be exactly the decimal spelling of the request's
        # own candidate_revision.
        with self.assertRaises(ValueError) as raised:
            _request(argv=("vespercode-validate", "cand-0001", "4"))
        self.assertIn("candidate_revision", str(raised.exception))
        with self.assertRaises(ValueError) as raised:
            _request(argv=("vespercode-validate", "cand-0001", "03"))
        self.assertIn("candidate_revision", str(raised.exception))
        # The consistent spelling is accepted.
        request = _request(
            candidate_id="cand-0002",
            candidate_revision=9,
            argv=("vespercode-validate", "cand-0002", "9"),
        )
        self.assertEqual(request.candidate_id, "cand-0002")
        self.assertEqual(request.candidate_revision, 9)

    def test_the_control_binding_fields_are_validated(self) -> None:
        for field in ("run_id", "candidate_id"):
            for identifier in ("", "   ", 42, None, "x" * 257):
                with self.subTest(field=field, identifier=identifier):
                    with self.assertRaises(ValueError):
                        _request(**{field: identifier})
        for field in ("run_id", "candidate_id"):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    _request(**{field: _V1_FROZEN_DOCKER_IMAGE_DIGEST})
        for revision in (-1, 1.5, "3", True, None):
            with self.subTest(revision=revision):
                with self.assertRaises(ValueError):
                    _request(candidate_revision=revision)

    def test_candidate_id_must_be_argv_token_conformant(self) -> None:
        # The closed grammar projects the candidate id into the
        # adapter-facing argv, so the id itself must be token-shaped:
        # paths, URLs, options, and whitespace cannot be executed
        # against even at the binding level.
        for candidate_id in (
            "cand/0001",
            "cand 0001",
            "cand:1",
            "-cand",
            "cand\\1",
        ):
            with self.subTest(candidate_id=candidate_id):
                with self.assertRaises(ValueError):
                    _request(candidate_id=candidate_id)

    def test_action_kind_must_be_from_the_closed_set(self) -> None:
        for action_kind in (
            "RUN_ARBITRARY_COMMAND",
            "run_tests",
            "validate_candidate",
            "",
            3,
            None,
        ):
            with self.subTest(action_kind=action_kind):
                with self.assertRaises(ValueError):
                    _request(action_kind=action_kind)

    def test_request_bindings_are_validated(self) -> None:
        for identifier in ("", "   ", 42, None, "x" * 257):
            for field in (
                "request_id",
                "execution_profile_id",
                "reference_profile_id",
            ):
                with self.subTest(field=field, identifier=identifier):
                    with self.assertRaises(ValueError):
                        _request(**{field: identifier})
        for field in (
            "execution_profile_revision",
            "reference_profile_revision",
        ):
            for revision in (-1, 1.5, "3", True, None):
                with self.subTest(field=field, revision=revision):
                    with self.assertRaises(ValueError):
                        _request(**{field: revision})
        # Digest-shaped binding values reject: v2 references are opaque.
        for field in (
            "request_id",
            "execution_profile_id",
            "reference_profile_id",
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    _request(**{field: _V1_FROZEN_DOCKER_IMAGE_DIGEST})

    def test_the_request_is_immutable(self) -> None:
        request = _request()
        with self.assertRaises(FrozenInstanceError):
            request.argv = ("vespercode-validate", "other", "9")  # type: ignore[misc]

    # ------------------------------------------------------------------
    # The validation citation (B4b-02A)
    # ------------------------------------------------------------------

    def test_a_cited_validation_run_is_an_opaque_identifier(self) -> None:
        request = _request(validation_run_id="valid-0001")
        self.assertEqual(request.validation_run_id, "valid-0001")
        # The citation is a control-plane key only: the argv grammar is
        # unchanged and never projects it.
        self.assertEqual(request.argv, ("vespercode-validate", "cand-0001", "3"))

    def test_an_uncited_validation_run_is_the_test_only_spelling(self) -> None:
        # ``None`` stays a constructible spelling of the request RECORD
        # (data), but it is the explicitly test-only spelling: the
        # production V2ExecutionService rejects an uncited request with
        # VALIDATION_BINDING_REQUIRED before the binding port is even
        # consulted, and only V2ExecutionTestService — the test-only
        # subclass — executes an uncited request through the offline
        # fakes (pinned in test_v2_execution_service.py).
        self.assertIsNone(_request().validation_run_id)
        self.assertIsNone(_request(validation_run_id=None).validation_run_id)

    def test_a_cited_validation_run_is_validated_like_an_opaque_id(self) -> None:
        for bad in ("", "   ", 42, "x" * 257, 3.5, True):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    _request(validation_run_id=bad)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            _request(validation_run_id=_V1_FROZEN_DOCKER_IMAGE_DIGEST)


if __name__ == "__main__":
    unittest.main()
