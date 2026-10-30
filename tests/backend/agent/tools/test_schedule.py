"""Schedule tools take the job owner from the turn, never from the model."""

from typing import Any, cast

from agent.scheduler import SchedulerService
from agent.tools.registry import ToolRegistry
from agent.tools.schedule import CancelScheduleTool, ScheduleTool

_TURN = {
    "role_id": "mira",
    "role_config_version": "v1",
    "thread_id": "thread:mira:desktop",
    "delivery_key": "turn-1",
}


def _registry(tmp_path) -> tuple[ToolRegistry, SchedulerService]:
    scheduler = SchedulerService(tmp_path / "schedules.json", host=cast(Any, None))
    registry = ToolRegistry()
    registry.register(ScheduleTool(scheduler))
    registry.register(CancelScheduleTool(scheduler))
    return registry, scheduler


async def test_model_arguments_cannot_reassign_a_new_job(tmp_path):
    registry, scheduler = _registry(tmp_path)

    await registry.execute(
        "schedule",
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
        context=_TURN,
    )

    (job,) = scheduler.list_jobs()
    assert (job.role_id, job.role_config_version, job.thread_id, job.delivery_key) == (
        "mira",
        "v1",
        "thread:mira:desktop",
        "turn-1",
    )


async def test_model_arguments_cannot_cancel_another_roles_job(tmp_path):
    registry, scheduler = _registry(tmp_path)
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

    await registry.execute(
        "cancel_schedule", {"id": job.id, "role_id": "yin"}, context=_TURN
    )

    assert scheduler.list_jobs() == [job]
