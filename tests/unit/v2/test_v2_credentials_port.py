"""Route B / B2: the injectable v2 credential provider port.

The v1 credential port (``credentials/port.py``) is pydantic-bound and
closed to the single ``OPENAI`` provider backed by Windows Credential
Manager; it remains untouched read-only legacy.  This slice defines the
stdlib-only v2 port: hidden input is wrapped in a non-comparable,
non-serializable, redacted secret object, ``get_for_call`` is the only
projection that can carry the wrapper out of the store, and ``reveal``
is consumed only by the provider call boundary.  Status reports carry
the provider name, a configured flag, and an update time — never the
secret, its length, or any derivative.  The real OS credential
integration is deliberately out of scope for B2; the in-memory provider
here is the deterministic fake used by tests and the demo composition.
"""

from __future__ import annotations

import copy
import pickle
import sys
import unittest

from vespercode.credentials.v2_port import (
    InMemoryV2CredentialProvider,
    V2CredentialError,
    V2CredentialMutation,
    V2CredentialSecret,
    V2CredentialStatus,
    _provider_reveal_capability,
    _RevealCapability,
    _storage_reveal_capability,
    _StorageCapability,
)

_SECRET = "v2-test-secret-material-0001"


class V2CredentialSecretTests(unittest.TestCase):
    def test_from_hidden_input_rejects_non_string_and_empty_values(self) -> None:
        with self.assertRaises(V2CredentialError):
            V2CredentialSecret.from_hidden_input("")
        with self.assertRaises(V2CredentialError):
            V2CredentialSecret.from_hidden_input(None)  # type: ignore[arg-type]
        with self.assertRaises(V2CredentialError):
            V2CredentialSecret.from_hidden_input(12345)  # type: ignore[arg-type]
        secret = V2CredentialSecret.from_hidden_input(_SECRET)
        self.assertEqual(secret.reveal(_provider_reveal_capability()), _SECRET)

    def test_reveal_requires_the_provider_call_boundary_capability(self) -> None:
        secret = V2CredentialSecret.from_hidden_input(_SECRET)
        # Direct ordinary use — no capability argument — is rejected.
        with self.assertRaises(TypeError):
            secret.reveal()  # type: ignore[call-arg]
        for wrong in (None, "", "capability", 123, object(), _RevealCapability()):
            with self.subTest(wrong=wrong):
                with self.assertRaises(V2CredentialError) as caught:
                    secret.reveal(wrong)
                self.assertEqual(
                    caught.exception.error_code, "CREDENTIAL_REVEAL_FORBIDDEN"
                )
        # The legitimate seam — the one providers/v2_call uses — still reveals.
        self.assertEqual(secret.reveal(_provider_reveal_capability()), _SECRET)

    def test_the_reveal_capability_is_absent_from_the_public_surface(self) -> None:
        module = sys.modules[V2CredentialSecret.__module__]
        capability = _provider_reveal_capability()
        # No public module attribute is the capability itself, and no
        # public export is capability-related by name.
        for name in dir(module):
            if name.startswith("_"):
                continue
            self.assertIsNot(getattr(module, name), capability, name)
        for exported in module.__all__:
            self.assertFalse(
                "capab" in exported.lower() or "reveal" in exported.lower(),
                f"capability-like public export: {exported}",
            )
        # The single minted instance is the only key: a fresh look-alike
        # instance of the private class does not unlock a secret.
        self.assertIsNot(_RevealCapability(), capability)

    def test_the_secret_wrapper_is_redacted_everywhere(self) -> None:
        secret = V2CredentialSecret.from_hidden_input(_SECRET)
        self.assertEqual(repr(secret), "V2CredentialSecret([redacted])")
        self.assertEqual(str(secret), "V2CredentialSecret([redacted])")
        self.assertNotIn(_SECRET, repr(secret))
        self.assertNotIn(_SECRET, str(secret))

    def test_the_secret_wrapper_is_not_comparable(self) -> None:
        secret = V2CredentialSecret.from_hidden_input(_SECRET)
        other = V2CredentialSecret.from_hidden_input(_SECRET)
        with self.assertRaises(TypeError):
            secret == other  # type: ignore[override]
        with self.assertRaises(TypeError):
            secret != other  # type: ignore[override]

    def test_the_secret_wrapper_is_not_serializable_or_copyable(self) -> None:
        secret = V2CredentialSecret.from_hidden_input(_SECRET)
        with self.assertRaises(TypeError):
            copy.copy(secret)
        with self.assertRaises(TypeError):
            copy.deepcopy(secret)
        with self.assertRaises(TypeError):
            pickle.dumps(secret)
        with self.assertRaises(TypeError):
            secret.__reduce__()

    def test_reveal_is_the_single_accessor(self) -> None:
        secret = V2CredentialSecret.from_hidden_input(_SECRET)
        self.assertEqual(secret.reveal(_provider_reveal_capability()), _SECRET)
        # The wrapper exposes no other attribute carrying the value.
        for name in dir(secret):
            if name.startswith("_"):
                continue
            attribute = getattr(secret, name)
            if isinstance(attribute, str):
                self.assertNotIn(_SECRET, attribute)


