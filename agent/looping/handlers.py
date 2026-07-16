from __future__ import annotations

from typing import TYPE_CHECKING, cast

from agent.core.passive_support import predict_current_user_source_ref
from agent.core.passive_turn import get_session_metadata
from agent.core.runtime_support import AgentLoopRunner, PromptRenderRunner, TurnRunResult
from agent.lifecycle.types import PromptRenderInput
from agent.looping.ports import SessionServices
from bus.events import (
    CodingAgentCompletionItem,
    InboundMessage,
    OutboundMessage,
    SpawnCompletionItem,
)

if TYPE_CHECKING:
    from agent.core.passive_turn import PassiveTurnPipeline
    from agent.tools.registry import ToolRegistry

async def process_spawn_completion_event(
    *,
    item: SpawnCompletionItem,
    key: str,
    session_svc: SessionServices,
    pipeline: "PassiveTurnPipeline",
    tools: "ToolRegistry",
    memory_window: int,
    run_agent_loop_fn: AgentLoopRunner,
    prompt_render_fn: PromptRenderRunner,
    dispatch_outbound: bool = True,
) -> OutboundMessage:
    # 1. 先读取 session 和内部事件，准备要给主模型的回传消息。
    event = item.event
    label = event.label or "后台任务"
    task = event.task.strip()
    status = (event.status or "incomplete").strip()
    result = event.result.strip()
    exit_reason = event.exit_reason.strip()
    retry_count = event.retry_count

    _EXIT_LABELS: dict[str, str] = {
        "completed": "正常完成",
        "max_iterations": "迭代预算耗尽（任务可能不完整）",
        "tool_loop": "工具调用循环截断（任务可能不完整）",
        "error": "执行出错",
        "forced_summary": "强制汇总（任务可能不完整）",
        "cancelled": "已取消",
    }
    exit_label = _EXIT_LABELS.get(exit_reason, exit_reason or "未知")

    if retry_count >= 1:
        guidance = (
            "⚠️ 已重试一次，不再重试。\n"
            "请直接将已获得的结果汇报给用户，说明已完成的部分和未完成的部分。"
        )
    else:
        guidance = (
            "**处理指引（按顺序判断，选其一执行）**\n"
            "1. 结果完整回答了原始任务 → 直接向用户汇报，不提及内部机制\n"
            "2. 退出原因是【迭代预算耗尽】或【工具调用循环截断】，且核心信息明显不足 → "
            "调用 spawn 重试；task 中说明上次卡在哪、这次从哪继续；"
            "run_in_background=true；同时简短告知用户正在补充\n"
            "3. 结果为空或明显出错 → 直接告知用户失败，询问是否需要重试\n"
            "重试只允许一次。"
        )

    current_message = (
        f"[后台任务回传]\n"
        f"任务标签: {label}\n"
        f"原始任务: {task or '（未提供）'}\n"
        f"退出原因: {exit_label}\n"
        f"执行结果:\n{result or '（无结果）'}\n\n"
        f"{guidance}\n\n"
        "禁止在回复中提及 subagent、spawn、job_id、内部事件等内部概念。\n"
        "必要时可读取结果里提到的文件来补充说明。"
    )

    return await _process_completion_message(
        channel=item.channel,
        chat_id=item.chat_id,
        timestamp=item.timestamp,
        key=key,
        current_message=current_message,
        sender="spawn",
        marker=f"[后台任务完成] {label} ({status})"
        + (f" [{exit_reason}]" if exit_reason else ""),
        default_content={
            "completed": "后台任务已完成。",
            "incomplete": "后台任务未全部完成，部分工作尚未收尾。",
            "cancelled": "后台任务已取消。",
        }.get(status, "后台任务执行出错。"),
        session_svc=session_svc,
        pipeline=pipeline,
        tools=tools,
        memory_window=memory_window,
        run_agent_loop_fn=run_agent_loop_fn,
        prompt_render_fn=prompt_render_fn,
        dispatch_outbound=dispatch_outbound,
    )


