"""Prompts and key presses sent to session agents, with each agent's command record.

The desktop panel and the role tools share this one sending path; only the
recorded source differs. A role's command hands the agent over to that role,
and a delivered command to an agent with a handling role is watched and
reported back (`agent_watch.py`). Records live as long as the Shiori process:
they survive configuration reloads and are never persisted or recovered.
"""

import asyncio
from contextlib import nullcontext
from typing import cast

from shiori_sdk.background_results import BackgroundResultTarget

from .agent_commands import AgentCommand, AgentCommandLog, CommandSource, Handover
from .agent_watch import AgentWatcher, state_seq
from .cli import CommandError
from .service import TaskService
from .sessions import SessionGate
from .task_management import linked_task, run_in_progress

UNCONFIRMED_CODES = frozenset({"timeout", "agent_prompt_stalled", "invalid_response"})
"""Outcomes that do not prove the input was or was not delivered."""

# Herdr's gate waits up to 5 s for a submitted prompt to show activity; the
# caller timeout covers submission too, so it leaves room beyond that gate.
PROMPT_TIMEOUT_MS = 10000

# The prompt process outlives Herdr's own wait by this much, so Herdr reports
# its timeout itself instead of the process being killed mid-wait.
_PROCESS_MARGIN_SECONDS = 5

_REFUSALS = {
    "agent_not_found": "Agent 已关闭，未发送。",
    "agent_blocked": "Agent 正在等待确认或回答，未发送；请先在 Herdr 中处理。",
}

# The live server's own refusals, and outcomes a session check must not mask.
_KEEP = UNCONFIRMED_CODES | frozenset(_REFUSALS)


def require_pane_id(value: object) -> str:
    """The agent target of a request: a nonempty pane ID."""
    if not isinstance(value, str) or not value:
        raise ValueError("缺少 agent 的 pane_id")
    return value


