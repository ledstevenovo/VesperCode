"""Route B / B4b-02C1: the real provider transport adapter.

The v1 transport (``llm/openai_adapter.py`` over the pydantic-bound
``profiles/endpoints.py`` map) is digest-bound legacy and remains
untouched read-only legacy; nothing here imports it, and no v1
endpoint manifest or adapter becomes a v2 provider path.

The v2 real transport adapter is the production implementation of the
B2 ``V2ProviderTransport`` protocol for the declared provider
endpoint/profile only:

- **The destination is never an input.** The adapter is constructed
  from exactly one v2 endpoint record and the reference profile record
  it must bind, plus an optional injectable HTTP edge — there is no
  URL, ``base_url``, header, argv, or shell parameter, and no
  environment or configuration override.  The URL derives internally
  from the closed built-in provider address map (``PROVIDER_ADDRESSES_V2``,
  the sole declared provider being ``OPENAI`` at
  ``https://api.openai.com:443/v1/chat/completions``); an endpoint
  record whose provider has no declared address cannot even construct
  the adapter.

- **The request body is the bounded control-plane projection.** The
  body is the deterministic JSON projection of the call request's
  control IDs and revisions — never file content, task text, or the
  credential — and a request whose projection exceeds
  ``PROVIDER_MAX_REQUEST_BODY_BYTES_V2`` fails closed before the edge
  is ever touched.  (The authorized-content payload for real
  completions is deliberately a later slice; this boundary proves the
  transport mechanism.)

- **One call, strict bounds, no retry.** The adapter performs exactly
  one edge call per ``call``, passing the closed read timeout
  (``PROVIDER_TRANSPORT_TIMEOUT_SECONDS_V2``); the real edge streams
  the response and aborts at the closed body bound
  (``PROVIDER_MAX_RESPONSE_BODY_BYTES_V2``), never follows a redirect,
  and is the only network edge of the v2 provider plane.  Any edge
  exception, any non-success status (including every 3xx redirect),
  any non-conforming result, and any over-bound body maps to the closed
  ``FAILED`` response: the adapter itself never raises a raw provider
  or network exception, never retries, and discards the response body
  — no body text, no secret, no URL appears in any response, retained
  state, or exception.

- **The credential is a provider-only handshake object.** ``call``
  accepts exactly the ``V2ProviderCallCredential`` minted by the
  provider call service after its atomic consume — never a raw value,
  never a bare secret wrapper — and any other argument (a raw string
  above all) rejects before the edge is ever touched, so no caller
  holding a raw secret can drive this adapter directly, past the
  service's authorization/consume boundary.  Inside this frame, and
  only here, the adapter opens the handshake exactly once through
  the transport-reveal seam granted to exactly this module, solely to
  build the ``Authorization`` header handed to the one edge call; a
  failed or replayed handshake, like every other failure, maps to the
  closed ``FAILED`` response.  The opened value is never stored on
  the adapter, never placed in a record or outcome, and the adapter's
  failure responses are indistinguishable by design (redaction).

The offline unit tests exercise the adapter through deterministic fake
edges only — no real network call exists in the unit suite.  The real
``httpx`` edge (``_HttpxV2ProviderEdge``) imports httpx lazily inside
the call, so importing this module loads no network client at all.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from vespercode.profiles.v2_endpoints import ProviderEndpointRecordV2
from vespercode.profiles.v2_reference import ReferenceProfileRecordV2
from vespercode.providers.v2_call import (
    ProviderCallRequestV2,
    ProviderCallResponseV2,
    V2ProviderCallCredential,
    _transport_reveal_capability,
)

PROVIDER_TRANSPORT_TIMEOUT_SECONDS_V2 = 60
"""The closed read timeout of one provider transport call."""

PROVIDER_MAX_REQUEST_BODY_BYTES_V2 = 1600
"""The closed bound on the serialized control-projection request body."""

PROVIDER_MAX_RESPONSE_BODY_BYTES_V2 = 1024 * 1024
"""The closed bound on the raw provider response body."""


class V2ProviderTransportError(ValueError):
    """One closed transport-edge failure (static message, nothing raw).

    The real HTTP edge raises this typed error — never a provider
    body, secret, or URL — and the adapter maps it (like every other
    edge exception) to the closed ``FAILED`` response.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ProviderAddressV2:
    """One trusted provider address from the closed built-in map.

    The five fields are declared configuration; ``request_url`` is the
    sole derived destination and the adapter never accepts any other
    spelling of it.
    """

    scheme: str
    host: str
    effective_port: int
    base_path: str
    call_path: str

    def request_url(self) -> str:
        return (
            f"{self.scheme}://{self.host}:{self.effective_port}"
            f"{self.base_path}{self.call_path}"
        )


