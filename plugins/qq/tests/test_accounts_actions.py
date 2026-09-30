from __future__ import annotations

import base64

from unittest.mock import AsyncMock

import pytest

from core.accounts.target_contract import AccountTarget, UncertainDeliveryError
from agent.account_delivery import AccountDelivery
from core.accounts import AccountRegistry
from core.accounts.delivery_ledger import AccountDeliveryLedger
from plugins.qq.backend.accounts_actions import (
    QQAccountActions,
    RepliedMessage,
    qq_chat_target,
)
from plugins.qq.backend.onebot import OneBotDisconnected, OneBotError
from core.identity import UserIdentityStore


# The account's QQ number and name, as merged-forward nodes are sent.
def _SENDER(account_id: str) -> tuple[str, str]:
    return "101", "米拉"


@pytest.mark.asyncio
async def test_actions_query_fresh_lists_and_require_actual_send_receipt():
    socket = AsyncMock()
    actions = QQAccountActions(lambda account_id: socket, AsyncMock(), _SENDER)
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
    with pytest.raises(UncertainDeliveryError, match="有效回执"):
        await actions.send_target("account-a", "private", "902", "hi")
    socket.call.return_value = {"message_id": 89}
    with pytest.raises(ValueError, match="目标 ID"):
        await actions.send_target("account-a", "group", "gqq:777", "hi")


@pytest.mark.asyncio
async def test_group_name_comes_from_napcat_group_info():
    socket = AsyncMock()
    actions = QQAccountActions(lambda account_id: socket, AsyncMock(), _SENDER)
    socket.call.return_value = {"group_id": 777, "group_name": "读书会"}
    assert await actions.group_name("account-a", "777") == "读书会"
    socket.call.assert_awaited_with("get_group_info", {"group_id": 777})

    socket.call.return_value = {"group_id": 777}
    with pytest.raises(OneBotError, match="未返回群名"):
        await actions.group_name("account-a", "777")


@pytest.mark.asyncio
async def test_group_mentions_and_temporary_sessions_use_napcat_targets():
    socket = AsyncMock()
    socket.call.return_value = {"message_id": 90}
    actions = QQAccountActions(lambda account_id: socket, AsyncMock(), _SENDER)

    await actions.send_target(
        "account-a", "group", "777", "开会", mention_ids=("902", "903")
    )
    socket.call.assert_awaited_with(
        "send_group_msg",
        {"group_id": 777, "message": "[CQ:at,qq=902] [CQ:at,qq=903] 开会"},
    )
    await actions.send_target("account-a", "group_member", "902", "hi", group_id="777")
    socket.call.assert_awaited_with(
        "send_private_msg", {"user_id": 902, "group_id": 777, "message": "hi"}
    )

    sends = socket.call.await_count
    with pytest.raises(ValueError, match="只有群消息"):
        await actions.send_target(
            "account-a", "private", "902", "hi", mention_ids=("1",)
        )
    with pytest.raises(ValueError, match="群号"):
        await actions.send_target("account-a", "group_member", "902", "hi")
    with pytest.raises(ValueError, match="@ 成员"):
        await actions.send_target("account-a", "group", "777", "hi", mention_ids=("x",))
    assert socket.call.await_count == sends


@pytest.mark.asyncio
async def test_images_follow_the_text_in_one_napcat_message(tmp_path):
    socket = AsyncMock()
    socket.call.return_value = {"message_id": 91}
    actions = QQAccountActions(lambda account_id: socket, AsyncMock(), _SENDER)
    image = tmp_path / "sky.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    encoded = base64.b64encode(image.read_bytes()).decode("ascii")

    receipt = await actions.send_target(
        "account-a",
        "private",
        "902",
        "看天空",
        images=(str(image), "https://x.test/a.png?w=1,h=2"),
    )
    assert receipt == {"message_id": "91"}
    socket.call.assert_awaited_once_with(
        "send_private_msg",
        {
            "user_id": 902,
            "message": f"看天空[CQ:image,file=base64://{encoded}]"
            "[CQ:image,file=https://x.test/a.png?w=1&#44;h=2]",
        },
    )
    await actions.send_target("account-a", "private", "902", "", images=(str(image),))
    socket.call.assert_awaited_with(
        "send_private_msg",
        {"user_id": 902, "message": f"[CQ:image,file=base64://{encoded}]"},
    )
    assert socket.call.await_count == 2


@pytest.mark.asyncio
async def test_long_group_text_sends_mentions_then_one_merged_forward(tmp_path):
    socket = AsyncMock()
    socket.call.side_effect = [
        {"message_id": 70},
        {"message_id": 71, "res_id": "r", "forward_id": "r"},
    ]
    actions = QQAccountActions(lambda account_id: socket, AsyncMock(), _SENDER)
    image = tmp_path / "sky.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    encoded = base64.b64encode(image.read_bytes()).decode("ascii")
    text = "第一段" + "字" * 300 + "\n\n第二段\n续行"

    receipt = await actions.send_target(
        "account-a",
        "group",
        "777",
        text,
        mention_ids=("902", "903"),
        images=(str(image),),
    )
    assert receipt == {"message_id": "71"}

    def node(content):
        return {
            "type": "node",
            "data": {"user_id": "101", "nickname": "米拉", "content": content},
        }

    assert [c.args for c in socket.call.await_args_list] == [
        (
            "send_group_msg",
            {"group_id": 777, "message": "[CQ:at,qq=902] [CQ:at,qq=903]"},
        ),
        (
            "send_group_forward_msg",
            {
                "group_id": 777,
                "messages": [
                    node("第一段" + "字" * 300),
                    node(f"第二段\n续行[CQ:image,file=base64://{encoded}]"),
                ],
            },
        ),
    ]


