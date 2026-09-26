"""Per-message platform provenance, independent of role-session routing."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from bus.events import InboundMessage

_PREFIX = "[消息来源: "
_TIME_PREFIX = "[当前消息时间:"


def _identifier(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    return str(value).strip() or None


@dataclass(frozen=True)
class MessageSource:
    """Immutable origin; channel and sender_id form a future member-profile key."""

    channel: str | None = None
    chat_id: str | None = None
    chat_type: str | None = None
    sender_id: str | None = None
    session_key: str | None = None

    @classmethod
    def from_inbound(cls, message: InboundMessage) -> MessageSource:
        """Capture platform fields, never mutable prompt-context aliases."""
        return cls(
            channel=_identifier(message.channel),
            chat_id=_identifier(message.chat_id),
            chat_type=_identifier(message.metadata.get("chat_type")),
            sender_id=_identifier(message.sender),
            session_key=_identifier(message.session_key),
        )

    @classmethod
    def from_metadata(
        cls, metadata: Mapping[str, Any], *, session_key: str
    ) -> MessageSource:
        """Reconstruct only recorded provenance; missing legacy fields stay unknown."""
        saved = metadata.get("message_source")
        if isinstance(saved, dict):
            return cls(
                channel=_identifier(saved.get("channel")),
                chat_id=_identifier(saved.get("chat_id")),
                chat_type=_identifier(saved.get("chat_type")),
                sender_id=_identifier(saved.get("sender_id")),
                session_key=_identifier(saved.get("session_key")),
            )
        return cls(
            channel=_identifier(metadata.get("transport_channel")),
            chat_id=_identifier(metadata.get("transport_chat_id")),
            chat_type=_identifier(metadata.get("chat_type")),
            sender_id=_identifier(metadata.get("sender_id")),
            session_key=session_key,
        )

    def to_metadata(self) -> dict[str, str | None]:
        """Serialize the captured source for durable per-message storage."""
        return asdict(self)


def with_message_source(
    content: str | list[dict[str, Any]], source: MessageSource
) -> str | list[dict[str, Any]]:
    """Add one source envelope without altering cached text or media blocks."""
    header = f"{_PREFIX}{json.dumps(source.to_metadata(), ensure_ascii=False)}]\n"
    if isinstance(content, str):
        return _with_text_source(content, header)
    blocks = [dict(block) for block in content]
    for block in blocks:
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            block["text"] = _with_text_source(block["text"], header)
            return blocks
    return [*blocks, {"type": "text", "text": header}]


def _with_text_source(content: str, header: str) -> str:
    if content.startswith(_TIME_PREFIX):
        stamp, separator, text = content.partition("\n")
        if text.startswith(header):
            text = text[len(header) :]
        return stamp + separator + header + text
    if content.startswith(header):
        content = content[len(header) :]
    return header + content
