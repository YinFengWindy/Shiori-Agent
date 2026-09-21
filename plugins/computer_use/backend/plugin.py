"""Registers independent tools and tears down the entire owned Driver generation."""

from agent.plugin_host.plugin_data import plugin_data_dir
from agent.plugin_host.runtime_context import PluginRuntimeContext

from .config import ComputerUseConfig
from .desktop import ComputerDesktop
from .tool import computer_tools


async def setup(ctx: PluginRuntimeContext) -> None:
    """Contributes lazy tools without launching or attaching to any desktop app."""
    if ctx.workspace is None:
        raise RuntimeError("Computer Use 需要宿主 workspace")
    desktop = ComputerDesktop(
        plugin_data_dir(ctx.workspace, ctx.plugin_id),
        ComputerUseConfig.model_validate(ctx.config.as_dict()),
    )
    for tool in computer_tools(desktop):
        ctx.tools.register(
            tool,
            risk="external-side-effect",
            search_hint="电脑 桌面 窗口 控件 截图 点击 输入 快捷键 computer",
        )
    ctx.effect("computer_desktop", desktop.close)
