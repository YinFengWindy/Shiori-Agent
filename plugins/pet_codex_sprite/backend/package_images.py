"""Codex spritesheet and preview validation."""

from __future__ import annotations

import io
from PIL import Image

_ATLAS_SIZE = (1536, 1872)
_CELL_SIZE = (192, 208)
_USED_CELLS = (6, 8, 8, 4, 5, 8, 6, 6, 6)


def validate_atlas(data: bytes) -> None:
    """Requires every animation frame and transparency in unused sprite cells."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "WEBP" or image.size != _ATLAS_SIZE:
                raise ValueError("桌宠精灵图必须是 1536 x 1872 WebP")
            alpha = image.convert("RGBA").getchannel("A")
    except OSError as error:
        raise ValueError("桌宠精灵图无效") from error
    for row, count in enumerate(_USED_CELLS):
        for column in range(8):
            occupied = (
                alpha.crop(
                    (
                        column * _CELL_SIZE[0],
                        row * _CELL_SIZE[1],
                        (column + 1) * _CELL_SIZE[0],
                        (row + 1) * _CELL_SIZE[1],
                    )
                ).getbbox()
                is not None
            )
            if column < count and not occupied:
                raise ValueError("桌宠精灵图缺少必需动画帧")
            if column >= count and occupied:
                raise ValueError("桌宠精灵图未使用单元必须透明")


def validate_preview(data: bytes) -> str:
    """Validates a preview image and returns its canonical extension."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {"PNG", "WEBP"}:
                raise ValueError("桌宠预览图必须是 PNG 或 WebP")
            extension = ".png" if image.format == "PNG" else ".webp"
            width, height = image.size
    except OSError as error:
        raise ValueError("桌宠预览图无效") from error
    if not 64 <= width <= 2048 or not 64 <= height <= 2048:
        raise ValueError("桌宠预览图尺寸必须在 64 到 2048 像素之间")
    return extension
