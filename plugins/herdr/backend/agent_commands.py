"""Commands sent to session agents, their per-agent record, and agent handovers.

Shared by the sending path (`agent_control.py`) and the watches reporting
back on commands (`agent_watch.py`). Everything here lives as long as the
Shiori process and is never persisted or recovered.
"""

from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Literal
from uuid import uuid4

from shiori_sdk.background_results import BackgroundResultTarget

from .models import now

type CommandKind = Literal["prompt", "keys"]
type CommandStatus = Literal["sending", "sent", "unconfirmed", "failed"]
type ReportStatus = Literal["none", "pending", "reported", "failed"]

COMMAND_LIMIT = 100
"""Records kept per agent; older ones are dropped."""


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


@dataclass(frozen=True)
class Handover:
    """The role handling an agent: the destination the host captured for it.

    The role is the target's own role; only its display name is kept beside.
    """

    role_name: str
    target: BackgroundResultTarget

    @property
    def role_id(self) -> str:
        """The handling role, as the host captured it."""
        return self.target.role_id

    def as_dict(self) -> dict[str, str]:
        """The role as the desktop and the role tools show it."""
        return {"role_id": self.role_id, "role_name": self.role_name}
