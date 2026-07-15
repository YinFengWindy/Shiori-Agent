from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Awaitable, Callable

import agent.core.passive_support as support
from agent.core.types import ReasonerResult
from agent.lifecycle.types import (
    AfterStepCtx,
    AfterToolResultCtx,
    BeforeStepInput,
    BeforeToolCallCtx,
)
from agent.tool_hooks import ToolExecutionRequest
from agent.tool_runtime import (
    append_assistant_tool_calls,
    append_tool_result,
    tool_call_batch_snapshot,
)
from agent.tools.base import normalize_tool_result

logger = logging.getLogger("agent.core.passive_turn")


def _is_tool_loop_guard_denial(exec_result: object) -> bool:
    traces = getattr(exec_result, "pre_hook_trace", ()) or ()
    return any(
        getattr(item, "decision", "") == "deny"
        and str(getattr(item, "reason", "")).startswith("tool_loop_guard:")
        for item in traces
    )


class _PassiveReasoningLoopMixin:
    """实现 DefaultReasoner 的多轮工具调用循环。"""

    async def run(
        self,
        initial_messages: list[dict],
        *,
        request_time: datetime | None = None,
        preloaded_tools: set[str] | None = None,
        preloaded_tool_order: list[str] | None = None,
        preflight_injected: bool = True,
        on_content_delta: Callable[[dict[str, str]], Awaitable[None]] | None = None,
        tool_event_session_key: str = "",
        tool_event_channel: str = "",
        tool_event_chat_id: str = "",
        tool_execution_context: dict[str, Any] | None = None,
        disabled_tools: set[str] | None = None,
    ) -> ReasonerResult:
        # 1. 初始化消息上下文、本轮工具轨迹。
        messages = initial_messages
        tools_used: list[str] = []
        tools_unlocked: list[str] = []
        tool_chain: list[dict[str, Any]] = []
        execution_context = dict(
            tool_execution_context
            if tool_execution_context is not None
            else self._tools.get_context()
        )
        # 2. 初始化本轮可见工具集合。
        visible_names: set[str] | None = None
        visible_order: list[str] | None = None
        streamed = False
        react_input_samples: list[int] = []
        react_cache_prompt_tokens = 0
        react_cache_hit_tokens = 0
        react_cache_seen = False
        disabled = set(disabled_tools or set())
        if self._tool_search_enabled:
            always_on = self._tools.get_always_on_names()
            visible_names = (always_on | (preloaded_tools or set())) - disabled
            visible_order = self._tools.get_registered_order(always_on - disabled)
            seen_visible = set(visible_order)
            for name in preloaded_tool_order or sorted(preloaded_tools or set()):
                if name in visible_names and name not in seen_visible:
                    visible_order.append(name)
                    seen_visible.add(name)
            logger.info(
                "[tool_search] visible=%d 个工具 always_on=%d preloaded=%d need_search=%s",
                len(visible_names),
                len(always_on),
                len(preloaded_tools or set()),
                "yes" if len(visible_names) == len(always_on) else "maybe",
            )

        iteration = -1
        while True:
            iteration += 1
            if (
                self._llm_config.max_iterations > 0
                and iteration >= self._llm_config.max_iterations
            ):
                break
            # 3. BeforeStep 模块链：token 估算、BeforeStep 事件、提示注入。
            step_ctx = await self._before_step.run(BeforeStepInput(
                session_key=tool_event_session_key,
                channel=tool_event_channel,
                chat_id=tool_event_chat_id,
                iteration=iteration,
                messages=messages,
                visible_names=visible_names,
            ))
            if step_ctx.early_stop:
                summary = await self._summarize_incomplete_progress(
                    messages,
                    reason="early_stop",
                    iteration=iteration + 1,
                    tools_used=tools_used,
                )
                return self._build_result(
                    reply=step_ctx.early_stop_reply or summary,
                    tools_used=tools_used,
                    tool_chain=tool_chain,
                    visible_names=visible_names,
                    thinking=None,
                    streamed=False,
                    react_input_samples=react_input_samples,
                    cache_prompt_tokens=react_cache_prompt_tokens,
                    cache_hit_tokens=react_cache_hit_tokens,
                    cache_seen=react_cache_seen,
                    tools_unlocked=tools_unlocked,
                )
            # 4. 调用 LLM，带上当前可见工具 schema。
            react_input_samples.append(step_ctx.input_tokens_estimate)
            logger.info(
                "[LLM调用] 第%d轮，可见工具=%s input_tokens~=%d",
                iteration + 1,
                f"{len(visible_names)}个" if visible_names is not None else "全部（tool_search未开启）",
                step_ctx.input_tokens_estimate,
            )
            schema_names: list[str] | set[str] | None = (
                list(visible_order) if visible_order is not None else None
            )
            if schema_names is None and disabled:
                schema_names = self._tools.get_registered_names() - disabled
            elif schema_names is not None:
                schema_names = [name for name in schema_names if name not in disabled]
            response = await self._llm.provider.chat(
                messages=messages,
                tools=self._tools.get_schemas(names=schema_names),
                model=self._llm_config.model,
                max_tokens=self._llm_config.max_tokens,
                tool_choice="auto",
                on_content_delta=on_content_delta,
            )
            if on_content_delta is not None and response.content:
                streamed = True
            if response.cache_prompt_tokens is not None:
                react_cache_seen = True
                react_cache_prompt_tokens += response.cache_prompt_tokens
                react_cache_hit_tokens += response.cache_hit_tokens or 0

            # 5. 模型返回 tool_calls 时，进入工具执行分支。
            if response.tool_calls:
                logger.info(
                    "[LLM决策→工具] 第%d轮，调用: %s",
                    iteration + 1,
                    [tc.name for tc in response.tool_calls],
                )
                append_assistant_tool_calls(
                    messages,
                    content=response.content,
                    tool_calls=response.tool_calls,
                    provider_fields=response.provider_fields,
                )
                tool_batch = tool_call_batch_snapshot(response.tool_calls)

                # 6. 逐个执行本轮工具调用。
                iter_calls: list[dict[str, Any]] = []
                for tool_batch_index, tool_call in enumerate(response.tool_calls):
                    if tool_call.name in disabled:
                        await self._observe_tool_call_started(
                            session_key=tool_event_session_key,
                            channel=tool_event_channel,
                            chat_id=tool_event_chat_id,
                            iteration=iteration + 1,
                            call_id=tool_call.id,
                            tool_name=tool_call.name,
                            arguments=tool_call.arguments,
                        )
                        result = (
                            f"工具 '{tool_call.name}' 在当前后台任务中不可用。"
                            "请直接返回要发送的最终内容，不要主动推送。"
                        )
                        append_tool_result(
                            messages,
                            tool_call_id=tool_call.id,
                            content=result,
                            tool_name=tool_call.name,
                        )
                        await self._observe_tool_call_completed(
                            session_key=tool_event_session_key,
                            channel=tool_event_channel,
                            chat_id=tool_event_chat_id,
                            iteration=iteration + 1,
                            call_id=tool_call.id,
                            tool_name=tool_call.name,
                            arguments=tool_call.arguments,
                            final_arguments=tool_call.arguments,
                            status="blocked",
                            result_preview=support.log_preview(result),
                        )
                        iter_calls.append(
                            {
                                "call_id": tool_call.id,
                                "name": tool_call.name,
                                "status": "blocked",
                                "arguments": tool_call.arguments,
                                "result": result,
                            }
                        )
                        continue
                    # 6.1 deferred 工具未解锁时，先回填 select: 引导错误。
                    if visible_names is not None and tool_call.name not in visible_names:
                        exec_result = await self._tool_executor.preflight(
                            ToolExecutionRequest(
                                call_id=tool_call.id,
                                tool_name=tool_call.name,
                                arguments=tool_call.arguments,
                                source="passive",
                                session_key=tool_event_session_key,
                                channel=tool_event_channel,
                                chat_id=tool_event_chat_id,
                                tool_batch=tool_batch,
                                tool_batch_index=tool_batch_index,
                            )
                        )
                        await self._observe_tool_call_started(
                            session_key=tool_event_session_key,
                            channel=tool_event_channel,
                            chat_id=tool_event_chat_id,
                            iteration=iteration + 1,
                            call_id=tool_call.id,
                            tool_name=tool_call.name,
                            arguments=tool_call.arguments,
                        )
                        if _is_tool_loop_guard_denial(exec_result):
                            result = str(exec_result.output)
                            append_tool_result(
                                messages,
                                tool_call_id=tool_call.id,
                                content=result,
                                tool_name=tool_call.name,
                            )
                            await self._observe_tool_call_completed(
                                session_key=tool_event_session_key,
                                channel=tool_event_channel,
                                chat_id=tool_event_chat_id,
                                iteration=iteration + 1,
                                call_id=tool_call.id,
                                tool_name=tool_call.name,
                                arguments=tool_call.arguments,
                                final_arguments=exec_result.final_arguments,
                                status=exec_result.status,
                                result_preview=support.log_preview(result),
                            )
                            iter_calls.append(
                                {
                                    "call_id": tool_call.id,
                                    "name": tool_call.name,
                                    "status": exec_result.status,
                                    "arguments": tool_call.arguments,
                                    "final_arguments": exec_result.final_arguments,
                                    "pre_hook_trace": [
                                        {
                                            "hook_name": item.hook_name,
                                            "event": item.event,
                                            "matched": item.matched,
                                            "decision": item.decision,
                                            "reason": item.reason,
                                            "extra_message": item.extra_message,
                                        }
                                        for item in exec_result.pre_hook_trace
                                    ],
                                    "result": result,
                                }
                            )
                            for skipped in response.tool_calls[tool_batch_index + 1:]:
                                append_tool_result(
                                    messages,
                                    tool_call_id=skipped.id,
                                    content="工具调用已因重复循环检测跳过。",
                                    tool_name=skipped.name,
                                )
                            tool_chain.append({"text": response.content, "calls": iter_calls})
                            summary = await self._summarize_incomplete_progress(
                                messages,
                                reason="tool_call_loop",
                                iteration=iteration + 1,
                                tools_used=tools_used,
                            )
                            return self._build_result(
                                reply=summary,
                                tools_used=tools_used,
                                tool_chain=tool_chain,
                                visible_names=visible_names,
                                thinking=None,
                                streamed=False,
                                react_input_samples=react_input_samples,
                                cache_prompt_tokens=react_cache_prompt_tokens,
                                cache_hit_tokens=react_cache_hit_tokens,
                                cache_seen=react_cache_seen,
                                tools_unlocked=tools_unlocked,
                            )
                        logger.warning(
                            "[工具未解锁] LLM 尝试调用 '%s'，但该工具 schema 不可见，引导模型先 tool_search",
                            tool_call.name,
                        )
                        result = (
                            f"工具 '{tool_call.name}' 当前未加载（schema 不可见）。"
                            f"请先调用 tool_search(query=\"select:{tool_call.name}\") 加载，"
                            "然后再调用该工具。不要放弃当前任务。"
                        )
                        append_tool_result(
                            messages,
                            tool_call_id=tool_call.id,
                            content=result,
                        )
                        await self._observe_tool_call_completed(
                            session_key=tool_event_session_key,
                            channel=tool_event_channel,
                            chat_id=tool_event_chat_id,
                            iteration=iteration + 1,
                            call_id=tool_call.id,
                            tool_name=tool_call.name,
                            arguments=tool_call.arguments,
                            final_arguments=tool_call.arguments,
                            status="blocked",
                            result_preview=support.log_preview(result),
                        )
                        iter_calls.append(
                            {
                                "call_id": tool_call.id,
                                "name": tool_call.name,
                                "arguments": tool_call.arguments,
                                "result": result,
                            }
                        )
                        continue

                    # 6.2 通过统一执行器跑 pre/post hooks + 真实工具。
                    # For tool_search: pass visible_names explicitly via
                    # set_excluded_names() instead of the old ContextVar channel.
                    if (
                        tool_call.name == "tool_search"
                        and visible_names is not None
                        and self._tool_search_tool is not None
                    ):
                        self._tool_search_tool.set_excluded_names(
                            visible_names | disabled
                        )
                    _args_preview = support.log_preview(tool_call.arguments, 120)
                    logger.info("[工具执行→] %s  args=%s", tool_call.name, _args_preview)
                    await self._observe_tool_call_started(
                        session_key=tool_event_session_key,
                        channel=tool_event_channel,
                        chat_id=tool_event_chat_id,
                        iteration=iteration + 1,
                        call_id=tool_call.id,
                        tool_name=tool_call.name,
                        arguments=tool_call.arguments,
                    )
                    # 工具调用统一先过 ToolExecutor：
                    # pre_hook 可改参/拒绝，真实执行后再补 post_hook trace。
                    await self._bus.fanout(BeforeToolCallCtx(
                        session_key=tool_event_session_key,
                        channel=tool_event_channel,
                        chat_id=tool_event_chat_id,
                        tool_name=tool_call.name,
                        arguments=dict(tool_call.arguments),
                    ))
                    exec_result = await self._tool_executor.execute(
                        ToolExecutionRequest(
                            call_id=tool_call.id,
                            tool_name=tool_call.name,
                            arguments=tool_call.arguments,
                            source="passive",
                            session_key=tool_event_session_key,
                            channel=tool_event_channel,
                            chat_id=tool_event_chat_id,
                            tool_batch=tool_batch,
                            tool_batch_index=tool_batch_index,
                        ),
                        # 真实工具执行入口仍是 ToolRegistry.execute；
                        # hook 只负责拦截与记录，不替代 registry。
                        lambda name, args: self._tools.execute(
                            name,
                            args,
                            context=execution_context,
                        ),
                    )
                    if exec_result.status == "success":
                        tools_used.append(tool_call.name)
                    result = exec_result.output
                    await self._bus.fanout(AfterToolResultCtx(
                        session_key=tool_event_session_key,
                        channel=tool_event_channel,
                        chat_id=tool_event_chat_id,
                        tool_name=tool_call.name,
                        arguments=dict(exec_result.final_arguments),
                        result=str(result),
                        status=exec_result.status,
                    ))
                    normalized = normalize_tool_result(result)
                    _result_preview = support.log_preview(normalized.preview())
                    _result_len = len(normalized.preview() or "")
                    await self._observe_tool_call_completed(
                        session_key=tool_event_session_key,
                        channel=tool_event_channel,
                        chat_id=tool_event_chat_id,
                        iteration=iteration + 1,
                        call_id=tool_call.id,
                        tool_name=tool_call.name,
                        arguments=tool_call.arguments,
                        final_arguments=exec_result.final_arguments,
                        status=exec_result.status,
                        result_preview=normalized.preview(),
                    )
                    logger.info(
                        "[工具结果←] %s  结果预览=%s  result_len=%d",
                        tool_call.name,
                        _result_preview,
                        _result_len,
                    )
                    append_tool_result(
                        messages,
                        tool_call_id=tool_call.id,
                        content=result,
                        tool_name=tool_call.name,
                    )

                    # 6.3 tool_search 的结果会扩展下一轮可见工具。
                    if (
                        exec_result.status == "success"
                        and tool_call.name == "tool_search"
                        and visible_names is not None
                    ):
                        _newly_unlocked = [
                            name
                            for name in self._discovery.unlock_names_from_result(normalized.text)
                            if name not in visible_names and name not in disabled
                        ]
                        if _newly_unlocked:
                            visible_names.update(_newly_unlocked)
                            tools_unlocked.extend(_newly_unlocked)
                            if visible_order is not None:
                                seen_visible = set(visible_order)
                                for name in _newly_unlocked:
                                    if name not in seen_visible:
                                        visible_order.append(name)
                                        seen_visible.add(name)
                            logger.info("[工具解锁] tool_search 新解锁: %s", sorted(_newly_unlocked))
                        else:
                            logger.info("[工具解锁] tool_search 未解锁新工具")
                    # tool_chain 持久化的是“执行后的事实”：
                    # 最终参数、hook trace、结果预览，供后续回放与 session 复原。
                    iter_calls.append(
                        {
                            "call_id": tool_call.id,
                            "name": tool_call.name,
                            "status": exec_result.status,
                            "arguments": tool_call.arguments,
                            "final_arguments": exec_result.final_arguments,
                            "pre_hook_trace": [
                                {
                                    "hook_name": item.hook_name,
                                    "event": item.event,
                                    "matched": item.matched,
                                    "decision": item.decision,
                                    "reason": item.reason,
                                    "extra_message": item.extra_message,
                                }
                                for item in exec_result.pre_hook_trace
                            ],
                            "post_hook_trace": [
                                {
                                    "hook_name": item.hook_name,
                                    "event": item.event,
                                    "matched": item.matched,
                                    "decision": item.decision,
                                    "reason": item.reason,
                                    "extra_message": item.extra_message,
                                }
                                for item in exec_result.post_hook_trace
                            ],
                            "result": normalized.preview(),
                        }
                    )
                    if _is_tool_loop_guard_denial(exec_result):
                        logger.warning(
                            "[循环检测] 插件截断重复工具调用，进入收尾 (iteration=%d, tool=%s)",
                            iteration + 1,
                            tool_call.name,
                        )
                        for skipped in response.tool_calls[tool_batch_index + 1:]:
                            append_tool_result(
                                messages,
                                tool_call_id=skipped.id,
                                content="工具调用已因重复循环检测跳过。",
                                tool_name=skipped.name,
                            )
                        tool_chain.append({"text": response.content, "calls": iter_calls})
                        summary = await self._summarize_incomplete_progress(
                            messages,
                            reason="tool_call_loop",
                            iteration=iteration + 1,
                            tools_used=tools_used,
                        )
                        return self._build_result(
                            reply=summary,
                            tools_used=tools_used,
                            tool_chain=tool_chain,
                            visible_names=visible_names,
                            thinking=None,
                            streamed=False,
                            react_input_samples=react_input_samples,
                            cache_prompt_tokens=react_cache_prompt_tokens,
                            cache_hit_tokens=react_cache_hit_tokens,
                            cache_seen=react_cache_seen,
                            tools_unlocked=tools_unlocked,
                        )

                # 7. 本轮工具执行完后，记录 tool_chain。
                tool_chain_group = {"text": response.content, "calls": iter_calls}
                if response.thinking is not None:
                    tool_chain_group["reasoning_content"] = response.thinking
                tool_chain.append(tool_chain_group)
                pressure_tokens = support.estimate_messages_tokens(messages)
                # 7a. AfterStep 模块链（工具分支）：通知观察者本轮工具执行完毕。
                after_step = await self._after_step.run(AfterStepCtx(
                    session_key=tool_event_session_key,
                    channel=tool_event_channel,
                    chat_id=tool_event_chat_id,
                    iteration=iteration,
                    context_tokens_estimate=pressure_tokens,
                    tools_called=tuple(tc.name for tc in response.tool_calls),
                    partial_reply=response.content or "",
                    tools_used_so_far=tuple(tools_used),
                    tool_chain_partial=tuple(tool_chain),
                    partial_thinking=response.thinking,
                    has_more=True,
                ))
                if after_step.early_stop:
                    reason = after_step.early_stop_reason or "after_step"
                    logger.warning(
                        "[插件收尾] reason=%s tokens~=%d，停止继续调用工具并收尾",
                        reason,
                        pressure_tokens,
                    )
                    summary = await self._summarize_incomplete_progress(
                        messages,
                        reason=reason,
                        iteration=iteration + 1,
                        tools_used=tools_used,
                    )
                    return self._build_result(
                        reply=summary,
                        tools_used=tools_used,
                        tool_chain=tool_chain,
                        visible_names=visible_names,
                        thinking=None,
                        streamed=False,
                        react_input_samples=react_input_samples,
                        cache_prompt_tokens=react_cache_prompt_tokens,
                        cache_hit_tokens=react_cache_hit_tokens,
                        cache_seen=react_cache_seen,
                        tools_unlocked=tools_unlocked,
                    )
                continue

            # 8. 没有 tool_calls 时，说明本轮得到最终回复。
            # 8a. 若 content 为空（模型只输出了 thinking），retry 一次。
            if not response.content and response.thinking:
                logger.warning(
                    "[空回复重试] 第%d轮，content为空但thinking非空，触发一次重试",
                    iteration + 1,
                )
                messages.append({"role": "assistant", "content": ""})
                messages.append({
                    "role": "user",
                    "content": "你刚才只输出了思考过程，没有给出正式回复。请直接回复用户，不要重复思考。",
                })
                retry_response = await self._llm.provider.chat(
                    messages=messages,
                    tools=[],
                    model=self._llm_config.model,
                    max_tokens=self._llm_config.max_tokens,
                    on_content_delta=on_content_delta,
                )
                if retry_response.cache_prompt_tokens is not None:
                    react_cache_seen = True
                    react_cache_prompt_tokens += retry_response.cache_prompt_tokens
                    react_cache_hit_tokens += retry_response.cache_hit_tokens or 0
                if retry_response.content:
                    response = retry_response
                    if on_content_delta is not None:
                        streamed = True
                    logger.info("[空回复重试] 重试成功，获得正常回复")
                else:
                    logger.warning("[空回复重试] 重试仍为空，使用fallback")

            logger.info(
                "[LLM决策→回复] 第%d轮，共调用工具%d次: %s",
                iteration + 1,
                len(tools_used),
                tools_used if tools_used else "无",
            )
            messages.append({"role": "assistant", "content": response.content})
            # 8b. AfterStep 模块链（最终回复分支）：通知观察者本轮推理结束。
            _ = await self._after_step.run(AfterStepCtx(
                session_key=tool_event_session_key,
                channel=tool_event_channel,
                chat_id=tool_event_chat_id,
                iteration=iteration,
                context_tokens_estimate=support.estimate_messages_tokens(messages),
                tools_called=(),
                partial_reply=response.content or "",
                tools_used_so_far=tuple(tools_used),
                tool_chain_partial=tuple(tool_chain),
                partial_thinking=response.thinking,
                has_more=False,
            ))
            return self._build_result(
                reply=response.content or "（无响应）",
                tools_used=tools_used,
                tool_chain=tool_chain,
                visible_names=visible_names,
                thinking=response.thinking,
                streamed=streamed,
                react_input_samples=react_input_samples,
                cache_prompt_tokens=react_cache_prompt_tokens,
                cache_hit_tokens=react_cache_hit_tokens,
                cache_seen=react_cache_seen,
                tools_unlocked=tools_unlocked,
            )

        # 9. 达到最大迭代次数后，生成不完整进展总结。
        logger.warning(
            "[迭代上限] 达到最大轮次%d，触发收尾总结，已调用工具: %s",
            iteration,
            tools_used if tools_used else "无",
        )
        summary = await self._summarize_incomplete_progress(
            messages,
            reason="max_iterations",
            iteration=iteration,
            tools_used=tools_used,
        )
        return self._build_result(
            reply=summary,
            tools_used=tools_used,
            tool_chain=tool_chain,
            visible_names=visible_names,
            thinking=None,
            streamed=False,
            react_input_samples=react_input_samples,
            cache_prompt_tokens=react_cache_prompt_tokens,
            cache_hit_tokens=react_cache_hit_tokens,
            cache_seen=react_cache_seen,
            tools_unlocked=tools_unlocked,
        )