class AgentControl:
    """Sends prompts and keys to the configured session's agents and records them.

    Every command handed to Herdr is recorded with its outcome. A timed-out
    or stalled prompt is recorded as unconfirmed and never resent. Inputs
    are validated here, so the panel RPC and the role tools share the rules.

    A role's command carries the destination the host captured in its tool
    turn and makes the role the agent's handling role; the user's command is
    reported to the handling role of that moment, or not at all without one.
    """

    def __init__(
        self,
        gate: SessionGate,
        log: AgentCommandLog,
        service: TaskService,
        watcher: AgentWatcher,
    ) -> None:
        self.gate, self.log, self.service = gate, log, service
        self.watcher = watcher

    @property
    def session(self) -> str:
        """The session this generation's commands go to."""
        return self.gate.cli.config.session

    def refusal(self, pane_id: str) -> str:
        """Why this agent takes no direct input now; empty when it does.

        A run of a plugin task owns its agent until it ends: direct input would
        land inside the monitored run, and its interruption is the task's
        tracked cancellation instead.
        """
        task = linked_task(self.service.tasks.values(), self.session, pane_id)
        if task is not None and run_in_progress(task):
            return "该 Agent 正在执行插件任务；要停下它请取消任务"
        return ""

    async def prompt(
        self,
        pane_id: object,
        text: object,
        source: CommandSource,
        report_to: BackgroundResultTarget | None = None,
    ) -> AgentCommand:
        """Submit `text` as a prompt; sent once Herdr sees the agent take it up.

        `report_to` is a role source's destination, captured in its tool turn.
        """
        target = require_pane_id(pane_id)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("消息不能为空")
        return await self._send(
            target,
            AgentCommand("prompt", text, source),
            report_to,
            # Settles as soon as the agent starts working (or asks something),
            # so the request does not wait for the agent's whole turn.
            (
                "agent",
                "prompt",
                target,
                text,
                "--wait",
                "--until",
                "working",
                "--until",
                "blocked",
                "--timeout",
                str(PROMPT_TIMEOUT_MS),
            ),
            timeout=max(
                self.gate.cli.config.cli_timeout_seconds,
                PROMPT_TIMEOUT_MS / 1000 + _PROCESS_MARGIN_SECONDS,
            ),
        )

    async def send_keys(
        self,
        pane_id: object,
        keys: object,
        source: CommandSource,
        report_to: BackgroundResultTarget | None = None,
    ) -> AgentCommand:
        """Press Herdr logical keys (`ctrl+c`, `esc`, `enter` …) in order."""
        target = require_pane_id(pane_id)
        names = cast(list[object], keys) if isinstance(keys, list) else []
        if not names or not all(isinstance(name, str) and name for name in names):
            raise ValueError("按键不能为空")
        pressed = [str(name) for name in names]
        return await self._send(
            target,
            AgentCommand("keys", " ".join(pressed), source),
            report_to,
            ("agent", "send-keys", target, *pressed),
        )

    def _require_free(self, pane_id: str) -> None:
        refusal = self.refusal(pane_id)
        if refusal:
            raise ValueError(refusal)

    async def _send(
        self,
        pane_id: str,
        command: AgentCommand,
        report_to: BackgroundResultTarget | None,
        args: tuple[str, ...],
        *,
        timeout: float | None = None,
    ) -> AgentCommand:
        if command.source.kind == "role" and report_to is None:
            raise PermissionError("角色的指令需要宿主抓取的回报目标")
        self._require_free(pane_id)
        task = linked_task(self.service.tasks.values(), self.session, pane_id)
        config = self.gate.cli.config
        handed = False
        baseline: int | None = None
        target: BackgroundResultTarget | None = None

        async def submit() -> dict[str, object]:
            nonlocal handed, baseline, target
            # A role's command reports to that role; the user's to the agent's
            # handling role of this moment, if any.
            handover = self.watcher.handover(self.session, pane_id)
            target = report_to or (handover.target if handover else None)
            if target is not None and command.kind == "keys":
                # Keys often answer a blocked agent: only a blocked state
                # reached after this read is the agent getting stuck again.
                # A failed read leaves it unknown and never holds back the
                # keys: an interrupt must not wait on an observation.
                try:
                    agent = await self.gate.cli.call("agent", "get", pane_id)
                    baseline = state_seq(agent["agent"])
                except CommandError:
                    baseline = None
            # The last look, after the session check: nothing awaits between
            # it and handing the input to Herdr.
            self._require_free(pane_id)
            _ = self.log.add(self.session, pane_id, command)
            handed = True
            if report_to is not None:
                self.watcher.take_over(
                    self.session, pane_id, Handover(command.source.role_name, report_to)
                )
            return await self.gate.cli.call(*args, timeout=timeout)

        def follow(working: bool = False) -> None:
            # A delivered or possibly delivered command is watched for its report.
            if target is not None:
                self.watcher.follow(
                    config,
                    pane_id,
                    command,
                    target,
                    working=working,
                    baseline=baseline,
                )

        # The task's continue and cancel hold this lock to start or stop a run;
        # holding it here keeps a run from starting while the input is sent.
        async with task.operation_lock if task else nullcontext():
            try:
                response = await self.gate.run(submit, keep=_KEEP)
            except CommandError as error:
                if not handed:
                    raise  # The session check failed; nothing was sent.
                if error.code in UNCONFIRMED_CODES:
                    message = "未确认 Agent 收到；输入可能已经送达，未自动重发。"
                    command.settle("unconfirmed", message)
                    follow()
                    raise CommandError(message, code=error.code) from error
                message = _REFUSALS.get(error.code, str(error))
                command.settle("failed", message)
                raise CommandError(message, code=error.code) from error
            except asyncio.CancelledError:
                if handed:
                    command.settle(
                        "unconfirmed", "Shiori 已停止等待；输入可能已经送达。"
                    )
                    follow()
                raise
            except Exception as error:
                if handed:
                    command.settle("failed", str(error))
                raise
            command.settle("sent")
            # A prompt returns once Herdr saw the agent working (or blocked).
            agent = response.get("agent")
            follow(
                command.kind == "prompt"
                and isinstance(agent, dict)
                and cast(dict[str, object], agent).get("agent_status") == "working"
            )
        return command
