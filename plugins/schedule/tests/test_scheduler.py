"""A due job runs through ``SCHEDULE_HOST`` as its occurrence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from shiori_sdk.core.schedule_host import scheduler_thread_id

from plugins.schedule.backend.scheduler import SchedulerService


@pytest.mark.parametrize("tier", ["instant", "soft"])
async def test_a_due_job_reaches_the_host_once(tmp_path: Path, host, tier):
    now = datetime(2026, 10, 30, 9, 0, tzinfo=timezone.utc)
    scheduler = SchedulerService(tmp_path / "schedules.json", _now_fn=lambda: now)
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
    scheduler.start(host, role_exists=lambda _role_id: True)
    try:
        await scheduler._tick()
        await scheduler._tick()
        await host.delivered.wait()
    finally:
        await scheduler.close()

    run, message, already_persisted = host.deliveries[0]
    assert len(host.deliveries) == 1
    assert (run.job_id, run.fire_at, run.chat_id) == (job.id, job.fire_at, "role:mira")
    assert run.thread_id == scheduler_thread_id("mira", job.id)
    # Only the soft turn already stored its reply in the conversation.
    assert already_persisted is (tier == "soft")
    assert message == ("喝水" if tier == "instant" else host.reply)
    if tier == "soft":
        assert [prompt for _run, prompt in host.turns] == ["看看天气"]
