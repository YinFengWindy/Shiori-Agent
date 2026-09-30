"""QQ account input admission and projection into the host message bus."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from bus.events import InboundMessage
from core.channels.pairing_command import answer_pairing_code
from core.common.message_source import GROUP_NAME_KEY, addresses_account
from infra.channels.contract import ChannelContext
from infra.channels.intake import ChannelIntake

from .accounts_actions import QQAccountActions, qq_chat_target
from .accounts_group_names import QQGroupNames
from .accounts_inbound import inbound_message, is_real_private_chat
from .accounts_reply_sender import with_reply_sender
from .accounts_store import QQConnectionConfig
from .channel.compat import download_to_temp, extract_cq_images
from .channel.group_filter import strip_at_segments
from .onebot import OneBotSocket


class QQInboundAdapter:
    """Keeps platform parsing and media admission separate from outbound sends."""

    name = "qq"
    _configs: dict[str, QQConnectionConfig]
    _states: dict[str, tuple[str, str]]
    _ids: dict[str, str]
    _sockets: dict[str, OneBotSocket]
    _intakes: dict[str, ChannelIntake]
    # The host's current admission gate. ``ctx.intake_paused`` only describes
    # how the channel was started (True under a runtime handover) and goes
    # stale once the host resumes it, so an account activated later reads this.
    _intake_paused: bool
    _ctx: ChannelContext | None
    _actions: QQAccountActions
    _group_names: QQGroupNames

    def pause_intake(self) -> None:
        """Buffers incoming messages during host generation replacement."""
        self._intake_paused = True
        for intake in self._intakes.values():
            intake.pause()

    def resume_intake(self) -> None:
        """Resumes incoming messages after host generation replacement."""
        self._intake_paused = False
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
        intake.start(paused=self._intake_paused)
        self._intakes[ref] = intake

    async def _on_event(self, ref: str, event: dict[str, Any]) -> None:
        if ref not in self._ids:
            return
        config = self._configs[ref]
        message = inbound_message(
            account_id=self._ids[ref],
            expected_uin=config.expected_uin,
            via_account=config.via_account(),
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

    async def _with_group_name(self, message: InboundMessage) -> InboundMessage:
        """Adds the group's name snapshot to a group message when it is known."""
        metadata = message.metadata
        if metadata.get("chat_type") != "group":
            return message
        name = await self._group_names.name(
            str(metadata["account_id"]), str(metadata["group_id"])
        )
        if name is None:
            return message
        return replace(message, metadata={**metadata, GROUP_NAME_KEY: name})

    async def _accept_inbound(self, message: InboundMessage) -> None:
        ctx = self._ctx
        if ctx is None:
            return
        message = await self._with_group_name(message)
        # NapCat is only asked for a group message that replies to another.
        message = await with_reply_sender(
            message,
            lambda account_id, message_id: self._actions.message_sender(
                account_id, message_id
            ),
        )
        hub = ctx.channel_hub
        if hub is None:
            # Without the host's account routing, a group message still only
            # passes when it @s this account or replies to it.
            if message.metadata.get("chat_type") == "group" and not addresses_account(
                message.metadata, str(message.metadata["platform_account_id"])
            ):
                return
        else:
            # A QQ number is the same for every account. Only a real private
            # chat pairs; a group temporary session never does.
            if is_real_private_chat(message) and await answer_pairing_code(
                hub,
                message,
                scope="platform",
                send=lambda text: self._actions.send_target(
                    str(message.metadata["account_id"]),
                    "private",
                    message.sender,
                    text,
                ),
            ):
                return
            # The host admits by account and response rules, then projects.
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
        if not message.metadata.get("conversation_duplicate"):
            await ctx.bus.publish_inbound(message)
