from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from shiori_sdk.commands import CommandInput
from shiori_sdk.core.conversation import COMMANDS
from shiori_sdk.core.memory import MEMORY_ENGINE
from shiori_sdk.core.sessions import SESSIONS, Sessions
from shiori_sdk.memory.engine import MemoryEngine, TurnRollback

if TYPE_CHECKING:
    from shiori_sdk.extensions import CommandPluginContext as PluginRuntimeContext

logger = logging.getLogger("plugin.undo")

_NO_TURN = "没有可撤销的上一轮对话。"


class PluginUndo:
    """Roll back the latest passive turn: memory first, then the session.

    ``current_memory`` is read immediately before the synchronous memory
    rollback and is not used after the session await (D25). An empty socket
    rolls back the session only. Memory failure leaves the session in place
    so the command can be retried. The two calls are not one transaction: a
    session failure after memory has already rolled back is reported, not
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
        memory = TurnRollback()
        memory_rolled_back = False
        if engine is not None:
            turn_id = sessions.last_passive_turn_id(session_key) or ""
            if not turn_id:
                return _NO_TURN
            try:
                memory = engine.rollback_turn(turn_id)
            except Exception:
                logger.exception(
                    "undo memory rollback failed; session left in place: session=%s turn_id=%s",
                    session_key,
                    turn_id,
                )
                return "记忆回滚失败，上一轮对话还在。可以重试。"
            memory_rolled_back = True
        try:
            result = await sessions.rollback_last_turn(
                session_key,
                rollback_source_ids=list(memory.rollback_source_ids) or None,
            )
        except Exception:
            if not memory_rolled_back:
                raise
            logger.exception(
                "undo session rollback failed after memory rollback: session=%s affected=%s restored=%s",
                session_key,
                memory.affected_ids,
                memory.restored_ids,
            )
            return _session_failure_reply(memory)
        if result is None:
            if memory_rolled_back:
                return (
                    "会话里已经没有可撤销的上一轮，但记忆已回滚。"
                    f"\n失效记忆：{len(memory.affected_ids)} 条"
                    f"\n恢复旧记忆：{len(memory.restored_ids)} 条"
                )
            return _NO_TURN
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
            "已撤销上一轮对话。"
            f"\n删除消息：{len(result.deleted_ids)} 条"
            f"\n失效记忆：{len(memory.affected_ids)} 条"
            f"\n恢复旧记忆：{len(memory.restored_ids)} 条"
        )


def _session_failure_reply(memory: TurnRollback) -> str:
    return (
        "记忆已回滚，但会话撤销失败。"
        f"\n失效记忆：{len(memory.affected_ids)} 条"
        f"\n恢复旧记忆：{len(memory.restored_ids)} 条"
        "\n请查看日志后重试。"
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
