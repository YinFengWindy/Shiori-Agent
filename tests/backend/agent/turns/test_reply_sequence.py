"""Cancellation cannot start the next message after a started publish."""

import asyncio

import pytest

from agent.turns.reply_sequence import ReplySequence, deliver_reply_sequence


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
