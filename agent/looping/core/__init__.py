"""Agent loop 的稳定公共入口。"""

import asyncio

from .assembly import _AssemblyMixin
from .helpers import (
    StreamDelta,
    StreamSink,
    StreamSinkFactory,
    StreamSupportPolicy,
    _MANUAL_CONSOLIDATION_TIMEOUT_SECONDS,
    _build_resume_content,
    _is_positive_int,
    _item_content,
    _STREAM_SUPPORT_POLICIES,
    _supports_stream_events,
    _suppresses_stream_events,
)
from .interrupts import _InterruptMixin
from .processing import _ProcessingMixin
from .streaming import _StreamingMixin

__all__ = ["AgentLoop"]


class AgentLoop(
    _AssemblyMixin,
    _StreamingMixin,
    _ProcessingMixin,
    _InterruptMixin,
):
    """
    主循环：从 MessageBus 消费 InboundMessage，
    驱动 LLM + 工具调用，将结果发回 MessageBus。
    对话历史按 session_key 独立维护，格式为 OpenAI messages。
    """

    async def trigger_memory_consolidation(
        self,
        session_key: str,
        *,
        archive_all: bool = False,
        force: bool = False,
    ) -> bool:
        from core.memory.markdown import ConsolidateRequest

        session = self.session_manager.get_or_create(session_key)
        if self._markdown_memory is None:
            raise RuntimeError("markdown memory runtime unavailable")
        maintenance = self._markdown_memory.maintenance
        try:
            result = await asyncio.wait_for(
                maintenance.consolidate(
                    ConsolidateRequest(
                        session=session,
                        archive_all=archive_all,
                        force=force,
                    )
                ),
                timeout=_MANUAL_CONSOLIDATION_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise TimeoutError("memory consolidation busy") from exc
        if result.trace.get("mode") == "markdown":
            await self.session_manager.save_async(session)
            return True
        return False

    def request_memory_consolidation(self, session_key: str) -> None:
        """非阻塞请求指定会话执行后台记忆整理。"""
        if self._markdown_memory is None:
            return
        self._markdown_memory.maintenance.request_background_consolidation(session_key)

    def get_memory_consolidation_failure(self, session_key: str) -> str | None:
        """返回指定会话最近一次后台记忆整理的明确失败原因。"""
        if self._markdown_memory is None:
            return "markdown memory runtime unavailable"
        return self._markdown_memory.maintenance.get_consolidation_failure(session_key)
