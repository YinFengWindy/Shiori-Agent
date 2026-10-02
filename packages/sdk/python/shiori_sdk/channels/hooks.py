"""Optional channel presentation hooks shared by host and plugins."""

from typing import Protocol, runtime_checkable


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
