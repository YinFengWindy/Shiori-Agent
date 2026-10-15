"""Prompts and key presses sent to session agents, with each agent's command record.

The desktop panel and the role tools share this one sending path; only the
recorded source differs. A role's command hands the agent over to that role,
and a delivered command to an agent with a handling role is watched and
reported back (`agent_watch.py`). Records live as long as the Shiori process:
they survive configuration reloads and are never persisted or recovered.
"""

import asyncio
from collections import deque
from contextlib import nullcontext
from dataclasses import asdict, dataclass, field
from typing import Literal, cast
from uuid import uuid4

from shiori_sdk.background_results import BackgroundResultTarget

from .agent_watch import AgentWatcher, Handover
from .cli import CommandError
from .models import now
from .service import TaskService
from .sessions import SessionGate
from .task_management import linked_task, run_in_progress

type CommandKind = Literal["prompt", "keys"]
type CommandStatus = Literal["sending", "sent", "unconfirmed", "failed"]
type ReportStatus = Literal["none", "pending", "reported", "failed"]

COMMAND_LIMIT = 100
"""Records kept per agent; older ones are dropped."""

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


@dataclass(frozen=True)
class CommandSource:
    """Who sent a command: the desktop user, or a role (ID and display name)."""

    kind: Literal["user", "role"]
    role_id: str = ""
    role_name: str = ""


USER = CommandSource("user")
"""The user typing in the desktop panel."""


@dataclass
class AgentCommand:
    """One prompt or key sequence sent to an agent and its outcome."""

    kind: CommandKind
    content: str
    source: CommandSource
    id: str = field(default_factory=lambda: uuid4().hex)
    sent_at: str = field(default_factory=now)
    status: CommandStatus = "sending"
    error: str = ""
    # Whether the agent's handling role hears how the agent ended up after it.
    report: ReportStatus = "none"
    report_error: str = ""

    def settle(self, status: CommandStatus, error: str = "") -> None:
        """Record the outcome once Herdr answered, or failed to."""
        self.status, self.error = status, error

    def settle_report(self, report: ReportStatus, error: str = "") -> None:
        """Record whether, and how, the command is reported back."""
        self.report, self.report_error = report, error

    def as_dict(self) -> dict[str, object]:
        """The JSON shape the desktop and the role tools read."""
        return asdict(self)


class AgentCommandLog:
    """Per-agent command records of this process, oldest first, at most 100 each.

    Keyed by session and pane ID, since pane IDs are only unique within a
    session. A process resource, so a configuration reload keeps the records.
    """

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], deque[AgentCommand]] = {}

    def add(self, session: str, pane_id: str, command: AgentCommand) -> AgentCommand:
        """Append a command; the oldest one of a full record is dropped."""
        records = self._records.setdefault(
            (session, pane_id), deque(maxlen=COMMAND_LIMIT)
        )
        records.append(command)
        return command

    def records(self, session: str, pane_id: str) -> list[dict[str, object]]:
        """One agent's records, oldest first."""
        return [
            command.as_dict() for command in self._records.get((session, pane_id), ())
        ]

    async def close(self) -> None:
        """Records are memory only; there is nothing to release."""
        self._records.clear()


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
        target: BackgroundResultTarget | None = None

        async def submit() -> dict[str, object]:
            # The last look, after the session check: nothing awaits between
            # it and handing the input to Herdr.
            nonlocal handed, target
            self._require_free(pane_id)
            _ = self.log.add(self.session, pane_id, command)
            handed = True
            if report_to is not None:
                source = command.source
                self.watcher.take_over(
                    self.session,
                    pane_id,
                    Handover(source.role_id, source.role_name, report_to),
                )
            handover = self.watcher.handover(self.session, pane_id)
            target = handover.target if handover else None
            return await self.gate.cli.call(*args, timeout=timeout)

        def follow(working: bool = False) -> None:
            # A delivered or possibly delivered command is watched for its report.
            if target is not None:
                self.watcher.follow(config, pane_id, command, target, working=working)

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
