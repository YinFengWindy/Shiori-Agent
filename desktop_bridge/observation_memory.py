from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from core.memory.engine import MemoryMutation, MemoryScope, MemoryWriteApi
from core.roles import RoleStore
from desktop_bridge.observation_safety import safe_observation_text


class ObservationMemoryWriter:
    """Persists one filtered shared-experience event through the common memory API."""

    def __init__(self, *, role_store: RoleStore, memory: MemoryWriteApi) -> None:
        self._role_store = role_store
        self._memory = memory

    async def remember(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validates and writes a settled observation episode."""

        role_id = str(payload.get("role_id") or "").strip()
        self._role_store.get_required(role_id)
        summary = safe_observation_text(payload.get("summary"), limit=280)
        if not summary:
            raise ValueError("观察经历摘要为空或包含敏感内容")
        source_ref = str(payload.get("source_ref") or "").strip()
        if not re.fullmatch(
            r"desktop-observation:[A-Za-z0-9-]{1,128}:\d{1,6}", source_ref
        ):
            raise ValueError("观察经历 source_ref 无效")
        happened_at = str(payload.get("happened_at") or "").strip()
        try:
            datetime.fromisoformat(happened_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("观察经历时间无效") from exc
        result = await self._memory.mutate(
            MemoryMutation(
                kind="remember",
                scope=MemoryScope(role_id=role_id),
                summary=summary,
                memory_kind="event",
                memory_domain="relationship",
                source_ref=source_ref,
                happened_at=happened_at,
            )
        )
        if not result.accepted:
            raise RuntimeError("观察经历未被记忆引擎接受")
        return {
            "item_id": result.item_id,
            "status": result.status,
            "memory_kind": result.actual_kind,
        }
