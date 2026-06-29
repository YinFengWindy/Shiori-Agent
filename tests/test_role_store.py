from __future__ import annotations

from pathlib import Path

from datetime import datetime

from bus.events import InboundMessage
from core.roles import RoleAggregateService, RoleStore, route_inbound_by_role
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


def test_role_aggregate_service_initializes_role_session_and_memory_space(tmp_path: Path):
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
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
    assert (aggregate.memory_root / "SELF.md").read_text(encoding="utf-8").strip().endswith("来自深海城的向导。")
    assert (aggregate.memory_root / "MEMORY.md").read_text(encoding="utf-8")
    assert aggregate.role.memory_init_state["seed_background_ready"] is True
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


def test_route_inbound_by_role_rejects_unbound_legacy_channel(tmp_path: Path):
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
    )

    try:
        _ = route_inbound_by_role(
            service,
            InboundMessage(
                channel="telegram",
                sender="u1",
                chat_id="chat-404",
                content="hello",
                timestamp=datetime.now(),
            ),
        )
    except KeyError as exc:
        assert "渠道未绑定角色" in str(exc)
    else:
        raise AssertionError("未绑定 legacy channel 必须失败")
