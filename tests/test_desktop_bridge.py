from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.tools.message_push import MessagePushTool
from bus.event_bus import EventBus
from bus.events_lifecycle import StreamDeltaReady, TurnCommitted
from core.integrations.novelai.models import (
    GenerateImageResult,
    GeneratedImageRecord,
    NovelAISettings,
)
from core.integrations.novelai.store import NovelAIStore
from core.roles import RoleStore
from desktop_bridge import DesktopBridgeServer, DesktopBridgeService
from session.manager import SessionManager


@pytest.mark.asyncio
async def test_desktop_bridge_role_lifecycle_and_chat_send(tmp_path: Path):
    role_store = RoleStore(tmp_path)
    session_manager = SessionManager(tmp_path)
    event_bus = EventBus()

    async def _process_direct(
        content: str,
        *,
        session_key: str,
        channel: str,
        chat_id: str,
        stream_events: bool,
        **kwargs,
    ) -> str:
        assert session_key == f"role:{role_id}"
        assert channel == "desktop"
        assert chat_id == f"role:{role_id}"
        assert stream_events is True
        session = session_manager.get_or_create(session_key)
        session.add_message("user", content)
        session.add_message("assistant", "hello")
        await session_manager.save_async(session)
        await event_bus.observe(
            StreamDeltaReady(
                session_key=session_key,
                channel=channel,
                chat_id=chat_id,
                content_delta="hel",
            )
        )
        await event_bus.observe(
            TurnCommitted(
                session_key=session_key,
                channel=channel,
                chat_id=chat_id,
                input_message=content,
                persisted_user_message=content,
                assistant_response="hello",
                tools_used=[],
                thinking=None,
            )
        )
        return "hello"

    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(process_direct=_process_direct),
        event_bus=event_bus,
    )
    emitted: list[dict] = []

    created = await service.handle(
        {
            "id": "1",
            "method": "roles.create",
            "payload": {
                "name": "Mira",
                "description": "desktop role",
                "system_prompt": "you are mira",
            },
        },
        emit_event=emitted.append,
    )
    role_id = created.payload["role"]["id"]

    opened = await service.handle(
        {
            "id": "2",
            "method": "session.openByRole",
            "payload": {"role_id": role_id},
        },
        emit_event=emitted.append,
    )
    assert opened.payload["session"]["key"] == f"role:{role_id}"
    assert opened.payload["session"]["created_at"]
    assert opened.payload["session"]["updated_at"]
    assert opened.payload["session"]["last_consolidated"] == 0
    assert opened.payload["session"]["messages"] == []

    response = await service.handle(
        {
            "id": "3",
            "method": "chat.send",
            "payload": {"role_id": role_id, "content": "hi"},
        },
        emit_event=emitted.append,
    )

    assert response.error is None
    assert response.payload["session"]["key"] == f"role:{role_id}"
    assert [item["role"] for item in response.payload["session"]["messages"]] == ["user", "assistant"]
    methods = [item["method"] for item in emitted]
    assert methods == ["session.updated", "chat.delta", "chat.done", "session.updated"]
    delta_event = next(item for item in emitted if item["method"] == "chat.delta")
    done_event = next(item for item in emitted if item["method"] == "chat.done")
    assert delta_event["payload"]["content_delta"] == "hel"
    assert done_event["payload"]["reply"] == "hello"


@pytest.mark.asyncio
async def test_desktop_bridge_role_create_generates_initial_self(tmp_path: Path):
    role_store = RoleStore(tmp_path)
    session_manager = SessionManager(tmp_path)
    event_bus = EventBus()

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

    from core.roles import RoleAggregateService

    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=event_bus,
        role_service=RoleAggregateService.from_runtime(
            workspace=tmp_path,
            role_store=role_store,
            session_manager=session_manager,
            self_seed_generator=_SelfSeed(),
        ),
    )

    created = await service.handle(
        {
            "id": "1",
            "method": "roles.create",
            "payload": {
                "name": "Mira",
                "description": "desktop role",
                "system_prompt": "you are mira",
            },
        },
        emit_event=lambda payload: None,
    )

    role_id = created.payload["role"]["id"]
    self_path = tmp_path / "roles" / role_id / "memory" / "SELF.md"
    self_text = self_path.read_text(encoding="utf-8")

    assert self_text.startswith("# 角色自我认知")
    assert "我是Mira。" in self_text


