from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import agent.core.passive_support as support
from agent.core.passive_helpers import get_session_metadata
from agent.core.types import ContextBundle
from agent.retrieval.protocol import RetrievalRequest, RetrievalResult

if TYPE_CHECKING:
    from agent.context import ContextBuilder
    from agent.core.runtime_support import SessionLike
    from agent.retrieval.protocol import MemoryRetrievalPipeline
    from bus.events import InboundMessage

class ContextStore(ABC):
    """
    ┌──────────────────────────────────────┐
    │ ContextStore                         │
    ├──────────────────────────────────────┤
    │ 1. 读取 session history              │
    │ 2. 调 retrieval pipeline             │
    │ 3. 收 skill mentions                 │
    │ 4. 输出 ContextBundle                │
    └──────────────────────────────────────┘
    """

    @abstractmethod
    async def prepare(
        self,
        *,
        msg: "InboundMessage",
        session_key: str,
        session: "SessionLike",
    ) -> ContextBundle:
        """准备本轮对话需要的上下文。"""


class DefaultContextStore(ContextStore):
    """从会话历史与记忆检索结果组装被动 turn 上下文。"""

    def __init__(
        self,
        *,
        retrieval: "MemoryRetrievalPipeline",
        context: "ContextBuilder",
        history_window: int = 500,
    ) -> None:
        self._retrieval = retrieval
        self._context = context
        self._history_window = max(1, int(history_window))

    async def prepare(
        self,
        *,
        msg: "InboundMessage",
        session_key: str,
        session: "SessionLike",
    ) -> ContextBundle:
        # 1. 先读取 session history，并转换成 retrieval pipeline 需要的结构。
        raw_history = list(session.get_history())
        history_messages = support.to_history_messages(raw_history)

        # 2. 系统轮次可显式跳过预检索，避免污染检索诊断和激活状态。
        if bool((msg.metadata or {}).get("skip_memory_retrieval")):
            retrieval_result = RetrievalResult(block="", trace=None)
        else:
            session_metadata = get_session_metadata(session)
            retrieval_result = await self._retrieval.retrieve(
                RetrievalRequest(
                    message=msg.content,
                    role_id=str(session_metadata.get("role_id") or "").strip(),
                    session_key=session_key,
                    channel=msg.context_channel,
                    chat_id=msg.context_chat_id,
                    history=history_messages,
                    session_metadata=session_metadata,
                    timestamp=msg.timestamp,
                )
            )

        # 3. 最后补齐 ContextBundle，把主链正式字段直接收进显式合同。
        skill_mentions = support.collect_skill_mentions(
            msg.content,
            self._context.skills.list_skills(filter_unavailable=False),
        )
        return ContextBundle(
            history=support.to_chat_messages(raw_history),
            memory_blocks=[retrieval_result.block] if retrieval_result.block else [],
            skill_mentions=skill_mentions,
            retrieved_memory_block=retrieval_result.block or "",
            retrieval_trace_raw=(
                retrieval_result.trace.raw
                if retrieval_result.trace is not None
                else None
            ),
            retrieval_metadata=dict(retrieval_result.metadata or {}),
            history_messages=history_messages,
        )
