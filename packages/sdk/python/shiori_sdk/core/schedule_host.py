"""``SCHEDULE_HOST``: run a role's due scheduled job on the host (P6s).

The scheduler keeps jobs, timing and their store. Running a role turn and
delivering into a role's conversation stay on the host. The host provides
this key before any plugin starts.

Each call runs on the host's currently published generation, the way an
incoming message does. It waits while no generation admits work. The port
itself does not belong to a generation, so a process-level scheduler can keep
one reference across runtime reloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from shiori_sdk.channels.threads import role_thread_prefix
from shiori_sdk.kernel import Key


def scheduler_thread_id(role_id: str, job_id: str) -> str:
    """The thread of a job created without a source conversation thread.

    The host recognises this format as the role's own scheduled-job context.
    """
    return f"{role_thread_prefix(role_id)}scheduler:{job_id}"


@dataclass(frozen=True, kw_only=True)
class ScheduledRun:
    """One due occurrence of a role's scheduled job.

    ``job_id`` with ``fire_at``, the nominal fire time of this occurrence,
    identifies the occurrence. The host derives the delivery key from them, so
    a retry of the same occurrence, also after a restart, is delivered once.
    ``created_at`` is when the job was created. ``thread_id`` is the job's
    conversation thread: the thread it was created in, or
    ``scheduler_thread_id(role_id, job_id)``. ``role_config_version`` is the
    role configuration the creating turn ran with; empty means the role's
    current one. ``channel`` and ``chat_id`` are the delivery target.
    """

    job_id: str
    fire_at: datetime
    created_at: datetime
    role_id: str
    role_config_version: str
    thread_id: str
    channel: str
    chat_id: str


class ScheduleHost(Protocol):
    """Runs scheduled role work through the host's role execution boundary."""

    async def deliver(
        self, run: ScheduledRun, message: str, *, already_persisted: bool = False
    ) -> str:
        """Send ``message`` from the role to ``run``'s target.

        The send is serialised with the role's other work in the thread and
        checked against the targets the role may reach. ``already_persisted``
        tells the channel that ``run_turn`` already stored ``message`` in the
        conversation, so the delivery does not store it again. Returns the
        send result text. Raises when the target is not allowed, the channel
        is unknown or the send fails.
        """
        ...

    async def run_turn(self, run: ScheduledRun, prompt: str) -> str:
        """Run ``prompt`` as a scheduled turn of the role and return its reply.

        The prompt is not stored as a user message. The turn skips memory
        retrieval and post-turn memory work and cannot push messages or use
        memory tools. Its reply is stored in the conversation but not sent:
        pass a non-empty reply to ``deliver`` with ``already_persisted=True``.
        Returns an empty string when the turn produced no reply.
        """
        ...


SCHEDULE_HOST: Key[ScheduleHost] = Key("schedule_host")
"""Scheduled role turns and deliveries. The host provides this."""
