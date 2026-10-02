from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from shiori_sdk.commands import CommandFrame, normalize_command
from shiori_sdk.lifecycle import LifecycleFrame
from shiori_sdk.sessions import SessionUndo, MemoryUndo

if TYPE_CHECKING:
    from shiori_sdk.extensions import CommandPluginContext as PluginRuntimeContext

logger = logging.getLogger("plugin.undo")

_SESSION_SLOT = "session:session"
_CTX_SLOT = "session:ctx"


class UndoCommandModule:
    """Handle /undo before any retrieval or reasoning takes place."""

    slot = "plugin_undo.undo"
    requires = ("before_turn.acquire_session", _SESSION_SLOT)
    produces = (_CTX_SLOT,)

    def __init__(self, plugin: "PluginUndo") -> None:
        self._plugin = plugin

    async def run[FrameT: LifecycleFrame](self, frame: FrameT) -> FrameT:
        """Short-circuit a matching command unless an earlier module handled it."""
        if _CTX_SLOT in frame.slots or not isinstance(frame, CommandFrame):
            return frame
        state = frame.command
        if normalize_command(state.content) != "/undo":
            return frame
        reply = await self._plugin.undo(state.session_key)
        frame.abort_command(reply)
        return frame


class PluginUndo:
    """Coordinate public session undo and memory source cleanup."""

    def __init__(
        self, session_manager: SessionUndo, memory_engine: MemoryUndo | None
    ) -> None:
        self._session_manager = session_manager
        self._memory_engine = memory_engine

    async def undo(self, session_key: str) -> str:
        """Undo the latest committed passive turn and report memory cleanup results."""
        session_manager = self._session_manager
        memory_result: dict[str, object] = {
            "affected_ids": [],
            "restored_ids": [],
            "rollback_source_ids": [],
        }
        message_ids_for_memory: list[str] = []

        def resolve_sources(message_ids: list[str]) -> list[str]:
            nonlocal memory_result, message_ids_for_memory
            message_ids_for_memory = list(message_ids)
            memory_result = _undo_memory_sources(
                self._memory_engine,
                message_ids,
                dry_run=True,
            )
            return _string_list(memory_result.get("rollback_source_ids"))

        result = await session_manager.undo_last_turn(
            session_key,
            rollback_source_resolver=resolve_sources,
        )
        if result is None:
            return "没有可撤销的上一轮对话。"
        try:
            memory_result = _undo_memory_sources(
                self._memory_engine,
                message_ids_for_memory or result.deleted_ids,
                dry_run=False,
            )
        except Exception:
            logger.exception(
                "undo memory cleanup failed after session delete: session=%s deleted_ids=%s dry_run=%s",
                session_key,
                result.deleted_ids,
                memory_result,
            )
            return (
                "已撤销上一轮对话，但记忆清理失败。"
                f"\n删除消息：{len(result.deleted_ids)} 条"
                "\n请查看日志后手动清理对应记忆。"
            )
        logger.info(
            "undo session=%s deleted=%d memory_superseded=%d memory_restored=%d last=%d->%d",
            session_key,
            len(result.deleted_ids),
            len(_string_list(memory_result.get("affected_ids"))),
            len(_string_list(memory_result.get("restored_ids"))),
            result.last_consolidated_before,
            result.last_consolidated_after,
        )
        return (
            "已撤销上一轮对话。"
            f"\n删除消息：{len(result.deleted_ids)} 条"
            f"\n失效记忆：{len(_string_list(memory_result.get('affected_ids')))} 条"
            f"\n恢复旧记忆：{len(_string_list(memory_result.get('restored_ids')))} 条"
        )


def _undo_memory_sources(
    memory_engine: MemoryUndo | None,
    message_ids: list[str],
    *,
    dry_run: bool,
) -> dict[str, object]:
    if memory_engine is None:
        return {"affected_ids": [], "restored_ids": [], "rollback_source_ids": []}
    return memory_engine.undo_by_message_sources(message_ids, dry_run=dry_run)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


async def setup(ctx: "PluginRuntimeContext") -> None:
    """Register scoped undo command and before-turn contribution."""
    if ctx.session_manager is None:
        raise RuntimeError("plugin_undo requires a session manager")
    engine = ctx.memory_engine
    plugin = PluginUndo(
        ctx.session_manager, engine if isinstance(engine, MemoryUndo) else None
    )
    ctx.lifecycle.contribute("before_turn", [UndoCommandModule(plugin)])
    ctx.bot_commands.add("undo", "撤销上一轮对话")
