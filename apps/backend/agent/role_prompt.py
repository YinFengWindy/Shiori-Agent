from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.prompting import PromptSectionRender
from core.roles import RoleStore
from core.roles.role_macros import expand_role_macros
from core.roles.role_prompt_compiler import RolePromptCompiler


def build_role_system_section(
    *,
    workspace: Path,
    session_metadata: dict[str, Any] | None,
    current_message: str = "",
) -> PromptSectionRender | None:
    """Render the active role for a user-visible turn."""
    metadata = session_metadata if isinstance(session_metadata, dict) else {}
    role_id = str(metadata.get("role_id") or "").strip()
    if not role_id:
        raise ValueError("role_id required for user-visible prompt")

    role = RoleStore(workspace).get_role(role_id)
    if role is None:
        raise ValueError(f"role not found for user-visible prompt: {role_id}")

    role_name = role.name.strip() or role_id
    prompt = (
        RolePromptCompiler()
        .compile(
            role,
            runtime_context=role.runtime_config,
            user_name=str(metadata.get("user_name") or ""),
        )
        .content.strip()
    )
    if not prompt:
        raise ValueError(f"role.system_prompt required: {role_id}")
    return PromptSectionRender(
        name="active_role",
        content=f"## Active Role: {role_name}\n{prompt}",
        is_static=False,
    )


def build_role_cache_prefix_section(
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

    runtime_config = (
        role.runtime_config if isinstance(role.runtime_config, dict) else {}
    )
    config_lines = [
        f"{key}={runtime_config[key]}"
        for key in sorted(runtime_config)
        if runtime_config[key] not in ("", None, [], {})
    ]

    blocks: list[str] = [f"role_id={role_id}"]
    background = expand_role_macros(
        role.profile.character.profile.strip(),
        role_name=role.name or role.id,
        nickname=role.profile.character.nickname,
        user_name=str(metadata.get("user_name") or ""),
    )
    if background:
        blocks.append(f"[role_background]\n{background}")
    if config_lines:
        blocks.append("[role_runtime_config]\n" + "\n".join(config_lines))

    return PromptSectionRender(
        name="role_cache_prefix",
        content="\n\n".join(blocks),
        is_static=False,
    )
