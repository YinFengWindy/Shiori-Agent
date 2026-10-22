"""Real plugin-kernel assembly shared by host integration tests.

Builds a ``PluginKernel`` over real generation settings and core inputs so
tests load plugin packages only through the kernel's public entry points.
"""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

# 预热 agent.core 导入链，避免 agent.lifecycle.types 触发循环导入
from agent.core.passive_turn import ContextStore as _  # noqa: F401
from agent.lifecycle.types import BeforeTurnCtx
from agent.plugin_host import (
    PluginGenerationSettings,
    PluginKernel,
    PluginRpcRegistry,
)
from agent.tools.registry import ToolRegistry
from bootstrap.plugin_core import PluginCoreInputs, plugin_core_modules
from bus.event_bus import EventBus
from core.scene.demand import SceneObservationDemand

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_FIXTURES = REPOSITORY_ROOT / "tests/fixtures/plugins"


def host_kernel(
    plugin_dirs: list[Path],
    *,
    settings: PluginGenerationSettings | None = None,
    tools: ToolRegistry | None = None,
    role_store: Any = None,
    memory_engine: Any = None,
    http: Any = None,
    relationship_runtime: Any = None,
    session_manager: Any = None,
    light_provider: Any = None,
    light_model: str | None = None,
    role_runtime_registry: Any = None,
    scene_observations: SceneObservationDemand | None = None,
    external_turns: Any = None,
    background_results: Any = None,
    event_bus: EventBus | None = None,
    rpc: PluginRpcRegistry[Any] | None = None,
    **options: Any,
) -> PluginKernel:
    """A kernel over ``settings`` with the same core provide list as bootstrap.

    ``settings`` defaults to an empty generation (no workspace). The remaining
    keywords are the ``PluginCoreInputs`` fields, real services or test
    doubles; one left None makes a plugin declaring a capability over it fail
    before setup. The core's ``workspace`` and ``process_resources`` are those
    of ``settings``; ``scene_observations`` and ``event_bus`` default to fresh
    ones and ``rpc`` to a new registry over that bus (pass one to read what
    plugins registered). ``options`` are the remaining ``PluginKernel``
    keyword arguments.
    """
    generation = settings if settings is not None else PluginGenerationSettings()
    bus = event_bus if event_bus is not None else EventBus()
    inputs = PluginCoreInputs(
        plugin_dirs=tuple(plugin_dirs),
        event_bus=bus,
        rpc=rpc if rpc is not None else PluginRpcRegistry(bus),
        scene_observations=(
            scene_observations
            if scene_observations is not None
            else SceneObservationDemand()
        ),
        workspace=generation.workspace,
        tools=tools,
        role_store=role_store,
        session_manager=session_manager,
        relationship_runtime=relationship_runtime,
        role_runtime_registry=role_runtime_registry,
        light_provider=light_provider,
        light_model=light_model,
        memory_engine=memory_engine,
        external_turns=external_turns,
        background_results=background_results,
        http=http,
        process_resources=generation.process_resources,
    )
    return PluginKernel(
        plugin_dirs,
        settings=generation,
        core=plugin_core_modules(inputs),
        **options,
    )


def make_kernel(
    plugin_dirs: list[Path],
    *,
    event_bus: EventBus,
    tools: ToolRegistry | None = None,
    namespace: str = "",
    strict: bool = False,
    plugin_configs: dict[str, dict] | None = None,
    workspace: Path | None = None,
    session_manager: object = None,
    memory_engine: object = None,
    light_provider: object = None,
    light_model: str | None = None,
    relationship_runtime: object = None,
    rpc: PluginRpcRegistry[Any] | None = None,
) -> PluginKernel:
    """Creates a kernel over real host services for the given plugin roots.

    ``event_bus`` and ``rpc`` are passed on to ``host_kernel``.
    """
    # 独立 workspace 确保 KV 测试能发现错误的插件目录写入。
    resolved_workspace = workspace
    if resolved_workspace is None:
        resolved_workspace = Path(
            tempfile.mkdtemp(prefix="shiori-plugin-host-test-workspace-")
        )
    return host_kernel(
        plugin_dirs,
        settings=PluginGenerationSettings(
            plugin_configs=plugin_configs or {}, workspace=resolved_workspace
        ),
        memory_engine=memory_engine,
        relationship_runtime=relationship_runtime,
        tools=tools,
        session_manager=session_manager,
        light_provider=light_provider,
        light_model=light_model,
        event_bus=event_bus,
        rpc=rpc,
        namespace=namespace,
        strict=strict,
    )


def before_turn_ctx(**overrides: object) -> BeforeTurnCtx:
    """Builds a minimal before-turn context, overriding the given fields."""
    defaults: dict = dict(
        session_key="test:123",
        channel="cli",
        chat_id="123",
        content="hello",
        timestamp=datetime.now(),
        retrieved_memory_block="",
        retrieval_trace_raw=None,
        history_messages=(),
        context_scope=None,
    )
    defaults.update(overrides)
    return BeforeTurnCtx(**defaults)
