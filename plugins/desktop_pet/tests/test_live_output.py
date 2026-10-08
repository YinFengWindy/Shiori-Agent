"""Live-reply output: events to the pet background and outcomes back by reply id."""

import pytest
from shiori_sdk.rpc import Concurrency
from shiori_sdk.testing.memory_context import FakeRpc
from plugins.desktop_pet.backend.live_output import (
    LiveReplyOutcome,
    LiveReplyOutput,
    OutputResult,
)


async def test_show_and_cancel_emit_the_background_contract():
    rpc = FakeRpc()
    output = LiveReplyOutput(rpc)
    await output.show(role_id="mira", reply_id="r1", run_id="run", text="你好")
    await output.cancel("run")
    await output.cancel()
    assert rpc.events == [
        (
            "live.reply.show",
            {
                "source": "live",
                "role_id": "mira",
                "reply_id": "r1",
                "run_id": "run",
                "text": "你好",
            },
        ),
        ("live.cancel", {"run_id": "run"}),
        ("live.cancel", {}),
    ]
    assert rpc.concurrency["live.reply.outcome"] is Concurrency.READ_ONLY
    assert rpc.admission_exempt["live.reply.outcome"] is True


async def test_outcomes_reach_subscribers_until_they_unsubscribe():
    rpc = FakeRpc()
    output = LiveReplyOutput(rpc)
    received: list[LiveReplyOutcome] = []

    async def listener(outcome: LiveReplyOutcome) -> None:
        received.append(outcome)

    unsubscribe = output.subscribe(listener)
    payload = {
        "reply_id": "r1",
        "run_id": "run",
        "bubble": {"status": "succeeded"},
        "speech": {"status": "failed", "error": "合成失败"},
    }
    assert await rpc.handlers["live.reply.outcome"](payload) == {"ok": True}
    assert received == [
        LiveReplyOutcome(
            reply_id="r1",
            run_id="run",
            bubble=OutputResult("succeeded"),
            speech=OutputResult("failed", "合成失败"),
        )
    ]
    unsubscribe()
    await rpc.handlers["live.reply.outcome"](payload)
    assert len(received) == 1


async def test_malformed_outcomes_are_rejected():
    rpc = FakeRpc()
    LiveReplyOutput(rpc)
    with pytest.raises(ValueError, match="reply_id"):
        await rpc.handlers["live.reply.outcome"](
            {"run_id": "run", "bubble": {"status": "succeeded"}}
        )
    with pytest.raises(ValueError, match="speech"):
        await rpc.handlers["live.reply.outcome"](
            {
                "reply_id": "r1",
                "run_id": "run",
                "bubble": {"status": "succeeded"},
                "speech": {"status": "done"},
            }
        )