@pytest.mark.asyncio
async def test_desktop_bridge_role_create_supports_async_self_seed_generator(tmp_path: Path):
    role_store = RoleStore(tmp_path)
    session_manager = SessionManager(tmp_path)
    event_bus = EventBus()

    class _AsyncSelfSeed:
        async def agenerate(self, role) -> str:
            await asyncio.sleep(0)
            return (
                "# 角色自我认知\n\n"
                "## 人格与形象\n"
                f"- 我是{role.name}。\n\n"
                "## 我对当前用户的理解\n"
                "- 我会谨慎认识用户。\n\n"
                "## 我们关系的定义\n"
                "- 我们的关系仍在建立中。\n"
            )

        def generate(self, role) -> str:
            raise AssertionError("事件循环中的桌面桥不应回退到同步 generate")

    from core.roles import RoleAggregateService

    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=event_bus,
        role_service=RoleAggregateService.from_runtime(
            workspace=tmp_path,
            role_store=role_store,
            session_manager=session_manager,
            self_seed_generator=_AsyncSelfSeed(),
        ),
    )

    created = await service.handle(
        {
            "id": "1",
            "method": "roles.create",
            "payload": {
                "name": "Mira",
                "description": "desktop role",
                "system_prompt": "you are mira",
            },
        },
        emit_event=lambda payload: None,
    )

    assert created.error is None
    role_id = created.payload["role"]["id"]
    self_path = tmp_path / "roles" / role_id / "memory" / "SELF.md"
    self_text = self_path.read_text(encoding="utf-8")

    assert self_text.startswith("# 角色自我认知")
    assert "我是Mira。" in self_text


@pytest.mark.asyncio
async def test_desktop_bridge_returns_role_not_found(tmp_path: Path):
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
    )

    response = await service.handle(
        {
            "id": "1",
            "method": "chat.send",
            "payload": {"role_id": "missing", "content": "hi"},
        },
        emit_event=lambda payload: None,
    )

    assert response.error is not None
    assert response.error.code == "role_not_found"


@pytest.mark.asyncio
async def test_desktop_bridge_chat_listeners_are_removed_after_send(tmp_path: Path):
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    session_manager = SessionManager(tmp_path)
    event_bus = EventBus()

    async def _process_direct(**kwargs) -> str:
        session = session_manager.get_or_create("role:mira")
        session.add_message("user", "hi")
        session.add_message("assistant", "hello")
        await session_manager.save_async(session)
        await event_bus.observe(
            TurnCommitted(
                session_key="role:mira",
                channel="desktop",
                chat_id="role:mira",
                input_message="hi",
                persisted_user_message="hi",
                assistant_response="hello",
                tools_used=[],
                thinking=None,
            )
        )
        return "hello"

    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(process_direct=_process_direct),
        event_bus=event_bus,
    )

    await service.handle(
        {
            "id": "1",
            "method": "chat.send",
            "payload": {"role_id": role.id, "content": "hi"},
        },
        emit_event=lambda payload: None,
    )

    assert event_bus._handlers.get(StreamDeltaReady, []) == []
    assert event_bus._handlers.get(TurnCommitted, []) == []


@pytest.mark.asyncio
async def test_desktop_bridge_emits_session_updated_for_background_desktop_push(tmp_path: Path):
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    session_manager = SessionManager(tmp_path)
    push_tool = MessagePushTool()
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
        push_tool=push_tool,
    )
    emitted: list[dict] = []
    service.add_event_listener(emitted.append)

    result = await push_tool.execute(
        channel="desktop",
        chat_id=role.id,
        message="主动消息",
    )

    assert "已发送" in result
    assert len(emitted) == 1
    assert emitted[0]["method"] == "session.updated"
    messages = emitted[0]["payload"]["session"]["messages"]
    assert messages[-1]["content"] == "主动消息"
    assert messages[-1]["metadata"]["proactive"] is True
    assert messages[-1]["metadata"]["tools_used"] == ["message_push"]


@pytest.mark.asyncio
async def test_desktop_bridge_desktop_push_does_not_duplicate_existing_proactive_message(tmp_path: Path):
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    session_manager = SessionManager(tmp_path)
    session = session_manager.open_role_session(
        role.id,
        role_name=role.name,
    )
    session.add_message("assistant", "主动消息", proactive=True, tools_used=["message_push"])
    await session_manager.save_async(session)
    push_tool = MessagePushTool()
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
        push_tool=push_tool,
    )

    _ = await push_tool.execute(
        channel="desktop",
        chat_id=role.id,
        message="主动消息",
    )

    session_after = session_manager.get_or_create("role:mira")
    assert len(session_after.messages) == 1


