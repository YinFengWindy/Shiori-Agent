"""CQ mention parsing shared by QQ account intake and message conversion."""

from __future__ import annotations

import re

_CQ_AT_RE = re.compile(r"\[CQ:at,qq=(\d+)[^\]]*\]")


def is_at_bot(raw_message: str, bot_uin: str) -> bool:
    """Return whether a CQ mention names this QQ account."""
    return any(qq == bot_uin for qq in _CQ_AT_RE.findall(raw_message))


def strip_at_segments(raw_message: str) -> str:
    """Remove CQ mentions from message text."""
    return _CQ_AT_RE.sub("", raw_message).strip()
