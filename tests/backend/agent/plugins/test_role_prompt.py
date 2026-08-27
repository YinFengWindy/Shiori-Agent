from __future__ import annotations

import pytest

from agent.plugins.role_prompt import (
    build_role_cache_prefix_section,
    build_role_system_section,
)
from core.roles import RoleStore


def _create_role_workspace(tmp_path):
    role = RoleStore(tmp_path).create_role(
        role_id="mira",
        name="Mira",
        system_prompt="你是 Mira。",
        background="角色背景",
        runtime_config={"dialogue_model_effort": "high"},
    )
    memory_root = tmp_path / "roles" / role.id / "memory"
    memory_root.mkdir(parents=True)
    (memory_root / "SELF.md").write_text("角色自我记忆", encoding="utf-8")
    (memory_root / "MEMORY.md").write_text("角色关系记忆", encoding="utf-8")
    return {"role_id": role.id}


def test_role_system_section_contains_only_role_prompt_and_mood_contract(
    tmp_path,
) -> None:
    metadata = _create_role_workspace(tmp_path)

    section = build_role_system_section(
        workspace=tmp_path,
        session_metadata=metadata,
    )

    assert section is not None
    assert "你是 Mira。" in section.content
    assert "Akashic" not in section.content
    assert "用户创建的角色" not in section.content


def test_role_cache_prefix_does_not_duplicate_memory_sections(tmp_path) -> None:
    metadata = _create_role_workspace(tmp_path)

    section = build_role_cache_prefix_section(
        workspace=tmp_path,
        session_metadata=metadata,
    )

    assert section is not None
    assert "role_id=mira" in section.content
    assert "[role_background]\n角色背景" in section.content
    assert "dialogue_model_effort=high" in section.content
    assert "角色自我记忆" not in section.content
    assert "角色关系记忆" not in section.content
    assert "role_self_memory" not in section.content
    assert "role_relationship_baseline" not in section.content


def test_role_system_section_rejects_missing_role_context(tmp_path) -> None:
    with pytest.raises(ValueError, match="role_id required"):
        build_role_system_section(
            workspace=tmp_path,
            session_metadata=None,
        )