@pytest.mark.asyncio
async def test_many_line_private_text_is_one_merged_forward():
    socket = AsyncMock()
    socket.call.return_value = {"message_id": 72}
    actions = QQAccountActions(lambda account_id: socket, AsyncMock(), _SENDER)
    text = "\n".join(str(line) for line in range(11))

    assert await actions.send_target("account-a", "private", "902", text) == {
        "message_id": "72"
    }
    socket.call.assert_awaited_once_with(
        "send_private_forward_msg",
        {
            "user_id": 902,
            "messages": [
                {
                    "type": "node",
                    "data": {"user_id": "101", "nickname": "米拉", "content": text},
                }
            ],
        },
    )


@pytest.mark.asyncio
async def test_invalid_local_image_is_refused_before_any_send(tmp_path):
    socket = AsyncMock()
    actions = QQAccountActions(lambda account_id: socket, AsyncMock(), _SENDER)
    not_image = tmp_path / "note.png"
    not_image.write_text("plain text", encoding="utf-8")
    with pytest.raises(ValueError, match="图片文件不存在"):
        await actions.send_target(
            "account-a", "private", "902", "hi", images=(str(tmp_path / "gone.png"),)
        )
    with pytest.raises(ValueError, match="图片仅支持"):
        await actions.send_target(
            "account-a", "private", "902", "hi", images=(str(not_image),)
        )
    socket.call.assert_not_awaited()


@pytest.mark.asyncio
async def test_actions_reject_invalid_directory_shape_and_propagate_api_failure():
    socket = AsyncMock()
    actions = QQAccountActions(lambda account_id: socket, AsyncMock(), _SENDER)
    socket.call.return_value = {"items": []}
    with pytest.raises(OneBotError, match="无效列表"):
        await actions.discover("account-a", "friends")
    socket.call.side_effect = OneBotError("NapCat get_group_list 失败")
    with pytest.raises(OneBotError, match="get_group_list"):
        await actions.discover("account-a", "groups")


@pytest.mark.asyncio
async def test_disconnect_is_pending_but_onebot_rejection_is_failed(tmp_path):
    accounts = AccountRegistry(lambda role_id: role_id == "mira")
    account = accounts.register(
        plugin_id="qq",
        platform="qq",
        platform_account_id="101",
        config_ref="bot",
        token="live",
        role_id="mira",
    )
    account_id = account.record.id
    accounts.report(account_id, "live", connection="online")
    socket = AsyncMock()
    actions = QQAccountActions(lambda selected: socket, AsyncMock(), _SENDER)

    async def send(payload):
        return await actions.send_target(
            payload["account_id"],
            payload["target_kind"],
            payload["target_id"],
            payload["message"],
        )

    target = AccountTarget("private", "901")

    rpc = type("Rpc", (), {"resolve": lambda self, name: ("qq", send)})()
    ledger = AccountDeliveryLedger(tmp_path)
    delivery = AccountDelivery(accounts, rpc, ledger, UserIdentityStore(tmp_path))
    socket.call.side_effect = OneBotDisconnected("NapCat WebSocket 已断开")
    with pytest.raises(UncertainDeliveryError):
        await delivery.send("qq", "mira", target, "hi")
    socket.call.side_effect = OneBotError("NapCat send_private_msg 失败: denied")
    with pytest.raises(OneBotError, match="denied"):
        await delivery.send("qq", "mira", target, "hi")

    attempts = AccountDeliveryLedger(tmp_path).list_for_role("mira")
    assert [(row.status, row.error) for row in attempts] == [
        ("pending", "UncertainDeliveryError"),
        ("failed", "OneBotError"),
    ]


def test_chat_target_preserves_qq_private_and_group_namespaces():
    assert qq_chat_target("901") == ("private", "901")
    assert qq_chat_target("gqq:777") == ("group", "777")
    with pytest.raises(ValueError, match="群号"):
        qq_chat_target("gqq:bad")


@pytest.mark.asyncio
async def test_replied_message_comes_from_one_napcat_get_msg():
    socket = AsyncMock()
    actions = QQAccountActions(lambda account_id: socket, AsyncMock(), _SENDER)
    socket.call.return_value = {
        "message_id": -35,
        "sender": {"user_id": 202, "nickname": "阿花", "card": ""},
        "raw_message": "[CQ:image,url=https://x/a.png]看这个",
    }
    assert await actions.replied_message("account-a", "-35") == RepliedMessage(
        sender_id="202",
        sender_name="阿花",
        raw_content="[CQ:image,url=https://x/a.png]看这个",
    )
    socket.call.assert_awaited_once_with("get_msg", {"message_id": -35})

    socket.call.return_value = {"message_id": -35}
    with pytest.raises(OneBotError, match="未返回发送者"):
        await actions.replied_message("account-a", "-35")
