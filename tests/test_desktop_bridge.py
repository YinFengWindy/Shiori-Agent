from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
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
from core.roles.relationship_runtime import RoleRelationshipRuntimeService
from desktop_bridge import DesktopBridgeServer, DesktopBridgeService
from desktop_bridge.models import BridgeResponse
from proactive_v2.presence import PresenceStore
from session.manager import SessionManager


async def _wait_until(predicate, *, attempts: int = 40) -> None:
    for _ in range(attempts):
        if predicate():
            return
        await asyncio.sleep(0)
    assert predicate()


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
        omit_user_turn: bool,
        stream_events: bool,
        media: list[str],
        **kwargs,
    ) -> str:
        assert session_key == f"role:{role_id}"
        assert channel == "desktop"
        assert chat_id == f"role:{role_id}"
        assert omit_user_turn is True
        assert stream_events is True
        assert media == ["D:\\files\\scene.png"]
        session = session_manager.get_or_create(session_key)
        session.add_message("assistant", "hello", metadata=dict(kwargs["metadata"]))
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
    assert "thread" not in opened.payload["session"]
    assert opened.payload["session"]["created_at"]
    assert opened.payload["session"]["updated_at"]
    assert opened.payload["session"]["last_consolidated"] == 0
    assert opened.payload["session"]["messages"] == []

    response = await service.handle(
        {
            "id": "3",
            "method": "chat.send",
            "payload": {
                "role_id": role_id,
                "content": "hi",
                "media": ["D:\\files\\scene.png"],
                "client_message_id": "desktop-message-1",
            },
        },
        emit_event=emitted.append,
    )

    assert response.error is None
    assert response.payload["session"]["key"] == f"role:{role_id}"
    assert "thread" not in response.payload["session"]
    assert [item["role"] for item in response.payload["session"]["messages"]] == [
        "user"
    ]
    assert response.payload["session"]["messages"][0]["content"] == "hi"
    assert response.payload["session"]["messages"][0]["media"] == [
        "D:\\files\\scene.png"
    ]
    assert response.payload["session"]["messages"][0]["metadata"][
        "client_message_id"
    ] == "desktop-message-1"
    await _wait_until(
        lambda: [item["method"] for item in emitted]
        == ["session.updated", "chat.delta", "chat.done", "session.updated"]
    )
    methods = [item["method"] for item in emitted]
    assert methods == ["session.updated", "chat.delta", "chat.done", "session.updated"]
    delta_event = next(item for item in emitted if item["method"] == "chat.delta")
    done_event = next(item for item in emitted if item["method"] == "chat.done")
    session_updated_event = emitted[-1]
    assert [
        item["role"] for item in session_updated_event["payload"]["session"]["messages"]
    ] == ["user", "assistant"]
    assert session_updated_event["payload"]["session"]["messages"][0]["media"] == [
        "D:\\files\\scene.png"
    ]
    assert delta_event["payload"]["content_delta"] == "hel"
    assert done_event["payload"]["reply"] == "hello"
    assert session_manager.conversation_store.list_message_thread_ids(f"role:{role_id}") == [
        f"thread:{role_id}:desktop",
        f"thread:{role_id}:desktop",
    ]


