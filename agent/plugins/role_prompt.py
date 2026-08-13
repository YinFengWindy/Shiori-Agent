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
    runtime_config = role.runtime_config if isinstance(role.runtime_config, dict) else {}
    mood_contract = _build_role_mood_output_contract(runtime_config)
    merged_prompt = prompt
    if mood_contract:
        merged_prompt += f"\n\n{mood_contract}"

    return PromptSectionRender(
        name="active_role",
        content=f"## Active Role: {role_name}\n{merged_prompt}",
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

    runtime_config = role.runtime_config if isinstance(role.runtime_config, dict) else {}
    config_lines = [
        f"{key}={runtime_config[key]}"
        for key in sorted(runtime_config)
        if runtime_config[key] not in ("", None, [], {})
    ]

    blocks: list[str] = [f"role_id={role_id}"]
    if role.background.strip():
        blocks.append(f"[role_background]\n{role.background.strip()}")
    if config_lines:
        blocks.append("[role_runtime_config]\n" + "\n".join(config_lines))

    return PromptSectionRender(
        name="role_cache_prefix",
        content="\n\n".join(blocks),
        is_static=False,
    )
def _build_role_mood_output_contract(runtime_config: dict[str, Any]) -> str:
    raw_mood_catalog = runtime_config.get("mood_catalog")
    if not isinstance(raw_mood_catalog, list):
        return ""
    mood_catalog = [str(item).strip() for item in raw_mood_catalog if str(item).strip()]
    if not mood_catalog:
        return ""
    default_mood = str(runtime_config.get("default_mood") or "").strip() or mood_catalog[0]
    mood_list_text = "、".join(mood_catalog)
    return (
        "## Mood Output Contract\n"
        "你每次回复都必须输出一个 JSON 对象，不要输出 JSON 之外的解释、markdown 或代码块。\n"
        'JSON 结构固定为：{"content":"<角色回复正文>","mood":"<当前心情>"}\n'
        f"`mood` 只能从以下列表中选择一个：{mood_list_text}。\n"
        f"如果难以判断，请使用默认心情：{default_mood}。"
    )
