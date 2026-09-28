"""Account avatars: small inline images the renderer can show under its CSP.

The desktop renderer only loads ``'self' data: blob:`` images, so an account
avatar is a base64 ``data:`` URI of a recognised image, never a remote URL.
An empty string is the well-defined "no avatar" value.
"""

from __future__ import annotations

import base64
import binascii
import re

# Decoded bytes; a platform avatar thumbnail is a few KiB to a few dozen KiB.
MAX_AVATAR_BYTES = 256 * 1024

_DATA_URI = re.compile(r"data:(image/[a-z]+);base64,([A-Za-z0-9+/]*={0,2})")


def _image_mime(content: bytes) -> str | None:
    """The MIME type the content's signature identifies, if a supported image."""
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def avatar_data_uri(content: bytes) -> str:
    """Encodes downloaded avatar bytes as the ``data:`` URI accounts carry.

    Raises ValueError for content that is not a PNG, JPEG, GIF or WebP image
    or exceeds ``MAX_AVATAR_BYTES``, so nothing unusable is stored.
    """
    if len(content) > MAX_AVATAR_BYTES:
        raise ValueError(f"账号头像超过 {MAX_AVATAR_BYTES // 1024} KiB")
    mime = _image_mime(content)
    if mime is None:
        raise ValueError("账号头像不是 PNG、JPEG、GIF 或 WebP 图片")
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


def validate_avatar(avatar: str) -> str:
    """Returns ``avatar`` if it is empty or a valid image data URI.

    The host boundary: a plugin passing a remote URL, a non-image, a MIME type
    that does not match the content, or an oversize image gets ValueError.
    """
    if avatar == "":
        return avatar
    match = _DATA_URI.fullmatch(avatar)
    if match is None:
        raise ValueError("账号头像必须是 base64 编码的 data:image URI")
    try:
        content = base64.b64decode(match.group(2), validate=True)
    except binascii.Error as exc:
        raise ValueError("账号头像的 base64 数据无效") from exc
    # Enforces the size cap and a supported image signature.
    avatar_data_uri(content)
    if _image_mime(content) != match.group(1):
        raise ValueError("账号头像的类型与图片内容不符")
    return avatar
