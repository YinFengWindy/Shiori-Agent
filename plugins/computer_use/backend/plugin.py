"""Registers independent tools and tears down the entire owned Driver generation."""

from shiori_sdk.storage import plugin_data_dir
from shiori_sdk.runtime import PluginRuntimeContext
from shiori_sdk.core.services import (
    CONFIG,
    PROCESSES,
    RESOURCES,
    TOOLS,
    TOOL_TURN,
    WORKSPACE,
)

from .config import ComputerUseConfig
from .desktop import ComputerDesktop
from .tool import computer_tools


async def setup(ctx: PluginRuntimeContext) -> None:
    """Contributes lazy tools without launching or attaching to any desktop app."""
    desktop = ComputerDesktop(
        plugin_data_dir(ctx.require(WORKSPACE), ctx.plugin_id),
        ComputerUseConfig.model_validate(ctx.require(CONFIG).as_dict()),
        processes=ctx.require(PROCESSES),
        resources=ctx.require(RESOURCES).root,
        current_turn=ctx.require(TOOL_TURN),
    )
    for tool in computer_tools(desktop):
        ctx.require(TOOLS).register(
            tool,
            risk="external-side-effect",
            search_hint="电脑 桌面 窗口 控件 截图 点击 输入 快捷键 computer",
        )
    ctx.effect("computer_desktop", desktop.close)
