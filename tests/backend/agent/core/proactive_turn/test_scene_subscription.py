"""Generation publication and disposal own scene-event handling."""

from unittest.mock import MagicMock
import pytest
from bus.event_bus import EventBus
from shiori_sdk.role_events import SceneObservationCommitted
from agent.core.proactive_turn.scene_subscription import SceneFollowupSubscription


def _event():
    return SceneObservationCommitted(
        session_key="role:mira",
        channel="desktop",
        chat_id="role:mira",
        role_id="mira",
        source="passive",
        transition="started",
        scene_key="rain",
        visual_description="雨夜车站的少女",
    )


@pytest.mark.asyncio
async def test_prepare_is_inert_start_idempotent_and_stop_detaches():
    runtime = MagicMock()
    bus = EventBus()
    subscription = SceneFollowupSubscription(bus, runtime)
    await bus.fanout(_event())
    runtime.apply_scene_decision.assert_not_called()
    subscription.start()
    subscription.start()
    await bus.fanout(_event())
    runtime.apply_scene_decision.assert_called_once_with("role:mira", "started", "rain")
    subscription.stop()
    subscription.stop()
    await bus.fanout(_event())
    runtime.apply_scene_decision.assert_called_once()


@pytest.mark.asyncio
async def test_new_generation_does_not_consume_old_bus_or_failed_candidate_events():
    runtime = MagicMock()
    old_bus, new_bus = EventBus(), EventBus()
    old = SceneFollowupSubscription(old_bus, runtime)
    candidate = SceneFollowupSubscription(new_bus, runtime)
    old.start()
    candidate.stop()
    await new_bus.fanout(_event())
    runtime.apply_scene_decision.assert_not_called()
    candidate.start()
    await old_bus.fanout(_event())
    await new_bus.fanout(_event())
    assert runtime.apply_scene_decision.call_count == 2
    old.stop()
    await old_bus.fanout(_event())
    assert runtime.apply_scene_decision.call_count == 2
    candidate.stop()
