from __future__ import annotations

import json
from pathlib import Path

from datetime import datetime

from bus.events import InboundMessage
from core.roles import (
    RoleAggregateService,
    RoleConfigMigrator,
    RoleRepository,
    RoleStore,
    route_inbound_by_role,
)
from session.manager import SessionManager


def test_role_store_creates_manifest_and_assets_layout(tmp_path: Path):
    store = RoleStore(tmp_path)

    assert (tmp_path / "roles" / "roles.json").exists()
    assert (tmp_path / "roles" / "assets").is_dir()
    assert store.list_roles() == []


def test_role_store_creates_role_and_copies_assets(tmp_path: Path):
    avatar = tmp_path / "avatar.png"
    avatar.write_bytes(b"avatar")
    illustration = tmp_path / "ill-1.png"
    illustration.write_bytes(b"ill")

    store = RoleStore(tmp_path)
    role = store.create_role(
        name="Mira",
        description="assistant role",
        system_prompt="you are mira",
        avatar_source=avatar,
        illustration_sources=[illustration],
    )

    assert role.id.startswith("role-")
    assert role.avatar is not None
    assert role.illustrations
    avatar_path = tmp_path / "roles" / role.avatar
    ill_path = tmp_path / "roles" / role.illustrations[0]
    assert avatar_path.read_bytes() == b"avatar"
    assert ill_path.read_bytes() == b"ill"


def test_role_store_migrates_featured_image_to_chat_background(tmp_path: Path):
    roles_dir = tmp_path / "roles"
    assets_dir = roles_dir / "assets" / "mira"
    assets_dir.mkdir(parents=True, exist_ok=True)
    asset_rel = "assets/mira/illustration-1.png"
    (roles_dir / asset_rel).write_bytes(b"ill")
    manifest = {
        "version": 1,
        "roles": [
            {
                "id": "mira",
                "name": "Mira",
                "description": "assistant role",
                "system_prompt": "you are mira",
                "background": "",
                "avatar": None,
                "featured_image": asset_rel,
                "illustrations": [asset_rel],
                "runtime_config": {},
                "memory_init_state": {},
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ],
    }
    (roles_dir / "roles.json").write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )

    store = RoleStore(tmp_path)
    role = store.get_role("mira")

    assert role is not None
    assert role.chat_background == asset_rel
    payload = json.loads((roles_dir / "roles.json").read_text(encoding="utf-8"))
    assert payload["roles"][0]["chat_background"] == asset_rel
    assert "featured_image" not in payload["roles"][0]


