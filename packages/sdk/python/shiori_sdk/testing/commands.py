"""Explicit session-rollback outcomes for independent command tests.

Command registrations need no fake: provide ``shiori_sdk.commands.CommandRegistry``
as ``COMMANDS`` on the fake context's kernel. Provide a ``FakeSessionUndo`` as
``SESSIONS`` when the command rolls a turn back.
"""

from shiori_sdk.core.sessions import RollbackResult


class FakeSessionUndo:
    """Return an explicitly seeded rollback, recording the session call."""

    def __init__(self, result: RollbackResult | None = None):
        self.result = result
        self.deleted = False
        self.source_ids: list[str] | None = None
        self.calls: list[str] = []
        self.turn_lookups: list[str] = []

    def last_passive_turn_id(self, session_key: str) -> str | None:
        """The seeded turn id, or None when this fake has no turn to undo."""
        self.turn_lookups.append(session_key)
        if self.result is None:
            return None
        return self.result.turn_id

    async def rollback_last_turn(
        self,
        session_key: str,
        *,
        rollback_source_ids: list[str] | None = None,
    ) -> RollbackResult | None:
        """Record the call and return the seeded result without touching a store."""
        self.calls.append(session_key)
        self.source_ids = (
            None if rollback_source_ids is None else list(rollback_source_ids)
        )
        if self.result is not None:
            self.deleted = True
        return self.result
