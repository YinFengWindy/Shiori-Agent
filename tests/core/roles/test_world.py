from __future__ import annotations

import asyncio

import pytest

from core.roles.services import RoleRepository
from core.roles.store import RoleStore
from core.roles.world import RoleExecutionContext, RoleWorldRegistry


def _context(role, *, thread_id: str = "thread:mira:desktop"):
    return RoleExecutionContext.create(
        role=role,
        thread_id=thread_id,
        transport_channel="desktop",
        transport_chat_id="self",
        source="test",
        work_kind="passive_turn",
        request_id="request-1",
        delivery_key="delivery-1",
    )


@pytest.mark.asyncio
async def test_registry_serializes_work_in_the_same_thread(tmp_path):
    repository = RoleRepository(RoleStore(tmp_path))
    role = repository.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="test",
    )
    registry = RoleWorldRegistry(repository)
    context = _context(role)
    events: list[str] = []
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    async def first() -> str:
        events.append("first:start")
        first_started.set()
        await release_first.wait()
        events.append("first:end")
        return "first"

    async def second() -> str:
        events.append("second")
        return "second"

    first_task = asyncio.create_task(registry.dispatch_thread(context, first))
    await first_started.wait()
    second_task = asyncio.create_task(registry.dispatch_thread(context, second))
    await asyncio.sleep(0)
    assert events == ["first:start"]

    release_first.set()
    assert await first_task == "first"
    assert await second_task == "second"
    assert events == ["first:start", "first:end", "second"]


@pytest.mark.asyncio
async def test_registry_allows_different_roles_to_execute_independently(tmp_path):
    repository = RoleRepository(RoleStore(tmp_path))
    mira = repository.create_role(role_id="mira", name="Mira", system_prompt="test")
    shiori = repository.create_role(
        role_id="shiori",
        name="Shiori",
        system_prompt="test",
    )
    registry = RoleWorldRegistry(repository)
    mira_started = asyncio.Event()
    shiori_started = asyncio.Event()
    release = asyncio.Event()

    async def wait_for(started: asyncio.Event) -> None:
        started.set()
        await release.wait()

    mira_task = asyncio.create_task(
        registry.dispatch_thread(_context(mira), lambda: wait_for(mira_started))
    )
    shiori_task = asyncio.create_task(
        registry.dispatch_thread(_context(shiori), lambda: wait_for(shiori_started))
    )
    await asyncio.wait_for(asyncio.gather(mira_started.wait(), shiori_started.wait()), 0.2)
    release.set()
    await asyncio.gather(mira_task, shiori_task)


@pytest.mark.asyncio
async def test_registry_rejects_context_after_role_configuration_changes(tmp_path):
    repository = RoleRepository(RoleStore(tmp_path))
    role = repository.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="test",
    )
    registry = RoleWorldRegistry(repository)
    context = _context(role)
    _ = await registry.get(role.id)
    _ = repository.update_role(role.id, description="updated")

    with pytest.raises(RuntimeError, match="角色配置已过期"):
        await registry.dispatch_thread(context, lambda: _return_none())


async def _return_none() -> None:
    return None
