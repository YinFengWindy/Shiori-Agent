"""Story-owned image generation through the registered NovelAI plugin tool."""

from __future__ import annotations

import json
from typing import Any

from story_simulation.errors import StoryInvalidOutputError, StoryProviderUnavailableError

_STORY_CG_MODEL = "nai-diffusion-4-5-full"
_BASE_NEGATIVE_PROMPT = "text, logo, watermark, signature, user interface, border"
_SCENE_PERSON_MARKERS = (
    "girl", "boy", "woman", "man", "person", "people", "human", "character",
    "couple", "group", "crowd", "feeding", "hug", "kiss", "embrace",
)
_PLAYER_MARKERS = (
    "player", "protagonist", "main character", "you", "man", "boy", "male", "1boy",
)


def prompt_mentions_people(prompt: str) -> bool:
    """Return whether a visual prompt explicitly describes a person."""

    normalized = prompt.casefold()
    return any(marker in normalized for marker in _SCENE_PERSON_MARKERS)


def _scene_prompt(prompt: str) -> str:
    """Keep environment tags while removing person-bearing comma tags."""

    tags = [tag.strip() for tag in prompt.split(",") if tag.strip()]
    kept = [
        tag
        for tag in tags
        if not any(marker in tag.casefold() for marker in _SCENE_PERSON_MARKERS)
    ]
    return ", ".join(kept) or "empty scene"


def _character_prompt_constraints(prompt: str) -> tuple[str, str]:
    """Describe the allowed role/player count without excluding a valid player."""

    has_player = any(marker in prompt.casefold() for marker in _PLAYER_MARKERS)
    if has_player:
        positive = "two characters, the described role and player only, exactly two people"
        negative = "duplicate, clone, twin, extra characters, unrelated characters, group, crowd, 2girls"
    else:
        positive = "solo, single character, exactly one character"
        negative = "multiple characters, duplicate, clone, twin, extra characters, group, crowd, 2girls, 2boys"
    return positive, negative


class StoryImageGenerator:
    """Adapt the plugin's ``generate_image`` tool to the Story resource contract."""

    def __init__(self, image_tool: Any | None) -> None:
        self._image_tool = image_tool

    async def generate(self, *, story: dict[str, Any], resource: dict[str, Any]) -> str:
        if self._image_tool is None:
            raise StoryProviderUnavailableError("NovelAI generate_image 工具未注册")
        prompt = str(resource.get("prompt") or "").strip()
        if not prompt or not prompt.isascii():
            raise StoryInvalidOutputError("视觉资源缺少有效的英文 NovelAI tags")
        visual_type = str(resource.get("visualType") or "scene").strip()
        if visual_type not in {"scene", "character"}:
            raise StoryInvalidOutputError("视觉资源缺少有效的视觉类型")
        if visual_type == "character":
            positive_constraints, negative_constraints = _character_prompt_constraints(prompt)
            generation_prompt = (
                f"{prompt}, anime screencap, visual novel CG, character-focused composition, "
                f"{positive_constraints}, cinematic lighting"
            )
            negative_prompt = f"{_BASE_NEGATIVE_PROMPT}, {negative_constraints}"
        else:
            scene_prompt = _scene_prompt(prompt)
            generation_prompt = (
                f"{scene_prompt}, empty scene, no characters, no people, no human figures, "
                "anime background, visual novel background, wide composition, cinematic lighting"
            )
            negative_prompt = (
                f"{_BASE_NEGATIVE_PROMPT}, person, people, human, character, 1girl, 1boy"
            )
        result = await self._image_tool.execute(
            prompt=generation_prompt,
            mode="txt2img",
            negative_prompt=negative_prompt,
            size_preset="landscape",
            model=_STORY_CG_MODEL,
            role_id=str((story.get("roleSnapshot") or {}).get("id") or ""),
            session_key=f"story:{story.get('id', '')}",
            intent="scene_cg",
            scene_key=f"story:{story.get('id', '')}:visual:{resource.get('id', '')}",
        )
        raw = str(getattr(result, "text", result) or "").strip()
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise StoryInvalidOutputError("NovelAI 工具未返回图片路径") from exc
        paths = payload.get("output_paths") if isinstance(payload, dict) else None
        if not isinstance(paths, list):
            raise StoryInvalidOutputError("NovelAI 工具返回的图片路径无效")
        path = next((str(item).strip() for item in paths if str(item).strip()), "")
        if not path:
            raise StoryInvalidOutputError("NovelAI 工具未返回图片路径")
        return path
