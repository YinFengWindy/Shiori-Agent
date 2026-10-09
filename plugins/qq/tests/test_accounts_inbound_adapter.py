from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from shiori_sdk.testing.channel_context import fake_channel_context
from shiori_sdk.testing.channel_hub import FakeChannelHub
from shiori_sdk.testing.channel_services import FakeMessageBus
from shiori_sdk.testing.http import FakeChannelHttp, FakeHttp, FakeHttpResources

import plugins.qq.backend.accounts_inbound_adapter as inbound_adapter
from plugins.qq.backend.accounts_actions import RepliedMessage
from plugins.qq.backend.accounts_inbound import inbound_message
from plugins.qq.backend.accounts_inbound_adapter import QQInboundAdapter
from plugins.qq.backend.accounts_group_names import QQGroupNames
from plugins.qq.backend.accounts_store import QQConnectionConfig
from plugins.qq.backend.onebot import OneBotError
from websockets.exceptions import ConnectionClosed


def _actions(**actions: object) -> SimpleNamespace:
    """NapCat actions; a message without a reply segment never asks for its reply."""
    return SimpleNamespace(**{"replied_message": AsyncMock(), **actions})


def _adapter() -> QQInboundAdapter:
    adapter = QQInboundAdapter()
    adapter._http = FakeHttp()
    adapter._actions = _actions()
    return adapter


def _group_message(mentioned: bool):
    raw = "[CQ:at,qq=202] hello" if mentioned else "hello"
    message = inbound_message(
        account_id="account-b",
        expected_uin="202",
        via_account=QQConnectionConfig(
            ref="b", ws_uri="ws://127.0.0.1:1", ws_token="t", expected_uin="202"
        ).via_account(),
        event={
            "post_type": "message",
            "message_type": "group",
            "self_id": 202,
            "group_id": 777,
            "user_id": 902,
            "raw_message": raw,
        },
    )
    assert message is not None
    return message


@pytest.mark.asyncio
async def test_account_router_receives_unmentioned_group_before_host_policy(
    tmp_path: Path,
):
    adapter = _adapter()
    adapter._group_names = QQGroupNames(AsyncMock(return_value="读书会"))
    bus, hub = FakeMessageBus(), FakeChannelHub(platform_account_id="202")
    adapter._ctx = fake_channel_context(tmp_path, bus=bus, channel_hub=hub)
    await adapter._accept_inbound(_group_message(False))
    # The plugin does not filter it; the host's group policy starts no turn.
    assert [message.metadata["mentioned"] for message in hub.offered] == [False]
    assert bus.inbound == []


@pytest.mark.asyncio
async def test_account_router_can_reject_a_mentioned_group_message(
    tmp_path: Path,
):
    adapter = _adapter()
    adapter._group_names = QQGroupNames(AsyncMock(return_value="读书会"))
    bus, hub = FakeMessageBus(), FakeChannelHub(allowed=False)
    adapter._ctx = fake_channel_context(tmp_path, bus=bus, channel_hub=hub)
    await adapter._accept_inbound(_group_message(True))
    assert len(hub.offered) == 1
    assert bus.inbound == []


@pytest.mark.asyncio
async def test_account_router_rejection_fetches_no_image(monkeypatch, tmp_path: Path):
    adapter = _adapter()
    adapter._group_names = QQGroupNames(AsyncMock(return_value="读书会"))
    bus, hub = FakeMessageBus(), FakeChannelHub(platform_account_id="202")
    download = AsyncMock()
    monkeypatch.setattr(inbound_adapter, "download_to_temp", download)
    adapter._ctx = fake_channel_context(tmp_path, bus=bus, channel_hub=hub)
    message = _group_message(False)
    message.content = "[CQ:image,url=https://example.com/private.png]"
    await adapter._accept_inbound(message)
    [offered] = hub.offered
    assert offered.metadata["account_id"] == "account-b"
    assert offered.metadata["mentioned"] is False
    # A picture alone is handed over as a line of text, for listening.
    assert offered.content == "[图片]"
    download.assert_not_awaited()
    assert bus.inbound == []


