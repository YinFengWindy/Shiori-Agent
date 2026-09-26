"""Account-scoped C2C sends with official QQBot receipts and failures."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from .account_identity import QQBotAccountIdentity
    from .channel import QQBotChannel


class _AccountSendingMixin:
    """Requires the composite's identity lookup and application channels."""

    _identity: QQBotAccountIdentity
    _channels: dict[str, QQBotChannel]

    async def send_target(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send C2C content through the selected application account."""
        app_id = self._identity.app_for_account(payload)
        channel = self._channels.get(app_id)
        if channel is None:
            raise RuntimeError("QQBot 应用账号未连接")
        openid = str(payload.get("user_openid") or "").strip()
        if not openid or ":" in openid:
            raise ValueError("无效的 QQBot 用户 OpenID")
        content = str(payload.get("content") or "").strip()
        if not content:
            raise ValueError("发送内容不能为空")
        try:
            receipt = await channel.send(channel._chat_id(openid), content)
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
            raise RuntimeError("QQBot 平台未返回消息 ID，发送结果不确定")
        return {"message_id": receipt, "chat_id": channel._chat_id(openid)}
