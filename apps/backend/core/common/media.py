from __future__ import annotations

import io
from pathlib import Path
from typing import BinaryIO

from PIL import Image


def detect_image_mime_from_header(header: bytes) -> str | None:
    """Returns the MIME type for supported raster image signatures."""

    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if header.startswith(b"BM"):
        return "image/bmp"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    return None


def write_png_thumbnail(
    data: bytes,
    target: Path | BinaryIO,
    size: int,
    *,
    formats: tuple[str, ...] | None = None,
) -> None:
    """把图片字节解码后等比缩到不超过 ``size`` × ``size``，以 PNG 写入 ``target``。

    ``formats`` 限定可接受的 Pillow 格式名（如 ``("PNG", "JPEG")``），None 为不限。
    无法解码、格式不在 ``formats`` 内或像素数超过 Pillow 的解压炸弹上限时抛
    ``ValueError``，不写入；写入 ``target`` 的错误原样抛出。动图只取第一帧。
    """
    try:
        with Image.open(io.BytesIO(data), formats=formats) as image:
            thumbnail = image.convert("RGBA")
        thumbnail.thumbnail((size, size))
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise ValueError("图片无法解码") from error
    with thumbnail:
        thumbnail.save(target, format="PNG")
