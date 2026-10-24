"""Route B / B2 (+ B4b-02C1): the provider call request/response boundary.

The v1 provider path (``profiles/endpoints.py``, the v1 CLI credential
flow, and the v1 release workflow) is digest-bound and remains untouched
read-only legacy; nothing here imports it and no v1 CLI/release path is
turned into a v2 provider path.

The v2 provider call boundary is one deterministic service over the
injectable pieces: the control database (endpoint, authorization, grant),
the injectable credential port, and an injectable transport.  The request
and outcome records carry control IDs and revisions only.  The
credential never flows to the transport as a raw string: after the
atomic consume the service mints the provider-only call credential
(``V2ProviderCallCredential`` — redacted, non-comparable,
non-serializable, single-use, minted only behind the provider-call
capability) and passes that object to the one transport call; the raw
value materializes only inside the real transport adapter's single
call frame, through the transport-reveal seam granted to exactly that
module, and never enters a record, an outcome, an exception, or a
database row.  The service consumes the authorization one-shot *before*
the transport call (so a duplicate call can never double-call the
provider), performs exactly one transport call, never retries on
failure, and maps any transport exception or failure response to a
closed error code with a static message.
"""

from __future__ import annotations

import copy
import pickle
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from vespercode.credentials.v2_port import (
    InMemoryV2CredentialProvider,
    V2CredentialError,
    V2CredentialSecret,
    _provider_reveal_capability,
    _RevealCapability,
    _storage_reveal_capability,
    _StorageCapability,
)
from vespercode.governance.v2_disclosure import (
    DisclosurePathScopeV2,
    DisclosureSourceV2,
)
from vespercode.profiles.v2_endpoints import ProviderEndpointRecordV2
from vespercode.profiles.v2_reference import ReferenceProfileRecordV2
from vespercode.providers.v2_call import (
    PROVIDER_CALL_FAILED_MESSAGE,
    ProviderCallRequestV2,
    ProviderCallResponseV2,
    V2ProviderCallCredential,
    V2ProviderCallService,
    _transport_reveal_capability,
    _TransportRevealCapability,
)
from vespercode.storage.v2_database import (
    V2_DATABASE_FILENAME,
    initialize_v2_database,
    open_v2_database,
)

_SECRET = "v2-provider-call-secret-0001"
_FUTURE = "2030-01-01T00:00:00+00:00"


