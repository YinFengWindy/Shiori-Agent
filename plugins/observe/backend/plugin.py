from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from bus.events_lifecycle import TurnCommitted
from core.memory.events import MemoryWritten, RetrievalCompleted

from .collector import GlobalErrorCollector
from .retention import run_retention_if_needed
from .telemetry import ObserveTelemetry
from .writer import TraceWriter

if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext

logger = logging.getLogger("plugin.observe")


async def setup(ctx: "PluginRuntimeContext") -> None:
    """等待 writer 数据库就绪后，再装配 retention、错误采集和遥测订阅。

    宿主首先停用并退订事件，与订阅的登记位置无关。其它资源仍刻意保持
    [writer 后台任务, retention 后台任务, 全局错误采集器] 的登记顺序，
    按 LIFO 逆序处置，因此实际清理顺序是
    事件订阅 -> 采集器 uninstall（把内存中缓冲的错误 flush 进队列）->
    retention 任务取消 -> writer 任务最后取消，writer 任务的取消时机晚于
    采集器 flush，保证 flush 出的最后一批错误仍有机会被 writer 写盘——
    与旧 terminate() 里"先 uninstall 采集器、再依次取消 retention/writer"的
    手写顺序等价（#183）。
    """
    workspace = ctx.workspace
    if workspace is None:
        logger.warning("observe 插件缺少 workspace，跳过加载")
        return

    db_path = workspace / "observe" / "observe.db"
    writer = TraceWriter(db_path)
    writer_task = ctx.background.spawn(writer.run(), name="writer")
    await writer.wait_ready(writer_task)
    _ = ctx.background.spawn(run_retention_if_needed(db_path), name="retention")

    collector = GlobalErrorCollector(writer)
    # 安装过程本身可能部分成功，先登记清理以覆盖 setup 的失败回滚。
    ctx.effect("collector", collector.uninstall)
    collector.install()

    ctx.events.on(TurnCommitted, lambda event: _observe_turn_committed(writer, event))
    ctx.events.on(RetrievalCompleted, lambda event: _observe_retrieval(writer, event))
    ctx.events.on(MemoryWritten, lambda event: _observe_memory_written(writer, event))
    ctx.expose(ObserveTelemetry(workspace))


def _observe_turn_committed(writer: TraceWriter, event: TurnCommitted) -> None:
    _emit_turn_trace(writer, event)


def _observe_retrieval(writer: TraceWriter, event: RetrievalCompleted) -> None:
    writer.emit(_to_rag_query_log(event))


def _observe_memory_written(writer: TraceWriter, event: MemoryWritten) -> None:
    writer.emit(_to_memory_write_trace(event))


def _emit_turn_trace(writer: TraceWriter, event: TurnCommitted) -> None:
    from .events import TurnTrace as TurnTraceEvent

    post_reply_budget = event.post_reply_budget
    react_stats = event.react_stats
    tool_chain = event.tool_chain_raw
    tool_chain_json = (
        json.dumps(_slim_tool_chain(tool_chain), ensure_ascii=False)
        if tool_chain
        else None
    )
    tool_calls = _slim_tool_calls(tool_chain)
    writer.emit(
        TurnTraceEvent(
            source="agent",
            session_key=event.session_key,
            user_msg=event.persisted_user_message,
            llm_output=event.assistant_response,
            raw_llm_output=event.raw_reply,
            meme_tag=event.meme_tag,
            meme_media_count=event.meme_media_count,
            tool_calls=tool_calls,
            tool_chain_json=tool_chain_json,
            history_window=post_reply_budget.get("history_window"),
            history_messages=post_reply_budget.get("history_messages"),
            history_chars=post_reply_budget.get("history_chars"),
            history_tokens=post_reply_budget.get("history_tokens"),
            prompt_tokens=post_reply_budget.get("prompt_tokens"),
            next_turn_baseline_tokens=post_reply_budget.get(
                "next_turn_baseline_tokens"
            ),
            react_iteration_count=react_stats.get("iteration_count"),
            react_input_sum_tokens=react_stats.get("turn_input_sum_tokens"),
            react_input_peak_tokens=react_stats.get("turn_input_peak_tokens"),
            react_final_input_tokens=react_stats.get("final_call_input_tokens"),
            react_cache_prompt_tokens=react_stats.get("cache_prompt_tokens"),
            react_cache_hit_tokens=react_stats.get("cache_hit_tokens"),
        )
    )
    logger.info(
        "[observe] turn_trace 已入队 session=%s tool_calls=%d",
        event.session_key,
        len(tool_calls),
    )


def _to_rag_query_log(event: RetrievalCompleted):
    from .events import RagHitLog, RagQueryLog

    return RagQueryLog(
        caller="passive",
        session_key=event.session_key,
        role_id=event.role_id,
        query=event.query,
        orig_query=event.orig_query,
        aux_queries=list(event.aux_queries),
        hits=[
            RagHitLog(
                item_id=hit.item_id,
                memory_type=hit.memory_type,
                score=hit.score,
                summary=hit.summary[:120],
                injected=hit.injected,
                confidence_label=hit.confidence_label,
                forced=hit.forced,
            )
            for hit in event.hits
        ],
        injected_count=event.injected_count,
        route_decision=event.route_decision,
        error=event.error,
    )


def _to_memory_write_trace(event: MemoryWritten):
    from .events import MemoryWriteTrace

    return MemoryWriteTrace(
        session_key=event.session_key,
        role_id=event.role_id,
        source_ref=event.source_ref,
        action=event.action,
        memory_type=event.memory_type,
        item_id=event.item_id,
        summary=event.summary,
        superseded_ids=list(event.superseded_ids),
        error=event.error,
    )


def _slim_tool_calls(tool_chain: list[dict[str, object]]) -> list[dict[str, str]]:
    return [
        {
            "name": str(call.get("name", "")),
            "args": str(call.get("arguments", ""))[:300],
            "result": str(call.get("result", ""))[:500],
        }
        for group in tool_chain
        for call in _group_calls(group)
    ]


def _slim_tool_chain(tool_chain: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "text": str(group.get("text") or ""),
            "calls": [
                {
                    "name": str(call.get("name", "")),
                    "args": str(call.get("arguments", ""))[:800],
                    "result": str(call.get("result", ""))[:1200],
                }
                for call in _group_calls(group)
            ],
        }
        for group in tool_chain
    ]


def _group_calls(group: dict[str, object]) -> list[dict[str, object]]:
    calls = group.get("calls")
    if not isinstance(calls, list):
        return []
    raw_calls = cast(list[object], calls)
    out: list[dict[str, object]] = []
    for call in raw_calls:
        if isinstance(call, Mapping):
            mapping = cast(Mapping[object, object], call)
            out.append(
                {
                    str(key): value
                    for key, value in mapping.items()
                    if isinstance(key, str)
                }
            )
    return out
