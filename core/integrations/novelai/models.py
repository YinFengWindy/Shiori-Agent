from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

NovelAIMode = Literal["txt2img", "img2img"]
NovelAISizePreset = Literal["square", "landscape", "portrait", "custom"]


@dataclass(frozen=True)
class NovelAISettings:
    """Runtime settings for the NovelAI image generation integration."""

    enabled: bool = False
    token: str = ""
    base_url: str = "https://image.novelai.net"
    default_model: str = "nai-diffusion-4-5-full"
    allow_txt2img: bool = True
    allow_img2img: bool = True
    auto_writeback_role_assets: bool = False
    max_pixels: int = 1024 * 1024
    max_steps: int = 28
    default_samples: int = 1


@dataclass(frozen=True)
class GenerateImageRequest:
    """Validated request accepted by the NovelAI generation service."""

    prompt: str
    mode: NovelAIMode = "txt2img"
    negative_prompt: str = ""
    base_image_path: str = ""
    size_preset: NovelAISizePreset = "square"
    custom_width: int | None = None
    custom_height: int | None = None
    steps: int | None = None
    seed: int | None = None
    sampler: str = "k_euler"
    model: str = ""
    role_id: str = ""
    session_key: str = ""

    def to_record_payload(self) -> dict[str, Any]:
        """Return a JSON-serializable request snapshot for persistence."""

        return asdict(self)


@dataclass(frozen=True)
class GenerateImageResult:
    """Output produced by a successful NovelAI generation request."""

    record_id: str
    created_at: str
    mode: NovelAIMode
    model: str
    seed: int | None
    width: int
    height: int
    output_paths: list[str]
    request_path: str
    meta_path: str
    wrote_back_to_role: bool = False
    role_asset_paths: list[str] = field(default_factory=list)

    def to_public_payload(self) -> dict[str, Any]:
        """Return the tool-facing payload."""

        return asdict(self)


@dataclass(frozen=True)
class GeneratedImageRecord:
    """Persistent metadata written for each generated NovelAI image record."""

    id: str
    created_at: str
    role_id: str
    session_key: str
    mode: NovelAIMode
    prompt: str
    negative_prompt: str
    model: str
    sampler: str
    steps: int
    seed: int | None
    width: int
    height: int
    base_image_path: str
    output_paths: list[str]
    wrote_back_to_role: bool
    role_asset_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the record for JSON persistence."""

        return asdict(self)
