"""Registers Browser Use lazily and binds cleanup to the v2 plugin effect scope."""

from shiori_sdk.storage import plugin_data_dir
from shiori_sdk.plugin_services import ServicePluginContext as PluginRuntimeContext

from .browser import BrowserSessions
from .config import BrowserUseConfig
from .tool import browser_tools


async def setup(ctx: PluginRuntimeContext) -> None:
    """Contributes discoverable tools; no native process runs until the first action."""
    sessions = BrowserSessions(
        plugin_data_dir(ctx.workspace, ctx.plugin_id),
        BrowserUseConfig.model_validate(ctx.config.as_dict()),
        processes=ctx.processes,
        resources=ctx.resources.root,
    )
    for tool in browser_tools(sessions):
        ctx.tools.register(
            tool,
            risk="external-side-effect",
            search_hint="浏览器 网页 导航 点击 填表 标签页 截图 browser",
        )
    ctx.effect("browser_sessions", sessions.close)
