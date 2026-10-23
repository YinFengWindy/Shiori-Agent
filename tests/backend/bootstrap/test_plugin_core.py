"""The core provide list: what plugins receive from the core modules it provides."""

from __future__ import annotations

import asyncio
import io
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from PIL import Image

from agent.plugin_host import (
    PluginGenerationSettings,
    PluginKernel,
    PluginRpcRegistry,
    PluginState,
)
from agent.core.turn_events import install_core_checks
from bootstrap.plugin_core import PluginCoreInputs, plugin_core_modules
from bus.event_bus import EventBus
from core.roles.models import RoleRecord
from core.roles.store import RoleStore
from core.scene.demand import SceneObservationDemand
from tests.support.plugin_kernel import host_kernel, make_kernel


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


@pytest.mark.asyncio
async def test_avatars_capability_caches_into_the_host_role_store(
    tmp_path: Path,
) -> None:
    """avatars 由核心 channels 模块经 role_store 提供：插件刷新的头像写进宿主 RoleStore。"""
    image = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(image, "PNG")
    package = tmp_path / "plugins" / "avatar_probe"
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        "api: 2\nid: avatar_probe\ncapabilities: [avatars]\n", encoding="utf-8"
    )
    (package / "backend/plugin.py").write_text(
        f"IMAGE = {image.getvalue()!r}\n"
        "async def fetch():\n"
        "    return IMAGE\n"
        "async def setup(ctx):\n"
        "    await ctx.avatars.refresh('sender', 'qq', '42', fetch)\n",
        encoding="utf-8",
    )
    role_store = RoleStore(tmp_path / "workspace")
    kernel = host_kernel(
        [tmp_path / "plugins"],
        settings=PluginGenerationSettings(workspace=tmp_path / "workspace"),
        role_store=role_store,
    )
    await kernel.load_all()
    try:
        assert [state["state"] for state in kernel.states()] == ["ACTIVE"]
        assert role_store.avatars.index().sender("qq", "42") is not None
    finally:
        await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_scene_observation_requests_reach_the_generation_demand(
    tmp_path: Path,
) -> None:
    """scene_observations 由核心 scene 模块提供：插件的观测需求登记进本代宿主共用的那份 demand。"""
    package = tmp_path / "plugins" / "scene_probe"
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        "api: 2\nid: scene_probe\ncapabilities: [scene_observations]\n",
        encoding="utf-8",
    )
    (package / "backend/plugin.py").write_text(
        "async def setup(ctx):\n"
        "    ctx.scene_observations.request(lambda role: role.id == 'mira')\n",
        encoding="utf-8",
    )
    demand = SceneObservationDemand()
    kernel = host_kernel(
        [tmp_path / "plugins"],
        scene_observations=demand,
    )
    await kernel.load_all()
    try:
        assert [state["state"] for state in kernel.states()] == ["ACTIVE"]
        assert demand.needed(cast(RoleRecord, SimpleNamespace(id="mira")))
    finally:
        await kernel.terminate_all(force=True)


def test_core_module_provide_failure_aborts_startup(tmp_path: Path) -> None:
    """§8.5：核心模块自身 provide 失败时整个启动失败，不像插件 setup 失败那样记为 FAILED。"""

    class CoreServiceBroken(RuntimeError):
        pass

    def broken_core_module(provide: object) -> None:
        raise CoreServiceBroken("核心服务初始化失败")

    bus = EventBus()
    with pytest.raises(CoreServiceBroken):
        _ = PluginKernel(
            [tmp_path],
            settings=PluginGenerationSettings(),
            core=(
                *plugin_core_modules(
                    PluginCoreInputs(
                        plugin_dirs=(tmp_path,),
                        event_bus=bus,
                        rpc=PluginRpcRegistry(bus),
                        scene_observations=SceneObservationDemand(),
                        workspace=None,
                        tools=None,
                        role_store=None,
                        session_manager=None,
                        relationship_runtime=None,
                        role_runtime_registry=None,
                        light_provider=None,
                        light_model=None,
                        memory_engine=None,
                        external_turns=None,
                        background_results=None,
                        http=None,
                        process_resources=None,
                    )
                ),
                broken_core_module,
            ),
            core_checks=install_core_checks,
        )
