"""Retain bounded, immutable export snapshots until the desktop saves or closes."""

from __future__ import annotations

import base64
import asyncio
import uuid
from typing import Any

from core.roles import RoleStore
from core.roles.card_export import export_role_card


class DesktopRoleCardExportService:
    """Own export snapshot IDs; never accept a renderer supplied filesystem path."""

    def __init__(self, role_store: RoleStore) -> None:
        self._store = role_store
        self._exports: dict[str, tuple[bytes, dict[str, Any]]] = {}

    async def preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Read the selected role once and retain exactly the previewed bytes."""
        role = self._store.get_role(str(payload.get("role_id") or ""))
        if role is None:
            raise ValueError("角色不存在")
        data, preview = await asyncio.to_thread(
            export_role_card, role, self._store, str(payload.get("format"))
        )
        export_id = uuid.uuid4().hex
        # Closed renderers cannot retain unbounded image snapshots.
        while len(self._exports) >= 4:
            self._exports.pop(next(iter(self._exports)))
        self._exports[export_id] = (data, preview)
        return {**preview, "export_id": export_id}

    async def read(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Read an existing snapshot for the main process's native save operation."""
        snapshot = self._exports.get(str(payload.get("export_id") or ""))
        if snapshot is None:
            raise ValueError("导出预览已失效，请重新预览")
        data, preview = snapshot
        return {
            "name": preview["name"],
            "format": preview["format"],
            "data_base64": base64.b64encode(data).decode("ascii"),
        }

    async def release(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Drop a closed or superseded preview without touching source roles."""
        self._exports.pop(str(payload.get("export_id") or ""), None)
        return {"released": True}
