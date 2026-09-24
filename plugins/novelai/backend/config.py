from __future__ import annotations

from pydantic import BaseModel, Field


class NovelAIConfig(BaseModel):
    """``[plugins.novelai]`` config schema: validated via ``plugin.config.*``.

    Field names and defaults mirror ``NovelAISettings`` (the frozen dataclass
    the runtime service actually consumes) exactly, so ``setup()`` can build a
    ``NovelAISettings`` straight off this model's ``model_dump()`` without a
    second, drift-prone copy of the defaults. ``title`` / ``unit`` only feed
    the desktop's schema-generated settings form.
    """

    # enabled 属于宿主插件管理；配置表单只声明生图参数，避免覆盖启停状态。
    token: str = Field(default="", title="API Token")
    base_url: str = Field(default="https://image.novelai.net", title="服务地址")
    default_model: str = Field(default="nai-diffusion-4-5-curated", title="默认模型")
    nsfw_model: str = Field(default="nai-diffusion-4-5-full", title="NSFW 模型")
    nsfw_enabled: bool = Field(default=False, title="允许 NSFW")
    allow_txt2img: bool = Field(default=True, title="允许文生图")
    allow_img2img: bool = Field(default=True, title="允许图生图")
    auto_writeback_role_assets: bool = Field(
        default=False, title="生成结果自动存入角色素材"
    )
    max_pixels: int = Field(
        default=1024 * 1024, title="单张像素上限", json_schema_extra={"unit": "像素"}
    )
    max_steps: int = Field(
        default=28, title="采样步数上限", json_schema_extra={"unit": "步"}
    )
    default_samples: int = Field(
        default=1, title="默认生成张数", json_schema_extra={"unit": "张"}
    )
    add_quality_tags: bool = Field(default=False, title="自动添加质量标签")
    undesired_content_preset: int = Field(default=0, title="负面内容预设")
