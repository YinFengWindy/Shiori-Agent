"""A live run end to end: controllable source, fake turns, real output contract, fake clock."""

import asyncio
import json

import pytest
from shiori_sdk.external_turns import ExternalTurnMessage
from shiori_sdk.testing.external_turns import FakeExternalTurns

from plugins.desktop_pet.backend.bilibili_credentials import BilibiliCredentials
from plugins.desktop_pet.backend.bilibili_live_api import LiveRoom
from plugins.desktop_pet.backend.bilibili_live_packets import LivePacketError
from plugins.desktop_pet.backend.bilibili_live_stream import LiveAuthRejected
from plugins.desktop_pet.backend.bilibili_login import BilibiliLoginRequired
from plugins.desktop_pet.backend.live_config import LiveConfig
from plugins.desktop_pet.backend.live_session import LiveSession, LiveSessionDeps

CREDENTIALS = BilibiliCredentials(
    uid=42, uname="主播", cookies={"SESSDATA": "s"}, refresh_token="r"
)


class Harness:
    """One session wired to fakes, with the pet's outcome RPC as the only way back."""

    def __init__(self, clock, source, turns, pet_output, *, timeout=30):
        self.clock = clock
        self.pet = pet_output
        self.bound = True
        self.login_valid = True
        self.ended: list[LiveSession] = []

        async def credentials(role_id: str) -> BilibiliCredentials:
            if not self.login_valid:
                raise BilibiliLoginRequired("B 站登录已失效，请重新扫码")
            return CREDENTIALS

        self.session = LiveSession(
            role_id="mira",
            room=LiveRoom(room_id=1001, title="测试直播间"),
            buvid="buvid-1",
            config=LiveConfig(
                room_id=1, reply_interval_seconds=0, wait_timeout_seconds=timeout
            ),
            deps=LiveSessionDeps(
                source=source,
                turns=turns,
                output=pet_output.output,
                credentials=credentials,
                still_bound=lambda role_id: self.bound,
                clock=clock,
                spawn=lambda work, *, name: asyncio.create_task(work, name=name),
            ),
            on_ended=self.ended.append,
        )

        async def route(outcome):
            self.session.outcome(outcome)

        pet_output.output.subscribe(route)

    async def start(self):
        self.session.start()
        await self.clock.settle()

    def status(self) -> dict:
        return self.session.snapshot()


@pytest.fixture
def make(clock, danmaku_source, pet_output):
    def build(turns, **options) -> Harness:
        return Harness(clock, danmaku_source, turns, pet_output, **options)

    return build


async def test_danmaku_reply_reaches_bubble_and_speech_as_one_text(
    make, clock, danmaku_source, pet_output, answers
):
    turns = FakeExternalTurns([answers.replied(" 欢迎！ "), answers.replied("你好呀")])
    harness = make(turns)
    await harness.start()
    assert (danmaku_source.current.uid, danmaku_source.current.buvid) == (
        42,
        "buvid-1",
    )
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
    [show] = pet_output.shows()
    assert (show["text"], show["role_id"]) == ("欢迎！", "mira")
    assert show["run_id"] == harness.session.status.run_id
    await pet_output.outcome(show)
    status = harness.status()
    assert status["recent"][0]["bubble"] == {"status": "succeeded", "error": ""}
    assert status["recent"][0]["speech"] == {"status": "succeeded", "error": ""}
    assert status["connection"] == "connected"

    # The logged-in account's own danmaku is an ordinary viewer message.
    danmaku_source.current.send("id-2", "我自己发的", uid=42, uname="主播")
    await clock.settle()
    assert turns.submitted[-1].sender_id == "42"
    assert len(pet_output.shows()) == 2
    await harness.session.stop("test")


async def test_repeated_delivery_and_reconnect_replay_reply_once(
    make, clock, danmaku_source, pet_output, answers
):
    turns = FakeExternalTurns([answers.replied("一"), answers.replied("二")])
    harness = make(turns)
    await harness.start()
    first = danmaku_source.current
    first.send("id-1", "你好")
    first.send("id-1", "你好")
    await clock.settle()
    await pet_output.outcome(pet_output.shows()[0])

    first.drop(ConnectionError("reset"))
    await clock.settle()
    assert harness.status()["connection"] == "reconnecting"
    assert harness.status()["connection_error"] == "弹幕连接中断: reset"
    await clock.advance(1)
    second = danmaku_source.current
    assert second is not first
    assert harness.status()["connection_error"] == "", "recovered"
    # The replay repeats id-1; a different viewer's equal text is a new message.
    second.send("id-1", "你好")
    second.send("id-2", "你好", uid=8)
    await clock.settle()

    assert [message.message_id for message in turns.submitted] == ["id-1", "id-2"]
    assert harness.status()["counters"]["redelivered"] == 2
    await harness.session.stop("test")


