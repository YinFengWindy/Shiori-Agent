"""Validation and serialization for plugin-owned role semantic memory reads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from shiori_sdk.memory.build import MemoryRoles


def require_memory_role(role_store: MemoryRoles, payload: dict[str, Any]) -> str:
    """Require a persisted role for every semantic list and detail request."""
    role_id = str(payload.get("role_id") or "").strip()
    if not role_id or not role_store.exists(role_id):
        raise ValueError(f"role not found: {role_id}")
    return role_id


SEMANTIC_FILTER_DIMENSIONS: tuple[str, ...] = ("memory_type", "memory_domain", "status")
"""Every structured filter a list request may carry; engines declare a subset."""


def reject_undeclared_filters(
    payload: dict[str, Any], declared: Mapping[str, object]
) -> None:
    """Fail when a request filters on a dimension the engine did not declare.

    ``declared`` is the ``filters`` object the engine returns, so the check
    follows the engine's own declaration instead of a separate block list.
    """
    undeclared = [
        key
        for key in SEMANTIC_FILTER_DIMENSIONS
        if key in payload and key not in declared
    ]
    if undeclared:
        raise ValueError(f"unsupported memory filters: {', '.join(undeclared)}")


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
