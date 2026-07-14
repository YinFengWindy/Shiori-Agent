from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from agent.tools.image_generate import GenerateImageTool
from core.integrations.novelai.models import GenerateImageResult


def test_generate_image_tool_requires_english_novelai_tags() -> None:
    prompt_description = GenerateImageTool.parameters["properties"]["prompt"][
        "description"
    ]
    negative_description = GenerateImageTool.parameters["properties"][
        "negative_prompt"
    ]["description"]

    assert "英文 NovelAI" in GenerateImageTool.description
    assert "逗号分隔" in prompt_description
    assert "禁止中文" in prompt_description
    assert "禁止中文" in negative_description


@pytest.mark.asyncio
async def test_generate_image_tool_defaults_to_user_requested_intent() -> None:
    service = cast(
        Any,
        SimpleNamespace(
            generate=AsyncMock(
                return_value=GenerateImageResult(
                    record_id="record",
                    created_at="2026-07-12T00:00:00+00:00",
                    mode="txt2img",
                    model="model",
                    seed=1,
                    width=1024,
                    height=1024,
                    output_paths=["output.png"],
                    request_path="request.json",
                    meta_path="meta.json",
                )
            )
        ),
    )
    tool = GenerateImageTool(service)

    payload = json.loads(await tool.execute(prompt="scene", mode="txt2img"))

    assert payload["intent"] == "user_requested"
    assert payload["scene_key"] == ""
    request = service.generate.await_args.args[0]
    assert request.prompt == "scene"
    assert service.generate.await_args.kwargs["prompt_tag_match_text"] == ""


@pytest.mark.asyncio
async def test_generate_image_tool_uses_runtime_user_message_for_tag_matching() -> None:
    service = cast(
        Any,
        SimpleNamespace(
            generate=AsyncMock(
                return_value=GenerateImageResult(
                    record_id="record",
                    created_at="2026-07-12T00:00:00+00:00",
                    mode="txt2img",
                    model="model",
                    seed=1,
                    width=1024,
                    height=1024,
                    output_paths=["output.png"],
                    request_path="request.json",
                    meta_path="meta.json",
                )
            )
        ),
    )
    tool = GenerateImageTool(
        service,
        context_provider=lambda: {"current_user_message": "给我画一张雨景"},
    )

    await tool.execute(
        prompt="1girl, rainy atmosphere",
        mode="txt2img",
        current_user_message="模型伪造的消息",
    )

    assert (
        service.generate.await_args.kwargs["prompt_tag_match_text"]
        == "给我画一张雨景"
    )


@pytest.mark.asyncio
async def test_generate_image_tool_requires_scene_key_for_auto_cg() -> None:
    service = cast(Any, SimpleNamespace(generate=AsyncMock()))
    tool = GenerateImageTool(service)

    with pytest.raises(ValueError, match="scene_key"):
        await tool.execute(prompt="scene", mode="txt2img", intent="scene_cg")

    service.generate.assert_not_awaited()
