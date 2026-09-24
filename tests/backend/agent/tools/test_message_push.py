from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.tools.message_push import MessagePushTool
from core.common.runtime_scope import bind_runtime


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"message": " \t\n"},
        {"file": "   "},
        {"image": "   "},
        {"message": " ", "file": "\t", "image": "\n"},
    ],
)
async def test_blank_payload_is_rejected_before_resolving_or_sending(payload):
    tool = MessagePushTool()
    send = AsyncMock()

    def resolve(_chat_id):
        raise AssertionError("empty payload must not resolve its target")

    tool.register_channel(
        "desktop",
        text=send,
        file=send,
        image=send,
        target_resolver=resolve,
    )

    result = await tool.execute(channel="desktop", chat_id="mira", **payload)

    assert result == "错误：message、file、image 至少提供一个"
    send.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("message", "  hello\n"),
        ("file", "report with spaces.pdf"),
        ("image", "https://example.test/image.png"),
    ],
)
async def test_only_nonblank_fields_are_sent_without_changing_content(field, value):
    tool = MessagePushTool()
    senders = {name: AsyncMock() for name in ("message", "file", "image")}
    tool.register_channel(
        "desktop",
        text=senders["message"],
        file=senders["file"],
        image=senders["image"],
    )
    payload = dict.fromkeys(senders, " \t\n")
    payload[field] = value

    result = await tool.execute(channel="desktop", chat_id="mira", **payload)

    assert "已发送" in result
    for name, sender in senders.items():
        if name == field:
            sender.assert_awaited_once()
            assert sender.await_args.args[:2] == ("mira", value)
        else:
            sender.assert_not_awaited()


@pytest.mark.asyncio
async def test_retired_transport_only_sends_for_previously_accepted_generation():
    tool = MessagePushTool()
    send = AsyncMock()
    tool.register_channel("telegram", text=send)
    tool.retire_channel("telegram")
    old = SimpleNamespace(channel_names=frozenset({"telegram", "qq"}))
    new = SimpleNamespace(channel_names=frozenset({"qq"}))

    with bind_runtime(old):
        await tool.execute(channel="telegram", chat_id="one", message="accepted")
    with bind_runtime(new):
        result = await tool.execute(channel="telegram", chat_id="one", message="new")
    send.assert_awaited_once_with("one", "accepted")
    assert "已停用" in result


@pytest.mark.parametrize("sender_name", ["text", "stream_text"])
async def test_delivery_metadata_keeps_legacy_senders_compatible(sender_name):
    tool = MessagePushTool()
    sender = AsyncMock()
    tool.register_channel("telegram", **{sender_name: sender})

    result = await tool.execute(
        channel="telegram",
        chat_id="one",
        message="scheduled",
        push_delivery_key="occurrence",
        push_message_already_persisted=True,
    )

    sender.assert_awaited_once_with("one", "scheduled")
    assert "已发送" in result


async def test_metadata_sender_uses_push_identity_not_shared_turn_identity():
    tool = MessagePushTool()
    sender = AsyncMock()
    tool.register_channel("desktop", text_with_metadata=sender)

    await tool.execute(
        channel="desktop",
        chat_id="one",
        message="first",
        delivery_key="turn",
    )
    sender.assert_awaited_once_with(
        "one",
        "first",
        {
            "delivery_key": "",
            "already_persisted": False,
        },
    )

    sender.reset_mock()
    await tool.execute(
        channel="desktop",
        chat_id="one",
        message="second",
        delivery_key="turn",
        push_delivery_key="occurrence",
        push_message_already_persisted=True,
    )
    sender.assert_awaited_once_with(
        "one",
        "second",
        {
            "delivery_key": "occurrence",
            "already_persisted": True,
        },
    )


async def test_model_json_cannot_impersonate_pending_turn_delivery():
    tool = MessagePushTool()
    sender = AsyncMock()
    tool.register_channel("desktop", text_with_metadata=sender)
    await tool.execute(
        channel="desktop",
        chat_id="one",
        message="hello",
        _pending_turn_delivery=True,
        pending_commit=True,
    )
    assert "pending_commit" not in sender.await_args.args[2]


@pytest.mark.parametrize("unsupported", ["text", "file", "image"])
async def test_unsupported_payload_rejects_all_requested_sends_before_delivery(
    unsupported,
):
    tool = MessagePushTool()
    senders = {name: AsyncMock() for name in ("text", "file", "image")}
    tool.register_channel(
        "limited",
        **{name: sender for name, sender in senders.items() if name != unsupported},
    )

    result = await tool.execute(
        channel="limited",
        chat_id="one",
        message="hello",
        file="/tmp/a.txt",
        image="/tmp/a.png",
    )

    assert result.startswith("发送失败：")
    assert "已发送" not in result
    for sender in senders.values():
        sender.assert_not_awaited()


@pytest.mark.asyncio
async def test_message_push_tool_covers_success_failure_and_fallbacks():
    tool = MessagePushTool()
    sent = {"text": [], "stream_text": [], "file": [], "image": []}

    async def text(chat_id: str, message: str) -> None:
        sent["text"].append((chat_id, message))

    async def stream_text(chat_id: str, message: str) -> None:
        sent["stream_text"].append((chat_id, message))

    async def file(chat_id: str, path: str, name: str | None) -> None:
        sent["file"].append((chat_id, path, name))

    async def image(chat_id: str, path: str) -> None:
        sent["image"].append((chat_id, path))

    tool.register_channel(
        "telegram",
        text=text,
        stream_text=stream_text,
        file=file,
        image=image,
    )
    result = await tool.execute(
        channel="telegram",
        chat_id=123,
        message="hello",
        file="/tmp/demo.txt",
        image="https://img",
    )

    assert "文本已发送" in result
    assert "文件 'demo.txt' 已发送" in result
    assert "图片已发送" in result
    assert sent["text"] == []
    assert sent["stream_text"] == [("123", "hello")]
    assert sent["file"] == [("123", "/tmp/demo.txt", "demo.txt")]
    assert sent["image"] == [("123", "https://img")]

    assert await tool.execute(channel="telegram", chat_id=1) == (
        "错误：message、file、image 至少提供一个"
    )
    assert "未注册" in await tool.execute(channel="qq", chat_id=1, message="x")

    tool.register_channel("limited", text=text)
    limited = await tool.execute(
        channel="limited", chat_id=1, file="/tmp/a.txt", image="/tmp/a.png"
    )
    assert "不支持发送文件" in limited
    assert "不支持发送图片" in limited

    async def broken(chat_id: str, message: str) -> None:
        raise RuntimeError("send failed")

    tool.register_channel("broken", text=broken)
    assert "发送失败" in await tool.execute(channel="broken", chat_id=1, message="x")
