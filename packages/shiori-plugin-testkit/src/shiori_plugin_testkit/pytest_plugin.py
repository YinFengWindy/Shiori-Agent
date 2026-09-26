"""Real runtime fixture registered by the explicitly installed testkit distribution."""

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path

import pytest
from shiori_plugin_testkit.bridge import PluginBridgeService
from shiori_plugin_testkit.packages import plugin_directory, stage_plugin_package

PluginRuntime = Callable[
    [tuple[str, ...], str],
    AbstractAsyncContextManager[tuple[PluginBridgeService, Path]],
]


@pytest.fixture
def plugin_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PluginRuntime:
    """Starts an isolated reloadable host for a plugin package's integration tests."""
    from agent.config import load_config_text
    from bootstrap.app import AppRuntime, RuntimeFeatures
    from desktop_bridge.runtime.service import ReloadableDesktopService

    @asynccontextmanager
    async def start(
        plugin_ids: tuple[str, ...], config_text: str = ""
    ) -> AsyncGenerator[tuple[PluginBridgeService, Path], None]:
        plugin_root = tmp_path / "plugin_dirs"
        for plugin_id in plugin_ids:
            _ = stage_plugin_package(
                plugin_directory(plugin_id),
                plugin_root / plugin_id,
            )

        def resolve_plugin_dirs(_workspace: Path) -> list[Path]:
            return [plugin_root]

        monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", resolve_plugin_dirs)
        text = (
            "[llm]\nregistrations = []\n"
            "\n[agent.maintenance]\nmemory_optimizer_enabled = false\n"
            '\n[proactive]\nenabled = false\nprofile = "quiet"\n' + config_text
        )
        path = tmp_path / "config.toml"
        _ = path.write_text(text, encoding="utf-8")
        app = AppRuntime(
            load_config_text(text),
            tmp_path,
            features=RuntimeFeatures(
                enable_message_channels=False, enable_proactive=False
            ),
        )
        try:
            await app.start()
            core = app.core
            if core is None:
                raise RuntimeError("Plugin runtime did not start")
            role_store = core.role_runtime_registry.repository.store
            service = ReloadableDesktopService(app, path, role_store)
            try:
                yield service, path
            finally:
                await service.aclose()
        finally:
            await app.shutdown()

    return start
