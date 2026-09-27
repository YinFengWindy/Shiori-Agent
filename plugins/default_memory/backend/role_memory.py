"""Default memory plugin's role-scoped semantic Dashboard RPCs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.roles.semantic_memory_requests import (
    SEMANTIC_STATUS_FILTERS,
    page_options,
    readable_item,
    reject_undeclared_filters,
    require_memory_role,
)
from desktop_bridge.method_policy import Concurrency

if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext


class DefaultRoleMemoryReader:
    """Expose only one persisted role's default-engine admin reads."""

    def __init__(self, role_store: Any, engine: Any) -> None:
        self._role_store = role_store
        self._engine = engine

    async def list(self, payload: dict[str, Any]) -> dict[str, object]:
        """Search and page one role's semantic items in the owning engine."""
        role_id = require_memory_role(self._role_store, payload)
        if self._engine is None:
            return {"role_id": role_id, "status": "disabled", "items": [], "total": 0}
        page, page_size, sort_order = page_options(payload)
        # Types and domains come from this role's data; status is an engine trait.
        filters: dict[str, list[str]] = {
            **self._engine.list_role_filter_values(role_id),
            "status": list(SEMANTIC_STATUS_FILTERS),
        }
        reject_undeclared_filters(payload, filters)
        status = str(payload.get("status") or "active")
        if status not in SEMANTIC_STATUS_FILTERS:
            raise ValueError("invalid memory status")
        items, total = self._engine.list_items_for_admin(
            role_id=role_id,
            q=str(payload.get("q") or "").strip(),
            memory_type=str(payload.get("memory_type") or "").strip(),
            memory_domain=str(payload.get("memory_domain") or "").strip(),
            status="" if status == "all" else status,
            page=page,
            page_size=page_size,
            sort_by="occurred_at",
            sort_order=sort_order,
        )
        return {
            "role_id": role_id,
            "status": "ready",
            "items": [readable_item(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "filters": filters,
        }

    async def detail(self, payload: dict[str, Any]) -> dict[str, object]:
        """Reject cross-role item IDs, even when the ID is known to the caller."""
        role_id = require_memory_role(self._role_store, payload)
        if self._engine is None:
            return {"role_id": role_id, "status": "disabled", "item": None}
        item_id = str(payload.get("item_id") or "").strip()
        if not item_id:
            raise ValueError("item_id required")
        item = self._engine.get_item_for_admin(item_id, include_embedding=False)
        if item is None or item.get("role_id") != role_id:
            raise ValueError("memory item not found")
        return {"role_id": role_id, "status": "ready", "item": readable_item(item)}


def register_role_semantic_memory(ctx: PluginRuntimeContext) -> None:
    """Register default-engine reads in this plugin's RPC namespace."""
    engine = ctx.memory_engine
    if engine is not None and engine.describe().name != "default":
        engine = None
    reader = DefaultRoleMemoryReader(ctx.role_store, engine)
    ctx.rpc.register(
        "roles.memory.semantic.list", reader.list, concurrency=Concurrency.READ_ONLY
    )
    ctx.rpc.register(
        "roles.memory.semantic.detail", reader.detail, concurrency=Concurrency.READ_ONLY
    )
