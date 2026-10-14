"""Candidate, publication, failure and shutdown boundaries of process resources."""

import asyncio
import pytest

from agent.plugin_host.effects import EffectScope
from agent.plugin_host.process_resources import ProcessResourceOwner


class Resource:
    def __init__(self):
        self.closed = 0
        self.close_gate: asyncio.Event | None = None

    async def close(self):
        self.closed += 1
        if self.close_gate:
            await self.close_gate.wait()


async def test_candidate_discard_preserves_active_resource_and_does_not_publish():
    owner = ProcessResourceOwner()
    first_effects, candidate_effects = EffectScope("one"), EffectScope("two")
    first = owner.for_plugin("one", "plugin", first_effects)
    resource = first.acquire("tasks-v1", Resource)
    owner.publish("one")
    candidate = owner.for_plugin("two", "plugin", candidate_effects)
    assert candidate.acquire("tasks-v1", Resource) is resource
    assert not candidate.active and first.active
    await candidate_effects.dispose_all()
    assert resource.closed == 0 and first.active
    await owner.close()
    assert resource.closed == 1


async def test_publication_preserves_resource_after_old_generation_disposal():
    owner = ProcessResourceOwner()
    old_effects, new_effects = EffectScope("old"), EffectScope("new")
    old = owner.for_plugin("old", "plugin", old_effects)
    resource = old.acquire("tasks-v1", Resource)
    owner.publish("old")
    new = owner.for_plugin("new", "plugin", new_effects)
    assert new.acquire("tasks-v1", Resource) is resource
    owner.publish("new")
    assert new.active and not old.active
    assert await old_effects.dispose_all() == []
    assert resource.closed == 0
    await new_effects.dispose_all()
    assert resource.closed == 1
    await owner.close()
    assert resource.closed == 1


async def test_removed_plugin_closes_on_publish_even_with_old_attachment_retained():
    owner = ProcessResourceOwner()
    effects = EffectScope("old")
    resource = owner.for_plugin("old", "plugin", effects).acquire("tasks-v1", Resource)
    owner.publish("old")
    owner.publish("disabled")
    await asyncio.sleep(0)
    assert resource.closed == 1
    await effects.dispose_all()
    await owner.close()
    assert resource.closed == 1


async def test_failed_new_resource_closes_and_other_plugin_contract_is_separate():
    owner = ProcessResourceOwner()
    effects_a, effects_b = EffectScope("a"), EffectScope("b")
    a = owner.for_plugin("candidate", "a", effects_a).acquire("tasks-v1", Resource)
    b = owner.for_plugin("candidate", "b", effects_b).acquire("tasks-v1", Resource)
    assert a is not b
    await effects_a.dispose_all()
    assert a.closed == 1 and b.closed == 0
    await owner.close()
    assert b.closed == 1


async def test_attachment_cleanup_failure_propagates_without_waiting_for_other_plugin():
    owner = ProcessResourceOwner()
    slow_effects, failing_effects = EffectScope("slow"), EffectScope("failing")
    slow = owner.for_plugin("old", "slow", slow_effects).acquire(
        "resource-v1", Resource
    )
    slow.close_gate = asyncio.Event()
    owner.publish("old")
    owner.publish("new")

    class Failing:
        async def close(self):
            raise ValueError("explicit cleanup failure")

    _ = owner.for_plugin("candidate", "failing", failing_effects).acquire(
        "resource-v1", Failing
    )
    errors = await asyncio.wait_for(failing_effects.dispose_all(), 1)
    assert len(errors) == 1 and errors[0].subgroup(ValueError) is not None
    slow.close_gate.set()
    await owner.close()


async def test_removed_resource_failure_is_visible_at_publication_drain():
    owner = ProcessResourceOwner()

    class Failing:
        async def close(self):
            raise ValueError("disable failure")

    _ = owner.for_plugin("old", "plugin", EffectScope("old")).acquire("v1", Failing)
    owner.publish("old")
    owner.publish("new")
    with pytest.raises(ExceptionGroup, match="资源清理"):
        await owner.drain()
    await owner.close()


async def test_attachment_is_inactive_as_soon_as_effect_cleanup_starts():
    owner = ProcessResourceOwner()
    effects = EffectScope("generation")
    attachment = owner.for_plugin("generation", "plugin", effects)
    owner.publish("generation")
    entered, finish = asyncio.Event(), asyncio.Event()

    async def view_cleanup():
        entered.set()
        await finish.wait()

    effects.add("view-cleanup", view_cleanup)
    cleanup = asyncio.create_task(effects.dispose_all())
    await entered.wait()
    assert not attachment.active
    finish.set()
    await cleanup
    await owner.close()
