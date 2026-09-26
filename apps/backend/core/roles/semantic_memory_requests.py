"""Validation and serialization for plugin-owned role semantic memory reads."""

from __future__ import annotations

from typing import Any

from .store import RoleStore


def require_memory_role(role_store: RoleStore, payload: dict[str, Any]) -> str:
    """Require a persisted role for every semantic list and detail request."""
    role_id = str(payload.get("role_id") or "").strip()
    if not role_id or role_store.get_role(role_id) is None:
        raise ValueError(f"role not found: {role_id}")
    return role_id


def page_options(payload: dict[str, Any]) -> tuple[int, int, str, str]:
    """Bound pagination and time sorting accepted from a plugin Dashboard."""
    page = max(1, int(payload.get("page") or 1))
    page_size = max(1, min(100, int(payload.get("page_size") or 20)))
    sort_by = str(payload.get("sort_by") or "created_at")
    if sort_by not in {"created_at", "updated_at", "happened_at"}:
        raise ValueError("invalid time sort")
    sort_order = str(payload.get("sort_order") or "desc")
    if sort_order not in {"asc", "desc"}:
        raise ValueError("invalid sort order")
    return page, page_size, sort_by, sort_order


def readable_item(item: dict[str, object]) -> dict[str, object]:
    """Drop vector and hash fields from the read-only Dashboard response."""
    visible = {
        key: value
        for key, value in item.items()
        if key not in {"embedding", "embedding_dim", "content_hash", "has_embedding"}
    }
    extra = visible.get("extra_json")
    if isinstance(extra, dict):
        visible["extra_json"] = {
            key: value
            for key, value in extra.items()
            if key not in {"embedding", "embedding_dim", "content_hash"}
        }
    return visible
