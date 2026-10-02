from typing import Any, cast
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.compaction import CompactionFailedError
from session.manager import SessionManager
from agent.tools.base import Tool
from agent.tools.registry import ToolRegistry

from agent.core.passive_turn import DefaultReasoner
from agent.core.runtime_support import ToolDiscoveryState
from agent.core.runtime_support import LLMServices
from agent.core.types import ContextRenderResult
from agent.core.types import ContextRequest
from agent.core.types import ReasonerResult
from agent.looping.ports import LLMConfig
from agent.provider import ContentSafetyError, ContextLengthError, LLMResponse, ToolCall
from bus.events import InboundMessage


def _stub_turn_injection_context(
    *, turn_injection_prompt: str | None = None
) -> dict[str, str]:
    if not turn_injection_prompt:
        return {}
    return {"turn_injection": turn_injection_prompt}


def _msg():
    return InboundMessage(
        content="hello",
        media=[],
        channel="cli",
        sender="user",
        chat_id="1",
        timestamp=datetime.now(timezone.utc),
    )


def _session(manager: SessionManager):
    session = manager.get_or_create("s:1")
    for index in range(3):
        session.add_message("user", str(index * 2))
        session.add_message(
            "assistant",
            str(index * 2 + 1),
            tool_chain=(
                [
                    {
                        "calls": [
                            {
                                "call_id": name,
                                "name": name,
                                "arguments": {},
                                "result": "done",
                            }
                            for name in ["always", "x", "uninstalled"]
                        ]
                    }
                ]
                if index == 0
                else []
            ),
        )
    manager.save(session)
    return session


def _tools():
    return SimpleNamespace(
        get_always_on_names=lambda: {"always"},
        has_tool=lambda name: name != "uninstalled",
        get_schemas=lambda names=None, external_only=False: [],
        get_registered_order=lambda names=None: sorted(names or ()),
        get_deferred_names=lambda visible=None, external_only=False: {
            "builtin": [],
            "mcp": {},
        },
        get_tool=lambda name: None,
        get_context=lambda: {},
    )


def _make_reasoner(
    *,
    manager: SessionManager,
    discovery: ToolDiscoveryState,
    tool_search_enabled: bool,
    provider=None,
    tools=None,
):
    def _render(request: ContextRequest, **kwargs: object) -> ContextRenderResult:
        messages = list(request.history) + [
            {"role": "user", "content": request.current_message}
        ]
        return ContextRenderResult(
            system_prompt="",
            turn_injection_context=_stub_turn_injection_context(
                turn_injection_prompt=request.turn_injection_prompt
            ),
            messages=messages,
            debug_breakdown=[],
        )

    return DefaultReasoner(
        llm=cast(
            Any,
            LLMServices(
                provider=(
                    provider
                    if provider is not None
                    else SimpleNamespace(chat=AsyncMock())
                ),
                light_provider=SimpleNamespace(),
            ),
        ),
        llm_config=LLMConfig(model="m", max_iterations=4, max_tokens=256),
        tools=cast(Any, tools if tools is not None else _tools()),
        discovery=discovery,
        tool_search_enabled=tool_search_enabled,
        context=cast(
            Any,
            SimpleNamespace(
                render=_render,
            ),
        ),
        session_manager=manager,
    )


def test_reasoner_run_turn_retries_and_preloads_history_tools(tmp_path):
    manager = SessionManager(tmp_path)
    reasoner = _make_reasoner(
        manager=manager, discovery=ToolDiscoveryState(), tool_search_enabled=True
    )
    reasoner.run = AsyncMock(
        side_effect=[
            ContentSafetyError("blocked"),
            ReasonerResult(
                reply="ok",
                metadata={"tools_used": ["tool_search", "x"], "tool_chain": []},
            ),
        ]
    )

    result = asyncio.run(reasoner.run_turn(msg=_msg(), session=_session(manager)))

    assert result.reply == "ok"
    assert result.tools_used == ["tool_search", "x"]
    assert result.tool_chain == []
    assert result.thinking is None
    assert result.context_retry["selected_plan"] == "trim_skills_catalog"
    # 历史里的 always_on 与已卸载工具不进入预加载，每次重试都带同一集合。
    for call in reasoner.run.await_args_list:
        assert call.kwargs["preloaded_tools"] == {"x"}
        assert call.kwargs["preloaded_tool_order"] == ["x"]


