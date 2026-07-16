from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from typing import Any, cast

import pytest

from agent.context import ContextBuilder
from agent.lifecycle.types import PromptRenderResult
from agent.looping.ports import SessionServices
from agent.tools.registry import ToolRegistry
from agent.core.runner import CoreRunner, CoreRunnerDeps
from bus.events import (
    CodingAgentCompletionItem,
    InboundMessage,
    OutboundMessage,
    SpawnCompletionItem,
)
from bus.internal_events import CodingAgentCompletionEvent, SpawnCompletionEvent


@pytest.mark.asyncio
async def test_core_runner_routes_passive_message_to_agent_core():
    runner = CoreRunner(
        CoreRunnerDeps(
            agent_core=cast(
                Any,
                SimpleNamespace(
                    process=AsyncMock(
                        return_value=OutboundMessage(
                            channel="cli",
                            chat_id="1",
                            content="final",
                        )
                    ),
                    pipeline=SimpleNamespace(),
                ),
            ),
        )
    )
    msg = InboundMessage(channel="cli", sender="hua", chat_id="1", content="hi")

    out = await runner.process(msg, "cli:1")

    assert out.content == "final"
    runner._agent_core.process.assert_awaited_once_with(
        msg,
        "cli:1",
        dispatch_outbound=True,
    )


@pytest.mark.asyncio
async def test_core_runner_handles_spawn_completion_via_direct_helper_deps():
    session = MagicMock()
    session.get_history.return_value = [{"role": "user", "content": "old"}]
    session.metadata = {"role_id": "mira"}
    session.key = "scheduler:job-1"
    session.messages = [{"id": "telegram:123:9"}]
    session_svc = SimpleNamespace(
        session_manager=SimpleNamespace(get_or_create=MagicMock(return_value=session))
    )
    context = SimpleNamespace(
        render=MagicMock(return_value=SimpleNamespace(messages=[{"role": "system", "content": "prompt"}]))
    )
    pipeline_mock = SimpleNamespace(
        post_reasoning=AsyncMock(
            return_value=OutboundMessage(
                channel="telegram",
                chat_id="123",
                content="spawn done",
            )
        )
    )
    item = SpawnCompletionItem(
        channel="telegram",
        chat_id="123",
        event=SpawnCompletionEvent(
            job_id="",
            label="任务",
            task="总结结果",
            status="completed",
            result="ok",
            exit_reason="completed",
            retry_count=0,
        ),
    )
    tool_context = {
        "channel": "telegram",
        "chat_id": "123",
        "session_key": "scheduler:job-1",
        "role_id": "mira",
        "current_timestamp": item.timestamp.isoformat(),
        "current_user_source_ref": "telegram:123:9",
    }
    tools = SimpleNamespace(
        set_context=MagicMock(),
        get_context=MagicMock(return_value=dict(tool_context)),
    )
    run_agent_loop_fn = AsyncMock(
        return_value=("done", ["spawn"], [{"name": "spawn"}], None, None)
    )
    prompt_render_fn = AsyncMock(
        return_value=PromptRenderResult(
            messages=[{"role": "system", "content": "prompt"}]
        )
    )
    runner = CoreRunner(
        CoreRunnerDeps(
            agent_core=cast(
                Any,
                SimpleNamespace(
                    process=AsyncMock(),
                    pipeline=pipeline_mock,
                ),
            ),
            session=cast(SessionServices, session_svc),
            context=cast(ContextBuilder, context),
            tools=cast(ToolRegistry, tools),
            memory_window=12,
            run_agent_loop_fn=run_agent_loop_fn,
            prompt_render_fn=prompt_render_fn,
        )
    )
    out = await runner.process(item, "scheduler:job-1", dispatch_outbound=False)

    assert out.content == "spawn done"
    session_calls = session_svc.session_manager.get_or_create.call_args_list
    assert session_calls
    assert {call.args[0] for call in session_calls} == {"scheduler:job-1"}
    tools.set_context.assert_called_once_with(
        channel="telegram",
        chat_id="123",
        session_key="scheduler:job-1",
            role_id="mira",
            current_timestamp=item.timestamp.isoformat(),
            current_user_source_ref="telegram:123:9",
            defer_push_session_sync="true",
        )
    prompt_render_fn.assert_awaited_once()
    render_input = prompt_render_fn.await_args.args[0]
    assert render_input.session_key == "scheduler:job-1"
    assert "后台任务回传" in render_input.content
    run_agent_loop_fn.assert_awaited_once()
    loop_kwargs = run_agent_loop_fn.await_args.kwargs
    assert loop_kwargs["tool_event_session_key"] == "scheduler:job-1"
    assert loop_kwargs["tool_event_channel"] == "telegram"
    assert loop_kwargs["tool_event_chat_id"] == "123"
    assert loop_kwargs["tool_execution_context"] == tool_context
    pipeline_mock.post_reasoning.assert_awaited_once()
    pr_kwargs = pipeline_mock.post_reasoning.await_args.kwargs
    assert pr_kwargs["dispatch_outbound"] is False
    runner._agent_core.process.assert_not_awaited()


