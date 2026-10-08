"""Engine lifecycle: one run at a time, uniform status, shutdown and role changes."""

import asyncio

import pytest
from shiori_sdk.role_events import RoleDeleted
from shiori_sdk.testing.external_turns import FakeExternalTurns
from shiori_sdk.testing.memory_context import FakeRpc
from shiori_sdk.testing.roles import FakeRoles

from plugins.desktop_pet.backend.bilibili_api import BilibiliLoginApi
from plugins.desktop_pet.backend.bilibili_credentials import (
    BilibiliCredentials,
    BilibiliCredentialStore,
)
from plugins.desktop_pet.backend.bilibili_live_api import BilibiliLiveApi
from plugins.desktop_pet.backend.bilibili_login import BilibiliLoginService
from plugins.desktop_pet.backend.live_config import LiveConfigStore
from plugins.desktop_pet.backend.live_engine import LiveEngine
from plugins.desktop_pet.backend.live_gate import LiveStartGate
from plugins.desktop_pet.backend.live_output import LiveReplyOutput
from plugins.desktop_pet.backend.live_session import LiveSessionDeps
from plugins.desktop_pet.backend.live_status import status_shape
from plugins.desktop_pet.backend.pet_state import RolePetStateStore
from plugins.desktop_pet.backend.voice_preferences import VoicePreferencesStore


class Setup:
    """A ready-to-start pet role: enabled pet, room 6, speech on, logged in."""

    def __init__(self, tmp_path, bilibili, clock, source, enable_pet) -> None:
        self.roles = FakeRoles(tmp_path)
        for role_id in ("mira", "other"):
            self.roles.create_role(role_id=role_id, name=role_id, system_prompt="")
        enable_pet(self.roles, "mira")
        self.configs = LiveConfigStore(tmp_path)
        self.configs.update("mira", {"room_id": 6})
        VoicePreferencesStore(tmp_path).write(
            {"enabled": True, "tts": {"plugin_id": "tts", "service_id": "voice"}}
        )
        credentials = BilibiliCredentialStore(tmp_path)
        credentials.write(
            "mira",
            BilibiliCredentials(
                uid=42,
                uname="主播",
                cookies={"SESSDATA": "sess%2C1%2Cabc"},
                refresh_token="r",
            ),
        )
        login = BilibiliLoginService(
            self.roles, credentials, BilibiliLoginApi(bilibili.transport)
        )
        is_pet_role = RolePetStateStore(self.roles).is_enabled
        self.rpc = FakeRpc()
        self.engine = LiveEngine(
            roles=self.roles,
            gate=LiveStartGate(
                roles=self.roles,
                configs=self.configs,
                voice=VoicePreferencesStore(tmp_path),
                is_pet_role=is_pet_role,
                credentials=login.require_credentials,
            ),
            configs=self.configs,
            api=BilibiliLiveApi(bilibili.transport),
            deps=LiveSessionDeps(
                source=source,
                turns=FakeExternalTurns(),
                output=LiveReplyOutput(self.rpc),
                credentials=login.require_credentials,
                still_bound=is_pet_role,
                clock=clock,
                spawn=lambda work, *, name: asyncio.create_task(work, name=name),
            ),
        )


@pytest.fixture
def live(tmp_path, bilibili, clock, danmaku_source, enable_pet) -> Setup:
    return Setup(tmp_path, bilibili, clock, danmaku_source, enable_pet)


async def test_run_lifecycle_uses_the_resolved_room_and_one_status_shape(
    live, danmaku_source, clock
):
    idle = live.engine.status("mira")
    assert idle == {**status_shape("mira"), "configured_room_id": 6}
    status = await live.engine.start("mira")
    await clock.settle()
    assert set(status) == set(idle)
    assert status["room"] == {"room_id": 1001, "title": "测试直播间"}
    assert (danmaku_source.current.room_id, danmaku_source.current.buvid) == (
        1001,
        "BUVID-FAKE",
    )
    with pytest.raises(ValueError, match="已有直播互动"):
        await live.engine.start("mira")

    # A new room is saved for the next run; the running one keeps its room.
    live.configs.update("mira", {"room_id": 7})
    status = live.engine.status("mira")
    assert (status["configured_room_id"], status["room"]["room_id"]) == (7, 1001)
    assert (await live.engine.pause("mira"))["state"] == "paused"
    assert (await live.engine.resume("mira"))["state"] == "running"
    stopped = await live.engine.stop("mira")
    assert (stopped["state"], stopped["stop_reason"]) == ("stopped", "已手动结束")
    assert live.engine.status("mira") == stopped


async def test_shutdown_during_a_pending_start_never_creates_a_run(
    live, bilibili, danmaku_source, clock
):
    bilibili.gate, bilibili.hold_path = asyncio.Event(), "/Room/get_info"
    starting = asyncio.create_task(live.engine.start("mira"))
    await bilibili.wait_held(1)
    await live.engine.shutdown()
    bilibili.gate.set()
    with pytest.raises(RuntimeError, match="已停用"):
        await starting
    await clock.advance(10)
    assert danmaku_source.connections == []
    assert live.engine.status("mira")["state"] == "idle"
    with pytest.raises(RuntimeError, match="已停用"):
        await live.engine.start("mira")


async def test_shutdown_ends_the_current_run(live):
    await live.engine.start("mira")
    await live.engine.shutdown()
    assert live.engine.status("mira")["stop_reason"] == "桌宠插件已停用"
    assert [name for name, _ in live.rpc.events] == ["live.cancel"]


async def test_switching_the_pet_role_ends_the_old_roles_run(live, clock, enable_pet):
    await live.engine.start("mira")
    enable_pet(live.roles, "other")
    await clock.advance(2)
    assert live.engine.status("mira")["stop_reason"] == "桌宠角色已切换或停用"
    with pytest.raises(ValueError, match="没有进行中的直播互动"):
        await live.engine.pause("mira")


async def test_deleting_the_role_ends_its_run_and_removes_its_settings(live):
    await live.engine.start("mira")
    del live.roles.values["mira"]
    await live.engine.on_role_deleted(RoleDeleted("mira"))
    assert not (live.configs.root / "mira.json").exists()
    with pytest.raises(ValueError, match="角色不存在"):
        live.engine.status("mira")
