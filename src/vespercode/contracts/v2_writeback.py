"""Frozen v2 writeback interfaces (Route A / A0).

These value objects are the stable contract between the v2 loop/staging
world and the real writeback and recovery services.  They deliberately
carry no content digest: identity and authorization come from opaque
references plus candidate revisions, and ordinary byte comparison is the
only content check used during write verification or recovery.

A ``PlannedWriteV2`` binds a REPLACE to the exact original bytes it is
allowed to overwrite, so the port can compare-and-publish: publication
refuses an externally modified target instead of overwriting it.

The module is standard-library only and importable without any filesystem,
network, or LLM dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

ALLOWED_WRITE_ACTION_TYPES = frozenset({"CREATE", "REPLACE"})
ACTIVE_TRANSACTION_STATES = frozenset({"PREPARED", "WRITING", "UNRESOLVED"})
TERMINAL_TRANSACTION_STATES = frozenset({"COMMITTED", "ROLLED_BACK"})


class TransactionStateV2(str, Enum):
    """Durable writeback transaction states.

    ``PREPARED`` -> ``WRITING`` -> ``COMMITTED`` is the happy path.  A fault
    during writing marks ``UNRESOLVED``; recovery may then re-drive the
    write (``WRITING``/``COMMITTED``) or restore the recorded originals
    (``ROLLED_BACK``).  Terminal states never change again.
    """

    PREPARED = "PREPARED"
    WRITING = "WRITING"
    COMMITTED = "COMMITTED"
    UNRESOLVED = "UNRESOLVED"
    ROLLED_BACK = "ROLLED_BACK"


class WritebackStatusV2(str, Enum):
    """Fail-closed outcomes of one explicit writeback request."""

    COMMITTED = "COMMITTED"
    DENIED = "DENIED"
    STALE = "STALE"
    MISMATCH = "MISMATCH"
    FAILED = "FAILED"


def _identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _revision(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("revision must be a non-negative integer")
    return value


def _write_path(value: str) -> str:
    """Lexical guards for a canonical relative POSIX-style path.

    Deep filesystem checks (confinement, reparse points, file types) belong
    to the workspace boundary; these guards keep garbage out of journals.
    """

    if not isinstance(value, str) or not value:
        raise ValueError("path must be a non-empty string")
    if "\x00" in value or "\r" in value or "\n" in value:
        raise ValueError("path must not contain control characters")
    if "\\" in value:
        raise ValueError("path must use '/' separators only")
    if ":" in value:
        raise ValueError("path must not contain a drive or stream separator")
    if value.startswith("/"):
        raise ValueError("path must be relative, not absolute")
    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError("path must be canonical: no empty, '.', or '..' segments")
    if any(any(ord(char) < 0x20 for char in part) for part in raw_parts):
        raise ValueError("path must not contain control characters")
    return value


def _action_type(value: str) -> str:
    if not isinstance(value, str) or value not in ALLOWED_WRITE_ACTION_TYPES:
        raise ValueError("action_type must be one of 'CREATE' or 'REPLACE'")
    return value


def _content(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("content must be a string")
    return value


@dataclass(frozen=True, slots=True)
class WriteOperationV2:
    """One explicit file mutation: CREATE a new file or REPLACE an existing."""

    action_type: str
    path: str
    content: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "action_type", _action_type(self.action_type))
        object.__setattr__(self, "path", _write_path(self.path))
        object.__setattr__(self, "content", _content(self.content))


@dataclass(frozen=True, slots=True)
class JournalEntryV2:
    """One durable journal row: the intended write plus the observed bytes.

    ``original_content`` is ``None`` for CREATE (the target must not exist)
    and the bytes read at prepare time for REPLACE.  It exists for ordinary
    recovery comparison only; it is not an identity or authorization value.
    """

    position: int
    path: str
    action_type: str
    content: str
    original_content: str | None

    def __post_init__(self) -> None:
        if isinstance(self.position, bool) or not isinstance(self.position, int):
            raise ValueError("position must be an integer")
        if self.position < 0:
            raise ValueError("position must be non-negative")
        object.__setattr__(self, "action_type", _action_type(self.action_type))
        object.__setattr__(self, "path", _write_path(self.path))
        object.__setattr__(self, "content", _content(self.content))
        if self.action_type == "REPLACE" and not isinstance(self.original_content, str):
            raise ValueError("REPLACE journal entries require original_content")
        if self.action_type == "CREATE" and self.original_content is not None:
            raise ValueError("CREATE journal entries must not carry original_content")

    def operation(self) -> WriteOperationV2:
        """The intended write, without its publish-time content binding."""

        return WriteOperationV2(self.action_type, self.path, self.content)

    def planned(self) -> "PlannedWriteV2":
        """The intended write bound to the bytes it may overwrite."""

        return PlannedWriteV2(self.operation(), self.original_content)

    def planned_restore(self) -> "PlannedWriteV2":
        """The undo of an applied write, bound to the applied bytes.

        Restoring a REPLACE expects the journaled content on disk (the
        applied write) and publishes the recorded original, so an external
        change after the apply is refused instead of overwritten.
        """

        if self.action_type != "REPLACE":
            raise ValueError("only REPLACE entries define a restore plan")
        assert self.original_content is not None
        return PlannedWriteV2(
            WriteOperationV2("REPLACE", self.path, self.original_content),
            self.content,
        )


class WorkspaceContentMismatchError(ValueError):
    """The target no longer holds the bytes a planned write may replace.

    Raised by workspace ports immediately before publication when the
    current target content differs from the plan's expected original (or
    the target cannot be read for comparison).  This is the compare-and-
    publish guard against overwriting external changes; it uses ordinary
    byte/text comparison, never a content digest.
    """


@dataclass(frozen=True, slots=True)
class PlannedWriteV2:
    """A write operation bound to the exact original bytes it may replace.

    ``expected_original`` is ``None`` for CREATE (the target must not
    exist at publication time) and the observed original bytes for
    REPLACE.  Ports must verify it immediately before publishing so an
    external modification between preflight and publication refuses the
    write instead of overwriting it.
    """

    operation: WriteOperationV2
    expected_original: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.operation, WriteOperationV2):
            raise ValueError("operation must be a WriteOperationV2")
        if (
            not isinstance(self.expected_original, str)
            and self.expected_original is not None
        ):
            raise ValueError("expected_original must be a string or None")
        if (
            self.operation.action_type == "CREATE"
            and self.expected_original is not None
        ):
            raise ValueError("CREATE plans must not expect original content")
        if self.operation.action_type == "REPLACE" and not isinstance(
            self.expected_original, str
        ):
            raise ValueError("REPLACE plans require expected_original")


@dataclass(frozen=True, slots=True)
class WritebackRequestV2:
    """An explicit, user-approved request to write candidate content to disk."""

    run_id: str
    candidate_id: str
    candidate_revision: int
    approval_id: str
    operations: tuple[WriteOperationV2, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _identifier(self.run_id, "run_id"))
        object.__setattr__(
            self, "candidate_id", _identifier(self.candidate_id, "candidate_id")
        )
        object.__setattr__(
            self, "candidate_revision", _revision(self.candidate_revision)
        )
        object.__setattr__(
            self, "approval_id", _identifier(self.approval_id, "approval_id")
        )
        if not isinstance(self.operations, tuple):
            raise ValueError("operations must be a tuple of WriteOperationV2")
        if not self.operations:
            raise ValueError("operations must contain at least one write")
        for operation in self.operations:
            if not isinstance(operation, WriteOperationV2):
                raise ValueError("operations must contain only WriteOperationV2 values")


@dataclass(frozen=True, slots=True)
class WritebackOutcomeV2:
    """Fail-closed result of one writeback request."""

    status: str
    transaction_id: str | None
    message: str

    def __post_init__(self) -> None:
        if self.status not in {status.value for status in WritebackStatusV2}:
            raise ValueError("status must be a WritebackStatusV2 value")
        if not isinstance(self.message, str) or not self.message:
            raise ValueError("message must be a non-empty string")


@dataclass(frozen=True, slots=True)
class RecoveryItemV2:
    """Byte-comparison verdict for one journal row during recovery preview."""

    position: int
    path: str
    action_type: str
    state: str

    def __post_init__(self) -> None:
        if self.state not in {"APPLIED", "PENDING", "DRIFTED", "UNREADABLE"}:
            raise ValueError(
                "recovery item state must be APPLIED, PENDING, DRIFTED, or UNREADABLE"
            )


@dataclass(frozen=True, slots=True)
class RecoveryPreviewV2:
    """Restart-safe preview of a non-terminal transaction."""

    transaction_id: str
    transaction_state: str
    items: tuple[RecoveryItemV2, ...]
    blocked: bool

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple):
            raise ValueError("items must be a tuple of RecoveryItemV2")
        if self.transaction_state not in ACTIVE_TRANSACTION_STATES:
            raise ValueError("preview requires a non-terminal transaction state")
        if self.blocked != any(
            item.state in {"DRIFTED", "UNREADABLE"} for item in self.items
        ):
            raise ValueError(
                "blocked must match the presence of DRIFTED or UNREADABLE items"
            )


@dataclass(frozen=True, slots=True)
class RecoveryOutcomeV2:
    """Fail-closed result of one recovery apply or rollback."""

    status: str
    transaction_id: str
    message: str

    def __post_init__(self) -> None:
        if self.status not in {"APPLIED", "ROLLED_BACK", "BLOCKED", "FAILED"}:
            raise ValueError("status must be APPLIED, ROLLED_BACK, BLOCKED, or FAILED")
        if not isinstance(self.message, str) or not self.message:
            raise ValueError("message must be a non-empty string")


@runtime_checkable
class V2WorkspacePort(Protocol):
    """The filesystem authority the writeback and recovery services depend on.

    Implementations must fail closed: unsafe reads raise instead of
    following links or reparse points, ``read_text`` returns ``None`` only
    for a cleanly absent regular file, ``validate`` checks a target without
    mutating anything, ``apply`` publishes only ``PlannedWriteV2`` values —
    rechecking the target immediately before the mutation and, for REPLACE,
    verifying by ordinary byte/text comparison that the target still holds
    exactly the expected original bytes — and ``remove_expected`` deletes a
    file only after verifying the same way that it still holds exactly the
    journaled bytes, so an external change between a recovery observation
    and the removal is refused instead of deleted.  No unbound removal
    exists in the protocol.
    """

    def read_text(self, path: str) -> str | None: ...

    def exists(self, path: str) -> bool: ...

    def validate(self, operation: WriteOperationV2) -> None: ...

    def apply(self, planned: "PlannedWriteV2") -> None: ...

    def remove_expected(self, path: str, expected_content: str) -> None: ...


__all__ = (
    "ACTIVE_TRANSACTION_STATES",
    "ALLOWED_WRITE_ACTION_TYPES",
    "JournalEntryV2",
    "PlannedWriteV2",
    "RecoveryItemV2",
    "RecoveryOutcomeV2",
    "RecoveryPreviewV2",
    "TERMINAL_TRANSACTION_STATES",
    "TransactionStateV2",
    "V2WorkspacePort",
    "WorkspaceContentMismatchError",
    "WritebackOutcomeV2",
    "WritebackRequestV2",
    "WritebackStatusV2",
    "WriteOperationV2",
)
