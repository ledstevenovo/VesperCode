"""Route B / B4b-02C1: the real provider transport adapter.

The v1 transport (``llm/openai_adapter.py`` over the pydantic-bound
``profiles/endpoints.py`` map) is digest-bound legacy and remains
untouched read-only legacy; nothing here imports it.

The v2 real transport adapter (``providers/v2_transport.py``) is the
production implementation of the B2 ``V2ProviderTransport`` protocol
for the declared provider endpoint/profile only:

- construction is closed: it accepts exactly the v2 endpoint record,
  the reference profile record it must bind, and an optional
  injectable HTTP edge — never a URL, ``base_url``, header set, argv,
  or shell input; the URL derives only from the closed built-in
  provider address map (the sole declared provider is ``OPENAI`` at
  ``https://api.openai.com:443/v1/chat/completions``);
- the request body is the bounded deterministic control-plane
  projection of the call request (control IDs and revisions only —
  never file content, task text, or the credential), and a request
  whose projection exceeds the closed bound fails before the edge is
  ever touched;
- the adapter passes the closed timeout to the edge, performs exactly
  one edge call, never retries, never follows a redirect, discards
  every edge exception, and reduces every non-success status or
  over-bound response body to the closed ``FAILED`` response — the
  response body and the credential never enter any response, outcome,
  or retained state;
- the real HTTP edge is the isolated network edge of the v2 provider
  plane (lazy ``httpx`` import inside the call, streaming read that
  aborts at the closed body bound, no redirect follow); the offline
  unit tests below exercise the adapter through the deterministic fake
  edge only and never make a real network call.
"""

from __future__ import annotations

import ast
import inspect
import json
import sys
import unittest
from dataclasses import fields
from pathlib import Path

