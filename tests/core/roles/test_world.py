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
async def test_registry_serializes_different_transport_threads_for_one_role(tmp_path):
    repository = RoleRepository(RoleStore(tmp_path))
    role = repository.create_role(role_id="mira", name="Mira", system_prompt="test")
    registry = RoleWorldRegistry(repository)
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

    first_task = asyncio.create_task(
        registry.dispatch_thread(
            _context(role, thread_id="thread:mira:telegram:1"),
            first,
        )
    )
    await first_started.wait()
    second_task = asyncio.create_task(
        registry.dispatch_thread(
            _context(role, thread_id="thread:mira:qq:2"),
            second,
        )
    )
    await asyncio.sleep(0)
    assert events == ["first:start"]

    release_first.set()
    await asyncio.gather(first_task, second_task)
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
async def test_role_capabilities_reject_the_wrong_work_kind(tmp_path):
    repository = RoleRepository(RoleStore(tmp_path))
    role = repository.create_role(role_id="mira", name="Mira", system_prompt="test")
    registry = RoleWorldRegistry(repository)

    with pytest.raises(ValueError, match="不接受工作类型"):
        await registry.dispatch_proactive_tick(_context(role), _return_none)


@pytest.mark.asyncio
async def test_registry_refreshes_configuration_without_replacing_the_world(tmp_path):
    repository = RoleRepository(RoleStore(tmp_path))
    role = repository.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="test",
    )
    registry = RoleWorldRegistry(repository)
    context = _context(role)
    first_world = await registry.get(role.id)
    updated = repository.update_role(role.id, description="updated")
    refreshed_world = await registry.get(role.id)

    assert refreshed_world is first_world
    assert refreshed_world.config_version != context.role_config_version
    await registry.dispatch_thread(context, lambda: _return_none())
    assert refreshed_world.config_version == RoleExecutionContext.create(
        role=updated,
        thread_id=context.thread_id,
        transport_channel=context.transport_channel,
        transport_chat_id=context.transport_chat_id,
        source=context.source,
        work_kind=context.work_kind,
    ).role_config_version


async def _return_none() -> None:
    return None


def test_registry_builds_direct_context_from_authoritative_role(tmp_path):
    repository = RoleRepository(RoleStore(tmp_path))
    role = repository.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="test",
    )
    registry = RoleWorldRegistry(repository)

    context = registry.create_context(
        role_id=role.id,
        thread_id="thread:mira:desktop",
        transport_channel="desktop",
        transport_chat_id="role:mira",
        source="desktop",
        work_kind="passive_turn",
    )

    assert context.role_id == "mira"
    assert context.thread_id == "thread:mira:desktop"
    assert context.role_config_version
