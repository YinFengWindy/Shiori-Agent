"""Model-authored message boundaries and cancellable complete-message delivery."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from shiori_sdk.reply_sequence import ReplySequencePolicy

_BUFFERED_REPLY: ContextVar[bool] = ContextVar("buffered_reply", default=False)
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


@contextmanager
def buffered_reply_scope(enabled: bool) -> Iterator[None]:
    """Keep unshown model text out of interruption snapshots for this turn."""
    token = _BUFFERED_REPLY.set(enabled)
    try:
        yield
    finally:
        _BUFFERED_REPLY.reset(token)


def reply_is_buffered() -> bool:
    """Whether progress observers must keep model text private."""
    return _BUFFERED_REPLY.get()


def presented_tool_chain(
    groups: Sequence[dict[str, Any]], *, buffered: bool
) -> list[dict[str, Any]]:
    """Retain tool facts and thinking while hiding dialogue never published.

    Both interrupted progress and completed results use this projection. The
    reasoning loop's private trace remains intact for subsequent model requests.
    """
    return [{**group, "text": ""} if buffered else dict(group) for group in groups]


@dataclass(frozen=True)
class ReplySequence:
    """Validated message contents in the exact order chosen by the model."""

    messages: tuple[str, ...]

    @property
    def content(self) -> str:
        """Plain dialogue used by whole-turn observers without protocol markers."""
        return "\n\n".join(self.messages)


def parse_reply_sequence(content: str, policy: ReplySequencePolicy) -> ReplySequence:
    """Split only explicit boundary lines, preserving ordinary and fenced text."""
    parts: list[str] = []
    lines: list[str] = []
    fence = ""
    for line in content.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        match = _FENCE.match(line.rstrip("\r\n"))
        if match:
            marker, suffix = match.groups()
            if not fence:
                if marker[0] != "`" or "`" not in suffix:
                    fence = marker
            elif (
                marker[0] == fence[0]
                and len(marker) >= len(fence)
                and not suffix.strip()
            ):
                fence = ""
            lines.append(line)
        elif (
            not fence
            and len(stripped) - len(stripped.lstrip(" ")) < 4
            and not stripped.startswith("\t")
            and stripped.strip() == policy.separator
        ):
            part = _without_boundary_blank_lines(lines)
            if not part.strip():
                raise ValueError("消息分隔符之间不能是空消息")
            parts.append(part)
            lines = []
        else:
            lines.append(line)
    tail = _without_boundary_blank_lines(lines)
    if parts and not tail.strip():
        raise ValueError("回复不能以消息分隔符结束")
    return ReplySequence(tuple([*parts, tail]))


def _without_boundary_blank_lines(lines: list[str]) -> str:
    start, end = 0, len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    # Preserve indented code and Markdown hard-break spaces on content lines.
    return "".join(lines[start:end]).rstrip("\r\n")


def message_pause(content: str) -> float:
    """A short bounded reading pause; it never changes message boundaries."""
    return min(1.8, max(0.6, len(content) * 0.025))


async def wait_between_messages(seconds: float) -> None:
    """Yield during pacing; the owning seam allows tests to control time."""
    await asyncio.sleep(seconds)


async def deliver_reply_sequence(
    sequence: ReplySequence,
    publish: Callable[[int, str], Awaitable[None]],
) -> None:
    """Publish serially; finish a started commit/event before propagating cancel."""
    for index, content in enumerate(sequence.messages):
        if index:
            await wait_between_messages(message_pause(sequence.messages[index - 1]))
        task = asyncio.ensure_future(publish(index, content))
        cancelled = False
        while True:
            try:
                await asyncio.shield(task)
                break
            except asyncio.CancelledError:
                if task.cancelled():
                    raise
                cancelled = True
                if task.done():
                    task.result()
                    break
        if cancelled:
            raise asyncio.CancelledError
