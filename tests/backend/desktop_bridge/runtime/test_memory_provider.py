from __future__ import annotations

from pathlib import Path

import pytest

from agent.plugin_host import PluginGenerationSettings
from desktop_bridge.runtime.plugin_management import memory_engine_provider
from tests.support.plugin_kernel import host_kernel

_PROVIDER = """
from shiori_sdk.core.memory import MEMORY_ENGINE

async def setup(ctx):
    ctx.provide(MEMORY_ENGINE, object())
"""

_QUIET = """
async def setup(ctx):
    return None
"""


def _plugin(root: Path, plugin_id: str, source: str, *, provides: bool) -> None:
    plugin = root / plugin_id
    (plugin / "backend").mkdir(parents=True)
    (plugin / "backend" / "plugin.py").write_text(source, encoding="utf-8")
    manifest = f"api: 2\nid: {plugin_id}\ncapabilities:\n  - events\n"
    if provides:
        manifest += "provides:\n  - memory_engine\n"
    (plugin / "manifest.yaml").write_text(manifest, encoding="utf-8")


@pytest.mark.asyncio
async def test_memory_provider_names_the_active_plugin_that_filled_the_socket(
    tmp_path: Path,
) -> None:
    root = tmp_path / "plugins"
    _plugin(root, "other_memory", _PROVIDER, provides=True)
    _plugin(root, "quiet", _QUIET, provides=False)
    kernel = host_kernel(
        [root],
        settings=PluginGenerationSettings(workspace=tmp_path / "workspace"),
    )
    await kernel.load_all()
    assert memory_engine_provider(kernel) == "other_memory"
    assert memory_engine_provider(None) is None


@pytest.mark.asyncio
async def test_memory_provider_is_empty_when_setup_does_not_provide(
    tmp_path: Path,
) -> None:
    root = tmp_path / "plugins"
    _plugin(root, "other_memory", _QUIET, provides=True)
    kernel = host_kernel(
        [root],
        settings=PluginGenerationSettings(workspace=tmp_path / "workspace"),
    )
    await kernel.load_all()
    assert memory_engine_provider(kernel) is None
