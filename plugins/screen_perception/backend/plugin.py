"""Owns the on-demand screen tool and its in-flight analyses."""

from shiori_sdk.runtime import PluginRuntimeContext
from shiori_sdk.core.services import MODELS, ROLES, TOOLS

from .capture import PrimaryScreenCapture
from .model import ObservationModelAdapter
from .tool import ObserveScreenTool


async def setup(ctx: PluginRuntimeContext) -> None:
    """Registers role-bound screen perception independently of presentation plugins."""
    tool = ObserveScreenTool(
        capture=PrimaryScreenCapture(),
        analyzer=ObservationModelAdapter(
            roles=ctx.require(ROLES),
            models=ctx.require(MODELS),
        ),
    )
    ctx.require(TOOLS).register(
        tool,
        always_on=True,
        risk="read-only",
        search_hint="屏幕 桌面 当前窗口 观察主屏",
    )
    ctx.effect("screen_analyses", tool.close)
