"""A live run end to end: controllable source, fake turns, real output contract, fake clock."""

import asyncio
import json

from shiori_sdk.external_turns import ExternalTurnMessage, ExternalTurnResult
from shiori_sdk.testing.external_turns import FakeExternalTurns
from shiori_sdk.testing.memory_context import FakeRpc

from plugins.desktop_pet.backend.bilibili_credentials import BilibiliCredentials
from plugins.desktop_pet.backend.bilibili_live_api import LiveRoom
from plugins.desktop_pet.backend.bilibili_login import BilibiliLoginRequired
from plugins.desktop_pet.backend.live_config import LiveConfig
from plugins.desktop_pet.backend.live_output import LiveReplyOutput
from plugins.desktop_pet.backend.live_session import LiveSession, LiveSessionDeps

CREDENTIALS = BilibiliCredentials(
    uid=42, uname="主播", cookies={"SESSDATA": "s"}, refresh_token="r"
)
ROOM = LiveRoom(room_id=1001, title="测试直播间")


def replied(text: str) -> ExternalTurnResult:
    return ExternalTurnResult(status="replied", reply=text)


class Harness:
    """One session wired to fakes, with the pet's outcome RPC as the only way back."""

    def __init__(self, clock, source, turns, *, interval=0, timeout=30, rpc=None):
        self.clock = clock
        self.source = source
        self.turns = turns
        self.rpc = rpc or FakeRpc()
        self.bound = True
        self.login_valid = True
        self.ended: list[LiveSession] = []
        output = LiveReplyOutput(self.rpc)

        async def credentials(role_id: str) -> BilibiliCredentials:
            if not self.login_valid:
                raise BilibiliLoginRequired("B 站登录已失效，请重新扫码")
            return CREDENTIALS

        self.session = LiveSession(
            role_id="mira",
            room=ROOM,
            buvid="buvid-1",
            config=LiveConfig(
                room_id=1,
                reply_interval_seconds=interval,
                wait_timeout_seconds=timeout,
            ),
            deps=LiveSessionDeps(
                source=source,
                turns=turns,
                output=output,
                credentials=credentials,
                still_bound=lambda role_id: self.bound,
                clock=clock,
                spawn=lambda work, name: asyncio.create_task(work, name=name),
            ),
            on_ended=self.ended.append,
        )

        async def route(outcome):
            self.session.outcome(outcome)

        output.subscribe(route)

    async def start(self):
        self.session.start()
        await self.clock.settle()

    def shows(self) -> list[dict]:
        return [
            payload for name, payload in self.rpc.events if name == "live.reply.show"
        ]

    def cancels(self) -> list[dict]:
        return [payload for name, payload in self.rpc.events if name == "live.cancel"]

    async def outcome(
        self, show: dict, bubble="succeeded", speech="succeeded", error=""
    ):
        await self.rpc.handlers["live.reply.outcome"](
            {
                "reply_id": show["reply_id"],
                "run_id": show["run_id"],
                "bubble": {
                    "status": bubble,
                    "error": error if bubble == "failed" else "",
                },
                "speech": {
                    "status": speech,
                    "error": error if speech == "failed" else "",
                },
            }
        )
        await self.clock.settle()


def held(gate: asyncio.Event, reply: str, cancelled: list[str]):
    """A turn answer that stays in flight until ``gate`` opens."""

    async def answer(message: ExternalTurnMessage) -> ExternalTurnResult:
        try:
            await gate.wait()
        except asyncio.CancelledError:
            cancelled.append(message.message_id)
            raise
        return replied(reply)

    return answer


