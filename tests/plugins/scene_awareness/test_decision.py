from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from plugins.scene_awareness.decision import SceneDecisionInput, decide_scene


@pytest.mark.asyncio
async def test_decide_scene_returns_validated_started_scene() -> None:
    provider = cast(
        Any,
        SimpleNamespace(
            chat=AsyncMock(
                return_value=SimpleNamespace(
                    content=(
                        '{"transition":"started","should_generate":true,'
                        '"scene_key":"rain-confession",'
                        '"prompt":"1girl, pink hair, standing in rain, emotional, night",'
                        '"negative_prompt":"blurry, text","size_preset":"portrait"}'
                    )
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
    assert decision.size_preset == "portrait"
    call = provider.chat.await_args.kwargs
    assert call["model"] == "qwen-flash"
    assert call["disable_thinking"] is True
    assert "started 和 changed 必须返回 should_generate=true" in call["messages"][0]["content"]


@pytest.mark.asyncio
async def test_decide_scene_allows_closed_without_generation() -> None:
    provider = cast(
        Any,
        SimpleNamespace(
            chat=AsyncMock(
                return_value=SimpleNamespace(
                    content='{"transition":"closed","should_generate":false}'
                )
            )
        ),
    )

    decision = await decide_scene(
        provider,
        model="qwen-flash",
        decision_input=SceneDecisionInput(
            role_name="Mira",
            role_prompt="role",
            user_message="晚安",
            current_scene_key="bedroom-night",
        ),
    )

    assert decision.transition == "closed"
    assert decision.should_generate is False


@pytest.mark.asyncio
async def test_decide_scene_allows_none_without_a_scene() -> None:
    provider = cast(
        Any,
        SimpleNamespace(
            chat=AsyncMock(
                return_value=SimpleNamespace(
                    content='{"transition":"none","should_generate":false}'
                )
            )
        ),
    )

    decision = await decide_scene(
        provider,
        model="qwen-flash",
        decision_input=SceneDecisionInput(
            role_name="Mira",
            role_prompt="role",
            user_message="你觉得今天的系统怎么样？",
        ),
    )

    assert decision.transition == "none"
    assert decision.scene_key == ""
    assert decision.should_generate is False
    prompt = provider.chat.await_args.kwargs["messages"][0]["content"]
    assert "没有 current_scene_key 且本轮没有形成任何明确可见场景时为 none" in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "error"),
    [
        ("not-json", "合法 JSON"),
        ('{"transition":"other","should_generate":false}', "transition"),
        ('{"transition":"started","should_generate":false}', "必须生成 CG"),
        ('{"transition":"closed","should_generate":true}', "不能生成 CG"),
        ('{"transition":"none","should_generate":true}', "none 不能生成 CG"),
        ('{"transition":"none","should_generate":false}', "已有场景"),
        (
            '{"transition":"none","should_generate":false,"scene_key":"rain"}',
            "不能提供场景或图像参数",
        ),
        (
            '{"transition":"changed","should_generate":true,'
            '"scene_key":"old-scene","prompt":"1girl, rain",'
            '"negative_prompt":"","size_preset":"portrait"}',
            "新的 scene_key",
        ),
        (
            '{"transition":"started","should_generate":true,'
            '"scene_key":"rain","prompt":"雨中的少女",'
            '"negative_prompt":"","size_preset":"portrait"}',
            "仅支持英文 NovelAI tags",
        ),
    ],
)
async def test_decide_scene_rejects_invalid_model_output(
    content: str,
    error: str,
) -> None:
    provider = cast(
        Any,
        SimpleNamespace(chat=AsyncMock(return_value=SimpleNamespace(content=content))),
    )

    with pytest.raises(ValueError, match=error):
        await decide_scene(
            provider,
            model="qwen-flash",
            decision_input=SceneDecisionInput(
                role_name="Mira",
                role_prompt="role",
                user_message="message",
                current_scene_key="old-scene",
            ),
        )
