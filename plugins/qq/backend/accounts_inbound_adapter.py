"""QQ account input admission and projection into the host message bus."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from shiori_sdk.messages import InboundMessage, TEXT_ATTACHMENT_TOOL_KEY
from shiori_sdk.channels.pairing_command import answer_pairing_code
from shiori_sdk.channels.message_source import GROUP_NAME_KEY, addresses_account
from shiori_sdk.channels import ChannelContext
from shiori_sdk.channels.services import ChannelIntake
from shiori_sdk.http import HttpGet

from .accounts_actions import QQAccountActions, qq_chat_target
from .accounts_avatar import refresh_message_avatars
from .accounts_group_names import QQGroupNames
from .accounts_inbound import inbound_message, is_real_private_chat
from .accounts_reply_quote import with_quote, with_replied_message
from .accounts_store import QQConnectionConfig
from .channel.compat import download_to_temp, extract_cq_images
from .channel.files import QQFile, extract_cq_files, receive_files
from .channel.group_filter import strip_at_segments, strip_reply_segments
from .onebot import OneBotSocket

if TYPE_CHECKING:
    from shiori_sdk.channels.avatars import AvatarsCapability

# The text of a message that is only pictures, as other channels write it.
IMAGE_PLACEHOLDER = "[图片]"


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
    # The host's avatar cache for senders and groups; None when not granted.
    _avatars: AvatarsCapability | None = None
    _http: HttpGet

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
        if self._ctx is None:
            # Accounts may authenticate before the transport is started; admission starts with it.
            return

        async def send_notice(chat_id: str, message: str) -> str:
            kind, target = qq_chat_target(chat_id)
            return (
                await self._actions.send_target(self._ids[ref], kind, target, message)
            )["message_id"]

        intake = self._ctx.intake_factory(self._accept_inbound, send_notice)
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

    def _refresh_avatars(self, message: InboundMessage) -> None:
        """Refreshes the avatars ``message`` shows, when the host caches avatars."""
        if self._avatars is not None:
            refresh_message_avatars(self._avatars, message, requester=self._http)

    async def _accept_inbound(self, message: InboundMessage) -> None:
        ctx = self._ctx
        if ctx is None:
            return
        message = await self._with_group_name(message)
        message, replied = await with_replied_message(
            message, self._actions.replied_message
        )
        # The host keeps the text it is handed, for a turn or for a group's
        # listening records (#538), so CQ codes leave before routing: a group
        # message's @ and any reply target already travel as metadata, and
        # pictures (the quoted message's too) are only downloaded, and the quote
        # only added, for a message that starts a turn.
        raw = strip_reply_segments(
            strip_at_segments(message.content)
            if message.metadata.get("chat_type") == "group"
            else message.content
        )
        text, image_urls = extract_cq_images(raw)
        text, files = extract_cq_files(text)
        # A picture alone reads as 「[图片]」, as other channels write it, so a
        # listened group message keeps a line even though its file is never
        # downloaded.
        message = replace(
            message,
            content=text or (IMAGE_PLACEHOLDER if image_urls else ""),
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
            # The host admits by account and response rules, then projects;
            # an unaddressed group message ends there (listened to or dropped).
            # Only a message the role receives, or one kept in the group's
            # listening records (#553), shows its sender and group.
            routed = hub.route_account_inbound(message, on_heard=self._refresh_avatars)
            if routed is None:
                return
            message = routed
            if message.metadata.get("conversation_duplicate"):
                return
            self._refresh_avatars(message)

        async def download(urls: list[str]) -> list[str]:
            if not urls:
                return []
            return await download_to_temp(
                urls, ctx.http_resources.external_default, ctx.attachment_store
            )

        async def download_files(
            text: str, files: list[QQFile]
        ) -> tuple[str, list[str]]:
            return await receive_files(
                text,
                files,
                ctx.http_resources.external_default,
                ctx.attachment_store,
                lambda file: self._actions.file_url(
                    str(message.metadata["account_id"]), message.chat_id, file
                ),
            )

        text, file_paths = await download_files(text or message.content, files)
        message = replace(
            message,
            content=text,
            media=[*await download(image_urls), *file_paths],
            metadata={**message.metadata, TEXT_ATTACHMENT_TOOL_KEY: "read_attachment"},
        )
        if replied is not None:
            message = await with_quote(message, replied, download, download_files)
        await ctx.bus.publish_inbound(message)