def test_role_store_migrates_existing_assets_into_default_category(tmp_path: Path):
    roles_dir = tmp_path / "roles"
    asset_dir = roles_dir / "assets" / "mira"
    asset_dir.mkdir(parents=True)
    asset_rel = "assets/mira/illustration-1.png"
    (roles_dir / asset_rel).write_bytes(b"ill")
    (roles_dir / "roles.json").write_text(
        json.dumps(
            {
                "version": 1,
                "roles": [
                    {
                        "id": "mira",
                        "name": "Mira",
                        "system_prompt": "you are mira",
                        "illustrations": [asset_rel],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    role = RoleStore(tmp_path).get_role("mira")

    assert role is not None
    assert role.asset_categories[0].id == "default"
    assert role.asset_category_bindings == {asset_rel: "default"}
    payload = json.loads((roles_dir / "roles.json").read_text(encoding="utf-8"))
    assert payload["version"] == 2


def test_role_store_assigns_uploaded_assets_and_moves_between_categories(tmp_path: Path):
    image = tmp_path / "reaction.png"
    image.write_bytes(b"reaction")
    store = RoleStore(tmp_path)
    store.create_role(name="Mira", system_prompt="mira", role_id="mira")
    categories = [
        {"id": "default", "name": "默认", "allow_role_send": False},
        {"id": "reactions", "name": "表情包", "allow_role_send": True},
    ]

    uploaded = store.update_role(
        "mira",
        asset_categories=categories,
        illustration_sources=[image],
        illustration_category_id="reactions",
    )
    asset_path = uploaded.illustrations[0]
    assert uploaded.asset_category_bindings[asset_path] == "reactions"

    moved = store.update_role(
        "mira",
        asset_category_bindings={asset_path: "default"},
    )
    assert moved.asset_category_bindings[asset_path] == "default"


def test_role_store_rejects_removing_category_still_used_by_assets(tmp_path: Path):
    image = tmp_path / "reaction.png"
    image.write_bytes(b"reaction")
    store = RoleStore(tmp_path)
    store.create_role(name="Mira", system_prompt="mira", role_id="mira")
    role = store.update_role(
        "mira",
        asset_categories=[
            {"id": "default", "name": "默认"},
            {"id": "reactions", "name": "表情包", "allow_role_send": True},
        ],
        illustration_sources=[image],
        illustration_category_id="reactions",
    )

    try:
        store.update_role(
            role.id,
            asset_categories=[{"id": "default", "name": "默认"}],
        )
    except ValueError as exc:
        assert "仍被图片使用" in str(exc)
    else:
        raise AssertionError("仍被图片使用的分类不能删除")


def test_role_store_accepts_category_removal_with_reassigned_bindings(tmp_path: Path):
    image = tmp_path / "reaction.png"
    image.write_bytes(b"reaction")
    store = RoleStore(tmp_path)
    store.create_role(name="Mira", system_prompt="mira", role_id="mira")
    role = store.update_role(
        "mira",
        asset_categories=[
            {"id": "default", "name": "默认"},
            {"id": "reactions", "name": "表情包", "allow_role_send": True},
        ],
        illustration_sources=[image],
        illustration_category_id="reactions",
    )
    asset_path = role.illustrations[0]

    updated = store.update_role(
        "mira",
        asset_categories=[{"id": "default", "name": "默认"}],
        asset_category_bindings={asset_path: "default"},
    )

    assert [category.id for category in updated.asset_categories] == ["default"]
    assert updated.asset_category_bindings[asset_path] == "default"


def test_role_store_updates_and_deletes_role(tmp_path: Path):
    store = RoleStore(tmp_path)
    role = store.create_role(
        name="Mira",
        description="assistant role",
        system_prompt="you are mira",
        role_id="mira",
    )

    updated = store.update_role(
        role.id,
        name="Mira Prime",
        system_prompt="you are still mira",
        description="updated",
    )
    assert updated.name == "Mira Prime"
    assert updated.system_prompt == "you are still mira"
    assert updated.description == "updated"
    assert store.get_role("mira") is not None
    assert store.delete_role("mira") is True
    assert store.get_role("mira") is None


def test_role_store_persists_runtime_config_updates(tmp_path: Path):
    store = RoleStore(tmp_path)
    role = store.create_role(
        name="Mira",
        description="assistant role",
        system_prompt="you are mira",
        role_id="mira",
        runtime_config={"nsfw_memory_enabled": False},
    )

    updated = store.update_role(
        role.id,
        runtime_config={"nsfw_memory_enabled": True},
    )

    assert updated.runtime_config["nsfw_memory_enabled"] is True
    reloaded = store.get_role("mira")
    assert reloaded is not None
    assert reloaded.runtime_config["nsfw_memory_enabled"] is True

def test_role_store_keeps_channel_access_and_proactive_target_on_the_role(tmp_path: Path):
    store = RoleStore(tmp_path)
    store.create_role(name="Mira", system_prompt="mira", role_id="mira")
    store.create_role(name="Luna", system_prompt="luna", role_id="luna")

    updated = store.update_role(
        "mira",
        channel_bindings=[
            {"channel": "telegram", "chat_id": "42", "allow_from": ["alice", "42"]},
            {"channel": "qq", "chat_id": "gqq:7", "allow_from": []},
        ],
        proactive={"enabled": True, "target_channel": "qq", "target_chat_id": "gqq:7"},
    )

    assert updated.channel_bindings[0].allow_from == ["42", "alice"]
    assert updated.proactive.target_channel == "qq"
    luna = store.get_role("luna")
    assert luna is not None
    assert luna.channel_bindings == []


def test_role_store_rejects_proactive_target_outside_its_bindings(tmp_path: Path):
    store = RoleStore(tmp_path)
    store.create_role(name="Mira", system_prompt="mira", role_id="mira")

    try:
        store.update_role(
            "mira",
            proactive={"enabled": True, "target_channel": "telegram", "target_chat_id": "42"},
        )
    except ValueError as exc:
        assert "当前角色已绑定" in str(exc)
    else:
        raise AssertionError("主动推送目标必须属于当前角色")


def test_role_store_disables_proactive_when_its_target_binding_is_removed(tmp_path: Path):
    store = RoleStore(tmp_path)
    store.create_role(name="Mira", system_prompt="mira", role_id="mira")
    store.update_role(
        "mira",
        channel_bindings=[{"channel": "telegram", "chat_id": "42", "allow_from": []}],
        proactive={"enabled": True, "target_channel": "telegram", "target_chat_id": "42"},
    )

    updated = store.update_role("mira", channel_bindings=[])

    assert updated.proactive.enabled is False
    assert updated.proactive.target_channel == ""


def test_role_store_rejects_desktop_binding_for_another_role_session(tmp_path: Path):
    store = RoleStore(tmp_path)
    store.create_role(name="Mira", system_prompt="mira", role_id="mira")

    try:
        store.update_role(
            "mira",
            channel_bindings=[{"channel": "desktop", "chat_id": "role:luna", "allow_from": []}],
        )
    except ValueError as exc:
        assert "role:mira" in str(exc)
    else:
        raise AssertionError("桌面端绑定不能指向其他角色会话")


def test_role_store_rejects_allow_list_for_desktop_binding(tmp_path: Path):
    store = RoleStore(tmp_path)
    store.create_role(name="Mira", system_prompt="mira", role_id="mira")

    try:
        store.update_role(
            "mira",
            channel_bindings=[{"channel": "desktop", "chat_id": "role:mira", "allow_from": ["alice"]}],
        )
    except ValueError as exc:
        assert "不支持允许对象" in str(exc)
    else:
        raise AssertionError("桌面端没有外部 sender，不能配置允许对象")


def test_role_config_migration_copies_legacy_file_once_without_runtime_fallback(tmp_path: Path):
    store = RoleStore(tmp_path)
    store.create_role(name="Mira", system_prompt="mira", role_id="mira")
    (tmp_path / "roles" / "channel_bindings.json").write_text(
        json.dumps({"version": 1, "bindings": {"telegram:42": {"channel": "telegram", "chat_id": "42", "role_id": "mira"}}}),
        encoding="utf-8",
    )
    proactive = type("LegacyProactive", (), {"enabled": True, "default_role_id": "mira", "default_channel": "telegram", "default_chat_id": "42"})()

    migrator = RoleConfigMigrator(tmp_path, RoleRepository(store))
    first = migrator.migrate(proactive)
    second = migrator.migrate(proactive)

    role = store.get_role("mira")
    assert first.bindings_migrated == 1
    assert first.proactive_migrated == 1
    assert second.bindings_migrated == 0
    assert second.proactive_migrated == 0
    assert role is not None
    assert role.channel_bindings[0].chat_id == "42"
    assert role.proactive.enabled is True


def test_role_config_migration_does_not_restore_a_removed_legacy_binding(tmp_path: Path):
    store = RoleStore(tmp_path)
    store.create_role(name="Mira", system_prompt="mira", role_id="mira")
    (tmp_path / "roles" / "channel_bindings.json").write_text(
        json.dumps(
            {
                "version": 1,
                "bindings": {
                    "telegram:42": {
                        "channel": "telegram",
                        "chat_id": "42",
                        "role_id": "mira",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    migrator = RoleConfigMigrator(tmp_path, RoleRepository(store))

    _ = migrator.migrate()
    _ = store.update_role("mira", channel_bindings=[])
    second = migrator.migrate()
    role = store.get_role("mira")

    assert second.bindings_migrated == 0
    assert role is not None
    assert role.channel_bindings == []


def test_role_store_delete_role_removes_role_runtime_directory(tmp_path: Path):
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
    )
    aggregate = service.create_role(
        role_id="mira",
        name="Mira",
        description="assistant role",
        system_prompt="you are mira",
    )

    role_dir = tmp_path / "roles" / aggregate.role.id
    assert role_dir.is_dir()
    assert (role_dir / "memory").is_dir()

    assert service.delete_role(aggregate.role.id)[0] is True
    assert not role_dir.exists()


def test_role_store_delete_role_keeps_other_role_runtime_directories(tmp_path: Path):
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
    )
    first = service.create_role(
        role_id="mira",
        name="Mira",
        description="assistant role",
        system_prompt="you are mira",
    )
    second = service.create_role(
        role_id="luna",
        name="Luna",
        description="assistant role",
        system_prompt="you are luna",
    )

    first_dir = tmp_path / "roles" / first.role.id
    second_dir = tmp_path / "roles" / second.role.id
    assert first_dir.is_dir()
    assert second_dir.is_dir()

    assert service.delete_role(first.role.id)[0] is True
    assert not first_dir.exists()
    assert second_dir.is_dir()
    assert (tmp_path / "roles" / "assets").is_dir()


def test_role_store_replaces_and_clears_old_assets(tmp_path: Path):
    avatar1 = tmp_path / "avatar-1.png"
    avatar1.write_bytes(b"avatar-1")
    avatar2 = tmp_path / "avatar-2.png"
    avatar2.write_bytes(b"avatar-2")
    ill1 = tmp_path / "ill-1.png"
    ill1.write_bytes(b"ill-1")

    store = RoleStore(tmp_path)
    role = store.create_role(
        name="Mira",
        description="assistant role",
        system_prompt="you are mira",
        role_id="mira",
        avatar_source=avatar1,
        illustration_sources=[ill1],
    )
    first_avatar = tmp_path / "roles" / role.avatar
    first_illustration = tmp_path / "roles" / role.illustrations[0]
    assert first_avatar.exists()
    assert first_illustration.exists()

    updated = store.update_role(
        "mira",
        avatar_source=avatar2,
        clear_illustrations=True,
    )
    assert updated.avatar is not None
    assert (tmp_path / "roles" / updated.avatar).read_bytes() == b"avatar-2"
    assert not first_avatar.exists()
    assert not first_illustration.exists()

    cleared = store.update_role("mira", clear_avatar=True)
    assert cleared.avatar is None


def test_role_store_removes_selected_illustration_only(tmp_path: Path):
    ill1 = tmp_path / "ill-1.png"
    ill1.write_bytes(b"ill-1")
    ill2 = tmp_path / "ill-2.png"
    ill2.write_bytes(b"ill-2")

    store = RoleStore(tmp_path)
    role = store.create_role(
        name="Mira",
        description="assistant role",
        system_prompt="you are mira",
        role_id="mira",
        illustration_sources=[ill1, ill2],
    )
    first_path = tmp_path / "roles" / role.illustrations[0]
    second_path = tmp_path / "roles" / role.illustrations[1]

    updated = store.update_role(
        "mira",
        removed_illustrations=[role.illustrations[0]],
    )

    assert len(updated.illustrations) == 1
    assert updated.illustrations[0] == role.illustrations[1]
    assert not first_path.exists()
    assert second_path.exists()


def test_role_store_rejects_out_of_root_asset_deletion(tmp_path: Path):
    outside = tmp_path.parent / "role-store-outside.txt"
    outside.write_text("outside", encoding="utf-8")
    store = RoleStore(tmp_path)

    try:
        store._remove_asset_relpath("../../role-store-outside.txt")
    except ValueError as exc:
        assert "路径越界" in str(exc)
    else:
        raise AssertionError("越界素材删除必须失败")

    assert outside.exists()
    outside.unlink()


def test_role_store_can_select_avatar_and_chat_background_from_asset_library(
    tmp_path: Path,
):
    ill1 = tmp_path / "ill-1.png"
    ill1.write_bytes(b"ill-1")
    ill2 = tmp_path / "ill-2.png"
    ill2.write_bytes(b"ill-2")

    store = RoleStore(tmp_path)
    role = store.create_role(
        name="Mira",
        description="assistant role",
        system_prompt="you are mira",
        role_id="mira",
        illustration_sources=[ill1, ill2],
    )

    updated = store.update_role(
        "mira",
        avatar_asset=role.illustrations[0],
        chat_background=role.illustrations[1],
    )

    assert updated.avatar == role.illustrations[0]
    assert updated.chat_background == role.illustrations[1]


def test_role_store_clears_selected_assets_when_underlying_asset_removed(
    tmp_path: Path,
):
    ill1 = tmp_path / "ill-1.png"
    ill1.write_bytes(b"ill-1")
    ill2 = tmp_path / "ill-2.png"
    ill2.write_bytes(b"ill-2")

    store = RoleStore(tmp_path)
    role = store.create_role(
        name="Mira",
        description="assistant role",
        system_prompt="you are mira",
        role_id="mira",
        illustration_sources=[ill1, ill2],
    )
    selected = store.update_role(
        "mira",
        avatar_asset=role.illustrations[0],
        chat_background=role.illustrations[0],
    )

    updated = store.update_role(
        "mira",
        removed_illustrations=[selected.illustrations[0]],
    )

    assert updated.avatar is None
    assert updated.chat_background is None


def test_role_aggregate_service_initializes_role_session_and_memory_space(
    tmp_path: Path,
):
    class _SelfSeed:
        def generate(self, role) -> str:
            return (
                "# 角色自我认知\n\n"
                "## 人格与形象\n"
                f"- 我是{role.name}。\n\n"
                "## 我对当前用户的理解\n"
                "- 我会谨慎认识用户。\n\n"
                "## 我们关系的定义\n"
                "- 我们的关系仍在建立中。\n"
            )

    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
        self_seed_generator=_SelfSeed(),
    )

    aggregate = service.create_role(
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
        background="来自深海城的向导。",
    )

    assert aggregate.session.key == f"role:{aggregate.role.id}"
    assert aggregate.session.metadata["role_id"] == aggregate.role.id
    assert aggregate.memory_root.is_dir()
    self_text = (aggregate.memory_root / "SELF.md").read_text(encoding="utf-8").strip()
    assert self_text.startswith("# 角色自我认知")
    assert "我是Mira。" in self_text
    assert "内部底座" not in self_text
    assert (aggregate.memory_root / "MEMORY.md").read_text(encoding="utf-8")
    assert aggregate.role.memory_init_state["seed_self_ready"] is True
    assert aggregate.role.memory_init_state["seed_first_impression_ready"] is True
    assert aggregate.role.runtime_config == {}


def test_role_aggregate_service_updates_background_without_losing_history(
    tmp_path: Path,
):
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
    )
    aggregate = service.create_role(
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
        background="旧背景",
    )

    updated = service.update_role(aggregate.role.id, background="新背景")

    self_text = (updated.memory_root / "SELF.md").read_text(encoding="utf-8")
    history_text = (updated.memory_root / "HISTORY.md").read_text(encoding="utf-8")
    assert "新背景" in self_text
    assert "旧版本: 旧背景" in history_text
    assert "新版本: 新背景" in history_text


def test_role_self_seed_generator_does_not_override_existing_self(tmp_path: Path):
    class _SelfSeed:
        def generate(self, role) -> str:
            return "# 角色自我认知\n\n## 人格与形象\n- 新生成内容\n"

    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
        self_seed_generator=_SelfSeed(),
    )
    aggregate = service.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )

    self_path = aggregate.memory_root / "SELF.md"
    self_path.write_text(
        "# 角色自我认知\n\n## 人格与形象\n- 旧内容\n", encoding="utf-8"
    )

    reopened = service.open_role("mira")

    assert "旧内容" in (reopened.memory_root / "SELF.md").read_text(encoding="utf-8")
    assert "新生成内容" not in (reopened.memory_root / "SELF.md").read_text(
        encoding="utf-8"
    )


def test_role_aggregate_service_user_edit_first_impression_becomes_baseline(
    tmp_path: Path,
):
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
    )
    aggregate = service.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )

    updated = service.update_relationship_baseline(
        aggregate.role.id,
        content="用户给人的第一印象是谨慎而真诚。",
        source="user_edited",
    )

    memory_text = (updated.memory_root / "MEMORY.md").read_text(encoding="utf-8")
    history_text = (updated.memory_root / "HISTORY.md").read_text(encoding="utf-8")
    assert "来源: user_edited" in memory_text
    assert "用户给人的第一印象是谨慎而真诚。" in memory_text
    assert "关系基线修订" in history_text


def test_role_aggregate_service_system_derived_cannot_override_user_relationship_baseline(
    tmp_path: Path,
):
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
    )
    aggregate = service.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    edited = service.update_relationship_baseline(
        aggregate.role.id,
        content="用户给人的第一印象是谨慎而真诚。",
        source="user_edited",
    )

    evolved = service.update_relationship_baseline(
        edited.role.id,
        content="系统推断用户最近显得更放松。",
        source="system_derived",
    )

    memory_text = (evolved.memory_root / "MEMORY.md").read_text(encoding="utf-8")
    history_text = (evolved.memory_root / "HISTORY.md").read_text(encoding="utf-8")
    assert "用户给人的第一印象是谨慎而真诚。" in memory_text
    assert "系统推断用户最近显得更放松。" not in memory_text
    assert "关系记忆演化建议" in history_text
    assert "系统建议: 系统推断用户最近显得更放松。" in history_text


def test_role_binding_service_requires_explicit_binding(tmp_path: Path):
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
    )
    aggregate = service.create_role(
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )

    try:
        service.open_bound_channel(channel="telegram", chat_id="chat-1")
    except KeyError as exc:
        assert "渠道未绑定角色" in str(exc)
    else:
        raise AssertionError("未绑定渠道必须失败")

    binding = service.bindings.bind("telegram", "chat-1", aggregate.role.id)
    opened = service.open_bound_channel(channel="telegram", chat_id="chat-1")
    assert binding.role_id == aggregate.role.id
    assert opened.role.id == aggregate.role.id
    assert opened.session.key == f"role:{aggregate.role.id}"


