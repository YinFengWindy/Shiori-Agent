"""Real plugin-kernel assembly shared by host integration tests.

Builds a ``PluginKernel`` over real ``HostServices`` so tests load plugin
packages only through the kernel's public entry points.
"""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

# 预热 agent.core 导入链，避免 agent.lifecycle.types 触发循环导入
from agent.core.passive_turn import ContextStore as _  # noqa: F401
from agent.lifecycle.types import BeforeTurnCtx
from agent.plugin_host import HostServices, PluginKernel
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_FIXTURES = REPOSITORY_ROOT / "tests/fixtures/plugins"


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
    return PluginKernel(
        plugin_dirs,
        services=HostServices(
            event_bus=event_bus,
            tool_registry=tools,
            plugin_configs=plugin_configs or {},
            workspace=resolved_workspace,
            session_manager=session_manager,
            memory_engine=memory_engine,
            light_provider=light_provider,
            light_model=light_model,
            relationship_runtime=relationship_runtime,
        ),
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
