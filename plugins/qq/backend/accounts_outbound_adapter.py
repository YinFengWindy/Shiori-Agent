"""QQ account outbound routing and delivery receipts."""

from __future__ import annotations

import logging

from bus.events import OutboundMessage
from core.common.channel_chat_types import REPLY_MENTION_IDS_KEY
from infra.channels.contract import ChannelContext

from .accounts_actions import qq_chat_target, qq_number
from .onebot import OneBotError, OneBotSocket

logger = logging.getLogger(__name__)


def _usable_mentions(chosen: list[object]) -> list[str]:
    """The role's extra mentions that are QQ numbers; others are skipped.

    They are optional extras on a reply that still @s its trigger, so an
    unusable ID is logged and dropped instead of failing the whole reply.
    """
    usable: list[str] = []
    for member in chosen:
        try:
            usable.append(qq_number(member, "@ 成员"))
        except ValueError:
            logger.warning("QQ 群回复跳过无法 @ 的成员 ID: %r", member)
    return usable


class QQOutboundAdapter:
    """Requires an explicit owned account for every QQ outbound message."""

    name = "qq"
    _sockets: dict[str, OneBotSocket]
    _ctx: ChannelContext | None

    async def send_target(
        self,
        account_id: str,
        kind: str,
        target_id: str,
        message: str,
        *,
        group_id: str = "",
        mention_ids: tuple[str, ...] = (),
    ) -> dict[str, str]:
        """The owning runtime supplies account-targeted sending."""
        raise NotImplementedError

    def via_account(self, account_id: str) -> dict[str, str]:
        """The owning runtime supplies the account's message snapshot."""
        raise NotImplementedError

    def status(self) -> dict[str, bool | str]:
        """Channel transport status; account reports carry login state."""
        return {"connected": any(not sock.closed for sock in self._sockets.values())}

    @staticmethod
    def _sending_account(metadata: dict[str, object]) -> str:
        """Every QQ send names the owned account it goes out through."""
        account_id = str(metadata.get("account_id") or "")
        if not account_id:
            raise OneBotError("QQ 发送需要明确指定账号")
        return account_id

    async def _send_with_metadata(
        self, chat_id: str, message: str, metadata: dict[str, object]
    ) -> str:
        account_id = self._sending_account(metadata)
        kind, target = qq_chat_target(chat_id)
        return (await self.send_target(account_id, kind, target, message))["message_id"]

    async def _on_response(self, msg: OutboundMessage) -> None:
        """Sends a role reply; a group reply @s its trigger and chosen members."""
        try:
            account_id = self._sending_account(msg.metadata)
            via = self.via_account(account_id)
            kind, target = qq_chat_target(msg.chat_id)
            mentions: tuple[str, ...] = ()
            if kind == "group":
                trigger = str(msg.metadata.get("sender_id") or "")
                chosen = _usable_mentions(
                    list(msg.metadata.get(REPLY_MENTION_IDS_KEY) or [])
                )
                mentions = tuple(dict.fromkeys(i for i in [trigger, *chosen] if i))
            message_id = (
                await self.send_target(
                    account_id, kind, target, msg.content, mention_ids=mentions
                )
            )["message_id"]
        except Exception:
            self._mark_delivery(msg, "failed")
            raise
        self._mark_delivery(msg, "sent", message_id, via)

    def _mark_delivery(
        self,
        msg: OutboundMessage,
        status: str,
        message_id: str = "",
        via_account: dict[str, str] | None = None,
    ) -> None:
        hub = self._ctx.channel_hub if self._ctx else None
        if hub is not None:
            hub.mark_delivery(
                msg,
                default_channel=self.name,
                delivery_status=status,
                external_message_id=message_id,
                via_account=via_account,
            )
