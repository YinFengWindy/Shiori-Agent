"""The plugin's setup: one process scheduler, role cleanup and the task block's RPC."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import pytest
from shiori_sdk.core.schedule_host import SCHEDULE_HOST
from shiori_sdk.core.scheduler import SCHEDULER, ScheduleRequest
from shiori_sdk.core.services import PROCESS_RESOURCES
from shiori_sdk.role_events import RoleDeleted
from shiori_sdk.rpc import Concurrency
from shiori_sdk.testing.process_resources import FakeProcessResources
from shiori_sdk.testing.service_context import FakeServiceContext

from plugins.schedule.backend.plugin import setup
from plugins.schedule.backend.scheduler import SchedulerService

PACKAGE_DIR = Path(__file__).resolve().parents[1]


def _context(workspace: Path, host, resources=None) -> FakeServiceContext:
    """One generation of the plugin; ``resources`` stands for the process."""
    ctx = FakeServiceContext("schedule", workspace, package_dir=PACKAGE_DIR)
    ctx.serve(SCHEDULE_HOST, host)
    if resources is not None:
        ctx.serve(PROCESS_RESOURCES, resources)
    for role_id in ("mira", "yin"):
        ctx.fake_roles.create_role(role_id=role_id, name=role_id, system_prompt="")
    return ctx


def _tickers() -> list[asyncio.Task[object]]:
    return [
        task
        for task in asyncio.all_tasks()
        if task.get_name() == "schedule:tick" and not task.done()
    ]


def _store(workspace: Path) -> list[dict[str, object]]:
    return json.loads((workspace / "schedules.json").read_text(encoding="utf-8"))


def _seed_job(workspace: Path, *, role_id: str, tier: str, when: str) -> str:
    """Writes one job to ``schedules.json`` the way an earlier run left it."""
    job = SchedulerService(workspace / "schedules.json").create_job(
        name="提醒",
        tier=tier,
        trigger="at",
        when=when,
        content="喝水" if tier == "instant" else "看看天气",
        timezone_name="UTC",
        channel="desktop",
        chat_id=f"role:{role_id}",
        role_id=role_id,
    )
    return job.id


def _request(role_id: str) -> ScheduleRequest:
    return ScheduleRequest(
        role_id=role_id,
        name="提醒",
        tier="instant",
        trigger="after",
        when="1h",
        content="喝水",
        timezone="UTC",
        channel="desktop",
        chat_id=f"role:{role_id}",
    )


def _just_due() -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()


async def test_generations_share_one_scheduler_that_fires_a_job_once(
    tmp_path: Path, host
):
    _seed_job(tmp_path, role_id="mira", tier="instant", when=_just_due())
    process = FakeProcessResources()
    old = _context(tmp_path, host, process)
    new = _context(tmp_path, host, process)
    try:
        await setup(old)
        # A reload or new generation sets the plugin up again in the same process.
        await setup(new)
        assert len(_tickers()) == 1

        await asyncio.wait_for(host.delivered.wait(), timeout=5)
        await asyncio.sleep(0.2)
        assert [message for _run, message, _ in host.deliveries] == ["喝水"]

        # The old generation retires; the new one keeps ticking the same jobs.
        await old.aclose()
        assert len(_tickers()) == 1
        job = new.kernel.get(SCHEDULER).create_job(_request("mira"))
        assert [item.id for item in new.kernel.get(SCHEDULER).list_jobs("mira")] == [
            job.id
        ]
    finally:
        await new.aclose()
        await process.close()
    assert _tickers() == []


async def test_disabling_stops_ticking_and_cancels_the_running_job(
    tmp_path: Path, host
):
    job_id = _seed_job(tmp_path, role_id="mira", tier="soft", when=_just_due())
    host.hold = asyncio.Event()
    ctx = _context(tmp_path, host)
    await setup(ctx)
    await asyncio.wait_for(host.turn_started.wait(), timeout=5)

    await ctx.aclose()

    assert host.turn_cancelled
    assert host.deliveries == []
    assert _tickers() == []
    # The job stays stored and runs again once the plugin is back on.
    assert [job["id"] for job in _store(tmp_path)] == [job_id]


async def test_a_deleted_roles_jobs_are_cancelled(tmp_path: Path, host):
    ctx = _context(tmp_path, host)
    await setup(ctx)
    try:
        scheduler = ctx.kernel.get(SCHEDULER)
        scheduler.create_job(_request("mira"))
        kept = scheduler.create_job(_request("yin"))

        await ctx.fake_events.emit(RoleDeleted("mira"))

        assert scheduler.list_jobs("mira") == []
        assert [job["id"] for job in _store(tmp_path)] == [kept.id]
    finally:
        await ctx.aclose()


async def test_startup_drops_the_jobs_of_roles_deleted_meanwhile(tmp_path: Path, host):
    _seed_job(tmp_path, role_id="ghost", tier="instant", when="2099-01-01T09:00")
    kept = _seed_job(tmp_path, role_id="mira", tier="instant", when="2099-01-01T09:00")
    ctx = _context(tmp_path, host)
    await setup(ctx)
    try:
        assert [job["id"] for job in _store(tmp_path)] == [kept]
    finally:
        await ctx.aclose()


async def test_the_task_block_creates_edits_and_cancels_a_roles_job(
    tmp_path: Path, host
):
    ctx = _context(tmp_path, host)
    await setup(ctx)
    rpc = ctx.fake_rpc
    form = {"name": "喝水", "tier": "instant", "trigger": "after", "when": "30m"}
    try:
        # Reading and cancelling answer while a reload pauses admission, as
        # the core's role task methods did.
        assert rpc.concurrency["list"] is Concurrency.READ_ONLY
        assert {name for name, exempt in rpc.admission_exempt.items() if exempt} == {
            "list",
            "cancel",
        }
        created = await rpc.handlers["create"](
            {"role_id": "mira", **form, "content": "记得喝水"}
        )
        task = created["task"]
        assert isinstance(task, dict)
        task_id = task["id"]
        (job,) = _store(tmp_path)
        # Desktop jobs go to the role's desktop chat.
        assert (job["role_id"], job["channel"], job["chat_id"]) == (
            "mira",
            "desktop",
            "role:mira",
        )

        await rpc.handlers["update"](
            {"role_id": "mira", "task_id": task_id, **form, "content": "喝杯温水"}
        )
        listed = await rpc.handlers["list"]({"role_id": "mira"})
        tasks = cast(list[dict[str, object]], listed["tasks"])
        assert [(item["id"], item["detail"]) for item in tasks] == [
            (task_id, "喝杯温水")
        ]
        assert (await rpc.handlers["list"]({"role_id": "yin"}))["tasks"] == []
        with pytest.raises(KeyError):
            await rpc.handlers["cancel"]({"role_id": "yin", "task_id": task_id})
        with pytest.raises(ValueError, match="role not found"):
            await rpc.handlers["list"]({"role_id": "ghost"})

        assert await rpc.handlers["cancel"](
            {"role_id": "mira", "task_id": task_id}
        ) == {"tasks": []}
        assert _store(tmp_path) == []
        await asyncio.sleep(0)
        assert rpc.events == [("tasks.changed", {"role_id": "mira"})] * 3
    finally:
        await ctx.aclose()
