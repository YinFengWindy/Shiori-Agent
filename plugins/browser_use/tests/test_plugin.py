"""Plugin registration works without a downloaded browser and revokes old generations."""

from pathlib import Path

import pytest
from shiori_plugin_testkit.packages import stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus


async def test_lazy_registration_disable_and_reenable(tmp_path):
    roots = tmp_path / "plugins"
    stage_plugin_package(Path(__file__).resolve().parents[1], roots / "browser_use")
    registry = ToolRegistry()
    kernel = PluginKernel(
        [roots],
        services=HostServices(
            workspace=tmp_path / "workspace",
            tool_registry=registry,
            event_bus=EventBus(),
            plugin_configs={"browser_use": {"enabled": True}},
        ),
    )
    await kernel.load_all()
    assert kernel.loaded_count == 1
    old_tool = registry.get_tool("agent_browser_snapshot")
    assert old_tool is not None
    assert "session" not in old_tool.parameters["properties"]
    assert registry.search("浏览器")
    await kernel.unload("browser_use")
    assert registry.get_tool("agent_browser_snapshot") is None
    with pytest.raises(RuntimeError, match="已停用"):
        await old_tool.execute(role_id="role")
    await kernel.load_all()
    assert registry.get_tool("agent_browser_snapshot") is not old_tool
    await kernel.unload("browser_use")


async def test_new_installs_leave_the_plugin_disabled(tmp_path):
    """manifest default_enabled: false —— 没有显式 enabled 时不加载、不贡献工具。"""
    roots = tmp_path / "plugins"
    stage_plugin_package(Path(__file__).resolve().parents[1], roots / "browser_use")
    registry = ToolRegistry()
    kernel = PluginKernel(
        [roots],
        services=HostServices(
            workspace=tmp_path,
            tool_registry=registry,
            event_bus=EventBus(),
        ),
    )
    await kernel.load_all()
    assert kernel.loaded_count == 0
    assert [item["state"] for item in kernel.states()] == ["DISABLED"]
    assert registry.get_tool("agent_browser_snapshot") is None


async def test_disabled_plugin_contributes_nothing(tmp_path):
    roots = tmp_path / "plugins"
    stage_plugin_package(Path(__file__).resolve().parents[1], roots / "browser_use")
    registry = ToolRegistry()
    kernel = PluginKernel(
        [roots],
        services=HostServices(
            workspace=tmp_path,
            tool_registry=registry,
            event_bus=EventBus(),
            plugin_configs={"browser_use": {"enabled": False}},
        ),
    )
    await kernel.load_all()
    assert registry.get_tool("agent_browser_open") is None


def test_config_schema_labels_fields_for_the_settings_form() -> None:
    from plugins.browser_use.backend.config import BrowserUseConfig

    properties = BrowserUseConfig.model_json_schema()["properties"]
    assert properties["headed"]["title"] == "显示浏览器窗口"
    assert properties["timeout_seconds"]["title"] == "单次操作超时"
    assert properties["timeout_seconds"]["unit"] == "秒"
