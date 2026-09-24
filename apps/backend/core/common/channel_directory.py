"""Optional channel hooks the core consults instead of hardcoded channel names.

A channel (built into the host or contributed by a plugin) may implement any of
the hook protocols below. Every hook is optional: a channel without it gets the
neutral default, so the core never needs to know a channel by name. The only
name the core owns is the reserved ``desktop`` transport.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

DESKTOP_CHANNEL = "desktop"
UNKNOWN_CHAT_TYPE = "unknown"


@runtime_checkable
class SupportsStreamEvents(Protocol):
    """Opts a channel into ``StreamDeltaReady`` events for chats it renders live.

    Without this hook a channel only receives the completed outbound reply.
    """

    def supports_stream_events(self, chat_id: str) -> bool: ...


@runtime_checkable
class SupportsSystemPromptHint(Protocol):
    """Adds channel-specific rules after the system prompt of a turn.

    The returned Markdown is appended verbatim (after a blank line); an empty
    string adds nothing.
    """

    def system_prompt_hint(self, chat_id: str) -> str: ...


@runtime_checkable
class SupportsDefaultChatType(Protocol):
    """Declares the ``chat_type`` assumed when an inbound message omits it."""

    default_chat_type: str


ChannelLookup = Callable[[str], object | None]


def _no_channels(_name: str) -> object | None:
    return None


def _is_desktop_session(chat_id: str) -> bool:
    """Accepts role-owned desktop session keys emitted by the bridge."""

    return chat_id.startswith("role:") and len(chat_id) > len("role:")


class ChannelDirectory:
    """Answers per-channel policy questions from the published channel set.

    The directory outlives runtime generations. The application binds it once
    to the long-lived channel host, whose connections change on handover; until
    then (and in isolated tests) every external channel gets neutral defaults.
    """

    def __init__(self) -> None:
        self._lookup: ChannelLookup = _no_channels

    def bind(self, lookup: ChannelLookup) -> None:
        """Resolves channel names through ``lookup`` from now on."""
        self._lookup = lookup

    def supports_stream_events(self, channel: str, chat_id: str) -> bool:
        """Returns whether a turn for this chat should publish stream deltas."""
        if channel == DESKTOP_CHANNEL:
            return _is_desktop_session(chat_id)
        target = self._lookup(channel)
        return isinstance(target, SupportsStreamEvents) and bool(
            target.supports_stream_events(chat_id)
        )

    def system_prompt_hint(self, channel: str, chat_id: str) -> str:
        """Returns the channel's extra system prompt rules, or an empty string."""
        target = self._lookup(channel)
        if not isinstance(target, SupportsSystemPromptHint):
            return ""
        return str(target.system_prompt_hint(chat_id) or "").strip()

    def default_chat_type(self, channel: str) -> str:
        """Returns the chat type assumed for inbound messages without one."""
        target = self._lookup(channel)
        if not isinstance(target, SupportsDefaultChatType):
            return UNKNOWN_CHAT_TYPE
        return str(target.default_chat_type or "").strip() or UNKNOWN_CHAT_TYPE
