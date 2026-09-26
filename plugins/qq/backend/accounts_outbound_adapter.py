"""QQ account outbound routing and delivery receipts."""

from __future__ import annotations

from bus.events import OutboundMessage
from infra.channels.contract import ChannelContext

from .accounts_actions import QQAccountActions, qq_chat_target
from .accounts_store import QQConnectionConfig
from .onebot import OneBotError, OneBotSocket


class QQOutboundAdapter:
    """Requires an explicit account when more than one QQ account is saved."""

    name = "qq"
    _configs: dict[str, QQConnectionConfig]
    _ids: dict[str, str]
    _sockets: dict[str, OneBotSocket]
    _ctx: ChannelContext | None
    _actions: QQAccountActions

    async def send_target(
        self, account_id: str, kind: str, target_id: str, message: str
    ) -> dict[str, str]:
        """The owning runtime supplies account-targeted sending."""
        raise NotImplementedError

    def status(self) -> dict[str, bool | str]:
        """Channel transport status; account reports carry login state."""
        return {"connected": any(not sock.closed for sock in self._sockets.values())}

    async def _send_legacy(self, chat_id: str, message: str) -> str:
        if len(self._configs) != 1:
            raise OneBotError("QQ 多账号发送需要明确指定账号")
        online = [ref for ref, socket in self._sockets.items() if not socket.closed]
        if len(online) != 1:
            raise OneBotError("QQ 账号不在线")
        kind, target = qq_chat_target(chat_id)
        return (
            await self._actions.send_target(self._ids[online[0]], kind, target, message)
        )["message_id"]

    async def _send_with_metadata(
        self, chat_id: str, message: str, metadata: dict[str, object]
    ) -> str:
        account_id = str(metadata.get("account_id") or "")
        if not account_id:
            return await self._send_legacy(chat_id, message)
        kind, target = qq_chat_target(chat_id)
        return (await self.send_target(account_id, kind, target, message))["message_id"]

    async def _on_response(self, msg: OutboundMessage) -> None:
        try:
            message_id = await self._send_with_metadata(
                msg.chat_id, msg.content, msg.metadata
            )
        except Exception:
            self._mark_delivery(msg, "failed")
            raise
        self._mark_delivery(msg, "sent", message_id)

    def _mark_delivery(
        self, msg: OutboundMessage, status: str, message_id: str = ""
    ) -> None:
        hub = self._ctx.channel_hub if self._ctx else None
        if hub is not None:
            hub.mark_delivery(
                msg,
                default_channel=self.name,
                delivery_status=status,
                external_message_id=message_id,
            )
