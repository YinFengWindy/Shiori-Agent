from __future__ import annotations

import pytest

from core.roles import RoleAggregateService, RoleStore
from session.manager import SessionManager
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
@pytest.mark.parametrize("binding", ["", "selected"])
async def test_role_lifecycle_prepares_local_memory_without_model_calls(
    tmp_path, binding
):
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
    )
    with patch(
        "core.roles.self_seed.LlmRoleSelfSeedGenerator.agenerate",
        new_callable=AsyncMock,
    ) as generate:
        created = await service.create_role_async(
            role_id="mira",
            name="Mira",
            system_prompt="mira",
            runtime_config={"dialogue_model_registration_id": binding},
        )
        await service.open_role_async("mira")
        await service.update_role_async("mira", description="updated")
        generate.assert_not_awaited()
    assert (created.memory_root / "SELF.md").exists()
    assert created.role.memory_init_state["self_seed"]["status"] == "pending"
    assert created.role.runtime_config["dialogue_model_registration_id"] == binding


def test_sync_unavailable_model_initializes_local_memory_without_provider_call(
    tmp_path,
):
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
    )
    with patch(
        "core.roles.self_seed.LlmRoleSelfSeedGenerator.agenerate",
        new_callable=AsyncMock,
    ) as generate:
        created = service.create_role(role_id="mira", name="Mira", system_prompt="mira")
        service.open_role("mira")
        service.update_role("mira", description="updated")
        generate.assert_not_called()
    assert created.role.memory_init_state["self_seed"]["status"] == "pending"


@pytest.mark.asyncio
async def test_profile_edits_preserve_user_self_content(tmp_path):
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
    )
    aggregate = await service.create_role_async(
        role_id="mira",
        name="Mira",
        system_prompt="旧规则",
        background="旧背景",
        profile={
            "character": {
                "profile": "{{char}}的新资料",
                "response_constraints": "回答简洁",
            }
        },
    )
    self_path = aggregate.memory_root / "SELF.md"
    self_path.write_text("# 我是谁\n\n自己编辑的内容\n", encoding="utf-8")
    saved_self = self_path.read_text(encoding="utf-8")
    history_path = aggregate.memory_root / "HISTORY.md"
    saved_history = history_path.read_text(encoding="utf-8")

    await service.update_role_async(
        "mira", profile={"character": {"profile": "再次更新的资料"}}
    )
    await service.open_role_async("mira")

    assert self_path.read_text(encoding="utf-8") == saved_self
    assert history_path.read_text(encoding="utf-8") == saved_history


def test_role_deletion_requires_a_lifecycle_listener(tmp_path) -> None:
    store = RoleStore(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=store,
        session_manager=SessionManager(tmp_path),
    )
    service.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="You are Mira.",
    )

    with pytest.raises(RuntimeError, match="角色删除生命周期监听器"):
        service.delete_role("mira")

    assert store.get_role("mira") is not None


def test_role_deletion_listener_can_be_removed(tmp_path) -> None:
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
    )
    deleted_role_ids: list[str] = []
    service.add_role_deleted_listener(deleted_role_ids.append)
    service.remove_role_deleted_listener(deleted_role_ids.append)
    service.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="You are Mira.",
    )

    with pytest.raises(RuntimeError, match="角色删除生命周期监听器"):
        service.delete_role("mira")

    assert deleted_role_ids == []


def test_sync_role_creation_persists_the_structured_profile(tmp_path) -> None:
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
    )

    aggregate = service.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="Legacy fallback.",
        profile={
            "character": {
                "profile": "A careful archivist.",
                "personality": "Quiet and precise.",
                "behavior_rules": "Answer from the archive.",
            }
        },
    )

    assert aggregate.role.profile.character.profile == "A careful archivist."
    assert aggregate.role.profile.character.personality == "Quiet and precise."


@pytest.mark.parametrize(
    ("runtime_config", "expected"),
    [
        (None, "default-model"),
        ({"nsfw_memory_enabled": True}, "default-model"),
        ({"dialogue_model_registration_id": ""}, ""),
        ({"dialogue_model_registration_id": "chosen"}, "chosen"),
    ],
)
def test_new_roles_bind_the_default_model_unless_the_caller_chose(
    tmp_path, runtime_config, expected
):
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
        default_dialogue_registration_id="default-model",
    )
    created = service.create_role(
        role_id="mira", name="Mira", system_prompt="mira", runtime_config=runtime_config
    )
    assert created.role.runtime_config["dialogue_model_registration_id"] == expected
    assert created.role.runtime_config["visual_model_registration_id"] == ""


def test_new_roles_stay_unbound_without_a_default_model(tmp_path):
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
    )
    created = service.create_role(role_id="mira", name="Mira", system_prompt="mira")
    assert created.role.runtime_config["dialogue_model_registration_id"] == ""
