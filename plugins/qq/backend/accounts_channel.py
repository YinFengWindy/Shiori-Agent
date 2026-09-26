"""QQ account channel I/O; connection lifecycle remains in accounts_runtime."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from bus.events import InboundMessage, OutboundMessage
from infra.channels.contract import ChannelContext
from infra.channels.intake import ChannelIntake

from .accounts_actions import QQAccountActions, qq_chat_target
from .accounts_inbound import inbound_message
from .accounts_store import QQConnectionConfig
from .channel.compat import download_to_temp, extract_cq_images
from .channel.group_filter import strip_at_segments
from .onebot import OneBotError, OneBotSocket


class QQChannelIO:
    """Adapts independent QQ sockets to the host's single channel boundary."""

    name = "qq"
    _configs: dict[str, QQConnectionConfig]
    _states: dict[str, tuple[str, str]]
    _ids: dict[str, str]
    _sockets: dict[str, OneBotSocket]
    _intakes: dict[str, ChannelIntake]
    _ctx: ChannelContext | None
    _actions: QQAccountActions

    async def send_target(
        self, account_id: str, kind: str, target_id: str, message: str
    ) -> dict[str, str]:
        """The owning runtime supplies account-targeted sending."""
        raise NotImplementedError

    def pause_intake(self) -> None:
        """Buffers incoming messages during host generation replacement."""
        for intake in self._intakes.values():
            intake.pause()

    def resume_intake(self) -> None:
        """Resumes incoming messages after host generation replacement."""
        for intake in self._intakes.values():
            intake.resume()

    def _start_intake(self, ref: str) -> None:
        if ref in self._intakes:
            return

        async def send_notice(chat_id: str, message: str) -> str:
            kind, target = qq_chat_target(chat_id)
            return (
                await self._actions.send_target(self._ids[ref], kind, target, message)
            )["message_id"]

        intake = ChannelIntake(self._accept_inbound, send_notice)
        intake.start(paused=self._ctx.intake_paused if self._ctx else False)
        self._intakes[ref] = intake

    def status(self) -> dict[str, bool | str]:
        """Channel transport status; individual account reports carry login state."""
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

    async def _on_event(self, ref: str, event: dict[str, Any]) -> None:
        if ref not in self._ids:
            return
        message = inbound_message(
            account_id=self._ids[ref],
            expected_uin=self._configs[ref].expected_uin,
            event=event,
        )
        if message is not None:
            await self._intakes[ref].submit(message)

    async def _on_socket_event(
        self, ref: str, socket: OneBotSocket, event: dict[str, Any]
    ) -> None:
        if (
            self._sockets.get(ref) is socket
            and self._states.get(ref, ("offline", ""))[0] == "online"
        ):
            await self._on_event(ref, event)

    async def _accept_inbound(self, message: InboundMessage) -> None:
        ctx = self._ctx
        if ctx is None:
            return
        hub = ctx.channel_hub
        if hub is not None and not hub.is_sender_allowed(
            channel=self.name, chat_id=message.chat_id, sender_id=message.sender
        ):
            return
        raw = (
            strip_at_segments(message.content)
            if message.metadata.get("chat_type") == "group"
            else message.content
        )
        text, image_urls = extract_cq_images(raw)
        media = (
            await download_to_temp(
                image_urls, ctx.http_resources.external_default, ctx.attachment_store
            )
            if image_urls
            else []
        )
        message = replace(message, content=text, media=media)
        if hub is not None:
            message = hub.route_inbound(message)
        if not message.metadata.get("conversation_duplicate"):
            await ctx.bus.publish_inbound(message)
