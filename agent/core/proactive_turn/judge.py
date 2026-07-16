"""主动回复 Judge 阶段与模型工具步执行。"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from agent.tool_hooks import ToolExecutionRequest
from core.common.diagnostic_log import diagnostic_line
from proactive_v2.context import AgentTickContext
from proactive_v2.gateway import GatewayResult
from proactive_v2.tools import TOOL_SCHEMAS, dispatch

logger = logging.getLogger(__name__)

_SCENE_TOOL_PROTOCOL_RETRY_PROMPT = (
    "【工具协议纠错】上一轮返回了普通文本，未产生任何工具调用，因此内容不会被发送。"
    "本轮必须返回一个工具调用：继续场景时调用 message_push；"
    "场景已变化时调用 finish_turn(decision=skip, reason=scene_changed)。"
    "不要直接输出回复正文。"
)
_TOOL_PROTOCOL_ERROR_NOTE = "model returned no tool call after one required retry"


class ProactiveJudgeHost(Protocol):
    """Judge 阶段访问 pipeline 状态所需的最小宿主契约。"""

    _cfg: Any
    _session_key: str
    _tool_deps: Any
    _llm_fn: Any
    _last_gateway_result: GatewayResult | None
    _tool_executor: Any
    last_ctx: AgentTickContext | None

    def _relationship_fallback_style_hint(self) -> str: ...

    async def _run_tool_step(
        self,
        messages: list[dict],
        ctx: AgentTickContext,
        *,
        loop_tag: str,
        tool_choice: str | dict = "auto",
        schemas: list[dict] | None = None,
        retry_on_no_tool_call: bool = False,
    ) -> bool: ...

    def _record_tick_step(
        self,
        ctx: AgentTickContext,
        *,
        phase: str,
        tool_name: str,
        tool_call_id: str,
        tool_args: dict[str, Any],
        tool_result_text: str,
    ) -> None: ...

    def _append_tool_messages(
        self,
        messages: list[dict],
        *,
        tool_name: str,
        tool_args: dict,
        tool_call_id: str,
        result: str,
    ) -> None: ...


async def judge_evaluate(
    pipeline: ProactiveJudgeHost,
    ctx: AgentTickContext,
    messages: list[dict],
) -> None:
    """运行多轮工具调用，完成候选分类、草稿和最终收尾。"""

    if pipeline._llm_fn is None:
        return

    while ctx.steps_taken < pipeline._cfg.agent_tick_max_steps:
        ok = await pipeline._run_tool_step(
            messages,
            ctx,
            loop_tag="loop",
            tool_choice="required" if ctx.scene_followup_mode else "auto",
            retry_on_no_tool_call=ctx.scene_followup_mode,
        )
        if not ok or ctx.terminal_action is not None:
            break

    gateway_result = pipeline._last_gateway_result
    if (
        ctx.terminal_action == "skip"
        and gateway_result is not None
        and gateway_result.content_meta
    ):
        all_content_ids = {meta["id"] for meta in gateway_result.content_meta}
        classified_ids = ctx.interesting_item_ids | ctx.discarded_item_ids
        unclassified_ids = all_content_ids - classified_ids
        if unclassified_ids:
            ctx.terminal_action = None
            ctx.skip_reason = ""
            ctx.skip_note = ""
            titles_hint = "; ".join(
                f"{meta['id']}（{meta['title'][:40]}）"
                for meta in gateway_result.content_meta
                if meta["id"] in unclassified_ids
            )
            completeness_msg = (
                f"【系统提示】以下 {len(unclassified_ids)} 个条目尚未完成分类：\n"
                f"{titles_hint}\n"
                "请对每条调用 mark_interesting 或 mark_not_interesting，"
                "全部分类完毕后再调用 message_push + finish_turn(decision=reply)，或 finish_turn(decision=skip, reason=...)。"
            )
            logger.info(
                "[proactive_v2] judge completeness: %d unclassified, resetting → %s",
                len(unclassified_ids),
                sorted(unclassified_ids),
            )
            messages.append({"role": "user", "content": completeness_msg})
            for _ in range(5):
                if (
                    ctx.terminal_action is not None
                    or ctx.steps_taken >= pipeline._cfg.agent_tick_max_steps
                ):
                    break
                ok = await pipeline._run_tool_step(
                    messages,
                    ctx,
                    loop_tag="complete",
                )
                if not ok:
                    break

    if (
        ctx.relationship_fallback_open
        and not ctx.scene_followup_mode
        and ctx.terminal_action == "skip"
        and ctx.skip_reason == "no_content"
        and ctx.steps_taken < pipeline._cfg.agent_tick_max_steps
    ):
        ctx.terminal_action = None
        ctx.skip_reason = ""
        relationship_reflection = (
            "【系统提示】本轮已通过 loneliness gate，说明现在默认应该主动联系用户。"
            "relationship fallback 不要求必须存在未完成话题；只要语气自然，就可以主动发一条轻量的关心、撒娇、试探或想你了的消息。"
            "只有当 recent_chat 明确显示用户正在忙、明显不适合打扰，才允许 finish_turn(decision=skip, reason=user_busy)。"
            "请现在优先 message_push + finish_turn(decision=reply)；不要再用 no_content 跳过。"
            + pipeline._relationship_fallback_style_hint()
        )
        logger.info(
            "[proactive_v2] judge relationship fallback: forcing one more reply-focused pass"
        )
        messages.append({"role": "user", "content": relationship_reflection})
        for _ in range(3):
            if (
                ctx.terminal_action is not None
                or ctx.steps_taken >= pipeline._cfg.agent_tick_max_steps
            ):
                break
            ok = await pipeline._run_tool_step(
                messages,
                ctx,
                loop_tag="relationship_reflect",
                tool_choice="auto",
            )
            if not ok:
                break

    if (
        ctx.terminal_action is None
        and ctx.interesting_item_ids
        and ctx.steps_taken < pipeline._cfg.agent_tick_max_steps
    ):
        ids_str = ", ".join(sorted(ctx.interesting_item_ids))
        reflection = (
            f"【系统提示】你已将以下条目标记为 interesting：{ids_str}。\n"
            "所有条目均已分类完毕。你必须现在调用 message_push 撰写推送，然后调用 finish_turn(decision=reply)；"
            "或直接调用 finish_turn(decision=skip, reason=...)。不允许直接结束。"
        )
        logger.info(
            "[proactive_v2] judge reflection: interesting=%d, injecting prompt",
            len(ctx.interesting_item_ids),
        )
        messages.append({"role": "user", "content": reflection})
        for _ in range(3):
            if (
                ctx.terminal_action is not None
                or ctx.steps_taken >= pipeline._cfg.agent_tick_max_steps
            ):
                break
            ok = await pipeline._run_tool_step(
                messages,
                ctx,
                loop_tag="reflect",
                tool_choice="auto",
            )
            if not ok:
                break

    pipeline.last_ctx = ctx


async def run_tool_step(
    pipeline: ProactiveJudgeHost,
    messages: list[dict],
    ctx: AgentTickContext,
    *,
    loop_tag: str,
    tool_choice: str | dict = "auto",
    schemas: list[dict] | None = None,
    retry_on_no_tool_call: bool = False,
) -> bool:
    """调用模型并执行工具；同场景模式可纠正一次纯文本响应。"""

    active_schemas = schemas or TOOL_SCHEMAS
    llm_fn = pipeline._llm_fn
    if llm_fn is None:
        return False
    tool_call = await llm_fn(messages, active_schemas, tool_choice)
    if tool_call is None and retry_on_no_tool_call:
        logger.warning(
            "[proactive_v2] %s: missing required tool call, retrying once",
            loop_tag,
        )
        messages.append(
            {"role": "user", "content": _SCENE_TOOL_PROTOCOL_RETRY_PROMPT}
        )
        tool_call = await llm_fn(messages, active_schemas, "required")
        if tool_call is None:
            ctx.skip_reason = "tool_protocol_error"
            ctx.skip_note = _TOOL_PROTOCOL_ERROR_NOTE
            logger.warning(
                diagnostic_line(
                    "ProactiveTurnPipeline._run_tool_step",
                    event="protocol_error",
                    flow="proactive",
                    phase="agent_loop",
                    session=pipeline._session_key,
                    tick=ctx.tick_id,
                    action="skip",
                    reason="tool_protocol_error",
                    counts=f"step:{ctx.steps_taken}",
                    note=_TOOL_PROTOCOL_ERROR_NOTE,
                )
            )
            return False
    if tool_call is None:
        logger.warning(
            "[proactive_v2] %s: llm_fn returned None at step %d, stopping",
            loop_tag,
            ctx.steps_taken,
        )
        return False
    tool_name = tool_call.get("name", "")
    tool_args = tool_call.get("input", {})
    arg_summary = json.dumps(tool_args, ensure_ascii=False)[:200]
    logger.info(
        diagnostic_line(
            "ProactiveTurnPipeline._run_tool_step",
            event="tool_call",
            flow="proactive",
            phase="agent_loop",
            session=pipeline._session_key,
            tick=ctx.tick_id,
            action=str(tool_name or "-"),
            counts=f"step:{ctx.steps_taken}",
        )
    )
    logger.info(
        "[proactive_v2] %s step %d: %s  args=%s",
        loop_tag,
        ctx.steps_taken,
        tool_name,
        arg_summary,
    )
    ctx.steps_taken += 1
    exec_result = await pipeline._tool_executor.execute(
        ToolExecutionRequest(
            call_id=str(tool_call.get("id") or f"call_{ctx.steps_taken}"),
            tool_name=tool_name,
            arguments=tool_args,
            source="proactive",
            session_key=pipeline._session_key,
        ),
        lambda name, args: dispatch(name, args, ctx, pipeline._tool_deps),
    )
    if exec_result.status == "error":
        logger.warning(
            diagnostic_line(
                "ProactiveTurnPipeline._run_tool_step",
                event="tool_result",
                flow="proactive",
                phase="agent_loop",
                session=pipeline._session_key,
                tick=ctx.tick_id,
                action=str(tool_name or "-"),
                reason="tool_error",
                counts=f"step:{ctx.steps_taken}",
                note=str(exec_result.output)[:160],
            )
        )
        logger.warning(
            "[proactive_v2] %s: tool error: %s",
            loop_tag,
            exec_result.output,
        )
        result = str(exec_result.output)
        call_id = tool_call.get("id") or f"call_{ctx.steps_taken}"
        pipeline._record_tick_step(
            ctx,
            phase=f"{loop_tag}:error",
            tool_name=tool_name,
            tool_call_id=str(call_id),
            tool_args=tool_args,
            tool_result_text=result,
        )
        pipeline._append_tool_messages(
            messages,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_call_id=call_id,
            result=result,
        )
        return False

    result = str(exec_result.output)
    logger.info(
        diagnostic_line(
            "ProactiveTurnPipeline._run_tool_step",
            event="tool_result",
            flow="proactive",
            phase="agent_loop",
            session=pipeline._session_key,
            tick=ctx.tick_id,
            action=str(tool_name or "-"),
            reason="-",
            counts=f"step:{ctx.steps_taken}",
        )
    )
    call_id = tool_call.get("id") or f"call_{ctx.steps_taken}"
    pipeline._record_tick_step(
        ctx,
        phase=loop_tag,
        tool_name=tool_name,
        tool_call_id=str(call_id),
        tool_args=tool_args,
        tool_result_text=result,
    )
    pipeline._append_tool_messages(
        messages,
        tool_name=tool_name,
        tool_args=tool_args,
        tool_call_id=call_id,
        result=result,
    )
    return True


def append_tool_messages(
    messages: list[dict],
    *,
    tool_name: str,
    tool_args: dict,
    tool_call_id: str,
    result: str,
) -> None:
    """把一次工具调用和结果追加到模型消息历史。"""

    messages.append(
        {
            "role": "assistant",
            "content": f"调用工具 {tool_name}",
            "tool_calls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(tool_args, ensure_ascii=False),
                    },
                }
            ],
        }
    )
    messages.append(
        {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result,
        }
    )
