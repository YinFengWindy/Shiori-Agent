"""plugin_host 测试共享设施：隔离导入命名空间与内核构造助手。"""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

# 预热 agent.core 导入链，避免 agent.lifecycle.types 触发循环导入
from agent.core.passive_turn import ContextStore as _  # noqa: F401
from agent.lifecycle.types import BeforeTurnCtx
from agent.plugin_host import HostServices, PluginKernel
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus

# 整包暂存由公共 testkit 提供。
from shiori_plugin_testkit.packages import stage_plugin_package as stage_plugin_package

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PLUGIN_FIXTURES = REPOSITORY_ROOT / "tests/fixtures/plugins"


@pytest.fixture(autouse=True)
def _clean_plugin_modules():
    import sys

    modules_before = set(sys.modules)
    yield
    # 清理测试期间导入的插件模块。
    for name in set(sys.modules) - modules_before:
        if name.startswith("akasic_plugin_"):
            _ = sys.modules.pop(name, None)


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
    light_model: str = "",
    relationship_runtime: object = None,
) -> PluginKernel:
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
    defaults: dict = dict(
        session_key="test:123",
        channel="cli",
        chat_id="123",
        content="hello",
        timestamp=datetime.now(),
        retrieved_memory_block="",
        retrieval_trace_raw=None,
        history_messages=(),
    )
    defaults.update(overrides)
    return BeforeTurnCtx(**defaults)


@pytest.fixture
def contract_package(tmp_path: Path) -> Path:
    """A tiny external contract package for static validation and kernel gates."""
    package = tmp_path / "external_demo"
    (package / "backend").mkdir(parents=True)
    (package / "renderer").mkdir()
    (package / "manifest.yaml").write_text(
        "api: 2\npackage_contract: 1\nid: external_demo\nversion: 1.2.3\n"
        "runtime_api: '>=2.0.0 <3.0.0'\nentry: backend/plugin.py\n"
        "capabilities: []\n"
        "peer_dependencies: {react: '>=19.2.0 <20.0.0', react-dom: '>=19.2.0 <20.0.0'}\n"
        "renderer:\n  ui: {entry: renderer/ui.mjs, css: [renderer/style.css]}\n"
        "  background: {entry: renderer/background.mjs, css: []}\n"
        "  surface: {entry: renderer/surface.mjs, css: [renderer/style.css]}\n",
        encoding="utf-8",
    )
    (package / "backend/plugin.py").write_text(
        "async def setup(ctx):\n    ctx.expose({'ready': True})\n", encoding="utf-8"
    )
    for name in ("ui", "background", "surface"):
        (package / f"renderer/{name}.mjs").write_text(
            'export default {pluginId: "external_demo"};\n', encoding="utf-8"
        )
    (package / "renderer/style.css").write_text(".demo {}\n", encoding="utf-8")
    return package
