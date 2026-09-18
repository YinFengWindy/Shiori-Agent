"""Story's real assembly and required NovelAI lifecycle, without external requests."""

import asyncio
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.plugin_host import HostServices, PluginKernel
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
from shiori_plugin_testkit.bridge import plugin_bridge_request
from desktop_bridge.method_policy import Concurrency


@pytest.mark.parametrize("novelai_enabled", [True, False])
def test_story_requires_active_novelai_and_unloads_before_it(
    tmp_path, monkeypatch, novelai_enabled
):
    from shiori_plugin_testkit.packages import plugin_directory

    packages = tmp_path / "packages"
    for name in ("novelai", "story"):
        shutil.copytree(
            (
                Path(__file__).resolve().parents[1]
                if name == "story"
                else plugin_directory(name)
            )
            / "backend",
            packages / name / "backend",
        )
        shutil.copyfile(
            (
                Path(__file__).resolve().parents[1]
                if name == "story"
                else plugin_directory(name)
            )
            / "manifest.yaml",
            packages / name / "manifest.yaml",
        )
    monkeypatch.setattr(
        "core.net.http.get_default_http_requester", lambda _: SimpleNamespace()
    )
    kernel = PluginKernel(
        [packages],
        services=HostServices(
            event_bus=EventBus(),
            tool_registry=ToolRegistry(),
            workspace=tmp_path / "workspace",
            plugin_configs={
                "novelai": {"enabled": novelai_enabled},
                "story": {"enabled": True},
            },
        ),
    )

    async def run():
        try:
            await kernel.load_all()
            states = {item["id"]: item for item in kernel.states()}
            if not novelai_enabled:
                assert states["story"]["state"] == "BLOCKED"
                assert "novelai" in states["story"]["error"]
                assert kernel.rpc.resolve("plugin.story.list") is None
                return
            assert states["story"]["state"] == "ACTIVE"
            resolved = kernel.rpc.resolve("plugin.story.list")
            assert resolved is not None
            assert await resolved[1]({}) == {"stories": []}
            assert kernel.rpc.resolve("plugin.story.cg.regenerate") is not None
            for method in ("create", "input", "continue", "cg.retry", "cg.regenerate"):
                policy = kernel.rpc.policy_for(f"plugin.story.{method}")
                assert policy is not None
                assert policy.concurrency is Concurrency.INTEGRATION
            await kernel.unload("novelai")
            assert kernel.rpc.resolve("plugin.story.list") is None
            assert kernel.rpc.resolve("plugin.novelai.generate") is None
            assert (
                tmp_path / "workspace" / "plugin-data" / "story" / "stories"
            ).exists()
        finally:
            await kernel.terminate_all()

    asyncio.run(run())


@pytest.mark.asyncio
async def test_novelai_toggle_blocks_and_restores_story_without_deleting_data(
    tmp_path, plugin_runtime
):
    """Story owns the contract for its NovelAI dependency and persisted archives."""
    async with plugin_runtime(("novelai", "story")) as (service, _):
        response = await plugin_bridge_request(service, "plugin.story.list")
        assert response.error is None, response.error
        saved = tmp_path / "plugin-data" / "story" / "stories" / "keep.txt"
        saved.write_text("existing story data", encoding="utf-8")
        response = await plugin_bridge_request(
            service, "plugin.story.get", {"story_id": "missing"}
        )
        assert response.error is not None
        assert response.error.code == "story_not_found"

        for enabled in (False, True):
            toggled = await plugin_bridge_request(
                service,
                "plugins.setEnabled",
                {
                    "plugin_id": "novelai",
                    "enabled": enabled,
                    "operation_id": f"novelai-{enabled}",
                },
            )
            assert toggled.error is None, toggled.error
            listed = await plugin_bridge_request(service, "plugins.list")
            story = next(
                row for row in listed.payload["plugins"] if row["id"] == "story"
            )
            assert story["dependencies"] == ["novelai"]
            assert story["state"] == ("ACTIVE" if enabled else "BLOCKED")
            response = await plugin_bridge_request(service, "plugin.story.list")
            assert (response.error is None) is enabled
            assert saved.read_text(encoding="utf-8") == "existing story data"
