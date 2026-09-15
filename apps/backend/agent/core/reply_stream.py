"""Incremental formal content decoding with a stable, already-delivered prefix."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from core.roles.reply_state import InvalidRoleReply


def _content_prefix(raw: str) -> str:
    decoder = json.JSONDecoder()
    raw = raw.lstrip()
    if not raw.startswith("{"):
        return ""
    index = 1
    while index < len(raw):
        while index < len(raw) and raw[index].isspace():
            index += 1
        try:
            key, index = decoder.raw_decode(raw, index)
        except ValueError:
            return ""
        while index < len(raw) and raw[index].isspace():
            index += 1
        if index >= len(raw) or raw[index] != ":":
            return ""
        index += 1
        while index < len(raw) and raw[index].isspace():
            index += 1
        if key == "content":
            if index >= len(raw) or raw[index] != '"':
                return ""
            start = index
            index += 1
            end = index
            while index < len(raw):
                char = raw[index]
                if char == '"':
                    break
                if char == "\\":
                    length = 6 if raw[index : index + 2] == "\\u" else 2
                    if index + length > len(raw):
                        break
                    index += length
                else:
                    index += 1
                end = index
            try:
                value = json.loads(raw[start:end] + '"')
            except ValueError:
                return ""
            # Hold a split UTF-16 surrogate until its low surrogate arrives.
            return value[:-1] if value and 0xD800 <= ord(value[-1]) <= 0xDBFF else value
        try:
            _, index = decoder.raw_decode(raw, index)
        except ValueError:
            return ""
        while index < len(raw) and raw[index].isspace():
            index += 1
        if index >= len(raw) or raw[index] != ",":
            return ""
        index += 1
    return ""


class RoleReplyStream:
    """Expose only content, preserving the emitted prefix across one correction."""

    def __init__(self, sink: Callable[[dict[str, str]], Awaitable[None]] | None):
        self._sink = sink
        self._raw = ""
        self.emitted = ""

    def begin_attempt(self) -> None:
        """Reset JSON framing while retaining content already displayed or spoken."""
        self._raw = ""

    async def push(self, delta: dict[str, str] | str) -> None:
        """Decode top-level content and forward thinking only as a separate event."""
        payload = {"content_delta": delta} if isinstance(delta, str) else delta
        if self._sink and payload.get("thinking_delta"):
            await self._sink({"thinking_delta": payload["thinking_delta"]})
        self._raw += payload.get("content_delta", "")
        prefix = _content_prefix(self._raw)
        if prefix.startswith(self.emitted):
            await self._emit(prefix)

    async def finish(self, content: str) -> None:
        """Reject rewrites of spoken text and emit only the remaining final suffix."""
        if not content.startswith(self.emitted):
            raise InvalidRoleReply("格式纠正改写了已展示的 content")
        await self._emit(content)

    async def _emit(self, content: str) -> None:
        suffix = content[len(self.emitted) :]
        if self._sink and suffix:
            await self._sink({"content_delta": suffix})
            self.emitted = content
