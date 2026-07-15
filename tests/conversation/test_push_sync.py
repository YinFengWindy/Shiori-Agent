from __future__ import annotations

from pathlib import Path

import pytest

from agent.lifecycle.types import AfterReasoningCtx
from agent.tools.message_push import MessagePushTool
from bus.event_bus import EventBus
from conversation.push_sync import ExternalImageSyncService
from session.manager import SessionManager


@pytest.mark.asyncio
async def test_turn_image_is_reserved_for_persistence_without_immediate_append(
    tmp_path: Path,
) -> None:
    session_manager = SessionManager(tmp_path)
    session_manager.open_role_session("mira", role_name="Mira")
    event_bus = EventBus()
    _ = ExternalImageSyncService(
        session_manager=session_manager,
        event_bus=event_bus,
    )
    push_tool = MessagePushTool(event_bus=event_bus)

    async def send_image(_chat_id: str, _image: str) -> None:
        return None

    push_tool.register_channel("telegram", image=send_image)
    image = str(tmp_path / "scene.png")

    result = await push_tool.execute(
        channel="telegram",
        chat_id="123",
        image=image,
        role_id="mira",
        session_key="role:mira",
        defer_push_session_sync="true",
    )

    assert result == "图片已发送"
    assert session_manager.get_or_create("role:mira").messages == []

    ctx = AfterReasoningCtx(
        session_key="role:mira",
        channel="telegram",
        chat_id="123",
        tools_used=("message_push",),
        thinking=None,
        response_metadata=object(),  # type: ignore[arg-type]
        streamed=False,
        tool_chain=(),
        context_retry={},
        reply="发给你了。",
    )
    updated = await event_bus.emit(ctx)

    assert updated.persisted_media == [image]
    assert updated.media == []


@pytest.mark.asyncio
async def test_pre_persisted_proactive_image_is_not_duplicated(tmp_path: Path) -> None:
    session_manager = SessionManager(tmp_path)
    session = session_manager.open_role_session("mira", role_name="Mira")
    image = str(tmp_path / "scene.png")
    session.add_message(
        "assistant",
        "给你看张图",
        media=[image],
        proactive=True,
        metadata={
            "transport_channel": "telegram",
            "transport_chat_id": "123",
        },
    )
    await session_manager.append_messages(session, session.messages[-1:])
    event_bus = EventBus()
    _ = ExternalImageSyncService(
        session_manager=session_manager,
        event_bus=event_bus,
    )
    push_tool = MessagePushTool(event_bus=event_bus)

    async def send_image(_chat_id: str, _image: str) -> None:
        return None

    push_tool.register_channel("telegram", image=send_image)

    result = await push_tool.execute(
        channel="telegram",
        chat_id="123",
        image=image,
        role_id="mira",
        session_key="role:mira",
        push_message_already_persisted="true",
    )

    assert result == "图片已发送"
    assert len(session_manager.get_or_create("role:mira").messages) == 1
