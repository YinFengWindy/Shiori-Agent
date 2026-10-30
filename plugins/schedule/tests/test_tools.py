"""Schedule tools take the job owner from the turn, never from the model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shiori_sdk.tools import Tool

from plugins.schedule.backend.scheduler import SchedulerService
from plugins.schedule.backend.tools import CancelScheduleTool, ScheduleTool

_TURN = {
    "role_id": "mira",
    "role_config_version": "v1",
    "thread_id": "thread:mira:desktop",
    "delivery_key": "turn-1",
}


async def _call(tool: Tool, arguments: dict[str, Any]) -> object:
    """Runs ``tool`` as the host does: its ``context_precedence`` keys come
    only from the turn, whatever the model passed."""
    merged = {**_TURN, **arguments}
    for key in tool.context_precedence:
        merged[key] = _TURN[key]
    return await tool.execute(**merged)


async def test_model_arguments_cannot_reassign_a_new_job(tmp_path: Path):
    scheduler = SchedulerService(tmp_path / "schedules.json")

    await _call(
        ScheduleTool(scheduler),
        {
            "tier": "instant",
            "trigger": "after",
            "when": "5m",
            "message": "喝水",
            "channel": "desktop",
            "chat_id": "role:mira",
            "role_id": "yin",
            "role_config_version": "forged",
            "thread_id": "thread:yin:desktop",
            "delivery_key": "forged",
        },
    )

    (job,) = scheduler.list_jobs()
    assert (job.role_id, job.role_config_version, job.thread_id, job.delivery_key) == (
        "mira",
        "v1",
        "thread:mira:desktop",
        "turn-1",
    )


async def test_model_arguments_cannot_cancel_another_roles_job(tmp_path: Path):
    scheduler = SchedulerService(tmp_path / "schedules.json")
    job = scheduler.create_job(
        name="提醒",
        tier="instant",
        trigger="after",
        when="5m",
        content="喝水",
        timezone_name="UTC",
        channel="desktop",
        chat_id="role:yin",
        role_id="yin",
    )

    await _call(CancelScheduleTool(scheduler), {"id": job.id, "role_id": "yin"})

    assert scheduler.list_jobs() == [job]