@pytest.mark.asyncio
async def test_desktop_bridge_server_streams_requests_and_responses(tmp_path: Path):
    role_store = RoleStore(tmp_path)
    session_manager = SessionManager(tmp_path)
    event_bus = EventBus()
    runtime = SimpleNamespace(
        session_manager=SimpleNamespace(workspace=tmp_path, open_role_session=session_manager.open_role_session),
        loop=SimpleNamespace(process_direct=AsyncMock(return_value="ok")),
        event_bus=event_bus,
    )
    server = DesktopBridgeServer(runtime)

    lines = iter(
        [
            json.dumps({"id": "1", "method": "health", "payload": {}}),
            "",
        ]
    )
    writes: list[dict] = []

    async def _read_line():
        try:
            return next(lines)
        except StopIteration:
            return None

    async def _write_payload(payload: dict):
        writes.append(payload)

    await server.serve_streams(read_line=_read_line, write_payload=_write_payload)

    assert writes == [
        {
            "id": "1",
            "type": "response",
            "method": "health",
            "payload": {"ok": True},
            "error": None,
        }
    ]


@pytest.mark.asyncio
async def test_desktop_bridge_updates_role_display_state(tmp_path: Path):
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    session_manager = SessionManager(tmp_path)
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
    )

    response = await service.handle(
        {
            "id": "1",
            "method": "session.updateDisplayState",
            "payload": {
                "role_id": role.id,
                "active_illustration": "roles/assets/mira/illustration-1.png",
            },
        },
        emit_event=lambda payload: None,
    )

    assert response.error is None
    assert response.payload["session"]["metadata"]["active_illustration"] == "roles/assets/mira/illustration-1.png"


@pytest.mark.asyncio
async def test_desktop_bridge_open_role_emits_session_updated(tmp_path: Path):
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    session_manager = SessionManager(tmp_path)
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
    )
    emitted: list[dict] = []

    response = await service.handle(
        {
            "id": "1",
            "method": "session.openByRole",
            "payload": {"role_id": role.id},
        },
        emit_event=emitted.append,
    )

    assert response.error is None
    assert emitted[0]["method"] == "session.updated"
    assert emitted[0]["payload"]["session"]["key"] == "role:mira"
    assert emitted[0]["payload"]["session"]["metadata"]["role_name"] == "Mira"


@pytest.mark.asyncio
async def test_desktop_bridge_role_create_and_update_copy_assets(tmp_path: Path):
    avatar = tmp_path / "avatar.png"
    avatar.write_bytes(b"avatar")
    ill1 = tmp_path / "ill-1.png"
    ill1.write_bytes(b"ill-1")
    ill2 = tmp_path / "ill-2.png"
    ill2.write_bytes(b"ill-2")

    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
    )

    created = await service.handle(
        {
            "id": "1",
            "method": "roles.create",
            "payload": {
                "name": "Mira",
                "description": "desktop role",
                "system_prompt": "you are mira",
                "avatar_source": str(avatar),
                "illustration_sources": [str(ill1)],
            },
        },
        emit_event=lambda payload: None,
    )

    assert created.error is None
    role = created.payload["role"]
    avatar_abs = Path(role["avatar_abs"])
    illustration_abs = Path(role["illustrations_abs"][0])
    assert avatar_abs.read_bytes() == b"avatar"
    assert illustration_abs.read_bytes() == b"ill-1"

    updated = await service.handle(
        {
            "id": "2",
            "method": "roles.update",
            "payload": {
                "role_id": role["id"],
                "avatar_source": str(avatar),
                "illustration_sources": [str(ill2)],
            },
        },
        emit_event=lambda payload: None,
    )

    assert updated.error is None
    updated_role = updated.payload["role"]
    assert Path(updated_role["avatar_abs"]).read_bytes() == b"avatar"
    assert len(updated_role["illustrations_abs"]) == 2
    assert Path(updated_role["illustrations_abs"][1]).read_bytes() == b"ill-2"


@pytest.mark.asyncio
async def test_desktop_bridge_role_update_removes_selected_illustration(tmp_path: Path):
    ill1 = tmp_path / "ill-1.png"
    ill1.write_bytes(b"ill-1")
    ill2 = tmp_path / "ill-2.png"
    ill2.write_bytes(b"ill-2")

    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
    )

    created = await service.handle(
        {
            "id": "1",
            "method": "roles.create",
            "payload": {
                "name": "Mira",
                "description": "desktop role",
                "system_prompt": "you are mira",
                "illustration_sources": [str(ill1), str(ill2)],
            },
        },
        emit_event=lambda payload: None,
    )

    role = created.payload["role"]
    removed_path = role["illustrations"][0]
    kept_abs_path = Path(role["illustrations_abs"][1])

    updated = await service.handle(
        {
            "id": "2",
            "method": "roles.update",
            "payload": {
                "role_id": role["id"],
                "removed_illustrations": [removed_path],
            },
        },
        emit_event=lambda payload: None,
    )

    assert updated.error is None
    updated_role = updated.payload["role"]
    assert updated_role["illustrations"] == [role["illustrations"][1]]
    assert len(updated_role["illustrations_abs"]) == 1
    assert kept_abs_path.exists()
    assert not (tmp_path / "roles" / removed_path).exists()


