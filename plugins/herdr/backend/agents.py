"""Read-only view of every agent in the configured Herdr session."""

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from shiori_sdk.plugin_services import ServicePluginContext
from shiori_sdk.rpc import Concurrency

from .cli import CommandError, HerdrCli
from .config import HerdrConfig
from .models import CodingTask
from .service import TaskService
from .task_management import task_detail


def agent_summary(agent: dict[str, Any], task_id: str | None) -> dict[str, object]:
    """One Herdr agent as the desktop lists it; the pane ID is its stable target."""
    return {
        "pane_id": str(agent.get("pane_id", "")),
        "workspace_id": str(agent.get("workspace_id", "")),
        "agent": str(agent.get("agent", "")),
        "status": str(agent.get("agent_status", "unknown")),
        "title": str(
            agent.get("terminal_title_stripped") or agent.get("terminal_title") or ""
        ),
        "cwd": str(agent.get("cwd", "")),
        "task_id": task_id,
    }


def linked_task(
    tasks: Iterable[CodingTask], session: str, agent: dict[str, Any]
) -> CodingTask | None:
    """The newest plugin task whose own session and pane host this same agent kind."""
    matches = [
        task
        for task in tasks
        if task.pane_id
        and task.config.session == session
        and task.pane_id == agent.get("pane_id")
        and task.agent == agent.get("agent")
    ]
    return max(matches, key=lambda task: task.created_at, default=None)


def group_agents(
    agents: list[dict[str, Any]],
    workspaces: list[dict[str, Any]],
    tasks: Iterable[CodingTask],
    session: str,
) -> list[dict[str, object]]:
    """Workspaces in Herdr's order, each with its agents; empty workspaces are left out.

    An agent whose workspace appeared after the workspace list was read is
    still shown, under its workspace ID, rather than dropped.
    """
    owned = list(tasks)
    order = sorted(workspaces, key=lambda item: item.get("number", 0))
    labels = {
        str(item["workspace_id"]): str(item.get("label") or item["workspace_id"])
        for item in order
    }
    groups: dict[str, list[dict[str, object]]] = {key: [] for key in labels}
    for agent in agents:
        task = linked_task(owned, session, agent)
        summary = agent_summary(agent, task.id if task else None)
        groups.setdefault(str(summary["workspace_id"]), []).append(summary)
    return [
        {"workspace_id": key, "label": labels.get(key, key), "agents": members}
        for key, members in groups.items()
        if members
    ]


class SessionAgents:
    """`agents.list` / `agents.get` against the current generation's session.

    The Herdr version and session check runs before the first read and again
    after any failed read, so polling a healthy session costs only the reads
    while a stopped or incompatible session still reports its actual reason.
    """

    def __init__(
        self,
        service: TaskService,
        ctx: ServicePluginContext,
        config: HerdrConfig,
        directory: Path,
    ) -> None:
        self.service, self.ctx = service, ctx
        # This generation's own adapter: its CommandError is the one caught here.
        self.cli = HerdrCli(config, ctx.processes, directory)
        self._verified = False

    def register(self) -> None:
        """Both readers are safe to run concurrently with each other and tasks."""
        self.ctx.rpc.register(
            "agents.list", self.list_agents, concurrency=Concurrency.READ_ONLY
        )
        self.ctx.rpc.register(
            "agents.get", self.get_agent, concurrency=Concurrency.READ_ONLY
        )

    async def _require_session(self) -> None:
        if not self.ctx.process_resources.active:
            raise RuntimeError("Herdr 配置已替换，请刷新看板")
        if not self._verified:
            await self.cli.require_supported_version()
            self._verified = True

    async def list_agents(self, _payload: dict[str, object]) -> dict[str, object]:
        """Every agent of the configured session, grouped by workspace."""
        await self._require_session()
        try:
            agents = (await self.cli.call("agent", "list"))["agents"]
            workspaces = (await self.cli.call("workspace", "list"))["workspaces"]
        except CommandError:
            self._verified = False
            raise
        return {
            "session": self.cli.config.session,
            "workspaces": group_agents(
                agents, workspaces, self.service.tasks.values(), self.cli.config.session
            ),
        }

    async def get_agent(self, payload: dict[str, object]) -> dict[str, object]:
        """One agent's state, recent terminal output and linked task.

        An agent Herdr no longer knows is reported as `agent: null`, so the
        desktop can say it is gone instead of showing a read error.
        """
        pane_id = payload.get("pane_id")
        if not isinstance(pane_id, str) or not pane_id:
            raise ValueError("缺少 agent 的 pane_id")
        await self._require_session()
        session = self.cli.config.session
        try:
            agent = (await self.cli.call("agent", "get", pane_id))["agent"]
            output = await self.cli.read(
                pane_id,
                source=(
                    "recent-unwrapped"
                    if agent.get("agent_status") in {"idle", "done"}
                    else "visible"
                ),
            )
        except CommandError as error:
            if error.code == "agent_not_found":
                return {"session": session, "agent": None, "output": "", "task": None}
            self._verified = False
            raise
        task = linked_task(self.service.tasks.values(), session, agent)
        return {
            "session": session,
            "agent": agent_summary(agent, task.id if task else None),
            "output": output,
            "task": task_detail(self.service, task) if task else None,
        }
