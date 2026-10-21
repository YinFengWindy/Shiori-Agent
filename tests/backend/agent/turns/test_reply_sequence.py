"""Boundaries are model-authored; cancellation cannot start the next message."""

import asyncio

import pytest

from agent.turns.reply_sequence import (
    ReplySequence,
    deliver_reply_sequence,
    parse_reply_sequence,
)
from agent.turns.reply_sequence import ReplySequencePolicy

POLICY = ReplySequencePolicy("<message-break/>")


@pytest.mark.parametrize("separator", ["", " ", " x", "x\ny", "x\ry", "```x"])
def test_rejects_invalid_separator(separator):
    with pytest.raises(ValueError):
        ReplySequencePolicy(separator)


def test_only_explicit_boundaries_split_and_preserve_markdown():
    code = "```python\n<message-break/>\n```\n\n    <message-break/>"
    result = parse_reply_sequence(
        f"第一行\n第二行\n<message-break/>\n{code}\n<message-break/>\n最后一句", POLICY
    )
    assert result.messages == ("第一行\n第二行", code, "最后一句")
    assert parse_reply_sequence("只说一句。", POLICY).messages == ("只说一句。",)
    assert parse_reply_sequence("", POLICY).messages == ("",)


def test_message_boundary_preserves_first_line_indentation_and_trailing_spaces():
    result = parse_reply_sequence(
        '\n前一句  \n\n<message-break/>\n\n    print("hello")  \n\n', POLICY
    )
    assert result.messages == ("前一句  ", '    print("hello")  ')


@pytest.mark.parametrize("indent", ["    ", "\t", " \t", "  \t", "   \t", "\t "])
def test_markdown_four_column_indentation_keeps_separator_as_code(indent):
    content = f"{indent}<message-break/>\n"
    assert parse_reply_sequence(content, POLICY).messages == (content.rstrip("\n"),)


@pytest.mark.parametrize("indent", ["", " ", "  ", "   "])
def test_separator_at_zero_to_three_columns_splits_messages(indent):
    result = parse_reply_sequence(f"one\n{indent}<message-break/>\ntwo", POLICY)
    assert result.messages == ("one", "two")


@pytest.mark.parametrize(
    "content",
    [
        "<message-break/>\na",
        "a\n<message-break/>",
        "a\n<message-break/>\n<message-break/>\nb",
    ],
)
def test_empty_segments_are_rejected(content):
    with pytest.raises(ValueError):
        parse_reply_sequence(content, POLICY)


async def test_cancel_finishes_inflight_publish_and_never_starts_tail():
    entered, release = asyncio.Event(), asyncio.Event()
    sent = []

    async def publish(index, content):
        entered.set()
        await release.wait()
        sent.append((index, content))

    task = asyncio.create_task(
        deliver_reply_sequence(ReplySequence(("one", "two")), publish)
    )
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sent == [(0, "one")]


async def test_failed_publish_does_not_attempt_the_tail():
    sent = []

    async def publish(index, content):
        sent.append(content)
        raise OSError("publish failed")

    with pytest.raises(OSError):
        await deliver_reply_sequence(ReplySequence(("one", "two")), publish)
    assert sent == ["one"]
