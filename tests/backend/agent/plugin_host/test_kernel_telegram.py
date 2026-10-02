from __future__ import annotations

import asyncio
from pathlib import Path

from shiori_plugin_testkit.packages import stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel
from agent.plugin_host.kv import PluginKVStore
from agent.plugin_host.plugin_data import plugin_data_dir
from bus.event_bus import EventBus
from core.roles.store import RoleStore

PLUGIN_DIR = Path(__file__).resolve().parents[4] / "plugins" / "telegram"


def test_saved_bots_run_as_members_and_a_refused_bot_is_reported(tmp_path) -> None:
    stage_plugin_package(PLUGIN_DIR, tmp_path / "telegram")
    role_store = RoleStore(tmp_path)
    role_store.create_role(role_id="mira", name="mira", system_prompt="m")
    PluginKVStore(plugin_data_dir(tmp_path, "telegram") / "kv.json").set(
        "bots",
        [
            {"ref": "1", "bot_id": "1", "token": "1:a", "role_id": "mira"},
            # A second Bot for the same role is refused, not fatal.
            {"ref": "2", "bot_id": "2", "token": "2:b", "role_id": "mira"},
        ],
    )
    kernel = PluginKernel(
        [tmp_path],
        services=HostServices(
            event_bus=EventBus(), workspace=tmp_path, role_store=role_store
        ),
    )
    asyncio.run(kernel.load_all())
    assert kernel.loaded_count == 1
    [group] = kernel.channels
    assert group.name == "telegram"
    assert group.member_channel("telegram_1") is not None
    assert group.member_channel("telegram_2") is None
    [refused] = role_store.accounts.rejected("telegram")
    assert "账号 2" in refused and "已有账号" in refused
    assert [row.record.id for row in role_store.accounts.list()] == ["telegram:1"]
