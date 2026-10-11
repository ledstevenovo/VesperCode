"""The v2 streaming TUI package.

The TUI is a lazily-shipped surface: only ``v2_launch`` (the injectable
launch spec and the offline demo factory) and ``v2_view_model`` (the
pure presentation state) are importable without ``textual``; the real
app lives in ``v2_app`` and imports textual at module level, so the
v2 CLI core and every offline test never pay the dependency (the
console entry imports ``v2_app`` only when the ``tui`` command runs).
"""

from __future__ import annotations

__all__: list[str] = []
