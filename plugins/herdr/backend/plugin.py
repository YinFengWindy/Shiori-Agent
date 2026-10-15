"""Register lazy local execution; enabling the plugin starts no processes."""

from shiori_sdk.plugin_services import ServicePluginContext
from shiori_sdk.storage import plugin_data_dir

from .cli import HerdrCli
from .config import HerdrConfig
from .service import TaskService
from .tool import StartCodingTask
from .management_tools import TaskManagementTool
from .dashboard import Dashboard
from .sessions import register_session_rpc


async def setup(ctx: ServicePluginContext) -> None:
    """Assemble the task service from public SDK capabilities only."""
    directory = plugin_data_dir(ctx.workspace, ctx.plugin_id)
    directory.mkdir(parents=True, exist_ok=True)
    config = HerdrConfig.model_validate(ctx.config.as_dict())
    service = ctx.process_resources.acquire(
        "tasks-v1", lambda: TaskService(directory, ctx.processes)
    )
    ctx.expose(service)
    Dashboard(service, ctx).register()
    # The retained task service may belong to an earlier generation; listing
    # sessions uses only this generation's config and process capability.
    register_session_rpc(ctx, HerdrCli(config, ctx.processes, directory))
    ctx.tools.register(
        StartCodingTask(service, ctx.background_results, config, ctx.process_resources),
        risk="external-side-effect",
        search_hint="写代码 开发 修bug coding agent codex claude herdr PR",
    )
    for action in ("list", "get", "continue", "cancel"):
        ctx.tools.register(
            TaskManagementTool(
                service,
                ctx.tools,
                ctx.process_resources,
                action,
                ctx.background_results,
            ),
            risk="read-only" if action in {"list", "get"} else "external-side-effect",
            search_hint="Herdr 任务 状态 进度 继续 取消 coding agent",
        )