def _private_message(content: str, **event: object):
    message = inbound_message(
        account_id="account-b",
        expected_uin="202",
        via_account=QQConnectionConfig(
            ref="b", ws_uri="ws://127.0.0.1:1", ws_token="t", expected_uin="202"
        ).via_account(),
        event={
            "post_type": "message",
            "message_type": "private",
            "self_id": 202,
            "user_id": 902,
            "raw_message": content,
            **event,
        },
    )
    assert message is not None
    return message


@pytest.mark.asyncio
async def test_private_pairing_code_binds_with_platform_scope_and_is_confirmed(
    tmp_path: Path,
):
    adapter = _adapter()
    adapter._group_names = QQGroupNames(AsyncMock(return_value="读书会"))
    bus = FakeMessageBus()
    hub = FakeChannelHub(pairing_code="PAIR1234")
    adapter._actions = _actions(send_target=AsyncMock(return_value={"message_id": "9"}))
    adapter._ctx = fake_channel_context(tmp_path, bus=bus, channel_hub=hub)
    await adapter._accept_inbound(_private_message("PAIR1234"))
    await adapter._accept_inbound(_private_message("你好"))
    # A group message is never offered as a pairing code.
    await adapter._accept_inbound(_group_message(True))

    assert hub.pairings == [
        ("902", "PAIR1234", "platform"),
        ("902", "你好", "platform"),
    ]
    adapter._actions.send_target.assert_awaited_once_with(
        "account-b", "private", "902", "已绑定"
    )
    assert [message.content for message in bus.inbound] == ["你好", "hello"]


@pytest.mark.asyncio
async def test_group_temporary_session_cannot_pair(tmp_path: Path):
    adapter = _adapter()
    bus, hub = FakeMessageBus(), FakeChannelHub(pairing_code="PAIR1234")
    adapter._actions = _actions(send_target=AsyncMock())
    adapter._ctx = fake_channel_context(tmp_path, bus=bus, channel_hub=hub)

    await adapter._accept_inbound(
        _private_message("PAIR1234", sub_type="group", group_id=777)
    )

    assert hub.pairings == []
    adapter._actions.send_target.assert_not_awaited()
    assert [message.content for message in bus.inbound] == ["PAIR1234"]


@pytest.mark.asyncio
async def test_group_message_carries_the_group_name_to_the_host(tmp_path: Path):
    adapter = _adapter()
    fetch = AsyncMock(return_value="读书会")
    adapter._group_names = QQGroupNames(fetch)
    hub = FakeChannelHub()
    routed = hub.offered
    adapter._ctx = fake_channel_context(tmp_path, channel_hub=hub)

    await adapter._accept_inbound(_group_message(True))
    await adapter._accept_inbound(_group_message(True))

    assert [message.metadata["group_name"] for message in routed] == ["读书会"] * 2
    fetch.assert_awaited_once_with("account-b", "777")
    await adapter._accept_inbound(_private_message("你好"))
    assert "group_name" not in routed[-1].metadata


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        # ``_socket_for`` when the account has no live socket.
        OneBotError("QQ 账号不在线"),
        # ``OneBotSocket.call`` when the socket closes while sending.
        ConnectionClosed(None, None),
        TimeoutError(),
    ],
)
async def test_group_message_is_routed_without_a_name_when_lookup_fails(
    caplog, failure, tmp_path: Path
):
    adapter = _adapter()
    adapter._group_names = QQGroupNames(AsyncMock(side_effect=failure))
    bus = FakeMessageBus()
    adapter._ctx = fake_channel_context(tmp_path, bus=bus)

    await adapter._accept_inbound(_group_message(True))

    [published] = bus.inbound
    assert "group_name" not in published.metadata
    assert "名称查询失败" in caplog.text


@pytest.mark.asyncio
async def test_group_reply_target_reaches_the_host_and_leaves_the_text(
    tmp_path: Path,
):
    adapter = _adapter()
    adapter._group_names = QQGroupNames(AsyncMock(return_value="读书会"))
    adapter._actions = _actions(
        replied_message=AsyncMock(return_value=RepliedMessage("202", "Mira", "早"))
    )
    hub = FakeChannelHub(platform_account_id="202")
    routed = hub.offered
    adapter._ctx = fake_channel_context(tmp_path, channel_hub=hub)

    message = _group_message(False)
    message.content = "[CQ:reply,id=-35] 是这样吗"
    await adapter._accept_inbound(message)

    adapter._actions.replied_message.assert_awaited_once_with("account-b", "-35")
    assert routed[0].metadata["reply_to_sender_id"] == "202"
    # The host is handed the cleaned text: what it keeps for a turn or for
    # the group's listening records (#538) carries no CQ codes, nor the quote.
    assert routed[0].content == "是这样吗"
    assert "reply_to_content" not in routed[0].metadata


