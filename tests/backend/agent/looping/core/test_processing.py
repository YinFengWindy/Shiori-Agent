"""Host turn cancellation notifies transport stream owners before returning."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.looping.core import AgentLoop
from agent.provider import LLMResponse, ToolCall
from bus.event_bus import EventBus
from shiori_sdk.messages import InboundMessage, OutboundMessage
from shiori_sdk.channel_events import TurnCancelled
from shiori_sdk.channels.message_source import MessageSource
from tests.support.tool_hooks import (
    FinalizeOnCallHook,
    _DummyTool,
    _FakeProvider,
    _StrictProvider,
    _make_agent_loop_with_tools,
)


@pytest.mark.asyncio
async def test_cancelled_processing_emits_origin_identity_for_stream_cleanup():
    loop = object.__new__(AgentLoop)
    loop._event_bus = EventBus()
    loop._processing_state = None
    loop._interrupt_states = {}
    loop._core_runner = SimpleNamespace(
        process=AsyncMock(side_effect=asyncio.CancelledError())
    )
    observed: list[TurnCancelled] = []

    async def observe(event: TurnCancelled):
        observed.append(event)

    loop._event_bus.on(TurnCancelled, observe)
    message = InboundMessage(
        "qqbot",
        "user",
        "c2c:user",
        "hello",
        metadata={"external_message_id": "source-1"},
    )
    with pytest.raises(asyncio.CancelledError):
        await loop._process(message, "role:mira")
    assert observed == [TurnCancelled("role:mira", "qqbot", "c2c:user", "source-1")]


@pytest.mark.asyncio
async def test_direct_desktop_turn_uses_persisted_sender_identity():
    loop = object.__new__(AgentLoop)
    loop._active_tasks = {}
    loop._active_turn_states = {}
    loop._session_services = SimpleNamespace(
        session_manager=SimpleNamespace(
            role_session_key=lambda role_id: f"role:{role_id}"
        )
    )
    loop._process = AsyncMock(
        return_value=OutboundMessage(
            channel="desktop", chat_id="role:mira", content="ok"
        )
    )
    metadata = {
        "source": "desktop",
        "role_id": "mira",
        "sender_id": "desktop",
        "chat_type": "desktop",
        "transport_channel": "desktop",
        "transport_chat_id": "role:mira",
    }

    await AgentLoop.process_direct(
        loop,
        content="刚才群里是谁说的？",
        session_key="role:mira",
        channel="desktop",
        chat_id="role:mira",
        metadata=metadata,
    )

    current = loop._process.await_args.args[0]
    assert current.sender == "desktop"
    assert MessageSource.from_inbound(current) == MessageSource.from_metadata(
        current.metadata, session_key="role:mira"
    )


def _assert_finalize_summary_request(provider) -> None:
    """The closing request carries no tools and names the tool-loop reason."""
    summary_call = provider.calls[-1]
    assert summary_call["tools"] == []
    assert summary_call["call_purpose"] == "auxiliary"
    assert "tool_call_loop" in summary_call["messages"][-1]["content"]


async def test_finalize_denial_stops_repeated_calls_and_returns_closed_summary(
    tmp_path,
):
    """A finalize denial ends the internal loop with a summary, not a template."""
    tool = _DummyTool("dummy")
    provider = _StrictProvider(
        [
            LLMResponse(content="", tool_calls=[ToolCall("c1", "dummy", {"x": 1})]),
            LLMResponse(content="", tool_calls=[ToolCall("c2", "dummy", {"x": 1})]),
            LLMResponse(content="", tool_calls=[ToolCall("c3", "dummy", {"x": 1})]),
            LLMResponse(
                content="已完成阶段A，剩余阶段B，下一步继续补齐", tool_calls=[]
            ),
        ]
    )
    loop = _make_agent_loop_with_tools(
        tmp_path, provider, [tool], hooks=[FinalizeOnCallHook("c3")]
    )

    final, tools_used, _, _vn, _ = await loop._run_agent_loop(
        [{"role": "user", "content": "test"}]
    )

    assert "最大迭代" not in final
    assert "下一步" in final
    assert len(tool.calls) == 2
    assert tools_used == ["dummy", "dummy"]
    assert len(provider.calls) == 4
    _assert_finalize_summary_request(provider)


async def test_finalize_denial_truncates_the_rest_of_a_multi_tool_batch(tmp_path):
    """The finalize call's siblings are skipped yet still answered in the chain."""
    tool_a = _DummyTool("a")
    tool_b = _DummyTool("b")
    hook = FinalizeOnCallHook("a2")
    provider = _StrictProvider(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall("a1", "a", {"x": 1}),
                    ToolCall("b1", "b", {"x": 2}),
                ],
            ),
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall("a2", "a", {"x": 1}),
                    ToolCall("b2", "b", {"x": 2}),
                ],
            ),
            LLMResponse(content="已总结当前进度", tool_calls=[]),
        ]
    )
    loop = _make_agent_loop_with_tools(
        tmp_path, provider, [tool_a, tool_b], hooks=[hook]
    )

    final, tools_used, _, _vn, _ = await loop._run_agent_loop(
        [{"role": "user", "content": "test"}]
    )

    assert final == "已总结当前进度"
    assert tools_used == ["a", "b"]
    assert hook.seen == ["a1", "b1", "a2"]
    assert len(tool_a.calls) == 1
    assert len(tool_b.calls) == 1
    _assert_finalize_summary_request(provider)


async def test_finalize_denial_of_a_locked_tool_request_keeps_chain_closed(tmp_path):
    """Requests for not-yet-unlocked tools go through the same finalize protocol."""
    tool = _DummyTool("hidden_tool")
    provider = _StrictProvider(
        [
            LLMResponse(
                content="", tool_calls=[ToolCall("h1", "hidden_tool", {"x": 1})]
            ),
            LLMResponse(
                content="", tool_calls=[ToolCall("h2", "hidden_tool", {"x": 1})]
            ),
            LLMResponse(content="已总结当前进度", tool_calls=[]),
        ]
    )
    loop = _make_agent_loop_with_tools(
        tmp_path,
        provider,
        [tool],
        hooks=[FinalizeOnCallHook("h2")],
        tool_search_enabled=True,
    )

    final, tools_used, _, _vn, _ = await loop._run_agent_loop(
        [{"role": "user", "content": "test"}]
    )

    assert final == "已总结当前进度"
    assert tools_used == []
    assert tool.calls == []
    assert len(provider.calls) == 3
    _assert_finalize_summary_request(provider)


async def test_max_iterations_returns_progress_summary_not_template(tmp_path):
    tool = _DummyTool("dummy")
    provider = _FakeProvider(
        [
            LLMResponse(content="", tool_calls=[ToolCall("c1", "dummy", {"x": 1})]),
            LLMResponse(
                content="目前完成数据抓取，待整理结论，下一步继续", tool_calls=[]
            ),
        ]
    )
    loop = _make_agent_loop_with_tools(tmp_path, provider, [tool])
    loop.max_iterations = 1

    final, _, _, _vn, _ = await loop._run_agent_loop(
        [{"role": "user", "content": "test"}]
    )

    assert "最大迭代" not in final
    assert "下一步" in final
