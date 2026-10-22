"""The core provide list: what plugins receive from the core modules it provides."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from agent.plugin_host import HostServices, PluginKernel, PluginState
from bootstrap.plugin_core import plugin_core_modules
from bus.event_bus import EventBus
from tests.support.plugin_kernel import make_kernel


@pytest.mark.asyncio
async def test_diagnostics_capability_hooks_go_through_crash_reporting(
    tmp_path: Path,
) -> None:
    """diagnostics 由 CRASH_REPORTING 构建：插件装的钩子真正接管进程钩子，卸载后还原。"""
    package = tmp_path / "plugins" / "crash_probe"
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        "api: 2\nid: crash_probe\ncapabilities: [diagnostics]\n", encoding="utf-8"
    )
    (package / "backend/plugin.py").write_text(
        "import logging\n"
        "def hook(*args):\n"
        "    pass\n"
        "async def setup(ctx):\n"
        "    owner = object()\n"
        "    ctx.diagnostics.install_global_hooks(\n"
        "        owner, logging.NullHandler(), hook, hook, None, hook\n"
        "    )\n"
        "    ctx.effect('hooks', lambda: ctx.diagnostics.uninstall_global_hooks(owner))\n"
        "    ctx.expose(hook)\n",
        encoding="utf-8",
    )
    original = sys.excepthook
    kernel = make_kernel([tmp_path / "plugins"], event_bus=EventBus())
    await kernel.load_all()
    try:
        handle = kernel._handles[str(package.absolute())]
        assert handle.state is PluginState.ACTIVE, handle.error
        assert sys.excepthook is handle.instance
    finally:
        await kernel.terminate_all(force=True)
    assert sys.excepthook is original


def test_core_module_provide_failure_aborts_startup(tmp_path: Path) -> None:
    """§8.5：核心模块自身 provide 失败时整个启动失败，不像插件 setup 失败那样记为 FAILED。"""

    class CoreServiceBroken(RuntimeError):
        pass

    def broken_core_module(provide: object) -> None:
        raise CoreServiceBroken("核心服务初始化失败")

    with pytest.raises(CoreServiceBroken):
        _ = PluginKernel(
            [tmp_path],
            services=HostServices(event_bus=EventBus()),
            core=(*plugin_core_modules(), broken_core_module),
        )
