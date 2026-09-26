"""Bot-scoped target discovery and explicit Telegram operations."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from telegram.error import TelegramError

from desktop_bridge.method_policy import Concurrency

from .credentials import verify_bot_token

if TYPE_CHECKING:
    from agent.plugin_host.capabilities import RpcCapability
    from agent.plugin_host.kv import PluginKVStore
    from .channel.lifecycle import TelegramChannel


class TelegramAccountApi:
    """Exposes observed chats and permission-limited member lookup per Bot."""

    def __init__(
        self,
        channels: dict[str, TelegramChannel],
        rpc: RpcCapability,
        store: PluginKVStore,
    ) -> None:
        self._channels = channels
        self._rpc = rpc
        self._store = store

    def register(self) -> None:
        self._rpc.register(
            "token.verify", verify_bot_token, concurrency=Concurrency.INTEGRATION
        )
        self._rpc.register(
            "identity.get", self.get_identity, concurrency=Concurrency.READ_ONLY
        )
        self._rpc.register(
            "known.list", self.list_known, concurrency=Concurrency.READ_ONLY
        )
        self._rpc.register(
            "member.get", self.get_member, concurrency=Concurrency.READ_ONLY
        )
        self._rpc.register(
            "target.send", self.send_target, concurrency=Concurrency.INTEGRATION
        )

    def _channel(self, payload: dict[str, Any]) -> TelegramChannel:
        ref = str(payload.get("ref") or "")
        try:
            return self._channels[ref]
        except KeyError as exc:
            raise ValueError("Unknown Telegram Bot account") from exc

    def _known_ref(self, payload: dict[str, Any]) -> str:
        ref = str(payload.get("ref") or "")
        if re.fullmatch(r"[a-z0-9_]{1,48}", ref) is None:
            raise ValueError("Unknown Telegram Bot account")
        return ref

    async def list_known(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return only chats observed by this Bot, never a full contact list."""
        ref = self._known_ref(payload)
        known = self._store.get(f"known_chats:{ref}", {})
        return {
            "scope": "known_conversations",
            "chats": sorted(
                known.values(), key=lambda item: item["last_seen"], reverse=True
            ),
        }

    async def get_identity(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return the last verified Bot identity without exposing its Token."""
        ref = self._known_ref(payload)
        return dict(self._store.get(f"identity:{ref}", {}))

    async def get_member(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Query one group member; Telegram may reject it without bot permission."""
        channel = self._channel(payload)
        chat_id = str(payload.get("chat_id") or "")
        user_id = str(payload.get("user_id") or "")
        known = self._store.get(f"known_chats:{channel._config_ref}", {})
        if not chat_id.startswith("-") or chat_id not in known or not user_id.isdigit():
            raise ValueError("A known group and numeric user ID are required")
        try:
            member = await channel.bot.get_chat_member(int(chat_id), int(user_id))
        except TelegramError:
            return {
                "scope": "specific_member",
                "status": "unavailable",
                "reason": "permission_or_platform_limit",
            }
        user = member.user
        return {
            "scope": "specific_member",
            "status": member.status,
            "user_id": str(user.id),
            "name": user.full_name,
            "username": user.username or "",
        }

    async def send_target(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send to one explicit target through the selected connected Bot."""
        channel = self._channel(payload)
        if not channel._online:
            raise RuntimeError("Telegram Bot is not connected")
        chat_id = str(payload.get("chat_id") or "").strip()
        text = str(payload.get("text") or "")
        topic = payload.get("message_thread_id")
        if not chat_id.lstrip("-").isdigit() or not text.strip():
            raise ValueError("A numeric chat ID and message text are required")
        if topic is not None and (
            not isinstance(topic, int) or topic <= 0 or not chat_id.startswith("-")
        ):
            raise ValueError("A group topic requires a positive message_thread_id")
        receipt = await channel.send(chat_id, text, message_thread_id=topic)
        return {"chat_id": chat_id, "message_thread_id": topic, "message_id": receipt}
