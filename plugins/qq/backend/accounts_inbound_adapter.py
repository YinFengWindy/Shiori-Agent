"""QQ account input admission and projection into the host message bus."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Protocol, runtime_checkable

from bus.events import InboundMessage
from infra.channels.contract import ChannelContext
from infra.channels.intake import ChannelIntake

from .accounts_actions import QQAccountActions, qq_chat_target
from .accounts_inbound import inbound_message
from .accounts_store import QQConnectionConfig
from .channel.compat import download_to_temp, extract_cq_images
from .channel.group_filter import strip_at_segments
from .onebot import OneBotSocket


@runtime_checkable
class AccountInboundRouter(Protocol):
    """#425 host route: admit by account/rules, then project or reject input."""

    def route_account_inbound(self, message: InboundMessage) -> InboundMessage | None:
        """Returns None for rejected account input; consumes `mentioned` metadata."""
        ...


class QQInboundAdapter:
    """Keeps platform parsing and media admission separate from outbound sends."""

    name = "qq"
    _configs: dict[str, QQConnectionConfig]
    _states: dict[str, tuple[str, str]]
    _ids: dict[str, str]
    _sockets: dict[str, OneBotSocket]
    _intakes: dict[str, ChannelIntake]
    _ctx: ChannelContext | None
    _actions: QQAccountActions

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
        if hub is not None and not isinstance(hub, AccountInboundRouter):
            # The legacy binding router cannot read account response rules.
            if message.metadata.get(
                "chat_type"
            ) == "group" and not message.metadata.get("mentioned"):
                return
            if not hub.is_sender_allowed(
                channel=self.name, chat_id=message.chat_id, sender_id=message.sender
            ):
                return
        elif (
            hub is None
            and message.metadata.get("chat_type") == "group"
            and not message.metadata.get("mentioned")
        ):
            return
        if isinstance(hub, AccountInboundRouter):
            routed = hub.route_account_inbound(message)
            if routed is None:
                return
            message = routed
            if message.metadata.get("conversation_duplicate"):
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
        if hub is not None and not isinstance(hub, AccountInboundRouter):
            message = hub.route_inbound(message)
        if not message.metadata.get("conversation_duplicate"):
            await ctx.bus.publish_inbound(message)
