"""Owns the on-demand screen tool and its in-flight analyses."""

from agent.plugin_host.runtime_context import PluginRuntimeContext
from core.roles import RoleRepository

from .capture import PrimaryScreenCapture
from .model import ObservationModelAdapter
from .tool import ObserveScreenTool


async def setup(ctx: PluginRuntimeContext) -> None:
    """Registers role-bound screen perception independently of presentation plugins."""
    if ctx.role_store is None or ctx.role_runtime_registry is None:
        raise RuntimeError("屏幕感知插件需要角色存储与模型运行时")
    tool = ObserveScreenTool(
        capture=PrimaryScreenCapture(),
        analyzer=ObservationModelAdapter(
            roles=RoleRepository(ctx.role_store),
            provider=None,
            model="",
            role_runtime_registry=ctx.role_runtime_registry,
        ),
    )
    ctx.tools.register(
        tool,
        always_on=True,
        risk="read-only",
        search_hint="屏幕 桌面 当前窗口 观察主屏",
    )
    ctx.effect("screen_analyses", tool.close)
