"""Explicit session-undo outcomes for independent command tests.

Command registrations need no fake: provide ``shiori_sdk.commands.CommandRegistry``
as ``COMMANDS`` on the fake context's kernel.
"""

from collections.abc import Callable
from shiori_sdk.sessions import UndoSessionResult


class FakeSessionUndo:
    """Return an explicitly seeded host result, recording preview-before-delete order."""

    def __init__(self, result: UndoSessionResult | None = None):
        self.result = result
        self.deleted = False
        self.rollback_sources: list[str] = []
        self.calls: list[str] = []

    async def undo_last_turn(
        self,
        session_key: str,
        *,
        rollback_source_resolver: Callable[[list[str]], list[str]] | None = None,
    ) -> UndoSessionResult | None:
        """Invoke the plugin's resolver before reporting the configured atomic deletion."""
        self.calls.append(session_key)
        if self.result is not None:
            if rollback_source_resolver is not None:
                self.rollback_sources = rollback_source_resolver(
                    list(self.result.deleted_ids)
                )
            self.deleted = True
        return self.result
