"""Behavior-oriented v2 governance policy.

This policy intentionally does not authenticate content with a digest.  It
does enforce the controls that protect a user's machine: workspace
confinement, a closed action vocabulary, sensitive-path denial, and protected
project-control files.  The policy is pure and can be tested with no LLM,
filesystem mutation, or network access.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath


class DecisionV2(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


@dataclass(frozen=True, slots=True)
class ActionRequestV2:
    action_type: str
    path: str
    workspace: Path

    def __post_init__(self) -> None:
        if not isinstance(self.action_type, str) or not self.action_type:
            raise ValueError("action_type must be non-empty")
        if not isinstance(self.path, str):
            raise ValueError("path must be a string")
        if not isinstance(self.workspace, Path):
            raise ValueError("workspace must be a Path")


class RelaxedPolicyV2:
    """Small fail-closed policy for v2 candidate actions."""

    _READ_ACTIONS = frozenset({"READ_FILE", "LIST_FILES", "SEARCH_TEXT"})
    _WRITE_ACTIONS = frozenset({"CREATE", "REPLACE", "APPLY_PATCH"})
    _SAFE_ACTIONS = _READ_ACTIONS | _WRITE_ACTIONS
    _PROTECTED_ROOTS = frozenset(
        {
            ".git",
            ".github",
            ".venv",
            "config",
            "containers",
            "delivery",
            "gates",
            "requirements",
            "spikes",
            "tests",
        }
    )
    _PROTECTED_FILES = frozenset(
        {
            "AGENTS.md",
            "AGENT_LOG.md",
            "PLAN.md",
            "REFLECTION.md",
            "SPEC.md",
            "SPEC_PROCESS.md",
            ".gitignore",
            "pyproject.toml",
        }
    )
    _SENSITIVE_NAMES = frozenset(
        {
            ".env",
            ".env.local",
            ".env.production",
            "credentials.json",
            "secrets.json",
        }
    )

    def evaluate(self, request: ActionRequestV2) -> DecisionV2:
        """Return ``ALLOW`` only when every deterministic guard passes."""

        if request.action_type not in self._SAFE_ACTIONS:
            return DecisionV2.DENY
        relative = self._canonical_relative_path(request.path)
        if relative is None:
            return DecisionV2.DENY
        if not self._confined(request.workspace, relative):
            return DecisionV2.DENY
        if self._is_sensitive(relative):
            return DecisionV2.DENY
        if request.action_type in self._WRITE_ACTIONS and self._is_protected(relative):
            return DecisionV2.DENY
        if (
            request.action_type in self._WRITE_ACTIONS
            and len(relative.parts) == 1
            and relative.parts[0].casefold() == "src"
        ):
            return DecisionV2.DENY
        return DecisionV2.ALLOW

    @staticmethod
    def _canonical_relative_path(path: str) -> PurePosixPath | None:
        if not path or "\\" in path or "\x00" in path:
            return None
        # Inspect the original spelling before PurePosixPath normalizes away
        # empty and ``.`` segments.  v2 accepts ordinary relative references,
        # not aliases that happen to resolve to one.
        raw_parts = path.split("/")
        if any(part in {"", ".", ".."} for part in raw_parts):
            return None
        candidate = PurePosixPath(path)
        if candidate.is_absolute() or ":" in path:
            return None
        parts = candidate.parts
        if not parts or any(part in {"", ".", ".."} for part in parts):
            return None
        return candidate

    @staticmethod
    def _confined(workspace: Path, relative: PurePosixPath) -> bool:
        try:
            root = workspace.resolve(strict=False)
            target = (root / Path(*relative.parts)).resolve(strict=False)
            return target == root or root in target.parents
        except (OSError, RuntimeError, ValueError):
            return False

    def _is_sensitive(self, relative: PurePosixPath) -> bool:
        folded_names = {name.casefold() for name in self._SENSITIVE_NAMES}
        return any(
            part.casefold() in folded_names
            or part.casefold().startswith(".env.")
            or part.casefold().endswith((".pem", ".key", ".p12", ".pfx"))
            for part in relative.parts
        )

    def _is_protected(self, relative: PurePosixPath) -> bool:
        protected_roots = {root.casefold() for root in self._PROTECTED_ROOTS}
        protected_files = {name.casefold() for name in self._PROTECTED_FILES}
        return (
            relative.parts[0].casefold() in protected_roots
            or relative.parts[-1].casefold() in protected_files
        )


__all__ = ["ActionRequestV2", "DecisionV2", "RelaxedPolicyV2"]