class _Transport:
    """Deterministic injectable fake provider transport.

    Records the control request and the provider-only call credential
    it received (the service-minted handshake object — never a raw
    string) so the boundary tests can assert exactly one call with
    the right inputs.
    """

    def __init__(
        self,
        *,
        response: ProviderCallResponseV2 | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[tuple[ProviderCallRequestV2, V2ProviderCallCredential]] = []
        self._response = response
        self._error = error

    def call(
        self, request: ProviderCallRequestV2, credential: V2ProviderCallCredential
    ) -> ProviderCallResponseV2:
        self.calls.append((request, credential))
        if self._error is not None:
            raise self._error
        if self._response is not None:
            return self._response
        return ProviderCallResponseV2("SUCCEEDED")


class V2ProviderCallCredentialTests(unittest.TestCase):
    """B4b-02C1 review fix: the provider-only call credential handshake.

    The main-thread review rejected the first cut's raw-string transport
    API: any caller holding a raw secret could drive the real transport
    adapter directly, bypassing the service's authorization/consume
    boundary.  The handshake object fixes that shape: minting requires
    the provider-call boundary capability (held only by the provider
    call service), opening requires the separately minted
    transport-reveal capability (handed only to the real transport
    adapter), and the object is redacted, non-comparable,
    non-serializable, and single-use.
    """

    def _mint(self) -> V2ProviderCallCredential:
        return V2ProviderCallCredential(
            V2CredentialSecret.from_hidden_input(_SECRET),
            _provider_reveal_capability(),
        )

    def test_minting_requires_the_provider_call_boundary_capability(self) -> None:
        secret = V2CredentialSecret.from_hidden_input(_SECRET)
        # Direct ordinary use — no capability argument — is rejected.
        with self.assertRaises(TypeError):
            V2ProviderCallCredential(secret)  # type: ignore[call-arg]
        for wrong in (
            None,
            "",
            "capability",
            123,
            object(),
            _RevealCapability(),
            _storage_reveal_capability(),
            _TransportRevealCapability(),
        ):
            with self.subTest(wrong=wrong):
                with self.assertRaises(V2CredentialError) as caught:
                    V2ProviderCallCredential(secret, wrong)
                self.assertEqual(
                    caught.exception.error_code, "CREDENTIAL_REVEAL_FORBIDDEN"
                )
        credential = V2ProviderCallCredential(secret, _provider_reveal_capability())
        self.assertEqual(
            credential.reveal_for_transport(_transport_reveal_capability()),
            _SECRET,
        )

    def test_minting_requires_a_real_secret_wrapper(self) -> None:
        for hostile in (None, "raw-secret", 123, object()):
            with self.subTest(hostile=hostile):
                with self.assertRaises(V2CredentialError):
                    V2ProviderCallCredential(
                        hostile,  # type: ignore[arg-type]
                        _provider_reveal_capability(),
                    )

    def test_the_transport_reveal_requires_the_exact_transport_capability(
        self,
    ) -> None:
        credential = self._mint()
        # Direct ordinary use — no capability argument — is rejected.
        with self.assertRaises(TypeError):
            credential.reveal_for_transport()  # type: ignore[call-arg]
        for wrong in (
            None,
            "",
            "capability",
            123,
            object(),
            _RevealCapability(),
            _provider_reveal_capability(),
            _storage_reveal_capability(),
            _TransportRevealCapability(),
        ):
            with self.subTest(wrong=wrong):
                with self.assertRaises(V2CredentialError) as caught:
                    credential.reveal_for_transport(wrong)
                self.assertEqual(
                    caught.exception.error_code, "CREDENTIAL_REVEAL_FORBIDDEN"
                )
        self.assertEqual(
            credential.reveal_for_transport(_transport_reveal_capability()),
            _SECRET,
        )

    def test_the_call_credential_is_single_use(self) -> None:
        credential = self._mint()
        self.assertEqual(
            credential.reveal_for_transport(_transport_reveal_capability()),
            _SECRET,
        )
        # A retained or replayed credential never yields a second raw
        # value — exactly one reveal per minted credential.
        with self.assertRaises(V2CredentialError) as caught:
            credential.reveal_for_transport(_transport_reveal_capability())
        self.assertEqual(caught.exception.error_code, "CREDENTIAL_REVEAL_FORBIDDEN")

    def test_the_capabilities_are_not_interchangeable(self) -> None:
        secret = V2CredentialSecret.from_hidden_input(_SECRET)
        # The mint capability never unlocks the wrapper's own reveal...
        with self.assertRaises(V2CredentialError) as caught:
            secret.reveal(_transport_reveal_capability())
        self.assertEqual(caught.exception.error_code, "CREDENTIAL_REVEAL_FORBIDDEN")
        # ...the mint capability never unlocks the transport reveal...
        credential = self._mint()
        with self.assertRaises(V2CredentialError):
            credential.reveal_for_transport(_provider_reveal_capability())
        # ...and fresh look-alike instances of the private classes never
        # unlock anything.
        self.assertIsNot(_TransportRevealCapability(), _transport_reveal_capability())
        self.assertIsNot(_provider_reveal_capability(), _transport_reveal_capability())
        self.assertIsNot(_StorageCapability(), _storage_reveal_capability())

    def test_the_call_credential_is_redacted(self) -> None:
        credential = self._mint()
        self.assertEqual(repr(credential), "V2ProviderCallCredential([redacted])")
        self.assertEqual(str(credential), "V2ProviderCallCredential([redacted])")
        self.assertNotIn(_SECRET, repr(credential))
        self.assertNotIn(_SECRET, str(credential))
        for name in dir(credential):
            if name.startswith("_"):
                continue
            attribute = getattr(credential, name, None)
            if isinstance(attribute, str):
                self.assertNotIn(_SECRET, attribute, name)

    def test_the_call_credential_is_not_comparable(self) -> None:
        first = self._mint()
        second = self._mint()
        with self.assertRaises(TypeError):
            first == second  # type: ignore[override]
        with self.assertRaises(TypeError):
            first != second  # type: ignore[override]

    def test_the_call_credential_is_not_serializable_or_copyable(self) -> None:
        credential = self._mint()
        with self.assertRaises(TypeError):
            copy.copy(credential)
        with self.assertRaises(TypeError):
            copy.deepcopy(credential)
        with self.assertRaises(TypeError):
            pickle.dumps(credential)
        with self.assertRaises(TypeError):
            credential.__reduce__()

    def test_the_transport_capability_is_absent_from_the_public_surface(
        self,
    ) -> None:
        module = sys.modules[V2ProviderCallCredential.__module__]
        capability = _transport_reveal_capability()
        for name in dir(module):
            if name.startswith("_"):
                continue
            self.assertIsNot(getattr(module, name), capability, name)
        from vespercode.providers import v2_call

        for exported in v2_call.__all__:
            self.assertFalse(
                "capab" in exported.lower() or "reveal" in exported.lower(),
                f"capability-like public export: {exported}",
            )

    def test_a_forged_instance_without_minted_state_rejects(self) -> None:
        # The cheap forgery path — ``__new__`` without the minted
        # slots — yields an object whose transport reveal is closed.
        forged = V2ProviderCallCredential.__new__(V2ProviderCallCredential)
        with self.assertRaises(V2CredentialError) as caught:
            forged.reveal_for_transport(_transport_reveal_capability())
        self.assertEqual(caught.exception.error_code, "CREDENTIAL_REVEAL_FORBIDDEN")


class V2ProviderCallTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self.database_path = self.root / V2_DATABASE_FILENAME
        initialize_v2_database(self.database_path)
        self.database = open_v2_database(self.database_path)
        self.database.create_reference_profile(
            ReferenceProfileRecordV2(
                "profile-1", 3, "3.12.4", "8.4.2", "0.16.1", "2.3.0"
            )
        )
        self.run_id = self.database.create_run(str(self.root))
        disclosure_id = self.database.create_disclosure(self.run_id)
        self.grant_id = self.database.create_disclosure_grant(
            run_id=self.run_id,
            disclosure_id=disclosure_id,
            reference_profile_id="profile-1",
            reference_profile_revision=3,
            expires_at=_FUTURE,
            byte_budget=1000,
            allowed_source_categories=("FILE_CONTENT", "TASK"),
            allowed_source_paths=(DisclosurePathScopeV2("ROOT", ""),),
        )
        self.assertTrue(self.database.activate_disclosure_grant(self.grant_id))
        self.database.create_provider_endpoint(
            ProviderEndpointRecordV2("endpoint-1", "OPENAI", "profile-1", 3)
        )
        outcome = self.database.authorize_disclosure_request(
            grant_id=self.grant_id,
            run_id=self.run_id,
            request_id="request-1",
            endpoint_id="endpoint-1",
            charge_bytes=10,
            sources=(DisclosureSourceV2("FILE_CONTENT", "src/app.py"),),
        )
        self.assertEqual(outcome.kind, "AUTHORIZED")
        self.authorization_id = outcome.authorization.authorization_id
        self.credentials = InMemoryV2CredentialProvider()
        self.credentials.set("OPENAI", V2CredentialSecret.from_hidden_input(_SECRET))
        self.transport = _Transport()
        self.service = V2ProviderCallService(
            self.database, self.credentials, self.transport
        )

    def tearDown(self) -> None:
        self.database.close()
        self._directory.cleanup()

    def _request(self, **overrides: object) -> ProviderCallRequestV2:
        values: dict[str, object] = {
            "request_id": "request-1",
            "authorization_id": self.authorization_id,
            "grant_id": self.grant_id,
            "run_id": self.run_id,
            "endpoint_id": "endpoint-1",
            "provider": "OPENAI",
            "reference_profile_id": "profile-1",
            "reference_profile_revision": 3,
        }
        values.update(overrides)
        return ProviderCallRequestV2(**values)  # type: ignore[arg-type]

    def _call(self, request: ProviderCallRequestV2):
        return self.service.call(request)

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_a_successful_call_consumes_the_authorization_once(self) -> None:
        outcome = self._call(self._request())
        self.assertEqual(outcome.request_id, "request-1")
        self.assertEqual(outcome.status, "SUCCEEDED")
        self.assertIsNone(outcome.error_code)
        self.assertEqual(len(self.transport.calls), 1)
        seen_request, seen_credential = self.transport.calls[0]
        self.assertIsInstance(seen_request, ProviderCallRequestV2)
        self.assertEqual(seen_request.authorization_id, self.authorization_id)
        # The service passes the provider-only call credential — never
        # a raw string — and it carries exactly the configured secret,
        # openable only through the transport-reveal seam.
        self.assertIsInstance(seen_credential, V2ProviderCallCredential)
        self.assertEqual(
            seen_credential.reveal_for_transport(_transport_reveal_capability()),
            _SECRET,
        )
        authorization = self.database.get_disclosure_authorization(
            self.authorization_id
        )
        self.assertEqual(authorization.status, "CONSUMED")

    def test_a_consumed_authorization_rejects_a_second_call(self) -> None:
        self._call(self._request())
        outcome = self._call(self._request())
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "AUTHORIZATION_NOT_AUTHORIZED")
        self.assertEqual(len(self.transport.calls), 1)

    # ------------------------------------------------------------------
    # Rejections before the credential or the transport are touched
    # ------------------------------------------------------------------

    def test_an_unknown_endpoint_rejects_before_any_call(self) -> None:
        outcome = self._call(self._request(endpoint_id="endpoint-missing"))
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "ENDPOINT_NOT_FOUND")
        self.assertEqual(self.transport.calls, [])

    def test_a_profile_binding_mismatch_rejects_before_any_call(self) -> None:
        # The request cites a different reference profile revision.
        stale = self._call(self._request(reference_profile_revision=2))
        self.assertEqual(stale.status, "FAILED")
        self.assertEqual(stale.error_code, "PROFILE_MISMATCH")
        # The request cites a different provider than the endpoint declares.
        provider = self._call(self._request(provider="OTHER"))
        self.assertEqual(provider.status, "FAILED")
        self.assertEqual(provider.error_code, "PROFILE_MISMATCH")
        self.assertEqual(self.transport.calls, [])

    def test_an_unknown_or_misbound_authorization_rejects_before_any_call(self) -> None:
        missing = self._call(self._request(authorization_id="auth-missing"))
        self.assertEqual(missing.status, "FAILED")
        self.assertEqual(missing.error_code, "AUTHORIZATION_NOT_FOUND")
        for overrides in (
            {"grant_id": "grant-wrong"},
            {"run_id": "run-wrong"},
            {"request_id": "request-wrong"},
            {"endpoint_id": "endpoint-9"},
        ):
            with self.subTest(overrides=overrides):
                request = self._request(**overrides)
                # Keep the endpoint binding check from masking the test's
                # target: only valid endpoint ids reach the binding check.
                if overrides.get("endpoint_id") == "endpoint-9":
                    self.database.create_provider_endpoint(
                        ProviderEndpointRecordV2("endpoint-9", "OPENAI", "profile-1", 3)
                    )
                outcome = self._call(request)
                self.assertEqual(outcome.status, "FAILED")
                self.assertEqual(
                    outcome.error_code,
                    "AUTHORIZATION_BINDING_MISMATCH",
                )
        self.assertEqual(self.transport.calls, [])

    def test_a_not_active_grant_rejects_before_any_call(self) -> None:
        self.assertTrue(self.database.revoke_disclosure_grant(self.grant_id))
        outcome = self._call(self._request())
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "GRANT_NOT_ACTIVE")
        self.assertEqual(self.transport.calls, [])
        # The authorization stays AUTHORIZED: no burn on a policy rejection.
        self.assertEqual(
            self.database.get_disclosure_authorization(self.authorization_id).status,
            "AUTHORIZED",
        )

    def test_an_expired_grant_rejects_before_any_call(self) -> None:
        service = V2ProviderCallService(
            self.database,
            self.credentials,
            self.transport,
            clock=lambda: datetime(2031, 1, 1, tzinfo=timezone.utc),
        )
        outcome = service.call(self._request())
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "GRANT_NOT_ACTIVE")
        self.assertEqual(self.transport.calls, [])

    # ------------------------------------------------------------------
    # Credential boundary
    # ------------------------------------------------------------------

    def test_a_missing_credential_rejects_without_consuming(self) -> None:
        self.credentials.clear("OPENAI")
        outcome = self._call(self._request())
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "CREDENTIAL_NOT_CONFIGURED")
        self.assertEqual(self.transport.calls, [])
        # The authorization is not burned by a missing credential.
        self.assertEqual(
            self.database.get_disclosure_authorization(self.authorization_id).status,
            "AUTHORIZED",
        )

    def test_revocation_between_the_grant_read_and_the_consume_blocks_the_call(
        self,
    ) -> None:
        # A hostile credential store mutates the control plane between
        # the service's grant read and its consume: the atomic consume
        # revalidation must reject with zero transport calls and no
        # burned authorization.
        class _RevokingCredentialProvider(InMemoryV2CredentialProvider):
            def __init__(self, database: object, grant_id: str) -> None:
                super().__init__()
                self._revoking_database = database
                self._revoking_grant_id = grant_id

            def get_for_call(self, provider: str):
                self._revoking_database.revoke_disclosure_grant(  # type: ignore[attr-defined]
                    self._revoking_grant_id
                )
                return super().get_for_call(provider)

        credentials = _RevokingCredentialProvider(self.database, self.grant_id)
        credentials.set("OPENAI", V2CredentialSecret.from_hidden_input(_SECRET))
        service = V2ProviderCallService(self.database, credentials, self.transport)
        outcome = service.call(self._request())
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "GRANT_NOT_ACTIVE")
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(
            self.database.get_disclosure_authorization(self.authorization_id).status,
            "AUTHORIZED",
        )
        # A retry cannot double-call the provider or consume anything.
        retry = service.call(self._request())
        self.assertEqual(retry.error_code, "GRANT_NOT_ACTIVE")
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(
            self.database.get_disclosure_authorization(self.authorization_id).status,
            "AUTHORIZED",
        )

    def test_expiry_crossing_between_the_read_and_the_consume_blocks_the_call(
        self,
    ) -> None:
        # The injected clock crosses the grant expiry between the
        # service's grant check and its consume-time recheck.
        times = iter(
            [
                datetime(2029, 1, 1, tzinfo=timezone.utc),
                datetime(2031, 1, 1, tzinfo=timezone.utc),
            ]
        )
        service = V2ProviderCallService(
            self.database,
            self.credentials,
            self.transport,
            clock=lambda: next(times),
        )
        outcome = service.call(self._request())
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "GRANT_NOT_ACTIVE")
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(
            self.database.get_disclosure_authorization(self.authorization_id).status,
            "AUTHORIZED",
        )

    # ------------------------------------------------------------------
    # Failure handling: one call, no retry, sanitized outcome
    # ------------------------------------------------------------------

    def test_a_transport_exception_never_reaches_the_outcome(self) -> None:
        transport = _Transport(
            error=RuntimeError(f"upstream rejected Authorization: Bearer {_SECRET}")
        )
        service = V2ProviderCallService(self.database, self.credentials, transport)
        outcome = service.call(self._request())
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "PROVIDER_CALL_FAILED")
        self.assertEqual(outcome.message, PROVIDER_CALL_FAILED_MESSAGE)
        self.assertNotIn(_SECRET, outcome.message)
        self.assertNotIn(_SECRET, repr(outcome))
        self.assertNotIn(_SECRET, str(outcome))
        # Exactly one call: no automatic retry on provider error.
        self.assertEqual(len(transport.calls), 1)

    def test_a_failure_response_maps_to_the_same_closed_failure(self) -> None:
        transport = _Transport(response=ProviderCallResponseV2("FAILED"))
        service = V2ProviderCallService(self.database, self.credentials, transport)
        outcome = service.call(self._request())
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "PROVIDER_CALL_FAILED")
        self.assertEqual(outcome.message, PROVIDER_CALL_FAILED_MESSAGE)
        self.assertEqual(len(transport.calls), 1)
        # The one-shot authorization is burned by the attempted call.
        self.assertEqual(
            self.database.get_disclosure_authorization(self.authorization_id).status,
            "CONSUMED",
        )

    def test_the_credential_value_never_enters_the_control_database(self) -> None:
        self._call(self._request())
        service = V2ProviderCallService(
            self.database,
            self.credentials,
            _Transport(error=RuntimeError(f"boom with {_SECRET}")),
        )
        second = self.database.authorize_disclosure_request(
            grant_id=self.grant_id,
            run_id=self.run_id,
            request_id="request-2",
            endpoint_id="endpoint-1",
            charge_bytes=10,
            sources=(DisclosureSourceV2("FILE_CONTENT", "src/other.py"),),
        )
        self.assertEqual(second.kind, "AUTHORIZED")
        service.call(
            self._request(
                request_id="request-2",
                authorization_id=second.authorization.authorization_id,
            )
        )
        connection = self.database._connection
        tables = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        ]
        for table in tables:
            for row in connection.execute(f'SELECT * FROM "{table}"').fetchall():
                self.assertNotIn(
                    _SECRET,
                    repr(tuple(row)),
                    f"the secret leaked into table {table}",
                )

    def test_outcome_messages_are_static_and_bounded(self) -> None:
        outcome = self._call(self._request(endpoint_id="endpoint-missing"))
        self.assertTrue(outcome.message)
        self.assertLessEqual(len(outcome.message), 200)


if __name__ == "__main__":
    unittest.main()