@pytest.mark.asyncio
async def test_desktop_bridge_chat_send_merges_reply_context_for_agent(tmp_path: Path):
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    session_manager = SessionManager(tmp_path)
    event_bus = EventBus()
    seen: dict[str, object] = {}

    async def _process_direct(
        content: str,
        *,
        session_key: str,
        media: list[str],
        metadata: dict[str, object],
        omit_user_turn: bool,
        **kwargs,
    ) -> str:
        seen["content"] = content
        seen["metadata"] = dict(metadata)
        seen["omit_user_turn"] = omit_user_turn
        session = session_manager.get_or_create(session_key)
        session.add_message("assistant", "继续")
        await session_manager.save_async(session)
        return "继续"

    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(process_direct=_process_direct),
        event_bus=event_bus,
    )

    response = await service.handle(
        {
            "id": "1",
            "method": "chat.send",
            "payload": {
                "role_id": role.id,
                "content": "再展开一点",
                "reply_to_message_id": "message-1",
                "reply_to_content": "她沉默了很久。",
                "reply_to_sender": "Mira",
            },
        },
        emit_event=lambda payload: None,
    )

    assert response.error is None
    await _wait_until(lambda: "content" in seen)
    assert seen["content"] == (
        "【你正在回复一条历史消息】\n"
        "被回复消息（来自 Mira）：\n"
        "她沉默了很久。\n\n"
        "【你当前新消息】\n"
        "再展开一点"
    )
    assert seen["metadata"] == {
        "request_id": "1",
        "delivery_key": "1",
        "reply_to_message_id": "message-1",
        "reply_to_sender": "Mira",
        "reply_to_content": "她沉默了很久。",
        "source": "desktop",
        "sender_id": "desktop",
        "chat_type": "desktop",
        "role_id": "mira",
        "thread_id": "thread:mira:desktop",
        "context_channel": "desktop",
        "context_chat_id": "role:mira",
        "transport_channel": "desktop",
        "transport_chat_id": "role:mira",
    }
    assert seen["omit_user_turn"] is True
    session = session_manager.get_or_create("role:mira")
    user_message = session.messages[0]
    assert user_message["content"] == "再展开一点"
    assert user_message["metadata"]["reply_to_message_id"] == "message-1"
    assert user_message["metadata"]["reply_to_content"] == "她沉默了很久。"


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
async def test_desktop_bridge_role_create_supports_async_self_seed_generator(
    tmp_path: Path,
):
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

    async def _process_direct(content: str, **kwargs) -> str:
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

    await _wait_until(
        lambda: event_bus._handlers.get(StreamDeltaReady, []) == []
        and len(event_bus._handlers.get(TurnCommitted, [])) == 1
    )
    assert event_bus._handlers.get(StreamDeltaReady, []) == []
    assert len(event_bus._handlers.get(TurnCommitted, [])) == 1


@pytest.mark.asyncio
async def test_desktop_bridge_chat_send_accepts_media_only(tmp_path: Path):
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    session_manager = SessionManager(tmp_path)
    event_bus = EventBus()

    async def _process_direct(
        content: str,
        *,
        session_key: str,
        media: list[str],
        **kwargs,
    ) -> str:
        assert content == ""
        assert media == ["D:\\files\\notes.md"]
        session = session_manager.get_or_create(session_key)
        session.add_message("user", content, media=media or None)
        session.add_message("assistant", "收到")
        await session_manager.save_async(session)
        await event_bus.observe(
            TurnCommitted(
                session_key=session_key,
                channel="desktop",
                chat_id=session_key,
                input_message=content,
                persisted_user_message=content,
                assistant_response="收到",
                tools_used=[],
                thinking=None,
            )
        )
        return "收到"

    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(process_direct=_process_direct),
        event_bus=event_bus,
    )

    response = await service.handle(
        {
            "id": "1",
            "method": "chat.send",
            "payload": {
                "role_id": role.id,
                "content": "",
                "media": ["D:\\files\\notes.md"],
            },
        },
        emit_event=lambda payload: None,
    )

    assert response.error is None
    await _wait_until(lambda: bool(session_manager.get_or_create("role:mira").messages))
    assert session_manager.get_or_create("role:mira").messages[0]["media"] == [
        "D:\\files\\notes.md"
    ]


