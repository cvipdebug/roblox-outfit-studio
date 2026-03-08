"""
core/history.py - Undo/redo command history for the canvas editor.

Uses a command-stack pattern: each operation is represented as a
CanvasState snapshot so that undo is simply restoring the previous
snapshot.  For large canvases a delta-based approach would save
memory, but snapshots keep the code simple and robust.
"""

from __future__ import annotations

from typing import List, Optional
from core.models import CanvasState


class HistoryManager:
    """
    Manages undo/redo history for the canvas.

    Each time a destructive edit is made the caller should call
    ``push(state)`` with a snapshot of the canvas *before* the
    edit.  ``undo()`` restores the most recent snapshot;
    ``redo()`` re-applies it.

    Args:
        max_steps: Maximum number of undo steps to keep in memory.
    """

    def __init__(self, max_steps: int = 100) -> None:
        self._max_steps = max_steps
        self._undo_stack: List[CanvasState] = []
        self._redo_stack: List[CanvasState] = []

    # ── Public API ───────────────────────────────────────────────────────────

    def push(self, state: CanvasState) -> None:
        """
        Push a *snapshot* of the canvas onto the undo stack.

        Call this *before* applying a destructive edit so that
        undo restores the state the user saw before the change.
        """
        self._undo_stack.append(state.snapshot())
        if len(self._undo_stack) > self._max_steps:
            self._undo_stack.pop(0)
        # Any new action clears the redo branch
        self._redo_stack.clear()

    def undo(self, current_state: CanvasState) -> Optional[CanvasState]:
        """
        Pop the undo stack and return the state to restore.

        The *current* state is saved to the redo stack so the user
        can redo the operation.  Returns ``None`` if there is
        nothing to undo.
        """
        if not self._undo_stack:
            return None
        self._redo_stack.append(current_state.snapshot())
        return self._undo_stack.pop()

    def redo(self, current_state: CanvasState) -> Optional[CanvasState]:
        """
        Pop the redo stack and return the state to restore.

        Returns ``None`` if there is nothing to redo.
        """
        if not self._redo_stack:
            return None
        self._undo_stack.append(current_state.snapshot())
        return self._redo_stack.pop()

    def clear(self) -> None:
        """Clear all undo/redo history."""
        self._undo_stack.clear()
        self._redo_stack.clear()

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    @property
    def undo_count(self) -> int:
        return len(self._undo_stack)

    @property
    def redo_count(self) -> int:
        return len(self._redo_stack)
