from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.looping.core import AgentLoop
from agent.looping.ports import AgentLoopConfig, AgentLoopDeps, MemoryServices
from agent.provider import LLMResponse
from agent.scheduler import JobStore, SchedulerService
from agent.tools.message_push import MessagePushTool
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
from bus.queue import MessageBus
from core.roles import RoleRepository, RoleRuntimeRegistry, RoleStore
from core.roles.model_runtime import RoleModelRuntime, RoleModelSnapshot
from desktop_bridge import DesktopBridgeService
from session.manager import SessionManager
from tests.support.scheduler import make_job


def test_job_store_raises_for_invalid_json(tmp_path: Path):
    path = tmp_path / "jobs.json"
    path.write_text("[broken", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        JobStore(path).load()


def test_job_store_raises_for_invalid_job_payload(tmp_path: Path):
    path = tmp_path / "jobs.json"
    path.write_text('[{"id": "incomplete"}]', encoding="utf-8")

    with pytest.raises((KeyError, TypeError, ValueError)):
        JobStore(path).load()


@pytest.mark.parametrize("trigger", ["at", "every"])
def test_delivery_identity_is_per_job_and_survives_job_store_reload(tmp_path, trigger):
    scheduler = SchedulerService(
        store_path=tmp_path / "jobs.json", push_tool=MagicMock()
    )
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    jobs = [make_job(trigger=trigger, fire_at=now) for _ in range(2)]
    for job in jobs:
        job.delivery_key = "shared-creating-turn"
    keys = [scheduler._job_role_metadata(job)["delivery_key"] for job in jobs]
    assert len(set(keys)) == 2
    assert "shared-creating-turn" not in keys
    scheduler.store.save({job.id: job for job in jobs})
    assert [
        scheduler._job_role_metadata(job)["delivery_key"]
        for job in scheduler.store.load()
    ] == keys


@pytest.mark.parametrize("tier", ["soft", "instant"])
async def test_recurring_desktop_delivery_persists_once_per_occurrence(tmp_path, tier):
    role_store = RoleStore(tmp_path)
    role_store.create_role(role_id="mira", name="Mira", system_prompt="test")
    sessions = SessionManager(tmp_path)
    event_bus = EventBus()
    provider = MagicMock()
    # Passive replies are plain content now (#303): no JSON envelope. A
    # follow-up mood/thought call still fires for this role-backed session,
    # but its own malformed reply degrades quietly and must not affect the
    # delivered content asserted below.
    provider.chat = AsyncMock(
        return_value=LLMResponse(
            content="scheduled reply",
            tool_calls=[],
        )
    )
    memory = MagicMock()
    memory.read_self.return_value = ""
    memory.read_recent_context.return_value = ""
    memory.get_memory_context.return_value = ""
    memory.has_long_term_memory.return_value = False
    model_runtime = RoleModelRuntime(role_store=role_store, registrations=[])
    model_runtime.resolve = MagicMock(
        return_value=RoleModelSnapshot(
            registration_id="test",
            provider=provider,
            model="test",
            effort="none",
            role_id="mira",
        )
    )
    loop = AgentLoop(
        AgentLoopDeps(
            bus=MessageBus(),
            provider=provider,
            tools=ToolRegistry(),
            session_manager=sessions,
            workspace=tmp_path,
            event_bus=event_bus,
            memory_services=MemoryServices(engine=memory),
            role_runtime_registry=RoleRuntimeRegistry(
                RoleRepository(role_store), model_resolver=model_runtime
            ),
        ),
        AgentLoopConfig(),
    )
    push = MessagePushTool()
    bridge = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=sessions,
        agent_loop=loop,
        event_bus=event_bus,
        push_tool=push,
    )
    emitted = []
    bridge.add_event_listener(emitted.append)
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    scheduler = SchedulerService(
        store_path=tmp_path / "jobs.json",
        push_tool=push,
        agent_loop=loop,
        _now_fn=lambda: now,
    )
    job = make_job(
        tier=tier,
        trigger="every",
        interval_seconds=60,
        fire_at=now,
        channel="desktop",
        chat_id="role:mira",
        message="scheduled reply",
        prompt="Send the scheduled reply",
    )
    scheduler._jobs[job.id] = job
    delivery_keys = []
    for occurrence in range(2):
        delivery_key = scheduler._job_role_metadata(job)["delivery_key"]
        delivery_keys.append(delivery_key)
        await scheduler._tick()
        await asyncio.gather(*scheduler._active_tasks.values())
        persisted = SessionManager(tmp_path).get_or_create("role:mira").messages
        assert len(persisted) == occurrence + 1
        assert [item["content"] for item in persisted] == ["scheduled reply"] * (
            occurrence + 1
        )
        assert persisted[-1]["metadata"]["delivery_key"] == delivery_key
        assert emitted[-1]["method"] == "session.updated"
        now = job.fire_at + timedelta(seconds=1)

    assert delivery_keys[0] != delivery_keys[1]
    assert [item["seq"] for item in persisted] == [0, 1]
    # Replay the first delivery after a later occurrence: it is no longer last.
    for _ in range(2):
        result = await push.execute(
            channel="desktop",
            chat_id="role:mira",
            message="scheduled reply",
            push_delivery_key=delivery_keys[0],
            push_message_already_persisted=tier == "soft",
        )
        assert "已发送" in result
    assert len(SessionManager(tmp_path).get_or_create("role:mira").messages) == 2
    if tier == "soft":
        # One passive turn per occurrence, each now making two calls: the
        # plain-content reply plus its separate mood/thought follow-up (#303).
        assert provider.chat.await_count == 4
    else:
        provider.chat.assert_not_awaited()
    await bridge.aclose()