@pytest.mark.asyncio
async def test_desktop_bridge_chat_send_updates_presence_and_loneliness_runtime(
    tmp_path: Path,
):
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    session_manager = SessionManager(tmp_path)
    presence = PresenceStore(session_manager._store)
    relationship_runtime = RoleRelationshipRuntimeService(
        tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        presence=presence,
    )
    relationship_runtime.write_snapshot(
        role.id,
        {
            "role_id": role.id,
            "role_self_view": "我最近会忍不住去想你。",
            "relation_tags": ["亲近", "等你主动"],
            "internal_profile": {
                "relation_state": {
                    "closeness": 0.9,
                    "dependence": 0.7,
                    "security": 0.8,
                    "initiative_desire": 0.6,
                    "neglect_sensitivity": 0.4,
                },
                "behavior_profile": {
                    "loneliness_growth_base": 1.2,
                    "loneliness_growth_when_unanswered": 1.8,
                    "trigger_threshold": 60,
                    "post_trigger_cooldown_minutes": 120,
                    "night_suppression": 0.4,
                },
            },
            "source_summary": {},
            "generated_at": "2026-07-06T18:00:00+08:00",
            "last_attempted_at": "2026-07-06T18:00:00+08:00",
            "last_source_message_count": 12,
            "last_error": "",
        },
    )
    relationship_runtime.write_loneliness_runtime(
        role.id,
        {
            "role_id": role.id,
            "loneliness_value": 80,
            "last_calculated_at": "2026-07-06T18:00:00+08:00",
            "last_user_at": "",
            "last_proactive_at": "",
            "awaiting_reply_after_proactive": True,
            "awaiting_reply_since": "2026-07-06T17:00:00+08:00",
            "last_triggered_at": "",
            "cooldown_until": "",
        },
    )
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
        relationship_runtime=relationship_runtime,
        presence=presence,
    )

    response = await service.handle(
        {
            "id": "1",
            "method": "chat.send",
            "payload": {"role_id": role.id, "content": "hi"},
        },
        emit_event=lambda payload: None,
    )

    assert response.error is None
    runtime_payload = response.payload["session"]["metadata"]["loneliness_runtime"]
    assert runtime_payload["loneliness_value"] < 80
    assert runtime_payload["awaiting_reply_after_proactive"] is False
    assert runtime_payload["awaiting_reply_since"] == ""
    assert runtime_payload["last_user_at"]
    assert presence.get_last_user_at("role:mira") is not None


@pytest.mark.asyncio
async def test_desktop_bridge_chat_send_rolls_back_runtime_side_effects_when_persist_fails(
    tmp_path: Path,
):
    class _Presence:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def record_user_message(self, session_key: str) -> None:
            self.calls.append(session_key)

    class _Relationship:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def handle_user_message(self, session_key: str) -> None:
            self.calls.append(session_key)

        def enrich_session_metadata(
            self,
            metadata: dict[str, object],
        ) -> dict[str, object]:
            metadata["relationship"] = "updated"
            return metadata

    role_store = RoleStore(tmp_path)
    role = role_store.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    session_manager = SessionManager(tmp_path)
    session_manager.append_messages = AsyncMock(side_effect=RuntimeError("db down"))  # type: ignore[method-assign]
    presence = _Presence()
    relationship = _Relationship()
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
        relationship_runtime=relationship,  # type: ignore[arg-type]
        presence=presence,
    )

    response = await service.handle(
        {
            "id": "1",
            "method": "chat.send",
            "payload": {"role_id": role.id, "content": "hi"},
        },
        emit_event=lambda payload: None,
    )

    assert response.error is not None
    assert response.error.code == "internal_error"
    assert presence.calls == []
    assert relationship.calls == []
    session = session_manager.get_or_create("role:mira")
    assert session.messages == []
    assert session.metadata.get("relationship") is None


@pytest.mark.asyncio
async def test_desktop_bridge_chat_send_rejects_empty_content_and_media(tmp_path: Path):
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=SessionManager(tmp_path),
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
    )

    response = await service.handle(
        {
            "id": "1",
            "method": "chat.send",
            "payload": {"role_id": role.id, "content": "", "media": []},
        },
        emit_event=lambda payload: None,
    )

    assert response.error is not None
    assert response.error.code == "invalid_request"
    assert response.error.message == "content 和 media 不能同时为空"


@pytest.mark.asyncio
async def test_desktop_bridge_emits_session_updated_for_background_desktop_push(
    tmp_path: Path,
):
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
    assert "thread" not in emitted[0]["payload"]["session"]
    messages = emitted[0]["payload"]["session"]["messages"]
    assert messages[-1]["content"] == "主动消息"
    assert messages[-1]["metadata"]["proactive"] is True
    assert messages[-1]["metadata"]["tools_used"] == ["message_push"]
    assert session_manager.conversation_store.list_message_thread_ids("role:mira") == [
        "thread:mira:desktop"
    ]


