"""Account-scoped Feishu profile, target lookup, and private sending."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from core.accounts.target_contract import UncertainDeliveryError

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
        """Sends a private message through one connected application."""
        channel = self._accounts.channel(str(payload.get("ref") or ""))
        if channel is None:
            raise RuntimeError("飞书账号未连接")
        try:
            message_id = await channel.send(
                str(payload.get("chat_id") or ""), str(payload.get("message") or "")
            )
        except httpx.TransportError as exc:
            raise UncertainDeliveryError("飞书发送连接中断，结果不确定") from exc
        if not message_id:
            raise UncertainDeliveryError("飞书平台未返回回执")
        return {"message_id": message_id}

    async def send_account(self, payload: dict[str, object]) -> dict[str, object]:
        """Validates the shared account-send contract before private delivery."""
        if str(payload.get("target_kind") or "") != "private":
            raise ValueError("飞书仅支持私聊发送")
        if payload.get("message_thread_id") is not None:
            raise ValueError("飞书不支持群话题")
        return await self.send(
            {
                "ref": self._accounts.ref_for_account(payload),
                "chat_id": payload.get("target_id"),
                "message": payload.get("message"),
            }
        )