PROVIDER_ADDRESSES_V2: Mapping[str, ProviderAddressV2] = MappingProxyType(
    {
        "OPENAI": ProviderAddressV2(
            scheme="https",
            host="api.openai.com",
            effective_port=443,
            base_path="/v1",
            call_path="/chat/completions",
        ),
    }
)
"""The closed built-in provider address map (no user input reaches it)."""


def resolve_provider_address_v2(provider: str) -> ProviderAddressV2:
    """Resolve one provider's trusted address from the closed map.

    Only a provider the map declares resolves; anything else — an
    unknown provider, a case-variant spelling, a raw URL — rejects
    without any network access, so no caller-supplied string can
    become a destination.
    """

    address = PROVIDER_ADDRESSES_V2.get(provider)
    if address is None:
        raise ValueError(
            "no trusted provider address is declared for the provider"
        )
    return address


@dataclass(frozen=True, slots=True)
class V2ProviderHttpResult:
    """One bounded HTTP edge result: a status and a body, nothing else.

    The adapter enforces the closed response-body bound after the
    result; the response body is never projected into any response,
    outcome, or record.
    """

    status_code: int
    body: bytes

    def __post_init__(self) -> None:
        if isinstance(self.status_code, bool) or not isinstance(
            self.status_code, int
        ):
            raise ValueError("status_code must be an integer HTTP status")
        if not 100 <= self.status_code <= 599:
            raise ValueError("status_code is outside the HTTP status range")
        if not isinstance(self.body, bytes):
            raise ValueError("body must be bytes")


@runtime_checkable
class V2ProviderHttpEdge(Protocol):
    """The injectable one-call HTTP edge of the provider transport.

    ``post`` performs exactly one request; implementations honor the
    passed closed timeout, never follow redirects, and return one
    bounded result.  The real implementation is the lazy-httpx edge;
    the offline unit tests inject deterministic fakes.
    """

    def post(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: int,
    ) -> V2ProviderHttpResult: ...


class _HttpxV2ProviderEdge:
    """The real HTTP edge: one streaming POST, no redirect follow.

    The httpx import is lazy (inside the call), so neither this module
    nor the adapter ever loads a network client at import or
    construction time.  The client is constructed per call with
    ``follow_redirects=False`` (a redirect is returned as a plain
    status the adapter rejects) and the closed read timeout; the
    streamed read accumulates chunks and aborts with the closed typed
    error as soon as the response-body bound is exceeded, so a hostile
    peer cannot force unbounded memory.
    """

    __slots__ = ()

    def post(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: int,
    ) -> V2ProviderHttpResult:
        try:
            import httpx
        except Exception as exc:  # noqa: BLE001 - fail closed, no network
            raise V2ProviderTransportError(
                "the httpx HTTP edge is not available"
            ) from exc
        with httpx.Client(
            timeout=timeout_seconds, follow_redirects=False
        ) as client:
            with client.stream(
                "POST", url, headers=dict(headers), content=body
            ) as response:
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > PROVIDER_MAX_RESPONSE_BODY_BYTES_V2:
                        raise V2ProviderTransportError(
                            "the provider response exceeds the closed bound"
                        )
                    chunks.append(chunk)
                return V2ProviderHttpResult(
                    status_code=response.status_code,
                    body=b"".join(chunks),
                )


def _control_request_body(request: ProviderCallRequestV2) -> bytes:
    """The deterministic bounded JSON projection of one control request.

    Carries the request's control IDs and revisions only — no file
    content, no task text, no credential, no digest — so the wire
    projection of a provider call is fully derived from the validated
    control-plane record.
    """

    payload = {
        "request_id": request.request_id,
        "authorization_id": request.authorization_id,
        "grant_id": request.grant_id,
        "run_id": request.run_id,
        "endpoint_id": request.endpoint_id,
        "provider": request.provider,
        "reference_profile_id": request.reference_profile_id,
        "reference_profile_revision": request.reference_profile_revision,
    }
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


