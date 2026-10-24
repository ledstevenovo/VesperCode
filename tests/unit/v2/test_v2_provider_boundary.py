"""Route B / B4b-02C1: the composed provider call boundary.

Composes the three production pieces of the provider plane over a
real v2 control database: the B2 ``V2ProviderCallService`` (the
authoritative one-shot consume gate), the B4b-02C1 OS credential
adapter over a deterministic fake backend, and the B4b-02C1 real
transport adapter over a deterministic fake HTTP edge.  Everything is
offline: no real OS store, no real network call.

Pins the composed call order and its security consequences:

- a safe backend end-to-end call succeeds: the authorization is
  consumed atomically BEFORE exactly one transport call, the edge
  receives the derived trusted URL, the Bearer credential, the
  bounded control body, and the closed timeout;
- a missing credential rejects with the closed
  ``CREDENTIAL_NOT_CONFIGURED`` code BEFORE the consume: nothing is
  burned, nothing is called;
- an unavailable or unsafe OS backend fails closed BEFORE the consume:
  the closed store error propagates loudly (an infrastructure
  failure is never silently mapped to a business outcome), no
  authorization is burned, no transport is touched;
- a timeout, a redirect, a non-success response, or an edge exception
  maps to the closed ``PROVIDER_CALL_FAILED`` code with the static
  message — exactly one edge call, no retry, no refund (the burned
  authorization stays consumed), and the secret never appears in any
  outcome, exception text, or database byte;
- the real transport adapter independently rechecks its own
  endpoint/provider/profile binding AFTER the service's checks, so a
  call that drifts past the service gate still never reaches the edge.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vespercode.credentials.v2_os_store import (
    OSV2CredentialProvider,
    V2OSCredentialStoreError,
)
from vespercode.credentials.v2_port import (
    V2CredentialSecret,
    _provider_reveal_capability,
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
    V2ProviderCallService,
)
from vespercode.providers.v2_transport import (
    V2ProviderHttpResult,
    V2ProviderTransportAdapter,
)
from vespercode.storage.v2_database import (
    V2_DATABASE_FILENAME,
    initialize_v2_database,
    open_v2_database,
)

_SECRET = "v2-boundary-test-secret-0001"
_FUTURE = "2030-01-01T00:00:00+00:00"
_OPENAI_URL = "https://api.openai.com:443/v1/chat/completions"
_OPENAI_SERVICE = "vespercode/v2/credential/OPENAI"
_PROBE_SERVICE = "vespercode/v2/probe"


class FakeOSBackend:
    """Deterministic simulation of the OS credential store (test double)."""

    def __init__(
        self, *, probe_failure: str | None = None, unavailable: bool = False
    ) -> None:
        self.entries: dict[str, tuple[str, str, int]] = {}
        self.probe_calls = 0
        self.write_calls: list[tuple[str, str]] = []
        self.deletes: list[str] = []
        self._probe_failure = probe_failure
        self._unavailable = unavailable
        self._clock_ms = 1_700_000_000_000

    def _gate(self) -> None:
        if self._unavailable:
            raise V2OSCredentialStoreError("CREDENTIAL_BACKEND_UNAVAILABLE")
        if self._probe_failure == "UNSAFE":
            raise V2OSCredentialStoreError("CREDENTIAL_BACKEND_UNSAFE")

    def backend_id(self) -> str:
        if self._unavailable:
            raise V2OSCredentialStoreError("CREDENTIAL_BACKEND_UNAVAILABLE")
        return "WINDOWS_CREDENTIAL_MANAGER"

    def probe_cycle(self) -> None:
        self._gate()
        self.entries[_PROBE_SERVICE] = (
            "capability-probe",
            "vespercode-v2-probe",
            self._clock_ms,
        )
        self.entries.pop(_PROBE_SERVICE, None)
        self.probe_calls += 1

    def write(self, service: str, username: str, secret: str) -> None:
        self._gate()
        self._clock_ms += 1_000
        self.entries[service] = (username, secret, self._clock_ms)
        self.write_calls.append((service, username))

    def read_metadata(self, service: str, username: str) -> int | None:
        self._gate()
        entry = self.entries.get(service)
        if entry is None:
            return None
        stored_username, _, last_written_ms = entry
        if stored_username != username:
            raise V2OSCredentialStoreError("CREDENTIAL_STORE_FAILED")
        return last_written_ms

    def read_value(self, service: str, username: str) -> str | None:
        self._gate()
        entry = self.entries.get(service)
        if entry is None:
            return None
        stored_username, value, _ = entry
        if stored_username != username:
            raise V2OSCredentialStoreError("CREDENTIAL_STORE_FAILED")
        return value

    def delete(self, service: str) -> None:
        self._gate()
        self.deletes.append(service)
        self.entries.pop(service, None)


class FakeEdge:
    """Deterministic injectable HTTP edge (test double, offline)."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        body: bytes = b"{}",
        error: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self._status_code = status_code
        self._body = body
        self._error = error

    def post(
        self,
        *,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: int,
    ) -> "V2ProviderHttpResult":
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "body": body,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self._error is not None:
            raise self._error
        from vespercode.providers.v2_transport import V2ProviderHttpResult

        return V2ProviderHttpResult(status_code=self._status_code, body=self._body)


class ComposedProviderBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self.database_path = self.root / V2_DATABASE_FILENAME
        initialize_v2_database(self.database_path)
        self.database = open_v2_database(self.database_path)
        self.profile = ReferenceProfileRecordV2(
            "profile-1", 3, "3.12.4", "8.4.2", "0.16.1", "2.3.0"
        )
        self.database.create_reference_profile(self.profile)
        self.endpoint = ProviderEndpointRecordV2("endpoint-1", "OPENAI", "profile-1", 3)
        self.database.create_provider_endpoint(self.endpoint)
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
        self.authorization_id = self._authorize("request-1", "endpoint-1")
        self.backend = FakeOSBackend()
        self.credentials = OSV2CredentialProvider(self.backend)
        self.credentials.set("OPENAI", V2CredentialSecret.from_hidden_input(_SECRET))
        self.edge = FakeEdge()
        self.adapter = V2ProviderTransportAdapter(
            endpoint=self.endpoint, profile=self.profile, http_edge=self.edge
        )
        self.service = V2ProviderCallService(
            self.database, self.credentials, self.adapter
        )

    def tearDown(self) -> None:
        self.database.close()
        self._directory.cleanup()

    def _authorize(self, request_id: str, endpoint_id: str) -> str:
        outcome = self.database.authorize_disclosure_request(
            grant_id=self.grant_id,
            run_id=self.run_id,
            request_id=request_id,
            endpoint_id=endpoint_id,
            charge_bytes=10,
            sources=(DisclosureSourceV2("FILE_CONTENT", "src/app.py"),),
        )
        self.assertEqual(outcome.kind, "AUTHORIZED")
        return outcome.authorization.authorization_id

    def _request(
        self, *, request_id: str = "request-1", endpoint_id: str = "endpoint-1"
    ) -> ProviderCallRequestV2:
        authorization_id = self.authorization_id
        if request_id != "request-1":
            authorization_id = self._authorize(request_id, endpoint_id)
        return ProviderCallRequestV2(
            request_id=request_id,
            authorization_id=authorization_id,
            grant_id=self.grant_id,
            run_id=self.run_id,
            endpoint_id=endpoint_id,
            provider="OPENAI",
            reference_profile_id="profile-1",
            reference_profile_revision=3,
        )

    def _authorization_status(self, authorization_id: str) -> str:
        record = self.database.get_disclosure_authorization(authorization_id)
        assert record is not None
        return record.status

    # ------------------------------------------------------------------
    # The safe-backend end-to-end call
    # ------------------------------------------------------------------

    def test_a_safe_backend_end_to_end_call_succeeds(self) -> None:
        outcome = self.service.call(self._request())
        self.assertEqual(outcome.status, "SUCCEEDED")
        self.assertIsNone(outcome.error_code)
        self.assertEqual(outcome.message, "the provider call completed")
        # Exactly one edge call, to the derived trusted URL, with the
        # revealed credential in the Bearer header and the closed
        # timeout — and the authorization is consumed.
        self.assertEqual(len(self.edge.calls), 1)
        call = self.edge.calls[0]
        self.assertEqual(call["url"], _OPENAI_URL)
        self.assertEqual(call["headers"]["Authorization"], f"Bearer {_SECRET}")
        self.assertEqual(call["headers"].get("Content-Type"), "application/json")
        self.assertEqual(call["timeout_seconds"], 60)
        self.assertEqual(self._authorization_status(self.authorization_id), "CONSUMED")

    def test_the_round_tripped_credential_is_the_os_stored_value(self) -> None:
        # The value that reaches the edge is the one the OS-backed
        # provider read fresh from the backend — proving the storage
        # and read paths round-trip through the wrapper boundary.
        self.service.call(self._request())
        assert self.backend.entries[_OPENAI_SERVICE][1] == _SECRET
        call = self.edge.calls[0]
        self.assertEqual(call["headers"]["Authorization"], f"Bearer {_SECRET}")

    # ------------------------------------------------------------------
    # Credential failures: before the consume, nothing burned
    # ------------------------------------------------------------------

    def test_a_missing_credential_rejects_without_consuming(self) -> None:
        self.credentials.clear("OPENAI")
        outcome = self.service.call(self._request())
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "CREDENTIAL_NOT_CONFIGURED")
        self.assertEqual(self.edge.calls, [])
        self.assertEqual(
            self._authorization_status(self.authorization_id), "AUTHORIZED"
        )

    def test_an_unsafe_backend_fails_closed_before_the_consume(self) -> None:
        backend = FakeOSBackend(probe_failure="UNSAFE")
        credentials = OSV2CredentialProvider(backend)
        service = V2ProviderCallService(self.database, credentials, self.adapter)
        with self.assertRaises(V2OSCredentialStoreError) as caught:
            service.call(self._request())
        self.assertEqual(caught.exception.code, "CREDENTIAL_BACKEND_UNSAFE")
        self.assertNotIn(_SECRET, str(caught.exception))
        self.assertEqual(self.edge.calls, [])
        self.assertEqual(
            self._authorization_status(self.authorization_id), "AUTHORIZED"
        )

    def test_an_unavailable_backend_fails_closed_before_the_consume(self) -> None:
        backend = FakeOSBackend(unavailable=True)
        credentials = OSV2CredentialProvider(backend)
        service = V2ProviderCallService(self.database, credentials, self.adapter)
        with self.assertRaises(V2OSCredentialStoreError) as caught:
            service.call(self._request())
        self.assertEqual(caught.exception.code, "CREDENTIAL_BACKEND_UNAVAILABLE")
        self.assertEqual(self.edge.calls, [])
        self.assertEqual(
            self._authorization_status(self.authorization_id), "AUTHORIZED"
        )

    # ------------------------------------------------------------------
    # Transport failures: one call, no retry, no refund, redaction
    # ------------------------------------------------------------------

    def _failing_service(self, edge: FakeEdge) -> V2ProviderCallService:
        adapter = V2ProviderTransportAdapter(
            endpoint=self.endpoint, profile=self.profile, http_edge=edge
        )
        return V2ProviderCallService(self.database, self.credentials, adapter)

    def test_a_timeout_fails_the_call_with_no_refund(self) -> None:
        edge = FakeEdge(error=TimeoutError("the connection timed out"))
        outcome = self._failing_service(edge).call(self._request())
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "PROVIDER_CALL_FAILED")
        self.assertEqual(outcome.message, PROVIDER_CALL_FAILED_MESSAGE)
        self.assertEqual(len(edge.calls), 1)
        self.assertEqual(self._authorization_status(self.authorization_id), "CONSUMED")

    def test_a_redirect_fails_the_call_without_a_follow(self) -> None:
        edge = FakeEdge(status_code=302)
        outcome = self._failing_service(edge).call(self._request())
        self.assertEqual(outcome.error_code, "PROVIDER_CALL_FAILED")
        self.assertEqual(len(edge.calls), 1)
        self.assertEqual(self._authorization_status(self.authorization_id), "CONSUMED")

    def test_a_non_success_response_fails_with_no_refund(self) -> None:
        edge = FakeEdge(status_code=503)
        outcome = self._failing_service(edge).call(self._request())
        self.assertEqual(outcome.error_code, "PROVIDER_CALL_FAILED")
        self.assertEqual(len(edge.calls), 1)
        self.assertEqual(self._authorization_status(self.authorization_id), "CONSUMED")

    def test_an_edge_exception_is_redacted_end_to_end(self) -> None:
        edge = FakeEdge(error=RuntimeError(f"leaked Authorization: Bearer {_SECRET}"))
        outcome = self._failing_service(edge).call(self._request())
        self.assertEqual(outcome.error_code, "PROVIDER_CALL_FAILED")
        self.assertEqual(outcome.message, PROVIDER_CALL_FAILED_MESSAGE)
        self.assertNotIn(_SECRET, outcome.message)
        self.assertNotIn(_SECRET, repr(outcome))
        self.assertNotIn(_SECRET, str(outcome))
        self.assertEqual(len(edge.calls), 1)

    def test_exactly_one_call_per_authorization_even_on_failure(self) -> None:
        edge = FakeEdge(error=RuntimeError("transient"))
        service = self._failing_service(edge)
        first = service.call(self._request())
        self.assertEqual(first.error_code, "PROVIDER_CALL_FAILED")
        self.assertEqual(len(edge.calls), 1)
        # The burned authorization is never refunded: the retry
        # rejects without a second edge call.
        second = service.call(self._request())
        self.assertEqual(second.error_code, "AUTHORIZATION_NOT_AUTHORIZED")
        self.assertEqual(len(edge.calls), 1)

    # ------------------------------------------------------------------
    # The adapter's independent binding recheck after the service gate
    # ------------------------------------------------------------------

    def test_a_binding_drift_past_the_service_burns_without_calling(self) -> None:
        # The request cites a second, legitimately declared endpoint
        # (same provider/profile binding), so every service-level
        # check passes — but the adapter is bound to endpoint-1 and
        # independently rechecks its own binding after the consume.
        self.database.create_provider_endpoint(
            ProviderEndpointRecordV2("endpoint-9", "OPENAI", "profile-1", 3)
        )
        authorization_id = self._authorize("request-2", "endpoint-9")
        request = ProviderCallRequestV2(
            request_id="request-2",
            authorization_id=authorization_id,
            grant_id=self.grant_id,
            run_id=self.run_id,
            endpoint_id="endpoint-9",
            provider="OPENAI",
            reference_profile_id="profile-1",
            reference_profile_revision=3,
        )
        outcome = self.service.call(request)
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "PROVIDER_CALL_FAILED")
        self.assertEqual(self.edge.calls, [])
        # No refund: the consume committed before the transport call.
        self.assertEqual(self._authorization_status(authorization_id), "CONSUMED")

    # ------------------------------------------------------------------
    # The secret never enters the control database
    # ------------------------------------------------------------------

    def test_the_credential_never_enters_the_control_database(self) -> None:
        self.service.call(self._request())
        self._failing_service(
            FakeEdge(error=RuntimeError(f"boom with {_SECRET}"))
        ).call(self._request(request_id="request-3"))
        # The raw database file bytes (and any journal siblings) carry
        # no byte of the secret, and neither does any row.
        paths = [
            self.database_path,
            Path(str(self.database_path) + "-journal"),
            Path(str(self.database_path) + "-wal"),
            Path(str(self.database_path) + "-shm"),
        ]
        for path in paths:
            if path.exists():
                self.assertNotIn(
                    _SECRET.encode("utf-8"),
                    path.read_bytes(),
                    f"the secret leaked into {path.name}",
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

    def test_the_composed_projections_stay_non_revealing(self) -> None:
        self.service.call(self._request())
        status = self.credentials.status("OPENAI")
        self.assertTrue(status.configured)
        self.assertNotIn(_SECRET, repr(status))
        wrapper = self.credentials.get_for_call("OPENAI")
        assert wrapper is not None
        self.assertEqual(wrapper.reveal(_provider_reveal_capability()), _SECRET)
        self.assertNotIn(_SECRET, repr(wrapper))
        self.assertEqual(repr(wrapper), "V2CredentialSecret([redacted])")


if __name__ == "__main__":
    unittest.main()
