"""Account-scoped Feishu profile, target lookup, and private sending."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import TYPE_CHECKING

import httpx

from core.accounts import VIA_ACCOUNT_KEY
from core.accounts.target_contract import (
    GROUP_MEMBER_TARGET,
    UncertainDeliveryError,
    account_send_media,
)

from .accounts import FeishuAccounts

if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext


class FeishuAccountDelivery:
    """Queries observed targets and sends through a connected application."""

    def __init__(self, ctx: PluginRuntimeContext, accounts: FeishuAccounts) -> None:
        self._ctx = ctx
        self._accounts = accounts

    async def profile(self, payload: dict[str, object]) -> dict[str, object]:
        """Cached bot identity and observed private targets of one application."""
        ref = str(payload.get("ref") or "")
        if self._accounts.application(ref) is None:
            raise KeyError("飞书账号不存在")
        identity = self._ctx.kv.get(f"profile:{ref}", {})
        targets = self._ctx.kv.get(f"targets:{ref}", {})
        return {
            "identity": identity,
            "targets": [
                {"chat_id": chat, "open_id": sender, "id_scope": "app"}
                for chat, sender in sorted(targets.items())
            ],
            "coverage": "observed_private_chats",
        }

    async def targets(self, payload: dict[str, object]) -> dict[str, object]:
        """Resolves an account-scoped known-private-chat request."""
        if str(payload.get("kind") or "") != "known":
            raise ValueError("飞书仅支持已交互的私聊目标")
        return await self.profile({"ref": self._accounts.ref_for_account(payload)})

    async def send(self, payload: dict[str, object]) -> dict[str, object]:
        """Sends a private message and/or images through one connected application.

        Text and each image are separate Feishu messages; the receipt is the
        first one's ID.
        """
        channel = self._accounts.channel(str(payload.get("ref") or ""))
        if channel is None:
            raise RuntimeError("飞书账号未连接")
        chat_id = str(payload.get("chat_id") or "")
        message = str(payload.get("message") or "")
        media = account_send_media(payload)
        if not message.strip() and not media:
            raise ValueError("消息和图片不能都为空")
        parts = [
            *([(channel.send, message)] if message.strip() else []),
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
                    "飞书消息已部分送达，后续图片发送失败"
                ) from exc
            receipt = receipt or message_id
        return {"message_id": receipt}

    async def send_account(self, payload: dict[str, object]) -> dict[str, object]:
        """Validates the shared account-send contract before private delivery.

        The receipt carries the application's message snapshot.
        """
        if payload.get("mention_ids"):
            raise ValueError("飞书没有群聊，不支持 @ 成员")
        if str(payload.get("target_kind") or "") == GROUP_MEMBER_TARGET:
            raise ValueError("飞书不支持群临时会话")
        if str(payload.get("target_kind") or "") != "private":
            raise ValueError("飞书仅支持私聊发送")
        if payload.get("message_thread_id") is not None:
            raise ValueError("飞书不支持群话题")
        ref = self._accounts.ref_for_account(payload)
        channel = self._accounts.channel(ref)
        if channel is None:
            raise RuntimeError("飞书账号未连接")
        # Taken before sending so a completed send always returns its snapshot.
        via = channel.via_account()
        result = await self.send(
            {
                "ref": ref,
                "chat_id": payload.get("target_id"),
                "message": payload.get("message"),
                "media": list(account_send_media(payload)),
            }
        )
        return {**result, VIA_ACCOUNT_KEY: via}


async def _confirmed(sending: Awaitable[str | None]) -> str:
    """One Feishu message's ID, with lost links and receipts as uncertain."""
    try:
        message_id = await sending
    except httpx.TransportError as exc:
        raise UncertainDeliveryError("飞书发送连接中断，结果不确定") from exc
    if not message_id:
        raise UncertainDeliveryError("飞书平台未返回回执")
    return message_id
