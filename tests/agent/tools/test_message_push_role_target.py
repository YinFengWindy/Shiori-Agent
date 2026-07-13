from __future__ import annotations

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
