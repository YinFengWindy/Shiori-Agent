from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from core.accounts.target_contract import UncertainDeliveryError
from plugins.feishu.backend.account_delivery import FeishuAccountDelivery


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
    channel = SimpleNamespace(send=AsyncMock(return_value="om_1"))
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

    assert await delivery.send_account(payload) == {"message_id": "om_1"}
    channel.send.assert_awaited_once_with("oc_a", "hello")
    with pytest.raises(ValueError, match="仅支持私聊"):
        await delivery.send_account({**payload, "target_kind": "group"})
    channel.send.return_value = None
    with pytest.raises(UncertainDeliveryError, match="未返回回执"):
        await delivery.send_account(payload)
    channel.send.side_effect = httpx.ReadTimeout("lost")
    with pytest.raises(UncertainDeliveryError, match="结果不确定"):
        await delivery.send_account(payload)
