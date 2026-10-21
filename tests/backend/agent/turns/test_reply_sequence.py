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


def test_rejects_blank_or_embedded_separator():
    for separator in ("", " ", " x", "x\ny"):
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


def test_validated_message_list_cannot_silently_lose_its_boundaries():
    policy = ReplySequencePolicy("<host-boundary/>", message_count=2)
    with pytest.raises(ValueError, match="丢失边界"):
        parse_reply_sequence("第一条\n\n第二条", policy)
    assert parse_reply_sequence(
        "```python\n未闭合代码\n<host-boundary/>\n另一条消息", policy
    ).messages == ("```python\n未闭合代码", "另一条消息")


def test_message_boundary_preserves_first_line_indentation_and_trailing_spaces():
    result = parse_reply_sequence(
        '\n前一句  \n\n<message-break/>\n\n    print("hello")  \n\n', POLICY
    )
    assert result.messages == ("前一句  ", '    print("hello")  ')


def test_markdown_indent_of_four_keeps_the_separator_inside_the_message():
    for indent in ("    ", "\t"):
        content = f"{indent}<message-break/>\n"
        assert parse_reply_sequence(content, POLICY).messages == (content.rstrip("\n"),)
    for indent in ("", "   "):
        result = parse_reply_sequence(f"one\n{indent}<message-break/>\ntwo", POLICY)
        assert result.messages == ("one", "two")


def test_empty_segments_are_rejected():
    for content in ("<message-break/>\na", "a\n<message-break/>\n<message-break/>\nb"):
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


@pytest.mark.parametrize("failure", [OSError, asyncio.CancelledError])
async def test_failed_publish_does_not_attempt_the_tail(failure):
    sent = []

    async def publish(index, content):
        sent.append(content)
        raise failure("publish failed")

    with pytest.raises(failure):
        await deliver_reply_sequence(ReplySequence(("one", "two")), publish)
    assert sent == ["one"]
