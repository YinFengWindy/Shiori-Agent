"""``live.*`` RPCs: names, lanes, role scoping and partial autosave."""

import pytest
from shiori_sdk.rpc import Concurrency
from shiori_sdk.testing.service_context import FakeServiceContext

from plugins.desktop_pet.backend.plugin import setup


async def test_config_rpcs_merge_fields_and_explain_errors(tmp_path):
    ctx = FakeServiceContext("desktop_pet", tmp_path)
    ctx.roles.create_role(role_id="mira", name="Mira", system_prompt="")
    await setup(ctx.as_capability())
    handlers = ctx.rpc.handlers
    assert ctx.rpc.concurrency["live.start"] is Concurrency.INTEGRATION
    assert ctx.rpc.concurrency["live.config.get"] is Concurrency.READ_ONLY

    with pytest.raises(ValueError, match="role_id"):
        await handlers["live.config.get"]({})
    with pytest.raises(ValueError, match="角色不存在"):
        await handlers["live.config.get"]({"role_id": "ghost"})
    assert await handlers["live.config.get"]({"role_id": "mira"}) == {
        "room_id": None,
        "reply_interval_seconds": 5,
        "wait_timeout_seconds": 30,
    }
    await handlers["live.config.set"]({"role_id": "mira", "room_id": 6})
    saved = await handlers["live.config.set"](
        {"role_id": "mira", "wait_timeout_seconds": 20}
    )
    assert saved == {
        "room_id": 6,
        "reply_interval_seconds": 5,
        "wait_timeout_seconds": 20,
    }
    with pytest.raises(ValueError, match="直播间号必须是正整数"):
        await handlers["live.config.set"]({"role_id": "mira", "room_id": -1})
    assert await handlers["live.config.get"]({"role_id": "mira"}) == saved

    status = await handlers["live.status"]({"role_id": "mira"})
    assert (status["state"], status["configured_room_id"], status["room"]) == (
        "idle",
        6,
        None,
    )
    with pytest.raises(ValueError, match="未启用桌宠"):
        await handlers["live.start"]({"role_id": "mira"})
    with pytest.raises(ValueError, match="没有进行中的直播互动"):
        await handlers["live.stop"]({"role_id": "mira"})
    await ctx.aclose()
