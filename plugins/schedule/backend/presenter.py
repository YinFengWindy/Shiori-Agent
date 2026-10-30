"""Read models of scheduled jobs: the task panel's rows and ``SCHEDULER`` views."""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shiori_sdk.core.scheduler import ScheduledJobInfo

from .scheduler import ScheduledJob


def serialize_task(job: ScheduledJob, *, running: bool) -> dict[str, object]:
    """One job as the task panel shows and edits it."""
    content = job.message or job.prompt or ""
    return {
        "id": job.id,
        "role_id": job.role_id,
        "status": "running" if running else "scheduled",
        "label": job.name or job.id[:8],
        "detail": content,
        "created_at": job.created_at.isoformat(),
        "next_run_at": job.fire_at.isoformat(),
        "editable": not running,
        "schedule": {
            "tier": job.tier,
            "trigger": job.trigger,
            "when": schedule_when(job),
            "content": content,
        },
    }


def job_info(job: ScheduledJob, *, running: bool) -> ScheduledJobInfo:
    """One job as ``SCHEDULER`` consumers read it."""
    return ScheduledJobInfo(
        id=job.id,
        role_id=job.role_id,
        name=job.name or "",
        tier=job.tier,
        trigger=job.trigger,
        when=schedule_when(job),
        content=job.message or job.prompt or "",
        channel=job.channel,
        chat_id=job.chat_id,
        next_run_at=job.fire_at,
        running=running,
    )


def schedule_when(job: ScheduledJob) -> str:
    """The job's ``when`` as the form edits it.

    An ``at`` job shows its next fire time in its own timezone; jobs stored
    before ``when`` was persisted rebuild it from the interval or cron rule.
    """
    if job.trigger == "at":
        try:
            return job.fire_at.astimezone(ZoneInfo(job.timezone)).strftime(
                "%Y-%m-%dT%H:%M"
            )
        except (ValueError, ZoneInfoNotFoundError):
            return job.fire_at.isoformat()
    stored = job.when.strip()
    if stored:
        return stored
    if job.trigger != "every":
        return ""
    if job.cron_expr:
        return job.cron_expr
    seconds = int(job.interval_seconds or 0)
    parts: list[str] = []
    for size, suffix in ((86400, "d"), (3600, "h"), (60, "m"), (1, "s")):
        value, seconds = divmod(seconds, size)
        if value:
            parts.append(f"{value}{suffix}")
    return "".join(parts)
