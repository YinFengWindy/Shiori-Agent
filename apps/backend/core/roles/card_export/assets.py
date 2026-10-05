"""Read only role-owned images and select portable visual declarations."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageDraw

from ..models import RoleRecord
from ..store import RoleStore
from ..card_import.safety import (
    MAX_MEMBER_BYTES,
    MAX_ARCHIVE_BYTES,
    MAX_ARCHIVE_MEMBERS,
)
from .images import png_image, portable_image


@dataclass(frozen=True)
class ExportImage:
    """One deduplicated image and the semantic uses represented by it."""

    path: str
    data: bytes
    uses: tuple[tuple[str, str], ...]
    extension: str = "png"


def collect_images(role: RoleRecord, store: RoleStore, *, cover_only: bool):
    """Select the avatar/card cover or all images, checking role ownership first."""
    bindings = role.runtime_config.get("mood_illustration_bindings")
    bindings = bindings if isinstance(bindings, dict) else {}
    default = str(role.runtime_config.get("default_mood") or "").strip()
    cover = bindings.get(default)
    cover = cover if isinstance(cover, str) and cover in role.illustrations else None
    if cover_only:
        selected = role.avatar or cover or role.chat_background
        declarations = [(selected, "icon", "main")] if selected else []
    else:
        declarations = [
            (role.avatar, "icon", "main"),
            (role.chat_background, "background", "main"),
            *[
                (path, "emotion", name)
                for name, path in bindings.items()
                if isinstance(name, str) and name.strip() and path in role.illustrations
            ],
        ]
        represented = {path for path, _, _ in declarations}
        declarations.extend(
            (path, "other", f"image-{index + 1}")
            for index, path in enumerate(role.illustrations)
            if path not in represented
        )
    images: dict[str, ExportImage] = {}
    paths: dict[str, tuple[bytes, str]] = {}
    total_bytes = 0
    for source, kind, name in declarations:
        if not source:
            continue
        if source not in paths:
            resolved = store.resolve_role_asset_path(role.id, source)
            if resolved is None or not resolved.is_file():
                raise ValueError("角色素材缺失或不属于该角色，请修复素材后重试")
            if resolved.stat().st_size > MAX_MEMBER_BYTES:
                raise ValueError("角色素材超过大小限制（单张最多 25 MiB）")
            raw = resolved.read_bytes()
            paths[source] = (
                (png_image(raw), "png") if cover_only else portable_image(raw)
            )
        data, extension = paths[source]
        digest = hashlib.sha256(data).hexdigest()
        previous = images.get(digest)
        if previous is None:
            total_bytes += len(data)
            if len(images) + 2 > MAX_ARCHIVE_MEMBERS:
                raise ValueError("角色卡包内条目过多（最多 128 个条目）")
            if total_bytes > MAX_ARCHIVE_BYTES:
                raise ValueError("角色卡包解压总大小超过限制")
        use = (kind, name)
        images[digest] = ExportImage(
            path=(
                previous.path
                if previous
                else f"assets/{kind}/images/{digest}.{extension}"
            ),
            data=data,
            extension=extension,
            uses=(
                (*previous.uses, use)
                if previous and use not in previous.uses
                else (previous.uses if previous else (use,))
            ),
        )
    if cover_only and not images:
        # A neutral, explicit image cover also works on systems without CJK fonts.
        image = Image.new("RGB", (480, 600), "#f4f1f5")
        draw = ImageDraw.Draw(image)
        draw.text((180, 280), "NO IMAGE", fill="#514a59", font_size=24)
        output = io.BytesIO()
        image.save(output, format="PNG")
        return [ExportImage("cover.png", output.getvalue(), (("icon", "main"),))]
    return list(images.values())