@pytest.mark.asyncio
async def test_desktop_bridge_role_update_selects_avatar_and_chat_background_from_library(tmp_path: Path):
    ill1 = tmp_path / "ill-1.png"
    ill1.write_bytes(b"ill-1")
    ill2 = tmp_path / "ill-2.png"
    ill2.write_bytes(b"ill-2")

    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
    )

    created = await service.handle(
        {
            "id": "1",
            "method": "roles.create",
            "payload": {
                "name": "Mira",
                "description": "desktop role",
                "system_prompt": "you are mira",
                "illustration_sources": [str(ill1), str(ill2)],
            },
        },
        emit_event=lambda payload: None,
    )

    role = created.payload["role"]
    updated = await service.handle(
        {
            "id": "2",
            "method": "roles.update",
            "payload": {
                "role_id": role["id"],
                "avatar_asset": role["illustrations"][0],
                "chat_background": role["illustrations"][1],
            },
        },
        emit_event=lambda payload: None,
    )

    assert updated.error is None
    updated_role = updated.payload["role"]
    assert updated_role["avatar"] == role["illustrations"][0]
    assert updated_role["avatar_abs"] == role["illustrations_abs"][0]
    assert updated_role["chat_background"] == role["illustrations"][1]
    assert updated_role["chat_background_abs"] == role["illustrations_abs"][1]


@pytest.mark.asyncio
async def test_desktop_bridge_role_update_clears_selected_slots_when_asset_removed(tmp_path: Path):
    ill1 = tmp_path / "ill-1.png"
    ill1.write_bytes(b"ill-1")
    ill2 = tmp_path / "ill-2.png"
    ill2.write_bytes(b"ill-2")

    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
    )

    created = await service.handle(
        {
            "id": "1",
            "method": "roles.create",
            "payload": {
                "name": "Mira",
                "description": "desktop role",
                "system_prompt": "you are mira",
                "illustration_sources": [str(ill1), str(ill2)],
            },
        },
        emit_event=lambda payload: None,
    )
    role = created.payload["role"]

    selected = await service.handle(
        {
            "id": "2",
            "method": "roles.update",
            "payload": {
                "role_id": role["id"],
                "avatar_asset": role["illustrations"][0],
                "chat_background": role["illustrations"][0],
            },
        },
        emit_event=lambda payload: None,
    )
    assert selected.error is None

    updated = await service.handle(
        {
            "id": "3",
            "method": "roles.update",
            "payload": {
                "role_id": role["id"],
                "removed_illustrations": [role["illustrations"][0]],
            },
        },
        emit_event=lambda payload: None,
    )

    assert updated.error is None
    updated_role = updated.payload["role"]
    assert updated_role["avatar"] is None
    assert updated_role["avatar_abs"] is None
    assert updated_role["chat_background"] is None
    assert updated_role["chat_background_abs"] is None


@pytest.mark.asyncio
async def test_desktop_bridge_chat_cancel_uses_interrupt_controller(tmp_path: Path):
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    session_manager = SessionManager(tmp_path)
    loop = SimpleNamespace(
        process_direct=AsyncMock(),
        request_interrupt=lambda session_key, sender="", command="/stop": SimpleNamespace(
            status="interrupted",
            session_key=session_key,
            message="cancelled",
        ),
    )
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=loop,
        event_bus=EventBus(),
    )

    response = await service.handle(
        {
            "id": "1",
            "method": "chat.cancel",
            "payload": {"role_id": role.id},
        },
        emit_event=lambda payload: None,
    )

    assert response.error is None
    assert response.payload["status"] == "interrupted"
    assert response.payload["session_key"] == "role:mira"


@pytest.mark.asyncio
async def test_desktop_bridge_normalizes_stale_active_illustration_on_role_update(tmp_path: Path):
    image = tmp_path / "ill-1.png"
    image.write_bytes(b"img")
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
        illustration_sources=[image],
    )
    session_manager = SessionManager(tmp_path)
    session_manager.update_role_session_display_state(
        role.id,
        active_illustration="illustration-old.png",
    )
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
    )

    response = await service.handle(
        {
            "id": "1",
            "method": "roles.update",
            "payload": {
                "role_id": role.id,
                "clear_illustrations": True,
            },
        },
        emit_event=lambda payload: None,
    )

    assert response.error is None
    session = session_manager.get_or_create("role:mira")
    assert "active_illustration" not in session.metadata


