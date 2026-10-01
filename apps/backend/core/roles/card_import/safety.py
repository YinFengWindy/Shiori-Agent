"""Security limits shared by character-card adapters."""

from __future__ import annotations

import io
from pathlib import PurePosixPath

from PIL import Image

MAX_SOURCE_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 128
MAX_ARCHIVE_BYTES = 200 * 1024 * 1024
MAX_MEMBER_BYTES = 25 * 1024 * 1024
SUPPORTED_IMAGE_FORMATS = frozenset({"PNG", "JPEG", "WEBP", "GIF"})


def safe_archive_path(value: str) -> str:
    """Return a normalized relative path or reject traversal and absolute paths."""
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or path == PurePosixPath(".")
        or ".." in path.parts
    ):
        raise ValueError("角色卡压缩包路径不安全")
    if any(not part or part == "." for part in path.parts):
        raise ValueError("角色卡压缩包路径不安全")
    return path.as_posix()


def validate_image(data: bytes, *, name: str = "角色卡素材") -> tuple[str, str]:
    """Validate image bytes and return ``(format, media_type)``."""
    if len(data) > MAX_MEMBER_BYTES:
        raise ValueError(
            f"{name}超过大小限制（单条目最多 {MAX_MEMBER_BYTES // (1024 * 1024)} MiB）"
        )
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
            image_format = image.format
    except (OSError, ValueError) as error:
        raise ValueError(f"{name}无效") from error
    if image_format not in SUPPORTED_IMAGE_FORMATS:
        raise ValueError(f"{name}格式不支持: {image_format}")
    media_type = Image.MIME.get(image_format, "application/octet-stream")
    return image_format, media_type
