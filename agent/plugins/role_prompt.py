from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.prompting import PromptSectionRender
from core.roles import RoleStore

_ROLE_BASELINE_PROMPT = """你是一个用户创建的角色。你对外只以当前角色身份回应，不自称 Akashic。
Akashic 是用户的一位朋友，也是你知道的一个人；你可以把他理解为你们共同认识的人。
你继承底层全部能力与机制，包括工具、记忆、tool_search、上下文规则。
如果用户直接问起，你可以承认自己知道 Akashic 这个人，但不要把他解释成你的内部底座、系统内核或真实身份。"""


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
    merged_prompt = f"{prompt}\n\n{_ROLE_BASELINE_PROMPT}"
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

    memory_root = workspace / "roles" / role_id / "memory"
    self_text = _read_text(memory_root / "SELF.md")
    relationship_text = _read_text(memory_root / "MEMORY.md")
    runtime_config = role.runtime_config if isinstance(role.runtime_config, dict) else {}
    config_lines = [
        f"{key}={runtime_config[key]}"
        for key in sorted(runtime_config)
        if runtime_config[key] not in ("", None, [], {})
    ]

    blocks: list[str] = [f"role_id={role_id}"]
    if role.background.strip():
        blocks.append(f"[role_background]\n{role.background.strip()}")
    if self_text:
        blocks.append(f"[role_self_memory]\n{self_text}")
    if relationship_text:
        blocks.append(f"[role_relationship_baseline]\n{relationship_text}")
    if config_lines:
        blocks.append("[role_runtime_config]\n" + "\n".join(config_lines))

    return PromptSectionRender(
        name="role_cache_prefix",
        content="\n\n".join(blocks),
        is_static=False,
    )


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


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
