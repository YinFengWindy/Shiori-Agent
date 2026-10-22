"""The core provide list: what plugins receive from the core modules it provides."""

from __future__ import annotations

import asyncio
import sys
import threading
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
    """diagnostics 由 CRASH_REPORTING 构建：三种进程钩子都被插件接管，卸载后还原；

    栈帧按发现根归因到 plugins/<目录>/...。
    """
    package = tmp_path / "plugins" / "crash_probe"
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        "api: 2\nid: crash_probe\ncapabilities: [diagnostics]\n", encoding="utf-8"
    )
    (package / "backend/plugin.py").write_text(
        "import asyncio\n"
        "import logging\n"
        "def hook(*args):\n"
        "    pass\n"
        "async def setup(ctx):\n"
        "    owner = object()\n"
        "    ctx.diagnostics.install_global_hooks(\n"
        "        owner, logging.NullHandler(), hook, hook,\n"
        "        asyncio.get_running_loop(), hook,\n"
        "    )\n"
        "    ctx.effect('hooks', lambda: ctx.diagnostics.uninstall_global_hooks(owner))\n"
        "    try:\n"
        "        raise RuntimeError('probe')\n"
        "    except RuntimeError as error:\n"
        "        frame = ctx.diagnostics.top_frame(error.__traceback__)\n"
        "    ctx.expose((hook, frame))\n",
        encoding="utf-8",
    )
    loop = asyncio.get_running_loop()
    originals = (sys.excepthook, threading.excepthook, loop.get_exception_handler())
    kernel = make_kernel([tmp_path / "plugins"], event_bus=EventBus())
    await kernel.load_all()
    try:
        handle = kernel._handles[str(package.absolute())]
        assert handle.state is PluginState.ACTIVE, handle.error
        hook, frame = handle.instance
        installed = (
            sys.excepthook,
            threading.excepthook,
            loop.get_exception_handler(),
        )
        assert installed == (hook, hook, hook)
        assert frame == "plugins/crash_probe/backend/plugin.py:13"
    finally:
        await kernel.terminate_all(force=True)
    restored = (sys.excepthook, threading.excepthook, loop.get_exception_handler())
    assert restored == originals


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
            core=(*plugin_core_modules([tmp_path], tools=None), broken_core_module),
        )