@pytest.mark.asyncio
async def test_desktop_bridge_push_rolls_back_runtime_side_effects_when_persist_fails(
    tmp_path: Path,
):
    class _Presence:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def record_proactive_sent(self, session_key: str) -> None:
            self.calls.append(session_key)

    class _Relationship:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def handle_proactive_sent(self, session_key: str) -> None:
            self.calls.append(session_key)

        def enrich_session_metadata(
            self,
            metadata: dict[str, object],
        ) -> dict[str, object]:
            metadata["relationship"] = "updated"
            return metadata

    role_store = RoleStore(tmp_path)
    role = role_store.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    session_manager = SessionManager(tmp_path)
    session_manager.save_async = AsyncMock(side_effect=RuntimeError("db down"))  # type: ignore[method-assign]
    push_tool = MessagePushTool()
    presence = _Presence()
    relationship = _Relationship()
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
        push_tool=push_tool,
        relationship_runtime=relationship,  # type: ignore[arg-type]
        presence=presence,
    )

    result = await push_tool.execute(
        channel="desktop",
        chat_id=role.id,
        message="主动消息",
    )

    assert "发送失败" in result
    assert presence.calls == []
    assert relationship.calls == []
    session = session_manager.get_or_create("role:mira")
    assert session.messages == []
    assert session.metadata.get("relationship") is None


@pytest.mark.asyncio
async def test_desktop_bridge_desktop_push_does_not_duplicate_existing_proactive_message(
    tmp_path: Path,
):
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
    session.add_message(
        "assistant", "主动消息", proactive=True, tools_used=["message_push"]
    )
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
async def test_desktop_bridge_push_does_not_treat_subset_media_as_duplicate(
    tmp_path: Path,
):
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
    session.add_message(
        "assistant",
        "主动消息",
        media=["a.png", "b.png"],
        proactive=True,
        tools_used=["message_push"],
    )
    await session_manager.save_async(session)
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
    )

    updated_session = await service._apply_desktop_push(
        role.id,
        message="主动消息",
        media=["a.png"],
    )

    assert len(updated_session.messages) == 2
    assert updated_session.messages[-1]["media"] == ["a.png"]


