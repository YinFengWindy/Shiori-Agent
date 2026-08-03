"""Story-owned image generation through the registered NovelAI plugin tool."""

from __future__ import annotations

import json
from typing import Any

from story_simulation.errors import StoryInvalidOutputError, StoryProviderUnavailableError


class StoryImageGenerator:
    """Adapt the plugin's ``generate_image`` tool to the Story resource contract."""

    def __init__(self, image_tool: Any | None) -> None:
        self._image_tool = image_tool

    async def generate(self, *, story: dict[str, Any], resource: dict[str, Any]) -> str:
        if self._image_tool is None:
            raise StoryProviderUnavailableError("NovelAI generate_image 工具未注册")
        prompt = str(resource.get("prompt") or "").strip()
        if not prompt or not prompt.isascii():
            raise StoryInvalidOutputError("开场背景缺少有效的英文 NovelAI tags")
        result = await self._image_tool.execute(
            prompt=(
                f"{prompt}, anime screencap, visual novel background, wide composition, "
                "cinematic lighting"
            ),
            mode="txt2img",
            negative_prompt="text, logo, watermark, signature, user interface, border",
            size_preset="landscape",
            role_id=str((story.get("roleSnapshot") or {}).get("id") or ""),
            session_key=f"story:{story.get('id', '')}",
            intent="scene_cg",
            scene_key=f"story:{story.get('id', '')}:opening",
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
