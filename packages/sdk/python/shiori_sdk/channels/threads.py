"""Conversation thread IDs of a role's channel sessions.

The host's conversation store and the SDK's ``FakeChannelHub`` both name an
external chat's thread with ``network_thread_id``, so a routed message carries
the same ``thread_id`` in plugin tests as in the host.
"""

from __future__ import annotations


def role_thread_prefix(role_id: str) -> str:
    """The prefix every thread ID of ``role_id`` starts with."""
    return f"thread:{role_id}:"


def network_thread_id(role_id: str, channel: str, chat_id: str) -> str:
    """The thread ID of one role's session in an external channel chat."""
    return f"{role_thread_prefix(role_id)}{channel}:{chat_id}"
