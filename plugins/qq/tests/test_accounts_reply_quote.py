from unittest.mock import AsyncMock

import pytest

from plugins.qq.backend.accounts_actions import RepliedMessage
from plugins.qq.backend.accounts_reply_quote import with_replied_message
from shiori_sdk.messages import InboundMessage


@pytest.mark.asyncio
async def test_reply_from_another_group_cannot_grant_quoted_files():
    message = InboundMessage(
        channel="qq",
        sender="902",
        chat_id="gqq:777",
        content="[CQ:reply,id=35]",
        metadata={"account_id": "account-a"},
    )
    reply = RepliedMessage(
        "303", "other", "[CQ:file,name=a.txt,url=https://x/file]", "gqq:888"
    )
    routed, quoted = await with_replied_message(message, AsyncMock(return_value=reply))
    assert quoted is None and "reply_to_sender_id" not in routed.metadata
