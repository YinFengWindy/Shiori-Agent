import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from agent.provider import LLMResponse, ToolCall
from plugins.scene_awareness.contracts import SCENE_DECISION_TOOL_NAME
from plugins.scene_awareness.decision import SceneDecisionInput, decide_scene


def _scene_tool_call(**overrides: Any) -> ToolCall:
    arguments = {
        "transition": "started",
        "should_generate": True,
        "scene_key": "rain-confession",
        "visual_key": "rain-confession-standing",
        "prompt": "1girl, pink hair, standing in rain, emotional, night",
        "negative_prompt": "blurry, text",
        "size_preset": "portrait",
    }
    arguments.update(overrides)
    return ToolCall("scene-1", SCENE_DECISION_TOOL_NAME, arguments)


@pytest.mark.asyncio
async def test_decide_scene_forces_observer_tool_with_isolated_system_prompt() -> None:
    provider = cast(
        Any,
        SimpleNamespace(
            chat=AsyncMock(
                return_value=LLMResponse(
                    content="",
                    tool_calls=[_scene_tool_call()],
                )
            )
        ),
    )

    decision = await decide_scene(
        provider,
        model="qwen-flash",
        decision_input=SceneDecisionInput(
            role_name="Mira",
            role_prompt="粉发少女",
            user_message="我终于找到你了",
            assistant_reply="她站在雨里，终于说出了藏了很久的话。",
        ),
    )

    assert decision.transition == "started"
    assert decision.should_generate is True
    assert decision.scene_key == "rain-confession"
    call = provider.chat.await_args.kwargs
    assert call["model"] == "qwen-flash"
    assert call["disable_thinking"] is True
    assert call["messages"][0]["role"] == "system"
    assert "不是角色扮演者" in call["messages"][0]["content"]
    assert call["tool_choice"] == {
        "type": "function",
        "function": {"name": SCENE_DECISION_TOOL_NAME},
    }
    assert call["tools"][0]["function"]["name"] == SCENE_DECISION_TOOL_NAME


@pytest.mark.asyncio
async def test_decide_scene_repairs_invalid_tool_protocol_once() -> None:
    provider = cast(
        Any,
        SimpleNamespace(
            chat=AsyncMock(
                side_effect=[
                    LLMResponse(content="我来解释一下", tool_calls=[]),
                    LLMResponse(
                        content="",
                        tool_calls=[
                            _scene_tool_call(
                                transition="none",
                                should_generate=False,
                                scene_key="",
                                visual_key="",
                                prompt="",
                                negative_prompt="",
                                size_preset="",
                            )
                        ],
                    ),
                ]
            )
        ),
    )

    decision = await decide_scene(
        provider,
        model="qwen-flash",
        decision_input=SceneDecisionInput(
            role_name="Mira",
            role_prompt="role",
            user_message="这段技术方案合理吗？",
        ),
    )

    assert decision.transition == "none"
    assert provider.chat.await_count == 2
    retry_messages = provider.chat.await_args_list[1].kwargs["messages"]
    assert "上一轮提交无效" in retry_messages[1]["content"]
    assert "必须调用一次提交工具" in retry_messages[1]["content"]


@pytest.mark.asyncio
async def test_decide_scene_repairs_malformed_tool_arguments_once() -> None:
    provider = cast(
        Any,
        SimpleNamespace(
            chat=AsyncMock(
                side_effect=[
                    json.JSONDecodeError("invalid", "{", 1),
                    LLMResponse(content="", tool_calls=[_scene_tool_call()]),
                ]
            )
        ),
    )

    decision = await decide_scene(
        provider,
        model="qwen-flash",
        decision_input=SceneDecisionInput(
            role_name="Mira",
            role_prompt="role",
            user_message="雨突然下大了",
            assistant_reply="她站在雨夜的车站里。",
        ),
    )

    assert decision.transition == "started"
    assert provider.chat.await_count == 2
    retry_messages = provider.chat.await_args_list[1].kwargs["messages"]
    assert "参数不是合法 JSON" in retry_messages[1]["content"]
