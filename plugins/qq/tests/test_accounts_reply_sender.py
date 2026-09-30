from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from bus.events import InboundMessage
from plugins.qq.backend.accounts_reply_sender import with_reply_sender
from plugins.qq.backend.onebot import OneBotError


def _group_reply() -> InboundMessage:
    return InboundMessage(
        channel="qq",
        sender="902",
        chat_id="gqq:777",
        content="[CQ:reply,id=-35] 是这样吗",
        metadata={"account_id": "account-b", "chat_type": "group"},
    )


@pytest.mark.asyncio
async def test_reply_target_is_the_sender_napcat_reports():
    fetch = AsyncMock(return_value="202")
    message = await with_reply_sender(_group_reply(), fetch)
    fetch.assert_awaited_once_with("account-b", "-35")
    assert message.metadata["reply_to_sender_id"] == "202"


@pytest.mark.asyncio
async def test_failed_lookup_keeps_the_message_without_a_reply_target(caplog):
    fetch = AsyncMock(side_effect=OneBotError("消息不存在"))
    message = await with_reply_sender(_group_reply(), fetch)
    assert "reply_to_sender_id" not in message.metadata
    assert "发送者查询失败" in caplog.text
