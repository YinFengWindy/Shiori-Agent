"""Plugin-submitted external-context turns (``external_turns`` capability).

A plugin that receives messages from a source that is not a channel account
(for example a live-stream chat) submits one message for a role. The host runs
it as an external-context turn in that source conversation's thread, exactly
like a group message a channel account received: the role sees only that
conversation's history and its external memory, the sender is never the bound
user, and the role is limited to the external tool whitelist. The message and
the reply are stored in that thread and appear in the phone's conversation
list under the conversation title. The reply is returned to the plugin and is
never dispatched to any channel.

User turns come first at entry: a submission never waits for the role. While
the role is replying or busy with other work, the host returns ``busy`` at once
and stores nothing. Once a submitted turn runs, role work arriving meanwhile
waits for it, so keep the messages short to answer. Cancelling the ``submit``
call cancels the turn.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Literal, Protocol

# replied: the turn ran and ``reply`` is its final text.
# busy: the role was busy; nothing ran and nothing was stored.
# duplicate: the conversation already holds ``message_id``; nothing ran.
type ExternalTurnStatus = Literal["replied", "busy", "duplicate"]


@dataclass(frozen=True)
class ExternalTurnMessage:
    """One message from an external source, submitted for ``role_id``.

    ``platform`` names the source (e.g. ``bilibili``) and must not be the
    host's ``desktop`` or a channel the host runs; with ``conversation_id`` it
    selects the role's conversation thread. ``conversation_title`` names the
    conversation in the phone. ``sender_id`` keys the sender's member profile
    on that platform; ``sender_name`` is a display-name snapshot.
    ``message_id`` is the platform message ID, unique within the conversation.
    Every field is required and must not be blank; surrounding whitespace is
    removed, except from ``text``.
    """

    role_id: str
    platform: str
    conversation_id: str
    conversation_title: str
    sender_id: str
    sender_name: str
    message_id: str
    text: str

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"外部回合消息的 {item.name} 不能为空")
            if item.name != "text":
                object.__setattr__(self, item.name, value.strip())


@dataclass(frozen=True)
class ExternalTurnResult:
    """The outcome of one submission; ``reply`` is empty unless ``replied``."""

    status: ExternalTurnStatus
    reply: str = ""


class ExternalTurns(Protocol):
    """Submit external-context turns for roles (manifest ``external_turns``)."""

    async def submit(self, message: ExternalTurnMessage) -> ExternalTurnResult:
        """Runs ``message`` as an external-context turn of its role.

        Raises ``ValueError`` for an unknown role or a reserved ``platform``.
        """
        ...
