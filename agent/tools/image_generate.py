from __future__ import annotations

import json
from typing import Any

from agent.tools.base import Tool
from core.integrations.novelai.models import GenerateImageRequest
from core.integrations.novelai.service import NovelAIService


class GenerateImageTool(Tool):
    """Generate an image through the NovelAI service and return a structured result."""

    name = "generate_image"
    description = (
        "使用 NovelAI 生成图片。支持 txt2img 和 img2img，"
        "适合角色立绘、场景图和参考图生成。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "正向提示词，描述想生成的画面内容。",
            },
            "mode": {
                "type": "string",
                "enum": ["txt2img", "img2img"],
                "description": "生成模式：txt2img 为文生图，img2img 为图生图。",
            },
            "base_image_path": {
                "type": "string",
                "description": "img2img 模式下的输入图片路径。",
            },
            "negative_prompt": {
                "type": "string",
                "description": "负向提示词，可选。",
            },
            "size_preset": {
                "type": "string",
                "enum": ["square", "landscape", "portrait", "custom"],
                "description": "尺寸预设。",
            },
            "custom_width": {
                "type": "integer",
                "description": "自定义宽度，仅 size_preset=custom 时使用。",
                "minimum": 1,
            },
            "custom_height": {
                "type": "integer",
                "description": "自定义高度，仅 size_preset=custom 时使用。",
                "minimum": 1,
            },
            "steps": {
                "type": "integer",
                "description": "采样步数。",
                "minimum": 1,
            },
            "seed": {
                "type": "integer",
                "description": "随机种子，可选。",
            },
            "sampler": {
                "type": "string",
                "description": "采样器名称，可选。",
            },
            "model": {
                "type": "string",
                "description": "模型名，默认使用全局配置。",
            },
        },
        "required": ["prompt", "mode"],
    }

    def __init__(self, service: NovelAIService) -> None:
        self._service = service

    async def execute(self, **kwargs: Any) -> str:
        request = GenerateImageRequest(
            prompt=str(kwargs.get("prompt") or ""),
            mode=str(kwargs.get("mode") or "txt2img"),  # type: ignore[arg-type]
            negative_prompt=str(kwargs.get("negative_prompt") or ""),
            base_image_path=str(kwargs.get("base_image_path") or ""),
            size_preset=str(kwargs.get("size_preset") or "square"),  # type: ignore[arg-type]
            custom_width=(
                int(kwargs["custom_width"])
                if kwargs.get("custom_width") is not None
                else None
            ),
            custom_height=(
                int(kwargs["custom_height"])
                if kwargs.get("custom_height") is not None
                else None
            ),
            steps=int(kwargs["steps"]) if kwargs.get("steps") is not None else None,
            seed=int(kwargs["seed"]) if kwargs.get("seed") is not None else None,
            sampler=str(kwargs.get("sampler") or "k_euler"),
            model=str(kwargs.get("model") or ""),
            role_id=str(kwargs.get("role_id") or ""),
            session_key=str(kwargs.get("session_key") or ""),
        )
        result = await self._service.generate(request)
        payload = result.to_public_payload()
        payload["message"] = (
            f"已生成 {len(result.output_paths)} 张图片，"
            f"模型 {result.model}，seed={result.seed}。"
        )
        return json.dumps(payload, ensure_ascii=False)
