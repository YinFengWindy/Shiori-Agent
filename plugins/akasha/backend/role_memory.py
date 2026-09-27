"""Akasha plugin's role-scoped semantic Dashboard RPCs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.roles.semantic_memory_requests import (
    page_options,
    readable_item,
    reject_undeclared_filters,
    require_memory_role,
)
from desktop_bridge.method_policy import Concurrency

if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext

# Every node is a turn with no domain or lifecycle status, so Akasha declares no
# structured filters; requests may only search and sort.
_DECLARED_FILTERS: dict[str, list[str]] = {}


class AkashaRoleMemoryReader:
    """Expose only one persisted role's Akasha turn nodes."""

    def __init__(self, role_store: Any, engine: Any) -> None:
        self._role_store = role_store
        self._engine = engine

    async def list(self, payload: dict[str, Any]) -> dict[str, object]:
        """Search and page role-owned turn nodes without unsupported filters."""
        role_id = require_memory_role(self._role_store, payload)
        if self._engine is None:
            return {"role_id": role_id, "status": "disabled", "items": [], "total": 0}
        page, page_size, sort_order = page_options(payload)
        reject_undeclared_filters(payload, _DECLARED_FILTERS)
        items, total = self._engine.list_items_for_admin(
            role_id=role_id,
            q=str(payload.get("q") or "").strip(),
            page=page,
            page_size=page_size,
            # Turn nodes always carry their source message time (first_ts_unix).
            sort_by="happened_at",
            sort_order=sort_order,
        )
        return {
            "role_id": role_id,
            "status": "ready",
            "items": [_dashboard_item(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "filters": dict(_DECLARED_FILTERS),
        }

    async def detail(self, payload: dict[str, Any]) -> dict[str, object]:
        """Read a node through Akasha's role-filtered store lookup."""
        role_id = require_memory_role(self._role_store, payload)
        if self._engine is None:
            return {"role_id": role_id, "status": "disabled", "item": None}
        item_id = str(payload.get("item_id") or "").strip()
        if not item_id:
            raise ValueError("item_id required")
        item = self._engine.get_role_item_for_admin(item_id, role_id=role_id)
        if item is None:
            raise ValueError("memory item not found")
        return {"role_id": role_id, "status": "ready", "item": _dashboard_item(item)}


def _dashboard_item(item: dict[str, object]) -> dict[str, object]:
    """Keep Akasha's generic admin status out of its role Dashboard."""
    visible = readable_item(item)
    visible.pop("status", None)
    return visible


def register_role_semantic_memory(ctx: PluginRuntimeContext) -> None:
    """Register Akasha reads in this plugin's RPC namespace."""
    engine = ctx.memory_engine
    if engine is not None and engine.describe().name != "akasha":
        engine = None
    reader = AkashaRoleMemoryReader(ctx.role_store, engine)
    ctx.rpc.register(
        "roles.memory.semantic.list", reader.list, concurrency=Concurrency.READ_ONLY
    )
    ctx.rpc.register(
        "roles.memory.semantic.detail", reader.detail, concurrency=Concurrency.READ_ONLY
    )
