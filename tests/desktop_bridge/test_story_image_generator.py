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
    assert "empty scene" in tool.calls[0]["prompt"]
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
    assert "1girl, solo" in tool.calls[0]["prompt"]
    assert "multiple people" in tool.calls[0]["negative_prompt"]
    assert "person" not in tool.calls[0]["negative_prompt"]
    assert tool.calls[0]["model"] == "nai-diffusion-4-5-full"


@pytest.mark.asyncio
async def test_scene_prompt_removes_character_tags_before_generation() -> None:
    tool = RecordingImageTool({"output_paths": ["D:\\stories\\scene.png"]})
    generator = StoryImageGenerator(tool)

    await generator.generate(
        story={"id": "story-1", "roleSnapshot": {"id": "role-1"}},
        resource={
            "id": "resource-1",
            "prompt": "warm living room, young woman feeding man, soft lamplight",
        },
    )

    assert "warm living room" in tool.calls[0]["prompt"]
    assert "young woman feeding man" not in tool.calls[0]["prompt"]


@pytest.mark.asyncio
async def test_character_prompt_keeps_the_player_without_extra_people() -> None:
    tool = RecordingImageTool({"output_paths": ["D:\\stories\\pair.png"]})
    generator = StoryImageGenerator(tool)

    await generator.generate(
        story={
            "id": "story-1",
            "roleSnapshot": {"id": "role-1"},
            "playerProfile": {"appearance": "暖棕色头发、黑色眼睛、圆脸"},
        },
        resource={
            "id": "resource-1",
            "visualType": "character",
            "prompt": "girl feeding man, warm living room",
        },
    )

    assert "young woman" not in tool.calls[0]["prompt"]
    assert "feeding man" not in tool.calls[0]["prompt"]
    assert "1girl, 1boy, duo" in tool.calls[0]["prompt"]
    assert "{{girl feeding boy}}" in tool.calls[0]["prompt"]
    assert "{{girl holding spoon}}" in tool.calls[0]["prompt"]
    assert "boy receiving food" in tool.calls[0]["prompt"]
    assert "warm brown hair" in tool.calls[0]["prompt"]
    assert "black eyes" in tool.calls[0]["prompt"]
    assert "round face" in tool.calls[0]["prompt"]
    assert "暖棕色头发" not in tool.calls[0]["prompt"]
    assert "boy feeding girl" in tool.calls[0]["negative_prompt"]


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
