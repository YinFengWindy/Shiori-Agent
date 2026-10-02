import asyncio
from contextvars import ContextVar
from unittest.mock import AsyncMock

import pytest

from shiori_sdk.messages import InboundMessage
from infra.channels.intake import ChannelIntake


def message(content="pending"):
    return InboundMessage(channel="chat", sender="user", chat_id="one", content=content)


@pytest.mark.asyncio
async def test_pause_buffers_without_admission_and_resume_delivers_after_publication():
    generation = [1]
    accepted = []

    async def accept(item):
        accepted.append((item.content, generation[0]))

    intake = ChannelIntake(accept, AsyncMock())
    intake.pause()
    await intake.submit(message("first"))
    await intake.submit(message("second"))
    assert accepted == []
    intake.resume()
    assert accepted == []
    generation[0] = 2
    await intake.drain()
    assert accepted == [("first", 2), ("second", 2)]
    await intake.close()


@pytest.mark.asyncio
async def test_connection_close_replies_through_old_credentials_instead_of_accepting_input():
    sent = []
    accepted = AsyncMock()

    async def old_account(chat_id, text):
        sent.append(("account-A", chat_id, text))

    intake = ChannelIntake(accepted, old_account)
    intake.pause()
    await intake.submit(message())
    await intake.close()
    accepted.assert_not_awaited()
    assert len(sent) == 1
    assert sent[0][:2] == ("account-A", "one")
    assert "重新发送" in sent[0][2]


@pytest.mark.asyncio
async def test_rollback_repause_before_cleanup_prevents_scheduled_candidate_input():
    accepted = AsyncMock()
    send = AsyncMock()
    intake = ChannelIntake(accepted, send)
    intake.pause()
    await intake.submit(message())
    intake.resume()
    intake.pause()
    await asyncio.sleep(0)
    accepted.assert_not_awaited()
    await intake.close()
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_capacity_overflow_gets_explicit_retry_notice():
    accepted = AsyncMock()
    send = AsyncMock()
    intake = ChannelIntake(accepted, send, capacity=1)
    intake.pause()
    await intake.submit(message("buffered"))
    await intake.submit(message("overflow"))
    send.assert_awaited_once()
    intake.resume()
    await intake.drain()
    assert [call.args[0].content for call in accepted.await_args_list] == ["buffered"]
    await intake.close()


@pytest.mark.asyncio
async def test_replay_does_not_inherit_the_apply_requests_runtime_context():
    inherited = ContextVar("inherited-generation", default="new")
    accepted = []

    async def accept(item):
        accepted.append(inherited.get())

    intake = ChannelIntake(accept, AsyncMock())
    intake.pause()
    await intake.submit(message())
    token = inherited.set("old")
    try:
        intake.resume()
        await intake.drain()
    finally:
        inherited.reset(token)
    assert accepted == ["new"]
    await intake.close()


@pytest.mark.asyncio
async def test_failed_buffered_admission_sends_retry_and_propagates_failure():
    accepted = AsyncMock(side_effect=RuntimeError("admission failed"))
    send = AsyncMock()
    intake = ChannelIntake(accepted, send)
    intake.pause()
    await intake.submit(message())
    intake.resume()
    with pytest.raises(ExceptionGroup, match="Channel intake failed"):
        await intake.drain()
    send.assert_awaited_once()
    await intake.close()
