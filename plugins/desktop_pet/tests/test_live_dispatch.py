"""The reply loop of one generation: pacing, expiry, busy, failures and output."""

import asyncio
import json

from shiori_sdk.external_turns import ExternalTurnMessage
from shiori_sdk.testing.external_turns import FakeExternalTurns

from plugins.desktop_pet.backend.bilibili_danmaku import Danmaku
from plugins.desktop_pet.backend.bilibili_live_api import LiveRoom
from plugins.desktop_pet.backend.live_config import LiveConfig
from plugins.desktop_pet.backend.live_dispatch import ReplyDispatcher
from plugins.desktop_pet.backend.live_queue import DanmakuQueue, QueuedDanmaku
from plugins.desktop_pet.backend.live_status import LiveStatus


class Loop:
    """A dispatcher running over a queue the test fills directly."""

    def __init__(self, clock, output, turns, *, interval=0, timeout=30):
        self.clock = clock
        self.queue = DanmakuQueue()
        self.status = LiveStatus("mira", LiveRoom(1001, "测试直播间"))
        self.bound = True
        config = LiveConfig(
            room_id=1, reply_interval_seconds=interval, wait_timeout_seconds=timeout
        )
        self.dispatcher = ReplyDispatcher(
            run_id="run-1",
            role_id="mira",
            room=LiveRoom(1001, "测试直播间"),
            queue=self.queue,
            config=lambda: config,
            turns=turns,
            output=output.output,
            still_bound=lambda: self.bound,
            status=self.status,
            clock=clock,
        )

        async def route(outcome):
            self.dispatcher.outcome(outcome)

        output.output.subscribe(route)
        self.task = asyncio.create_task(self.dispatcher.run())

    async def send(self, *message_ids: str) -> None:
        for message_id in message_ids:
            danmaku = Danmaku(message_id, 7, "小明", f"弹幕{message_id}")
            self.queue.push(QueuedDanmaku(danmaku, self.clock.now()))
        self.dispatcher.wake()
        await self.clock.settle()

    async def close(self) -> None:
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)

    def counter(self, name: str) -> int:
        return self.status.snapshot()["counters"][name]


async def test_reply_text_is_shown_once_and_status_records_both_paths(
    clock, pet_output, answers
):
    turns = FakeExternalTurns([answers.replied("  你好呀 ")])
    loop = Loop(clock, pet_output, turns)
    await loop.send("id-1")
    [message] = turns.submitted
    assert message == ExternalTurnMessage(
        role_id="mira",
        platform="bilibili",
        conversation_id="1001",
        conversation_title="测试直播间",
        sender_id="7",
        sender_name="小明",
        message_id="id-1",
        text="弹幕id-1",
    )
    [show] = pet_output.shows()
    assert (show["text"], show["run_id"]) == ("你好呀", "run-1")
    await pet_output.outcome(show, speech="skipped")
    [record] = loop.status.snapshot()["recent"]
    assert record["bubble"]["status"] == "succeeded"
    assert record["speech"]["status"] == "skipped"
    await loop.close()


async def test_next_reply_waits_for_the_outcome_then_the_interval(
    clock, pet_output, answers
):
    turns = FakeExternalTurns([answers.replied("一"), answers.replied("二")])
    loop = Loop(clock, pet_output, turns, interval=5, timeout=600)
    await loop.send("id-1", "id-2")
    await clock.advance(10)
    assert len(turns.submitted) == 1, "output still pending"
    await pet_output.outcome(pet_output.shows()[0])
    await clock.advance(4.9)
    assert len(turns.submitted) == 1
    await clock.advance(0.1)
    assert len(turns.submitted) == 2
    await loop.close()


async def test_missing_outcome_is_released_after_the_safety_timeout(
    clock, pet_output, answers
):
    turns = FakeExternalTurns([answers.replied("一"), answers.replied("二")])
    loop = Loop(clock, pet_output, turns, timeout=600)
    await loop.send("id-1", "id-2")
    await clock.advance(119)
    assert len(turns.submitted) == 1
    await clock.advance(1)
    assert len(turns.submitted) == 2
    status = loop.status.snapshot()
    assert status["recent"][1]["error"] == "未收到直播回复输出结果"
    await loop.close()


async def test_waiting_danmaku_expire_and_are_never_replayed(
    clock, pet_output, answers
):
    gate, cancelled = asyncio.Event(), []
    turns = FakeExternalTurns([answers.held(gate, "一", cancelled)])
    loop = Loop(clock, pet_output, turns, timeout=30)
    await loop.send("id-0")
    await loop.send(*(f"id-{n}" for n in range(1, 25)))
    assert loop.dispatcher.generating
    assert len(loop.queue) == 20, "bounded while the turn is slow"
    await clock.advance(30)
    gate.set()
    await clock.settle()
    await pet_output.outcome(pet_output.shows()[0])
    await clock.advance(60)
    assert len(turns.submitted) == 1
    assert (len(loop.queue), loop.counter("expired")) == (0, 20)
    await loop.close()


