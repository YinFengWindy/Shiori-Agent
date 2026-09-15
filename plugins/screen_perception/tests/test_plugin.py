"""Exercise registration, role model selection, and independent plugin teardown."""

import asyncio
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image, ImageGrab
from shiori_plugin_testkit.packages import plugin_directory, stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
from core.roles import RoleStore


async def _kernel(tmp_path, provider):
    roots = tmp_path / "plugins"
    stage_plugin_package(
        Path(__file__).resolve().parents[1], roots / "screen_perception"
    )
    stage_plugin_package(plugin_directory("desktop_pet"), roots / "desktop_pet")
    store = RoleStore(tmp_path / "workspace")
    store.create_role(role_id="mira", name="Mira", system_prompt="test")
    activations = []

    class RoleRuntime:
        @contextmanager
        def activate_model(self, purpose):
            activations.append(purpose)
            yield SimpleNamespace(provider=provider, model="role-vision")

    registry = SimpleNamespace(get=AsyncMock(return_value=RoleRuntime()))
    tools = ToolRegistry()
    kernel = PluginKernel(
        [roots],
        services=HostServices(
            workspace=tmp_path / "workspace",
            event_bus=EventBus(),
            tool_registry=tools,
            role_store=store,
            role_runtime_registry=registry,
        ),
    )
    await kernel.load_all()
    assert kernel.loaded_count == 2
    return kernel, tools, registry, activations


@pytest.mark.asyncio
async def test_screen_tool_uses_role_vision_without_desktop_pet(tmp_path, monkeypatch):
    provider = SimpleNamespace(
        chat=AsyncMock(
            return_value=SimpleNamespace(
                content='{"interface_summary":"编辑器","activity_key":"coding","targets":[],"risks":[]}',
                tool_calls=[],
            )
        )
    )
    monkeypatch.setattr(ImageGrab, "grab", lambda **_: Image.new("RGB", (10, 8)))
    kernel, tools, registry, activations = await _kernel(tmp_path, provider)
    await kernel.unload("desktop_pet")
    assert tools.get_tool("pet_action") is None

    result = await tools.execute(
        "observe_screen", {"role_id": "forged"}, context={"role_id": "mira"}
    )

    assert json.loads(result) == {
        "available": True,
        "interface_summary": "编辑器",
        "activity_key": "coding",
    }
    registry.get.assert_awaited_once_with("mira")
    assert activations == ["vision"]
    assert provider.chat.await_args.kwargs["payload_snapshot_enabled"] is False
    assert provider.chat.await_args.kwargs["model"] == "role-vision"
    await kernel.unload("screen_perception")
    assert tools.get_tool("observe_screen") is None


@pytest.mark.asyncio
async def test_screen_disable_cancels_analysis_and_leaves_pet_live(
    tmp_path, monkeypatch
):
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def chat(**_):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(ImageGrab, "grab", lambda **_: Image.new("RGB", (10, 8)))
    kernel, tools, _, _ = await _kernel(tmp_path, SimpleNamespace(chat=chat))
    tool = tools.get_tool("observe_screen")
    pending = asyncio.create_task(tool.execute(role_id="mira"))
    await started.wait()
    await kernel.unload("screen_perception")

    assert cancelled.is_set()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert tools.get_tool("observe_screen") is None
    assert tools.get_tool("pet_action") is not None
    assert kernel.rpc.resolve("plugin.desktop_pet.bubble.dismiss") is not None
    with pytest.raises(RuntimeError, match="已停用"):
        await tool.execute(role_id="mira")
    await kernel.unload("desktop_pet")


@pytest.mark.asyncio
async def test_disabled_screen_plugin_never_contributes_a_tool(tmp_path):
    root = tmp_path / "plugins"
    stage_plugin_package(
        Path(__file__).resolve().parents[1], root / "screen_perception"
    )
    tools = ToolRegistry()
    kernel = PluginKernel(
        [root],
        services=HostServices(
            workspace=tmp_path,
            tool_registry=tools,
            event_bus=EventBus(),
            plugin_configs={"screen_perception": {"enabled": False}},
        ),
    )
    await kernel.load_all()
    assert tools.get_tool("observe_screen") is None
    assert kernel.loaded_count == 0
