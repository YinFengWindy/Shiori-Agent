from __future__ import annotations

import json
from pathlib import Path

from datetime import datetime

from bus.events import InboundMessage
from core.roles import (
    RoleAggregateService,
    RoleLegacyMigrator,
    RoleStore,
    route_inbound_by_role,
)
from session.manager import SessionManager
from memory2.store import MemoryStore2


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


def test_role_store_can_select_avatar_and_featured_image_from_asset_library(tmp_path: Path):
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
        featured_image=role.illustrations[1],
    )

    assert updated.avatar == role.illustrations[0]
    assert updated.featured_image == role.illustrations[1]


def test_role_store_clears_selected_assets_when_underlying_asset_removed(tmp_path: Path):
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
        featured_image=role.illustrations[0],
    )

    updated = store.update_role(
        "mira",
        removed_illustrations=[selected.illustrations[0]],
    )

    assert updated.avatar is None
    assert updated.featured_image is None


def test_role_aggregate_service_initializes_role_session_and_memory_space(tmp_path: Path):
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


def test_role_aggregate_service_updates_background_without_losing_history(tmp_path: Path):
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
    self_path.write_text("# 角色自我认知\n\n## 人格与形象\n- 旧内容\n", encoding="utf-8")

    reopened = service.open_role("mira")

    assert "旧内容" in (reopened.memory_root / "SELF.md").read_text(encoding="utf-8")
    assert "新生成内容" not in (reopened.memory_root / "SELF.md").read_text(encoding="utf-8")


def test_role_aggregate_service_user_edit_first_impression_becomes_baseline(tmp_path: Path):
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


def test_role_aggregate_service_system_derived_cannot_override_user_relationship_baseline(tmp_path: Path):
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

    assert routed.session_key == "role:mira"
    assert routed.metadata["role_id"] == "mira"
    assert routed.metadata["context_channel"] == "telegram"
    assert routed.metadata["context_chat_id"] == "chat-1"
    assert routed.metadata["transport_channel"] == "telegram"
    assert routed.metadata["transport_chat_id"] == "chat-1"


def test_route_inbound_by_role_accepts_legacy_qq_group_binding_without_gqq_prefix(
    tmp_path: Path,
):
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    _ = service.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    _ = service.bindings.bind("qq", "852463977", "mira")

    routed = route_inbound_by_role(
        service,
        InboundMessage(
            channel="qq",
            sender="u1",
            chat_id="gqq:852463977",
            content="hello",
            timestamp=datetime.now(),
            metadata={"chat_type": "group", "group_id": "852463977"},
        ),
    )

    assert routed.session_key == "role:mira:group:852463977:member:u1"
    assert routed.metadata["role_id"] == "mira"
    assert routed.metadata["group_member_id"] == "u1"
    assert routed.metadata["group_context_key"] == "groupctx:qq:852463977"
    assert routed.metadata["context_channel"] == "qq"
    assert routed.metadata["context_chat_id"] == "gqq:852463977"
    assert routed.metadata["transport_channel"] == "qq"
    assert routed.metadata["transport_chat_id"] == "gqq:852463977"


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


def test_role_legacy_migrator_moves_confirmed_session_into_role_session(tmp_path: Path):
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    _ = service.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    legacy = session_manager.get_or_create("telegram:123")
    legacy.metadata["role_id"] = "mira"
    legacy.add_message("user", "hello")
    session_manager.save(legacy)

    migrator = RoleLegacyMigrator(
        workspace=tmp_path,
        roles=service,
        session_manager=session_manager,
    )
    summary = migrator.migrate()

    migrated = session_manager.get_or_create("role:mira")
    assert "telegram:123" in summary.migrated_session_keys
    assert "telegram:123" in summary.migrated_bindings
    assert [item["content"] for item in migrated.messages] == ["hello"]
    binding = service.bindings.get_binding("telegram", "123")
    assert binding is not None
    assert binding.role_id == "mira"


def test_role_legacy_migrator_splits_legacy_group_session_by_member(tmp_path: Path):
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    _ = service.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    legacy = session_manager.get_or_create("qq:gqq:100")
    legacy.metadata["role_id"] = "mira"
    legacy.metadata["group_id"] = "100"
    legacy.add_message("user", "u1-hello", metadata={"member_id": "u1"})
    legacy.add_message("assistant", "a1")
    legacy.add_message("user", "u2-hello", metadata={"member_id": "u2"})
    legacy.add_message("assistant", "a2")
    session_manager.save(legacy)

    migrator = RoleLegacyMigrator(
        workspace=tmp_path,
        roles=service,
        session_manager=session_manager,
    )
    summary = migrator.migrate()

    member1 = session_manager.get_or_create("role:mira:group:100:member:u1")
    member2 = session_manager.get_or_create("role:mira:group:100:member:u2")
    assert "qq:gqq:100" in summary.migrated_session_keys
    assert [item["content"] for item in member1.messages] == ["u1-hello", "a1"]
    assert [item["content"] for item in member2.messages] == ["u2-hello", "a2"]
    assert member1.metadata["group_member_id"] == "u1"
    assert member2.metadata["group_member_id"] == "u2"