def test_reasoner_run_turn_context_length_failure_is_explicit_without_retry(tmp_path):
    manager = SessionManager(tmp_path)
    reasoner = _make_reasoner(
        manager=manager, discovery=ToolDiscoveryState(), tool_search_enabled=False
    )
    reasoner.run = AsyncMock(side_effect=ContextLengthError("long"))
    session = _session(manager)
    original_ids = [message["id"] for message in session.messages]
    with pytest.raises(CompactionFailedError) as caught:
        asyncio.run(reasoner.run_turn(msg=_msg(), session=session))
    assert caught.value.result.failure_stage == "provider"
    assert caught.value.result.error == "long"
    assert not caught.value.result.committed
    assert reasoner.run.await_count == 1
    assert [message["id"] for message in session.messages] == original_ids


def test_reasoner_run_turn_content_safety_trims_dynamic_sections_before_history(
    tmp_path,
):
    manager = SessionManager(tmp_path)
    calls: list[dict] = []

    def _render(request: ContextRequest, **kwargs: object) -> ContextRenderResult:
        calls.append(
            {
                "history_len": len(request.history),
                "disabled_sections": set(request.disabled_sections or set()),
            }
        )
        return ContextRenderResult(
            system_prompt="",
            turn_injection_context=_stub_turn_injection_context(
                turn_injection_prompt=request.turn_injection_prompt
            ),
            messages=list(request.history) + [{"role": "user"}],
            debug_breakdown=[],
        )

    discovery = ToolDiscoveryState()
    reasoner = DefaultReasoner(
        llm=cast(
            Any,
            LLMServices(
                provider=SimpleNamespace(chat=AsyncMock()),
                light_provider=SimpleNamespace(),
            ),
        ),
        llm_config=LLMConfig(model="m", max_iterations=4, max_tokens=256),
        tools=cast(Any, _tools()),
        discovery=discovery,
        tool_search_enabled=False,
        context=cast(
            Any,
            SimpleNamespace(
                render=_render,
            ),
        ),
        session_manager=manager,
    )
    reasoner.run = AsyncMock(
        side_effect=[
            ContentSafetyError("blocked"),
            ReasonerResult(
                reply="ok",
                metadata={"tools_used": [], "tool_chain": []},
            ),
        ]
    )

    result = asyncio.run(reasoner.run_turn(msg=_msg(), session=_session(manager)))
    assert result.reply == "ok"
    assert result.tools_used == []
    assert result.tool_chain == []
    assert calls[0]["history_len"] == 10
    assert calls[0]["disabled_sections"] == set()
    assert calls[1]["history_len"] == calls[0]["history_len"]
    assert calls[1]["disabled_sections"] == {"skills_catalog"}


def test_provider_context_failure_after_side_effect_never_replays_the_tool(tmp_path):
    class SideEffectTool(Tool):
        name = "side_effect"
        description = "Record one external operation"
        parameters = {"type": "object", "properties": {}}

        def __init__(self):
            self.calls = 0

        async def execute(self, **kwargs):
            self.calls += 1
            return "already committed"

    manager = SessionManager(tmp_path)
    session = _session(manager)
    original = deepcopy(session.messages)
    tool = SideEffectTool()
    registry = ToolRegistry()
    registry.register(tool, always_on=True)
    provider = SimpleNamespace(
        chat=AsyncMock(
            side_effect=[
                LLMResponse(
                    content="", tool_calls=[ToolCall("once", "side_effect", {})]
                ),
                ContextLengthError("tool result does not fit"),
            ]
        )
    )
    reasoner = _make_reasoner(
        manager=manager,
        discovery=ToolDiscoveryState(),
        tool_search_enabled=False,
        provider=provider,
        tools=registry,
    )
    with pytest.raises(CompactionFailedError) as caught:
        asyncio.run(reasoner.run_turn(msg=_msg(), session=session))
    assert caught.value.result.failure_stage == "provider"
    assert tool.calls == 1
    assert provider.chat.await_count == 2
    assert session.messages == original
