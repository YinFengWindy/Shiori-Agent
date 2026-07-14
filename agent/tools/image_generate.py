from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from agent.tools.base import Tool
from core.integrations.novelai.models import GenerateImageRequest
from core.integrations.novelai.service import NovelAIService


class GenerateImageTool(Tool):
    """Generate an image through the NovelAI service and return a structured result."""

    name = "generate_image"
    description = (
        "使用 NovelAI 英文 tags 生成图片。支持 txt2img 和 img2img，"
        "适合角色立绘、场景图和参考图生成。即使用户使用中文描述，"
        "也必须先转换为逗号分隔的英文 NovelAI tags 后再调用。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "逗号分隔的英文 NovelAI 正向 tags。禁止中文和自然语言句子；"
                    "用户使用中文描述时，先在内部转换为英文 tags。"
                ),
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
                "description": "逗号分隔的英文 NovelAI 负向 tags，可选；禁止中文。",
            },
            "strength": {
                "type": "number",
                "description": "img2img 强度，范围 0 到 1。",
                "minimum": 0,
                "maximum": 1,
            },
            "noise": {
                "type": "number",
                "description": "img2img 噪声，范围 0 到 1。",
                "minimum": 0,
                "maximum": 1,
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
            "intent": {
                "type": "string",
                "enum": ["user_requested", "scene_cg"],
                "description": "调用意图：用户主动要求生图，或角色为关键场景生成 CG。",
            },
            "scene_key": {
                "type": "string",
                "description": "自动场景 CG 的简短场景标识；intent=scene_cg 时必填。",
            },
        },
        "required": ["prompt", "mode"],
    }

    def __init__(
        self,
        service: NovelAIService,
        *,
        context_provider: Callable[[], dict[str, str]] | None = None,
    ) -> None:
        self._service = service
        self._context_provider = context_provider or (lambda: {})

    async def execute(self, **kwargs: Any) -> str:
        intent = str(kwargs.get("intent") or "user_requested").strip()
        if intent not in {"user_requested", "scene_cg"}:
            raise ValueError("intent 必须是 user_requested 或 scene_cg")
        scene_key = str(kwargs.get("scene_key") or "").strip()
        if intent == "scene_cg" and not scene_key:
            raise ValueError("scene_cg 请求必须提供 scene_key")
        request = GenerateImageRequest(
            prompt=str(kwargs.get("prompt") or ""),
            mode=str(kwargs.get("mode") or "txt2img"),  # type: ignore[arg-type]
            negative_prompt=str(kwargs.get("negative_prompt") or ""),
            base_image_path=str(kwargs.get("base_image_path") or ""),
            strength=(
                float(kwargs["strength"])
                if kwargs.get("strength") is not None
                else None
            ),
            noise=(float(kwargs["noise"]) if kwargs.get("noise") is not None else None),
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
            sampler=str(kwargs.get("sampler") or "k_euler_ancestral"),
            model=str(kwargs.get("model") or ""),
            role_id=str(kwargs.get("role_id") or ""),
            session_key=str(kwargs.get("session_key") or ""),
        )
        context = self._context_provider()
        result = await self._service.generate(
            request,
            prompt_tag_match_text=str(context.get("current_user_message") or ""),
        )
        payload = result.to_public_payload()
        payload["intent"] = intent
        payload["scene_key"] = scene_key
        payload["message"] = (
            f"已生成 {len(result.output_paths)} 张图片，"
            f"模型 {result.model}，seed={result.seed}。"
        )
        return json.dumps(payload, ensure_ascii=False)
