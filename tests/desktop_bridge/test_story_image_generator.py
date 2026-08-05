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
        resource={"id": "resource-1", "prompt": "old school building, afternoon"},
    )

    assert path == "D:\\stories\\opening.png"
    assert tool.calls[0]["intent"] == "scene_cg"
    assert tool.calls[0]["scene_key"] == "story:story-1:visual:resource-1"
    assert tool.calls[0]["size_preset"] == "landscape"
    assert tool.calls[0]["model"] == "nai-diffusion-4-5-full"
    assert "anime background" in tool.calls[0]["prompt"]
    assert "person" in tool.calls[0]["negative_prompt"]


@pytest.mark.asyncio
async def test_uses_character_prompt_without_a_scene_character_exclusion() -> None:
    tool = RecordingImageTool({"output_paths": ["D:\\stories\\character.png"]})
    generator = StoryImageGenerator(tool)

    await generator.generate(
        story={"id": "story-1", "roleSnapshot": {"id": "role-1"}},
        resource={
            "id": "resource-1",
            "visualType": "character",
            "prompt": "girl handing umbrella, emotional close-up",
        },
    )

    assert "visual novel CG" in tool.calls[0]["prompt"]
    assert "person" not in tool.calls[0]["negative_prompt"]
    assert tool.calls[0]["model"] == "nai-diffusion-4-5-full"


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
