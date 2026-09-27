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


SEMANTIC_STATUS_FILTERS: tuple[str, ...] = ("active", "superseded", "all")
"""Status filter values an engine declares when it can filter by item status."""


def page_options(payload: dict[str, Any]) -> tuple[int, int, str]:
    """Bound pagination and the single supported sort of a plugin Dashboard.

    Items always sort by occurrence time, falling back to record time when an
    item has none; ``sort_order`` only picks newest (``desc``) or oldest
    (``asc``). A ``sort_by`` field is rejected so an outdated caller fails
    instead of silently receiving a different order than it asked for.
    """
    if "sort_by" in payload:
        raise ValueError("sort_by is not supported; items sort by occurrence time")
    page = max(1, int(payload.get("page") or 1))
    page_size = max(1, min(100, int(payload.get("page_size") or 20)))
    sort_order = str(payload.get("sort_order") or "desc")
    if sort_order not in {"asc", "desc"}:
        raise ValueError("invalid sort order")
    return page, page_size, sort_order


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
