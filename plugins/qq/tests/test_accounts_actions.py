from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from plugins.qq.backend.accounts_actions import QQAccountActions
from plugins.qq.backend.onebot import OneBotError


@pytest.mark.asyncio
async def test_actions_query_fresh_lists_and_require_actual_send_receipt():
    socket = AsyncMock()
    actions = QQAccountActions(lambda account_id: socket)
    socket.call.return_value = [{"user_id": 902, "card": "群名片", "nickname": "昵称"}]
    result = await actions.discover("account-a", "members", "777")
    assert result == {
        "items": [{"id": "902", "name": "群名片"}],
        "complete": True,
        "source": "napcat",
    }
    socket.call.assert_awaited_with("get_group_member_list", {"group_id": 777})

    socket.call.return_value = {"message_id": 88}
    assert await actions.send_target("account-a", "private", "902", "hi") == {
        "message_id": "88"
    }
    socket.call.assert_awaited_with(
        "send_private_msg", {"user_id": 902, "message": "hi"}
    )

    socket.call.return_value = {}
    with pytest.raises(ValueError, match="消息回执"):
        await actions.send_target("account-a", "private", "902", "hi")
    socket.call.return_value = {"message_id": 89}
    with pytest.raises(ValueError, match="目标 ID"):
        await actions.send_target("account-a", "group", "gqq:777", "hi")


@pytest.mark.asyncio
async def test_actions_reject_invalid_directory_shape_and_propagate_api_failure():
    socket = AsyncMock()
    actions = QQAccountActions(lambda account_id: socket)
    socket.call.return_value = {"items": []}
    with pytest.raises(OneBotError, match="无效列表"):
        await actions.discover("account-a", "friends")
    socket.call.side_effect = OneBotError("NapCat get_group_list 失败")
    with pytest.raises(OneBotError, match="get_group_list"):
        await actions.discover("account-a", "groups")
