from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.prompting import PromptSectionRender
from core.roles import RoleStore


def build_role_system_section(
    *,
    workspace: Path,
    session_metadata: dict[str, Any] | None,
) -> PromptSectionRender | None:
    metadata = session_metadata if isinstance(session_metadata, dict) else {}
    role_id = str(metadata.get("role_id") or "").strip()
    if not role_id:
        return None

    role = RoleStore(workspace).get_role(role_id)
    if role is None:
        return None

    role_name = role.name.strip() or role_id
    prompt = role.system_prompt.strip()
    if not prompt:
        return None

    return PromptSectionRender(
        name="active_role",
        content=f"## Active Role: {role_name}\n{prompt}",
        is_static=False,
    )
