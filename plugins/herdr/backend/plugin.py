"""Register lazy local execution; enabling the plugin starts no processes."""

from shiori_sdk.plugin_services import ServicePluginContext
from shiori_sdk.storage import plugin_data_dir
from shiori_sdk.core.services import (
    BACKGROUND_RESULTS,
    CONFIG,
    PROCESSES,
    PROCESS_RESOURCES,
    ROLES,
    TOOLS,
    WORKSPACE,
)

from .cli import HerdrCli
from .config import HerdrConfig
from .service import TaskService
from .tool import StartCodingTask
from .management_tools import TaskManagementTool
from .dashboard import Dashboard
from .sessions import SessionGate, register_session_rpc
from .agents import SessionAgents
from .agent_commands import AgentCommandLog
from .agent_control import AgentControl
from .agent_tools import AgentTool
from .agent_watch import AgentWatcher


async def setup(ctx: ServicePluginContext) -> None:
    """Assemble the task service from public SDK capabilities only."""
    directory = plugin_data_dir(ctx.require(WORKSPACE), ctx.plugin_id)
    directory.mkdir(parents=True, exist_ok=True)
    config = HerdrConfig.model_validate(ctx.require(CONFIG).as_dict())
    # Tasks and watches are built idle; each generation offers its own
    # process capability, which they use only while it is published.
    service = ctx.require(PROCESS_RESOURCES).acquire(
        "tasks-v2", lambda: TaskService(directory)
    )
    service.attach(ctx.require(PROCESS_RESOURCES), ctx.require(PROCESSES), directory)
    ctx.expose(service)
    # Command records, handovers and watches outlive configuration reloads
    # like the tasks do.
    commands = ctx.require(PROCESS_RESOURCES).acquire(
        "agent-commands-v2", AgentCommandLog
    )
    watcher = ctx.require(PROCESS_RESOURCES).acquire("agent-watches-v2", AgentWatcher)
    watcher.attach(ctx.require(PROCESS_RESOURCES), ctx.require(PROCESSES), directory)
    Dashboard(service, ctx).register()
    # The retained task service may run an earlier generation's code; sessions
    # and agents use only this generation's config and process capability,
    # so the CommandError caught there is this generation's own.
    cli = HerdrCli(config, ctx.require(PROCESSES), directory)
    register_session_rpc(ctx, cli)
    control = AgentControl(
        SessionGate(cli, ctx.require(PROCESS_RESOURCES)), commands, service, watcher
    )
    agents = SessionAgents(service, ctx, control)
    agents.register()
    # Session-wide, without confirmation: the user asked roles to drive agents.
    for action in ("list", "read", "prompt", "keys"):
        ctx.require(TOOLS).register(
            AgentTool(
                action,
                agents,
                ctx.require(TOOLS),
                ctx.require(ROLES),
                ctx.require(BACKGROUND_RESULTS),
                ctx.require(PROCESS_RESOURCES),
            ),
            risk="read-only" if action in {"list", "read"} else "external-side-effect",
            search_hint="Herdr agent 终端 Claude Code Codex 发消息 按键 中断 推动",
        )
    ctx.require(TOOLS).register(
        StartCodingTask(
            service,
            ctx.require(BACKGROUND_RESULTS),
            config,
            ctx.require(PROCESS_RESOURCES),
        ),
        risk="external-side-effect",
        search_hint="写代码 开发 修bug coding agent codex claude herdr PR",
    )
    for action in ("list", "get", "continue", "cancel"):
        ctx.require(TOOLS).register(
            TaskManagementTool(
                service,
                ctx.require(TOOLS),
                ctx.require(PROCESS_RESOURCES),
                action,
                ctx.require(BACKGROUND_RESULTS),
            ),
            risk="read-only" if action in {"list", "get"} else "external-side-effect",
            search_hint="Herdr 任务 状态 进度 继续 取消 coding agent",
        )
