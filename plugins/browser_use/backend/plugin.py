"""Registers Browser Use lazily and binds cleanup to the v2 plugin effect scope."""

from shiori_sdk.storage import plugin_data_dir
from shiori_sdk.plugin_services import ServicePluginContext as PluginRuntimeContext
from shiori_sdk.core.services import CONFIG, PROCESSES, RESOURCES, TOOLS, WORKSPACE

from .browser import BrowserSessions
from .config import BrowserUseConfig
from .tool import browser_tools
from .ego_tool import ego_tools


async def setup(ctx: PluginRuntimeContext) -> None:
    """Contributes discoverable tools; no native process runs until the first action."""
    config = BrowserUseConfig.model_validate(ctx.require(CONFIG).as_dict())
    sessions = BrowserSessions(
        plugin_data_dir(ctx.require(WORKSPACE), ctx.plugin_id),
        config,
        processes=ctx.require(PROCESSES),
        resources=ctx.require(RESOURCES).root,
    )
    for tool in (
        ego_tools(sessions)
        if config.backend == "ego(lite)"
        else browser_tools(sessions)
    ):
        ctx.require(TOOLS).register(
            tool,
            risk="external-side-effect",
            search_hint="浏览器 网页 导航 点击 填表 标签页 截图 browser",
        )
    ctx.effect("browser_sessions", sessions.close)
