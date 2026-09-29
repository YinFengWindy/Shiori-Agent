"""Account-scoped C2C sends with official QQBot receipts and failures."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import TYPE_CHECKING, Any

import httpx
from core.accounts import VIA_ACCOUNT_KEY
from core.accounts.target_contract import (
    GROUP_MEMBER_TARGET,
    UncertainDeliveryError,
    account_send_media,
)

if TYPE_CHECKING:
    from .account_identity import QQBotAccountIdentity
    from .channel import QQBotChannel


class _AccountSendingMixin:
    """Requires the composite's identity lookup and application channels."""

    _identity: QQBotAccountIdentity
    _channels: dict[str, QQBotChannel]

    async def account_send(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Adapt the shared account contract to QQBot's C2C OpenID send.

        Text and each image go out as separate C2C messages; the receipt is
        the first one's ID and carries the application's message snapshot.
        """
        if "target_kind" not in payload and "user_openid" in payload:
            return await self.send_target(payload)
        if payload.get("mention_ids"):
            raise ValueError("QQBot 没有群聊，不支持 @ 成员")
        if str(payload.get("target_kind") or "") == GROUP_MEMBER_TARGET:
            raise ValueError("QQBot 不支持群临时会话")
        if str(payload.get("target_kind") or "") != "private":
            raise ValueError("QQBot 仅支持私聊发送")
        if payload.get("message_thread_id") is not None:
            raise ValueError("QQBot 不支持群话题")
        # Taken before sending so a completed send always returns its snapshot.
        via = self._identity.via_account(self._identity.app_for_account(payload))
        result = await self.send_target(
            {
                "account_id": payload.get("account_id"),
                "user_openid": payload.get("target_id"),
                "content": payload.get("message"),
                "media": list(account_send_media(payload)),
            }
        )
        return {**result, VIA_ACCOUNT_KEY: via}

    async def send_target(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send C2C content and optional images through the selected application."""
        app_id = self._identity.app_for_account(payload)
        channel = self._channels.get(app_id)
        if channel is None:
            raise RuntimeError("QQBot 应用账号未连接")
        openid = str(payload.get("user_openid") or "").strip()
        if not openid or ":" in openid:
            raise ValueError("无效的 QQBot 用户 OpenID")
        content = str(payload.get("content") or "").strip()
        media = account_send_media(payload)
        if not content and not media:
            raise ValueError("发送内容不能为空")
        chat_id = channel._chat_id(openid)
        # Text, then each image, as separate C2C messages; the first ID is the receipt.
        parts = [
            *([(channel.send, content)] if content else []),
            *((channel.send_image, image) for image in media),
        ]
        receipt = ""
        for send, value in parts:
            try:
                message_id = await _confirmed(send(chat_id, value))
            except Exception as exc:
                if not receipt:
                    raise
                # The user already has part of the message: not a clean failure.
                raise UncertainDeliveryError(
                    "QQBot 消息已部分送达，后续图片发送失败"
                ) from exc
            receipt = receipt or message_id
        return {"message_id": receipt, "chat_id": chat_id}


async def _confirmed(sending: Awaitable[str | None]) -> str:
    """One C2C message's platform ID, with QQBot failures in contract terms."""
    try:
        receipt = await sending
    except httpx.TransportError as exc:
        raise UncertainDeliveryError("QQBot 发送连接中断，结果不确定") from exc
    except httpx.HTTPStatusError as exc:
        try:
            body = exc.response.json()
        except ValueError:
            body = {}
        reason = (
            str(body.get("message") or body.get("msg") or "").strip()
            if isinstance(body, dict)
            else ""
        )
        raise RuntimeError(
            f"QQBot 平台拒绝发送 (HTTP {exc.response.status_code})"
            + (f": {reason}" if reason else "")
        ) from exc
    if not receipt:
        raise UncertainDeliveryError("QQBot 平台未返回消息 ID，发送结果不确定")
    return receipt
