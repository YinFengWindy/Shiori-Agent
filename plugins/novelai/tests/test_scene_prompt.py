import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.provider import LLMResponse, ToolCall
from bus.events_lifecycle import SceneObservationCommitted
from plugins.novelai.backend.scene_prompt import prepare_scene_prompt


def _event():
    return SceneObservationCommitted(
        "role:mira",
        "desktop",
        "role:mira",
        "mira",
        "passive",
        "started",
        visual_description="少女坐在车站长椅上",
        role_description="粉发少女",
        assistant_reply="她坐下休息",
    )


@pytest.mark.asyncio
async def test_prompt_model_uses_only_frozen_scene_and_validates_provider_parameters():
    payload = dict(
        prompt="1girl, pink hair, sitting, station",
        negative_prompt="blurry",
        size_preset="landscape",
    )
    provider = SimpleNamespace(
        chat=AsyncMock(
            return_value=LLMResponse(
                content="",
                tool_calls=[ToolCall("cg", "submit_scene_image_prompt", payload)],
            )
        )
    )
    assert (
        await prepare_scene_prompt(provider, model="configured-light", event=_event())
        == payload
    )
    call = provider.chat.await_args.kwargs
    assert call["model"] == "configured-light"
    assert call["call_purpose"] == "auxiliary"
    assert call["max_tokens"] == 600
    snapshot = json.loads(call["messages"][1]["content"])
    assert snapshot["visual_description"] == "少女坐在车站长椅上"
    assert snapshot["role_description"] == "粉发少女"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        dict(prompt="中文标签", negative_prompt="", size_preset="portrait"),
        dict(prompt="1girl", negative_prompt="", size_preset="huge"),
        dict(prompt="1girl"),
    ],
)
async def test_invalid_provider_prompt_is_visible_failure(payload):
    provider = SimpleNamespace(
        chat=AsyncMock(
            return_value=LLMResponse(
                content="",
                tool_calls=[ToolCall("cg", "submit_scene_image_prompt", payload)],
            )
        )
    )
    with pytest.raises(ValueError):
        await prepare_scene_prompt(provider, model="light", event=_event())
