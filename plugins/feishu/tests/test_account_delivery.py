from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from core.accounts.target_contract import UncertainDeliveryError
from plugins.feishu.backend.account_delivery import FeishuAccountDelivery


def _png(tmp_path) -> str:
    """A real PNG file on disk, as a local image path."""
    path = tmp_path / "sky.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"body")
    return str(path)


class _KV:
    def __init__(self) -> None:
        self.data = {
            "profile:feishu:app": {"open_id": "ou_bot"},
            "targets:feishu:app": {"oc_b": "ou_b", "oc_a": "ou_a"},
        }

    def get(self, key: str, default=None):
        return self.data.get(key, default)


@pytest.mark.asyncio
async def test_profile_and_targets_stay_scoped_to_the_selected_account() -> None:
    accounts = SimpleNamespace(
        application=lambda ref: object() if ref == "feishu:app" else None,
        ref_for_account=lambda payload: (
            "feishu:app" if payload["account_id"] == "feishu:feishu:app" else None
        ),
    )
    delivery = FeishuAccountDelivery(SimpleNamespace(kv=_KV()), accounts)

    result = await delivery.targets(
        {"account_id": "feishu:feishu:app", "kind": "known"}
    )
    assert result == {
        "identity": {"open_id": "ou_bot"},
        "targets": [
            {"chat_id": "oc_a", "open_id": "ou_a", "id_scope": "app"},
            {"chat_id": "oc_b", "open_id": "ou_b", "id_scope": "app"},
        ],
        "coverage": "observed_private_chats",
    }
    with pytest.raises(ValueError, match="仅支持已交互"):
        await delivery.targets({"account_id": "feishu:feishu:app", "kind": "groups"})
    with pytest.raises(KeyError, match="账号不存在"):
        await delivery.profile({"ref": "other"})


@pytest.mark.asyncio
async def test_account_send_requires_private_target_and_certain_receipt() -> None:
    via = {"platform": "feishu", "platform_account_id": "feishu:app"}
    channel = SimpleNamespace(
        send=AsyncMock(return_value="om_1"), via_account=lambda: via
    )
    accounts = SimpleNamespace(
        channel=lambda ref: channel if ref == "feishu:app" else None,
        ref_for_account=lambda payload: "feishu:app",
    )
    delivery = FeishuAccountDelivery(SimpleNamespace(kv=_KV()), accounts)
    payload = {
        "account_id": "feishu:feishu:app",
        "target_kind": "private",
        "target_id": "oc_a",
        "message": "hello",
    }

    assert await delivery.send_account(payload) == {
        "message_id": "om_1",
        "via_account": via,
    }
    channel.send.assert_awaited_once_with("oc_a", "hello")
    with pytest.raises(ValueError, match="仅支持私聊"):
        await delivery.send_account({**payload, "target_kind": "group"})
    # No group chats: mentions and group temporary sessions are refused clearly.
    with pytest.raises(ValueError, match="不支持 @ 成员"):
        await delivery.send_account(
            {**payload, "target_kind": "group", "mention_ids": ["ou_b"]}
        )
    with pytest.raises(ValueError, match="群临时会话"):
        await delivery.send_account({**payload, "target_kind": "group_member"})
    channel.send.assert_awaited_once()
    channel.send.return_value = None
    with pytest.raises(UncertainDeliveryError, match="未返回回执"):
        await delivery.send_account(payload)
    channel.send.side_effect = httpx.ReadTimeout("lost")
    with pytest.raises(UncertainDeliveryError, match="结果不确定"):
        await delivery.send_account(payload)


@pytest.mark.asyncio
async def test_account_send_delivers_images_after_the_text(tmp_path) -> None:
    sky = _png(tmp_path)
    channel = SimpleNamespace(
        send=AsyncMock(return_value="om_text"),
        send_image=AsyncMock(return_value="om_image"),
        via_account=lambda: {},
    )
    accounts = SimpleNamespace(
        channel=lambda ref: channel, ref_for_account=lambda payload: "feishu:app"
    )
    delivery = FeishuAccountDelivery(SimpleNamespace(kv=_KV()), accounts)
    payload = {
        "account_id": "feishu:feishu:app",
        "target_kind": "private",
        "target_id": "oc_a",
        "message": "看天空",
        "media": [sky],
    }
    assert (await delivery.send_account(payload))["message_id"] == "om_text"
    channel.send.assert_awaited_once_with("oc_a", "看天空")
    channel.send_image.assert_awaited_once_with("oc_a", sky)
    only_image = await delivery.send_account({**payload, "message": ""})
    assert only_image["message_id"] == "om_image"
    channel.send.assert_awaited_once()

    # The text already reached the chat: a failed image leaves it uncertain.
    channel.send_image.side_effect = FileNotFoundError("sky.png")
    with pytest.raises(UncertainDeliveryError, match="部分送达"):
        await delivery.send_account(payload)
    with pytest.raises(FileNotFoundError):
        await delivery.send_account({**payload, "message": ""})


@pytest.mark.asyncio
async def test_invalid_local_image_is_refused_before_any_send(tmp_path) -> None:
    channel = SimpleNamespace(
        send=AsyncMock(return_value="om_text"),
        send_image=AsyncMock(return_value="om_image"),
        via_account=lambda: {},
    )
    accounts = SimpleNamespace(
        channel=lambda ref: channel, ref_for_account=lambda payload: "feishu:app"
    )
    delivery = FeishuAccountDelivery(SimpleNamespace(kv=_KV()), accounts)
    with pytest.raises(ValueError, match="图片文件不存在"):
        await delivery.send_account(
            {
                "account_id": "feishu:feishu:app",
                "target_kind": "private",
                "target_id": "oc_a",
                "message": "看天空",
                "media": [str(tmp_path / "gone.png")],
            }
        )
    channel.send.assert_not_awaited()
    channel.send_image.assert_not_awaited()
