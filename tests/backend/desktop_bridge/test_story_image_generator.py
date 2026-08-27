from __future__ import annotations

import json

import pytest

from desktop_bridge.story_image_generator import StoryImageGenerator
from story_simulation.errors import StoryInvalidOutputError


class RecordingImageTool:
    def __init__(self, result: dict) -> None:
        self.calls: list[dict] = []
        self._result = result

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return json.dumps(self._result)


@pytest.mark.asyncio
async def test_uses_registered_plugin_tool_for_story_scene_cg() -> None:
    tool = RecordingImageTool({"output_paths": ["D:\\stories\\opening.png"]})
    generator = StoryImageGenerator(tool)

    path = await generator.generate(
        story={"id": "story-1", "roleSnapshot": {"id": "role-1"}},
        resource={
            "id": "resource-1",
            "prompt": "white background, old school building, afternoon",
        },
    )

    assert path == "D:\\stories\\opening.png"
    assert tool.calls[0]["intent"] == "scene_cg"
    assert tool.calls[0]["scene_key"] == "story:story-1:visual:resource-1"
    assert tool.calls[0]["size_preset"] == "landscape"
    assert tool.calls[0]["model"] == "nai-diffusion-4-5-full"
    assert tool.calls[0]["prompt"] == "white background, old school building, afternoon"
    assert tool.calls[0]["negative_prompt"] == ""


@pytest.mark.asyncio
async def test_passes_a_model_ready_character_prompt_without_rewriting_it() -> None:
    tool = RecordingImageTool({"output_paths": ["D:\\stories\\character.png"]})
    generator = StoryImageGenerator(tool)

    await generator.generate(
        story={"id": "story-1", "roleSnapshot": {"id": "role-1"}},
        resource={
            "id": "resource-1",
            "visualType": "character",
            "prompt": "white background, 1girl, solo, girl, holding umbrella, emotional close-up",
        },
    )

    assert tool.calls[0]["prompt"] == "white background, 1girl, solo, girl, holding umbrella, emotional close-up"
    assert tool.calls[0]["negative_prompt"] == ""
    assert tool.calls[0]["model"] == "nai-diffusion-4-5-full"


@pytest.mark.asyncio
async def test_passes_a_model_ready_scene_prompt_without_removing_tags() -> None:
    tool = RecordingImageTool({"output_paths": ["D:\\stories\\scene.png"]})
    generator = StoryImageGenerator(tool)

    await generator.generate(
        story={"id": "story-1", "roleSnapshot": {"id": "role-1"}},
        resource={
            "id": "resource-1",
            "prompt": "white background, warm living room, young woman feeding man, soft lamplight",
        },
    )

    assert tool.calls[0]["prompt"] == "white background, warm living room, young woman feeding man, soft lamplight"


@pytest.mark.asyncio
async def test_passes_player_appearance_tags_from_the_model_without_injection() -> None:
    tool = RecordingImageTool({"output_paths": ["D:\\stories\\pair.png"]})
    generator = StoryImageGenerator(tool)
    resource_prompt = "white background, 1girl, 1boy, duo, {{girl feeding boy}}, {{girl holding spoon}}, boy receiving food, warm brown hair, black eyes, round face, warm living room"

    await generator.generate(
        story={
            "id": "story-1",
            "roleSnapshot": {"id": "role-1"},
            "playerProfile": {"appearance": "warm brown hair, black eyes, round face"},
        },
        resource={
            "id": "resource-1",
            "visualType": "character",
            "prompt": resource_prompt,
        },
    )

    assert tool.calls[0]["prompt"] == resource_prompt
    assert tool.calls[0]["negative_prompt"] == ""


@pytest.mark.asyncio
async def test_rejects_non_ascii_prompt_before_calling_plugin_tool() -> None:
    tool = RecordingImageTool({"output_paths": ["D:\\stories\\opening.png"]})
    generator = StoryImageGenerator(tool)

    with pytest.raises(StoryInvalidOutputError, match="NovelAI tags"):
        await generator.generate(
            story={"id": "story-1", "roleSnapshot": {}},
            resource={"prompt": "午后的旧校舍"},
        )
    assert tool.calls == []