@pytest.mark.asyncio
async def test_received_message_refreshes_its_sender_and_group_avatars(
    tmp_path: Path,
):
    adapter = _adapter()
    adapter._avatars = Mock(refresh=Mock(return_value=None))
    adapter._group_names = QQGroupNames(AsyncMock(return_value="读书会"))
    adapter._ctx = fake_channel_context(tmp_path)

    await adapter._accept_inbound(_group_message(True))

    assert {call.args[:3] for call in adapter._avatars.refresh.call_args_list} == {
        ("sender", "qq", "902"),
        ("chat", "qq", "gqq:777"),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("heard", [True, False])
async def test_only_a_listened_group_message_refreshes_avatars(
    heard: bool, tmp_path: Path
):
    adapter = _adapter()
    adapter._avatars = Mock(refresh=Mock(return_value=None))
    adapter._group_names = QQGroupNames(AsyncMock(return_value="读书会"))
    bus = FakeMessageBus()
    # 宿主把存进旁听记录的消息交给 on_heard；未开旁听而丢弃的不交。
    hub = FakeChannelHub(platform_account_id="202", listening=heard)
    adapter._ctx = fake_channel_context(tmp_path, bus=bus, channel_hub=hub)

    await adapter._accept_inbound(_group_message(False))

    refreshed = {call.args[:3] for call in adapter._avatars.refresh.call_args_list}
    assert refreshed == (
        {("sender", "qq", "902"), ("chat", "qq", "gqq:777")} if heard else set()
    )
    assert bus.inbound == []


@pytest.mark.asyncio
async def test_quote_of_a_turn_reaches_the_role_but_the_stored_text_stays_its_own(
    monkeypatch, tmp_path: Path
):
    adapter = _adapter()
    adapter._group_names = QQGroupNames(AsyncMock(return_value="读书会"))
    adapter._actions = _actions(
        replied_message=AsyncMock(
            return_value=RepliedMessage(
                "303",
                "阿花",
                "[CQ:reply,id=-9][CQ:at,qq=202] 看[CQ:image,url=https://x/q.png]",
            )
        )
    )
    bus = FakeMessageBus()
    profile = FakeChannelHttp(lambda _request: httpx.Response(200))
    downloads = []

    async def download(urls, http, store):
        downloads.append((http, store))
        return [url.replace("https://x/", "D:/att/") for url in urls]

    monkeypatch.setattr(inbound_adapter, "download_to_temp", download)
    adapter._ctx = fake_channel_context(
        tmp_path,
        bus=bus,
        http_resources=FakeHttpResources(external_default=profile),
    )

    message = _group_message(True)
    message.content = (
        "[CQ:reply,id=-35][CQ:at,qq=202] 这是啥[CQ:image,url=https://x/own.png]"
    )
    await adapter._accept_inbound(message)

    [turn] = bus.inbound
    # Downloads use the host's external profile and attachment store.
    assert {http for http, _store in downloads} == {profile}
    assert {_store for _http, _store in downloads} == {adapter._ctx.attachment_store}
    # The quoted text loses its CQ codes (no nested reply, no @); its picture
    # is downloaded and joins the turn ahead of the message's own. Wrapping
    # the text is the host's (``with_reply_quote``).
    assert turn.metadata["reply_to_content"] == "看"
    assert turn.metadata["reply_to_media"] == ["D:/att/q.png"]
    assert turn.media == ["D:/att/q.png", "D:/att/own.png"]
    assert turn.metadata["persisted_user_content"] == "这是啥"
    assert "来自 阿花（ID 303）" in turn.content


@pytest.mark.asyncio
async def test_private_reply_that_cannot_be_fetched_passes_without_a_quote(
    caplog, tmp_path: Path
):
    adapter = _adapter()
    adapter._actions = _actions(
        replied_message=AsyncMock(side_effect=OneBotError("消息不存在"))
    )
    bus = FakeMessageBus()
    adapter._ctx = fake_channel_context(tmp_path, bus=bus)

    await adapter._accept_inbound(_private_message("[CQ:reply,id=-35]你好"))

    [published] = bus.inbound
    assert published.content == "你好"
    assert "reply_to_sender_id" not in published.metadata
    assert "查询失败" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("private", [False, True])
async def test_direct_and_quoted_text_files_join_current_turn_after_admission(
    tmp_path, private
):
    adapter = _adapter()
    adapter._group_names = QQGroupNames(AsyncMock(return_value="读书会"))
    adapter._actions = _actions(
        replied_message=AsyncMock(
            return_value=RepliedMessage(
                "303",
                "阿花",
                "[CQ:file,name=引用.txt,url=https://x/quote]",
            )
        )
    )
    bus = FakeMessageBus()
    http = FakeChannelHttp(
        lambda request: httpx.Response(
            200,
            content=(
                b"image"
                if request.url.path == "/own.png"
                else "中文正文\n续文".encode()
            ),
            headers={
                "content-type": (
                    "image/png"
                    if request.url.path.endswith(".png")
                    else "application/octet-stream"
                )
            },
        )
    )
    adapter._ctx = fake_channel_context(
        tmp_path,
        bus=bus,
        http_resources=FakeHttpResources(external_default=http),
    )
    message = _private_message("") if private else _group_message(True)
    message.content = (
        "[CQ:reply,id=35][CQ:at,qq=202]分析"
        "[CQ:image,url=https://x/own.png][CQ:file,name=自己的.md,url=https://x/own]"
    )
    await adapter._accept_inbound(message)
    [turn] = bus.inbound
    assert [Path(path).suffix for path in turn.media] == [".txt", ".png", ".md"]
    assert Path(turn.media[0]).read_text(encoding="utf-8") == "中文正文\n续文"
    assert turn.metadata["reply_to_media"] == turn.media[:1]
    assert turn.metadata["reply_to_content"] == "[文件：引用.txt]"
    assert turn.metadata["text_attachment_tool"] == "read_attachment"
    assert "文件" in turn.content and "1 张图片" not in turn.content
    assert "自己的.md" in turn.metadata["persisted_user_content"]


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["listened", "rejected", "duplicate"])
async def test_files_are_not_downloaded_for_unadmitted_or_duplicate_messages(
    tmp_path, decision
):
    adapter = _adapter()
    adapter._group_names = QQGroupNames(AsyncMock(return_value="读书会"))
    bus = FakeMessageBus()
    http = FakeChannelHttp(lambda _: httpx.Response(200, content=b"text"))
    hub = FakeChannelHub(
        platform_account_id="202", listening=True, allowed=decision != "rejected"
    )
    adapter._ctx = fake_channel_context(
        tmp_path,
        bus=bus,
        channel_hub=hub,
        http_resources=FakeHttpResources(external_default=http),
    )
    message = _group_message(decision != "listened")
    message.metadata["external_message_id"] = "456"
    message.content = "[CQ:file,name=附件.txt,url=https://x/file]"
    await adapter._accept_inbound(message)
    initial = len(http.requests)
    if decision == "duplicate":
        assert initial == 1
        await adapter._accept_inbound(message)
    else:
        assert initial == 0 and not bus.inbound
    assert len(http.requests) == initial
    assert "附件.txt" in hub.offered[-1].content


@pytest.mark.asyncio
async def test_quoted_file_download_failure_is_visible_and_not_an_attachment(tmp_path):
    adapter = _adapter()
    adapter._actions = _actions(
        replied_message=AsyncMock(
            return_value=RepliedMessage(
                "303",
                "阿花",
                "[CQ:file,name=引用.txt,url=https://x/quote]",
            )
        )
    )
    bus = FakeMessageBus()
    adapter._ctx = fake_channel_context(
        tmp_path,
        bus=bus,
        http_resources=FakeHttpResources(
            external_default=FakeChannelHttp(lambda _: httpx.Response(404)),
        ),
    )
    await adapter._accept_inbound(_private_message("[CQ:reply,id=35]请阅读"))
    [turn] = bus.inbound
    assert (
        turn.media == [] and "HTTP 404" in turn.content and "未接收正文" in turn.content
    )