async def test_danmaku_reply_reaches_bubble_and_speech_as_one_text(
    clock, danmaku_source
):
    turns = FakeExternalTurns([replied("  欢迎来到直播间！ "), replied("你好呀")])
    harness = Harness(clock, danmaku_source, turns)
    await harness.start()
    assert danmaku_source.current.uid == 42
    assert danmaku_source.current.buvid == "buvid-1"

    danmaku_source.current.send("id-1", "主播好", uid=7, uname="小明")
    await clock.settle()

    assert turns.submitted == [
        ExternalTurnMessage(
            role_id="mira",
            platform="bilibili",
            conversation_id="1001",
            conversation_title="测试直播间",
            sender_id="7",
            sender_name="小明",
            message_id="id-1",
            text="主播好",
        )
    ]
    [show] = harness.shows()
    assert show["text"] == "欢迎来到直播间！"
    assert show["role_id"] == "mira"
    assert show["run_id"] == harness.session.status.run_id
    await harness.outcome(show)
    status = harness.session.snapshot()
    assert status["recent"] == [
        {
            "reply_id": show["reply_id"],
            "generation": "replied",
            "error": "",
            "bubble": {"status": "succeeded", "error": ""},
            "speech": {"status": "succeeded", "error": ""},
        }
    ]
    assert status["connection"] == "connected"

    # The logged-in account's own danmaku is an ordinary viewer message.
    danmaku_source.current.send("id-2", "我自己发的", uid=42, uname="主播")
    await clock.settle()
    assert turns.submitted[-1].sender_id == "42"
    assert len(harness.shows()) == 2
    await harness.session.stop("test")


async def test_repeated_delivery_and_reconnect_replay_reply_once(clock, danmaku_source):
    turns = FakeExternalTurns([replied("一"), replied("二"), replied("三")])
    harness = Harness(clock, danmaku_source, turns)
    await harness.start()
    first = danmaku_source.current
    first.send("id-1", "你好")
    first.send("id-1", "你好")
    await clock.settle()
    await harness.outcome(harness.shows()[0])

    first.drop(ConnectionError("reset"))
    await clock.settle()
    assert harness.session.snapshot()["connection"] == "reconnecting"
    await clock.advance(1)
    second = danmaku_source.current
    assert second is not first
    # The replay repeats id-1; a different viewer's equal text is a new message.
    second.send("id-1", "你好")
    second.send("id-2", "你好", uid=8)
    await clock.settle()

    assert [message.message_id for message in turns.submitted] == ["id-1", "id-2"]
    assert len(harness.shows()) == 2
    assert harness.session.snapshot()["counters"]["redelivered"] == 2
    await harness.session.stop("test")


async def test_next_reply_waits_for_output_outcome_then_interval(clock, danmaku_source):
    turns = FakeExternalTurns([replied("一"), replied("二")])
    harness = Harness(clock, danmaku_source, turns, interval=5)
    await harness.start()
    danmaku_source.current.send("id-1", "一")
    danmaku_source.current.send("id-2", "二")
    await clock.settle()
    assert len(turns.submitted) == 1
    await clock.advance(10)
    assert len(turns.submitted) == 1, "output still pending"

    await harness.outcome(harness.shows()[0])
    await clock.advance(4.9)
    assert len(turns.submitted) == 1
    await clock.advance(0.1)
    assert len(turns.submitted) == 2
    await harness.session.stop("test")


async def test_missing_outcome_is_released_after_safety_timeout(clock, danmaku_source):
    turns = FakeExternalTurns([replied("一"), replied("二")])
    harness = Harness(clock, danmaku_source, turns, timeout=600)
    await harness.start()
    danmaku_source.current.send("id-1", "一")
    danmaku_source.current.send("id-2", "二")
    await clock.settle()
    await clock.advance(119)
    assert len(turns.submitted) == 1
    await clock.advance(1)
    assert len(turns.submitted) == 2
    status = harness.session.snapshot()
    assert status["recent"][1]["error"] == "未收到直播回复输出结果"
    await harness.session.stop("test")


async def test_burst_is_bounded_expires_and_never_replays_backlog(
    clock, danmaku_source
):
    gate, cancelled = asyncio.Event(), []
    turns = FakeExternalTurns([held(gate, "一", cancelled)])
    harness = Harness(clock, danmaku_source, turns, timeout=30)
    await harness.start()
    danmaku_source.current.send("id-0", "弹幕0")
    await clock.settle()
    for index in range(1, 25):
        danmaku_source.current.send(f"id-{index}", f"弹幕{index}")
    await clock.settle()
    status = harness.session.snapshot()
    assert status["generating"] is True
    assert status["queue_length"] == 20
    assert status["counters"]["evicted"] == 4

    await clock.advance(30)
    gate.set()
    await clock.settle()
    # Everything that waited through the slow turn expired instead of replaying.
    status = harness.session.snapshot()
    assert (status["queue_length"], status["counters"]["expired"]) == (0, 20)
    await harness.outcome(harness.shows()[0])
    await clock.advance(60)
    assert len(turns.submitted) == 1
    await harness.session.stop("test")


