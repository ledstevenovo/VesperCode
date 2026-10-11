"""Route A / RA-08: deterministic conservative secret-content scanner.

The writeback journal persists staged content and observed originals into
the local v2 control database.  The path policy keeps sensitive FILES out,
but an ordinary ``src/*.py`` can still carry a credential, so this scanner
runs at the writeback pre-journal boundary: a hit refuses the writeback
before any port write, before the approval is consumed, and before a
transaction or journal row exists.

The scanner is deliberately conservative:

- it matches assignment spellings (``api_key =``, ``password:``, ``token=``
  and case-insensitive variants), so ordinary code that merely *mentions*
  credential handling can be refused as a false positive;
- it matches PEM private-key headers (but not public certificates);
- it matches high-entropy provider token shapes (GitHub, Slack, OpenAI/
  Anthropic project keys, Stripe, AWS access key ids, Google API keys,
  npm tokens, JWT-shaped segments) with enough structure to avoid everyday
  text;
- it performs no entropy detection: an unstructured random secret with no
  recognizable marker is NOT caught.

The returned marker is a fixed spelling or a safe category label from this
module; the matched secret material itself is never returned, so markers
are safe to log.

Standard library only; no digest, no v1 module reuse.
"""

from __future__ import annotations

import re

PROVIDER_TOKEN_MARKER = "provider-token"

_ASSIGNMENT_PATTERN = re.compile(
    r"\b(api[_-]?key|client_secret|secret|access_token|refresh_token|"
    r"auth_token|token|password|passwd|pwd)\s*[=:]"
)
_BEARER_PATTERN = re.compile(r"(?:authorization\s*:\s*bearer|bearer)\s")
_PEM_PRIVATE_KEY_MARKERS = (
    "-----begin private key",
    "-----begin rsa private key",
    "-----begin ec private key",
    "-----begin dsa private key",
    "-----begin openssh private key",
    "-----begin pgp private key",
    "-----begin encrypted private key",
)
# All matching is case-insensitive; patterns are written in the lowercase
# form matched against a casefolded copy of the scanned text.
_PROVIDER_TOKEN_PATTERN = re.compile(
    r"(?:gh[pousr]_[0-9a-z]{20,}"  # GitHub user/OAuth/app tokens
    r"|github_pat_[0-9a-z_]{20,}"  # GitHub fine-grained PAT
    r"|xox[abprs]-[0-9a-z-]{10,}"  # Slack tokens
    r"|sk-(?:proj|ant)-[0-9a-z_\-]{20,}"  # OpenAI/Anthropic project keys
    r"|(?:sk|rk)_(?:live|test)_[0-9a-z]{20,}"  # Stripe secret/restricted keys
    r"|akia[0-9a-z]{16}"  # AWS access key id
    r"|aiza[0-9a-z_\-]{35}"  # Google API key
    r"|npm_[0-9a-z]{30,}"  # npm granular token
    r"|ey[a-z0-9_-]{10,}\.[a-z0-9_-]{10,}\.[a-z0-9_-]{10,})"  # JWT shape
)


def find_secret_marker(text: str) -> str | None:
    """Return a static marker id if the text looks secret-like, else None.

    The marker identifies the *category* of the hit (a fixed assignment
    spelling, a PEM header, or the label ``provider-token``); it never
    contains the matched secret material, so it is safe to log.
    """

    if not isinstance(text, str) or not text:
        return None
    lowered = text.casefold()
    assignment = _ASSIGNMENT_PATTERN.search(lowered)
    if assignment is not None:
        return f"{assignment.group(1)}="
    if _BEARER_PATTERN.search(lowered) is not None:
        return "bearer-token"
    for marker in _PEM_PRIVATE_KEY_MARKERS:
        if marker in lowered:
            return marker
    if _PROVIDER_TOKEN_PATTERN.search(lowered) is not None:
        return PROVIDER_TOKEN_MARKER
    return None


def contains_secret_like_content(text: str) -> bool:
    """True when the text must not be journaled by the writeback boundary."""

    return find_secret_marker(text) is not None


__all__ = [
    "PROVIDER_TOKEN_MARKER",
    "contains_secret_like_content",
    "find_secret_marker",
]