async def process_coding_agent_completion_event(
    *,
    item: CodingAgentCompletionItem,
    key: str,
    session_svc: SessionServices,
    pipeline: "PassiveTurnPipeline",
    tools: "ToolRegistry",
    memory_window: int,
    run_agent_loop_fn: AgentLoopRunner,
    prompt_render_fn: PromptRenderRunner,
    dispatch_outbound: bool = True,
) -> OutboundMessage:
    """Lets the manager role synthesize a persisted Coding Agent result."""

    event = item.event
    artifacts = "\n".join(f"- {path}" for path in event.artifacts) or "（无）"
    error = f"\n错误代码: {event.error_code}" if event.error_code else ""
    current_message = (
        "[Coding Agent 运行回传]\n"
        f"任务标签: {event.label or 'Coding 任务'}\n"
        f"任务模式: {event.mode}\n"
        f"执行器: {event.provider} / {event.profile_id}\n"
        f"运行状态: {event.status}{error}\n"
        f"原始任务: {event.task}\n"
        f"执行结果:\n{event.result or '（无结果）'}\n"
        f"产物:\n{artifacts}\n\n"
        "请查询同一任务的其他 Run 状态；若仍有依赖或并行 Run 未结束，只汇报当前进展。"
        "若结果已齐备，向用户汇总方案、改动、测试、风险和保留的 worktree。"
        "不要声称代码已合并、push 或进入原仓库，除非结果明确证明该动作发生。"
    )
    default_content = {
        "succeeded": "Coding 任务已完成。",
        "cancelled": "Coding 任务已取消，运行现场已保留。",
        "waiting_approval": "Coding 任务正在等待你的明确批准。",
    }.get(event.status, "Coding 任务执行失败，运行现场已保留。")
    return await _process_completion_message(
        channel=item.channel,
        chat_id=item.chat_id,
        timestamp=item.timestamp,
        key=key,
        current_message=current_message,
        sender="coding_agent",
        marker=f"[Coding Agent 运行更新] {event.label} ({event.status})",
        default_content=default_content,
        session_svc=session_svc,
        pipeline=pipeline,
        tools=tools,
        memory_window=memory_window,
        run_agent_loop_fn=run_agent_loop_fn,
        prompt_render_fn=prompt_render_fn,
        dispatch_outbound=dispatch_outbound,
        extra_tool_context={
            "role_id": event.manager_role_id,
            "thread_id": event.thread_id,
            "request_id": event.request_id,
            "delivery_key": event.delivery_key,
            "transport_channel": item.channel,
            "transport_chat_id": item.chat_id,
            **{str(name): str(value) for name, value in item.metadata.items()},
        },
    )


async def _process_completion_message(
    *,
    channel: str,
    chat_id: str,
    timestamp,
    key: str,
    current_message: str,
    sender: str,
    marker: str,
    default_content: str,
    session_svc: SessionServices,
    pipeline: "PassiveTurnPipeline",
    tools: "ToolRegistry",
    memory_window: int,
    run_agent_loop_fn: AgentLoopRunner,
    prompt_render_fn: PromptRenderRunner,
    dispatch_outbound: bool,
    extra_tool_context: dict[str, str] | None = None,
) -> OutboundMessage:
    """Runs a typed internal completion through the shared manager-role turn."""

    session = session_svc.session_manager.get_or_create(key)
    session_metadata = get_session_metadata(session)
    tool_context = {
        "channel": channel,
        "chat_id": chat_id,
        "session_key": key,
        "role_id": str(session_metadata.get("role_id") or "").strip(),
        "current_timestamp": timestamp.isoformat(),
        "current_user_source_ref": predict_current_user_source_ref(
            session_manager=session_svc.session_manager,
            session=session,
        ),
        "defer_push_session_sync": "true",
    }
    tool_context.update(extra_tool_context or {})
    tools.set_context(**tool_context)
    tool_execution_context = tools.get_context()
    prompt_render = await prompt_render_fn(
        PromptRenderInput(
            session_key=key,
            channel=channel,
            chat_id=chat_id,
            content=current_message,
            media=None,
            timestamp=timestamp,
            history=session.get_history(max_messages=memory_window),
            skill_names=None,
            retrieved_memory_block="",
            disabled_sections=set(),
            turn_injection_prompt="",
            session_metadata=session_metadata,
        )
    )
    initial_messages = prompt_render.messages
    final_content, tools_used, tool_chain, _, _thinking = await run_agent_loop_fn(
        initial_messages,
        request_time=timestamp,
        preloaded_tools=None,
        tool_event_session_key=key,
        tool_event_channel=channel,
        tool_event_chat_id=chat_id,
        tool_execution_context=tool_execution_context,
    )
    if final_content is None:
        final_content = default_content

    pseudo_msg = InboundMessage(
        channel=channel,
        sender=sender,
        chat_id=chat_id,
        content=marker,
        timestamp=timestamp,
        media=[],
        metadata={"skip_post_memory": True},
    )
    parsed_tool_chain = cast(list[dict[str, object]], tool_chain)
    return await pipeline.post_reasoning(
        msg=pseudo_msg,
        session_key=key,
        turn_result=TurnRunResult(
            reply=final_content,
            tools_used=tools_used,
            tool_chain=parsed_tool_chain,
        ),
        dispatch_outbound=dispatch_outbound,
    )