class V2CredentialStorageRevealTests(unittest.TestCase):
    """B4b-02C1: the storage-reveal seam for the OS credential store.

    The raw value of a wrapped secret is reachable in exactly two
    capability-gated frames: the provider transport call frame
    (``reveal``, granted only to ``providers/v2_call``) and the OS
    storage write frame (``reveal_for_storage``, granted only to
    ``credentials/v2_os_store``).  The two capabilities are minted
    separately, handed only through module-private friend seams, and
    are never interchangeable.
    """

    def test_reveal_for_storage_requires_the_exact_storage_capability(self) -> None:
        secret = V2CredentialSecret.from_hidden_input(_SECRET)
        # Direct ordinary use — no capability argument — is rejected.
        with self.assertRaises(TypeError):
            secret.reveal_for_storage()  # type: ignore[call-arg]
        for wrong in (
            None,
            "",
            "capability",
            123,
            object(),
            _RevealCapability(),
            _provider_reveal_capability(),
        ):
            with self.subTest(wrong=wrong):
                with self.assertRaises(V2CredentialError) as caught:
                    secret.reveal_for_storage(wrong)
                self.assertEqual(
                    caught.exception.error_code, "CREDENTIAL_REVEAL_FORBIDDEN"
                )
        self.assertEqual(
            secret.reveal_for_storage(_storage_reveal_capability()), _SECRET
        )

    def test_the_two_capabilities_are_not_interchangeable(self) -> None:
        secret = V2CredentialSecret.from_hidden_input(_SECRET)
        # The storage capability does not unlock the provider-call
        # reveal ...
        with self.assertRaises(V2CredentialError) as caught:
            secret.reveal(_storage_reveal_capability())
        self.assertEqual(
            caught.exception.error_code, "CREDENTIAL_REVEAL_FORBIDDEN"
        )
        # ... and the provider-call capability does not unlock the
        # storage reveal.
        with self.assertRaises(V2CredentialError) as caught:
            secret.reveal_for_storage(_provider_reveal_capability())
        self.assertEqual(
            caught.exception.error_code, "CREDENTIAL_REVEAL_FORBIDDEN"
        )
        # The single minted instances are the only keys: fresh
        # look-alike instances of the private classes never unlock.
        self.assertIsNot(_StorageCapability(), _storage_reveal_capability())
        self.assertIsNot(_provider_reveal_capability(), _storage_reveal_capability())

    def test_the_storage_capability_is_absent_from_the_public_surface(self) -> None:
        module = sys.modules[V2CredentialSecret.__module__]
        capability = _storage_reveal_capability()
        for name in dir(module):
            if name.startswith("_"):
                continue
            self.assertIsNot(getattr(module, name), capability, name)
        for exported in module.__all__:
            self.assertFalse(
                "storage" in exported.lower() or "reveal" in exported.lower(),
                f"storage-capability-like public export: {exported}",
            )

    def test_reveal_for_storage_is_redacted_like_reveal(self) -> None:
        secret = V2CredentialSecret.from_hidden_input(_SECRET)
        # No wrapper attribute, repr, or str carries the value.
        for name in dir(secret):
            if name.startswith("_"):
                continue
            attribute = getattr(secret, name, None)
            if isinstance(attribute, str):
                self.assertNotIn(_SECRET, attribute, name)


