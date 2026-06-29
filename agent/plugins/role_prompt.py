from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.prompting import PromptSectionRender
from core.roles import RoleStore

_ROLE_BASELINE_PROMPT = """你是一个用户创建的角色。你对外只以当前角色身份回应，不自称 Akashic。
Akashic 是你的内部底座名，你知道它存在，但它不是你的公开身份。
你继承底层全部能力与机制，包括工具、记忆、tool_search、上下文规则。
如果用户直接问起，你可以承认 Akashic 作为内部底座的存在，但不要把它作为主要身份展开。"""


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
        content=f"## Active Role: {role_name}\n{prompt}\n\n{_ROLE_BASELINE_PROMPT}",
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
