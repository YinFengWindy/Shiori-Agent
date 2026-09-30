"""CQ mention and reply parsing shared by QQ account intake and message conversion."""

from __future__ import annotations

import re

_CQ_AT_RE = re.compile(r"\[CQ:at,qq=(\d+)[^\]]*\]")
# NapCat message IDs are signed 32-bit hashes, so a replied-to ID may be negative.
_CQ_REPLY_RE = re.compile(r"\[CQ:reply,(?:[^\]]*,)?id=(-?\d+)[^\]]*\]")


def at_member_ids(raw_message: str) -> tuple[str, ...]:
    """The QQ numbers a message structurally mentions (@), in order, deduplicated.

    ``@全体成员`` (``qq=all``) names no member and is left out.
    """
    return tuple(dict.fromkeys(_CQ_AT_RE.findall(raw_message)))


def reply_message_id(raw_message: str) -> str | None:
    """The message ID the message's CQ reply segment points at; None without one."""
    match = _CQ_REPLY_RE.search(raw_message)
    return match.group(1) if match else None


def strip_at_segments(raw_message: str) -> str:
    """Remove CQ mentions from message text."""
    return _CQ_AT_RE.sub("", raw_message).strip()


def strip_reply_segments(raw_message: str) -> str:
    """Remove CQ reply segments from message text; the reply target is metadata."""
    return _CQ_REPLY_RE.sub("", raw_message).strip()
