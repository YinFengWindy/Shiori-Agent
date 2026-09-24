"""Plugin registration works without a downloaded browser and revokes old generations."""

from pathlib import Path

import pytest
from shiori_plugin_testkit.packages import stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus


async def test_lazy_registration_disable_and_reenable(tmp_path):
    roots = tmp_path / "plugins"
    stage_plugin_package(Path(__file__).resolve().parents[1], roots / "computer_use")
    registry = ToolRegistry()
    kernel = PluginKernel(
        [roots],
        services=HostServices(
            workspace=tmp_path / "workspace",
            tool_registry=registry,
            event_bus=EventBus(),
        ),
    )
    await kernel.load_all()
    assert kernel.loaded_count == 1
    old_tool = registry.get_tool("computer_get_window_state")
    assert old_tool is not None
    assert "session" not in old_tool.parameters["properties"]
    assert registry.search("电脑")
    await kernel.unload("computer_use")
    assert registry.get_tool("computer_get_window_state") is None
    with pytest.raises(RuntimeError, match="已停用"):
        await old_tool.execute(role_id="role", pid=42, window_id=81)
    await kernel.load_all()
    assert registry.get_tool("computer_get_window_state") is not old_tool
    await kernel.unload("computer_use")


async def test_disabled_plugin_contributes_nothing(tmp_path):
    roots = tmp_path / "plugins"
    stage_plugin_package(Path(__file__).resolve().parents[1], roots / "computer_use")
    registry = ToolRegistry()
    kernel = PluginKernel(
        [roots],
        services=HostServices(
            workspace=tmp_path,
            tool_registry=registry,
            event_bus=EventBus(),
            plugin_configs={"computer_use": {"enabled": False}},
        ),
    )
    await kernel.load_all()
    assert registry.get_tool("computer_list_windows") is None


def test_config_schema_labels_fields_for_the_settings_form() -> None:
    from plugins.computer_use.backend.config import ComputerUseConfig

    timeout = ComputerUseConfig.model_json_schema()["properties"]["timeout_seconds"]
    assert timeout["title"] == "单次操作超时" and timeout["unit"] == "秒"