class V2ProviderTransportAdapter:
    """The real provider transport for one declared endpoint/profile binding.

    ``endpoint`` and ``profile`` are the v2 control-plane records this
    adapter is declared to serve (the database rows the provider call
    service checks against); their binding is verified at construction
    and the provider's trusted address is resolved from the closed map
    — an unknown provider cannot construct an adapter.  ``http_edge``
    defaults to the real lazy-httpx edge.  ``call`` rechecks the
    request's own endpoint/provider/profile binding (defense in depth
    after the service's checks), performs exactly one edge call, and
    maps everything else to the closed ``FAILED`` response.
    """

    __slots__ = ("_endpoint", "_profile", "_address", "_edge")

    def __init__(
        self,
        *,
        endpoint: ProviderEndpointRecordV2,
        profile: ReferenceProfileRecordV2,
        http_edge: V2ProviderHttpEdge | None = None,
    ) -> None:
        if not isinstance(endpoint, ProviderEndpointRecordV2):
            raise ValueError("endpoint must be a ProviderEndpointRecordV2")
        if not isinstance(profile, ReferenceProfileRecordV2):
            raise ValueError("profile must be a ReferenceProfileRecordV2")
        if (
            endpoint.reference_profile_id != profile.reference_profile_id
            or endpoint.reference_profile_revision != profile.profile_revision
        ):
            raise ValueError(
                "the endpoint does not bind the reference profile"
            )
        if http_edge is None:
            http_edge = _HttpxV2ProviderEdge()
        if not isinstance(http_edge, V2ProviderHttpEdge):
            raise ValueError("http_edge must implement the v2 provider edge")
        self._endpoint = endpoint
        self._profile = profile
        self._address = resolve_provider_address_v2(endpoint.provider)
        self._edge = http_edge

    def call(
        self,
        request: ProviderCallRequestV2,
        credential: V2ProviderCallCredential,
    ) -> ProviderCallResponseV2:
        """Perform exactly one provider transport call for one request.

        ``credential`` is the provider-only call credential handshake
        object minted by the provider call service after its atomic
        consume — never a raw value; a raw string (or anything else)
        rejects before the edge is ever touched, so no caller holding
        a raw secret can bypass the service's authorization/consume
        boundary through this adapter.  Inside this frame, and only
        here, the adapter opens the handshake exactly once, solely to
        build the ``Authorization`` header of the single edge call;
        every failure — binding drift, an oversized control body, a
        failed or replayed handshake, an edge exception, a redirect, a
        non-success status, a non-conforming result, or an over-bound
        response body — maps to the closed ``FAILED`` response with
        zero retries and zero leakage of body, secret, or URL.
        """

        if not isinstance(request, ProviderCallRequestV2):
            raise ValueError("request must be a ProviderCallRequestV2")
        if not isinstance(credential, V2ProviderCallCredential):
            raise ValueError(
                "credential must be the provider-only call credential "
                "(a V2ProviderCallCredential), never a raw value"
            )
        if not self._binding_matches(request):
            return ProviderCallResponseV2("FAILED")
        body = _control_request_body(request)
        if len(body) > PROVIDER_MAX_REQUEST_BODY_BYTES_V2:
            return ProviderCallResponseV2("FAILED")
        try:
            # The single sanctioned materialization: the handshake opens
            # only here, only once, and the opened value exists only
            # inside this frame to build the one Authorization header.
            value = credential.reveal_for_transport(
                _transport_reveal_capability()
            )
        except Exception:  # noqa: BLE001 - redacted; never retried
            return ProviderCallResponseV2("FAILED")
        headers = {
            "Authorization": f"Bearer {value}",
            "Content-Type": "application/json",
        }
        try:
            result = self._edge.post(
                url=self._address.request_url(),
                headers=headers,
                body=body,
                timeout_seconds=PROVIDER_TRANSPORT_TIMEOUT_SECONDS_V2,
            )
        except Exception:  # noqa: BLE001 - redacted; never retried
            return ProviderCallResponseV2("FAILED")
        if not isinstance(result, V2ProviderHttpResult):
            return ProviderCallResponseV2("FAILED")
        if result.status_code != 200:
            # Includes every 3xx redirect: never followed, never
            # re-sent — the request was not delivered to the trusted
            # endpoint, so the call fails closed.
            return ProviderCallResponseV2("FAILED")
        if len(result.body) > PROVIDER_MAX_RESPONSE_BODY_BYTES_V2:
            return ProviderCallResponseV2("FAILED")
        # The response body is discarded: the transport-facing
        # response is a status and nothing else.
        return ProviderCallResponseV2("SUCCEEDED")

    def _binding_matches(self, request: ProviderCallRequestV2) -> bool:
        return (
            request.endpoint_id == self._endpoint.endpoint_id
            and request.provider == self._endpoint.provider
            and request.reference_profile_id
            == self._endpoint.reference_profile_id
            and request.reference_profile_revision
            == self._endpoint.reference_profile_revision
        )


__all__ = (
    "PROVIDER_ADDRESSES_V2",
    "PROVIDER_MAX_REQUEST_BODY_BYTES_V2",
    "PROVIDER_MAX_RESPONSE_BODY_BYTES_V2",
    "PROVIDER_TRANSPORT_TIMEOUT_SECONDS_V2",
    "ProviderAddressV2",
    "V2ProviderHttpEdge",
    "V2ProviderHttpResult",
    "V2ProviderTransportAdapter",
    "V2ProviderTransportError",
    "resolve_provider_address_v2",
)
