"""Host-free message, attachment and sender fixtures for transport tests."""

import asyncio
from pathlib import Path
from uuid import uuid4

from shiori_sdk.channels.services import OutboundHandler
from shiori_sdk.messages import InboundMessage, OutboundMessage


class FakeMessageBus:
    """Record admitted input and dispatch replies without runtime leases or retry policy."""

    def __init__(self):
        self.inbound: list[InboundMessage] = []
        self._inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self.outbound: dict[str, list[OutboundHandler]] = {}
        # (channel, chat_id, external_message_id) of replies a test marks as
        # still queued in the host; the fake itself dispatches immediately.
        self.pending_outbound: set[tuple[str, str, str]] = set()

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

    def subscribe_outbound(
        self,
        channel: str,
        callback: OutboundHandler,
        *,
        supports_reply_sequence: bool = False,
    ) -> None:
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
        """Whether the test marked this turn's committed reply as still queued."""
        return (channel, chat_id, external_message_id) in self.pending_outbound


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


class FakeInterruptResult:
    """The control-plane reply a channel shows the sender after ``/stop``."""

    def __init__(self, *, status: str, session_key: str, message: str):
        self.status, self.session_key, self.message = status, session_key, message


class FakeInterruptController:
    """Record interrupt requests and answer with a fixture-selected reply.

    The host matches the session and exact transport origin; this fake only
    records the request, so tests assert who asked and what the channel sent.
    """

    def __init__(self, *, message: str = "已中断", status: str = "interrupted"):
        self.message, self.status = message, status
        self.requests: list[dict[str, str]] = []

    def request_interrupt(
        self,
        session_key: str,
        sender: str = "",
        command: str = "/stop",
        *,
        channel: str = "",
        chat_id: str = "",
        account_id: str = "",
        chat_type: str = "",
        message_thread_id: str = "",
    ) -> FakeInterruptResult:
        """Record the request; the reply text is the fixture's ``message``."""
        self.requests.append(
            {
                "session_key": session_key,
                "sender": sender,
                "command": command,
                **({"channel": channel, "chat_id": chat_id} if channel else {}),
                **({"account_id": account_id} if account_id else {}),
                **({"chat_type": chat_type} if chat_type else {}),
                **(
                    {"message_thread_id": message_thread_id}
                    if message_thread_id
                    else {}
                ),
            }
        )
        return FakeInterruptResult(
            status=self.status, session_key=session_key, message=self.message
        )
