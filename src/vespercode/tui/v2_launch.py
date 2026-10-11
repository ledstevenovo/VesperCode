"""Launch composition of the v2 streaming TUI (stdlib-only surface).

``V2TuiLaunchSpec`` is the closed, injectable hand-off between the CLI
composition and the textual app: the workspace the loop runs over, the
pre-filled task, the turn budget, and one LLM factory producing a fresh
streaming v2 boundary per run.  The default factory is the scripted
streaming mock (``llm.v2.ScriptedStreamLLMV2``) over the mechanism demo
script — guardrail denial, feedback recovery, DONE — so the TUI is a
fully offline, deterministic, key-free demonstration.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from vespercode.llm.v2 import ScriptedStreamLLMV2

DEFAULT_DEMO_TASK = "fix the failing example without touching its test"
"""The task pre-filled by the offline scripted demo."""

_DEMO_ACTIONS: tuple[dict[str, str], ...] = (
    {
        "action_type": "REPLACE",
        "path": "tests/test_example.py",
        "content": "watered-down assertion",
    },
    {
        "action_type": "REPLACE",
        "path": "src/example.py",
        "content": "fixed body\n",
    },
    {"action_type": "DONE"},
)
"""Guardrail denial, feedback-driven recovery, stop — the demo loop."""

_DEMO_REASONING = "checking protected paths before staging a write"


def build_demo_llm_factory() -> Callable[[], ScriptedStreamLLMV2]:
    """One fresh scripted streaming mock per run (deterministic, offline)."""

    def factory() -> ScriptedStreamLLMV2:
        return ScriptedStreamLLMV2(
            [dict(action) for action in _DEMO_ACTIONS],
            chunk_size=6,
            reasoning=_DEMO_REASONING,
        )

    return factory


@dataclass(frozen=True, slots=True)
class V2TuiLaunchSpec:
    """The closed launch hand-off for the streaming TUI."""

    workspace: Path
    task: str
    max_turns: int
    llm_factory: Callable[[], Any]

    def __post_init__(self) -> None:
        if not isinstance(self.workspace, Path):
            raise TypeError("workspace must be a Path")
        if not isinstance(self.task, str) or not self.task:
            raise ValueError("task must be a non-empty string")
        if isinstance(self.max_turns, bool) or not isinstance(self.max_turns, int):
            raise ValueError("max_turns must be an integer")
        if self.max_turns < 1:
            raise ValueError("max_turns must be positive")
        if not callable(self.llm_factory):
            raise TypeError("llm_factory must be callable")


__all__ = ["DEFAULT_DEMO_TASK", "V2TuiLaunchSpec", "build_demo_llm_factory"]
