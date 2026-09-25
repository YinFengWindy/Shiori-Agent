from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

from agent.config_models import Config
from bootstrap.proactive import (
    build_memory_optimizer_task,
    build_proactive_runtime,
    _build_role_prompt_resolver,
)
from core.roles import RoleStore
from agent.core.proactive_turn.gates import (
    ProactiveGateAdapter,
    ProactiveGateContext,
    ProactiveGateDecision,
)
from proactive_v2.config import ProactiveConfig


def test_proactive_role_prompt_compiles_current_profile_and_always_active_knowledge(
    tmp_path,
):
    store = RoleStore(tmp_path)
    store.create_role(
        name="Mira",
        role_id="mira",
        system_prompt="过时的规则",
        runtime_config={"mood_catalog": ["平静"]},
        profile={
            "character": {
                "profile": "{{char}}的资料",
                "nickname": "小栞",
                "personality": "温柔",
                "response_constraints": "简洁回应{{user}}",
            },
            "knowledge_base": {
                "enabled": True,
                "entries": [
                    {"content": "常驻知识", "always_active": True},
                    {"content": "消息关键词知识", "primary_keys": ["Mira"]},
                    {"content": "已停用知识", "enabled": False, "always_active": True},
                ],
            },
        },
    )
    resolve = _build_role_prompt_resolver(tmp_path, "mira")

    prompt = resolve()
    assert prompt.startswith("[role_identity]\nMira")
    assert "小栞的资料" in prompt and "温柔" in prompt and "简洁回应用户" in prompt
    assert "常驻知识" in prompt
    assert prompt.index("[role_knowledge]") < prompt.index(
        "[role_response_constraints]"
    )
    assert "过时的规则" not in prompt
    assert "消息关键词知识" not in prompt and "已停用知识" not in prompt
    assert "Mood Output Contract" not in prompt

    store.update_role(
        "mira",
        name="Shiori",
        profile={"character": {"response_constraints": "只回复一句"}},
    )
    updated = resolve()
    assert updated.startswith("[role_identity]\nShiori")
    assert "只回复一句" in updated
    assert "常驻知识" not in updated and "小栞" not in updated


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
                agent={"max_steps": 11},
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
                agent={"max_steps": 22},
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
    from agent.core.proactive_turn.strategies import RelationshipStrategy

    motive = RelationshipStrategy(MagicMock())

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
                role_runtime_registry=MagicMock(),
            ),
        ),
        proactive_gates=[proactive_gate],
        proactive_motives=[motive],
        event_bus=event_bus,
    )

    assert tasks == ["run:mira", "run:luna"]
    assert set(loops) == {"mira", "luna"}
    assert not hasattr(loops["mira"].config, "agent_tick_model")
    assert loops["mira"].config.tick_interval_s0 == 480
    assert not hasattr(loops["luna"].config, "agent_tick_model")
    assert loops["luna"].config.tick_interval_s0 == 1800
    assert loops["luna"].config.drift_enabled is True
    assert loops["luna"].config.drift_min_interval_hours == 7
    assert (
        created[0]["state_store"].db_path
        == tmp_path / "roles" / "mira" / "proactive.db"
    )
    assert (
        created[1]["state_store"].db_path
        == tmp_path / "roles" / "luna" / "proactive.db"
    )
    assert created[0]["event_bus"] is event_bus
    assert created[1]["event_bus"] is event_bus
    assert created[0]["proactive_gates"] == [proactive_gate]
    assert created[1]["proactive_gates"] == [proactive_gate]
    assert created[0]["proactive_motives"] == [motive]
    assert created[1]["proactive_motives"] == [motive]


def test_bootstrap_proactive_builders_cover_enabled_and_disabled_paths(
    monkeypatch, tmp_path
):
    config = Config(
        provider="openai",
        model="m",
        api_key="",
        base_url="http://localhost:11434/v1",
        proactive=ProactiveConfig(enabled=True),
        memory_optimizer_enabled=False,
        memory_optimizer_interval_seconds=7200,
        max_tokens=128,
    )
    agent_loop = MagicMock(processing_state=None)
    dependencies = {
        "session_manager": MagicMock(),
        "provider": MagicMock(),
        "light_provider": None,
        "push_tool": MagicMock(),
        "memory_store": None,
        "presence": MagicMock(),
        "agent_loop": agent_loop,
    }
    tasks, loops = build_proactive_runtime(config, tmp_path, **dependencies)
    assert tasks == [] and loops == {}

    memory_store = MagicMock(memory_dir=tmp_path / "memory")
    mem_tasks, optimizer = build_memory_optimizer_task(
        config,
        provider=dependencies["provider"],
        memory_store=memory_store,
    )
    assert mem_tasks == [] and optimizer is None

    store = RoleStore(tmp_path)
    store.create_role(name="Mira", role_id="mira", system_prompt="Role prompt")
    store.update_role(
        "mira",
        channel_bindings=[
            {
                "channel": "telegram",
                "chat_id": "42",
                "chat_type": "private",
                "allow_from": ["42"],
            }
        ],
        proactive={
            "enabled": True,
            "target_channel": "telegram",
            "target_chat_id": "42",
        },
    )
    proactive_loop = MagicMock()
    proactive_loop.run.return_value = "loop-task"
    monkeypatch.setattr(
        "bootstrap.proactive.ProactiveLoop", MagicMock(return_value=proactive_loop)
    )
    optimizer_loop = MagicMock()
    optimizer_loop.run.return_value = "mem-task"
    create_optimizer_loop = MagicMock(return_value=optimizer_loop)
    monkeypatch.setattr(
        "bootstrap.proactive.MemoryOptimizerLoop", create_optimizer_loop
    )
    create_optimizer = MagicMock()
    monkeypatch.setattr("bootstrap.proactive.MemoryOptimizer", create_optimizer)

    config.memory_optimizer_enabled = True
    agent_loop.processing_state = MagicMock()
    dependencies["light_provider"] = MagicMock()
    dependencies["memory_store"] = MagicMock()
    tasks, loops = build_proactive_runtime(config, tmp_path, **dependencies)
    assert tasks == ["loop-task"] and loops == {"mira": proactive_loop}
    mem_tasks, optimizer = build_memory_optimizer_task(
        config,
        provider=dependencies["provider"],
        memory_store=memory_store,
    )
    assert mem_tasks == ["mem-task"]
    assert optimizer is create_optimizer.return_value
    create_optimizer_loop.assert_called_once_with(optimizer, interval_seconds=7200)
    assert create_optimizer.call_args.kwargs["memory"] is memory_store

    config.model_registrations = []
    mem_tasks, optimizer = build_memory_optimizer_task(
        config,
        provider=dependencies["provider"],
        memory_store=memory_store,
    )
    assert mem_tasks == [] and optimizer is None
    create_optimizer.assert_called_once()
