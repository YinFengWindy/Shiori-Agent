"""``SCHEDULER``: roles' scheduled jobs (P6s, D17).

The ``schedule`` plugin provides this key; the host never does. A consumer
declares it in ``optional_inject``, ``get``s it on every use and does without
scheduling when it is ``None`` (the plugin is off). Jobs persist in
``<workspace>/schedules.json``; this key does not change that file. Due jobs
run through ``SCHEDULE_HOST`` (``shiori_sdk.core.schedule_host``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from shiori_sdk.kernel import Key


@dataclass(frozen=True, kw_only=True)
class ScheduleRequest:
    """A new job of one role.

    ``tier`` is ``"instant"`` (send ``content`` as is) or ``"soft"`` (run
    ``content`` as a scheduled turn of the role and send its reply).
    ``trigger`` is ``"at"`` (``when`` is ``HH:MM`` or an ISO time),
    ``"after"`` (a duration such as ``30m`` or ``1h30m``) or ``"every"`` (a
    duration or a five- or six-field cron expression). ``timezone`` is an IANA
    name that ``when`` is read in. ``channel`` and ``chat_id`` are the
    delivery target. ``thread_id`` is the conversation thread the job belongs
    to; empty gives the job its own thread
    (``scheduler_thread_id(role_id, job_id)``).
    """

    role_id: str
    name: str
    tier: str
    trigger: str
    when: str
    content: str
    timezone: str
    channel: str
    chat_id: str
    thread_id: str = ""


@dataclass(frozen=True, kw_only=True)
class ScheduledJobInfo:
    """One pending job as stored.

    ``next_run_at`` is the next nominal fire time (timezone-aware).
    ``running`` tells whether the job is executing right now.
    """

    id: str
    role_id: str
    name: str
    tier: str
    trigger: str
    when: str
    content: str
    channel: str
    chat_id: str
    next_run_at: datetime
    running: bool


class Scheduler(Protocol):
    """Create, list and cancel a role's scheduled jobs."""

    def create_job(self, request: ScheduleRequest) -> ScheduledJobInfo:
        """Validate and persist a new job, then schedule it.

        Raises ``ValueError`` for an unknown tier or trigger, an unparsable
        ``when``, an unknown timezone or an empty name, content or target.
        """
        ...

    def list_jobs(self, role_id: str) -> list[ScheduledJobInfo]:
        """The role's pending jobs."""
        ...

    def cancel_job(self, role_id: str, job_id: str) -> bool:
        """Remove the role's job and stop it if it is running.

        Returns ``False`` when the role has no job with that id.
        """
        ...


SCHEDULER: Key[Scheduler] = Key("scheduler")
"""Roles' scheduled jobs. The schedule plugin provides this; the host never does."""
