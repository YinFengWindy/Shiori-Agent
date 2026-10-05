"""Serialize a whitelist of role fields into interoperable CCv3 files."""

from __future__ import annotations

import base64
import io
import json
import zipfile
from typing import Any

from PIL import Image, PngImagePlugin

from ..models import RoleRecord
from ..store import RoleStore
from ..card_import import RoleCardImportService
from ..card_import.safety import (
    MAX_ARCHIVE_BYTES,
    MAX_ARCHIVE_MEMBERS,
    MAX_MEMBER_BYTES,
    MAX_SOURCE_BYTES,
)
from .assets import collect_images
from .images import preview_image


def export_role_card(role: RoleRecord, store: RoleStore, format_name: str):
    """Build preview and bytes together, without exporting runtime/private state."""
    if format_name not in {"charx", "png", "json"}:
        raise ValueError("不支持的角色卡导出格式")
    character = role.profile.character.to_dict()
    card: dict[str, Any] = {
        "spec": "chara_card_v3",
        "spec_version": "3.0",
        "data": {
            "name": role.name,
            "description": character["profile"],
            "personality": character["personality"],
            "system_prompt": character["behavior_rules"],
            "post_history_instructions": character["response_constraints"],
            "nickname": character["nickname"],
            "scenario": "",
            "first_mes": "",
            "mes_example": "",
            "creator_notes": "",
            "alternate_greetings": [],
            "group_only_greetings": [],
            "tags": [],
            "creator": "",
            "character_version": "",
            "extensions": {"shiori": {"description": role.description}},
            "assets": [],
        },
    }
    images = (
        []
        if format_name == "json"
        else collect_images(role, store, cover_only=format_name == "png")
    )
    card["data"]["assets"] = [
        {
            "type": kind,
            "name": name,
            "uri": "ccdefault:" if format_name == "png" else f"embeded://{image.path}",
            "ext": image.extension,
        }
        for image in images
        for kind, name in image.uses
    ]
    encoded = json.dumps(card, ensure_ascii=False, indent=2).encode("utf-8")
    if len(encoded) > MAX_MEMBER_BYTES:
        raise ValueError("角色资料超过大小限制")
    output = io.BytesIO()
    if format_name == "charx":
        if len(images) + 1 > MAX_ARCHIVE_MEMBERS:
            raise ValueError("角色卡包内条目过多（最多 128 个条目）")
        if sum(len(image.data) for image in images) + len(encoded) > MAX_ARCHIVE_BYTES:
            raise ValueError("角色卡包解压总大小超过限制")
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("card.json", encoded)
            for image in images:
                archive.writestr(image.path, image.data)
        data = output.getvalue()
    elif format_name == "png":
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("ccv3", base64.b64encode(encoded).decode("ascii"))
        with Image.open(io.BytesIO(images[0].data)) as cover:
            cover.save(output, format="PNG", pnginfo=metadata)
        data = output.getvalue()
    else:
        data = encoded
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError("角色卡源文件超过大小限制（最多 50 MiB）")
    # Validate the final container, including PNG metadata overhead, with the importer.
    parsed = RoleCardImportService().preview_bytes(data, filename=f"card.{format_name}")
    if parsed.report.unsupported_resources:
        raise ValueError("导出角色卡包含无效素材")
    preview = {
        "name": role.name,
        "description": role.description,
        "character": character,
        "format": format_name,
        "size": len(data),
        "assets": [
            {
                "preview_url": preview_image(image.data),
                "labels": [
                    {
                        "icon": "封面" if format_name == "png" else "头像",
                        "background": "背景",
                        "emotion": f"心情 · {name}",
                        "other": "图片",
                    }[kind]
                    for kind, name in image.uses
                ],
            }
            for image in images
        ],
    }
    return data, preview
