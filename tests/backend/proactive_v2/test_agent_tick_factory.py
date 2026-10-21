from __future__ import annotations

import json

from core.roles.reply_state import RoleReplyContext
from typing import Any, cast

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from proactive_v2.agent_tick_factory import AgentTickDeps, AgentTickFactory
from proactive_v2.config import ProactiveConfig
from proactive_v2.config_loader import load_proactive_config
from proactive_v2.context import AgentTickContext
from proactive_v2.gateway import GatewayResult
from proactive_v2.mcp_sources import McpClientPool
from bootstrap.proactive import build_proactive_runtime
from core.desktop_presence import DesktopPresence


class _FakeProvider:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(tool_calls=[], content="")


def _build_deps(*, with_pool: bool):
    cfg = SimpleNamespace(
        role_id="",
        agent_tick_web_fetch_max_chars=4000,
        message_dedupe_recent_n=3,
    )
    # Like Sensor: the session key follows whichever config the test installs.
    sense = SimpleNamespace(
        target_session_key=lambda: (
            f"role:{deps.cfg.role_id}" if deps.cfg.role_id else ""
        ),
        target_transport=lambda: ("telegram", "1"),
        collect_recent=lambda: [],
        collect_recent_proactive=lambda n: [],
    )
    deps = AgentTickDeps(
        cfg=cfg,
        sense=sense,
        presence=SimpleNamespace(get_last_user_at=lambda _: None),
        provider=_FakeProvider(),
        model="m",
        max_tokens=128,
        memory=None,
        state_store=SimpleNamespace(),
        any_action_gate=SimpleNamespace(),
        passive_busy_fn=None,
        deduper=None,
        rng=SimpleNamespace(),
        workspace_context_fn=lambda: "",
        role_prompt_fn=lambda: "测试角色提示词",
        pool=McpClientPool() if with_pool else None,
    )
    return deps


def test_agent_tick_factory_build_requires_pool():
    deps = _build_deps(with_pool=False)
    try:
        AgentTickFactory(deps).build()
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "pool 不能为空" in str(e)


def test_agent_tick_factory_build_returns_tick():
    deps = _build_deps(with_pool=True)
    deps.cfg.role_id = "mira"
    tick = AgentTickFactory(deps).build()
    assert tick is not None


def test_agent_tick_factory_prefers_role_session_key_when_role_id_present():
    deps = _build_deps(with_pool=True)
    deps.cfg.role_id = "mira"
    tick = AgentTickFactory(deps).build()
    assert tick._session_key == "role:mira"


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("legacy_drift_enabled", [None, False, True])
def test_agent_tick_factory_builds_drift_only_when_main_switch_is_enabled(
    tmp_path, enabled, legacy_drift_enabled
):
    deps = _build_deps(with_pool=True)
    drift = {"max_steps": 9}
    if legacy_drift_enabled is not None:
        drift["enabled"] = legacy_drift_enabled
    deps.cfg = load_proactive_config(
        {"enabled": enabled, "profile": "daily", "drift": drift},
        role_id="mira",
    )
    deps.state_store = SimpleNamespace(workspace_dir=tmp_path)
    deps.any_action_gate = SimpleNamespace()
    tick = AgentTickFactory(deps).build()
    if enabled:
        assert tick._drift_pipeline is not None
        assert tick._drift_pipeline._store.drift_dir == tmp_path / "drift"
        assert tick._drift_pipeline._max_steps == 9
    else:
        assert tick._drift_pipeline is None


def test_agent_tick_factory_binds_drift_step_recorder_to_tick_store(tmp_path):
    deps = _build_deps(with_pool=True)
    deps.cfg = ProactiveConfig(
        role_id="mira",
        drift_enabled=True,
    )
    state_store = SimpleNamespace(
        workspace_dir=tmp_path,
        record_tick_step_log=MagicMock(),
    )
    deps.state_store = state_store

    tick = AgentTickFactory(deps).build()
    assert tick._drift_pipeline is not None
    assert tick._drift_pipeline.step_recorder is not None

    ctx = AgentTickContext(
        reply_context=RoleReplyContext(("平静",), ""),
        tick_id="tick1",
        session_key="telegram:1",
    )
    ctx.steps_taken = 3
    tick._drift_pipeline.step_recorder(
        ctx,
        "drift",
        "read_file",
        "call1",
        {"path": "x"},
        "ok",
    )

    state_store.record_tick_step_log.assert_called_once()
    kwargs = state_store.record_tick_step_log.call_args.kwargs
    assert kwargs["tick_id"] == "tick1"
    assert kwargs["step_index"] == 3
    assert kwargs["phase"] == "drift"
    assert kwargs["tool_name"] == "read_file"


