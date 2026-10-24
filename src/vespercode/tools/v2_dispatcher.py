"""Deterministic v2 tool dispatch with policy interception."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from vespercode.contracts.v2_writeback import (
    PlannedWriteV2,
    WorkspaceContentMismatchError,
    WriteOperationV2,
)
from vespercode.governance.relaxed_policy import (
    ActionRequestV2,
    DecisionV2,
    RelaxedPolicyV2,
)


@dataclass(frozen=True, slots=True)
class V2ToolResult:
    status: str
    message: str
    path: str | None = None
    error: Exception | None = None


@dataclass
class InMemoryWorkspacePort:
    """Deterministic staging port.

    The loop stages candidate content here; real disk mutation happens only
    through the approval-gated writeback services.  ``apply``/``remove``
    implement the strict CREATE/REPLACE semantics of the
    ``V2WorkspacePort`` protocol so the writeback and recovery services can
    be tested offline without touching the filesystem.
    """

    files: dict[str, str] = field(default_factory=dict)

    def replace(self, path: str, content: str) -> None:
        self.files[path] = content

    def read_text(self, path: str) -> str | None:
        return self.files.get(path)

    def exists(self, path: str) -> bool:
        return path in self.files

    def validate(self, operation: WriteOperationV2) -> None:
        if operation.action_type == "CREATE" and operation.path in self.files:
            raise ValueError(f"CREATE target already exists: {operation.path}")
        if operation.action_type == "REPLACE" and operation.path not in self.files:
            raise ValueError(f"REPLACE target does not exist: {operation.path}")

    def apply(self, planned: PlannedWriteV2) -> None:
        """Publish a planned write; refuse changed bytes (compare-and-publish)."""

        self.validate(planned.operation)
        current = self.files.get(planned.operation.path)
        if (
            planned.operation.action_type == "REPLACE"
            and current != planned.expected_original
        ):
            raise WorkspaceContentMismatchError(
                "target changed after preflight; refusing to overwrite: "
                f"{planned.operation.path}"
            )
        self.files[planned.operation.path] = planned.operation.content

    def remove_expected(self, path: str, expected_content: str) -> None:
        """Delete a file only if it still holds exactly the expected bytes."""
        current = self.files.get(path)
        if current != expected_content:
            raise WorkspaceContentMismatchError(
                f"target changed after observation; refusing to remove: {path}"
            )
        del self.files[path]


class V2ToolDispatcher:
    def __init__(
        self,
        workspace: InMemoryWorkspacePort,
        policy: RelaxedPolicyV2 | None = None,
    ) -> None:
        self._workspace = workspace
        self._policy = policy or RelaxedPolicyV2()

    def dispatch(self, action: dict[str, object], workspace: Path) -> V2ToolResult:
        if set(action) - {"action_type", "path", "content"}:
            return V2ToolResult("FAILED", "unknown action field")
        action_type = action.get("action_type")
        if action_type == "DONE":
            if set(action) != {"action_type"}:
                return V2ToolResult("FAILED", "DONE cannot carry action fields")
            return V2ToolResult("DONE", "model requested stop")
        if action.get("action_id") is not None:
            return V2ToolResult("FAILED", "model-supplied action_id is forbidden")
        if action_type != "REPLACE":
            return V2ToolResult("FAILED", "unsupported v2 action")
        path = action.get("path")
        content = action.get("content")
        if not isinstance(path, str) or not isinstance(content, str):
            return V2ToolResult("FAILED", "REPLACE requires string path and content")
        decision = self._policy.evaluate(ActionRequestV2("REPLACE", path, workspace))
        if decision is DecisionV2.DENY:
            return V2ToolResult("DENIED", f"protected or unsafe path: {path}", path)
        self._workspace.replace(path, content)
        return V2ToolResult("SUCCESS", f"replaced {path}", path)


__all__ = ["InMemoryWorkspacePort", "V2ToolDispatcher", "V2ToolResult"]