async def test_busy_role_is_not_waited_for_and_the_danmaku_expires(
    clock, danmaku_source
):
    busy = ExternalTurnResult(status="busy")
    turns = FakeExternalTurns([busy] * 10)
    harness = Harness(clock, danmaku_source, turns, timeout=5)
    await harness.start()
    danmaku_source.current.send("id-1", "在吗")
    await clock.settle()
    assert len(turns.submitted) == 1
    assert harness.session.snapshot()["queue_length"] == 1
    await clock.advance(5)
    # Retried once per second while it waited, then dropped; nothing shown.
    assert [message.message_id for message in turns.submitted] == ["id-1"] * 5
    status = harness.session.snapshot()
    assert status["queue_length"] == 0
    assert status["counters"]["expired"] == 1
    assert harness.shows() == []
    await clock.advance(10)
    assert len(turns.submitted) == 5
    await harness.session.stop("test")


async def test_duplicate_result_is_skipped(clock, danmaku_source):
    turns = FakeExternalTurns([ExternalTurnResult(status="duplicate"), replied("二")])
    harness = Harness(clock, danmaku_source, turns)
    await harness.start()
    danmaku_source.current.send("id-1", "一")
    danmaku_source.current.send("id-2", "二")
    await clock.settle()
    assert [show["text"] for show in harness.shows()] == ["二"]
    await harness.session.stop("test")


async def test_generation_failure_shows_and_speaks_nothing(clock, danmaku_source):
    async def fail(message: ExternalTurnMessage) -> ExternalTurnResult:
        raise RuntimeError("模型超时")

    turns = FakeExternalTurns([fail, replied("")])
    harness = Harness(clock, danmaku_source, turns)
    await harness.start()
    danmaku_source.current.send("id-1", "一")
    danmaku_source.current.send("id-2", "二")
    await clock.settle()

    assert harness.shows() == []
    status = harness.session.snapshot()
    assert [record["generation"] for record in status["recent"]] == ["failed", "failed"]
    assert status["recent"][1]["error"] == "回复生成失败: 模型超时"
    assert status["last_error"] == "角色回复为空"
    assert status["counters"]["generation_failed"] == 2
    assert status["state"] == "running"
    await harness.session.stop("test")


async def test_one_failed_output_path_is_reported_without_regenerating(
    clock, danmaku_source
):
    turns = FakeExternalTurns([replied("一"), replied("二")])
    harness = Harness(clock, danmaku_source, turns)
    await harness.start()
    danmaku_source.current.send("id-1", "一")
    await clock.settle()
    await harness.outcome(harness.shows()[0], bubble="failed", error="窗口不可用")
    danmaku_source.current.send("id-2", "二")
    await clock.settle()
    await harness.outcome(harness.shows()[1], speech="failed", error="合成失败")

    status = harness.session.snapshot()
    assert [message.message_id for message in turns.submitted] == ["id-1", "id-2"]
    assert len(harness.shows()) == 2
    second, first = status["recent"]
    assert first["bubble"] == {"status": "failed", "error": "窗口不可用"}
    assert first["speech"] == {"status": "succeeded", "error": ""}
    assert second["speech"] == {"status": "failed", "error": "合成失败"}
    assert status["last_error"] == "语音输出失败: 合成失败"
    await harness.session.stop("test")


async def test_undelivered_show_is_reported_and_does_not_block(clock, danmaku_source):
    class NoBackgroundRpc(FakeRpc):
        async def emit(self, name, payload):
            await super().emit(name, payload)
            return False

    turns = FakeExternalTurns([replied("一"), replied("二")])
    harness = Harness(clock, danmaku_source, turns, rpc=NoBackgroundRpc())
    await harness.start()
    danmaku_source.current.send("id-1", "一")
    danmaku_source.current.send("id-2", "二")
    await clock.settle()
    assert len(harness.shows()) == 2
    assert harness.session.snapshot()["last_error"] == "桌宠后台未接收直播回复"
    await harness.session.stop("test")


