"""Affection: relationship, loneliness and the affection state files."""

from __future__ import annotations

from typing import Any

from shiori_sdk.core.affection import AFFECTION
from shiori_sdk.core.affection_host import AFFECTION_HOST
from shiori_sdk.core.services import BACKGROUND
from shiori_sdk.runtime import PluginRuntimeContext

from .relationship.loops import LonelinessHeartbeatLoop
from .relationship.service import RoleRelationshipRuntimeService

_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100


class AffectionApi:
    """Plugin RPC the affection page calls."""

    def __init__(self, runtime: RoleRelationshipRuntimeService) -> None:
        self._runtime = runtime

    def history(self, payload: dict[str, Any]) -> dict[str, Any]:
        """One newest-first page plus the current summary."""
        role_id = str(payload.get("role_id") or "").strip()
        if self._runtime.sources.get_role(role_id) is None:
            raise ValueError(f"role not found: {role_id}")
        page = max(1, int(payload.get("page") or 1))
        page_size = max(
            1, min(_MAX_PAGE_SIZE, int(payload.get("page_size") or _DEFAULT_PAGE_SIZE))
        )
        summary = self._runtime.affection.current_summary(role_id)
        entries, total = self._runtime.affection.history_page(
            role_id, page=page, page_size=page_size
        )
        return {
            "role_id": role_id,
            "affection": summary,
            "items": [{"id": id_, **entry.to_dict()} for id_, entry in entries],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def chat_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        """The chat sidebar's summary, relationship tags and loneliness."""
        role_id = str(payload.get("role_id") or "").strip()
        if self._runtime.sources.get_role(role_id) is None:
            raise ValueError(f"role not found: {role_id}")
        return self._runtime.chat_status(role_id)

    def stage_prompts_get(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Each stage's injected guidance."""
        role_id = str(payload.get("role_id") or "").strip()
        if self._runtime.sources.get_role(role_id) is None:
            raise ValueError(f"role not found: {role_id}")
        return {"role_id": role_id, "stages": self._runtime.stage_prompts_view(role_id)}

    def stage_prompts_set(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Writes named stages and answers with every stage as stored."""
        changes = payload.get("prompts")
        if not isinstance(changes, dict):
            raise ValueError("prompts 必须是以阶段名为键的对象")
        role_id = str(payload.get("role_id") or "").strip()
        self._runtime.apply_stage_prompts(role_id, changes)
        return {"role_id": role_id, "stages": self._runtime.stage_prompts_view(role_id)}


async def setup(ctx: PluginRuntimeContext) -> None:
    """Provides ``AFFECTION`` and starts the loneliness heartbeat."""
    runtime = RoleRelationshipRuntimeService(ctx.require(AFFECTION_HOST))
    ctx.provide(AFFECTION, runtime)
    ctx.expose(AffectionApi(runtime))
    loop = LonelinessHeartbeatLoop(runtime)
    task = ctx.require(BACKGROUND).spawn(loop.run(), name="loneliness")

    def stop() -> None:
        loop.stop()
        task.cancel()

    ctx.effect("affection.loneliness", stop)
