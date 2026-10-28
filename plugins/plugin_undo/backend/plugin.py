from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from shiori_sdk.commands import CommandInput
from shiori_sdk.core.conversation import COMMANDS
from shiori_sdk.core.memory import MEMORY_ENGINE
from shiori_sdk.core.sessions import SESSIONS, RollbackResult, Sessions, TurnChanged
from shiori_sdk.memory.engine import MemoryEngine, TurnRollback

if TYPE_CHECKING:
    from shiori_sdk.runtime import PluginRuntimeContext

logger = logging.getLogger("plugin.undo")

_NO_TURN = "没有可撤销的上一轮对话。"


class PluginUndo:
    """Roll back the latest passive turn: memory first, then the session.

    ``current_memory`` is read immediately before the synchronous memory
    rollback and is not used after the session await (D25). An empty socket
    rolls back the session only. Memory rolls back over every message id of
    the turn read before the session lock; the session then deletes that turn
    only if it is still the latest. Memory failure leaves the session in place
    so the command can be retried. The two calls are not one transaction: a
    session that fails or moved on after memory rolled back is reported, not
    undone inside this command (D10).
    """

    def __init__(
        self,
        sessions: Sessions,
        current_memory: Callable[[], MemoryEngine | None],
    ) -> None:
        self._sessions = sessions
        self._current_memory = current_memory

    async def undo(self, session_key: str) -> str:
        """Undo the latest committed passive turn and report what memory did."""
        sessions = self._sessions
        engine = self._current_memory()
        if engine is None:
            result = await sessions.rollback_last_turn(session_key)
            if not isinstance(result, RollbackResult):
                return _NO_TURN
            return _undone_reply(session_key, result, TurnRollback())
        turn = sessions.last_passive_turn(session_key)
        if turn is None:
            return _NO_TURN
        try:
            memory = engine.rollback_turn(turn.turn_id, turn.message_ids)
        except Exception:
            logger.exception(
                "undo memory rollback failed; session left in place: session=%s turn_id=%s",
                session_key,
                turn.turn_id,
            )
            return "记忆回滚失败，上一轮对话还在。可以重试。"
        try:
            result = await sessions.rollback_last_turn(
                session_key,
                expected_turn=turn,
                rollback_source_ids=memory.rollback_source_ids,
            )
        except Exception:
            logger.exception(
                "undo session rollback failed after memory rollback: session=%s affected=%s restored=%s",
                session_key,
                memory.affected_ids,
                memory.restored_ids,
            )
            return f"记忆已回滚，但会话撤销失败。{_memory_counts(memory)}\n请查看日志后重试。"
        if result is None:
            return (
                f"会话里已经没有可撤销的上一轮，但记忆已回滚。{_memory_counts(memory)}"
            )
        if isinstance(result, TurnChanged):
            logger.warning(
                "undo session moved on after memory rollback: session=%s rolled_back=%s latest=%s affected=%s",
                session_key,
                turn.turn_id,
                result.turn_id,
                memory.affected_ids,
            )
            return "已回滚上一轮的记忆，但会话里有新消息，上一轮对话未撤销。"
        return _undone_reply(session_key, result, memory)


def _memory_counts(memory: TurnRollback) -> str:
    return (
        f"\n失效记忆：{len(memory.affected_ids)} 条"
        f"\n恢复旧记忆：{len(memory.restored_ids)} 条"
    )


def _undone_reply(
    session_key: str, result: RollbackResult, memory: TurnRollback
) -> str:
    logger.info(
        "undo session=%s deleted=%d memory_superseded=%d memory_restored=%d last=%d->%d turn_id=%s",
        session_key,
        len(result.deleted_ids),
        len(memory.affected_ids),
        len(memory.restored_ids),
        result.last_consolidated_before,
        result.last_consolidated_after,
        result.turn_id,
    )
    return (
        f"已撤销上一轮对话。\n删除消息：{len(result.deleted_ids)} 条"
        f"{_memory_counts(memory)}"
    )


async def setup(ctx: "PluginRuntimeContext") -> None:
    """Register the scoped ``/undo`` command."""

    def current_memory() -> MemoryEngine | None:
        return ctx.get(MEMORY_ENGINE)

    plugin = PluginUndo(ctx.require(SESSIONS), current_memory)

    async def undo(command: CommandInput) -> str:
        return await plugin.undo(command.session_key)

    remove = ctx.require(COMMANDS).register("undo", undo, description="撤销上一轮对话")
    ctx.effect("command:undo", remove)
