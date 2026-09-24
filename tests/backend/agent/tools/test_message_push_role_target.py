from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from agent.tools.message_push import MessagePushTool


@pytest.mark.asyncio
async def test_message_push_rejects_role_target_not_owned_by_role() -> None:
    tool = MessagePushTool()
    tool.set_role_target_validator(
        lambda role_id, channel, chat_id: (role_id, channel, chat_id)
        == ("mira", "telegram", "123")
    )

    with pytest.raises(PermissionError, match="未绑定目标渠道"):
        await tool.execute(
            channel="telegram",
            chat_id="456",
            message="hello",
            role_id="mira",
        )


@pytest.mark.asyncio
async def test_message_push_allows_the_role_owned_target() -> None:
    sent: list[tuple[str, str]] = []
    tool = MessagePushTool()
    tool.set_role_target_validator(
        lambda role_id, channel, chat_id: (role_id, channel, chat_id)
        == ("mira", "telegram", "123")
    )

    async def send(chat_id: str, message: str) -> None:
        sent.append((chat_id, message))

    tool.register_channel("telegram", text=send)
    result = await tool.execute(
        channel="telegram",
        chat_id="123",
        message="hello",
        role_id="mira",
    )

    assert result == "文本已发送"
    assert sent == [("123", "hello")]


@pytest.mark.asyncio
async def test_message_push_resolves_target_before_role_validation() -> None:
    sent: list[tuple[str, str]] = []
    tool = MessagePushTool()
    tool.set_role_target_validator(
        lambda role_id, channel, chat_id: (role_id, channel, chat_id)
        == ("mira", "telegram", "7602298892")
    )

    async def send(chat_id: str, message: str) -> None:
        sent.append((chat_id, message))

    tool.register_channel(
        "telegram",
        text=send,
        target_resolver=lambda chat_id: (
            "7602298892" if chat_id.lstrip("@").lower() == "windy" else chat_id
        ),
    )
    result = await tool.execute(
        channel="telegram",
        chat_id="@Windy",
        message="hello",
        role_id="mira",
    )

    assert result == "文本已发送"
    assert sent == [("7602298892", "hello")]


def test_message_push_description_lists_only_registered_channels() -> None:
    tool = MessagePushTool()
    send = AsyncMock()
    tool.register_channel("desktop", text=send, description="桌面端")
    tool.register_channel("qqbot", text=send, description="官方 QQBot，不能写成 qq")
    tool.register_channel("plain", text=send)

    assert (
        "当前可用渠道：desktop（桌面端）、qqbot（官方 QQBot，不能写成 qq）、plain。"
        in (tool.description)
    )
    assert "telegram" not in tool.description
    assert tool.to_schema()["function"]["description"] == tool.description

    tool.retire_channel("plain")
    assert "plain" not in tool.description
    tool.unregister_channel("qqbot")
    assert "qqbot" not in tool.description
    tool.register_channel("qqbot", text=send)
    assert "qqbot。" in tool.description


@pytest.mark.asyncio
async def test_message_push_does_not_treat_qq_as_qqbot() -> None:
    sent: list[tuple[str, str]] = []
    tool = MessagePushTool()
    tool.set_role_target_validator(
        lambda role_id, channel, chat_id: (role_id, channel, chat_id)
        == ("yinfeng", "qqbot", "c2c:user-1")
    )

    async def send(chat_id: str, message: str) -> None:
        sent.append((chat_id, message))

    tool.register_channel("qqbot", text=send)

    with pytest.raises(PermissionError, match="未绑定目标渠道: qq:"):
        await tool.execute(
            channel="qq",
            chat_id="c2c:user-1",
            message="hello",
            role_id="yinfeng",
        )

    result = await tool.execute(
        channel="qqbot",
        chat_id="c2c:user-1",
        message="hello",
        role_id="yinfeng",
    )
    assert result == "文本已发送"
    assert sent == [("c2c:user-1", "hello")]


@pytest.mark.asyncio
async def test_message_push_sends_text_when_channel_only_registers_stream_sender() -> (
    None
):
    sent: list[tuple[str, str]] = []
    tool = MessagePushTool()

    async def send_stream(chat_id: str, message: str) -> None:
        sent.append((chat_id, message))

    tool.register_channel("qqbot", stream_text=send_stream)

    result = await tool.execute(
        channel="qqbot",
        chat_id="c2c:user-1",
        message="主动推送",
    )

    assert result == "文本已发送"
    assert sent == [("c2c:user-1", "主动推送")]


@pytest.mark.asyncio
async def test_message_push_surfaces_actionable_role_target_error() -> None:
    tool = MessagePushTool()
    tool.set_role_target_validator(
        lambda _role_id, _channel, _chat_id: (
            "角色未绑定 qq；该会话已绑定渠道 qqbot，请使用 channel=qqbot"
        )
    )

    with pytest.raises(PermissionError, match="请使用 channel=qqbot"):
        await tool.execute(
            channel="qq",
            chat_id="c2c:user-1",
            message="hello",
            role_id="yinfeng",
        )
