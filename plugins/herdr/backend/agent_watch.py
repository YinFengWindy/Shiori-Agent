"""Handing agents over to roles, and reporting back to them once an agent stops.

A role becomes an agent's handling role when it sends the agent a prompt or
keys through its tools; a later role takes over from it. Every command sent
to an agent with a handling role, by a role or by the user in the panel, is
watched until the agent stops working, gets blocked, disappears, or the
watch times out, and is then reported once to the role that is to hear of
it. The report destination is only ever captured by the host in a role's
tool turn; the plugin never picks a role itself.

Handovers and watches live as long as the Shiori process: they survive
configuration reloads, end with the plugin or the application, and are
never persisted or recovered. Stopping a watch never touches the agent.
"""

import asyncio
import json
import time
from collections.abc import Callable
from contextvars import Context
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from shiori_sdk.background_results import BackgroundResultTarget
from shiori_sdk.processes import Processes

from .cli import CommandError, HerdrCli
from .config import HerdrConfig

if TYPE_CHECKING:
    from .agent_control import AgentCommand, ReportStatus

type Outcome = Literal["finished", "idle", "blocked", "gone", "timeout", "unreadable"]

OUTCOMES: dict[Outcome, str] = {
    "finished": "Agent 工作后已停下",
    "idle": "Agent 处于空闲，指令后未观察到它开始工作",
    "blocked": "Agent 卡住了，正在等待确认或回答",
    "gone": "Agent 已关闭",
    "timeout": "追踪超时，Agent 可能仍在工作；未中断或重发",
    "unreadable": "无法读取 Agent 状态，已停止追踪",
}
"""What each way a watch ends means, as the report states it."""

OUTPUT_TAIL = 4000
"""Characters of terminal output a report carries, from the end."""

POLL_SECONDS = 2.0
"""Pause before each look at the agent, as the task monitor polls."""

START_GRACE_SECONDS = 30.0
"""How long an idle agent may take to start on a command before it is reported idle."""

READ_FAILURE_LIMIT = 5
"""Consecutive failed state reads after which the watch gives up."""

USER_SENDER = "用户在 Herdr 面板直接发送"
"""How a report names a command the user typed into the panel."""


@dataclass(frozen=True)
class Handover:
    """The role handling an agent, and where its reports go."""

    role_id: str
    role_name: str
    target: BackgroundResultTarget

    def as_dict(self) -> dict[str, str]:
        """The role as the desktop and the role tools show it."""
        return {"role_id": self.role_id, "role_name": self.role_name}


@dataclass
class _Pending:
    command: "AgentCommand"
    target: BackgroundResultTarget


@dataclass
class _Watch:
    """One agent's watch: the commands awaiting a report and what was seen."""

    cli: HerdrCli
    pane_id: str
    pending: list[_Pending] = field(default_factory=list)
    reporting: list[_Pending] = field(default_factory=list)
    # When the latest command arrived; the start grace and timeout count from it.
    changed_at: float = 0.0
    # Bumped by every arriving command, so a read begun before it is discarded.
    revision: int = 0
    working: bool = False
    agent: dict[str, Any] = field(default_factory=dict)
    worker: asyncio.Task[None] | None = None


def report_text(
    session: str,
    pane_id: str,
    outcome: Outcome,
    agent: dict[str, Any],
    output: str,
    batch: list[_Pending],
) -> str:
    """The report: how the agent stopped, its title, the commands and the output tail."""
    return json.dumps(
        {
            "session": session,
            "pane_id": pane_id,
            "agent": str(agent.get("agent", "")),
            "outcome": outcome,
            "outcome_text": OUTCOMES[outcome],
            "agent_state": str(agent.get("agent_status", "")),
            "title": str(
                agent.get("terminal_title_stripped")
                or agent.get("terminal_title")
                or ""
            ),
            "commands": [
                {
                    "kind": item.command.kind,
                    "content": item.command.content,
                    "sender": (
                        USER_SENDER
                        if item.command.source.kind == "user"
                        else item.command.source.role_name
                        or item.command.source.role_id
                    ),
                    "sent_at": item.command.sent_at,
                    "send_status": item.command.status,
                }
                for item in batch
            ],
            "output": output,
        },
        ensure_ascii=False,
    )