@pytest.mark.asyncio
async def test_desktop_bridge_server_streams_requests_and_responses(tmp_path: Path):
    role_store = RoleStore(tmp_path)
    session_manager = SessionManager(tmp_path)
    event_bus = EventBus()
    runtime = SimpleNamespace(
        session_manager=SimpleNamespace(
            workspace=tmp_path, open_role_session=session_manager.open_role_session
        ),
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
async def test_desktop_bridge_server_returns_invalid_request_and_keeps_stream_open(
    tmp_path: Path,
):
    role_store = RoleStore(tmp_path)
    session_manager = SessionManager(tmp_path)
    event_bus = EventBus()
    runtime = SimpleNamespace(
        session_manager=SimpleNamespace(
            workspace=tmp_path, open_role_session=session_manager.open_role_session
        ),
        loop=SimpleNamespace(process_direct=AsyncMock(return_value="ok")),
        event_bus=event_bus,
    )
    server = DesktopBridgeServer(runtime)

    lines = iter(
        [
            '{"id":"broken"',
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

    assert writes[0]["error"]["code"] == "invalid_request"
    assert writes[0]["method"] == "invalid_request"
    assert writes[1]["method"] == "health"
    assert writes[1]["payload"] == {"ok": True}


@pytest.mark.asyncio
async def test_desktop_bridge_server_wraps_handler_errors_without_closing_stream(
    tmp_path: Path,
):
    role_store = RoleStore(tmp_path)
    session_manager = SessionManager(tmp_path)
    event_bus = EventBus()
    runtime = SimpleNamespace(
        session_manager=SimpleNamespace(
            workspace=tmp_path, open_role_session=session_manager.open_role_session
        ),
        loop=SimpleNamespace(process_direct=AsyncMock(return_value="ok")),
        event_bus=event_bus,
    )
    server = DesktopBridgeServer(runtime)
    call_count = 0

    async def _handle(request, emit_event):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("boom")
        return BridgeResponse(
            id=str(request["id"]),
            type="response",
            method=str(request["method"]),
            payload={"ok": True},
        )

    server.service.handle = _handle
    lines = iter(
        [
            json.dumps({"id": "1", "method": "health", "payload": {}}),
            json.dumps({"id": "2", "method": "health", "payload": {}}),
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

    assert writes[0]["id"] == "1"
    assert writes[0]["error"]["code"] == "internal_error"
    assert writes[1]["id"] == "2"
    assert writes[1]["payload"] == {"ok": True}


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
    assert (
        response.payload["session"]["metadata"]["active_illustration"]
        == "roles/assets/mira/illustration-1.png"
    )


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
async def test_desktop_bridge_updates_role_asset_categories_and_send_permission(tmp_path: Path):
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
            "payload": {"name": "Mira", "system_prompt": "mira"},
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
                "asset_categories": [
                    {"id": "default", "name": "默认", "allow_role_send": False},
                    {"id": "reaction", "name": "表情包", "allow_role_send": True},
                ],
                "asset_category_bindings": {},
            },
        },
        emit_event=lambda payload: None,
    )

    assert updated.error is None
    assert updated.payload["role"]["asset_categories"][1]["allow_role_send"] is True


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
async def test_desktop_bridge_role_update_selects_avatar_and_chat_background_from_library(
    tmp_path: Path,
):
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
async def test_desktop_bridge_role_update_clears_selected_slots_when_asset_removed(
    tmp_path: Path,
):
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
async def test_desktop_bridge_normalizes_stale_active_illustration_on_role_update(
    tmp_path: Path,
):
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
async def test_desktop_bridge_syncs_role_metadata_into_session_on_open_and_update(
    tmp_path: Path,
):
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
async def test_desktop_bridge_recomputes_loneliness_runtime_for_roles_and_sessions_on_read(
    tmp_path: Path,
):
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    session_manager = SessionManager(tmp_path)
    relationship_runtime = RoleRelationshipRuntimeService(
        tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        presence=SimpleNamespace(
            get_last_user_at=lambda _key: None,
            get_last_proactive_at=lambda _key: None,
        ),
    )
    relationship_runtime.write_snapshot(
        role.id,
        {
            "role_id": role.id,
            "role_self_view": "我最近会忍不住去想你。",
            "relation_tags": ["亲近", "等你主动"],
            "internal_profile": {
                "relation_state": {
                    "closeness": 0.8,
                },
                "behavior_profile": {},
            },
            "source_summary": {},
            "generated_at": "2026-07-06T18:00:00+08:00",
            "last_attempted_at": "2026-07-06T18:00:00+08:00",
            "last_error": "",
        },
    )
    stale_runtime_at = datetime.now(timezone.utc) - timedelta(minutes=21)
    relationship_runtime.write_loneliness_runtime(
        role.id,
        {
            "role_id": role.id,
            "loneliness_value": 58,
            "last_calculated_at": stale_runtime_at.isoformat(),
            "last_user_at": "",
            "last_proactive_at": "",
            "awaiting_reply_after_proactive": False,
            "awaiting_reply_since": "",
            "last_triggered_at": "",
            "cooldown_until": "",
        },
    )
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
        relationship_runtime=relationship_runtime,
    )

    roles_response = await service.handle(
        {
            "id": "1",
            "method": "roles.list",
            "payload": {},
        },
        emit_event=lambda payload: None,
    )
    session_response = await service.handle(
        {
            "id": "2",
            "method": "session.openByRole",
            "payload": {"role_id": role.id},
        },
        emit_event=lambda payload: None,
    )

    assert roles_response.error is None
    role_payload = roles_response.payload["roles"][0]
    assert (
        role_payload["relationship_snapshot"]["role_self_view"]
        == "我最近会忍不住去想你。"
    )
    assert role_payload["loneliness_runtime"]["loneliness_value"] > 58
    assert session_response.error is None
    assert (
        session_response.payload["session"]["metadata"]["relationship_snapshot"][
            "role_self_view"
        ]
        == "我最近会忍不住去想你。"
    )
    assert (
        session_response.payload["session"]["metadata"]["loneliness_runtime"][
            "loneliness_value"
        ]
        > 58
    )


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
    output_path = (
        tmp_path
        / "private_runtime"
        / "novelai"
        / "outputs"
        / "2026-06-30"
        / "rec-1"
        / "output-1.png"
    )
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
        config=SimpleNamespace(
            novelai=NovelAISettings(enabled=True, token="novel-token")
        ),
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
