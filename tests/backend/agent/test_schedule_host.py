"""``SCHEDULE_HOST`` runs a due occurrence and delivers it under its own key.

The schedule plugin's own tests drive its scheduler against a fake port;
these drive the host's port directly.
"""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from shiori_sdk.core.schedule_host import ScheduledRun, scheduler_thread_id

from agent.schedule_host import HostScheduleRunner
from agent.tools.message_push import MessagePushTool
from tests.support.push import allow_every_role_target


class _Loop:
    """The dispatcher entry points, running each operation in place."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.turns: list[dict[str, Any]] = []

    async def process_direct(self, content: str, **kwargs: Any) -> str:
        self.turns.append({"content": content, **kwargs})
        return self.reply

    async def run_role_operation(self, metadata, operation):
        return await operation()


@pytest.mark.parametrize("tier", ["instant", "soft"])
async def test_an_occurrence_is_delivered_under_its_own_key(tier):
    fire_at = datetime(2026, 10, 30, 9, 0, tzinfo=timezone.utc)
    push = MessagePushTool(role_target_validator=allow_every_role_target)
    sender = AsyncMock(return_value=None)
    push.register_channel("desktop", text_with_metadata=sender)
    loop = _Loop(reply="今天会下雨，记得带伞")
    host = HostScheduleRunner(lambda: loop, push)
    run = ScheduledRun(
        job_id="job-1",
        fire_at=fire_at,
        created_at=fire_at,
        role_id="mira",
        role_config_version="",
        thread_id=scheduler_thread_id("mira", "job-1"),
        channel="desktop",
        chat_id="role:mira",
    )
    occurrence_key = f"scheduler:job-1:{fire_at.isoformat()}"

    if tier == "instant":
        await host.deliver(run, "喝水")
    else:
        reply = await host.run_turn(run, "看看天气")
        await host.deliver(run, reply, already_persisted=True)

    chat_id, message, delivery = sender.await_args.args
    assert sender.await_count == 1
    assert chat_id == "role:mira"
    assert delivery["delivery_key"] == occurrence_key
    # Only the soft turn already stored its reply in the conversation.
    assert delivery["already_persisted"] is (tier == "soft")
    assert message == ("喝水" if tier == "instant" else "今天会下雨，记得带伞")
    if tier == "soft":
        # The turn and its delivery share the occurrence's key.
        (turn,) = loop.turns
        assert turn["metadata"]["delivery_key"] == occurrence_key
