"""Register lazy local execution; enabling the plugin starts no processes."""

from shiori_sdk.plugin_services import ServicePluginContext
from shiori_sdk.storage import plugin_data_dir

from .cli import HerdrCli
from .config import HerdrConfig
from .service import TaskService
from .tool import StartCodingTask
from .management_tools import TaskManagementTool
from .dashboard import Dashboard
from .sessions import SessionGate, register_session_rpc
from .agents import SessionAgents
from .agent_control import AgentCommandLog, AgentControl
from .agent_tools import AgentTool
from .agent_watch import AgentWatcher


async def setup(ctx: ServicePluginContext) -> None:
    """Assemble the task service from public SDK capabilities only."""
    directory = plugin_data_dir(ctx.workspace, ctx.plugin_id)
    directory.mkdir(parents=True, exist_ok=True)
    config = HerdrConfig.model_validate(ctx.config.as_dict())
    service = ctx.process_resources.acquire(
        "tasks-v1", lambda: TaskService(directory, ctx.processes)
    )
    ctx.expose(service)
    # Command records, handovers and watches outlive configuration reloads
    # like the tasks do.
    commands = ctx.process_resources.acquire("agent-commands-v2", AgentCommandLog)
    watcher = ctx.process_resources.acquire(
        "agent-watches-v1", lambda: AgentWatcher(directory, ctx.processes)
    )
    Dashboard(service, ctx).register()
    # The retained task service may belong to an earlier generation; sessions
    # and agents use only this generation's config and process capability,
    # so the CommandError caught there is this generation's own.
    cli = HerdrCli(config, ctx.processes, directory)
    register_session_rpc(ctx, cli)
    control = AgentControl(
        SessionGate(cli, ctx.process_resources), commands, service, watcher
    )
    agents = SessionAgents(service, ctx, control)
    agents.register()
    # Session-wide, without confirmation: the user asked roles to drive agents.
    for action in ("list", "read", "prompt", "keys"):
        ctx.tools.register(
            AgentTool(
                action,
                agents,
                ctx.tools,
                ctx.roles,
                ctx.background_results,
                ctx.process_resources,
            ),
            risk="read-only" if action in {"list", "read"} else "external-side-effect",
            search_hint="Herdr agent 终端 Claude Code Codex 发消息 按键 中断 推动",
        )
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
