import asyncio
from unittest.mock import AsyncMock

import pytest

from bus.event_bus import EventBus
from bus.events_lifecycle import ProactiveMessageCommitted
from shiori_sdk.role_events import SceneObservationCommitted
from core.roles.store import RoleStore
from core.scene.controller import SceneAwarenessController
from core.scene.contracts import SceneDecision
from core.scene.service import SceneObservationService
from core.scene.state import SceneStateStore
from session.manager import SessionManager


def _service(tmp_path, *, state=None, decision=None, needed=True):
    roles = RoleStore(tmp_path)
    if roles.get_role("mira") is None:
        roles.create_role(role_id="mira", name="Mira", system_prompt="粉发少女")
    sessions = SessionManager(tmp_path)
    bus = EventBus()
    decide = decision or AsyncMock(
        return_value=SceneDecision("started", "rain", "umbrella", "少女撑伞站在雨夜里")
    )
    controller = SceneAwarenessController(
        role_store=roles,
        session_manager=sessions,
        event_bus=bus,
        kv_store=state or SceneStateStore(tmp_path),
        light_provider=object(),
        light_model="mock",
        decision_provider=decide,
        needs_observation=lambda _: needed,
    )
    return SceneObservationService(controller, bus), bus, decide


def _event(text="少女站在雨夜里"):
    return ProactiveMessageCommitted(
        session_key="role:mira",
        channel="desktop",
        role_id="mira",
        assistant_response=text,
        thread_id="thread:mira:desktop",
    )


@pytest.mark.asyncio
async def test_prepare_and_discard_are_inert_and_publication_is_idempotent(tmp_path):
    service, bus, model = _service(tmp_path)
    await bus.fanout(_event())
    model.assert_not_awaited()
    assert not service.controller.state.path.exists()
    service.activate()
    service.activate()
    await bus.fanout(_event())
    await asyncio.gather(*service.controller.tasks.values())
    model.assert_awaited_once()
    await service.close()
    await bus.fanout(_event())
    model.assert_awaited_once()
    candidate, bus, model = _service(tmp_path)
    await candidate.close()
    model.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_demand_does_not_start_model_or_write_scene_state(tmp_path):
    service, bus, model = _service(tmp_path, needed=False)
    service.activate()
    await bus.fanout(_event())
    assert not service.controller.tasks
    model.assert_not_awaited()
    assert not service.controller.state.path.exists()
    await service.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("newer_finishes_first", [False, True])
async def test_old_accepted_observation_finishes_across_preparation_and_publication(
    tmp_path, newer_finishes_first
):
    entered, finish = asyncio.Event(), asyncio.Event()

    async def old_decide(*args, **kwargs):
        entered.set()
        await finish.wait()
        return SceneDecision("started", "old", "old-frame", "旧场景")

    old, old_bus, _ = _service(tmp_path, decision=old_decide)
    old.activate()
    await old_bus.fanout(_event())
    await entered.wait()
    new, new_bus, _ = _service(tmp_path, state=old.controller.state)
    observations = []
    old_bus.on(SceneObservationCommitted, observations.append)
    new_bus.on(SceneObservationCommitted, observations.append)
    if newer_finishes_first:
        old.deactivate()
        new.activate()
        await new_bus.fanout(_event("新的场景"))
        await asyncio.gather(*new.controller.tasks.values())
    finish.set()
    await asyncio.gather(*old.controller.tasks.values())
    if not newer_finishes_first:
        old.deactivate()
        new.activate()
    assert [event.scene_key for event in observations] == (
        ["rain"] if newer_finishes_first else ["old"]
    )
    assert (
        new.controller.state.current("role:mira")["scene_key"]
        == observations[-1].scene_key
    )
    await old.close()
    await new.close()


@pytest.mark.asyncio
async def test_close_detaches_before_waiting_for_cancelled_displaced_tasks(tmp_path):
    cancelled, finish = asyncio.Event(), asyncio.Event()

    async def decide(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            await finish.wait()
            raise

    service, bus, _ = _service(tmp_path, decision=decide)
    service.activate()
    await bus.fanout(_event())
    await asyncio.sleep(0)
    closing = asyncio.create_task(service.close())
    await cancelled.wait()
    await bus.fanout(_event("不应进入"))
    assert len(service.controller.tasks) == 1
    finish.set()
    await closing
    assert not service.controller.tasks
