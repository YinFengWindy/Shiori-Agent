from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.channels.chat_id_command import answer_chat_id_command
from core.common.channel_chat_types import ChatTypeDeclaration

_QQ = (
    ChatTypeDeclaration("private", "私聊", "QQ 号"),
    ChatTypeDeclaration("group", "群聊", "群号", prefix="gqq:"),
)


async def _answer(hub: Any, send: AsyncMock) -> None:
    await answer_chat_id_command(
        cast(Any, hub),
        channel="qq",
        chat_id="gqq:831907794",
        chat_type="group",
        sender_id="7",
        sender_alias="troll",
        declarations=_QQ,
        send=send,
    )


@pytest.mark.asyncio
async def test_unbound_or_admitted_senders_get_the_binding_form_fields() -> None:
    hub = SimpleNamespace(is_sender_blocked=MagicMock(return_value=False))
    send = AsyncMock()

    await _answer(hub, send)
    await _answer(None, send)

    assert [call.args for call in send.await_args_list] == [
        ("会话类型：群聊\n群号：831907794",),
        ("会话类型：群聊\n群号：831907794",),
    ]
    hub.is_sender_blocked.assert_called_once_with(
        channel="qq", chat_id="gqq:831907794", sender_id="7", sender_alias="troll"
    )


@pytest.mark.asyncio
async def test_a_blacklisted_sender_gets_nothing() -> None:
    send = AsyncMock()

    await _answer(SimpleNamespace(is_sender_blocked=MagicMock(return_value=True)), send)

    send.assert_not_awaited()