def test_agent_tick_factory_requires_role_id():
    deps = _build_deps(with_pool=True)
    try:
        AgentTickFactory(deps).build()
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "role_id required for proactive session key" in str(e)


def test_build_proactive_runtime_accepts_light_agent_loop_stub(tmp_path):
    cfg = SimpleNamespace(
        proactive=SimpleNamespace(
            enabled=False,
        ),
        fitbit=SimpleNamespace(enabled=False),
        memory_optimizer_enabled=False,
        memory_optimizer_interval_seconds=3600,
        model="m",
        max_tokens=128,
        light_model="lm",
    )
    tasks, loops = build_proactive_runtime(
        cast(Any, cfg),
        tmp_path,
        session_manager=cast(Any, SimpleNamespace()),
        provider=cast(Any, SimpleNamespace()),
        light_provider=None,
        push_tool=cast(Any, SimpleNamespace()),
        memory_store=None,
        presence=cast(Any, SimpleNamespace()),
        agent_loop=cast(Any, SimpleNamespace(processing_state=None)),
        desktop_presence=DesktopPresence(),
        group_environment=cast(Any, SimpleNamespace()),
    )
    assert tasks == []
    assert loops == {}


async def test_agent_tick_factory_llm_fn_forces_disable_thinking():
    deps = _build_deps(with_pool=True)
    deps.cfg.role_id = "mira"
    provider = deps.provider
    tick = AgentTickFactory(deps).build()

    await tick._llm_fn(
        messages=[{"role": "user", "content": "hi"}],
        schemas=[{"type": "function"}],
        tool_choice="required",
        disable_thinking=True,
    )

    assert provider.calls[-1]["disable_thinking"] is True


async def test_agent_tick_factory_llm_fn_honors_disable_thinking_without_schemas():
    deps = _build_deps(with_pool=True)
    deps.cfg.role_id = "mira"
    provider = deps.provider
    tick = AgentTickFactory(deps).build()

    await tick._llm_fn(
        messages=[{"role": "user", "content": "hi"}],
        schemas=[],
        disable_thinking=True,
    )

    assert provider.calls[-1]["disable_thinking"] is True


def test_agent_tick_factory_feeds_the_affection_block_to_proactive_and_drift(
    tmp_path,
):
    deps = _build_deps(with_pool=True)
    deps.cfg.role_id = "mira"
    deps.cfg.drift_enabled = True
    deps.state_store = SimpleNamespace(workspace_dir=tmp_path)
    deps.affection_prompt_fn = (
        lambda: "## 好感度\n你对用户的好感：70（亲密，范围 -100 到 100）"
    )
    tick = AgentTickFactory(deps).build()

    frame = tick._build_runtime_context_message(
        AgentTickContext(session_key="role:mira"), GatewayResult()
    )

    assert "70（亲密，范围 -100 到 100）" in frame["content"]
    assert "70/100" not in tick._build_system_prompt()
    drift = tick._drift_pipeline
    assert drift is not None
    assert drift._tool_deps.affection_prompt_fn is deps.affection_prompt_fn


