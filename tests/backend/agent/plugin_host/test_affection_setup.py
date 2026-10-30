"""The real affection package, loaded by the host kernel, serves its UI's RPC."""

from __future__ import annotations

from pathlib import Path

from agent.plugin_host import PluginGenerationSettings, PluginRpcRegistry
from bus.event_bus import EventBus
from core.roles import RoleStore
from session.manager import SessionManager
from shiori_sdk.rpc import Concurrency
from shiori_sdk.testing.packages import plugin_directory, stage_plugin_package
from tests.support.plugin_kernel import host_kernel


async def test_the_sidebar_and_role_tab_methods_reach_the_loaded_plugin(
    tmp_path: Path,
) -> None:
    """The renderer calls ``plugin.affection.<method>``; each must be registered."""
    root = tmp_path / "plugins"
    stage_plugin_package(plugin_directory("affection"), root / "affection")
    workspace = tmp_path / "workspace"
    roles = RoleStore(workspace)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    bus = EventBus()
    rpc = PluginRpcRegistry(bus)
    kernel = host_kernel(
        [root],
        settings=PluginGenerationSettings(workspace=workspace),
        role_store=roles,
        session_manager=SessionManager(workspace),
        event_bus=bus,
        rpc=rpc,
    )
    await kernel.load_all()
    try:
        resolved = rpc.resolve("plugin.affection.chat_status")
        assert resolved is not None
        status = await resolved[1]({"role_id": "mira"})
        assert status == {
            "role_id": "mira",
            "affection": None,
            "relation_tags": [],
            "loneliness": 0.0,
        }
        # Reading the summary settles decay, so it writes and is not read-only.
        assert rpc.policy_for("plugin.affection.chat_status").concurrency is (
            Concurrency.MUTATION
        )
        for method in ("history", "stage_prompts_get", "stage_prompts_set"):
            assert rpc.resolve(f"plugin.affection.{method}") is not None
    finally:
        await kernel.terminate_all(force=True)