from vespercode.credentials.v2_port import (
    V2CredentialSecret,
    _provider_reveal_capability,
)
from vespercode.profiles.v2_endpoints import ProviderEndpointRecordV2
from vespercode.profiles.v2_reference import ReferenceProfileRecordV2
from vespercode.providers.v2_call import (
    ProviderCallRequestV2,
    V2ProviderCallCredential,
)
from vespercode.providers.v2_transport import (
    PROVIDER_ADDRESSES_V2,
    PROVIDER_MAX_REQUEST_BODY_BYTES_V2,
    PROVIDER_MAX_RESPONSE_BODY_BYTES_V2,
    PROVIDER_TRANSPORT_TIMEOUT_SECONDS_V2,
    ProviderAddressV2,
    V2ProviderHttpEdge,
    V2ProviderHttpResult,
    V2ProviderTransportAdapter,
    resolve_provider_address_v2,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _REPO_ROOT / "src" / "vespercode"
_SECRET = "v2-transport-test-secret-0001"
_OPENAI_URL = "https://api.openai.com:443/v1/chat/completions"
_ENDPOINT = ProviderEndpointRecordV2("endpoint-1", "OPENAI", "profile-1", 3)
_PROFILE = ReferenceProfileRecordV2(
    "profile-1", 3, "3.12.4", "8.4.2", "0.16.1", "2.3.0"
)


class _NoResult:
    """Sentinel: the fake answers with its scripted status/body."""


class FakeEdge:
    """Deterministic injectable HTTP edge (test double).

    Records every call exactly as the adapter made it — URL, headers,
    body, timeout — so the offline tests can pin the derived request,
    and answers with a scripted status/body, a scripted arbitrary
    result object (including hostile ones), or a scripted exception.
    It never opens a socket.
    """

    def __init__(
        self,
        *,
        status_code: int = 200,
        body: bytes = b"{}",
        result: object = _NoResult(),
        error: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self._status_code = status_code
        self._body = body
        self._result = result
        self._error = error

    def post(
        self,
        *,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: int,
    ) -> V2ProviderHttpResult:
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
        if not isinstance(self._result, _NoResult):
            return self._result  # type: ignore[no-any-return]
        return V2ProviderHttpResult(
            status_code=self._status_code, body=self._body
        )


def _request(**overrides: object) -> ProviderCallRequestV2:
    values: dict[str, object] = dict(
        request_id="request-1",
        authorization_id="auth-1",
        grant_id="grant-1",
        run_id="run-1",
        endpoint_id="endpoint-1",
        provider="OPENAI",
        reference_profile_id="profile-1",
        reference_profile_revision=3,
    )
    values.update(overrides)
    return ProviderCallRequestV2(**values)  # type: ignore[arg-type]


def _minted_credential() -> V2ProviderCallCredential:
    """One fresh provider call credential (the test-side mint).

    Mirrors exactly what the provider call service does after its
    atomic consume: mint the handshake object from the configured
    secret behind the provider-call capability.  A fresh mint per
    call keeps the single-use property out of the adapter tests'
    way.
    """

    return V2ProviderCallCredential(
        V2CredentialSecret.from_hidden_input(_SECRET),
        _provider_reveal_capability(),
    )


class ProviderAddressRegistryTests(unittest.TestCase):
    def test_the_closed_address_map_covers_exactly_the_declared_providers(
        self,
    ) -> None:
        self.assertEqual(set(PROVIDER_ADDRESSES_V2), {"OPENAI"})

    def test_the_sole_address_is_the_trusted_openai_https_endpoint(self) -> None:
        address = resolve_provider_address_v2("OPENAI")
        self.assertEqual(
            address,
            ProviderAddressV2(
                scheme="https",
                host="api.openai.com",
                effective_port=443,
                base_path="/v1",
                call_path="/chat/completions",
            ),
        )
        self.assertEqual(address.request_url(), _OPENAI_URL)

    def test_an_unknown_or_lookalike_provider_has_no_address(self) -> None:
        for provider in (
            "ANTHROPIC",
            "openai",
            "",
            "OPENAI_PUBLIC_API_V1",
            "https://evil.example",
        ):
            with self.subTest(provider=provider):
                with self.assertRaises(ValueError):
                    resolve_provider_address_v2(provider)  # type: ignore[arg-type]


class V2ProviderTransportAdapterConstructionTests(unittest.TestCase):
    def test_the_constructor_signature_is_closed(self) -> None:
        parameters = inspect.signature(
            V2ProviderTransportAdapter.__init__
        ).parameters
        self.assertEqual(
            set(parameters) - {"self"}, {"endpoint", "profile", "http_edge"}
        )
        for name, parameter in parameters.items():
            if name == "self":
                continue
            self.assertEqual(
                parameter.kind, inspect.Parameter.KEYWORD_ONLY, name
            )

    def test_a_binding_mismatch_between_endpoint_and_profile_rejects(self) -> None:
        stale = ReferenceProfileRecordV2(
            "profile-1", 4, "3.12.4", "8.4.2", "0.16.1", "2.3.0"
        )
        foreign = ReferenceProfileRecordV2(
            "profile-2", 3, "3.12.4", "8.4.2", "0.16.1", "2.3.0"
        )
        for profile in (stale, foreign):
            with self.subTest(profile=profile):
                with self.assertRaises(ValueError):
                    V2ProviderTransportAdapter(endpoint=_ENDPOINT, profile=profile)

    def test_an_endpoint_for_an_undeclared_provider_rejects(self) -> None:
        endpoint = ProviderEndpointRecordV2(
            "endpoint-2", "MYSTERY", "profile-1", 3
        )
        with self.assertRaises(ValueError):
            V2ProviderTransportAdapter(endpoint=endpoint, profile=_PROFILE)

    def test_non_record_arguments_reject(self) -> None:
        for endpoint, profile, edge in (
            ("endpoint-1", _PROFILE, None),
            (_ENDPOINT, "profile-1", None),
            (_ENDPOINT, _PROFILE, "not-an-edge"),
        ):
            with self.subTest(endpoint=endpoint, profile=profile, edge=edge):
                with self.assertRaises(ValueError):
                    V2ProviderTransportAdapter(
                        endpoint=endpoint,  # type: ignore[arg-type]
                        profile=profile,  # type: ignore[arg-type]
                        http_edge=edge,  # type: ignore[arg-type]
                    )

    def test_default_construction_never_touches_the_network_stack(self) -> None:
        # The asserted contract is that CONSTRUCTING the adapter with the
        # default edge loads no HTTP client; httpx may only appear in
        # sys.modules when a real call lazily imports it.  Same-process
        # state from earlier test files is causally irrelevant, so the
        # check is a delta over sys.modules.
        httpx_before = "httpx" in sys.modules
        adapter = V2ProviderTransportAdapter(endpoint=_ENDPOINT, profile=_PROFILE)
        self.assertIsNotNone(adapter)
        self.assertEqual(
            "httpx" in sys.modules,
            httpx_before,
            "constructing the default-transport adapter imported httpx",
        )


class V2ProviderTransportAdapterCallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.edge = FakeEdge()
        self.adapter = V2ProviderTransportAdapter(
            endpoint=_ENDPOINT, profile=_PROFILE, http_edge=self.edge
        )

    def test_a_successful_call_sends_the_derived_url_once(self) -> None:
        response = self.adapter.call(_request(), _minted_credential())
        self.assertEqual(response.status, "SUCCEEDED")
        self.assertEqual(len(self.edge.calls), 1)
        call = self.edge.calls[0]
        self.assertEqual(call["url"], _OPENAI_URL)
        self.assertEqual(
            call["headers"],
            {
                "Authorization": f"Bearer {_SECRET}",
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(
            call["timeout_seconds"], PROVIDER_TRANSPORT_TIMEOUT_SECONDS_V2
        )

    def test_the_request_body_is_the_bounded_control_projection(self) -> None:
        self.adapter.call(_request(), _minted_credential())
        body = self.edge.calls[0]["body"]
        assert isinstance(body, bytes)
        self.assertLessEqual(len(body), PROVIDER_MAX_REQUEST_BODY_BYTES_V2)
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(
            payload,
            {
                "request_id": "request-1",
                "authorization_id": "auth-1",
                "grant_id": "grant-1",
                "run_id": "run-1",
                "endpoint_id": "endpoint-1",
                "provider": "OPENAI",
                "reference_profile_id": "profile-1",
                "reference_profile_revision": 3,
            },
        )
        # The projection is deterministic: the same request maps to
        # the same body bytes.
        self.edge.calls.clear()
        self.adapter.call(_request(), _minted_credential())
        assert isinstance(self.edge.calls[0]["body"], bytes)
        self.assertEqual(self.edge.calls[0]["body"], body)

    def test_an_oversized_control_request_fails_before_the_edge(self) -> None:
        request = _request(
            request_id="r" * 256,
            authorization_id="a" * 256,
            grant_id="g" * 256,
            run_id="u" * 256,
            endpoint_id="e" * 256,
            reference_profile_id="p" * 256,
        )
        # Sanity: a valid-but-maximal record really does project past
        # the closed request-body bound.
        projection = json.dumps(
            {
                "request_id": request.request_id,
                "authorization_id": request.authorization_id,
                "grant_id": request.grant_id,
                "run_id": request.run_id,
                "endpoint_id": request.endpoint_id,
                "provider": request.provider,
                "reference_profile_id": request.reference_profile_id,
                "reference_profile_revision": request.reference_profile_revision,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertGreater(len(projection), PROVIDER_MAX_REQUEST_BODY_BYTES_V2)
        response = self.adapter.call(request, _minted_credential())
        self.assertEqual(response.status, "FAILED")
        self.assertEqual(self.edge.calls, [])

    def test_a_binding_drift_rejects_before_the_edge(self) -> None:
        for overrides in (
            {"endpoint_id": "endpoint-2"},
            {"provider": "OTHER"},
            {"reference_profile_id": "profile-9"},
            {"reference_profile_revision": 4},
        ):
            with self.subTest(overrides=overrides):
                response = self.adapter.call(
                    _request(**overrides), _minted_credential()
                )
                self.assertEqual(response.status, "FAILED")
        self.assertEqual(self.edge.calls, [])

    def test_a_non_record_request_rejects(self) -> None:
        with self.assertRaises(ValueError):
            self.adapter.call(
                "not-a-request", _minted_credential()  # type: ignore[arg-type]
            )

    def test_an_empty_credential_rejects(self) -> None:
        with self.assertRaises(ValueError):
            self.adapter.call(_request(), "")

    def test_a_raw_string_credential_rejects_before_the_edge(self) -> None:
        # The security gap this suite pins: any caller holding a raw
        # secret could previously drive the adapter directly, past the
        # service's authorization/consume boundary.  A raw string — even
        # the real secret spelling — now rejects before the HTTP edge
        # is ever touched.
        for hostile in (_SECRET, "", "not-the-service-mint"):
            with self.subTest(hostile=hostile):
                with self.assertRaises(ValueError):
                    self.adapter.call(_request(), hostile)  # type: ignore[arg-type]
        self.assertEqual(self.edge.calls, [])

    def test_any_non_handshake_credential_rejects_before_the_edge(self) -> None:
        # Not only raw strings: no other object opens the adapter — a
        # bare ``V2CredentialSecret`` wrapper (self-wrapping a raw
        # value) rejects exactly like everything else, so the only
        # accepted credential is the service-minted handshake.
        for hostile in (
            None,
            123,
            b"raw-bytes",
            object(),
            V2CredentialSecret.from_hidden_input(_SECRET),
        ):
            with self.subTest(hostile=hostile):
                with self.assertRaises(ValueError):
                    self.adapter.call(_request(), hostile)  # type: ignore[arg-type]
        self.assertEqual(self.edge.calls, [])

    def test_a_replayed_handshake_fails_closed_before_the_edge(self) -> None:
        # The handshake is single-use: after the one successful call,
        # replaying the same object never reaches the edge again.
        credential = _minted_credential()
        first = self.adapter.call(_request(), credential)
        self.assertEqual(first.status, "SUCCEEDED")
        self.assertEqual(len(self.edge.calls), 1)
        replay = self.adapter.call(_request(), credential)
        self.assertEqual(replay.status, "FAILED")
        self.assertEqual(len(self.edge.calls), 1)

    def test_a_redirect_response_fails_without_a_second_send(self) -> None:
        edge = FakeEdge(status_code=302)
        adapter = V2ProviderTransportAdapter(
            endpoint=_ENDPOINT, profile=_PROFILE, http_edge=edge
        )
        response = adapter.call(_request(), _minted_credential())
        self.assertEqual(response.status, "FAILED")
        self.assertEqual(len(edge.calls), 1)

    def test_every_non_success_status_fails(self) -> None:
        for status_code in (301, 307, 400, 401, 403, 404, 429, 500, 503, 204):
            with self.subTest(status_code=status_code):
                edge = FakeEdge(status_code=status_code)
                adapter = V2ProviderTransportAdapter(
                    endpoint=_ENDPOINT, profile=_PROFILE, http_edge=edge
                )
                response = adapter.call(_request(), _minted_credential())
                self.assertEqual(response.status, "FAILED")
                self.assertEqual(len(edge.calls), 1)

    def test_an_oversized_response_body_fails(self) -> None:
        edge = FakeEdge(
            status_code=200,
            body=b"x" * (PROVIDER_MAX_RESPONSE_BODY_BYTES_V2 + 1),
        )
        adapter = V2ProviderTransportAdapter(
            endpoint=_ENDPOINT, profile=_PROFILE, http_edge=edge
        )
        response = adapter.call(_request(), _minted_credential())
        self.assertEqual(response.status, "FAILED")
        self.assertEqual(len(edge.calls), 1)

    def test_a_timeout_maps_to_the_closed_failure_with_no_retry(self) -> None:
        edge = FakeEdge(error=TimeoutError("the connection timed out"))
        adapter = V2ProviderTransportAdapter(
            endpoint=_ENDPOINT, profile=_PROFILE, http_edge=edge
        )
        response = adapter.call(_request(), _minted_credential())
        self.assertEqual(response.status, "FAILED")
        self.assertEqual(len(edge.calls), 1)

    def test_any_edge_exception_is_redacted_and_never_retried(self) -> None:
        edge = FakeEdge(
            error=RuntimeError(f"leaked Authorization: Bearer {_SECRET}")
        )
        adapter = V2ProviderTransportAdapter(
            endpoint=_ENDPOINT, profile=_PROFILE, http_edge=edge
        )
        response = adapter.call(_request(), _minted_credential())
        self.assertEqual(response.status, "FAILED")
        self.assertEqual(len(edge.calls), 1)

    def test_a_non_conforming_edge_result_fails(self) -> None:
        for result in ("not-a-result", None, 200):
            with self.subTest(result=result):
                edge = FakeEdge(result=result)
                adapter = V2ProviderTransportAdapter(
                    endpoint=_ENDPOINT, profile=_PROFILE, http_edge=edge
                )
                response = adapter.call(_request(), _minted_credential())
                self.assertEqual(response.status, "FAILED")
                self.assertEqual(len(edge.calls), 1)

    def test_an_out_of_range_edge_status_fails(self) -> None:
        class _HostileEdge:
            def post(self, **kwargs: object) -> V2ProviderHttpResult:
                return V2ProviderHttpResult(status_code=999, body=b"")

        adapter = V2ProviderTransportAdapter(
            endpoint=_ENDPOINT, profile=_PROFILE, http_edge=_HostileEdge()
        )
        response = adapter.call(_request(), _minted_credential())
        self.assertEqual(response.status, "FAILED")

    def test_the_adapter_retains_no_secret_state(self) -> None:
        response = self.adapter.call(_request(), _minted_credential())
        self.assertEqual(response.status, "SUCCEEDED")
        for name in dir(self.adapter):
            if name.startswith("__"):
                continue
            attribute = getattr(self.adapter, name, None)
            if isinstance(attribute, str):
                self.assertNotIn(_SECRET, attribute, name)
        self.assertNotIn(_SECRET, repr(self.adapter))
        self.assertNotIn(_SECRET, repr(response))
        self.assertNotIn(_SECRET, str(response))

    def test_the_closed_bounds_and_timeout_are_pinned(self) -> None:
        self.assertEqual(PROVIDER_TRANSPORT_TIMEOUT_SECONDS_V2, 60)
        self.assertEqual(PROVIDER_MAX_RESPONSE_BODY_BYTES_V2, 1024 * 1024)
        self.assertEqual(PROVIDER_MAX_REQUEST_BODY_BYTES_V2, 1600)

    def test_the_http_result_record_is_closed(self) -> None:
        result = V2ProviderHttpResult(status_code=200, body=b"{}")
        self.assertEqual(
            {field.name for field in fields(result)}, {"status_code", "body"}
        )
        for hostile in (
            {"status_code": True, "body": b""},
            {"status_code": 99, "body": b""},
            {"status_code": 600, "body": b""},
            {"status_code": 200, "body": "not-bytes"},
        ):
            with self.subTest(hostile=hostile):
                with self.assertRaises(ValueError):
                    V2ProviderHttpResult(**hostile)  # type: ignore[arg-type]

    def test_the_fake_edge_conforms_to_the_edge_protocol(self) -> None:
        self.assertIsInstance(FakeEdge(), V2ProviderHttpEdge)


def _module_level_import_names(relative: str) -> set[str]:
    tree = ast.parse((_SRC_ROOT / relative).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    return names


def _all_import_names(relative: str) -> set[str]:
    tree = ast.parse((_SRC_ROOT / relative).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    return names


class ImportIsolationTests(unittest.TestCase):
    def test_httpx_never_imports_at_module_scope(self) -> None:
        module_level = _module_level_import_names("providers/v2_transport.py")
        self.assertNotIn("httpx", module_level)
        # The real edge still reaches httpx — lazily, inside the call,
        # so importing the adapter never loads a network client.
        self.assertIn("httpx", _all_import_names("providers/v2_transport.py"))

    def test_the_transport_never_imports_sockets_subprocess_or_v1_authority(
        self,
    ) -> None:
        all_imports = _all_import_names("providers/v2_transport.py")
        for forbidden in ("socket", "subprocess", "os"):
            self.assertNotIn(forbidden, all_imports)
        for forbidden in (
            "vespercode.profiles.endpoints",
            "vespercode.credentials.port",
            "vespercode.credentials.service",
            "vespercode.credentials.wincred_store",
            "vespercode.llm.openai_adapter",
        ):
            self.assertNotIn(forbidden, all_imports)

    def test_the_transport_holds_only_the_transport_reveal_seam(self) -> None:
        # The adapter's single granted capability is the transport-reveal
        # seam; the provider-call reveal seam (the mint), the wrapper's
        # own ``reveal`` target, and the OS storage seam never appear in
        # the transport module, so the OS storage reveal frame stays
        # separate from the provider transport frame.
        tree = ast.parse(
            (_SRC_ROOT / "providers/v2_transport.py").read_text(encoding="utf-8")
        )
        imported_names: set[str] = set()
        imported_from: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported_from.add(node.module or "")
                imported_names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                imported_names.update(alias.name for alias in node.names)
        self.assertIn("_transport_reveal_capability", imported_names)
        self.assertIn("vespercode.providers.v2_call", imported_from)
        for forbidden in (
            "_provider_reveal_capability",
            "_storage_reveal_capability",
            "reveal",
            "reveal_for_storage",
            "vespercode.credentials.v2_port",
            "vespercode.credentials.v2_os_store",
        ):
            self.assertNotIn(forbidden, imported_names)
            self.assertNotIn(forbidden, imported_from)


if __name__ == "__main__":
    unittest.main()
