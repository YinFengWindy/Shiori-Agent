"""Narrow injected channel services; implementations and ownership belong to the host."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from shiori_sdk.messages import InboundMessage, OutboundMessage
from .identity import IdentityScope
from .identity_index import IdentityIndexes

type Sender = Callable[[str, str], Awaitable[str | None]]
type OutboundHandler = Callable[[OutboundMessage], Awaitable[None]]
type InboundHandler = Callable[[InboundMessage], Awaitable[None]]

# Admission limits shared by the host intake and the SDK fake.
CHANNEL_INTAKE_CAPACITY = 256
"""Messages one paused connection buffers before replying with a retry notice."""
CHANNEL_INTAKE_RETRY_NOTICE = "渠道配置正在切换，这条消息尚未处理，请稍后重新发送。"
"""Reply for input that a closed, full or failing intake could not admit."""


class MessageBus(Protocol):
    """Publish admitted input and register connection-owned reply handlers."""

    async def publish_inbound(self, msg: InboundMessage) -> None: ...
    def subscribe_outbound(
        self,
        channel: str,
        callback: OutboundHandler,
        *,
        supports_reply_sequence: bool = False,
    ) -> None:
        """Register transport; sequence opt-in promises bounded sends and delivery_outcome receipts."""
        ...

    def unsubscribe_outbound(self, channel: str, callback: OutboundHandler) -> None: ...
    def has_pending_outbound(
        self, channel: str, chat_id: str, external_message_id: str
    ) -> bool:
        """Whether a committed reply still owns this turn's live preview."""
        ...


class ChannelIntake(Protocol):
    """Bounded admission buffering, retained on its original connection during handover."""

    def start(self, *, paused: bool = False) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    async def submit(self, message: InboundMessage) -> None: ...
    async def drain(self) -> None: ...
    async def close(self) -> None: ...


class IntakeFactory(Protocol):
    """Create host-owned admission coordination for one connection's callbacks."""

    def __call__(self, accept: InboundHandler, send: Sender) -> ChannelIntake: ...


class AttachmentStore(Protocol):
    """Allocate and persist received media in the host-selected upload directory."""

    def create_path(self, prefix: str, suffix: str) -> Path: ...
    def write_bytes(self, data: bytes, *, prefix: str, suffix: str) -> Path: ...


class ChannelSessions(IdentityIndexes, Protocol):
    """Read transport identity metadata without exposing the session repository."""

    def get_channel_metadata(self, channel: str) -> Sequence[Mapping[str, object]]: ...
    async def remember_channel_identity(
        self, channel: str, chat_id: str, key: str, value: str
    ) -> None:
        """Persist a normalized identity only when the metadata value changed."""
        ...


class InterruptResult(Protocol):
    """The control-plane response presented to the sender."""

    @property
    def message(self) -> str: ...


class InterruptController(Protocol):
    """Interrupt a turn without placing a command on the conversation queue."""

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
    ) -> InterruptResult:
        """Target the receiving account/chat/topic; omitted scope never widens it.

        Pass the inbound chat type and opaque topic ID (empty outside a topic).
        Session-only calls remain supported for desktop and legacy turns.
        """
        ...


class ChannelHub(Protocol):
    """Host admission, account routing, identity pairing and delivery persistence."""

    def is_sender_allowed(
        self,
        *,
        channel: str,
        chat_id: str,
        sender_id: str,
        sender_alias: str = "",
        account_id: str = "",
    ) -> bool: ...
    def is_sender_blocked(
        self,
        *,
        channel: str,
        chat_id: str,
        sender_id: str,
        sender_alias: str = "",
    ) -> bool: ...
    def route_inbound(self, message: InboundMessage) -> InboundMessage: ...
    def route_account_inbound(
        self,
        message: InboundMessage,
        *,
        on_heard: Callable[[InboundMessage], None] | None = None,
    ) -> InboundMessage | None: ...
    def claim_pairing(
        self, message: InboundMessage, *, scope: IdentityScope
    ) -> bool: ...
    def resolve_runtime_session_key(self, channel: str, chat_id: str) -> str: ...
    def resolve_account_runtime_session_key(self, account_id: str) -> str: ...
    def mark_delivery(
        self,
        message: OutboundMessage,
        *,
        default_channel: str,
        delivery_status: str,
        external_message_id: str = "",
        via_account: dict[str, str] | None = None,
    ) -> object: ...