async def test_pause_cancels_turn_and_output_and_resume_takes_only_new_danmaku(
    clock, danmaku_source
):
    gate, cancelled = asyncio.Event(), []
    turns = FakeExternalTurns([held(gate, "迟到的回复", cancelled), replied("新回复")])
    harness = Harness(clock, danmaku_source, turns)
    await harness.start()
    old_run = harness.session.status.run_id
    danmaku_source.current.send("id-1", "一")
    danmaku_source.current.send("id-2", "二")
    await clock.settle()

    await harness.session.pause()
    gate.set()
    await clock.settle()
    assert cancelled == ["id-1"]
    assert harness.cancels() == [{"run_id": old_run}]
    status = harness.session.snapshot()
    assert (status["state"], status["queue_length"]) == ("paused", 0)
    danmaku_source.current.send("id-3", "暂停时")
    await clock.settle()

    harness.session.resume()
    # A replay of earlier danmaku after resume is not new.
    danmaku_source.current.send("id-2", "二")
    danmaku_source.current.send("id-3", "暂停时")
    danmaku_source.current.send("id-4", "恢复后")
    await clock.settle()
    assert [message.message_id for message in turns.submitted] == ["id-1", "id-4"]
    [show] = harness.shows()
    assert show["text"] == "新回复"
    assert show["run_id"] == harness.session.status.run_id != old_run
    await harness.session.stop("test")


async def test_stop_releases_connection_and_late_result_never_shows(
    clock, danmaku_source
):
    gate, cancelled = asyncio.Event(), []
    turns = FakeExternalTurns([held(gate, "迟到的回复", cancelled)])
    harness = Harness(clock, danmaku_source, turns)
    await harness.start()
    run_id = harness.session.status.run_id
    danmaku_source.current.send("id-1", "一")
    await clock.settle()

    await harness.session.stop("已手动结束")
    gate.set()
    await clock.settle()
    danmaku_source.current.send("id-2", "二")
    await clock.advance(60)

    assert cancelled == ["id-1"]
    assert harness.shows() == []
    assert harness.cancels() == [{"run_id": run_id}]
    assert len(danmaku_source.connections) == 1
    assert harness.ended == [harness.session]
    status = harness.session.snapshot()
    assert (status["state"], status["connection"]) == ("stopped", "closed")
    assert status["stop_reason"] == "已手动结束"


async def test_role_switch_ends_the_run_and_drops_the_pending_reply(
    clock, danmaku_source
):
    gate, cancelled = asyncio.Event(), []
    turns = FakeExternalTurns([held(gate, "旧角色的回复", cancelled)])
    harness = Harness(clock, danmaku_source, turns)
    await harness.start()
    danmaku_source.current.send("id-1", "一")
    await clock.settle()

    harness.bound = False
    gate.set()
    await clock.settle()
    assert harness.shows() == []
    await clock.advance(2)
    status = harness.session.snapshot()
    assert (status["state"], status["stop_reason"]) == (
        "stopped",
        "桌宠角色已切换或停用",
    )
    assert len(harness.cancels()) == 1
    assert harness.ended == [harness.session]


async def test_invalid_login_on_reconnect_ends_the_run_explicitly(
    clock, danmaku_source
):
    harness = Harness(clock, danmaku_source, FakeExternalTurns())
    await harness.start()
    harness.login_valid = False
    danmaku_source.current.drop(ConnectionError("reset"))
    await clock.advance(1)

    status = harness.session.snapshot()
    assert status["connection"] == "login_invalid"
    assert status["state"] == "stopped"
    assert "B 站登录已失效" in status["stop_reason"]
    assert len(danmaku_source.connections) == 1


async def test_unreplied_danmaku_leave_no_trace(tmp_path, clock, danmaku_source):
    busy = ExternalTurnResult(status="busy")
    turns = FakeExternalTurns([busy] * 5)
    harness = Harness(clock, danmaku_source, turns, timeout=5)
    await harness.start()
    for index in range(25):
        danmaku_source.current.send(f"id-{index}", f"秘密弹幕{index}", uname="路人")
    await clock.advance(10)
    await harness.session.stop("test")

    status = json.dumps(harness.session.snapshot(), ensure_ascii=False)
    assert "秘密弹幕" not in status and "路人" not in status
    assert list(tmp_path.iterdir()) == []
