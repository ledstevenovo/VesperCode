"""Route B / B3: the typed, allowlisted form contracts of the v2 WebUI.

Every mutation and query endpoint of the v2 local WebUI accepts exactly
one closed form: ``V2FormContract`` names the endpoint's exact field set
and gives each field a closed typed parser — bounded identifiers,
non-negative decimal revisions, bounded task text, the literal
confirmation, and the CSRF token form.  Any extra, missing, duplicated,
or malformed field is a closed ``V2FormError`` that the app turns into
an HTTP error *before any domain call*, so a malformed form performs
zero shell calls and zero writes.

No form ever carries a filesystem path, a policy or profile override, a
provider URL, a secret, or a credential: the field kinds exist for
control-plane references (opaque IDs, revisions) and bounded text only.
"""

from __future__ import annotations

import re
from typing import Mapping, Sequence

from urllib.parse import parse_qs

V2_CONFIRM_LITERAL = "CONFIRM"
"""The exact literal every mutation form must repeat."""

V2_TASK_MAX_CHARS = 4096
"""The closed task-text bound (identical on the CLI and the WebUI)."""

V2_MAX_FORM_FIELDS = 64
"""The closed bound on fields in one URL-encoded body."""

V2_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
"""The closed identifier form: an opaque short token, never a path."""

V2_REVISION_RE = re.compile(r"^[0-9]{1,10}$")
"""The closed revision form: a non-negative decimal integer."""

V2_TOKEN_RE = re.compile(r"^[0-9a-f]{64}$")
"""The closed CSRF synchronizer-token form."""

V2_FORM_ERROR_CODES = (
    "UNKNOWN_FIELD",
    "MISSING_FIELD",
    "DUPLICATE_FIELD",
    "INVALID_IDENTIFIER",
    "INVALID_REVISION",
    "INVALID_TASK",
    "INVALID_CONFIRMATION",
    "INVALID_TOKEN",
    "FORM_MALFORMED",
)
"""The closed error-code vocabulary of the v2 form layer."""

_FIELD_KINDS = frozenset(
    {"identifier", "revision", "task", "confirm", "token"}
)


class V2FormError(ValueError):
    """One closed form-contract rejection."""

    def __init__(self, code: str, message: str | None = None) -> None:
        if code not in V2_FORM_ERROR_CODES:
            raise ValueError("unknown v2 form error code")
        super().__init__(message if message is not None else code)
        self.code = code


def v2_identifier(value: object, field_name: str) -> str:
    """Parse one bounded opaque identifier (never a path)."""

    if not isinstance(value, str) or V2_IDENTIFIER_RE.fullmatch(value) is None:
        raise V2FormError("INVALID_IDENTIFIER")
    return value


def v2_revision(value: object, field_name: str) -> int:
    """Parse one non-negative decimal revision."""

    if (
        not isinstance(value, str)
        or V2_REVISION_RE.fullmatch(value) is None
        or int(value) > 2_147_483_647
    ):
        raise V2FormError("INVALID_REVISION")
    return int(value)


def v2_task(value: object, field_name: str) -> str:
    """Parse one bounded, non-empty task text."""

    if not isinstance(value, str) or not value:
        raise V2FormError("INVALID_TASK")
    if len(value) > V2_TASK_MAX_CHARS:
        raise V2FormError("INVALID_TASK")
    if "\x00" in value:
        raise V2FormError("INVALID_TASK")
    return value


def v2_confirmation(value: object, field_name: str) -> str:
    """Parse the exact confirmation literal."""

    if value != V2_CONFIRM_LITERAL:
        raise V2FormError("INVALID_CONFIRMATION")
    return value


def v2_csrf_token(value: object, field_name: str) -> str:
    """Parse one closed CSRF synchronizer token."""

    if not isinstance(value, str) or V2_TOKEN_RE.fullmatch(value) is None:
        raise V2FormError("INVALID_TOKEN")
    return value


_PARSERS = {
    "identifier": v2_identifier,
    "revision": v2_revision,
    "task": v2_task,
    "confirm": v2_confirmation,
    "token": v2_csrf_token,
}


