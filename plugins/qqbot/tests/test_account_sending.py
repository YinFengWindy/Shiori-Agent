from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from plugins.qqbot.backend.account_sending import _AccountSendingMixin
from shiori_sdk.accounts.targets import UncertainDeliveryError


def _png(tmp_path) -> str:
    """A real PNG file on disk, as a local image path."""
    path = tmp_path / "sky.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"body")
    return str(path)


class _Sending(_AccountSendingMixin):
    def __init__(self, channel):
        self._channels = {"100": channel}
        self._identity = SimpleNamespace(
            app_for_account=lambda payload: (
                "100" if payload["account_id"] == "account-100" else None
            ),
            via_account=lambda app_id: {"platform_account_id": app_id},
        )


@pytest.mark.asyncio
async def test_send_returns_official_receipt_from_selected_application():
    sent = []

    async def send(chat_id, content):
        sent.append((chat_id, content))
        return "platform-message-id"

    channel = SimpleNamespace(_chat_id=lambda openid: f"c2c:100:{openid}", send=send)
    result = await _Sending(channel).send_target(
        {"account_id": "account-100", "user_openid": "opaque", "content": "hello"}
    )
    assert result == {
        "message_id": "platform-message-id",
        "chat_id": "c2c:100:opaque",
    }
    assert sent == [("c2c:100:opaque", "hello")]

    shared = await _Sending(channel).account_send(
        {
            "account_id": "account-100",
            "target_kind": "private",
            "target_id": "opaque",
            "message": "again",
        }
    )
    assert shared["message_id"] == "platform-message-id"
    assert shared["via_account"] == {"platform_account_id": "100"}
    assert sent[-1] == ("c2c:100:opaque", "again")
    legacy = await _Sending(channel).account_send(
        {"account_id": "account-100", "user_openid": "opaque", "content": "old"}
    )
    assert legacy["message_id"] == "platform-message-id"
    assert sent[-1] == ("c2c:100:opaque", "old")
    with pytest.raises(ValueError, match="私聊"):
        await _Sending(channel).account_send(
            {"account_id": "account-100", "target_kind": "group"}
        )
    # No group chats: mentions and group temporary sessions are refused clearly.
    with pytest.raises(ValueError, match="不支持 @ 成员"):
        await _Sending(channel).account_send(
            {"account_id": "account-100", "target_kind": "group", "mention_ids": ["1"]}
        )
    with pytest.raises(ValueError, match="群临时会话"):
        await _Sending(channel).account_send(
            {"account_id": "account-100", "target_kind": "group_member"}
        )
    assert len(sent) == 3


@pytest.mark.asyncio
async def test_send_reports_platform_failure_reason():
    request = httpx.Request(
        "POST", "https://api.sgroup.qq.com/v2/users/opaque/messages"
    )
    response = httpx.Response(
        403, json={"message": "target unavailable"}, request=request
    )

    async def denied(chat_id, content):
        raise httpx.HTTPStatusError("rejected", request=request, response=response)

    channel = SimpleNamespace(_chat_id=lambda openid: f"c2c:100:{openid}", send=denied)
    with pytest.raises(RuntimeError, match="HTTP 403.*target unavailable"):
        await _Sending(channel).send_target(
            {"account_id": "account-100", "user_openid": "opaque", "content": "hello"}
        )


@pytest.mark.asyncio
async def test_missing_qqbot_receipt_is_uncertain():
    async def no_receipt(chat_id, content):
        return None

    channel = SimpleNamespace(
        _chat_id=lambda openid: f"c2c:100:{openid}", send=no_receipt
    )
    with pytest.raises(UncertainDeliveryError):
        await _Sending(channel).send_target(
            {"account_id": "account-100", "user_openid": "opaque", "content": "hi"}
        )


@pytest.mark.asyncio
async def test_qqbot_transport_error_is_uncertain():
    async def disconnected(chat_id, content):
        raise httpx.ConnectError("connection lost")

    channel = SimpleNamespace(
        _chat_id=lambda openid: f"c2c:100:{openid}", send=disconnected
    )
    with pytest.raises(UncertainDeliveryError):
        await _Sending(channel).send_target(
            {"account_id": "account-100", "user_openid": "opaque", "content": "hi"}
        )


@pytest.mark.asyncio
async def test_images_follow_the_text_as_separate_c2c_messages(tmp_path):
    sky = _png(tmp_path)
    sent = []

    async def send(chat_id, content):
        sent.append(("text", content))
        return "text-id"

    async def send_image(chat_id, image):
        sent.append(("image", image))
        return f"image-{len(sent)}"

    channel = SimpleNamespace(
        _chat_id=lambda openid: f"c2c:100:{openid}", send=send, send_image=send_image
    )
    result = await _Sending(channel).account_send(
        {
            "account_id": "account-100",
            "target_kind": "private",
            "target_id": "opaque",
            "message": "看天空",
            "media": [sky, "https://x.test/a.png"],
        }
    )
    assert result["message_id"] == "text-id"
    assert sent == [
        ("text", "看天空"),
        ("image", sky),
        ("image", "https://x.test/a.png"),
    ]
    sent.clear()
    only_image = await _Sending(channel).account_send(
        {
            "account_id": "account-100",
            "target_kind": "private",
            "target_id": "opaque",
            "message": "",
            "media": [sky],
        }
    )
    assert (only_image["message_id"], sent) == (
        "image-1",
        [("image", sky)],
    )


@pytest.mark.asyncio
async def test_failed_image_after_the_text_is_uncertain(tmp_path):
    sky = _png(tmp_path)

    async def send(chat_id, content):
        return "text-id"

    async def broken_image(chat_id, image):
        raise FileNotFoundError(image)

    channel = SimpleNamespace(
        _chat_id=lambda openid: f"c2c:100:{openid}", send=send, send_image=broken_image
    )
    payload = {
        "account_id": "account-100",
        "target_kind": "private",
        "target_id": "opaque",
        "message": "看天空",
        "media": [sky],
    }
    with pytest.raises(UncertainDeliveryError, match="部分送达"):
        await _Sending(channel).account_send(payload)
    # Nothing reached the user: the image's own error stands.
    with pytest.raises(FileNotFoundError):
        await _Sending(channel).account_send({**payload, "message": ""})


@pytest.mark.asyncio
async def test_invalid_local_image_is_refused_before_any_send(tmp_path):
    sent = []

    async def send(chat_id, content):
        sent.append(content)
        return "text-id"

    channel = SimpleNamespace(
        _chat_id=lambda openid: f"c2c:100:{openid}", send=send, send_image=send
    )
    not_image = tmp_path / "note.png"
    not_image.write_text("plain text", encoding="utf-8")
    payload = {
        "account_id": "account-100",
        "target_kind": "private",
        "target_id": "opaque",
        "message": "看天空",
    }
    with pytest.raises(ValueError, match="图片文件不存在"):
        await _Sending(channel).account_send(
            {**payload, "media": [str(tmp_path / "gone.png")]}
        )
    with pytest.raises(ValueError, match="图片仅支持"):
        await _Sending(channel).account_send({**payload, "media": [str(not_image)]})
    assert sent == []
