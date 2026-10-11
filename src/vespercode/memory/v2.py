"""Run-scoped v2 memory with no cross-run selection."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class V2MemoryEntry:
    run_id: str
    text: str
    source: str


class V2Memory:
    def __init__(self) -> None:
        self._entries: list[V2MemoryEntry] = []

    def remember(self, run_id: str, text: str, *, source: str) -> None:
        if not run_id or not text or not source:
            raise ValueError("memory entries require run, text, and source")
        lowered = text.casefold()
        if any(
            marker in lowered
            for marker in (
                "api_key=",
                "apikey=",
                "secret=",
                "token=",
                "access_token=",
                "password=",
                "password:",
                "authorization: bearer ",
                "bearer ",
                "-----begin ",
                "begin rsa private key",
                "begin ec private key",
                "begin openssh private key",
            )
        ):
            raise ValueError("secret-like memory content is not allowed")
        self._entries.append(V2MemoryEntry(run_id, text, source))

    def select(self, run_id: str, *, limit: int = 20) -> tuple[V2MemoryEntry, ...]:
        if limit < 1:
            raise ValueError("memory limit must be positive")
        return tuple(entry for entry in self._entries if entry.run_id == run_id)[-limit:]

    def clear(self, run_id: str) -> int:
        before = len(self._entries)
        self._entries = [entry for entry in self._entries if entry.run_id != run_id]
        return before - len(self._entries)


__all__ = ["V2Memory", "V2MemoryEntry"]
