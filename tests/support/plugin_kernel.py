"""Real plugin-kernel assembly shared by host integration tests.

Builds a ``PluginKernel`` over real generation settings and core inputs so
tests load plugin packages only through the kernel's public entry points.
"""

from __future__ import annotations

import tempfile
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, cast

# 预热 agent.core 导入链，避免 agent.lifecycle.types 触发循环导入
from agent.core.passive_turn import ContextStore as _  # noqa: F401
from agent.core.turn_events import install_core_checks
from agent.lifecycle.types import BeforeTurnCtx
from agent.plugin_host import (
    PluginGenerationSettings,
    PluginKernel,
    PluginRpcRegistry,
)
from agent.plugin_host.core_keys import CoreModule, CoreProvide
from agent.tools.registry import ToolRegistry
from bootstrap.plugin_core import PluginCoreInputs, plugin_core_modules
from bus.event_bus import EventBus
from shiori_sdk.kernel import Key

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_FIXTURES = REPOSITORY_ROOT / "tests/fixtures/plugins"


def host_kernel(
    plugin_dirs: list[Path],
    *,
    settings: PluginGenerationSettings | None = None,
    tools: ToolRegistry | None = None,
    role_store: Any = None,
    provider: Any = None,
    model: str | None = None,
    http: Any = None,
    session_manager: Any = None,
    light_provider: Any = None,
    light_model: str | None = None,
    role_runtime_registry: Any = None,
    scene_followup: bool = False,
    external_turns: Any = None,
    background_results: Any = None,
    event_bus: EventBus | None = None,
    rpc: PluginRpcRegistry[Any] | None = None,
    proactive_host: Any = None,
    conversation: Any = None,
    withheld: frozenset[Key[Any]] = frozenset(),
    **options: Any,
) -> PluginKernel:
    """A kernel over ``settings`` with the same core provide list as bootstrap.

    ``settings`` defaults to an empty generation (no workspace). The remaining
    keywords are the ``PluginCoreInputs`` fields, real services or test
    doubles; one left None makes a plugin declaring a capability over it fail
    before setup. The core's ``workspace`` and ``process_resources`` are those
    of ``settings``. ``event_bus`` defaults to a fresh one and ``rpc`` to a new
    registry over that bus (pass one to read what plugins registered).
    ``withheld`` keys are dropped from the core
    provide list, as if no core module provided them. ``options`` are the
    remaining ``PluginKernel`` keyword arguments.
    """
    generation = settings if settings is not None else PluginGenerationSettings()
    bus = event_bus if event_bus is not None else EventBus()
    inputs = PluginCoreInputs(
        plugin_dirs=tuple(plugin_dirs),
        event_bus=bus,
        rpc=rpc if rpc is not None else PluginRpcRegistry(bus),
        scene_followup=scene_followup,
        workspace=generation.workspace,
        tools=tools,
        role_store=role_store,
        session_manager=session_manager,
        role_runtime_registry=role_runtime_registry,
        provider=provider,
        model=model,
        light_provider=light_provider,
        light_model=light_model,
        external_turns=external_turns,
        background_results=background_results,
        http=http,
        process_resources=generation.process_resources,
        proactive_host=proactive_host,
        conversation=conversation,
    )
    return PluginKernel(
        plugin_dirs,
        settings=generation,
        core=tuple(
            _withholding(module, withheld) for module in plugin_core_modules(inputs)
        ),
        core_checks=partial(install_core_checks, workspace=generation.workspace),
        **options,
    )


def _withholding(module: CoreModule, withheld: frozenset[Key[Any]]) -> CoreModule:
    """``module`` providing everything except the ``withheld`` keys."""

    def provide_except(provide: CoreProvide) -> None:
        def guarded(key: Key[Any], impl: Any) -> None:
            if key not in withheld:
                provide(key, impl)

        module(cast(CoreProvide, guarded))

    return provide_except


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
    provider: object = None,
    model: str | None = None,
    light_provider: object = None,
    light_model: str | None = None,
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
        provider=provider,
        model=model,
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
