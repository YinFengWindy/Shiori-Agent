"""Due scheduled jobs reach the channel through ``SCHEDULE_HOST``."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

from agent.schedule_host import HostScheduleRunner
from agent.scheduler import SchedulerService
from agent.tools.message_push import MessagePushTool
from shiori_sdk.core.schedule_host import scheduler_thread_id
from tests.support.push import allow_every_role_target


class _Loop:
    """The dispatcher entry points, running each operation in place."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.turns: list[dict[str, Any]] = []
        self.operations: list[dict[str, str]] = []

    async def process_direct(self, content: str, **kwargs: Any) -> str:
        self.turns.append({"content": content, **kwargs})
        return self.reply

    async def run_role_operation(self, metadata, operation):
        self.operations.append(dict(metadata))
        return await operation()


@pytest.mark.parametrize("tier", ["instant", "soft"])
async def test_due_job_is_delivered_once_per_occurrence_through_the_port(
    tmp_path, tier
):
    now = datetime(2026, 10, 30, 9, 0, tzinfo=timezone.utc)
    push = MessagePushTool(role_target_validator=allow_every_role_target)
    sender = AsyncMock(return_value=None)
    push.register_channel("desktop", text_with_metadata=sender)
    loop = _Loop(reply="今天会下雨，记得带伞")
    scheduler = SchedulerService(
        tmp_path / "schedules.json",
        host=HostScheduleRunner(lambda: loop, push),
        _now_fn=lambda: now,
    )
    job = scheduler.create_job(
        name="提醒",
        tier=tier,
        trigger="at",
        when=(now - timedelta(seconds=1)).isoformat(),
        content="喝水" if tier == "instant" else "看看天气",
        timezone_name="UTC",
        channel="desktop",
        chat_id="role:mira",
        role_id="mira",
    )
    occurrence_key = f"scheduler:{job.id}:{job.fire_at.isoformat()}"

    await scheduler._tick()
    await asyncio.gather(*scheduler._active_tasks.values())

    chat_id, message, delivery = sender.await_args.args
    assert sender.await_count == 1
    assert chat_id == "role:mira"
    assert delivery["delivery_key"] == occurrence_key
    # Only the soft turn already stored its reply in the conversation.
    assert delivery["already_persisted"] is (tier == "soft")
    assert message == ("喝水" if tier == "instant" else "今天会下雨，记得带伞")
    (operation,) = loop.operations
    assert operation["thread_id"] == scheduler_thread_id("mira", job.id)
    assert operation["role_work_kind"] == "scheduled_job"
    if tier == "soft":
        (turn,) = loop.turns
        assert turn["content"] == "看看天气"
        assert turn["metadata"]["delivery_key"] == occurrence_key
        assert "message_push" in turn["disabled_tools"]
    else:
        assert loop.turns == []
