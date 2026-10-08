"""Engine gate and lifecycle: only the pet role with room and login starts one run."""

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
from plugins.desktop_pet.backend.bilibili_login import (
    BilibiliLoginRequired,
    BilibiliLoginService,
)
from plugins.desktop_pet.backend.live_config import LiveConfigStore
from plugins.desktop_pet.backend.live_engine import LiveEngine
from plugins.desktop_pet.backend.live_output import LiveReplyOutput
from plugins.desktop_pet.backend.live_session import LiveSessionDeps
from plugins.desktop_pet.backend.pet_state import RolePetStateStore


class Setup:
    def __init__(self, tmp_path, bilibili, clock, source, enable_pet) -> None:
        self.roles = FakeRoles(tmp_path)
        for role_id in ("mira", "other"):
            self.roles.create_role(role_id=role_id, name=role_id, system_prompt="")
        enable_pet(self.roles, "mira")
        self.credentials = BilibiliCredentialStore(tmp_path)
        self.configs = LiveConfigStore(tmp_path)
        self.rpc = FakeRpc()
        login = BilibiliLoginService(
            self.roles, self.credentials, BilibiliLoginApi(bilibili.transport)
        )
        self.engine = LiveEngine(
            roles=self.roles,
            configs=self.configs,
            api=BilibiliLiveApi(bilibili.transport),
            deps=LiveSessionDeps(
                source=source,
                turns=FakeExternalTurns(),
                output=LiveReplyOutput(self.rpc),
                credentials=login.require_credentials,
                still_bound=RolePetStateStore(self.roles).is_enabled,
                clock=clock,
                spawn=lambda work, name: asyncio.create_task(work, name=name),
            ),
        )

    def log_in(self, role_id="mira", cookies=None) -> None:
        self.credentials.write(
            role_id,
            BilibiliCredentials(
                uid=42,
                uname="主播",
                cookies=cookies or {"SESSDATA": "sess%2C1%2Cabc"},
                refresh_token="r",
            ),
        )


@pytest.fixture
def live(tmp_path, bilibili, clock, danmaku_source, enable_pet) -> Setup:
    return Setup(tmp_path, bilibili, clock, danmaku_source, enable_pet)


async def test_start_requires_pet_role_room_and_valid_login(live, bilibili):
    with pytest.raises(ValueError, match="未启用桌宠"):
        await live.engine.start("other")
    with pytest.raises(ValueError, match="尚未配置直播间"):
        await live.engine.start("mira")
    live.configs.write("mira", {"room_id": 6})
    with pytest.raises(BilibiliLoginRequired, match="尚未登录"):
        await live.engine.start("mira")
    live.log_in()
    bilibili.login_valid = False
    with pytest.raises(BilibiliLoginRequired, match="已失效"):
        await live.engine.start("mira")
    assert live.engine.status("mira") == {"role_id": "mira", "state": "idle"}


async def test_started_run_uses_resolved_room_and_is_the_only_one(
    live, danmaku_source, clock
):
    live.configs.write("mira", {"room_id": 6})
    live.log_in()
    status = await live.engine.start("mira")
    await clock.settle()
    assert status["room"] == {"room_id": 1001, "title": "测试直播间"}
    assert danmaku_source.current.room_id == 1001
    assert danmaku_source.current.buvid == "BUVID-FAKE"
    with pytest.raises(ValueError, match="已有直播互动"):
        await live.engine.start("mira")
    assert live.engine.status("other") == {"role_id": "other", "state": "idle"}

    assert (await live.engine.pause("mira"))["state"] == "paused"
    assert (await live.engine.resume("mira"))["state"] == "running"
    stopped = await live.engine.stop("mira")
    assert (stopped["state"], stopped["stop_reason"]) == ("stopped", "已手动结束")
    assert live.engine.status("mira") == stopped
    # A new run may start once the old one ended.
    assert (await live.engine.start("mira"))["state"] == "running"
    await live.engine.shutdown()
    assert live.engine.status("mira")["stop_reason"] == "桌宠插件已停用"


async def test_switching_the_pet_role_ends_the_old_roles_run(live, clock, enable_pet):
    live.configs.write("mira", {"room_id": 6})
    live.log_in()
    await live.engine.start("mira")
    enable_pet(live.roles, "other")
    await clock.advance(2)
    assert live.engine.status("mira")["stop_reason"] == "桌宠角色已切换或停用"
    with pytest.raises(ValueError, match="没有进行中的直播互动"):
        await live.engine.pause("mira")
    assert [name for name, _ in live.rpc.events] == ["live.cancel"]


async def test_deleting_the_role_ends_its_run_and_removes_its_settings(live, clock):
    live.configs.write("mira", {"room_id": 6})
    live.log_in()
    await live.engine.start("mira")
    del live.roles.values["mira"]
    await live.engine.on_role_deleted(RoleDeleted("mira"))
    assert live.engine.status("mira") == {"role_id": "mira", "state": "idle"}
    assert not (live.configs.root / "mira.json").exists()