async def test_pause_cancels_turn_and_output_and_resume_takes_only_new_danmaku(
    make, clock, danmaku_source, pet_output, answers
):
    gate, cancelled = asyncio.Event(), []
    turns = FakeExternalTurns(
        [answers.held(gate, "迟到的回复", cancelled), answers.replied("新回复")]
    )
    harness = make(turns)
    await harness.start()
    old_run = harness.session.status.run_id
    danmaku_source.current.send("id-1", "一")
    danmaku_source.current.send("id-2", "二")
    await clock.settle()

    await harness.session.pause()
    gate.set()
    await clock.settle()
    assert cancelled == ["id-1"]
    assert pet_output.cancels() == [{"run_id": old_run}]
    assert (harness.status()["state"], harness.status()["queue_length"]) == (
        "paused",
        0,
    )
    danmaku_source.current.send("id-3", "暂停时")
    await clock.settle()

    harness.session.resume()
    # A replay of earlier danmaku after resume is not new.
    for message_id in ("id-2", "id-3", "id-4"):
        danmaku_source.current.send(message_id, "弹幕")
    await clock.settle()
    assert [message.message_id for message in turns.submitted] == ["id-1", "id-4"]
    [show] = pet_output.shows()
    assert show["text"] == "新回复"
    assert show["run_id"] == harness.session.status.run_id != old_run
    await harness.session.stop("test")


async def test_stop_releases_connection_and_late_result_never_shows(
    make, clock, danmaku_source, pet_output, answers
):
    gate, cancelled = asyncio.Event(), []
    harness = make(FakeExternalTurns([answers.held(gate, "迟到", cancelled)]))
    await harness.start()
    run_id = harness.session.status.run_id
    danmaku_source.current.send("id-1", "一")
    await clock.settle()

    await harness.session.stop("已手动结束")
    gate.set()
    danmaku_source.current.send("id-2", "二")
    await clock.advance(60)

    assert cancelled == ["id-1"]
    assert pet_output.shows() == []
    assert pet_output.cancels() == [{"run_id": run_id}]
    assert len(danmaku_source.connections) == 1
    assert harness.ended == [harness.session]
    status = harness.status()
    assert (status["state"], status["connection"]) == ("stopped", "closed")
    assert status["stop_reason"] == "已手动结束"


async def test_resume_or_pause_during_a_stop_cannot_start_processing_again(
    make, clock, danmaku_source, pet_output, answers
):
    turns = FakeExternalTurns([answers.replied("不应出现")])
    harness = make(turns)
    await harness.start()
    await harness.session.pause()
    stopping = asyncio.create_task(harness.session.stop("已手动结束"))
    await asyncio.sleep(0)
    assert not stopping.done(), "stop is still awaiting its cleanup"
    with pytest.raises(ValueError, match="未暂停"):
        harness.session.resume()
    with pytest.raises(ValueError, match="未在运行"):
        await harness.session.pause()
    await stopping
    danmaku_source.current.send("id-1", "一")
    await clock.advance(60)
    assert turns.submitted == [] and pet_output.shows() == []
    assert harness.ended == [harness.session]


async def test_role_switch_ends_the_run_and_drops_the_pending_reply(
    make, clock, danmaku_source, pet_output, answers
):
    gate, cancelled = asyncio.Event(), []
    harness = make(FakeExternalTurns([answers.held(gate, "旧角色的回复", cancelled)]))
    await harness.start()
    danmaku_source.current.send("id-1", "一")
    await clock.settle()

    harness.bound = False
    gate.set()
    await clock.settle()
    assert pet_output.shows() == []
    await clock.advance(2)
    status = harness.status()
    assert (status["state"], status["stop_reason"]) == (
        "stopped",
        "桌宠角色已切换或停用",
    )
    assert len(pet_output.cancels()) == 1
    with pytest.raises(ValueError):
        harness.session.resume()


async def test_invalid_login_on_reconnect_ends_the_run_explicitly(
    make, clock, danmaku_source
):
    harness = make(FakeExternalTurns())
    await harness.start()
    harness.login_valid = False
    danmaku_source.current.drop(ConnectionError("reset"))
    await clock.advance(1)

    status = harness.status()
    assert (status["connection"], status["state"]) == ("login_invalid", "stopped")
    assert status["stop_reason"] == "B 站登录不可用: B 站登录已失效，请重新扫码"
    assert len(danmaku_source.connections) == 1


async def test_platform_rejection_ends_the_run_instead_of_retrying(
    make, clock, danmaku_source
):
    harness = make(FakeExternalTurns())
    await harness.start()
    danmaku_source.current.drop(LiveAuthRejected("弹幕服务器拒绝认证 code=-101"))
    await clock.advance(60)
    status = harness.status()
    assert (status["connection"], status["state"]) == ("rejected", "stopped")
    assert status["connection_error"] == "弹幕服务器拒绝认证 code=-101"
    assert len(danmaku_source.connections) == 1


async def test_protocol_error_ends_the_run_visibly(make, clock, danmaku_source):
    harness = make(FakeExternalTurns())
    await harness.start()
    danmaku_source.current.drop(LivePacketError("直播信息流包被截断"))
    await clock.advance(60)
    status = harness.status()
    assert status["state"] == "stopped"
    assert status["stop_reason"] == "直播运行异常: 直播信息流包被截断"
    assert len(danmaku_source.connections) == 1


async def test_unreplied_danmaku_leave_no_trace(
    make, tmp_path, clock, danmaku_source, answers
):
    harness = make(FakeExternalTurns([answers.status("busy")] * 5), timeout=5)
    await harness.start()
    for index in range(25):
        danmaku_source.current.send(f"id-{index}", f"秘密弹幕{index}", uname="路人")
    await clock.advance(10)
    await harness.session.stop("test")
    assert harness.status()["counters"]["evicted"] == 5

    status = json.dumps(harness.status(), ensure_ascii=False)
    assert "秘密弹幕" not in status and "路人" not in status
    assert list(tmp_path.iterdir()) == []
