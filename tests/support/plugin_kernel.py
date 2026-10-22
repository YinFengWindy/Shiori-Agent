"""Real plugin-kernel assembly shared by host integration tests.

Builds a ``PluginKernel`` over real ``HostServices`` so tests load plugin
packages only through the kernel's public entry points.
"""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

# 预热 agent.core 导入链，避免 agent.lifecycle.types 触发循环导入
from agent.core.passive_turn import ContextStore as _  # noqa: F401
from agent.lifecycle.types import BeforeTurnCtx
from agent.plugin_host import HostServices, PluginKernel
from agent.tools.registry import ToolRegistry
from bootstrap.plugin_core import plugin_core_modules
from bus.event_bus import EventBus
from core.scene.demand import SceneObservationDemand

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_FIXTURES = REPOSITORY_ROOT / "tests/fixtures/plugins"


def host_kernel(
    plugin_dirs: list[Path],
    *,
    services: HostServices,
    tools: ToolRegistry | None = None,
    session_manager: Any = None,
    light_provider: Any = None,
    light_model: str | None = None,
    role_runtime_registry: Any = None,
    scene_observations: SceneObservationDemand | None = None,
    external_turns: Any = None,
    background_results: Any = None,
    **options: Any,
) -> PluginKernel:
    """A kernel over ``services`` with the same core provide list as bootstrap.

    ``tools`` is the tool registry the core provides (none: plugins declaring
    ``tools`` fail before setup); ``session_manager``, ``light_provider``,
    ``light_model``, ``role_runtime_registry``, ``external_turns`` and
    ``background_results`` are what the core provides
    (real services or test doubles; none: plugins declaring them fail before
    setup), and ``scene_observations`` the demand registry (a fresh one by
    default). The core's role store, workspace and relationship runtime are
    those of ``services``. ``options`` are the remaining ``PluginKernel``
    keyword arguments.
    """
    return PluginKernel(
        plugin_dirs,
        services=services,
        core=plugin_core_modules(
            plugin_dirs,
            tools=tools,
            role_store=services.role_store,
            session_manager=session_manager,
            workspace=services.workspace,
            relationship_runtime=services.relationship_runtime,
            role_runtime_registry=role_runtime_registry,
            light_provider=light_provider,
            light_model=light_model,
            scene_observations=(
                scene_observations
                if scene_observations is not None
                else SceneObservationDemand()
            ),
            memory_engine=services.memory_engine,
            external_turns=external_turns,
            background_results=background_results,
        ),
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
) -> PluginKernel:
    """Creates a kernel over real host services for the given plugin roots."""
    # 独立 workspace 确保 KV 测试能发现错误的插件目录写入。
    resolved_workspace = workspace
    if resolved_workspace is None:
        resolved_workspace = Path(
            tempfile.mkdtemp(prefix="shiori-plugin-host-test-workspace-")
        )
    return host_kernel(
        plugin_dirs,
        services=HostServices(
            event_bus=event_bus,
            plugin_configs=plugin_configs or {},
            workspace=resolved_workspace,
            memory_engine=memory_engine,
            relationship_runtime=relationship_runtime,
        ),
        tools=tools,
        session_manager=session_manager,
        light_provider=light_provider,
        light_model=light_model,
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
