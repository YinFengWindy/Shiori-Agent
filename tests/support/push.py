"""Message push helpers for host tests."""

from __future__ import annotations


def allow_every_role_target(_role_id: str, _channel: str, _chat_id: str) -> bool:
    """A role target check that admits any target.

    For tests about delivery rather than the role check: passing it makes the
    open check visible where the ``MessagePushTool`` is built. Tests of the
    check itself pass the runtime's ``_validate_role_target`` or their own rule.
    """
    return True