def test_route_inbound_by_role_rewrites_legacy_channel_to_role_session(tmp_path: Path):
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    aggregate = service.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    _ = service.bindings.bind("telegram", "chat-1", aggregate.role.id)

    routed = route_inbound_by_role(
        service,
        InboundMessage(
            channel="telegram",
            sender="u1",
            chat_id="chat-1",
            content="hello",
            timestamp=datetime.now(),
            metadata={"chat_type": "private"},
        ),
    )

    assert routed.session_key == "thread:mira:telegram:chat-1"
    assert routed.metadata["role_id"] == "mira"
    assert routed.metadata["thread_id"] == "thread:mira:telegram:chat-1"
    assert routed.metadata["context_channel"] == "telegram"
    assert routed.metadata["context_chat_id"] == "chat-1"
    assert routed.metadata["transport_channel"] == "telegram"
    assert routed.metadata["transport_chat_id"] == "chat-1"
    thread = session_manager.conversation_store.get_thread_by_legacy_session_key(
        "telegram:chat-1"
    )
    assert thread is not None
    assert thread.thread_kind == "network"
    routed_session = session_manager.get_or_create("thread:mira:telegram:chat-1")
    assert routed_session.metadata["role_name"] == "Mira"
    assert routed_session.metadata["thread_id"] == "thread:mira:telegram:chat-1"


def test_route_inbound_by_role_leaves_unbound_legacy_channel_untouched(tmp_path: Path):
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
    )

    original = InboundMessage(
        channel="telegram",
        sender="u1",
        chat_id="chat-404",
        content="hello",
        timestamp=datetime.now(),
    )

    routed = route_inbound_by_role(service, original)

    assert routed is original
    assert "role_id" not in routed.metadata
    assert "session_key_override" not in routed.metadata
