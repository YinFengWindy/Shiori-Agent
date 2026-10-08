"""Status: one shape in every state, and current errors that clear on recovery."""

from plugins.desktop_pet.backend.bilibili_live_api import LiveRoom
from plugins.desktop_pet.backend.live_output import LiveReplyOutcome, OutputResult
from plugins.desktop_pet.backend.live_status import (
    ConnectionState,
    LiveCounter,
    LiveStatus,
    status_shape,
)


def outcome(reply_id: str, bubble: str, speech: str) -> LiveReplyOutcome:
    return LiveReplyOutcome(
        reply_id, "run", OutputResult(bubble, "x" if bubble == "failed" else ""),
        OutputResult(speech, "y" if speech == "failed" else ""),
    )  # fmt: skip


def test_running_and_idle_status_share_one_shape():
    idle = status_shape("mira")
    running = LiveStatus("mira", LiveRoom(1001, "t")).snapshot(
        queue_length=1, generating=False, output_pending=False
    )
    assert set(idle) == set(running)
    assert idle["counters"] == {counter.value: 0 for counter in LiveCounter}
    assert (idle["state"], idle["connection"], idle["room"]) == ("idle", None, None)


def test_errors_are_current_and_clear_when_the_condition_recovers():
    status = LiveStatus("mira", LiveRoom(1001, "t"))
    status.connection_failed(ConnectionState.RECONNECTING, "断开")
    assert status.snapshot()["connection_error"] == "断开"
    status.connected()
    assert status.snapshot()["connection_error"] == ""

    status.generated("r1")
    status.output_finished(outcome("r1", "failed", "succeeded"))
    assert status.reply_error == "气泡输出失败: x"
    status.generated("r2")
    status.output_finished(outcome("r2", "cancelled", "cancelled"))
    assert status.reply_error == "气泡输出失败: x", "a cancelled reply proves nothing"
    status.generated("r3")
    status.output_finished(outcome("r3", "succeeded", "skipped"))
    assert status.reply_error == ""


def test_recent_replies_are_bounded_and_newest_first():
    status = LiveStatus("mira", LiveRoom(1001, "t"))
    for index in range(12):
        status.generated(f"r{index}")
    recent = status.snapshot()["recent"]
    assert [record["reply_id"] for record in recent] == [
        f"r{n}" for n in range(11, 1, -1)
    ]