class V2FormContract:
    """One closed form shape: an exact field set with typed parsers.

    ``fields`` is the ordered tuple of ``(name, kind)`` pairs.  ``parse``
    requires the form's key set to equal the contract's field set
    exactly — any unknown or missing field rejects — and then parses
    every value with its closed parser, returning the typed mapping.
    """

    def __init__(
        self, endpoint: str, fields: Sequence[tuple[str, str]]
    ) -> None:
        if not isinstance(endpoint, str) or not endpoint:
            raise ValueError("endpoint must be a non-empty string")
        self._endpoint = endpoint
        self._fields = tuple(fields)
        seen: set[str] = set()
        for name, kind in self._fields:
            if not isinstance(name, str) or not name:
                raise ValueError("field names must be non-empty strings")
            if name in seen:
                raise ValueError(f"duplicate form field: {name}")
            seen.add(name)
            if kind not in _FIELD_KINDS:
                raise ValueError(f"unknown form field kind: {kind}")

    @property
    def endpoint(self) -> str:
        return self._endpoint

    @property
    def fields(self) -> tuple[tuple[str, str], ...]:
        return self._fields

    def parse(self, form: Mapping[str, str]) -> dict[str, object]:
        """Parse one form against the contract, fail closed on any drift."""

        if not isinstance(form, Mapping):
            raise V2FormError("FORM_MALFORMED")
        expected = {name for name, _ in self._fields}
        actual = set(form)
        if actual - expected:
            raise V2FormError("UNKNOWN_FIELD")
        if expected - actual:
            raise V2FormError("MISSING_FIELD")
        parsed: dict[str, object] = {}
        for name, kind in self._fields:
            parsed[name] = _PARSERS[kind](form[name], name)
        return parsed


V2_RUN_START_FORM = V2FormContract(
    "run_start",
    (("task", "task"), ("confirm", "confirm"), ("csrf_token", "token")),
)

V2_WRITEBACK_APPROVE_FORM = V2FormContract(
    "writeback_approve",
    (
        ("run_id", "identifier"),
        ("candidate_id", "identifier"),
        ("candidate_revision", "revision"),
        ("confirm", "confirm"),
        ("csrf_token", "token"),
    ),
)

V2_WRITEBACK_APPLY_FORM = V2FormContract(
    "writeback_apply",
    (
        ("run_id", "identifier"),
        ("candidate_id", "identifier"),
        ("candidate_revision", "revision"),
        ("approval_id", "identifier"),
        ("confirm", "confirm"),
        ("csrf_token", "token"),
    ),
)

V2_RECOVERY_APPLY_FORM = V2FormContract(
    "recovery_apply",
    (("transaction_id", "identifier"), ("confirm", "confirm"), ("csrf_token", "token")),
)

V2_RUN_DETAIL_QUERY = V2FormContract("run_detail", (("run_id", "identifier"),))

V2_RECOVERY_PREVIEW_QUERY = V2FormContract(
    "recovery_preview", (("transaction_id", "identifier"),)
)

V2_CREDENTIAL_QUERY = V2FormContract("credentials", (("provider", "identifier"),))


def parse_v2_urlencoded(body: str) -> dict[str, str]:
    """Parse one URL-encoded body into flat fields, fail closed.

    Repeated fields (HTTP parameter pollution) reject, an excessive
    field count rejects, and malformed bodies reject — each with the
    closed ``V2FormError`` the server maps to an HTTP 400.
    """

    if not isinstance(body, str):
        raise V2FormError("FORM_MALFORMED")
    try:
        pairs = parse_qs(
            body,
            keep_blank_values=True,
            strict_parsing=False,
            max_num_fields=V2_MAX_FORM_FIELDS,
        )
    except (ValueError, UnicodeError):
        raise V2FormError("FORM_MALFORMED") from None
    flat: dict[str, str] = {}
    for key, values in pairs.items():
        if not isinstance(key, str) or not key:
            raise V2FormError("FORM_MALFORMED")
        if len(key) > 128:
            raise V2FormError("FORM_MALFORMED")
        if len(values) != 1:
            raise V2FormError("DUPLICATE_FIELD")
        flat[key] = values[0]
    if len(flat) > V2_MAX_FORM_FIELDS:
        raise V2FormError("FORM_MALFORMED")
    return flat


__all__ = [
    "V2_CONFIRM_LITERAL",
    "V2_CREDENTIAL_QUERY",
    "V2FormContract",
    "V2FormError",
    "V2_FORM_ERROR_CODES",
    "V2_IDENTIFIER_RE",
    "V2_MAX_FORM_FIELDS",
    "V2_RECOVERY_APPLY_FORM",
    "V2_RECOVERY_PREVIEW_QUERY",
    "V2_REVISION_RE",
    "V2_RUN_DETAIL_QUERY",
    "V2_RUN_START_FORM",
    "V2_TASK_MAX_CHARS",
    "V2_TOKEN_RE",
    "V2_WRITEBACK_APPROVE_FORM",
    "V2_WRITEBACK_APPLY_FORM",
    "parse_v2_urlencoded",
    "v2_confirmation",
    "v2_csrf_token",
    "v2_identifier",
    "v2_revision",
    "v2_task",
]
