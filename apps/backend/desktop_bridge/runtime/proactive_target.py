"""Bridge handler previewing where a role's next proactive message would go."""

from __future__ import annotations

from typing import Any

from core.roles.models import RoleProactiveCandidate
from core.roles.store import RoleStore
from proactive_v2.target_selection import ProactiveTargetResolver


def preview_proactive_target(
    roles: RoleStore, resolver: ProactiveTargetResolver, payload: dict[str, Any]
) -> dict[str, dict[str, str] | None]:
    """Selects among the given, possibly unsaved, candidates of an existing role.

    Uses the same resolver as proactive delivery, so the renderer never
    re-implements the rule. ``target`` is ``None`` when no candidate is given.
    """
    role_id = str(payload.get("role_id") or "").strip()
    if roles.get_role(role_id) is None:
        raise KeyError(f"角色不存在: {role_id}")
    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list):
        raise ValueError("candidates 必须是数组")
    candidates = [RoleProactiveCandidate.from_dict(item) for item in raw_candidates]
    if not candidates:
        return {"target": None}
    return {"target": resolver.resolve(role_id, candidates).to_dict()}