@pytest.mark.parametrize("needs_correction", [False, True])
async def test_natural_drift_uses_shared_messages_and_preserves_thinking(
    tmp_path, monkeypatch, needs_correction
):
    from unittest.mock import AsyncMock, Mock
    from agent.provider import LLMResponse, ToolCall
    from agent.looping.ports import SessionServices
    from agent.turns.channel_sequence import ChannelSequenceOwner
    from agent.turns.orchestrator import TurnOrchestrator, TurnOrchestratorDeps
    from agent.turns.outbound import DeliveryReceipt
    from agent.turns.proactive_sequence import current_proactive_reply
    from bus.queue import MessageBus
    from proactive_v2.tools import ToolDeps
    from session.manager import SessionManager

    manager = SessionManager(tmp_path)
    manager.get_or_create("role:mira").metadata.update(
        role_id="mira", role_runtime_config={"natural_chat_enabled": True}
    )
    dispatch = AsyncMock(return_value=DeliveryReceipt.sent())
    owner = TurnOrchestrator(
        TurnOrchestratorDeps(
            session=SessionServices(manager),
            outbound=SimpleNamespace(dispatch=dispatch),
        )
    )
    deps = _build_deps(with_pool=True)
    deps.cfg.role_id = "mira"
    deps.cfg.drift_enabled = True
    deps.sense.target_transport = lambda: ("desktop", "role:mira")
    deps.state_store = SimpleNamespace(workspace_dir=tmp_path, mark_delivery=Mock())
    deps.turn_orchestrator = owner
    expected = [
        "刚想到你。",
        "示例里的 <message-break/> 是原文。\n```python\nprint('hello')",
    ]
    raw = '{"messages":' + json.dumps(expected, ensure_ascii=False) + "}"
    requests = []

    async def chat(**kwargs):
        requests.append(kwargs)
        names = [tool["function"]["name"] for tool in kwargs["tools"]]
        if names == ["finish_reply"]:
            return LLMResponse(
                "",
                [ToolCall("fixed", "finish_reply", {"messages": expected}, raw)],
                total_tokens=7,
            )
        if len(requests) == 1:
            return LLMResponse(
                "",
                [
                    ToolCall(
                        "draft",
                        "message_push",
                        {
                            "messages": [] if needs_correction else expected,
                            "mood": "平静",
                            "thought": "我想和你分享。",
                        },
                        raw if not needs_correction else None,
                    )
                ],
                thinking="保留正常思考",
                total_tokens=11,
            )
        return LLMResponse(
            "",
            [
                ToolCall(
                    "done",
                    "finish_drift",
                    {
                        "skill_used": "meme-manage",
                        "one_line": "已分享",
                        "next": "等待新想法",
                        "message_result": "sent",
                    },
                )
            ],
        )

    deps.provider = SimpleNamespace(chat=chat)
    factory = AgentTickFactory(deps)
    drift = factory._build_drift_pipeline(ToolDeps())
    assert drift is not None
    ctx = AgentTickContext(
        session_key="role:mira", reply_context=owner.capture_reply_context("role:mira")
    )
    monkeypatch.setattr("agent.turns.reply_sequence.wait_between_messages", AsyncMock())
    with ChannelSequenceOwner().bind(MessageBus()):
        async with owner.natural_reply_scope(
            "role:mira", "desktop", "role:mira", turn_id="drift:test"
        ):
            assert await drift.run(ctx, factory._build_llm_fn())
            plan = current_proactive_reply()
            assert plan is not None and plan.completion is not None
            assert plan.protocol.reply is not None
            assert plan.protocol.reply.raw_text == raw
            assert plan.completion.response.thinking == "保留正常思考"
            assert plan.completion.total_tokens == (18 if needs_correction else 11)
    assert ctx.drift_finished and ctx.drift_message_sent
    assert [call.args[0].content for call in dispatch.await_args_list] == expected
    rows = SessionManager(tmp_path).get_or_create("role:mira").messages
    assert [row["content"] for row in rows] == expected
    assert rows[0]["reasoning_content"] == "保留正常思考"
    assert "reasoning_content" not in rows[1]
    assert len({row["metadata"]["reply_sequence_id"] for row in rows}) == 1
    deps.state_store.mark_delivery.assert_called_once()
    normal = [r for r in requests if r.get("call_purpose") != "auxiliary"]
    assert len(normal) == 2
    assert all(
        r["disable_thinking"] is False and r["tool_choice"] == "auto" for r in normal
    )
    corrections = [r for r in requests if r.get("call_purpose") == "auxiliary"]
    assert len(corrections) == int(needs_correction)
    assert all(
        [t["function"]["name"] for t in r["tools"]] == ["finish_reply"]
        for r in corrections
    )
    schema = next(
        t["function"]
        for t in requests[0]["tools"]
        if t["function"]["name"] == "message_push"
    )
    assert "messages" in schema["parameters"]["required"]
    assert "message" not in schema["parameters"]["properties"]
