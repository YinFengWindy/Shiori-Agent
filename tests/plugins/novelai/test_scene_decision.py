from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from plugins.novelai.scene_decision import SceneCgDecisionInput, decide_scene_cg


@pytest.mark.asyncio
async def test_decide_scene_cg_returns_validated_generation_request() -> None:
    provider = cast(
        Any,
        SimpleNamespace(
            chat=AsyncMock(
                return_value=SimpleNamespace(
                    content=(
                        '{"should_generate":true,"scene_key":"rain-confession",'
                        '"prompt":"1girl, pink hair, standing in rain, emotional, night",'
                        '"negative_prompt":"blurry, text","size_preset":"portrait"}'
                    )
                )
            )
        ),
    )

    decision = await decide_scene_cg(
        provider,
        model="qwen-flash",
        decision_input=SceneCgDecisionInput(
            role_name="Mira",
            role_prompt="粉发少女",
            user_message="我终于找到你了",
            assistant_reply="她站在雨里，终于说出了藏了很久的话。",
        ),
    )

    assert decision.should_generate is True
    assert decision.scene_key == "rain-confession"
    assert decision.size_preset == "portrait"
    call = provider.chat.await_args.kwargs
    assert call["model"] == "qwen-flash"
    assert call["disable_thinking"] is True
    assert "粉发少女" in call["messages"][0]["content"]
    assert "清晰、值得定格的可见画面" in call["messages"][0]["content"]
    assert "普通闲聊" in call["messages"][0]["content"]


@pytest.mark.asyncio
async def test_decide_scene_cg_allows_non_generation_decision() -> None:
    provider = cast(
        Any,
        SimpleNamespace(
            chat=AsyncMock(
                return_value=SimpleNamespace(
                    content='{"should_generate":false,"scene_transition":"closed"}'
                )
            )
        ),
    )

    decision = await decide_scene_cg(
        provider,
        model="qwen-flash",
        decision_input=SceneCgDecisionInput(
            role_name="Mira",
            role_prompt="role",
            user_message="早上好",
        ),
    )

    assert decision.should_generate is False
    assert decision.scene_transition == "closed"


@pytest.mark.asyncio
async def test_decide_scene_cg_rejects_unknown_scene_transition() -> None:
    provider = cast(
        Any,
        SimpleNamespace(
            chat=AsyncMock(
                return_value=SimpleNamespace(
                    content='{"should_generate":false,"scene_transition":"other"}'
                )
            )
        ),
    )

    with pytest.raises(ValueError, match="scene_transition"):
        await decide_scene_cg(
            provider,
            model="qwen-flash",
            decision_input=SceneCgDecisionInput(
                role_name="Mira",
                role_prompt="role",
                user_message="message",
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "error"),
    [
        ("not-json", "合法 JSON"),
        ('{"should_generate":"yes"}', "布尔 should_generate"),
        (
            '{"should_generate":true,"scene_key":"rain",'
            '"prompt":"雨中的少女","negative_prompt":"",'
            '"size_preset":"portrait"}',
            "仅支持英文 NovelAI tags",
        ),
    ],
)
async def test_decide_scene_cg_rejects_invalid_model_output(
    content: str,
    error: str,
) -> None:
    provider = cast(
        Any,
        SimpleNamespace(chat=AsyncMock(return_value=SimpleNamespace(content=content))),
    )

    with pytest.raises(ValueError, match=error):
        await decide_scene_cg(
            provider,
            model="qwen-flash",
            decision_input=SceneCgDecisionInput(
                role_name="Mira",
                role_prompt="role",
                user_message="message",
            ),
        )
