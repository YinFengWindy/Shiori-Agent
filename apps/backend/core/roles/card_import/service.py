"""Unified role-card preview service."""

from __future__ import annotations

import json
from pathlib import Path

from .charx_adapter import adapt_charx, adapt_charx_bytes
from .json_adapter import adapt_json
from .models import RoleCardImportPreview
from .png_adapter import adapt_png, adapt_png_bytes
from .safety import MAX_SOURCE_BYTES


class RoleCardImportService:
    """Parse supported card formats without creating roles or copying assets."""

    def preview(self, source: str | Path) -> RoleCardImportPreview:
        path = Path(source).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"角色卡不存在: {path}")
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError(
                f"角色卡源文件超过大小限制（最多 {MAX_SOURCE_BYTES // (1024 * 1024)} MiB）"
            )
        suffix = path.suffix.casefold()
        if suffix == ".json":
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("角色卡 JSON 无效") from error
            return adapt_json(payload, source_name=path.name)
        if suffix in {".png", ".apng"}:
            return adapt_png(path)
        if suffix == ".charx":
            return adapt_charx(path)
        raise ValueError("不支持的角色卡格式")

    def preview_bytes(self, data: bytes, *, filename: str) -> RoleCardImportPreview:
        """Write no files: parse bytes through the same bounded adapters."""
        if len(data) > MAX_SOURCE_BYTES:
            raise ValueError(
                f"角色卡源文件超过大小限制（最多 {MAX_SOURCE_BYTES // (1024 * 1024)} MiB）"
            )
        suffix = Path(filename).suffix.casefold()
        if suffix == ".json":
            try:
                payload = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("角色卡 JSON 无效") from error
            return adapt_json(payload, source_name=filename)
        if suffix in {".png", ".apng"}:
            return adapt_png_bytes(data, source_name=filename)
        if suffix == ".charx":
            return adapt_charx_bytes(data)
        raise ValueError("不支持的角色卡格式")
