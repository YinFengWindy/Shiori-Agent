import asyncio

import pytest

from shiori_sdk.external_turns import ExternalTurnMessage, ExternalTurnResult
from shiori_sdk.testing.external_turns import FakeExternalTurns


def _message(message_id: str) -> ExternalTurnMessage:
    return ExternalTurnMessage(
        role_id="mira",
        platform="bilibili",
        conversation_id="room-1",
        conversation_title="直播间",
        sender_id="uid-7",
        sender_name="观众七",
        message_id=message_id,
        text="主播好",
    )


async def test_answers_in_order_and_fails_when_none_is_queued():
    release = asyncio.Event()

    async def in_flight(message: ExternalTurnMessage) -> ExternalTurnResult:
        await release.wait()
        return ExternalTurnResult("replied", f"re:{message.message_id}")

    turns = FakeExternalTurns([ExternalTurnResult("busy"), in_flight])

    assert (await turns.submit(_message("m1"))).status == "busy"
    pending = asyncio.create_task(turns.submit(_message("m2")))
    await asyncio.sleep(0)
    assert not pending.done()
    release.set()
    assert await pending == ExternalTurnResult("replied", "re:m2")
    with pytest.raises(AssertionError, match="没有排队的结果"):
        await turns.submit(_message("m3"))
    assert [item.message_id for item in turns.submitted] == ["m1", "m2", "m3"]
