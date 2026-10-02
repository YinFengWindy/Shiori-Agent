"""The intake fake answers rejected input the way the host intake does."""

import pytest

from shiori_sdk.channels.services import (
    CHANNEL_INTAKE_CAPACITY,
    CHANNEL_INTAKE_RETRY_NOTICE,
)
from shiori_sdk.messages import InboundMessage
from shiori_sdk.testing.channel_intake import FakeChannelIntake


def _message(content: str) -> InboundMessage:
    return InboundMessage(channel="chat", sender="user", chat_id="one", content=content)


class _Recorder:
    def __init__(self, *, fail: bool = False) -> None:
        self.accepted: list[str] = []
        self.sent: list[tuple[str, str]] = []
        self.fail = fail

    async def accept(self, message: InboundMessage) -> None:
        if self.fail:
            raise RuntimeError("admission failed")
        self.accepted.append(message.content)

    async def send(self, chat_id: str, text: str) -> str | None:
        self.sent.append((chat_id, text))
        return None


async def test_submit_after_close_replies_with_retry_notice() -> None:
    recorder = _Recorder()
    intake = FakeChannelIntake(recorder.accept, recorder.send)
    await intake.close()

    await intake.submit(_message("late"))

    assert recorder.accepted == []
    assert recorder.sent == [("one", CHANNEL_INTAKE_RETRY_NOTICE)]


async def test_default_capacity_overflow_replies_with_retry_notice() -> None:
    recorder = _Recorder()
    intake = FakeChannelIntake(recorder.accept, recorder.send)
    intake.pause()
    for index in range(CHANNEL_INTAKE_CAPACITY + 1):
        await intake.submit(_message(str(index)))

    assert recorder.sent == [("one", CHANNEL_INTAKE_RETRY_NOTICE)]
    intake.resume()
    await intake.drain()
    assert recorder.accepted == [str(index) for index in range(CHANNEL_INTAKE_CAPACITY)]
    await intake.close()


async def test_failed_replay_is_recorded_answered_and_reported_on_drain() -> None:
    recorder = _Recorder(fail=True)
    intake = FakeChannelIntake(recorder.accept, recorder.send)
    intake.pause()
    await intake.submit(_message("buffered"))
    intake.resume()

    with pytest.raises(ExceptionGroup, match="Channel intake failed"):
        await intake.drain()
    assert recorder.sent == [("one", CHANNEL_INTAKE_RETRY_NOTICE)]
    await intake.close()