@pytest.mark.asyncio
async def test_desktop_bridge_syncs_role_metadata_into_session_on_open_and_update(tmp_path: Path):
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    session_manager = SessionManager(tmp_path)
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
    )

    opened = await service.handle(
        {
            "id": "1",
            "method": "session.openByRole",
            "payload": {"role_id": role.id},
        },
        emit_event=lambda payload: None,
    )
    assert opened.error is None
    assert opened.payload["session"]["metadata"]["role_name"] == "Mira"
    assert opened.payload["session"]["metadata"]["role_prompt"] == "you are mira"

    updated = await service.handle(
        {
            "id": "2",
            "method": "roles.update",
            "payload": {
                "role_id": role.id,
                "name": "Mira Prime",
                "system_prompt": "you are still mira",
            },
        },
        emit_event=lambda payload: None,
    )
    assert updated.error is None
    session = session_manager.get_or_create("role:mira")
    assert session.metadata["role_name"] == "Mira Prime"
    assert session.metadata["role_prompt"] == "you are still mira"


@pytest.mark.asyncio
async def test_desktop_bridge_role_delete_removes_role_session(tmp_path: Path):
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    session_manager = SessionManager(tmp_path)
    session_manager.open_role_session(role.id, role_name=role.name)
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
    )

    response = await service.handle(
        {
            "id": "1",
            "method": "roles.delete",
            "payload": {"role_id": role.id},
        },
        emit_event=lambda payload: None,
    )

    assert response.error is None
    assert response.payload["deleted"] is True
    assert response.payload["session_deleted"] is True
    assert session_manager._store.get_session_meta("role:mira") is None


@pytest.mark.asyncio
async def test_desktop_bridge_novelai_generate_and_history(tmp_path: Path):
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    session_manager = SessionManager(tmp_path)
    novelai_store = NovelAIStore(tmp_path)
    output_path = tmp_path / "private_runtime" / "novelai" / "outputs" / "2026-06-30" / "rec-1" / "output-1.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"png")
    request_path = output_path.parent / "request.json"
    request_path.write_text("{}", encoding="utf-8")
    meta_path = output_path.parent / "meta.json"
    meta_path.write_text("{}", encoding="utf-8")
    novelai_store.append_record(
        GeneratedImageRecord(
            id="rec-0",
            created_at="2026-06-30T10:00:00+00:00",
            mode="txt2img",
            role_id="mira",
            session_key="role:mira",
            prompt="history item",
            negative_prompt="",
            model="nai-diffusion-4-5-full",
            sampler="k_euler",
            steps=28,
            seed=123,
            width=1024,
            height=1024,
            base_image_path="",
            output_paths=[str(output_path)],
            wrote_back_to_role=False,
        )
    )
    novelai_service = SimpleNamespace(
        generate=AsyncMock(
            return_value=GenerateImageResult(
                record_id="rec-1",
                created_at="2026-06-30T12:00:00+00:00",
                mode="txt2img",
                model="nai-diffusion-4-5-full",
                seed=456,
                width=1024,
                height=1024,
                output_paths=[str(output_path)],
                request_path=str(request_path),
                meta_path=str(meta_path),
                wrote_back_to_role=True,
                role_asset_paths=["assets/mira/output.png"],
            )
        )
    )
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
        config=SimpleNamespace(novelai=NovelAISettings(enabled=True, token="novel-token")),
        novelai_service=novelai_service,
        novelai_store=novelai_store,
    )

    generated = await service.handle(
        {
            "id": "1",
            "method": "novelai.generate",
            "payload": {
                "role_id": role.id,
                "prompt": "moonlight portrait",
                "mode": "txt2img",
            },
        },
        emit_event=lambda payload: None,
    )
    history = await service.handle(
        {
            "id": "2",
            "method": "novelai.history",
            "payload": {"role_id": role.id, "limit": 5},
        },
        emit_event=lambda payload: None,
    )

    assert generated.error is None
    assert generated.payload["result"]["record_id"] == "rec-1"
    assert generated.payload["result"]["wrote_back_to_role"] is True
    novelai_service.generate.assert_awaited_once()
    request = novelai_service.generate.await_args.args[0]
    assert request.role_id == "mira"
    assert request.session_key == "role:mira"

    assert history.error is None
    assert history.payload["records"][0]["id"] == "rec-0"
