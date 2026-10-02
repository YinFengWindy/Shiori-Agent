"""Host-free message, attachment and sender fixtures for transport tests."""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from uuid import uuid4

from shiori_sdk.channels.services import OutboundHandler, Sender
from shiori_sdk.messages import InboundMessage, OutboundMessage


class FakeMessageBus:
    """Record admitted input and dispatch replies without runtime leases or retry policy."""

    def __init__(self):
        self.inbound: list[InboundMessage] = []
        self._inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self.outbound: dict[str, list[OutboundHandler]] = {}

    async def publish_inbound(self, msg: InboundMessage) -> None:
        """Record input and make it available to a waiting test."""
        self.inbound.append(msg)
        await self._inbound.put(msg)

    async def consume_inbound(self) -> InboundMessage:
        """Return the next admitted input."""
        return await self._inbound.get()

    @property
    def inbound_size(self) -> int:
        """Number of messages not consumed by a test."""
        return self._inbound.qsize()

    def subscribe_outbound(self, channel: str, callback: OutboundHandler) -> None:
        """Register a connection's reply callback."""
        self.outbound.setdefault(channel, []).append(callback)

    def unsubscribe_outbound(self, channel: str, callback: OutboundHandler) -> None:
        """Remove only the specified connection's callback."""
        remaining = [cb for cb in self.outbound.get(channel, []) if cb != callback]
        if remaining:
            self.outbound[channel] = remaining
        else:
            self.outbound.pop(channel, None)

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """Deliver once; retry semantics are verified by real host integration tests."""
        for callback in self.outbound.get(msg.channel, []):
            await callback(msg)

    def has_pending_outbound(
        self, channel: str, chat_id: str, external_message_id: str
    ) -> bool:
        """The fake dispatches immediately and never owns a pending reply queue."""
        return False


class FakeAttachmentStore:
    """Write test attachments only beneath an explicitly supplied directory."""

    def __init__(self, root: Path):
        self.root = root

    def create_path(self, prefix: str, suffix: str) -> Path:
        """Allocate a path beneath this fixture's root."""
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root / f"{prefix}{uuid4().hex}{suffix}"

    def write_bytes(self, data: bytes, *, prefix: str, suffix: str) -> Path:
        """Persist received bytes for attachment assertions."""
        path = self.create_path(prefix, suffix)
        path.write_bytes(data)
        return path


class FakePushSenders:
    """Record the public senders owned by each connection."""

    def __init__(self):
        self.senders: dict[str, Sender | None] = {}
        # Channel -> the sender names (and description) its connection registered.
        self.registrations: dict[str, dict[str, object]] = {}

    def register_channel(
        self,
        channel: str,
        text: Sender | None = None,
        stream_text: Sender | None = None,
        file: Callable[[str, str, str | None], Awaitable[str | None]] | None = None,
        image: Sender | None = None,
        target_resolver: Callable[[str], str] | None = None,
        text_with_metadata: (
            Callable[[str, str, dict[str, object]], Awaitable[str | None]] | None
        ) = None,
        image_with_metadata: (
            Callable[[str, str, dict[str, object]], Awaitable[str | None]] | None
        ) = None,
        description: str = "",
    ) -> None:
        """Retain a sender registration for a test-owned channel."""
        self.senders[channel] = text
        offered: dict[str, object | None] = {
            "text": text,
            "stream_text": stream_text,
            "file": file,
            "image": image,
            "target_resolver": target_resolver,
            "text_with_metadata": text_with_metadata,
            "image_with_metadata": image_with_metadata,
            "description": description.strip() or None,
        }
        self.registrations[channel] = {
            name: value for name, value in offered.items() if value is not None
        }

    def unregister_channel(self, channel: str, *, text: Sender | None = None) -> None:
        """Keep replacement registrations when the previous connection stops."""
        if text is None or self.senders.get(channel) == text:
            self.senders.pop(channel, None)
            self.registrations.pop(channel, None)


class FakeInterruptResult:
    """The control-plane reply a channel shows the sender after ``/stop``."""

    def __init__(self, *, status: str, session_key: str, message: str):
        self.status, self.session_key, self.message = status, session_key, message


class FakeInterruptController:
    """Record interrupt requests and answer with a fixture-selected reply.

    The host interrupts the turn running on ``session_key``; this fake only
    records the request, so tests assert who asked and what the channel sent.
    """

    def __init__(self, *, message: str = "已中断", status: str = "interrupted"):
        self.message, self.status = message, status
        self.requests: list[dict[str, str]] = []

    def request_interrupt(
        self, session_key: str, sender: str = "", command: str = "/stop"
    ) -> FakeInterruptResult:
        """Record the request; the reply text is the fixture's ``message``."""
        self.requests.append(
            {"session_key": session_key, "sender": sender, "command": command}
        )
        return FakeInterruptResult(
            status=self.status, session_key=session_key, message=self.message
        )
