from __future__ import annotations

import logging
from typing import Any

import agent.core.passive_support as support
from agent.core.types import LLMToolCall, ReasonerResult
from bus.events_lifecycle import ToolCallCompleted, ToolCallStarted

logger = logging.getLogger("agent.core.passive_turn")

_SUMMARY_MAX_TOKENS = 512
_INCOMPLETE_SUMMARY_PROMPT = """当前任务需要先暂停继续调用工具，请直接输出给用户看的中文阶段性回复。
必须基于已有上下文，不要编造结果。
必须包含四点：
1) 已经使用了哪些工具或操作，以及拿到了什么关键信息；
2) 当前已经做到哪一步；
3) 还缺什么信息或步骤；
4) 如果继续，下一步会怎么做。
可以提到工具名称和关键结果，但不要暴露 tool_call_id、schema、内部 prompt 或原始参数 JSON。
禁止输出"已达到最大迭代次数"这类模板句；不要输出 JSON。"""


class _PassiveReasoningResultMixin:
    """处理工具事件观测、阶段总结与 ReasonerResult 构建。"""

    async def _observe_tool_call_started(
        self,
        *,
        session_key: str,
        channel: str,
        chat_id: str,
        iteration: int,
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> None:
        if self._event_bus is None or not session_key:
            return
        await self._event_bus.observe(
            ToolCallStarted(
                session_key=session_key,
                channel=channel,
                chat_id=chat_id,
                iteration=iteration,
                call_id=call_id,
                tool_name=tool_name,
                arguments=dict(arguments),
            )
        )
    async def _observe_tool_call_completed(
        self,
        *,
        session_key: str,
        channel: str,
        chat_id: str,
        iteration: int,
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        final_arguments: dict[str, Any],
        status: str,
        result_preview: str,
    ) -> None:
        if self._event_bus is None or not session_key:
            return
        await self._event_bus.observe(
            ToolCallCompleted(
                session_key=session_key,
                channel=channel,
                chat_id=chat_id,
                iteration=iteration,
                call_id=call_id,
                tool_name=tool_name,
                arguments=dict(arguments),
                final_arguments=dict(final_arguments),
                status=status,
                result_preview=result_preview,
            )
        )

    async def _summarize_incomplete_progress(
        self,
        messages: list[dict],
        *,
        reason: str,
        iteration: int,
        tools_used: list[str],
    ) -> str:
        # 1. 先构造收尾总结 prompt。
        summary_prompt = (
            f"[收尾原因] {reason}\n"
            f"[已执行轮次] {iteration}\n"
            f"[已调用工具] {', '.join(tools_used[-8:]) if tools_used else '无'}\n\n"
            + _INCOMPLETE_SUMMARY_PROMPT
        )

        # 2. 先尝试让模型给一段中文收尾总结。
        try:
            response = await self._llm.provider.chat(
                messages=messages
                + [
                    support.build_context_hint_message(
                        "summary_request",
                        summary_prompt,
                    )
                ],
                tools=[],
                model=self._llm_config.model,
                max_tokens=min(_SUMMARY_MAX_TOKENS, self._llm_config.max_tokens),
            )
            text = (response.content or "").strip()
            if text:
                return text
        except Exception as exc:
            logger.warning("生成预算收尾总结失败: %s", exc)

        # 3. 模型收尾失败时，返回固定兜底文案。
        tool_text = "、".join(tools_used[-8:]) if tools_used else "无"
        done = f"已尝试 {iteration} 轮，调用工具 {len(tools_used)} 次（{tool_text}）。"
        return (
            f"这次任务还没完全收束。{done}"
            "我先停在当前进度，后续会继续基于已有工具结果补齐缺失信息并给你最终结论。"
        )

    def _build_result(
        self,
        *,
        reply: str,
        tools_used: list[str],
        tool_chain: list[dict[str, Any]],
        visible_names: set[str] | None,
        thinking: str | None,
        streamed: bool,
        react_input_samples: list[int],
        cache_prompt_tokens: int,
        cache_hit_tokens: int,
        cache_seen: bool,
        tools_unlocked: list[str] | None = None,
    ) -> ReasonerResult:
        # 1. 先把 tool_chain 扁平化成 invocations。
        invocations: list[LLMToolCall] = []
        for group in tool_chain:
            for call in group.get("calls") or []:
                args = call.get("arguments")
                invocations.append(
                    LLMToolCall(
                        id=str(call.get("call_id", "") or ""),
                        name=str(call.get("name", "") or ""),
                        arguments=args if isinstance(args, dict) else {},
                    )
                )

        # 2. 再把运行时元数据统一塞进 metadata。
        react_stats = {
            "iteration_count": len(react_input_samples),
            "turn_input_sum_tokens": sum(react_input_samples),
            "turn_input_peak_tokens": max(react_input_samples, default=0),
            "final_call_input_tokens": react_input_samples[-1] if react_input_samples else 0,
        }
        if cache_seen:
            react_stats["cache_prompt_tokens"] = cache_prompt_tokens
            react_stats["cache_hit_tokens"] = cache_hit_tokens
            hit_rate = (
                cache_hit_tokens / cache_prompt_tokens
                if cache_prompt_tokens > 0
                else 0.0
            )
            logger.info(
                "[KV缓存] 本轮 prompt_tokens=%d hit_tokens=%d hit_rate=%.2f%%",
                cache_prompt_tokens,
                cache_hit_tokens,
                hit_rate * 100,
            )
        metadata = {
            "tools_used": list(tools_used),
            "tools_unlocked": list(tools_unlocked or []),
            "tool_chain": list(tool_chain),
            "visible_names": set(visible_names) if visible_names is not None else None,
            "react_stats": react_stats,
        }

        # 3. 最后返回标准 ReasonerResult。
        return ReasonerResult(
            reply=reply,
            invocations=invocations,
            thinking=thinking,
            streamed=streamed,
            metadata=metadata,
        )
