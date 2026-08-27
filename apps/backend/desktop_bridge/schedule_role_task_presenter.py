from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo


def serialize_schedule_role_task(job: Any, *, running: bool) -> dict[str, object]:
    """Serializes one scheduled job for the desktop role-task UI."""
    content = job.message or job.prompt or ""
    return {
        "id": job.id,
        "role_id": job.role_id,
        "kind": "schedule",
        "status": "running" if running else "scheduled",
        "label": job.name or job.id[:8],
        "detail": content,
        "created_at": job.created_at.isoformat(),
        "next_run_at": job.fire_at.isoformat(),
        "cancellable": True,
        "editable": not running,
        "schedule": {
            "tier": job.tier,
            "trigger": job.trigger,
            "when": _schedule_when(job),
            "content": content,
        },
    }


def _schedule_when(job: Any) -> str:
    if job.trigger == "at":
        try:
            return job.fire_at.astimezone(ZoneInfo(job.timezone)).strftime(
                "%Y-%m-%dT%H:%M"
            )
        except Exception:
            return job.fire_at.isoformat()
    stored = str(getattr(job, "when", "") or "").strip()
    if stored:
        return stored
    if job.trigger != "every":
        return ""
    if job.cron_expr:
        return str(job.cron_expr)
    seconds = int(job.interval_seconds or 0)
    parts: list[str] = []
    for size, suffix in ((86400, "d"), (3600, "h"), (60, "m"), (1, "s")):
        value, seconds = divmod(seconds, size)
        if value:
            parts.append(f"{value}{suffix}")
    return "".join(parts)
