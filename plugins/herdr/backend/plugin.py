"""Register lazy local execution; enabling the plugin starts no processes."""

from shiori_sdk.plugin_services import ServicePluginContext
from shiori_sdk.storage import plugin_data_dir

from .cli import HerdrCli
from .config import HerdrConfig
from .service import TaskService
from .tool import StartCodingTask


async def setup(ctx: ServicePluginContext) -> None:
    """Assemble the task service from public SDK capabilities only."""
    directory = plugin_data_dir(ctx.workspace, ctx.plugin_id)
    directory.mkdir(parents=True, exist_ok=True)
    service = TaskService(
        HerdrCli(
            HerdrConfig.model_validate(ctx.config.as_dict()), ctx.processes, directory
        ),
        ctx.background,
        directory,
    )
    ctx.expose(service)
    ctx.tools.register(
        StartCodingTask(service, ctx.background_results),
        risk="external-side-effect",
        search_hint="写代码 开发 修bug coding agent codex claude herdr PR",
    )
