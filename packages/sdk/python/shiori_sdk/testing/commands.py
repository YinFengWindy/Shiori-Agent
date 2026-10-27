"""Explicit session-rollback outcomes for independent command tests.

Command registrations need no fake: provide ``shiori_sdk.commands.CommandRegistry``
as ``COMMANDS`` on the fake context's kernel. Provide a ``FakeSessions`` as
``SESSIONS`` when the command rolls a turn back.
"""

from collections.abc import Sequence

from shiori_sdk.core.sessions import PassiveTurn, RollbackResult, TurnChanged


class FakeSessions:
    """A session whose latest passive turn is the seeded ``result``.

    ``last_passive_turn`` reads it, ``rollback_last_turn`` deletes it. Replace
    ``result`` between the two calls to model a turn committed in between.
    """

    def __init__(self, result: RollbackResult | None = None):
        self.result = result
        self.deleted = False
        self.source_ids: tuple[str, ...] | None = None
        self.calls: list[str] = []

    def last_passive_turn(self, session_key: str) -> PassiveTurn | None:
        """The seeded turn, or None when this fake has no turn to undo."""
        if self.result is None:
            return None
        return PassiveTurn(self.result.turn_id, self.result.deleted_ids)

    async def rollback_last_turn(
        self,
        session_key: str,
        *,
        expected_turn: PassiveTurn | None = None,
        rollback_source_ids: Sequence[str] = (),
    ) -> RollbackResult | TurnChanged | None:
        """Delete the seeded turn unless it is not exactly ``expected_turn``."""
        self.calls.append(session_key)
        result = self.result
        if result is None:
            return None
        if expected_turn is not None and expected_turn != PassiveTurn(
            result.turn_id, result.deleted_ids
        ):
            return TurnChanged(result.turn_id)
        self.source_ids = tuple(rollback_source_ids)
        self.deleted = True
        return result