class AgentWatcher:
    """Handovers and watches of this process, keyed by session and pane ID.

    A process resource: it builds its own CLI per watch from the session's
    configuration snapshot, so the errors it catches are its own generation's.
    """

    def __init__(self, directory: Path, processes: Processes) -> None:
        self.directory, self.processes = directory, processes
        self.closed = False
        self.poll_seconds = POLL_SECONDS
        self.start_grace_seconds = START_GRACE_SECONDS
        self.clock: Callable[[], float] = time.monotonic
        self._handovers: dict[tuple[str, str], Handover] = {}
        self._watches: dict[tuple[str, str], _Watch] = {}

    def handover(self, session: str, pane_id: str) -> Handover | None:
        """The agent's handling role, if any."""
        return self._handovers.get((session, pane_id))

    def take_over(self, session: str, pane_id: str, handover: Handover) -> None:
        """The role becomes the agent's handling role, replacing any earlier one."""
        self._handovers[(session, pane_id)] = handover

    def follow(
        self,
        config: HerdrConfig,
        pane_id: str,
        command: "AgentCommand",
        target: BackgroundResultTarget,
        *,
        working: bool,
    ) -> None:
        """Watch the agent for this delivered command and report it once.

        A command arriving while the agent is already watched joins the
        commands awaiting the report, which lists them all. `working` tells
        that the agent was seen working on the command already. Keys keep
        what was seen, so an interrupt of working agent reads as it stopping.
        """
        if self.closed:
            command.settle_report("failed", "Shiori 已停止监视，不会回报")
            return
        key = (config.session, pane_id)
        watch = self._watches.get(key)
        if watch is None:
            cli = HerdrCli(config.model_copy(deep=True), self.processes, self.directory)
            watch = self._watches[key] = _Watch(cli, pane_id)
            watch.worker = asyncio.create_task(
                self._run(key, watch), name=f"herdr-watch:{pane_id}", context=Context()
            )
        command.settle_report("pending")
        watch.pending.append(_Pending(command, target))
        watch.changed_at = self.clock()
        watch.revision += 1
        watch.working = working or (command.kind == "keys" and watch.working)

    async def close(self) -> None:
        """Stop every watch; the agents keep running and nothing is reported."""
        self.closed = True
        workers = [
            watch.worker
            for watch in self._watches.values()
            if watch.worker and not watch.worker.done()
        ]
        for worker in workers:
            _ = worker.cancel()
        outcomes = await asyncio.gather(*workers, return_exceptions=True)
        self._handovers.clear()
        errors = [error for error in outcomes if isinstance(error, Exception)]
        if errors:
            raise ExceptionGroup("Herdr agent 监视清理失败", errors)

    async def _run(self, key: tuple[str, str], watch: _Watch) -> None:
        try:
            while watch.pending:
                outcome, output = await self._observe(watch)
                watch.reporting, watch.pending = watch.pending, []
                watch.working = False
                if outcome == "gone":
                    _ = self._handovers.pop(key, None)
                await self._report(key[0], watch, outcome, output)
                watch.reporting = []
            # Commands arriving during a report start another round above.
        except asyncio.CancelledError:
            for item in (*watch.reporting, *watch.pending):
                if item.command.report == "pending":
                    item.command.settle_report("failed", "Shiori 已停止监视，未回报")
            raise
        except Exception as error:
            # The watch's boundary: its commands say why they were not reported.
            for item in (*watch.reporting, *watch.pending):
                if item.command.report == "pending":
                    item.command.settle_report("failed", f"监视出错，未回报：{error}")
        finally:
            if self._watches.get(key) is watch:
                del self._watches[key]

    async def _observe(self, watch: _Watch) -> tuple[Outcome, str]:
        """Poll until the agent stops, blocks, goes away, or the watch times out."""
        failures = 0
        while True:
            await asyncio.sleep(self.poll_seconds)
            revision = watch.revision
            outcome: Outcome | None = None
            try:
                agent = (await watch.cli.call("agent", "get", watch.pane_id))["agent"]
            except CommandError as error:
                if error.code == "agent_not_found":
                    return "gone", ""
                failures += 1
                if failures >= READ_FAILURE_LIMIT:
                    return "unreadable", f"状态读取失败：{error}"
            else:
                failures = 0
                # A command arrived during the read: what was read predates it.
                if revision != watch.revision:
                    continue
                watch.agent = agent
                state = agent.get("agent_status")
                if state == "working":
                    watch.working = True
                elif state == "blocked":
                    outcome = "blocked"
                elif state in {"idle", "done"}:
                    if watch.working:
                        outcome = "finished"
                    elif self.clock() - watch.changed_at >= self.start_grace_seconds:
                        outcome = "idle"
            if outcome is None and (
                self.clock() - watch.changed_at >= watch.cli.config.task_timeout_seconds
            ):
                outcome = "timeout"
            if outcome is not None:
                return outcome, await self._tail(watch)

    async def _tail(self, watch: _Watch) -> str:
        state = watch.agent.get("agent_status")
        try:
            output = await watch.cli.read(
                watch.pane_id,
                source="recent-unwrapped" if state in {"idle", "done"} else "visible",
            )
        except CommandError as error:
            return f"终端输出暂不可读：{error}"
        return output[-OUTPUT_TAIL:]

    async def _report(
        self, session: str, watch: _Watch, outcome: Outcome, output: str
    ) -> None:
        """One report per destination role and thread; a report ID is never resent."""
        groups: dict[tuple[str, str], list[_Pending]] = {}
        for item in watch.reporting:
            groups.setdefault((item.target.role_id, item.target.thread_id), []).append(
                item
            )
        for batch in groups.values():
            text = report_text(
                session, watch.pane_id, outcome, watch.agent, output, batch
            )
            status: ReportStatus
            try:
                # The newest command's ID belongs to this report alone.
                delivered = await batch[-1].target.report(
                    f"herdr-agent:{batch[-1].command.id}", text
                )
            except Exception as error:
                status, message = "failed", str(error) or type(error).__name__
            else:
                status, message = (
                    ("reported", "")
                    if delivered
                    else ("failed", "回报已尝试过，未重发")
                )
            for item in batch:
                item.command.settle_report(status, message)