def test_role_legacy_migrator_marks_ambiguous_group_memory_unresolved(tmp_path: Path):
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    _ = service.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )

    memory_store = MemoryStore2(tmp_path / "memory" / "memory2.db", vec_dim=2)
    unresolved_result = memory_store.upsert_item(
        memory_type="preference",
        summary="群里某人偏好中文回复",
        embedding=[1.0, 0.0],
        extra={
            "role_id": "mira",
            "memory_domain": "relationship",
            "scope_channel": "qq",
            "scope_chat_id": "gqq:100",
        },
        source_ref="legacy:group:pref",
    )
    resolved_result = memory_store.upsert_item(
        memory_type="preference",
        summary="成员 u1 偏好中文回复",
        embedding=[1.0, 0.0],
        extra={
            "role_id": "mira",
            "memory_domain": "relationship",
            "scope_channel": "qq",
            "scope_chat_id": "gqq:100",
            "group_member_id": "u1",
        },
        source_ref="legacy:group:member-pref",
    )
    unresolved_item_id = unresolved_result.split(":", 1)[1]
    resolved_item_id = resolved_result.split(":", 1)[1]

    migrator = RoleLegacyMigrator(
        workspace=tmp_path,
        roles=service,
        session_manager=session_manager,
        memory_store=memory_store,
    )
    summary = migrator.migrate()

    assert unresolved_item_id in summary.unresolved_memory_item_ids
    assert resolved_item_id in summary.migrated_memory_item_ids


def test_role_legacy_migrator_keeps_unconfirmed_session_in_unresolved(tmp_path: Path):
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    legacy = session_manager.get_or_create("telegram:404")
    legacy.add_message("user", "hello")
    session_manager.save(legacy)

    migrator = RoleLegacyMigrator(
        workspace=tmp_path,
        roles=service,
        session_manager=session_manager,
    )
    summary = migrator.migrate()

    unresolved = json.loads((tmp_path / "roles" / "migration_unresolved.json").read_text(encoding="utf-8"))
    assert summary.migrated_session_keys == []
    assert "telegram:404" in unresolved["unresolved_session_keys"]


def test_role_legacy_migrator_is_idempotent_for_sessions_and_memory_items(tmp_path: Path):
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    _ = service.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    legacy = session_manager.get_or_create("telegram:123")
    legacy.metadata["role_id"] = "mira"
    legacy.add_message("user", "hello")
    session_manager.save(legacy)

    memory_store = MemoryStore2(tmp_path / "memory" / "memory2.db", vec_dim=2)
    item_result = memory_store.upsert_item(
        memory_type="profile",
        summary="用户常驻上海",
        embedding=[1.0, 0.0],
        extra={"role_id": "mira", "memory_domain": "relationship"},
        source_ref="telegram:123:profile",
    )
    item_id = item_result.split(":", 1)[1]

    migrator = RoleLegacyMigrator(
        workspace=tmp_path,
        roles=service,
        session_manager=session_manager,
        memory_store=memory_store,
    )
    first = migrator.migrate()
    second = migrator.migrate()

    assert "telegram:123" in first.migrated_session_keys
    assert item_id in first.migrated_memory_item_ids
    assert second.migrated_session_keys == []
    assert second.migrated_memory_item_ids == []
    migrated = session_manager.get_or_create("role:mira")
    assert [item["content"] for item in migrated.messages] == ["hello"]


def test_role_legacy_migrator_avoids_duplicate_messages_when_state_file_missing(tmp_path: Path):
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    _ = service.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    legacy = session_manager.get_or_create("telegram:123")
    legacy.metadata["role_id"] = "mira"
    legacy.add_message("user", "hello")
    session_manager.save(legacy)

    migrator = RoleLegacyMigrator(
        workspace=tmp_path,
        roles=service,
        session_manager=session_manager,
    )
    first = migrator.migrate()
    assert "telegram:123" in first.migrated_session_keys

    state_path = tmp_path / "roles" / "migration_state.json"
    if state_path.exists():
        state_path.unlink()

    second = migrator.migrate()

    migrated = session_manager.get_or_create("role:mira")
    assert second.migrated_session_keys == ["telegram:123"]
    assert [item["content"] for item in migrated.messages] == ["hello"]