class InMemoryV2CredentialProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = InMemoryV2CredentialProvider()

    def test_provider_names_must_be_safe_identifiers(self) -> None:
        secret = V2CredentialSecret.from_hidden_input(_SECRET)
        for bad_name in ("", " ", "bad name", "bad/name", "x" * 65, "x:y"):
            with self.subTest(bad_name=bad_name):
                with self.assertRaises(V2CredentialError):
                    self.provider.set(bad_name, secret)
        self.provider.set("OPENAI", secret)
        self.assertTrue(self.provider.status("OPENAI").configured)

    def test_set_then_status_reports_configured_without_the_secret(self) -> None:
        self.assertFalse(self.provider.status("OPENAI").configured)
        secret = V2CredentialSecret.from_hidden_input(_SECRET)
        mutation = self.provider.set("OPENAI", secret)
        self.assertIsInstance(mutation, V2CredentialMutation)
        self.assertEqual(mutation.kind, "STORED")
        self.assertEqual(mutation.provider, "OPENAI")
        status = self.provider.status("OPENAI")
        self.assertIsInstance(status, V2CredentialStatus)
        self.assertEqual(status.provider, "OPENAI")
        self.assertTrue(status.configured)
        self.assertIsInstance(status.updated_at, str)
        self.assertTrue(bool(status.updated_at))
        # The status projection carries no secret material; the field
        # surface is pinned to the three redacted fields by its own
        # test below.
        self.assertNotIn(_SECRET, repr(status))
        self.assertNotIn(_SECRET, str(status))

    def test_status_field_surface_is_exactly_the_redacted_three(self) -> None:
        self.provider.set("OPENAI", V2CredentialSecret.from_hidden_input(_SECRET))
        status = self.provider.status("OPENAI")
        self.assertEqual(
            {field for field in status.__dataclass_fields__},
            {"provider", "configured", "updated_at"},
        )

    def test_clear_makes_the_provider_unconfigured_and_reports_it(self) -> None:
        self.provider.set("OPENAI", V2CredentialSecret.from_hidden_input(_SECRET))
        mutation = self.provider.clear("OPENAI")
        self.assertEqual(mutation.kind, "CLEARED")
        self.assertEqual(mutation.provider, "OPENAI")
        self.assertNotIn(_SECRET, repr(mutation))
        self.assertFalse(self.provider.status("OPENAI").configured)
        self.assertIsNone(self.provider.get_for_call("OPENAI"))
        # Clearing an unconfigured provider is an idempotent success.
        self.assertEqual(self.provider.clear("OPENAI").kind, "CLEARED")

    def test_get_for_call_returns_the_wrapper_or_none(self) -> None:
        self.assertIsNone(self.provider.get_for_call("OPENAI"))
        self.provider.set("OPENAI", V2CredentialSecret.from_hidden_input(_SECRET))
        wrapper = self.provider.get_for_call("OPENAI")
        self.assertIsInstance(wrapper, V2CredentialSecret)
        self.assertEqual(wrapper.reveal(_provider_reveal_capability()), _SECRET)

    def test_set_overwrites_the_previous_value_for_the_same_provider(self) -> None:
        self.provider.set(
            "OPENAI", V2CredentialSecret.from_hidden_input("first-value")
        )
        self.provider.set(
            "OPENAI", V2CredentialSecret.from_hidden_input("second-value")
        )
        revealed = self.provider.get_for_call("OPENAI").reveal(
            _provider_reveal_capability()
        )
        self.assertEqual(revealed, "second-value")

    def test_providers_are_independent(self) -> None:
        self.provider.set("OPENAI", V2CredentialSecret.from_hidden_input(_SECRET))
        self.assertFalse(self.provider.status("OTHER").configured)
        self.assertIsNone(self.provider.get_for_call("OTHER"))
        self.provider.clear("OTHER")
        self.assertTrue(self.provider.status("OPENAI").configured)


if __name__ == "__main__":
    unittest.main()
