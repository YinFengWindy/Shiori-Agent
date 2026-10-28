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
from core.error_context import current_session_key
from core.roles.models import RoleRecord
from core.roles.store import RoleStore
from core.scene.demand import SceneObservationDemand
from tests.support.plugin_kernel import host_kernel, make_kernel

_CRASH_PROBE = """\
import asyncio
import logging
from shiori_sdk.core.crash_reporting import CRASH_REPORTING

def hook(*args):
    pass

async def setup(ctx):
    reporting = ctx.require(CRASH_REPORTING)
    owner = object()
    reporting.install(
        owner, logging.NullHandler(), hook, hook,
        asyncio.get_running_loop(), hook,
    )
    ctx.effect("hooks", lambda: reporting.uninstall(owner))
    seen = reporting.session_key()
    try:
        raise RuntimeError("probe")
    except RuntimeError as error:
        frame = reporting.top_frame(error.__traceback__)
    ctx.expose((hook, frame, seen))
"""


@pytest.mark.asyncio
async def test_crash_reporting_hooks_session_and_frame(tmp_path: Path) -> None:
    """CRASH_REPORTING 接管三种进程钩子，并给出会话与插件栈帧；卸载后钩子还原。"""
    package = tmp_path / "plugins" / "crash_probe"
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        "api: 4\nid: crash_probe\ninject:\n  - crash_reporting\n",
        encoding="utf-8",
    )
    (package / "backend/plugin.py").write_text(_CRASH_PROBE, encoding="utf-8")
    raise_line = next(
        index
        for index, line in enumerate(_CRASH_PROBE.splitlines(), 1)
        if line.strip() == 'raise RuntimeError("probe")'
    )
    loop = asyncio.get_running_loop()
    originals = (sys.excepthook, threading.excepthook, loop.get_exception_handler())
    token = current_session_key.set("role:mira")
    kernel = make_kernel([tmp_path / "plugins"], event_bus=EventBus())
    try:
        await kernel.load_all()
        handle = kernel._handles[str(package.absolute())]
        assert handle.state is PluginState.ACTIVE, handle.error
        hook, frame, seen = handle.instance
        installed = (
            sys.excepthook,
            threading.excepthook,
            loop.get_exception_handler(),
        )
        assert installed == (hook, hook, hook)
        assert frame == f"plugins/crash_probe/backend/plugin.py:{raise_line}"
        assert seen == "role:mira"
    finally:
        await kernel.terminate_all(force=True)
        current_session_key.reset(token)
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
        "api: 4\nid: avatar_probe\ninject: [avatars]\n",
        encoding="utf-8",
    )
    (package / "backend/plugin.py").write_text(
        f"IMAGE = {image.getvalue()!r}\n"
        "from shiori_sdk.core.services import AVATARS\n"
        "async def fetch():\n"
        "    return IMAGE\n"
        "async def setup(ctx):\n"
        "    await ctx.require(AVATARS).refresh('sender', 'qq', '42', fetch)\n",
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
        "api: 4\nid: scene_probe\n" "inject: [scene_observations]\n",
        encoding="utf-8",
    )
    (package / "backend/plugin.py").write_text(
        "from shiori_sdk.core.services import SCENE_OBSERVATIONS\n"
        "async def setup(ctx):\n"
        "    ctx.require(SCENE_OBSERVATIONS).request(lambda role: role.id == 'mira')\n",
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
                        provider=None,
                        model=None,
                        light_provider=None,
                        light_model=None,
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
