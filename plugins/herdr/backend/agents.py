"""Desktop RPC over every agent in the configured Herdr session."""

from collections.abc import Iterable
from typing import Any

from shiori_sdk.plugin_services import ServicePluginContext
from shiori_sdk.rpc import Concurrency

from .agent_control import USER, AgentControl, require_pane_id
from .cli import CommandError
from .models import CodingTask
from .service import TaskService
from .task_management import linked_task, task_detail


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
        task = linked_task(owned, session, agent.get("pane_id"))
        summary = agent_summary(agent, task.id if task else None)
        groups.setdefault(str(summary["workspace_id"]), []).append(summary)
    return [
        {"workspace_id": key, "label": labels.get(key, key), "agents": members}
        for key, members in groups.items()
        if members
    ]


class SessionAgents:
    """`agents.*` RPC against the current generation's session.

    Reads go through the control's session gate; prompts and keys are the
    desktop user's commands on the shared control, recorded as from 「你」.
    """

    def __init__(
        self, service: TaskService, ctx: ServicePluginContext, control: AgentControl
    ) -> None:
        self.service, self.ctx, self.control = service, ctx, control
        self.gate, self.cli = control.gate, control.gate.cli

    def register(self) -> None:
        """Readers run concurrently; commands take the bounded external-call lane."""
        self.ctx.rpc.register(
            "agents.list", self.list_agents, concurrency=Concurrency.READ_ONLY
        )
        self.ctx.rpc.register(
            "agents.get", self.get_agent, concurrency=Concurrency.READ_ONLY
        )
        self.ctx.rpc.register(
            "agents.prompt", self.prompt_agent, concurrency=Concurrency.INTEGRATION
        )
        self.ctx.rpc.register(
            "agents.keys", self.send_keys, concurrency=Concurrency.INTEGRATION
        )

    async def list_agents(self, _payload: dict[str, object]) -> dict[str, object]:
        """Every agent of the configured session, grouped by workspace."""

        async def read() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
            agents = (await self.cli.call("agent", "list"))["agents"]
            workspaces = (await self.cli.call("workspace", "list"))["workspaces"]
            return agents, workspaces

        agents, workspaces = await self.gate.run(read)
        return {
            "session": self.cli.config.session,
            "workspaces": group_agents(
                agents, workspaces, self.service.tasks.values(), self.cli.config.session
            ),
        }

    async def get_agent(self, payload: dict[str, object]) -> dict[str, object]:
        """One agent's state, recent terminal output, command record and linked task.

        An agent Herdr no longer knows is reported as `agent: null`, so the
        desktop can say it is gone instead of showing a read error.
        `can_prompt` tells whether the agent takes direct input now.
        """
        pane_id = require_pane_id(payload.get("pane_id"))
        session = self.cli.config.session
        commands = self.control.log.records(session, pane_id)

        async def read() -> tuple[dict[str, Any], str]:
            agent = (await self.cli.call("agent", "get", pane_id))["agent"]
            output = await self.cli.read(
                pane_id,
                source=(
                    "recent-unwrapped"
                    if agent.get("agent_status") in {"idle", "done"}
                    else "visible"
                ),
            )
            return agent, output

        try:
            agent, output = await self.gate.run(
                read, keep=frozenset({"agent_not_found"})
            )
        except CommandError as error:
            if error.code != "agent_not_found":
                raise
            return {
                "session": session,
                "agent": None,
                "output": "",
                "task": None,
                "commands": commands,
                "can_prompt": False,
            }
        task = linked_task(self.service.tasks.values(), session, pane_id)
        return {
            "session": session,
            "agent": agent_summary(agent, task.id if task else None),
            "output": output,
            "task": task_detail(self.service, task) if task else None,
            "commands": commands,
            "can_prompt": not self.control.refusal(pane_id),
        }

    async def prompt_agent(self, payload: dict[str, object]) -> dict[str, object]:
        """Send the user's text to the agent as a prompt; the control validates it."""
        command = await self.control.prompt(
            payload.get("pane_id"), payload.get("text"), USER
        )
        return {"command": command.as_dict()}

    async def send_keys(self, payload: dict[str, object]) -> dict[str, object]:
        """Press the user's keys in the agent, e.g. `["ctrl+c"]` to interrupt."""
        command = await self.control.send_keys(
            payload.get("pane_id"), payload.get("keys"), USER
        )
        return {"command": command.as_dict()}
