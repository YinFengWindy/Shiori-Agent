from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agent.core.proactive_turn.gates import (
    ProactiveGateChain,
    ProactiveGateCompletion,
    ProactiveGateContext,
    ProactiveMode,
)
from agent.plugins.context import PluginContext, PluginKVStore
from bus.event_bus import EventBus
from bus.events_lifecycle import SceneObservationCommitted
from plugins.relationship_proactive.plugin import RelationshipProactivePlugin


def _context() -> ProactiveGateContext:
    return ProactiveGateContext(
        tick_id="tick",
        session_key="role:mira",
        now_utc=datetime.now(timezone.utc),
        target_transports=(("desktop", "role:mira"),),
    )


def test_scene_gate_claims_tick_and_advances_only_after_delivery(tmp_path: Path):
    runtime = MagicMock()
    runtime.should_trigger_scene_followup.return_value = (
        True,
        {"attempt_index": 1},
    )
    plugin = RelationshipProactivePlugin()
    plugin.context = PluginContext(
        event_bus=EventBus(),
        tool_registry=None,
        plugin_id="relationship_proactive",
        plugin_dir=tmp_path,
        kv_store=PluginKVStore(tmp_path / ".kv.json"),
        relationship_runtime=runtime,
    )
    chain = ProactiveGateChain(plugin.proactive_gates())

    result = chain.evaluate(_context())

    assert result.activation is not None
    assert result.activation.mode == ProactiveMode.SCENE_FOLLOWUP
    runtime.should_trigger_proactive.assert_not_called()
    chain.finalize(
        ProactiveGateCompletion(
            activation=result.activation,
            session_key="role:mira",
            occurred_at=datetime.now(timezone.utc),
            outcome="delivered",
        )
    )
    runtime.handle_scene_followup_sent.assert_called_once()
    runtime.close_scene_followup.assert_not_called()


def test_loneliness_gate_blocks_when_relationship_runtime_rejects(tmp_path: Path):
    runtime = MagicMock()
    runtime.should_trigger_scene_followup.return_value = (False, {})
    runtime.should_trigger_proactive.return_value = (False, {"reason": "below_threshold"})
    plugin = RelationshipProactivePlugin()
    plugin.context = PluginContext(
        event_bus=EventBus(),
        tool_registry=None,
        plugin_id="relationship_proactive",
        plugin_dir=tmp_path,
        kv_store=PluginKVStore(tmp_path / ".kv.json"),
        relationship_runtime=runtime,
    )

    result = ProactiveGateChain(plugin.proactive_gates()).evaluate(_context())

    assert result.blocked is True
    assert result.reason == "loneliness"


@pytest.mark.asyncio
async def test_plugin_applies_shared_scene_observation(tmp_path: Path):
    runtime = MagicMock()
    bus = EventBus()
    plugin = RelationshipProactivePlugin()
    plugin.context = PluginContext(
        event_bus=bus,
        tool_registry=None,
        plugin_id="relationship_proactive",
        plugin_dir=tmp_path,
        kv_store=PluginKVStore(tmp_path / ".kv.json"),
        relationship_runtime=runtime,
    )
    await plugin.initialize()

    await bus.fanout(
        SceneObservationCommitted(
            session_key="role:mira",
            channel="desktop",
            chat_id="role:mira",
            role_id="mira",
            source="passive",
            transition="started",
            scene_key="rain",
            should_generate=True,
            prompt="1girl, rain",
        )
    )

    runtime.apply_scene_decision.assert_called_once_with(
        "role:mira",
        "started",
        "rain",
    )
    await plugin.terminate()
