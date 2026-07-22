from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

from bootstrap.proactive import build_proactive_runtime
from agent.core.proactive_turn.gates import (
    ProactiveGateAdapter,
    ProactiveGateContext,
    ProactiveGateDecision,
)
from proactive_v2.config import ProactiveConfig


def test_build_proactive_runtime_isolates_role_policy_and_state(tmp_path, monkeypatch):
    created: list[dict[str, Any]] = []

    class FakeLoop:
        def __init__(self, **kwargs):
            self.config = kwargs["config"]
            self.state_store = kwargs["state_store"]
            created.append(kwargs)

        def run(self):
            return f"run:{self.config.default_role_id}"

    roles = [
        SimpleNamespace(
            id="mira",
            proactive=SimpleNamespace(
                enabled=True,
                target_channel="telegram",
                target_chat_id="1",
                profile="daily",
                overrides={},
                agent={"model": "mira-model", "max_steps": 11},
                drift={"enabled": False},
            ),
        ),
        SimpleNamespace(
            id="luna",
            proactive=SimpleNamespace(
                enabled=True,
                target_channel="qq",
                target_chat_id="2",
                profile="quiet",
                overrides={},
                agent={"model": "luna-model", "max_steps": 22},
                drift={"enabled": True, "min_interval_hours": 7},
            ),
        ),
    ]
    monkeypatch.setattr(
        "bootstrap.proactive.RoleStore",
        lambda _workspace: SimpleNamespace(list_roles=lambda: roles),
    )
    monkeypatch.setattr("bootstrap.proactive.ProactiveLoop", FakeLoop)
    monkeypatch.setattr(
        "bootstrap.proactive.ProactiveStateStore",
        lambda path: SimpleNamespace(db_path=path, workspace_dir=path.parent),
    )
    config = SimpleNamespace(
        proactive=ProactiveConfig(enabled=True),
        model="main-model",
        max_tokens=128,
        light_model="light-model",
        api_key="",
    )
    event_bus = object()
    class _PassGate(ProactiveGateAdapter):
        name = "test.gate"

        def evaluate(self, ctx: ProactiveGateContext) -> ProactiveGateDecision:
            return ProactiveGateDecision.continue_()

    proactive_gate = _PassGate()

    tasks, loops = build_proactive_runtime(
        cast(Any, config),
        tmp_path,
        session_manager=MagicMock(),
        provider=MagicMock(),
        light_provider=None,
        push_tool=MagicMock(),
        memory_store=None,
        presence=MagicMock(),
        agent_loop=cast(
            Any,
            SimpleNamespace(
                processing_state=None,
                role_world_registry=MagicMock(),
            ),
        ),
        proactive_gates=[proactive_gate],
        event_bus=event_bus,
    )

    assert tasks == ["run:mira", "run:luna"]
    assert set(loops) == {"mira", "luna"}
    assert loops["mira"].config.agent_tick_model == "mira-model"
    assert loops["mira"].config.tick_interval_s0 == 480
    assert loops["luna"].config.agent_tick_model == "luna-model"
    assert loops["luna"].config.tick_interval_s0 == 1800
    assert loops["luna"].config.drift_enabled is True
    assert loops["luna"].config.drift_min_interval_hours == 7
    assert created[0]["state_store"].db_path == tmp_path / "roles" / "mira" / "proactive.db"
    assert created[1]["state_store"].db_path == tmp_path / "roles" / "luna" / "proactive.db"
    assert created[0]["event_bus"] is event_bus
    assert created[1]["event_bus"] is event_bus
    assert created[0]["proactive_gates"] == [proactive_gate]
    assert created[1]["proactive_gates"] == [proactive_gate]