async def test_busy_role_is_retried_without_waiting_until_the_danmaku_expires(
    clock, pet_output, answers
):
    turns = FakeExternalTurns([answers.status("busy")] * 10)
    loop = Loop(clock, pet_output, turns, timeout=5)
    await loop.send("id-1")
    assert len(turns.submitted) == 1 and len(loop.queue) == 1
    await clock.advance(5)
    assert [m.message_id for m in turns.submitted] == ["id-1"] * 5
    assert (len(loop.queue), loop.counter("expired"), loop.counter("busy")) == (0, 1, 5)
    await clock.advance(10)
    assert len(turns.submitted) == 5 and pet_output.shows() == []
    await loop.close()


async def test_duplicate_result_is_skipped(clock, pet_output, answers):
    turns = FakeExternalTurns([answers.status("duplicate"), answers.replied("二")])
    loop = Loop(clock, pet_output, turns)
    await loop.send("id-1", "id-2")
    assert [show["text"] for show in pet_output.shows()] == ["二"]
    assert loop.counter("duplicates") == 1
    await loop.close()


async def test_failed_or_empty_generation_shows_nothing_and_a_reply_clears_it(
    clock, pet_output, answers
):
    turns = FakeExternalTurns(
        [
            answers.failing(RuntimeError("模型超时")),
            answers.replied(" "),
            answers.replied("好的"),
        ]
    )
    loop = Loop(clock, pet_output, turns)
    await loop.send("id-1", "id-2")
    assert pet_output.shows() == []
    status = loop.status.snapshot()
    assert [r["error"] for r in status["recent"]] == [
        "角色回复为空",
        "回复生成失败: 模型超时",
    ]
    assert status["reply_error"] == "角色回复为空"
    await loop.send("id-3")
    await pet_output.outcome(pet_output.shows()[0])
    assert loop.status.snapshot()["reply_error"] == ""
    await loop.close()


async def test_any_turn_failure_is_a_generation_failure_not_the_end_of_the_run(
    clock, pet_output, answers
):
    # ValueError subclasses raised inside the turn (JSON, validation) included.
    turns = FakeExternalTurns(
        [
            answers.failing(json.JSONDecodeError("bad", "{", 0)),
            answers.failing(ValueError("校验失败")),
            answers.replied("好的"),
        ]
    )
    loop = Loop(clock, pet_output, turns)
    await loop.send("id-1", "id-2", "id-3")
    assert not loop.task.done()
    assert loop.counter("generation_failed") == 2
    assert [show["text"] for show in pet_output.shows()] == ["好的"]
    await loop.close()


async def test_failed_output_paths_are_reported_without_regenerating(
    clock, pet_output, answers
):
    turns = FakeExternalTurns([answers.replied("一"), answers.replied("二")])
    loop = Loop(clock, pet_output, turns)
    await loop.send("id-1")
    await pet_output.outcome(pet_output.shows()[0], bubble="failed", error="窗口没了")
    await loop.send("id-2")
    await pet_output.outcome(pet_output.shows()[1], speech="failed", error="合成失败")
    status = loop.status.snapshot()
    assert [m.message_id for m in turns.submitted] == ["id-1", "id-2"]
    assert len(pet_output.shows()) == 2
    second, first = status["recent"]
    assert first["bubble"] == {"status": "failed", "error": "窗口没了"}
    assert first["speech"] == {"status": "succeeded", "error": ""}
    assert second["speech"] == {"status": "failed", "error": "合成失败"}
    assert status["reply_error"] == "语音输出失败: 合成失败"
    await loop.close()


async def test_undelivered_show_is_reported_and_does_not_block(
    clock, lost_pet_output, answers
):
    turns = FakeExternalTurns([answers.replied("一"), answers.replied("二")])
    loop = Loop(clock, lost_pet_output, turns)
    await loop.send("id-1", "id-2")
    assert len(lost_pet_output.shows()) == 2
    assert loop.status.snapshot()["reply_error"] == "桌宠后台未接收直播回复"
    await loop.close()


async def test_reply_of_a_role_that_is_no_longer_the_pet_is_dropped(
    clock, pet_output, answers
):
    turns = FakeExternalTurns([answers.replied("旧角色")])
    loop = Loop(clock, pet_output, turns)
    loop.bound = False
    await loop.send("id-1")
    assert turns.submitted == [], "no turn for a role that is no longer the pet"
    assert pet_output.shows() == []
    assert loop.status.snapshot()["reply_error"] == "桌宠角色已切换或停用"
    await loop.close()