@pytest.mark.asyncio
async def test_core_runner_routes_coding_completion_to_manager_summary():
    thread_id = "thread:mira:telegram:123"
    session = MagicMock()
    session.get_history.return_value = [{"role": "user", "content": "修复登录"}]
    session.metadata = {"role_id": "mira", "thread_id": thread_id}
    session.key = thread_id
    session.messages = [{"id": "telegram:123:10"}]
    session_svc = SimpleNamespace(
        session_manager=SimpleNamespace(get_or_create=MagicMock(return_value=session))
    )
    context = SimpleNamespace(
        render=MagicMock(
            return_value=SimpleNamespace(
                messages=[{"role": "system", "content": "prompt"}]
            )
        )
    )
    pipeline_mock = SimpleNamespace(
        post_reasoning=AsyncMock(
            return_value=OutboundMessage(
                channel="telegram",
                chat_id="123",
                content="Coding 任务汇总完成",
            )
        )
    )
    metadata = {
        "source_channel": "telegram",
        "source_chat_id": "123",
        "request_id": "request-1",
    }
    item = CodingAgentCompletionItem(
        channel="telegram",
        chat_id="123",
        event=CodingAgentCompletionEvent(
            task_id="task-1",
            run_id="run-1",
            label="修复登录",
            task="修复登录白屏",
            mode="execute",
            status="succeeded",
            provider="codex",
            profile_id="codex_deep",
            result="已修改登录逻辑，相关测试通过",
            thread_id=thread_id,
            manager_role_id="mira",
            request_id="request-1",
            delivery_key="delivery-1",
            artifacts=("D:/worktrees/repo/run-1",),
        ),
        metadata=metadata,
    )
    tool_context = {
        "channel": "telegram",
        "chat_id": "123",
        "session_key": thread_id,
        "role_id": "mira",
        "current_timestamp": item.timestamp.isoformat(),
        "current_user_source_ref": "telegram:123:10",
    }
    tools = SimpleNamespace(
        set_context=MagicMock(),
        get_context=MagicMock(return_value=dict(tool_context)),
    )
    run_agent_loop_fn = AsyncMock(
        return_value=("Coding 任务汇总完成", ["coding_agent"], [], None, None)
    )
    prompt_render_fn = AsyncMock(
        return_value=PromptRenderResult(
            messages=[{"role": "system", "content": "prompt"}]
        )
    )
    runner = CoreRunner(
        CoreRunnerDeps(
            agent_core=cast(
                Any,
                SimpleNamespace(process=AsyncMock(), pipeline=pipeline_mock),
            ),
            session=cast(SessionServices, session_svc),
            context=cast(ContextBuilder, context),
            tools=cast(ToolRegistry, tools),
            memory_window=12,
            run_agent_loop_fn=run_agent_loop_fn,
            prompt_render_fn=prompt_render_fn,
        )
    )

    out = await runner.process(item, item.session_key, dispatch_outbound=False)

    assert out.content == "Coding 任务汇总完成"
    assert item.metadata == metadata
    session_svc.session_manager.get_or_create.assert_called_once_with(thread_id)
    tools.set_context.assert_called_once_with(
        channel="telegram",
        chat_id="123",
        session_key=thread_id,
        role_id="mira",
        current_timestamp=item.timestamp.isoformat(),
            current_user_source_ref="telegram:123:10",
            defer_push_session_sync="true",
            thread_id=thread_id,
            request_id="request-1",
            delivery_key="delivery-1",
            transport_channel="telegram",
            transport_chat_id="123",
            source_channel="telegram",
            source_chat_id="123",
        )
    prompt_render_fn.assert_awaited_once()
    render_input = prompt_render_fn.await_args.args[0]
    assert render_input.session_key == thread_id
    assert "[Coding Agent 运行回传]" in render_input.content
    assert "codex / codex_deep" in render_input.content
    assert "已修改登录逻辑，相关测试通过" in render_input.content
    assert "D:/worktrees/repo/run-1" in render_input.content
    run_agent_loop_fn.assert_awaited_once()
    loop_kwargs = run_agent_loop_fn.await_args.kwargs
    assert loop_kwargs["tool_event_session_key"] == thread_id
    assert loop_kwargs["tool_execution_context"] == tool_context
    pipeline_mock.post_reasoning.assert_awaited_once()
    pr_kwargs = pipeline_mock.post_reasoning.await_args.kwargs
    assert pr_kwargs["msg"].sender == "coding_agent"
    assert pr_kwargs["msg"].metadata == {"skip_post_memory": True}
    assert pr_kwargs["dispatch_outbound"] is False
    runner._agent_core.process.assert_not_awaited()
